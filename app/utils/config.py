import requests
from typing import Dict, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


def fetch_cookies_data(url: str) -> str:
    response = requests.get(url)
    response.raise_for_status()  # Raise an exception for HTTP errors
    return response.text


class Settings(BaseSettings):
    # 核心功能配置
    DIRECT_LINK_MODE: int = 1
    
    # 域名和访问控制 - Railway 兼容配置
    ALLOWED_HOSTS: str = 'localhost,127.0.0.1,*.vercel.app,*.up.railway.app,*.railway.app'
    
    # API 鉴权配置
    SECRET_KEY: str = 'your-main-secret-key-2024'
    MULTI_DOMAIN_KEYS: str = ''
    
    # 功能开关（简化配置）
    DISABLE_TURNSTILE: int = 1
    DISABLE_DOCS: int = 0
    DISABLE_DEMO: int = 0
    DISABLE_HOST_VALIDATION: int = 1  # Railway 部署时推荐禁用严格主机验证
    
    # WARP 代理池配置
    WARP_CONFIG_DIR: str = 'warp-configs'
    PROXY_HEALTH_CHECK_INTERVAL: int = 300
    ENABLE_WARP_PROXY: int = 1  # 生产环境启用 WARP 代理
    
    # 以下配置在直链模式下可忽略，但保留以兼容代理模式
    CRYPT_KEY: str = 'fl5JcIwHh0SM87Vl18B_Sn65lVOwhYIQ3fnfGYqpVlE='
    CRYPT_TTL: int = 28800
    TURNSTILE_KEY: str = ''
    DISABLE_SIGN: int = 1
    REST_MODE: int = 0
    COOKIES_URL: str = ''
    COOKIES: str = ''

    class Config:
        env_file = "./.env"

    @field_validator('COOKIES')
    def load_cookies(cls, v, values):
        if not v and values.data.get("COOKIES_URL"):
            url = values.data["COOKIES_URL"]
            try:
                return fetch_cookies_data(url)
            except:
                return ''
        return v or ''

    def get_domain_keys(self) -> Dict[str, str]:
        """
        解析多域名多密钥配置
        格式: domain1:key1,domain2:key2
        返回: {domain1: key1, domain2: key2}
        """
        if not self.MULTI_DOMAIN_KEYS:
            return {}
        
        domain_keys = {}
        try:
            pairs = self.MULTI_DOMAIN_KEYS.split(',')
            for pair in pairs:
                if ':' in pair:
                    domain, key = pair.split(':', 1)
                    domain_keys[domain.strip()] = key.strip()
        except Exception:
            pass
        
        return domain_keys

    def validate_secret_for_domain(self, secret: str, domain: Optional[str] = None) -> bool:
        """
        验证密钥是否有效
        支持主密钥和域名专用密钥
        """
        # 首先检查主密钥
        if secret == self.SECRET_KEY:
            return True
        
        # 如果有域名，检查域名专用密钥
        if domain:
            domain_keys = self.get_domain_keys()
            # 精确匹配
            if domain in domain_keys and secret == domain_keys[domain]:
                return True
            # 通配符匹配
            for pattern, key in domain_keys.items():
                if pattern.startswith('*.') and domain.endswith(pattern[2:]) and secret == key:
                    return True
        
        return False


settings = Settings()
