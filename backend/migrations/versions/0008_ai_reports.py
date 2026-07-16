"""ai reports

Revision ID: 0008_ai_reports
Revises: 0007_site_scores
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa
from app.core.database import Base
import app.models  # noqa: F401
from migrations.helpers import table_exists


revision = "0008_ai_reports"
down_revision = "0007_site_scores"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if table_exists("ai_reports") or table_exists("ai_call_logs"):
        Base.metadata.create_all(op.get_bind())
        return
    op.create_table(
        "ai_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("score_snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("report_content", sa.Text(), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_reports_project_id", "ai_reports", ["project_id"])

    op.create_table(
        "ai_call_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("input_length", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_length", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_call_logs_project_id", "ai_call_logs", ["project_id"])
    op.create_index("ix_ai_call_logs_report_id", "ai_call_logs", ["report_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_call_logs_report_id", table_name="ai_call_logs")
    op.drop_index("ix_ai_call_logs_project_id", table_name="ai_call_logs")
    op.drop_table("ai_call_logs")
    op.drop_index("ix_ai_reports_project_id", table_name="ai_reports")
    op.drop_table("ai_reports")
