from flask import Flask, request, jsonify, render_template, send_from_directory
import os
import json
import time
import base64
import requests
import zipfile
import shutil
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.common_client import CommonClient
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MODEL_FOLDER'] = 'static/models'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['MODEL_FOLDER'], exist_ok=True)

import http.client

# 配置您的密钥
SECRET_ID = os.environ.get("TENCENTCLOUD_SECRET_ID", "AKID9GByeAWhongS7j0yrdHpHdqxwpchs3DK")
SECRET_KEY = os.environ.get("TENCENTCLOUD_SECRET_KEY", "66xhLsHYk2CE6tGZov592kHdrDVuW4Vo")
VECTOR_ENGINE_API_KEY = os.environ.get("VECTOR_ENGINE_API_KEY", "") # 稍后请手动填入或设置环境变量

def get_image_base64(file_path):
    with open(file_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    return encoded_string

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate_image', methods=['POST'])
def generate_image():
    data = request.json
    prompt = data.get('prompt')
    api_key = data.get('api_key') or VECTOR_ENGINE_API_KEY # 优先使用前端传来的Key，其次是环境变量

    if not prompt:
        return jsonify({'error': 'No prompt provided'})
    if not api_key:
        return jsonify({'error': 'No API Key provided'})

    try:
        conn = http.client.HTTPSConnection("api.vectorengine.ai")
        payload = json.dumps({
            "size": "1024x1024", # 调整为正方形以适应通常的 3D 输入需求
            "prompt": prompt,
            "model": "gpt-image-1",
            "n": 1,
            "response_format": "b64_json" # 显式请求 b64_json 格式
        })
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        conn.request("POST", "/v1/images/generations", payload, headers)
        res = conn.getresponse()
        data = res.read()
        response_data = json.loads(data.decode("utf-8"))
        
        # Check for explicit error from API
        if 'error' in response_data:
            error_msg = response_data['error']
            if isinstance(error_msg, dict) and 'message' in error_msg:
                return jsonify({'error': f"API Error: {error_msg['message']}", 'details': response_data})
            return jsonify({'error': f"API Error: {str(error_msg)}", 'details': response_data})

        # 打印 API 响应以调试 (省略过长的 Base64)
        debug_data = response_data.copy()
        if 'data' in debug_data and isinstance(debug_data['data'], list):
            for item in debug_data['data']:
                if 'b64_json' in item:
                    item['b64_json'] = item['b64_json'][:50] + "..." # 截断显示
        print("Vector Engine API Response:", json.dumps(debug_data, indent=2))
        
        # 尝试解析 URL
        image_url = None
        
        # 深度调试
        if 'data' in response_data:
            print(f"Data field found. Type: {type(response_data['data'])}")
            if isinstance(response_data['data'], list) and len(response_data['data']) > 0:
                item = response_data['data'][0]
                print(f"First item keys: {item.keys()}")
                if 'url' in item:
                    image_url = item['url']
                    print("Found URL in data[0]['url']")
                elif 'image_url' in item:
                    image_url = item['image_url']
                    print("Found URL in data[0]['image_url']")
                elif 'b64_json' in item:
                    # 处理 b64_json 字段
                    b64_data = item['b64_json']
                    # 补充前缀以适配后续逻辑
                    if not b64_data.startswith("data:image"):
                         # 关键修复：这里直接保存纯 base64 字符串，不加前缀，因为下面解码时会自己拆分
                         # 或者如果我们要加前缀，下面的 split 就要对应
                         # 为了稳妥，我们在这里模拟成一个 data URI
                         image_url = f"data:image/png;base64,{b64_data}"
                    else:
                         image_url = b64_data
                    print("Found URL in data[0]['b64_json']")
            else:
                print("Data field is empty or not a list")
        
        # 如果上面没找到，尝试在根目录找
        if not image_url:
            if 'url' in response_data:
                image_url = response_data['url']
                print("Found URL in root['url']")
            elif 'image_url' in response_data:
                image_url = response_data['image_url']
                print("Found URL in root['image_url']")
            
        if image_url:
            print(f"Final Image URL (prefix): {image_url[:50]}...")
            filename = f"gen_{int(time.time())}.png"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            # 处理 Base64 Data URI
            if image_url.startswith("data:image"):
                # 格式通常是 data:image/png;base64,xxxxxx...
                try:
                    header, encoded = image_url.split(",", 1)
                    # Fix padding and clean string
                    encoded = encoded.strip().replace("\n", "").replace("\r", "").replace(" ", "")
                    
                    # Add padding if needed
                    missing_padding = len(encoded) % 4
                    if missing_padding:
                        encoded += '=' * (4 - missing_padding)
                    
                    img_data = base64.b64decode(encoded)
                    with open(file_path, 'wb') as f:
                        f.write(img_data)
                except Exception as e:
                    return jsonify({'error': f'Failed to decode base64 image: {str(e)}'})
            else:
                # 处理普通 HTTP 链接
                img_response = requests.get(image_url)
                with open(file_path, 'wb') as f:
                    f.write(img_response.content)
                
            return jsonify({
                'status': 'success',
                'image_url': image_url[:100] + "..." if len(image_url) > 100 else image_url, # 避免返回过长的 Base64
                'local_image_url': f'/static/uploads/{filename}', # 本地链接
                'filename': filename
            })
        else:
            return jsonify({'error': 'Failed to parse image URL from response', 'details': response_data})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)})

