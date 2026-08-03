"""backfill amap business_hours from raw_data.biz_ext.open_time

Revision ID: 0014_backfill_amap_business_hours
Revises: 0013_government_statistics
Create Date: 2026-07-31
"""

from alembic import op
import json
import sqlalchemy as sa

from migrations.helpers import column_exists, table_exists


revision = "0014_backfill_amap_business_hours"
down_revision = "0013_government_statistics"
branch_labels = None
depends_on = None

TARGET_TABLES = ("pois", "food_businesses", "entertainments")


def _normalize_hours(value) -> str | None:
    if isinstance(value, (list, tuple)):
        parts = [str(item).strip() for item in value if str(item).strip()]
        if not parts:
            return None
        return "、".join(parts)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _backfill_table(table_name: str) -> None:
    """把高德 raw_data.biz_ext.open_time 回填到 business_hours 列（幂等）。

    SQLite 的 JSON 列以文本存储、原生 SQL 读回是字符串，PostgreSQL 读回是 dict，
    因此统一先转成 dict 再处理。
    """
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(f"SELECT id, raw_data FROM {table_name} WHERE business_hours IS NULL")
    ).mappings().all()
    for row in rows:
        raw = row["raw_data"]
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (TypeError, ValueError):
                raw = None
        if not isinstance(raw, dict):
            continue
        biz_ext = raw.get("biz_ext")
        if not isinstance(biz_ext, dict):
            continue
        hours = _normalize_hours(biz_ext.get("open_time"))
        if not hours:
            continue
        bind.execute(
            sa.text(f"UPDATE {table_name} SET business_hours = :hours WHERE id = :id"),
            {"hours": hours, "id": row["id"]},
        )


def upgrade() -> None:
    for table_name in TARGET_TABLES:
        if table_exists(table_name) and column_exists(table_name, "business_hours"):
            _backfill_table(table_name)


def downgrade() -> None:
    # 数据回填不可逆，删除历史营业时间会破坏人工已核实数据，故不执行任何操作。
    pass
