from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.data_source.crawler.base import crawler_settings
from app.data_source.crawler.crawl4ai_client import Crawl4AIClient
from app.data_source.crawler.search_discovery import (
    SearchDiscoveryClient,
    discover_urls_for_payload,
)
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
        "address": _text(markdown, r"(?:地址|位置)[：:\s]{0,4}([^\n，,。；;]{4,80})"),
        "monthly_rent": monthly,
        "area_sqm": area,
        "rent_per_sqm": unit,
        "property_fee": _num(markdown, r"(?:物业费)[^\d]{0,8}(\d+(?:\.\d+)?)"),
        "transfer_fee": _num(markdown, r"(?:转让费)[^\d]{0,8}(\d+(?:\.\d+)?)"),
        "floor": _text(markdown, r"(?:楼层)[：:\s]{0,4}([^\n，,。；;]{1,30})"),
        "publish_date": _text(markdown, r"(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)"),
        "source_url": url,
        "review_summary": markdown[:1000],
    }


def _has_value(data: dict[str, Any]) -> bool:
    return any(value not in (None, "", []) for key, value in data.items() if key not in {"source_url", "review_summary"})


def _text(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.I)
    if not match:
        return None
    return match.group(1).strip()


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


def _create_rent_from_crawler(db: Session, project_id: str, payload: dict[str, Any], detail: dict[str, Any]) -> bool:
    if not _has_value(detail):
        return False
    raw = {
        "crawler_detail": {key: value for key, value in detail.items() if value is not None},
        "search_query": payload.get("search_query"),
        "search_result": payload.get("search_result"),
        "source_url": detail.get("source_url") or payload.get("url"),
    }
    manual_detail = {
        key: detail.get(key)
        for key in ("property_fee", "transfer_fee", "floor", "publish_date", "source_url")
        if detail.get(key) is not None
    }
    if manual_detail:
        raw["manual_detail"] = manual_detail
    row = RentDataRecord(
        project_id=project_id,
        monthly_rent=detail.get("monthly_rent"),
        area_sqm=detail.get("area_sqm"),
        rent_per_sqm=detail.get("rent_per_sqm"),
        location_type=detail.get("address") or payload.get("address"),
        source="crawler",
        confidence=0.5,
        status="pending_review",
        raw_data=raw,
    )
    db.add(row)
    return True


def _create_competitor_from_crawler(db: Session, project_id: str, payload: dict[str, Any], detail: dict[str, Any]) -> bool:
    if not _has_value(detail):
        return False
    row = UnifiedCompetitorRecord(
        project_id=project_id,
        name=payload.get("name") or "公开网页竞品线索",
        address=payload.get("address"),
        area_sqm=detail.get("area_sqm"),
        machine_count=int(detail["machine_count"]) if detail.get("machine_count") is not None else None,
        hour_price=detail.get("hour_price"),
        member_price=detail.get("member_price"),
        occupancy_rate=detail.get("occupancy_rate"),
        source="crawler",
        confidence=0.6,
        status="pending_review",
        raw_data={
            "crawler_detail": {key: value for key, value in detail.items() if value is not None},
            "search_query": payload.get("search_query"),
            "search_result": payload.get("search_result"),
            "source_url": detail.get("source_url") or payload.get("url"),
        },
    )
    db.add(row)
    return True


def _create_supporting_from_crawler(db: Session, project_id: str, payload: dict[str, Any], detail: dict[str, Any]) -> bool:
    if not _has_value(detail):
        return False
    record_type = payload.get("record_type") or "food"
    raw_data = {
        "address": payload.get("address"),
        "crawler_detail": {key: value for key, value in detail.items() if value is not None},
        "manual_detail": {
            key: detail.get(key)
            for key in ("business_hours", "night_operation", "is_24_hours", "source_url")
            if detail.get(key) is not None
        },
        "search_query": payload.get("search_query"),
        "search_result": payload.get("search_result"),
        "source_url": detail.get("source_url") or payload.get("url"),
    }
    if record_type == "entertainment":
        row = EntertainmentRecord(
            project_id=project_id,
            name=payload.get("name") or "公开网页配套线索",
            type="crawler",
            business_hours=detail.get("business_hours"),
            night_business=detail.get("night_operation"),
            source="crawler",
            confidence=0.55,
            status="pending_review",
            raw_data=raw_data,
        )
    else:
        row = FoodBusinessRecord(
            project_id=project_id,
            name=payload.get("name") or "公开网页配套线索",
            category="crawler",
            business_hours=detail.get("business_hours"),
            night_business=detail.get("night_operation"),
            rating=detail.get("rating"),
            source="crawler",
            confidence=0.55,
            status="pending_review",
            raw_data=raw_data,
        )
    db.add(row)
    return True


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