@app.route('/list_models', methods=['GET'])
def list_models():
    models = []
    models_dir = app.config['MODEL_FOLDER']
    if os.path.exists(models_dir):
        # Iterate over job ID folders
        for job_id in os.listdir(models_dir):
            job_path = os.path.join(models_dir, job_id)
            if os.path.isdir(job_path):
                # Look for obj and mtl inside
                obj_file = None
                mtl_file = None
                metadata = {}
                
                # Try load metadata
                meta_path = os.path.join(job_path, "metadata.json")
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                    except:
                        pass

                for root, dirs, files in os.walk(job_path):
                    for f in files:
                        if f.lower().endswith('.obj'):
                            rel_path = os.path.relpath(os.path.join(root, f), 'static')
                            obj_file = rel_path.replace('\\', '/')
                        elif f.lower().endswith('.mtl'):
                            rel_path = os.path.relpath(os.path.join(root, f), 'static')
                            mtl_file = rel_path.replace('\\', '/')
                
                if obj_file:
                    models.append({
                        'id': job_id,
                        'name': metadata.get('title', f"Memory {job_id[:4]}"), # Use title from metadata
                        'date': metadata.get('date', time.strftime('%Y-%m-%d', time.localtime(os.path.getctime(job_path)))), # User date or file date
                        'obj_url': f'/static/{obj_file}',
                        'mtl_url': f'/static/{mtl_file}' if mtl_file else None,
                        'created_at': os.path.getctime(job_path) 
                    })
    
    # Sort by user assigned date (newest first)
    models.sort(key=lambda x: x['date'], reverse=True)
    
    return jsonify({'models': models})

@app.route('/update_model', methods=['POST'])
def update_model():
    data = request.json
    model_id = data.get('id')
    new_title = data.get('title')
    new_date = data.get('date')
    
    if not model_id:
        return jsonify({'error': 'Missing model ID'})
        
    job_folder = os.path.join(app.config['MODEL_FOLDER'], model_id)
    if not os.path.exists(job_folder):
        return jsonify({'error': 'Model not found'})
        
    meta_path = os.path.join(job_folder, "metadata.json")
    metadata = {}
    
    # Read existing
    if os.path.exists(meta_path):
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        except:
            pass
            
    # Update
    if new_title:
        metadata['title'] = new_title
    if new_date:
        metadata['date'] = new_date
        
    # Save
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f)
        
    return jsonify({'status': 'success'})

