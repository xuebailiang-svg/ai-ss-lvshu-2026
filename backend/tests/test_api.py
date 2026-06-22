def payload(**prop): return {"name":"北京测试点","city":"北京","address":"东长安街1号","radius":3000,"property":{"area_sqm":800,"monthly_rent":80000,"floor":"1F","street_facing":True,"night_entrance":True,"use_allowed":True,"power_sufficient":True,"fire_confirmed":True,**prop}}
def test_health(client): assert client.get("/api/health").json()["status"]=="ok"
def test_create_query_and_workflow(client):
    r=client.post("/api/evaluations",json=payload()); assert r.status_code==201; id=r.json()["id"]
    assert client.get(f"/api/evaluations/{id}").status_code==200
    assert client.post(f"/api/evaluations/{id}/geocode").json()["coordinate_system"]=="GCJ02"
    assert client.post(f"/api/evaluations/{id}/collect-pois").json()["count"]==1
    score=client.post(f"/api/evaluations/{id}/score").json(); assert score["hard_risks"]; assert score["recommendation"].startswith("高风险")
    assert client.get(f"/api/evaluations/{id}/report").status_code==200
def test_property_hard_risk_cannot_be_hidden(client):
    id=client.post("/api/evaluations",json=payload(use_allowed=False)).json()["id"]
    result=client.post(f"/api/evaluations/{id}/score").json(); assert result["hard_risks"]; assert "高风险" in result["recommendation"]
def test_missing_data_lowers_confidence(client):
    sparse={"name":"空数据","city":"北京","address":"测试路","property":{}}
    result=client.post(f"/api/evaluations/{client.post('/api/evaluations',json=sparse).json()['id']}/score").json(); assert result["confidence"]<50; assert result["completeness"]<50

