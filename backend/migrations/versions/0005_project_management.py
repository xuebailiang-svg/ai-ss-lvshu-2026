"""project management soft delete

Revision ID: 0005_project_management
Revises: 0004_unified_data_model
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_project_management"
down_revision = "0004_unified_data_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("site_projects", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("site_projects", "deleted_at")
