from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import SystemConfigRecord
from app.system_config.crypto import ConfigCryptoError, decrypt_value, encrypt_value
from app.system_config.schemas import SystemConfigUpdate


SECRET_KEYS = {"deepseek_api_key", "amap_web_service_key"}
SUPPORTED_KEYS = SECRET_KEYS | {"deepseek_base_url", "deepseek_model"}


def mask_secret(value: str) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return value[:2] + "********"
    return value[:6] + "********" + value[-4:]


def _record(db: Session, key: str) -> SystemConfigRecord | None:
    return db.scalar(select(SystemConfigRecord).where(SystemConfigRecord.config_key == key))


def _database_value(db: Session, key: str) -> str | None:
    row = _record(db, key)
    if not row:
        return None
    return decrypt_value(row.encrypted_value)


def resolve_config_value(key: str, env_fallback: str = "") -> str:
    """运行时读取：数据库优先；迁移未执行、解密失败或无记录时回退环境变量。"""
    if key not in SUPPORTED_KEYS:
        return env_fallback
    try:
        with SessionLocal() as db:
            value = _database_value(db, key)
            return value if value is not None else env_fallback
    except Exception:
        return env_fallback


def update_configs(db: Session, body: SystemConfigUpdate) -> None:
    values = body.model_dump(exclude_none=True)
    if not values:
        return
    # 保存前验证主密钥，避免写入无法解密的数据。
    encrypt_value("configuration-key-check")
    for key, raw_value in values.items():
        value = str(raw_value).strip()
        if not value:
            continue
        row = _record(db, key)
        if not row:
            row = SystemConfigRecord(config_key=key, encrypted_value="", is_secret=key in SECRET_KEYS)
            db.add(row)
        row.encrypted_value = encrypt_value(value)
        row.is_secret = key in SECRET_KEYS
        row.updated_at = datetime.now(timezone.utc)
    db.commit()


def _effective(db: Session, key: str, env_value: str, warnings: list[str]) -> tuple[str, str]:
    try:
        value = _database_value(db, key)
        if value is not None:
            return value, "database"
    except ConfigCryptoError as exc:
        warnings.append(f"{key}: {exc}")
    return (env_value, "env") if env_value else ("", "none")


def config_status(db: Session) -> dict[str, Any]:
    settings = get_settings()
    warnings: list[str] = []
    deepseek_key, deepseek_source = _effective(db, "deepseek_api_key", settings.deepseek_api_key, warnings)
    amap_key, amap_source = _effective(db, "amap_web_service_key", settings.amap_web_service_key, warnings)
    base_url, _ = _effective(db, "deepseek_base_url", settings.deepseek_base_url, warnings)
    model, _ = _effective(db, "deepseek_model", settings.deepseek_model, warnings)
    return {
        "management_enabled": bool(settings.admin_config_token and len(settings.system_config_encryption_key) >= 32),
        "deepseek": {
            "configured": bool(deepseek_key),
            "source": deepseek_source,
            "masked": mask_secret(deepseek_key),
        },
        "amap": {
            "configured": bool(amap_key) or settings.amap_mock,
            "source": amap_source if amap_key else ("mock" if settings.amap_mock else "none"),
            "masked": mask_secret(amap_key),
        },
        "deepseek_base_url": base_url or "https://api.deepseek.com",
        "deepseek_model": model or "deepseek-chat",
        "warnings": warnings,
    }
