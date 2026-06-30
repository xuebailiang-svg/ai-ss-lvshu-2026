from __future__ import annotations

from collections import Counter

from app.core.config import get_settings
from app.providers.amap import AmapDataProvider, ProviderError
from app.tools.base import BaseTool, ToolResult


class PoiSearchTool(BaseTool):
    tool_name = "poi_search"

    async def run(self, context: dict) -> ToolResult:
        settings = get_settings()
        geo = (context.get("agent_state") or {}).get("geo") or context.get("geocode") or {}
        location = geo.get("location") or {}
        longitude = geo.get("longitude") if geo.get("longitude") is not None else location.get("longitude")
        latitude = geo.get("latitude") if geo.get("latitude") is not None else location.get("latitude")
        radius = context["input"].get("radius_meters") or 1000
        if longitude is None or latitude is None:
            return self.failed(
                "缺少经纬度，无法执行周边 POI 查询",
                warnings=["请先完成 geocode；本步骤未调用高德 POI。"],
            )

        categories = [
            "网吧", "网咖", "电竞馆", "电竞酒店",
            "小学", "中学", "幼儿园", "政府机构", "医院",
            "地铁站", "公交站", "停车场",
            "餐饮", "奶茶", "便利店", "商场", "KTV", "酒吧", "台球厅", "电影院", "酒店",
            "住宅小区", "公寓", "写字楼", "大学", "中职", "技校",
        ]
        provider = AmapDataProvider(settings.amap_web_service_key, mock=settings.amap_mock)
        try:
            rows = await provider.search_nearby(longitude, latitude, radius, categories)
        except ProviderError as exc:
            mock_provider = AmapDataProvider("", mock=True)
            rows = await mock_provider.search_nearby(longitude, latitude, radius, categories)
            diagnostics = mock_provider.last_poi_diagnostics | {"fallback_error": exc.to_dict()}
            context["pois"] = rows
            context["poi_diagnostics"] = diagnostics
            counts = dict(Counter(row.get("category") or "其他" for row in rows))
            return self.success(
                f"周边 POI 查询已降级为 mock，共获得 {len(rows)} 条",
                data={
                    "pois": self._normalize_rows(rows),
                    "items": rows,
                    "category_counts": counts,
                    "counts": counts,
                    "partial_success": False,
                    "diagnostics": diagnostics,
                },
                confidence=0.3,
                sources=["amap_mock_poi"],
                warnings=[
                    f"高德 POI 查询失败，已使用 mock POI：{exc.error_code} {exc.message}",
                    "mock POI 仅用于保持 Agent 流程可运行，不能作为真实选址依据。",
                ],
            )

        context["pois"] = rows
        diagnostics = provider.last_poi_diagnostics
        counts = dict(Counter(row.get("category") or "其他" for row in rows))
        partial_success = bool(diagnostics.get("failed_keywords"))
        context["poi_diagnostics"] = diagnostics
        warnings = []
        failed = diagnostics.get("failed_keywords") or []
        if failed:
            warnings.append(f"有 {len(failed)} 个高德关键词采集失败，已保留成功返回的数据。")
        if settings.amap_mock:
            warnings.append("当前使用 AMAP_MOCK，POI 为模拟数据。")
        return self.success(
            f"周边 POI 查询完成，共获得 {len(rows)} 条",
            data={
                "pois": self._normalize_rows(rows),
                "items": rows,
                "category_counts": counts,
                "counts": counts,
                "partial_success": partial_success,
                "diagnostics": diagnostics,
            },
            confidence=0.78 if rows and not partial_success else 0.58 if rows else 0.35,
            sources=["amap_mock_poi" if settings.amap_mock else "amap_poi"],
            warnings=warnings,
        )

    @staticmethod
    def _normalize_rows(rows: list[dict]) -> list[dict]:
        normalized = []
        for row in rows:
            normalized.append(
                {
                    "name": row.get("name"),
                    "type": row.get("category") or row.get("type_code"),
                    "distance_meters": row.get("distance_m"),
                    "address": row.get("address"),
                    "location": {"longitude": row.get("longitude"), "latitude": row.get("latitude")},
                    "source": row.get("source") or "amap",
                    "typecode": row.get("type_code"),
                    "raw_data": row.get("raw_data") or {},
                }
            )
        return normalized
