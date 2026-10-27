"""Add account-owned Web Push subscriptions and per-device delivery state.

Revision ID: 0075_web_push_delivery
Revises: 0074_contextual_templates
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0075_web_push_delivery"
down_revision: str | None = "0074_contextual_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds account-owned browser capability records and independent per-subscription delivery "
    "state. Existing notification rows are unchanged; Web Push remains disabled until VAPID "
    "configuration and a later owner rollout decision."
)


def upgrade() -> None:
    op.create_table(
        "web_push_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("endpoint", sa.String(length=2048), nullable=False),
        sa.Column("endpoint_hash", sa.String(length=64), nullable=False),
        sa.Column("p256dh", sa.String(length=128), nullable=False),
        sa.Column("auth", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=128), nullable=True),
        sa.UniqueConstraint("endpoint_hash", name="uq_web_push_subscriptions_endpoint_hash"),
    )
    op.create_index(
        "ix_web_push_subscriptions_user_id",
        "web_push_subscriptions",
        ["user_id"],
    )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "notification_id",
            sa.Integer(),
            sa.ForeignKey("notifications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            sa.Integer(),
            sa.ForeignKey("web_push_subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(length=32), nullable=False, server_default="web_push"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "notification_id",
            "subscription_id",
            name="uq_notification_deliveries_notification_subscription",
        ),
        sa.CheckConstraint(
            "channel = 'web_push'",
            name="ck_notification_deliveries_web_push_channel",
        ),
    )
    op.create_index(
        "ix_notification_deliveries_notification_id",
        "notification_deliveries",
        ["notification_id"],
    )
    op.create_index(
        "ix_notification_deliveries_subscription_id",
        "notification_deliveries",
        ["subscription_id"],
    )
    op.create_index(
        "ix_notification_deliveries_next_attempt_at",
        "notification_deliveries",
        ["next_attempt_at"],
    )
    op.create_index(
        "ix_notification_deliveries_due_queue",
        "notification_deliveries",
        ["status", "next_attempt_at", "id"],
        postgresql_where=sa.text("status = 'queued'"),
        sqlite_where=sa.text("status = 'queued'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_deliveries_due_queue",
        table_name="notification_deliveries",
    )
    op.drop_index(
        "ix_notification_deliveries_next_attempt_at",
        table_name="notification_deliveries",
    )
    op.drop_index(
        "ix_notification_deliveries_subscription_id",
        table_name="notification_deliveries",
    )
    op.drop_index(
        "ix_notification_deliveries_notification_id",
        table_name="notification_deliveries",
    )
    op.drop_table("notification_deliveries")
    op.drop_index(
        "ix_web_push_subscriptions_user_id",
        table_name="web_push_subscriptions",
    )
    op.drop_table("web_push_subscriptions")
