"""government statistics and data sync runs

Revision ID: 0013_government_statistics
Revises: 0012_crawl_tasks
Create Date: 2026-07-28
"""

from alembic import op
import sqlalchemy as sa

from migrations.helpers import table_exists


revision = "0013_government_statistics"
down_revision = "0012_crawl_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not table_exists("regional_statistics"):
        op.create_table(
            "regional_statistics",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("metric_code", sa.String(length=80), nullable=False),
            sa.Column("metric_name", sa.String(length=160), nullable=False),
            sa.Column("value_numeric", sa.Float(), nullable=True),
            sa.Column("value_text", sa.Text(), nullable=True),
            sa.Column("unit", sa.String(length=40), nullable=True),
            sa.Column("scope_level", sa.String(length=30), nullable=False),
            sa.Column("scope_code", sa.String(length=40), nullable=False),
            sa.Column("scope_name", sa.String(length=120), nullable=False),
            sa.Column("stat_period", sa.String(length=30), nullable=False),
            sa.Column("source_name", sa.String(length=160), nullable=False),
            sa.Column("source_url", sa.Text(), nullable=False),
            sa.Column("source_format", sa.String(length=30), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="pending_review"),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0.8"),
            sa.Column("raw_data", sa.JSON(), nullable=True),
            sa.UniqueConstraint(
                "metric_code",
                "scope_code",
                "stat_period",
                "source_name",
                name="uq_regional_statistics_metric_scope_period_source",
            ),
        )
        op.create_index("ix_regional_statistics_metric_code", "regional_statistics", ["metric_code"])
        op.create_index("ix_regional_statistics_scope_level", "regional_statistics", ["scope_level"])
        op.create_index("ix_regional_statistics_scope_code", "regional_statistics", ["scope_code"])
        op.create_index("ix_regional_statistics_scope_name", "regional_statistics", ["scope_name"])
        op.create_index("ix_regional_statistics_stat_period", "regional_statistics", ["stat_period"])
        op.create_index("ix_regional_statistics_status", "regional_statistics", ["status"])

    if not table_exists("data_sync_runs"):
        op.create_table(
            "data_sync_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("provider", sa.String(length=80), nullable=False),
            sa.Column("project_id", sa.String(length=80), nullable=True),
            sa.Column("scope_code", sa.String(length=40), nullable=True),
            sa.Column("scope_name", sa.String(length=120), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
            sa.Column("imported_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("pending_review_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("input_snapshot", sa.JSON(), nullable=True),
            sa.Column("result_snapshot", sa.JSON(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_data_sync_runs_provider", "data_sync_runs", ["provider"])
        op.create_index("ix_data_sync_runs_project_id", "data_sync_runs", ["project_id"])
        op.create_index("ix_data_sync_runs_scope_code", "data_sync_runs", ["scope_code"])
        op.create_index("ix_data_sync_runs_status", "data_sync_runs", ["status"])


def downgrade() -> None:
    if table_exists("data_sync_runs"):
        op.drop_index("ix_data_sync_runs_status", table_name="data_sync_runs")
        op.drop_index("ix_data_sync_runs_scope_code", table_name="data_sync_runs")
        op.drop_index("ix_data_sync_runs_project_id", table_name="data_sync_runs")
        op.drop_index("ix_data_sync_runs_provider", table_name="data_sync_runs")
        op.drop_table("data_sync_runs")
    if table_exists("regional_statistics"):
        op.drop_index("ix_regional_statistics_status", table_name="regional_statistics")
        op.drop_index("ix_regional_statistics_stat_period", table_name="regional_statistics")
        op.drop_index("ix_regional_statistics_scope_name", table_name="regional_statistics")
        op.drop_index("ix_regional_statistics_scope_code", table_name="regional_statistics")
        op.drop_index("ix_regional_statistics_scope_level", table_name="regional_statistics")
        op.drop_index("ix_regional_statistics_metric_code", table_name="regional_statistics")
        op.drop_table("regional_statistics")
