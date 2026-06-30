from __future__ import annotations

from typing import Any


class SiteSelectionPlanner:
    """Rule-based planner for the first Agent planning phase.

    It intentionally does not call an external LLM. The output shape mirrors what
    a future LLM planner can produce: an ordered plan plus plan_reasoning.
    """

    default_plan = [
        "geocode",
        "poi_search",
        "redline_check",
        "competitor_search",
        "traffic_analysis",
        "supporting_analysis",
        "rent_estimate",
        "population_estimate",
        "scoring",
        "similar_case_search",
        "report_generate",
    ]

    def plan(self, agent_input: dict[str, Any]) -> dict[str, Any]:
        address = str(agent_input.get("address") or "")
        city = str(agent_input.get("city") or "")
        business_type = str(agent_input.get("business_type") or "电竞馆")
        plan = list(self.default_plan)
        reasoning = [
            "电竞馆选址必须先做地址解析，后续工具需要候选点位置。",
            "商圈和周边环境分析必须包含 poi_search，竞品、交通、配套、人口代理均依赖 POI。",
            "红线检查属于高优先级准入风险，但需要复用 poi_search 的敏感场所结果，避免重复请求相同 POI。",
            "夜经济分析必须包含 supporting_analysis，用于识别餐饮、娱乐、酒店等夜间消费配套。",
            "租金和人口第一阶段没有真实数据源，作为估算/人工核实工具保留在计划中。",
            "scoring 必须在信息收集后执行，相似案例检索用于用历史反馈校准决策，report_generate 必须在评分后执行。",
        ]
        if "电竞" not in business_type and "网咖" not in business_type:
            reasoning.append(f"当前业态为 {business_type}，但系统仍按电竞馆选址规则执行第一版受控计划。")
        if not address or not city:
            reasoning.append("地址或城市缺失时，geocode 可能失败，后续工具会降级继续记录数据缺口。")
        return {
            "planner": "rule_based_v1",
            "input": {"address": address, "city": city, "business_type": business_type},
            "plan": [{"order": index, "tool_name": name} for index, name in enumerate(plan, start=1)],
            "plan_reasoning": reasoning,
        }
