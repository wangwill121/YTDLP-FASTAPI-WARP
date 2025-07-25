#!/usr/bin/env python3
"""
WARP 配置管理器
使用真实的 Cloudflare WARP API 生成和管理 WireGuard 配置
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime

from .warp_api_client import CloudflareWARPAPI, generate_real_warp_configs

logger = logging.getLogger(__name__)

class WARPConfigGenerator:
    """WARP 配置生成器 - 使用真实的 Cloudflare API"""
    
    def __init__(self, config_dir: str = "warp-configs"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        
        logger.info("WARP 配置生成器初始化 - 使用真实的 Cloudflare API")
    
    async def generate_config(self, config_id: int) -> str:
        """
        生成单个 WARP 配置文件 (使用真实 API)
        """
        try:
            async with CloudflareWARPAPI() as api:
                config_name = f"warp_api_{config_id:02d}.conf"
                result = await api.create_warp_config(config_name)
                
                if result:
                    _, config_content = result
                    return config_content
                else:
                    raise Exception(f"无法从 Cloudflare API 生成配置 {config_id}")
                    
        except Exception as e:
            logger.error(f"生成配置 {config_id} 失败: {e}")
            # 返回错误提示而不是模拟数据
            raise Exception(f"WARP 配置生成失败: {e}")
    
    async def generate_multiple_configs(self, count: int = 8) -> Dict[str, str]:
        """
        生成多个 WARP 配置 (使用真实 API)
        """
        try:
            logger.info(f"正在通过 Cloudflare API 生成 {count} 个真实 WARP 配置...")
            
            # 使用真实的 API 生成配置
            configs = await generate_real_warp_configs(count)
            
            if not configs:
                raise Exception("无法从 Cloudflare API 生成任何配置")
            
            logger.info(f"✅ 成功生成 {len(configs)} 个真实 WARP 配置")
            return configs
            
        except Exception as e:
            logger.error(f"批量生成配置失败: {e}")
            raise
    
    def save_configs_to_disk(self, configs: Dict[str, str]) -> List[str]:
        """保存配置到磁盘"""
        saved_files = []
        
        for filename, content in configs.items():
            config_path = self.config_dir / filename
            
            try:
                with open(config_path, 'w') as f:
                    f.write(content)
                saved_files.append(str(config_path))
                logger.info(f"✅ 已保存真实 WARP 配置: {filename}")
            except Exception as e:
                logger.error(f"保存配置文件失败 {filename}: {e}")
        
        return saved_files
    
    def validate_config(self, config_file: str) -> bool:
        """验证配置文件格式"""
        try:
            config_path = Path(config_file)
            if not config_path.exists():
                return False
            
            with open(config_path, 'r') as f:
                content = f.read()
            
            # 检查必要的配置段
            required_sections = ['[Interface]', '[Peer]']
            required_fields = ['PrivateKey', 'Address', 'PublicKey', 'Endpoint']
            
            for section in required_sections:
                if section not in content:
                    logger.warning(f"配置文件缺少 {section} 段: {config_file}")
                    return False
            
            for field in required_fields:
                if field not in content:
                    logger.warning(f"配置文件缺少 {field} 字段: {config_file}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"验证配置文件失败 {config_file}: {e}")
            return False
    
    def scan_existing_configs(self) -> List[str]:
        """扫描现有配置文件"""
        if not self.config_dir.exists():
            return []
        
        config_files = list(self.config_dir.glob("*.conf"))
        return [str(f) for f in config_files]
    
    def get_config_info(self, config_file: str) -> Optional[Dict]:
        """获取配置文件信息"""
        try:
            config_path = Path(config_file)
            if not config_path.exists():
                return None
            
            # 获取文件基本信息
            stat = config_path.stat()
            info = {
                "file_path": str(config_path),
                "file_name": config_path.name,
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "is_valid": self.validate_config(config_file)
            }
            
            # 尝试解析配置内容
            try:
                with open(config_path, 'r') as f:
                    content = f.read()
                
                # 提取关键信息
                for line in content.split('\n'):
                    line = line.strip()
                    if line.startswith('Address'):
                        info["address"] = line.split('=', 1)[1].strip()
                    elif line.startswith('Endpoint'):
                        info["endpoint"] = line.split('=', 1)[1].strip()
                    elif line.startswith('PublicKey') and '[Peer]' in content:
                        # 这是 Peer 的公钥，不是我们的
                        pass
                
            except Exception as e:
                logger.warning(f"解析配置文件内容失败 {config_file}: {e}")
            
            return info
            
        except Exception as e:
            logger.error(f"获取配置文件信息失败 {config_file}: {e}")
            return None


class WARPConfigManager:
    """WARP 配置管理器 - 使用真实 API"""
    
    def __init__(self, config_dir: str = "warp-configs"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        self.generator = WARPConfigGenerator(config_dir)
        
        logger.info("WARP 配置管理器初始化 - 集成真实 Cloudflare API")
    
    async def setup_initial_configs(self, count: int = 8) -> Dict[str, Any]:
        """初始化配置文件 (使用真实 API)"""
        logger.info(f"🚀 开始通过 Cloudflare API 设置 {count} 个真实 WARP 配置...")
        
        try:
            # 检查现有配置
            existing_configs = self.list_configs()
            valid_existing = [c for c in existing_configs if c.get('is_valid', False)]
            
            if len(valid_existing) >= count:
                logger.info(f"✅ 已有足够的有效配置 ({len(valid_existing)})，跳过生成")
                return {
                    "total_generated": 0,
                    "existing_valid": len(valid_existing),
                    "saved_files": 0,
                    "valid_configs": len(valid_existing),
                    "invalid_configs": 0,
                    "config_dir": str(self.config_dir),
                    "files": [c['file_path'] for c in valid_existing]
                }
            
            # 计算需要生成的数量
            needed_count = count - len(valid_existing)
            logger.info(f"需要生成 {needed_count} 个新配置 (现有有效配置: {len(valid_existing)})")
            
            # 通过 Cloudflare API 生成配置
            configs = await self.generator.generate_multiple_configs(needed_count)
            
            if not configs:
                logger.error("❌ 无法从 Cloudflare API 生成任何配置")
                return {
                    "total_generated": 0,
                    "error": "Cloudflare API 生成配置失败",
                    "existing_valid": len(valid_existing)
                }
            
            # 保存到磁盘
            saved_files = self.generator.save_configs_to_disk(configs)
            
            # 验证生成的配置
            valid_configs = []
            invalid_configs = []
            
            for config_file in saved_files:
                if self.generator.validate_config(config_file):
                    valid_configs.append(config_file)
                else:
                    invalid_configs.append(config_file)
            
            total_valid = len(valid_existing) + len(valid_configs)
            
            result = {
                "total_generated": len(configs),
                "existing_valid": len(valid_existing),
                "saved_files": len(saved_files),
                "valid_configs": total_valid,
                "invalid_configs": len(invalid_configs),
                "config_dir": str(self.config_dir),
                "files": valid_configs,
                "api_source": "真实 Cloudflare WARP API"
            }
            
            logger.info(f"✅ WARP 配置设置完成: {total_valid} 个有效配置 (通过真实 API)")
            return result
            
        except Exception as e:
            logger.error(f"❌ 设置 WARP 配置失败: {e}")
            return {
                "total_generated": 0,
                "error": str(e),
                "api_source": "真实 Cloudflare WARP API"
            }
    
    def list_configs(self) -> List[Dict]:
        """列出所有配置文件"""
        configs = []
        config_files = self.generator.scan_existing_configs()
        
        for config_file in config_files:
            info = self.generator.get_config_info(config_file)
            if info:
                configs.append(info)
        
        return configs
    
    async def add_new_config(self, config_name: str = None) -> Optional[str]:
        """添加新的配置文件 (使用真实 API)"""
        try:
            async with CloudflareWARPAPI() as api:
                result = await api.create_warp_config(config_name)
                
                if result:
                    name, content = result
                    
                    # 保存到磁盘
                    config_path = self.config_dir / name
                    with open(config_path, 'w') as f:
                        f.write(content)
                    
                    logger.info(f"✅ 添加新的真实 WARP 配置: {name}")
                    return str(config_path)
                else:
                    logger.error("❌ 无法从 Cloudflare API 生成新配置")
                    return None
                    
        except Exception as e:
            logger.error(f"添加新配置失败: {e}")
            return None
    
    def remove_config(self, config_file: str) -> bool:
        """移除配置文件"""
        try:
            config_path = Path(config_file)
            if config_path.exists():
                # 创建备份
                backup_dir = self.config_dir / "backup"
                backup_dir.mkdir(exist_ok=True)
                
                backup_path = backup_dir / f"{config_path.name}.{int(datetime.now().timestamp())}.bak"
                config_path.rename(backup_path)
                
                logger.info(f"✅ 配置文件已移除并备份: {config_path.name}")
                return True
            else:
                logger.warning(f"配置文件不存在: {config_file}")
                return False
                
        except Exception as e:
            logger.error(f"移除配置文件失败 {config_file}: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """获取管理器状态"""
        configs = self.list_configs()
        valid_configs = [c for c in configs if c.get('is_valid', False)]
        
        return {
            "config_dir": str(self.config_dir),
            "total_configs": len(configs),
            "valid_configs": len(valid_configs),
            "invalid_configs": len(configs) - len(valid_configs),
            "api_type": "真实 Cloudflare WARP API",
            "last_check": datetime.now().isoformat()
        }


# 全局实例
_warp_manager: Optional[WARPConfigManager] = None

def get_warp_manager(config_dir: str = "warp-configs") -> WARPConfigManager:
    """获取全局 WARP 管理器实例"""
    global _warp_manager
    if _warp_manager is None:
        _warp_manager = WARPConfigManager(config_dir)
    return _warp_manager 