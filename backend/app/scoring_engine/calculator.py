from __future__ import annotations

from collections import Counter
from typing import Any


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def text_of(row: dict[str, Any]) -> str:
    parts = []
    for key in ("name", "category", "sub_category", "address", "business_hours", "type"):
        value = row.get(key)
        if value:
            parts.append(str(value))
    for value in row.values():
        if isinstance(value, (str, int, float)):
            parts.append(str(value))
    raw = row.get("raw_data")
    if isinstance(raw, dict):
        parts.extend(str(v) for v in raw.values() if isinstance(v, (str, int, float)))
    return " ".join(parts)


def any_keyword(rows: list[dict[str, Any]], keywords: list[str]) -> bool:
    return any(any(keyword in text_of(row) for keyword in keywords) for row in rows)


def count_keyword(rows: list[dict[str, Any]], keywords: list[str]) -> int:
    return sum(1 for row in rows if any(keyword in text_of(row) for keyword in keywords))


def average_value(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if row.get(field) is not None]
    return round(sum(values) / len(values), 2) if values else None


class ProjectScoreCalculator:
    def __init__(self, rules: dict[str, Any]):
        self.rules = rules

    def calculate(self, dataset: dict[str, Any]) -> dict[str, Any]:
        competitor_analysis = self.competitor_analysis(dataset)
        supporting_analysis = self.supporting_analysis(dataset)
        rent_analysis = self.rent_analysis(dataset)
        dimensions = {
            "population": self.population_score(dataset),
            "traffic": self.traffic_score(dataset),
            "support": self.support_score(dataset, supporting_analysis),
            "competitor": self.competitor_score(dataset, competitor_analysis),
            "rent": self.rent_score(dataset, rent_analysis),
        }
        raw_total = sum(item["score"] for item in dimensions.values())
        maximum_total = sum(item["max"] for item in dimensions.values())
        total = round(raw_total / maximum_total * 100, 2) if maximum_total else 0
        confidence = round(sum(item["confidence"] for item in dimensions.values()) / len(dimensions), 2)
        risks = []
        missing = []
        advantages = []
        for item in dimensions.values():
            risks.extend(item["risks"])
            missing.extend(item["missing_data"])
            advantages.extend(item["reasons"])
        return {
            "total_score": total,
            "level": self.level(total),
            "confidence": confidence,
            "dimensions": dimensions,
            "advantages": advantages,
            "risks": risks,
            "missing_data": missing,
            "competitor_analysis": competitor_analysis,
            "supporting_analysis": supporting_analysis,
            "rent_analysis": rent_analysis,
            "scoring_version": str(self.rules.get("version", "project-score-v1")),
        }

    def level(self, total: float) -> str:
        levels = self.rules.get("levels", {})
        if total >= float(levels.get("recommend", 75)):
            return "推荐"
        if total >= float(levels.get("cautious", 60)):
            return "谨慎推荐"
        return "不推荐"

    def population_score(self, dataset: dict[str, Any]) -> dict[str, Any]:
        cfg = self.rules["population"]
        max_score = float(cfg["weight"])
        pois = dataset.get("pois", [])
        population = dataset.get("population_data") or {}
        supplements = dataset.get("supplements", [])
        rows = pois + supplements
        score = 0.0
        reasons: list[str] = []

        university_count = int(population.get("nearby_university_count") or 0)
        if university_count > 0 or any_keyword(rows, ["大学", "学院"]):
            score += float(cfg["university"])
            reasons.append("周边存在大学，年轻客户来源较好")
        vocational_count = int(population.get("nearby_school_count") or 0)
        if vocational_count > 0 or any_keyword(rows, ["技校", "高职", "职业院校", "职业学校", "中职"]):
            score += float(cfg["vocational_school"])
            reasons.append("周边存在高职或技校，潜在年轻客群较好")
        apartment_count = int(population.get("nearby_apartment_count") or 0)
        if apartment_count > 0 or any_keyword(rows, ["公寓"]):
            score += float(cfg["apartment"])
            reasons.append("周边存在公寓，居住型年轻客群较好")
        residential_count = int(population.get("nearby_residential_count") or 0)
        if residential_count > 0 or any_keyword(rows, ["小区", "住宅"]):
            score += float(cfg["young_residential"])
            reasons.append("周边存在住宅小区，具备基础客群")
        if any_keyword(rows, ["回迁房", "安置房"]):
            score += float(cfg["relocation_housing"])
            reasons.append("周边存在回迁房或安置房，可能有上网消费客群")

        missing = [] if reasons else ["人口代理数据"]
        return self.dimension(score, max_score, reasons, [], missing, 0.8 if reasons else 0.45)

    def traffic_score(self, dataset: dict[str, Any]) -> dict[str, Any]:
        cfg = self.rules["traffic"]
        max_score = float(cfg["weight"])
        rows = dataset.get("pois", []) + dataset.get("supplements", [])
        score = 0.0
        reasons: list[str] = []
        risks: list[str] = []

        if any_keyword(rows, ["地铁"]):
            score += float(cfg["subway"])
            reasons.append("周边存在地铁，可达性较好")
        if any_keyword(rows, ["公交"]):
            score += float(cfg["bus"])
            reasons.append("周边存在公交，可达性有支撑")
        if any_keyword(rows, ["停车场", "停车"]):
            score += float(cfg["parking"])
            reasons.append("周边存在停车资源")

        penalty_keywords = {
            "elevated_road": ["高架"],
            "interchange": ["立交"],
            "underpass": ["地下通道", "地下隧道"],
            "railway": ["火车道", "铁路"],
            "green_barrier": ["大型绿化带", "绿化隔离"],
        }
        for key, keywords in penalty_keywords.items():
            if any_keyword(rows, keywords):
                score += float(cfg["penalties"][key])
                risks.append(f"存在{keywords[0]}等交通阻隔因素")

        missing = [] if reasons or risks else ["交通可达性数据"]
        return self.dimension(score, max_score, reasons, risks, missing, 0.8 if reasons or risks else 0.45)

    @staticmethod
    def _supporting_manual_detail(row: dict[str, Any]) -> dict[str, Any]:
        raw = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
        detail = raw.get("manual_detail")
        return detail if isinstance(detail, dict) else {}

    @staticmethod
    def _is_night_business_row(row: dict[str, Any]) -> bool:
        raw = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
        groups = set(raw.get("supporting_groups") or [])
        if raw.get("supporting_group"):
            groups.add(raw["supporting_group"])
        return "night_economy" in groups

    @staticmethod
    def _detail_value_present(value: Any) -> bool:
        return value is not None and (not isinstance(value, str) or bool(value.strip()))

    def supporting_analysis(self, dataset: dict[str, Any]) -> dict[str, Any]:
        confirmed_food = [
            row for row in dataset.get("food_businesses", []) if row.get("status") == "confirmed"
        ]
        confirmed_entertainment = [
            row for row in dataset.get("entertainments", []) if row.get("status") == "confirmed"
        ]
        regular_food = [row for row in confirmed_food if not self._is_night_business_row(row)]
        night_business_candidates = [row for row in confirmed_food if self._is_night_business_row(row)]

        night_food_count = sum(
            1
            for row in regular_food
            if self._supporting_manual_detail(row).get("night_operation") is True
        )
        night_business_count = sum(
            1
            for row in night_business_candidates
            if self._supporting_manual_detail(row).get("is_24_hours") is True
            or self._supporting_manual_detail(row).get("night_operation") is True
        )

        available_detail_fields = 0
        total_detail_fields = 0
        for row in regular_food + confirmed_entertainment:
            detail = self._supporting_manual_detail(row)
            for field_name in ("business_hours", "night_operation"):
                total_detail_fields += 1
                if self._detail_value_present(detail.get(field_name)):
                    available_detail_fields += 1
        for row in night_business_candidates:
            detail = self._supporting_manual_detail(row)
            for field_name in ("is_24_hours", "night_operation"):
                total_detail_fields += 1
                if self._detail_value_present(detail.get(field_name)):
                    available_detail_fields += 1
        detail_completeness = (
            round(available_detail_fields / total_detail_fields, 2) if total_detail_fields else 0.0
        )

        verified_night_count = night_food_count + night_business_count
        if verified_night_count >= 8:
            night_activity_level = "high"
        elif verified_night_count >= 3:
            night_activity_level = "medium"
        elif verified_night_count > 0:
            night_activity_level = "low"
        else:
            night_activity_level = "none"

        return {
            "food_count": len(regular_food),
            "night_food_count": night_food_count,
            "entertainment_count": len(confirmed_entertainment),
            "night_business_count": night_business_count,
            "night_business_candidate_count": len(night_business_candidates),
            "confirmed_supporting_count": len(confirmed_food) + len(confirmed_entertainment),
            "night_activity_level": night_activity_level,
            "detail_completeness": detail_completeness,
        }

    def support_score(
        self,
        dataset: dict[str, Any],
        analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cfg = self.rules["support"]
        max_score = float(cfg["weight"])
        analysis = analysis or self.supporting_analysis(dataset)
        score = 0.0
        reasons: list[str] = []
        missing: list[str] = []
        total_confirmed = int(analysis.get("confirmed_supporting_count") or 0)

        if int(analysis["food_count"]) >= int(cfg.get("food_threshold", 20)):
            score += float(cfg.get("food_score", 8))
            reasons.append(f"已确认餐饮 {analysis['food_count']} 家，餐饮配套较丰富")
        if int(analysis["night_food_count"]) >= int(cfg.get("night_food_threshold", 5)):
            score += float(cfg.get("night_food_score", 3))
            reasons.append(f"已人工确认夜间营业餐饮 {analysis['night_food_count']} 家")
        if int(analysis["entertainment_count"]) >= int(cfg.get("entertainment_threshold", 5)):
            score += float(cfg.get("entertainment_score", 5))
            reasons.append(f"已确认娱乐配套 {analysis['entertainment_count']} 家")
        if int(analysis["night_business_count"]) >= int(cfg.get("night_business_threshold", 3)):
            score += float(cfg.get("night_business_score", 4))
            reasons.append(f"已人工确认24小时或夜间商业 {analysis['night_business_count']} 家")

        if total_confirmed == 0:
            missing.append("已确认周边配套数据")
            confidence = 0.35
        else:
            completeness = float(analysis.get("detail_completeness") or 0)
            confidence = 0.4 + 0.5 * completeness
            if completeness < 0.5:
                missing.append("夜间经营信息不足")

        result = self.dimension(score, max_score, reasons, [], missing, confidence)
        result["analysis"] = analysis
        return result

    def competitor_analysis(self, dataset: dict[str, Any]) -> dict[str, Any]:
        competitors = list(dataset.get("competitors", []))
        confirmed = [row for row in competitors if row.get("status") == "confirmed"]
        pending = [row for row in competitors if row.get("status") == "pending_review"]
        cfg = self.rules["competitor"]
        pending_weight = float(cfg.get("pending_review_weight", 0.5))
        weighted_count = len(confirmed) + len(pending) * pending_weight

        count_cfg = cfg.get("count_scores", {})
        low_max = float(count_cfg.get("low_max", 2))
        medium_max = float(count_cfg.get("medium_max", cfg.get("too_many_threshold", 5)))
        if weighted_count <= low_max:
            competition_level = "low"
        elif weighted_count <= medium_max:
            competition_level = "medium"
        else:
            competition_level = "high"

        gpu_values = [str(row.get("gpu")).strip() for row in confirmed if str(row.get("gpu") or "").strip()]
        common_gpu = Counter(gpu_values).most_common(1)[0][0] if gpu_values else None
        completeness_fields = ("hour_price", "occupancy_rate", "machine_count", "gpu")
        available_points = sum(
            1
            for row in confirmed
            for field in completeness_fields
            if row.get(field) is not None and str(row.get(field)).strip() != ""
        )
        possible_points = len(confirmed) * len(completeness_fields)
        operating_data_completeness = round(available_points / possible_points, 2) if possible_points else 0.0

        return {
            "competitor_count": len(confirmed),
            "candidate_competitor_count": len(competitors),
            "confirmed_competitor_count": len(confirmed),
            "pending_review_count": len(pending),
            "weighted_competitor_count": round(weighted_count, 2),
            "average_distance": average_value(confirmed, "distance_meters"),
            "average_hour_price": average_value(confirmed, "hour_price"),
            "average_occupancy_rate": average_value(confirmed, "occupancy_rate"),
            "average_machine_count": average_value(confirmed, "machine_count"),
            "common_gpu": common_gpu,
            "operating_data_completeness": operating_data_completeness,
            "competition_level": competition_level,
        }

    def competitor_score(self, dataset: dict[str, Any], analysis: dict[str, Any] | None = None) -> dict[str, Any]:
        cfg = self.rules["competitor"]
        max_score = float(cfg["weight"])
        competitors = dataset.get("competitors", [])
        analysis = analysis or self.competitor_analysis(dataset)
        score = 0.0
        reasons: list[str] = []
        risks: list[str] = []
        missing: list[str] = []
        count = int(analysis["candidate_competitor_count"])
        confirmed_count = int(analysis["confirmed_competitor_count"])
        pending_count = int(analysis["pending_review_count"])
        weighted_count = float(analysis["weighted_competitor_count"])

        if count == 0:
            score += float(cfg["none_bonus"])
            reasons.append("当前项目未录入竞品，竞争压力暂低")
            missing.append("竞品经营数据")
            confidence = 0.4
        else:
            count_cfg = cfg.get("count_scores")
            if count_cfg:
                if weighted_count <= float(count_cfg.get("low_max", 2)):
                    score += float(count_cfg.get("low", 12))
                    reasons.append(f"有效竞争强度约 {weighted_count:g} 家，竞争压力较低")
                elif weighted_count <= float(count_cfg.get("medium_max", 5)):
                    score += float(count_cfg.get("medium", 8))
                    reasons.append(f"有效竞争强度约 {weighted_count:g} 家，竞争程度中等")
                else:
                    score += float(count_cfg.get("high", 4))
                    risks.append(f"有效竞争强度约 {weighted_count:g} 家，竞争压力较高")
            else:
                if count <= 3:
                    score += float(cfg["reasonable_count_bonus"])
                    reasons.append(f"周边竞品 {count} 家，数量处于可分析范围")
                if count > int(cfg["too_many_threshold"]):
                    score += float(cfg["too_many_penalty"])
                    risks.append(f"周边竞品 {count} 家，竞争压力较高")

            operating_scores = cfg.get("operating_data_scores", {})
            fallback_quality_score = float(cfg.get("quality_bonus", 5)) / 3
            average_price = analysis.get("average_hour_price")
            average_occupancy = analysis.get("average_occupancy_rate")
            average_machine_count = analysis.get("average_machine_count")
            common_gpu = analysis.get("common_gpu")

            if average_price is not None:
                score += float(operating_scores.get("price", fallback_quality_score))
                reasons.append(f"已确认竞品平均价格 {average_price:g} 元/小时，可用于判断区域消费能力")
            else:
                missing.append("竞品价格")
            if average_machine_count is not None:
                score += float(operating_scores.get("machine_count", fallback_quality_score))
                reasons.append(f"已确认竞品平均机器数量 {average_machine_count:g} 台")
            else:
                missing.append("竞品机器数量")
            if common_gpu:
                reasons.append(f"已确认竞品常见显卡配置为 {common_gpu}")
            else:
                missing.append("竞品显卡配置")
            if average_occupancy is not None:
                score += float(operating_scores.get("occupancy", fallback_quality_score))
                reasons.append(f"已确认竞品平均上座率约 {average_occupancy * 100:.0f}%")
                if average_occupancy >= float(cfg.get("high_occupancy_threshold", 0.7)):
                    score += float(cfg.get("high_occupancy_penalty", -1))
                    risks.append("竞品上座率较高，市场需求较成熟，但竞争强度也较高")
            else:
                missing.append("竞品上座率")

            if confirmed_count == 0:
                missing.append("已确认竞品经营信息")
                if pending_count:
                    risks.append(f"仍有 {pending_count} 家疑似竞品待确认，当前仅按较低权重参考")
                confidence = 0.35
            else:
                completeness = float(analysis.get("operating_data_completeness") or 0)
                confidence = 0.45 + 0.45 * completeness
                if pending_count:
                    risks.append(f"另有 {pending_count} 家疑似竞品待确认，按较低权重计入数量压力")
                    confidence -= 0.05
                if completeness < 0.5:
                    missing.append("竞品经营信息不足")

        result = self.dimension(score, max_score, reasons, risks, list(dict.fromkeys(missing)), confidence)
        result["analysis"] = analysis
        return result

    @staticmethod
    def _positive_number(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    def rent_analysis(self, dataset: dict[str, Any]) -> dict[str, Any]:
        records = dataset.get("rent_records")
        if not isinstance(records, list):
            legacy = dataset.get("rent_data")
            records = [legacy] if isinstance(legacy, dict) and legacy else []

        confirmed = [row for row in records if row.get("status") == "confirmed"]
        valid: list[dict[str, Any]] = []
        for row in confirmed:
            address = row.get("address") or row.get("location_type")
            area = self._positive_number(row.get("area_sqm"))
            monthly_rent = self._positive_number(row.get("monthly_rent"))
            if not address or area is None or monthly_rent is None:
                continue
            unit_price = self._positive_number(row.get("rent_per_sqm")) or monthly_rent / area
            valid.append({**row, "_area": area, "_monthly_rent": monthly_rent, "_unit_price": unit_price})

        count = len(valid)
        completeness = round(count / len(confirmed), 2) if confirmed else 0.0
        if not valid:
            return {
                "confirmed_rent_count": 0,
                "average_area_sqm": None,
                "average_monthly_rent": None,
                "average_rent_unit_price": None,
                "current_rent_unit_price": None,
                "reference_average_rent_unit_price": None,
                "rent_pressure": "unknown",
                "data_completeness": completeness,
            }

        average_area = round(sum(row["_area"] for row in valid) / count, 2)
        average_monthly = round(sum(row["_monthly_rent"] for row in valid) / count, 2)
        average_unit = round(sum(row["_unit_price"] for row in valid) / count, 2)

        # 没有额外“候选租金”标记时，以最新一条有效记录作为当前租金，之前记录作为项目内参照样本。
        current = valid[-1]
        reference_rows = valid[:-1] or valid
        reference_average = round(sum(row["_unit_price"] for row in reference_rows) / len(reference_rows), 2)
        ratio = current["_unit_price"] / reference_average if reference_average else 1.0
        cfg = self.rules["rent"]
        if ratio < float(cfg.get("low_pressure_ratio", 0.8)):
            pressure = "low"
        elif ratio > float(cfg.get("high_pressure_ratio", 1.2)):
            pressure = "high"
        else:
            pressure = "medium"

        return {
            "confirmed_rent_count": count,
            "average_area_sqm": average_area,
            "average_monthly_rent": average_monthly,
            "average_rent_unit_price": average_unit,
            "current_rent_unit_price": round(current["_unit_price"], 2),
            "reference_average_rent_unit_price": reference_average,
            "rent_pressure": pressure,
            "data_completeness": completeness,
        }

    def rent_score(self, dataset: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
        cfg = self.rules["rent"]
        max_score = float(cfg["weight"])
        reasons: list[str] = []
        risks: list[str] = []
        missing: list[str] = []
        sample_count = int(analysis.get("confirmed_rent_count") or 0)
        pressure = analysis.get("rent_pressure")
        if sample_count == 0:
            missing.append("有效租金样本")
            result = self.dimension(0, max_score, reasons, risks, missing, 0.2)
            result["analysis"] = analysis
            return result

        score_by_pressure = {
            "low": float(cfg.get("low_pressure_score", max_score)),
            "medium": float(cfg.get("medium_pressure_score", max_score * 0.6)),
            "high": float(cfg.get("high_pressure_score", max_score * 0.2)),
        }
        score = score_by_pressure.get(str(pressure), 0.0)
        pressure_text = {"low": "较低", "medium": "中等", "high": "较高"}.get(str(pressure), "未知")
        reasons.append(f"根据 {sample_count} 条有效租金记录，当前租金压力为{pressure_text}")
        if pressure == "high":
            risks.append("当前租金单价高于项目内参照样本平均值的 1.2 倍，成本压力较大")
        elif pressure == "low":
            reasons.append("当前租金单价低于项目内参照样本平均值的 0.8 倍")

        minimum_count = int(cfg.get("minimum_sample_count", 3))
        completeness = float(analysis.get("data_completeness") or 0)
        confidence = min(0.95, 0.55 + 0.35 * completeness)
        if sample_count < minimum_count:
            missing.append("租金样本不足")
            risks.append(f"当前仅有 {sample_count} 条有效租金记录，压力判断仅供参考")
            confidence = min(confidence, 0.45)
        if completeness < 1:
            missing.append("部分已确认租金缺少地址、面积或月租金")

        result = self.dimension(score, max_score, reasons, risks, list(dict.fromkeys(missing)), confidence)
        result["analysis"] = analysis
        return result

    @staticmethod
    def dimension(
        score: float,
        max_score: float,
        reasons: list[str],
        risks: list[str],
        missing: list[str],
        confidence: float,
    ) -> dict[str, Any]:
        return {
            "score": round(clamp(score, 0, max_score), 2),
            "max": max_score,
            "confidence": round(clamp(confidence, 0, 1), 2),
            "reasons": reasons,
            "risks": risks,
            "missing_data": missing,
        }
