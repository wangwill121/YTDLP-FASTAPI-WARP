#!/usr/bin/env python3
"""
测试 Railway 上部署的 WARP 功能
通过 HTTP API 调用来检查 WARP 是否在容器中正常工作
"""

import asyncio
import aiohttp
import json
import sys
from datetime import datetime

# Railway 部署的 URL
RAILWAY_URL = "https://web-production-90e87.up.railway.app"

async def test_health():
    """测试基本健康检查"""
    print("🔍 测试基本健康检查...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{RAILWAY_URL}/healthz") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ 健康检查: {data}")
                    return True
                else:
                    print(f"❌ 健康检查失败: HTTP {response.status}")
                    return False
    except Exception as e:
        print(f"❌ 健康检查异常: {e}")
        return False

async def test_ip_check():
    """测试 IP 检查接口"""
    print("\n🔍 测试 IP 检查接口...")
    
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get(f"{RAILWAY_URL}/ip-check") as response:
                if response.status == 200:
                    data = await response.json()
                    print("✅ IP 检查接口调用成功")
                    
                    # 分析结果
                    container_ips = data.get("container_ips", {})
                    warp_analysis = data.get("warp_analysis", {})
                    
                    print(f"📊 获取到的 IP: {container_ips.get('successful_ips', [])}")
                    print(f"🌐 WARP 状态: {warp_analysis.get('warp_status', 'UNKNOWN')}")
                    print(f"💡 建议: {data.get('recommendation', '无建议')}")
                    
                    if warp_analysis.get("is_cloudflare_ip", False):
                        print("🎉 检测到 WARP 已启用!")
                    else:
                        print("⚠️ 未检测到 WARP")
                    
                    return data
                elif response.status == 404:
                    print("❌ IP 检查接口不存在 (可能需要重新部署)")
                    return None
                else:
                    print(f"❌ IP 检查失败: HTTP {response.status}")
                    text = await response.text()
                    print(f"错误详情: {text}")
                    return None
    except Exception as e:
        print(f"❌ IP 检查异常: {e}")
        return None

async def test_warp_test():
    """测试 WARP 连接测试接口"""
    print("\n🎥 测试 WARP 连接测试接口...")
    
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            async with session.get(f"{RAILWAY_URL}/warp-test") as response:
                if response.status == 200:
                    data = await response.json()
                    print("✅ WARP 测试接口调用成功")
                    
                    # 分析结果
                    summary = data.get("summary", {})
                    tests = data.get("tests", [])
                    
                    print(f"📊 测试统计: {summary.get('successful')}/{summary.get('total_tests')} 成功")
                    print(f"🌐 WARP 工作状态: {'正常' if summary.get('warp_working') else '异常'}")
                    print(f"📡 直连工作状态: {'正常' if summary.get('direct_working') else '异常'}")
                    print(f"💡 建议: {summary.get('recommendation', '无建议')}")
                    
                    # 详细测试结果
                    for test in tests:
                        test_type = test.get("test_type", "unknown")
                        success = test.get("success", False)
                        proxy = test.get("proxy_used", "无")
                        time_taken = test.get("response_time", 0)
                        
                        status = "✅" if success else "❌"
                        print(f"{status} {test_type.upper()} 测试: {time_taken:.2f}s (代理: {proxy})")
                        
                        if not success and test.get("error"):
                            print(f"   错误: {test['error']}")
                    
                    return data
                elif response.status == 404:
                    print("❌ WARP 测试接口不存在 (可能需要重新部署)")
                    return None
                elif response.status == 503:
                    data = await response.json()
                    print(f"⚠️ WARP 功能不可用: {data.get('message', '未知原因')}")
                    return data
                else:
                    print(f"❌ WARP 测试失败: HTTP {response.status}")
                    text = await response.text()
                    print(f"错误详情: {text}")
                    return None
    except Exception as e:
        print(f"❌ WARP 测试异常: {e}")
        return None

async def test_warp_status():
    """测试 WARP 状态接口"""
    print("\n📊 测试 WARP 状态接口...")
    
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get(f"{RAILWAY_URL}/warp-status") as response:
                if response.status == 200:
                    data = await response.json()
                    print("✅ WARP 状态接口调用成功")
                    
                    # 分析结果
                    warp_manager = data.get("warp_manager", {})
                    proxy_pool = data.get("proxy_pool", {})
                    config_files = data.get("config_files", [])
                    
                    print(f"📁 配置管理器: {warp_manager.get('total_configs', 0)} 个配置")
                    print(f"✅ 有效配置: {warp_manager.get('valid_configs', 0)} 个")
                    print(f"❌ 无效配置: {warp_manager.get('invalid_configs', 0)} 个")
                    
                    if proxy_pool.get("status") == "initialized":
                        print(f"🌐 代理池: 已初始化 ({proxy_pool.get('total_proxies', 0)} 个代理)")
                    else:
                        print(f"⚠️ 代理池: {proxy_pool.get('status', '未知状态')}")
                    
                    return data
                elif response.status == 404:
                    print("❌ WARP 状态接口不存在 (可能需要重新部署)")
                    return None
                elif response.status == 503:
                    data = await response.json()
                    print(f"⚠️ WARP 功能不可用: {data.get('message', '未知原因')}")
                    return data
                else:
                    print(f"❌ WARP 状态查询失败: HTTP {response.status}")
                    text = await response.text()
                    print(f"错误详情: {text}")
                    return None
    except Exception as e:
        print(f"❌ WARP 状态查询异常: {e}")
        return None

