import asyncio
import aiohttp
import logging
import time
import random
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class ProxyInfo:
    """代理信息类"""
    host: str
    port: int
    protocol: str = "socks5"
    
    # 健康状态
    is_healthy: bool = True
    last_check: float = field(default_factory=time.time)
    response_time: float = 0.0
    error_count: int = 0
    success_count: int = 0
    
    # 使用统计
    last_used: float = 0.0
    concurrent_requests: int = 0
    max_concurrent: int = 10
    
    # WARP 配置信息 (可选)
    config_file: Optional[str] = None
    endpoint: str = ""
    
    @property
    def url(self) -> str:
        """返回代理 URL"""
        return f"{self.protocol}://{self.host}:{self.port}"
    
    @property
    def success_rate(self) -> float:
        """成功率计算"""
        total = self.success_count + self.error_count
        if total == 0:
            return 1.0
        return self.success_count / total
    
    @property
    def health_score(self) -> float:
        """健康分数 (0-1)"""
        if not self.is_healthy:
            return 0.0
        
        # 基础分数：成功率
        score = self.success_rate
        
        # 响应时间惩罚 (>5秒开始扣分)
        if self.response_time > 5.0:
            score *= max(0.1, 1.0 - (self.response_time - 5.0) / 10.0)
        
        # 并发数惩罚
        if self.concurrent_requests >= self.max_concurrent:
            score *= 0.1
        
        return max(0.0, min(1.0, score))


