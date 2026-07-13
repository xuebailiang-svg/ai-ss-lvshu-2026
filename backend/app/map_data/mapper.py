from __future__ import annotations

from typing import Any

from app.data_model.converters import normalize_data


def amap_poi_to_unified(raw: dict[str, Any], *, category: str | None = None, sub_category: str | None = None) -> dict[str, Any]:
    payload = {
        **raw,
        "source": "amap",
        "category": category or raw.get("category"),
        "type": sub_category or raw.get("sub_category") or raw.get("type") or raw.get("typecode"),
    }
    normalized, _warnings = normalize_data(
        {
            "type": "amap_poi",
            "source": "amap",
            "category": payload.get("category"),
            "data": payload,
        }
    )
    normalized["source"] = "amap"
    normalized["confidence"] = 0.9
    normalized["raw_data"] = raw
    if sub_category:
        normalized["sub_category"] = sub_category
    return normalized