async def test_video_api():
    """测试视频解析接口"""
    print("\n🎥 测试视频解析接口...")
    
    test_video_id = "dQw4w9WgXcQ"  # Rick Roll
    
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45)) as session:
            # 需要添加必要的头部信息
            headers = {
                "x-secret": "your-main-secret-key-2024"  # 使用配置文件中的默认密钥
            }
            
            async with session.get(f"{RAILWAY_URL}/v1/video/{test_video_id}", headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    print("✅ 视频解析成功")
                    
                    title = data.get("title", "未知标题")
                    duration = data.get("duration", 0)
                    video_url = data.get("video_url")
                    audio_url = data.get("audio_url")
                    
                    print(f"📹 标题: {title}")
                    print(f"⏱️ 时长: {duration} 秒")
                    print(f"🎥 视频链接: {'已获取' if video_url else '未获取'}")
                    print(f"🔊 音频链接: {'已获取' if audio_url else '未获取'}")
                    
                    # 检查处理时间
                    processing_time = response.headers.get("X-Processing-Time")
                    if processing_time:
                        print(f"⚡ 处理时间: {processing_time}s")
                    
                    return data
                elif response.status == 401:
                    print("❌ 视频解析失败: API 密钥无效")
                    return None
                else:
                    print(f"❌ 视频解析失败: HTTP {response.status}")
                    text = await response.text()
                    print(f"错误详情: {text}")
                    return None
    except Exception as e:
        print(f"❌ 视频解析异常: {e}")
        return None

async def main():
    """主测试函数"""
    print("🚀 开始测试 Railway 上的 WARP 功能...\n")
    
    # 测试结果收集
    results = {
        "timestamp": datetime.now().isoformat(),
        "railway_url": RAILWAY_URL,
        "tests": {}
    }
    
    # 1. 基本健康检查
    health_ok = await test_health()
    results["tests"]["health"] = health_ok
    
    if not health_ok:
        print("\n❌ 基本健康检查失败，终止测试")
        return
    
    # 2. IP 检查
    ip_result = await test_ip_check()
    results["tests"]["ip_check"] = ip_result
    
    # 3. WARP 连接测试
    warp_test_result = await test_warp_test()
    results["tests"]["warp_test"] = warp_test_result
    
    # 4. WARP 状态查询
    warp_status_result = await test_warp_status()
    results["tests"]["warp_status"] = warp_status_result
    
    # 5. 视频解析测试
    video_result = await test_video_api()
    results["tests"]["video_api"] = video_result
    
    # 生成最终报告
    print("\n" + "="*60)
    print("📋 Railway WARP 测试结果摘要:")
    print("="*60)
    
    # 接口可用性
    available_apis = 0
    total_apis = 4  # ip-check, warp-test, warp-status, video
    
    if ip_result is not None:
        available_apis += 1
        print("✅ IP 检查接口: 可用")
    else:
        print("❌ IP 检查接口: 不可用")
    
    if warp_test_result is not None:
        available_apis += 1
        print("✅ WARP 测试接口: 可用")
    else:
        print("❌ WARP 测试接口: 不可用")
    
    if warp_status_result is not None:
        available_apis += 1
        print("✅ WARP 状态接口: 可用")
    else:
        print("❌ WARP 状态接口: 不可用")
    
    if video_result is not None:
        available_apis += 1
        print("✅ 视频解析接口: 可用")
    else:
        print("❌ 视频解析接口: 不可用")
    
    print(f"\n📊 接口可用性: {available_apis}/{total_apis}")
    
    # WARP 功能分析
    if ip_result and ip_result.get("warp_analysis", {}).get("is_cloudflare_ip", False):
        print("🎉 WARP 状态: 已启用")
    else:
        print("⚠️ WARP 状态: 未启用或检测失败")
    
    # 建议
    print("\n💡 建议:")
    if available_apis == 0:
        print("❌ 需要重新部署应用以包含新的测试接口")
    elif ip_result and not ip_result.get("warp_analysis", {}).get("is_cloudflare_ip", False):
        print("⚠️ WARP 可能未正确配置，检查容器中的 WARP 配置文件")
    elif warp_test_result and not warp_test_result.get("summary", {}).get("warp_working", False):
        print("⚠️ WARP 代理池可能有问题，检查代理配置和连接")
    else:
        print("✅ 系统运行良好")
    
    # 保存详细结果
    with open("railway_warp_test_result.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n📄 详细结果已保存到: railway_warp_test_result.json")

if __name__ == "__main__":
    asyncio.run(main()) 