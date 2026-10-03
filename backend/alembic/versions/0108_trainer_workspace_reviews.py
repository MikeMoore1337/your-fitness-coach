"""Add bounded trainer task provenance and weekly check-in reviews."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0108_trainer_workspace_reviews"
down_revision: str | None = "0107_public_shares"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds nullable task provenance and an owner-scoped trainer review table. Existing coach tasks "
    "remain valid with the default kind 'other'; no client facts are rewritten."
)


def upgrade() -> None:
    with op.batch_alter_table("coach_tasks") as batch_op:
        batch_op.add_column(
            sa.Column("kind", sa.String(length=32), nullable=False, server_default="other")
        )
        batch_op.add_column(sa.Column("source_kind", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("source_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("reason", sa.String(length=240), nullable=True))
        batch_op.create_check_constraint(
            "ck_coach_tasks_kind",
            "kind IN ('review_check_in', 'update_program', 'contact_client', "
            "'review_technique', 'schedule_follow_up', 'other')",
        )
        batch_op.create_check_constraint(
            "ck_coach_tasks_source_kind",
            "source_kind IS NULL OR source_kind IN "
            "('weekly_check_in', 'workout', 'program', 'client', 'manual')",
        )

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
    with op.batch_alter_table("coach_tasks") as batch_op:
        batch_op.drop_constraint("ck_coach_tasks_source_kind", type_="check")
        batch_op.drop_constraint("ck_coach_tasks_kind", type_="check")
        batch_op.drop_column("reason")
        batch_op.drop_column("source_id")
        batch_op.drop_column("source_kind")
        batch_op.drop_column("kind")
