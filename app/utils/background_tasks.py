import asyncio
import logging
import psutil
import time
from typing import Optional, List
from app.utils.proxy_pool import get_proxy_pool
from app.utils.metrics import get_metrics

logger = logging.getLogger(__name__)

class BackgroundTaskManager:
    """后台任务管理器"""
    
    def __init__(self):
        self.tasks: List[asyncio.Task] = []
        self.running = False
    
    async def start_all_tasks(self):
        """启动所有后台任务"""
        if self.running:
            return
        
        self.running = True
        logger.info("启动后台任务...")
        
        # 系统监控任务
        system_monitor_task = asyncio.create_task(self._system_monitor_loop())
        self.tasks.append(system_monitor_task)
        
        # 数据清理任务
        cleanup_task = asyncio.create_task(self._cleanup_loop())
        self.tasks.append(cleanup_task)
        
        logger.info(f"已启动 {len(self.tasks)} 个后台任务")
    
    async def stop_all_tasks(self):
        """停止所有后台任务"""
        if not self.running:
            return
        
        self.running = False
        logger.info("停止后台任务...")
        
        # 取消所有任务
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        # 等待任务完成
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        self.tasks.clear()
        logger.info("所有后台任务已停止")
    
    async def _system_monitor_loop(self):
        """系统监控循环 - 每30秒记录一次系统指标"""
        while self.running:
            try:
                # 获取系统指标
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                memory_percent = memory.percent
                
                # 记录到性能监控
                metrics = get_metrics()
                await metrics.record_system_metrics(
                    cpu_usage=cpu_percent,
                    memory_usage=memory_percent,
                    queue_size=0  # 暂时设为0，可以后续添加队列监控
                )
                
                # 记录代理池状态
                proxy_pool = get_proxy_pool()
                if proxy_pool:
                    stats = proxy_pool.get_proxy_stats()
                    logger.debug(f"系统监控 - CPU: {cpu_percent}%, 内存: {memory_percent}%, 代理: {stats['healthy']}/{stats['total']}")
                else:
                    logger.debug(f"系统监控 - CPU: {cpu_percent}%, 内存: {memory_percent}%, 代理池未初始化")
                
                await asyncio.sleep(30)  # 每30秒监控一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"系统监控异常: {e}")
                await asyncio.sleep(60)  # 出错时等待1分钟
    
    async def _cleanup_loop(self):
        """数据清理循环 - 每小时清理一次旧数据"""
        while self.running:
            try:
                # 清理性能指标旧数据
                metrics = get_metrics()
                await metrics.cleanup_old_data()
                
                logger.info("定期数据清理完成")
                
                # 每小时清理一次
                await asyncio.sleep(3600)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"数据清理异常: {e}")
                await asyncio.sleep(1800)  # 出错时等待30分钟


# 全局后台任务管理器
_task_manager: Optional[BackgroundTaskManager] = None

async def start_background_tasks():
    """启动后台任务"""
    global _task_manager
    if _task_manager is None:
        _task_manager = BackgroundTaskManager()
    await _task_manager.start_all_tasks()

async def stop_background_tasks():
    """停止后台任务"""
    global _task_manager
    if _task_manager:
        await _task_manager.stop_all_tasks()
        _task_manager = None

def get_task_manager() -> Optional[BackgroundTaskManager]:
    """获取任务管理器实例"""
    return _task_manager 