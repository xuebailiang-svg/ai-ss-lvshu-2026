from __future__ import annotations

from app.data_source.base import ProviderAvailability
from app.data_source.registry import build_default_registry
from app.core.database import SessionLocal
from app.models import RentDataRecord


def create_project(client) -> str:
    response = client.post(
        "/api/projects",
        json={
            "name": "租金数据测试项目",
            "city": "西安市",
            "district": "雁塔区",
            "address": "小寨地铁站",
            "radius_meters": 1000,
            "business_type": "电竞馆",
        },
    )
    assert response.status_code == 200
    return response.json()["project_id"]


def upload_rent_csv(client, project_id: str, content: str):
    return client.post(
        f"/api/projects/{project_id}/rent/import",
        files={"file": ("rent.csv", content.encode("utf-8-sig"), "text/csv")},
    )


def import_rent_record(client, project_id: str, data: dict):
    response = client.post(
        f"/api/projects/{project_id}/data/import",
        json={"type": "rent", "data": data},
    )
    assert response.status_code == 200
    return response.json()["data"]


def test_manual_rent_provider_is_registered_and_available():
    provider = build_default_registry().get("manual_rent")

    assert provider.availability == ProviderAvailability.available
    assert provider.capabilities == ("rent",)


def test_rent_csv_import_and_query_list(client):
    project_id = create_project(client)
    response = upload_rent_csv(
        client,
        project_id,
        "地址,面积,月租金,物业费,转让费\n小寨商铺,500,30000,2000,50000\n",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["total_rows"] == 1
    assert body["imported_rows"] == 1
    assert body["failed_rows"] == 0

    rent = client.get(f"/api/projects/{project_id}/rent")
    assert rent.status_code == 200
    data = rent.json()
    assert data["total"] == 1
    assert data["incomplete_count"] == 0
    assert data["items"][0]["address"] == "小寨商铺"
    assert data["items"][0]["area_sqm"] == 500
    assert data["items"][0]["monthly_rent"] == 30000
    assert data["items"][0]["rent_unit_price"] == 60
    assert data["items"][0]["property_fee"] == 2000
    assert data["items"][0]["transfer_fee"] == 50000
    assert data["items"][0]["source"] == "manual"
    assert data["items"][0]["status"] == "pending_review"
    assert data["items"][0]["detail_completed"] is False


def test_rent_csv_requires_address_area_and_monthly_rent(client):
    project_id = create_project(client)
    response = upload_rent_csv(client, project_id, "面积,月租金\n500,30000\n")

    assert response.status_code == 400
    assert "缺少必填字段：地址" in response.json()["detail"]


def test_rent_csv_keeps_valid_rows_when_one_row_is_invalid(client):
    project_id = create_project(client)
    response = upload_rent_csv(
        client,
        project_id,
        "地址,面积,月租金,物业费,转让费\n有效商铺,400,24000,1200,0\n异常商铺,错误,20000,,\n",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_rows"] == 2
    assert body["imported_rows"] == 1
    assert body["failed_rows"] == 1
    assert body["errors"][0]["row"] == 3
    assert "面积必须为数字" in body["errors"][0]["reason"]

    rent = client.get(f"/api/projects/{project_id}/rent").json()
    assert rent["total"] == 1
    assert rent["items"][0]["address"] == "有效商铺"


def test_rent_list_returns_empty_structure(client):
    project_id = create_project(client)
    response = client.get(f"/api/projects/{project_id}/rent")

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "total": 0,
        "incomplete_count": 0,
        "confirmed_count": 0,
        "detail_completed_count": 0,
    }


def test_rent_csv_rejects_empty_file(client):
    project_id = create_project(client)
    response = client.post(
        f"/api/projects/{project_id}/rent/import",
        files={"file": ("rent.csv", b"", "text/csv")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "CSV文件为空"


def test_rent_review_supports_confirmed_rejected_and_pending(client):
    project_id = create_project(client)
    upload_rent_csv(client, project_id, "地址,面积,月租金\n测试商铺,300,18000\n")
    rent_id = client.get(f"/api/projects/{project_id}/rent").json()["items"][0]["id"]

    confirmed = client.post(
        f"/api/projects/{project_id}/rent/{rent_id}/review",
        json={"status": "confirmed"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    assert client.get(f"/api/projects/{project_id}/rent").json()["confirmed_count"] == 1

    rejected = client.post(
        f"/api/projects/{project_id}/rent/{rent_id}/review",
        json={"status": "rejected"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    pending = client.post(
        f"/api/projects/{project_id}/rent/{rent_id}/review",
        json={"status": "pending_review"},
    )
    assert pending.status_code == 200
    assert pending.json()["status"] == "pending_review"


def test_rent_detail_is_saved_in_manual_detail_without_losing_raw_data(client):
    project_id = create_project(client)
    upload_rent_csv(client, project_id, "地址,面积,月租金,物业费\n详情商铺,500,30000,1800\n")
    rent_id = client.get(f"/api/projects/{project_id}/rent").json()["items"][0]["id"]

    response = client.put(
        f"/api/projects/{project_id}/rent/{rent_id}",
        json={
            "property_type": "临街商铺",
            "floor": "一层",
            "location_remark": "临近地铁出口",
            "source_url": "https://example.com/rent/1",
            "publish_date": "2026-07-15",
            "rent_remark": "房东报价，尚未议价",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["manual_detail"]["property_type"] == "临街商铺"
    assert body["manual_detail"]["source_url"] == "https://example.com/rent/1"
    assert body["detail_completed"] is True

    detail = client.get(f"/api/projects/{project_id}/rent/{rent_id}")
    assert detail.status_code == 200
    assert detail.json()["manual_detail"]["rent_remark"] == "房东报价，尚未议价"

    with SessionLocal() as db:
        row = db.get(RentDataRecord, rent_id)
        assert row is not None
        assert row.raw_data["property_fee"] == 1800
        assert row.raw_data["manual_detail"]["property_type"] == "临街商铺"


def test_rent_detail_and_review_are_isolated_by_project(client):
    owner_project_id = create_project(client)
    other_project_id = create_project(client)
    upload_rent_csv(client, owner_project_id, "地址,面积,月租金\n隔离测试商铺,200,12000\n")
    rent_id = client.get(f"/api/projects/{owner_project_id}/rent").json()["items"][0]["id"]

    detail = client.get(f"/api/projects/{other_project_id}/rent/{rent_id}")
    update = client.put(
        f"/api/projects/{other_project_id}/rent/{rent_id}",
        json={"property_type": "不应保存"},
    )
    review = client.post(
        f"/api/projects/{other_project_id}/rent/{rent_id}/review",
        json={"status": "confirmed"},
    )

    assert detail.status_code == 404
    assert update.status_code == 404
    assert review.status_code == 404
    owner_item = client.get(f"/api/projects/{owner_project_id}/rent/{rent_id}").json()
    assert owner_item["status"] == "pending_review"
    assert owner_item["manual_detail"] == {
        "property_type": None,
        "floor": None,
        "location_remark": None,
        "source_url": None,
        "publish_date": None,
        "rent_remark": None,
    }


def test_rent_quality_only_checks_confirmed_records(client):
    project_id = create_project(client)
    import_rent_record(
        client,
        project_id,
        {"location_type": "已确认商铺", "area_sqm": 500, "monthly_rent": 30000, "status": "confirmed"},
    )
    import_rent_record(
        client,
        project_id,
        {"location_type": "待确认商铺", "status": "pending_review"},
    )
    import_rent_record(
        client,
        project_id,
        {"location_type": "已排除商铺", "status": "rejected"},
    )

    quality = client.get(f"/api/projects/{project_id}/data-quality")

    assert quality.status_code == 200
    rent_quality = quality.json()["rent_quality"]
    assert rent_quality["total_confirmed"] == 1
    assert len(rent_quality["incomplete_items"]) == 1
    assert rent_quality["incomplete_items"][0]["address"] == "已确认商铺"


def test_rent_quality_excludes_pending_and_rejected_when_no_confirmed_data(client):
    project_id = create_project(client)
    import_rent_record(client, project_id, {"location_type": "待确认商铺", "status": "pending_review"})
    import_rent_record(client, project_id, {"location_type": "已排除商铺", "status": "rejected"})

    body = client.get(f"/api/projects/{project_id}/data-quality").json()

    assert body["rent_quality"] == {
        "total_confirmed": 0,
        "detail_completed": 0,
        "incomplete": 0,
        "missing_summary": [],
        "incomplete_items": [],
    }
    assert "真实租金" in body["missing"]


def test_rent_quality_reports_missing_core_fields(client):
    project_id = create_project(client)
    row = import_rent_record(
        client,
        project_id,
        {"location_type": "缺少面积商铺", "monthly_rent": 20000, "status": "confirmed"},
    )

    body = client.get(f"/api/projects/{project_id}/data-quality").json()
    rent_quality = body["rent_quality"]

    area_missing = next(item for item in rent_quality["missing_summary"] if item["field"] == "area_sqm")
    assert area_missing == {"field": "area_sqm", "label": "面积", "missing_count": 1, "importance": "core"}
    assert rent_quality["incomplete_items"][0]["rent_id"] == row["id"]
    assert "面积" in rent_quality["incomplete_items"][0]["missing_fields"]
    assert "租金核心字段" in body["missing"]


def test_rent_quality_detail_missing_disappears_after_supplement(client):
    project_id = create_project(client)
    row = import_rent_record(
        client,
        project_id,
        {"location_type": "详情测试商铺", "area_sqm": 400, "monthly_rent": 24000, "status": "confirmed"},
    )
    before = client.get(f"/api/projects/{project_id}/data-quality").json()["rent_quality"]
    assert before["incomplete"] == 1
    assert {item["field"] for item in before["missing_summary"]} >= {
        "property_type",
        "source_url",
        "publish_date",
        "floor",
    }

    update = client.put(
        f"/api/projects/{project_id}/rent/{row['id']}",
        json={
            "property_type": "临街商铺",
            "source_url": "https://example.com/rent/quality",
            "publish_date": "2026-07-15",
            "floor": "一层",
        },
    )
    assert update.status_code == 200

    after = client.get(f"/api/projects/{project_id}/data-quality").json()["rent_quality"]
    assert after["detail_completed"] == 1
    assert after["incomplete"] == 0
    assert after["missing_summary"] == []


def test_rent_quality_core_penalty_is_applied_without_changing_cost_score(client):
    project_id = create_project(client)
    import_rent_record(
        client,
        project_id,
        {"location_type": "完整租金商铺", "area_sqm": 500, "monthly_rent": 30000, "status": "confirmed"},
    )
    before = client.get(f"/api/projects/{project_id}/data-quality").json()["quality_score"]

    import_rent_record(
        client,
        project_id,
        {"location_type": "缺少面积商铺", "monthly_rent": 20000, "status": "confirmed"},
    )
    after = client.get(f"/api/projects/{project_id}/data-quality").json()["quality_score"]

    assert after == before - 1
