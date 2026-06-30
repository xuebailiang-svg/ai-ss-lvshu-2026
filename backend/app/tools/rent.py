from __future__ import annotations

from app.tools.base import BaseTool, ToolResult


class RentEstimateTool(BaseTool):
    tool_name = "rent_estimate"

    async def run(self, context: dict) -> ToolResult:
        data = {
            "rent_level": "unknown",
            "monthly_rent": None,
            "rent_per_sqm_day": None,
        }
        context["rent"] = data
        return self.success(
            "租金数据暂未自动获取，已列为人工核实项",
            data=data,
            confidence=0.2,
            sources=["manual_required"],
            warnings=["第一阶段未接入租金数据源；不要把该结果当作真实租金。"],
        )
