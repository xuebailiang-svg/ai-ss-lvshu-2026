from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter

from fastapi import APIRouter, HTTPException

from .registry import build_default_registry
from .schemas import ConnectivityCheckResponse, DataSourceStatusItem, DataSourceStatusResponse
from .crawler.runtime import read_worker_health


router = APIRouter(prefix="/api/data-sources", tags=["data-sources"])


@router.get("/crawler/runtime")
def get_crawler_runtime_status() -> dict:
    """返回不含密钥的独立爬虫 Worker 运行状态。"""
    health = read_worker_health()
    public_keys = {
        "installed",
        "reachable",
        "status",
        "message",
        "browser_ready",
        "checked_at",
        "age_seconds",
    }
    return {key: value for key, value in health.items() if key in public_keys}


@router.get("/status", response_model=DataSourceStatusResponse)
def get_data_source_status() -> DataSourceStatusResponse:
    registry = build_default_registry()
    return DataSourceStatusResponse(
        items=[
            DataSourceStatusItem(
                name=descriptor.name,
                display_name=descriptor.display_name,
                status=descriptor.availability.value,
                description=descriptor.description,
                capabilities=list(descriptor.capabilities),
                check_supported=descriptor.check_supported,
            )
            for descriptor in registry.list()
        ]
    )


@router.post("/{provider_name}/check", response_model=ConnectivityCheckResponse)
async def check_data_source_connectivity(provider_name: str) -> ConnectivityCheckResponse:
    registry = build_default_registry()
    try:
        provider = registry.get(provider_name)
    except (ValueError, KeyError):
        raise HTTPException(status_code=404, detail="Data provider not found") from None

    started = perf_counter()
    result = await provider.check_connectivity()
    latency_ms = max(0, round((perf_counter() - started) * 1000))
    return ConnectivityCheckResponse(
        name=provider.name,
        configured=result.configured,
        reachable=result.reachable,
        status=result.status.value,
        message=result.message,
        latency_ms=latency_ms,
        checked_at=datetime.now(timezone.utc).isoformat(),
    )
