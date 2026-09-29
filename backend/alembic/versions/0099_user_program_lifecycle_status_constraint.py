"""Swap the user-program lifecycle status constraint safely online."""

from collections.abc import Sequence

from alembic import op

revision: str = "0099_user_program_lifecycle_status_constraint"
down_revision: str | None = "0098_program_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "constraint_swap"
online_rollout_notes = (
    "Replaces the user-program status CHECK with a NOT VALID constraint under a bounded lock "
    "timeout, then validates existing rows under a bounded statement timeout."
)
online_rollout_constraint_table = "user_programs"
online_rollout_constraint_name = "ck_user_programs_status"
online_rollout_lock_timeout_seconds = 3
online_rollout_statement_timeout_seconds = 30


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE user_programs DROP CONSTRAINT IF EXISTS ck_user_programs_status, "
            "ADD CONSTRAINT ck_user_programs_status CHECK (status IN "
            "('scheduled', 'active', 'paused', 'completed', 'terminated', 'archived')) NOT VALID"
        )
        op.execute("ALTER TABLE user_programs VALIDATE CONSTRAINT ck_user_programs_status")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE user_programs DROP CONSTRAINT IF EXISTS ck_user_programs_status, "
            "ADD CONSTRAINT ck_user_programs_status CHECK (status IN "
            "('scheduled', 'active', 'completed', 'archived')) NOT VALID"
        )
        op.execute("ALTER TABLE user_programs VALIDATE CONSTRAINT ck_user_programs_status")
