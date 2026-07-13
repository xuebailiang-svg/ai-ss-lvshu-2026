from __future__ import annotations


def create_project(client):
    response = client.post(
        "/api/projects",
        json={
            "name": "小寨电竞馆选址",
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


def create_basic_competitor(client, project_id: str) -> int:
    response = client.post(
        f"/api/projects/{project_id}/data/import",
        json={
            "type": "competitor",
            "data": {
                "name": "高德采集竞品",
                "distance_meters": 500,
                "source": "amap",
            },
        },
    )
    assert response.status_code == 200
    return int(response.json()["data"]["id"])


def test_create_competitor_manual_input(client):
    project_id = create_project(client)
    competitor_id = create_basic_competitor(client, project_id)

    response = client.post(
        f"/api/projects/{project_id}/manual-input",
        json={
            "type": "competitor",
            "target_id": str(competitor_id),
            "data": {
                "machine_count": 120,
                "hardware": {"cpu": "i5", "gpu": "RTX 3060", "monitor": "27寸 165Hz"},
                "price": {"hour_price": 15, "member_price": 12},
                "operation": {"occupancy_rate": 0.8, "monthly_sales": 300000, "annual_sales": 3600000, "recharge_amount": 50000},
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "竞品数据补充成功"
    assert body["updated"]["machine_count"] == 120
    assert body["updated"]["gpu"] == "RTX 3060"


def test_rent_manual_input_success(client):
    project_id = create_project(client)

    response = client.post(
        f"/api/projects/{project_id}/manual-input",
        json={
            "type": "rent",
            "data": {
                "monthly_rent": 30000,
                "area_sqm": 500,
                "rent_per_sqm": 60,
                "property_fee": 3000,
                "transfer_fee": 100000,
                "remark": "人工询价",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    dataset = client.get(f"/api/projects/{project_id}/dataset").json()
    assert dataset["rent_data"]["monthly_rent"] == 30000
    assert dataset["rent_data"]["raw_data"]["manual_input"]["property_fee"] == 3000
    assert dataset["rent_data"]["raw_data"]["manual_input"]["transfer_fee"] == 100000


def test_missing_data_returns_field_level_items(client):
    project_id = create_project(client)
    create_basic_competitor(client, project_id)

    response = client.get(f"/api/projects/{project_id}/missing-data")

    assert response.status_code == 200
    body = response.json()
    fields = {(item["type"], item["field"]) for item in body["missing"]}
    assert ("competitor", "hour_price") in fields
    assert ("competitor", "occupancy_rate") in fields
    assert ("rent", "monthly_rent") in fields


def test_manual_data_overrides_empty_amap_competitor_fields(client):
    project_id = create_project(client)
    competitor_id = create_basic_competitor(client, project_id)

    client.post(
        f"/api/projects/{project_id}/manual-input",
        json={
            "type": "competitor",
            "target_id": str(competitor_id),
            "data": {"hour_price": 18, "occupancy_rate": 0.75, "gpu": "RTX 4060"},
        },
    )

    dataset = client.get(f"/api/projects/{project_id}/dataset").json()
    competitor = dataset["competitors"][0]
    assert competitor["source"] == "manual"
    assert competitor["hour_price"] == 18
    assert competitor["occupancy_rate"] == 0.75
    assert competitor["gpu"] == "RTX 4060"


def test_manual_competitor_accepts_external_target_id(client):
    project_id = create_project(client)

    response = client.post(
        f"/api/projects/{project_id}/manual-input",
        json={
            "type": "competitor",
            "target_id": "amap-poi-xxx",
            "data": {"name": "外部POI竞品", "machine_count": 60, "hour_price": 10},
        },
    )

    assert response.status_code == 200
    assert response.json()["updated"]["name"] == "外部POI竞品"


def test_manual_input_history_is_saved(client):
    project_id = create_project(client)
    competitor_id = create_basic_competitor(client, project_id)

    client.post(
        f"/api/projects/{project_id}/manual-input",
        json={
            "type": "competitor",
            "target_id": str(competitor_id),
            "data": {"machine_count": 80, "hour_price": 12},
        },
    )

    response = client.get(f"/api/projects/{project_id}/manual-inputs")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) >= 2
    fields = {item["field_name"] for item in items}
    assert {"machine_count", "hour_price"} <= fields


def test_data_quality_improves_after_manual_input(client):
    project_id = create_project(client)
    competitor_id = create_basic_competitor(client, project_id)
    before = client.get(f"/api/projects/{project_id}/data-quality").json()["quality_score"]

    client.post(
        f"/api/projects/{project_id}/manual-input",
        json={
            "type": "competitor",
            "target_id": str(competitor_id),
            "data": {
                "machine_count": 100,
                "gpu": "RTX 3060",
                "hour_price": 15,
                "occupancy_rate": 0.8,
                "monthly_sales": 250000,
            },
        },
    )
    client.post(
        f"/api/projects/{project_id}/manual-input",
        json={"type": "rent", "data": {"monthly_rent": 28000, "area_sqm": 450, "rent_per_sqm": 62}},
    )

    after = client.get(f"/api/projects/{project_id}/data-quality").json()["quality_score"]
    assert after > before
