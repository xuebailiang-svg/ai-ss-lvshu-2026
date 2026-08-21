from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    EntertainmentRecord,
    FoodBusinessRecord,
    RentDataRecord,
    SiteProjectRecord,
    SupplementRecord,
    UnifiedCompetitorRecord,
    UnifiedPOIRecord,
)


AMAP_READY_STATUSES = {"success", "success_zero", "partial", "truncated", "legacy_success"}


def _item(
    item_id: str,
    label: str,
    category: str,
    status: str,
    weight: int,
    earned: float,
    summary: str,
    action: str | None = None,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "label": label,
        "category": category,
        "status": status,
        "weight": weight,
        "earned": round(earned, 1),
        "summary": summary,
        "action": action,
    }


def _count(db: Session, model: Any, project_id: str) -> int:
    return int(db.scalar(select(func.count()).select_from(model).where(model.project_id == project_id)) or 0)


def _unknown_fields(row: Any) -> set[str]:
    raw = row.raw_data if isinstance(getattr(row, "raw_data", None), dict) else {}
    meta = raw.get("_manual_meta") if isinstance(raw.get("_manual_meta"), dict) else {}
    return set(meta.get("unknown_fields") or [])


def _amap_state(db: Session, project: SiteProjectRecord) -> dict[str, Any]:
    raw = project.raw_data if isinstance(project.raw_data, dict) else {}
    state = raw.get("_amap_collection")
    if isinstance(state, dict) and state.get("status"):
        return dict(state)
    amap_pois = int(
        db.scalar(
            select(func.count()).select_from(UnifiedPOIRecord).where(
                UnifiedPOIRecord.project_id == project.project_id,
                UnifiedPOIRecord.source == "amap",
            )
        )
        or 0
    )
    if amap_pois:
        return {
            "status": "legacy_success",
            "collected_at": None,
            "poi_count": amap_pois,
            "message": "检测到升级前已保存的高德 POI",
        }
    return {"status": "not_started", "collected_at": None, "poi_count": 0, "message": "尚未执行高德采集"}


