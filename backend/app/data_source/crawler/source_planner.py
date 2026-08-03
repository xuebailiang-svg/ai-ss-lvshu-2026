from __future__ import annotations

import asyncio
import json
import re
from typing import Any
from urllib.parse import urlparse

from app.llm.client import DeepSeekClient
from app.models import SiteProjectRecord


SOURCE_CATALOG: dict[str, list[dict[str, Any]]] = {
    "competitor": [
        {"priority": 1, "source_type": "merchant_detail", "domains": ["dianping.com", "meituan.com"], "reason": "核验门店名称、价格和营业时间"},
        {"priority": 2, "source_type": "official_account", "domains": ["weixin.qq.com"], "reason": "补充开业、活动和设备配置线索"},
        {"priority": 3, "source_type": "map_or_review", "domains": ["amap.com", "baidu.com"], "reason": "交叉核对名称和地址，不单独采信泛内容页"},
    ],
    "supporting": [
        {"priority": 1, "source_type": "merchant_detail", "domains": ["dianping.com", "meituan.com"], "reason": "核验营业时间、评分和夜间经营线索"},
        {"priority": 2, "source_type": "official_account", "domains": ["weixin.qq.com"], "reason": "补充商户公告和营业安排"},
        {"priority": 3, "source_type": "map_detail", "domains": ["amap.com", "baidu.com"], "reason": "交叉核对名称和地址"},
    ],
    "rent": [
        {"priority": 1, "source_type": "property_listing", "domains": ["ke.com", "anjuke.com", "58.com"], "reason": "获取商铺面积、租金、楼层和发布时间"},
        {"priority": 2, "source_type": "local_property", "domains": [], "reason": "补充本地商业地产公开挂牌线索"},
        {"priority": 3, "source_type": "manual_url", "domains": [], "reason": "搜索受限时由用户提供具体挂牌页"},
    ],
}

MISSING_FIELDS = {
    "competitor": ["business_hours", "hour_price", "member_price", "machine_count", "area_sqm", "occupancy_rate"],
    "supporting": ["business_hours", "night_operation", "is_24_hours", "rating"],
    "rent": ["address", "area_sqm", "monthly_rent", "rent_per_sqm", "property_fee", "transfer_fee", "floor", "publish_date"],
}

SEARCH_FIELD_TERMS = {
    "business_hours": "营业时间",
    "hour_price": "价格",
    "member_price": "会员价",
    "machine_count": "机器配置 机位",
    "area_sqm": "面积",
    "occupancy_rate": "上座率",
    "night_operation": "夜间营业",
    "is_24_hours": "24小时",
    "rating": "评分",
    "address": "地址",
    "monthly_rent": "月租",
    "rent_per_sqm": "租金单价",
    "property_fee": "物业费",
    "transfer_fee": "转让费",
    "floor": "楼层",
    "publish_date": "发布时间",
}


def build_rule_search_queries(project: SiteProjectRecord, payload: dict[str, Any]) -> list[str]:
    city = project.city or ""
    district = project.district or ""
    project_address = project.address or ""
    name = str(payload.get("name") or "").strip()
    address = str(payload.get("address") or project_address or "").strip()
    task_type = str(payload.get("task_type") or "")
    location = " ".join(part for part in (city, district, address) if part).strip()
    target = " ".join(part for part in (location, name) if part).strip()
    missing_fields = payload.get("missing_fields") if isinstance(payload.get("missing_fields"), list) else MISSING_FIELDS.get(task_type, [])
    terms = [SEARCH_FIELD_TERMS[field] for field in missing_fields if field in SEARCH_FIELD_TERMS]
    if task_type == "competitor":
        grouped = [" ".join(terms[index:index + 2]) for index in range(0, len(terms), 2)] or ["门店详情"]
        return _dedupe([f"{target} {suffix}" for suffix in grouped])[:4]
    if task_type == "supporting":
        grouped = [" ".join(terms[index:index + 2]) for index in range(0, len(terms), 2)] or ["门店详情"]
        return _dedupe([f"{target} {suffix}" for suffix in grouped])[:3]
    if task_type == "rent":
        area = getattr(project, "expected_area_sqm", None) or ""
        area_text = f" {area:g}平" if isinstance(area, (int, float)) else ""
        field_terms = " ".join(terms[:4]) or "月租 面积"
        return _dedupe([f"{city} {district} {project_address} 商铺出租{area_text} {field_terms}", f"{city} {project_address} 商铺转让 {field_terms}"])
    return []


