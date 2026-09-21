"""Add additive structured exercise prescriptions and workout lineage."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0093_advanced_prescriptions"
down_revision: str | None = "0092_coach_crm_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_GROUP_CHECK = (
    "(group_id IS NULL AND group_kind IS NULL AND group_order IS NULL) OR "
    "(group_id IS NOT NULL AND group_kind IN "
    "('sequence', 'superset', 'rest_pause', 'myo_reps', 'cluster', 'drop_chain', 'circuit') "
    "AND group_order IS NOT NULL AND group_order >= 1)"
)


def upgrade() -> None:
    with op.batch_alter_table("program_template_exercises") as batch_op:
        batch_op.add_column(sa.Column("group_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("group_kind", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("group_order", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("prescription", sa.JSON(), nullable=True))
        batch_op.create_check_constraint("ck_program_template_exercises_group", _GROUP_CHECK)

    with op.batch_alter_table("program_template_exercise_weeks") as batch_op:
        batch_op.add_column(sa.Column("prescription", sa.JSON(), nullable=True))

    with op.batch_alter_table("user_workout_exercises") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source_template_exercise_id",
                sa.Integer(),
                sa.ForeignKey(
                    "program_template_exercises.id",
                    name="fk_user_workout_exercises_source_template_exercise_id",
                    ondelete="SET NULL",
                ),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "source_weekly_prescription_id",
                sa.Integer(),
                sa.ForeignKey(
                    "program_template_exercise_weeks.id",
                    name="fk_user_workout_exercises_source_weekly_prescription_id",
                    ondelete="SET NULL",
                ),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("group_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("group_kind", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("group_order", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("prescription", sa.JSON(), nullable=True))
        batch_op.create_check_constraint("ck_user_workout_exercises_group", _GROUP_CHECK)

    op.create_index(
        "ix_user_workout_exercises_source_template_exercise_id",
        "user_workout_exercises",
        ["source_template_exercise_id"],
    )
    op.create_index(
        "ix_user_workout_exercises_source_weekly_prescription_id",
        "user_workout_exercises",
        ["source_weekly_prescription_id"],
    )

    with op.batch_alter_table("user_workout_sets") as batch_op:
        batch_op.add_column(sa.Column("planned_role", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("planned_group_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("planned_group_kind", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("planned_position", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("planned_round", sa.Integer(), nullable=True))

    with op.batch_alter_table("program_revisions") as batch_op:
        batch_op.drop_constraint("ck_program_revisions_change_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_program_revisions_change_kind",
            "change_kind IN "
            "('assigned', 'program_archived', 'plan_updated', 'block_created', "
            "'block_updated', 'block_status_changed', 'exercise_replaced', "
            "'prescription_updated')",
        )


def downgrade() -> None:
    with op.batch_alter_table("program_revisions") as batch_op:
        batch_op.drop_constraint("ck_program_revisions_change_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_program_revisions_change_kind",
            "change_kind IN "
            "('assigned', 'program_archived', 'plan_updated', 'block_created', "
            "'block_updated', 'block_status_changed')",
        )

    with op.batch_alter_table("user_workout_sets") as batch_op:
        batch_op.drop_column("planned_round")
        batch_op.drop_column("planned_position")
        batch_op.drop_column("planned_group_kind")
        batch_op.drop_column("planned_group_id")
        batch_op.drop_column("planned_role")

    op.drop_index(
        "ix_user_workout_exercises_source_template_exercise_id",
        table_name="user_workout_exercises",
    )
    op.drop_index(
        "ix_user_workout_exercises_source_weekly_prescription_id",
        table_name="user_workout_exercises",
    )
    with op.batch_alter_table("user_workout_exercises") as batch_op:
        batch_op.drop_constraint("ck_user_workout_exercises_group", type_="check")
        batch_op.drop_column("prescription")
        batch_op.drop_column("group_order")
        batch_op.drop_column("group_kind")
        batch_op.drop_column("group_id")
        batch_op.drop_column("source_weekly_prescription_id")
        batch_op.drop_column("source_template_exercise_id")

    with op.batch_alter_table("program_template_exercise_weeks") as batch_op:
        batch_op.drop_column("prescription")

    with op.batch_alter_table("program_template_exercises") as batch_op:
        batch_op.drop_constraint("ck_program_template_exercises_group", type_="check")
        batch_op.drop_column("prescription")
        batch_op.drop_column("group_order")
        batch_op.drop_column("group_kind")
        batch_op.drop_column("group_id")
