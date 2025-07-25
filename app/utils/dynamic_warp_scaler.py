#!/usr/bin/env python3
"""
动态 WARP 扩容系统
根据流量负载和响应时间自动调整 WARP 配置数量

⚠️ 重要说明：
1. 每个设备注册都向 Cloudflare 发送请求，过于频繁可能触发速率限制
2. IP 级别的速率限制：同一 IP 地址注册过多设备可能被限制
3. 需要谨慎控制扩容速度，避免被 Cloudflare 识别为滥用
4. 推荐的扩容策略：渐进式、低频率、有监控
"""

import asyncio
import logging
import time
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import deque

from .warp_api_client import CloudflareWARPAPI
from .warp_optimizer import get_warp_optimizer
from .concurrency_limiter import get_concurrency_limiter

logger = logging.getLogger(__name__)

@dataclass
class ScalingMetrics:
    """扩容指标"""
    avg_response_time: float = 0.0
    active_connections: int = 0
    queue_length: int = 0
    error_rate: float = 0.0
    config_count: int = 0
    timestamp: datetime = None

@dataclass 
class ScalingLimits:
    """扩容限制配置"""
    # 基础限制
    min_configs: int = 5
    max_configs: int = 15  # 保守上限，避免过度使用
    target_configs: int = 8
    
    # 性能阈值
    max_response_time: float = 3.0  # 秒
    max_queue_length: int = 20
    max_error_rate: float = 0.1  # 10%
    
    # 扩容控制
    scale_up_threshold: float = 2.0  # 响应时间阈值
    scale_down_threshold: float = 1.0  # 响应时间阈值
    scale_cooldown: int = 300  # 5分钟冷却期
    max_scale_per_hour: int = 3  # 每小时最多扩容3次
    
    # API 调用限制（防止触发 Cloudflare 限制）
    api_call_interval: int = 60  # 每次 API 调用间隔
    max_concurrent_registrations: int = 2  # 最大并发注册数

