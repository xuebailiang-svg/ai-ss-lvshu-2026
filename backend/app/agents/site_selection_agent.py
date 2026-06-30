from __future__ import annotations

from time import perf_counter
from typing import Any
from uuid import uuid4

from app.agents.planner import SiteSelectionPlanner
from app.core.config import get_settings
from app.feedback import SiteFeedbackStore
from app.trace import AgentTraceStore
from app.tools import (
    CompetitorSearchTool,
    GeocodeTool,
    PoiSearchTool,
    PopulationEstimateTool,
    RedlineCheckTool,
    RentEstimateTool,
    ReportGenerateTool,
    ScoringTool,
    SimilarCaseSearchTool,
    SupportingAnalysisTool,
    TrafficAnalysisTool,
)
from app.tools.base import BaseTool, ToolResult
from app.tools.base_validator import ToolOutputValidator


class SiteSelectionAgent:
    """Planner + Tool Execution + Reflection 的第一阶段 Agent。

    当前 planner 为 rule-based，不调用外部大模型；后续可将
    SiteSelectionPlanner 替换成 LLM planner，但工具白名单和 ToolResult 协议不变。
    """

    def __init__(self, tools: list[BaseTool] | None = None, planner: SiteSelectionPlanner | None = None):
        tool_list = tools or [
            GeocodeTool(),
            RedlineCheckTool(),
            PoiSearchTool(),
            CompetitorSearchTool(),
            TrafficAnalysisTool(),
            SupportingAnalysisTool(),
            RentEstimateTool(),
            PopulationEstimateTool(),
            ScoringTool(),
            SimilarCaseSearchTool(),
            ReportGenerateTool(),
        ]
        self.tool_registry = {tool.tool_name: tool for tool in tool_list}
        self.planner = planner or SiteSelectionPlanner()

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        task_id = str(uuid4())
        agent_input = {
            "address": str(payload.get("address") or "").strip(),
            "city": str(payload.get("city") or "").strip(),
            "radius_meters": int(payload.get("radius_meters") or 1000),
            "business_type": str(payload.get("business_type") or "电竞馆").strip() or "电竞馆",
        }
        trace_store = AgentTraceStore() if settings.enable_trace else None
        if trace_store:
            trace_store.start_run(task_id, agent_input)
        planner_started = perf_counter()
        plan_result = self.planner.plan(agent_input)
        if trace_store:
            trace_store.append_step(
                task_id,
                step_name="planner",
                input_data=agent_input,
                output_data=plan_result,
                tool_name="planner",
                status="success",
                confidence=1.0,
                duration_ms=round((perf_counter() - planner_started) * 1000),
            )
        context: dict[str, Any] = {
            "task_id": task_id,
            "trace_store": trace_store,
            "input": agent_input,
            "plan": plan_result["plan"],
            "plan_reasoning": plan_result["plan_reasoning"],
            "agent_state": self._initial_agent_state(),
            "steps": [],
            "step_results": [],
            "data_gaps": [],
            "manual_check_items": [],
        }

        for planned_step in plan_result["plan"]:
            tool_name = planned_step["tool_name"]
            tool = self.tool_registry.get(tool_name)
            if not tool:
                result = ToolResult(
                    tool_name=tool_name,
                    status="skipped",
                    summary=f"工具 {tool_name} 未注册，已跳过。",
                    confidence=0,
                    warnings=["planner 生成了未注册工具；请检查工具白名单。"],
                )
                result = ToolOutputValidator.validate(result, fallback_tool_name=tool_name)
                self._append_step(context, planned_step, result, 0)
                continue

            if self._should_skip(tool_name, context):
                result = ToolResult(
                    tool_name=tool_name,
                    status="skipped",
                    summary=f"{tool_name} 缺少前置数据，已跳过。",
                    confidence=0,
                    warnings=["该工具需要前置结果；Agent 已记录数据缺口并继续执行。"],
                )
                result = ToolOutputValidator.validate(result, fallback_tool_name=tool_name)
                context["data_gaps"].append(f"{tool_name} 缺少前置数据")
                self._append_step(context, planned_step, result, 0)
                continue

            started = perf_counter()
            try:
                result = await tool.run(context)
            except Exception as exc:  # noqa: BLE001 - Agent must record and continue.
                result = tool.failed(
                    f"{tool.tool_name} 执行异常：{type(exc).__name__}: {exc}",
                    warnings=["该工具失败，Agent 已继续执行后续可执行步骤。"],
                )
            duration_ms = round((perf_counter() - started) * 1000)
            result = ToolOutputValidator.validate(result, fallback_tool_name=tool_name)
            self._update_agent_state(context, result.tool_name)
            self._append_step(context, planned_step, result, duration_ms)
            if result.status == "failed":
                context["data_gaps"].append(f"{result.tool_name} 未成功：{result.summary}")

        reflection = self.reflection_step(context) if settings.enable_reflection else {
            "issues": [],
            "missing_data": [],
            "confidence_adjustment": 0,
            "risk_of_overestimate": 0,
            "risk_of_underestimate": 0,
            "adjusted_score_suggestion": (context.get("final_score") or {}).get("total"),
            "final_confidence": 0,
            "recommendation": "Reflection disabled by config.",
        }
        context["reflection"] = reflection
        self._append_reflection_step(context, reflection)
        if context.get("report"):
            context["report"]["reflection"] = reflection
            context["report"]["data_quality"] = self._build_data_quality(context, reflection)

        failed_count = sum(1 for step in context["steps"] if step["status"] == "failed")
        skipped_count = sum(1 for step in context["steps"] if step["status"] == "skipped")
        result = {
            "task_id": task_id,
            "status": "completed" if failed_count == 0 and skipped_count == 0 else "completed_with_warnings",
            "input": agent_input,
            "plan": plan_result["plan"],
            "plan_reasoning": plan_result["plan_reasoning"],
            "agent_state": context["agent_state"],
            "steps": context["steps"],
            "final_score": context.get("final_score"),
            "report": context.get("report"),
            "reflection": reflection,
            "similar_cases": context.get("similar_cases", []),
            "trace": (trace_store.get_trace(task_id) or {}).get("trace", []) if trace_store else [],
            "trace_summary": trace_store.summary(task_id) if trace_store else {"total_steps": 0, "failed_steps": 0, "avg_confidence": 0, "total_duration_ms": 0},
            "data_gaps": self._unique(context.get("data_gaps", []) + reflection.get("missing_data", [])),
            "manual_check_items": self._unique(context.get("manual_check_items", [])),
        }
        if settings.enable_feedback:
            try:
                feedback_record = SiteFeedbackStore().save_initial_result(result)
                result["feedback_record"] = {
                    "task_id": feedback_record.get("task_id"),
                    "actual_business_result": feedback_record.get("actual_business_result"),
                    "updated_at": feedback_record.get("updated_at"),
                }
            except Exception as exc:
                result["feedback_record"] = None
                result.setdefault("warnings", []).append(f"feedback 写入失败但 Agent 已完成：{type(exc).__name__}: {exc}")
        return result

    @staticmethod
    def _initial_agent_state() -> dict[str, Any]:
        return {
            "geo": None,
            "redline": None,
            "poi": None,
            "competitor": None,
            "traffic": None,
            "rent": None,
            "population": None,
            "similar_cases": None,
        }

    @staticmethod
    def _should_skip(tool_name: str, context: dict[str, Any]) -> bool:
        if tool_name in {"competitor_search", "traffic_analysis", "supporting_analysis", "population_estimate"}:
            return "pois" not in context
        if tool_name == "redline_check":
            return "geocode" not in context
        if tool_name == "scoring":
            return not any(key in context for key in ("competitors", "traffic", "supporting", "population", "rent"))
        if tool_name == "similar_case_search":
            return "final_score" not in context or not get_settings().enable_similar_cases
        if tool_name == "report_generate":
            return "final_score" not in context
        return False

    @staticmethod
    def _update_agent_state(context: dict[str, Any], tool_name: str) -> None:
        mapping = {
            "geocode": ("geo", "geocode"),
            "redline_check": ("redline", "redline"),
            "poi_search": ("poi", "pois"),
            "competitor_search": ("competitor", "competitors"),
            "traffic_analysis": ("traffic", "traffic"),
            "rent_estimate": ("rent", "rent"),
            "population_estimate": ("population", "population"),
            "similar_case_search": ("similar_cases", "similar_cases"),
        }
        if tool_name in mapping:
            state_key, context_key = mapping[tool_name]
            context["agent_state"][state_key] = context.get(context_key)

    def _append_step(self, context: dict[str, Any], planned_step: dict[str, Any], result: ToolResult, duration_ms: int) -> None:
        result = ToolOutputValidator.validate(result, fallback_tool_name=str(planned_step.get("tool_name") or "unknown_tool"))
        result_dict = result.to_dict()
        input_snapshot = self._step_input_snapshot(context)
        step = {
            "step": len(context["steps"]) + 1,
            "planned_order": planned_step.get("order"),
            "tool_name": result.tool_name,
            "status": result.status,
            "summary": result.summary,
            "duration_ms": duration_ms,
            "confidence": result.confidence,
            "sources": result.sources,
            "warnings": result.warnings,
            "input": input_snapshot,
            "output": result_dict,
        }
        context["steps"].append(step)
        context["step_results"].append(result_dict)
        trace_store = context.get("trace_store")
        if trace_store:
            trace_store.append_step(
                context["task_id"],
                step_name=result.tool_name,
                input_data=input_snapshot,
                output_data=result_dict,
                tool_name=result.tool_name,
                status=result.status,
                confidence=result.confidence,
                duration_ms=duration_ms,
            )

    def _append_reflection_step(self, context: dict[str, Any], reflection: dict[str, Any]) -> None:
        result = ToolResult(
            tool_name="reflection",
            status="success",
            summary=reflection["recommendation"],
            data=reflection,
            confidence=max(0.0, min(1.0, 0.7 + reflection.get("confidence_adjustment", 0))),
            sources=["agent_reflection_rule_v1"],
            warnings=reflection.get("issues", []),
        )
        self._append_step(context, {"order": len(context.get("plan", [])) + 1}, result, 0)

    @staticmethod
    def _step_input_snapshot(context: dict[str, Any]) -> dict[str, Any]:
        geo = (context.get("agent_state") or {}).get("geo") or {}
        location = geo.get("location") or {}
        return {
            "agent_state": {key: bool(value) for key, value in (context.get("agent_state") or {}).items()},
            "used_upstream_results": {
                "geo_location": location if location else None,
                "has_geocode": bool(context.get("geocode")),
                "has_poi": bool(context.get("pois")),
                "has_redline": bool(context.get("redline")),
                "has_competitors": bool(context.get("competitors")),
            },
            "poi_count": len(context.get("pois") or []),
            "competitor_count": len(context.get("competitors") or []),
            "input": context.get("input", {}),
        }

    @staticmethod
    def reflection_step(context: dict[str, Any]) -> dict[str, Any]:
        issues: list[str] = []
        missing_data: list[str] = []
        low_confidence = [
            result for result in context.get("step_results", [])
            if result.get("status") != "skipped" and (result.get("confidence") or 0) < 0.7
        ]
        step_by_tool = {result.get("tool_name"): result for result in context.get("step_results", [])}
        geocode_result = step_by_tool.get("geocode") or {}
        poi_result = step_by_tool.get("poi_search") or {}
        competitor_result = step_by_tool.get("competitor_search") or {}
        redline_result = step_by_tool.get("redline_check") or {}
        if not context.get("geocode"):
            missing_data.append("地址坐标")
        if any("mock" in source for source in geocode_result.get("sources", [])):
            issues.append("geocode 使用了 mock 坐标，不能作为真实选址依据。")
            missing_data.append("真实地址坐标")
        if not context.get("pois"):
            missing_data.append("周边 POI")
        if (poi_result.get("data") or {}).get("partial_success"):
            issues.append("poi_search 出现 partial_success，部分高德关键词采集失败。")
            missing_data.append("部分 POI 关键词结果")
        if not context.get("competitors"):
            missing_data.append("竞品数据")
        competitor_missing = (competitor_result.get("data") or {}).get("missing_fields") or []
        if competitor_missing:
            issues.append("competitor_search 无法从高德获取竞品价格、配置、上座率、充值信息等经营数据。")
            missing_data.extend(competitor_missing)
        redline_data = redline_result.get("data") or {}
        if "amap_poi" not in redline_result.get("sources", []) or redline_data.get("risk_level") == "unknown":
            issues.append("redline_check 缺少完整 amap_poi 证据或风险状态 unknown。")
            missing_data.append("红线边界人工核实")
        if not (context.get("rent") or {}).get("monthly_rent"):
            missing_data.append("真实租金")
        if not context.get("population"):
            missing_data.append("真实人口数据")
        if low_confidence:
            issues.append(f"{len(low_confidence)} 个关键工具结果置信度低于 70%。")
        if missing_data:
            issues.append("存在关键数据缺失，需要人工补充。")
        failed_or_skipped = [step for step in context.get("steps", []) if step.get("status") in {"failed", "skipped"}]
        if failed_or_skipped:
            issues.append(f"{len(failed_or_skipped)} 个步骤失败或跳过。")
        similar_cases = context.get("similar_cases") or []
        losses = sum(1 for item in similar_cases if item.get("historical_result") == "loss")
        profits = sum(1 for item in similar_cases if item.get("historical_result") == "profit")
        risk_of_overestimate = min(1.0, 0.15 * len(issues) + 0.2 * losses)
        risk_of_underestimate = min(1.0, 0.1 * len([item for item in similar_cases if item.get("similarity", 0) >= 0.6]) + 0.15 * profits)
        confidence_adjustment = -0.1 * min(3, len(issues)) - 0.05 * losses + 0.03 * profits
        base_score = (context.get("final_score") or {}).get("total")
        adjusted_score = None
        if base_score is not None:
            adjusted_score = max(0, min(100, round(float(base_score) + confidence_adjustment * 20)))
        final_confidence = max(
            0.1,
            min(
                0.95,
                SiteSelectionAgent._average([result.get("confidence", 0) for result in context.get("step_results", [])])
                + confidence_adjustment,
            ),
        )
        recommendation = "建议补齐缺失数据后再进入最终决策。" if issues else "数据链路基本完整，可进入下一步现场核验。"
        return {
            "issues": issues,
            "missing_data": SiteSelectionAgent._unique(missing_data),
            "confidence_adjustment": round(confidence_adjustment, 2),
            "risk_of_overestimate": round(risk_of_overestimate, 2),
            "risk_of_underestimate": round(risk_of_underestimate, 2),
            "adjusted_score_suggestion": adjusted_score,
            "final_confidence": round(final_confidence, 2),
            "recommendation": recommendation,
        }

    @staticmethod
    def _build_data_quality(context: dict[str, Any], reflection: dict[str, Any]) -> dict[str, Any]:
        real_sources = []
        mock_warnings = []
        estimated_warnings = []
        for result in context.get("step_results", []):
            for source in result.get("sources", []):
                if source.startswith("amap_") and "mock" not in source and source not in real_sources:
                    real_sources.append(source)
                if "mock" in source:
                    mock_warnings.append(f"{result.get('tool_name')} 使用 mock 数据源：{source}")
            for warning in result.get("warnings", []):
                if "mock" in warning or "模拟" in warning:
                    mock_warnings.append(warning)
                if "估算" in warning or "代理指标" in warning:
                    estimated_warnings.append(warning)
        return {
            "real_data_sources": SiteSelectionAgent._unique(real_sources),
            "mock_warnings": SiteSelectionAgent._unique(mock_warnings),
            "estimated_warnings": SiteSelectionAgent._unique(estimated_warnings),
            "missing_data": reflection.get("missing_data", []),
            "manual_check_items": context.get("manual_check_items", []),
        }

    @staticmethod
    def _average(values: list[Any]) -> float:
        nums = []
        for value in values:
            try:
                nums.append(float(value))
            except (TypeError, ValueError):
                continue
        return sum(nums) / len(nums) if nums else 0.0

    @staticmethod
    def _unique(items: list[Any]) -> list[Any]:
        out = []
        for item in items:
            if item not in out:
                out.append(item)
        return out
