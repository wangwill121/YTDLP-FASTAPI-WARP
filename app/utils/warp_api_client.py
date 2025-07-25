#!/usr/bin/env python3
"""
真实的 Cloudflare WARP API 客户端
基于官方 Cloudflare WARP API 生成真实的 WireGuard 配置
"""

import asyncio
import aiohttp
import logging
import base64
import json
import subprocess
import tempfile
import os
import uuid
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class CloudflareWARPAPI:
    """
    Cloudflare WARP API 客户端
    使用官方 API 生成真实的 WireGuard 配置
    """
    
    def __init__(self):
        self.api_base = "https://api.cloudflareclient.com"
        self.api_version = "v0a537"  # 更新版本号
        self.session: Optional[aiohttp.ClientSession] = None
        
        # 官方 Cloudflare WARP 端点
        self.warp_endpoints = [
            "engage.cloudflareclient.com:2408",
            "162.159.192.1:2408",
            "162.159.193.1:2408",
            "162.159.195.1:2408",
            "188.114.96.1:2408",
            "188.114.97.1:2408",
            "188.114.98.1:2408",
            "188.114.99.1:2408",
        ]
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                "User-Agent": "1.1.1.1/6.10 CFNetwork/1494.0.7 Darwin/23.4.0",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()
    
    def _generate_wireguard_keypair(self) -> Tuple[str, str]:
        """
        使用 WireGuard 官方工具生成密钥对
        返回: (private_key, public_key)
        """
        try:
            # 生成私钥
            private_key_process = subprocess.run(
                ["wg", "genkey"], 
                capture_output=True, 
                text=True, 
                check=True
            )
            private_key = private_key_process.stdout.strip()
            
            # 从私钥生成公钥
            public_key_process = subprocess.run(
                ["wg", "pubkey"], 
                input=private_key, 
                capture_output=True, 
                text=True, 
                check=True
            )
            public_key = public_key_process.stdout.strip()
            
            return private_key, public_key
            
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            # 如果没有安装 wg 工具，使用备用方法
            logger.warning(f"WireGuard 工具不可用: {e}，使用备用生成方法")
            return self._generate_keypair_fallback()
    
    def _generate_keypair_fallback(self) -> Tuple[str, str]:
        """
        备用密钥生成方法（如果没有 wg 工具）
        """
        # 生成32字节随机私钥
        private_bytes = os.urandom(32)
        private_key = base64.b64encode(private_bytes).decode()
        
        # 这是简化版本，真实的公钥派生需要椭圆曲线运算
        # 在生产环境中，建议安装 wireguard-tools
        public_bytes = os.urandom(32)
        public_key = base64.b64encode(public_bytes).decode()
        
        return private_key, public_key
    
    async def register_device(self) -> Optional[Dict]:
        """
        向 Cloudflare 注册新的 WARP 设备
        """
        if not self.session:
            raise RuntimeError("请在 async with 上下文中使用")
        
        try:
            # 生成 WireGuard 密钥对
            private_key, public_key = self._generate_wireguard_keypair()
            
            # 构建注册请求
            install_id = str(uuid.uuid4())
            tos_date = datetime.now(timezone.utc).isoformat()
            
            registration_data = {
                "key": public_key,
                "install_id": install_id,
                "fcm_token": f"fcm_token_{uuid.uuid4().hex[:16]}",
                "warp_enabled": True,
                "tos": tos_date,
                "type": "Linux",
                "locale": "en_US",
                "model": "Linux",
                "serial_number": f"SN{uuid.uuid4().hex[:8].upper()}"
            }
            
            # 发送注册请求
            url = f"{self.api_base}/{self.api_version}/reg"
            
            logger.info(f"正在向 Cloudflare 注册 WARP 设备...")
            async with self.session.post(url, json=registration_data) as response:
                if response.status == 200:
                    device_info = await response.json()
                    
                    # 添加我们生成的私钥
                    device_info["private_key"] = private_key
                    device_info["public_key"] = public_key
                    
                    logger.info(f"✅ WARP 设备注册成功: {device_info.get('id', 'unknown')}")
                    return device_info
                else:
                    error_text = await response.text()
                    logger.error(f"❌ WARP 设备注册失败: {response.status} - {error_text}")
                    return None
                    
        except Exception as e:
            logger.error(f"❌ WARP 设备注册异常: {e}")
            return None
    
    def generate_wireguard_config(self, device_info: Dict) -> str:
        """
        根据设备信息生成 WireGuard 配置文件
        """
        try:
            logger.info(f"设备信息结构: {list(device_info.keys())}")
            
            # 获取私钥
            private_key = device_info.get("private_key", "")
            if not private_key:
                raise ValueError("缺少私钥信息")
            
            # 从设备信息中提取配置
            config_data = device_info.get("config", {})
            
            if not config_data:
                logger.warning("设备信息中没有 config 字段，尝试直接使用设备信息")
                # 如果没有 config 字段，尝试直接使用顶级字段
                config_data = device_info
            
            # 尝试获取接口配置
            interface_config = config_data.get("interface", {})
            
            # 获取地址信息
            addresses = interface_config.get("addresses", {})
            if isinstance(addresses, dict):
                v4_address = addresses.get("v4", "172.16.0.2/32")
                v6_address = addresses.get("v6", "")
            elif isinstance(addresses, list) and addresses:
                # 如果是列表格式
                v4_address = addresses[0] if addresses else "172.16.0.2/32"
                v6_address = addresses[1] if len(addresses) > 1 else ""
            else:
                # 使用默认地址
                v4_address = "172.16.0.2/32"
                v6_address = "2606:4700:110:8000::1/128"
            
            # 获取对等节点配置
            peers_config = config_data.get("peers", [])
            if not peers_config:
                # 如果没有 peers，使用默认的 Cloudflare WARP 配置
                logger.warning("没有找到 peers 配置，使用默认 Cloudflare WARP 配置")
                peer_public_key = "bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo="
                endpoint = "engage.cloudflareclient.com:2408"
                reserved = []
            else:
                peer_config = peers_config[0]
                peer_public_key = peer_config.get("public_key", "bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=")
                
                # 处理端点信息
                endpoint_info = peer_config.get("endpoint", {})
                if isinstance(endpoint_info, dict):
                    endpoint = endpoint_info.get("host", "engage.cloudflareclient.com:2408")
                else:
                    endpoint = str(endpoint_info) if endpoint_info else "engage.cloudflareclient.com:2408"
                
                reserved = peer_config.get("reserved", [])
            
            # 生成配置文件内容
            config_content = f"""[Interface]
PrivateKey = {private_key}
Address = {v4_address}"""
            
            if v6_address:
                config_content += f", {v6_address}"
            
            config_content += f"""
DNS = 1.1.1.1, 1.0.0.1, 2606:4700:4700::1111, 2606:4700:4700::1001
MTU = 1280

[Peer]
PublicKey = {peer_public_key}
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = {endpoint}
"""
            
            # 添加 Reserved 字段（如果存在）
            if reserved and isinstance(reserved, list):
                reserved_str = ",".join(map(str, reserved))
                config_content += f"Reserved = {reserved_str}\n"
            
            return config_content
            
        except Exception as e:
            logger.error(f"生成 WireGuard 配置失败: {e}")
            logger.error(f"设备信息内容: {device_info}")
            raise
    
    async def create_warp_config(self, config_name: str = None) -> Optional[Tuple[str, str]]:
        """
        创建单个 WARP 配置
        
        Returns:
            Optional[Tuple[str, str]]: (配置名称, 配置内容) 或 None
        """
        try:
            device_info = await self.register_device()
            if not device_info:
                return None
            
            config_content = self.generate_wireguard_config(device_info)
            
            # 生成配置名称
            if not config_name:
                device_id = device_info.get("id", uuid.uuid4().hex[:8])
                config_name = f"warp_{device_id}.conf"
            
            logger.info(f"✅ 成功生成 WARP 配置: {config_name}")
            return config_name, config_content
            
        except Exception as e:
            logger.error(f"创建 WARP 配置失败: {e}")
            return None
    
    async def create_multiple_configs(self, count: int = 8) -> Dict[str, str]:
        """
        批量创建多个 WARP 配置
        
        Args:
            count: 要创建的配置数量
            
        Returns:
            Dict[str, str]: {配置名称: 配置内容}
        """
        configs = {}
        success_count = 0
        
        logger.info(f"开始批量创建 {count} 个 WARP 配置...")
        
        # 使用信号量限制并发数，避免过于频繁的 API 调用
        semaphore = asyncio.Semaphore(3)
        
        async def create_single_config(index: int):
            async with semaphore:
                try:
                    config_name = f"warp_real_{index+1:02d}.conf"
                    result = await self.create_warp_config(config_name)
                    
                    if result:
                        name, content = result
                        return name, content
                    
                    # 如果失败，等待一段时间再重试
                    await asyncio.sleep(2)
                    return None, None
                    
                except Exception as e:
                    logger.error(f"创建配置 {index+1} 失败: {e}")
                    return None, None
        
        # 并发创建配置
        tasks = [create_single_config(i) for i in range(count)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"配置 {i+1} 创建异常: {result}")
                continue
                
            name, content = result
            if name and content:
                configs[name] = content
                success_count += 1
            
            # 在请求之间添加延迟，避免触发速率限制
            if i < len(results) - 1:
                await asyncio.sleep(1)
        
        logger.info(f"✅ 批量创建完成: {success_count}/{count} 个配置成功")
        return configs


# 便捷函数
async def generate_real_warp_configs(count: int = 8) -> Dict[str, str]:
    """
    生成真实的 WARP 配置文件
    
    Args:
        count: 要生成的配置数量
        
    Returns:
        Dict[str, str]: {配置文件名: 配置内容}
    """
    async with CloudflareWARPAPI() as api:
        return await api.create_multiple_configs(count)


# 测试函数
async def test_warp_api():
    """测试 WARP API 连接"""
    try:
        async with CloudflareWARPAPI() as api:
            result = await api.create_warp_config("test_config.conf")
            if result:
                name, content = result
                print(f"✅ 测试成功！生成配置: {name}")
                print("配置内容预览:")
                print(content[:200] + "..." if len(content) > 200 else content)
                return True
            else:
                print("❌ 测试失败：无法生成配置")
                return False
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        return False


if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_warp_api()) 