class DynamicWARPScaler:
    """动态 WARP 扩容器"""
    
    def __init__(self, limits: ScalingLimits = None):
        self.limits = limits or ScalingLimits()
        self.metrics_history: deque = deque(maxlen=100)  # 保留最近100个指标
        self.last_scale_time: Optional[datetime] = None
        self.scale_operations_per_hour: List[datetime] = []
        self.is_scaling: bool = False
        
        # 依赖组件
        self.warp_optimizer = None
        self.concurrency_limiter = None
        
        logger.info("🚀 动态 WARP 扩容器初始化")
    
    async def initialize(self):
        """初始化扩容器"""
        try:
            self.warp_optimizer = get_warp_optimizer()
            self.concurrency_limiter = get_concurrency_limiter()
            
            logger.info("✅ 动态扩容器初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 动态扩容器初始化失败: {e}")
            return False
    
    def collect_metrics(self) -> ScalingMetrics:
        """收集当前系统指标"""
        try:
            # 获取并发控制器状态
            concurrency_status = self.concurrency_limiter.get_status()
            
            # 获取 WARP 优化器状态
            warp_status = self.warp_optimizer.get_optimization_status()
            
            # 计算平均响应时间（模拟，实际应该从真实请求中获取）
            avg_response_time = self._calculate_avg_response_time()
            
            # 计算错误率（模拟）
            error_rate = self._calculate_error_rate()
            
            metrics = ScalingMetrics(
                avg_response_time=avg_response_time,
                active_connections=concurrency_status.get("active_requests", 0),
                queue_length=concurrency_status.get("queued_requests", 0),
                error_rate=error_rate,
                config_count=warp_status.get("healthy_configs", 0),
                timestamp=datetime.now()
            )
            
            # 添加到历史记录
            self.metrics_history.append(metrics)
            
            return metrics
            
        except Exception as e:
            logger.error(f"收集指标失败: {e}")
            return ScalingMetrics(timestamp=datetime.now())
    
    def _calculate_avg_response_time(self) -> float:
        """计算平均响应时间（简化实现）"""
        if len(self.metrics_history) == 0:
            return 1.0
        
        # 基于队列长度估算响应时间
        recent_metrics = list(self.metrics_history)[-10:]  # 最近10个指标
        queue_lengths = [m.queue_length for m in recent_metrics]
        
        if not queue_lengths:
            return 1.0
        
        avg_queue = statistics.mean(queue_lengths)
        # 简化计算：队列越长，响应时间越长
        estimated_time = 1.0 + (avg_queue * 0.1)
        
        return min(estimated_time, 10.0)  # 最大10秒
    
    def _calculate_error_rate(self) -> float:
        """计算错误率（简化实现）"""
        if len(self.metrics_history) == 0:
            return 0.0
        
        # 基于配置数量和负载估算错误率
        recent_metrics = list(self.metrics_history)[-5:]
        total_requests = sum(m.active_connections + m.queue_length for m in recent_metrics)
        config_count = recent_metrics[-1].config_count if recent_metrics else 5
        
        if total_requests == 0:
            return 0.0
        
        # 简化计算：配置不足时错误率升高
        if config_count < self.limits.min_configs:
            return 0.2
        elif total_requests > (config_count * 4):  # 每个配置承载超过4个请求
            return 0.1
        else:
            return 0.02
    
    def should_scale_up(self, metrics: ScalingMetrics) -> bool:
        """判断是否应该扩容"""
        if self.is_scaling:
            logger.debug("正在扩容中，跳过")
            return False
        
        # 检查冷却期
        if self.last_scale_time:
            time_since_last = (datetime.now() - self.last_scale_time).total_seconds()
            if time_since_last < self.limits.scale_cooldown:
                logger.debug(f"冷却期内，剩余 {self.limits.scale_cooldown - time_since_last:.0f} 秒")
                return False
        
        # 检查每小时扩容次数限制
        if self._get_scales_in_last_hour() >= self.limits.max_scale_per_hour:
            logger.warning("已达到每小时最大扩容次数限制")
            return False
        
        # 检查是否已达到最大配置数
        if metrics.config_count >= self.limits.max_configs:
            logger.debug(f"已达到最大配置数限制: {self.limits.max_configs}")
            return False
        
        # 性能指标检查
        should_scale = (
            metrics.avg_response_time > self.limits.scale_up_threshold or
            metrics.queue_length > self.limits.max_queue_length or
            metrics.error_rate > self.limits.max_error_rate
        )
        
        if should_scale:
            logger.info(f"满足扩容条件: 响应时间={metrics.avg_response_time:.2f}s, "
                       f"队列长度={metrics.queue_length}, 错误率={metrics.error_rate:.2%}")
        
        return should_scale
    
    def should_scale_down(self, metrics: ScalingMetrics) -> bool:
        """判断是否应该缩容"""
        if self.is_scaling:
            return False
        
        # 检查冷却期
        if self.last_scale_time:
            time_since_last = (datetime.now() - self.last_scale_time).total_seconds()
            if time_since_last < self.limits.scale_cooldown:
                return False
        
        # 检查是否已达到最小配置数
        if metrics.config_count <= self.limits.min_configs:
            return False
        
        # 检查是否有持续的低负载
        if len(self.metrics_history) < 5:
            return False
        
        recent_metrics = list(self.metrics_history)[-5:]
        all_low_load = all(
            m.avg_response_time < self.limits.scale_down_threshold and
            m.queue_length == 0 and
            m.error_rate < 0.05
            for m in recent_metrics
        )
        
        if all_low_load:
            logger.info("检测到持续低负载，考虑缩容")
        
        return all_low_load
    
    def _get_scales_in_last_hour(self) -> int:
        """获取过去一小时的扩容次数"""
        one_hour_ago = datetime.now() - timedelta(hours=1)
        self.scale_operations_per_hour = [
            op_time for op_time in self.scale_operations_per_hour 
            if op_time > one_hour_ago
        ]
        return len(self.scale_operations_per_hour)
    
    async def scale_up(self, target_count: int = None) -> bool:
        """扩容操作"""
        if self.is_scaling:
            logger.warning("扩容操作已在进行中")
            return False
        
        self.is_scaling = True
        try:
            current_metrics = self.collect_metrics()
            current_count = current_metrics.config_count
            
            # 确定目标数量
            if target_count is None:
                target_count = min(current_count + 2, self.limits.max_configs)
            
            add_count = target_count - current_count
            if add_count <= 0:
                logger.info("无需扩容")
                return True
            
            logger.info(f"🚀 开始扩容: {current_count} → {target_count} (+{add_count})")
            
            # 限制并发API调用，避免触发Cloudflare限制
            semaphore = asyncio.Semaphore(self.limits.max_concurrent_registrations)
            
            async def add_single_config(index: int) -> bool:
                async with semaphore:
                    try:
                        logger.info(f"正在生成第 {index+1} 个新配置...")
                        
                        # 添加延迟，避免过于频繁的API调用
                        if index > 0:
                            await asyncio.sleep(self.limits.api_call_interval)
                        
                        config_path = await self.warp_optimizer.warp_manager.add_new_config(
                            f"warp_scale_{int(time.time())}_{index+1:02d}.conf"
                        )
                        
                        if config_path:
                            logger.info(f"✅ 成功添加配置: {config_path}")
                            return True
                        else:
                            logger.error(f"❌ 添加配置失败: {index+1}")
                            return False
                            
                    except Exception as e:
                        logger.error(f"添加配置异常 {index+1}: {e}")
                        return False
            
            # 并发添加配置
            tasks = [add_single_config(i) for i in range(add_count)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            success_count = sum(1 for r in results if r is True)
            
            # 更新记录
            self.last_scale_time = datetime.now()
            self.scale_operations_per_hour.append(self.last_scale_time)
            
            # 触发优化器更新
            await self.warp_optimizer.force_optimization()
            
            logger.info(f"✅ 扩容完成: 成功添加 {success_count}/{add_count} 个配置")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"❌ 扩容操作失败: {e}")
            return False
        finally:
            self.is_scaling = False
    
    async def scale_down(self, target_count: int = None) -> bool:
        """缩容操作"""
        if self.is_scaling:
            logger.warning("缩容操作已在进行中")
            return False
        
        self.is_scaling = True
        try:
            current_metrics = self.collect_metrics()
            current_count = current_metrics.config_count
            
            # 确定目标数量
            if target_count is None:
                target_count = max(current_count - 1, self.limits.min_configs)
            
            remove_count = current_count - target_count
            if remove_count <= 0:
                logger.info("无需缩容")
                return True
            
            logger.info(f"📉 开始缩容: {current_count} → {target_count} (-{remove_count})")
            
            # 缩容逻辑（移除不健康的配置）
            result = await self.warp_optimizer.force_optimization()
            
            self.last_scale_time = datetime.now()
            self.scale_operations_per_hour.append(self.last_scale_time)
            
            logger.info(f"✅ 缩容完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 缩容操作失败: {e}")
            return False
        finally:
            self.is_scaling = False
    
    async def monitor_and_scale(self):
        """监控并执行自动扩缩容"""
        try:
            # 收集指标
            metrics = self.collect_metrics()
            
            logger.debug(f"指标: 响应时间={metrics.avg_response_time:.2f}s, "
                        f"活跃连接={metrics.active_connections}, "
                        f"队列长度={metrics.queue_length}, "
                        f"错误率={metrics.error_rate:.2%}, "
                        f"配置数={metrics.config_count}")
            
            # 判断是否需要扩容
            if self.should_scale_up(metrics):
                await self.scale_up()
            elif self.should_scale_down(metrics):
                await self.scale_down()
            
        except Exception as e:
            logger.error(f"监控扩容失败: {e}")
    
    async def start_monitoring(self, interval: int = 60):
        """开始监控循环"""
        logger.info(f"🔄 开始自动扩容监控 (间隔: {interval}秒)")
        
        while True:
            try:
                await self.monitor_and_scale()
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error(f"监控循环异常: {e}")
                await asyncio.sleep(interval)
    
    def get_status(self) -> Dict:
        """获取扩容器状态"""
        current_metrics = self.collect_metrics() if self.metrics_history else ScalingMetrics()
        
        return {
            "scaling_limits": {
                "min_configs": self.limits.min_configs,
                "max_configs": self.limits.max_configs,
                "target_configs": self.limits.target_configs,
                "max_response_time": self.limits.max_response_time,
                "scale_cooldown": self.limits.scale_cooldown,
                "max_scale_per_hour": self.limits.max_scale_per_hour
            },
            "current_metrics": {
                "avg_response_time": current_metrics.avg_response_time,
                "active_connections": current_metrics.active_connections,
                "queue_length": current_metrics.queue_length,
                "error_rate": current_metrics.error_rate,
                "config_count": current_metrics.config_count
            },
            "scaling_status": {
                "is_scaling": self.is_scaling,
                "last_scale_time": self.last_scale_time.isoformat() if self.last_scale_time else None,
                "scales_in_last_hour": self._get_scales_in_last_hour(),
                "metrics_history_count": len(self.metrics_history)
            },
            "recommendations": self._get_recommendations(current_metrics)
        }
    
    def _get_recommendations(self, metrics: ScalingMetrics) -> List[str]:
        """获取扩容建议"""
        recommendations = []
        
        if metrics.avg_response_time > self.limits.scale_up_threshold:
            recommendations.append(f"响应时间过高 ({metrics.avg_response_time:.2f}s)，建议扩容")
        
        if metrics.queue_length > self.limits.max_queue_length:
            recommendations.append(f"队列过长 ({metrics.queue_length})，建议扩容")
        
        if metrics.error_rate > self.limits.max_error_rate:
            recommendations.append(f"错误率过高 ({metrics.error_rate:.2%})，建议扩容")
        
        if metrics.config_count < self.limits.min_configs:
            recommendations.append(f"配置数不足 ({metrics.config_count})，建议补充到最少 {self.limits.min_configs} 个")
        
        if metrics.config_count > self.limits.max_configs:
            recommendations.append(f"配置数过多 ({metrics.config_count})，建议减少到 {self.limits.max_configs} 个以下")
        
        if self._get_scales_in_last_hour() >= self.limits.max_scale_per_hour:
            recommendations.append("已达到每小时扩容次数限制，请等待")
        
        if not recommendations:
            recommendations.append("系统运行状态良好")
        
        return recommendations


# 全局实例
_scaler: Optional[DynamicWARPScaler] = None

def get_dynamic_scaler(limits: ScalingLimits = None) -> DynamicWARPScaler:
    """获取全局动态扩容器实例"""
    global _scaler
    if _scaler is None:
        _scaler = DynamicWARPScaler(limits)
    return _scaler

async def start_auto_scaling(interval: int = 60):
    """启动自动扩容"""
    scaler = get_dynamic_scaler()
    await scaler.initialize()
    await scaler.start_monitoring(interval) 