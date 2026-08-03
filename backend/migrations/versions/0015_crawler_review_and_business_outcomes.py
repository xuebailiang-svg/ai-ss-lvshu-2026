"""crawler field review and business outcomes

Revision ID: 0015_crawler_review_outcomes
Revises: 0014_backfill_amap_business_hours
Create Date: 2026-08-02
"""

from alembic import op
import sqlalchemy as sa

from migrations.helpers import table_exists


revision = "0015_crawler_review_outcomes"
down_revision = "0014_backfill_amap_business_hours"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not table_exists("crawler_field_suggestions"):
        op.create_table(
            "crawler_field_suggestions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.String(80), nullable=False),
            sa.Column("task_id", sa.Integer(), nullable=False),
            sa.Column("record_type", sa.String(40), nullable=False),
            sa.Column("record_id", sa.Integer(), nullable=True),
            sa.Column("field_name", sa.String(80), nullable=False),
            sa.Column("suggested_value", sa.JSON(), nullable=True),
            sa.Column("reviewed_value", sa.JSON(), nullable=True),
            sa.Column("source_url", sa.Text(), nullable=False),
            sa.Column("source_domain", sa.String(200), nullable=True),
            sa.Column("evidence_excerpt", sa.Text(), nullable=True),
            sa.Column("extraction_method", sa.String(40), nullable=False, server_default="rule_extract"),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0.6"),
            sa.Column("source_quality", sa.String(30), nullable=False, server_default="medium"),
            sa.Column("freshness_status", sa.String(30), nullable=False, server_default="unknown"),
            sa.Column("conflict_status", sa.String(30), nullable=False, server_default="none"),
            sa.Column("status", sa.String(30), nullable=False, server_default="pending_review"),
            sa.Column("review_remark", sa.Text(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("task_id", "record_type", "record_id", "field_name", "source_url", name="uq_crawler_suggestion_task_record_field_source"),
        )
        for column in ("project_id", "task_id", "record_type", "record_id", "field_name", "source_domain", "status"):
            op.create_index(f"ix_crawler_field_suggestions_{column}", "crawler_field_suggestions", [column])

    if not table_exists("business_outcomes"):
        op.create_table(
            "business_outcomes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.String(80), nullable=False),
            sa.Column("actual_monthly_rent", sa.Float(), nullable=True),
            sa.Column("actual_area_sqm", sa.Float(), nullable=True),
            sa.Column("actual_machine_count", sa.Integer(), nullable=True),
            sa.Column("opening_date", sa.Date(), nullable=True),
            sa.Column("actual_investment", sa.Float(), nullable=True),
            sa.Column("occupancy_rate", sa.Float(), nullable=True),
            sa.Column("result_status", sa.String(50), nullable=True),
            sa.Column("success_reasons", sa.JSON(), nullable=False),
            sa.Column("failure_reasons", sa.JSON(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("status", sa.String(30), nullable=False, server_default="pending_review"),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("project_id", name="uq_business_outcomes_project_id"),
        )
        op.create_index("ix_business_outcomes_project_id", "business_outcomes", ["project_id"], unique=True)
        op.create_index("ix_business_outcomes_status", "business_outcomes", ["status"])


def downgrade() -> None:
    if table_exists("business_outcomes"):
        op.drop_table("business_outcomes")
    if table_exists("crawler_field_suggestions"):
        op.drop_table("crawler_field_suggestions")
