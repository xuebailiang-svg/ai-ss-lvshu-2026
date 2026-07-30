from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.data_source.base import DataSourceRequest
from app.models import (
    DataSyncRunRecord,
    RegionalStatisticRecord,
    SiteProjectRecord,
)
from app.projects.service import (
    count_pois_by_category,
    count_rows,
    project_stats,
)
from app.models import EntertainmentRecord, FoodBusinessRecord, RentDataRecord, UnifiedPOIRecord

from .provider import GovernmentStatsProvider


ADMIN_CODES = {
    "陕西省": "610000",
    "西安市": "610100",
    "新城区": "610102",
    "碑林区": "610103",
    "莲湖区": "610104",
    "灞桥区": "610111",
    "未央区": "610112",
    "雁塔区": "610113",
    "阎良区": "610114",
    "临潼区": "610115",
    "长安区": "610116",
    "高陵区": "610117",
    "鄠邑区": "610118",
    "蓝田县": "610122",
    "周至县": "610124",
}

METRIC_GROUPS = {
    "resident_population": "population",
    "registered_population": "population",
    "urbanization_rate": "population",
    "population_age_structure": "population",
    "gdp": "economy",
    "tertiary_industry_share": "economy",
    "retail_sales_total": "consumption",
    "disposable_income_per_capita": "consumption",
    "consumption_expenditure_per_capita": "consumption",
    "employment_total": "employment",
}

CORE_METRICS = {
    "resident_population": "常住人口",
    "gdp": "地区生产总值",
    "tertiary_industry_share": "第三产业占比",
    "retail_sales_total": "社会消费品零售总额",
    "disposable_income_per_capita": "居民人均可支配收入",
}


def now() -> datetime:
    return datetime.now(timezone.utc)


def admin_code(name: str | None) -> str | None:
    if not name:
        return None
    clean = name.strip()
    return ADMIN_CODES.get(clean)


def statistic_to_dict(row: RegionalStatisticRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "metric_code": row.metric_code,
        "metric_name": row.metric_name,
        "value_numeric": row.value_numeric,
        "value_text": row.value_text,
        "unit": row.unit,
        "scope_level": row.scope_level,
        "scope_code": row.scope_code,
        "scope_name": row.scope_name,
        "stat_period": row.stat_period,
        "source_name": row.source_name,
        "source_url": row.source_url,
        "source_format": row.source_format,
        "published_at": row.published_at,
        "collected_at": row.collected_at,
        "status": row.status,
        "confidence": row.confidence,
    }


def sync_run_to_dict(row: DataSyncRunRecord | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": row.id,
        "provider": row.provider,
        "project_id": row.project_id,
        "scope_code": row.scope_code,
        "scope_name": row.scope_name,
        "status": row.status,
        "imported_count": row.imported_count,
        "pending_review_count": row.pending_review_count,
        "failed_count": row.failed_count,
        "result_snapshot": row.result_snapshot or {},
        "error_message": row.error_message,
        "created_at": row.created_at,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
    }


