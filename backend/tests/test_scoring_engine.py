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
            "status": "confirmed",
            "machine_count": 100,
            "gpu": "RTX 3060",
            "hour_price": 15,
            "member_price": 12,
            "occupancy_rate": 0.75,
            "source": "manual",
        },
    )
    for index in range(20):
        import_data(
            client,
            project_id,
            "food",
            {
                "name": f"已确认餐饮{index}",
                "status": "confirmed",
                "supporting_group": "food",
                "manual_detail": {
                    "business_hours": "10:00-02:00",
                    "night_operation": index < 5,
                },
            },
        )
    for index in range(5):
        import_data(
            client,
            project_id,
            "entertainment",
            {
                "name": f"已确认娱乐{index}",
                "type": "KTV",
                "status": "confirmed",
                "manual_detail": {
                    "business_hours": "12:00-03:00",
                    "night_operation": True,
                },
            },
        )
    for index in range(3):
        import_data(
            client,
            project_id,
            "food",
            {
                "name": f"已确认夜间商业{index}",
                "status": "confirmed",
                "supporting_group": "night_economy",
                "manual_detail": {
                    "is_24_hours": True,
                    "night_operation": True,
                },
            },
        )
    for monthly_rent in (30000, 32000, 28000):
        import_data(
            client,
            project_id,
            "rent",
            {
                "location_type": "小寨商铺",
                "monthly_rent": monthly_rent,
                "area_sqm": 500,
                "status": "confirmed",
                "source": "manual",
            },
        )
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
    assert body["dimensions"]["rent"]["score"] == 12
    assert body["dimensions"]["rent"]["max"] == 20
    assert body["rent_analysis"]["confirmed_rent_count"] == 3
    assert body["score_id"] is not None


def test_missing_data_scoring_has_lower_confidence(client):
    project_id = create_project(client)

    response = client.post(f"/api/projects/{project_id}/score")

    assert response.status_code == 200
    body = response.json()
    assert body["total_score"] < 50
    assert body["confidence"] < 0.6
    assert "有效租金样本" in body["missing_data"]
    assert "人口代理数据" in body["missing_data"]
    assert body["competitor_analysis"]["competitor_count"] == 0
    assert body["competitor_analysis"]["competition_level"] == "low"


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
        import_data(
            client,
            project_id,
            "competitor",
            {"name": f"竞品{index}", "distance_meters": 100 + index, "status": "confirmed"},
        )

    response = client.post(f"/api/projects/{project_id}/score")

    assert response.status_code == 200
    body = response.json()
    assert any("竞争压力较高" in item for item in body["risks"])
    assert "竞品价格" in body["missing_data"]
    assert body["dimensions"]["competitor"]["confidence"] < 0.6


def test_confirmed_competitor_operating_data_enters_scoring(client):
    project_id = create_project(client)
    import_data(
        client,
        project_id,
        "competitor",
        {
            "name": "已确认电竞馆",
            "distance_meters": 600,
            "status": "confirmed",
            "hour_price": 10,
            "occupancy_rate": 0.75,
            "machine_count": 120,
            "gpu": "RTX 4060",
        },
    )

    response = client.post(f"/api/projects/{project_id}/score")

    assert response.status_code == 200
    body = response.json()
    analysis = body["competitor_analysis"]
    assert analysis["competitor_count"] == 1
    assert analysis["confirmed_competitor_count"] == 1
    assert analysis["pending_review_count"] == 0
    assert analysis["average_distance"] == 600
    assert analysis["average_hour_price"] == 10
    assert analysis["average_occupancy_rate"] == 0.75
    assert analysis["average_machine_count"] == 120
    assert analysis["common_gpu"] == "RTX 4060"
    assert analysis["competition_level"] == "low"
    assert body["dimensions"]["competitor"]["analysis"] == analysis
    assert any("平均价格" in item for item in body["dimensions"]["competitor"]["reasons"])


def test_rejected_competitor_is_excluded_from_scoring(client):
    project_id = create_project(client)
    import_data(
        client,
        project_id,
        "competitor",
        {
            "name": "已排除网络公司",
            "distance_meters": 200,
            "status": "rejected",
            "hour_price": 99,
            "occupancy_rate": 0.99,
            "machine_count": 999,
        },
    )

    response = client.post(f"/api/projects/{project_id}/score")

    assert response.status_code == 200
    analysis = response.json()["competitor_analysis"]
    assert analysis["competitor_count"] == 0
    assert analysis["candidate_competitor_count"] == 0
    assert analysis["confirmed_competitor_count"] == 0
    assert analysis["average_hour_price"] is None