def _project_rent_payload(project: SiteProjectRecord) -> dict[str, Any]:
    raw = project.raw_data if isinstance(project.raw_data, dict) else {}
    return {
        "task_type": "rent",
        "record_type": "project",
        "record_id": None,
        "name": f"{project.address or project.city}周边租金",
        "address": project.address,
        "url": None,
        "source": "project",
        "status": "pending_review",
        "expected_area_sqm": raw.get("expected_area_sqm"),
    }


def _load_candidates(db: Session, project: SiteProjectRecord, task_type: str, limit: int) -> list[dict[str, Any]]:
    project_id = project.project_id
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
        payloads = [_candidate_payload(row, "rent") for row in rows]
        if not payloads:
            payloads.append(_project_rent_payload(project))
        return payloads
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


def _skip_task(task: CrawlTaskRecord, payload: dict[str, Any], message: str) -> None:
    task.status = "skipped"
    task.error_message = message
    task.result_snapshot = {
        **(task.result_snapshot or {}),
        "search_queries": payload.get("search_queries") or [],
        "search_results": payload.get("search_results") or [],
        "discovered_url_count": len(payload.get("search_results") or []),
        "message": message,
    }
    task.finished_at = _now()


async def _run_existing_task(
    db: Session,
    task: CrawlTaskRecord,
    project: SiteProjectRecord,
    *,
    settings: Any,
    crawler: Crawl4AIClient,
    discovery_client: SearchDiscoveryClient,
) -> dict[str, Any]:
    payload = dict(task.input_snapshot or {})
    url = task.target_url or payload.get("url")
    discovered_url_count = 0
    task.status = "running"
    task.started_at = task.started_at or _now()
    db.flush()

    if not url and payload.get("discover_urls", True):
        discovered_payloads, queries, discovered_results, error_message = await discover_urls_for_payload(
            project,
            payload,
            settings=settings,
            client=discovery_client,
        )
        discovered_url_count = len(discovered_results)
        payload = {
            **payload,
            "discovery_attempted": True,
            "search_queries": queries,
            "search_results": discovered_results,
        }
        if not discovered_payloads:
            payload["discovery_error"] = error_message
            task.input_snapshot = payload
            _skip_task(task, payload, error_message or "未搜索到可访问的公开网页，建议人工补充或手动提供来源链接。")
            return {"status": "skipped", "saved": None, "discovered_url_count": discovered_url_count}
        selected_payload = discovered_payloads[0]
        payload = {
            **payload,
            **selected_payload,
            "search_queries": queries,
            "search_results": discovered_results,
        }
        url = selected_payload.get("url")
        task.target_url = url
        task.source_domain = _domain(url)
        task.input_snapshot = payload
        task.result_snapshot = {
            **(task.result_snapshot or {}),
            "search_queries": queries,
            "search_results": discovered_results,
            "discovered_url_count": discovered_url_count,
        }
    else:
        task.input_snapshot = payload

    ok, reason = _domain_allowed(url)
    if not ok:
        _skip_task(task, payload, reason or "缺少可访问的公开来源 URL")
        return {"status": "skipped", "saved": None, "discovered_url_count": discovered_url_count}

    try:
        page = await crawler.crawl(url, timeout_seconds=settings.timeout_seconds)
        markdown = page.markdown or ""
        if payload["task_type"] == "competitor":
            detail = _extract_competitor(markdown, url)
        elif payload["task_type"] == "supporting":
            detail = _extract_supporting(markdown, url)
        else:
            detail = _extract_rent(markdown, url)

        target = _get_target_row(db, task.project_id, payload)
        changed = False
        saved_type: str | None = None
        if target is not None:
            if payload["task_type"] == "competitor":
                changed = _apply_competitor(target, detail)
                saved_type = "competitors" if changed else None
            elif payload["task_type"] == "supporting":
                changed = _apply_supporting(target, detail)
                saved_type = "supporting" if changed else None
            else:
                changed = _apply_rent(target, detail)
                saved_type = "rent" if changed else None
        elif payload["task_type"] == "rent":
            changed = _create_rent_from_crawler(db, task.project_id, payload, detail)
            saved_type = "rent" if changed else None
        elif payload["task_type"] == "competitor":
            changed = _create_competitor_from_crawler(db, task.project_id, payload, detail)
            saved_type = "competitors" if changed else None
        elif payload["task_type"] == "supporting":
            changed = _create_supporting_from_crawler(db, task.project_id, payload, detail)
            saved_type = "supporting" if changed else None

        task.result_snapshot = {
            **(task.result_snapshot or {}),
            "url": url,
            "search_query": payload.get("search_query"),
            "search_result": payload.get("search_result"),
            "extracted": detail,
            "extracted_fields": {key: value for key, value in detail.items() if value not in (None, "", [])},
            "changed": changed,
        }
        task.status = "success" if changed else "partial"
        task.finished_at = _now()
        return {"status": task.status, "saved": saved_type, "discovered_url_count": discovered_url_count}
    except Exception as exc:
        task.status = "failed"
        task.error_message = str(exc)
        task.finished_at = _now()
        return {"status": "failed", "saved": None, "discovered_url_count": discovered_url_count}


