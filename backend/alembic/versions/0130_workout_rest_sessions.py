"""Add trusted, idempotent workout-rest measurements (additive)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0130_workout_rest_sessions"
down_revision: str | None = "0129_coach_workflow_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = "Add empty rest measurements; preserve all historical workouts and prescriptions."


def upgrade() -> None:
    op.create_table(
        "workout_rest_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("workout_id", sa.Integer(), sa.ForeignKey("user_workouts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_set_id", sa.Integer(), sa.ForeignKey("user_workout_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("planned_seconds", sa.Integer(), nullable=False),
        sa.Column("adjusted_seconds", sa.Integer(), nullable=False),
        sa.Column("measured_seconds", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source", sa.String(20), nullable=True),
        sa.Column("quality", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("source_set_id", name="uq_workout_rest_source_set"),
        sa.CheckConstraint("planned_seconds > 0", name="ck_workout_rest_plan_positive"),
        sa.CheckConstraint("adjusted_seconds > 0", name="ck_workout_rest_adjusted_positive"),
        sa.CheckConstraint("version >= 1", name="ck_workout_rest_version_positive"),
        sa.CheckConstraint("status IN ('running','completed','skipped','interrupted','unknown')", name="ck_workout_rest_status"),
    )
    op.create_index("ix_workout_rest_sessions_user_id", "workout_rest_sessions", ["user_id"])
    op.create_index("ix_workout_rest_sessions_workout_id", "workout_rest_sessions", ["workout_id"])
    op.create_table(
        "workout_rest_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("workout_rest_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mutation_id", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(128), nullable=False),
        sa.Column("applied_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("session_id", "mutation_id", name="uq_workout_rest_action_mutation"),
    )


def downgrade() -> None:
    op.drop_table("workout_rest_actions")
    op.drop_index("ix_workout_rest_sessions_workout_id", table_name="workout_rest_sessions")
    op.drop_index("ix_workout_rest_sessions_user_id", table_name="workout_rest_sessions")
    op.drop_table("workout_rest_sessions")
