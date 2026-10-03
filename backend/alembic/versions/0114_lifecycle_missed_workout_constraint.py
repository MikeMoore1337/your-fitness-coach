"""Allow instance-scoped missed workout facts in the lifecycle ledger."""

from collections.abc import Sequence

from alembic import op

revision: str = "0114_lifecycle_missed_workout_constraint"
down_revision: str | None = "0113_lifecycle_workout_instances"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "constraint_swap"
online_rollout_notes = (
    "Replaces the lifecycle milestone type CHECK under bounded PostgreSQL lock and statement "
    "timeouts. The replacement adds workout_missed and validates nullable instance identifiers."
)
online_rollout_constraint_table = "lifecycle_milestones"
online_rollout_constraint_name = "ck_lifecycle_milestones_type"
online_rollout_lock_timeout_seconds = 3
online_rollout_statement_timeout_seconds = 30


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE lifecycle_milestones DROP CONSTRAINT IF EXISTS "
            "ck_lifecycle_milestones_type, ADD CONSTRAINT ck_lifecycle_milestones_type "
            "CHECK (milestone_type IN ('onboarding_completed', 'program_activated', "
            "'workout_started', 'workout_completed', 'workout_missed', "
            "'nutrition_entry_confirmed', 'weekly_review_completed', "
            "'recovery_action_confirmed', 'progress_next_action_completed') AND "
            "(workout_id IS NULL OR workout_id >= 1) AND "
            "(program_id IS NULL OR program_id >= 1) AND "
            "(program_revision_number IS NULL OR program_revision_number >= 0)) NOT VALID"
        )
        op.execute("ALTER TABLE lifecycle_milestones VALIDATE CONSTRAINT ck_lifecycle_milestones_type")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE lifecycle_milestones DROP CONSTRAINT IF EXISTS "
            "ck_lifecycle_milestones_type, ADD CONSTRAINT ck_lifecycle_milestones_type "
            "CHECK (milestone_type IN ('onboarding_completed', 'program_activated', "
            "'workout_started', 'workout_completed', 'nutrition_entry_confirmed', "
            "'weekly_review_completed', 'recovery_action_confirmed', "
            "'progress_next_action_completed')) NOT VALID"
        )
        op.execute("ALTER TABLE lifecycle_milestones VALIDATE CONSTRAINT ck_lifecycle_milestones_type")
