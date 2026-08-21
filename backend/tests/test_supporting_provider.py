from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.data_model.schemas import EntertainmentData, FoodBusinessData
from app.data_source import DataSourceRequest, ProviderCallStatus, build_default_registry
from app.data_source.amap import AmapProvider
from app.data_source.supporting import AmapSupportingProvider
from app.map_data.amap_client import AmapMapDataClient


class FakeAmapClient:
    key = "test"
    mock = False

    def __init__(self, rows_by_keywords: dict[tuple[str, ...], list[dict[str, Any]]]):
        self.rows_by_keywords = rows_by_keywords

    async def collect_pois(self, **kwargs):
        category_keywords = kwargs.get("category_keywords") or {}
        keywords = tuple(next(iter(category_keywords.values()), []))
        return self.rows_by_keywords.get(keywords, []), {"queries": [], "failed_keywords": []}

    async def check_connectivity(self, **kwargs):
        return {"status": "1", "info": "OK", "infocode": "10000"}


def poi_row(category: str, sub_category: str, name: str, distance: int, identity: str) -> dict[str, Any]:
    return {
        "category": category,
        "sub_category": sub_category,
        "name": name,
        "address": "西安市雁塔区测试路",
        "location": "108.95,34.22",
        "distance": str(distance),
        "id": identity,
    }


def rows_by_keywords() -> dict[tuple[str, ...], list[dict[str, Any]]]:
    return {
        ("餐厅", "小吃", "快餐", "烧烤"): [poi_row("food", "烧烤", "测试烧烤店", 220, "food-1")],
        ("KTV", "酒吧", "台球", "密室", "电影院"): [poi_row("entertainment", "KTV", "测试KTV", 480, "ent-1")],
        ("夜市", "便利店", "超市"): [poi_row("food", "夜市", "测试夜市", 350, "night-1")],
    }


def project_payload() -> dict[str, Any]:
    return {
        "name": "周边配套测试项目",
        "city": "西安市",
        "district": "雁塔区",
        "address": "小寨地铁站",
        "longitude": 108.946767,
        "latitude": 34.222838,
        "radius_meters": 1000,
        "business_type": "电竞馆",
    }


def test_supporting_provider_loads_from_registry():
    registry = build_default_registry(amap_client=AmapMapDataClient(key="test", mock=False))

    provider = registry.get("amap_supporting")
    assert provider.availability == "available"
    assert provider.capabilities == ("food", "entertainment", "night_economy")


def test_amap_supporting_provider_converts_poi_categories():
    provider = AmapSupportingProvider(AmapProvider(FakeAmapClient(rows_by_keywords())))
    request = DataSourceRequest(city="西安市", longitude=108.94, latitude=34.22, radius_meters=1000)

    food = asyncio.run(provider.get_food(request))
    entertainment = asyncio.run(provider.get_entertainment(request))
    night = asyncio.run(provider.get_night_economy(request))

    assert food.status == ProviderCallStatus.success
    assert isinstance(food.items[0], FoodBusinessData)
    assert food.items[0].name == "测试烧烤店"
    assert food.items[0].raw_data["address"] == "西安市雁塔区测试路"
    assert entertainment.status == ProviderCallStatus.success
    assert isinstance(entertainment.items[0], EntertainmentData)
    assert entertainment.items[0].type == "ktv"
    assert night.items[0].raw_data["supporting_group"] == "night_economy"
    assert night.items[0].night_business is True


