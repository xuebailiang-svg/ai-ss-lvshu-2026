from __future__ import annotations

from app.tools.base import BaseTool, ToolResult


class SupportingAnalysisTool(BaseTool):
    tool_name = "supporting_analysis"

    async def run(self, context: dict) -> ToolResult:
        pois = context.get("pois") or []
        keywords = ["餐", "奶茶", "便利店", "KTV", "酒吧", "台球", "电影", "酒店"]
        items = [row for row in pois if row.get("category") in {"商业配套", "娱乐"} or any(key in row.get("name", "") for key in keywords)]
        context["supporting"] = {"items": items, "count": len(items)}
        return self.success(
            f"周边配套 POI {len(items)} 条",
            data=context["supporting"],
            confidence=0.7 if items else 0.35,
            sources=["amap_poi"],
            warnings=["营业时间、夜间消费活跃度需要人工核实。"],
        )
