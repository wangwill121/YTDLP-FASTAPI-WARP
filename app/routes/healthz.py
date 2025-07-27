#!/usr/bin/env python3
"""
健康检查和系统状态路由
"""

import logging
import psutil
import time
import asyncio
import aiohttp
import yt_dlp
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

# 导入新的组件（如果启用）
try:
    from app.utils.concurrency_limiter import get_concurrency_limiter
    from app.utils.warp_optimizer import get_warp_optimizer
    ADVANCED_FEATURES_AVAILABLE = True
except ImportError:
    ADVANCED_FEATURES_AVAILABLE = False

# 导入 WARP 相关组件
try:
    from app.utils.proxy_pool import get_proxy_pool
    from app.utils.warp_manager import get_warp_manager
    WARP_AVAILABLE = True
except ImportError:
    WARP_AVAILABLE = False

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/healthz", summary="健康检查", tags=["Health"])
async def health_check():
    """基本健康检查"""
    return {"status": "healthy", "message": "Service is running"}


@router.get("/ip-check", summary="IP 地址检测", tags=["Network"])
async def check_ip_address():
    """
    检测容器的真实出口 IP 地址
    用于验证 WARP 是否生效（Cloudflare IP 段表示 WARP 生效）
    """
    try:
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
                            else:
                                results.append({
                                    "service": service_url,
                                    "status": "error",
                                    "error": "无法解析 IP 字段"
                                })
                        else:
                            results.append({
                                "service": service_url,
                                "status": "error",
                                "error": f"HTTP {response.status}"
                            })
                except Exception as e:
                    results.append({
                        "service": service_url,
                        "status": "error",
                        "error": str(e)
                    })
        
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
                            if "warp=on" in trace_data.lower() or "warp=plus" in trace_data.lower():
                                is_cloudflare_ip = True
                                cloudflare_check = "WARP detected via trace"
                            else:
                                cloudflare_check = "No WARP detected"
                        else:
                            cloudflare_check = f"Trace service error: {response.status}"
            except Exception as e:
                cloudflare_check = f"Trace check failed: {e}"
        
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
        
    except Exception as e:
        logger.error(f"IP 检查失败: {e}")
        raise HTTPException(status_code=500, detail=f"IP 检查失败: {str(e)}")


@router.get("/warp-test", summary="WARP 连接测试", tags=["Network"])
async def test_warp_connection():
    """
    使用 yt-dlp 测试 WARP 代理连接
    模拟真实的视频解析请求来验证 WARP 是否正常工作
    """
    if not WARP_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "message": "WARP 功能未启用",
                "reason": "Missing WARP dependencies"
            }
        )
    
    try:
        results = {
            "timestamp": datetime.now().isoformat(),
            "tests": [],
            "summary": {}
        }
        
        # 测试 1: 无代理的直接连接
        logger.info("测试无代理连接...")
        direct_result = await _test_ytdlp_connection(None, "direct")
        results["tests"].append(direct_result)
        
        # 测试 2: 使用 WARP 代理连接
        if WARP_AVAILABLE:
            proxy_pool = get_proxy_pool()
            if proxy_pool:
                logger.info("测试 WARP 代理连接...")
                
                # 获取最佳代理
                proxy_info = await proxy_pool.get_best_proxy()
                if proxy_info:
                    warp_result = await _test_ytdlp_connection(proxy_info.url, "warp")
                    results["tests"].append(warp_result)
                    
                    # 释放代理
                    await proxy_pool.release_proxy(proxy_info, success=warp_result["success"])
                else:
                    results["tests"].append({
                        "test_type": "warp",
                        "success": False,
                        "error": "无可用的 WARP 代理",
                        "proxy_used": None
                    })
            else:
                results["tests"].append({
                    "test_type": "warp",
                    "success": False,
                    "error": "WARP 代理池未初始化",
                    "proxy_used": None
                })
        
        # 生成摘要
        successful_tests = [t for t in results["tests"] if t.get("success")]
        failed_tests = [t for t in results["tests"] if not t.get("success")]
        
        results["summary"] = {
            "total_tests": len(results["tests"]),
            "successful": len(successful_tests),
            "failed": len(failed_tests),
            "warp_working": any(t["test_type"] == "warp" and t["success"] for t in results["tests"]),
            "direct_working": any(t["test_type"] == "direct" and t["success"] for t in results["tests"]),
            "recommendation": _get_warp_recommendation(results["tests"])
        }
        
        return results
        
    except Exception as e:
        logger.error(f"WARP 连接测试失败: {e}")
        raise HTTPException(status_code=500, detail=f"WARP 测试失败: {str(e)}")


