"""Keep the explicit day type selected for a manual date."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0152_nutrition_override_day_type"
down_revision: str | None = "0151_nutrition_schedule_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = "Add an optional explicit day type without changing existing overrides."


def upgrade() -> None:
    op.add_column(
        "nutrition_target_date_overrides", sa.Column("day_type", sa.String(16), nullable=True)
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        if bind.execute(sa.text("SHOW transaction_isolation")).scalar_one() != "read committed":
            raise RuntimeError("Unsafe downgrade: PostgreSQL READ COMMITTED isolation is required")
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute("LOCK TABLE nutrition_target_date_overrides IN ACCESS EXCLUSIVE MODE")
    elif bind.dialect.name == "sqlite":
        op.execute("UPDATE nutrition_target_date_overrides SET id = id WHERE 0")
        if not getattr(bind.connection.driver_connection, "in_transaction", False):
            raise RuntimeError("Unsafe downgrade: override day type locking requires a transaction")
    else:
        raise RuntimeError("Unsafe downgrade: override day type locking is unsupported")
    if bind.execute(
        sa.text("SELECT 1 FROM nutrition_target_date_overrides WHERE day_type IS NOT NULL LIMIT 1")
    ).first():
        raise RuntimeError("Cannot discard explicit nutrition day types")
    op.drop_column("nutrition_target_date_overrides", "day_type")
