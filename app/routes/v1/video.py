"""
Video processing routes for yt-dlp FastAPI
"""

import logging
from typing import Optional, Annotated
import time
import asyncio
import uuid
import yt_dlp

from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import JSONResponse

from app.models.error import HTTPError
from app.models.media import SimpleVideoResponse
from app.utils.proxy_pool import get_proxy_pool
from app.utils.metrics import get_metrics
from app.utils.crypto import encrypt_data
from app.utils.config import settings
from app.utils.dlp_utils import DLPUtils

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get(
    "/video/{video_id}",
    summary="解析视频信息",
    description="解析 YouTube 视频，返回4K无声视频和高质量音频直链",
    response_model=SimpleVideoResponse,
    responses={
        400: {"model": HTTPError},
        401: {"model": HTTPError},
        404: {"model": HTTPError}
    },
    tags=["Video"]
)
async def fetch_simple(request: Request, video_id: str, x_secret: Annotated[Optional[str], Header()] = None) -> JSONResponse:
    """
    🚀 视频解析接口 - 支持直链和代理模式
    
    模式说明：
    - 直链模式：返回 YouTube 真实下载链接（速度快，零流量成本）
    - 代理模式：返回加密的本地代理链接（避免 IP 限制，支持高并发）
    """
    # 生成请求 ID 用于性能追踪
    request_id = str(uuid.uuid4())
    metrics = get_metrics()
    await metrics.start_request(request_id)
    
    start_time = time.time()
    proxy_used = None
    
    try:
        # 🔐 API 鉴权检查
        if not settings.validate_secret_for_domain(x_secret, str(request.url.hostname)):
            raise HTTPException(status_code=401, detail="Invalid API key")

        # 🎬 基础验证
    if not DLPUtils.validate_youtube_video_id(video_id):
            raise HTTPException(status_code=400, detail="无效的 YouTube 视频 ID")
        
        logger.info(f"开始解析视频: {video_id}")
        
        # 🎯 获取代理（如果启用）
        proxy_info = None
        if settings.ENABLE_WARP_PROXY:
            proxy_pool = get_proxy_pool()
            if proxy_pool:
                proxy_info = await proxy_pool.get_best_proxy()
                if proxy_info:
                    proxy_used = proxy_info.url
                    logger.info(f"使用代理: {proxy_used}")
        
        # 🚀 核心解析逻辑
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        # 配置 yt-dlp 选项
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'skip_download': True,
            # 获取所有格式，在代码中筛选最佳直链
            'format': 'all',
        }
        
        # 添加代理配置
        if proxy_info:
            ydl_opts['proxy'] = proxy_info.url
        
        # 🎯 解析视频信息
        loop = asyncio.get_event_loop()
        video_info = await loop.run_in_executor(
            None, 
            lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=False)
        )
        
        if not video_info:
            raise HTTPException(status_code=404, detail="视频不存在或无法访问")
        
        # 🔍 提取格式信息
        formats = video_info.get('formats', [])
        if not formats:
            raise HTTPException(status_code=404, detail="无法获取视频格式信息")
        
        # 🎥 选择最佳视频格式 (优先级：可直接下载 > 4K无声 > 1080p)
        video_format = None
        
        # 过滤视频格式：无声视频，非 HLS/DASH 流媒体
        video_formats = []
        for fmt in formats:
            if (fmt.get('vcodec') != 'none' and 
                fmt.get('acodec') == 'none' and
                fmt.get('protocol') not in ['m3u8', 'm3u8_native', 'http_dash_segments'] and
                fmt.get('url') and 
                not fmt.get('url', '').endswith('.m3u8')):
                video_formats.append(fmt)
        
        # 按优先级排序：4K > 1080p > 其他，质量越高越好
        video_formats.sort(key=lambda x: (
            x.get('height', 0) if x.get('height', 0) <= 2160 else 0,  # 4K 优先
            x.get('tbr', 0),  # 比特率越高越好
            x.get('filesize', 0) if x.get('filesize') else 0  # 文件大小
        ), reverse=True)
        
        video_format = video_formats[0] if video_formats else None
        
        # 记录选择的视频格式
        if video_format:
            logger.info(f"选择视频格式: {video_format.get('format_id')} - {video_format.get('height')}p - {video_format.get('ext')} - {video_format.get('protocol')}")
        else:
            logger.warning("未找到合适的视频格式")
        
        # 🔊 选择最佳音频格式 (优先级：m4a > mp3 > 其他)
        audio_format = None
        
        # 过滤音频格式：纯音频，非流媒体
        audio_formats = []
        for fmt in formats:
            if (fmt.get('acodec') != 'none' and 
                fmt.get('vcodec') == 'none' and
                fmt.get('protocol') not in ['m3u8', 'm3u8_native', 'http_dash_segments'] and
                fmt.get('url') and 
                not fmt.get('url', '').endswith('.m3u8')):
                audio_formats.append(fmt)
        
        # 按优先级排序：m4a > mp3 > webm > 其他，质量越高越好
        audio_formats.sort(key=lambda x: (
            1 if x.get('ext') == 'm4a' else 0.5 if x.get('ext') == 'mp3' else 0,  # 格式优先级
            x.get('abr', 0),  # 音频比特率
            x.get('filesize', 0) if x.get('filesize') else 0  # 文件大小
        ), reverse=True)
        
        audio_format = audio_formats[0] if audio_formats else None
        
        # 记录选择的音频格式
        if audio_format:
            logger.info(f"选择音频格式: {audio_format.get('format_id')} - {audio_format.get('ext')} - {audio_format.get('abr')}kbps - {audio_format.get('protocol')}")
        else:
            logger.warning("未找到合适的音频格式")
        
        # 构建响应
        response_data = {
            "video_id": video_id,
            "title": video_info.get('title', ''),
            "duration": video_info.get('duration', 0),
        }
        
        # 根据配置返回直链或代理链接
        if settings.DIRECT_LINK_MODE:
            # 直链模式：返回真实 YouTube 链接
            response_data.update({
                "video_url": video_format.get('url') if video_format else None,
                "audio_url": audio_format.get('url') if audio_format else None,
            })
    else:
            # 代理模式：返回加密的本地代理链接
            host = str(request.url.hostname)
            port = request.url.port
            scheme = request.url.scheme
            
            base_url = f"{scheme}://{host}"
            if port and port not in (80, 443):
                base_url += f":{port}"
            
            if video_format:
                video_data = {
                    "url": video_format.get('url'),
                    "type": "video"
                }
                video_token = encrypt_data(video_data)
                response_data["video_url"] = f"{base_url}/v1/proxy/{video_token}"
            
            if audio_format:
                audio_data = {
                    "url": audio_format.get('url'),
                    "type": "audio"
                }
                audio_token = encrypt_data(audio_data)
                response_data["audio_url"] = f"{base_url}/v1/proxy/{audio_token}"
        
        processing_time = time.time() - start_time
        
        # 释放代理
        if proxy_info:
            proxy_pool = get_proxy_pool()
            if proxy_pool:
                await proxy_pool.release_proxy(proxy_info, success=True)
        
        # 记录性能指标
        await metrics.end_request(
            request_id=request_id,
            video_id=video_id,
            success=True,
            proxy_used=proxy_used,
            response_size=len(str(response_data))
        )
        
        logger.info(f"视频解析完成: {video_id}, 耗时: {processing_time:.2f}秒")
        
            return JSONResponse(
            content=response_data,
            headers={"X-Processing-Time": f"{processing_time:.3f}"}
        )
        
    except HTTPException:
        # 释放代理（失败情况）
        if proxy_info:
            proxy_pool = get_proxy_pool()
            if proxy_pool:
                await proxy_pool.release_proxy(proxy_info, success=False)
        
        # 记录失败指标
        await metrics.end_request(
            request_id=request_id,
            video_id=video_id,
            success=False,
            proxy_used=proxy_used
        )
        raise
        except Exception as e:
        processing_time = time.time() - start_time
        
        # 释放代理（异常情况）
        if proxy_info:
            proxy_pool = get_proxy_pool()
            if proxy_pool:
                await proxy_pool.release_proxy(proxy_info, success=False)
        
        # 记录异常指标
        await metrics.end_request(
            request_id=request_id,
            video_id=video_id,
            success=False,
            error_type=type(e).__name__,
            proxy_used=proxy_used
        )
        
        logger.error(f"视频解析失败: {video_id}, 错误: {e}, 耗时: {processing_time:.2f}秒")
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")


