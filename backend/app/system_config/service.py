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


SECRET_KEYS = {
    "deepseek_api_key",
    "amap_web_service_key",
    "amap_js_key",
    "amap_security_js_code",
    "third_party_api_key",
}
CRAWLER_KEYS = {
    "crawler_enabled",
    "crawler_provider",
    "crawler_timeout_seconds",
    "crawler_max_pages_per_task",
    "crawler_max_tasks_per_project",
    "crawler_rate_limit_seconds",
    "crawler_allowed_domains",
    "crawler_blocked_domains",
    "crawler_search_enabled",
    "crawler_search_provider",
    "crawler_search_max_results",
    "crawler_search_timeout_seconds",
    "crawler_search_allowed_domains",
}
GOV_DATA_KEYS = {
    "gov_data_enabled",
    "gov_data_sources",
    "gov_data_timeout_seconds",
    "gov_data_max_retries",
    "gov_data_rate_limit_seconds",
}
SUPPORTED_KEYS = SECRET_KEYS | {"deepseek_base_url", "deepseek_model"} | CRAWLER_KEYS | GOV_DATA_KEYS


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
    amap_js_key, amap_js_source = _effective(db, "amap_js_key", "", warnings)
    amap_security_code, amap_security_source = _effective(db, "amap_security_js_code", "", warnings)
    third_party_key, third_party_source = _effective(db, "third_party_api_key", "", warnings)
    base_url, _ = _effective(db, "deepseek_base_url", settings.deepseek_base_url, warnings)
    model, _ = _effective(db, "deepseek_model", settings.deepseek_model, warnings)
    crawler_enabled_raw, crawler_enabled_source = _effective(
        db,
        "crawler_enabled",
        "true" if settings.crawler_enabled else "false",
        warnings,
    )
    crawler_provider, _ = _effective(db, "crawler_provider", settings.crawler_provider, warnings)
    crawler_timeout, _ = _effective(db, "crawler_timeout_seconds", str(settings.crawler_timeout_seconds), warnings)
    crawler_max_pages, _ = _effective(db, "crawler_max_pages_per_task", str(settings.crawler_max_pages_per_task), warnings)
    crawler_max_tasks, _ = _effective(db, "crawler_max_tasks_per_project", str(settings.crawler_max_tasks_per_project), warnings)
    crawler_rate_limit, _ = _effective(db, "crawler_rate_limit_seconds", str(settings.crawler_rate_limit_seconds), warnings)
    crawler_allowed_domains, _ = _effective(db, "crawler_allowed_domains", settings.crawler_allowed_domains, warnings)
    crawler_blocked_domains, _ = _effective(db, "crawler_blocked_domains", settings.crawler_blocked_domains, warnings)
    crawler_search_enabled_raw, _ = _effective(
        db,
        "crawler_search_enabled",
        "true" if settings.crawler_search_enabled else "false",
        warnings,
    )
    crawler_search_provider, _ = _effective(db, "crawler_search_provider", settings.crawler_search_provider, warnings)
    crawler_search_max_results, _ = _effective(db, "crawler_search_max_results", str(settings.crawler_search_max_results), warnings)
    crawler_search_timeout, _ = _effective(db, "crawler_search_timeout_seconds", str(settings.crawler_search_timeout_seconds), warnings)
    crawler_search_allowed_domains, _ = _effective(db, "crawler_search_allowed_domains", settings.crawler_search_allowed_domains, warnings)
    gov_data_enabled_raw, _ = _effective(
        db,
        "gov_data_enabled",
        "true" if settings.gov_data_enabled else "false",
        warnings,
    )
    gov_data_sources, _ = _effective(db, "gov_data_sources", settings.gov_data_sources, warnings)
    gov_data_timeout, _ = _effective(db, "gov_data_timeout_seconds", str(settings.gov_data_timeout_seconds), warnings)
    gov_data_max_retries, _ = _effective(db, "gov_data_max_retries", str(settings.gov_data_max_retries), warnings)
    gov_data_rate_limit, _ = _effective(db, "gov_data_rate_limit_seconds", str(settings.gov_data_rate_limit_seconds), warnings)
    crawler_enabled = str(crawler_enabled_raw).strip().lower() in {"1", "true", "yes", "on"}
    crawler_search_enabled = str(crawler_search_enabled_raw).strip().lower() in {"1", "true", "yes", "on"}
    gov_data_enabled = str(gov_data_enabled_raw).strip().lower() in {"1", "true", "yes", "on"}
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
        "amap_js": {
            "configured": bool(amap_js_key),
            "source": amap_js_source,
            "masked": mask_secret(amap_js_key),
        },
        "amap_security": {
            "configured": bool(amap_security_code),
            "source": amap_security_source,
            "masked": mask_secret(amap_security_code),
        },
        "third_party": {
            "configured": bool(third_party_key),
            "source": third_party_source,
            "masked": mask_secret(third_party_key),
        },
        "crawler": {
            "configured": crawler_enabled,
            "source": crawler_enabled_source,
            "masked": None,
        },
        "deepseek_base_url": base_url or "https://api.deepseek.com",
        "deepseek_model": model or "deepseek-chat",
        "crawler_enabled": crawler_enabled,
        "crawler_provider": crawler_provider or "crawl4ai",
        "crawler_timeout_seconds": int(crawler_timeout or 60),
        "crawler_max_pages_per_task": int(crawler_max_pages or 5),
        "crawler_max_tasks_per_project": int(crawler_max_tasks or 50),
        "crawler_rate_limit_seconds": int(crawler_rate_limit or 5),
        "crawler_allowed_domains": crawler_allowed_domains or "",
        "crawler_blocked_domains": crawler_blocked_domains or "",
        "crawler_search_enabled": crawler_search_enabled,
        "crawler_search_provider": crawler_search_provider or "duckduckgo_html",
        "crawler_search_max_results": int(crawler_search_max_results or 5),
        "crawler_search_timeout_seconds": int(crawler_search_timeout or 10),
        "crawler_search_allowed_domains": crawler_search_allowed_domains or "",
        "gov_data_enabled": gov_data_enabled,
        "gov_data_sources": gov_data_sources or "national,shaanxi,xian",
        "gov_data_timeout_seconds": int(gov_data_timeout or 15),
        "gov_data_max_retries": int(gov_data_max_retries or 2),
        "gov_data_rate_limit_seconds": int(gov_data_rate_limit or 1),
        "warnings": warnings,
    }
