def create_project(client):
    response = client.post("/api/projects", json={
        "name": "小寨电竞馆选址",
        "city": "西安市",
        "district": "雁塔区",
        "address": "小寨地铁站",
        "longitude": 108.946767,
        "latitude": 34.222838,
        "radius_meters": 1000,
        "business_type": "电竞馆",
    })
    assert response.status_code == 200
    return response.json()["project_id"]


def test_create_project_success(client):
    project_id = create_project(client)

    assert project_id.startswith("proj_")


def test_create_project_preserves_utf8_text(client):
    payload = {
        "name": "陕西省西安市雁塔区西部电子社区电竞馆",
        "city": "西安市",
        "district": "雁塔区",
        "address": "陕西省西安市雁塔区西部电子社区",
        "longitude": 108.946767,
        "latitude": 34.222838,
        "radius_meters": 1000,
        "business_type": "电竞馆",
    }

    response = client.post("/api/projects", json=payload)

    assert response.status_code == 200
    project_id = response.json()["project_id"]
    detail = client.get(f"/api/projects/{project_id}").json()["project"]
    assert detail["name"] == payload["name"]
    assert detail["city"] == payload["city"]
    assert detail["district"] == payload["district"]
    assert detail["address"] == payload["address"]
    assert detail["business_type"] == payload["business_type"]


def test_get_project_success(client):
    project_id = create_project(client)

    response = client.get(f"/api/projects/{project_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["project"]["project_id"] == project_id
    assert data["project"]["city"] == "西安市"
    assert data["stats"]["poi_count"] == 0


def test_import_poi_success(client):
    project_id = create_project(client)

    response = client.post(f"/api/projects/{project_id}/data/import", json={
        "type": "poi",
        "data": {
            "name": "小寨地铁站",
            "category": "transport",
            "distance_meters": 300,
            "source": "amap",
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["project_id"] == project_id
    assert body["data"]["name"] == "小寨地铁站"
    assert body["data"]["category"] == "transport"


def test_import_competitor_success(client):
    project_id = create_project(client)

    response = client.post(f"/api/projects/{project_id}/data/import", json={
        "type": "competitor",
        "data": {
            "name": "XX电竞馆",
            "distance_meters": 500,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["project_id"] == project_id
    assert body["data"]["name"] == "XX电竞馆"
    assert body["data"]["distance_meters"] == 500
    assert "缺少" in "".join(body["warnings"])


def test_dataset_returns_complete_structure(client):
    project_id = create_project(client)
    client.post(f"/api/projects/{project_id}/data/import", json={
        "type": "poi",
        "data": {"name": "西安交通大学", "category": "education", "distance_meters": 900},
    })
    client.post(f"/api/projects/{project_id}/data/import", json={
        "type": "competitor",
        "data": {"name": "XX电竞馆", "distance_meters": 500},
    })
    client.post(f"/api/projects/{project_id}/data/import", json={
        "type": "rent",
        "data": {"monthly_rent": 30000, "area_sqm": 500, "rent_per_sqm": 60},
    })

    response = client.get(f"/api/projects/{project_id}/dataset")

    assert response.status_code == 200
    data = response.json()
    assert data["project"]["project_id"] == project_id
    assert len(data["pois"]) == 1
    assert len(data["competitors"]) == 1
    assert isinstance(data["food_businesses"], list)
    assert isinstance(data["entertainments"], list)
    assert data["rent_data"]["monthly_rent"] == 30000
    assert isinstance(data["population_data"], dict)
    assert isinstance(data["supplements"], list)


def test_data_quality_returns_missing_fields(client):
    project_id = create_project(client)
    client.post(f"/api/projects/{project_id}/data/import", json={
        "type": "competitor",
        "data": {"name": "缺少经营数据的竞品", "distance_meters": 500},
    })

    response = client.get(f"/api/projects/{project_id}/data-quality")

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == project_id
    assert body["quality_score"] < 100
    assert "竞品价格" in body["missing"]
    assert "竞品上座率" in body["missing"]
    assert "真实租金" in body["missing"]
    assert body["warnings"]


def test_delete_project_is_soft_delete(client):
    project_id = create_project(client)
    delete_response = client.delete(f"/api/projects/{project_id}")

    assert delete_response.status_code == 204
    assert client.get(f"/api/projects/{project_id}").status_code == 404
    list_response = client.get("/api/projects")
    assert all(item["project_id"] != project_id for item in list_response.json()["items"])