def test_collect_supporting_api_saves_unified_data_without_duplicates(client, monkeypatch):
    async def fake_collect_pois(self, **kwargs):
        category_keywords = kwargs.get("category_keywords") or {}
        keywords = tuple(next(iter(category_keywords.values()), []))
        return rows_by_keywords().get(keywords, []), {"queries": [], "failed_keywords": []}

    monkeypatch.setattr(AmapMapDataClient, "collect_pois", fake_collect_pois)
    project_id = client.post("/api/projects", json=project_payload()).json()["project_id"]

    first = client.post(f"/api/projects/{project_id}/collect/supporting")
    second = client.post(f"/api/projects/{project_id}/collect/supporting")

    assert first.status_code == 200
    assert first.json()["success"] is True
    assert first.json()["food_count"] == 1
    assert first.json()["entertainment_count"] == 1
    assert first.json()["night_business_count"] == 1
    assert first.json()["supporting_analysis"]["night_activity_level"] == "low"
    assert first.json()["created_count"] == 3
    assert second.json()["created_count"] == 0
    assert second.json()["updated_count"] == 3

    dataset = client.get(f"/api/projects/{project_id}/dataset").json()
    assert len(dataset["food_businesses"]) == 2
    assert len(dataset["entertainments"]) == 1
    assert dataset["food_businesses"][0]["source"] == "amap"
    assert dataset["entertainments"][0]["source"] == "amap"
    assert dataset["food_businesses"][0]["raw_data"]["address"] == "西安市雁塔区测试路"


def test_collect_supporting_api_returns_zero_for_no_data(client, monkeypatch):
    async def fake_collect_pois(self, **kwargs):
        return [], {"queries": [], "failed_keywords": []}

    monkeypatch.setattr(AmapMapDataClient, "collect_pois", fake_collect_pois)
    project_id = client.post("/api/projects", json=project_payload()).json()["project_id"]

    response = client.post(f"/api/projects/{project_id}/collect/supporting")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["food_count"] == 0
    assert response.json()["entertainment_count"] == 0
    assert response.json()["night_business_count"] == 0
    assert response.json()["supporting_analysis"]["night_activity_level"] == "none"
    assert response.json()["message"] == "未发现周边配套数据"


def test_collect_supporting_unknown_project_returns_404(client):
    response = client.post("/api/projects/not-exists/collect/supporting")

    assert response.status_code == 404


