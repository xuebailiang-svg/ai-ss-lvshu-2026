from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any


class WebsiteAdapter(ABC):
    name = "base"

    @abstractmethod
    def supports(self, url: str, html: str) -> bool: ...

    @abstractmethod
    def extract(self, task_type: str, url: str, html: str) -> dict[str, Any]: ...


class JsonLdAdapter(WebsiteAdapter):
    """Extract conservative, schema.org-backed fields before generic text rules."""

    name = "json_ld"

    def supports(self, url: str, html: str) -> bool:
        return "application/ld+json" in (html or "").lower()

    def extract(self, task_type: str, url: str, html: str) -> dict[str, Any]:
        objects: list[dict[str, Any]] = []
        for raw in re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html or "",
            flags=re.I | re.S,
        ):
            try:
                value = json.loads(raw.strip())
            except (TypeError, ValueError):
                continue
            if isinstance(value, dict) and isinstance(value.get("@graph"), list):
                objects.extend(item for item in value["@graph"] if isinstance(item, dict))
            elif isinstance(value, list):
                objects.extend(item for item in value if isinstance(item, dict))
            elif isinstance(value, dict):
                objects.append(value)

        detail: dict[str, Any] = {"source_url": url}
        for item in objects:
            if not detail.get("business_hours"):
                hours = item.get("openingHours") or item.get("openingHoursSpecification")
                if isinstance(hours, str):
                    detail["business_hours"] = hours[:200]
            rating = item.get("aggregateRating")
            if task_type == "supporting" and isinstance(rating, dict):
                try:
                    number = float(rating.get("ratingValue"))
                    if 0 <= number <= 5:
                        detail["rating"] = number
                except (TypeError, ValueError):
                    pass
            if task_type == "rent":
                offer = item.get("offers") if isinstance(item.get("offers"), dict) else {}
                try:
                    price = float(offer.get("price"))
                    if 100 <= price <= 10_000_000:
                        detail["monthly_rent"] = price
                except (TypeError, ValueError):
                    pass
                address = item.get("address")
                if isinstance(address, dict):
                    detail["address"] = "".join(str(address.get(key) or "") for key in ("addressRegion", "addressLocality", "streetAddress"))[:100] or None
                elif isinstance(address, str):
                    detail["address"] = address[:100]
        return detail


ADAPTERS: tuple[WebsiteAdapter, ...] = (JsonLdAdapter(),)


def extract_structured_fields(task_type: str, url: str, html: str | None) -> tuple[dict[str, Any], list[str]]:
    merged: dict[str, Any] = {}
    used: list[str] = []
    for adapter in ADAPTERS:
        if adapter.supports(url, html or ""):
            result = adapter.extract(task_type, url, html or "")
            for field, value in result.items():
                if value not in (None, "", []) and field not in merged:
                    merged[field] = value
            used.append(adapter.name)
    return merged, used
