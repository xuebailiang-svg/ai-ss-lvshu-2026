def payload(**prop): return {"name":"北京测试点","city":"北京","address":"东长安街1号","radius":3000,"property":{"area_sqm":800,"monthly_rent":80000,"floor":"1F","street_facing":True,"night_entrance":True,"use_allowed":True,"power_sufficient":True,"fire_confirmed":True,**prop}}
def test_health(client): assert client.get("/api/health").json()["status"]=="ok"
def test_create_query_and_workflow(client):
    r=client.post("/api/evaluations",json=payload()); assert r.status_code==201; id=r.json()["id"]
    assert client.get(f"/api/evaluations/{id}").status_code==200
    assert client.post(f"/api/evaluations/{id}/geocode").json()["coordinate_system"]=="GCJ02"
    collected = client.post(f"/api/evaluations/{id}/collect-pois").json()
    assert collected["count"] >= 5
    assert collected["diagnostics"]["saved_by_category"]["竞品"] >= 1
    score=client.post(f"/api/evaluations/{id}/score").json(); assert score["hard_risks"]; assert score["recommendation"].startswith("高风险")
    assert client.get(f"/api/evaluations/{id}/report").status_code==200

def test_collect_pois_multiple_categories_and_diagnostics(client):
    id=client.post("/api/evaluations",json=payload()).json()["id"]
    client.post(f"/api/evaluations/{id}/geocode")
    collected=client.post(f"/api/evaluations/{id}/collect-pois").json()
    assert collected["diagnostics"]["raw_return_count"] >= 5
    diag=client.get(f"/api/evaluations/{id}/poi-diagnostics").json()
    assert diag["poi_total"] >= 5
    assert diag["by_category"]["竞品"] >= 1
    assert diag["by_category"]["交通"] >= 1
    assert diag["by_category"]["商业配套"] >= 1
    assert diag["by_category"]["中学"] >= 1
    assert diag["by_category"]["住宅小区"] >= 1
    report=client.post(f"/api/evaluations/{id}/score") and client.get(f"/api/evaluations/{id}/report").json()
    sections=report["sections"]
    assert sections["traffic"]["auto_collected_count"] >= 1
    assert sections["commercial"]["auto_collected_count"] >= 1
    assert sections["sensitive_places"]["auto_collected_count"] >= 1
    assert sections["population_proxy"]["auto_collected_count"] >= 1
def test_property_hard_risk_cannot_be_hidden(client):
    id=client.post("/api/evaluations",json=payload(use_allowed=False)).json()["id"]
    result=client.post(f"/api/evaluations/{id}/score").json(); assert result["hard_risks"]; assert "高风险" in result["recommendation"]
def test_missing_data_lowers_confidence(client):
    sparse={"name":"空数据","city":"北京","address":"测试路","property":{}}
    result=client.post(f"/api/evaluations/{client.post('/api/evaluations',json=sparse).json()['id']}/score").json(); assert result["confidence"]<50; assert result["completeness"]<50
