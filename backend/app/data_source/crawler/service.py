from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.data_source.crawler.base import crawler_settings
from app.data_source.crawler.adapters import extract_structured_fields
from app.data_source.crawler.crawl4ai_client import Crawl4AIClient
from app.data_source.crawler.evidence import build_field_evidence, meaningful_fields, retain_evidenced_fields
from app.data_source.crawler.search_discovery import (
    SearchDiscoveryClient,
    discover_urls_for_payload,
    page_matches_target,
)
from app.data_source.crawler.source_planner import build_ai_source_plan, build_rule_source_plan, rank_real_candidates
from app.data_source.crawler.review_service import persist_task_suggestions
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


def _friendly_crawl_error(exc: Exception) -> str:
    message = str(exc)
    if "Executable doesn't exist" in message or "playwright install" in message:
        return "Playwright Chromium 未安装，请重新执行独立爬虫安装脚本：scripts/crawler/install.sh"
    if "Timeout" in message or "timeout" in message:
        return "公开网页抓取超时，请稍后重试或换用更具体的详情页 URL。"
    if "net::ERR_NAME_NOT_RESOLVED" in message:
        return "公开网页域名无法解析，请检查 URL 是否正确。"
    if "net::ERR_CONNECTION" in message:
        return "公开网页暂时无法连接，请稍后重试或人工补充。"
    return message


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
    input_snapshot = row.input_snapshot if isinstance(row.input_snapshot, dict) else {}
    result_snapshot = row.result_snapshot if isinstance(row.result_snapshot, dict) else {}
    extracted_fields = result_snapshot.get("extracted_fields") if isinstance(result_snapshot.get("extracted_fields"), dict) else {}
    field_evidence = result_snapshot.get("field_evidence") if isinstance(result_snapshot.get("field_evidence"), list) else []
    candidate_attempts = result_snapshot.get("candidate_attempts") if isinstance(result_snapshot.get("candidate_attempts"), list) else []
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
        "planning_mode": input_snapshot.get("planning_mode") or "rules",
        "extracted_fields": extracted_fields,
        "evidence_count": len(field_evidence),
        "attempt_count": len(candidate_attempts),
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


def _bounded(value: float | None, minimum: float, maximum: float) -> float | None:
    if value is None or value < minimum or value > maximum:
        return None
    return value


def _hours(text: str) -> str | None:
    match = re.search(r"(\d{1,2}:\d{2}\s*[-~至]\s*\d{1,2}:\d{2})", text)
    return match.group(1).replace(" ", "") if match else None


def _extract_competitor(markdown: str, url: str) -> dict[str, Any]:
    occupancy_rate = _bounded(
        _num(markdown, r"(?:上座率|满座率)[^\d]{0,8}(\d+(?:\.\d+)?)%?"),
        0,
        100,
    )
    if occupancy_rate is not None and occupancy_rate > 1:
        occupancy_rate = round(occupancy_rate / 100, 4)
    return {
        "business_hours": _hours(markdown),
        "hour_price": _bounded(
            _num(markdown, r"(?:小时价|上网价|网费|时价|价格|单价)[^\d]{0,8}(\d+(?:\.\d+)?)"),
            1,
            200,
        ),
        "member_price": _bounded(
            _num(markdown, r"(?:会员价|会员价格)[^\d]{0,8}(\d+(?:\.\d+)?)"),
            1,
            200,
        ),
        "machine_count": _bounded(
            _num(markdown, r"(?:机器|机位|电脑)[^\d]{0,8}(\d{2,4})"),
            10,
            3000,
        ),
        "area_sqm": _bounded(
            _num(markdown, r"(?:面积)[^\d]{0,8}(\d+(?:\.\d+)?)"),
            20,
            5000,
        ),
        "occupancy_rate": occupancy_rate,
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
        "rating": _bounded(
            _num(markdown, r"(?:评分|星级)[^\d]{0,8}(\d+(?:\.\d+)?)"),
            0,
            5,
        ),
        "source_url": url,
        "review_summary": markdown[:1000],
    }


