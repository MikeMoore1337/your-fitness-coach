"""Track confirmed macro-aware suggestions in the existing diary batch ledger."""

from collections.abc import Sequence

from alembic import op

revision: str = "0106_macro_aware_suggestions"
down_revision: str | None = "0105_russian_program_titles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "constraint_swap"
online_rollout_constraint_table = "food_diary_batch_operations"
online_rollout_constraint_name = "ck_food_diary_batch_operations_kind"
online_rollout_lock_timeout_seconds = 3
online_rollout_statement_timeout_seconds = 30
online_rollout_notes = (
    "Allows explicit macro-aware suggestion confirmations to use the existing idempotent diary "
    "batch ledger without changing existing rows or nutrition snapshots."
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE food_diary_batch_operations DROP CONSTRAINT IF EXISTS "
            "ck_food_diary_batch_operations_kind, ADD CONSTRAINT "
            "ck_food_diary_batch_operations_kind CHECK (operation_kind IN "
            "('meal_template', 'natural_input', 'suggestion')) NOT VALID"
        )
        op.execute(
            "ALTER TABLE food_diary_batch_operations VALIDATE CONSTRAINT "
            "ck_food_diary_batch_operations_kind"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE food_diary_batch_operations DROP CONSTRAINT IF EXISTS "
            "ck_food_diary_batch_operations_kind, ADD CONSTRAINT "
            "ck_food_diary_batch_operations_kind CHECK (operation_kind IN "
            "('meal_template', 'natural_input')) NOT VALID"
        )
        op.execute(
            "ALTER TABLE food_diary_batch_operations VALIDATE CONSTRAINT "
            "ck_food_diary_batch_operations_kind"
        )