def test_pending_competitors_do_not_affect_formal_count(client):
    project_id = create_project(client)
    import_data(
        client,
        project_id,
        "competitor",
        {"name": "已确认竞品", "distance_meters": 400, "status": "confirmed", "hour_price": 12},
    )
    import_data(client, project_id, "competitor", {"name": "待核实竞品1", "distance_meters": 500})
    import_data(client, project_id, "competitor", {"name": "待核实竞品2", "distance_meters": 700})

    response = client.post(f"/api/projects/{project_id}/score")

    assert response.status_code == 200
    analysis = response.json()["competitor_analysis"]
    assert analysis["competitor_count"] == 1
    assert analysis["candidate_competitor_count"] == 3
    assert analysis["confirmed_competitor_count"] == 1
    assert analysis["pending_review_count"] == 2
    assert analysis["weighted_competitor_count"] == 1
    assert analysis["average_distance"] == 400


def test_competitor_scoring_handles_missing_operating_data(client):
    project_id = create_project(client)
    import_data(
        client,
        project_id,
        "competitor",
        {"name": "仅有基础信息的竞品", "distance_meters": 300, "status": "confirmed"},
    )

    response = client.post(f"/api/projects/{project_id}/score")

    assert response.status_code == 200
    body = response.json()
    analysis = body["competitor_analysis"]
    competitor_dimension = body["dimensions"]["competitor"]
    assert analysis["average_hour_price"] is None
    assert analysis["average_occupancy_rate"] is None
    assert analysis["average_machine_count"] is None
    assert "竞品经营信息不足" in competitor_dimension["missing_data"]
    assert competitor_dimension["confidence"] < 0.6


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


def supporting_row(
    name: str,
    *,
    status: str = "confirmed",
    group: str = "food",
    manual_detail: dict | None = None,
) -> dict:
    return {
        "name": name,
        "status": status,
        "raw_data": {
            "supporting_group": group,
            "supporting_groups": [group],
            "manual_detail": manual_detail or {},
        },
    }


def test_night_consumption_dimension_reaches_twenty_with_confirmed_evidence():
    rules = load_rules()
    food = [
        supporting_row(
            f"餐饮{index}",
            manual_detail={"business_hours": "10:00-02:00", "night_operation": index < 5},
        )
        for index in range(20)
    ]
    night_business = [
        supporting_row(
            f"夜间商业{index}",
            group="night_economy",
            manual_detail={"is_24_hours": True, "night_operation": True},
        )
        for index in range(3)
    ]
    entertainment = [
        supporting_row(
            f"娱乐{index}",
            group="entertainment",
            manual_detail={"business_hours": "12:00-03:00", "night_operation": True},
        )
        for index in range(5)
    ]
    dataset = {
        "pois": [],
        "competitors": [],
        "rent_data": {},
        "food_businesses": food + night_business,
        "entertainments": entertainment,
        "supplements": [],
    }

    result = ProjectScoreCalculator(rules).calculate(dataset)

    analysis = result["supporting_analysis"]
    assert analysis["food_count"] == 20
    assert analysis["night_food_count"] == 5
    assert analysis["entertainment_count"] == 5
    assert analysis["night_business_count"] == 3
    assert analysis["night_activity_level"] == "high"
    assert analysis["detail_completeness"] == 1
    assert result["dimensions"]["support"]["score"] == 20
    assert result["dimensions"]["support"]["analysis"] == analysis


def test_supporting_analysis_excludes_pending_and_rejected_rows():
    rules = load_rules()
    dataset = {
        "pois": [],
        "competitors": [],
        "rent_data": {},
        "food_businesses": [
            supporting_row("已确认餐饮", manual_detail={"business_hours": "10:00-22:00", "night_operation": False}),
            supporting_row("待核实餐饮", status="pending_review", manual_detail={"business_hours": "24小时", "night_operation": True}),
            supporting_row("已排除餐饮", status="rejected", manual_detail={"business_hours": "24小时", "night_operation": True}),
        ],
        "entertainments": [
            supporting_row("待核实娱乐", status="pending_review", group="entertainment", manual_detail={"business_hours": "24小时", "night_operation": True}),
        ],
        "supplements": [],
    }

    result = ProjectScoreCalculator(rules).calculate(dataset)

    analysis = result["supporting_analysis"]
    assert analysis["food_count"] == 1
    assert analysis["night_food_count"] == 0
    assert analysis["entertainment_count"] == 0
    assert analysis["confirmed_supporting_count"] == 1


