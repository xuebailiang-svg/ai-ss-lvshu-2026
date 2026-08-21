"""Compatibility helpers for historical Alembic revision identifiers.

This module runs immediately before ``alembic upgrade head``.  It only rewrites
known revision aliases in ``alembic_version``; it never stamps an unknown
database or changes application tables.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine, inspect, text


LEGACY_REVISION_ALIASES = {
    # The original identifier is 33 characters, while Alembic creates
    # alembic_version.version_num as VARCHAR(32) on PostgreSQL by default.
    "0014_backfill_amap_business_hours": "0014_amap_hours",
}


def normalize_legacy_alembic_versions(database_url: str | None = None) -> list[tuple[str, str]]:
    """Replace exact, known legacy revision IDs and return applied changes.

    Missing ``alembic_version`` means this is a fresh or unversioned database;
    Alembic's regular migration flow remains responsible for it.
    """

    url = database_url or os.getenv("DATABASE_URL", "sqlite:///./site_selection.db")
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
    )
    applied: list[tuple[str, str]] = []
    try:
        if "alembic_version" not in inspect(engine).get_table_names():
            return applied
        with engine.begin() as connection:
            current_versions = set(
                connection.execute(text("SELECT version_num FROM alembic_version")).scalars()
            )
            for legacy_revision, canonical_revision in LEGACY_REVISION_ALIASES.items():
                if legacy_revision not in current_versions:
                    continue
                connection.execute(
                    text(
                        "UPDATE alembic_version "
                        "SET version_num = :canonical "
                        "WHERE version_num = :legacy"
                    ),
                    {"canonical": canonical_revision, "legacy": legacy_revision},
                )
                applied.append((legacy_revision, canonical_revision))
        return applied
    finally:
        engine.dispose()


def main() -> None:
    applied = normalize_legacy_alembic_versions()
    if applied:
        for legacy_revision, canonical_revision in applied:
            print(f"Normalized Alembic revision: {legacy_revision} -> {canonical_revision}")
    else:
        print("Alembic revision compatibility check: no legacy revision found")


if __name__ == "__main__":
    main()
