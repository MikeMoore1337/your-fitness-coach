"""Persist validated canonical exercise references in AI Coach messages."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0101_ai_coach_exercise_refs"
down_revision: str | None = "0100_program_revision_kind_ck"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_coach_conversation_messages",
        sa.Column(
            "exercise_references",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("ai_coach_conversation_messages", "exercise_references")
