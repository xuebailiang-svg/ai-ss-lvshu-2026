from __future__ import annotations

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.llm.client import DeepSeekClient
from app.map_data.amap_client import AmapMapDataClient
from app.models import SystemConfigRecord


ADMIN_HEADERS = {"X-Admin-Token": "test-admin-token"}


def enable_management(monkeypatch) -> None:
    monkeypatch.setenv("SYSTEM_CONFIG_ENCRYPTION_KEY", "test-encryption-master-key-32-characters-long")
    monkeypatch.setenv("ADMIN_CONFIG_TOKEN", "test-admin-token")
    get_settings.cache_clear()


def test_config_save_is_encrypted_and_status_never_returns_plain_key(client, monkeypatch):
    enable_management(monkeypatch)
    deepseek_key = "sk-test-deepseek-secret-value"
    amap_key = "amap-test-secret-value"

    response = client.put(
        "/api/system/config",
        headers=ADMIN_HEADERS,
        json={"deepseek_api_key": deepseek_key, "amap_web_service_key": amap_key},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["deepseek"]["configured"] is True
    assert body["deepseek"]["source"] == "database"
    assert body["amap"]["configured"] is True
    assert deepseek_key not in response.text
    assert amap_key not in response.text
    with SessionLocal() as db:
        rows = db.query(SystemConfigRecord).all()
    assert len(rows) == 2
    assert all(deepseek_key not in row.encrypted_value for row in rows)
    assert all(amap_key not in row.encrypted_value for row in rows)


def test_database_config_has_priority_over_environment(client, monkeypatch):
    enable_management(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-deepseek-key")
    monkeypatch.setenv("AMAP_WEB_SERVICE_KEY", "env-amap-key")
    get_settings.cache_clear()
    response = client.put(
        "/api/system/config",
        headers=ADMIN_HEADERS,
        json={
            "deepseek_api_key": "database-deepseek-key",
            "amap_web_service_key": "database-amap-key",
            "deepseek_base_url": "https://api.deepseek.com",
            "deepseek_model": "deepseek-chat",
        },
    )
    assert response.status_code == 200

    assert DeepSeekClient().api_key == "database-deepseek-key"
    assert AmapMapDataClient(mock=False).key == "database-amap-key"


def test_environment_is_used_when_database_config_is_missing(client, monkeypatch):
    enable_management(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-only-deepseek-key")
    monkeypatch.setenv("AMAP_WEB_SERVICE_KEY", "env-only-amap-key")
    get_settings.cache_clear()

    status = client.get("/api/system/config")

    assert status.status_code == 200
    assert status.json()["deepseek"]["source"] == "env"
    assert status.json()["amap"]["source"] == "env"
    assert DeepSeekClient().api_key == "env-only-deepseek-key"
    assert AmapMapDataClient(mock=False).key == "env-only-amap-key"


def test_config_update_requires_admin_token(client, monkeypatch):
    enable_management(monkeypatch)

    response = client.put("/api/system/config", json={"deepseek_api_key": "should-not-save"})

    assert response.status_code == 401
    assert "管理员Token无效" in response.text


def test_connection_checks_use_runtime_clients_without_external_network(client, monkeypatch):
    enable_management(monkeypatch)

    def fake_deepseek_check(self):
        return None

    async def fake_amap_check(self, *, timeout_seconds=3.0):
        return {"status": "1", "info": "OK", "infocode": "10000"}

    monkeypatch.setattr("app.llm.client.DeepSeekClient.check_connectivity", fake_deepseek_check)
    monkeypatch.setattr("app.map_data.amap_client.AmapMapDataClient.check_connectivity", fake_amap_check)

    deepseek = client.post("/api/system/config/deepseek/test", headers=ADMIN_HEADERS)
    amap = client.post("/api/system/config/amap/test", headers=ADMIN_HEADERS)

    assert deepseek.status_code == 200
    assert deepseek.json()["success"] is True
    assert amap.status_code == 200
    assert amap.json()["success"] is True


def test_government_data_settings_are_saved_and_returned(client, monkeypatch):
    enable_management(monkeypatch)

    response = client.put(
        "/api/system/config",
        headers=ADMIN_HEADERS,
        json={
            "gov_data_enabled": "true",
            "gov_data_sources": "national,shaanxi,xian",
            "gov_data_timeout_seconds": "20",
            "gov_data_max_retries": "3",
            "gov_data_rate_limit_seconds": "2",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["gov_data_enabled"] is True
    assert body["gov_data_sources"] == "national,shaanxi,xian"
    assert body["gov_data_timeout_seconds"] == 20
    assert body["gov_data_max_retries"] == 3
    assert body["gov_data_rate_limit_seconds"] == 2
