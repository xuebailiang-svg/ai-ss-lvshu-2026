"""crawl tasks

Revision ID: 0012_crawl_tasks
Revises: 0011_memory_and_scoring_config
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa
from migrations.helpers import table_exists


revision = "0012_crawl_tasks"
down_revision = "0011_memory_and_scoring_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if table_exists("crawl_tasks"):
        return
    op.create_table(
        "crawl_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("task_type", sa.String(length=40), nullable=False),
        sa.Column("target_name", sa.String(length=200), nullable=True),
        sa.Column("target_address", sa.String(length=300), nullable=True),
        sa.Column("target_url", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=False, server_default="crawl4ai"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("source_domain", sa.String(length=200), nullable=True),
        sa.Column("input_snapshot", sa.JSON(), nullable=True),
        sa.Column("result_snapshot", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_crawl_tasks_project_id", "crawl_tasks", ["project_id"])
    op.create_index("ix_crawl_tasks_task_type", "crawl_tasks", ["task_type"])
    op.create_index("ix_crawl_tasks_status", "crawl_tasks", ["status"])
    op.create_index("ix_crawl_tasks_source_domain", "crawl_tasks", ["source_domain"])


def downgrade() -> None:
    op.drop_index("ix_crawl_tasks_source_domain", table_name="crawl_tasks")
    op.drop_index("ix_crawl_tasks_status", table_name="crawl_tasks")
    op.drop_index("ix_crawl_tasks_task_type", table_name="crawl_tasks")
    op.drop_index("ix_crawl_tasks_project_id", table_name="crawl_tasks")
    op.drop_table("crawl_tasks")
