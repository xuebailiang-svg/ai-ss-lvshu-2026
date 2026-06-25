from __future__ import annotations

from statistics import mean

from app.scoring.base import ScoringEngine


class RuleBasedScoringEngine(ScoringEngine):
    def evaluate(self, ctx, cfg):
        pois = ctx.get("pois", [])
        prop = ctx.get("property", {}) or {}
        weights = cfg["weights"]

        def count(*cats):
            return sum(1 for poi in pois if poi.get("category") in cats)

        competitors = [poi for poi in pois if poi.get("category") == "竞品"]
        competitor_enrichments = [poi.get("enrichment") for poi in competitors if poi.get("enrichment")]
        verified_enrichments = [e for e in competitor_enrichments if e.get("is_manually_verified") or e.get("verified_at")]

        transport = min(weights["transport"], count("交通") * 4)
        population = min(weights["population_proxy"], count("住宅小区", "公寓", "宿舍", "写字楼", "大学", "中职", "技校") * 3)
        commercial = min(weights["commercial"], count("商业配套") * 2)
        competition = self._competition_score(weights["competition"], competitors, competitor_enrichments)
        price_pressure = self._price_pressure_score(weights["competitor_price_pressure"], competitor_enrichments)
        occupancy = self._occupancy_score(weights["competitor_occupancy"], competitor_enrichments)
        property_score = self._property_score(weights["property"], prop)
        rent_pressure = self._rent_pressure_score(weights["rent_pressure"], prop)
        power_network = self._power_network_score(weights["power_network"], prop)
        fire_night = self._fire_night_score(weights["fire_night"], prop)

        hard = self._hard_risks(pois, prop, cfg)
        completeness = self._completeness(pois, prop, competitor_enrichments)
        manual_ratio = len(verified_enrichments) / max(1, len(competitors)) if competitors else 0
        confidence = round(min(95, completeness * 0.55 + manual_ratio * 25 + min(15, len(pois) * 0.4)), 1)

        dimensions = {
            "交通分析": transport,
            "人口代理指标": population,
            "竞品强度": competition,
            "竞品价格压力": price_pressure,
            "竞品上座率": occupancy,
            "商业配套": commercial,
            "物业条件": property_score,
            "租金压力": rent_pressure,
            "供电和网络条件": power_network,
            "消防和夜间经营条件": fire_night,
            "数据完整度": round(weights["completeness"] * completeness / 100, 1),
            "人工核实比例": round(weights["manual_verification"] * manual_ratio, 1),
        }

        total = round(sum(dimensions.values()), 1)
        recommendation = self._recommendation(total, hard, cfg)
        review = self._review_items(pois, prop, competitors, competitor_enrichments)
        positive, negative = self._evidence(pois, prop, competitors, competitor_enrichments)

        return {
            "total_score": total,
            "recommendation": recommendation,
            "dimensions": dimensions,
            "positive_evidence": positive,
            "negative_evidence": negative,
            "hard_risks": hard,
            "review_items": review,
            "completeness": completeness,
            "confidence": confidence,
            "model_version": cfg["version"],
        }

    @staticmethod
    def _competition_score(weight, competitors, enrichments):
        if not competitors:
            return round(weight * 0.75, 1)
        strong = 0
        for enrichment in enrichments:
            machines = enrichment.get("machine_count") or 0
            area = enrichment.get("area_sqm") or 0
            if machines >= 80 or area >= 600:
                strong += 1
        pressure = min(1, (len(competitors) + strong * 1.5) / 8)
        return round(max(0, weight * (1 - pressure)), 1)

    @staticmethod
    def _price_pressure_score(weight, enrichments):
        prices = []
        for enrichment in enrichments:
            for key in ("normal_price", "member_price", "premium_price"):
                value = enrichment.get(key)
                if value is not None:
                    prices.append(float(value))
        if not prices:
            return round(weight * 0.45, 1)
        avg = mean(prices)
        if avg < 6:
            return round(weight * 0.25, 1)
        if avg < 10:
            return round(weight * 0.55, 1)
        return round(weight * 0.85, 1)

    @staticmethod
    def _occupancy_score(weight, enrichments):
        rates = [e.get("peak_occupancy_rate") for e in enrichments if e.get("peak_occupancy_rate") is not None]
        if not rates:
            return round(weight * 0.45, 1)
        avg = mean(float(rate) for rate in rates)
        if avg >= 0.75:
            return round(weight * 0.35, 1)
        if avg >= 0.5:
            return round(weight * 0.65, 1)
        return round(weight * 0.85, 1)

    @staticmethod
    def _property_score(weight, prop):
        fields = [
            "area_sqm", "usable_area_sqm", "floor", "night_entrance", "use_allowed",
            "power_sufficient", "fire_confirmed", "street_facing", "parking_condition",
            "facade_visibility",
        ]
        filled = sum(prop.get(key) is not None for key in fields)
        return round(weight * filled / len(fields), 1)

    @staticmethod
    def _rent_pressure_score(weight, prop):
        rent_per_sqm_day = prop.get("rent_per_sqm_day")
        if rent_per_sqm_day is None:
            return round(weight * 0.4, 1)
        rent = float(rent_per_sqm_day)
        if rent <= 2.0:
            return round(weight * 0.9, 1)
        if rent <= 3.5:
            return round(weight * 0.65, 1)
        if rent <= 5.0:
            return round(weight * 0.4, 1)
        return round(weight * 0.2, 1)

    @staticmethod
    def _power_network_score(weight, prop):
        score = 0
        checks = [
            prop.get("power_sufficient"),
            prop.get("power_expansion_allowed"),
            bool(prop.get("network_carriers")),
            prop.get("dual_line_supported"),
        ]
        for value in checks:
            if value is True:
                score += 1
            elif value:
                score += 0.75
        return round(weight * score / len(checks), 1)

    @staticmethod
    def _fire_night_score(weight, prop):
        checks = [
            prop.get("fire_confirmed"),
            prop.get("night_entrance"),
            prop.get("sprinkler"),
            prop.get("smoke_exhaust"),
            (prop.get("safety_exit_count") or 0) >= 2 if prop.get("safety_exit_count") is not None else None,
        ]
        score = sum(1 for value in checks if value is True)
        return round(weight * score / len(checks), 1)

    @staticmethod
    def _hard_risks(pois, prop, cfg):
        hard = []
        for poi in pois:
            limit = cfg.get("risk_distance_m", {}).get(poi.get("category"))
            dist = poi.get("distance_m")
            if limit and dist is not None and dist <= limit:
                hard.append({
                    "code": "SENSITIVE_PLACE_DISTANCE",
                    "level": "high",
                    "message": f"{poi['name']} 距离约 {dist} 米，可能不符合准入要求",
                    "poi_id": poi.get("id"),
                })
        for field, label in [
            ("use_allowed", "物业不允许电竞馆/网咖业态"),
            ("power_sufficient", "供电容量不足"),
            ("fire_confirmed", "消防条件无法确认"),
            ("night_entrance", "缺少独立夜间出入口"),
        ]:
            if prop.get(field) is False:
                hard.append({"code": f"PROPERTY_{field.upper()}", "level": "high", "message": label})
        return hard

    @staticmethod
    def _completeness(pois, prop, enrichments):
        property_fields = [
            "area_sqm", "usable_area_sqm", "monthly_rent", "rent_per_sqm_day", "floor",
            "power_sufficient", "network_carriers", "night_entrance", "use_allowed",
            "fire_confirmed", "safety_exit_count", "street_facing", "source", "confidence",
        ]
        filled_property = sum(prop.get(key) is not None for key in property_fields)
        poi_score = min(20, len(pois)) / 20
        enrichment_fields = ["machine_count", "normal_price", "peak_occupancy_rate", "source", "confidence"]
        enrichment_possible = max(1, len(enrichments) * len(enrichment_fields))
        enrichment_filled = sum(e.get(key) is not None for e in enrichments for key in enrichment_fields)
        return round(min(100, (filled_property / len(property_fields) * 55) + (poi_score * 25) + (enrichment_filled / enrichment_possible * 20)), 1)

    @staticmethod
    def _review_items(pois, prop, competitors, enrichments):
        items = [
            "高架、铁路、河流、绿化带等空间阻隔需现场复核",
            "当地文化旅游、行政审批及消防政策需复核",
        ]
        if not pois:
            items.append("尚未采集周边 POI")
        if competitors and len(enrichments) < len(competitors):
            items.append("仍有竞品缺少人工调研数据")
        for key, label in [
            ("fire_confirmed", "消防条件"),
            ("power_sufficient", "供电容量"),
            ("night_entrance", "独立夜间出入口"),
            ("use_allowed", "物业业态许可"),
        ]:
            if prop.get(key) is None:
                items.append(f"{label}尚未核实")
        return items

    @staticmethod
    def _evidence(pois, prop, competitors, enrichments):
        count_by = lambda cat: sum(1 for poi in pois if poi.get("category") == cat)
        positive = [
            f"周边交通 POI {count_by('交通')} 条",
            f"商业配套 POI {count_by('商业配套')} 条",
            f"已人工补充竞品 {len(enrichments)} 条",
        ]
        if prop.get("rent_per_machine_month") is not None:
            positive.append(f"每台机器分摊月租金约 {round(prop['rent_per_machine_month'], 1)} 元")
        negative = [f"竞品 {len(competitors)} 条"]
        if not enrichments and competitors:
            negative.append("竞品人工调研数据不足")
        if prop.get("monthly_rent") is None and prop.get("rent_per_sqm_day") is None:
            negative.append("租金数据缺失")
        return positive, negative

    @staticmethod
    def _recommendation(total, hard, cfg):
        if hard:
            return "高风险，可能不符合准入"
        if total >= cfg["thresholds"]["recommended"]:
            return "推荐"
        if total >= cfg["thresholds"]["cautious"]:
            return "谨慎评估"
        return "暂不推荐"