class WARPProxyPool:
    """WARP 代理池管理器 - 生产环境版本"""
    
    def __init__(self, config_dir: str = "warp-configs", health_check_interval: int = 300):
        self.config_dir = Path(config_dir)
        self.health_check_interval = health_check_interval
        self.proxies: Dict[str, ProxyInfo] = {}
        self.round_robin_index = 0
        self._lock = asyncio.Lock()
        self._health_check_task: Optional[asyncio.Task] = None
        
        # 只加载生产环境的 WARP 配置文件代理
        self._load_warp_config_proxies()
    
    def _load_warp_config_proxies(self):
        """加载 WARP 配置文件代理 (生产环境优化版本)"""
        logger.info("加载生产环境 WARP 配置代理...")
        
        if not self.config_dir.exists():
            logger.warning(f"WARP 配置目录不存在: {self.config_dir}")
            return
        
        # 扫描配置文件
        config_files = list(self.config_dir.glob("*.conf"))
        if not config_files:
            logger.warning(f"未找到 WARP 配置文件: {self.config_dir}")
            return
        
        # 限制配置数量 (基于 Cloudflare 免费账户限制)
        max_configs = 8  # 保守限制
        if len(config_files) > max_configs:
            logger.warning(f"配置文件过多 ({len(config_files)})，仅使用前 {max_configs} 个")
            config_files = config_files[:max_configs]
        
        # 为每个配置文件创建代理信息
        for config_file in config_files:
            config_name = config_file.stem
            
            # 从配置文件中提取端点信息
            endpoint_info = self._parse_warp_config(config_file)
            if endpoint_info:
                host, port = endpoint_info
                proxy_id = f"warp_{config_name}"
                
                self.proxies[proxy_id] = ProxyInfo(
                    host=host,
                    port=port,
                    config_file=str(config_file),
                    endpoint=f"{host}:{port}",
                    max_concurrent=4  # 降低单个代理并发数
                )
            else:
                logger.warning(f"无法解析配置文件: {config_file}")
        
        logger.info(f"已加载 {len(self.proxies)} 个 WARP 配置代理")
    
    def _parse_warp_config(self, config_file: Path) -> Optional[Tuple[str, int]]:
        """解析 WARP 配置文件，提取端点信息"""
        try:
            with open(config_file, 'r') as f:
                content = f.read()
            
            # 查找 Endpoint 行
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('Endpoint'):
                    # 格式: Endpoint = host:port
                    endpoint = line.split('=', 1)[1].strip()
                    if ':' in endpoint:
                        host, port_str = endpoint.rsplit(':', 1)
                        try:
                            port = int(port_str)
                            return host, port
                        except ValueError:
                            pass
            
            # 如果没有找到端点，使用默认的 Cloudflare WARP 端点
            return "engage.cloudflareclient.com", 2408
            
        except Exception as e:
            logger.error(f"解析配置文件失败 {config_file}: {e}")
            return None
    
    async def start_health_check(self):
        """启动健康检查任务"""
        if self._health_check_task and not self._health_check_task.done():
            return
        
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("WARP 代理池健康检查已启动")
    
    async def stop_health_check(self):
        """停止健康检查任务"""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        logger.info("WARP 代理池健康检查已停止")
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while True:
            try:
                await self._check_all_proxies()
                await asyncio.sleep(self.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查异常: {e}")
                await asyncio.sleep(60)  # 出错时短暂等待
    
    async def _check_all_proxies(self):
        """检查所有代理的健康状态"""
        if not self.proxies:
            return
        
        tasks = []
        for proxy_id, proxy in self.proxies.items():
            task = asyncio.create_task(self._check_single_proxy(proxy_id, proxy))
            tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        # 记录健康状态
        healthy_count = sum(1 for p in self.proxies.values() if p.is_healthy)
        logger.info(f"代理健康检查完成: {healthy_count}/{len(self.proxies)} 健康")
    
    async def _check_single_proxy(self, proxy_id: str, proxy: ProxyInfo):
        """检查单个代理的健康状态"""
        start_time = time.time()
        
        try:
            # 使用代理访问测试 URL
            connector = aiohttp.TCPConnector()
            proxy_url = proxy.url
            
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            ) as session:
                test_url = "https://www.youtube.com"
                async with session.get(
                    test_url,
                    proxy=proxy_url
                ) as response:
                    if response.status == 200:
                        proxy.is_healthy = True
                        proxy.success_count += 1
                        proxy.error_count = max(0, proxy.error_count - 1)  # 成功时减少错误计数
                    else:
                        raise aiohttp.ClientError(f"HTTP {response.status}")
            
        except Exception as e:
            proxy.is_healthy = False
            proxy.error_count += 1
            logger.warning(f"代理 {proxy_id} 检查失败: {e}")
        
        finally:
            proxy.response_time = time.time() - start_time
            proxy.last_check = time.time()
    
    async def get_best_proxy(self) -> Optional[ProxyInfo]:
        """获取最佳代理"""
        async with self._lock:
            healthy_proxies = [
                proxy for proxy in self.proxies.values()
                if proxy.is_healthy and proxy.concurrent_requests < proxy.max_concurrent
            ]
            
            if not healthy_proxies:
                logger.warning("没有可用的健康代理")
                return None
            
            # 按健康分数排序，选择最佳代理
            healthy_proxies.sort(key=lambda p: p.health_score, reverse=True)
            best_proxy = healthy_proxies[0]
            
            # 更新使用统计
            best_proxy.last_used = time.time()
            best_proxy.concurrent_requests += 1
            
            return best_proxy
    
    async def release_proxy(self, proxy: ProxyInfo, success: bool = True):
        """释放代理"""
        async with self._lock:
            proxy.concurrent_requests = max(0, proxy.concurrent_requests - 1)
            
            if success:
                proxy.success_count += 1
            else:
                proxy.error_count += 1
                # 连续失败太多次，标记为不健康
                if proxy.error_count >= 5:
                    proxy.is_healthy = False
    
    def get_proxy_stats(self) -> Dict:
        """获取代理池统计信息"""
        if not self.proxies:
            return {
                "total": 0,
                "healthy": 0,
                "average_response_time": 0.0,
                "average_success_rate": 0.0
            }
        
        healthy_proxies = [p for p in self.proxies.values() if p.is_healthy]
        
        avg_response_time = sum(p.response_time for p in self.proxies.values()) / len(self.proxies)
        avg_success_rate = sum(p.success_rate for p in self.proxies.values()) / len(self.proxies)
        
        return {
            "total": len(self.proxies),
            "healthy": len(healthy_proxies),
            "average_response_time": round(avg_response_time, 2),
            "average_success_rate": round(avg_success_rate * 100, 1)
        }


# 全局代理池实例
_proxy_pool: Optional[WARPProxyPool] = None

async def initialize_proxy_pool(config_dir: str = "warp-configs", health_check_interval: int = 300):
    """初始化代理池"""
    global _proxy_pool
    _proxy_pool = WARPProxyPool(config_dir, health_check_interval)
    await _proxy_pool.start_health_check()
    return _proxy_pool

async def shutdown_proxy_pool():
    """关闭代理池"""
    global _proxy_pool
    if _proxy_pool:
        await _proxy_pool.stop_health_check()
        _proxy_pool = None

def get_proxy_pool() -> Optional[WARPProxyPool]:
    """获取代理池实例"""
    return _proxy_pool 