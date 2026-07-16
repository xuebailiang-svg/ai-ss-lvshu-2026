from __future__ import annotations

import hmac
import time

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.system_config.crypto import ConfigCryptoError
from app.system_config.schemas import ConnectionTestResponse, SystemConfigStatus, SystemConfigUpdate
from app.system_config.service import config_status, update_configs


router = APIRouter(prefix="/api/system/config", tags=["system-config"])


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    expected = get_settings().admin_config_token
    if not expected:
        raise HTTPException(503, "系统配置写入未启用，请先配置ADMIN_CONFIG_TOKEN")
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(401, "管理员Token无效")


@router.get("", response_model=SystemConfigStatus)
def get_system_config(db: Session = Depends(get_db)):
    return config_status(db)


@router.put("", response_model=SystemConfigStatus, dependencies=[Depends(require_admin)])
def put_system_config(body: SystemConfigUpdate, db: Session = Depends(get_db)):
    try:
        update_configs(db, body)
    except ConfigCryptoError as exc:
        raise HTTPException(503, str(exc)) from exc
    return config_status(db)


@router.post("/deepseek/test", response_model=ConnectionTestResponse, dependencies=[Depends(require_admin)])
def test_deepseek_connection():
    from app.llm.client import DeepSeekClient

    started = time.perf_counter()
    try:
        DeepSeekClient().check_connectivity()
        return {
            "success": True,
            "provider": "deepseek",
            "message": "DeepSeek接口连接正常",
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
    except Exception as exc:
        raise HTTPException(502, f"DeepSeek连接失败：{exc}") from exc


@router.post("/amap/test", response_model=ConnectionTestResponse, dependencies=[Depends(require_admin)])
async def test_amap_connection():
    from app.map_data.amap_client import AmapMapDataClient

    started = time.perf_counter()
    try:
        data = await AmapMapDataClient().check_connectivity()
        if str(data.get("status")) != "1":
            raise RuntimeError(str(data.get("info") or "高德接口返回失败"))
        return {
            "success": True,
            "provider": "amap",
            "message": "高德Web服务接口连接正常",
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
    except Exception as exc:
        raise HTTPException(502, f"高德连接失败：{exc}") from exc
