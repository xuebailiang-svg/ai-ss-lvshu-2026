import asyncio

import httpx
import pytest

from app.providers.amap import AmapDataProvider, ProviderError


def run(coro):
    return asyncio.run(coro)


def response(status="1", *, info="OK", infocode="10000", count="1", geocodes=None):
    return httpx.Response(
        200,
        json={
            "status": status,
            "info": info,
            "infocode": infocode,
            "count": count,
            "geocodes": geocodes if geocodes is not None else [
                {
                    "formatted_address": "北京市朝阳区阜通东大街6号",
                    "province": "北京市",
                    "city": "北京市",
                    "district": "朝阳区",
                    "location": "116.480000,39.990000",
                    "level": "门牌号",
                }
            ],
        },
    )


def test_address_empty_does_not_call_amap():
    calls = []

    def handler(req):
        calls.append(req)
        return response()

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ProviderError) as exc:
                await AmapDataProvider("secret", client=client).geocode("   ", "北京市")
        assert exc.value.error_code == "AMAP_INVALID_ADDRESS"

    run(scenario())
    assert calls == []


def test_city_empty_is_not_sent():
    seen = []

    def handler(req):
        seen.append(dict(req.url.params))
        return response()

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await AmapDataProvider("secret", client=client).geocode("朝阳区阜通东大街6号", "")

    run(scenario())
    assert "city" not in seen[0]
    assert seen[0]["address"] == "朝阳区阜通东大街6号"
    assert seen[0]["output"] == "JSON"


def test_district_or_development_zone_city_is_ignored_without_error():
    seen = []

    def handler(req):
        seen.append(dict(req.url.params))
        return response()

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await AmapDataProvider("secret", client=client).geocode("小寨西路", "雁塔区")
            await AmapDataProvider("secret", client=client).geocode("科技二路", "高新开发区")

    run(scenario())
    assert all("city" not in params for params in seen)


def test_chinese_address_is_passed_via_params_for_client_encoding():
    seen = []

    def handler(req):
        seen.append(req)
        return response()

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await AmapDataProvider("secret", client=client).geocode("朝阳区阜通东大街6号", "北京市")

    run(scenario())
    params = dict(seen[0].url.params)
    assert params["address"] == "朝阳区阜通东大街6号"
    assert params["city"] == "北京市"
    assert params["key"] == "secret"


def test_successful_geocode_is_parsed():
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: response())) as client:
            data = await AmapDataProvider("secret", client=client).geocode("朝阳区阜通东大街6号", "北京市")
        assert data["formatted_address"] == "北京市朝阳区阜通东大街6号"
        assert data["district"] == "朝阳区"
        assert data["longitude"] == 116.48
        assert data["latitude"] == 39.99
        assert data["coordinate_system"] == "GCJ02"

    run(scenario())


def test_30001_triggers_fallback():
    seen = []

    def handler(req):
        seen.append(dict(req.url.params))
        if len(seen) == 1:
            return response(
                "0",
                info="ENGINE_RESPONSE_DATA_ERROR",
                infocode="30001",
                count="0",
                geocodes=[],
            )
        return response()

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            data = await AmapDataProvider("secret", client=client).geocode("雁塔区小寨西路", "西安市")
        assert data["retry_attempts"][0]["infocode"] == "30001"

    run(scenario())
    assert len(seen) == 2
    assert seen[0]["city"] == "西安市"
    assert "city" not in seen[1]


def test_fallback_success_records_retry_attempts():
    def handler(req):
        params = dict(req.url.params)
        if params.get("city"):
            return response(count="0", geocodes=[])
        return response()

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            data = await AmapDataProvider("secret", client=client).geocode("雁塔区小寨西路", "西安市")
        assert len(data["retry_attempts"]) == 2
        assert data["retry_attempts"][0]["count"] == "0"
        assert data["retry_attempts"][1]["status"] == "1"

    run(scenario())


def test_fallback_failure_returns_clear_error():
    def handler(req):
        return response(count="0", geocodes=[])

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ProviderError) as exc:
                await AmapDataProvider("secret", client=client).geocode("不存在的地址", "西安市")
        assert exc.value.error_code == "AMAP_GEOCODE_EMPTY"
        assert "补充省、市、区、街道或门牌号" in exc.value.message
        assert len(exc.value.retry_attempts) == 3

    run(scenario())


def test_missing_key_returns_configuration_error():
    async def scenario():
        with pytest.raises(ProviderError) as exc:
            await AmapDataProvider("").geocode("朝阳区阜通东大街6号", "北京市")
        assert exc.value.error_code == "AMAP_KEY_MISSING"
        assert "AMAP_WEB_SERVICE_KEY" in exc.value.message

    run(scenario())


def test_rate_limit_error_is_not_key_permission():
    assert AmapDataProvider._error_code("CUQPS_HAS_EXCEEDED_THE_LIMIT", "10021") == "AMAP_RATE_LIMIT"
    error = AmapDataProvider("secret")._api_error(
        "place/around",
        {"keywords": "公交车站"},
        {"status": "0", "info": "CUQPS_HAS_EXCEEDED_THE_LIMIT", "infocode": "10021"},
    )
    assert error.error_code == "AMAP_RATE_LIMIT"
    assert "Key 类型" not in error.message
    assert "限流" in error.message


def test_search_nearby_records_rate_limited_keyword(monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr("app.providers.amap.provider.asyncio.sleep", no_sleep)
    calls = []

    def handler(req):
        params = dict(req.url.params)
        calls.append(params)
        if params.get("keywords") == "地铁站":
            return httpx.Response(200, json={
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "count": "1",
                "pois": [{
                    "id": "metro-1",
                    "name": "测试地铁站",
                    "type": "地铁站",
                    "typecode": "150500",
                    "address": "测试地址",
                    "location": "108.1,34.1",
                    "distance": "120",
                }],
            })
        return httpx.Response(200, json={
            "status": "0",
            "info": "CUQPS_HAS_EXCEEDED_THE_LIMIT",
            "infocode": "10021",
            "count": "0",
            "pois": [],
        })

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = AmapDataProvider("secret", client=client)
            rows = await provider.search_nearby(108.0, 34.0, 3000, ["地铁站", "公交车站"])
        assert len(rows) == 1
        assert rows[0]["name"] == "测试地铁站"
        assert len([call for call in calls if call.get("keywords") == "公交车站"]) == 3
        diagnostics = provider.last_poi_diagnostics
        assert diagnostics["saved_count"] == 1
        assert diagnostics["failed_keywords"][0]["keyword"] == "公交车站"
        assert diagnostics["failed_keywords"][0]["error_code"] == "AMAP_RATE_LIMIT"
        assert any(item["status"] == "success" and item["keyword"] == "地铁站" for item in diagnostics["queries"])
        assert any(item["status"] == "failed" and item["keyword"] == "公交车站" for item in diagnostics["queries"])

    run(scenario())


def test_error_payload_never_contains_real_key():
    def handler(req):
        return response(
            "0",
            info="ENGINE_RESPONSE_DATA_ERROR",
            infocode="30001",
            count="0",
            geocodes=[],
        )

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ProviderError) as exc:
                await AmapDataProvider("real-secret-key", client=client).geocode("不存在的地址", "西安市")
        payload = str(exc.value.to_dict())
        assert "real-secret-key" not in payload
        assert "key" not in exc.value.sanitized_params or exc.value.sanitized_params["key"] == "***"

    run(scenario())
