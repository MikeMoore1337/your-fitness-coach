"""Store account-owned AI Coach conversations separately from durable memory."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0086_ai_coach_conversations"
down_revision: str | None = "0085_first_touch_attribution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Creates bounded account-owned conversation and message tables. Existing AI Coach consent, "
    "memory and period-report records are retained; no backfill or provider call is required."
)


def upgrade() -> None:
    op.create_table(
        "ai_coach_conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey(
                "users.id",
                name="fk_ai_coach_conversations_user_id_users",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "title IS NULL OR length(title) BETWEEN 1 AND 80",
            name="ck_ai_coach_conversations_title_length",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_coach_conversations_user_id",
        "ai_coach_conversations",
        ["user_id"],
    )
    op.create_index(
        "ix_ai_coach_conversations_user_updated",
        "ai_coach_conversations",
        ["user_id", "updated_at"],
    )

    op.create_table(
        "ai_coach_conversation_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "conversation_id",
            sa.Integer(),
            sa.ForeignKey(
                "ai_coach_conversations.id",
                name="fk_ai_coach_conversation_messages_conversation_id_conversations",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("safety_category", sa.String(length=48), nullable=False),
        sa.Column("failure_category", sa.String(length=32), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "role IN ('user', 'assistant')",
            name="ck_ai_coach_conversation_messages_role",
        ),
        sa.CheckConstraint(
            "status IN ('complete', 'failed')",
            name="ck_ai_coach_conversation_messages_status",
        ),
        sa.CheckConstraint(
            "length(content) BETWEEN 1 AND 1600",
            name="ck_ai_coach_conversation_messages_content_length",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_coach_conversation_messages_conversation_id",
        "ai_coach_conversation_messages",
        ["conversation_id"],
    )
    op.create_index(
        "ix_ai_coach_conversation_messages_conversation_created",
        "ai_coach_conversation_messages",
        ["conversation_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_coach_conversation_messages_conversation_created",
        table_name="ai_coach_conversation_messages",
    )
    op.drop_index(
        "ix_ai_coach_conversation_messages_conversation_id",
        table_name="ai_coach_conversation_messages",
    )
    op.drop_table("ai_coach_conversation_messages")
    op.drop_index(
        "ix_ai_coach_conversations_user_updated",
        table_name="ai_coach_conversations",
    )
    op.drop_index(
        "ix_ai_coach_conversations_user_id",
        table_name="ai_coach_conversations",
    )
    op.drop_table("ai_coach_conversations")
