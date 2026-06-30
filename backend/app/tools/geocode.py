from __future__ import annotations

from app.core.config import get_settings
from app.providers.amap import AmapDataProvider, ProviderError
from app.tools.base import BaseTool, ToolResult


class GeocodeTool(BaseTool):
    tool_name = "geocode"

    async def run(self, context: dict) -> ToolResult:
        settings = get_settings()
        provider = AmapDataProvider(settings.amap_web_service_key, mock=settings.amap_mock)
        address = context["input"].get("address", "")
        city = context["input"].get("city")
        if not str(address or "").strip():
            return self.failed(
                "地址不能为空，无法执行地址解析",
                sources=[],
                warnings=["请补充候选地址后再启动 Agent。"],
            )
        try:
            raw = await provider.geocode(address, city)
            data = self._normalize_geocode(raw, mock=settings.amap_mock)
            context["geocode"] = data
            return self.success(
                "地址解析完成",
                data=data,
                confidence=0.9 if data.get("location") else 0.55,
                sources=["amap_mock_geocode" if settings.amap_mock else "amap_geocode"],
                warnings=[] if not settings.amap_mock else ["当前使用 AMAP_MOCK，地址解析为模拟数据。"],
            )
        except ProviderError as exc:
            data = self._mock_geocode(address, city, raw_error=exc.to_dict())
            context["geocode"] = data
            return self.success(
                "地址解析已降级为 mock 坐标",
                data=data,
                confidence=0.35,
                sources=["amap_mock_geocode"],
                warnings=[
                    f"高德 geocode 调用失败，已使用 mock geocode：{exc.error_code} {exc.message}",
                    "mock 坐标仅用于保持 Agent 流程可运行，不能作为真实选址依据。",
                ],
            )

    @staticmethod
    def _normalize_geocode(raw: dict, *, mock: bool = False) -> dict:
        longitude = raw.get("longitude")
        latitude = raw.get("latitude")
        return {
            **raw,
            "location": {"longitude": longitude, "latitude": latitude},
            "formatted_address": raw.get("formatted_address"),
            "province": raw.get("province"),
            "city": raw.get("city"),
            "district": raw.get("district"),
            "source": "amap_mock" if mock else "amap",
            "is_mock": mock,
            "raw": raw.get("raw") or {},
        }

    @staticmethod
    def _mock_geocode(address: str, city: str | None, *, raw_error: dict | None = None) -> dict:
        return {
            "formatted_address": f"{city or ''}{address}".strip() or "mock 地址",
            "province": None,
            "city": city,
            "district": None,
            "longitude": 116.397428,
            "latitude": 39.90923,
            "location": {"longitude": 116.397428, "latitude": 39.90923},
            "coordinate_system": "GCJ02",
            "provider": "amap_mock",
            "source": "amap_mock",
            "is_mock": True,
            "raw": {"mock": True, "fallback_reason": raw_error or {}},
        }
