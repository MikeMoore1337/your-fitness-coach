"""Add private notes for a specific workout exercise occurrence."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0139_workout_exercise_notes"
down_revision: str | None = "0138_equipment_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = "Add private exercise notes and their idempotent mutation records."


def upgrade() -> None:
    op.create_table(
        "workout_exercise_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "workout_id",
            sa.Integer(),
            sa.ForeignKey("user_workouts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workout_exercise_id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("context_key", sa.String(64), nullable=False),
        sa.Column("source_template_exercise_id", sa.Integer(), nullable=True),
        sa.Column("plan_revision_number", sa.Integer(), nullable=True),
        sa.Column("week_type", sa.String(8), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("workout_id", "context_key", name="uq_workout_exercise_notes_context"),
        sa.CheckConstraint("version >= 1", name="ck_workout_exercise_notes_version"),
        sa.CheckConstraint(
            "body IS NULL OR length(body) <= 500", name="ck_workout_exercise_notes_body_length"
        ),
    )
    op.create_index(
        "ix_workout_exercise_notes_workout_id", "workout_exercise_notes", ["workout_id"]
    )
    op.create_table(
        "workout_exercise_note_mutations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "note_id",
            sa.Integer(),
            sa.ForeignKey("workout_exercise_notes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("mutation_id", sa.String(64), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("applied_version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "mutation_id", name="uq_workout_exercise_note_mutation"),
    )
    op.create_index(
        "ix_workout_exercise_note_mutations_note_id", "workout_exercise_note_mutations", ["note_id"]
    )


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT 1 FROM workout_exercise_notes LIMIT 1")).first():
        raise RuntimeError("Unsafe downgrade: exercise notes exist; use a forward fix")
    op.drop_table("workout_exercise_note_mutations")
    op.drop_table("workout_exercise_notes")
