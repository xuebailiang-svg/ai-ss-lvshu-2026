from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import ScoringDimensionRecord, ScoringFactorRecord
from app.scoring_engine.config_schemas import ScoringConfigUpdate


DEFAULT_DIMENSIONS: list[dict[str, Any]] = [
    {"key": "redline_compliance", "name": "红线合规", "description": "小学、幼儿园、中学、政府机构等硬性风险距离检查。", "weight": 10, "data_sources": ["amap", "manual"]},
    {"key": "traffic_access", "name": "交通可达", "description": "地铁、公交、停车等可达性。", "weight": 8, "data_sources": ["amap"]},
    {"key": "traffic_barrier", "name": "交通阻隔", "description": "高架、立交、地下通道、铁路、大型绿化隔离等减分因素。", "weight": 6, "data_sources": ["manual", "amap"]},
    {"key": "customer_population", "name": "客群人口", "description": "大学、高职、技校、公寓、年轻住宅、回迁房等潜在客群。", "weight": 10, "data_sources": ["amap", "manual", "third_party"]},
    {"key": "competitor_environment", "name": "竞品环境", "description": "周边电竞馆、网咖等竞品数量、距离和确认状态。", "weight": 10, "data_sources": ["amap_competitor", "manual"]},
    {"key": "competitor_operation", "name": "竞品经营", "description": "竞品配置、价格、上座率、机器数量、经营强度。", "weight": 10, "data_sources": ["manual", "crawler_competitor"]},
    {"key": "night_consumption", "name": "夜间消费", "description": "夜间餐饮、便利店、夜间商业和夜间人流代理信息。", "weight": 8, "data_sources": ["amap_supporting", "manual"]},
    {"key": "entertainment_support", "name": "娱乐配套", "description": "KTV、酒吧、台球、密室、电影院等娱乐消费环境。", "weight": 6, "data_sources": ["amap_supporting", "manual"]},
    {"key": "food_support", "name": "餐饮配套", "description": "餐饮、小吃、烧烤、夜宵等周边消费配套。", "weight": 6, "data_sources": ["amap_supporting", "manual"]},
    {"key": "rent_cost", "name": "租金成本", "description": "有效租金样本、租金单价和成本压力。", "weight": 8, "data_sources": ["manual_rent", "manual"]},
    {"key": "property_condition", "name": "物业条件", "description": "面积、供电、消防、门头、停车、网络和物业限制。", "weight": 6, "data_sources": ["manual"]},
    {"key": "market_capacity", "name": "市场容量", "description": "区域消费容量、目标人群规模和增长空间。", "weight": 6, "data_sources": ["manual", "third_party"]},
    {"key": "data_quality", "name": "数据质量", "description": "数据来源完整度、人工核实状态和缺失数据影响。", "weight": 6, "data_sources": ["system"]},
]

ENGINE_WEIGHT_MAPPING = {
    "population": ["customer_population"],
    "traffic": ["traffic_access", "traffic_barrier"],
    "support": ["night_consumption", "entertainment_support", "food_support"],
    "competitor": ["competitor_environment", "competitor_operation"],
    "rent": ["rent_cost", "property_condition"],
}


def seed_default_scoring_config(db: Session) -> None:
    exists = db.scalar(select(ScoringDimensionRecord.id).limit(1))
    if exists:
        return
    now = datetime.now(timezone.utc)
    for index, item in enumerate(DEFAULT_DIMENSIONS):
        db.add(
            ScoringDimensionRecord(
                key=item["key"],
                name=item["name"],
                description=item["description"],
                weight=float(item["weight"]),
                enabled=True,
                data_sources=list(item["data_sources"]),
                sort_order=index,
                created_at=now,
                updated_at=now,
            )
        )
    db.commit()


def _dimension_to_dict(row: ScoringDimensionRecord, factors: list[ScoringFactorRecord]) -> dict[str, Any]:
    return {
        "key": row.key,
        "name": row.name,
        "description": row.description,
        "weight": row.weight,
        "enabled": row.enabled,
        "data_sources": row.data_sources or [],
        "sort_order": row.sort_order,
        "factors": [
            {
                "key": factor.key,
                "name": factor.name,
                "description": factor.description,
                "weight": factor.weight,
                "enabled": factor.enabled,
                "data_sources": factor.data_sources or [],
                "sort_order": factor.sort_order,
                "config": factor.config or {},
            }
            for factor in factors
        ],
    }


