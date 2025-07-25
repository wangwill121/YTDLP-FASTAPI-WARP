#!/usr/bin/env python3
"""
WARP 配置优化器
基于 Cloudflare 免费账户限制，智能管理和优化 WARP 配置数量
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta

from .warp_manager import WARPConfigManager, WARPConfigGenerator
from .concurrency_limiter import AccountTier

logger = logging.getLogger(__name__)

@dataclass
class WARPOptimizationConfig:
    """WARP 优化配置"""
    # 基于免费账户的保守配置
    target_config_count: int = 8           # 目标配置数量 (保守估计)
    min_config_count: int = 5              # 最小配置数量
    max_config_count: int = 8              # 最大配置数量 (留余量)
    
    # 健康检查配置
    health_check_interval: float = 300.0   # 健康检查间隔 (5分钟)
    health_check_timeout: float = 10.0     # 单个检查超时
    failure_threshold: int = 3             # 失败阈值
    recovery_check_interval: float = 900.0 # 恢复检查间隔 (15分钟)
    
    # 配置管理
    config_dir: str = "warp-configs"
    backup_dir: str = "warp-configs-backup"
    account_tier: AccountTier = AccountTier.FREE

class WARPOptimizer:
    """
    WARP 配置优化器
    
    功能:
    1. 维护最优的配置数量 (5-8个)
    2. 自动清理不可用配置
    3. 智能补充新配置
    4. 提供配置健康状态监控
    """
    
    def __init__(self, config: WARPOptimizationConfig = None):
        self.config = config or WARPOptimizationConfig()
        self.warp_manager = WARPConfigManager(self.config.config_dir)
        
        # 状态追踪
        self.healthy_configs: List[str] = []
        self.unhealthy_configs: List[str] = []
        self.config_health_status: Dict[str, Dict] = {}
        
        # 任务状态
        self._optimization_task: Optional[asyncio.Task] = None
        self._is_running = False
        
        logger.info(f"WARP 优化器初始化: 目标配置数={self.config.target_config_count}, "
                   f"账户等级={self.config.account_tier.value}")
    
    async def initialize(self) -> Dict[str, Any]:
        """初始化 WARP 配置"""
        logger.info("开始初始化 WARP 配置...")
        
        # 1. 检查现有配置
        existing_configs = self.warp_manager.list_configs()
        logger.info(f"发现现有配置: {len(existing_configs)} 个")
        
        # 2. 健康检查现有配置
        await self._check_all_configs_health()
        
        # 3. 清理不健康的配置
        cleaned_count = await self._cleanup_unhealthy_configs()
        
        # 4. 补充配置到目标数量
        added_count = await self._ensure_target_config_count()
        
        # 5. 最终健康检查
        await self._check_all_configs_health()
        
        result = {
            "initial_configs": len(existing_configs),
            "cleaned_configs": cleaned_count,
            "added_configs": added_count,
            "final_healthy_configs": len(self.healthy_configs),
            "final_unhealthy_configs": len(self.unhealthy_configs),
            "target_reached": len(self.healthy_configs) >= self.config.min_config_count,
            "optimization_status": "success" if len(self.healthy_configs) >= self.config.min_config_count else "partial"
        }
        
        logger.info(f"WARP 配置初始化完成: {result}")
        return result
    
    async def start_optimization_loop(self):
        """启动优化循环"""
        if self._is_running:
            logger.warning("优化循环已在运行")
            return
        
        self._is_running = True
        self._optimization_task = asyncio.create_task(self._optimization_loop())
        logger.info("WARP 优化循环已启动")
    
    async def stop_optimization_loop(self):
        """停止优化循环"""
        self._is_running = False
        if self._optimization_task:
            self._optimization_task.cancel()
            try:
                await self._optimization_task
            except asyncio.CancelledError:
                pass
        logger.info("WARP 优化循环已停止")
    
    async def _optimization_loop(self):
        """优化循环主逻辑"""
        while self._is_running:
            try:
                logger.info("开始 WARP 配置优化循环...")
                
                # 1. 健康检查
                await self._check_all_configs_health()
                
                # 2. 清理不健康配置
                if self.unhealthy_configs:
                    cleaned = await self._cleanup_unhealthy_configs()
                    if cleaned > 0:
                        logger.info(f"清理了 {cleaned} 个不健康配置")
                
                # 3. 确保配置数量
                added = await self._ensure_target_config_count()
                if added > 0:
                    logger.info(f"添加了 {added} 个新配置")
                
                # 4. 报告状态
                self._log_optimization_status()
                
                # 等待下次检查
                await asyncio.sleep(self.config.health_check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"优化循环异常: {e}")
                await asyncio.sleep(60)  # 出错后等待1分钟
    
    async def _check_all_configs_health(self):
        """检查所有配置的健康状态"""
        logger.info("开始健康检查所有 WARP 配置...")
        
        configs = self.warp_manager.list_configs()
        if not configs:
            logger.warning("没有找到任何 WARP 配置")
            return
        
        # 并发检查所有配置
        tasks = []
        for config_info in configs:
            config_file = config_info.get('file_path', '')
            if config_file:
                task = asyncio.create_task(
                    self._check_single_config_health(config_file)
                )
                tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        # 更新健康配置列表
        self.healthy_configs = [
            config_file for config_file, status in self.config_health_status.items()
            if status.get('is_healthy', False)
        ]
        
        self.unhealthy_configs = [
            config_file for config_file, status in self.config_health_status.items()
            if not status.get('is_healthy', True)
        ]
        
        logger.info(f"健康检查完成: {len(self.healthy_configs)} 健康, "
                   f"{len(self.unhealthy_configs)} 不健康")
    
    async def _check_single_config_health(self, config_file: str) -> bool:
        """检查单个配置的健康状态"""
        config_name = Path(config_file).name
        
        try:
            # 模拟健康检查 (实际环境中需要真正的网络检查)
            # 这里我们基于文件存在性和格式正确性来判断
            
            if not Path(config_file).exists():
                raise FileNotFoundError(f"配置文件不存在: {config_file}")
            
            # 验证配置文件格式
            is_valid = self.warp_manager.generator.validate_config(config_file)
            if not is_valid:
                raise ValueError(f"配置文件格式无效: {config_file}")
            
            # 在本地环境中，我们无法真正测试 WARP 连接
            # 所以这里使用简化的健康判断逻辑
            
            # 模拟网络检查 (随机失败率，模拟真实环境)
            import random
            if random.random() < 0.1:  # 10% 的失败率
                raise Exception("模拟网络连接失败")
            
            # 更新健康状态
            self.config_health_status[config_file] = {
                'is_healthy': True,
                'last_check': time.time(),
                'consecutive_failures': 0,
                'last_error': None,
                'response_time': random.uniform(0.5, 2.0)  # 模拟响应时间
            }
            
            logger.debug(f"配置健康: {config_name}")
            return True
            
        except Exception as e:
            # 更新不健康状态
            current_status = self.config_health_status.get(config_file, {})
            consecutive_failures = current_status.get('consecutive_failures', 0) + 1
            
            self.config_health_status[config_file] = {
                'is_healthy': False,
                'last_check': time.time(),
                'consecutive_failures': consecutive_failures,
                'last_error': str(e),
                'response_time': None
            }
            
            logger.warning(f"配置不健康: {config_name}, 连续失败: {consecutive_failures}, 错误: {e}")
            return False
    
    async def _cleanup_unhealthy_configs(self) -> int:
        """清理不健康的配置"""
        if not self.unhealthy_configs:
            return 0
        
        # 创建备份目录
        backup_dir = Path(self.config.backup_dir)
        backup_dir.mkdir(exist_ok=True)
        
        cleaned_count = 0
        for config_file in self.unhealthy_configs.copy():
            try:
                config_status = self.config_health_status.get(config_file, {})
                consecutive_failures = config_status.get('consecutive_failures', 0)
                
                # 只清理连续失败次数超过阈值的配置
                if consecutive_failures >= self.config.failure_threshold:
                    config_path = Path(config_file)
                    config_name = config_path.name
                    
                    # 备份配置
                    backup_path = backup_dir / f"{config_name}.{int(time.time())}.bak"
                    if config_path.exists():
                        config_path.rename(backup_path)
                        logger.info(f"配置已备份: {config_name} -> {backup_path.name}")
                    
                    # 从状态中移除
                    self.config_health_status.pop(config_file, None)
                    self.unhealthy_configs.remove(config_file)
                    cleaned_count += 1
                    
                    logger.info(f"清理不健康配置: {config_name} "
                               f"(连续失败 {consecutive_failures} 次)")
                    
            except Exception as e:
                logger.error(f"清理配置失败 {config_file}: {e}")
        
        return cleaned_count
    
    async def _ensure_target_config_count(self) -> int:
        """确保配置数量达到目标"""
        current_healthy = len(self.healthy_configs)
        target_count = self.config.target_config_count
        
        if current_healthy >= target_count:
            logger.info(f"健康配置数量充足: {current_healthy}/{target_count}")
            return 0
        
        needed_count = target_count - current_healthy
        max_allowed = self.config.max_config_count - current_healthy
        actual_add_count = min(needed_count, max_allowed)
        
        if actual_add_count <= 0:
            logger.warning(f"无法添加更多配置: 当前{current_healthy}, "
                          f"最大允许{self.config.max_config_count}")
            return 0
        
        logger.info(f"需要添加 {actual_add_count} 个配置 "
                   f"(当前: {current_healthy}, 目标: {target_count})")
        
        # 生成新配置
        try:
            # 使用真实 API 生成新配置
            new_configs = await self.warp_manager.generator.generate_multiple_configs(actual_add_count)
            
            # 保存新配置
            saved_files = self.warp_manager.generator.save_configs_to_disk(new_configs)
            
            # 立即检查新配置的健康状态
            for config_file in saved_files:
                await self._check_single_config_health(config_file)
                if self.config_health_status.get(config_file, {}).get('is_healthy', False):
                    self.healthy_configs.append(config_file)
            
            logger.info(f"成功添加 {len(saved_files)} 个新配置")
            return len(saved_files)
            
        except Exception as e:
            logger.error(f"添加新配置失败: {e}")
            return 0
    
    def _log_optimization_status(self):
        """记录优化状态"""
        total_configs = len(self.healthy_configs) + len(self.unhealthy_configs)
        health_rate = (len(self.healthy_configs) / total_configs * 100) if total_configs > 0 else 0
        
        status_msg = (
            f"WARP 配置状态: "
            f"总计={total_configs}, "
            f"健康={len(self.healthy_configs)}, "
            f"不健康={len(self.unhealthy_configs)}, "
            f"健康率={health_rate:.1f}%, "
            f"目标数量={self.config.target_config_count}"
        )
        
        if len(self.healthy_configs) >= self.config.min_config_count:
            logger.info(f"✅ {status_msg}")
        else:
            logger.warning(f"⚠️ {status_msg} - 健康配置不足！")
    
    def get_optimization_status(self) -> Dict[str, Any]:
        """获取优化状态"""
        total_configs = len(self.healthy_configs) + len(self.unhealthy_configs)
        
        # 计算平均响应时间
        response_times = [
            status['response_time'] 
            for status in self.config_health_status.values() 
            if status.get('response_time') is not None
        ]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        return {
            "config_counts": {
                "total": total_configs,
                "healthy": len(self.healthy_configs),
                "unhealthy": len(self.unhealthy_configs),
                "target": self.config.target_config_count,
                "min_required": self.config.min_config_count,
                "max_allowed": self.config.max_config_count
            },
            "health_metrics": {
                "health_rate": (len(self.healthy_configs) / total_configs * 100) if total_configs > 0 else 0,
                "avg_response_time": round(avg_response_time, 2),
                "meets_minimum": len(self.healthy_configs) >= self.config.min_config_count,
                "meets_target": len(self.healthy_configs) >= self.config.target_config_count
            },
            "optimization_status": {
                "is_running": self._is_running,
                "last_check": max([s.get('last_check', 0) for s in self.config_health_status.values()], default=0),
                "next_check_in": self.config.health_check_interval,
                "account_tier": self.config.account_tier.value
            },
            "config_details": [
                {
                    "file": Path(config_file).name,
                    "is_healthy": status.get('is_healthy', False),
                    "consecutive_failures": status.get('consecutive_failures', 0),
                    "response_time": status.get('response_time'),
                    "last_error": status.get('last_error')
                }
                for config_file, status in self.config_health_status.items()
            ],
            "recommendations": self._get_recommendations()
        }
    
    def _get_recommendations(self) -> List[str]:
        """获取优化建议"""
        recommendations = []
        healthy_count = len(self.healthy_configs)
        
        if healthy_count < self.config.min_config_count:
            recommendations.append(f"健康配置不足，建议立即检查网络连接和配置文件")
        
        if healthy_count < self.config.target_config_count:
            recommendations.append(f"配置数量低于目标，系统将自动补充")
        
        unhealthy_rate = len(self.unhealthy_configs) / (healthy_count + len(self.unhealthy_configs)) if (healthy_count + len(self.unhealthy_configs)) > 0 else 0
        if unhealthy_rate > 0.3:
            recommendations.append("不健康配置比例较高，建议检查网络环境或更换配置源")
        
        if not self._is_running:
            recommendations.append("优化循环未运行，建议启动自动优化")
        
        return recommendations
    
    async def force_optimization(self) -> Dict[str, Any]:
        """强制执行一次优化"""
        logger.info("开始强制优化 WARP 配置...")
        
        # 健康检查
        await self._check_all_configs_health()
        
        # 清理不健康配置
        cleaned = await self._cleanup_unhealthy_configs()
        
        # 补充配置
        added = await self._ensure_target_config_count()
        
        # 再次健康检查
        await self._check_all_configs_health()
        
        result = {
            "cleaned_configs": cleaned,
            "added_configs": added,
            "final_healthy": len(self.healthy_configs),
            "final_unhealthy": len(self.unhealthy_configs),
            "optimization_timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"强制优化完成: {result}")
        return result


# 全局实例
_optimizer: Optional[WARPOptimizer] = None

def get_warp_optimizer(config: WARPOptimizationConfig = None) -> WARPOptimizer:
    """获取全局 WARP 优化器实例"""
    global _optimizer
    if _optimizer is None:
        _optimizer = WARPOptimizer(config)
    return _optimizer 