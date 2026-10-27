"""Allow quick diary entries to retain partial macro estimates."""

from collections.abc import Sequence

from alembic import op

revision: str = "0103_nutrition_partial"
down_revision: str | None = "0102_nutrition_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "constraint_swap"
online_rollout_constraint_table = "food_diary_entries"
online_rollout_constraint_name = "ck_food_diary_entries_quick_macros_complete"
online_rollout_lock_timeout_seconds = 3
online_rollout_statement_timeout_seconds = 30
online_rollout_notes = (
    "Swaps the legacy all-or-none quick macro check under bounded local timeouts; the replacement "
    "retains the required quick calorie invariant while allowing nullable individual macros."
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE food_diary_entries DROP CONSTRAINT IF EXISTS "
            "ck_food_diary_entries_quick_macros_complete, ADD CONSTRAINT "
            "ck_food_diary_entries_quick_macros_complete CHECK ("
            "entry_kind <> 'quick_add' OR quick_energy_kcal IS NOT NULL) NOT VALID"
        )
        op.execute(
            "ALTER TABLE food_diary_entries VALIDATE CONSTRAINT "
            "ck_food_diary_entries_quick_macros_complete"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE food_diary_entries DROP CONSTRAINT IF EXISTS "
            "ck_food_diary_entries_quick_macros_complete, ADD CONSTRAINT "
            "ck_food_diary_entries_quick_macros_complete CHECK ("
            "(quick_protein_g IS NULL AND quick_fat_g IS NULL AND quick_carbs_g IS NULL) OR "
            "(quick_protein_g IS NOT NULL AND quick_fat_g IS NOT NULL AND "
            "quick_carbs_g IS NOT NULL)) NOT VALID"
        )
        op.execute(
            "ALTER TABLE food_diary_entries VALIDATE CONSTRAINT "
            "ck_food_diary_entries_quick_macros_complete"
        )
