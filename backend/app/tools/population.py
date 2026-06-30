from __future__ import annotations

from app.tools.base import BaseTool, ToolResult


class PopulationEstimateTool(BaseTool):
    tool_name = "population_estimate"

    async def run(self, context: dict) -> ToolResult:
        pois = context.get("pois") or []
        proxies = [row for row in pois if row.get("category") in {"住宅小区", "公寓", "写字楼", "大学", "中职", "技校"}]
        data = {"proxy_poi_count": len(proxies), "items": proxies[:20]}
        context["population"] = data
        return self.success(
            f"人口代理 POI {len(proxies)} 条",
            data=data,
            confidence=0.45,
            sources=["amap_poi_proxy"],
            warnings=["人口代理指标不等于真实人口；需要第三方人口数据或现场调研补充。"],
        )