def build_rule_source_plan(project: SiteProjectRecord, payload: dict[str, Any]) -> dict[str, Any]:
    task_type = str(payload.get("task_type") or "")
    return {
        "mode": "rules",
        "task_type": task_type,
        "target_name": payload.get("name"),
        "target_address": payload.get("address") or project.address,
        "missing_fields": payload.get("missing_fields") if isinstance(payload.get("missing_fields"), list) else MISSING_FIELDS.get(task_type, []),
        "strategies": SOURCE_CATALOG.get(task_type, []),
        "search_queries": build_rule_search_queries(project, payload),
        "truth_boundary": "搜索词和来源类型可由AI建议；最终URL只能来自真实搜索结果或用户输入。",
    }


async def build_ai_source_plan(
    project: SiteProjectRecord,
    payload: dict[str, Any],
    *,
    client: DeepSeekClient | Any | None = None,
) -> dict[str, Any]:
    fallback = build_rule_source_plan(project, payload)
    llm = client or DeepSeekClient()
    prompt = (
        "你是电竞馆商业选址的数据源规划器。只返回JSON对象。"
        "你可以建议搜索词、来源类型和优先域名，但禁止编造具体网页URL。"
        "JSON字段必须为 search_queries(最多6条)、preferred_source_types、preferred_domains、reason。"
    )
    context = {
        "project": {"city": project.city, "district": project.district, "address": project.address, "business_type": project.business_type},
        "target": payload,
        "rule_plan": fallback,
    }
    try:
        result = await asyncio.to_thread(llm.generate_chat, context, prompt)
        parsed = _parse_json_object(result.content)
        queries = _clean_strings(parsed.get("search_queries"), maximum=6)
        domains = [item for item in _clean_strings(parsed.get("preferred_domains"), maximum=12) if _valid_domain(item)]
        base_queries = queries or fallback["search_queries"]
        domain_queries = [f"{query} site:{domain}" for domain in domains[:2] for query in base_queries[:2]]
        planned_queries = _dedupe([*domain_queries, *base_queries])[:6]
        return {
            **fallback,
            "mode": "ai_assisted",
            "search_queries": planned_queries,
            "preferred_source_types": _clean_strings(parsed.get("preferred_source_types"), maximum=8),
            "preferred_domains": domains,
            "reason": str(parsed.get("reason") or "AI结合业务目标补充了搜索策略"),
            "ai_model": getattr(result, "model", None),
        }
    except Exception as exc:
        return {**fallback, "mode": "rules_fallback", "ai_error": str(exc)}


async def rank_real_candidates(
    project: SiteProjectRecord,
    payload: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    client: DeepSeekClient | Any | None = None,
) -> dict[str, Any]:
    allowed = [str(item.get("url")) for item in candidates if item.get("url")]
    fallback = {"mode": "rules", "ordered_urls": allowed, "reasons": {}}
    if len(allowed) < 2:
        return fallback
    prompt = (
        "你是网页来源相关性审核器。只返回JSON对象，字段为 ordered_urls 和 reasons。"
        "ordered_urls只能从输入候选URL原样选择，禁止新增、改写或猜测URL。"
        "优先目标名称、地址和业务字段都匹配的详情页，排除百科、旅游、泛城市介绍。"
    )
    try:
        llm = client or DeepSeekClient()
        result = await asyncio.to_thread(
            llm.generate_chat,
            {"project": {"city": project.city, "district": project.district, "address": project.address}, "target": payload, "candidates": candidates},
            prompt,
        )
        parsed = _parse_json_object(result.content)
        ordered = [url for url in _clean_strings(parsed.get("ordered_urls"), maximum=len(allowed)) if url in allowed]
        ordered.extend(url for url in allowed if url not in ordered)
        raw_reasons = parsed.get("reasons") if isinstance(parsed.get("reasons"), dict) else {}
        return {"mode": "ai_assisted", "ordered_urls": ordered, "reasons": {url: str(raw_reasons.get(url) or "") for url in ordered}, "ai_model": getattr(result, "model", None)}
    except Exception as exc:
        return {**fallback, "mode": "rules_fallback", "ai_error": str(exc)}


def _parse_json_object(content: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(content or "").strip(), flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("AI source plan missing JSON object")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("AI source plan must be a JSON object")
    return value


def _clean_strings(value: Any, *, maximum: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return _dedupe([str(item).strip() for item in value if isinstance(item, str) and item.strip()])[:maximum]


def _valid_domain(value: str) -> bool:
    parsed = urlparse(value if "://" in value else f"https://{value}")
    return bool(parsed.netloc and " " not in parsed.netloc)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value.strip()))
