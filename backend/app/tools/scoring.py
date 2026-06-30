from __future__ import annotations

from app.tools.base import BaseTool, ToolResult


class ScoringTool(BaseTool):
    tool_name = "scoring"

    async def run(self, context: dict) -> ToolResult:
        competitors = context.get("competitors") or []
        traffic = (context.get("traffic") or {}).get("items") or []
        supporting = (context.get("supporting") or {}).get("items") or []
        population_count = (context.get("population") or {}).get("proxy_poi_count") or 0
        redline_risks = (context.get("redline") or {}).get("sensitive_within_200m") or []

        score = 55
        score += min(12, len(traffic) * 2)
        score += min(10, len(supporting))
        score += min(8, population_count * 2)
        score -= min(15, len(competitors) * 3)
        if redline_risks:
            score -= 25
        score = max(0, min(100, score))
        level = "建议进一步实地考察" if score >= 70 else "谨慎评估" if score >= 50 else "暂不推荐"
        data = {"total": score, "level": level}
        context["final_score"] = data
        return self.success(
            f"综合评分 {score}，评级：{level}",
            data=data,
            confidence=0.55,
            sources=["agent_rule_v1"],
            warnings=["第一阶段为受控 Agent 规则评分，不是大模型判断，也不是最终投资建议。"],
        )
