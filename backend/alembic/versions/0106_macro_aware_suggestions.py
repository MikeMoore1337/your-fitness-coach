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

_CONSTRAINT = "ck_food_diary_batch_operations_kind"
_EXPRESSION = "operation_kind IN ('meal_template', 'natural_input', 'suggestion')"
_LEGACY_EXPRESSION = "operation_kind IN ('meal_template', 'natural_input')"


def _postgres_constraint(expression: str) -> None:
    op.execute(
        f"ALTER TABLE food_diary_batch_operations DROP CONSTRAINT IF EXISTS {_CONSTRAINT}, "
        f"ADD CONSTRAINT {_CONSTRAINT} CHECK ({expression}) NOT VALID"
    )
    op.execute(
        f"ALTER TABLE food_diary_batch_operations VALIDATE CONSTRAINT {_CONSTRAINT}"
    )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        _postgres_constraint(_EXPRESSION)
        return
    with op.batch_alter_table("food_diary_batch_operations") as batch_op:
        batch_op.drop_constraint(_CONSTRAINT, type_="check")
        batch_op.create_check_constraint(_CONSTRAINT, _EXPRESSION)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        _postgres_constraint(_LEGACY_EXPRESSION)
        return
    with op.batch_alter_table("food_diary_batch_operations") as batch_op:
        batch_op.drop_constraint(_CONSTRAINT, type_="check")
        batch_op.create_check_constraint(_CONSTRAINT, _LEGACY_EXPRESSION)
