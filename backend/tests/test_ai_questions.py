from __future__ import annotations

import json

import httpx

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.llm.schemas import DeepSeekResult
from app.models import SupplementRecord, UnifiedCompetitorRecord


def create_project(client) -> str:
    response = client.post(
        "/api/projects",
        json={
            "name": "AI有限追问测试",
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


def configure_ai(monkeypatch, selector=None):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()

    def fake_generate(self, analysis_input, prompt=None):
        candidates = analysis_input["allowed_candidates"]
        selected = selector(candidates) if selector else candidates[:3]
        content = json.dumps(
            {
                "questions": [
                    {
                        "candidate_id": item["candidate_id"],
                        "title": item["title"],
                        "help_text": item["help_text"],
                    }
                    for item in selected
                ]
            },
            ensure_ascii=False,
        )
        return DeepSeekResult(
            content=content,
            model="deepseek-chat",
            duration_ms=1,
            input_length=10,
            output_length=10,
        )

    monkeypatch.setattr("app.llm.client.DeepSeekClient.generate_report", fake_generate)


def test_first_round_has_at_most_three_allowed_questions(client, monkeypatch):
    configure_ai(monkeypatch)
    project_id = create_project(client)

    response = client.post(f"/api/projects/{project_id}/ai-questions", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "questions_ready"
    assert body["round"] == 1
    assert 1 <= len(body["questions"]) <= 3
    assert all(item["field_key"].startswith("property:primary:") for item in body["questions"])
    assert all(item["field_key"].rsplit(":", 1)[-1] in {"address", "area_sqm", "monthly_rent"} for item in body["questions"])


def test_answers_write_user_values_and_unknown_without_repeat(client, monkeypatch):
    configure_ai(monkeypatch)
    project_id = create_project(client)
    questions = client.post(f"/api/projects/{project_id}/ai-questions", json={}).json()["questions"]

    response = client.post(
        f"/api/projects/{project_id}/ai-questions/answers",
        json={
            "answers": [
                {"question_id": questions[0]["question_id"], "value": "候选物业A"},
                {"question_id": questions[1]["question_id"], "unknown": True},
                {"question_id": questions[2]["question_id"], "skip": True},
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["saved_count"] == 1
    assert response.json()["unknown_count"] == 1
    assert response.json()["skipped_count"] == 1
    with SessionLocal() as db:
        property_row = db.query(SupplementRecord).filter_by(
            project_id=project_id, target_type="candidate_property", field_name="manual_detail"
        ).one()
        assert property_row.value["address"] == "候选物业A"
        assert "area_sqm" in property_row.raw_data["_manual_meta"]["unknown_fields"]

    same_round = client.post(f"/api/projects/{project_id}/ai-questions", json={}).json()
    assert same_round["status"] == "round_complete"
    assert all(item["field_key"] not in {question["field_key"] for question in questions} for item in same_round["questions"])


def test_second_round_and_total_question_limit(client, monkeypatch):
    configure_ai(monkeypatch)
    project_id = create_project(client)
    first = client.post(f"/api/projects/{project_id}/ai-questions", json={}).json()
    client.post(
        f"/api/projects/{project_id}/ai-questions/answers",
        json={"answers": [{"question_id": item["question_id"], "unknown": True} for item in first["questions"]]},
    )

    second = client.post(
        f"/api/projects/{project_id}/ai-questions", json={"continue_round": True}
    ).json()
    assert second["round"] == 2
    assert len(second["questions"]) == 2
    assert second["asked_count"] == 5
    client.post(
        f"/api/projects/{project_id}/ai-questions/answers",
        json={"answers": [{"question_id": item["question_id"], "unknown": True} for item in second["questions"]]},
    )
    stopped = client.post(
        f"/api/projects/{project_id}/ai-questions", json={"continue_round": True}
    ).json()
    assert stopped["status"] == "limit_reached"
    assert stopped["questions"] == []


def test_invalid_or_out_of_catalog_ai_output_is_safely_skipped(client, monkeypatch):
    configure_ai(monkeypatch, selector=lambda candidates: [{**candidates[0], "candidate_id": "profit_prediction"}])
    project_id = create_project(client)

    body = client.post(f"/api/projects/{project_id}/ai-questions", json={}).json()

    assert body["status"] == "skipped"
    assert body["questions"] == []
    with SessionLocal() as db:
        assert db.query(SupplementRecord).filter_by(project_id=project_id, target_type="ai_question").count() == 0


def test_ai_network_failure_is_safely_skipped(client, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()

    def fail_generate(self, analysis_input, prompt=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("app.llm.client.DeepSeekClient.generate_report", fail_generate)
    project_id = create_project(client)

    response = client.post(f"/api/projects/{project_id}/ai-questions", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "skipped"
    assert response.json()["questions"] == []


def test_existing_competitor_values_and_unknown_fields_are_not_asked(client, monkeypatch):
    configure_ai(monkeypatch, selector=lambda candidates: candidates)
    project_id = create_project(client)
    with SessionLocal() as db:
        db.add(
            UnifiedCompetitorRecord(
                project_id=project_id,
                name="已核实电竞馆",
                distance_meters=200,
                hour_price=12,
                machine_count=100,
                source="amap",
                status="confirmed",
                raw_data={"_manual_meta": {"unknown_fields": ["gpu", "occupancy_rate"]}},
            )
        )
        db.commit()

    body = client.post(f"/api/projects/{project_id}/ai-questions", json={}).json()

    assert all(not item["field_key"].startswith("competitor:") for item in body["questions"])


def test_answer_validation_rejects_duplicate_submission(client, monkeypatch):
    configure_ai(monkeypatch)
    project_id = create_project(client)
    question = client.post(f"/api/projects/{project_id}/ai-questions", json={}).json()["questions"][0]
    payload = {"answers": [{"question_id": question["question_id"], "unknown": True}]}

    assert client.post(f"/api/projects/{project_id}/ai-questions/answers", json=payload).status_code == 200
    duplicate = client.post(f"/api/projects/{project_id}/ai-questions/answers", json=payload)
    assert duplicate.status_code == 422


def test_answer_revalidates_field_is_still_missing(client, monkeypatch):
    configure_ai(monkeypatch)
    project_id = create_project(client)
    question = client.post(f"/api/projects/{project_id}/ai-questions", json={}).json()["questions"][0]
    with SessionLocal() as db:
        now_known = SupplementRecord(
            project_id=project_id,
            target_type="candidate_property",
            target_id="primary",
            field_name="manual_detail",
            value={"address": "已由其他人工流程补充"},
            source="manual",
            confidence=1,
            status="confirmed",
            raw_data={},
        )
        db.add(now_known)
        db.commit()

    response = client.post(
        f"/api/projects/{project_id}/ai-questions/answers",
        json={"answers": [{"question_id": question["question_id"], "unknown": True}]},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "field already has a value"
