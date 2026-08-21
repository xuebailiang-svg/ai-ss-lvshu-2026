from __future__ import annotations


def create_project(client) -> str:
    response = client.post(
        "/api/projects",
        json={
            "name": "准备度测试项目",
            "city": "西安市",
            "district": "雁塔区",
            "address": "小寨地铁站",
            "longitude": 108.946767,
            "latitude": 34.222838,
            "radius_meters": 1000,
            "business_type": "电竞馆",
        },
    )
    assert response.status_code == 200
    return response.json()["project_id"]


def import_data(client, project_id: str, data_type: str, data: dict):
    response = client.post(
        f"/api/projects/{project_id}/data/import",
        json={"type": data_type, "data": data},
    )
    assert response.status_code == 200
    return response.json()["data"]


def group_item(readiness: dict, group: str, item_id: str) -> dict:
    return next(item for item in readiness["groups"][group] if item["id"] == item_id)


def test_empty_project_is_blocked_by_amap_not_by_optional_business_data(client):
    project_id = create_project(client)

    body = client.get(f"/api/projects/{project_id}/data-quality").json()
    readiness = body["readiness"]

    assert readiness["status"] == "blocked"
    assert readiness["can_generate_report"] is False
    assert group_item(readiness, "technical_prerequisites", "project_location")["status"] == "complete"
    assert group_item(readiness, "technical_prerequisites", "amap_collection")["status"] == "blocked"
    assert group_item(readiness, "optional", "optional_sales")["weight"] == 0
    assert "竞品营业额" not in body["missing"]


def test_readiness_has_fixed_transparent_weight_catalog(client):
    project_id = create_project(client)
    body = client.get(f"/api/projects/{project_id}/data-quality").json()
    readiness = body["readiness"]
    items = [item for group in readiness["groups"].values() for item in group]

    assert sum(item["weight"] for item in items) == 100
    assert body["quality_score"] == readiness["completion_percent"]
    assert "推荐概率" in readiness["score_explanation"]
    assert {item["id"] for item in items} == {
        "project_location",
        "amap_collection",
        "competitor_inventory",
        "competitor_core_details",
        "candidate_property",
        "supporting_context",
        "optional_sales",
    }


def test_explicit_unknown_is_acknowledged_without_repeated_red_warning(client):
    project_id = create_project(client)
    import_data(
        client,
        project_id,
        "poi",
        {"name": "高德竞品候选", "category": "competitor", "source": "amap"},
    )
    competitor = import_data(
        client,
        project_id,
        "competitor",
        {"name": "待现场核实电竞馆", "distance_meters": 300, "status": "confirmed", "source": "amap"},
    )
    response = client.put(
        f"/api/projects/{project_id}/competitors/{competitor['id']}",
        json={
            "unknown_fields": [
                "hour_price", "member_price", "machine_count", "cpu", "gpu", "monitor", "occupancy_rate",
            ]
        },
    )
    assert response.status_code == 200
    property_response = client.post(
        f"/api/projects/{project_id}/manual-input",
        json={
            "type": "property",
            "target_id": "primary",
            "data": {"unknown_fields": ["address", "area_sqm", "monthly_rent"]},
        },
    )
    assert property_response.status_code == 200

    body = client.get(f"/api/projects/{project_id}/data-quality").json()
    readiness = body["readiness"]

    assert readiness["status"] == "ready"
    assert readiness["formal_report_ready"] is True
    assert group_item(readiness, "key_unknowns", "competitor_core_details")["status"] == "acknowledged_unknown"
    assert group_item(readiness, "key_unknowns", "candidate_property")["status"] == "acknowledged_unknown"
    assert "核心竞品经营信息" not in body["missing"]
    assert "候选物业核心条件" not in body["missing"]


def test_mvp_quality_response_excludes_frozen_source_modules(client):
    project_id = create_project(client)
    body = client.get(f"/api/projects/{project_id}/data-quality").json()

    assert "crawler_quality" not in body
    assert "regional_context_quality" not in body
    assert "simulation_data_summary" not in body
