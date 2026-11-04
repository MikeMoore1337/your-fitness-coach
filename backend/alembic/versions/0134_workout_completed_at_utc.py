"""Record unambiguous completion instants for new workouts."""

import sqlalchemy as sa

from alembic import op

revision = "0134_workout_completed_at_utc"
down_revision = "0133_profile_height_numeric"
branch_labels = None
depends_on = None
online_rollout_phase = "expand"
online_rollout_notes = "Nullable UTC completion instant; existing timestamps remain unchanged."


def upgrade():
    op.add_column("user_workouts", sa.Column("completed_at_utc", sa.DateTime(), nullable=True))


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # A repeatable snapshot can predate the lock and hide committed writes.
        if bind.execute(sa.text("SHOW transaction_isolation")).scalar_one() != "read committed":
            raise RuntimeError("Unsafe downgrade: PostgreSQL READ COMMITTED isolation is required")
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute("LOCK TABLE user_workouts IN ACCESS EXCLUSIVE MODE")
    elif bind.dialect.name == "sqlite":
        op.execute("UPDATE user_workouts SET id = id WHERE 0")
        if not getattr(bind.connection.driver_connection, "in_transaction", False):
            raise RuntimeError(
                "Unsafe downgrade: workout completion locking requires a transaction"
            )
    else:
        raise RuntimeError("Unsafe downgrade: workout completion locking is unsupported")
    if bind.execute(
        sa.text("SELECT 1 FROM user_workouts WHERE completed_at_utc IS NOT NULL LIMIT 1")
    ).first():
        raise RuntimeError("Cannot discard recorded UTC workout completion instants")
    op.drop_column("user_workouts", "completed_at_utc")
