from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


METADATA_FIELDS = {"source_url", "review_summary", "field_evidence"}
FIELD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "business_hours": ("营业时间", "营业", "开放时间"),
    "hour_price": ("小时价", "上网价", "网费", "价格", "单价"),
    "member_price": ("会员价", "会员价格"),
    "machine_count": ("机器", "机位", "电脑"),
    "area_sqm": ("面积", "建筑面积"),
    "occupancy_rate": ("上座率", "满座率"),
    "night_operation": ("24小时", "通宵", "凌晨", "夜宵", "夜间"),
    "is_24_hours": ("24小时",),
    "rating": ("评分", "星级"),
    "address": ("地址", "位置"),
    "monthly_rent": ("月租", "租金"),
    "rent_per_sqm": ("元/㎡/月", "元/平/月", "单价"),
    "property_fee": ("物业费",),
    "transfer_fee": ("转让费",),
    "floor": ("楼层",),
    "publish_date": ("发布", "更新", "日期"),
}

HIGH_QUALITY_DOMAINS = ("gov.cn", "stats.gov.cn", "anjuke.com", "ke.com", "fang.com")
LOW_QUALITY_DOMAINS = ("baike.baidu.com", "zhihu.com", "zhuanlan.zhihu.com")


def source_quality_for_url(url: str) -> str:
    domain = (urlparse(url).netloc or "").lower()
    if any(domain == item or domain.endswith("." + item) for item in HIGH_QUALITY_DOMAINS):
        return "high"
    if any(domain == item or domain.endswith("." + item) for item in LOW_QUALITY_DOMAINS):
        return "low"
    return "medium"


def freshness_for_detail(detail: dict[str, Any]) -> str:
    value = detail.get("publish_date")
    if not value:
        return "unknown"
    match = re.search(r"(20\d{2})", str(value))
    if not match:
        return "unknown"
    age = datetime.now(timezone.utc).year - int(match.group(1))
    return "fresh" if age <= 1 else "aging" if age <= 3 else "stale"


def meaningful_fields(detail: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in detail.items() if key not in METADATA_FIELDS and value not in (None, "", [])}


def build_field_evidence(detail: dict[str, Any], markdown: str, url: str) -> list[dict[str, Any]]:
    lines = [_clean_line(line) for line in markdown.splitlines() if _clean_line(line)]
    evidence: list[dict[str, Any]] = []
    for field, value in meaningful_fields(detail).items():
        keywords = FIELD_KEYWORDS.get(field, ())
        excerpt = next((line for line in lines if any(keyword in line for keyword in keywords)), "")
        if not excerpt:
            value_text = str(value)
            excerpt = next((line for line in lines if value_text and value_text in line), "")
        method = "rule_extract"
        confidence = 0.75
        if not excerpt and field == "rent_per_sqm" and detail.get("monthly_rent") is not None and detail.get("area_sqm"):
            excerpt = f"由月租金 {detail['monthly_rent']} ÷ 面积 {detail['area_sqm']} 计算"
            method = "derived"
            confidence = 0.7
        if not excerpt:
            continue
        evidence.append({
            "field": field,
            "value": value,
            "source_url": url,
            "source_domain": (urlparse(url).netloc or "").lower(),
            "excerpt": excerpt[:280],
            "method": method,
            "confidence": confidence,
            "source_quality": source_quality_for_url(url),
            "freshness_status": freshness_for_detail(detail),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        })
    return evidence


def retain_evidenced_fields(detail: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    allowed = {str(item.get("field")) for item in evidence if item.get("field")}
    return {
        key: value
        for key, value in detail.items()
        if key in METADATA_FIELDS or key in allowed
    }


def crawler_suggestion_from_raw(raw_data: Any, status: str | None = None) -> dict[str, Any] | None:
    raw = raw_data if isinstance(raw_data, dict) else {}
    detail = raw.get("crawler_detail") if isinstance(raw.get("crawler_detail"), dict) else {}
    fields = meaningful_fields(detail)
    evidence = detail.get("field_evidence") if isinstance(detail.get("field_evidence"), list) else []
    source_url = detail.get("source_url") or raw.get("source_url")
    if not fields and not source_url and not evidence:
        return None
    return {
        "fields": fields,
        "source_url": source_url,
        "source_domain": (urlparse(source_url).netloc or "").lower() if source_url else None,
        "field_evidence": evidence,
        "review_status": status or "pending_review",
        "notice": "爬虫线索已随记录完成人工确认。" if status == "confirmed" else "爬虫线索尚未人工确认，不作为最终事实。",
    }


def _clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[#>*`]+", " ", value or "")).strip()
