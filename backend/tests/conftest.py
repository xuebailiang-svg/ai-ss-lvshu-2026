import os
from pathlib import Path
os.environ["DATABASE_URL"]="sqlite:///./test.db"; os.environ["APP_ENV"]="test"; os.environ["AMAP_MOCK"]="true"; os.environ["SITE_FEEDBACK_STORE_PATH"]="./test_feedback.json"; os.environ["AGENT_TRACE_STORE_PATH"]="./test_agent_traces.json"
import pytest
from fastapi.testclient import TestClient
from app.core.config import get_settings
from app.core.database import Base,engine
from app.main import app
@pytest.fixture(autouse=True)
def clean_db():
    get_settings.cache_clear()
    paths = [Path(os.environ["SITE_FEEDBACK_STORE_PATH"]), Path(os.environ["AGENT_TRACE_STORE_PATH"])]
    for path in paths:
        if path.exists():
            path.unlink()
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine); yield
    get_settings.cache_clear()
    for path in paths:
        if path.exists():
            path.unlink()
@pytest.fixture
def client():
    with TestClient(app) as c: yield c
