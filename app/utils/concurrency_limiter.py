#!/usr/bin/env python3
"""
并发限制器
基于 Cloudflare WARP 免费账户限制的并发控制系统
参考: https://developers.cloudflare.com/cloudflare-one/account-limits/
"""

import asyncio
import time
import logging
import uuid
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from collections import deque
from enum import Enum

logger = logging.getLogger(__name__)

class AccountTier(Enum):
    """账户等级"""
    FREE = "free"
    STANDARD = "standard" 
    ENTERPRISE = "enterprise"

@dataclass
class CloudflareWARPLimits:
    """Cloudflare WARP 账户限制"""
    # 基于官方文档的限制
    warp_connectors: int = 10           # WARP Connectors 限制
    max_concurrent_per_connector: int = 5  # 每个连接器的保守并发数
    rate_limit_per_second: float = 3.0     # 保守的 QPS 限制
    burst_limit: int = 10               # 突发请求限制
    connection_timeout: float = 30.0    # 连接超时
    
    @property
    def total_max_concurrent(self) -> int:
        """总最大并发数"""
        return self.warp_connectors * self.max_concurrent_per_connector

@dataclass
class ConcurrencyConfig:
    """并发配置"""
    account_tier: AccountTier = AccountTier.FREE
    max_queue_size: int = 50           # 队列最大长度
    request_timeout: float = 45.0      # 请求总超时
    cleanup_interval: float = 30.0     # 清理间隔
    
    def get_warp_limits(self) -> CloudflareWARPLimits:
        """根据账户等级获取 WARP 限制"""
        if self.account_tier == AccountTier.FREE:
            return CloudflareWARPLimits(
                warp_connectors=8,              # 保守估计，留2个余量
                max_concurrent_per_connector=4, # 保守的并发数
                rate_limit_per_second=2.5,     # 保守的 QPS
                burst_limit=8,
                connection_timeout=25.0
            )
        elif self.account_tier == AccountTier.STANDARD:
            return CloudflareWARPLimits(
                warp_connectors=10,
                max_concurrent_per_connector=6,
                rate_limit_per_second=5.0,
                burst_limit=15,
                connection_timeout=30.0
            )
        else:  # ENTERPRISE
            return CloudflareWARPLimits(
                warp_connectors=20,
                max_concurrent_per_connector=10,
                rate_limit_per_second=10.0,
                burst_limit=25,
                connection_timeout=30.0
            )

@dataclass
class RequestInfo:
    """请求信息"""
    request_id: str
    priority: int = 0
    created_at: float = 0.0
    started_at: Optional[float] = None
    video_id: Optional[str] = None
    user_ip: Optional[str] = None

