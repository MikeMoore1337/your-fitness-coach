"""Allow plan fill operations in the existing plan idempotency ledger."""

from collections.abc import Sequence

from alembic import op

revision: str = "0122_plan_fill_kind"
down_revision: str | None = "0121_plan_consumption_bridge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "constraint_swap"
online_rollout_constraint_table = "nutrition_plan_operations"
online_rollout_constraint_name = "ck_nutrition_plan_operations_kind"
online_rollout_lock_timeout_seconds = 3
online_rollout_statement_timeout_seconds = 30
online_rollout_notes = (
    "Adds the plan-fill operation kind through a bounded NOT VALID CHECK replacement "
    "without rewriting existing idempotency rows."
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE nutrition_plan_operations DROP CONSTRAINT IF EXISTS "
            "ck_nutrition_plan_operations_kind, ADD CONSTRAINT "
            "ck_nutrition_plan_operations_kind CHECK (operation_kind IN "
            "('add', 'copy', 'fill')) NOT VALID"
        )
        op.execute(
            "ALTER TABLE nutrition_plan_operations VALIDATE CONSTRAINT "
            "ck_nutrition_plan_operations_kind"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE nutrition_plan_operations DROP CONSTRAINT IF EXISTS "
            "ck_nutrition_plan_operations_kind, ADD CONSTRAINT "
            "ck_nutrition_plan_operations_kind CHECK (operation_kind IN "
            "('add', 'copy')) NOT VALID"
        )
        op.execute(
            "ALTER TABLE nutrition_plan_operations VALIDATE CONSTRAINT "
            "ck_nutrition_plan_operations_kind"
        )
