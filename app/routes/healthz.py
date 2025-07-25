#!/usr/bin/env python3
"""
健康检查和系统状态路由
"""

import logging
import psutil
import time
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

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/healthz", summary="健康检查", tags=["Health"])
async def health_check():
    """基本健康检查"""
    return {"status": "healthy", "message": "Service is running"}


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
                "advanced_features": ADVANCED_FEATURES_AVAILABLE
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
