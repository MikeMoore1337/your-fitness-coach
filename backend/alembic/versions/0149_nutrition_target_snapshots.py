"""Keep completed-day target references without changing existing rows."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0149_nutrition_target_snapshots"
down_revision: str | None = "0148_import_self_assignment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = "Add an empty completed-day target reference table without backfilling data."


def upgrade() -> None:
    op.create_table(
        "nutrition_target_day_snapshots",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("diary_date", sa.Date(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("captured_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["nutrition_targets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("user_id", "diary_date"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        if bind.execute(sa.text("SHOW transaction_isolation")).scalar_one() != "read committed":
            raise RuntimeError("Unsafe downgrade: PostgreSQL READ COMMITTED isolation is required")
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute("LOCK TABLE nutrition_target_day_snapshots IN ACCESS EXCLUSIVE MODE")
    elif bind.dialect.name == "sqlite":
        op.execute("UPDATE nutrition_target_day_snapshots SET user_id = user_id WHERE 0")
        if not getattr(bind.connection.driver_connection, "in_transaction", False):
            raise RuntimeError("Unsafe downgrade: target snapshot locking requires a transaction")
    else:
        raise RuntimeError("Unsafe downgrade: target snapshot locking is unsupported")
    if bind.execute(sa.text("SELECT 1 FROM nutrition_target_day_snapshots LIMIT 1")).first():
        raise RuntimeError("Cannot discard completed-day nutrition target snapshots")
    op.drop_table("nutrition_target_day_snapshots")
