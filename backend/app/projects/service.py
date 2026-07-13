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
        "created_at": project.created_at,
        "deleted_at": project.deleted_at,
    }


def row_to_dict(row: Any) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def project_stats(db: Session, project_id: str) -> dict[str, Any]:
    poi_count = count_rows(db, UnifiedPOIRecord, project_id)
    competitor_count = count_rows(db, UnifiedCompetitorRecord, project_id)
    food_count = count_rows(db, FoodBusinessRecord, project_id)
    entertainment_count = count_rows(db, EntertainmentRecord, project_id)
    missing = data_quality(db, project_id)["missing"]
    return {
        "poi_count": poi_count,
        "competitor_count": competitor_count,
        "food_count": food_count,
        "entertainment_count": entertainment_count,
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
        "competitors": rows_for_project(db, UnifiedCompetitorRecord, project_id),
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


def data_quality(db: Session, project_id: str) -> dict[str, Any]:
    missing: list[str] = []
    warnings: list[str] = []
    competitors = db.scalars(select(UnifiedCompetitorRecord).where(UnifiedCompetitorRecord.project_id == project_id)).all()
    rent = latest_for_project(db, RentDataRecord, project_id)
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
    if not rent or not rent.get("monthly_rent"):
        missing.append("真实租金")
    if pois == 0:
        missing.append("周边 POI")
    if food == 0:
        missing.append("餐饮和夜间消费数据")
    if entertainment == 0:
        missing.append("娱乐配套数据")

    quality_score = max(0, 100 - len(missing) * 12)
    return {
        "project_id": project_id,
        "quality_score": quality_score,
        "missing": missing,
        "warnings": warnings,
    }
