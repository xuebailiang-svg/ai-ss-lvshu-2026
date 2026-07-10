"""unified data model

Revision ID: 0004_unified_data_model
Revises: 0003_poi_enrichments
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_unified_data_model"
down_revision = "0003_poi_enrichments"
branch_labels = None
depends_on = None


def source_columns() -> list[sa.Column]:
    return [
        sa.Column("source", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending_review"),
        sa.Column("raw_data", sa.JSON(), nullable=False, server_default="{}"),
    ]


def upgrade() -> None:
    op.create_table(
        "site_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("project_name", sa.String(length=160), nullable=True),
        sa.Column("city", sa.String(length=80), nullable=False),
        sa.Column("district", sa.String(length=80), nullable=True),
        sa.Column("address", sa.String(length=300), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("radius_meters", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("business_type", sa.String(length=80), nullable=False, server_default="电竞馆"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        *source_columns(),
        sa.UniqueConstraint("project_id"),
    )
    op.create_index("ix_site_projects_project_id", "site_projects", ["project_id"])

    op.create_table(
        "pois",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(length=80), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("sub_category", sa.String(length=100), nullable=True),
        sa.Column("address", sa.String(length=300), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("distance_meters", sa.Integer(), nullable=True),
        sa.Column("walking_distance_meters", sa.Integer(), nullable=True),
        sa.Column("business_hours", sa.String(length=200), nullable=True),
        *source_columns(),
    )
    op.create_index("ix_pois_project_id", "pois", ["project_id"])
    op.create_index("ix_pois_category", "pois", ["category"])

    op.create_table(
        "competitors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(length=80), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("address", sa.String(length=300), nullable=True),
        sa.Column("distance_meters", sa.Integer(), nullable=True),
        sa.Column("area_sqm", sa.Float(), nullable=True),
        sa.Column("opening_date", sa.String(length=50), nullable=True),
        sa.Column("opening_years", sa.Float(), nullable=True),
        sa.Column("machine_count", sa.Integer(), nullable=True),
        sa.Column("cpu", sa.String(length=120), nullable=True),
        sa.Column("gpu", sa.String(length=120), nullable=True),
        sa.Column("monitor", sa.String(length=120), nullable=True),
        sa.Column("hour_price", sa.Float(), nullable=True),
        sa.Column("member_price", sa.Float(), nullable=True),
        sa.Column("occupancy_rate", sa.Float(), nullable=True),
        sa.Column("monthly_sales", sa.Float(), nullable=True),
        sa.Column("annual_sales", sa.Float(), nullable=True),
        sa.Column("recharge_amount", sa.Float(), nullable=True),
        *source_columns(),
    )
    op.create_index("ix_competitors_project_id", "competitors", ["project_id"])

    op.create_table(
        "food_businesses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(length=80), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("distance_meters", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("opening_date", sa.String(length=50), nullable=True),
        sa.Column("opening_years", sa.Float(), nullable=True),
        sa.Column("business_hours", sa.String(length=200), nullable=True),
        sa.Column("night_business", sa.Boolean(), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        *source_columns(),
    )
    op.create_index("ix_food_businesses_project_id", "food_businesses", ["project_id"])

    op.create_table(
        "entertainments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(length=80), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False, server_default="other"),
        sa.Column("distance_meters", sa.Integer(), nullable=True),
        sa.Column("opening_date", sa.String(length=50), nullable=True),
        sa.Column("business_hours", sa.String(length=200), nullable=True),
        sa.Column("night_business", sa.Boolean(), nullable=True),
        *source_columns(),
    )
    op.create_index("ix_entertainments_project_id", "entertainments", ["project_id"])

    op.create_table(
        "rent_data",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(length=80), nullable=True),
        sa.Column("monthly_rent", sa.Float(), nullable=True),
        sa.Column("area_sqm", sa.Float(), nullable=True),
        sa.Column("rent_per_sqm", sa.Float(), nullable=True),
        sa.Column("location_type", sa.String(length=100), nullable=True),
        *source_columns(),
    )
    op.create_index("ix_rent_data_project_id", "rent_data", ["project_id"])

    op.create_table(
        "population_data",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(length=80), nullable=True),
        sa.Column("nearby_university_count", sa.Integer(), nullable=True),
        sa.Column("nearby_school_count", sa.Integer(), nullable=True),
        sa.Column("nearby_apartment_count", sa.Integer(), nullable=True),
        sa.Column("nearby_residential_count", sa.Integer(), nullable=True),
        sa.Column("young_population_indicator", sa.Float(), nullable=True),
        *source_columns(),
    )
    op.create_index("ix_population_data_project_id", "population_data", ["project_id"])

    op.create_table(
        "supplements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(length=80), nullable=True),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", sa.String(length=120), nullable=True),
        sa.Column("field_name", sa.String(length=120), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        *source_columns(),
        sa.Column("created_time", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_supplements_project_id", "supplements", ["project_id"])
    op.create_index("ix_supplements_target_type", "supplements", ["target_type"])


def downgrade() -> None:
    op.drop_index("ix_supplements_target_type", table_name="supplements")
    op.drop_index("ix_supplements_project_id", table_name="supplements")
    op.drop_table("supplements")
    op.drop_index("ix_population_data_project_id", table_name="population_data")
    op.drop_table("population_data")
    op.drop_index("ix_rent_data_project_id", table_name="rent_data")
    op.drop_table("rent_data")
    op.drop_index("ix_entertainments_project_id", table_name="entertainments")
    op.drop_table("entertainments")
    op.drop_index("ix_food_businesses_project_id", table_name="food_businesses")
    op.drop_table("food_businesses")
    op.drop_index("ix_competitors_project_id", table_name="competitors")
    op.drop_table("competitors")
    op.drop_index("ix_pois_category", table_name="pois")
    op.drop_index("ix_pois_project_id", table_name="pois")
    op.drop_table("pois")
    op.drop_index("ix_site_projects_project_id", table_name="site_projects")
    op.drop_table("site_projects")
