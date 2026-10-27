"""Add versioned trainer check-in templates."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0127_check_in_templates"
down_revision: str | None = "0126_plan_source_constraint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds empty coach-owned check-in template, assignment, and response tables with bounded "
    "field snapshots; existing users and check-in rows are unchanged."
)


def upgrade() -> None:
    op.create_table(
        "coach_check_in_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "coach_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("cadence", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 128", name="ck_check_in_template_name"),
        sa.CheckConstraint(
            "cadence IN ('weekly', 'biweekly', 'monthly')",
            name="ck_check_in_template_cadence",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "coach_user_id",
            "idempotency_key",
            name="uq_check_in_template_coach_idempotency",
        ),
    )
    op.create_index(
        "ix_check_in_template_coach_active_updated",
        "coach_check_in_templates",
        ["coach_user_id", "is_active", "updated_at"],
    )

    op.create_table(
        "coach_check_in_template_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "template_id",
            sa.Integer(),
            sa.ForeignKey("coach_check_in_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("field_definitions", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_check_in_template_version_number"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "version", name="uq_check_in_template_version_number"),
        sa.UniqueConstraint(
            "template_id",
            "idempotency_key",
            name="uq_check_in_template_version_idempotency",
        ),
    )
    op.create_index(
        "ix_check_in_template_version_template_version",
        "coach_check_in_template_versions",
        ["template_id", "version"],
    )

    op.create_table(
        "coach_check_in_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "template_id",
            sa.Integer(),
            sa.ForeignKey("coach_check_in_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "template_version_id",
            sa.Integer(),
            sa.ForeignKey("coach_check_in_template_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
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
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("next_due_on", sa.Date(), nullable=False),
        sa.Column("last_response_at", sa.DateTime(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'revoked')",
            name="ck_check_in_assignment_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "template_id", "client_user_id", name="uq_check_in_assignment_template_client"
        ),
        sa.UniqueConstraint(
            "coach_user_id", "idempotency_key", name="uq_check_in_assignment_coach_idempotency"
        ),
    )
    op.create_index(
        "ix_check_in_assignment_coach_status",
        "coach_check_in_assignments",
        ["coach_user_id", "status"],
    )
    op.create_index(
        "ix_check_in_assignment_client_status",
        "coach_check_in_assignments",
        ["client_user_id", "status"],
    )

    op.create_table(
        "coach_check_in_responses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "assignment_id",
            sa.Integer(),
            sa.ForeignKey("coach_check_in_assignments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "template_id",
            sa.Integer(),
            sa.ForeignKey("coach_check_in_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "template_version_id",
            sa.Integer(),
            sa.ForeignKey("coach_check_in_template_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
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
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assignment_id", "due_on", name="uq_check_in_response_assignment_due"),
        sa.UniqueConstraint(
            "client_user_id", "idempotency_key", name="uq_check_in_response_client_idempotency"
        ),
    )
    op.create_index(
        "ix_check_in_response_client_submitted",
        "coach_check_in_responses",
        ["client_user_id", "submitted_at"],
    )
    op.create_index(
        "ix_check_in_response_coach_template",
        "coach_check_in_responses",
        ["coach_user_id", "template_id", "submitted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_check_in_response_coach_template", table_name="coach_check_in_responses")
    op.drop_index("ix_check_in_response_client_submitted", table_name="coach_check_in_responses")
    op.drop_table("coach_check_in_responses")
    op.drop_index("ix_check_in_assignment_client_status", table_name="coach_check_in_assignments")
    op.drop_index("ix_check_in_assignment_coach_status", table_name="coach_check_in_assignments")
    op.drop_table("coach_check_in_assignments")
    op.drop_index(
        "ix_check_in_template_version_template_version",
        table_name="coach_check_in_template_versions",
    )
    op.drop_table("coach_check_in_template_versions")
    op.drop_index(
        "ix_check_in_template_coach_active_updated",
        table_name="coach_check_in_templates",
    )
    op.drop_table("coach_check_in_templates")
