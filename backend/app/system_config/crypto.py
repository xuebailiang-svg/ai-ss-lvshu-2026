from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class ConfigCryptoError(RuntimeError):
    pass


def _fernet() -> Fernet:
    master_key = get_settings().system_config_encryption_key.strip()
    if len(master_key) < 32:
        raise ConfigCryptoError("SYSTEM_CONFIG_ENCRYPTION_KEY未配置或长度不足32位")
    derived = base64.urlsafe_b64encode(hashlib.sha256(master_key.encode("utf-8")).digest())
    return Fernet(derived)


def encrypt_value(value: str) -> str:
    if not value:
        raise ConfigCryptoError("配置值不能为空")
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_value(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ConfigCryptoError("配置解密失败，请检查SYSTEM_CONFIG_ENCRYPTION_KEY") from exc
