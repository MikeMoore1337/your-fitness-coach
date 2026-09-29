"""Swap the program-revision lifecycle kind constraint safely online."""

from collections.abc import Sequence

from alembic import op

revision: str = "0100_program_revision_kind_ck"
down_revision: str | None = "0099_user_program_status_ck"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "constraint_swap"
online_rollout_notes = (
    "Replaces the program-revision change-kind CHECK with a NOT VALID constraint under a bounded "
    "lock timeout, then validates existing rows under a bounded statement timeout."
)
online_rollout_constraint_table = "program_revisions"
online_rollout_constraint_name = "ck_program_revisions_change_kind"
online_rollout_lock_timeout_seconds = 3
online_rollout_statement_timeout_seconds = 30


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE program_revisions DROP CONSTRAINT IF EXISTS "
            "ck_program_revisions_change_kind, ADD CONSTRAINT "
            "ck_program_revisions_change_kind CHECK (change_kind IN "
            "('assigned', 'program_archived', 'plan_updated', 'block_created', 'block_updated', "
            "'block_status_changed', 'program_lifecycle', 'program_restarted')) NOT VALID"
        )
        op.execute(
            "ALTER TABLE program_revisions VALIDATE CONSTRAINT ck_program_revisions_change_kind"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "ALTER TABLE program_revisions DROP CONSTRAINT IF EXISTS "
            "ck_program_revisions_change_kind, ADD CONSTRAINT "
            "ck_program_revisions_change_kind CHECK (change_kind IN "
            "('assigned', 'program_archived', 'plan_updated', 'block_created', 'block_updated', "
            "'block_status_changed')) NOT VALID"
        )
        op.execute(
            "ALTER TABLE program_revisions VALIDATE CONSTRAINT ck_program_revisions_change_kind"
        )
