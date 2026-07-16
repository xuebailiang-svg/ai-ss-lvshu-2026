from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data_model import normalize_data
from app.models import (
    EntertainmentRecord,
    FoodBusinessRecord,
    PopulationDataRecord,
    RentDataRecord,
    SiteProjectRecord,
    SupplementRecord,
    UnifiedCompetitorRecord,
    UnifiedPOIRecord,
)
from app.projects.schemas import ProjectCreate


DATASET_TABLES = {
    "poi": UnifiedPOIRecord,
    "competitor": UnifiedCompetitorRecord,
    "food": FoodBusinessRecord,
    "entertainment": EntertainmentRecord,
    "rent": RentDataRecord,
    "population": PopulationDataRecord,
    "supplement": SupplementRecord,
}

EFFECTIVE_COMPETITOR_STATUSES = ("confirmed", "pending_review")

COMPETITOR_DETAIL_IMPORTANT_FIELDS = {
    "hour_price": "价格",
    "machine_count": "机器数量",
    "gpu": "显卡配置",
    "occupancy_rate": "上座率",
    "business_hours": "营业时间",
}

COMPETITOR_DETAIL_RECOMMENDED_FIELDS = {
    "area_sqm": "面积",
    "member_price": "会员价格",
    "cpu": "CPU配置",
    "monitor": "显示器配置",
    "opening_date": "开业时间",
    "monthly_sales": "月营业额",
    "recharge_info": "充值活动",
}


def create_project(db: Session, body: ProjectCreate) -> SiteProjectRecord:
    project = SiteProjectRecord(
        project_id=f"proj_{uuid4().hex[:12]}",
        project_name=body.name,
        city=body.city,
        district=body.district,
        address=body.address,
        longitude=body.longitude,
        latitude=body.latitude,
        radius_meters=body.radius_meters,
        business_type=body.business_type,
        source="manual",
        status="confirmed",
        confidence=0.9,
        raw_data=body.model_dump(),
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def list_projects(db: Session) -> list[SiteProjectRecord]:
    return list(db.scalars(select(SiteProjectRecord).where(SiteProjectRecord.deleted_at.is_(None)).order_by(SiteProjectRecord.created_at.desc(), SiteProjectRecord.id.desc())).all())


def get_project(db: Session, project_id: str, *, include_deleted: bool = False) -> SiteProjectRecord | None:
    stmt = select(SiteProjectRecord).where(SiteProjectRecord.project_id == project_id)
    if not include_deleted:
        stmt = stmt.where(SiteProjectRecord.deleted_at.is_(None))
    return db.scalar(stmt)


def soft_delete_project(db: Session, project: SiteProjectRecord) -> None:
    project.deleted_at = datetime.now(timezone.utc)
    project.status = "missing"
    db.commit()


def project_to_dict(project: SiteProjectRecord) -> dict[str, Any]:
    raw_data = project.raw_data or {}
    return {
        "project_id": project.project_id,
        "name": project.project_name,
        "city": project.city,
        "district": project.district,
        "address": project.address,
        "longitude": project.longitude,
        "latitude": project.latitude,
        "radius_meters": project.radius_meters,
        "business_type": project.business_type,
        "expected_area_sqm": raw_data.get("expected_area_sqm"),
        "investment_budget": raw_data.get("investment_budget"),
        "status": project.status,
        "created_at": project.created_at,
        "deleted_at": project.deleted_at,
    }


def row_to_dict(row: Any) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def project_stats(db: Session, project_id: str) -> dict[str, Any]:
    poi_count = count_rows(db, UnifiedPOIRecord, project_id)
    competitor_count = int(
        db.scalar(
            select(func.count()).select_from(UnifiedCompetitorRecord).where(
                UnifiedCompetitorRecord.project_id == project_id,
                UnifiedCompetitorRecord.status.in_(EFFECTIVE_COMPETITOR_STATUSES),
            )
        )
        or 0
    )
    food_count = count_rows(db, FoodBusinessRecord, project_id)
    entertainment_count = count_rows(db, EntertainmentRecord, project_id)
    rent_count = count_rows(db, RentDataRecord, project_id)
    missing = data_quality(db, project_id)["missing"]
    return {
        "poi_count": poi_count,
        "competitor_count": competitor_count,
        "food_count": food_count,
        "entertainment_count": entertainment_count,
        "rent_count": rent_count,
        "missing_fields": missing,
    }


def count_rows(db: Session, model: Any, project_id: str) -> int:
    return int(db.scalar(select(func.count()).select_from(model).where(model.project_id == project_id)) or 0)


def count_pois_by_category(db: Session, project_id: str, category: str) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(UnifiedPOIRecord).where(
                UnifiedPOIRecord.project_id == project_id,
                UnifiedPOIRecord.category == category,
            )
        )
        or 0
    )


