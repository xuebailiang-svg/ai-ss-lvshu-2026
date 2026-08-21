from __future__ import annotations

import asyncio
import math
import re
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


class AmapRequestError(RuntimeError):
    def __init__(self, code: str, message: str, *, infocode: str | None = None):
        super().__init__(message)
        self.code = code
        self.infocode = infocode


def _normalized_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def poi_identity(poi: dict[str, Any]) -> tuple[Any, ...]:
    amap_id = str(poi.get("id") or "").strip()
    if amap_id:
        return ("amap_id", amap_id)
    location = str(poi.get("location") or "")
    longitude, latitude = "", ""
    if "," in location:
        longitude, latitude = location.split(",", 1)
    try:
        longitude = f"{float(longitude):.6f}"
        latitude = f"{float(latitude):.6f}"
    except (TypeError, ValueError):
        pass
    return (
        "fallback",
        _normalized_text(poi.get("name")),
        _normalized_text(poi.get("address")),
        longitude,
        latitude,
    )


def _distance_meters(poi: dict[str, Any], longitude: float, latitude: float) -> float | None:
    try:
        return float(poi.get("distance"))
    except (TypeError, ValueError):
        pass
    location = str(poi.get("location") or "")
    if "," not in location:
        return None
    try:
        poi_lng, poi_lat = (float(item) for item in location.split(",", 1))
    except (TypeError, ValueError):
        return None
    radius = 6_371_000.0
    lat1, lat2 = math.radians(latitude), math.radians(poi_lat)
    delta_lat = math.radians(poi_lat - latitude)
    delta_lng = math.radians(poi_lng - longitude)
    value = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(value))


