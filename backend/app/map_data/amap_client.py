from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.config import get_settings


AMAP_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "transport": ["地铁", "公交", "停车场"],
    "competitor": ["网吧", "电竞馆", "电竞酒店"],
    "education": ["大学", "技校", "职业院校"],
    "residential": ["小区", "公寓"],
    "food": ["餐厅", "烧烤", "夜宵"],
    "entertainment": ["KTV", "酒吧", "电影院", "台球", "密室"],
}


class AmapConfigError(RuntimeError):
    pass


class AmapMapDataClient:
    base_url = "https://restapi.amap.com/v3"

    def __init__(self, *, key: str | None = None, mock: bool | None = None, client: httpx.AsyncClient | None = None):
        settings = get_settings()
        self.key = (key if key is not None else settings.amap_web_service_key).strip()
        self.mock = settings.amap_mock if mock is None else mock
        self.client = client

    def ensure_configured(self) -> None:
        if not self.key and not self.mock:
            raise AmapConfigError("AMAP_WEB_SERVICE_KEY未配置")

    async def collect_pois(
        self,
        *,
        longitude: float,
        latitude: float,
        radius_meters: int,
        city: str | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        self.ensure_configured()
        if self.mock:
            return self._mock_pois(longitude=longitude, latitude=latitude), {"mock": True}

        rows: list[dict[str, Any]] = []
        diagnostics: dict[str, Any] = {"queries": [], "failed_keywords": []}
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=15)
        try:
            for category, keywords in AMAP_CATEGORY_KEYWORDS.items():
                for keyword in keywords:
                    params: dict[str, Any] = {
                        "key": self.key,
                        "location": f"{longitude},{latitude}",
                        "radius": radius_meters,
                        "keywords": keyword,
                        "offset": 20,
                        "page": 1,
                        "extensions": "all",
                        "output": "JSON",
                        "citylimit": "false",
                        "sortrule": "distance",
                    }
                    if city:
                        params["city"] = city
                    try:
                        data = await self._get_place_around(client, params)
                    except Exception as exc:  # noqa: BLE001 - 采集服务需要容错记录单个关键词失败
                        diagnostics["failed_keywords"].append(
                            {"category": category, "keyword": keyword, "message": str(exc)}
                        )
                        diagnostics["queries"].append(
                            {"category": category, "keyword": keyword, "status": "failed", "count": 0}
                        )
                        await asyncio.sleep(0.3)
                        continue

                    pois = data.get("pois") if isinstance(data, dict) else []
                    if not isinstance(pois, list):
                        pois = []
                    for poi in pois:
                        if isinstance(poi, dict):
                            rows.append({"category": category, "sub_category": keyword, **poi})
                    diagnostics["queries"].append(
                        {
                            "category": category,
                            "keyword": keyword,
                            "status": "success",
                            "count": len(pois),
                            "infocode": data.get("infocode"),
                            "info": data.get("info"),
                        }
                    )
                    await asyncio.sleep(0.3)
        finally:
            if owns_client:
                await client.aclose()
        diagnostics["raw_count"] = len(rows)
        return rows, diagnostics

    async def _get_place_around(self, client: httpx.AsyncClient, params: dict[str, Any]) -> dict[str, Any]:
        response = await client.get(f"{self.base_url}/place/around", params=params)
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "1":
            info = str(data.get("info", "unknown error"))
            infocode = str(data.get("infocode", ""))
            raise RuntimeError(f"Amap place/around failed: {info} ({infocode})")
        return data

    @staticmethod
    def _mock_pois(*, longitude: float, latitude: float) -> list[dict[str, Any]]:
        samples = [
            ("transport", "地铁", "示例地铁站", 0.001, 0.001, 120),
            ("competitor", "电竞馆", "示例电竞馆", 0.002, 0.001, 260),
            ("education", "大学", "示例大学", 0.003, 0.001, 500),
            ("residential", "小区", "示例住宅小区", 0.001, 0.002, 300),
            ("food", "烧烤", "示例夜宵烧烤", 0.002, 0.002, 360),
            ("entertainment", "KTV", "示例KTV", 0.003, 0.002, 620),
        ]
        return [
            {
                "id": f"mock-{index}",
                "category": category,
                "sub_category": sub_category,
                "name": name,
                "type": sub_category,
                "address": "候选点附近",
                "location": f"{longitude + lng_offset},{latitude + lat_offset}",
                "distance": str(distance),
                "source": "amap",
                "mock": True,
            }
            for index, (category, sub_category, name, lng_offset, lat_offset, distance) in enumerate(samples, start=1)
        ]