def _extract_rent(markdown: str, url: str) -> dict[str, Any]:
    monthly = _bounded(
        _num(markdown, r"(?:月租|租金)[^\d]{0,8}(\d+(?:\.\d+)?)"),
        100,
        10_000_000,
    )
    area = _bounded(
        _num(markdown, r"(?:面积|建筑面积)[^\d]{0,8}(\d+(?:\.\d+)?)"),
        5,
        100_000,
    )
    unit = _bounded(
        _num(markdown, r"(?:元/㎡/月|元/平/月|单价)[^\d]{0,8}(\d+(?:\.\d+)?)"),
        0.1,
        10_000,
    )
    if unit is None and monthly is not None and area:
        unit = round(monthly / area, 2)
    return {
        "address": _text(markdown, r"(?:地址|位置)[：:\s]{0,4}([^\n，,。；;]{4,80})"),
        "monthly_rent": monthly,
        "area_sqm": area,
        "rent_per_sqm": unit,
        "property_fee": _bounded(
            _num(markdown, r"(?:物业费)[^\d]{0,8}(\d+(?:\.\d+)?)"),
            0,
            1_000_000,
        ),
        "transfer_fee": _bounded(
            _num(markdown, r"(?:转让费)[^\d]{0,8}(\d+(?:\.\d+)?)"),
            0,
            100_000_000,
        ),
        "floor": _text(markdown, r"(?:楼层)[：:\s]{0,4}([^\n，,。；;]{1,30})"),
        "publish_date": _text(markdown, r"(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)"),
        "source_url": url,
        "review_summary": markdown[:1000],
    }


def _has_value(data: dict[str, Any]) -> bool:
    return bool(meaningful_fields(data))


def _meaningful_fields(data: dict[str, Any]) -> dict[str, Any]:
    return meaningful_fields(data)


def _detail_is_sufficient(
    task_type: str,
    detail: dict[str, Any],
    *,
    target_exists: bool,
) -> tuple[bool, str | None]:
    fields = _meaningful_fields(detail)
    if not fields:
        return False, "页面可访问，但未识别到可用业务字段，请换用更具体的详情页或人工补充。"
    if task_type == "rent" and not target_exists:
        if detail.get("monthly_rent") is None or detail.get("area_sqm") is None:
            return False, "租金网页缺少月租金或面积，未创建租金记录。"
    return True, None


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
    if row.status == "confirmed":
        # 已确认记录只保存爬虫建议；必须经过字段审核后才能改动正式字段。
        return _has_value(detail)
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
    if row.status == "confirmed":
        return _has_value(detail)
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
    if row.status == "confirmed":
        return _has_value(detail)
    for field in ("monthly_rent", "area_sqm", "rent_per_sqm"):
        value = detail.get(field)
        if value is not None and getattr(row, field) is None:
            setattr(row, field, value)
            changed = True
    return changed or _has_value(detail)


