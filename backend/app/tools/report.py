from __future__ import annotations

from app.tools.base import BaseTool, ToolResult


class ReportGenerateTool(BaseTool):
    tool_name = "report_generate"

    async def run(self, context: dict) -> ToolResult:
        score = context.get("final_score") or {"total": None, "level": "未评分"}
        competitors = context.get("competitors") or []
        traffic = (context.get("traffic") or {}).get("items") or []
        supporting = (context.get("supporting") or {}).get("items") or []
        redline = (context.get("redline") or {}).get("sensitive_within_200m") or []
        similar_cases = context.get("similar_cases") or []
        data_gaps = context.setdefault("data_gaps", [])
        manual_items = context.setdefault("manual_check_items", [])

        for item in ["竞品价格和机器配置", "租金、物业费、转让费", "消防、供电、网络和夜间入口", "真实人流与上座率"]:
            if item not in manual_items:
                manual_items.append(item)
        if not traffic:
            data_gaps.append("交通 POI 数据不足")
        if not supporting:
            data_gaps.append("周边配套 POI 数据不足")
        data_gaps.append("租金数据未自动获取")
        data_gaps.append("人口数据仅为 POI 代理指标")

        report = {
            "summary": f"候选点综合评分 {score.get('total')}，{score.get('level')}。",
            "advantages": [
                f"交通 POI {len(traffic)} 条" if traffic else "交通数据待补充",
                f"周边配套 POI {len(supporting)} 条" if supporting else "周边配套待补充",
            ],
            "risks": [f"发现 {len(redline)} 个红线风险"] if redline else ["暂无已知红线风险，但需现场核实"],
            "data_sources": self._collect_sources(context),
            "confidence": min(0.8, max(0.35, sum(step.get("confidence", 0) for step in context.get("step_results", [])) / max(1, len(context.get("step_results", []))))),
            "data_gaps": data_gaps,
            "manual_check_items": manual_items,
            "missing_fields": self._collect_missing_fields(context),
            "decision_factors": self._decision_factors(context),
            "negative_factors": self._negative_factors(context),
            "feature_importance_guess": {
                "红线风险": 0.25,
                "竞品强度": 0.2,
                "交通可达性": 0.15,
                "周边配套": 0.15,
                "人口代理": 0.1,
                "租金物业": 0.1,
                "历史反馈案例": 0.05,
            },
            "uncertainty_analysis": self._uncertainty_analysis(context),
            "similar_case_analysis": {
                "has_similar_cases": bool(similar_cases),
                "cases": similar_cases,
                "comparison_summary": self._similar_case_summary(similar_cases),
                "differences": [diff for item in similar_cases for diff in item.get("key_differences", [])][:8],
            },
            "recommendations": [
                "优先现场核实竞品经营情况和价格。",
                "补齐租金、物业和消防条件后再做最终决策。",
            ],
        }
        context["report"] = report
        return self.success(
            "Agent 报告生成完成",
            data=report,
            confidence=report["confidence"],
            sources=["agent_rule_v1"],
            warnings=["报告为第一阶段 Agent 规则汇总，不调用大模型。"],
        )

    @staticmethod
    def _collect_sources(context: dict) -> list[str]:
        sources = ["agent_rule_v1", "manual_required"]
        for result in context.get("step_results", []):
            for source in result.get("sources", []):
                if source not in sources:
                    sources.append(source)
        return sources

    @staticmethod
    def _collect_missing_fields(context: dict) -> list[str]:
        fields = []
        for result in context.get("step_results", []):
            for field in (result.get("data") or {}).get("missing_fields", []):
                if field not in fields:
                    fields.append(field)
        return fields

    @staticmethod
    def _decision_factors(context: dict) -> list[str]:
        factors = []
        traffic = (context.get("traffic") or {}).get("items") or []
        supporting = (context.get("supporting") or {}).get("items") or []
        competitors = context.get("competitors") or []
        redline = context.get("redline") or {}
        if redline.get("risk_level") == "low":
            factors.append("200m 红线检查未发现已知敏感对象")
        if traffic:
            factors.append(f"周边交通 POI {len(traffic)} 条")
        if supporting:
            factors.append(f"周边商业/夜间配套 POI {len(supporting)} 条")
        if competitors:
            factors.append(f"已识别竞品 {len(competitors)} 条，可进入人工竞品调研")
        return factors or ["当前正向证据不足，需要补充现场调研"]

    @staticmethod
    def _negative_factors(context: dict) -> list[str]:
        factors = []
        redline = context.get("redline") or {}
        competitors = context.get("competitors") or []
        if redline.get("risk_level") == "high":
            factors.append("200m 内存在红线敏感对象")
        if len(competitors) >= 5:
            factors.append("周边竞品数量较多，价格和配置压力需重点核实")
        if not (context.get("rent") or {}).get("monthly_rent"):
            factors.append("缺少真实租金数据，成本压力无法确认")
        return factors or ["未发现明确负向因素，但仍需现场核实"]

    @staticmethod
    def _uncertainty_analysis(context: dict) -> list[str]:
        items = []
        for result in context.get("step_results", []):
            if (result.get("confidence") or 0) < 0.7:
                items.append(f"{result.get('tool_name')} 置信度不足")
            if (result.get("data") or {}).get("partial_success"):
                items.append(f"{result.get('tool_name')} 存在 partial_success")
        if not (context.get("rent") or {}).get("monthly_rent"):
            items.append("租金、物业、转让费仍需人工回填")
        if not context.get("similar_cases"):
            items.append("历史反馈样本不足，暂不能进行案例校准")
        return list(dict.fromkeys(items))

    @staticmethod
    def _similar_case_summary(cases: list[dict]) -> str:
        if not cases:
            return "暂无历史反馈样本可对比。"
        profit = sum(1 for item in cases if item.get("historical_result") == "profit")
        loss = sum(1 for item in cases if item.get("historical_result") == "loss")
        unknown = sum(1 for item in cases if item.get("historical_result") == "unknown")
        return f"相似案例中盈利 {profit} 个、亏损 {loss} 个、未知 {unknown} 个。"