class ConcurrencyLimiter:
    """
    基于 Cloudflare WARP 限制的并发控制器
    
    核心原则:
    1. 严格控制总并发数不超过 Cloudflare 限制
    2. 实现智能队列管理
    3. 提供优雅的降级机制
    4. 监控和报告系统状态
    """
    
    def __init__(self, config: ConcurrencyConfig = None):
        self.config = config or ConcurrencyConfig()
        self.warp_limits = self.config.get_warp_limits()
        
        # 并发控制
        self.active_requests: Dict[str, RequestInfo] = {}
        self.request_queue: deque[RequestInfo] = deque()
        self.semaphore = asyncio.Semaphore(self.warp_limits.total_max_concurrent)
        
        # 速率限制 (令牌桶算法)
        self.tokens = float(self.warp_limits.burst_limit)
        self.last_refill = time.time()
        
        # 统计信息
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "rejected_requests": 0,
            "timeout_requests": 0,
            "queued_requests": 0,
            "peak_concurrent": 0,
            "peak_queue_size": 0
        }
        
        self._lock = asyncio.Lock()
        logger.info(f"并发限制器初始化: 最大并发={self.warp_limits.total_max_concurrent}, "
                   f"QPS限制={self.warp_limits.rate_limit_per_second}, "
                   f"账户等级={self.config.account_tier.value}")
    
    async def acquire_request_slot(self, 
                                 video_id: str = None, 
                                 user_ip: str = None,
                                 priority: int = 0) -> Optional[str]:
        """
        获取请求槽位
        
        Args:
            video_id: 视频ID
            user_ip: 用户IP
            priority: 优先级 (0=普通, 1=高优先级, -1=低优先级)
        
        Returns:
            Optional[str]: 请求ID，None表示被拒绝
        """
        request_id = str(uuid.uuid4())
        current_time = time.time()
        
        async with self._lock:
            # 检查速率限制
            if not await self._check_rate_limit():
                self.stats["rejected_requests"] += 1
                logger.warning(f"请求被速率限制拒绝: video_id={video_id}, ip={user_ip}")
                return None
            
            # 检查队列是否已满
            if len(self.request_queue) >= self.config.max_queue_size:
                self.stats["rejected_requests"] += 1
                logger.warning(f"请求被拒绝-队列已满: video_id={video_id}, ip={user_ip}")
                return None
            
            # 创建请求信息
            request_info = RequestInfo(
                request_id=request_id,
                priority=priority,
                created_at=current_time,
                video_id=video_id,
                user_ip=user_ip
            )
            
            # 尝试直接获取槽位
            try:
                self.semaphore.acquire_nowait()
                # 直接执行
                request_info.started_at = current_time
                self.active_requests[request_id] = request_info
                self.stats["total_requests"] += 1
                self.stats["peak_concurrent"] = max(
                    self.stats["peak_concurrent"], 
                    len(self.active_requests)
                )
                logger.info(f"请求直接执行: {request_id[:8]}... (并发: {len(self.active_requests)})")
                return request_id
                
            except Exception:
                # 加入队列
                self.request_queue.append(request_info)
                self.stats["queued_requests"] += 1
                self.stats["peak_queue_size"] = max(
                    self.stats["peak_queue_size"],
                    len(self.request_queue)
                )
                
                queue_position = len(self.request_queue)
                estimated_wait = queue_position * 5  # 估算等待时间
                
                logger.info(f"请求加入队列: {request_id[:8]}... "
                           f"(位置: {queue_position}, 预计等待: {estimated_wait}s)")
                return request_id
    
    async def wait_for_slot(self, request_id: str, timeout: Optional[float] = None) -> bool:
        """
        等待获取槽位
        
        Args:
            request_id: 请求ID
            timeout: 超时时间
            
        Returns:
            bool: 是否成功获取槽位
        """
        timeout = timeout or self.config.request_timeout
        start_time = time.time()
        check_interval = 0.5  # 检查间隔
        
        while time.time() - start_time < timeout:
            async with self._lock:
                # 检查是否已经在执行
                if request_id in self.active_requests:
                    request_info = self.active_requests[request_id]
                    if request_info.started_at is not None:
                        return True
                
                # 在队列中查找请求
                for i, item in enumerate(self.request_queue):
                    if item.request_id == request_id:
                        # 如果是队列首位，尝试获取槽位
                        if i == 0:
                            try:
                                self.semaphore.acquire_nowait()
                                # 从队列移除并激活
                                request_info = self.request_queue.popleft()
                                request_info.started_at = time.time()
                                self.active_requests[request_id] = request_info
                                self.stats["total_requests"] += 1
                                self.stats["peak_concurrent"] = max(
                                    self.stats["peak_concurrent"], 
                                    len(self.active_requests)
                                )
                                
                                logger.info(f"队列请求开始执行: {request_id[:8]}... "
                                           f"(等待时间: {time.time() - request_info.created_at:.1f}s)")
                                return True
                            except Exception:
                                pass
                        else:
                            # 还在队列中等待
                            logger.debug(f"请求队列等待: {request_id[:8]}... (位置: {i+1})")
                        break
                else:
                    # 请求不在队列中，可能已被清理
                    logger.warning(f"请求未找到: {request_id[:8]}...")
                    return False
            
            # 等待一段时间再检查
            await asyncio.sleep(check_interval)
        
        # 超时处理
        await self._handle_request_timeout(request_id)
        return False
    
    async def release_request_slot(self, request_id: str, success: bool = True):
        """释放请求槽位"""
        async with self._lock:
            if request_id in self.active_requests:
                request_info = self.active_requests.pop(request_id)
                self.semaphore.release()
                
                if success:
                    self.stats["successful_requests"] += 1
                
                execution_time = time.time() - (request_info.started_at or request_info.created_at)
                logger.info(f"请求完成: {request_id[:8]}... "
                           f"(执行时间: {execution_time:.1f}s, 成功: {success})")
                
                # 处理队列中的下一个请求
                await self._process_queue()
    
    async def _check_rate_limit(self) -> bool:
        """检查速率限制 (令牌桶算法)"""
        current_time = time.time()
        
        # 补充令牌
        time_passed = current_time - self.last_refill
        self.tokens = min(
            self.warp_limits.burst_limit,
            self.tokens + time_passed * self.warp_limits.rate_limit_per_second
        )
        self.last_refill = current_time
        
        # 检查是否有可用令牌
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        
        return False
    
    async def _process_queue(self):
        """处理队列中的请求"""
        if not self.request_queue:
            return
        
        # 按优先级排序队列
        sorted_queue = sorted(
            self.request_queue, 
            key=lambda x: (-x.priority, x.created_at)
        )
        self.request_queue = deque(sorted_queue)
    
    async def _handle_request_timeout(self, request_id: str):
        """处理请求超时"""
        async with self._lock:
            # 从队列中移除
            self.request_queue = deque(
                item for item in self.request_queue 
                if item.request_id != request_id
            )
            
            # 从活跃请求中移除
            if request_id in self.active_requests:
                del self.active_requests[request_id]
                self.semaphore.release()
            
            self.stats["timeout_requests"] += 1
            logger.warning(f"请求超时: {request_id[:8]}...")
    
    def get_status(self) -> Dict[str, Any]:
        """获取详细状态信息"""
        current_time = time.time()
        
        # 计算队列等待时间
        avg_queue_wait = 0.0
        if self.request_queue:
            wait_times = [current_time - item.created_at for item in self.request_queue]
            avg_queue_wait = sum(wait_times) / len(wait_times)
        
        return {
            "limits": {
                "max_concurrent": self.warp_limits.total_max_concurrent,
                "max_per_connector": self.warp_limits.max_concurrent_per_connector,
                "warp_connectors": self.warp_limits.warp_connectors,
                "rate_limit_per_second": self.warp_limits.rate_limit_per_second,
                "account_tier": self.config.account_tier.value
            },
            "current": {
                "active_requests": len(self.active_requests),
                "queued_requests": len(self.request_queue),
                "available_tokens": round(self.tokens, 2),
                "concurrent_utilization": len(self.active_requests) / self.warp_limits.total_max_concurrent,
                "queue_utilization": len(self.request_queue) / self.config.max_queue_size,
                "avg_queue_wait_time": round(avg_queue_wait, 1)
            },
            "statistics": self.stats.copy(),
            "queue_details": [
                {
                    "request_id": item.request_id[:8] + "...",
                    "priority": item.priority,
                    "wait_time": round(current_time - item.created_at, 1),
                    "video_id": item.video_id
                }
                for item in list(self.request_queue)[:5]  # 显示前5个
            ],
            "recommendations": self._get_recommendations()
        }
    
    def _get_recommendations(self) -> List[str]:
        """获取系统建议"""
        recommendations = []
        
        utilization = len(self.active_requests) / self.warp_limits.total_max_concurrent
        queue_utilization = len(self.request_queue) / self.config.max_queue_size
        
        if utilization > 0.8:
            recommendations.append("并发使用率过高，建议考虑升级账户或优化请求")
        
        if queue_utilization > 0.6:
            recommendations.append("队列压力较大，用户可能体验到较长等待时间")
        
        if self.stats["rejected_requests"] > self.stats["total_requests"] * 0.1:
            recommendations.append("拒绝率较高，建议降低请求频率或增加队列大小")
        
        if self.tokens < 1.0:
            recommendations.append("速率限制生效中，请求将被限制")
        
        return recommendations
    
    async def cleanup_expired_requests(self):
        """清理过期请求"""
        current_time = time.time()
        timeout = self.config.request_timeout
        
        async with self._lock:
            # 清理过期的活跃请求
            expired_active = [
                req_id for req_id, req_info in self.active_requests.items()
                if current_time - req_info.created_at > timeout
            ]
            
            for req_id in expired_active:
                logger.warning(f"清理过期活跃请求: {req_id[:8]}...")
                del self.active_requests[req_id]
                self.semaphore.release()
                self.stats["timeout_requests"] += 1
            
            # 清理过期的队列请求
            original_queue_size = len(self.request_queue)
            self.request_queue = deque(
                item for item in self.request_queue
                if current_time - item.created_at <= timeout
            )
            
            expired_queue_count = original_queue_size - len(self.request_queue)
            if expired_queue_count > 0:
                logger.warning(f"清理 {expired_queue_count} 个过期队列请求")
                self.stats["timeout_requests"] += expired_queue_count


# 全局实例
_limiter: Optional[ConcurrencyLimiter] = None

def get_concurrency_limiter(config: ConcurrencyConfig = None) -> ConcurrencyLimiter:
    """获取全局并发限制器实例"""
    global _limiter
    if _limiter is None:
        _limiter = ConcurrencyLimiter(config)
    return _limiter

async def start_cleanup_task():
    """启动清理任务"""
    limiter = get_concurrency_limiter()
    
    while True:
        try:
            await limiter.cleanup_expired_requests()
            await asyncio.sleep(limiter.config.cleanup_interval)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"清理任务异常: {e}")
            await asyncio.sleep(60) 