def dataset(db: Session, project: SiteProjectRecord) -> dict[str, Any]:
    project_id = project.project_id
    return {
        "project": project_to_dict(project),
        "pois": rows_for_project(db, UnifiedPOIRecord, project_id),
        "competitors": [
            row_to_dict(row)
            for row in db.scalars(
                select(UnifiedCompetitorRecord).where(
                    UnifiedCompetitorRecord.project_id == project_id,
                    UnifiedCompetitorRecord.status.in_(EFFECTIVE_COMPETITOR_STATUSES),
                ).order_by(UnifiedCompetitorRecord.id.asc())
            ).all()
        ],
        "food_businesses": rows_for_project(db, FoodBusinessRecord, project_id),
        "entertainments": rows_for_project(db, EntertainmentRecord, project_id),
        "rent_data": latest_for_project(db, RentDataRecord, project_id) or {},
        "population_data": latest_for_project(db, PopulationDataRecord, project_id) or {},
        "supplements": rows_for_project(db, SupplementRecord, project_id),
    }


def rows_for_project(db: Session, model: Any, project_id: str) -> list[dict[str, Any]]:
    rows = db.scalars(select(model).where(model.project_id == project_id).order_by(model.id.asc())).all()
    return [row_to_dict(row) for row in rows]


def latest_for_project(db: Session, model: Any, project_id: str) -> dict[str, Any] | None:
    row = db.scalar(select(model).where(model.project_id == project_id).order_by(model.timestamp.desc(), model.id.desc()))
    return row_to_dict(row) if row else None


