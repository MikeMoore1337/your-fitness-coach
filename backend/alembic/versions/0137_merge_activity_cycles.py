"""Converge activity completion and program cycle migration histories."""

revision = "0137_merge_activity_cycles"
down_revision = ("0134_workout_completed_at_utc", "0136_program_week_unbounded")
branch_labels = None
depends_on = None
online_rollout_phase = "expand"
online_rollout_notes = "Merge independent histories without schema or data changes."


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
