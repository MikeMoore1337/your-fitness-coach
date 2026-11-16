"""Add dated references to canonical nutrition targets."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0150_nutrition_date_overrides"
down_revision: str | None = "0149_nutrition_target_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = "Add an optional target scope and empty date override table."


def upgrade() -> None:
    op.add_column("nutrition_targets", sa.Column("target_scope", sa.String(16), nullable=True))
    op.create_table(
        "nutrition_target_date_overrides",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "target_id",
            sa.Integer(),
            sa.ForeignKey("nutrition_targets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_nutrition_date_override_request"),
    )
    op.create_index(
        "ix_nutrition_date_overrides_user_date",
        "nutrition_target_date_overrides",
        ["user_id", "target_date"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        if bind.execute(sa.text("SHOW transaction_isolation")).scalar_one() != "read committed":
            raise RuntimeError("Unsafe downgrade: PostgreSQL READ COMMITTED isolation is required")
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute("LOCK TABLE nutrition_target_date_overrides, nutrition_targets IN ACCESS EXCLUSIVE MODE")
    elif bind.dialect.name == "sqlite":
        op.execute("UPDATE nutrition_target_date_overrides SET id = id WHERE 0")
        if not getattr(bind.connection.driver_connection, "in_transaction", False):
            raise RuntimeError("Unsafe downgrade: date override locking requires a transaction")
    else:
        raise RuntimeError("Unsafe downgrade: date override locking is unsupported")
    if bind.execute(sa.text("SELECT 1 FROM nutrition_target_date_overrides LIMIT 1")).first():
        raise RuntimeError("Cannot discard nutrition date overrides")
    if bind.execute(sa.text("SELECT 1 FROM nutrition_targets WHERE target_scope IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("Cannot discard scoped nutrition targets")
    op.drop_index("ix_nutrition_date_overrides_user_date", table_name="nutrition_target_date_overrides")
    op.drop_table("nutrition_target_date_overrides")
    op.drop_column("nutrition_targets", "target_scope")
