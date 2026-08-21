from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.map_data.amap_client import AmapMapDataClient
from app.map_data.mapper import amap_poi_to_unified
from app.models import UnifiedPOIRecord
from sqlalchemy import select


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


def test_amap_client_paginates_deduplicates_and_filters_radius():
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        if page == 1:
            pois = [
                {"id": "p1", "name": "A", "address": "一号路", "location": "108.0,34.0", "distance": "100"},
                {"id": "p2", "name": "B", "address": "二号路", "location": "108.001,34.0", "distance": "200"},
            ]
        elif page == 2:
            pois = [
                {"id": "p2", "name": "B重复", "address": "二号路", "location": "108.001,34.0", "distance": "200"},
                {"id": "p3", "name": "范围外", "address": "三号路", "location": "109.0,35.0", "distance": "1500"},
            ]
        else:
            pois = []
        return httpx.Response(200, json={"status": "1", "count": "4", "pois": pois})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            amap = AmapMapDataClient(
                key="test", mock=False, client=http_client, page_size=2, max_pages_per_keyword=3,
                max_records_per_category=10, rate_limit_seconds=0,
            )
            return await amap.collect_pois(
                longitude=108.0, latitude=34.0, radius_meters=1000,
                category_keywords={"transport": ["地铁"]},
            )

    rows, diagnostics = asyncio.run(run())
    assert [row["id"] for row in rows] == ["p1", "p2"]
    assert diagnostics["raw_return_count"] == 4
    assert diagnostics["unique_count"] == 2
    assert diagnostics["duplicate_count"] == 1
    assert diagnostics["outside_radius_count"] == 1
    assert diagnostics["queries"][0]["pages_fetched"] == 2


def test_amap_client_marks_category_limit_as_truncated():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "status": "1", "count": "9", "pois": [
                {"id": "1", "name": "A", "distance": "10"},
                {"id": "2", "name": "B", "distance": "20"},
                {"id": "3", "name": "C", "distance": "30"},
            ],
        })

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            amap = AmapMapDataClient(
                key="test", mock=False, client=http_client, page_size=3, max_pages_per_keyword=3,
                max_records_per_category=2, rate_limit_seconds=0,
            )
            return await amap.collect_pois(
                longitude=108.0, latitude=34.0, radius_meters=1000,
                category_keywords={"food": ["餐厅", "烧烤"]},
            )

    rows, diagnostics = asyncio.run(run())
    assert len(rows) == 2
    assert diagnostics["truncated"] is True
    assert diagnostics["category_summary"]["food"] == {"raw_count": 3, "unique_count": 2, "truncated": True}


def test_geocode_requires_confirmation_when_multiple_candidates(client, monkeypatch):
    async def fake_geocode(self, **kwargs):
        return {"geocodes": [
            {"location": "108.90,34.20", "formatted_address": "候选地址一", "district": "雁塔区", "level": "兴趣点"},
            {"location": "108.91,34.21", "formatted_address": "候选地址二", "district": "雁塔区", "level": "兴趣点"},
        ]}

    monkeypatch.setattr("app.map_data.amap_client.AmapMapDataClient.geocode", fake_geocode)
    payload = _project_payload()
    payload.pop("longitude")
    payload.pop("latitude")
    project_id = client.post("/api/projects", json=payload).json()["project_id"]

    ambiguous = client.post(f"/api/projects/{project_id}/geocode").json()
    assert ambiguous["success"] is False
    assert ambiguous["status"] == "needs_confirmation"
    assert [item["formatted_address"] for item in ambiguous["candidates"]] == ["候选地址一", "候选地址二"]

    confirmed = client.post(f"/api/projects/{project_id}/geocode?candidate_index=1").json()
    assert confirmed["success"] is True
    assert confirmed["location"] == {"longitude": 108.91, "latitude": 34.21}


def test_recollect_preserves_manual_raw_data(client, monkeypatch):
    async def fake_collect_pois(self, **kwargs):
        return [_fake_amap_rows()[0]], {"mocked": True}

    monkeypatch.setattr("app.map_data.amap_client.AmapMapDataClient.collect_pois", fake_collect_pois)
    project_id = client.post("/api/projects", json=_project_payload()).json()["project_id"]
    assert client.post(f"/api/projects/{project_id}/collect/amap").status_code == 200

    with SessionLocal() as db:
        row = db.scalar(select(UnifiedPOIRecord).where(UnifiedPOIRecord.project_id == project_id))
        row.raw_data = {**row.raw_data, "manual_detail": {"verified_name": "人工核实名称"}}
        db.commit()

    second = client.post(f"/api/projects/{project_id}/collect/amap").json()
    assert second["diagnostics"]["created_count"] == 0
    assert second["diagnostics"]["updated_count"] == 1
    dataset = client.get(f"/api/projects/{project_id}/dataset").json()
    assert dataset["pois"][0]["raw_data"]["manual_detail"] == {"verified_name": "人工核实名称"}


def test_collect_amap_distinguishes_zero_partial_failed_and_truncated(client, monkeypatch):
    project_ids = [client.post("/api/projects", json={**_project_payload(), "name": f"状态测试{index}"}).json()["project_id"] for index in range(4)]
    responses = iter([
        ([], {"query_count": 2, "failed_query_count": 0, "failed_keywords": []}),
        ([_fake_amap_rows()[0]], {"query_count": 2, "failed_query_count": 1, "failed_keywords": [{"keyword": "公交"}]}),
        ([], {"query_count": 2, "failed_query_count": 2, "failed_keywords": [{"keyword": "地铁"}, {"keyword": "公交"}]}),
        ([_fake_amap_rows()[0]], {"query_count": 1, "failed_query_count": 0, "truncated": True}),
    ])

    async def fake_collect_pois(self, **kwargs):
        return next(responses)

    monkeypatch.setattr("app.map_data.amap_client.AmapMapDataClient.collect_pois", fake_collect_pois)
    bodies = [client.post(f"/api/projects/{project_id}/collect/amap").json() for project_id in project_ids]
    assert [body["collection_status"] for body in bodies] == ["success_zero", "partial", "failed", "truncated"]
    assert [body["success"] for body in bodies] == [True, True, False, True]
    qualities = [client.get(f"/api/projects/{project_id}/data-quality").json() for project_id in project_ids]
    assert [body["readiness"]["amap_collection"]["status"] for body in qualities] == [
        "success_zero", "partial", "failed", "truncated",
    ]
    assert [body["readiness"]["can_generate_report"] for body in qualities] == [True, True, False, True]
    assert any("零结果" in warning for warning in qualities[0]["warnings"])
    assert any("采集缺口" in warning for warning in qualities[1]["warnings"])
    assert any("配置上限" in warning for warning in qualities[3]["warnings"])
