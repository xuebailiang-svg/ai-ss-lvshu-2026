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
    biz_ext = raw.get("biz_ext") if isinstance(raw.get("biz_ext"), dict) else {}
    normalized["raw_data"] = {
        **raw,
        "_amap_fields": {
            "poi_id": str(raw.get("id") or "").strip() or None,
            "phone": str(raw.get("tel") or "").strip() or None,
            "rating": biz_ext.get("rating") if biz_ext.get("rating") not in (None, "") else None,
            "business_hours": normalized.get("business_hours"),
            "operating_status": (
                raw.get("business_status")
                or biz_ext.get("business_status")
                or raw.get("business_state")
                or None
            ),
        },
    }
    if sub_category:
        normalized["sub_category"] = sub_category
    return normalized
