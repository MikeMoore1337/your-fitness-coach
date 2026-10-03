"""Expand trainer task provenance and weekly check-in reviews."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0108_trainer_workspace_reviews"
down_revision: str | None = "0107_public_shares"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds four nullable task provenance columns with direct ADD COLUMN operations plus an empty "
    "owner-scoped trainer review table. Existing coach tasks remain readable while the follow-up "
    "backfill and constraint swaps run; no client facts are rewritten."
)


def upgrade() -> None:
    op.add_column("coach_tasks", sa.Column("kind", sa.String(length=32), nullable=True))
    op.add_column("coach_tasks", sa.Column("source_kind", sa.String(length=32), nullable=True))
    op.add_column("coach_tasks", sa.Column("source_id", sa.Integer(), nullable=True))
    op.add_column("coach_tasks", sa.Column("reason", sa.String(length=240), nullable=True))

    op.create_table(
        "coach_check_in_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "coach_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "check_in_id",
            sa.Integer(),
            sa.ForeignKey("weekly_check_ins.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "follow_up_task_id",
            sa.Integer(),
            sa.ForeignKey("coach_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="reviewed"),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('reviewed')", name="ck_coach_check_in_reviews_status"),
        sa.CheckConstraint(
            "response IS NULL OR length(response) <= 2000",
            name="ck_coach_check_in_reviews_response_length",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "coach_user_id",
            "check_in_id",
            name="uq_coach_check_in_reviews_coach_check_in",
        ),
    )
    op.create_index(
        "ix_coach_check_in_reviews_coach_status",
        "coach_check_in_reviews",
        ["coach_user_id", "status", "reviewed_at"],
        unique=False,
    )
    op.create_index(
        "ix_coach_check_in_reviews_client_check_in",
        "coach_check_in_reviews",
        ["client_user_id", "check_in_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_coach_check_in_reviews_client_check_in",
        table_name="coach_check_in_reviews",
    )
    op.drop_index(
        "ix_coach_check_in_reviews_coach_status",
        table_name="coach_check_in_reviews",
    )
    op.drop_table("coach_check_in_reviews")
    op.drop_column("coach_tasks", "reason")
    op.drop_column("coach_tasks", "source_id")
    op.drop_column("coach_tasks", "source_kind")
    op.drop_column("coach_tasks", "kind")
