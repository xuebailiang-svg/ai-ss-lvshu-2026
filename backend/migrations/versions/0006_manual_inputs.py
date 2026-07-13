"""manual input history

Revision ID: 0006_manual_inputs
Revises: 0005_project_management
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_manual_inputs"
down_revision = "0005_project_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manual_inputs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", sa.String(length=120), nullable=True),
        sa.Column("field_name", sa.String(length=120), nullable=False),
        sa.Column("old_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.8"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_manual_inputs_project_id", "manual_inputs", ["project_id"])
    op.create_index("ix_manual_inputs_target_type", "manual_inputs", ["target_type"])
    op.create_index("ix_manual_inputs_target_id", "manual_inputs", ["target_id"])


def downgrade() -> None:
    op.drop_index("ix_manual_inputs_target_id", table_name="manual_inputs")
    op.drop_index("ix_manual_inputs_target_type", table_name="manual_inputs")
    op.drop_index("ix_manual_inputs_project_id", table_name="manual_inputs")
    op.drop_table("manual_inputs")
