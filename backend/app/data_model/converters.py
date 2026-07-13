from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from .enums import DataSourceType, DataStatus, EntertainmentType, POICategory
from .schemas import (
    CompetitorData,
    EntertainmentData,
    FoodBusinessData,
    POIData,
    PopulationData,
    RentData,
    SiteProject,
    SupplementData,
)
from .validators import parse_location, to_bool, to_float, to_int


CHINESE_COMPETITOR_FIELD_MAP = {
    "名称": "name",
    "地址": "address",
    "距离": "distance_meters",
    "距离米": "distance_meters",
    "面积": "area_sqm",
    "营业面积": "area_sqm",
    "开业时间": "opening_date",
    "开业年限": "opening_years",
    "机器数量": "machine_count",
    "CPU": "cpu",
    "cpu": "cpu",
    "显卡": "gpu",
    "GPU": "gpu",
    "显示器": "monitor",
    "价格": "hour_price",
    "小时价": "hour_price",
    "会员价": "member_price",
    "上座率": "occupancy_rate",
    "月售": "monthly_sales",
    "年售": "annual_sales",
    "充值金额": "recharge_amount",
    "数据来源": "source",
    "置信度": "confidence",
}


def convert_amap_poi(raw: dict[str, Any], *, category: str | POICategory | None = None) -> POIData:
    location = raw.get("location") or raw.get("经纬度")
    longitude, latitude = parse_location(location)
    if longitude is None:
        longitude = to_float(raw.get("longitude") or raw.get("lng"))
    if latitude is None:
        latitude = to_float(raw.get("latitude") or raw.get("lat"))
    payload = {
        "name": raw.get("name") or raw.get("名称") or "未命名 POI",
        "category": category or infer_poi_category(raw),
        "sub_category": raw.get("type") or raw.get("subcategory") or raw.get("sub_category") or raw.get("typecode"),
        "address": raw.get("address") or raw.get("地址"),
        "longitude": longitude,
        "latitude": latitude,
        "distance_meters": to_int(raw.get("distance") or raw.get("distance_meters") or raw.get("距离")),
        "walking_distance_meters": to_int(raw.get("walking_distance_meters") or raw.get("walking_distance") or raw.get("步行距离")),
        "business_hours": raw.get("business_hours") or raw.get("营业时间"),
        "source": DataSourceType.amap,
        "confidence": 0.95,
        "status": DataStatus.confirmed,
        "raw_data": raw,
    }
    return POIData(**payload)


def convert_manual_competitor(raw: dict[str, Any]) -> CompetitorData:
    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        normalized[CHINESE_COMPETITOR_FIELD_MAP.get(key, key)] = value
    for key in ("distance_meters", "machine_count"):
        normalized[key] = to_int(normalized.get(key))
    for key in ("area_sqm", "opening_years", "hour_price", "member_price", "occupancy_rate", "monthly_sales", "annual_sales", "recharge_amount", "confidence"):
        if key in normalized:
            normalized[key] = to_float(normalized.get(key))
    normalized.setdefault("source", DataSourceType.manual)
    normalized.setdefault("status", DataStatus.pending_review)
    normalized.setdefault("confidence", 0.8)
    normalized["raw_data"] = raw
    return CompetitorData(**normalized)


def normalize_data(body: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    data_type = str(body.get("data_type") or body.get("type") or "poi").strip().lower()
    raw = body.get("data") if isinstance(body.get("data"), dict) else body
    warnings: list[str] = []
    try:
        if data_type in {"amap_poi", "poi"} and str(raw.get("source") or body.get("source") or "").lower() == "amap":
            item = convert_amap_poi(raw, category=body.get("category"))
        elif data_type == "poi":
            item = POIData(**{**raw, "raw_data": raw})
        elif data_type == "competitor":
            item = convert_manual_competitor(raw)
            for field in ("hour_price", "machine_count", "occupancy_rate", "monthly_sales"):
                if getattr(item, field) is None:
                    warnings.append(f"缺少竞品字段：{field}")
        elif data_type == "food":
            item = FoodBusinessData(**coerce_food(raw))
        elif data_type == "entertainment":
            item = EntertainmentData(**coerce_entertainment(raw))
        elif data_type == "rent":
            item = RentData(**{**raw, "raw_data": raw})
        elif data_type == "population":
            item = PopulationData(**{**raw, "raw_data": raw})
            warnings.append("人口数据为代理指标，不代表真实人口。")
        elif data_type == "supplement":
            item = SupplementData(**{**raw, "raw_data": raw})
        elif data_type == "site_project":
            item = SiteProject(**raw)
        else:
            raise ValueError(f"unsupported data_type: {data_type}")
    except ValidationError:
        raise
    return item.model_dump(mode="python"), warnings


def coerce_food(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        **raw,
        "distance_meters": to_int(raw.get("distance_meters") or raw.get("距离")),
        "opening_years": to_float(raw.get("opening_years") or raw.get("开业年限")),
        "night_business": to_bool(raw.get("night_business") or raw.get("夜间营业")),
        "rating": to_float(raw.get("rating") or raw.get("评分")),
        "raw_data": raw,
    }


def coerce_entertainment(raw: dict[str, Any]) -> dict[str, Any]:
    text_type = str(raw.get("type") or raw.get("类型") or "other").lower()
    type_map = {
        "ktv": EntertainmentType.ktv,
        "bar": EntertainmentType.bar,
        "酒吧": EntertainmentType.bar,
        "billiard": EntertainmentType.billiard,
        "台球": EntertainmentType.billiard,
        "cinema": EntertainmentType.cinema,
        "电影院": EntertainmentType.cinema,
        "escape_room": EntertainmentType.escape_room,
        "密室": EntertainmentType.escape_room,
    }
    return {
        **raw,
        "type": type_map.get(text_type, EntertainmentType.other),
        "distance_meters": to_int(raw.get("distance_meters") or raw.get("距离")),
        "night_business": to_bool(raw.get("night_business") or raw.get("夜间营业")),
        "raw_data": raw,
    }


def infer_poi_category(raw: dict[str, Any]) -> POICategory:
    text = " ".join(str(raw.get(key) or "") for key in ("name", "type", "typecode", "category", "名称"))
    if any(word in text for word in ("网吧", "网咖", "电竞", "电竞酒店")):
        return POICategory.competitor
    if any(word in text for word in ("大学", "学院", "小学", "中学", "幼儿园", "学校")):
        return POICategory.education
    if any(word in text for word in ("地铁", "公交", "停车", "车站")):
        return POICategory.transport
    if any(word in text for word in ("餐饮", "餐厅", "火锅", "烧烤", "便利店", "奶茶")):
        return POICategory.food
    if any(word in text for word in ("KTV", "酒吧", "台球", "电影院", "密室")):
        return POICategory.entertainment
    if any(word in text for word in ("小区", "公寓", "住宅")):
        return POICategory.residential
    if any(word in text for word in ("商场", "写字楼", "商业")):
        return POICategory.commercial
    return POICategory.other
