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


def _amap_business_hours(raw: dict[str, Any]) -> str | None:
    """从高德 POI 原始数据中提取营业时间（biz_ext.open_time）。

    高德 place/around 接口返回的营业时间在 ``biz_ext.open_time``，
    可能是字符串或数组，统一规范为逗号分隔的字符串。
    """
    biz_ext = raw.get("biz_ext") if isinstance(raw.get("biz_ext"), dict) else {}
    value = biz_ext.get("open_time") or raw.get("opentime")
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        parts = [str(item).strip() for item in value if str(item).strip()]
        if not parts:
            return None
        value = "、".join(parts)
    text = str(value).strip()
    return text or None


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
    "会员价格": "member_price",
    "上座率": "occupancy_rate",
    "月售": "monthly_sales",
    "月营业额": "monthly_sales",
    "年售": "annual_sales",
    "年营业额": "annual_sales",
    "充值金额": "recharge_amount",
    "充值信息": "recharge_amount",
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
        "business_hours": _amap_business_hours(raw) or raw.get("business_hours") or raw.get("营业时间"),
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
    for key in ("area_sqm", "opening_years", "hour_price", "member_price", "monthly_sales", "annual_sales", "recharge_amount", "confidence"):
        if key in normalized:
            normalized[key] = to_float(normalized.get(key))
    occupancy = normalized.get("occupancy_rate")
    if occupancy is not None:
        text = str(occupancy).strip()
        value = to_float(text.rstrip("%"))
        normalized["occupancy_rate"] = value / 100 if value is not None and (text.endswith("%") or value > 1) else value
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
            item = RentData(**coerce_rent(raw))
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
        "name": raw.get("name") or raw.get("名称"),
        "distance_meters": to_int(raw.get("distance_meters") or raw.get("距离")),
        "category": raw.get("category") or raw.get("品类"),
        "opening_date": raw.get("opening_date") or raw.get("开业时间"),
        "opening_years": to_float(raw.get("opening_years") or raw.get("开业年限")),
        "business_hours": _amap_business_hours(raw) or raw.get("business_hours") or raw.get("营业时间"),
        "night_business": to_bool(raw.get("night_business") or raw.get("是否夜间营业") or raw.get("夜间营业")),
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
        "name": raw.get("name") or raw.get("名称"),
        "type": type_map.get(text_type, EntertainmentType.other),
        "distance_meters": to_int(raw.get("distance_meters") or raw.get("距离")),
        "opening_date": raw.get("opening_date") or raw.get("开业时间"),
        "business_hours": _amap_business_hours(raw) or raw.get("business_hours") or raw.get("营业时间"),
        "night_business": to_bool(raw.get("night_business") or raw.get("是否夜间营业") or raw.get("夜间营业")),
        "raw_data": raw,
    }


def coerce_rent(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        **raw,
        "monthly_rent": to_float(raw.get("monthly_rent") or raw.get("月租金")),
        "area_sqm": to_float(raw.get("area_sqm") or raw.get("面积")),
        "rent_per_sqm": to_float(raw.get("rent_per_sqm") or raw.get("单平租金")),
        "location_type": raw.get("location_type") or raw.get("地址"),
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
