#!/usr/bin/env python3
"""
基础功能测试
"""
import requests
import os
from dotenv import load_dotenv

load_dotenv()

def test_health_check():
    """测试健康检查接口"""
    try:
        response = requests.get("http://localhost:8000/healthz")
        print(f"健康检查: {response.status_code}")
        if response.status_code == 200:
            print("✅ 服务运行正常")
        else:
            print("❌ 服务异常")
    except Exception as e:
        print(f"❌ 连接失败: {e}")

def test_video_api():
    """测试视频解析接口"""
    secret_key = os.getenv("SECRET_KEY", "test-secret-key-2024")
    
    try:
        response = requests.get(
            "http://localhost:8000/v1/video/dQw4w9WgXcQ",
            headers={"X-Secret": secret_key}
        )
        print(f"视频解析: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 解析成功: {data.get('title', 'Unknown')}")
        else:
            print(f"❌ 解析失败: {response.text}")
    except Exception as e:
        print(f"❌ 请求失败: {e}")

if __name__ == "__main__":
    print("🧪 开始基础功能测试...")
    test_health_check()
    test_video_api()
    print("🏁 测试完成")
