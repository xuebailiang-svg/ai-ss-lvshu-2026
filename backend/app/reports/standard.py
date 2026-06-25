from app.reports.base import ReportRenderer


class StandardReportRenderer(ReportRenderer):
    disclaimer = "系统结果仅用于初步选址调研，最终以当地行政审批、消防、文旅和其他主管部门要求为准。"

    def render(self, result, ctx=None):
        evaluation = (ctx or {}).get("evaluation", {})
        pois = evaluation.get("pois", [])
        prop = ((evaluation.get("site") or {}).get("property") or {})
        competitors = [poi for poi in pois if poi.get("category") == "竞品"]
        enriched = [poi for poi in competitors if poi.get("enrichment")]
        traffic = [poi for poi in pois if poi.get("category") == "交通"]
        sensitive = [poi for poi in pois if poi.get("category") in {"小学", "中学", "幼儿园", "敏感场所"}]
        population = [poi for poi in pois if poi.get("category") in {"住宅小区", "公寓", "宿舍", "写字楼", "大学", "中职", "技校"}]
        commercial = [poi for poi in pois if poi.get("category") == "商业配套"]

        return {
            "disclaimer": self.disclaimer,
            "hard_risk": bool(result.get("hard_risks")),
            "conclusion": result.get("recommendation"),
            "score": result.get("total_score"),
            "confidence": result.get("confidence"),
            "dimensions": result.get("dimensions"),
            "positive_evidence": result.get("positive_evidence"),
            "risk_factors": result.get("hard_risks", []) + result.get("negative_evidence", []),
            "manual_review": result.get("review_items"),
            "data_note": "人口相关数量均为 POI 代理指标，不代表真实人口；人工估算数据会明确标注为估算值。",
            "sections": {
                "summary": {
                    "title": "结论摘要",
                    "recommendation": result.get("recommendation"),
                    "score": result.get("total_score"),
                    "basis": result.get("positive_evidence", []) + result.get("negative_evidence", []),
                },
                "hard_risks": {"title": "硬性风险", "items": result.get("hard_risks", [])},
                "score": {"title": "综合评分", "dimensions": result.get("dimensions", {})},
                "quality": {
                    "title": "数据完整度和可信度",
                    "completeness": result.get("completeness"),
                    "confidence": result.get("confidence"),
                    "manual_competitor_records": len(enriched),
                },
                "competitors": {
                    "title": "竞品分析",
                    "auto_collected_count": len(competitors),
                    "manual_survey_count": len(enriched),
                    "items": [self._competitor_item(poi) for poi in competitors],
                },
                "traffic": {"title": "交通分析", "auto_collected_count": len(traffic), "items": self._brief(traffic)},
                "sensitive_places": {"title": "敏感场所", "auto_collected_count": len(sensitive), "items": self._brief(sensitive)},
                "population_proxy": {
                    "title": "人口代理指标",
                    "auto_collected_count": len(population),
                    "note": "这是基于住宅、公寓、写字楼、大学、中职、技校等 POI 的代理指标，不是真实人口。",
                    "items": self._brief(population),
                },
                "commercial": {"title": "商业配套", "auto_collected_count": len(commercial), "items": self._brief(commercial)},
                "property_cost": {
                    "title": "物业与成本",
                    "manual_data": prop,
                    "rent_summary": {
                        "monthly_rent": prop.get("monthly_rent"),
                        "rent_per_sqm_month": prop.get("rent_per_sqm_month"),
                        "rent_per_sqm_day": prop.get("rent_per_sqm_day"),
                        "rent_per_machine_month": prop.get("rent_per_machine_month"),
                    },
                },
                "review_items": {"title": "待人工核实事项", "items": result.get("review_items", [])},
                "data_sources": {
                    "title": "数据来源",
                    "auto": ["高德地图 Web 服务 POI / Geocode"],
                    "manual": ["竞品调研表", "物业调查表"],
                    "estimated": ["人口代理指标", "人工填写的上座率估算值"],
                    "unverified": [item for item in result.get("review_items", [])],
                },
                "scoring_rules": {
                    "title": "评分规则说明",
                    "model_version": result.get("model_version"),
                    "note": "硬性风险与普通评分分离，高分不能覆盖准入风险。",
                },
            },
        }

    @staticmethod
    def _brief(rows):
        return [{"id": row.get("id"), "name": row.get("name"), "distance_m": row.get("distance_m"), "source": row.get("source"), "confidence": row.get("confidence"), "needs_verification": row.get("needs_verification")} for row in rows[:20]]

    @staticmethod
    def _competitor_item(poi):
        enrichment = poi.get("enrichment") or {}
        occupancy = {
            "peak_occupancy_rate": enrichment.get("peak_occupancy_rate"),
            "offpeak_occupancy_rate": enrichment.get("offpeak_occupancy_rate"),
            "label": "估算值" if enrichment.get("peak_occupancy_rate") is not None or enrichment.get("offpeak_occupancy_rate") is not None else None,
        }
        return {
            "id": poi.get("id"),
            "name": poi.get("name"),
            "distance_m": poi.get("distance_m"),
            "amap_data": {"address": poi.get("address"), "business_hours": poi.get("business_hours"), "phone": poi.get("phone")},
            "manual_data": enrichment or None,
            "occupancy": occupancy,
            "verified": bool(enrichment.get("is_manually_verified") or enrichment.get("verified_at")),
        }
