import base64
import json
import time
from cryptography.fernet import Fernet
from typing import Dict, Any, Optional
from app.utils.config import settings

def encrypt_data(data: Dict[str, Any], ttl: Optional[int] = None) -> str:
        """
    加密数据

        Args:
        data: 要加密的数据字典
        ttl: 过期时间（秒），None 表示使用默认 TTL

        Returns:
        加密后的 base64 字符串
    """
    if ttl is None:
        ttl = settings.CRYPT_TTL
    
    # 添加时间戳和过期时间
    payload = {
        "data": data,
        "timestamp": time.time(),
        "expires_at": time.time() + ttl
    }
    
    # 序列化为 JSON
    json_data = json.dumps(payload, separators=(',', ':'))
    
    # 加密
    fernet = Fernet(settings.CRYPT_KEY.encode() if isinstance(settings.CRYPT_KEY, str) else settings.CRYPT_KEY)
    encrypted = fernet.encrypt(json_data.encode())
    
    # 返回 base64 编码
    return base64.urlsafe_b64encode(encrypted).decode()

def decrypt_data(encrypted_data: str) -> Optional[Dict[str, Any]]:
    """
    解密数据

        Args:
        encrypted_data: 加密的 base64 字符串

        Returns:
        解密后的数据字典，如果失败或过期返回 None
    """
    try:
        # 解码 base64
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
        
        # 解密
        fernet = Fernet(settings.CRYPT_KEY.encode() if isinstance(settings.CRYPT_KEY, str) else settings.CRYPT_KEY)
        decrypted = fernet.decrypt(encrypted_bytes)
        
        # 反序列化 JSON
        payload = json.loads(decrypted.decode())
        
        # 检查是否过期
        current_time = time.time()
        if current_time > payload.get("expires_at", 0):
            return None  # 已过期
        
        return payload.get("data")
    
    except Exception:
        return None

def generate_encryption_key() -> str:
    """生成新的加密密钥"""
    return Fernet.generate_key().decode() 