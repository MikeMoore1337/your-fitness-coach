"""Add optional side-specific workout facts without rewriting existing sets."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0143_workout_set_sides"
down_revision: str | None = "0142_workout_history_import"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = "Add nullable execution metadata and an empty side facts table."


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
    op.add_column(
        "user_workout_sets",
        sa.Column(
            "execution_mode",
            sa.String(16),
            sa.CheckConstraint(
                "execution_mode IS NULL OR execution_mode IN ('bilateral', 'per_side', 'alternating')",
                name="ck_user_workout_sets_execution_mode",
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "user_workout_sets",
        sa.Column(
            "first_side",
            sa.String(5),
            sa.CheckConstraint(
                "first_side IS NULL OR first_side IN ('left', 'right')",
                name="ck_user_workout_sets_first_side",
            ),
            nullable=True,
        ),
    )
    op.create_table(
        "user_workout_set_sides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "workout_set_id",
            sa.Integer(),
            sa.ForeignKey("user_workout_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("side", sa.String(5), nullable=False),
        sa.Column("actual_reps", sa.Integer(), nullable=True),
        sa.Column("actual_weight", sa.Numeric(10, 2), nullable=True),
        sa.Column("rir", sa.String(2), nullable=True),
        sa.Column("reached_failure", sa.Boolean(), nullable=True),
        sa.Column("is_completed", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("workout_set_id", "side", name="uq_user_workout_set_sides_set_side"),
        sa.CheckConstraint("side IN ('left', 'right')", name="ck_user_workout_set_sides_side"),
        sa.CheckConstraint(
            "actual_reps IS NULL OR actual_reps >= 0", name="ck_user_workout_set_sides_reps"
        ),
        sa.CheckConstraint(
            "actual_weight IS NULL OR actual_weight >= 0", name="ck_user_workout_set_sides_weight"
        ),
        sa.CheckConstraint(
            "rir IS NULL OR rir IN ('0', '1', '2', '3', '4+')",
            name="ck_user_workout_set_sides_rir",
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")
        op.execute("SET LOCAL statement_timeout = '30s'")
        op.execute("LOCK TABLE user_workout_sets, user_workout_set_sides IN ACCESS EXCLUSIVE MODE")
    if (
        bind.execute(sa.text("SELECT 1 FROM user_workout_set_sides LIMIT 1")).first()
        or bind.execute(
            sa.text(
                "SELECT 1 FROM user_workout_sets "
                "WHERE execution_mode IS NOT NULL OR first_side IS NOT NULL LIMIT 1"
            )
        ).first()
    ):
        raise RuntimeError("Unsafe downgrade: side-specific workout facts exist")
    op.drop_table("user_workout_set_sides")
    op.drop_column("user_workout_sets", "first_side")
    op.drop_column("user_workout_sets", "execution_mode")