def test_supporting_manual_audit_tracks_unknown_fields(client, monkeypatch):
    project_id, item = confirmed_supporting_item(client, monkeypatch, "food")
    response = client.put(
        f"/api/projects/{project_id}/supporting/{item['id']}",
        json={
            "business_hours": "18:00-02:00",
            "night_operation": True,
            "remark": "现场核实",
            "unknown_fields": ["opening_date"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["manual_detail"]["business_hours"] == "18:00-02:00"
    assert body["manual_meta"]["field_sources"]["business_hours"] == "manual"
    assert body["manual_meta"]["field_sources"]["opening_date"] == "manual_unknown"
    assert body["manual_meta"]["history_count"] >= 3


def collect_supporting_for_review(client, monkeypatch) -> tuple[str, dict[str, Any]]:
    async def fake_collect_pois(self, **kwargs):
        category_keywords = kwargs.get("category_keywords") or {}
        keywords = tuple(next(iter(category_keywords.values()), []))
        return rows_by_keywords().get(keywords, []), {"queries": [], "failed_keywords": []}

    monkeypatch.setattr(AmapMapDataClient, "collect_pois", fake_collect_pois)
    project_id = client.post("/api/projects", json=project_payload()).json()["project_id"]
    client.post(f"/api/projects/{project_id}/collect/supporting")
    body = client.get(f"/api/projects/{project_id}/supporting").json()
    return project_id, body


def test_query_supporting_list_groups_results_and_keeps_candidates_pending(client, monkeypatch):
    project_id, body = collect_supporting_for_review(client, monkeypatch)

    assert body["total"] == 3
    assert body["effective_count"] == 0
    assert {item["category"] for item in body["items"]} == {"food", "entertainment", "night_business"}
    assert all(item["status"] == "pending_review" for item in body["items"])
    assert all(item["address"] == "西安市雁塔区测试路" for item in body["items"])
    assert body["stats"]["food"]["pending_review"] == 1
    assert body["stats"]["entertainment"]["pending_review"] == 1
    assert body["stats"]["night_business"]["pending_review"] == 1
    assert all(":" in item["id"] for item in body["items"])

@pytest.mark.parametrize("review_status", ["confirmed", "rejected", "pending_review"])
def test_review_supporting_status(client, monkeypatch, review_status):
    project_id, body = collect_supporting_for_review(client, monkeypatch)
    item = body["items"][0]

    response = client.post(
        f"/api/projects/{project_id}/supporting/{item['id']}/review",
        json={"status": review_status},
    )

    assert response.status_code == 200
    assert response.json()["id"] == item["id"]
    assert response.json()["status"] == review_status
    refreshed = client.get(f"/api/projects/{project_id}/supporting").json()
    refreshed_item = next(row for row in refreshed["items"] if row["id"] == item["id"])
    assert refreshed_item["status"] == review_status


def test_rejected_supporting_item_is_excluded_from_effective_stats(client, monkeypatch):
    project_id, body = collect_supporting_for_review(client, monkeypatch)
    item = body["items"][0]
    category = item["category"]

    confirmed = client.post(
        f"/api/projects/{project_id}/supporting/{item['id']}/review",
        json={"status": "confirmed"},
    )
    after_confirm = client.get(f"/api/projects/{project_id}/supporting").json()
    rejected = client.post(
        f"/api/projects/{project_id}/supporting/{item['id']}/review",
        json={"status": "rejected"},
    )
    after_reject = client.get(f"/api/projects/{project_id}/supporting").json()

    assert confirmed.status_code == 200
    assert after_confirm["effective_count"] == 1
    assert after_confirm["stats"][category]["confirmed"] == 1
    assert rejected.status_code == 200
    assert after_reject["effective_count"] == 0
    assert after_reject["stats"][category]["confirmed"] == 0
    assert after_reject["stats"][category]["rejected"] == 1
    assert after_reject["stats"][category]["total"] == 1
    quality = client.get(f"/api/projects/{project_id}/data-quality").json()
    assert quality["supporting_detail_quality"]["total_confirmed"] == 0


def confirmed_supporting_item(client, monkeypatch, category: str) -> tuple[str, dict[str, Any]]:
    project_id, body = collect_supporting_for_review(client, monkeypatch)
    item = next(row for row in body["items"] if row["category"] == category)
    response = client.post(
        f"/api/projects/{project_id}/supporting/{item['id']}/review",
        json={"status": "confirmed"},
    )
    assert response.status_code == 200
    return project_id, response.json()


def test_get_and_update_food_supporting_detail_preserves_amap_raw_data(client, monkeypatch):
    project_id, item = confirmed_supporting_item(client, monkeypatch, "food")

    before = client.get(f"/api/projects/{project_id}/supporting/{item['id']}")
    update = client.put(
        f"/api/projects/{project_id}/supporting/{item['id']}",
        json={
            "business_hours": "18:00-03:00",
            "opening_date": "2020",
            "food_type": "烧烤",
            "night_operation": True,
            "remark": "晚上客流较多",
        },
    )
    after = client.get(f"/api/projects/{project_id}/supporting/{item['id']}")

    assert before.status_code == 200
    assert before.json()["manual_detail"] == {
        "business_hours": None,
        "opening_date": None,
        "remark": None,
        "food_type": None,
        "entertainment_type": None,
        "night_operation": None,
        "is_24_hours": None,
        "night_flow_remark": None,
    }
    assert update.status_code == 200
    assert update.json()["manual_detail"]["food_type"] == "烧烤"
    assert update.json()["manual_detail"]["night_operation"] is True
    assert update.json()["detail_completed"] is True
    assert after.json()["manual_detail"]["business_hours"] == "18:00-03:00"

    dataset = client.get(f"/api/projects/{project_id}/dataset").json()
    saved = next(row for row in dataset["food_businesses"] if row["name"] == item["name"])
    assert saved["source"] == "amap"
    assert saved["raw_data"]["id"] == "food-1"
    assert saved["raw_data"]["manual_detail"]["remark"] == "晚上客流较多"


@pytest.mark.parametrize(
    ("category", "payload", "expected_field", "expected_value"),
    [
        (
            "entertainment",
            {"entertainment_type": "KTV", "night_operation": True, "remark": "晚间营业"},
            "entertainment_type",
            "KTV",
        ),
        (
            "night_business",
            {"is_24_hours": True, "night_operation": True, "night_flow_remark": "凌晨仍有顾客"},
            "is_24_hours",
            True,
        ),
    ],
)
def test_different_supporting_categories_save_their_manual_fields(
    client,
    monkeypatch,
    category,
    payload,
    expected_field,
    expected_value,
):
    project_id, item = confirmed_supporting_item(client, monkeypatch, category)

    response = client.put(
        f"/api/projects/{project_id}/supporting/{item['id']}",
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["manual_detail"][expected_field] == expected_value


def test_supporting_detail_requires_confirmation(client, monkeypatch):
    project_id, body = collect_supporting_for_review(client, monkeypatch)
    item = body["items"][0]

    response = client.put(
        f"/api/projects/{project_id}/supporting/{item['id']}",
        json={"remark": "未确认时不能补充"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "请先确认该配套信息，再补充经营详情"


def test_supporting_detail_isolated_by_project_and_rejects_protected_fields(client, monkeypatch):
    first_project_id, item = confirmed_supporting_item(client, monkeypatch, "food")
    second_project_id = client.post(
        "/api/projects",
        json={**project_payload(), "name": "第二个配套项目"},
    ).json()["project_id"]

    other_project_get = client.get(f"/api/projects/{second_project_id}/supporting/{item['id']}")
    other_project_update = client.put(
        f"/api/projects/{second_project_id}/supporting/{item['id']}",
        json={"remark": "越权修改"},
    )
    protected_field = client.put(
        f"/api/projects/{first_project_id}/supporting/{item['id']}",
        json={"source": "manual", "remark": "尝试修改来源"},
    )

    assert other_project_get.status_code == 404
    assert other_project_update.status_code == 404
    assert protected_field.status_code == 422


def test_confirmed_supporting_missing_details_appear_in_data_quality(client, monkeypatch):
    project_id, item = confirmed_supporting_item(client, monkeypatch, "food")

    response = client.get(f"/api/projects/{project_id}/data-quality")

    assert response.status_code == 200
    body = response.json()
    assert {
        "project_id",
        "quality_score",
        "missing",
        "warnings",
        "competitor_detail_quality",
        "supporting_detail_quality",
    } <= set(body)
    quality = body["supporting_detail_quality"]
    assert quality["total_confirmed"] == 1
    assert quality["completed"] == 0
    assert quality["incomplete"] == 1
    assert quality["incomplete_items"] == [
        {
            "id": item["id"],
            "name": item["name"],
            "category": "food",
            "missing_fields": ["营业时间", "夜间营业"],
        }
    ]
    assert {entry["field"] for entry in quality["missing_summary"]} == {
        "business_hours",
        "night_operation",
    }


def test_completed_supporting_detail_removes_quality_missing_and_improves_score(client, monkeypatch):
    project_id, item = confirmed_supporting_item(client, monkeypatch, "food")
    before = client.get(f"/api/projects/{project_id}/data-quality").json()

    update = client.put(
        f"/api/projects/{project_id}/supporting/{item['id']}",
        json={"business_hours": "10:00-22:00", "night_operation": False},
    )
    after = client.get(f"/api/projects/{project_id}/data-quality").json()

    assert update.status_code == 200
    assert after["supporting_detail_quality"]["total_confirmed"] == 1
    assert after["supporting_detail_quality"]["completed"] == 1
    assert after["supporting_detail_quality"]["incomplete"] == 0
    assert after["supporting_detail_quality"]["missing_summary"] == []
    assert after["supporting_detail_quality"]["incomplete_items"] == []
    assert after["quality_score"] > before["quality_score"]


def test_night_business_quality_requires_manual_24_hour_and_night_operation_checks(client, monkeypatch):
    project_id, item = confirmed_supporting_item(client, monkeypatch, "night_business")
    before = client.get(f"/api/projects/{project_id}/data-quality").json()

    update = client.put(
        f"/api/projects/{project_id}/supporting/{item['id']}",
        json={"is_24_hours": False, "night_operation": True},
    )
    after = client.get(f"/api/projects/{project_id}/data-quality").json()

    assert before["supporting_detail_quality"]["incomplete_items"][0]["missing_fields"] == [
        "是否24小时营业",
        "夜间营业",
    ]
    assert update.status_code == 200
    assert after["supporting_detail_quality"]["completed"] == 1
    assert after["supporting_detail_quality"]["incomplete"] == 0
