def payload(**prop):
    return {
        "name": "西安测试点",
        "city": "西安市",
        "address": "雁塔区小寨西路",
        "radius": 3000,
        "property": {
            "area_sqm": 600,
            "monthly_rent": 60000,
            "street_facing": True,
            "night_entrance": True,
            "use_allowed": True,
            "power_sufficient": True,
            "fire_confirmed": True,
            **prop,
        },
    }


def prepared_evaluation(client):
    evaluation_id = client.post("/api/evaluations", json=payload()).json()["id"]
    client.post(f"/api/evaluations/{evaluation_id}/geocode")
    client.post(f"/api/evaluations/{evaluation_id}/collect-pois")
    return evaluation_id


def test_public_poi_list_hides_internal_fields(client):
    evaluation_id = prepared_evaluation(client)
    data = client.get(f"/api/evaluations/{evaluation_id}/pois").json()
    assert data["total"] >= 5
    row = data["items"][0]
    assert {"poi_id", "name", "business_category", "subcategory", "missing_items_text"} <= set(row)
    assert "longitude" not in row
    assert "latitude" not in row
    assert "typecode" not in row
    assert "type_code" not in row
    assert "provider_poi_id" not in row
    assert "raw_data" not in row
    assert "confidence" not in row


def test_manual_poi_persists_after_amap_recollect(client):
    evaluation_id = prepared_evaluation(client)
    created = client.post(
        f"/api/evaluations/{evaluation_id}/pois",
        json={
            "name": "现场发现电竞酒店",
            "business_category": "竞品",
            "subcategory": "电竞酒店",
            "address": "现场补充地址",
            "machine_count": 80,
            "data_source": "人工",
            "verification_status": "已人工核实",
        },
    ).json()
    assert created["is_manual"] is True

    client.post(f"/api/evaluations/{evaluation_id}/collect-pois")
    rows = client.get(f"/api/evaluations/{evaluation_id}/pois").json()["items"]
    assert any(row["name"] == "现场发现电竞酒店" for row in rows)


def test_category_csv_export_and_import(client):
    evaluation_id = prepared_evaluation(client)
    rows = client.get(f"/api/evaluations/{evaluation_id}/pois").json()["items"]
    competitor = next(row for row in rows if row["business_category"] == "竞品")

    exported = client.get(f"/api/evaluations/{evaluation_id}/pois/export?category=competitor")
    assert exported.status_code == 200
    text = exported.text.lstrip("\ufeff")
    header = text.splitlines()[0]
    assert "poi_id" in header
    assert "名称" in header
    assert "typecode" not in header.lower()
    assert "type_code" not in header.lower()
    assert "longitude" not in header.lower()
    assert "latitude" not in header.lower()
    assert "confidence" not in header.lower()
    assert "raw_data" not in header.lower()

    csv_text = (
        "poi_id,名称,业务类别,细分类,地址,直线距离,步行距离,步行时间,数据来源,核实状态,待补充项,备注,机器数量,CPU,显卡,普通区价格\n"
        f"{competitor['poi_id']},{competitor['name']},竞品,网咖,{competitor.get('address') or ''},{competitor.get('distance_m') or ''},500,7,现场调研,已人工核实,,已电话核实,120,i7,RTX 4070,8\n"
    )
    imported = client.post(f"/api/evaluations/{evaluation_id}/pois/import", json={"category": "competitor", "csv_text": csv_text}).json()
    assert imported["success_count"] == 1
    assert imported["failed_count"] == 0

    updated = client.get(f"/api/evaluations/{evaluation_id}/pois").json()["items"]
    row = next(item for item in updated if item["poi_id"] == competitor["poi_id"])
    assert row["verification_status"] == "已人工核实"
    assert row["walking_distance_m"] == 500
    assert row["supplement"]["machine_count"] == "120"
    assert row["supplement"]["gpu"] == "RTX 4070"


def test_csv_import_rejects_poi_outside_current_evaluation(client):
    source_id = prepared_evaluation(client)
    target_id = prepared_evaluation(client)
    source_poi = client.get(f"/api/evaluations/{source_id}/pois").json()["items"][0]
    csv_text = (
        "poi_id,名称,业务类别,细分类,地址,数据来源,核实状态\n"
        f"{source_poi['poi_id']},{source_poi['name']},竞品,网咖,,现场调研,已人工核实\n"
    )
    result = client.post(f"/api/evaluations/{target_id}/pois/import", json={"category": "competitor", "csv_text": csv_text}).json()
    assert result["success_count"] == 0
    assert result["failed_count"] == 1
    assert "不属于当前评估" in result["errors"][0]["reason"]
