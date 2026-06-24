"""m15 research enhancements"""
from alembic import op
import sqlalchemy as sa

revision = "0002_m15"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    property_columns = [
        sa.Column("usable_area_sqm", sa.Float(), nullable=True),
        sa.Column("floor_height_m", sa.Float(), nullable=True),
        sa.Column("rent_per_sqm_day", sa.Float(), nullable=True),
        sa.Column("rent_per_sqm_month", sa.Float(), nullable=True),
        sa.Column("property_fee_monthly", sa.Float(), nullable=True),
        sa.Column("transfer_fee", sa.Float(), nullable=True),
        sa.Column("deposit", sa.Float(), nullable=True),
        sa.Column("rent_free_months", sa.Float(), nullable=True),
        sa.Column("lease_term_months", sa.Integer(), nullable=True),
        sa.Column("rent_escalation", sa.String(length=200), nullable=True),
        sa.Column("power_capacity_kw", sa.Float(), nullable=True),
        sa.Column("power_expansion_allowed", sa.Boolean(), nullable=True),
        sa.Column("network_carriers", sa.String(length=200), nullable=True),
        sa.Column("dual_line_supported", sa.Boolean(), nullable=True),
        sa.Column("sprinkler", sa.Boolean(), nullable=True),
        sa.Column("smoke_exhaust", sa.Boolean(), nullable=True),
        sa.Column("safety_exit_count", sa.Integer(), nullable=True),
        sa.Column("parking_condition", sa.String(length=200), nullable=True),
        sa.Column("facade_width_m", sa.Float(), nullable=True),
        sa.Column("facade_visibility", sa.String(length=100), nullable=True),
        sa.Column("noise_complaint_risk", sa.String(length=100), nullable=True),
        sa.Column("required_rectifications", sa.Text(), nullable=True),
        sa.Column("property_contact", sa.String(length=120), nullable=True),
        sa.Column("machine_count", sa.Integer(), nullable=True),
        sa.Column("rent_per_machine_month", sa.Float(), nullable=True),
        sa.Column("surveyed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    ]
    for column in property_columns:
        op.add_column("property_surveys", column)

    competitor_columns = [
        sa.Column("cpu", sa.String(length=100), nullable=True),
        sa.Column("gpu", sa.String(length=100), nullable=True),
        sa.Column("monitor_size_inch", sa.Float(), nullable=True),
        sa.Column("monitor_refresh_rate", sa.Integer(), nullable=True),
        sa.Column("normal_price", sa.Float(), nullable=True),
        sa.Column("premium_price", sa.Float(), nullable=True),
        sa.Column("private_room_price", sa.Float(), nullable=True),
        sa.Column("member_price", sa.Float(), nullable=True),
        sa.Column("recharge_promotion", sa.String(length=300), nullable=True),
        sa.Column("opening_basis", sa.String(length=300), nullable=True),
        sa.Column("peak_occupancy_rate", sa.Float(), nullable=True),
        sa.Column("offpeak_occupancy_rate", sa.Float(), nullable=True),
        sa.Column("survey_method", sa.String(length=100), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_manually_verified", sa.Boolean(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    ]
    for column in competitor_columns:
        op.add_column("competitor_enrichments", column)

    op.create_table(
        "competitor_survey_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("poi_observation_id", sa.Integer(), sa.ForeignKey("poi_observations.id"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_competitor_survey_records_poi_observation_id", "competitor_survey_records", ["poi_observation_id"])


def downgrade():
    op.drop_index("ix_competitor_survey_records_poi_observation_id", table_name="competitor_survey_records")
    op.drop_table("competitor_survey_records")
    for name in [
        "updated_at", "is_manually_verified", "verified_at", "survey_method", "offpeak_occupancy_rate",
        "peak_occupancy_rate", "opening_basis", "recharge_promotion", "member_price", "private_room_price",
        "premium_price", "normal_price", "monitor_refresh_rate", "monitor_size_inch", "gpu", "cpu",
    ]:
        op.drop_column("competitor_enrichments", name)
    for name in [
        "updated_at", "verified_at", "confidence", "source", "surveyed_at", "rent_per_machine_month",
        "machine_count", "property_contact", "required_rectifications", "noise_complaint_risk",
        "facade_visibility", "facade_width_m", "parking_condition", "safety_exit_count", "smoke_exhaust",
        "sprinkler", "dual_line_supported", "network_carriers", "power_expansion_allowed",
        "power_capacity_kw", "rent_escalation", "lease_term_months", "rent_free_months", "deposit",
        "transfer_fee", "property_fee_monthly", "rent_per_sqm_month", "rent_per_sqm_day",
        "floor_height_m", "usable_area_sqm",
    ]:
        op.drop_column("property_surveys", name)
