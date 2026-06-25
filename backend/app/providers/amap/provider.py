from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.providers.base import DataProvider


class ProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "AMAP_PROVIDER_ERROR",
        provider: str = "amap",
        endpoint: str | None = None,
        status: str | None = None,
        info: str | None = None,
        infocode: str | None = None,
        sanitized_params: dict[str, Any] | None = None,
        raw_response_sanitized: dict[str, Any] | None = None,
        retry_attempts: list[dict[str, Any]] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.provider = provider
        self.endpoint = endpoint
        self.status = status
        self.info = info
        self.infocode = infocode
        self.sanitized_params = sanitized_params or {}
        self.raw_response_sanitized = raw_response_sanitized or {}
        self.retry_attempts = retry_attempts or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "error_code": self.error_code,
            "provider": self.provider,
            "endpoint": self.endpoint,
            "status": self.status,
            "info": self.info,
            "infocode": self.infocode,
            "sanitized_params": self.sanitized_params,
            "raw_response_sanitized": self.raw_response_sanitized,
            "retry_attempts": self.retry_attempts,
        }


class AmapDataProvider(DataProvider):
    base_url = "https://restapi.amap.com/v3"
    geocode_endpoint = "geocode/geo"
    poi_query_groups = [
        ("竞品", ["网吧", "网咖", "电竞馆", "电竞酒店"]),
        ("敏感场所", ["小学", "中学", "幼儿园", "政府机构", "医院"]),
        ("交通", ["地铁站", "公交站", "停车场"]),
        ("商业配套", ["餐饮", "奶茶", "便利店", "KTV", "酒吧", "台球厅", "电影院", "密室", "酒店"]),
        ("人口代理", ["住宅小区", "公寓", "写字楼", "大学", "中职", "技校"]),
    ]

    def __init__(
        self,
        key: str,
        client: httpx.AsyncClient | None = None,
        mock: bool = False,
    ):
        self.key = (key or "").strip()
        self.client = client
        self.mock = mock
        self.last_poi_diagnostics: dict[str, Any] = {}

    async def _get(self, path: str, params: dict[str, Any]):
        if not self.key:
            raise ProviderError(
                "后端未配置高德 Web 服务 Key，请检查 AMAP_WEB_SERVICE_KEY。",
                error_code="AMAP_KEY_MISSING",
                endpoint=path,
                sanitized_params=self._sanitize_params(params),
            )

        request_params = {**params, "key": self.key}
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=15)
        try:
            response = await client.get(f"{self.base_url}/{path}", params=request_params)
            response.raise_for_status()
            data = response.json()
            if data.get("status") != "1":
                raise self._api_error(path, params, data)
            return data
        except ProviderError:
            raise
        except httpx.HTTPError as exc:
            raise ProviderError(
                "服务器无法访问高德接口，请检查服务器网络、防火墙或 DNS。",
                error_code="AMAP_NETWORK_ERROR",
                endpoint=path,
                sanitized_params=self._sanitize_params(params),
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

    async def _get_raw(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.key:
            raise ProviderError(
                "后端未配置高德 Web 服务 Key，请检查 AMAP_WEB_SERVICE_KEY。",
                error_code="AMAP_KEY_MISSING",
                endpoint=path,
                sanitized_params=self._sanitize_params(params),
            )
        request_params = {**params, "key": self.key}
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=15)
        try:
            response = await client.get(f"{self.base_url}/{path}", params=request_params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise ProviderError(
                "服务器无法访问高德接口，请检查服务器网络、防火墙或 DNS。",
                error_code="AMAP_NETWORK_ERROR",
                endpoint=path,
                sanitized_params=self._sanitize_params(params),
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

    async def geocode(self, address: str, city: str | None = None):
        address_clean = self._clean_text(address)
        city_clean = self._normalize_city(city)
        if not address_clean:
            raise ProviderError(
                "地址不能为空，请补充省、市、区、街道或门牌号后重试。",
                error_code="AMAP_INVALID_ADDRESS",
                endpoint=self.geocode_endpoint,
                sanitized_params={},
            )

        if self.mock:
            return {
                "formatted_address": f"{city_clean or ''}{address_clean}",
                "district": city_clean or "测试区",
                "longitude": 116.397428,
                "latitude": 39.90923,
                "coordinate_system": "GCJ02",
                "provider": "amap",
                "retry_attempts": [],
            }

        attempts = self._geocode_attempts(address_clean, city_clean)
        retry_attempts: list[dict[str, Any]] = []
        last_error: ProviderError | None = None

        for index, attempt in enumerate(attempts, start=1):
            params = self._build_geocode_params(attempt["address"], attempt.get("city"))
            try:
                data = await self._get_raw(self.geocode_endpoint, params)
            except ProviderError as exc:
                exc.retry_attempts = retry_attempts
                raise

            summary = self._attempt_summary(index, attempt["label"], params, data)
            retry_attempts.append(summary)

            if data.get("status") != "1":
                last_error = self._api_error(
                    self.geocode_endpoint,
                    params,
                    data,
                    retry_attempts=retry_attempts,
                )
                if self._should_fallback(data):
                    continue
                raise last_error

            rows = data.get("geocodes")
            if not isinstance(rows, list) or not rows:
                last_error = ProviderError(
                    "高德未能解析该地址，请补充省、市、区、街道或门牌号后重试。",
                    error_code="AMAP_GEOCODE_EMPTY",
                    endpoint=self.geocode_endpoint,
                    status=str(data.get("status", "")),
                    info=str(data.get("info", "")),
                    infocode=str(data.get("infocode", "")),
                    sanitized_params=self._sanitize_params(params),
                    raw_response_sanitized=self._sanitize_response(data),
                    retry_attempts=retry_attempts,
                )
                continue

            parsed = self._parse_geocode_row(rows[0], address_clean)
            parsed["retry_attempts"] = retry_attempts
            return parsed

        if last_error:
            last_error.message = "高德未能解析该地址。系统已尝试备用解析方式，请补充省、市、区、街道或门牌号后重试。"
            last_error.retry_attempts = retry_attempts
            raise last_error

        raise ProviderError(
            "高德未能解析该地址，请补充省、市、区、街道或门牌号后重试。",
            error_code="AMAP_GEOCODE_FAILED",
            endpoint=self.geocode_endpoint,
            retry_attempts=retry_attempts,
        )

    async def geocode_debug(self, address: str, city: str | None = None) -> dict[str, Any]:
        address_clean = self._clean_text(address)
        city_clean = self._normalize_city(city)
        if not address_clean:
            raise ProviderError(
                "地址不能为空，请补充省、市、区、街道或门牌号后重试。",
                error_code="AMAP_INVALID_ADDRESS",
                endpoint=self.geocode_endpoint,
                sanitized_params={},
            )

        attempts = self._geocode_attempts(address_clean, city_clean)
        results = []
        for index, attempt in enumerate(attempts, start=1):
            params = self._build_geocode_params(attempt["address"], attempt.get("city"))
            data = await self._get_raw(self.geocode_endpoint, params)
            results.append(self._attempt_summary(index, attempt["label"], params, data))
        return {"provider": "amap", "endpoint": self.geocode_endpoint, "attempts": results}

    async def search_nearby(self, longitude, latitude, radius, categories):
        if self.mock:
            rows = [
                {
                    "source": "amap",
                    "provider_record_id": "mock-competitor-1",
                    "name": "示例电竞网咖",
                    "category": "竞品",
                    "type_code": "080000",
                    "address": "候选点附近",
                    "longitude": longitude + 0.0005,
                    "latitude": latitude + 0.0005,
                    "distance_m": 90,
                    "phone": None,
                    "business_hours": None,
                    "business_area": None,
                    "observed_at": datetime.now(timezone.utc),
                    "fetched_at": datetime.now(timezone.utc),
                    "confidence": 0.6,
                    "is_estimated": True,
                    "needs_verification": True,
                    "raw_data": {"mock": True, "query_group": "竞品"},
                },
                {
                    "source": "amap",
                    "provider_record_id": "mock-school-1",
                    "name": "示例中学",
                    "category": "中学",
                    "type_code": "141200",
                    "address": "候选点附近",
                    "longitude": longitude + 0.001,
                    "latitude": latitude + 0.001,
                    "distance_m": 160,
                    "phone": None,
                    "business_hours": None,
                    "business_area": None,
                    "observed_at": datetime.now(timezone.utc),
                    "fetched_at": datetime.now(timezone.utc),
                    "confidence": 0.6,
                    "is_estimated": True,
                    "needs_verification": True,
                    "raw_data": {"mock": True, "query_group": "敏感场所"},
                },
                {
                    "source": "amap",
                    "provider_record_id": "mock-traffic-1",
                    "name": "示例地铁站",
                    "category": "交通",
                    "type_code": "150500",
                    "address": "候选点附近",
                    "longitude": longitude + 0.0015,
                    "latitude": latitude + 0.0015,
                    "distance_m": 320,
                    "phone": None,
                    "business_hours": None,
                    "business_area": None,
                    "observed_at": datetime.now(timezone.utc),
                    "fetched_at": datetime.now(timezone.utc),
                    "confidence": 0.6,
                    "is_estimated": True,
                    "needs_verification": True,
                    "raw_data": {"mock": True, "query_group": "交通"},
                },
                {
                    "source": "amap",
                    "provider_record_id": "mock-commercial-1",
                    "name": "示例餐饮店",
                    "category": "商业配套",
                    "type_code": "050000",
                    "address": "候选点附近",
                    "longitude": longitude + 0.002,
                    "latitude": latitude + 0.002,
                    "distance_m": 450,
                    "phone": None,
                    "business_hours": None,
                    "business_area": None,
                    "observed_at": datetime.now(timezone.utc),
                    "fetched_at": datetime.now(timezone.utc),
                    "confidence": 0.6,
                    "is_estimated": True,
                    "needs_verification": True,
                    "raw_data": {"mock": True, "query_group": "商业配套"},
                },
                {
                    "source": "amap",
                    "provider_record_id": "mock-population-1",
                    "name": "示例住宅小区",
                    "category": "住宅小区",
                    "type_code": "120300",
                    "address": "候选点附近",
                    "longitude": longitude + 0.0025,
                    "latitude": latitude + 0.0025,
                    "distance_m": 680,
                    "phone": None,
                    "business_hours": None,
                    "business_area": None,
                    "observed_at": datetime.now(timezone.utc),
                    "fetched_at": datetime.now(timezone.utc),
                    "confidence": 0.6,
                    "is_estimated": True,
                    "needs_verification": True,
                    "raw_data": {"mock": True, "query_group": "人口代理"},
                },
            ]
            self.last_poi_diagnostics = {
                "provider": "amap",
                "mock": True,
                "queries": [{"group": group, "raw_count": 1, "saved_count": 1} for group, _ in self.poi_query_groups],
                "raw_return_count": len(rows),
                "saved_count": len(rows),
                "duplicate_count": 0,
                "invalid_location_count": 0,
                "filtered_out_count": 0,
            }
            return rows

        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        raw_return_count = 0
        duplicate_count = 0
        invalid_location_count = 0
        queries = []

        for group, keywords_list in self._poi_query_groups(categories):
            keywords = "|".join(keywords_list)
            data = await self._get(
                "place/around",
                {
                    "location": f"{longitude},{latitude}",
                    "radius": radius,
                    "keywords": keywords,
                    "offset": 25,
                    "page": 1,
                    "extensions": "all",
                    "output": "JSON",
                    "citylimit": "false",
                    "sortrule": "distance",
                },
            )
            pois = data.get("pois", [])
            if not isinstance(pois, list):
                pois = []
            group_raw = len(pois)
            group_saved = 0
            raw_return_count += group_raw
            for poi in pois:
                provider_id = str(poi.get("id") or "")
                if not provider_id:
                    invalid_location_count += 1
                    continue
                if provider_id in seen:
                    duplicate_count += 1
                    continue
                try:
                    lng, lat = map(float, poi["location"].split(","))
                except (KeyError, ValueError):
                    invalid_location_count += 1
                    continue
                seen.add(provider_id)
                raw_data = dict(poi)
                raw_data["_query_group"] = group
                out.append(
                    {
                        "source": "amap",
                        "provider_record_id": provider_id,
                        "name": poi.get("name", "未知"),
                        "category": self._category(poi),
                        "type_code": poi.get("typecode"),
                        "address": self._text(poi.get("address")),
                        "longitude": lng,
                        "latitude": lat,
                        "distance_m": int(poi["distance"])
                        if str(poi.get("distance", "")).isdigit()
                        else None,
                        "phone": self._text(poi.get("tel")),
                        "business_hours": (poi.get("biz_ext") or {}).get("open_time"),
                        "business_area": self._text(poi.get("business_area")),
                        "observed_at": datetime.now(timezone.utc),
                        "fetched_at": datetime.now(timezone.utc),
                        "confidence": 0.75,
                        "is_estimated": False,
                        "needs_verification": False,
                        "raw_data": raw_data,
                    }
                )
                group_saved += 1
            queries.append(
                {
                    "group": group,
                    "keywords": keywords_list,
                    "raw_count": group_raw,
                    "saved_count": group_saved,
                    "status": str(data.get("status", "")),
                    "info": str(data.get("info", "")),
                    "infocode": str(data.get("infocode", "")),
                    "count": str(data.get("count", "")),
                }
            )
        self.last_poi_diagnostics = {
            "provider": "amap",
            "endpoint": "place/around",
            "radius": radius,
            "query_count": len(queries),
            "queries": queries,
            "raw_return_count": raw_return_count,
            "saved_count": len(out),
            "duplicate_count": duplicate_count,
            "invalid_location_count": invalid_location_count,
            "filtered_out_count": duplicate_count + invalid_location_count,
            "params_policy": {
                "request_mode": "grouped_keywords",
                "offset": 25,
                "citylimit": False,
                "sortrule": "distance",
            },
        }
        return out

    async def get_place_detail(self, provider_place_id):
        return await self._get(
            "place/detail",
            {"id": provider_place_id, "extensions": "all", "output": "JSON"},
        )

    def _api_error(
        self,
        endpoint: str,
        params: dict[str, Any],
        data: dict[str, Any],
        *,
        retry_attempts: list[dict[str, Any]] | None = None,
    ) -> ProviderError:
        info = str(data.get("info", "unknown error"))
        infocode = str(data.get("infocode", ""))
        code = self._error_code(info, infocode)
        if infocode == "30001":
            message = "高德服务响应失败，可能与地址格式、城市参数或高德服务侧响应有关。系统已尝试备用解析方式，请检查地址是否完整。"
        elif code == "AMAP_KEY_PERMISSION":
            message = "高德 Key 类型或接口权限可能不正确，请确认使用的是 Web 服务 API Key。"
        else:
            message = f"Amap API failed: {info} ({infocode})"
        return ProviderError(
            message,
            error_code=code,
            endpoint=endpoint,
            status=str(data.get("status", "")),
            info=info,
            infocode=infocode,
            sanitized_params=self._sanitize_params(params),
            raw_response_sanitized=self._sanitize_response(data),
            retry_attempts=retry_attempts or [],
        )

    @staticmethod
    def _error_code(info: str, infocode: str) -> str:
        key_indicators = {
            "10001",
            "10002",
            "10003",
            "10008",
            "10009",
            "10010",
            "10011",
            "10012",
            "10013",
            "10014",
            "10015",
            "10016",
            "10017",
            "10019",
            "10020",
            "10021",
            "10022",
            "10023",
            "10026",
            "10027",
            "10028",
            "10029",
        }
        if infocode in key_indicators or "KEY" in info.upper() or "USERKEY" in info.upper():
            return "AMAP_KEY_PERMISSION"
        if infocode == "30001" or info == "ENGINE_RESPONSE_DATA_ERROR":
            return "AMAP_ENGINE_RESPONSE_DATA_ERROR"
        return "AMAP_API_ERROR"

    @staticmethod
    def _should_fallback(data: dict[str, Any]) -> bool:
        return data.get("infocode") == "30001" or data.get("count") in (0, "0", None)

    @classmethod
    def _build_geocode_params(cls, address: str, city: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {"address": address, "output": "JSON"}
        city_clean = cls._normalize_city(city)
        if city_clean:
            params["city"] = city_clean
        return params

    @classmethod
    def _geocode_attempts(cls, address: str, city: str | None) -> list[dict[str, str]]:
        attempts = [{"label": "primary", "address": address}]
        if city:
            attempts[0]["city"] = city
            attempts.append({"label": "without_city", "address": address})
            combined = address if cls._contains_city(address, city) else f"{city}{address}"
            attempts.append({"label": "city_plus_address_without_city", "address": combined})
        return attempts

    @staticmethod
    def _contains_city(address: str, city: str) -> bool:
        return city in address or city.rstrip("市") in address

    @staticmethod
    def _clean_text(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _normalize_city(cls, value: Any) -> str | None:
        city = cls._clean_text(value)
        if not city:
            return None
        invalid = {"undefined", "null", "none", "全部", "全国", "请选择", "不限", "all"}
        if city.lower() in invalid or city in invalid:
            return None
        district_suffixes = ("区", "县", "旗", "镇", "乡", "街道", "开发区", "新区", "园区")
        city_suffixes = ("市", "自治州", "地区", "盟")
        if city.endswith(district_suffixes) and not city.endswith(city_suffixes):
            return None
        return city

    @staticmethod
    def _parse_geocode_row(row: Any, fallback_address: str) -> dict[str, Any]:
        if not isinstance(row, dict):
            raise ProviderError(
                "高德返回的 geocodes 结构异常，请补充地址后重试。",
                error_code="AMAP_RESPONSE_SCHEMA_ERROR",
                endpoint=AmapDataProvider.geocode_endpoint,
            )
        location = row.get("location")
        if not isinstance(location, str) or "," not in location:
            raise ProviderError(
                "高德返回的经纬度为空或格式异常，请补充地址后重试。",
                error_code="AMAP_RESPONSE_SCHEMA_ERROR",
                endpoint=AmapDataProvider.geocode_endpoint,
            )
        try:
            lng, lat = map(float, location.split(",", 1))
        except ValueError as exc:
            raise ProviderError(
                "高德返回的经纬度格式异常，请补充地址后重试。",
                error_code="AMAP_RESPONSE_SCHEMA_ERROR",
                endpoint=AmapDataProvider.geocode_endpoint,
            ) from exc
        return {
            "formatted_address": AmapDataProvider._text(row.get("formatted_address"))
            or fallback_address,
            "district": AmapDataProvider._text(row.get("district"))
            or AmapDataProvider._text(row.get("adcode")),
            "longitude": lng,
            "latitude": lat,
            "coordinate_system": "GCJ02",
            "provider": "amap",
        }

    @classmethod
    def _attempt_summary(
        cls,
        index: int,
        label: str,
        params: dict[str, Any],
        data: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "attempt": index,
            "label": label,
            "sanitized_params": cls._sanitize_params(params),
            "status": str(data.get("status", "")),
            "info": str(data.get("info", "")),
            "infocode": str(data.get("infocode", "")),
            "count": str(data.get("count", "")),
            "geocodes": cls._geocode_brief(data.get("geocodes")),
        }

    @staticmethod
    def _sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
        return {k: ("***" if k.lower() == "key" else v) for k, v in params.items()}

    @classmethod
    def _sanitize_response(cls, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            return {"raw_type": type(data).__name__}
        return {
            "status": data.get("status"),
            "info": data.get("info"),
            "infocode": data.get("infocode"),
            "count": data.get("count"),
            "geocodes": cls._geocode_brief(data.get("geocodes")),
        }

    @staticmethod
    def _geocode_brief(rows: Any) -> list[dict[str, Any]]:
        if not isinstance(rows, list):
            return []
        brief = []
        for row in rows[:3]:
            if not isinstance(row, dict):
                continue
            brief.append(
                {
                    "formatted_address": row.get("formatted_address"),
                    "province": row.get("province"),
                    "city": row.get("city"),
                    "district": row.get("district"),
                    "location": row.get("location"),
                    "level": row.get("level"),
                }
            )
        return brief

    @staticmethod
    def _text(value: Any) -> str | None:
        return value if isinstance(value, str) and value else None

    @classmethod
    def _poi_query_groups(cls, categories: list[str]):
        requested = {str(item).strip() for item in categories or [] if str(item).strip()}
        if not requested:
            return cls.poi_query_groups
        selected = []
        for group, keywords in cls.poi_query_groups:
            if any(keyword in requested for keyword in keywords):
                selected.append((group, keywords))
        return selected or cls.poi_query_groups

    @staticmethod
    def _category(poi: dict[str, Any]):
        text = f"{poi.get('name', '')} {poi.get('type', '')}"
        groups = [
            ("竞品", ["网吧", "网咖", "电竞", "电竞酒店"]),
            ("小学", ["小学"]),
            ("中学", ["中学"]),
            ("幼儿园", ["幼儿园"]),
            ("敏感场所", ["政府机构", "政府机关", "医院"]),
            ("交通", ["地铁", "公交", "停车"]),
            ("商业配套", ["商场", "餐饮", "美食", "奶茶", "便利店", "KTV", "酒吧", "台球", "电影院", "电影", "密室", "酒店"]),
            ("大学", ["大学", "学院"]),
            ("中职", ["中职", "职业中学", "职业学校"]),
            ("技校", ["技校", "技工学校"]),
            ("住宅小区", ["住宅小区", "小区", "居民区"]),
            ("公寓", ["公寓"]),
            ("写字楼", ["写字楼", "商务楼", "办公楼"]),
        ]
        return next((group for group, keys in groups if any(key in text for key in keys)), "其他")