def create_sync_run(
    db: Session,
    *,
    project_id: str | None,
    city: str,
    district: str | None,
    sources: list[str],
    force_refresh: bool = False,
) -> DataSyncRunRecord:
    row = DataSyncRunRecord(
        provider="government_stats",
        project_id=project_id,
        scope_code=admin_code(district) or admin_code(city),
        scope_name=district or city,
        status="pending",
        input_snapshot={
            "city": city,
            "district": district,
            "sources": sources,
            "force_refresh": force_refresh,
        },
        result_snapshot={},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _upsert_statistic(db: Session, item) -> tuple[RegionalStatisticRecord, bool]:
    row = db.scalar(
        select(RegionalStatisticRecord).where(
            RegionalStatisticRecord.metric_code == item.metric_code,
            RegionalStatisticRecord.scope_code == item.scope_code,
            RegionalStatisticRecord.stat_period == item.stat_period,
            RegionalStatisticRecord.source_name == item.source_name,
        )
    )
    created = row is None
    if row is None:
        row = RegionalStatisticRecord(
            metric_code=item.metric_code,
            scope_code=item.scope_code,
            stat_period=item.stat_period,
            source_name=item.source_name,
        )
        db.add(row)
    previous_status = row.status if not created else None
    row.metric_name = item.metric_name
    row.value_numeric = item.value_numeric
    row.value_text = item.value_text
    row.unit = item.unit
    row.scope_level = item.scope_level
    row.scope_name = item.scope_name
    row.source_url = str(item.source_url)
    row.source_format = item.source_format
    row.published_at = item.published_at
    row.collected_at = now()
    row.status = previous_status if previous_status in {"confirmed", "rejected"} else item.status
    row.confidence = item.confidence
    row.raw_data = item.raw_data or {}
    return row, created


async def execute_sync_run(run_id: int) -> None:
    with SessionLocal() as db:
        run = db.get(DataSyncRunRecord, run_id)
        if not run:
            return
        run.status = "running"
        run.started_at = now()
        db.commit()
        snapshot = run.input_snapshot or {}
        try:
            result = await GovernmentStatsProvider().get_statistics(
                DataSourceRequest(
                    project_id=run.project_id,
                    city=snapshot.get("city"),
                    categories=list(snapshot.get("sources") or []),
                )
            )
            imported = 0
            pending = 0
            for item in result.items:
                row, _ = _upsert_statistic(db, item)
                imported += 1
                if row.status == "pending_review":
                    pending += 1
            run.imported_count = imported
            run.pending_review_count = pending
            run.failed_count = len(result.warnings)
            run.result_snapshot = {
                "warnings": list(result.warnings),
                "sources": result.metadata.get("sources", {}),
                "stat_periods": sorted({item.stat_period for item in result.items}, reverse=True),
                "scope_names": sorted({item.scope_name for item in result.items}),
            }
            run.status = "success" if result.items and not result.warnings else "partial" if result.items else "failed"
            run.error_message = None if result.items else "未从官方页面识别到可用指标"
        except Exception:
            run.status = "failed"
            run.failed_count = 1
            run.error_message = "政府公开数据同步失败，请稍后重试或使用官方文件上传"
        finally:
            run.finished_at = now()
            db.commit()


def latest_sync_run(db: Session, project_id: str | None = None) -> DataSyncRunRecord | None:
    stmt = select(DataSyncRunRecord).where(DataSyncRunRecord.provider == "government_stats")
    if project_id:
        stmt = stmt.where(DataSyncRunRecord.project_id == project_id)
    return db.scalar(stmt.order_by(DataSyncRunRecord.created_at.desc(), DataSyncRunRecord.id.desc()))


def has_fresh_cache(db: Session, city: str, district: str | None = None, *, days: int = 365) -> bool:
    codes = [code for code in (admin_code(city), admin_code(district)) if code]
    if not codes:
        return False
    row = db.scalar(
        select(RegionalStatisticRecord)
        .where(
            RegionalStatisticRecord.scope_code.in_(codes),
            RegionalStatisticRecord.status == "confirmed",
            RegionalStatisticRecord.collected_at >= now() - timedelta(days=days),
        )
        .limit(1)
    )
    return row is not None


def _latest_confirmed_by_metric(
    db: Session,
    *,
    scope_codes: list[str],
) -> list[RegionalStatisticRecord]:
    if not scope_codes:
        return []
    rows = list(
        db.scalars(
            select(RegionalStatisticRecord)
            .where(
                RegionalStatisticRecord.scope_code.in_(scope_codes),
                RegionalStatisticRecord.status == "confirmed",
            )
            .order_by(
                RegionalStatisticRecord.scope_level.desc(),
                RegionalStatisticRecord.stat_period.desc(),
                RegionalStatisticRecord.id.desc(),
            )
        ).all()
    )
    latest: dict[tuple[str, str], RegionalStatisticRecord] = {}
    for row in rows:
        latest.setdefault((row.scope_code, row.metric_code), row)
    return list(latest.values())


def city_insight(db: Session, project: SiteProjectRecord) -> dict[str, Any]:
    city_code = admin_code(project.city)
    district_code = admin_code(project.district)
    codes = [code for code in (city_code, district_code, ADMIN_CODES.get("陕西省"), "100000") if code]
    rows = _latest_confirmed_by_metric(db, scope_codes=codes)
    macro_context: dict[str, dict[str, list[dict[str, Any]]]] = {
        "population": {},
        "economy": {},
        "consumption": {},
        "employment": {},
    }
    for row in rows:
        group = METRIC_GROUPS.get(row.metric_code)
        if not group:
            continue
        macro_context[group].setdefault(row.scope_level, []).append(statistic_to_dict(row))

    stats = project_stats(db, project.project_id)
    trade_area_context = {
        "scope": {
            "radius_meters": project.radius_meters,
            "address": project.address,
            "note": "以下为项目分析半径内的POI与人工确认数据，不是政府宏观统计。",
        },
        "poi": {
            "total": stats["poi_count"],
            "transport": count_pois_by_category(db, project.project_id, "transport"),
            "education": count_pois_by_category(db, project.project_id, "education"),
            "residential": count_pois_by_category(db, project.project_id, "residential"),
        },
        "competitors": {"effective_count": stats["competitor_count"]},
        "supporting": {
            "food_count": count_rows(db, FoodBusinessRecord, project.project_id),
            "entertainment_count": count_rows(db, EntertainmentRecord, project.project_id),
        },
        "rent": {"sample_count": count_rows(db, RentDataRecord, project.project_id)},
    }
    target_rows = [row for row in rows if row.scope_level in {"city", "district"}]
    fallback_rows = [row for row in rows if row.scope_level in {"province", "country"}]
    available_codes = {row.metric_code for row in target_rows}
    missing_metrics = [
        {"metric_code": code, "label": label}
        for code, label in CORE_METRICS.items()
        if code not in available_codes
    ]
    sources = sorted(
        {
            (row.source_name, row.source_url, row.stat_period, row.scope_name)
            for row in rows
        }
    )
    latest_period = max((row.stat_period for row in rows), default=None)
    latest_target_period = max((row.stat_period for row in target_rows), default=None)
    available_scope_names = sorted({row.scope_name for row in rows})
    target_scope_names = sorted({row.scope_name for row in target_rows})
    fallback_scope_names = sorted({row.scope_name for row in fallback_rows})
    requested_target_scopes = [
        scope_name
        for scope_name in (project.city, project.district)
        if scope_name
    ]
    missing_target_scopes = [
        scope_name
        for scope_name in requested_target_scopes
        if scope_name not in target_scope_names
    ]
    coverage_status = (
        "target_ready"
        if target_rows
        else "fallback_only"
        if fallback_rows
        else "unavailable"
    )
    if coverage_status == "target_ready":
        scope_warning = (
            "已加载城市或区县官方统计。宏观统计仅作为区域背景，"
            "不能代表项目分析半径内的真实人口或客流。"
        )
    elif coverage_status == "fallback_only":
        fallback_text = "、".join(fallback_scope_names) or "上级行政区"
        missing_text = "、".join(missing_target_scopes) or "目标城市/区县"
        scope_warning = (
            f"当前仅加载{fallback_text}宏观统计；{missing_text}指标暂缺。"
            "不得将上级行政区数据描述为项目所在城市、区县或商圈数据。"
        )
    else:
        scope_warning = "尚无可用政府公开统计，不能生成城市或区县宏观结论。"
    sync = latest_sync_run(db, project.project_id)
    return {
        "project_id": project.project_id,
        "scope": {
            "city": project.city,
            "city_code": city_code,
            "district": project.district,
            "district_code": district_code,
        },
        "status": "ready" if rows else "collecting" if sync and sync.status in {"pending", "running"} else "unavailable",
        "macro_context": macro_context,
        "trade_area_context": trade_area_context,
        "lbs_context": {
            "available": False,
            "missing": ["1km居住人口", "工作人口", "小时客流", "客群画像"],
            "message": "暂未接入商业LBS数据，不使用城市宏观数据推算1km真实人口和客流。",
        },
        "data_quality": {
            "confirmed_metric_count": len(rows),
            "confirmed_target_metric_count": len(target_rows),
            "fallback_metric_count": len(fallback_rows),
            "missing_metrics": missing_metrics,
            "latest_period": latest_period,
            "latest_target_period": latest_target_period,
            "coverage_status": coverage_status,
            "available_scope_names": available_scope_names,
            "target_scope_names": target_scope_names,
            "fallback_scope_names": fallback_scope_names,
            "missing_target_scopes": missing_target_scopes,
            "scope_warning": scope_warning,
        },
        "sources": [
            {
                "source_name": source_name,
                "source_url": source_url,
                "stat_period": stat_period,
                "scope_name": scope_name,
            }
            for source_name, source_url, stat_period, scope_name in sources
        ],
        "latest_sync": sync_run_to_dict(sync),
    }


def review_records(db: Session, status: str = "pending_review") -> list[dict[str, Any]]:
    return [
        statistic_to_dict(row)
        for row in db.scalars(
            select(RegionalStatisticRecord)
            .where(RegionalStatisticRecord.status == status)
            .order_by(RegionalStatisticRecord.collected_at.desc(), RegionalStatisticRecord.id.desc())
        ).all()
    ]


def review_record(db: Session, record_id: int, status: str) -> dict[str, Any] | None:
    row = db.get(RegionalStatisticRecord, record_id)
    if not row:
        return None
    row.status = status
    db.commit()
    db.refresh(row)
    return statistic_to_dict(row)


def save_uploaded_statistics(db: Session, items: list[Any]) -> dict[str, int]:
    imported = 0
    pending = 0
    for item in items:
        row, _ = _upsert_statistic(db, item)
        imported += 1
        if row.status == "pending_review":
            pending += 1
    db.commit()
    return {"imported_count": imported, "pending_review_count": pending}
