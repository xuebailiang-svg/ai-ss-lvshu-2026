from __future__ import annotations

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.llm.schemas import DeepSeekResult
from app.llm.service import build_ai_input
from app.llm.prompts import AI_DATA_REVIEW_PROMPT, SITE_SELECTION_REPORT_PROMPT
from app.models import AICallLogRecord, AIReportRecord


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


def seed_project_for_ai(client) -> str:
    project_id = create_project(client)
    import_data(client, project_id, "poi", {"name": "小寨地铁站", "category": "transport", "sub_category": "地铁", "source": "amap"})
    import_data(client, project_id, "poi", {"name": "夜宵烧烤", "category": "food", "sub_category": "夜宵", "source": "amap"})
    import_data(client, project_id, "poi", {"name": "欢乐KTV", "category": "entertainment", "sub_category": "KTV", "source": "amap"})
    import_data(
        client,
        project_id,
        "competitor",
        {
            "name": "XX电竞馆",
            "status": "confirmed",
            "distance_meters": 500,
            "machine_count": 100,
            "gpu": "RTX 3060",
            "hour_price": 15,
            "occupancy_rate": 0.7,
            "source": "manual",
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
    import_data(
        client,
        project_id,
        "food",
        {
            "name": "已确认夜间餐饮",
            "status": "confirmed",
            "supporting_group": "food",
            "manual_detail": {"business_hours": "18:00-02:00", "night_operation": True},
        },
    )
    import_data(
        client,
        project_id,
        "entertainment",
        {
            "name": "已确认娱乐场所",
            "status": "confirmed",
            "supporting_group": "entertainment",
            "manual_detail": {"business_hours": "12:00-03:00", "night_operation": True},
        },
    )
    client.post(f"/api/projects/{project_id}/score")
    return project_id


def test_ai_report_without_api_key_returns_clear_message(client, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    get_settings.cache_clear()
    project_id = create_project(client)

    response = client.post(f"/api/projects/{project_id}/ai-report")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["message"] == "DeepSeek API Key未配置"


def test_ai_review_without_api_key_returns_quality(client, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    get_settings.cache_clear()
    project_id = create_project(client)

    response = client.post(f"/api/projects/{project_id}/ai-review")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["message"] == "DeepSeek API Key未配置"
    assert body["data_quality"]["project_id"] == project_id


def test_mock_deepseek_returns_ai_review(client, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()

    def fake_generate_report(self, analysis_input, prompt=None):
        assert prompt == AI_DATA_REVIEW_PROMPT
        assert analysis_input["project"]["project_id"]
        assert "data_quality" in analysis_input
        assert "data_inventory" in analysis_input
        return DeepSeekResult(
            content="# 数据核验结论\n\n## 一、当前是否建议生成正式报告\n- 结论：暂不建议",
            model="deepseek-chat",
            duration_ms=10,
            input_length=100,
            output_length=50,
        )

    monkeypatch.setattr("app.llm.client.DeepSeekClient.generate_report", fake_generate_report)
    project_id = seed_project_for_ai(client)

    response = client.post(f"/api/projects/{project_id}/ai-review")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["model"] == "deepseek-chat"
    assert "数据核验结论" in body["content"]
    assert body["data_quality"]["project_id"] == project_id


def test_mock_deepseek_returns_report(client, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()

    def fake_generate_report(self, analysis_input, prompt=None):
        assert analysis_input["score_result"]["total_score"] >= 0
        assert analysis_input["competitor_analysis"]["competitor_count"] == 1
        assert analysis_input["competitor_analysis"]["average_hour_price"] == 15
        assert analysis_input["supporting_analysis"]["food_count"] == 1
        assert analysis_input["supporting_analysis"]["night_food_count"] == 1
        assert analysis_input["supporting_analysis"]["entertainment_count"] == 1
        assert analysis_input["rent_analysis"]["confirmed_rent_count"] == 3
        assert analysis_input["rent"] == {}
        return DeepSeekResult(
            content="# 电竞馆选址分析报告\n\n## 一、综合结论\n推荐。",
            model="deepseek-chat",
            duration_ms=12,
            input_length=100,
            output_length=30,
        )

    monkeypatch.setattr("app.llm.client.DeepSeekClient.generate_report", fake_generate_report)
    project_id = seed_project_for_ai(client)

    response = client.post(f"/api/projects/{project_id}/ai-report")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["report_id"]
    assert body["model"] == "deepseek-chat"
    assert "电竞馆选址分析报告" in body["content"]


def test_ai_input_conversion_has_fixed_sections(client):
    project_id = seed_project_for_ai(client)
    with SessionLocal() as db:
        analysis_input = build_ai_input(db, project_id)

    data = analysis_input.model_dump(mode="python")
    assert set(data) == {
        "project",
        "location",
        "environment",
        "competitors",
        "competitor_analysis",
        "supporting_analysis",
        "rent_analysis",
        "city_insight",
        "rent",
        "score_result",
        "data_quality",
        "simulation_data_summary",
        "memory_context",
        "risks",
    }
    assert data["city_insight"]["lbs_context"]["available"] is False
    assert "小时客流" in data["city_insight"]["lbs_context"]["missing"]
    assert data["project"]["project_id"] == project_id
    assert "transport" in data["environment"]
    assert "population" in data["environment"]
    assert "support" in data["environment"]
    assert data["competitors"]
    assert data["competitor_analysis"]["competitor_count"] == 1
    assert data["competitor_analysis"]["average_distance"] == 500
    assert data["competitor_analysis"]["common_gpu"] == "RTX 3060"
    assert data["supporting_analysis"]["food_count"] == 1
    assert data["supporting_analysis"]["night_food_count"] == 1
    assert data["supporting_analysis"]["entertainment_count"] == 1
    assert data["supporting_analysis"]["night_business_count"] == 0
    assert data["rent_analysis"]["confirmed_rent_count"] == 3
    assert data["rent_analysis"]["average_rent_unit_price"] == 60
    assert data["rent_analysis"]["rent_pressure"] == "medium"
    assert data["rent"] == {}
    assert data["simulation_data_summary"]["has_simulation_data"] is False
    assert data["score_result"]["total_score"] >= 0


def test_ai_report_without_competitors_is_generated_safely(client, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()

    def fake_generate_report(self, analysis_input, prompt=None):
        assert analysis_input["competitors"] == []
        assert analysis_input["competitor_analysis"]["competitor_count"] == 0
        assert analysis_input["competitor_analysis"]["average_hour_price"] is None
        assert analysis_input["supporting_analysis"]["food_count"] == 0
        assert analysis_input["supporting_analysis"]["night_activity_level"] == "none"
        assert analysis_input["rent_analysis"]["confirmed_rent_count"] == 0
        assert analysis_input["rent_analysis"]["rent_pressure"] == "unknown"
        return DeepSeekResult(
            content="# 电竞馆选址分析报告\n\n## 四、竞争环境分析\n未发现已确认竞品。",
            model="deepseek-chat",
            duration_ms=10,
            input_length=80,
            output_length=20,
        )

    monkeypatch.setattr("app.llm.client.DeepSeekClient.generate_report", fake_generate_report)
    project_id = create_project(client)
    client.post(f"/api/projects/{project_id}/score")

    response = client.post(f"/api/projects/{project_id}/ai-report")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "竞争环境分析" in response.json()["content"]


def test_ai_input_keeps_missing_competitor_operating_data_empty(client):
    project_id = create_project(client)
    import_data(
        client,
        project_id,
        "competitor",
        {"name": "仅有基础信息的电竞馆", "distance_meters": 350, "status": "confirmed"},
    )
    client.post(f"/api/projects/{project_id}/score")

    with SessionLocal() as db:
        data = build_ai_input(db, project_id).model_dump(mode="python")

    analysis = data["competitor_analysis"]
    assert analysis["competitor_count"] == 1
    assert analysis["average_distance"] == 350
    assert analysis["average_hour_price"] is None
    assert analysis["average_occupancy_rate"] is None
    assert analysis["average_machine_count"] is None
    assert analysis["common_gpu"] is None


def test_ai_input_does_not_send_rejected_competitors(client):
    project_id = create_project(client)
    import_data(
        client,
        project_id,
        "competitor",
        {
            "name": "已排除网络服务点",
            "status": "rejected",
            "distance_meters": 100,
            "hour_price": 99,
            "occupancy_rate": 0.99,
        },
    )
    client.post(f"/api/projects/{project_id}/score")

    with SessionLocal() as db:
        data = build_ai_input(db, project_id).model_dump(mode="python")

    assert data["competitors"] == []
    assert data["competitor_analysis"]["competitor_count"] == 0


def test_report_prompt_requires_competitor_evidence_and_missing_data_disclosure():
    assert "## 四、竞争环境分析" in SITE_SELECTION_REPORT_PROMPT
    assert "competitor_analysis" in SITE_SELECTION_REPORT_PROMPT
    assert "pending_review 只能作为数量参考" in SITE_SELECTION_REPORT_PROMPT
    assert "禁止补造价格、配置、上座率、机器数量或距离" in SITE_SELECTION_REPORT_PROMPT
    assert "simulation_data_summary" in SITE_SELECTION_REPORT_PROMPT
    assert "演示模拟数据" in SITE_SELECTION_REPORT_PROMPT


def test_ai_input_handles_missing_supporting_details_without_guessing(client):
    project_id = create_project(client)
    import_data(
        client,
        project_id,
        "food",
        {"name": "营业详情待补充餐饮", "status": "confirmed", "supporting_group": "food"},
    )
    client.post(f"/api/projects/{project_id}/score")

    with SessionLocal() as db:
        data = build_ai_input(db, project_id).model_dump(mode="python")

    analysis = data["supporting_analysis"]
    assert analysis["food_count"] == 1
    assert analysis["night_food_count"] == 0
    assert analysis["detail_completeness"] == 0
    assert data["environment"]["support"]["food_businesses"][0]["status"] == "confirmed"


def test_ai_input_does_not_send_rejected_supporting_data(client):
    project_id = create_project(client)
    import_data(
        client,
        project_id,
        "food",
        {
            "name": "已排除便利店候选",
            "status": "rejected",
            "supporting_group": "night_economy",
            "manual_detail": {"is_24_hours": True, "night_operation": True},
        },
    )
    client.post(f"/api/projects/{project_id}/score")

    with SessionLocal() as db:
        data = build_ai_input(db, project_id).model_dump(mode="python")

    assert data["environment"]["support"]["food_businesses"] == []
    assert data["supporting_analysis"]["food_count"] == 0
    assert data["supporting_analysis"]["night_business_count"] == 0


def test_report_prompt_requires_night_consumption_evidence_and_disclosure():
    assert "## 五、夜间消费环境分析" in SITE_SELECTION_REPORT_PROMPT
    assert "supporting_analysis" in SITE_SELECTION_REPORT_PROMPT
    assert "pending_review 不能作为事实描述" in SITE_SELECTION_REPORT_PROMPT
    assert "便利店等于24小时营业" in SITE_SELECTION_REPORT_PROMPT
    assert "detail_completeness" in SITE_SELECTION_REPORT_PROMPT


def test_ai_input_handles_insufficient_rent_samples(client):
    project_id = create_project(client)
    import_data(
        client,
        project_id,
        "rent",
        {
            "location_type": "候选商铺",
            "monthly_rent": 30000,
            "area_sqm": 500,
            "status": "confirmed",
            "source": "manual",
        },
    )
    client.post(f"/api/projects/{project_id}/score")

    with SessionLocal() as db:
        data = build_ai_input(db, project_id).model_dump(mode="python")

    assert data["rent_analysis"]["confirmed_rent_count"] == 1
    assert data["rent_analysis"]["rent_pressure"] == "medium"
    assert "租金样本不足" in data["score_result"]["missing_data"]


def test_ai_input_does_not_send_rejected_rent(client):
    project_id = create_project(client)
    import_data(
        client,
        project_id,
        "rent",
        {
            "location_type": "无效租金样本",
            "monthly_rent": 999999,
            "area_sqm": 100,
            "status": "rejected",
            "source": "manual",
        },
    )
    client.post(f"/api/projects/{project_id}/score")

    with SessionLocal() as db:
        data = build_ai_input(db, project_id).model_dump(mode="python")

    assert data["rent"] == {}
    assert data["rent_analysis"]["confirmed_rent_count"] == 0
    assert data["rent_analysis"]["average_monthly_rent"] is None


def test_report_prompt_requires_rent_evidence_and_truthfulness():
    assert "## 六、租金成本分析" in SITE_SELECTION_REPORT_PROMPT
    assert "只能使用输入中的 rent_analysis" in SITE_SELECTION_REPORT_PROMPT
    assert "有效租金样本数量、平均租金单价、租金压力等级和数据完整度" in SITE_SELECTION_REPORT_PROMPT
    assert "禁止推测城市租金水平" in SITE_SELECTION_REPORT_PROMPT
    assert "禁止预测营业收入" in SITE_SELECTION_REPORT_PROMPT
    assert "禁止根据租金直接判断项目是否盈利" in SITE_SELECTION_REPORT_PROMPT


def test_ai_report_is_saved_with_call_log(client, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()

    def fake_generate_report(self, analysis_input, prompt=None):
        return DeepSeekResult(
            content="# 电竞馆选址分析报告\n\n## 一、综合结论\n谨慎推荐。",
            model="deepseek-chat",
            duration_ms=20,
            input_length=123,
            output_length=45,
        )

    monkeypatch.setattr("app.llm.client.DeepSeekClient.generate_report", fake_generate_report)
    project_id = seed_project_for_ai(client)
    response = client.post(f"/api/projects/{project_id}/ai-report")

    assert response.status_code == 200
    report_id = int(response.json()["report_id"])
    with SessionLocal() as db:
        report = db.get(AIReportRecord, report_id)
        logs = db.query(AICallLogRecord).filter(AICallLogRecord.report_id == report_id).all()
    assert report is not None
    assert report.project_id == project_id
    assert report.input_snapshot["project"]["project_id"] == project_id
    assert report.score_snapshot["total_score"] >= 0
    assert len(logs) == 1
    assert logs[0].input_length == 123
    assert logs[0].output_length == 45


def test_ai_report_project_not_found(client):
    response = client.post("/api/projects/not-exists/ai-report")
    assert response.status_code == 404
