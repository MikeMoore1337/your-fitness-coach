"""Add versioned schedule bindings and references to nutrition targets."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0151_nutrition_schedule_rules"
down_revision: str | None = "0150_nutrition_date_overrides"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = (
    "Add empty versioned nutrition schedule tables without rewriting existing data."
)


def upgrade() -> None:
    op.create_table(
        "nutrition_schedule_bindings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "program_revision_id",
            sa.Integer(),
            sa.ForeignKey("program_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("effective_from", sa.Date(), nullable=False),
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
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_nutrition_binding_request"),
    )
    op.create_index(
        "ix_nutrition_bindings_user_date",
        "nutrition_schedule_bindings",
        ["user_id", "effective_from"],
    )
    op.create_table(
        "nutrition_target_schedule_rules",
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
        sa.Column(
            "program_id",
            sa.Integer(),
            sa.ForeignKey("user_programs.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("day_type", sa.String(16), nullable=False),
        sa.Column("week_type", sa.String(16), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("source_cycle_week", sa.Integer(), nullable=True),
        sa.Column("cycle_boundary", sa.Integer(), nullable=True),
        sa.Column("weekday", sa.Integer(), nullable=True),
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
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name="uq_nutrition_schedule_rule_request"
        ),
        sa.CheckConstraint(
            "scope IN ('template', 'future', 'recovery')", name="ck_nutrition_schedule_rule_scope"
        ),
        sa.CheckConstraint(
            "day_type IN ('training', 'rest', 'recovery')", name="ck_nutrition_schedule_day_type"
        ),
        sa.CheckConstraint(
            "week_type IS NULL OR week_type IN ('light', 'medium', 'heavy')",
            name="ck_nutrition_schedule_week_type",
        ),
    )
    op.create_index(
        "ix_nutrition_schedule_rules_user_date",
        "nutrition_target_schedule_rules",
        ["user_id", "effective_from"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        if bind.execute(sa.text("SHOW transaction_isolation")).scalar_one() != "read committed":
            raise RuntimeError("Unsafe downgrade: PostgreSQL READ COMMITTED isolation is required")
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute(
            "LOCK TABLE nutrition_target_schedule_rules, nutrition_schedule_bindings, nutrition_targets IN ACCESS EXCLUSIVE MODE"
        )
    elif bind.dialect.name == "sqlite":
        op.execute("UPDATE nutrition_schedule_bindings SET id = id WHERE 0")
        if not getattr(bind.connection.driver_connection, "in_transaction", False):
            raise RuntimeError(
                "Unsafe downgrade: nutrition schedule locking requires a transaction"
            )
    else:
        raise RuntimeError("Unsafe downgrade: nutrition schedule locking is unsupported")
    if bind.execute(sa.text("SELECT 1 FROM nutrition_schedule_bindings LIMIT 1")).first():
        raise RuntimeError("Cannot discard nutrition schedule bindings")
    if bind.execute(sa.text("SELECT 1 FROM nutrition_target_schedule_rules LIMIT 1")).first():
        raise RuntimeError("Cannot discard nutrition schedule rules")
    if bind.execute(
        sa.text("SELECT 1 FROM nutrition_targets WHERE target_scope = 'schedule' LIMIT 1")
    ).first():
        raise RuntimeError("Cannot discard scheduled nutrition targets")
    op.drop_index(
        "ix_nutrition_schedule_rules_user_date", table_name="nutrition_target_schedule_rules"
    )
    op.drop_table("nutrition_target_schedule_rules")
    op.drop_index("ix_nutrition_bindings_user_date", table_name="nutrition_schedule_bindings")
    op.drop_table("nutrition_schedule_bindings")
