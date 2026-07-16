from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.data_model.schemas import CompetitorData
from app.data_source import DataSourceRequest, ProviderCallStatus, build_default_registry
from app.data_source.amap import AmapProvider
from app.data_source.competitor import AmapCompetitorProvider
from app.map_data.amap_client import AmapMapDataClient


class FakeAmapClient:
    key = "test"
    mock = False

    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows
        self.last_kwargs: dict[str, Any] = {}

    async def collect_pois(self, **kwargs):
        self.last_kwargs = kwargs
        return self.rows, {"queries": [], "failed_keywords": []}

    async def check_connectivity(self, **kwargs):
        return {"status": "1", "info": "OK", "infocode": "10000"}


def competitor_rows() -> list[dict[str, Any]]:
    return [
        {
            "category": "competitor",
            "sub_category": "电竞馆",
            "name": "测试电竞馆",
            "address": "西安市雁塔区测试路1号",
            "location": "108.95,34.22",
            "distance": "320",
            "id": "amap-competitor-1",
        }
    ]


def project_payload() -> dict[str, Any]:
    return {
        "name": "竞品采集测试项目",
        "city": "西安市",
        "district": "雁塔区",
        "address": "小寨地铁站",
        "longitude": 108.946767,
        "latitude": 34.222838,
        "radius_meters": 1000,
        "business_type": "电竞馆",
    }


def test_competitor_providers_load_from_registry():
    registry = build_default_registry(amap_client=AmapMapDataClient(key="test", mock=False))

    assert registry.get("amap_competitor").availability == "available"
    assert registry.get("amap_competitor").capabilities == ("competitor",)
    assert registry.get("crawler_competitor").availability == "disabled"


def test_amap_competitor_provider_converts_to_unified_model():
    client = FakeAmapClient(competitor_rows())
    provider = AmapCompetitorProvider(AmapProvider(client))

    result = asyncio.run(
        provider.get_competitors(
            DataSourceRequest(city="西安市", longitude=108.94, latitude=34.22, radius_meters=1000)
        )
    )

    assert result.status == ProviderCallStatus.success
    assert len(result.items) == 1
    assert isinstance(result.items[0], CompetitorData)
    assert result.items[0].name == "测试电竞馆"
    assert result.items[0].distance_meters == 320
    assert result.items[0].source == "amap"
    assert result.items[0].status == "pending_review"
    assert result.items[0].confidence == 0.9
    assert client.last_kwargs["category_keywords"] == {
        "competitor": ["电竞馆", "网吧", "网咖", "互联网服务"]
    }


def test_amap_competitor_provider_handles_empty_result():
    provider = AmapCompetitorProvider(AmapProvider(FakeAmapClient([])))

    result = asyncio.run(
        provider.get_competitors(DataSourceRequest(longitude=108.94, latitude=34.22))
    )

    assert result.status == ProviderCallStatus.success
    assert result.items == []


def test_collect_competitors_api_saves_and_updates_without_duplicates(client, monkeypatch):
    async def fake_collect_pois(self, **kwargs):
        return competitor_rows(), {"queries": [], "failed_keywords": []}

    monkeypatch.setattr(AmapMapDataClient, "collect_pois", fake_collect_pois)
    project_id = client.post("/api/projects", json=project_payload()).json()["project_id"]

    first = client.post(f"/api/projects/{project_id}/collect/competitors")
    second = client.post(f"/api/projects/{project_id}/collect/competitors")

    assert first.status_code == 200
    assert first.json()["discovered_count"] == 1
    assert first.json()["created_count"] == 1
    assert second.status_code == 200
    assert second.json()["created_count"] == 0
    assert second.json()["updated_count"] == 1
    dataset = client.get(f"/api/projects/{project_id}/dataset").json()
    assert len(dataset["competitors"]) == 1
    saved = dataset["competitors"][0]
    assert saved["name"] == "测试电竞馆"
    assert saved["source"] == "amap"
    assert saved["raw_data"]["id"] == "amap-competitor-1"
    assert saved["status"] == "pending_review"


