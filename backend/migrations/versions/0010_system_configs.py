"""system config encrypted storage

Revision ID: 0010_system_configs
Revises: 0009_chat_sessions
Create Date: 2026-07-16
"""

from alembic import op
import sqlalchemy as sa
from migrations.helpers import table_exists


revision = "0010_system_configs"
down_revision = "0009_chat_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if table_exists("system_configs"):
        return
    op.create_table(
        "system_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("config_key", sa.String(length=120), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("config_key", name="uq_system_configs_config_key"),
    )
    op.create_index("ix_system_configs_config_key", "system_configs", ["config_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_system_configs_config_key", table_name="system_configs")
    op.drop_table("system_configs")
