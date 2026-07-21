"""memory and scoring config

Revision ID: 0011_memory_and_scoring_config
Revises: 0010_system_configs
Create Date: 2026-07-21
"""

from alembic import op
import sqlalchemy as sa
from app.core.database import Base
import app.models  # noqa: F401
from migrations.helpers import table_exists


revision = "0011_memory_and_scoring_config"
down_revision = "0010_system_configs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if (
        table_exists("memory_items")
        and table_exists("scoring_dimensions")
        and table_exists("scoring_factors")
    ):
        return
    if table_exists("memory_items") or table_exists("scoring_dimensions") or table_exists("scoring_factors"):
        Base.metadata.create_all(op.get_bind())
        return

    op.create_table(
        "memory_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope", sa.String(length=30), nullable=False),
        sa.Column("memory_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False, server_default="manual"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending_review"),
        sa.Column("project_id", sa.String(length=80), nullable=True),
        sa.Column("user_id", sa.String(length=80), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_memory_items_scope", "memory_items", ["scope"])
    op.create_index("ix_memory_items_memory_type", "memory_items", ["memory_type"])
    op.create_index("ix_memory_items_status", "memory_items", ["status"])
    op.create_index("ix_memory_items_project_id", "memory_items", ["project_id"])
    op.create_index("ix_memory_items_user_id", "memory_items", ["user_id"])

    op.create_table(
        "scoring_dimensions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("data_sources", sa.JSON(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_scoring_dimensions_key", "scoring_dimensions", ["key"], unique=True)

    op.create_table(
        "scoring_factors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dimension_key", sa.String(length=80), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("data_sources", sa.JSON(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_scoring_factors_dimension_key", "scoring_factors", ["dimension_key"])
    op.create_index("ix_scoring_factors_key", "scoring_factors", ["key"])


def downgrade() -> None:
    op.drop_index("ix_scoring_factors_key", table_name="scoring_factors")
    op.drop_index("ix_scoring_factors_dimension_key", table_name="scoring_factors")
    op.drop_table("scoring_factors")
    op.drop_index("ix_scoring_dimensions_key", table_name="scoring_dimensions")
    op.drop_table("scoring_dimensions")
    op.drop_index("ix_memory_items_user_id", table_name="memory_items")
    op.drop_index("ix_memory_items_project_id", table_name="memory_items")
    op.drop_index("ix_memory_items_status", table_name="memory_items")
    op.drop_index("ix_memory_items_memory_type", table_name="memory_items")
    op.drop_index("ix_memory_items_scope", table_name="memory_items")
    op.drop_table("memory_items")