def collect_competitor_for_review(client, monkeypatch) -> tuple[str, int]:
    async def fake_collect_pois(self, **kwargs):
        return competitor_rows(), {"queries": [], "failed_keywords": []}

    monkeypatch.setattr(AmapMapDataClient, "collect_pois", fake_collect_pois)
    project_id = client.post("/api/projects", json=project_payload()).json()["project_id"]
    client.post(f"/api/projects/{project_id}/collect/competitors")
    item = client.get(f"/api/projects/{project_id}/competitors").json()["items"][0]
    return project_id, item["id"]


def test_query_project_competitor_list(client, monkeypatch):
    project_id, competitor_id = collect_competitor_for_review(client, monkeypatch)

    response = client.get(f"/api/projects/{project_id}/competitors")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == competitor_id
    assert body["items"][0]["status"] == "pending_review"
    assert body["items"][0]["raw_category"] == "电竞馆"
    assert body["items"][0]["created_at"]


@pytest.mark.parametrize(
    ("review_status", "expected_status"),
    [
        ("confirmed", "confirmed"),
        ("rejected", "rejected"),
        ("pending_review", "pending_review"),
    ],
)
def test_review_project_competitor_status(client, monkeypatch, review_status, expected_status):
    project_id, competitor_id = collect_competitor_for_review(client, monkeypatch)

    response = client.post(
        f"/api/projects/{project_id}/competitors/{competitor_id}/review",
        json={"status": review_status},
    )

    assert response.status_code == 200
    assert response.json()["status"] == expected_status


def test_rejected_competitor_is_excluded_from_effective_stats_and_dataset(client, monkeypatch):
    project_id, competitor_id = collect_competitor_for_review(client, monkeypatch)
    client.post(
        f"/api/projects/{project_id}/competitors/{competitor_id}/review",
        json={"status": "rejected"},
    )

    project = client.get(f"/api/projects/{project_id}").json()
    quality = client.get(f"/api/projects/{project_id}/data-quality").json()
    dataset = client.get(f"/api/projects/{project_id}/dataset").json()
    review_list = client.get(f"/api/projects/{project_id}/competitors").json()

    assert project["stats"]["competitor_count"] == 0
    assert "竞品数据" in quality["missing"]
    assert dataset["competitors"] == []
    assert review_list["items"][0]["status"] == "rejected"
    assert quality["competitor_detail_quality"]["total_competitors"] == 0
    assert quality["competitor_detail_quality"]["incomplete_competitors"] == 0


def test_recollection_does_not_overwrite_manual_review_status(client, monkeypatch):
    project_id, competitor_id = collect_competitor_for_review(client, monkeypatch)
    client.post(
        f"/api/projects/{project_id}/competitors/{competitor_id}/review",
        json={"status": "confirmed"},
    )

    client.post(f"/api/projects/{project_id}/collect/competitors")
    item = client.get(f"/api/projects/{project_id}/competitors").json()["items"][0]

    assert item["status"] == "confirmed"


def test_get_and_update_competitor_detail_preserves_raw_data(client, monkeypatch):
    project_id, competitor_id = collect_competitor_for_review(client, monkeypatch)

    detail_before = client.get(f"/api/projects/{project_id}/competitors/{competitor_id}")
    update = client.put(
        f"/api/projects/{project_id}/competitors/{competitor_id}",
        json={
            "area_sqm": 680,
            "machine_count": 120,
            "cpu": "Intel i7",
            "gpu": "RTX 4060",
            "monitor": "27英寸 240Hz",
            "hour_price": 12,
            "member_price": 9,
            "business_hours": "24小时",
            "opening_date": "2024-01",
            "occupancy_rate": "80%",
            "monthly_sales": 180000,
            "annual_sales": 2100000,
            "recharge_info": "充500送100",
            "remark": "现场人工调研",
        },
    )

    assert detail_before.status_code == 200
    assert detail_before.json()["name"] == "测试电竞馆"
    assert update.status_code == 200
    body = update.json()
    assert body["area_sqm"] == 680
    assert body["machine_count"] == 120
    assert body["occupancy_rate"] == 0.8
    assert body["business_hours"] == "24小时"
    assert body["recharge_info"] == "充500送100"
    assert body["source"] == "amap"
    assert body["status"] == "pending_review"

    dataset = client.get(f"/api/projects/{project_id}/dataset").json()
    raw_data = dataset["competitors"][0]["raw_data"]
    assert raw_data["id"] == "amap-competitor-1"
    assert raw_data["manual_detail"]["business_hours"] == "24小时"
    assert raw_data["manual_detail"]["remark"] == "现场人工调研"


