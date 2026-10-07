"""Allow stale recipe plan sources after recipe deletion."""

from collections.abc import Sequence

from alembic import op

revision: str = "0126_nutrition_plan_source_constraint"
down_revision: str | None = "0125_grocery_lists"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "constraint_swap"
online_rollout_constraint_table = "nutrition_plan_items"
online_rollout_constraint_name = "ck_nutrition_plan_items_single_source"
online_rollout_lock_timeout_seconds = 3
online_rollout_statement_timeout_seconds = 30
online_rollout_notes = (
    "Relaxes only the recipe source reference so a planned row can retain a stale "
    "snapshot after recipe deletion; PostgreSQL constraint validation remains bounded."
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute(
        "ALTER TABLE nutrition_plan_items DROP CONSTRAINT IF EXISTS "
        "ck_nutrition_plan_items_single_source, ADD CONSTRAINT "
        "ck_nutrition_plan_items_single_source CHECK ("
        "(item_kind = 'food' AND food_id IS NOT NULL AND recipe_id IS NULL) OR "
        "(item_kind = 'recipe' AND food_id IS NULL AND amount_unit = 'g')) NOT VALID"
    )
    op.execute(
        "ALTER TABLE nutrition_plan_items VALIDATE CONSTRAINT ck_nutrition_plan_items_single_source"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute(
        "ALTER TABLE nutrition_plan_items DROP CONSTRAINT IF EXISTS "
        "ck_nutrition_plan_items_single_source, ADD CONSTRAINT "
        "ck_nutrition_plan_items_single_source CHECK ("
        "(item_kind = 'food' AND food_id IS NOT NULL AND recipe_id IS NULL) OR "
        "(item_kind = 'recipe' AND recipe_id IS NOT NULL AND food_id IS NULL AND "
        "amount_unit = 'g')) NOT VALID"
    )
    op.execute(
        "ALTER TABLE nutrition_plan_items VALIDATE CONSTRAINT ck_nutrition_plan_items_single_source"
    )
