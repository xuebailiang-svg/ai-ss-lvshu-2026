from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_source.crawler.base import crawler_settings
from app.data_source.crawler.crawl4ai_client import Crawl4AIClient
from app.models import (
    CrawlTaskRecord,
    EntertainmentRecord,
    FoodBusinessRecord,
    RentDataRecord,
    SiteProjectRecord,
    UnifiedCompetitorRecord,
)
from app.projects.service import get_project


class CrawlProjectNotFoundError(RuntimeError):
    pass


class CrawlTaskNotFoundError(RuntimeError):
    pass


def _now():
    return datetime.now(timezone.utc)


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    return (parsed.netloc or "").lower() or None


def _domain_allowed(url: str | None) -> tuple[bool, str | None]:
    domain = _domain(url)
    if not domain:
        return False, "缺少公开来源URL"
    settings = crawler_settings()
    if any(domain == item or domain.endswith("." + item) for item in settings.blocked_domains):
        return False, f"来源域名已被禁用：{domain}"
    if settings.allowed_domains and not any(
        domain == item or domain.endswith("." + item) for item in settings.allowed_domains
    ):
        return False, f"来源域名不在允许列表：{domain}"
    return True, None


def _source_url(raw: Any) -> str | None:
    data = raw if isinstance(raw, dict) else {}
    candidates = [
        data.get("source_url"),
        data.get("url"),
        data.get("detail_url"),
        data.get("shop_url"),
    ]
    for nested_key in ("manual_detail", "crawler_detail"):
        nested = data.get(nested_key)
        if isinstance(nested, dict):
            candidates.extend([nested.get("source_url"), nested.get("url")])
    for value in candidates:
        if isinstance(value, str) and value.strip().startswith(("http://", "https://")):
            return value.strip()
    return None


def _task_to_public(row: CrawlTaskRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "task_type": row.task_type,
        "target_name": row.target_name,
        "target_address": row.target_address,
        "target_url": row.target_url,
        "provider": row.provider,
        "status": row.status,
        "source_domain": row.source_domain,
        "error_message": row.error_message,
        "created_at": row.created_at,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
    }


def _task_detail(row: CrawlTaskRecord) -> dict[str, Any]:
    return {
        **_task_to_public(row),
        "input_snapshot": row.input_snapshot or {},
        "result_snapshot": row.result_snapshot or {},
    }


def _num(text: str, *patterns: str) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except (TypeError, ValueError):
                return None
    return None


def _hours(text: str) -> str | None:
    match = re.search(r"(\d{1,2}:\d{2}\s*[-~至]\s*\d{1,2}:\d{2})", text)
    return match.group(1).replace(" ", "") if match else None


def _extract_competitor(markdown: str, url: str) -> dict[str, Any]:
    return {
        "business_hours": _hours(markdown),
        "hour_price": _num(markdown, r"(?:小时价|时价|价格|单价)[^\d]{0,8}(\d+(?:\.\d+)?)"),
        "member_price": _num(markdown, r"(?:会员价|会员价格)[^\d]{0,8}(\d+(?:\.\d+)?)"),
        "machine_count": _num(markdown, r"(?:机器|机位|电脑)[^\d]{0,8}(\d{2,4})"),
        "area_sqm": _num(markdown, r"(?:面积)[^\d]{0,8}(\d+(?:\.\d+)?)"),
        "occupancy_rate": _num(markdown, r"(?:上座率|满座率)[^\d]{0,8}(\d+(?:\.\d+)?)%?"),
        "source_url": url,
        "review_summary": markdown[:1000],
    }


def _extract_supporting(markdown: str, url: str) -> dict[str, Any]:
    hours = _hours(markdown)
    night_operation = None
    if re.search(r"24小时|通宵|凌晨|夜宵", markdown):
        night_operation = True
    return {
        "business_hours": hours,
        "night_operation": night_operation,
        "is_24_hours": True if re.search(r"24小时", markdown) else None,
        "rating": _num(markdown, r"(?:评分|星级)[^\d]{0,8}(\d+(?:\.\d+)?)"),
        "source_url": url,
        "review_summary": markdown[:1000],
    }


def _extract_rent(markdown: str, url: str) -> dict[str, Any]:
    monthly = _num(markdown, r"(?:月租|租金)[^\d]{0,8}(\d+(?:\.\d+)?)")
    area = _num(markdown, r"(?:面积|建筑面积)[^\d]{0,8}(\d+(?:\.\d+)?)")
    unit = _num(markdown, r"(?:元/㎡/月|元/平/月|单价)[^\d]{0,8}(\d+(?:\.\d+)?)")
    if unit is None and monthly is not None and area:
        unit = round(monthly / area, 2)
    return {
        "monthly_rent": monthly,
        "area_sqm": area,
        "rent_per_sqm": unit,
        "source_url": url,
        "review_summary": markdown[:1000],
    }


def _has_value(data: dict[str, Any]) -> bool:
    return any(value not in (None, "", []) for key, value in data.items() if key not in {"source_url", "review_summary"})