async def _expand_payloads_with_discovery(
    project: SiteProjectRecord,
    payloads: list[dict[str, Any]],
    *,
    discover_urls: bool,
    settings: Any,
    discovery_client: SearchDiscoveryClient,
) -> tuple[list[dict[str, Any]], int]:
    expanded: list[dict[str, Any]] = []
    discovered_url_count = 0
    seen_task_keys: set[tuple[str, int | None, str | None]] = set()
    for payload in payloads:
        if payload.get("url") or not discover_urls:
            expanded.append(payload)
            continue
        discovered_payloads, queries, discovered_results, error_message = await discover_urls_for_payload(
            project,
            payload,
            settings=settings,
            client=discovery_client,
        )
        discovered_url_count += len(discovered_payloads)
        if not discovered_payloads:
            expanded.append(
                {
                    **payload,
                    "discovery_attempted": True,
                    "search_queries": queries,
                    "search_results": discovered_results,
                    "discovery_error": error_message,
                }
            )
            continue
        for discovered_payload in discovered_payloads:
            key = (
                str(discovered_payload.get("task_type")),
                discovered_payload.get("record_id"),
                discovered_payload.get("url"),
            )
            if key in seen_task_keys:
                continue
            seen_task_keys.add(key)
            expanded.append(discovered_payload)
    return expanded, discovered_url_count


async def enrich_project_with_crawler(
    db: Session,
    project_id: str,
    *,
    types: list[str],
    max_items: int,
    discover_urls: bool = True,
    client: Crawl4AIClient | None = None,
    discovery_client: SearchDiscoveryClient | None = None,
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
            "discovered_url_count": 0,
            "saved": {"competitors": 0, "supporting": 0, "rent": 0},
            "message": "爬虫能力未启用，请先在配置页启用",
        }

    allowed_types = [item for item in types if item in {"competitor", "supporting", "rent"}]
    per_type_limit = max(1, min(max_items, settings.max_tasks_per_project))
    payloads: list[dict[str, Any]] = []
    for task_type in allowed_types:
        payloads.extend(_load_candidates(db, project, task_type, per_type_limit))
    payloads, discovered_url_count = await _expand_payloads_with_discovery(
        project,
        payloads,
        discover_urls=discover_urls,
        settings=settings,
        discovery_client=discovery_client or SearchDiscoveryClient(),
    )
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
            task.error_message = payload.get("discovery_error") or reason
            if payload.get("discovery_attempted"):
                task.result_snapshot = {
                    "search_queries": payload.get("search_queries") or [],
                    "search_results": payload.get("search_results") or [],
                    "message": "未发现可抓取的公开网页",
                }
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
            elif payload["task_type"] == "rent":
                changed = _create_rent_from_crawler(db, project_id, payload, detail)
                saved["rent"] += 1 if changed else 0
            task.result_snapshot = {
                "url": url,
                "search_query": payload.get("search_query"),
                "search_result": payload.get("search_result"),
                "extracted": detail,
                "changed": changed,
            }
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
        "discovered_url_count": discovered_url_count,
        "saved": saved,
        "message": "爬虫补充完成，结果需要人工确认" if completed else "未发现可抓取的公开来源URL",
    }


