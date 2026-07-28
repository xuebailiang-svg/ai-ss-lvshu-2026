from __future__ import annotations

import asyncio

from app.data_model.schemas import CompetitorData, POIData, RentData
from app.data_source import (
    AmapProvider,
    DataSourceName,
    DataSourceRequest,
    ManualUploadProvider,
    ProviderAvailability,
    ProviderCallStatus,
    build_default_registry,
)
from app.map_data.amap_client import AmapMapDataClient
from app.core.config import get_settings


def test_default_registry_loads_provider_statuses():
    registry = build_default_registry(amap_client=AmapMapDataClient(key="", mock=False))

    statuses = {item.source: item.availability for item in registry.list()}

    assert registry.get("manual").source == DataSourceName.manual
    assert statuses[DataSourceName.amap] == ProviderAvailability.not_configured
    assert statuses[DataSourceName.manual] == ProviderAvailability.available
    assert statuses[DataSourceName.crawler] == ProviderAvailability.disabled
    assert statuses[DataSourceName.third_party] == ProviderAvailability.not_configured


def test_manual_upload_provider_outputs_unified_models():
    provider = ManualUploadProvider()

    competitors = asyncio.run(
        provider.get_competitors(DataSourceRequest(records=[{"名称": "测试电竞馆", "距离": "500"}]))
    )
    rents = asyncio.run(
        provider.get_rent(DataSourceRequest(records=[{"地址": "测试商铺", "面积": "500", "月租金": "30000"}]))
    )

    assert competitors.status == ProviderCallStatus.success
    assert isinstance(competitors.items[0], CompetitorData)
    assert competitors.items[0].source == "manual"
    assert isinstance(rents.items[0], RentData)
    assert rents.items[0].monthly_rent == 30000


def test_amap_provider_reuses_existing_client_and_mapper():
    class FakeAmapClient:
        key = "test"
        mock = False

        async def collect_pois(self, **kwargs):
            return [
                {
                    "category": "transport",
                    "sub_category": "地铁",
                    "name": "测试地铁站",
                    "location": "108.9,34.2",
                    "distance": "120",
                }
            ], {"queries": [], "failed_keywords": []}

    provider = AmapProvider(FakeAmapClient())
    result = asyncio.run(
        provider.get_poi(
            DataSourceRequest(city="西安市", longitude=108.9, latitude=34.2, radius_meters=1000)
        )
    )

    assert result.status == ProviderCallStatus.success
    assert isinstance(result.items[0], POIData)
    assert result.items[0].source == "amap"
    assert result.items[0].category == "transport"


def test_unsupported_provider_method_returns_clear_status():
    provider = AmapProvider(AmapMapDataClient(key="test", mock=False))

    result = asyncio.run(provider.get_rent(DataSourceRequest()))

    assert result.status == ProviderCallStatus.unsupported
    assert result.items == []


def test_data_source_status_api_returns_all_registered_providers(client):
    response = client.get("/api/data-sources/status")

    assert response.status_code == 200
    items = {item["name"]: item for item in response.json()["items"]}
    assert set(items) == {
        "amap",
        "manual",
        "manual_rent",
        "amap_competitor",
        "crawler_competitor",
        "crawler_supporting",
        "crawler_rent",
        "amap_supporting",
        "crawler",
        "third_party",
    }
    assert items["amap"]["status"] == "available"
    assert items["amap"]["capabilities"] == ["poi"]
    assert items["amap"]["check_supported"] is True
    assert items["manual"]["status"] == "available"
    assert "competitor" in items["manual"]["capabilities"]
    assert items["manual_rent"]["status"] == "available"
    assert items["manual_rent"]["capabilities"] == ["rent"]
    assert items["crawler"]["status"] == "disabled"
    assert items["crawler"]["check_supported"] is False
    assert items["amap_competitor"]["status"] == "available"
    assert items["amap_competitor"]["capabilities"] == ["competitor"]
    assert items["crawler_competitor"]["status"] == "disabled"
    assert items["crawler_supporting"]["status"] == "disabled"
    assert items["crawler_rent"]["status"] == "disabled"
    assert items["amap_supporting"]["status"] == "available"
    assert items["amap_supporting"]["capabilities"] == ["food", "entertainment", "night_economy"]
    assert items["third_party"]["status"] == "not_configured"
    assert all(item["description"] for item in items.values())


def test_amap_connectivity_returns_not_configured(client, monkeypatch):
    monkeypatch.setenv("AMAP_MOCK", "false")
    monkeypatch.delenv("AMAP_WEB_SERVICE_KEY", raising=False)
    get_settings.cache_clear()

    response = client.post("/api/data-sources/amap/check")

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is False
    assert body["reachable"] is False
    assert body["status"] == "not_configured"
    assert body["message"] == "AMAP_WEB_SERVICE_KEY未配置"


def test_manual_connectivity_is_local_and_available(client):
    response = client.post("/api/data-sources/manual/check")

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["reachable"] is True
    assert body["status"] == "ok"
    assert "本地能力" in body["message"]


def test_crawler_connectivity_is_disabled(client):
    response = client.post("/api/data-sources/crawler_competitor/check")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "disabled"
    assert body["message"] == "爬虫能力未启用"


def test_crawler_connectivity_detects_missing_playwright_runtime(client, monkeypatch):
    monkeypatch.setenv("CRAWLER_ENABLED", "true")
    get_settings.cache_clear()
    monkeypatch.setattr("app.data_source.crawler.crawl4ai_client.ensure_crawl4ai_available", lambda: None)

    def fail_runtime():
        raise RuntimeError("Playwright Chromium 未安装")

    monkeypatch.setattr("app.data_source.crawler.crawl4ai_client.ensure_playwright_chromium_available", fail_runtime)

    response = client.post("/api/data-sources/crawler_competitor/check")

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["reachable"] is False
    assert body["status"] == "failed"
    assert "Playwright Chromium 未安装" in body["message"]


def test_unknown_provider_connectivity_returns_404(client):
    response = client.post("/api/data-sources/unknown/check")

    assert response.status_code == 404


def test_mock_amap_connectivity_returns_ok(client, monkeypatch):
    monkeypatch.setenv("AMAP_MOCK", "true")
    monkeypatch.delenv("AMAP_WEB_SERVICE_KEY", raising=False)
    get_settings.cache_clear()

    response = client.post("/api/data-sources/amap/check")

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["reachable"] is True
    assert body["status"] == "ok"
    assert isinstance(body["latency_ms"], int)
    assert body["checked_at"]