async def _test_ytdlp_connection(proxy_url: str = None, test_type: str = "unknown") -> Dict[str, Any]:
    """使用 yt-dlp 测试连接"""
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Rick Roll - 稳定的测试视频
    start_time = time.time()
    
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,  # 只提取基本信息，不解析格式
            'skip_download': True,
            'socket_timeout': 15,
            'retries': 1,
        }
        
        if proxy_url:
            ydl_opts['proxy'] = proxy_url
        
        # 在线程池中运行 yt-dlp
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(
            None,
            lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(test_url, download=False)
        )
        
        processing_time = time.time() - start_time
        
        if info and info.get('title'):
            return {
                "test_type": test_type,
                "success": True,
                "proxy_used": proxy_url,
                "response_time": round(processing_time, 2),
                "video_info": {
                    "title": info.get('title'),
                    "uploader": info.get('uploader'),
                    "duration": info.get('duration')
                },
                "message": f"yt-dlp 连接成功 ({test_type})"
            }
        else:
            return {
                "test_type": test_type,
                "success": False,
                "proxy_used": proxy_url,
                "response_time": round(processing_time, 2),
                "error": "无法获取视频信息",
                "message": f"yt-dlp 连接失败 ({test_type})"
            }
            
    except Exception as e:
        processing_time = time.time() - start_time
        return {
            "test_type": test_type,
            "success": False,
            "proxy_used": proxy_url,
            "response_time": round(processing_time, 2),
            "error": str(e),
            "message": f"yt-dlp 测试异常 ({test_type})"
        }


def _get_warp_recommendation(tests: list) -> str:
    """根据测试结果生成建议"""
    warp_test = next((t for t in tests if t["test_type"] == "warp"), None)
    direct_test = next((t for t in tests if t["test_type"] == "direct"), None)
    
    if warp_test and warp_test["success"]:
        if direct_test and direct_test["success"]:
            return "✅ WARP 和直连都正常，系统运行良好"
        else:
            return "✅ WARP 工作正常，建议优先使用 WARP 代理"
    elif direct_test and direct_test["success"]:
        return "⚠️ 直连正常但 WARP 失败，检查 WARP 配置"
    else:
        return "❌ 所有连接都失败，检查网络和配置"


