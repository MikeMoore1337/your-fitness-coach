"""Add explicit planned-item lifecycle and diary bridge metadata."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0121_nutrition_plan_consumption_bridge"
down_revision: str | None = "0120_nutrition_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds additive planned-item lifecycle fields and allows the canonical diary batch "
    "writer to link one consumed plan item without changing existing entries."
)


def upgrade() -> None:
    with op.batch_alter_table("nutrition_plan_items") as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(length=16), server_default="planned", nullable=False)
        )
        batch_op.add_column(sa.Column("diary_entry_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("action_idempotency_key", sa.String(length=128), nullable=True)
        )
        batch_op.add_column(
            sa.Column("action_request_fingerprint", sa.String(length=64), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_nutrition_plan_items_diary_entry_id",
            "food_diary_entries",
            ["diary_entry_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_check_constraint(
            "ck_nutrition_plan_items_status",
            "status IN ('planned', 'consumed', 'skipped')",
        )
        batch_op.create_check_constraint(
            "ck_nutrition_plan_items_diary_link",
            "diary_entry_id IS NULL OR status = 'consumed'",
        )

    op.create_index(
        "ix_nutrition_plan_items_diary_entry_id",
        "nutrition_plan_items",
        ["diary_entry_id"],
    )

    with op.batch_alter_table("nutrition_plan_operations") as batch_op:
        batch_op.drop_constraint("ck_nutrition_plan_operations_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_nutrition_plan_operations_kind",
            "operation_kind IN ('add', 'copy', 'fill')",
        )

    with op.batch_alter_table("food_diary_batch_operations") as batch_op:
        batch_op.drop_constraint("ck_food_diary_batch_operations_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_food_diary_batch_operations_kind",
            "operation_kind IN ('meal_template', 'natural_input', 'suggestion', 'planned_item')",
        )


def downgrade() -> None:
    with op.batch_alter_table("food_diary_batch_operations") as batch_op:
        batch_op.drop_constraint("ck_food_diary_batch_operations_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_food_diary_batch_operations_kind",
            "operation_kind IN ('meal_template', 'natural_input', 'suggestion')",
        )

    with op.batch_alter_table("nutrition_plan_operations") as batch_op:
        batch_op.drop_constraint("ck_nutrition_plan_operations_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_nutrition_plan_operations_kind",
            "operation_kind IN ('add', 'copy')",
        )

    op.drop_index(
        "ix_nutrition_plan_items_diary_entry_id",
        table_name="nutrition_plan_items",
    )
    with op.batch_alter_table("nutrition_plan_items") as batch_op:
        batch_op.drop_constraint("ck_nutrition_plan_items_diary_link", type_="check")
        batch_op.drop_constraint("ck_nutrition_plan_items_status", type_="check")
        batch_op.drop_constraint(
            "fk_nutrition_plan_items_diary_entry_id",
            type_="foreignkey",
        )
        batch_op.drop_column("action_request_fingerprint")
        batch_op.drop_column("action_idempotency_key")
        batch_op.drop_column("diary_entry_id")
        batch_op.drop_column("status")
