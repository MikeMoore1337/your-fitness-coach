"""Add opt-in contextual reminder template schedules.

Revision ID: 0074_contextual_templates
Revises: 0073_report_handoffs
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0074_contextual_templates"
down_revision: str | None = "0073_report_handoffs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds nullable reminder flags with a constant FALSE PostgreSQL fast default for existing "
    "rows and old writers, plus empty per-user template schedules; no populated table scan."
)


def upgrade() -> None:
    op.add_column(
        "notification_settings",
        sa.Column(
            "meal_reminders_enabled",
            sa.Boolean(),
            nullable=True,
            server_default=sa.text("FALSE"),
        ),
    )
    op.add_column(
        "notification_settings",
        sa.Column(
            "hydration_reminders_enabled",
            sa.Boolean(),
            nullable=True,
            server_default=sa.text("FALSE"),
        ),
    )
    op.add_column(
        "notification_settings",
        sa.Column(
            "movement_reminders_enabled",
            sa.Boolean(),
            nullable=True,
            server_default=sa.text("FALSE"),
        ),
    )
    op.create_table(
        "reminder_template_schedules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("template_key", sa.String(length=32), nullable=False),
        sa.Column("template_version", sa.String(length=16), nullable=False, server_default="v1"),
        sa.Column(
            "weekdays",
            sa.JSON(),
            nullable=False,
            server_default="[0,1,2,3,4,5,6]",
        ),
        sa.Column("schedule_times", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("window_start", sa.Time(), nullable=True),
        sa.Column("window_end", sa.Time(), nullable=True),
        sa.Column("interval_minutes", sa.Integer(), nullable=True),
        sa.Column("max_per_day", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("minimum_spacing_minutes", sa.Integer(), nullable=False, server_default="120"),
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
        sa.CheckConstraint(
            "template_key IN ('meal_logging', 'hydration', 'movement_break')",
            name="ck_reminder_template_schedules_key",
        ),
        sa.CheckConstraint(
            "template_version IN ('v1')",
            name="ck_reminder_template_schedules_version",
        ),
        sa.CheckConstraint(
            "max_per_day BETWEEN 1 AND 8",
            name="ck_reminder_template_schedules_max_per_day",
        ),
        sa.CheckConstraint(
            "minimum_spacing_minutes BETWEEN 15 AND 720",
            name="ck_reminder_template_schedules_spacing",
        ),
        sa.CheckConstraint(
            "interval_minutes IS NULL OR interval_minutes BETWEEN 30 AND 360",
            name="ck_reminder_template_schedules_interval",
        ),
        sa.CheckConstraint(
            "(window_start IS NULL AND window_end IS NULL) OR "
            "(window_start IS NOT NULL AND window_end IS NOT NULL AND window_start < window_end)",
            name="ck_reminder_template_schedules_window",
        ),
        sa.UniqueConstraint(
            "user_id",
            "template_key",
            name="uq_reminder_template_schedules_user_key",
        ),
    )
    op.create_index(
        "ix_reminder_template_schedules_user_id",
        "reminder_template_schedules",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reminder_template_schedules_user_id",
        table_name="reminder_template_schedules",
    )
    op.drop_table("reminder_template_schedules")
    op.drop_column("notification_settings", "movement_reminders_enabled")
    op.drop_column("notification_settings", "hydration_reminders_enabled")
    op.drop_column("notification_settings", "meal_reminders_enabled")
