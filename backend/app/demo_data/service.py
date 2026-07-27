from __future__ import annotations

from datetime import datetime, timezone
from random import Random
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    EntertainmentRecord,
    FoodBusinessRecord,
    RentDataRecord,
    SiteProjectRecord,
    UnifiedCompetitorRecord,
    UnifiedPOIRecord,
)

DEMO_SOURCE = "simulation"
DEMO_WARNING = "演示模拟数据，仅用于流程演示；不能作为真实投资决策依据。"


def generate_project_demo_data(
    db: Session,
    project: SiteProjectRecord,
    *,
    include: list[str],
    max_competitors: int = 8,
    max_supporting: int = 12,
    rent_samples: int = 5,
) -> dict[str, Any]:
    include_set = set(include or [])
    rng = Random(project.project_id)
    generated = {"competitors": 0, "supporting": 0, "rent": 0}
    updated = {"competitors": 0, "supporting": 0, "rent": 0}

    if "competitor" in include_set:
        count = _enrich_competitors(db, project.project_id, rng, max_competitors)
        updated["competitors"] = count
        if count == 0:
            generated["competitors"] = _create_demo_competitors(db, project, rng, min(3, max_competitors))

    if "supporting" in include_set:
        count = _enrich_supporting(db, project.project_id, rng, max_supporting)
        updated["supporting"] = count
        if count == 0:
            generated["supporting"] = _create_demo_supporting(db, project, rng, min(8, max_supporting))

    if "rent" in include_set:
        generated["rent"] = _create_demo_rent_samples(db, project, rng, rent_samples)

    project_raw = _safe_dict(project.raw_data)
    project_raw["demo_data_generated"] = True
    project_raw["demo_data_warning"] = DEMO_WARNING
    project_raw["demo_data_updated_at"] = datetime.now(timezone.utc).isoformat()
    project.raw_data = project_raw

    db.commit()
    return {
        "success": True,
        "project_id": project.project_id,
        "generated": generated,
        "updated": updated,
        "message": "演示数据已生成，请继续执行数据核验、评分和AI报告。",
        "warning": DEMO_WARNING,
    }


def simulation_data_summary(db: Session, project_id: str) -> dict[str, Any]:
    competitor_count = _count_demo_rows(db, UnifiedCompetitorRecord, project_id)
    food_count = _count_demo_rows(db, FoodBusinessRecord, project_id)
    entertainment_count = _count_demo_rows(db, EntertainmentRecord, project_id)
    rent_count = _count_demo_rows(db, RentDataRecord, project_id)
    total = competitor_count + food_count + entertainment_count + rent_count
    return {
        "has_simulation_data": total > 0,
        "source": DEMO_SOURCE,
        "warning": DEMO_WARNING if total > 0 else None,
        "competitor_count": competitor_count,
        "food_count": food_count,
        "entertainment_count": entertainment_count,
        "rent_count": rent_count,
        "total_count": total,
    }


def _enrich_competitors(db: Session, project_id: str, rng: Random, max_items: int) -> int:
    rows = list(
        db.scalars(
            select(UnifiedCompetitorRecord)
            .where(
                UnifiedCompetitorRecord.project_id == project_id,
                UnifiedCompetitorRecord.status != "rejected",
                UnifiedCompetitorRecord.source != "manual",
            )
            .order_by(UnifiedCompetitorRecord.distance_meters.asc().nullslast(), UnifiedCompetitorRecord.id.asc())
            .limit(max_items)
        ).all()
    )
    for index, row in enumerate(rows):
        _fill_competitor(row, rng, index)
    return len(rows)


def _create_demo_competitors(db: Session, project: SiteProjectRecord, rng: Random, count: int) -> int:
    poi_rows = list(
        db.scalars(
            select(UnifiedPOIRecord)
            .where(
                UnifiedPOIRecord.project_id == project.project_id,
                UnifiedPOIRecord.category == "competitor",
            )
            .order_by(UnifiedPOIRecord.distance_meters.asc().nullslast(), UnifiedPOIRecord.id.asc())
            .limit(count)
        ).all()
    )
    created = 0
    for index in range(count):
        poi = poi_rows[index] if index < len(poi_rows) else None
        row = UnifiedCompetitorRecord(
            project_id=project.project_id,
            name=poi.name if poi else f"{project.address or project.city}周边电竞馆样本{index + 1}",
            address=poi.address if poi else f"{project.address or project.city}周边商圈",
            distance_meters=poi.distance_meters if poi and poi.distance_meters is not None else 300 + index * 180,
            source=DEMO_SOURCE,
            status="confirmed",
            confidence=0.3,
            raw_data=_demo_raw({"generated_from": "poi" if poi else "project"}),
        )
        _fill_competitor(row, rng, index)
        db.add(row)
        created += 1
    return created


