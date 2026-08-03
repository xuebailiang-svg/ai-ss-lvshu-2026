from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.map_data.mapper import amap_poi_to_unified


def _project_payload() -> dict[str, Any]:
    return {
        "name": "小寨电竞馆选址",
        "city": "西安市",
        "district": "雁塔区",
        "address": "小寨地铁站",
        "longitude": 108.946767,
        "latitude": 34.222838,
        "radius_meters": 1000,
        "business_type": "电竞馆",
    }


def _fake_amap_rows() -> list[dict[str, Any]]:
    return [
        {
            "id": "amap-transport-1",
            "category": "transport",
            "sub_category": "地铁",
            "name": "小寨地铁站",
            "type": "地铁",
            "address": "西安市雁塔区",
            "location": "108.946767,34.222838",
            "distance": "120",
            "source": "amap",
        },
        {
            "id": "amap-competitor-1",
            "category": "competitor",
            "sub_category": "电竞馆",
            "name": "XX电竞馆",
            "type": "电竞馆",
            "address": "西安市雁塔区",
            "location": "108.947000,34.223000",
            "distance": "300",
            "source": "amap",
        },
        {
            "id": "amap-food-1",
            "category": "food",
            "sub_category": "烧烤",
            "name": "夜宵烧烤",
            "type": "烧烤",
            "address": "西安市雁塔区",
            "location": "108.948000,34.224000",
            "distance": "500",
            "source": "amap",
        },
        {
            "id": "amap-entertainment-1",
            "category": "entertainment",
            "sub_category": "KTV",
            "name": "欢乐KTV",
            "type": "KTV",
            "address": "西安市雁塔区",
            "location": "108.949000,34.225000",
            "distance": "800",
            "source": "amap",
        },
    ]


def test_amap_mapper_converts_to_unified_poi():
    row = _fake_amap_rows()[0]
    mapped = amap_poi_to_unified(row, category="transport", sub_category="地铁")
    assert mapped["name"] == "小寨地铁站"
    assert mapped["category"] == "transport"
    assert mapped["sub_category"] == "地铁"
    assert mapped["longitude"] == 108.946767
    assert mapped["latitude"] == 34.222838
    assert mapped["distance_meters"] == 120
    assert mapped["source"] == "amap"
    assert mapped["confidence"] == 0.9


def test_amap_mapper_extracts_business_hours_from_open_time():
    row = _fake_amap_rows()[2]
    row["biz_ext"] = {"open_time": "10:00-23:00", "rating": "4.5"}
    mapped = amap_poi_to_unified(row, category="food", sub_category="烧烤")
    assert mapped["business_hours"] == "10:00-23:00"

    list_row = _fake_amap_rows()[2]
    list_row["biz_ext"] = {"open_time": ["10:00-14:00", "17:00-21:30"]}
    mapped = amap_poi_to_unified(list_row, category="food", sub_category="烧烤")
    assert mapped["business_hours"] == "10:00-14:00、17:00-21:30"

    empty_row = _fake_amap_rows()[2]
    empty_row["biz_ext"] = {"open_time": []}
    mapped = amap_poi_to_unified(empty_row, category="food", sub_category="烧烤")
    assert mapped["business_hours"] is None


def test_geocode_project_endpoint_resolves_and_saves_coordinates(client):
    payload = _project_payload()
    payload.pop("longitude")
    payload.pop("latitude")
    project_id = client.post("/api/projects", json=payload).json()["project_id"]

    response = client.post(f"/api/projects/{project_id}/geocode")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["location"]["longitude"] is not None
    assert body["location"]["latitude"] is not None
    assert body["already_located"] is False

    project = client.get(f"/api/projects/{project_id}").json()["project"]
    assert project["longitude"] == body["location"]["longitude"]
    assert project["latitude"] == body["location"]["latitude"]


def test_geocode_project_endpoint_idempotent_when_already_located(client):
    project_id = client.post("/api/projects", json=_project_payload()).json()["project_id"]

    response = client.post(f"/api/projects/{project_id}/geocode")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["already_located"] is True
    assert body["location"]["longitude"] == 108.946767
    assert body["location"]["latitude"] == 34.222838


def test_geocode_project_endpoint_force_refreshes_coordinates(client, monkeypatch):
    async def fake_geocode(self, **kwargs):
        return {
            "geocodes": [{
                "location": "108.950000,34.230000",
                "formatted_address": "陕西省西安市雁塔区小寨地铁站",
            }]
        }

    monkeypatch.setattr("app.map_data.amap_client.AmapMapDataClient.geocode", fake_geocode)
    project_id = client.post("/api/projects", json=_project_payload()).json()["project_id"]

    response = client.post(f"/api/projects/{project_id}/geocode?force=true")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["already_located"] is False
    assert body["location"] == {"longitude": 108.95, "latitude": 34.23}
    assert body["diagnostics"]["forced"] is True


