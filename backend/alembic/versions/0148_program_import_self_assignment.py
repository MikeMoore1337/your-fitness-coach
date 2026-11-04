"""Record self-assignment results for idempotent program import recovery."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0148_import_self_assignment"
down_revision: str | None = "0147_session_rotation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = "Add nullable import assignment identity without rewriting existing rows."


def upgrade() -> None:
    op.add_column(
        "program_imports", sa.Column("self_assigned_program_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "program_imports", sa.Column("self_assignment_request_hash", sa.String(64), nullable=True)
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        if bind.exec_driver_sql("SHOW transaction_isolation").scalar_one() != "read committed":
            raise RuntimeError("Unsafe downgrade: import assignments require READ COMMITTED")
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute("LOCK TABLE program_imports IN ACCESS EXCLUSIVE MODE")
    elif bind.dialect.name == "sqlite":
        op.execute("UPDATE program_imports SET id = id WHERE 0")
        if not getattr(bind.connection.driver_connection, "in_transaction", False):
            raise RuntimeError("Unsafe downgrade: import assignment locking requires a transaction")
    else:
        raise RuntimeError("Unsafe downgrade: import assignment locking is unsupported")
    if bind.execute(
        sa.text(
            "SELECT 1 FROM program_imports WHERE self_assigned_program_id IS NOT NULL "
            "OR self_assignment_request_hash IS NOT NULL LIMIT 1"
        )
    ).first():
        raise RuntimeError("Cannot discard program import assignment identities")
    op.drop_column("program_imports", "self_assignment_request_hash")
    op.drop_column("program_imports", "self_assigned_program_id")
