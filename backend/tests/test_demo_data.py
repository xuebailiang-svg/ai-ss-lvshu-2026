from __future__ import annotations

from app.core.database import SessionLocal
from app.llm.service import build_ai_input
from app.models import RentDataRecord, UnifiedCompetitorRecord


def create_project(client):
    response = client.post(
        "/api/projects",
        json={
            "name": "小寨电竞馆选址演示",
            "city": "西安市",
            "district": "雁塔区",
            "address": "小寨地铁站",
            "longitude": 108.946767,
            "latitude": 34.222838,
            "radius_meters": 1000,
            "business_type": "电竞馆",
            "expected_area_sqm": 520,
            "investment_budget": 180,
        },
    )
    assert response.status_code == 200
    return response.json()["project_id"]


def import_data(client, project_id: str, data_type: str, data: dict):
    response = client.post(f"/api/projects/{project_id}/data/import", json={"type": data_type, "data": data})
    assert response.status_code == 200
    return response.json()["data"]


def test_generate_demo_data_enriches_existing_project_data(client):
    project_id = create_project(client)
    import_data(client, project_id, "competitor", {"name": "待补充电竞馆", "distance_meters": 350, "source": "amap"})
    import_data(client, project_id, "food", {"name": "待确认餐饮", "distance_meters": 280, "source": "amap"})

    response = client.post(f"/api/projects/{project_id}/demo-data/generate", json={"include": ["competitor", "supporting", "rent"]})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["updated"]["competitors"] == 1
    assert body["updated"]["supporting"] == 1
    assert body["generated"]["rent"] > 0
    assert "演示模拟数据" in body["warning"]

    with SessionLocal() as db:
        competitor = db.query(UnifiedCompetitorRecord).filter_by(project_id=project_id, name="待补充电竞馆").one()
        rent_rows = db.query(RentDataRecord).filter_by(project_id=project_id, source="simulation").all()

    assert competitor.status == "confirmed"
    assert competitor.hour_price is not None
    assert competitor.machine_count is not None
    assert competitor.raw_data["demo_generated"] is True
    assert rent_rows
    assert all(row.status == "confirmed" for row in rent_rows)


def test_generate_demo_data_marks_quality_and_ai_input_as_simulation(client):
    project_id = create_project(client)

    response = client.post(f"/api/projects/{project_id}/demo-data/generate", json={"include": ["competitor", "supporting", "rent"]})
    assert response.status_code == 200

    quality_response = client.get(f"/api/projects/{project_id}/data-quality")
    assert quality_response.status_code == 200
    quality = quality_response.json()
    assert "simulation_data_summary" not in quality

    client.post(f"/api/projects/{project_id}/score")
    with SessionLocal() as db:
        ai_input = build_ai_input(db, project_id).model_dump(mode="python")

    assert ai_input["simulation_data_summary"]["has_simulation_data"] is True
    assert ai_input["simulation_data_summary"]["total_count"] > 0