def _merge_raw(row: Any, detail: dict[str, Any]) -> None:
    raw = dict(row.raw_data or {})
    existing = raw.get("crawler_detail") if isinstance(raw.get("crawler_detail"), dict) else {}
    raw["crawler_detail"] = {**existing, **{k: v for k, v in detail.items() if v is not None}}
    row.raw_data = raw


def _apply_competitor(row: UnifiedCompetitorRecord, detail: dict[str, Any]) -> bool:
    changed = False
    _merge_raw(row, detail)
    for field in ("area_sqm", "machine_count", "hour_price", "member_price", "occupancy_rate"):
        value = detail.get(field)
        if value is not None and getattr(row, field) is None:
            setattr(row, field, int(value) if field == "machine_count" else value)
            changed = True
    manual = dict((row.raw_data or {}).get("manual_detail") or {})
    if detail.get("business_hours") and not manual.get("business_hours"):
        manual["business_hours"] = detail["business_hours"]
        raw = dict(row.raw_data or {})
        raw["manual_detail"] = manual
        row.raw_data = raw
        changed = True
    return changed or _has_value(detail)


def _apply_supporting(row: Any, detail: dict[str, Any]) -> bool:
    changed = False
    _merge_raw(row, detail)
    if detail.get("business_hours") and not row.business_hours:
        row.business_hours = detail["business_hours"]
        changed = True
    if detail.get("night_operation") is not None and row.night_business is None:
        row.night_business = bool(detail["night_operation"])
        changed = True
    if hasattr(row, "rating") and detail.get("rating") is not None and row.rating is None:
        row.rating = detail["rating"]
        changed = True
    return changed or _has_value(detail)


def _apply_rent(row: RentDataRecord, detail: dict[str, Any]) -> bool:
    changed = False
    _merge_raw(row, detail)
    for field in ("monthly_rent", "area_sqm", "rent_per_sqm"):
        value = detail.get(field)
        if value is not None and getattr(row, field) is None:
            setattr(row, field, value)
            changed = True
    return changed or _has_value(detail)


def _candidate_payload(row: Any, task_type: str, record_type: str | None = None) -> dict[str, Any]:
    raw = row.raw_data if isinstance(row.raw_data, dict) else {}
    return {
        "task_type": task_type,
        "record_type": record_type,
        "record_id": row.id,
        "name": getattr(row, "name", None) or getattr(row, "location_type", None),
        "address": getattr(row, "address", None) or raw.get("address") or getattr(row, "location_type", None),
        "url": _source_url(raw),
        "source": getattr(row, "source", None),
        "status": getattr(row, "status", None),
    }


def _load_candidates(db: Session, project_id: str, task_type: str, limit: int) -> list[dict[str, Any]]:
    statuses = ("pending_review", "confirmed")
    if task_type == "competitor":
        rows = db.scalars(
            select(UnifiedCompetitorRecord)
            .where(UnifiedCompetitorRecord.project_id == project_id, UnifiedCompetitorRecord.status.in_(statuses))
            .order_by(UnifiedCompetitorRecord.distance_meters.asc(), UnifiedCompetitorRecord.id.asc())
            .limit(limit)
        ).all()
        return [_candidate_payload(row, "competitor") for row in rows]
    if task_type == "supporting":
        food_rows = db.scalars(
            select(FoodBusinessRecord)
            .where(FoodBusinessRecord.project_id == project_id, FoodBusinessRecord.status.in_(statuses))
            .order_by(FoodBusinessRecord.distance_meters.asc(), FoodBusinessRecord.id.asc())
            .limit(limit)
        ).all()
        remaining = max(0, limit - len(food_rows))
        entertainment_rows = db.scalars(
            select(EntertainmentRecord)
            .where(EntertainmentRecord.project_id == project_id, EntertainmentRecord.status.in_(statuses))
            .order_by(EntertainmentRecord.distance_meters.asc(), EntertainmentRecord.id.asc())
            .limit(remaining)
        ).all()
        return [
            *[_candidate_payload(row, "supporting", "food") for row in food_rows],
            *[_candidate_payload(row, "supporting", "entertainment") for row in entertainment_rows],
        ]
    if task_type == "rent":
        rows = db.scalars(
            select(RentDataRecord)
            .where(RentDataRecord.project_id == project_id, RentDataRecord.status.in_(statuses))
            .order_by(RentDataRecord.timestamp.desc(), RentDataRecord.id.desc())
            .limit(limit)
        ).all()
        return [_candidate_payload(row, "rent") for row in rows]
    return []


