#!/usr/bin/env python3
"""
本地 WARP 测试脚本
用于在部署前验证 WARP 功能是否正常工作
"""

import asyncio
import aiohttp
import json
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_ip_check():
    """测试 IP 检查功能"""
    print("🔍 正在检查容器出口 IP...")
    
    # 多个 IP 检测服务
    ip_services = [
        "https://api.ipify.org?format=json",
        "https://httpbin.org/ip",
        "https://api.myip.com",
        "https://ipapi.co/json/",
    ]
    
    results = []
    
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        for service_url in ip_services:
            try:
                async with session.get(service_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # 不同服务的 IP 字段名不同
                        ip = None
                        if 'ip' in data:
                            ip = data['ip']
                        elif 'origin' in data:
                            ip = data['origin']
                        
                        if ip:
                            results.append({
                                "service": service_url,
                                "ip": ip,
                                "status": "success",
                                "data": data
                            })
                            print(f"✅ {service_url}: {ip}")
                        else:
                            results.append({
                                "service": service_url,
                                "status": "error",
                                "error": "无法解析 IP 字段"
                            })
                            print(f"❌ {service_url}: 无法解析 IP 字段")
                    else:
                        results.append({
                            "service": service_url,
                            "status": "error",
                            "error": f"HTTP {response.status}"
                        })
                        print(f"❌ {service_url}: HTTP {response.status}")
            except Exception as e:
                results.append({
                    "service": service_url,
                    "status": "error",
                    "error": str(e)
                })
                print(f"❌ {service_url}: {e}")
    
    # 提取成功获取的 IP
    successful_ips = [r["ip"] for r in results if r.get("ip")]
    
    # 检查是否为 Cloudflare IP 段
    is_cloudflare_ip = False
    cloudflare_check = "unknown"
    
    if successful_ips:
        # 使用第一个成功的 IP 进行 Cloudflare 检查
        test_ip = successful_ips[0]
        try:
            # Cloudflare 的 IP 段检查
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                # 使用 Cloudflare 的 trace 服务
                async with session.get("https://1.1.1.1/cdn-cgi/trace") as response:
                    if response.status == 200:
                        trace_data = await response.text()
                        print(f"\n📊 Cloudflare Trace 结果:")
                        print(trace_data)
                        
                        if "warp=on" in trace_data.lower() or "warp=plus" in trace_data.lower():
                            is_cloudflare_ip = True
                            cloudflare_check = "WARP detected via trace"
                            print("✅ 检测到 WARP 已启用!")
                        else:
                            cloudflare_check = "No WARP detected"
                            print("❌ 未检测到 WARP")
                    else:
                        cloudflare_check = f"Trace service error: {response.status}"
                        print(f"❌ Trace 服务错误: {response.status}")
        except Exception as e:
            cloudflare_check = f"Trace check failed: {e}"
            print(f"❌ Cloudflare Trace 检查失败: {e}")
    
    return {
        "timestamp": datetime.now().isoformat(),
        "container_ips": {
            "results": results,
            "successful_ips": successful_ips,
            "unique_ips": list(set(successful_ips)),
            "total_services": len(ip_services),
            "successful_services": len(successful_ips)
        },
        "warp_analysis": {
            "is_cloudflare_ip": is_cloudflare_ip,
            "check_method": cloudflare_check,
            "warp_status": "ACTIVE" if is_cloudflare_ip else "INACTIVE"
        },
        "recommendation": "WARP 生效" if is_cloudflare_ip else "WARP 可能未生效，检查配置"
    }

async def test_ytdlp_with_warp():
    """测试 yt-dlp 使用 WARP 代理"""
    print("\n🎥 正在测试 yt-dlp 功能...")
    
    try:
        # 导入所需模块
        import yt_dlp
        from app.utils.proxy_pool import get_proxy_pool
        
        test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        
        # 测试1: 直接连接
        print("📡 测试直接连接...")
        direct_start = asyncio.get_event_loop().time()
        
        ydl_opts_direct = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'skip_download': True,
            'socket_timeout': 15,
            'retries': 1,
        }
        
        try:
            loop = asyncio.get_event_loop()
            info_direct = await loop.run_in_executor(
                None,
                lambda: yt_dlp.YoutubeDL(ydl_opts_direct).extract_info(test_url, download=False)
            )
            
            direct_time = asyncio.get_event_loop().time() - direct_start
            if info_direct and info_direct.get('title'):
                print(f"✅ 直接连接成功: {info_direct.get('title')} ({direct_time:.2f}s)")
                direct_success = True
            else:
                print("❌ 直接连接失败: 无法获取视频信息")
                direct_success = False
        except Exception as e:
            direct_time = asyncio.get_event_loop().time() - direct_start
            print(f"❌ 直接连接失败: {e} ({direct_time:.2f}s)")
            direct_success = False
        
        # 测试2: WARP 代理连接
        print("🌐 测试 WARP 代理连接...")
        warp_success = False
        warp_time = 0
        proxy_used = None
        
        try:
            proxy_pool = get_proxy_pool()
            if proxy_pool:
                proxy_info = await proxy_pool.get_best_proxy()
                if proxy_info:
                    proxy_used = proxy_info.url
                    print(f"📡 使用代理: {proxy_used}")
                    
                    warp_start = asyncio.get_event_loop().time()
                    
                    ydl_opts_warp = ydl_opts_direct.copy()
                    ydl_opts_warp['proxy'] = proxy_used
                    
                    try:
                        info_warp = await loop.run_in_executor(
                            None,
                            lambda: yt_dlp.YoutubeDL(ydl_opts_warp).extract_info(test_url, download=False)
                        )
                        
                        warp_time = asyncio.get_event_loop().time() - warp_start
                        
                        if info_warp and info_warp.get('title'):
                            print(f"✅ WARP 代理连接成功: {info_warp.get('title')} ({warp_time:.2f}s)")
                            warp_success = True
                        else:
                            print("❌ WARP 代理连接失败: 无法获取视频信息")
                        
                        # 释放代理
                        await proxy_pool.release_proxy(proxy_info, success=warp_success)
                        
                    except Exception as e:
                        warp_time = asyncio.get_event_loop().time() - warp_start
                        print(f"❌ WARP 代理连接失败: {e} ({warp_time:.2f}s)")
                        await proxy_pool.release_proxy(proxy_info, success=False)
                else:
                    print("❌ 无可用的 WARP 代理")
            else:
                print("❌ WARP 代理池未初始化")
                
        except Exception as e:
            print(f"❌ WARP 代理测试失败: {e}")
        
        # 生成建议
        if warp_success and direct_success:
            recommendation = "✅ WARP 和直连都正常，系统运行良好"
        elif warp_success:
            recommendation = "✅ WARP 工作正常，建议优先使用 WARP 代理"
        elif direct_success:
            recommendation = "⚠️ 直连正常但 WARP 失败，检查 WARP 配置"
        else:
            recommendation = "❌ 所有连接都失败，检查网络和配置"
        
        print(f"\n💡 建议: {recommendation}")
        
        return {
            "direct_test": {
                "success": direct_success,
                "response_time": direct_time
            },
            "warp_test": {
                "success": warp_success,
                "response_time": warp_time,
                "proxy_used": proxy_used
            },
            "recommendation": recommendation
        }
        
    except ImportError as e:
        print(f"❌ 导入模块失败: {e}")
        return {"error": f"Missing dependencies: {e}"}
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return {"error": str(e)}