@app.route('/diary', methods=['GET', 'POST'])
def handle_diary():
    diary_folder = os.path.join('static', 'diaries')
    os.makedirs(diary_folder, exist_ok=True)
    
    if request.method == 'POST':
        data = request.json
        date = data.get('date')
        content = data.get('content')
        
        if not date:
            return jsonify({'error': 'Date required'})
            
        file_path = os.path.join(diary_folder, f"{date}.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump({'date': date, 'content': content, 'updated_at': time.time()}, f)
            
        return jsonify({'status': 'success'})
        
    else: # GET
        date = request.args.get('date')
        if not date:
            return jsonify({'error': 'Date required'})
            
        file_path = os.path.join(diary_folder, f"{date}.json")
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        else:
            return jsonify({'date': date, 'content': ''})

@app.route('/upload', methods=['POST'])
def upload_file():
    file_path = None
    
    # Get Metadata
    memory_date = request.form.get('date', time.strftime('%Y-%m-%d'))
    memory_title = request.form.get('title', 'Untitled Memory')

    # 检查是上传文件还是使用已生成的文件
    if 'filename' in request.form:
        # 使用刚刚生成的图片
        filename = request.form['filename']
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'})
    elif 'file' in request.files:
        # 上传新图片
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No selected file'})
        if file:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
    else:
         return jsonify({'error': 'No file part or filename provided'})

    if file_path:
        try:
            # 1. 提交任务
            cred = credential.Credential(SECRET_ID, SECRET_KEY)
            httpProfile = HttpProfile()
            httpProfile.endpoint = "hunyuan.tencentcloudapi.com"
            clientProfile = ClientProfile()
            clientProfile.httpProfile = httpProfile
            client = CommonClient("hunyuan", "2023-09-01", cred, "ap-guangzhou", clientProfile)

            img_base64 = get_image_base64(file_path)
            params = {
                "ImageBase64": img_base64,
            }
            
            # 使用正确的 Action
            response_submit = client.call_json("SubmitHunyuanTo3DJob", params)
            
            if "Response" not in response_submit or "JobId" not in response_submit["Response"]:
                return jsonify({'error': 'Failed to submit job', 'details': response_submit})
            
            job_id = response_submit["Response"]["JobId"]
            
            # 2. 轮询结果
            # 为了简单起见，这里是阻塞的，实际生产中应该用异步任务 (Celery/Redis)
            # 但为了快速展示 MVP，我们在后端循环等待
            status = "RUNNING"
            result_data = None
            
            # 最多等待 5 分钟
            for _ in range(60):
                response_query = client.call_json("QueryHunyuanTo3DJob", {"JobId": job_id})
                data = response_query.get("Response", {})
                status = data.get("Status")
                
                if status == "SUCCESS" or status == "DONE":
                    result_data = data
                    break
                elif status == "FAILED":
                    return jsonify({'error': 'Job failed', 'details': data})
                
                time.sleep(5)
            
            if not result_data:
                return jsonify({'error': 'Timeout waiting for job'})
            
            # 3. 处理结果
            model_url = None
            result_files = result_data.get("ResultFile3Ds", [])
            for item in result_files:
                file_3d_list = item.get("File3D", [])
                for file_info in file_3d_list:
                    if file_info.get("Type") in ["OBJ", "GLB"]:
                        model_url = file_info.get("Url")
                        break
                if model_url:
                    break
            
            if not model_url:
                return jsonify({'error': 'No 3D model found in result'})
            
            # 4. 下载并解压
            job_folder = os.path.join(app.config['MODEL_FOLDER'], job_id)
            os.makedirs(job_folder, exist_ok=True)
            
            # 保存元数据
            meta_path = os.path.join(job_folder, "metadata.json")
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "title": memory_title,
                    "date": memory_date,
                    "created_at": time.time()
                }, f)
            
            zip_path = os.path.join(job_folder, "model.zip")
            
            # 下载 Zip
            r = requests.get(model_url)
            with open(zip_path, 'wb') as f:
                f.write(r.content)
            
            # 解压
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(job_folder)
            
            # 查找 obj 文件和 mtl 文件
            obj_file = None
            mtl_file = None
            for root, dirs, files in os.walk(job_folder):
                for f in files:
                    if f.lower().endswith('.obj'):
                        # 返回相对于 static 的路径
                        rel_path = os.path.relpath(os.path.join(root, f), 'static')
                        # 统一使用 forward slash for web
                        obj_file = rel_path.replace('\\', '/')
                    elif f.lower().endswith('.mtl'):
                        rel_path = os.path.relpath(os.path.join(root, f), 'static')
                        mtl_file = rel_path.replace('\\', '/')

            return jsonify({
                'status': 'success',
                'obj_url': f'/static/{obj_file}',
                'mtl_url': f'/static/{mtl_file}' if mtl_file else None
            })

        except Exception as e:
            return jsonify({'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
