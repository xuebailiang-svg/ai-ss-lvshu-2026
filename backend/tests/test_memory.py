def test_memory_pending_requires_review_before_context(client):
    created = client.post(
        "/api/memory",
        json={
            "scope": "global",
            "memory_type": "business_rule",
            "title": "夜经济规则",
            "content": "夜间餐饮和娱乐场所越集中，电竞馆夜间客流基础越好。",
            "tags": ["电竞馆", "夜经济"],
            "source": "manual",
        },
    )
    assert created.status_code == 200
    memory_id = created.json()["id"]

    project = client.post(
        "/api/projects",
        json={
            "name": "小寨测试",
            "city": "西安市",
            "address": "小寨地铁站",
            "radius_meters": 1000,
            "business_type": "电竞馆",
        },
    ).json()["project_id"]

    assert client.get(f"/api/projects/{project}/memory/context").json()["items"] == []

    reviewed = client.post(f"/api/memory/{memory_id}/review", json={"status": "confirmed"})
    assert reviewed.status_code == 200

    context = client.get(f"/api/projects/{project}/memory/context").json()
    assert len(context["items"]) == 1
    assert context["items"][0]["title"] == "夜经济规则"


def test_memory_project_isolation(client):
    first = client.post(
        "/api/projects",
        json={"name": "项目A", "city": "西安市", "address": "A", "radius_meters": 1000, "business_type": "电竞馆"},
    ).json()["project_id"]
    second = client.post(
        "/api/projects",
        json={"name": "项目B", "city": "西安市", "address": "B", "radius_meters": 1000, "business_type": "电竞馆"},
    ).json()["project_id"]
    client.post(
        "/api/memory",
        json={
            "scope": "project",
            "memory_type": "project_note",
            "title": "项目A备注",
            "content": "仅项目A可见",
            "project_id": first,
            "status": "confirmed",
        },
    )

    assert client.get(f"/api/projects/{first}/memory/context").json()["items"][0]["title"] == "项目A备注"
    assert client.get(f"/api/projects/{second}/memory/context").json()["items"] == []


def test_memory_list_api_shape(client):
    # 通过 API 覆盖主要路径；这里保持测试文件兼容旧 conftest，不强依赖额外 fixture。
    response = client.get("/api/memory")
    assert response.status_code == 200
    assert "items" in response.json()
