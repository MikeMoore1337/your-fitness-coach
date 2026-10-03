"""Add instance-scoped lifecycle facts for workout recovery metrics."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0113_lifecycle_workout_instances"
down_revision: str | None = "0112_lifecycle_milestones"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds nullable server-owned workout/program identity and missed-at facts to the existing "
    "lifecycle ledger and builds lookup/idempotency indexes concurrently on PostgreSQL. Existing "
    "Stage 1 rows remain valid and no product payload is backfilled."
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.add_column(
            "lifecycle_milestones",
            sa.Column("workout_id", sa.Integer(), nullable=True),
            if_not_exists=True,
        )
        op.add_column(
            "lifecycle_milestones",
            sa.Column("program_id", sa.Integer(), nullable=True),
            if_not_exists=True,
        )
        op.add_column(
            "lifecycle_milestones",
            sa.Column("program_revision_number", sa.Integer(), nullable=True),
            if_not_exists=True,
        )
        op.add_column(
            "lifecycle_milestones",
            sa.Column("missed_at", sa.DateTime(), nullable=True),
            if_not_exists=True,
        )
        with op.get_context().autocommit_block():
            op.create_index(
                "ix_lifecycle_milestones_type_workout",
                "lifecycle_milestones",
                ["milestone_type", "workout_id"],
                if_not_exists=True,
                postgresql_concurrently=True,
            )
            op.create_index(
                "uq_lifecycle_milestones_user_type_workout",
                "lifecycle_milestones",
                ["user_id", "milestone_type", "workout_id"],
                unique=True,
                if_not_exists=True,
                postgresql_concurrently=True,
            )
    else:
        op.add_column(
            "lifecycle_milestones",
            sa.Column("workout_id", sa.Integer(), nullable=True),
        )
        op.add_column(
            "lifecycle_milestones",
            sa.Column("program_id", sa.Integer(), nullable=True),
        )
        op.add_column(
            "lifecycle_milestones",
            sa.Column("program_revision_number", sa.Integer(), nullable=True),
        )
        op.add_column(
            "lifecycle_milestones",
            sa.Column("missed_at", sa.DateTime(), nullable=True),
        )
        op.create_index(
            "ix_lifecycle_milestones_type_workout",
            "lifecycle_milestones",
            ["milestone_type", "workout_id"],
            if_not_exists=True,
            postgresql_concurrently=True,
        )
        op.create_index(
            "uq_lifecycle_milestones_user_type_workout",
            "lifecycle_milestones",
            ["user_id", "milestone_type", "workout_id"],
            unique=True,
            if_not_exists=True,
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.drop_index(
                "uq_lifecycle_milestones_user_type_workout",
                table_name="lifecycle_milestones",
                postgresql_concurrently=True,
                if_exists=True,
            )
            op.drop_index(
                "ix_lifecycle_milestones_type_workout",
                table_name="lifecycle_milestones",
                postgresql_concurrently=True,
                if_exists=True,
            )
    else:
        op.drop_index("uq_lifecycle_milestones_user_type_workout", table_name="lifecycle_milestones")
        op.drop_index("ix_lifecycle_milestones_type_workout", table_name="lifecycle_milestones")
    op.drop_column("lifecycle_milestones", "missed_at")
    op.drop_column("lifecycle_milestones", "program_revision_number")
    op.drop_column("lifecycle_milestones", "program_id")
    op.drop_column("lifecycle_milestones", "workout_id")
