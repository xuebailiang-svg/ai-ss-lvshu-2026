import os
from functools import lru_cache
from pydantic import BaseModel


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    app_env: str
    database_url: str
    amap_web_service_key: str
    amap_mock: bool
    amap_poi_page_size: int
    amap_poi_max_pages_per_keyword: int
    amap_poi_max_records_per_category: int
    amap_poi_rate_limit_seconds: float
    scoring_config_path: str
    enable_debug_endpoints: bool
    enable_trace: bool
    enable_reflection: bool
    enable_feedback: bool
    enable_similar_cases: bool
    enable_debug_api: bool
    frontend_runtime_config_path: str
    site_feedback_store_path: str
    agent_trace_store_path: str
    app_version: str
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    system_config_encryption_key: str
    admin_config_token: str
    crawler_enabled: bool
    crawler_provider: str
    crawler_timeout_seconds: int
    crawler_max_pages_per_task: int
    crawler_max_tasks_per_project: int
    crawler_rate_limit_seconds: int
    crawler_allowed_domains: str
    crawler_blocked_domains: str
    crawler_search_enabled: bool
    crawler_search_provider: str
    crawler_search_max_results: int
    crawler_search_timeout_seconds: int
    crawler_search_allowed_domains: str
    gov_data_enabled: bool
    gov_data_sources: str
    gov_data_timeout_seconds: int
    gov_data_max_retries: int
    gov_data_rate_limit_seconds: int
    gov_data_user_agent: str

@lru_cache
def get_settings() -> Settings:
    enable_debug_api = env_bool("ENABLE_DEBUG_API", False)
    return Settings(
        app_env=os.getenv("APP_ENV","production"),
        database_url=os.getenv("DATABASE_URL","sqlite:///./site_selection.db"),
        amap_web_service_key=os.getenv("AMAP_WEB_SERVICE_KEY",""),
        amap_mock=env_bool("AMAP_MOCK", False),
        amap_poi_page_size=max(1, min(25, int(os.getenv("AMAP_POI_PAGE_SIZE", "20")))),
        amap_poi_max_pages_per_keyword=max(1, int(os.getenv("AMAP_POI_MAX_PAGES_PER_KEYWORD", "3"))),
        amap_poi_max_records_per_category=max(1, int(os.getenv("AMAP_POI_MAX_RECORDS_PER_CATEGORY", "100"))),
        amap_poi_rate_limit_seconds=max(0, float(os.getenv("AMAP_POI_RATE_LIMIT_SECONDS", "0.3"))),
        scoring_config_path=os.getenv("SCORING_CONFIG_PATH","app/scoring/default.yaml"),
        enable_debug_endpoints=env_bool("ENABLE_DEBUG_ENDPOINTS", False) or enable_debug_api,
        enable_trace=env_bool("ENABLE_TRACE", True),
        enable_reflection=env_bool("ENABLE_REFLECTION", True),
        enable_feedback=env_bool("ENABLE_FEEDBACK", True),
        enable_similar_cases=env_bool("ENABLE_SIMILAR_CASES", True),
        enable_debug_api=enable_debug_api,
        frontend_runtime_config_path=os.getenv("FRONTEND_RUNTIME_CONFIG_PATH","/etc/esports-site-selection/frontend-runtime.json"),
        site_feedback_store_path=os.getenv("SITE_FEEDBACK_STORE_PATH", "data/site_feedback.json"),
        agent_trace_store_path=os.getenv("AGENT_TRACE_STORE_PATH", "data/agent_traces.json"),
        app_version=os.getenv("APP_VERSION", "v1.0.0-beta"),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        system_config_encryption_key=os.getenv("SYSTEM_CONFIG_ENCRYPTION_KEY", ""),
        admin_config_token=os.getenv("ADMIN_CONFIG_TOKEN", ""),
        crawler_enabled=env_bool("CRAWLER_ENABLED", False),
        crawler_provider=os.getenv("CRAWLER_PROVIDER", "crawl4ai"),
        crawler_timeout_seconds=int(os.getenv("CRAWLER_TIMEOUT_SECONDS", "60")),
        crawler_max_pages_per_task=int(os.getenv("CRAWLER_MAX_PAGES_PER_TASK", "5")),
        crawler_max_tasks_per_project=int(os.getenv("CRAWLER_MAX_TASKS_PER_PROJECT", "50")),
        crawler_rate_limit_seconds=int(os.getenv("CRAWLER_RATE_LIMIT_SECONDS", "5")),
        crawler_allowed_domains=os.getenv("CRAWLER_ALLOWED_DOMAINS", ""),
        crawler_blocked_domains=os.getenv("CRAWLER_BLOCKED_DOMAINS", ""),
        crawler_search_enabled=env_bool("CRAWLER_SEARCH_ENABLED", True),
        crawler_search_provider=os.getenv("CRAWLER_SEARCH_PROVIDER", "bing_html"),
        crawler_search_max_results=int(os.getenv("CRAWLER_SEARCH_MAX_RESULTS", "5")),
        crawler_search_timeout_seconds=int(os.getenv("CRAWLER_SEARCH_TIMEOUT_SECONDS", "10")),
        crawler_search_allowed_domains=os.getenv("CRAWLER_SEARCH_ALLOWED_DOMAINS", ""),
        gov_data_enabled=env_bool("GOV_DATA_ENABLED", True),
        gov_data_sources=os.getenv("GOV_DATA_SOURCES", "national,shaanxi,xian"),
        gov_data_timeout_seconds=int(os.getenv("GOV_DATA_TIMEOUT_SECONDS", "15")),
        gov_data_max_retries=int(os.getenv("GOV_DATA_MAX_RETRIES", "2")),
        gov_data_rate_limit_seconds=int(os.getenv("GOV_DATA_RATE_LIMIT_SECONDS", "1")),
        gov_data_user_agent=os.getenv(
            "GOV_DATA_USER_AGENT",
            "esports-site-selection/1.0 (+government-public-data)",
        ),
    )
