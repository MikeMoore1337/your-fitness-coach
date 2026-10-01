"""Add nullable source metadata for approximate diary nutrition."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0102_approximate_nutrition_source"
down_revision: str | None = "0101_ai_coach_exercise_refs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds one nullable source scalar with no default; existing diary rows remain readable and "
    "the application derives a legacy source until new writes populate it."
)


def upgrade() -> None:
    op.add_column(
        "food_diary_entries",
        sa.Column("nutrition_source", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("food_diary_entries", "nutrition_source")
