from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.core.database import Base
from app.core.migration_compat import LEGACY_REVISION_ALIASES, normalize_legacy_alembic_versions
import app.models  # noqa: F401 - register metadata


BACKEND_DIR = Path(__file__).resolve().parents[1]


def migration_head() -> str:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1, f"expected a single Alembic head, got: {heads}"
    return heads[0]


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
        assert connection.execute(text("select version_num from alembic_version")).scalar() == migration_head()
    tables = set(inspect(engine).get_table_names())
    assert {
        "site_projects",
        "poi_enrichments",
        "site_scores",
        "ai_reports",
        "system_configs",
        "crawl_tasks",
        "regional_statistics",
        "data_sync_runs",
        "crawler_field_suggestions",
        "business_outcomes",
    }.issubset(tables)
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


def test_revision_identifiers_fit_default_alembic_version_column():
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    script = ScriptDirectory.from_config(config)

    revisions = list(script.walk_revisions())
    assert revisions
    assert all(len(item.revision) <= 32 for item in revisions), [
        item.revision for item in revisions if len(item.revision) > 32
    ]
    assert len({item.revision for item in revisions}) == len(revisions)


def test_legacy_long_revision_is_normalized_before_upgrade(tmp_path: Path):
    database_path = tmp_path / "legacy_revision.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0013_government_statistics"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    legacy_revision, canonical_revision = next(iter(LEGACY_REVISION_ALIASES.items()))
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE alembic_version SET version_num = :legacy"),
            {"legacy": legacy_revision},
        )
    engine.dispose()

    assert normalize_legacy_alembic_versions(database_url) == [
        (legacy_revision, canonical_revision)
    ]
    run_upgrade(database_path)
    assert_head(database_path)