async def main():
    """主测试函数"""
    print("🚀 开始 WARP 功能测试...\n")
    
    # 测试 IP 检查
    ip_result = await test_ip_check()
    
    # 测试 yt-dlp 功能
    ytdlp_result = await test_ytdlp_with_warp()
    
    # 输出完整结果
    print("\n" + "="*60)
    print("📋 测试结果摘要:")
    print("="*60)
    
    # IP 检查结果
    if ip_result["warp_analysis"]["is_cloudflare_ip"]:
        print("✅ IP 检查: WARP 已启用")
    else:
        print("❌ IP 检查: WARP 未启用")
    
    # yt-dlp 测试结果
    if isinstance(ytdlp_result, dict) and "error" not in ytdlp_result:
        if ytdlp_result["warp_test"]["success"]:
            print("✅ WARP 代理: yt-dlp 连接成功")
        else:
            print("❌ WARP 代理: yt-dlp 连接失败")
        
        if ytdlp_result["direct_test"]["success"]:
            print("✅ 直接连接: yt-dlp 连接成功")
        else:
            print("❌ 直接连接: yt-dlp 连接失败")
    else:
        print("❌ yt-dlp 测试: 模块导入失败")
    
    print("\n💡 最终建议:")
    print(ip_result["recommendation"])
    if isinstance(ytdlp_result, dict) and "recommendation" in ytdlp_result:
        print(ytdlp_result["recommendation"])
    
    # 保存详细结果到文件
    full_result = {
        "timestamp": datetime.now().isoformat(),
        "ip_check": ip_result,
        "ytdlp_test": ytdlp_result
    }
    
    with open("warp_test_result.json", "w", encoding="utf-8") as f:
        json.dump(full_result, f, indent=2, ensure_ascii=False)
    
    print(f"\n📄 详细结果已保存到: warp_test_result.json")

if __name__ == "__main__":
    asyncio.run(main()) 