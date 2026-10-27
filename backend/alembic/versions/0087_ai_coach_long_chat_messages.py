"""Expand persisted conversational input without rewriting the deployed message constraint."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0087_ai_coach_long_chat_messages"
down_revision: str | None = "0086_ai_coach_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds a nullable overflow text column for account-owned chat input above the historical "
    "1600-character inline bound. The old column and constraint remain intact for an online rollout; "
    "the application enforces the 2000-character request limit."
)


def upgrade() -> None:
    op.add_column(
        "ai_coach_conversation_messages",
        sa.Column("content_overflow", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_coach_conversation_messages", "content_overflow")
