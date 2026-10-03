"""Add server-owned nutrition repeat preview state and replay counters."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0115_nutrition_repeat_preview"
down_revision: str | None = "0114_missed_workout_constraint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Creates an empty owner-scoped repeat preview table and adds nullable operational linkage "
    "and replay counters to existing copy operations. No diary rows or private nutrition facts "
    "are backfilled; new indexes are built only on the empty table."
)


def upgrade() -> None:
    op.create_table(
        "food_diary_repeat_previews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("copy_scope", sa.String(length=16), nullable=False),
        sa.Column("source_entry_id", sa.Integer(), nullable=True),
        sa.Column("source_date", sa.Date(), nullable=False),
        sa.Column("source_meal_type", sa.String(length=16), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("target_meal_type", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("persistence_failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "copy_scope IN ('product', 'meal', 'day')",
            name="ck_food_diary_repeat_previews_scope",
        ),
        sa.CheckConstraint(
            "source_meal_type IS NULL OR "
            "source_meal_type IN ('breakfast', 'lunch', 'dinner', 'snacks')",
            name="ck_food_diary_repeat_previews_source_meal",
        ),
        sa.CheckConstraint(
            "target_meal_type IS NULL OR "
            "target_meal_type IN ('breakfast', 'lunch', 'dinner', 'snacks')",
            name="ck_food_diary_repeat_previews_target_meal",
        ),
        sa.CheckConstraint(
            "persistence_failure_count >= 0",
            name="ck_food_diary_repeat_previews_failure_count",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_food_diary_repeat_previews_token"),
    )
    op.create_index(
        "ix_food_diary_repeat_previews_user_created",
        "food_diary_repeat_previews",
        ["user_id", "created_at", "id"],
        unique=False,
    )
    op.add_column(
        "food_diary_copy_operations",
        sa.Column("preview_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "food_diary_copy_operations",
        sa.Column("replay_count", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("food_diary_copy_operations", "replay_count")
    op.drop_column("food_diary_copy_operations", "preview_id")
    op.drop_index(
        "ix_food_diary_repeat_previews_user_created",
        table_name="food_diary_repeat_previews",
    )
    op.drop_table("food_diary_repeat_previews")