class AmapMapDataClient:
    base_url = "https://restapi.amap.com/v3"

    def __init__(
        self,
        *,
        key: str | None = None,
        mock: bool | None = None,
        client: httpx.AsyncClient | None = None,
        page_size: int | None = None,
        max_pages_per_keyword: int | None = None,
        max_records_per_category: int | None = None,
        rate_limit_seconds: float | None = None,
    ):
        settings = get_settings()
        from app.system_config.service import resolve_config_value

        self.key = (
            key if key is not None else resolve_config_value("amap_web_service_key", settings.amap_web_service_key)
        ).strip()
        self.mock = settings.amap_mock if mock is None else mock
        self.client = client
        self.page_size = max(1, min(25, page_size or settings.amap_poi_page_size))
        self.max_pages_per_keyword = max(1, max_pages_per_keyword or settings.amap_poi_max_pages_per_keyword)
        self.max_records_per_category = max(1, max_records_per_category or settings.amap_poi_max_records_per_category)
        self.rate_limit_seconds = max(
            0.0,
            settings.amap_poi_rate_limit_seconds if rate_limit_seconds is None else rate_limit_seconds,
        )

    def ensure_configured(self) -> None:
        if not self.key and not self.mock:
            raise AmapConfigError("AMAP_WEB_SERVICE_KEY未配置")

    async def _request_json(
        self,
        client: httpx.AsyncClient,
        path: str,
        params: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        try:
            response = await client.get(
                f"{self.base_url}/{path}",
                params=params,
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise AmapRequestError("timeout", "高德接口请求超时，请稍后重试") from exc
        except httpx.HTTPStatusError as exc:
            raise AmapRequestError("http_error", f"高德接口返回 HTTP {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise AmapRequestError("network_error", "无法连接高德接口，请检查服务器网络") from exc
        except ValueError as exc:
            raise AmapRequestError("invalid_response", "高德接口返回内容无法解析") from exc
        if not isinstance(data, dict):
            raise AmapRequestError("invalid_response", "高德接口返回格式异常")
        if str(data.get("status")) != "1":
            info = str(data.get("info") or "unknown error")
            infocode = str(data.get("infocode") or "")
            raise AmapRequestError("amap_error", f"高德接口请求失败：{info} ({infocode})", infocode=infocode)
        return data

    async def check_connectivity(self, *, timeout_seconds: float = 3.0) -> dict[str, Any]:
        """使用固定地址执行轻量检查，不向调用层暴露带 Key 的请求 URL。"""
        self.ensure_configured()
        if self.mock:
            return {"status": "1", "info": "OK", "infocode": "10000", "mock": True}
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=timeout_seconds)
        try:
            return await self._request_json(
                client,
                "geocode/geo",
                {"key": self.key, "city": "西安市", "address": "小寨地铁站", "output": "JSON"},
                timeout_seconds=timeout_seconds,
            )
        finally:
            if owns_client:
                await client.aclose()

    async def geocode(self, *, city: str, address: str, timeout_seconds: float = 8.0) -> dict[str, Any]:
        self.ensure_configured()
        if self.mock:
            return {
                "status": "1",
                "geocodes": [{"formatted_address": f"{city}{address}", "location": "108.946767,34.222838"}],
                "mock": True,
            }
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=timeout_seconds)
        try:
            data = await self._request_json(
                client,
                "geocode/geo",
                {"key": self.key, "city": city, "address": address, "output": "JSON"},
                timeout_seconds=timeout_seconds,
            )
            geocodes = data.get("geocodes")
            if not isinstance(geocodes, list) or not geocodes:
                raise AmapRequestError("no_geocode_result", "高德地址解析没有返回候选地址")
            return data
        finally:
            if owns_client:
                await client.aclose()

    async def collect_pois(
        self,
        *,
        longitude: float,
        latitude: float,
        radius_meters: int,
        city: str | None = None,
        category_keywords: dict[str, list[str]] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        self.ensure_configured()
        if self.mock:
            rows = self._mock_pois(longitude=longitude, latitude=latitude)
            return rows, {
                "mock": True,
                "query_count": 1,
                "successful_query_count": 1,
                "failed_query_count": 0,
                "raw_return_count": len(rows),
                "effective_count": len(rows),
                "unique_count": len(rows),
                "duplicate_count": 0,
                "outside_radius_count": 0,
                "truncated": False,
                "category_summary": {},
                "queries": [],
                "failed_keywords": [],
            }

        unique_rows: dict[tuple[Any, ...], dict[str, Any]] = {}
        diagnostics: dict[str, Any] = {"queries": [], "failed_keywords": [], "category_summary": {}}
        raw_return_count = 0
        effective_count = 0
        duplicate_count = 0
        outside_radius_count = 0
        truncated = False
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=15)
        try:
            for category, keywords in (category_keywords or AMAP_CATEGORY_KEYWORDS).items():
                category_keys: set[tuple[Any, ...]] = set()
                category_raw = 0
                category_truncated = False
                for keyword in keywords:
                    if len(category_keys) >= self.max_records_per_category:
                        category_truncated = True
                        truncated = True
                        break
                    query_raw = 0
                    query_unique_before = len(category_keys)
                    pages_fetched = 0
                    query_failed = False
                    total_available: int | None = None
                    for page in range(1, self.max_pages_per_keyword + 1):
                        params: dict[str, Any] = {
                            "key": self.key,
                            "location": f"{longitude},{latitude}",
                            "radius": radius_meters,
                            "keywords": keyword,
                            "offset": self.page_size,
                            "page": page,
                            "extensions": "all",
                            "output": "JSON",
                            "citylimit": "false",
                            "sortrule": "distance",
                        }
                        if city:
                            params["city"] = city
                        try:
                            data = await self._get_place_around(client, params)
                        except AmapRequestError as exc:
                            diagnostics["failed_keywords"].append(
                                {"category": category, "keyword": keyword, "code": exc.code, "message": str(exc)}
                            )
                            query_failed = True
                            break

                        pages_fetched += 1
                        try:
                            total_available = int(data.get("count"))
                        except (TypeError, ValueError):
                            total_available = None
                        pois = data.get("pois")
                        if not isinstance(pois, list):
                            pois = []
                        query_raw += len(pois)
                        category_raw += len(pois)
                        raw_return_count += len(pois)
                        for poi in pois:
                            if not isinstance(poi, dict):
                                continue
                            distance = _distance_meters(poi, longitude, latitude)
                            if distance is not None and distance > radius_meters:
                                outside_radius_count += 1
                                continue
                            effective_count += 1
                            enriched = {"category": category, "sub_category": keyword, **poi}
                            identity = poi_identity(enriched)
                            if identity in unique_rows:
                                duplicate_count += 1
                                continue
                            if len(category_keys) >= self.max_records_per_category:
                                category_truncated = True
                                truncated = True
                                break
                            unique_rows[identity] = enriched
                            category_keys.add(identity)
                        if len(category_keys) >= self.max_records_per_category:
                            category_truncated = True
                            truncated = True
                            break
                        if not pois or len(pois) < self.page_size:
                            break
                        if total_available is not None and page * self.page_size >= total_available:
                            break
                        if page == self.max_pages_per_keyword:
                            category_truncated = True
                            truncated = True
                        if self.rate_limit_seconds:
                            await asyncio.sleep(self.rate_limit_seconds)

                    diagnostics["queries"].append(
                        {
                            "category": category,
                            "keyword": keyword,
                            "status": "failed" if query_failed else "success",
                            "pages_fetched": pages_fetched,
                            "raw_count": query_raw,
                            "unique_count": len(category_keys) - query_unique_before,
                            "total_available": total_available,
                            "truncated": category_truncated,
                        }
                    )
                    if self.rate_limit_seconds:
                        await asyncio.sleep(self.rate_limit_seconds)

                diagnostics["category_summary"][category] = {
                    "raw_count": category_raw,
                    "unique_count": len(category_keys),
                    "truncated": category_truncated,
                }
        finally:
            if owns_client:
                await client.aclose()

        query_count = len(diagnostics["queries"])
        failed_count = sum(1 for item in diagnostics["queries"] if item["status"] == "failed")
        diagnostics.update(
            {
                "query_count": query_count,
                "successful_query_count": query_count - failed_count,
                "failed_query_count": failed_count,
                "raw_return_count": raw_return_count,
                "effective_count": effective_count,
                "unique_count": len(unique_rows),
                "duplicate_count": duplicate_count,
                "outside_radius_count": outside_radius_count,
                "truncated": truncated,
            }
        )
        return list(unique_rows.values()), diagnostics

    async def _get_place_around(self, client: httpx.AsyncClient, params: dict[str, Any]) -> dict[str, Any]:
        return await self._request_json(client, "place/around", params)

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