def test_supporting_scoring_handles_no_data_and_missing_details():
    rules = load_rules()
    empty_dataset = {
        "pois": [],
        "competitors": [],
        "rent_data": {},
        "food_businesses": [],
        "entertainments": [],
        "supplements": [],
    }
    missing_detail_dataset = {
        **empty_dataset,
        "food_businesses": [supporting_row("只有名称的餐饮")],
    }

    empty_result = ProjectScoreCalculator(rules).calculate(empty_dataset)
    missing_result = ProjectScoreCalculator(rules).calculate(missing_detail_dataset)

    assert empty_result["supporting_analysis"]["food_count"] == 0
    assert empty_result["dimensions"]["support"]["score"] == 0
    assert "已确认周边配套数据" in empty_result["dimensions"]["support"]["missing_data"]
    assert missing_result["supporting_analysis"]["detail_completeness"] == 0
    assert "夜间经营信息不足" in missing_result["dimensions"]["support"]["missing_data"]
    assert missing_result["dimensions"]["support"]["confidence"] < 0.5


def rent_dataset(records: list[dict]) -> dict:
    return {
        "pois": [],
        "competitors": [],
        "rent_data": records[-1] if records else {},
        "rent_records": records,
        "food_businesses": [],
        "entertainments": [],
        "supplements": [],
    }


def rent_record(unit_price: float, *, status: str = "confirmed", address: str | None = "测试商铺") -> dict:
    return {
        "location_type": address,
        "area_sqm": 100,
        "monthly_rent": unit_price * 100,
        "rent_per_sqm": unit_price,
        "status": status,
    }


def test_confirmed_rent_records_participate_in_analysis():
    calculator = ProjectScoreCalculator(load_rules())
    result = calculator.calculate(rent_dataset([rent_record(80), rent_record(100), rent_record(120)]))

    analysis = result["rent_analysis"]
    assert analysis["confirmed_rent_count"] == 3
    assert analysis["average_area_sqm"] == 100
    assert analysis["average_monthly_rent"] == 10000
    assert analysis["average_rent_unit_price"] == 100
    assert result["dimensions"]["rent"]["max"] == 20


def test_pending_and_rejected_rent_records_are_excluded():
    calculator = ProjectScoreCalculator(load_rules())
    result = calculator.calculate(
        rent_dataset([rent_record(80), rent_record(200, status="pending_review"), rent_record(300, status="rejected")])
    )

    assert result["rent_analysis"]["confirmed_rent_count"] == 1
    assert result["rent_analysis"]["average_rent_unit_price"] == 80


def test_confirmed_rent_missing_core_fields_is_excluded():
    calculator = ProjectScoreCalculator(load_rules())
    records = [
        rent_record(100),
        {**rent_record(110), "area_sqm": None},
        {**rent_record(120), "monthly_rent": None},
        rent_record(130, address=None),
    ]
    result = calculator.calculate(rent_dataset(records))

    assert result["rent_analysis"]["confirmed_rent_count"] == 1
    assert result["rent_analysis"]["data_completeness"] == 0.25
    assert "部分已确认租金缺少地址、面积或月租金" in result["dimensions"]["rent"]["missing_data"]


def test_rent_pressure_uses_project_reference_sample_ratios():
    calculator = ProjectScoreCalculator(load_rules())
    reference = [rent_record(100), rent_record(100), rent_record(100)]

    low = calculator.calculate(rent_dataset([*reference, rent_record(79)]))
    medium = calculator.calculate(rent_dataset([*reference, rent_record(120)]))
    high = calculator.calculate(rent_dataset([*reference, rent_record(121)]))

    assert low["rent_analysis"]["rent_pressure"] == "low"
    assert low["dimensions"]["rent"]["score"] == 20
    assert medium["rent_analysis"]["rent_pressure"] == "medium"
    assert medium["dimensions"]["rent"]["score"] == 12
    assert high["rent_analysis"]["rent_pressure"] == "high"
    assert high["dimensions"]["rent"]["score"] == 4


def test_rent_sample_shortage_reduces_confidence():
    calculator = ProjectScoreCalculator(load_rules())
    result = calculator.calculate(rent_dataset([rent_record(100), rent_record(100)]))

    dimension = result["dimensions"]["rent"]
    assert "租金样本不足" in dimension["missing_data"]
    assert dimension["confidence"] <= 0.45
    assert any("仅有 2 条" in risk for risk in dimension["risks"])
