"""Add explicit authenticated trainer report handoffs.

Revision ID: 0073_report_handoffs
Revises: 0072_web_articles_lifecycle
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0073_report_handoffs"
down_revision: str | None = "0072_web_articles_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds an empty metadata-only handoff table; report payloads remain live and are not persisted."
)


def upgrade() -> None:
    op.create_table(
        "report_handoffs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "sender_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "trainer_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "relationship_id",
            sa.Integer(),
            sa.ForeignKey("coach_clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period", sa.String(length=32), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("report_contract_version", sa.String(length=64), nullable=False),
        sa.Column("included_section_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("report_revision", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "notification_id",
            sa.Integer(),
            sa.ForeignKey("notifications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("delivery_status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("delivery_attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_retry_idempotency_key", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "period IN ('days_1', 'days_7', 'days_30', 'days_90', 'days_365', "
            "'current_week', 'current_month', 'previous_month', 'custom')",
            name="ck_report_handoffs_period",
        ),
        sa.CheckConstraint(
            "period_end >= period_start",
            name="ck_report_handoffs_period_order",
        ),
        sa.CheckConstraint(
            "delivery_attempt >= 1",
            name="ck_report_handoffs_delivery_attempt",
        ),
        sa.CheckConstraint(
            "delivery_status IN ('delivered', 'pending', 'failed')",
            name="ck_report_handoffs_delivery_status",
        ),
        sa.UniqueConstraint(
            "sender_user_id",
            "idempotency_key",
            name="uq_report_handoffs_sender_idempotency",
        ),
        sa.UniqueConstraint(
            "sender_user_id",
            "trainer_user_id",
            "relationship_id",
            "period_start",
            "period_end",
            "report_contract_version",
            "report_revision",
            name="uq_report_handoffs_revision",
        ),
        sa.UniqueConstraint("notification_id", name="uq_report_handoffs_notification"),
    )
    op.create_index(
        "ix_report_handoffs_sender_user_id",
        "report_handoffs",
        ["sender_user_id"],
    )
    op.create_index(
        "ix_report_handoffs_trainer_user_id",
        "report_handoffs",
        ["trainer_user_id"],
    )
    op.create_index(
        "ix_report_handoffs_relationship_id",
        "report_handoffs",
        ["relationship_id"],
    )
    op.create_index(
        "ix_report_handoffs_notification_id",
        "report_handoffs",
        ["notification_id"],
    )
    op.create_index(
        "ix_report_handoffs_sender_created",
        "report_handoffs",
        ["sender_user_id", "created_at"],
    )
    op.create_index(
        "ix_report_handoffs_trainer_created",
        "report_handoffs",
        ["trainer_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_report_handoffs_trainer_created", table_name="report_handoffs")
    op.drop_index("ix_report_handoffs_sender_created", table_name="report_handoffs")
    op.drop_index("ix_report_handoffs_notification_id", table_name="report_handoffs")
    op.drop_index("ix_report_handoffs_relationship_id", table_name="report_handoffs")
    op.drop_index("ix_report_handoffs_trainer_user_id", table_name="report_handoffs")
    op.drop_index("ix_report_handoffs_sender_user_id", table_name="report_handoffs")
    op.drop_table("report_handoffs")
