from __future__ import annotations

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


class ProjectScoreCalculator:
    def __init__(self, rules: dict[str, Any]):
        self.rules = rules

    def calculate(self, dataset: dict[str, Any]) -> dict[str, Any]:
        dimensions = {
            "population": self.population_score(dataset),
            "traffic": self.traffic_score(dataset),
            "support": self.support_score(dataset),
            "competitor": self.competitor_score(dataset),
            "rent": self.rent_score(dataset),
        }
        total = round(sum(item["score"] for item in dimensions.values()), 2)
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

    def support_score(self, dataset: dict[str, Any]) -> dict[str, Any]:
        cfg = self.rules["support"]
        max_score = float(cfg["weight"])
        rows = dataset.get("pois", []) + dataset.get("food_businesses", []) + dataset.get("entertainments", []) + dataset.get("supplements", [])
        score = 0.0
        reasons: list[str] = []

        if any_keyword(rows, ["夜市"]):
            score += float(cfg["night_market"])
            reasons.append("周边存在夜市，夜间人流有支撑")
        if any_keyword(rows, ["24小时", "便利店"]):
            score += float(cfg["convenience_24h"])
            reasons.append("周边存在便利店或24小时业态")
        if any_keyword(rows, ["凌晨", "夜宵", "烧烤"]):
            score += float(cfg["late_food"])
            reasons.append("周边存在夜宵或凌晨营业餐饮")

        entertainment_count = count_keyword(rows, ["KTV", "酒吧", "台球", "电影院", "密室"])
        if entertainment_count:
            entertainment_score = min(float(cfg["entertainment_max"]), float(entertainment_count))
            score += entertainment_score
            reasons.append("周边存在娱乐消费配套")

        missing = [] if reasons else ["夜经济和配套数据"]
        return self.dimension(score, max_score, reasons, [], missing, 0.8 if reasons else 0.45)

    def competitor_score(self, dataset: dict[str, Any]) -> dict[str, Any]:
        cfg = self.rules["competitor"]
        max_score = float(cfg["weight"])
        competitors = dataset.get("competitors", [])
        score = 0.0
        reasons: list[str] = []
        risks: list[str] = []
        missing: list[str] = []
        count = len(competitors)

        if count == 0:
            score += float(cfg["none_bonus"])
            reasons.append("当前项目未录入竞品，竞争压力暂低")
            missing.append("竞品经营数据")
            confidence = 0.4
        else:
            if count <= 3:
                score += float(cfg["reasonable_count_bonus"])
                reasons.append(f"周边竞品 {count} 家，数量处于可分析范围")
            if count > int(cfg["too_many_threshold"]):
                score += float(cfg["too_many_penalty"])
                risks.append(f"周边竞品 {count} 家，竞争压力较高")

            quality_parts = 0
            if any(row.get("hour_price") is not None or row.get("member_price") is not None for row in competitors):
                quality_parts += 1
            else:
                missing.append("竞品价格")
            if any(row.get("machine_count") is not None or row.get("cpu") or row.get("gpu") or row.get("monitor") for row in competitors):
                quality_parts += 1
            else:
                missing.append("竞品配置")
            if any(row.get("occupancy_rate") is not None for row in competitors):
                quality_parts += 1
            else:
                missing.append("竞品上座率")
            score += float(cfg["quality_bonus"]) * quality_parts / 3
            if quality_parts == 3:
                reasons.append("竞品价格、配置和上座率数据较完整")
            confidence = 0.4 + 0.5 * quality_parts / 3

        return self.dimension(score, max_score, reasons, risks, missing, confidence)

    def rent_score(self, dataset: dict[str, Any]) -> dict[str, Any]:
        cfg = self.rules["rent"]
        max_score = float(cfg["weight"])
        rent = dataset.get("rent_data") or {}
        reasons: list[str] = []
        risks: list[str] = []
        missing: list[str] = []

        monthly_rent = rent.get("monthly_rent")
        area_sqm = rent.get("area_sqm")
        rent_per_sqm = rent.get("rent_per_sqm")
        if rent_per_sqm is None and monthly_rent and area_sqm:
            rent_per_sqm = float(monthly_rent) / float(area_sqm)
        if rent_per_sqm is None:
            missing.append("真实租金")
            return self.dimension(0, max_score, reasons, risks, missing, 0.35)

        rent_value = float(rent_per_sqm)
        if rent_value <= float(cfg["reasonable_rent_per_sqm"]):
            score = float(cfg["reasonable"])
            reasons.append("租金处于合理区间")
        elif rent_value <= float(cfg["high_rent_per_sqm"]):
            score = float(cfg["medium"])
            risks.append("租金存在一定压力")
        else:
            score = float(cfg["high"])
            risks.append("租金偏高，成本压力较大")
        return self.dimension(score, max_score, reasons, risks, missing, 0.85)

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
