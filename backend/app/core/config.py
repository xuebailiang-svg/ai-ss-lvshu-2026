import os
from functools import lru_cache
from pydantic import BaseModel

class Settings(BaseModel):
    app_env: str
    database_url: str
    amap_web_service_key: str
    amap_mock: bool
    scoring_config_path: str
    enable_debug_endpoints: bool
    frontend_runtime_config_path: str

@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_env=os.getenv("APP_ENV","production"),
        database_url=os.getenv("DATABASE_URL","sqlite:///./site_selection.db"),
        amap_web_service_key=os.getenv("AMAP_WEB_SERVICE_KEY",""),
        amap_mock=os.getenv("AMAP_MOCK","false").lower() in {"1","true","yes"},
        scoring_config_path=os.getenv("SCORING_CONFIG_PATH","app/scoring/default.yaml"),
        enable_debug_endpoints=os.getenv("ENABLE_DEBUG_ENDPOINTS","false").lower() in {"1","true","yes"},
        frontend_runtime_config_path=os.getenv("FRONTEND_RUNTIME_CONFIG_PATH","/etc/esports-site-selection/frontend-runtime.json"),
    )
