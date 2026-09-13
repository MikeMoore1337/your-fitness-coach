"""Add basis-aware food facts and local nutrition-label draft/catalog lifecycle.

Revision ID: 0081_nutrition_label_catalog
Revises: 0080_program_import_doc_format
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0081_nutrition_label_catalog"
down_revision: str | None = "0080_program_import_doc_format"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds canonical basis/provenance JSON, owner-scoped short-lived label drafts and persistent "
    "user-confirmed community contributions. Existing 100 g projections remain populated."
)


def _food_constraints(batch_op) -> None:
    for name in (
        "ck_foods_provenance",
        "ck_foods_standard_serving_complete",
        "ck_foods_active_nutrients",
        "ck_foods_active_catalog_trust",
    ):
        batch_op.drop_constraint(name, type_="check")
    batch_op.create_check_constraint(
        "ck_foods_provenance",
        "provenance IN ('internal', 'external', 'user', 'user_confirmed_package')",
    )
    batch_op.create_check_constraint(
        "ck_foods_standard_serving_complete",
        "standard_serving_amount IS NULL AND standard_serving_unit IS NULL "
        "AND standard_serving_weight_g IS NULL OR standard_serving_amount > 0 "
        "AND standard_serving_unit IN ('g', 'ml', 'piece', 'serving') "
        "AND (standard_serving_unit IN ('ml', 'serving') OR standard_serving_weight_g > 0)",
    )
    batch_op.create_check_constraint(
        "ck_foods_active_nutrients",
        "status <> 'active' OR (energy_kcal_per_100g IS NOT NULL "
        "AND protein_g_per_100g IS NOT NULL AND fat_g_per_100g IS NOT NULL "
        "AND carbs_g_per_100g IS NOT NULL) OR canonical_complete = true",
    )
    batch_op.create_check_constraint(
        "ck_foods_active_catalog_trust",
        "food_type = 'user' OR status <> 'active' OR trust_level = 'verified' "
        "OR catalog_quality = 'community_unverified'",
    )
    batch_op.create_check_constraint(
        "ck_foods_catalog_quality",
        "catalog_quality IN ('private', 'verified', 'community_unverified')",
    )
    batch_op.create_check_constraint(
        "ck_foods_nutrition_basis_kind",
        "nutrition_basis_kind IN ('per_100_g', 'per_100_ml', 'per_serving')",
    )
    batch_op.create_check_constraint(
        "ck_foods_nutrition_basis_unit",
        "nutrition_basis_unit IN ('g', 'ml', 'serving')",
    )
    batch_op.create_check_constraint(
        "ck_foods_nutrition_basis_shape",
        "(nutrition_basis_kind = 'per_100_g' AND nutrition_basis_unit = 'g' "
        "AND nutrition_basis_amount = 100) OR "
        "(nutrition_basis_kind = 'per_100_ml' AND nutrition_basis_unit = 'ml' "
        "AND nutrition_basis_amount = 100) OR "
        "(nutrition_basis_kind = 'per_serving' AND nutrition_basis_unit = 'serving' "
        "AND nutrition_basis_amount = 1)",
    )


def upgrade() -> None:
    op.add_column(
        "foods",
        sa.Column("nutrition_basis_kind", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "foods",
        sa.Column("nutrition_basis_amount", sa.Numeric(precision=10, scale=3), nullable=True),
    )
    op.add_column(
        "foods",
        sa.Column("nutrition_basis_unit", sa.String(length=16), nullable=True),
    )
    op.add_column("foods", sa.Column("canonical_facts", sa.JSON(), nullable=True))
    op.add_column("foods", sa.Column("nutrition_provenance", sa.JSON(), nullable=True))
    op.add_column(
        "foods",
        sa.Column("canonical_complete", sa.Boolean(), nullable=True, server_default=sa.true()),
    )
    op.add_column(
        "foods",
        sa.Column("catalog_quality", sa.String(length=24), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE foods SET nutrition_basis_kind = 'per_100_g', "
            "nutrition_basis_amount = 100, nutrition_basis_unit = 'g', "
            "canonical_complete = true, "
            "catalog_quality = CASE WHEN food_type = 'user' THEN 'private' ELSE 'verified' END "
            "WHERE nutrition_basis_kind IS NULL"
        )
    )
    with op.batch_alter_table("foods") as batch_op:
        batch_op.alter_column(
            "provenance",
            existing_type=sa.String(length=16),
            type_=sa.String(length=32),
        )
        batch_op.alter_column(
            "nutrition_basis_kind",
            existing_type=sa.String(length=16),
            nullable=False,
            server_default="per_100_g",
        )
        batch_op.alter_column(
            "nutrition_basis_amount",
            existing_type=sa.Numeric(precision=10, scale=3),
            nullable=False,
            server_default="100",
        )
        batch_op.alter_column(
            "nutrition_basis_unit",
            existing_type=sa.String(length=16),
            nullable=False,
            server_default="g",
        )
        batch_op.alter_column(
            "canonical_complete",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        )
        batch_op.alter_column(
            "catalog_quality",
            existing_type=sa.String(length=24),
            nullable=False,
            server_default="verified",
        )
        _food_constraints(batch_op)

    op.create_table(
        "nutrition_label_drafts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("canonical_payload", sa.JSON(), nullable=False),
        sa.Column("product_name", sa.String(length=256), nullable=True),
        sa.Column("product_brand", sa.String(length=128), nullable=True),
        sa.Column("product_barcode", sa.String(length=14), nullable=True),
        sa.Column("confirmed_visibility", sa.String(length=24), nullable=True),
        sa.Column("confirmed_food_id", sa.Integer(), nullable=True),
        sa.Column("ocr_engine", sa.String(length=32), nullable=False),
        sa.Column("ocr_engine_version", sa.String(length=64), nullable=False),
        sa.Column("source_mime", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'confirmed', 'cancelled', 'expired')",
            name="ck_nutrition_label_drafts_status",
        ),
        sa.CheckConstraint("revision > 0", name="ck_nutrition_label_drafts_revision"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="nutrition_label_drafts_user_id_fkey", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_food_id"],
            ["foods.id"],
            name="nutrition_label_drafts_confirmed_food_id_fkey",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="nutrition_label_drafts_pkey"),
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name="uq_nutrition_label_drafts_user_idempotency"
        ),
    )
    op.create_index(
        "ix_nutrition_label_drafts_user_status",
        "nutrition_label_drafts",
        ["user_id", "status", "expires_at"],
    )
    op.create_index(
        "ix_nutrition_label_drafts_expires_at", "nutrition_label_drafts", ["expires_at"]
    )

    op.create_table(
        "nutrition_catalog_contributions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=False),
        sa.Column("contributor_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "visibility", sa.String(length=24), nullable=False, server_default="share_to_yfc_catalog"
        ),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("payload_digest", sa.String(length=64), nullable=False),
        sa.Column("canonical_payload", sa.JSON(), nullable=False),
        sa.Column("source_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "state IN ('accepted', 'duplicate', 'conflict')",
            name="ck_nutrition_catalog_contributions_state",
        ),
        sa.CheckConstraint(
            "visibility = 'share_to_yfc_catalog'",
            name="ck_nutrition_catalog_contributions_visibility",
        ),
        sa.ForeignKeyConstraint(
            ["food_id"], ["foods.id"], name="nutrition_catalog_contributions_food_id_fkey", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["contributor_user_id"],
            ["users.id"],
            name="nutrition_catalog_contributions_contributor_user_id_fkey",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="nutrition_catalog_contributions_pkey"),
        sa.UniqueConstraint(
            "food_id",
            "payload_digest",
            name="uq_nutrition_catalog_contributions_food_digest",
        ),
    )
    op.create_index(
        "ix_nutrition_catalog_contributions_food_created",
        "nutrition_catalog_contributions",
        ["food_id", "created_at"],
    )
    op.create_index(
        "ix_nutrition_catalog_contributions_contributor_created",
        "nutrition_catalog_contributions",
        ["contributor_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_nutrition_catalog_contributions_contributor_created",
        table_name="nutrition_catalog_contributions",
    )
    op.drop_index(
        "ix_nutrition_catalog_contributions_food_created",
        table_name="nutrition_catalog_contributions",
    )
    op.drop_table("nutrition_catalog_contributions")
    op.drop_index("ix_nutrition_label_drafts_expires_at", table_name="nutrition_label_drafts")
    op.drop_index("ix_nutrition_label_drafts_user_status", table_name="nutrition_label_drafts")
    op.drop_table("nutrition_label_drafts")
    with op.batch_alter_table("foods") as batch_op:
        for name in (
            "ck_foods_nutrition_basis_shape",
            "ck_foods_nutrition_basis_unit",
            "ck_foods_nutrition_basis_kind",
            "ck_foods_catalog_quality",
            "ck_foods_active_catalog_trust",
            "ck_foods_active_nutrients",
            "ck_foods_standard_serving_complete",
            "ck_foods_provenance",
        ):
            batch_op.drop_constraint(name, type_="check")
        batch_op.create_check_constraint(
            "ck_foods_provenance", "provenance IN ('internal', 'external', 'user')"
        )
        batch_op.create_check_constraint(
            "ck_foods_standard_serving_complete",
            "standard_serving_amount IS NULL AND standard_serving_unit IS NULL "
            "AND standard_serving_weight_g IS NULL OR standard_serving_amount > 0 "
            "AND standard_serving_unit IN ('g', 'ml', 'piece', 'serving') "
            "AND standard_serving_weight_g > 0",
        )
        batch_op.create_check_constraint(
            "ck_foods_active_nutrients",
            "status <> 'active' OR (energy_kcal_per_100g IS NOT NULL "
            "AND protein_g_per_100g IS NOT NULL AND fat_g_per_100g IS NOT NULL "
            "AND carbs_g_per_100g IS NOT NULL)",
        )
        batch_op.create_check_constraint(
            "ck_foods_active_catalog_trust",
            "food_type = 'user' OR status <> 'active' OR trust_level = 'verified'",
        )
        batch_op.alter_column(
            "provenance",
            existing_type=sa.String(length=32),
            type_=sa.String(length=16),
        )
        batch_op.drop_column("catalog_quality")
        batch_op.drop_column("canonical_complete")
        batch_op.drop_column("nutrition_provenance")
        batch_op.drop_column("canonical_facts")
        batch_op.drop_column("nutrition_basis_unit")
        batch_op.drop_column("nutrition_basis_amount")
        batch_op.drop_column("nutrition_basis_kind")