def test_geocode_project_endpoint_not_found(client):
    response = client.post("/api/projects/not-exists/geocode")
    assert response.status_code == 404


def test_collect_amap_pois_saves_project_data(client, monkeypatch):
    async def fake_collect_pois(self, **kwargs):
        return _fake_amap_rows(), {"mocked": True}

    monkeypatch.setattr("app.map_data.amap_client.AmapMapDataClient.collect_pois", fake_collect_pois)
    project_id = client.post("/api/projects", json=_project_payload()).json()["project_id"]
    quality_before = client.get(f"/api/projects/{project_id}/data-quality").json()

    response = client.post(f"/api/projects/{project_id}/collect/amap")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["collected"]["poi_count"] == 4
    assert body["collected"]["competitor_count"] == 1
    assert body["collected"]["food_count"] == 1
    assert body["collected"]["entertainment_count"] == 1

    dataset = client.get(f"/api/projects/{project_id}/dataset").json()
    assert len(dataset["pois"]) == 4
    assert {row["category"] for row in dataset["pois"]} >= {"transport", "competitor", "food", "entertainment"}
    quality_after = client.get(f"/api/projects/{project_id}/data-quality").json()
    assert quality_after["quality_score"] > quality_before["quality_score"]


def test_collect_amap_pois_upserts_duplicates(client, monkeypatch):
    async def fake_collect_pois(self, **kwargs):
        return _fake_amap_rows(), {"mocked": True}

    monkeypatch.setattr("app.map_data.amap_client.AmapMapDataClient.collect_pois", fake_collect_pois)
    project_id = client.post("/api/projects", json=_project_payload()).json()["project_id"]

    first = client.post(f"/api/projects/{project_id}/collect/amap")
    second = client.post(f"/api/projects/{project_id}/collect/amap")

    assert first.status_code == 200
    assert second.status_code == 200
    dataset = client.get(f"/api/projects/{project_id}/dataset").json()
    assert len(dataset["pois"]) == 4


def test_collect_amap_preserves_business_hours_and_exposes_phone(client, monkeypatch):
    call_count = 0

    async def fake_collect_pois(self, **kwargs):
        nonlocal call_count
        rows = _fake_amap_rows()
        rows[2]["tel"] = "029-12345678"
        if call_count == 0:
            rows[2]["biz_ext"] = {"open_time": "10:00-23:00"}
        call_count += 1
        return rows, {"mocked": True}

    monkeypatch.setattr("app.map_data.amap_client.AmapMapDataClient.collect_pois", fake_collect_pois)
    project_id = client.post("/api/projects", json=_project_payload()).json()["project_id"]

    assert client.post(f"/api/projects/{project_id}/collect/amap").status_code == 200
    assert client.post(f"/api/projects/{project_id}/collect/amap").status_code == 200

    dataset = client.get(f"/api/projects/{project_id}/dataset").json()
    food = next(row for row in dataset["pois"] if row["category"] == "food")
    assert food["business_hours"] == "10:00-23:00"
    assert food["phone"] == "029-12345678"


def test_collect_amap_reports_unique_stored_count(client, monkeypatch):
    async def fake_collect_pois(self, **kwargs):
        rows = _fake_amap_rows()
        return [*rows, dict(rows[0])], {"raw_count": 5}

    monkeypatch.setattr("app.map_data.amap_client.AmapMapDataClient.collect_pois", fake_collect_pois)
    project_id = client.post("/api/projects", json=_project_payload()).json()["project_id"]

    response = client.post(f"/api/projects/{project_id}/collect/amap")

    assert response.status_code == 200
    body = response.json()
    assert body["collected"]["poi_count"] == 4
    assert body["diagnostics"]["raw_discovered_count"] == 5
    assert body["diagnostics"]["stored_unique_count"] == 4
    assert body["diagnostics"]["duplicate_count"] == 1
    dataset = client.get(f"/api/projects/{project_id}/dataset").json()
    assert len(dataset["pois"]) == 4


def test_collect_amap_without_key_returns_clear_error(client, monkeypatch):
    monkeypatch.setenv("AMAP_MOCK", "false")
    monkeypatch.delenv("AMAP_WEB_SERVICE_KEY", raising=False)
    get_settings.cache_clear()
    project_id = client.post("/api/projects", json=_project_payload()).json()["project_id"]

    response = client.post(f"/api/projects/{project_id}/collect/amap")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["message"] == "AMAP_WEB_SERVICE_KEY未配置"


def test_collect_amap_project_not_found(client):
    response = client.post("/api/projects/not-exists/collect/amap")
    assert response.status_code == 404
