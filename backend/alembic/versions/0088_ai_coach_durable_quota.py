"""Persist AI Coach windows and idempotent provider reservations."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0088_ai_coach_durable_quota"
down_revision: str | None = "0087_ai_coach_long_chat_messages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds content-free account/service quota windows and short-lived reservations. Extends chat "
    "messages with processing/idempotency metadata; existing conversation content is preserved."
)


def upgrade() -> None:
    with op.batch_alter_table("ai_coach_conversation_messages") as batch:
        batch.add_column(sa.Column("data_class", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("prompt_version", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("processing_started_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("rate_limit_scope", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("rate_limit_retry_after_seconds", sa.Integer(), nullable=True))
        batch.drop_constraint("ck_ai_coach_conversation_messages_status", type_="check")
        batch.create_check_constraint(
            "ck_ai_coach_conversation_messages_status",
            "status IN ('processing', 'complete', 'failed')",
        )

    op.create_table(
        "ai_coach_quota_windows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("quota_kind", sa.String(length=16), nullable=False),
        sa.Column("subject_key", sa.String(length=128), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("window_started_at", sa.DateTime(), nullable=False),
        sa.Column("reset_at", sa.DateTime(), nullable=False),
        sa.Column("limit_value", sa.Integer(), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "quota_kind IN ('user', 'service')",
            name="ck_ai_coach_quota_windows_kind",
        ),
        sa.CheckConstraint("limit_value >= 1", name="ck_ai_coach_quota_windows_limit"),
        sa.CheckConstraint("used_count >= 0", name="ck_ai_coach_quota_windows_used"),
        sa.UniqueConstraint(
            "quota_kind",
            "subject_key",
            name="uq_ai_coach_quota_windows_kind_subject",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_coach_quota_windows_user_id",
        "ai_coach_quota_windows",
        ["user_id"],
    )
    op.create_index(
        "ix_ai_coach_quota_windows_user_reset",
        "ai_coach_quota_windows",
        ["user_id", "reset_at"],
    )

    op.create_table(
        "ai_coach_quota_reservations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(length=128), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "user_window_id",
            sa.Integer(),
            sa.ForeignKey("ai_coach_quota_windows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "service_window_id",
            sa.Integer(),
            sa.ForeignKey("ai_coach_quota_windows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finalized_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('reserved', 'consumed', 'released', 'expired')",
            name="ck_ai_coach_quota_reservations_status",
        ),
        sa.UniqueConstraint(
            "request_key",
            name="uq_ai_coach_quota_reservations_request_key",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_coach_quota_reservations_user_id",
        "ai_coach_quota_reservations",
        ["user_id"],
    )
    op.create_index(
        "ix_ai_coach_quota_reservations_window_status_expiry",
        "ai_coach_quota_reservations",
        ["service_window_id", "status", "expires_at"],
    )
    op.create_index(
        "uq_ai_coach_conversation_messages_user_request",
        "ai_coach_conversation_messages",
        ["conversation_id", "request_id"],
        unique=True,
        postgresql_where=sa.text("role = 'user' AND request_id IS NOT NULL"),
        sqlite_where=sa.text("role = 'user' AND request_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_ai_coach_conversation_messages_user_request",
        table_name="ai_coach_conversation_messages",
    )
    op.drop_index(
        "ix_ai_coach_quota_reservations_window_status_expiry",
        table_name="ai_coach_quota_reservations",
    )
    op.drop_index(
        "ix_ai_coach_quota_reservations_user_id",
        table_name="ai_coach_quota_reservations",
    )
    op.drop_table("ai_coach_quota_reservations")
    op.drop_index(
        "ix_ai_coach_quota_windows_user_reset",
        table_name="ai_coach_quota_windows",
    )
    op.drop_index(
        "ix_ai_coach_quota_windows_user_id",
        table_name="ai_coach_quota_windows",
    )
    op.drop_table("ai_coach_quota_windows")
    with op.batch_alter_table("ai_coach_conversation_messages") as batch:
        batch.drop_constraint("ck_ai_coach_conversation_messages_status", type_="check")
        batch.create_check_constraint(
            "ck_ai_coach_conversation_messages_status",
            "status IN ('complete', 'failed')",
        )
        batch.drop_column("processing_started_at")
        batch.drop_column("prompt_version")
        batch.drop_column("data_class")
        batch.drop_column("rate_limit_retry_after_seconds")
        batch.drop_column("rate_limit_scope")