def _competitor_item(db: Session, project_id: str, amap_ready: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    competitors = list(
        db.scalars(
            select(UnifiedCompetitorRecord).where(
                UnifiedCompetitorRecord.project_id == project_id,
                UnifiedCompetitorRecord.status != "rejected",
            ).order_by(UnifiedCompetitorRecord.distance_meters.asc().nullslast(), UnifiedCompetitorRecord.id.asc())
        ).all()
    )
    poi_candidates = int(
        db.scalar(
            select(func.count()).select_from(UnifiedPOIRecord).where(
                UnifiedPOIRecord.project_id == project_id,
                UnifiedPOIRecord.category == "competitor",
            )
        )
        or 0
    )
    if competitors:
        inventory = _item(
            "competitor_inventory", "疑似竞品清单", "key", "complete", 15, 15,
            f"已有 {len(competitors)} 家未排除的疑似竞品。",
        )
    elif poi_candidates:
        inventory = _item(
            "competitor_inventory", "疑似竞品清单", "key", "missing", 15, 0,
            f"高德 POI 中发现 {poi_candidates} 个竞品候选，但尚未整理成竞品清单。",
            "进入人工补充页整理疑似竞品",
        )
    elif amap_ready:
        inventory = _item(
            "competitor_inventory", "疑似竞品清单", "key", "complete", 15, 15,
            "本次高德采集未发现疑似竞品；这是零结果事实，不代表市场中绝对没有竞品。",
        )
    else:
        inventory = _item(
            "competitor_inventory", "疑似竞品清单", "key", "missing", 15, 0,
            "尚无可核验的疑似竞品清单。", "先完成高德采集",
        )

    if not competitors:
        detail = _item(
            "competitor_core_details", "核心竞品经营信息", "key",
            "not_applicable" if amap_ready and not poi_candidates else "missing",
            20, 20 if amap_ready and not poi_candidates else 0,
            "当前没有需要补充的竞品候选。" if amap_ready and not poi_candidates else "尚未形成核心竞品经营信息。",
            None if amap_ready and not poi_candidates else "整理并核实最近的疑似竞品",
        )
        return inventory, detail

    core = competitors[: min(3, len(competitors))]
    unresolved: list[str] = []
    acknowledged: list[str] = []
    for row in core:
        unknown = _unknown_fields(row)
        groups = {
            "价格": bool(row.hour_price is not None or row.member_price is not None),
            "机器/配置": bool(row.machine_count is not None or row.cpu or row.gpu or row.monitor),
            "现场上座率": row.occupancy_rate is not None,
        }
        unknown_groups = {
            "价格": bool({"hour_price", "member_price"} & unknown),
            "机器/配置": bool({"machine_count", "cpu", "gpu", "monitor"} & unknown),
            "现场上座率": "occupancy_rate" in unknown,
        }
        for label, known in groups.items():
            if known:
                continue
            marker = f"{row.name}：{label}"
            (acknowledged if unknown_groups[label] else unresolved).append(marker)
    if unresolved:
        detail = _item(
            "competitor_core_details", "核心竞品经营信息", "key", "missing", 20, 0,
            f"最近 {len(core)} 家竞品仍有 {len(unresolved)} 组关键信息未处理。",
            "优先补充价格、机器配置和现场上座率",
        )
    elif acknowledged:
        detail = _item(
            "competitor_core_details", "核心竞品经营信息", "key", "acknowledged_unknown", 20, 10,
            f"最近 {len(core)} 家竞品的缺失项已明确标记未知，报告会保留不确定性。",
            "如能现场取得信息，可继续完善",
        )
    else:
        detail = _item(
            "competitor_core_details", "核心竞品经营信息", "key", "complete", 20, 20,
            f"最近 {len(core)} 家竞品的价格、机器配置和现场上座率已处理。",
        )
    return inventory, detail


def _property_item(db: Session, project_id: str) -> dict[str, Any]:
    property_row = db.scalar(
        select(SupplementRecord).where(
            SupplementRecord.project_id == project_id,
            SupplementRecord.target_type == "candidate_property",
            SupplementRecord.field_name == "manual_detail",
        ).order_by(SupplementRecord.id.desc())
    )
    values = dict(property_row.value) if property_row and isinstance(property_row.value, dict) else {}
    unknown = _unknown_fields(property_row) if property_row else set()
    if not values:
        rent = db.scalar(
            select(RentDataRecord).where(
                RentDataRecord.project_id == project_id,
                RentDataRecord.status == "confirmed",
            ).order_by(RentDataRecord.timestamp.desc(), RentDataRecord.id.desc())
        )
        if rent:
            values = {"address": rent.location_type, "area_sqm": rent.area_sqm, "monthly_rent": rent.monthly_rent}
            unknown = _unknown_fields(rent)
    required = {"address": "地址", "area_sqm": "面积", "monthly_rent": "月租"}
    missing = [label for field, label in required.items() if values.get(field) in (None, "") and field not in unknown]
    acknowledged = [label for field, label in required.items() if values.get(field) in (None, "") and field in unknown]
    if missing:
        return _item(
            "candidate_property", "候选物业核心条件", "key", "missing", 15, 0,
            f"仍需处理：{'、'.join(missing)}。", "补充候选物业地址、面积和月租",
        )
    if acknowledged:
        return _item(
            "candidate_property", "候选物业核心条件", "key", "acknowledged_unknown", 15, 7.5,
            f"以下信息已明确标记未知：{'、'.join(acknowledged)}。", "取得物业资料后继续完善",
        )
    return _item(
        "candidate_property", "候选物业核心条件", "key", "complete", 15, 15,
        "候选物业地址、面积和月租已处理。",
    )


def _supporting_item(db: Session, project_id: str, amap_ready: bool) -> dict[str, Any]:
    food = list(db.scalars(select(FoodBusinessRecord).where(FoodBusinessRecord.project_id == project_id)).all())
    entertainment = list(db.scalars(select(EntertainmentRecord).where(EntertainmentRecord.project_id == project_id)).all())
    confirmed = [row for row in (*food, *entertainment) if row.status == "confirmed"]
    candidates = [row for row in (*food, *entertainment) if row.status != "rejected"]
    if confirmed:
        unresolved = 0
        acknowledged = 0
        for row in confirmed:
            raw = row.raw_data if isinstance(row.raw_data, dict) else {}
            detail = raw.get("manual_detail") if isinstance(raw.get("manual_detail"), dict) else {}
            unknown = _unknown_fields(row)
            groups = set(raw.get("supporting_groups") or [])
            if raw.get("supporting_group"):
                groups.add(raw["supporting_group"])
            required = ("is_24_hours", "night_operation") if "night_economy" in groups else (
                "business_hours", "night_operation",
            )
            for field in required:
                if detail.get(field) is not None:
                    continue
                if field in unknown:
                    acknowledged += 1
                else:
                    unresolved += 1
        if unresolved:
            return _item(
                "supporting_context", "周边配套现场核实", "recommended", "missing", 10, 0,
                f"已确认 {len(confirmed)} 家配套，但仍有 {unresolved} 项营业信息未处理。",
                "按需补充营业时间和夜间经营状态",
            )
        if acknowledged:
            return _item(
                "supporting_context", "周边配套现场核实", "recommended", "acknowledged_unknown", 10, 5,
                f"已确认配套中有 {acknowledged} 项营业信息明确标记未知。",
                "如能现场取得信息，可继续完善",
            )
        return _item(
            "supporting_context", "周边配套现场核实", "recommended", "complete", 10, 10,
            f"已人工确认 {len(confirmed)} 家餐饮或娱乐配套。",
        )
    if candidates:
        return _item(
            "supporting_context", "周边配套现场核实", "recommended", "missing", 10, 0,
            f"已有 {len(candidates)} 家配套候选，尚未人工确认。", "按需确认夜间营业和有效性",
        )
    if amap_ready:
        return _item(
            "supporting_context", "周边配套现场核实", "recommended", "not_applicable", 10, 10,
            "本次采集未形成配套候选，可在报告中说明零结果。",
        )
    return _item(
        "supporting_context", "周边配套现场核实", "recommended", "missing", 10, 0,
        "尚无周边配套数据。", "先完成高德采集",
    )


def build_readiness(db: Session, project: SiteProjectRecord) -> dict[str, Any]:
    amap = _amap_state(db, project)
    amap_status = str(amap.get("status") or "not_started")
    amap_ready = amap_status in AMAP_READY_STATUSES
    location_ready = project.longitude is not None and project.latitude is not None

    location_item = _item(
        "project_location", "项目坐标", "technical",
        "complete" if location_ready else "blocked", 15, 15 if location_ready else 0,
        "项目地址已定位，可按分析半径采集。" if location_ready else "项目尚未获得可用坐标。",
        None if location_ready else "重新确认地址并完成定位",
    )
    amap_messages = {
        "not_started": ("blocked", "尚未执行高德采集。", "执行高德 POI 采集"),
        "failed": ("blocked", "最近一次高德采集失败。", "检查 Key 或网络后重试"),
        "needs_confirmation": ("blocked", "地址存在多个候选，尚未确认。", "选择正确地址后重新采集"),
        "success_zero": ("complete", "高德请求成功，但当前范围返回 0 条有效 POI。", None),
        "partial": ("complete", "高德部分关键词采集成功，结果存在缺口。", "可重试失败关键词"),
        "truncated": ("complete", "高德采集成功，但结果达到配置上限。", "报告中保留截断说明"),
        "success": ("complete", f"高德采集成功，保存 {int(amap.get('poi_count') or 0)} 条 POI。", None),
        "legacy_success": ("complete", f"检测到 {int(amap.get('poi_count') or 0)} 条升级前高德 POI。", None),
    }
    state, summary, action = amap_messages.get(amap_status, amap_messages["not_started"])
    amap_item = _item("amap_collection", "高德基础采集", "technical", state, 25, 25 if amap_ready else 0, summary, action)
    inventory, competitor_detail = _competitor_item(db, project.project_id, amap_ready)
    property_item = _property_item(db, project.project_id)
    supporting_item = _supporting_item(db, project.project_id, amap_ready)
    optional_item = _item(
        "optional_sales", "竞品营业额", "optional", "optional", 0, 0,
        "营业额仅在来源可靠时填写，不影响数据准备度。",
    )

    items = [location_item, amap_item, inventory, competitor_detail, property_item, supporting_item, optional_item]
    technical = [item for item in items if item["category"] == "technical"]
    key = [item for item in items if item["category"] == "key"]
    recommended = [item for item in items if item["category"] == "recommended"]
    optional = [item for item in items if item["category"] == "optional"]
    technical_blocked = any(item["status"] == "blocked" for item in technical)
    key_missing = any(item["status"] == "missing" for item in key)
    total_weight = sum(item["weight"] for item in items)
    earned = sum(item["earned"] for item in items)
    percent = round(earned / total_weight * 100) if total_weight else 0
    status = "blocked" if technical_blocked else "needs_input" if key_missing else "ready"
    missing = [item["label"] for item in items if item["status"] in {"blocked", "missing"}]
    warnings = []
    if amap_status == "partial":
        warnings.append("高德部分关键词请求失败，报告必须说明采集缺口。")
    if amap_status == "truncated":
        warnings.append("高德结果达到配置上限，数量不代表区域内全部商户。")
    if amap_status == "success_zero":
        warnings.append("高德成功返回零结果，应表述为本次查询未发现，不得表述为绝对不存在。")
    if any(item["status"] == "acknowledged_unknown" for item in items):
        warnings.append("部分关键数据已明确标记未知，报告必须保留不确定性。")

    return {
        "status": status,
        "can_generate_report": not technical_blocked,
        "formal_report_ready": not technical_blocked and not key_missing,
        "completion_percent": percent,
        "score_explanation": "准备度按固定检查项权重汇总，不代表项目推荐概率。",
        "amap_collection": amap,
        "groups": {
            "technical_prerequisites": technical,
            "key_unknowns": key,
            "recommended": recommended,
            "optional": optional,
        },
        "summary": {
            "total": len(items),
            "complete": sum(item["status"] in {"complete", "not_applicable", "optional"} for item in items),
            "acknowledged_unknown": sum(item["status"] == "acknowledged_unknown" for item in items),
            "missing": sum(item["status"] == "missing" for item in items),
            "blocked": sum(item["status"] == "blocked" for item in items),
        },
        "missing": missing,
        "warnings": warnings,
        "inventory": {
            "poi_count": _count(db, UnifiedPOIRecord, project.project_id),
            "competitor_count": _count(db, UnifiedCompetitorRecord, project.project_id),
            "food_count": _count(db, FoodBusinessRecord, project.project_id),
            "entertainment_count": _count(db, EntertainmentRecord, project.project_id),
            "rent_count": _count(db, RentDataRecord, project.project_id),
        },
    }
