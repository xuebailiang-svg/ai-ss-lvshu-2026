def create_project(client):
    response = client.post("/api/projects", json={
        "name": "CSV导入测试项目",
        "city": "西安市",
        "address": "小寨地铁站",
        "radius_meters": 1000,
        "business_type": "电竞馆",
    })
    assert response.status_code == 200
    return response.json()["project_id"]


def upload_csv(client, project_id, data_type, text):
    return client.post(
        f"/api/projects/{project_id}/data/upload",
        data={"data_type": data_type},
        files={"file": ("data.csv", text.encode("utf-8-sig"), "text/csv")},
    )


def test_normal_csv_import(client):
    project_id = create_project(client)
    response = upload_csv(
        client,
        project_id,
        "competitor",
        "名称,地址,距离,面积,机器数量,价格,上座率\n甲电竞馆,小寨,300,600,120,15,80%\n乙网咖,长安路,500,400,80,12,60",
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "success": True,
        "total_rows": 2,
        "imported_rows": 2,
        "failed_rows": 0,
        "duplicate_rows": 0,
        "errors": [],
        "duplicates": [],
    }
    dataset = client.get(f"/api/projects/{project_id}/dataset").json()
    assert len(dataset["competitors"]) == 2
    assert dataset["competitors"][0]["source"] == "manual"
    assert dataset["competitors"][0]["occupancy_rate"] == 0.8
    stats = client.get(f"/api/projects/{project_id}").json()["stats"]
    assert stats["competitor_count"] == 2


def test_missing_required_header(client):
    project_id = create_project(client)
    response = upload_csv(client, project_id, "food", "名称,营业时间\n某餐厅,00:00-24:00")

    assert response.status_code == 400
    assert "缺少必填字段" in response.json()["detail"]
    assert "距离" in response.json()["detail"]


def test_partial_invalid_rows_do_not_block_valid_rows(client):
    project_id = create_project(client)
    response = upload_csv(
        client,
        project_id,
        "rent",
        "地址,面积,月租金,物业费\n物业A,500,30000,2000\n物业B,错误,40000,2500\n物业C,600,50000,3000",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_rows"] == 3
    assert body["imported_rows"] == 2
    assert body["failed_rows"] == 1
    assert body["errors"][0]["row"] == 3
    assert "面积格式错误" in body["errors"][0]["reason"]


def test_empty_csv_is_rejected(client):
    project_id = create_project(client)
    response = upload_csv(client, project_id, "competitor", "")

    assert response.status_code == 400
    assert response.json()["detail"] == "CSV文件为空"


def test_duplicate_competitor_and_rent_rows_are_skipped(client):
    project_id = create_project(client)
    competitor_csv = "名称,地址,距离\n甲电竞馆,小寨,300"
    rent_csv = "地址,面积,月租金\n物业A,500,30000"

    assert upload_csv(client, project_id, "competitor", competitor_csv).json()["imported_rows"] == 1
    assert upload_csv(client, project_id, "rent", rent_csv).json()["imported_rows"] == 1
    duplicate_competitor = upload_csv(client, project_id, "competitor", competitor_csv).json()
    duplicate_rent = upload_csv(client, project_id, "rent", rent_csv).json()

    assert duplicate_competitor["imported_rows"] == 0
    assert duplicate_competitor["duplicate_rows"] == 1
    assert duplicate_competitor["duplicates"][0]["row"] == 2
    assert duplicate_rent["imported_rows"] == 0
    assert duplicate_rent["duplicate_rows"] == 1
    stats = client.get(f"/api/projects/{project_id}").json()["stats"]
    assert stats["competitor_count"] == 1
    assert stats["rent_count"] == 1