@router.get(
    "/formats/{video_id}",
    summary="获取视频格式信息",
    description="获取 YouTube 视频的所有可用格式",
    tags=["Video"]
)
async def get_formats(request: Request, video_id: str, x_secret: Annotated[Optional[str], Header()] = None):
    """获取视频的所有可用格式信息"""
    try:
        # 🔐 API 鉴权检查
        if not settings.validate_secret_for_domain(x_secret, str(request.url.hostname)):
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        # 🎬 基础验证
        if not DLPUtils.validate_youtube_video_id(video_id):
            raise HTTPException(status_code=400, detail="无效的 YouTube 视频 ID")
        
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        # 配置 yt-dlp 选项
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'skip_download': True,
        }
        
        # 解析视频信息
        loop = asyncio.get_event_loop()
        video_info = await loop.run_in_executor(
            None, 
            lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=False)
        )
        
        if not video_info:
            raise HTTPException(status_code=404, detail="视频不存在或无法访问")
        
        formats = video_info.get('formats', [])
        
        # 简化格式信息
        simplified_formats = []
        for fmt in formats:
            simplified_formats.append({
                "format_id": fmt.get('format_id'),
                "ext": fmt.get('ext'),
                "resolution": f"{fmt.get('width', 0)}x{fmt.get('height', 0)}" if fmt.get('width') else None,
                "filesize": fmt.get('filesize'),
                "vcodec": fmt.get('vcodec'),
                "acodec": fmt.get('acodec'),
                "abr": fmt.get('abr'),
                "vbr": fmt.get('vbr'),
            })
        
        return {
            "video_id": video_id,
            "title": video_info.get('title', ''),
            "duration": video_info.get('duration', 0),
            "formats": simplified_formats
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"格式获取失败: {video_id}, 错误: {e}")
        raise HTTPException(status_code=500, detail=f"获取格式失败: {str(e)}")