def import_project_data(db: Session, project_id: str, data_type: str, raw: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    normalized, warnings = normalize_data({"type": data_type, "data": raw})
    model = DATASET_TABLES[data_type]
    payload = {key: value for key, value in normalized.items() if key in model.__table__.columns.keys()}
    payload["project_id"] = project_id
    row = model(**payload)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row_to_dict(row), warnings


def competitor_detail_quality(competitors: list[UnifiedCompetitorRecord]) -> tuple[dict[str, Any], float]:
    confirmed = [row for row in competitors if row.status == "confirmed"]
    missing_counts: dict[str, int] = {
        field_name: 0
        for field_name in (*COMPETITOR_DETAIL_IMPORTANT_FIELDS, *COMPETITOR_DETAIL_RECOMMENDED_FIELDS)
    }
    incomplete_items: list[dict[str, Any]] = []
    important_missing_total = 0
    recommended_missing_total = 0

    for row in confirmed:
        raw_data = row.raw_data if isinstance(row.raw_data, dict) else {}
        manual_detail = raw_data.get("manual_detail") if isinstance(raw_data.get("manual_detail"), dict) else {}

        def field_value(field_name: str):
            if field_name in {"business_hours", "recharge_info"}:
                return manual_detail.get(field_name)
            return getattr(row, field_name, None)

        important_missing = [
            field_name
            for field_name in COMPETITOR_DETAIL_IMPORTANT_FIELDS
            if field_value(field_name) is None or str(field_value(field_name)).strip() == ""
        ]
        recommended_missing = [
            field_name
            for field_name in COMPETITOR_DETAIL_RECOMMENDED_FIELDS
            if field_value(field_name) is None or str(field_value(field_name)).strip() == ""
        ]
        for field_name in (*important_missing, *recommended_missing):
            missing_counts[field_name] += 1
        important_missing_total += len(important_missing)
        recommended_missing_total += len(recommended_missing)

        if important_missing or recommended_missing:
            labels = [
                COMPETITOR_DETAIL_IMPORTANT_FIELDS.get(field_name)
                or COMPETITOR_DETAIL_RECOMMENDED_FIELDS[field_name]
                for field_name in (*important_missing, *recommended_missing)
            ]
            incomplete_items.append(
                {
                    "competitor_id": row.id,
                    "name": row.name,
                    "missing_fields": labels,
                }
            )

    missing_summary = []
    for importance, fields in (
        ("important", COMPETITOR_DETAIL_IMPORTANT_FIELDS),
        ("recommended", COMPETITOR_DETAIL_RECOMMENDED_FIELDS),
    ):
        for field_name, label in fields.items():
            if missing_counts[field_name] > 0:
                missing_summary.append(
                    {
                        "field": field_name,
                        "label": label,
                        "missing_count": missing_counts[field_name],
                        "importance": importance,
                    }
                )

    # 只影响数据完整度，不改变业务评分；详情扣分封顶 10 分。
    detail_penalty = min(10.0, important_missing_total + recommended_missing_total * 0.25)
    return {
        "total_competitors": len(competitors),
        "confirmed_competitors": len(confirmed),
        "incomplete_competitors": len(incomplete_items),
        "missing_summary": missing_summary,
        "incomplete_items": incomplete_items,
    }, detail_penalty


def supporting_detail_quality(
    food_rows: list[FoodBusinessRecord],
    entertainment_rows: list[EntertainmentRecord],
) -> tuple[dict[str, Any], float]:
    missing_counts = {
        "business_hours": 0,
        "night_operation": 0,
        "is_24_hours": 0,
    }
    labels = {
        "business_hours": "营业时间",
        "night_operation": "夜间营业",
        "is_24_hours": "是否24小时营业",
    }
    incomplete_items: list[dict[str, Any]] = []
    completed = 0
    missing_total = 0

    def is_missing(value: Any) -> bool:
        return value is None or (isinstance(value, str) and not value.strip())

    def inspect_row(row: Any, record_type: str, category: str) -> None:
        nonlocal completed, missing_total
        raw = row.raw_data if isinstance(row.raw_data, dict) else {}
        manual_detail = raw.get("manual_detail") if isinstance(raw.get("manual_detail"), dict) else {}
        required = ("is_24_hours", "night_operation") if category == "night_business" else (
            "business_hours",
            "night_operation",
        )
        missing_fields = [field_name for field_name in required if is_missing(manual_detail.get(field_name))]
        if not missing_fields:
            completed += 1
            return
        for field_name in missing_fields:
            missing_counts[field_name] += 1
        missing_total += len(missing_fields)
        incomplete_items.append(
            {
                "id": f"{record_type}:{row.id}",
                "name": row.name,
                "category": category,
                "missing_fields": [labels[field_name] for field_name in missing_fields],
            }
        )

    confirmed_food = [row for row in food_rows if row.status == "confirmed"]
    confirmed_entertainment = [row for row in entertainment_rows if row.status == "confirmed"]
    for row in confirmed_food:
        raw = row.raw_data if isinstance(row.raw_data, dict) else {}
        groups = set(raw.get("supporting_groups") or [])
        if raw.get("supporting_group"):
            groups.add(raw["supporting_group"])
        category = "night_business" if "night_economy" in groups else "food"
        inspect_row(row, "food", category)
    for row in confirmed_entertainment:
        inspect_row(row, "entertainment", "entertainment")

    missing_summary = [
        {"field": field_name, "label": labels[field_name], "missing_count": count}
        for field_name, count in missing_counts.items()
        if count > 0
    ]
    total_confirmed = len(confirmed_food) + len(confirmed_entertainment)
    # 每个缺失关键详情扣 0.5 分，封顶 5 分；仅影响数据质量，不影响业务评分。
    detail_penalty = min(5.0, missing_total * 0.5)
    return {
        "total_confirmed": total_confirmed,
        "completed": completed,
        "incomplete": len(incomplete_items),
        "missing_summary": missing_summary,
        "incomplete_items": incomplete_items,
    }, detail_penalty


def rent_data_quality(rent_rows: list[RentDataRecord]) -> tuple[dict[str, Any], float]:
    confirmed = [row for row in rent_rows if row.status == "confirmed"]
    core_fields = {
        "address": "地址",
        "area_sqm": "面积",
        "monthly_rent": "月租金",
    }
    detail_fields = {
        "property_type": "物业类型",
        "source_url": "来源",
        "publish_date": "发布日期",
        "floor": "楼层",
    }
    missing_counts = {field_name: 0 for field_name in (*core_fields, *detail_fields)}
    incomplete_items: list[dict[str, Any]] = []
    detail_completed = 0
    core_missing_total = 0

    def is_missing(value: Any) -> bool:
        return value is None or (isinstance(value, str) and not value.strip())

    for row in confirmed:
        raw_data = row.raw_data if isinstance(row.raw_data, dict) else {}
        manual_detail = raw_data.get("manual_detail") if isinstance(raw_data.get("manual_detail"), dict) else {}
        values = {
            "address": row.location_type or raw_data.get("address") or raw_data.get("地址"),
            "area_sqm": row.area_sqm,
            "monthly_rent": row.monthly_rent,
            **{field_name: manual_detail.get(field_name) for field_name in detail_fields},
        }
        missing_core = [field_name for field_name in core_fields if is_missing(values.get(field_name))]
        missing_detail = [field_name for field_name in detail_fields if is_missing(values.get(field_name))]
        core_missing_total += len(missing_core)
        for field_name in (*missing_core, *missing_detail):
            missing_counts[field_name] += 1
        if not missing_detail:
            detail_completed += 1
        if missing_core or missing_detail:
            labels = {**core_fields, **detail_fields}
            incomplete_items.append(
                {
                    "rent_id": row.id,
                    "address": values.get("address") or "地址待补充",
                    "missing_fields": [labels[field_name] for field_name in (*missing_core, *missing_detail)],
                    "core_missing_fields": [core_fields[field_name] for field_name in missing_core],
                }
            )

    labels = {**core_fields, **detail_fields}
    missing_summary = [
        {
            "field": field_name,
            "label": labels[field_name],
            "missing_count": count,
            "importance": "core" if field_name in core_fields else "recommended",
        }
        for field_name, count in missing_counts.items()
        if count > 0
    ]
    # 仅核心字段影响数据质量，每缺一项扣 1 分，租金数据总扣分封顶 5 分。
    penalty = min(5.0, float(core_missing_total))
    return {
        "total_confirmed": len(confirmed),
        "detail_completed": detail_completed,
        "incomplete": len(incomplete_items),
        "missing_summary": missing_summary,
        "incomplete_items": incomplete_items,
    }, penalty


def data_quality(db: Session, project_id: str) -> dict[str, Any]:
    missing: list[str] = []
    warnings: list[str] = []
    competitors = db.scalars(
        select(UnifiedCompetitorRecord).where(
            UnifiedCompetitorRecord.project_id == project_id,
            UnifiedCompetitorRecord.status.in_(EFFECTIVE_COMPETITOR_STATUSES),
        )
    ).all()
    detail_quality, detail_penalty = competitor_detail_quality(list(competitors))
    supporting_food_rows = list(
        db.scalars(select(FoodBusinessRecord).where(FoodBusinessRecord.project_id == project_id)).all()
    )
    supporting_entertainment_rows = list(
        db.scalars(select(EntertainmentRecord).where(EntertainmentRecord.project_id == project_id)).all()
    )
    supporting_quality, supporting_penalty = supporting_detail_quality(
        supporting_food_rows,
        supporting_entertainment_rows,
    )
    rent_rows = list(
        db.scalars(select(RentDataRecord).where(RentDataRecord.project_id == project_id)).all()
    )
    rent_quality, rent_penalty = rent_data_quality(rent_rows)
    pois = count_rows(db, UnifiedPOIRecord, project_id)
    food = count_rows(db, FoodBusinessRecord, project_id) or count_pois_by_category(db, project_id, "food")
    entertainment = count_rows(db, EntertainmentRecord, project_id) or count_pois_by_category(db, project_id, "entertainment")

    if not competitors:
        missing.append("竞品数据")
    else:
        if not any(row.hour_price is not None or row.member_price is not None for row in competitors):
            missing.append("竞品价格")
        if not any(row.occupancy_rate is not None for row in competitors):
            missing.append("竞品上座率")
        if not any(row.machine_count is not None or row.cpu or row.gpu or row.monitor for row in competitors):
            missing.append("竞品机器配置")
        if not any(row.monthly_sales is not None or row.annual_sales is not None for row in competitors):
            missing.append("竞品营业额")
            warnings.append("当前竞品数据只能用于基础距离分析")
    if detail_quality["incomplete_competitors"]:
        warnings.append("已确认竞品仍缺少经营信息，建议补充后再生成报告")
    if supporting_quality["incomplete"]:
        warnings.append("已确认周边配套仍缺少营业详情，建议继续人工核实")
    if rent_quality["total_confirmed"] == 0:
        missing.append("真实租金")
    elif any(item.get("core_missing_fields") for item in rent_quality["incomplete_items"]):
        missing.append("租金核心字段")
        warnings.append("已确认租金缺少地址、面积或月租金，成本数据依据仍不完整")
    if any(item.get("missing_fields") for item in rent_quality["incomplete_items"]):
        warnings.append("已确认租金仍有建议补充信息，请核实物业类型、来源、发布日期和楼层")
    if pois == 0:
        missing.append("周边 POI")
    if food == 0:
        missing.append("餐饮和夜间消费数据")
    if entertainment == 0:
        missing.append("娱乐配套数据")

    rent_missing_marker = 1 if "租金核心字段" in missing else 0
    quality_score = max(
        0,
        round(
            100
            - (len(missing) - rent_missing_marker) * 12
            - detail_penalty
            - supporting_penalty
            - rent_penalty
        ),
    )
    return {
        "project_id": project_id,
        "quality_score": quality_score,
        "missing": missing,
        "warnings": warnings,
        "competitor_detail_quality": detail_quality,
        "supporting_detail_quality": supporting_quality,
        "rent_quality": rent_quality,
    }
