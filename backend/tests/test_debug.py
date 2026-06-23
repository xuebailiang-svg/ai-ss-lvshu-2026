def test_debug_amap_geocode_disabled_by_default(client):
    response = client.post(
        "/api/debug/amap/geocode",
        json={"city": "Beijing", "address": "test"},
    )
    assert response.status_code == 404
