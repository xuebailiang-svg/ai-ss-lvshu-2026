def test_scoring_config_defaults(client):
    response = client.get("/api/scoring/config")
    assert response.status_code == 200
    data = response.json()
    names = [item["name"] for item in data["dimensions"]]
    assert "红线合规" in names
    assert "竞品经营" in names
    assert "数据质量" in names
    assert round(data["total_weight"], 2) == 100


def test_scoring_config_update_and_reset(client):
    data = client.get("/api/scoring/config").json()
    dimensions = data["dimensions"]
    dimensions[0]["weight"] = 12
    dimensions[1]["weight"] = 6

    updated = client.put("/api/scoring/config", json={"dimensions": dimensions})
    assert updated.status_code == 200
    updated_data = updated.json()
    assert updated_data["dimensions"][0]["weight"] == 12

    reset = client.post("/api/scoring/config/reset")
    assert reset.status_code == 200
    reset_data = reset.json()
    assert reset_data["dimensions"][0]["name"] == "红线合规"
    assert round(reset_data["total_weight"], 2) == 100
