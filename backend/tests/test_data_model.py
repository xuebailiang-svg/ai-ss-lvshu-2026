import pytest
from pydantic import ValidationError

from app.data_model import CompetitorData, POIData, convert_amap_poi, convert_manual_competitor


def test_amap_poi_converts_to_unified_poi_data():
    raw = {
        "id": "amap-1",
        "name": "小寨地铁站",
        "type": "地铁站",
        "typecode": "150500",
        "address": "西安市雁塔区",
        "location": "108.953421,34.229763",
        "distance": "520",
    }

    poi = convert_amap_poi(raw)

    assert isinstance(poi, POIData)
    assert poi.name == "小寨地铁站"
    assert poi.category == "transport"
    assert poi.longitude == 108.953421
    assert poi.latitude == 34.229763
    assert poi.distance_meters == 520
    assert poi.source == "amap"
    assert poi.confidence == 0.95
    assert poi.status == "confirmed"
    assert poi.raw_data["id"] == "amap-1"


def test_manual_competitor_chinese_fields_convert_to_competitor_data():
    raw = {
        "名称": "某某电竞馆",
        "地址": "小寨商圈",
        "距离": "800",
        "机器数量": "120",
        "显卡": "RTX 4060",
        "价格": "8",
        "上座率": "0.72",
        "月售": "180000",
    }

    competitor = convert_manual_competitor(raw)

    assert isinstance(competitor, CompetitorData)
    assert competitor.name == "某某电竞馆"
    assert competitor.distance_meters == 800
    assert competitor.machine_count == 120
    assert competitor.gpu == "RTX 4060"
    assert competitor.hour_price == 8
    assert competitor.occupancy_rate == 0.72
    assert competitor.monthly_sales == 180000
    assert competitor.source == "manual"
    assert competitor.confidence == 0.8


def test_missing_competitor_price_is_allowed():
    competitor = convert_manual_competitor({"名称": "只知道名字的网咖", "距离": "300"})

    assert competitor.name == "只知道名字的网咖"
    assert competitor.hour_price is None
    assert competitor.machine_count is None
    assert competitor.distance_meters == 300


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_confidence_must_be_between_zero_and_one(confidence):
    with pytest.raises(ValidationError):
        CompetitorData(name="非法置信度竞品", confidence=confidence)


def test_data_validate_api_converts_amap_poi(client):
    response = client.post("/api/data/validate", json={
        "data_type": "poi",
        "source": "amap",
        "data": {
            "name": "西安交通大学",
            "type": "大学",
            "location": "108.987,34.246",
            "distance": "900",
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["normalized_data"]["category"] == "education"
    assert body["normalized_data"]["source"] == "amap"
    assert body["warnings"] == []


def test_data_validate_api_reports_missing_competitor_fields(client):
    response = client.post("/api/data/validate", json={
        "data_type": "competitor",
        "data": {"名称": "缺少经营数据的竞品"},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["normalized_data"]["name"] == "缺少经营数据的竞品"
    assert "缺少竞品字段：hour_price" in body["warnings"]


def test_data_validate_api_rejects_invalid_confidence(client):
    response = client.post("/api/data/validate", json={
        "data_type": "competitor",
        "data": {"名称": "非法置信度竞品", "置信度": "1.2"},
    })

    assert response.status_code == 422
    body = response.json()["detail"]
    assert body["success"] is False