def test_competitor_detail_cannot_update_other_project_record(client, monkeypatch):
    first_project_id, competitor_id = collect_competitor_for_review(client, monkeypatch)
    second_project_id = client.post("/api/projects", json={**project_payload(), "name": "第二个项目"}).json()["project_id"]

    response = client.put(
        f"/api/projects/{second_project_id}/competitors/{competitor_id}",
        json={"area_sqm": 500},
    )

    assert first_project_id != second_project_id
    assert response.status_code == 404
    original = client.get(f"/api/projects/{first_project_id}/competitors/{competitor_id}").json()
    assert original["area_sqm"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {"area_sqm": -1},
        {"machine_count": 1.5},
        {"hour_price": -1},
        {"occupancy_rate": 120},
        {"monthly_sales": -1},
    ],
)
def test_competitor_detail_rejects_invalid_numeric_fields(client, monkeypatch, payload):
    project_id, competitor_id = collect_competitor_for_review(client, monkeypatch)

    response = client.put(
        f"/api/projects/{project_id}/competitors/{competitor_id}",
        json=payload,
    )

    assert response.status_code == 422


def confirm_competitor(client, project_id: str, competitor_id: int) -> None:
    response = client.post(
        f"/api/projects/{project_id}/competitors/{competitor_id}/review",
        json={"status": "confirmed"},
    )
    assert response.status_code == 200


def complete_competitor_detail_payload() -> dict[str, Any]:
    return {
        "area_sqm": 680,
        "machine_count": 120,
        "cpu": "Intel i7",
        "gpu": "RTX 4060",
        "monitor": "27英寸 240Hz",
        "hour_price": 12,
        "member_price": 9,
        "business_hours": "24小时",
        "opening_date": "2024-01",
        "occupancy_rate": 0.8,
        "monthly_sales": 180000,
        "recharge_info": "充500送100",
    }


def test_confirmed_competitor_missing_price_is_reported_by_data_quality(client, monkeypatch):
    project_id, competitor_id = collect_competitor_for_review(client, monkeypatch)
    confirm_competitor(client, project_id, competitor_id)

    response = client.get(f"/api/projects/{project_id}/data-quality")

    assert response.status_code == 200
    body = response.json()
    detail = body["competitor_detail_quality"]
    assert detail["total_competitors"] == 1
    assert detail["confirmed_competitors"] == 1
    assert detail["incomplete_competitors"] == 1
    price_summary = next(item for item in detail["missing_summary"] if item["field"] == "hour_price")
    assert price_summary == {
        "field": "hour_price",
        "label": "价格",
        "missing_count": 1,
        "importance": "important",
    }
    assert "价格" in detail["incomplete_items"][0]["missing_fields"]
    assert {"project_id", "quality_score", "missing", "warnings", "competitor_detail_quality"} <= set(body)


def test_completed_confirmed_competitor_no_longer_reports_detail_missing(client, monkeypatch):
    project_id, competitor_id = collect_competitor_for_review(client, monkeypatch)
    confirm_competitor(client, project_id, competitor_id)
    before = client.get(f"/api/projects/{project_id}/data-quality").json()

    update = client.put(
        f"/api/projects/{project_id}/competitors/{competitor_id}",
        json=complete_competitor_detail_payload(),
    )
    after = client.get(f"/api/projects/{project_id}/data-quality").json()

    assert update.status_code == 200
    assert before["competitor_detail_quality"]["incomplete_competitors"] == 1
    assert after["competitor_detail_quality"]["incomplete_competitors"] == 0
    assert after["competitor_detail_quality"]["missing_summary"] == []
    assert after["competitor_detail_quality"]["incomplete_items"] == []
    assert after["quality_score"] > before["quality_score"]
