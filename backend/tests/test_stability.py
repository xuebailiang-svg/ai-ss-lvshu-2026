import os

from app.core.config import get_settings
from app.feedback import SiteFeedbackStore
from app.trace import AgentTraceStore


def agent_payload(index: int = 0):
    return {
        "address": f"雁塔区小寨西路{index}号",
        "city": "西安市",
        "radius_meters": 1000,
        "business_type": "电竞馆",
    }


def test_agent_run_10_times_stably(client):
    task_ids = []
    for index in range(10):
        response = client.post("/api/agent/site-selection/run", json=agent_payload(index))
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"]
        assert data["status"] in {"completed", "completed_with_warnings"}
        assert data["final_score"]["total"] is not None
        task_ids.append(data["task_id"])

    assert len(set(task_ids)) == 10


def test_amap_mock_true_false_modes_do_not_crash(client):
    original = os.environ.get("AMAP_MOCK")
    try:
        for value in ("true", "false"):
            os.environ["AMAP_MOCK"] = value
            get_settings.cache_clear()
            response = client.post("/api/agent/site-selection/run", json=agent_payload(1 if value == "true" else 2))
            assert response.status_code == 200
            assert response.json()["task_id"]
    finally:
        if original is None:
            os.environ.pop("AMAP_MOCK", None)
        else:
            os.environ["AMAP_MOCK"] = original
        get_settings.cache_clear()


def test_feedback_store_continuous_writes(client):
    task_ids = []
    for index in range(5):
        run = client.post("/api/agent/site-selection/run", json=agent_payload(index)).json()
        task_ids.append(run["task_id"])
        feedback = client.post("/api/feedback/site-result", json={
            "task_id": run["task_id"],
            "actual_result": "unknown",
            "notes": f"stability-{index}",
        })
        assert feedback.status_code == 200

    records = SiteFeedbackStore().list_records()
    assert all(task_id in {row["task_id"] for row in records} for task_id in task_ids)


def test_trace_store_continuous_writes(client):
    task_ids = []
    for index in range(5):
        run = client.post("/api/agent/site-selection/run", json=agent_payload(index)).json()
        task_ids.append(run["task_id"])

    store = AgentTraceStore()
    for task_id in task_ids:
        trace = store.get_trace(task_id)
        assert trace
        assert trace["trace"]
        assert trace["trace"][0]["step_name"] == "planner"


def test_similar_cases_empty_data_returns_stably(client):
    response = client.post("/api/agent/site-selection/run", json=agent_payload(0))
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data.get("similar_cases"), list)
