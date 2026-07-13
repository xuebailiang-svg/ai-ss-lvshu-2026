from __future__ import annotations

from pathlib import Path

from app.scoring_engine.calculator import ProjectScoreCalculator
from app.scoring_engine.rules import load_rules


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


def import_data(client, project_id: str, data_type: str, data: dict):
    response = client.post(f"/api/projects/{project_id}/data/import", json={"type": data_type, "data": data})
    assert response.status_code == 200
    return response.json()["data"]


def seed_complete_project(client) -> str:
    project_id = create_project(client)
    for poi in [
        {"name": "小寨地铁站", "category": "transport", "sub_category": "地铁", "distance_meters": 120, "source": "amap"},
        {"name": "公交站", "category": "transport", "sub_category": "公交", "distance_meters": 100, "source": "amap"},
        {"name": "停车场", "category": "transport", "sub_category": "停车场", "distance_meters": 200, "source": "amap"},
        {"name": "西安交通大学", "category": "education", "sub_category": "大学", "distance_meters": 800, "source": "amap"},
        {"name": "职业技术学校", "category": "education", "sub_category": "技校", "distance_meters": 900, "source": "amap"},
        {"name": "青年公寓", "category": "residential", "sub_category": "公寓", "distance_meters": 300, "source": "amap"},
        {"name": "住宅小区", "category": "residential", "sub_category": "小区", "distance_meters": 400, "source": "amap"},
        {"name": "夜市烧烤", "category": "food", "sub_category": "夜宵", "distance_meters": 200, "source": "amap"},
        {"name": "24小时便利店", "category": "food", "sub_category": "便利店", "distance_meters": 160, "source": "amap"},
        {"name": "欢乐KTV", "category": "entertainment", "sub_category": "KTV", "distance_meters": 500, "source": "amap"},
        {"name": "台球俱乐部", "category": "entertainment", "sub_category": "台球", "distance_meters": 520, "source": "amap"},
    ]:
        import_data(client, project_id, "poi", poi)
    import_data(
        client,
        project_id,
        "competitor",
        {
            "name": "XX电竞馆",
            "distance_meters": 500,
            "machine_count": 100,
            "gpu": "RTX 3060",
            "hour_price": 15,
            "member_price": 12,
            "occupancy_rate": 0.75,
            "source": "manual",
        },
    )
    import_data(client, project_id, "rent", {"monthly_rent": 30000, "area_sqm": 500, "rent_per_sqm": 60, "source": "manual"})
    return project_id


def test_complete_data_scoring(client):
    project_id = seed_complete_project(client)

    response = client.post(f"/api/projects/{project_id}/score")

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == project_id
    assert body["total_score"] >= 75
    assert body["level"] == "推荐"
    assert body["dimensions"]["population"]["score"] > 0
    assert body["dimensions"]["traffic"]["score"] == 20
    assert body["dimensions"]["rent"]["score"] == 10
    assert body["score_id"] is not None


def test_missing_data_scoring_has_lower_confidence(client):
    project_id = create_project(client)

    response = client.post(f"/api/projects/{project_id}/score")

    assert response.status_code == 200
    body = response.json()
    assert body["total_score"] < 50
    assert body["confidence"] < 0.6
    assert "真实租金" in body["missing_data"]
    assert "人口代理数据" in body["missing_data"]


def test_traffic_penalty_rule(client):
    project_id = create_project(client)
    import_data(client, project_id, "poi", {"name": "小寨地铁站", "category": "transport", "sub_category": "地铁", "source": "amap"})
    import_data(client, project_id, "supplement", {"target_type": "traffic", "field_name": "barrier", "value": "附近有高架和火车道"})

    response = client.post(f"/api/projects/{project_id}/score")

    assert response.status_code == 200
    traffic = response.json()["dimensions"]["traffic"]
    assert traffic["score"] == 0
    assert any("高架" in item or "火车道" in item for item in traffic["risks"])


def test_competitor_risk_for_too_many_competitors(client):
    project_id = create_project(client)
    for index in range(6):
        import_data(client, project_id, "competitor", {"name": f"竞品{index}", "distance_meters": 100 + index})

    response = client.post(f"/api/projects/{project_id}/score")

    assert response.status_code == 200
    body = response.json()
    assert any("竞争压力较高" in item for item in body["risks"])
    assert "竞品价格" in body["missing_data"]
    assert body["dimensions"]["competitor"]["confidence"] < 0.6


def test_yaml_weight_change_takes_effect(tmp_path: Path):
    custom_yaml = tmp_path / "rules.yaml"
    custom_yaml.write_text(
        """
version: custom
levels:
  recommend: 75
  cautious: 60
population:
  weight: 40
  university: 20
  vocational_school: 8
  apartment: 5
  young_residential: 5
  relocation_housing: 2
traffic:
  weight: 20
  subway: 10
  bus: 5
  parking: 5
  penalties:
    elevated_road: -5
    interchange: -5
    underpass: -5
    railway: -5
    green_barrier: -3
support:
  weight: 20
  night_market: 8
  convenience_24h: 4
  late_food: 4
  entertainment_max: 4
competitor:
  weight: 20
  none_bonus: 10
  reasonable_count_bonus: 5
  quality_bonus: 5
  too_many_threshold: 5
  too_many_penalty: -5
rent:
  weight: 10
  reasonable: 10
  medium: 6
  high: 3
  reasonable_rent_per_sqm: 100
  high_rent_per_sqm: 150
""",
        encoding="utf-8",
    )
    rules = load_rules(custom_yaml)
    dataset = {"pois": [{"name": "某大学", "category": "education", "sub_category": "大学"}], "competitors": [], "rent_data": {}}

    result = ProjectScoreCalculator(rules).calculate(dataset)

    assert result["scoring_version"] == "custom"
    assert result["dimensions"]["population"]["score"] == 20
    assert result["dimensions"]["population"]["max"] == 40


def test_confidence_calculation(client):
    complete_project_id = seed_complete_project(client)
    sparse_project_id = create_project(client)
    import_data(client, sparse_project_id, "competitor", {"name": "只有名称的竞品", "distance_meters": 300})

    complete = client.post(f"/api/projects/{complete_project_id}/score").json()
    sparse = client.post(f"/api/projects/{sparse_project_id}/score").json()

    assert complete["confidence"] > sparse["confidence"]
    assert complete["dimensions"]["competitor"]["confidence"] > sparse["dimensions"]["competitor"]["confidence"]
