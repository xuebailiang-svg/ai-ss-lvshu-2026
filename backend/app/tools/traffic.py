from __future__ import annotations

from app.tools.base import BaseTool, ToolResult


class TrafficAnalysisTool(BaseTool):
    tool_name = "traffic_analysis"

    async def run(self, context: dict) -> ToolResult:
        pois = context.get("pois") or []
        traffic = [row for row in pois if row.get("category") == "交通"]
        metro = [row for row in traffic if "地铁" in row.get("name", "")]
        bus = [row for row in traffic if "公交" in row.get("name", "")]
        parking = [row for row in traffic if "停车" in row.get("name", "")]
        context["traffic"] = {"items": traffic, "metro": metro, "bus": bus, "parking": parking}
        return self.success(
            f"交通 POI {len(traffic)} 条，其中地铁 {len(metro)}、公交 {len(bus)}、停车 {len(parking)}",
            data=context["traffic"],
            confidence=0.72 if traffic else 0.35,
            sources=["amap_poi"],
            warnings=["步行时间、人流量、夜间可达性仍需现场或路径规划补充。"],
        )
