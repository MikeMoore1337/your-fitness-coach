"""Add trainer CRM core operational entities."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0092_coach_crm_core"
down_revision: str | None = "0091_body_measurement_custom"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds coach-owned business sessions, bounded weekly series, package ledger, manual payment "
    "records and trainer tasks. Session times are stored as naive UTC plus an IANA timezone."
)


def upgrade() -> None:
    with op.batch_alter_table("coach_clients") as batch_op:
        batch_op.add_column(
            sa.Column(
                "operational_status",
                sa.String(length=16),
                server_default="active",
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "ck_coach_clients_operational_status",
            "operational_status IN ('active', 'paused', 'archived')",
        )

    op.create_table(
        "coach_packages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "coach_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("counts_sessions", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("included_sessions", sa.Integer(), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("state", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "counts_sessions = 0 OR included_sessions IS NOT NULL",
            name="ck_coach_packages_count_requires_total",
        ),
        sa.CheckConstraint(
            "included_sessions IS NULL OR included_sessions BETWEEN 1 AND 1000",
            name="ck_coach_packages_included_sessions",
        ),
        sa.CheckConstraint(
            "state IN ('active', 'finished', 'cancelled')",
            name="ck_coach_packages_state",
        ),
        sa.CheckConstraint(
            "expires_on IS NULL OR starts_on IS NULL OR expires_on >= starts_on",
            name="ck_coach_packages_date_order",
        ),
        sa.UniqueConstraint(
            "coach_user_id",
            "idempotency_key",
            name="uq_coach_packages_coach_idempotency",
        ),
        sa.PrimaryKeyConstraint("id", name="coach_packages_pkey"),
    )
    op.create_index(
        "ix_coach_packages_coach_client_state",
        "coach_packages",
        ["coach_user_id", "client_user_id", "state"],
    )

    op.create_table(
        "coach_session_series",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "coach_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "package_id",
            sa.Integer(),
            sa.ForeignKey("coach_packages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("recurrence_kind", sa.String(length=16), server_default="weekly", nullable=False),
        sa.Column("weekdays", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("recurrence_end_date", sa.Date(), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("location", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("recurrence_kind = 'weekly'", name="ck_coach_series_recurrence_kind"),
        sa.CheckConstraint(
            "duration_minutes BETWEEN 15 AND 480",
            name="ck_coach_series_duration_minutes",
        ),
        sa.CheckConstraint(
            "occurrence_count IS NULL OR occurrence_count BETWEEN 1 AND 52",
            name="ck_coach_series_occurrence_count",
        ),
        sa.CheckConstraint(
            "recurrence_end_date IS NULL OR recurrence_end_date >= start_date",
            name="ck_coach_series_date_order",
        ),
        sa.CheckConstraint("format IN ('gym', 'online', 'other')", name="ck_coach_series_format"),
        sa.UniqueConstraint(
            "coach_user_id",
            "idempotency_key",
            name="uq_coach_session_series_coach_idempotency",
        ),
        sa.PrimaryKeyConstraint("id", name="coach_session_series_pkey"),
    )
    op.create_index(
        "ix_coach_session_series_coach_status",
        "coach_session_series",
        ["coach_user_id", "status", "start_date"],
    )

    op.create_table(
        "coach_business_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "coach_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "series_id",
            sa.Integer(),
            sa.ForeignKey("coach_session_series.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "package_id",
            sa.Integer(),
            sa.ForeignKey("coach_packages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_workout_id",
            sa.Integer(),
            sa.ForeignKey("user_workouts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("occurrence_key", sa.String(length=32), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("starts_at_utc", sa.DateTime(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("location", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="scheduled", nullable=False),
        sa.Column("private_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "duration_minutes BETWEEN 15 AND 480",
            name="ck_coach_business_sessions_duration_minutes",
        ),
        sa.CheckConstraint(
            "status IN ('scheduled', 'completed', 'cancelled', 'no_show')",
            name="ck_coach_business_sessions_status",
        ),
        sa.CheckConstraint(
            "format IN ('gym', 'online', 'other')",
            name="ck_coach_business_sessions_format",
        ),
        sa.CheckConstraint(
            "private_note IS NULL OR length(private_note) <= 2000",
            name="ck_coach_business_sessions_private_note_length",
        ),
        sa.UniqueConstraint(
            "series_id", "occurrence_key", name="uq_coach_business_sessions_series_occurrence"
        ),
        sa.UniqueConstraint(
            "coach_user_id", "idempotency_key", name="uq_coach_business_sessions_coach_idempotency"
        ),
        sa.PrimaryKeyConstraint("id", name="coach_business_sessions_pkey"),
    )
    op.create_index(
        "ix_coach_business_sessions_coach_start_status",
        "coach_business_sessions",
        ["coach_user_id", "starts_at_utc", "status"],
    )
    op.create_index(
        "ix_coach_business_sessions_client_start_status",
        "coach_business_sessions",
        ["client_user_id", "starts_at_utc", "status"],
    )

    op.create_table(
        "coach_package_ledger",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "package_id",
            sa.Integer(),
            sa.ForeignKey("coach_packages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("coach_business_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("entry_type", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "entry_type IN ('charge', 'reversal')",
            name="ck_coach_package_ledger_entry_type",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_coach_package_ledger_quantity"),
        sa.UniqueConstraint("idempotency_key", name="uq_coach_package_ledger_idempotency"),
        sa.PrimaryKeyConstraint("id", name="coach_package_ledger_pkey"),
    )
    op.create_index(
        "ix_coach_package_ledger_package_created",
        "coach_package_ledger",
        ["package_id", "created_at", "id"],
    )

    op.create_table(
        "coach_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "coach_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "package_id",
            sa.Integer(),
            sa.ForeignKey("coach_packages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("expected_amount_minor", sa.Integer(), nullable=False),
        sa.Column("paid_amount_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=True),
        sa.Column("method", sa.String(length=32), nullable=True),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="expected", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('expected', 'partial', 'paid', 'cancelled')",
            name="ck_coach_payments_status",
        ),
        sa.CheckConstraint("expected_amount_minor > 0", name="ck_coach_payments_expected_amount"),
        sa.CheckConstraint(
            "paid_amount_minor >= 0 AND paid_amount_minor <= expected_amount_minor",
            name="ck_coach_payments_paid_amount",
        ),
        sa.UniqueConstraint(
            "coach_user_id", "idempotency_key", name="uq_coach_payments_coach_idempotency"
        ),
        sa.PrimaryKeyConstraint("id", name="coach_payments_pkey"),
    )
    op.create_index(
        "ix_coach_payments_coach_client_date",
        "coach_payments",
        ["coach_user_id", "client_user_id", "payment_date"],
    )

    op.create_table(
        "coach_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "coach_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("due_at_utc", sa.DateTime(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("reopened_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("state IN ('open', 'completed')", name="ck_coach_tasks_state"),
        sa.CheckConstraint("length(trim(title)) BETWEEN 1 AND 240", name="ck_coach_tasks_title"),
        sa.UniqueConstraint(
            "coach_user_id", "idempotency_key", name="uq_coach_tasks_coach_idempotency"
        ),
        sa.PrimaryKeyConstraint("id", name="coach_tasks_pkey"),
    )
    op.create_index(
        "ix_coach_tasks_coach_state_due",
        "coach_tasks",
        ["coach_user_id", "state", "due_at_utc"],
    )
    op.create_index("ix_coach_tasks_client_due", "coach_tasks", ["client_user_id", "due_at_utc"])


def downgrade() -> None:
    op.drop_index("ix_coach_tasks_client_due", table_name="coach_tasks")
    op.drop_index("ix_coach_tasks_coach_state_due", table_name="coach_tasks")
    op.drop_table("coach_tasks")
    op.drop_index("ix_coach_payments_coach_client_date", table_name="coach_payments")
    op.drop_table("coach_payments")
    op.drop_index("ix_coach_package_ledger_package_created", table_name="coach_package_ledger")
    op.drop_table("coach_package_ledger")
    op.drop_index(
        "ix_coach_business_sessions_client_start_status",
        table_name="coach_business_sessions",
    )
    op.drop_index(
        "ix_coach_business_sessions_coach_start_status",
        table_name="coach_business_sessions",
    )
    op.drop_table("coach_business_sessions")
    op.drop_index("ix_coach_session_series_coach_status", table_name="coach_session_series")
    op.drop_table("coach_session_series")
    op.drop_index("ix_coach_packages_coach_client_state", table_name="coach_packages")
    op.drop_table("coach_packages")
    with op.batch_alter_table("coach_clients") as batch_op:
        batch_op.drop_constraint("ck_coach_clients_operational_status", type_="check")
        batch_op.drop_column("operational_status")
