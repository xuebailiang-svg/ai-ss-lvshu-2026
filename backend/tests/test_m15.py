from datetime import datetime, timezone

from app.core.database import SessionLocal
from app.models import PoiObservation


def base_payload(**property_overrides):
    return {
        "name": "M1.5测试点",
        "city": "西安市",
        "address": "雁塔区小寨西路",
        "radius": 3000,
        "property": {
            "area_sqm": 600,
            "monthly_rent": 90000,
            "use_allowed": True,
            "fire_confirmed": True,
            "power_sufficient": True,
            "night_entrance": True,
            **property_overrides,
        },
    }


def create_eval(client, **property_overrides):
    response = client.post("/api/evaluations", json=base_payload(**property_overrides))
    assert response.status_code == 201
    return response.json()["id"]


def add_competitor(evaluation_id: int, name="强竞品网咖"):
    with SessionLocal() as db:
        poi = PoiObservation(
            evaluation_id=evaluation_id,
            source="amap",
            provider_record_id=f"manual-{evaluation_id}-{name}",
            name=name,
            category="竞品",
            type_code="080000",
            address="附近商圈",
            longitude=108.9,
            latitude=34.2,
            distance_m=450,
            confidence=0.75,
            needs_verification=True,
            raw_data={"test": True},
        )
        db.add(poi)
        db.commit()
        db.refresh(poi)
        return poi.id


def test_competitor_enrichment_create_update_and_history(client):
    evaluation_id = create_eval(client)
    poi_id = add_competitor(evaluation_id)
    body = {
        "machine_count": 120,
        "area_sqm": 800,
        "cpu": "i7",
        "gpu": "RTX 4070",
        "monitor_size_inch": 27,
        "monitor_refresh_rate": 240,
        "normal_price": 8,
        "premium_price": 12,
        "private_room_price": 20,
        "member_price": 6,
        "recharge_promotion": "充500送100",
        "opened_at_estimate": "2024年",
        "opening_basis": "门店招牌和点评记录",
        "peak_occupancy_rate": 0.8,
        "offpeak_occupancy_rate": 0.35,
        "surveyed_at": datetime.now(timezone.utc).isoformat(),
        "survey_method": "现场观察",
        "source": "人工调研",
        "confidence": 0.9,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "is_manually_verified": True,
        "notes": "周末客流强",
    }
    first = client.put(f"/api/competitors/{poi_id}/enrichment", json=body)
    assert first.status_code == 200
    assert first.json()["machine_count"] == 120
    body["machine_count"] = 130
    second = client.put(f"/api/competitors/{poi_id}/enrichment", json=body)
    assert second.status_code == 200
    assert second.json()["machine_count"] == 130
    history = client.get(f"/api/competitors/{poi_id}/enrichments").json()
    assert history["latest"]["machine_count"] == 130
    assert len(history["records"]) == 2


def test_property_survey_save_and_rent_conversion(client):
    evaluation_id = create_eval(client)
    response = client.put(
        f"/api/evaluations/{evaluation_id}/property",
        json={
            "area_sqm": 500,
            "usable_area_sqm": 450,
            "rent_per_sqm_day": 3,
            "machine_count": 100,
            "source": "物业访谈",
            "confidence": 0.8,
            "fire_confirmed": True,
            "power_sufficient": True,
            "night_entrance": True,
            "use_allowed": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["monthly_rent"] == 40500
    assert data["rent_per_sqm_month"] == 90
    assert data["rent_per_machine_month"] == 405


def test_property_hard_risk_recognition(client):
    evaluation_id = create_eval(client, use_allowed=False, fire_confirmed=False, power_sufficient=False, night_entrance=False)
    result = client.post(f"/api/evaluations/{evaluation_id}/score").json()
    codes = {item["code"] for item in result["hard_risks"]}
    assert "PROPERTY_USE_ALLOWED" in codes
    assert "PROPERTY_FIRE_CONFIRMED" in codes
    assert "PROPERTY_POWER_SUFFICIENT" in codes
    assert "PROPERTY_NIGHT_ENTRANCE" in codes


def test_missing_data_lowers_completeness_and_manual_verification_improves_confidence(client):
    sparse_id = client.post("/api/evaluations", json={"name": "缺数据", "city": "西安市", "address": "测试路", "property": {}}).json()["id"]
    sparse = client.post(f"/api/evaluations/{sparse_id}/score").json()
    enriched_id = create_eval(client)
    poi_id = add_competitor(enriched_id)
    client.put(
        f"/api/competitors/{poi_id}/enrichment",
        json={"machine_count": 100, "normal_price": 8, "peak_occupancy_rate": 0.7, "source": "人工", "confidence": 0.95, "is_manually_verified": True, "verified_at": datetime.now(timezone.utc).isoformat()},
    )
    enriched = client.post(f"/api/evaluations/{enriched_id}/score").json()
    assert sparse["completeness"] < enriched["completeness"]
    assert sparse["confidence"] < enriched["confidence"]


def test_comparison_api_and_report_manual_estimated_labels(client):
    first_id = create_eval(client)
    second_response = client.post("/api/evaluations", json={**base_payload(), "name": "对比点2", "address": "另一个地址"})
    second_id = second_response.json()["id"]
    poi_id = add_competitor(first_id)
    client.put(
        f"/api/competitors/{poi_id}/enrichment",
        json={"machine_count": 90, "peak_occupancy_rate": 0.7, "source": "人工调研", "confidence": 0.8, "is_manually_verified": True},
    )
    client.post(f"/api/evaluations/{first_id}/score")
    client.post(f"/api/evaluations/{second_id}/score")
    compare = client.post("/api/evaluations/compare", json={"evaluation_ids": [first_id, second_id]})
    assert compare.status_code == 200
    assert len(compare.json()["items"]) == 2
    report = client.get(f"/api/evaluations/{first_id}/report").json()
    assert report["sections"]["competitors"]["manual_survey_count"] == 1
    assert report["sections"]["competitors"]["items"][0]["occupancy"]["label"] == "估算值"
    assert report["sections"]["data_sources"]["manual"]
