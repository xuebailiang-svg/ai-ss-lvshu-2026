from __future__ import annotations

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.llm.schemas import DeepSeekResult
from app.llm.service import build_ai_input
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
        {"name": "XX电竞馆", "machine_count": 100, "gpu": "RTX 3060", "hour_price": 15, "occupancy_rate": 0.7, "source": "manual"},
    )
    import_data(client, project_id, "rent", {"monthly_rent": 30000, "area_sqm": 500, "rent_per_sqm": 60, "source": "manual"})
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


def test_mock_deepseek_returns_report(client, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()

    def fake_generate_report(self, analysis_input, prompt=None):
        assert analysis_input["score_result"]["total_score"] >= 0
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
    assert set(data) == {"project", "location", "environment", "competitors", "rent", "score_result", "data_quality", "risks"}
    assert data["project"]["project_id"] == project_id
    assert "transport" in data["environment"]
    assert "population" in data["environment"]
    assert "support" in data["environment"]
    assert data["competitors"]
    assert data["score_result"]["total_score"] >= 0


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
