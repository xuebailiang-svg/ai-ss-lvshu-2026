from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.core.database import Base
import app.models  # noqa: F401 - register metadata


BACKEND_DIR = Path(__file__).resolve().parents[1]


def run_upgrade(database_path: Path) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def assert_head(database_path: Path) -> None:
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        assert connection.execute(text("select version_num from alembic_version")).scalar() == "0012_crawl_tasks"
    tables = set(inspect(engine).get_table_names())
    assert {"site_projects", "poi_enrichments", "site_scores", "ai_reports", "system_configs", "crawl_tasks"}.issubset(tables)
    engine.dispose()


def test_empty_database_upgrades_to_head(tmp_path: Path):
    database_path = tmp_path / "empty.db"

    run_upgrade(database_path)
    run_upgrade(database_path)

    assert_head(database_path)


def test_unversioned_existing_schema_upgrades_without_duplicate_objects(tmp_path: Path):
    database_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    engine.dispose()

    run_upgrade(database_path)

    assert_head(database_path)
