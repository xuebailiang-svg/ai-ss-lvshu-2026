from __future__ import annotations

from app.chat.context import build_project_chat_context
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.llm.schemas import DeepSeekResult
from app.models import ChatSessionRecord


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


def seed_chat_project(client):
    project_id = create_project(client)
    import_data(client, project_id, "poi", {"name": "小寨地铁站", "category": "transport", "sub_category": "地铁", "source": "amap"})
    import_data(client, project_id, "competitor", {"name": "XX电竞馆", "distance_meters": 500, "source": "amap"})
    import_data(client, project_id, "rent", {"monthly_rent": 30000, "area_sqm": 500, "rent_per_sqm": 60, "source": "manual"})
    client.post(f"/api/projects/{project_id}/score")
    return project_id


def fake_chat_answer(content: str = "根据当前项目评分和竞品数据，主要问题是竞品数据不完整。"):
    def _fake(self, chat_input, prompt):
        assert "project" in chat_input
        assert "dataset" in chat_input
        assert "score" in chat_input
        assert "chat_history" in chat_input
        return DeepSeekResult(
            content=content,
            model="deepseek-chat",
            duration_ms=8,
            input_length=100,
            output_length=len(content),
        )

    return _fake


def test_create_chat_session(client):
    project_id = seed_chat_project(client)

    response = client.post(f"/api/projects/{project_id}/chat/session")

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == project_id
    assert body["session_id"].isdigit()


def test_send_message_success(client, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()
    monkeypatch.setattr("app.llm.client.DeepSeekClient.generate_chat", fake_chat_answer())
    project_id = seed_chat_project(client)
    session_id = client.post(f"/api/projects/{project_id}/chat/session").json()["session_id"]

    response = client.post(f"/api/chat/{session_id}/message", json={"message": "为什么这个地址不推荐？"})

    assert response.status_code == 200
    body = response.json()
    assert "竞品数据" in body["answer"]
    assert "score_result" in body["references"]
    assert "competitor_data" in body["references"]


def test_chat_history_saved(client, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()
    monkeypatch.setattr("app.llm.client.DeepSeekClient.generate_chat", fake_chat_answer("已保存历史。"))
    project_id = seed_chat_project(client)
    session_id = client.post(f"/api/projects/{project_id}/chat/session").json()["session_id"]

    client.post(f"/api/chat/{session_id}/message", json={"message": "请解释评分"})
    response = client.get(f"/api/chat/{session_id}/messages")

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == project_id
    assert len(body["messages"]) == 2
    assert [item["role"] for item in body["messages"]] == ["user", "assistant"]


def test_project_context_loads_dataset_score_report_and_history(client, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()
    monkeypatch.setattr("app.llm.client.DeepSeekClient.generate_report", lambda self, data, prompt=None: DeepSeekResult(content="# 电竞馆选址分析报告", model="deepseek-chat", duration_ms=1, input_length=1, output_length=1))
    project_id = seed_chat_project(client)
    client.post(f"/api/projects/{project_id}/ai-report")
    session_id = client.post(f"/api/projects/{project_id}/chat/session").json()["session_id"]

    with SessionLocal() as db:
        session = db.get(ChatSessionRecord, int(session_id))
        context = build_project_chat_context(db, session, "为什么评分低？")

    assert context["project"]["project_id"] == project_id
    assert context["dataset"]["competitors"]
    assert context["score"]["total_score"] >= 0
    assert "电竞馆选址分析报告" in context["latest_report"]["content"]
    assert isinstance(context["chat_history"], list)


def test_deepseek_mock_called_for_simulation(client, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()
    monkeypatch.setattr("app.llm.client.DeepSeekClient.generate_chat", fake_chat_answer("租金降低后，成本因素会提升。"))
    project_id = seed_chat_project(client)
    session_id = client.post(f"/api/projects/{project_id}/chat/session").json()["session_id"]

    response = client.post(f"/api/chat/{session_id}/message", json={"message": "如果租金降低30%，会怎么样？"})

    assert response.status_code == 200
    body = response.json()
    assert body["simulation"]["simulation"] is True
    assert body["simulation"]["type"] == "rent_reduction"
    assert "simulation" in body["references"]


def test_history_limit_creates_summary(client, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()
    monkeypatch.setattr("app.llm.client.DeepSeekClient.generate_chat", fake_chat_answer("简短回答"))
    project_id = seed_chat_project(client)
    session_id = client.post(f"/api/projects/{project_id}/chat/session").json()["session_id"]

    for index in range(22):
        response = client.post(f"/api/chat/{session_id}/message", json={"message": f"第{index}个问题"})
        assert response.status_code == 200

    history = client.get(f"/api/chat/{session_id}/messages").json()
    assert history["conversation_summary"]
    assert len(history["messages"]) == 44
