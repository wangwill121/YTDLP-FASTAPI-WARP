import time
import asyncio
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

@dataclass
class RequestMetrics:
    """单次请求指标"""
    timestamp: float
    video_id: str
    processing_time: float
    proxy_used: Optional[str] = None
    success: bool = True
    error_type: Optional[str] = None
    response_size: int = 0
    
@dataclass
class SystemMetrics:
    """系统指标"""
    timestamp: float
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    active_requests: int = 0
    queue_size: int = 0

class PerformanceMetrics:
    """性能指标管理器"""
    
    def __init__(self, history_size: int = 1000):
        self.history_size = history_size
        
        # 请求历史记录 (最近1000条)
        self.request_history: deque = deque(maxlen=history_size)
        
        # 系统指标历史 (最近100条)
        self.system_history: deque = deque(maxlen=100)
        
        # 实时统计
        self.active_requests: Dict[str, float] = {}  # request_id -> start_time
        self.hourly_stats: Dict[str, Dict] = defaultdict(lambda: {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_processing_time": 0.0,
            "avg_processing_time": 0.0
        })
        
        # 代理使用统计
        self.proxy_stats: Dict[str, Dict] = defaultdict(lambda: {
            "requests": 0,
            "successes": 0,
            "failures": 0,
            "total_time": 0.0,
            "avg_time": 0.0
        })
        
        self._lock = asyncio.Lock()
    
    async def start_request(self, request_id: str) -> float:
        """开始记录请求"""
        start_time = time.time()
        async with self._lock:
            self.active_requests[request_id] = start_time
        return start_time
    
    async def end_request(self, 
                         request_id: str, 
                         video_id: str,
                         success: bool = True,
                         error_type: Optional[str] = None,
                         proxy_used: Optional[str] = None,
                         response_size: int = 0) -> float:
        """结束记录请求"""
        end_time = time.time()
        
        async with self._lock:
            start_time = self.active_requests.pop(request_id, end_time)
            processing_time = end_time - start_time
            
            # 记录请求指标
            metrics = RequestMetrics(
                timestamp=end_time,
                video_id=video_id,
                processing_time=processing_time,
                proxy_used=proxy_used,
                success=success,
                error_type=error_type,
                response_size=response_size
            )
            
            self.request_history.append(metrics)
            
            # 更新小时统计
            hour_key = datetime.fromtimestamp(end_time).strftime("%Y-%m-%d %H")
            stats = self.hourly_stats[hour_key]
            stats["total_requests"] += 1
            stats["total_processing_time"] += processing_time
            
            if success:
                stats["successful_requests"] += 1
            else:
                stats["failed_requests"] += 1
            
            # 计算平均处理时间
            if stats["total_requests"] > 0:
                stats["avg_processing_time"] = stats["total_processing_time"] / stats["total_requests"]
            
            # 更新代理统计
            if proxy_used:
                proxy_stat = self.proxy_stats[proxy_used]
                proxy_stat["requests"] += 1
                proxy_stat["total_time"] += processing_time
                
                if success:
                    proxy_stat["successes"] += 1
                else:
                    proxy_stat["failures"] += 1
                
                # 计算平均时间
                if proxy_stat["requests"] > 0:
                    proxy_stat["avg_time"] = proxy_stat["total_time"] / proxy_stat["requests"]
        
        return processing_time
    
    async def record_system_metrics(self, 
                                  cpu_usage: float, 
                                  memory_usage: float, 
                                  queue_size: int = 0):
        """记录系统指标"""
        async with self._lock:
            metrics = SystemMetrics(
                timestamp=time.time(),
                cpu_usage=cpu_usage,
                memory_usage=memory_usage,
                active_requests=len(self.active_requests),
                queue_size=queue_size
            )
            self.system_history.append(metrics)
    
    def get_current_stats(self) -> Dict[str, Any]:
        """获取当前统计信息"""
        now = time.time()
        
        # 最近1小时的请求
        recent_requests = [
            r for r in self.request_history 
            if now - r.timestamp <= 3600
        ]
        
        # 最近10分钟的请求
        recent_10min = [
            r for r in recent_requests
            if now - r.timestamp <= 600
        ]
        
        # 计算统计
        total_recent = len(recent_requests)
        successful_recent = sum(1 for r in recent_requests if r.success)
        
        total_10min = len(recent_10min)
        successful_10min = sum(1 for r in recent_10min if r.success)
        
        # 平均处理时间
        avg_time_1h = 0.0
        avg_time_10m = 0.0
        
        if recent_requests:
            avg_time_1h = sum(r.processing_time for r in recent_requests) / len(recent_requests)
        
        if recent_10min:
            avg_time_10m = sum(r.processing_time for r in recent_10min) / len(recent_10min)
        
        # 系统指标
        latest_system = self.system_history[-1] if self.system_history else None
        
        return {
            "requests_1h": total_recent,
            "successful_1h": successful_recent,
            "success_rate_1h": successful_recent / total_recent if total_recent > 0 else 0.0,
            "avg_processing_time_1h": round(avg_time_1h, 2),
            
            "requests_10m": total_10min,
            "successful_10m": successful_10min,
            "success_rate_10m": successful_10min / total_10min if total_10min > 0 else 0.0,
            "avg_processing_time_10m": round(avg_time_10m, 2),
            
            "active_requests": len(self.active_requests),
            "total_requests_recorded": len(self.request_history),
            
            "system": {
                "cpu_usage": latest_system.cpu_usage if latest_system else 0.0,
                "memory_usage": latest_system.memory_usage if latest_system else 0.0,
                "queue_size": latest_system.queue_size if latest_system else 0
            } if latest_system else None
        }
    
    def get_proxy_performance(self) -> Dict[str, Dict]:
        """获取代理性能统计"""
        result = {}
        for proxy_id, stats in self.proxy_stats.items():
            result[proxy_id] = {
                "requests": stats["requests"],
                "success_rate": stats["successes"] / stats["requests"] if stats["requests"] > 0 else 0.0,
                "avg_time": round(stats["avg_time"], 2),
                "total_time": round(stats["total_time"], 2)
            }
        return result
    
    def get_hourly_trends(self, hours: int = 24) -> List[Dict]:
        """获取最近N小时的趋势数据"""
        current_time = datetime.now()
        trends = []
        
        for i in range(hours):
            hour_time = current_time - timedelta(hours=i)
            hour_key = hour_time.strftime("%Y-%m-%d %H")
            
            stats = self.hourly_stats.get(hour_key, {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "avg_processing_time": 0.0
            })
            
            trends.append({
                "hour": hour_key,
                "total_requests": stats["total_requests"],
                "success_rate": stats["successful_requests"] / stats["total_requests"] if stats["total_requests"] > 0 else 0.0,
                "avg_processing_time": round(stats["avg_processing_time"], 2)
            })
        
        return list(reversed(trends))  # 从早到晚排序
    
    async def cleanup_old_data(self):
        """清理旧数据"""
        async with self._lock:
            current_time = datetime.now()
            cutoff_time = current_time - timedelta(days=7)  # 保留7天数据
            cutoff_key = cutoff_time.strftime("%Y-%m-%d %H")
            
            # 清理小时统计
            old_keys = [k for k in self.hourly_stats.keys() if k < cutoff_key]
            for key in old_keys:
                del self.hourly_stats[key]
            
            logger.info(f"清理了 {len(old_keys)} 个旧的小时统计记录")


# 全局指标实例
_metrics: Optional[PerformanceMetrics] = None

def get_metrics() -> PerformanceMetrics:
    """获取全局指标实例"""
    global _metrics
    if _metrics is None:
        _metrics = PerformanceMetrics()
    return _metrics

def reset_metrics():
    """重置指标"""
    global _metrics
    _metrics = PerformanceMetrics() 