"""site score history

Revision ID: 0007_site_scores
Revises: 0006_manual_inputs
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa
from migrations.helpers import table_exists


revision = "0007_site_scores"
down_revision = "0006_manual_inputs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if table_exists("site_scores"):
        return
    op.create_table(
        "site_scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("total_score", sa.Float(), nullable=False),
        sa.Column("level", sa.String(length=50), nullable=False),
        sa.Column("dimension_scores", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("advantage_items", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("risk_items", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("missing_data", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_site_scores_project_id", "site_scores", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_site_scores_project_id", table_name="site_scores")
    op.drop_table("site_scores")