def _create_rent_from_crawler(db: Session, project_id: str, payload: dict[str, Any], detail: dict[str, Any]) -> bool:
    if detail.get("monthly_rent") is None or detail.get("area_sqm") is None:
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
    manual = raw.get("manual_detail") if isinstance(raw.get("manual_detail"), dict) else {}
    if task_type == "competitor":
        current = {
            "business_hours": manual.get("business_hours"),
            "hour_price": getattr(row, "hour_price", None),
            "member_price": getattr(row, "member_price", None),
            "machine_count": getattr(row, "machine_count", None),
            "area_sqm": getattr(row, "area_sqm", None),
            "occupancy_rate": getattr(row, "occupancy_rate", None),
        }
    elif task_type == "supporting":
        current = {
            "business_hours": getattr(row, "business_hours", None) or manual.get("business_hours"),
            "night_operation": getattr(row, "night_business", None) if getattr(row, "night_business", None) is not None else manual.get("night_operation"),
            "is_24_hours": manual.get("is_24_hours"),
            "rating": getattr(row, "rating", None),
        }
    else:
        current = {
            "address": getattr(row, "location_type", None) or raw.get("address"),
            "area_sqm": getattr(row, "area_sqm", None),
            "monthly_rent": getattr(row, "monthly_rent", None),
            "rent_per_sqm": getattr(row, "rent_per_sqm", None),
            "property_fee": manual.get("property_fee") or raw.get("property_fee"),
            "transfer_fee": manual.get("transfer_fee") or raw.get("transfer_fee"),
            "floor": manual.get("floor"),
            "publish_date": manual.get("publish_date"),
        }
    return {
        "task_type": task_type,
        "record_type": record_type,
        "record_id": row.id,
        "name": getattr(row, "name", None) or getattr(row, "location_type", None),
        "address": getattr(row, "address", None) or raw.get("address") or getattr(row, "location_type", None),
        "url": _source_url(raw),
        "source": getattr(row, "source", None),
        "status": getattr(row, "status", None),
        "missing_fields": [key for key, value in current.items() if value in (None, "")],
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
        "missing_fields": ["address", "area_sqm", "monthly_rent", "rent_per_sqm", "property_fee", "transfer_fee", "floor", "publish_date"],
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


def _latest_created_target(db: Session, project_id: str, payload: dict[str, Any]) -> Any | None:
    if payload["task_type"] == "competitor":
        return db.scalar(select(UnifiedCompetitorRecord).where(
            UnifiedCompetitorRecord.project_id == project_id,
            UnifiedCompetitorRecord.source == "crawler",
        ).order_by(UnifiedCompetitorRecord.id.desc()))
    if payload["task_type"] == "rent":
        return db.scalar(select(RentDataRecord).where(
            RentDataRecord.project_id == project_id,
            RentDataRecord.source == "crawler",
        ).order_by(RentDataRecord.id.desc()))
    model = EntertainmentRecord if payload.get("record_type") == "entertainment" else FoodBusinessRecord
    return db.scalar(select(model).where(model.project_id == project_id, model.source == "crawler").order_by(model.id.desc()))


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
        "search_errors": payload.get("search_errors") or [],
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
    candidate_payloads: list[dict[str, Any]] = [{**payload, "url": url}] if url else []
    task.status = "running"
    task.started_at = task.started_at or _now()
    db.flush()

    if not url and payload.get("discover_urls", True):
        rule_plan = build_rule_source_plan(project, payload)
        planning_mode = str(payload.get("planning_mode") or "rules")
        source_plan = rule_plan
        if planning_mode == "ai_assisted":
            source_plan = await build_ai_source_plan(project, payload)
        queries_for_search = source_plan.get("search_queries") or rule_plan["search_queries"]
        payload["source_plan"] = source_plan
        discovered_payloads, queries, discovered_results, error_message, search_errors = await discover_urls_for_payload(
            project,
            payload,
            settings=settings,
            client=discovery_client,
            queries=queries_for_search,
        )
        discovered_url_count = len(discovered_results)
        payload = {
            **payload,
            "discovery_attempted": True,
            "search_queries": queries,
            "search_results": discovered_results,
            "search_errors": search_errors,
        }
        if not discovered_payloads:
            payload["discovery_error"] = error_message
            task.input_snapshot = payload
            _skip_task(task, payload, error_message or "未搜索到可访问的公开网页，建议人工补充或手动提供来源链接。")
            return {"status": "skipped", "saved": None, "discovered_url_count": discovered_url_count}
        ranking = {"mode": "rules", "ordered_urls": [item.get("url") for item in discovered_payloads]}
        if planning_mode == "ai_assisted" and len(discovered_payloads) > 1:
            ranking = await rank_real_candidates(
                project,
                payload,
                [item.get("search_result") or {"url": item.get("url")} for item in discovered_payloads],
            )
            order = {url: index for index, url in enumerate(ranking.get("ordered_urls") or [])}
            discovered_payloads.sort(key=lambda item: order.get(item.get("url"), len(order)))
        payload = {
            **payload,
            "search_queries": queries,
            "search_results": discovered_results,
            "search_errors": search_errors,
            "source_plan": source_plan,
            "ai_ranking": ranking,
        }
        candidate_payloads = discovered_payloads[: max(1, settings.max_pages_per_task)]
        task.input_snapshot = payload
        task.result_snapshot = {
            **(task.result_snapshot or {}),
            "search_queries": queries,
            "search_results": discovered_results,
            "search_errors": search_errors,
            "discovered_url_count": discovered_url_count,
            "source_plan": source_plan,
            "ai_ranking": ranking,
        }
    else:
        task.input_snapshot = payload

    attempts: list[dict[str, Any]] = []
    merged_detail: dict[str, Any] = {}
    merged_evidence: list[dict[str, Any]] = []
    field_conflicts: list[dict[str, Any]] = []
    adapters_used: set[str] = set()
    accepted_payload: dict[str, Any] | None = None
    target = _get_target_row(db, task.project_id, payload)

    for candidate in candidate_payloads[: max(1, settings.max_pages_per_task)]:
        candidate_url = candidate.get("url")
        ok, reason = _domain_allowed(candidate_url)
        if not ok:
            attempts.append({"url": candidate_url, "status": "blocked", "message": reason})
            continue
        try:
            page = await crawler.crawl(candidate_url, timeout_seconds=settings.timeout_seconds)
            markdown = page.markdown or ""
        except Exception as exc:
            attempts.append({"url": candidate_url, "status": "failed", "message": _friendly_crawl_error(exc)})
            continue

        candidate_context = {**payload, **candidate}
        page_relevant, relevance_reasons = page_matches_target(candidate_context, markdown)
        if not page_relevant:
            attempts.append({"url": candidate_url, "status": "irrelevant", "message": "；".join(relevance_reasons)})
            continue

        if payload["task_type"] == "competitor":
            extracted = _extract_competitor(markdown, candidate_url)
        elif payload["task_type"] == "supporting":
            extracted = _extract_supporting(markdown, candidate_url)
        else:
            extracted = _extract_rent(markdown, candidate_url)
        structured, adapter_names = extract_structured_fields(
            payload["task_type"], candidate_url, getattr(page, "html", None)
        )
        adapters_used.update(adapter_names)
        extracted = {**extracted, **{key: value for key, value in structured.items() if value not in (None, "", [])}}
        evidence = build_field_evidence(extracted, markdown, candidate_url)
        detail = retain_evidenced_fields(extracted, evidence)
        detail["field_evidence"] = evidence
        sufficient, insufficient_reason = _detail_is_sufficient(payload["task_type"], detail, target_exists=target is not None)
        if not sufficient:
            attempts.append({"url": candidate_url, "status": "insufficient", "message": insufficient_reason, "extracted_fields": list(_meaningful_fields(detail))})
            continue

        accepted_payload = accepted_payload or candidate
        attempts.append({"url": candidate_url, "status": "accepted", "extracted_fields": list(_meaningful_fields(detail)), "evidence_count": len(evidence)})
        if payload["task_type"] == "rent":
            # 一个租金样本的面积和月租必须来自同一挂牌页，禁止跨房源拼接。
            merged_detail = detail
            merged_evidence = evidence
            break
        existing_fields = set(_meaningful_fields(merged_detail))
        for field, value in _meaningful_fields(detail).items():
            if field not in existing_fields:
                merged_detail[field] = value
                merged_evidence.extend(item for item in evidence if item.get("field") == field)
            elif merged_detail.get(field) != value:
                field_conflicts.append({
                    "field": field,
                    "kept_value": merged_detail.get(field),
                    "conflicting_value": value,
                    "source_url": candidate_url,
                })
        merged_detail.setdefault("source_url", candidate_url)
        merged_detail.setdefault("review_summary", extracted.get("review_summary"))

    if not accepted_payload or not _meaningful_fields(merged_detail):
        message = "候选网页均未通过相关性和字段证据校验，未识别到可用业务字段，未写入业务数据。"
        task.result_snapshot = {
            **(task.result_snapshot or {}),
            "candidate_attempts": attempts,
            "extracted_fields": {},
            "field_evidence": [],
            "field_conflicts": field_conflicts,
            "changed": False,
            "message": message,
        }
        task.status = "failed" if attempts and all(item.get("status") == "failed" for item in attempts) else "skipped"
        task.error_message = message
        task.finished_at = _now()
        return {"status": task.status, "saved": None, "discovered_url_count": discovered_url_count}

    merged_detail["field_evidence"] = merged_evidence
    payload = {**payload, **accepted_payload}
    url = accepted_payload.get("url")
    task.target_url = url
    task.source_domain = _domain(url)
    task.input_snapshot = payload

    changed = False
    saved_type: str | None = None
    if target is not None:
        if payload["task_type"] == "competitor":
            changed = _apply_competitor(target, merged_detail)
            saved_type = "competitors" if changed else None
        elif payload["task_type"] == "supporting":
            changed = _apply_supporting(target, merged_detail)
            saved_type = "supporting" if changed else None
        else:
            changed = _apply_rent(target, merged_detail)
            saved_type = "rent" if changed else None
    elif payload["task_type"] == "rent":
        changed = _create_rent_from_crawler(db, task.project_id, payload, merged_detail)
        saved_type = "rent" if changed else None
    elif payload["task_type"] == "competitor":
        changed = _create_competitor_from_crawler(db, task.project_id, payload, merged_detail)
        saved_type = "competitors" if changed else None
    elif payload["task_type"] == "supporting":
        changed = _create_supporting_from_crawler(db, task.project_id, payload, merged_detail)
        saved_type = "supporting" if changed else None

    db.flush()
    suggestion_target = target or (_latest_created_target(db, task.project_id, payload) if changed else None)
    suggestion_count = persist_task_suggestions(
        db, task, payload, merged_detail, merged_evidence, suggestion_target
    )

    task.result_snapshot = {
        **(task.result_snapshot or {}),
        "url": url,
        "candidate_attempts": attempts,
        "extracted": merged_detail,
        "extracted_fields": _meaningful_fields(merged_detail),
        "field_evidence": merged_evidence,
        "field_conflicts": field_conflicts,
        "adapters_used": sorted(adapters_used),
        "suggestion_count": suggestion_count,
        "changed": changed,
    }
    task.status = "success" if changed else "skipped"
    if not changed:
        task.error_message = "候选页面通过校验，但没有可写入的新字段，未修改现有数据。"
        task.result_snapshot["message"] = task.error_message
    task.finished_at = _now()
    return {"status": task.status, "saved": saved_type, "discovered_url_count": discovered_url_count}


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
        discovered_payloads, queries, discovered_results, error_message, search_errors = await discover_urls_for_payload(
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
                    "search_errors": search_errors,
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
            "message": "爬虫能力未启用，请先安装独立爬虫服务并在配置页启用",
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
                    "search_errors": payload.get("search_errors") or [],
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
                "extracted_fields": _meaningful_fields(detail),
                "changed": changed,
            }
            task.status = "success" if changed else "partial"
            if not changed:
                task.error_message = "页面可访问，但未识别到可用字段，请换用更具体的详情页或人工补充。"
                task.result_snapshot["message"] = task.error_message
            task.finished_at = _now()
            completed += 1
        except Exception as exc:
            task.status = "failed"
            task.error_message = _friendly_crawl_error(exc)
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
    planning_mode: str = "rules",
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
        task = _create_task(project_id, {**payload, "discover_urls": discover_urls, "planning_mode": planning_mode})
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
        "message": "爬虫任务已创建，独立 Worker 将在后台处理" if task_ids else "没有可用于爬虫补充的候选数据",
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
            "message": "爬虫能力未启用，请先安装独立爬虫服务并在配置页启用",
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
        "message": "手动 URL 爬虫任务已创建，独立 Worker 将在后台处理",
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
