import json
import time
import base64
import os
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
# 尝试导入具体的客户端，如果不存在则使用通用客户端
# from tencentcloud.hunyuan.v20230901 import hunyuan_client, models

def get_image_base64(file_path):
    with open(file_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    return encoded_string

def call_hunyuan_3d_api(secret_id, secret_key, image_path):
    try:
        # 实例化一个认证对象，入参需要传入腾讯云账户 SecretId 和 SecretKey
        cred = credential.Credential(secret_id, secret_key)

        # 实例化一个http选项，可选的，没有特殊需求可以跳过
        httpProfile = HttpProfile()
        httpProfile.endpoint = "hunyuan.tencentcloudapi.com"  # 确认Endpoint，通常是这个

        # 实例化一个client选项，可选的
        clientProfile = ClientProfile()
        clientProfile.httpProfile = httpProfile

        # 实例化要请求产品的client对象, clientProfile是可选的
        # 这里我们使用通用调用方式 (Common Client)，因为它不需要特定版本的SDK包，
        # 只要知道 Action 和 Version 即可。
        # Service: hunyuan, Version: 2023-09-01 (假设版本，需根据实际文档确认)
        from tencentcloud.common.common_client import CommonClient
        client = CommonClient("hunyuan", "2023-09-01", cred, "ap-guangzhou", clientProfile)

        # 1. 提交任务
        print(f"正在提交图片: {image_path} ...")
        img_base64 = get_image_base64(image_path)
        
        # 构造请求参数
        # 注意：具体的参数名称 (Params) 需要参考您提供的文档链接。
        # 根据搜索结果推测，Action 为 SubmitHunyuan3DJob 或类似名称
        # 参数通常包含 ImageBase64 或 ImageUrl
        params = {
            "ImageBase64": img_base64,
            # "Prompt": "optional text prompt if needed" 
        }
        
        # 调用接口
        # 替换为实际的 Action 名称，例如 "SubmitHunyuan3DJob" 或 "SubmitHunyuanTo3DJob"
        # 根据搜索到的信息，"SubmitHunyuanTo3DJob" 可能性较大
        action_submit = "SubmitHunyuanTo3DJob" 
        response_submit = client.call_json(action_submit, params)
        
        print("任务提交响应:", response_submit)
        
        if "Response" not in response_submit:
            print("提交失败，未获取到Response")
            return

        # 获取 JobId
        job_id = response_submit["Response"].get("JobId")
        if not job_id:
            print("未获取到 JobId")
            return
            
        print(f"任务提交成功，JobId: {job_id}")
        
        # 2. 轮询结果
        action_query = "QueryHunyuanTo3DJob" # 替换为实际的查询 Action
        
        while True:
            print("正在查询任务状态...")
            query_params = {
                "JobId": job_id
            }
            response_query = client.call_json(action_query, query_params)
            
            # 解析状态
            # 假设返回结构中有 Status: "RUNNING" | "SUCCESS" | "FAILED"
            # 具体字段需参考文档
            data = response_query.get("Response", {})
            status = data.get("Status")
            
            print(f"当前状态: {status}")
            
            if status == "SUCCESS" or status == "DONE":
                print("生成成功！")
                # 打印完整数据以便调试
                print("完整响应数据:", json.dumps(data, indent=2, ensure_ascii=False))
                
                # result_url = data.get("ResultUrl") 
                # if result_url:
                #     print(f"3D模型下载链接: {result_url}")
                # else:
                #     print("未找到 ResultUrl 字段，请检查上方完整响应数据中的链接字段。")
                
                # 解析 ResultFile3Ds 结构
                result_files = data.get("ResultFile3Ds", [])
                if result_files:
                    # 遍历查找 OBJ 或 GLB 类型的文件
                    found_model = False
                    for item in result_files:
                        file_3d_list = item.get("File3D", [])
                        for file_info in file_3d_list:
                            file_type = file_info.get("Type")
                            file_url = file_info.get("Url")
                            
                            if file_type in ["OBJ", "GLB"]:
                                print(f"找到 3D 模型 ({file_type}): {file_url}")
                                found_model = True
                            elif file_type == "GIF":
                                print(f"找到预览 GIF: {file_url}")
                                
                    if not found_model:
                        print("未找到 OBJ 或 GLB 格式的 3D 模型文件。")
                else:
                    print("未找到 ResultFile3Ds 字段。")
                
                break
            elif status == "FAILED":
                print("生成失败。")
                print(data)
                break
            
            time.sleep(5) # 等待5秒再次查询

    except TencentCloudSDKException as err:
        print(f"腾讯云SDK异常: {err}")
    except Exception as err:
        print(f"其他异常: {err}")

if __name__ == "__main__":
    # 配置您的密钥
    # 建议从环境变量获取，或者直接在此处填入（注意不要泄露）
    SECRET_ID = os.environ.get("TENCENTCLOUD_SECRET_ID", "AKID9GByeAWhongS7j0yrdHpHdqxwpchs3DK")
    SECRET_KEY = os.environ.get("TENCENTCLOUD_SECRET_KEY", "66xhLsHYk2CE6tGZov592kHdrDVuW4Vo")
    
    # 图片路径
    IMAGE_PATH = "test_image.jpg" 
    
    if not os.path.exists(IMAGE_PATH):
        print(f"请准备一张测试图片并保存为 {IMAGE_PATH}")
    else:
        call_hunyuan_3d_api(SECRET_ID, SECRET_KEY, IMAGE_PATH)
