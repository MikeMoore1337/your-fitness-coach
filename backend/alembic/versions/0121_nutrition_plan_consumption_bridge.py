"""Add explicit planned-item lifecycle and diary bridge metadata."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0121_plan_consumption_bridge"
down_revision: str | None = "0120_nutrition_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds additive planned-item lifecycle fields and allows the canonical diary batch "
    "writer to link one consumed plan item without changing existing entries."
)


def upgrade() -> None:
    op.add_column(
        "nutrition_plan_items",
        sa.Column("status", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "nutrition_plan_items",
        sa.Column("diary_entry_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "nutrition_plan_items",
        sa.Column("action_idempotency_key", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "nutrition_plan_items",
        sa.Column("action_request_fingerprint", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("nutrition_plan_items", "action_request_fingerprint")
    op.drop_column("nutrition_plan_items", "action_idempotency_key")
    op.drop_column("nutrition_plan_items", "diary_entry_id")
    op.drop_column("nutrition_plan_items", "status")
