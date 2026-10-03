"""Add privacy-safe server-confirmed lifecycle milestone evidence."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0112_lifecycle_milestones"
down_revision: str | None = "0111_source_kind_check"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Creates an empty account-scoped milestone ledger with server-only writes. The ledger stores "
    "no raw product payloads or personal facts and is deleted with its owning account."
)


def upgrade() -> None:
    op.create_table(
        "lifecycle_milestones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("milestone_type", sa.String(length=48), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("surface", sa.String(length=16), nullable=False, server_default="server"),
        sa.Column(
            "server_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "authoritative_outcome_status",
            sa.String(length=16),
            nullable=False,
            server_default="confirmed",
        ),
        sa.CheckConstraint(
            "milestone_type IN ("
            "'onboarding_completed', 'program_activated', 'workout_started', "
            "'workout_completed', 'nutrition_entry_confirmed', "
            "'weekly_review_completed', 'recovery_action_confirmed', "
            "'progress_next_action_completed'"
            ")",
            name="ck_lifecycle_milestones_type",
        ),
        sa.CheckConstraint("schema_version >= 1", name="ck_lifecycle_milestones_schema_version"),
        sa.CheckConstraint("surface IN ('server')", name="ck_lifecycle_milestones_surface"),
        sa.CheckConstraint(
            "authoritative_outcome_status IN ('confirmed')",
            name="ck_lifecycle_milestones_outcome_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "milestone_type",
            "occurred_at",
            name="uq_lifecycle_milestones_user_type_occurred",
        ),
    )
    op.create_index(
        "ix_lifecycle_milestones_user_occurred",
        "lifecycle_milestones",
        ["user_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_lifecycle_milestones_type_occurred",
        "lifecycle_milestones",
        ["milestone_type", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_lifecycle_milestones_type_occurred", table_name="lifecycle_milestones")
    op.drop_index("ix_lifecycle_milestones_user_occurred", table_name="lifecycle_milestones")
    op.drop_table("lifecycle_milestones")
