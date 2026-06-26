"""poi enrichments

Revision ID: 0003_poi_enrichments
Revises: 0002_m15_research_enhancements
Create Date: 2026-06-25
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_poi_enrichments"
down_revision = "0002_m15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "poi_enrichments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("poi_observation_id", sa.Integer(), sa.ForeignKey("poi_observations.id"), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("data_source", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column("verification_status", sa.String(length=50), nullable=False, server_default="未核实"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("poi_observation_id"),
    )
    op.create_index("ix_poi_enrichments_poi_observation_id", "poi_enrichments", ["poi_observation_id"])
    op.alter_column("poi_observations", "longitude", existing_type=sa.Float(), nullable=True)
    op.alter_column("poi_observations", "latitude", existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    op.alter_column("poi_observations", "latitude", existing_type=sa.Float(), nullable=False)
    op.alter_column("poi_observations", "longitude", existing_type=sa.Float(), nullable=False)
    op.drop_index("ix_poi_enrichments_poi_observation_id", table_name="poi_enrichments")
    op.drop_table("poi_enrichments")
