import pytest

from app.agents import SiteSelectionAgent
from app.core.config import get_settings
from app.feedback import SiteFeedbackStore
from app.providers.amap import ProviderError
from app.providers.amap.provider import AmapDataProvider
from app.tools.base import BaseTool
from app.tools.base_validator import ToolOutputValidator
from app.tools.competitor import CompetitorSearchTool
from app.tools.geocode import GeocodeTool
from app.tools.redline import RedlineCheckTool
from app.trace import AgentTraceStore


def test_site_selection_agent_api_runs_controlled_workflow(client):
    response = client.post("/api/agent/site-selection/run", json={
        "address": "雁塔区小寨西路",
        "city": "西安市",
        "radius_meters": 1000,
        "business_type": "电竞馆",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["task_id"]
    assert data["status"] in {"completed", "completed_with_warnings"}
    assert data["input"]["city"] == "西安市"
    assert len(data["plan"]) == 11
    assert data["plan_reasoning"]
    assert len(data["steps"]) == 12
    assert [step["tool_name"] for step in data["steps"][:11]] == [
        "geocode",
        "poi_search",
        "redline_check",
        "competitor_search",
        "traffic_analysis",
        "supporting_analysis",
        "rent_estimate",
        "population_estimate",
        "scoring",
        "similar_case_search",
        "report_generate",
    ]
    assert data["steps"][-1]["tool_name"] == "reflection"
    assert data["reflection"]["recommendation"]
    assert data["final_score"]["total"] is not None
    assert data["report"]["summary"]
    assert data["report"]["reflection"]
    assert data["report"]["decision_factors"]
    assert data["report"]["negative_factors"]
    assert data["report"]["feature_importance_guess"]
    assert data["report"]["uncertainty_analysis"]
    assert "risk_of_overestimate" in data["reflection"]
    assert "adjusted_score_suggestion" in data["reflection"]
    assert "final_confidence" in data["reflection"]
    assert data["feedback_record"]["task_id"] == data["task_id"]
    assert data["trace_summary"]["total_steps"] == len(data["trace"])
    assert data["trace_summary"]["total_steps"] == len(data["steps"]) + 1
    assert data["trace"][0]["step_name"] == "planner"
    assert data["agent_state"]["geo"]["location"]["longitude"] is not None
    assert data["steps"][0]["sources"]
    assert "warnings" in data["steps"][0]
    assert data["data_gaps"]
    assert data["manual_check_items"]
    warnings = [warning for step in data["steps"] for warning in step.get("warnings", [])]
    assert any("模拟" in warning or "未接入" in warning or "代理指标" in warning for warning in warnings)
    stored = SiteFeedbackStore().list_records()
    assert stored and stored[0]["task_id"] == data["task_id"]
    events = SiteFeedbackStore().events_for_task(data["task_id"])
    assert [event["event_type"] for event in events] == ["agent_run_completed", "feedback_initialized"]
    trace_record = AgentTraceStore().get_trace(data["task_id"])
    assert trace_record and len(trace_record["trace"]) == len(data["steps"]) + 1


@pytest.mark.anyio
async def test_geocode_fallback_mock_when_amap_fails(monkeypatch):
    async def raise_error(self, address, city=None):
        raise ProviderError("Amap API failed: INVALID_USER_KEY (10001)", error_code="AMAP_KEY_PERMISSION")

    monkeypatch.setattr(AmapDataProvider, "geocode", raise_error)
    result = await GeocodeTool().run({"input": {"city": "西安市", "address": "雁塔区小寨西路"}})

    assert result.status == "success"
    assert result.data["is_mock"] is True
    assert result.data["location"]["longitude"] is not None
    assert "amap_mock_geocode" in result.sources
    assert any("mock geocode" in warning for warning in result.warnings)


@pytest.mark.anyio
async def test_agent_keeps_running_when_poi_partial_success(monkeypatch, client):
    async def fake_search(self, longitude, latitude, radius, categories):
        self.last_poi_diagnostics = {
            "failed_keywords": [
                {
                    "category": "交通",
                    "keyword": "公交车站",
                    "infocode": "10021",
                    "info": "CUQPS_HAS_EXCEEDED_THE_LIMIT",
                    "error_code": "AMAP_RATE_LIMIT",
                    "message": "高德接口请求过快，触发限流",
                }
            ]
        }
        return [
            {
                "source": "amap",
                "provider_record_id": "poi-1",
                "name": "测试电竞馆",
                "category": "竞品",
                "type_code": "080000",
                "address": "测试地址",
                "longitude": 108.9,
                "latitude": 34.2,
                "distance_m": 120,
                "confidence": 0.75,
                "raw_data": {},
            }
        ]

    monkeypatch.setattr(AmapDataProvider, "search_nearby", fake_search)
    response = client.post("/api/agent/site-selection/run", json={
        "address": "雁塔区小寨西路",
        "city": "西安市",
        "radius_meters": 1000,
        "business_type": "电竞馆",
    })
    data = response.json()
    poi_step = next(step for step in data["steps"] if step["tool_name"] == "poi_search")

    assert response.status_code == 200
    assert data["status"] in {"completed", "completed_with_warnings"}
    assert poi_step["output"]["data"]["partial_success"] is True
    assert any("partial_success" in issue for issue in data["reflection"]["issues"])


@pytest.mark.anyio
async def test_competitor_search_does_not_fabricate_missing_fields():
    context = {
        "input": {"radius_meters": 1000},
        "agent_state": {
            "poi": [
                {
                    "source": "amap",
                    "name": "某某电竞网咖",
                    "category": "竞品",
                    "address": "测试地址",
                    "distance_m": 88,
                    "longitude": 108.9,
                    "latitude": 34.2,
                }
            ]
        },
    }
    result = await CompetitorSearchTool().run(context)
    competitor = result.data["competitors"][0]

    assert result.status == "success"
    assert "价格" in competitor["missing_fields"]
    assert "上座率" in competitor["missing_fields"]
    assert "price" not in competitor


@pytest.mark.anyio
async def test_redline_check_detects_sensitive_place_within_200m():
    context = {
        "geocode": {"location": {"longitude": 108.9, "latitude": 34.2}},
        "agent_state": {
            "geo": {"location": {"longitude": 108.9, "latitude": 34.2}},
            "poi": [
                {
                    "source": "amap",
                    "name": "测试小学",
                    "category": "小学",
                    "address": "测试地址",
                    "distance_m": 150,
                }
            ],
        },
    }
    result = await RedlineCheckTool().run(context)

    assert result.status == "success"
    assert result.data["risk_level"] == "high"
    assert result.data["violations"][0]["distance_meters"] == 150
    assert "amap_poi" in result.sources


def test_feedback_update_api(client):
    response = client.post("/api/agent/site-selection/run", json={
        "address": "雁塔区小寨西路",
        "city": "西安市",
        "radius_meters": 1000,
        "business_type": "电竞馆",
    })
    task_id = response.json()["task_id"]
    feedback = client.post("/api/feedback/site-result", json={
        "task_id": task_id,
        "actual_result": "profit",
        "notes": "试营业表现良好",
        "monthly_revenue_range": "10-20万",
    })

    assert feedback.status_code == 200
    row = feedback.json()["record"]
    assert row["actual_business_result"] == "profit"
    assert row["user_feedback"] == "试营业表现良好"
    events = SiteFeedbackStore().events_for_task(task_id)
    assert events[-1]["event_type"] == "feedback_updated"


def test_similar_case_search_uses_feedback_store(client):
    first = client.post("/api/agent/site-selection/run", json={
        "address": "雁塔区小寨西路",
        "city": "西安市",
        "radius_meters": 1000,
        "business_type": "电竞馆",
    }).json()
    client.post("/api/feedback/site-result", json={
        "task_id": first["task_id"],
        "actual_result": "profit",
        "notes": "盈利",
    })

    second = client.post("/api/agent/site-selection/run", json={
        "address": "雁塔区小寨西路2号",
        "city": "西安市",
        "radius_meters": 1000,
        "business_type": "电竞馆",
    }).json()

    assert second["similar_cases"]
    assert second["similar_cases"][0]["historical_result"] == "profit"


def test_trace_debug_api_returns_full_trace(client):
    import os
    os.environ["ENABLE_DEBUG_API"] = "true"
    get_settings.cache_clear()
    response = client.post("/api/agent/site-selection/run", json={
        "address": "雁塔区小寨西路",
        "city": "西安市",
        "radius_meters": 1000,
        "business_type": "电竞馆",
    })
    task_id = response.json()["task_id"]
    trace = client.get(f"/api/agent/site-selection/trace/{task_id}")

    assert trace.status_code == 200
    data = trace.json()
    assert data["task_id"] == task_id
    assert data["summary"]["total_steps"] == len(data["trace"])
    assert data["trace"][0]["step_name"] == "planner"
    assert data["reflection"]
    assert "feedback_events" in data
    os.environ.pop("ENABLE_DEBUG_API", None)
    get_settings.cache_clear()


@pytest.mark.anyio
async def test_tool_failure_is_recorded_in_trace():
    class FailingGeocodeTool(BaseTool):
        tool_name = "geocode"

        async def run(self, context):
            raise RuntimeError("boom")

    data = await SiteSelectionAgent(tools=[FailingGeocodeTool()]).run({
        "address": "雁塔区小寨西路",
        "city": "西安市",
        "radius_meters": 1000,
        "business_type": "电竞馆",
    })
    trace = AgentTraceStore().get_trace(data["task_id"])["trace"]

    assert any(step["status"] == "failed" for step in trace)
    assert all("input" in step and "output" in step and "duration_ms" in step for step in trace)


def test_tool_output_validator_normalizes_invalid_output():
    result = ToolOutputValidator.validate(
        {"tool_name": "bad_tool", "status": "broken", "confidence": 2, "sources": "x", "warnings": "w", "data": []},
        fallback_tool_name="bad_tool",
    )

    assert result.status == "failed"
    assert result.confidence == 1
    assert result.sources == ["x"]
    assert isinstance(result.data, dict)
    assert any("Invalid tool status" in warning for warning in result.warnings)


def test_debug_api_disabled_returns_403(client):
    get_settings.cache_clear()
    response = client.get("/api/agent/site-selection/trace/not-exists")
    assert response.status_code == 403


def test_system_health_returns_module_status(client):
    response = client.get("/api/system/health")
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "v1.0-beta"
    assert data["modules"]["tools"] is True
    assert data["modules"]["planner"] is True
    assert data["modules"]["amap"] is True


def test_feedback_store_file_is_created_when_missing():
    store = SiteFeedbackStore()
    if store.path.exists():
        store.path.unlink()
    ok, error = store.can_write()
    assert ok, error
    assert store.path.exists()


@pytest.mark.anyio
async def test_trace_write_failure_does_not_break_agent(monkeypatch):
    def raise_write(self, data):
        raise OSError("disk readonly")

    monkeypatch.setattr(AgentTraceStore, "_write", raise_write)
    data = await SiteSelectionAgent().run({
        "address": "雁塔区小寨西路",
        "city": "西安市",
        "radius_meters": 1000,
        "business_type": "电竞馆",
    })
    assert data["task_id"]
    assert data["status"] in {"completed", "completed_with_warnings"}


def test_feedback_event_log_appends_events(client):
    response = client.post("/api/agent/site-selection/run", json={
        "address": "雁塔区小寨西路",
        "city": "西安市",
        "radius_meters": 1000,
        "business_type": "电竞馆",
    })
    task_id = response.json()["task_id"]
    client.post("/api/feedback/site-result", json={"task_id": task_id, "actual_result": "loss", "notes": "样本"})
    events = SiteFeedbackStore().events_for_task(task_id)
    assert [event["event_type"] for event in events] == ["agent_run_completed", "feedback_initialized", "feedback_updated"]
