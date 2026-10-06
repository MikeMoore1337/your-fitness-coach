"""Constrain the new planned-item lifecycle fields."""

from collections.abc import Sequence

from alembic import op

revision: str = "0124_plan_item_lifecycle"
down_revision: str | None = "0123_diary_planned_item_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "constraint_swap"
online_rollout_constraint_table = "nutrition_plan_items"
online_rollout_constraint_name = "ck_nutrition_plan_items_lifecycle"
online_rollout_lock_timeout_seconds = 3
online_rollout_statement_timeout_seconds = 30
online_rollout_notes = (
    "Adds one bounded lifecycle CHECK that tolerates pre-bridge NULL status values, "
    "enforces valid new writes, and avoids a blocking table rewrite."
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE nutrition_plan_items DROP CONSTRAINT IF EXISTS "
            "ck_nutrition_plan_items_lifecycle, ADD CONSTRAINT "
            "ck_nutrition_plan_items_lifecycle CHECK ("
            "(status IS NULL OR status IN ('planned', 'consumed', 'skipped')) AND "
            "(diary_entry_id IS NULL OR status = 'consumed')) NOT VALID"
        )
        op.execute(
            "ALTER TABLE nutrition_plan_items VALIDATE CONSTRAINT ck_nutrition_plan_items_lifecycle"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE nutrition_plan_items DROP CONSTRAINT IF EXISTS "
            "ck_nutrition_plan_items_lifecycle"
        )