def _fill_competitor(row: UnifiedCompetitorRecord, rng: Random, index: int) -> None:
    machine_count = row.machine_count or rng.choice([72, 96, 120, 150, 180])
    hour_price = row.hour_price or rng.choice([8, 10, 12, 15, 18])
    occupancy_rate = row.occupancy_rate if row.occupancy_rate is not None else round(rng.uniform(0.38, 0.72), 2)
    row.machine_count = machine_count
    row.area_sqm = row.area_sqm or float(machine_count * rng.choice([4, 5, 6]))
    row.cpu = row.cpu or rng.choice(["i5-12400F", "i5-13400F", "Ryzen 5 5600"])
    row.gpu = row.gpu or rng.choice(["RTX 3060", "RTX 4060", "RTX 4070"])
    row.monitor = row.monitor or rng.choice(["27英寸 165Hz", "27英寸 240Hz", "32英寸 165Hz"])
    row.hour_price = hour_price
    row.member_price = row.member_price or max(6, hour_price - 2)
    row.occupancy_rate = occupancy_rate
    row.monthly_sales = row.monthly_sales or round(machine_count * hour_price * occupancy_rate * 8 * 30, 2)
    row.annual_sales = row.annual_sales or round(float(row.monthly_sales or 0) * 12, 2)
    row.opening_date = row.opening_date or str(2019 + index % 5)
    row.confidence = min(row.confidence or 0.3, 0.3)
    row.status = "confirmed"
    row.raw_data = _merge_demo_detail(
        row.raw_data,
        {
            "business_hours": rng.choice(["10:00-02:00", "12:00-03:00", "24小时营业"]),
            "recharge_info": rng.choice(["充500送80", "充1000送200", "会员充值折扣"]),
            "remark": DEMO_WARNING,
        },
    )


