from __future__ import annotations

from app.core.config import get_settings
from app.feedback import SiteFeedbackStore
from app.tools.base import BaseTool, ToolResult


class SimilarCaseSearchTool(BaseTool):
    tool_name = "similar_case_search"

    async def run(self, context: dict) -> ToolResult:
        if not get_settings().enable_similar_cases:
            context["similar_cases"] = []
            return self.success(
                "相似案例检索已按配置关闭",
                data={"similar_cases": [], "has_similar_cases": False, "comparison_summary": "similar_case_search disabled"},
                confidence=0,
                sources=["config"],
                warnings=["ENABLE_SIMILAR_CASES=false"],
            )
        snapshot = {
            "task_id": context.get("task_id"),
            "input": context.get("input") or {},
            "agent_state": context.get("agent_state") or {},
            "final_score": context.get("final_score") or {},
            "report": context.get("report") or {},
        }
        cases = SiteFeedbackStore().find_similar_cases(snapshot)
        context["similar_cases"] = cases
        summary = f"检索到 {len(cases)} 个历史相似案例" if cases else "暂无历史相似案例"
        return self.success(
            summary,
            data={
                "similar_cases": cases,
                "has_similar_cases": bool(cases),
                "comparison_summary": self._comparison_summary(cases),
            },
            confidence=0.65 if cases else 0.25,
            sources=["feedback_store"],
            warnings=[] if cases else ["反馈样本不足，当前无法用历史结果校准本次判断。"],
        )

    @staticmethod
    def _comparison_summary(cases: list[dict]) -> str:
        if not cases:
            return "暂无可对比历史案例。"
        profit = sum(1 for item in cases if item.get("historical_result") == "profit")
        loss = sum(1 for item in cases if item.get("historical_result") == "loss")
        unknown = sum(1 for item in cases if item.get("historical_result") == "unknown")
        return f"相似案例中盈利 {profit} 个、亏损 {loss} 个、未知 {unknown} 个。"