def _get_target_row(db: Session, project_id: str, payload: dict[str, Any]) -> Any | None:
    record_id = payload.get("record_id")
    if payload["task_type"] == "competitor":
        return db.scalar(select(UnifiedCompetitorRecord).where(UnifiedCompetitorRecord.project_id == project_id, UnifiedCompetitorRecord.id == record_id))
    if payload["task_type"] == "rent":
        return db.scalar(select(RentDataRecord).where(RentDataRecord.project_id == project_id, RentDataRecord.id == record_id))
    if payload["task_type"] == "supporting" and payload.get("record_type") == "food":
        return db.scalar(select(FoodBusinessRecord).where(FoodBusinessRecord.project_id == project_id, FoodBusinessRecord.id == record_id))
    if payload["task_type"] == "supporting" and payload.get("record_type") == "entertainment":
        return db.scalar(select(EntertainmentRecord).where(EntertainmentRecord.project_id == project_id, EntertainmentRecord.id == record_id))
    return None


def _create_task(project_id: str, payload: dict[str, Any]) -> CrawlTaskRecord:
    url = payload.get("url")
    return CrawlTaskRecord(
        project_id=project_id,
        task_type=payload["task_type"],
        target_name=payload.get("name"),
        target_address=payload.get("address"),
        target_url=url,
        provider="crawl4ai",
        status="pending",
        source_domain=_domain(url),
        input_snapshot=payload,
        result_snapshot={},
        created_at=_now(),
    )


async def enrich_project_with_crawler(
    db: Session,
    project_id: str,
    *,
    types: list[str],
    max_items: int,
    client: Crawl4AIClient | None = None,
) -> dict[str, Any]:
    project: SiteProjectRecord | None = get_project(db, project_id)
    if not project:
        raise CrawlProjectNotFoundError("Project not found")
    settings = crawler_settings()
    if not settings.enabled:
        return {
            "success": False,
            "project_id": project_id,
            "task_count": 0,
            "completed_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "saved": {"competitors": 0, "supporting": 0, "rent": 0},
            "message": "爬虫能力未启用，请先在配置页启用",
        }

    allowed_types = [item for item in types if item in {"competitor", "supporting", "rent"}]
    per_type_limit = max(1, min(max_items, settings.max_tasks_per_project))
    payloads: list[dict[str, Any]] = []
    for task_type in allowed_types:
        payloads.extend(_load_candidates(db, project_id, task_type, per_type_limit))
    payloads = payloads[: settings.max_tasks_per_project]

    crawler = client or Crawl4AIClient()
    saved = {"competitors": 0, "supporting": 0, "rent": 0}
    completed = failed = skipped = 0

    for payload in payloads:
        task = _create_task(project_id, payload)
        db.add(task)
        db.flush()
        url = payload.get("url")
        ok, reason = _domain_allowed(url)
        if not ok:
            task.status = "skipped"
            task.error_message = reason
            task.finished_at = _now()
            skipped += 1
            continue
        task.status = "running"
        task.started_at = _now()
        try:
            page = await crawler.crawl(url, timeout_seconds=settings.timeout_seconds)
            markdown = page.markdown or ""
            if payload["task_type"] == "competitor":
                detail = _extract_competitor(markdown, url)
            elif payload["task_type"] == "supporting":
                detail = _extract_supporting(markdown, url)
            else:
                detail = _extract_rent(markdown, url)
            target = _get_target_row(db, project_id, payload)
            changed = False
            if target is not None:
                if payload["task_type"] == "competitor":
                    changed = _apply_competitor(target, detail)
                    saved["competitors"] += 1 if changed else 0
                elif payload["task_type"] == "supporting":
                    changed = _apply_supporting(target, detail)
                    saved["supporting"] += 1 if changed else 0
                else:
                    changed = _apply_rent(target, detail)
                    saved["rent"] += 1 if changed else 0
            task.result_snapshot = {"url": url, "extracted": detail, "changed": changed}
            task.status = "success" if changed else "partial"
            task.finished_at = _now()
            completed += 1
        except Exception as exc:
            task.status = "failed"
            task.error_message = str(exc)
            task.finished_at = _now()
            failed += 1
    db.commit()
    return {
        "success": completed > 0 or skipped > 0,
        "project_id": project_id,
        "task_count": len(payloads),
        "completed_count": completed,
        "failed_count": failed,
        "skipped_count": skipped,
        "saved": saved,
        "message": "爬虫补充完成，结果需要人工确认" if completed else "未发现可抓取的公开来源URL",
    }


def list_crawl_tasks(db: Session, project_id: str) -> dict[str, Any]:
    if not get_project(db, project_id):
        raise CrawlProjectNotFoundError("Project not found")
    rows = db.scalars(
        select(CrawlTaskRecord)
        .where(CrawlTaskRecord.project_id == project_id)
        .order_by(CrawlTaskRecord.created_at.desc(), CrawlTaskRecord.id.desc())
    ).all()
    return {"items": [_task_to_public(row) for row in rows], "total": len(rows)}


def get_crawl_task(db: Session, project_id: str, task_id: int) -> dict[str, Any]:
    if not get_project(db, project_id):
        raise CrawlProjectNotFoundError("Project not found")
    row = db.scalar(
        select(CrawlTaskRecord).where(CrawlTaskRecord.project_id == project_id, CrawlTaskRecord.id == task_id)
    )
    if not row:
        raise CrawlTaskNotFoundError("Crawl task not found")
    return _task_detail(row)
