"""Add private per-exercise setup memories."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0119_exercise_setup_memory"
down_revision: str | None = "0118_measurement_eligibility"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds an empty owner-scoped exercise setup memory table. Rows are private to the account, "
    "canonical exercise ids are unique per user, and account deletion/export handle the new domain."
)


def upgrade() -> None:
    op.create_table(
        "exercise_setup_memories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "exercise_id",
            sa.Integer(),
            sa.ForeignKey("exercises.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "length(body) BETWEEN 1 AND 240",
            name="ck_exercise_setup_memories_body_length",
        ),
        sa.CheckConstraint("version >= 1", name="ck_exercise_setup_memories_version_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "exercise_id",
            name="uq_exercise_setup_memories_user_exercise",
        ),
    )
    op.create_index("ix_exercise_setup_memories_user_id", "exercise_setup_memories", ["user_id"])
    op.create_index(
        "ix_exercise_setup_memories_exercise_id", "exercise_setup_memories", ["exercise_id"]
    )
    op.create_index(
        "ix_exercise_setup_memories_exercise_user",
        "exercise_setup_memories",
        ["exercise_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_exercise_setup_memories_exercise_user", table_name="exercise_setup_memories")
    op.drop_index("ix_exercise_setup_memories_exercise_id", table_name="exercise_setup_memories")
    op.drop_index("ix_exercise_setup_memories_user_id", table_name="exercise_setup_memories")
    op.drop_table("exercise_setup_memories")
