"""Add nullable structured exercise prescriptions and workout lineage."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0093_advanced_prescriptions"
down_revision: str | None = "0092_coach_crm_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds only nullable scalar prescription, grouping, and lineage columns using direct ADD "
    "COLUMN operations. No rows are scanned or backfilled and no populated table is rewritten. "
    "Each addition takes only the brief PostgreSQL catalog lock; it adds no row-data work. The "
    "previous application revision ignores these nullable columns and remains compatible."
)


def upgrade() -> None:
    op.add_column(
        "program_template_exercises",
        sa.Column("group_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "program_template_exercises",
        sa.Column("group_kind", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "program_template_exercises",
        sa.Column("group_order", sa.Integer(), nullable=True),
    )
    op.add_column(
        "program_template_exercises",
        sa.Column("prescription", sa.JSON(), nullable=True),
    )
    op.add_column(
        "program_template_exercise_weeks",
        sa.Column("prescription", sa.JSON(), nullable=True),
    )
    op.add_column(
        "user_workout_exercises",
        sa.Column("source_template_exercise_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "user_workout_exercises",
        sa.Column("source_weekly_prescription_id", sa.Integer(), nullable=True),
    )
    op.add_column("user_workout_exercises", sa.Column("group_id", sa.Integer(), nullable=True))
    op.add_column(
        "user_workout_exercises",
        sa.Column("group_kind", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "user_workout_exercises",
        sa.Column("group_order", sa.Integer(), nullable=True),
    )
    op.add_column(
        "user_workout_exercises",
        sa.Column("prescription", sa.JSON(), nullable=True),
    )
    op.add_column(
        "user_workout_sets", sa.Column("planned_role", sa.String(length=16), nullable=True)
    )
    op.add_column("user_workout_sets", sa.Column("planned_group_id", sa.Integer(), nullable=True))
    op.add_column(
        "user_workout_sets",
        sa.Column("planned_group_kind", sa.String(length=16), nullable=True),
    )
    op.add_column("user_workout_sets", sa.Column("planned_position", sa.Integer(), nullable=True))
    op.add_column("user_workout_sets", sa.Column("planned_round", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_workout_sets", "planned_round")
    op.drop_column("user_workout_sets", "planned_position")
    op.drop_column("user_workout_sets", "planned_group_kind")
    op.drop_column("user_workout_sets", "planned_group_id")
    op.drop_column("user_workout_sets", "planned_role")
    op.drop_column("user_workout_exercises", "prescription")
    op.drop_column("user_workout_exercises", "group_order")
    op.drop_column("user_workout_exercises", "group_kind")
    op.drop_column("user_workout_exercises", "group_id")
    op.drop_column("user_workout_exercises", "source_weekly_prescription_id")
    op.drop_column("user_workout_exercises", "source_template_exercise_id")
    op.drop_column("program_template_exercise_weeks", "prescription")
    op.drop_column("program_template_exercises", "prescription")
    op.drop_column("program_template_exercises", "group_order")
    op.drop_column("program_template_exercises", "group_kind")
    op.drop_column("program_template_exercises", "group_id")