def list_scoring_config(db: Session) -> dict[str, Any]:
    seed_default_scoring_config(db)
    dimensions = list(db.scalars(select(ScoringDimensionRecord).order_by(ScoringDimensionRecord.sort_order, ScoringDimensionRecord.id)).all())
    factors = list(db.scalars(select(ScoringFactorRecord).order_by(ScoringFactorRecord.sort_order, ScoringFactorRecord.id)).all())
    factor_map: dict[str, list[ScoringFactorRecord]] = {}
    for factor in factors:
        factor_map.setdefault(factor.dimension_key, []).append(factor)
    items = [_dimension_to_dict(row, factor_map.get(row.key, [])) for row in dimensions]
    total_weight = round(sum(float(item["weight"]) for item in items if item["enabled"]), 2)
    return {"dimensions": items, "total_weight": total_weight, "normalized": abs(total_weight - 100) < 0.01}


def replace_scoring_config(db: Session, body: ScoringConfigUpdate) -> dict[str, Any]:
    if not body.dimensions:
        raise ValueError("dimensions cannot be empty")
    now = datetime.now(timezone.utc)
    db.execute(delete(ScoringFactorRecord))
    db.execute(delete(ScoringDimensionRecord))
    for index, dimension in enumerate(body.dimensions):
        db.add(
            ScoringDimensionRecord(
                key=dimension.key,
                name=dimension.name,
                description=dimension.description,
                weight=dimension.weight,
                enabled=dimension.enabled,
                data_sources=dimension.data_sources,
                sort_order=dimension.sort_order or index,
                created_at=now,
                updated_at=now,
            )
        )
        for factor_index, factor in enumerate(dimension.factors):
            db.add(
                ScoringFactorRecord(
                    dimension_key=dimension.key,
                    key=factor.key,
                    name=factor.name,
                    description=factor.description,
                    weight=factor.weight,
                    enabled=factor.enabled,
                    data_sources=factor.data_sources,
                    sort_order=factor.sort_order or factor_index,
                    config=factor.config,
                    created_at=now,
                    updated_at=now,
                )
            )
    db.commit()
    return list_scoring_config(db)


def reset_scoring_config(db: Session) -> dict[str, Any]:
    db.execute(delete(ScoringFactorRecord))
    db.execute(delete(ScoringDimensionRecord))
    db.commit()
    seed_default_scoring_config(db)
    return list_scoring_config(db)


def rules_with_db_weights(db: Session, rules: dict[str, Any]) -> dict[str, Any]:
    config = list_scoring_config(db)
    if _is_default_dimension_config(config["dimensions"]):
        rules["scoring_config"] = config
        return rules
    enabled_weights = {
        item["key"]: float(item["weight"])
        for item in config["dimensions"]
        if item.get("enabled")
    }
    mapped_weights = {
        engine_key: sum(enabled_weights.get(key, 0.0) for key in config_keys)
        for engine_key, config_keys in ENGINE_WEIGHT_MAPPING.items()
    }
    active_total = sum(mapped_weights.values())
    if active_total <= 0:
        return rules
    adjusted = dict(rules)
    for engine_key, weight in mapped_weights.items():
        if engine_key in adjusted:
            adjusted[engine_key] = dict(adjusted[engine_key])
            adjusted[engine_key]["weight"] = round(weight / active_total * 100, 4)
    adjusted["scoring_config"] = config
    return adjusted


def _is_default_dimension_config(dimensions: list[dict[str, Any]]) -> bool:
    if len(dimensions) != len(DEFAULT_DIMENSIONS):
        return False
    defaults = {item["key"]: item for item in DEFAULT_DIMENSIONS}
    for item in dimensions:
        default = defaults.get(item["key"])
        if not default:
            return False
        if bool(item.get("enabled")) is not True:
            return False
        if abs(float(item.get("weight") or 0) - float(default["weight"])) > 0.0001:
            return False
    return True
