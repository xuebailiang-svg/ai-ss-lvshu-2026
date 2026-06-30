from __future__ import annotations

from app.core.config import get_settings
from app.providers.amap import AmapDataProvider, ProviderError
from app.tools.base import BaseTool, ToolResult


class CompetitorSearchTool(BaseTool):
    tool_name = "competitor_search"
    competitor_keywords = ["电竞", "网咖", "网吧", "Internet cafe", "cyber cafe"]
    missing_fields = ["上座率", "配置", "价格", "充值信息", "月售", "年售"]

    async def run(self, context: dict) -> ToolResult:
        pois = (context.get("agent_state") or {}).get("poi") or context.get("pois") or []
        competitors = self._extract_competitors(pois)
        warnings = [
            "高德 POI 可提供竞品名称、地址、距离等基础信息，但无法提供上座率、配置、充值、月售、年售。"
        ]
        sources = ["amap_poi"] if pois else []

        if not competitors:
            supplemented, supplement_warnings = await self._supplement_from_amap(context)
            competitors = self._extract_competitors(supplemented)
            if supplemented:
                sources = ["amap_poi"]
                warnings.append("poi_search 未识别到竞品，已执行一次竞品关键词补充搜索。")
            warnings.extend(supplement_warnings)

        normalized = [self._normalize_competitor(row) for row in competitors]
        nearest = min(
            (item.get("distance_meters") for item in normalized if item.get("distance_meters") is not None),
            default=None,
        )
        context["competitors"] = competitors
        return self.success(
            f"识别到竞品 POI {len(competitors)} 条",
            data={
                "competitors": normalized,
                "items": competitors,
                "competitor_count": len(competitors),
                "count": len(competitors),
                "nearest_distance_meters": nearest,
                "missing_fields": self.missing_fields,
            },
            confidence=0.72 if competitors else 0.4,
            sources=sources or ["agent_no_competitor_source"],
            warnings=warnings if competitors else warnings + ["未识别到竞品，不代表现场不存在，需要人工现场核实。"],
        )

    @classmethod
    def _extract_competitors(cls, rows: list[dict]) -> list[dict]:
        competitors = []
        for row in rows:
            text = f"{row.get('name', '')} {row.get('category', '')} {row.get('type_code', '')} {row.get('type', '')}"
            if row.get("category") == "竞品" or any(keyword.lower() in text.lower() for keyword in cls.competitor_keywords):
                competitors.append(row)
        return competitors

    @classmethod
    def _normalize_competitor(cls, row: dict) -> dict:
        return {
            "name": row.get("name"),
            "distance_meters": row.get("distance_m"),
            "address": row.get("address"),
            "type": row.get("category") or row.get("type_code"),
            "source": row.get("source") or "amap",
            "location": {"longitude": row.get("longitude"), "latitude": row.get("latitude")},
            "missing_fields": list(cls.missing_fields),
        }

    async def _supplement_from_amap(self, context: dict) -> tuple[list[dict], list[str]]:
        settings = get_settings()
        geo = (context.get("agent_state") or {}).get("geo") or context.get("geocode") or {}
        location = geo.get("location") or {}
        longitude = geo.get("longitude") if geo.get("longitude") is not None else location.get("longitude")
        latitude = geo.get("latitude") if geo.get("latitude") is not None else location.get("latitude")
        if longitude is None or latitude is None:
            return [], ["缺少经纬度，无法补充执行竞品关键词搜索。"]
        provider = AmapDataProvider(settings.amap_web_service_key, mock=settings.amap_mock)
        radius = context["input"].get("radius_meters") or 1000
        try:
            rows = await provider.search_nearby(longitude, latitude, radius, ["网咖", "网吧", "电竞馆"])
        except ProviderError as exc:
            return [], [f"竞品关键词补充搜索失败：{exc.error_code} {exc.message}"]
        context["competitor_diagnostics"] = provider.last_poi_diagnostics
        return rows, ["竞品补充搜索使用 AMAP_MOCK，结果为模拟数据。"] if settings.amap_mock else []
