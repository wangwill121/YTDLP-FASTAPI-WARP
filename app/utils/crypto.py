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
    fernet = Fernet(settings.CRYPT_KEY.encode())
    encrypted_data = fernet.encrypt(json_data.encode())
    
    # 返回 base64 编码
    return base64.urlsafe_b64encode(encrypted_data).decode()

def decrypt_data(encrypted_data: str) -> Optional[Dict[str, Any]]:
    """
    解密数据

        Args:
        encrypted_data: 加密的 base64 字符串

        Returns:
        解密后的数据字典，如果解密失败或过期则返回 None
    """
    try:
        # 解码 base64
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
        
        # 解密
        fernet = Fernet(settings.CRYPT_KEY.encode())
        decrypted_data = fernet.decrypt(encrypted_bytes)
        
        # 解析 JSON
        payload = json.loads(decrypted_data.decode())
        
        # 检查是否过期
        if time.time() > payload.get("expires_at", 0):
            return None
        
        return payload.get("data")
    
    except Exception:
        return None

def generate_encryption_key() -> str:
    """
    生成新的加密密钥

        Returns:
        base64 编码的加密密钥
    """
    key = Fernet.generate_key()
    return key.decode() 