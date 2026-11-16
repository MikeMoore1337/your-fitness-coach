"""Replace the active-food CHECK with its basis-aware equivalent."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0156_nutrition_catalog_check"
down_revision: str | None = "0155_nutrition_catalog_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "constraint_swap"
online_rollout_notes = "Replace and validate the active-food CHECK under bounded PostgreSQL locks."
online_rollout_constraint_table = "foods"
online_rollout_constraint_name = "ck_foods_active_nutrients"
online_rollout_lock_timeout_seconds = 3
online_rollout_statement_timeout_seconds = 30


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE foods DROP CONSTRAINT IF EXISTS ck_foods_active_nutrients, ADD CONSTRAINT ck_foods_active_nutrients CHECK ("
            "status <> 'active' OR (energy_kcal_per_100g IS NOT NULL "
            "AND protein_g_per_100g IS NOT NULL AND fat_g_per_100g IS NOT NULL "
            "AND carbs_g_per_100g IS NOT NULL) "
            "OR (canonical_complete IS TRUE "
            "AND (source_name IS NULL OR source_name <> 'yfc_community' OR ("
            "canonical_facts IS NOT NULL AND nutrition_basis_kind IS NOT NULL "
            "AND nutrition_basis_kind IN ('per_100_g', 'per_100_ml', 'per_serving') "
            "AND ((canonical_facts ->> 'source_basis') = nutrition_basis_kind OR ("
            "(canonical_facts ->> 'source_basis') = 'per_serving' "
            "AND ((nutrition_basis_kind = 'per_100_g' AND "
            "(canonical_facts -> 'serving_size' ->> 'unit') = 'g') OR "
            "(nutrition_basis_kind = 'per_100_ml' AND "
            "(canonical_facts -> 'serving_size' ->> 'unit') = 'ml')) "
            "AND standard_serving_unit = (canonical_facts -> 'serving_size' ->> 'unit') "
            "AND standard_serving_amount > 0 AND standard_serving_amount < 10000000 "
            "AND CAST(canonical_facts -> 'serving_size' ->> 'amount' AS NUMERIC) = standard_serving_amount)) "
            "AND (canonical_facts -> 'normalized_facts' -> 'energy_kcal' ->> 'basis_ref') IS NOT NULL "
            "AND (canonical_facts -> 'normalized_facts' -> 'energy_kcal' ->> 'basis_ref') = nutrition_basis_kind "
            "AND (canonical_facts -> 'normalized_facts' -> 'energy_kcal' ->> 'value') IS NOT NULL "
            "AND (canonical_facts -> 'normalized_facts' -> 'protein_g' ->> 'basis_ref') = nutrition_basis_kind "
            "AND (canonical_facts -> 'normalized_facts' -> 'protein_g' ->> 'value') IS NOT NULL "
            "AND (canonical_facts -> 'normalized_facts' -> 'fat_g' ->> 'basis_ref') = nutrition_basis_kind "
            "AND (canonical_facts -> 'normalized_facts' -> 'fat_g' ->> 'value') IS NOT NULL "
            "AND (canonical_facts -> 'normalized_facts' -> 'carbohydrate_g' ->> 'basis_ref') = nutrition_basis_kind "
            "AND (canonical_facts -> 'normalized_facts' -> 'carbohydrate_g' ->> 'value') IS NOT NULL)) IS TRUE)"
            ") NOT VALID"
        )
        op.execute("ALTER TABLE foods VALIDATE CONSTRAINT ck_foods_active_nutrients")
    else:
        with op.batch_alter_table("foods") as batch:
            batch.drop_constraint("ck_foods_active_nutrients", type_="check")
            batch.create_check_constraint(
                "ck_foods_active_nutrients",
                "status <> 'active' OR (energy_kcal_per_100g IS NOT NULL "
                "AND protein_g_per_100g IS NOT NULL AND fat_g_per_100g IS NOT NULL "
                "AND carbs_g_per_100g IS NOT NULL) "
                "OR (canonical_complete IS TRUE "
                "AND (source_name IS NULL OR source_name <> 'yfc_community' OR ("
                "canonical_facts IS NOT NULL AND nutrition_basis_kind IS NOT NULL "
                "AND nutrition_basis_kind IN ('per_100_g', 'per_100_ml', 'per_serving') "
                "AND ((canonical_facts ->> 'source_basis') = nutrition_basis_kind OR ("
                "(canonical_facts ->> 'source_basis') = 'per_serving' "
                "AND ((nutrition_basis_kind = 'per_100_g' AND "
                "(canonical_facts -> 'serving_size' ->> 'unit') = 'g') OR "
                "(nutrition_basis_kind = 'per_100_ml' AND "
                "(canonical_facts -> 'serving_size' ->> 'unit') = 'ml')) "
                "AND standard_serving_unit = (canonical_facts -> 'serving_size' ->> 'unit') "
                "AND standard_serving_amount > 0 AND standard_serving_amount < 10000000 "
                "AND CAST(canonical_facts -> 'serving_size' ->> 'amount' AS NUMERIC) = standard_serving_amount)) "
                "AND (canonical_facts -> 'normalized_facts' -> 'energy_kcal' ->> 'basis_ref') IS NOT NULL "
                "AND (canonical_facts -> 'normalized_facts' -> 'energy_kcal' ->> 'basis_ref') = nutrition_basis_kind "
                "AND (canonical_facts -> 'normalized_facts' -> 'energy_kcal' ->> 'value') IS NOT NULL "
                "AND (canonical_facts -> 'normalized_facts' -> 'protein_g' ->> 'basis_ref') = nutrition_basis_kind "
                "AND (canonical_facts -> 'normalized_facts' -> 'protein_g' ->> 'value') IS NOT NULL "
                "AND (canonical_facts -> 'normalized_facts' -> 'fat_g' ->> 'basis_ref') = nutrition_basis_kind "
                "AND (canonical_facts -> 'normalized_facts' -> 'fat_g' ->> 'value') IS NOT NULL "
                "AND (canonical_facts -> 'normalized_facts' -> 'carbohydrate_g' ->> 'basis_ref') = nutrition_basis_kind "
                "AND (canonical_facts -> 'normalized_facts' -> 'carbohydrate_g' ->> 'value') IS NOT NULL)) IS TRUE)",
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        if bind.execute(sa.text("SHOW transaction_isolation")).scalar_one() != "read committed":
            raise RuntimeError("Unsafe downgrade: PostgreSQL READ COMMITTED isolation is required")
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "LOCK TABLE foods, nutrition_catalog_identifiers, nutrition_import_drafts IN ACCESS EXCLUSIVE MODE"
        )
    elif bind.dialect.name == "sqlite":
        op.execute("UPDATE nutrition_import_drafts SET id = id WHERE 0")
        if not getattr(bind.connection.driver_connection, "in_transaction", False):
            raise RuntimeError("Unsafe downgrade: catalogue locking requires a transaction")
    else:
        raise RuntimeError("Unsafe downgrade: catalogue locking is unsupported")
    if (
        bind.execute(sa.text("SELECT 1 FROM nutrition_catalog_identifiers LIMIT 1")).first()
        or bind.execute(
            sa.text(
                "SELECT 1 FROM nutrition_import_drafts WHERE catalog_receipt IS NOT NULL OR adapter_id IS NOT NULL LIMIT 1"
            )
        ).first()
        or bind.execute(
            sa.text(
                "SELECT 1 FROM foods WHERE food_type = 'system' AND source_name = 'yfc_community' LIMIT 1"
            )
        ).first()
        or bind.execute(
            sa.text(
                "SELECT 1 FROM foods WHERE status = 'active' AND (energy_kcal_per_100g IS NULL "
                "OR protein_g_per_100g IS NULL OR fat_g_per_100g IS NULL OR carbs_g_per_100g IS NULL) LIMIT 1"
            )
        ).first()
    ):
        raise RuntimeError("Cannot discard catalogue import identity or receipt data")
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE foods DROP CONSTRAINT ck_foods_active_nutrients, "
            "ADD CONSTRAINT ck_foods_active_nutrients CHECK (status <> 'active' OR "
            "(energy_kcal_per_100g IS NOT NULL AND protein_g_per_100g IS NOT NULL "
            "AND fat_g_per_100g IS NOT NULL AND carbs_g_per_100g IS NOT NULL)) NOT VALID"
        )
        op.execute("ALTER TABLE foods VALIDATE CONSTRAINT ck_foods_active_nutrients")
    else:
        with op.batch_alter_table("foods") as batch:
            batch.drop_constraint("ck_foods_active_nutrients", type_="check")
            batch.create_check_constraint(
                "ck_foods_active_nutrients",
                "status <> 'active' OR (energy_kcal_per_100g IS NOT NULL "
                "AND protein_g_per_100g IS NOT NULL AND fat_g_per_100g IS NOT NULL "
                "AND carbs_g_per_100g IS NOT NULL)",
            )