def _enrich_supporting(db: Session, project_id: str, rng: Random, max_items: int) -> int:
    food_rows = list(
        db.scalars(
            select(FoodBusinessRecord)
            .where(FoodBusinessRecord.project_id == project_id, FoodBusinessRecord.status != "rejected")
            .where(FoodBusinessRecord.source != "manual")
            .order_by(FoodBusinessRecord.distance_meters.asc().nullslast(), FoodBusinessRecord.id.asc())
            .limit(max_items)
        ).all()
    )
    entertainment_rows = list(
        db.scalars(
            select(EntertainmentRecord)
            .where(EntertainmentRecord.project_id == project_id, EntertainmentRecord.status != "rejected")
            .where(EntertainmentRecord.source != "manual")
            .order_by(EntertainmentRecord.distance_meters.asc().nullslast(), EntertainmentRecord.id.asc())
            .limit(max(1, max_items // 2))
        ).all()
    )
    for row in food_rows:
        row.status = "confirmed"
        row.business_hours = row.business_hours or rng.choice(["10:00-02:00", "11:00-01:00", "17:00-03:00"])
        row.night_business = True if row.night_business is None else row.night_business
        row.rating = row.rating or round(rng.uniform(4.0, 4.8), 1)
        row.confidence = min(row.confidence or 0.3, 0.3)
        row.raw_data = _merge_demo_detail(row.raw_data, {"night_operation": True, "business_hours": row.business_hours})
    for row in entertainment_rows:
        row.status = "confirmed"
        row.business_hours = row.business_hours or rng.choice(["12:00-02:00", "14:00-03:00", "18:00-04:00"])
        row.night_business = True if row.night_business is None else row.night_business
        row.confidence = min(row.confidence or 0.3, 0.3)
        row.raw_data = _merge_demo_detail(row.raw_data, {"night_operation": True, "business_hours": row.business_hours})
    return len(food_rows) + len(entertainment_rows)


def _create_demo_supporting(db: Session, project: SiteProjectRecord, rng: Random, count: int) -> int:
    created = 0
    food_count = max(1, count * 2 // 3)
    entertainment_count = count - food_count
    for index in range(food_count):
        hours = rng.choice(["10:00-02:00", "11:00-01:00", "17:00-03:00"])
        db.add(
            FoodBusinessRecord(
                project_id=project.project_id,
                name=f"{project.address or project.city}周边夜间餐饮样本{index + 1}",
                distance_meters=150 + index * 80,
                category=rng.choice(["餐饮", "烧烤", "小吃", "快餐"]),
                business_hours=hours,
                night_business=True,
                rating=round(rng.uniform(4.0, 4.8), 1),
                source=DEMO_SOURCE,
                confidence=0.3,
                status="confirmed",
                raw_data=_merge_demo_detail(_demo_raw({"supporting_group": "food"}), {"night_operation": True, "business_hours": hours}),
            )
        )
        created += 1
    for index in range(entertainment_count):
        hours = rng.choice(["12:00-02:00", "14:00-03:00", "18:00-04:00"])
        db.add(
            EntertainmentRecord(
                project_id=project.project_id,
                name=f"{project.address or project.city}周边娱乐样本{index + 1}",
                type=rng.choice(["KTV", "台球", "电影院", "密室"]),
                distance_meters=260 + index * 120,
                business_hours=hours,
                night_business=True,
                source=DEMO_SOURCE,
                confidence=0.3,
                status="confirmed",
                raw_data=_merge_demo_detail(_demo_raw({"supporting_group": "entertainment"}), {"night_operation": True, "business_hours": hours}),
            )
        )
        created += 1
    return created


def _create_demo_rent_samples(db: Session, project: SiteProjectRecord, rng: Random, count: int) -> int:
    existing_demo_rows = list(
        db.scalars(
            select(RentDataRecord).where(
                RentDataRecord.project_id == project.project_id,
                RentDataRecord.source == DEMO_SOURCE,
            )
        ).all()
    )
    for row in existing_demo_rows:
        db.delete(row)

    expected_area = _expected_area(project)
    created = 0
    for index in range(count):
        area = float(max(200, expected_area + rng.randint(-120, 160)))
        unit_price = float(rng.choice([48, 55, 62, 68, 75, 88]))
        monthly_rent = round(area * unit_price, 2)
        db.add(
            RentDataRecord(
                project_id=project.project_id,
                monthly_rent=monthly_rent,
                area_sqm=area,
                rent_per_sqm=unit_price,
                location_type=f"{project.address or project.city}周边商铺样本{index + 1}",
                source=DEMO_SOURCE,
                confidence=0.3,
                status="confirmed",
                raw_data=_merge_demo_detail(
                    _demo_raw({"address": f"{project.address or project.city}周边商铺样本{index + 1}"}),
                    {
                        "property_type": "临街商业",
                        "floor": rng.choice(["1层", "2层", "负1层"]),
                        "source_url": "simulation://demo-rent",
                        "publish_date": datetime.now(timezone.utc).date().isoformat(),
                        "rent_remark": DEMO_WARNING,
                    },
                ),
            )
        )
        created += 1
    return created


def _expected_area(project: SiteProjectRecord) -> int:
    raw = _safe_dict(project.raw_data)
    value = raw.get("expected_area_sqm")
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 520


def _merge_demo_detail(raw_data: Any, detail: dict[str, Any]) -> dict[str, Any]:
    raw = _safe_dict(raw_data)
    manual_detail = raw.get("manual_detail") if isinstance(raw.get("manual_detail"), dict) else {}
    demo_detail = raw.get("demo_detail") if isinstance(raw.get("demo_detail"), dict) else {}
    merged_detail = {**manual_detail}
    for key, value in detail.items():
        if merged_detail.get(key) in (None, ""):
            merged_detail[key] = value
    raw["manual_detail"] = merged_detail
    raw["demo_detail"] = {**demo_detail, **detail}
    raw["demo_generated"] = True
    raw["demo_source"] = DEMO_SOURCE
    raw["demo_warning"] = DEMO_WARNING
    raw["demo_generated_at"] = datetime.now(timezone.utc).isoformat()
    return raw


def _demo_raw(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "demo_generated": True,
        "demo_source": DEMO_SOURCE,
        "demo_warning": DEMO_WARNING,
        **(extra or {}),
    }


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _count_demo_rows(db: Session, model: Any, project_id: str) -> int:
    rows = db.scalars(select(model).where(model.project_id == project_id)).all()
    count = 0
    for row in rows:
        raw = _safe_dict(getattr(row, "raw_data", None))
        if getattr(row, "source", None) == DEMO_SOURCE or raw.get("demo_generated") is True:
            count += 1
    return count
