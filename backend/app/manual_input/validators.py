from __future__ import annotations

from typing import Any


COMPETITOR_FIELDS = {
    "name",
    "address",
    "distance_meters",
    "area_sqm",
    "opening_date",
    "machine_count",
    "cpu",
    "gpu",
    "monitor",
    "hour_price",
    "member_price",
    "business_hours",
    "occupancy_rate",
    "monthly_sales",
    "annual_sales",
    "recharge_amount",
    "recharge_info",
    "remark",
}

RENT_FIELDS = {
    "address",
    "monthly_rent",
    "area_sqm",
    "rent_per_sqm",
    "property_fee",
    "transfer_fee",
    "location_type",
    "remark",
}

POPULATION_FIELDS = {
    "nearby_university_count",
    "nearby_school_count",
    "nearby_apartment_count",
    "nearby_residential_count",
    "young_population_indicator",
    "target_customer_description",
}

PROPERTY_FIELDS = {
    "address", "area_sqm", "monthly_rent", "floor", "property_type", "use_allowed",
    "power_capacity_kw", "power_sufficient", "fire_confirmed", "network_carriers",
    "dual_line_supported", "night_entrance", "independent_entrance", "notes", "unknown_fields",
}


def flatten_manual_data(data: dict[str, Any]) -> dict[str, Any]:
    flattened = dict(data or {})
    hardware = flattened.pop("hardware", None)
    if isinstance(hardware, dict):
        flattened.update({key: value for key, value in hardware.items() if key in {"cpu", "gpu", "monitor"}})
    price = flattened.pop("price", None)
    if isinstance(price, dict):
        flattened.update({key: value for key, value in price.items() if key in {"hour_price", "member_price"}})
    operation = flattened.pop("operation", None)
    if isinstance(operation, dict):
        flattened.update(
            {
                key: value
                for key, value in operation.items()
                if key in {"occupancy_rate", "monthly_sales", "annual_sales", "recharge_amount"}
            }
        )
    return flattened


def allowed_fields(data_type: str) -> set[str]:
    if data_type == "competitor":
        return COMPETITOR_FIELDS
    if data_type == "rent":
        return RENT_FIELDS
    if data_type == "population":
        return POPULATION_FIELDS
    if data_type == "supplement":
        return {"target_type", "target_id", "field_name", "value", "remark"}
    if data_type == "property":
        return PROPERTY_FIELDS
    return set()


def validate_manual_payload(data_type: str, data: dict[str, Any]) -> dict[str, Any]:
    flattened = flatten_manual_data(data)
    fields = allowed_fields(data_type)
    if not fields:
        raise ValueError(f"unsupported manual input type: {data_type}")
    unknown = sorted(set(flattened) - fields)
    if unknown:
        raise ValueError(f"unsupported fields for {data_type}: {', '.join(unknown)}")
    return flattened