def queue_project_crawler_tasks(
    db: Session,
    project_id: str,
    *,
    types: list[str],
    max_items: int,
    discover_urls: bool = True,
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
            "task_ids": [],
            "completed_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "discovered_url_count": 0,
            "saved": {"competitors": 0, "supporting": 0, "rent": 0},
            "message": "爬虫能力未启用，请先在配置页启用",
        }

    allowed_types = [item for item in types if item in {"competitor", "supporting", "rent"}]
    per_type_limit = max(1, min(max_items, settings.max_tasks_per_project))
    payloads: list[dict[str, Any]] = []
    for task_type in allowed_types:
        payloads.extend(_load_candidates(db, project, task_type, per_type_limit))
    payloads = payloads[: settings.max_tasks_per_project]

    task_ids: list[int] = []
    for payload in payloads:
        task = _create_task(project_id, {**payload, "discover_urls": discover_urls})
        db.add(task)
        db.flush()
        task_ids.append(task.id)
    db.commit()
    return {
        "success": bool(task_ids),
        "project_id": project_id,
        "task_count": len(task_ids),
        "task_ids": task_ids,
        "completed_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "discovered_url_count": 0,
        "saved": {"competitors": 0, "supporting": 0, "rent": 0},
        "message": "爬虫任务已创建，请稍后查看结果" if task_ids else "没有可用于爬虫补充的候选数据",
    }


def queue_manual_url_crawl_task(
    db: Session,
    project_id: str,
    *,
    task_type: str,
    name: str,
    address: str | None,
    url: str,
    record_type: str | None = None,
) -> dict[str, Any]:
    project = get_project(db, project_id)
    if not project:
        raise CrawlProjectNotFoundError("Project not found")
    settings = crawler_settings()
    if not settings.enabled:
        return {
            "success": False,
            "project_id": project_id,
            "task_count": 0,
            "task_ids": [],
            "completed_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "discovered_url_count": 0,
            "saved": {"competitors": 0, "supporting": 0, "rent": 0},
            "message": "爬虫能力未启用，请先在配置页启用",
        }
    payload = {
        "task_type": task_type,
        "record_type": record_type or ("food" if task_type == "supporting" else None),
        "record_id": None,
        "name": name,
        "address": address,
        "url": url,
        "source": "manual_url",
        "status": "pending_review",
        "discover_urls": False,
    }
    task = _create_task(project_id, payload)
    db.add(task)
    db.commit()
    return {
        "success": True,
        "project_id": project_id,
        "task_count": 1,
        "task_ids": [task.id],
        "completed_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "discovered_url_count": 0,
        "saved": {"competitors": 0, "supporting": 0, "rent": 0},
        "message": "手动 URL 爬虫任务已创建，请稍后查看结果",
    }


async def process_crawl_task_ids(task_ids: list[int]) -> None:
    if not task_ids:
        return
    settings = crawler_settings()
    crawler = Crawl4AIClient()
    discovery_client = SearchDiscoveryClient()
    with SessionLocal() as db:
        for task_id in task_ids:
            task = db.get(CrawlTaskRecord, task_id)
            if not task:
                continue
            project = get_project(db, task.project_id)
            if not project:
                task.status = "failed"
                task.error_message = "Project not found"
                task.finished_at = _now()
                db.commit()
                continue
            try:
                await _run_existing_task(
                    db,
                    task,
                    project,
                    settings=settings,
                    crawler=crawler,
                    discovery_client=discovery_client,
                )
            finally:
                db.commit()


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
