"""Add explicit program lifecycle states and restart lineage."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0098_program_lifecycle"
down_revision: str | None = "0097_program_import_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds nullable restart lineage and widens lifecycle check constraints. Existing program and "
    "revision rows keep their current values; no workout history is rewritten."
)


def upgrade() -> None:
    with op.batch_alter_table("user_programs") as batch_op:
        batch_op.drop_constraint("ck_user_programs_status", type_="check")
        batch_op.create_check_constraint(
            "ck_user_programs_status",
            "status IN ('scheduled', 'active', 'paused', 'completed', 'terminated', 'archived')",
        )
        batch_op.add_column(sa.Column("restarted_from_program_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_user_programs_restarted_from_program_id",
            "user_programs",
            ["restarted_from_program_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_user_programs_restarted_from_program_id", ["restarted_from_program_id"]
        )

    with op.batch_alter_table("program_revisions") as batch_op:
        batch_op.drop_constraint("ck_program_revisions_change_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_program_revisions_change_kind",
            "change_kind IN ('assigned', 'program_archived', 'plan_updated', 'block_created', "
            "'block_updated', 'block_status_changed', 'program_lifecycle', 'program_restarted')",
        )


def downgrade() -> None:
    op.execute(
        "UPDATE user_programs SET status = 'archived' WHERE status IN ('paused', 'terminated')"
    )
    op.execute(
        "UPDATE program_revisions SET change_kind = 'program_archived' "
        "WHERE change_kind IN ('program_lifecycle', 'program_restarted')"
    )
    with op.batch_alter_table("program_revisions") as batch_op:
        batch_op.drop_constraint("ck_program_revisions_change_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_program_revisions_change_kind",
            "change_kind IN ('assigned', 'program_archived', 'plan_updated', 'block_created', "
            "'block_updated', 'block_status_changed')",
        )
    with op.batch_alter_table("user_programs") as batch_op:
        batch_op.drop_index("ix_user_programs_restarted_from_program_id")
        batch_op.drop_constraint("fk_user_programs_restarted_from_program_id", type_="foreignkey")
        batch_op.drop_column("restarted_from_program_id")
        batch_op.drop_constraint("ck_user_programs_status", type_="check")
        batch_op.create_check_constraint(
            "ck_user_programs_status",
            "status IN ('scheduled', 'active', 'completed', 'archived')",
        )