@router.get("/warp-status", summary="WARP 状态详情", tags=["Network"])
async def get_warp_status():
    """获取 WARP 配置和代理池状态"""
    if not WARP_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "message": "WARP 功能未启用",
                "reason": "Missing WARP dependencies"
            }
        )
    
    try:
        status = {
            "timestamp": datetime.now().isoformat(),
            "warp_manager": {},
            "proxy_pool": {},
            "config_files": []
        }
        
        # WARP 管理器状态
        try:
            warp_manager = get_warp_manager()
            manager_status = warp_manager.get_status()
            status["warp_manager"] = manager_status
            
            # 获取配置文件详情
            configs = warp_manager.list_configs()
            status["config_files"] = configs
            
        except Exception as e:
            status["warp_manager"] = {"error": str(e)}
        
        # 代理池状态
        try:
            proxy_pool = get_proxy_pool()
            if proxy_pool:
                pool_status = proxy_pool.get_pool_status()
                status["proxy_pool"] = pool_status
            else:
                status["proxy_pool"] = {"status": "not_initialized"}
                
        except Exception as e:
            status["proxy_pool"] = {"error": str(e)}
        
        return status
        
    except Exception as e:
        logger.error(f"获取 WARP 状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"状态获取失败: {str(e)}")


@router.get("/status", summary="系统状态", tags=["Health"])
async def system_status():
    """系统详细状态"""
    try:
        # 基本系统信息
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        status = {
            "timestamp": datetime.now().isoformat(),
            "system": {
                "cpu_percent": cpu_percent,
                "memory": {
                    "total": memory.total,
                    "used": memory.used,
                    "percent": memory.percent
                },
                "disk": {
                    "total": disk.total,
                    "used": disk.used,
                    "percent": (disk.used / disk.total) * 100
                }
            },
            "service": {
                "uptime_seconds": time.time(),
                "advanced_features": ADVANCED_FEATURES_AVAILABLE,
                "warp_available": WARP_AVAILABLE
            }
        }
        
        return JSONResponse(content=status)
        
    except Exception as e:
        logger.error(f"获取系统状态失败: {e}")
        raise HTTPException(status_code=500, detail="无法获取系统状态")


@router.get("/test-video", summary="测试视频解析", tags=["Test"])
async def test_video_parsing():
    """简化的视频解析测试"""
    try:
        import yt_dlp
        
        # 使用 yt-dlp 测试一个简单的视频
        test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'format': 'best[height<=720]',  # 限制分辨率避免超时
            'noplaylist': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 只提取元数据，不下载
            info = ydl.extract_info(test_url, download=False)
            
            result = {
                "status": "success",
                "video_info": {
                    "title": info.get('title', 'Unknown'),
                    "duration": info.get('duration', 0),
                    "uploader": info.get('uploader', 'Unknown'),
                    "view_count": info.get('view_count', 0),
                    "format_count": len(info.get('formats', [])),
                    "direct_link_available": bool(info.get('url'))
                },
                "message": "视频解析功能正常"
            }
            
            return JSONResponse(content=result)
            
    except Exception as e:
        logger.error(f"视频解析测试失败: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"视频解析测试失败: {str(e)}",
                "suggestion": "检查网络连接和 yt-dlp 配置"
            }
        )


# 高级功能端点（如果可用）
if ADVANCED_FEATURES_AVAILABLE:
    
    @router.get("/concurrency", summary="并发控制状态", tags=["Advanced"])
    async def concurrency_status():
        """获取并发控制状态"""
        try:
            limiter = get_concurrency_limiter()
            status = limiter.get_status()
            return JSONResponse(content=status)
        except Exception as e:
            logger.error(f"获取并发状态失败: {e}")
            raise HTTPException(status_code=500, detail="无法获取并发状态")
    
    @router.get("/warp-optimization", summary="WARP 优化状态", tags=["Advanced"])
    async def warp_optimization_status():
        """获取 WARP 优化状态"""
        try:
            optimizer = get_warp_optimizer()
            status = optimizer.get_optimization_status()
            return JSONResponse(content=status)
        except Exception as e:
            logger.error(f"获取 WARP 状态失败: {e}")
            raise HTTPException(status_code=500, detail="无法获取 WARP 状态")
    
    @router.post("/warp-optimization/force", summary="强制 WARP 优化", tags=["Advanced"])
    async def force_warp_optimization():
        """强制执行 WARP 优化"""
        try:
            optimizer = get_warp_optimizer()
            result = await optimizer.force_optimization()
            return JSONResponse(content={"status": "success", "result": result})
        except Exception as e:
            logger.error(f"强制 WARP 优化失败: {e}")
            raise HTTPException(status_code=500, detail="强制优化失败")
else:
    
    @router.get("/concurrency", summary="并发控制状态（不可用）", tags=["Advanced"])
    async def concurrency_status_unavailable():
        """并发控制功能不可用"""
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "message": "高级并发控制功能未启用",
                "reason": "Missing dependencies or disabled"
            }
        )
    
    @router.get("/warp-optimization", summary="WARP 优化状态（不可用）", tags=["Advanced"]) 
    async def warp_optimization_status_unavailable():
        """WARP 优化功能不可用"""
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable", 
                "message": "WARP 优化功能未启用",
                "reason": "Missing dependencies or disabled"
            }
        )
