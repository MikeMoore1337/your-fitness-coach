"""Add trainer-owned onboarding and communication workflow templates."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0129_coach_workflow_templates"
down_revision: str | None = "0128_coach_client_labels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds empty trainer-owned workflow template, version, assignment, and communication draft "
    "tables. Existing profiles, programs, check-ins, agenda rows, and notifications are unchanged."
)


def upgrade() -> None:
    op.create_table(
        "coach_workflow_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "coach_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('onboarding', 'communication')",
            name="ck_coach_workflow_template_kind",
        ),
        sa.CheckConstraint(
            "length(name) BETWEEN 1 AND 128",
            name="ck_coach_workflow_template_name",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "coach_user_id",
            "idempotency_key",
            name="uq_coach_workflow_template_coach_idempotency",
        ),
    )
    op.create_index(
        "ix_coach_workflow_template_coach_kind_updated",
        "coach_workflow_templates",
        ["coach_user_id", "kind", "updated_at"],
    )

    op.create_table(
        "coach_workflow_template_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "template_id",
            sa.Integer(),
            sa.ForeignKey("coach_workflow_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_coach_workflow_template_version_number"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "template_id",
            "version",
            name="uq_coach_workflow_template_version_number",
        ),
        sa.UniqueConstraint(
            "template_id",
            "idempotency_key",
            name="uq_coach_workflow_template_version_idempotency",
        ),
    )
    op.create_index(
        "ix_coach_workflow_template_version_template_version",
        "coach_workflow_template_versions",
        ["template_id", "version"],
    )

    op.create_table(
        "coach_workflow_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "template_id",
            sa.Integer(),
            sa.ForeignKey("coach_workflow_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "template_version_id",
            sa.Integer(),
            sa.ForeignKey("coach_workflow_template_versions.id", ondelete="RESTRICT"),
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
        sa.Column("status", sa.String(length=16), server_default="assigned", nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('assigned', 'completed', 'revoked')",
            name="ck_coach_workflow_assignment_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "coach_user_id",
            "idempotency_key",
            name="uq_coach_workflow_assignment_coach_idempotency",
        ),
    )
    op.create_index(
        "ix_coach_workflow_assignment_coach_template",
        "coach_workflow_assignments",
        ["coach_user_id", "template_id", "created_at"],
    )
    op.create_index(
        "ix_coach_workflow_assignment_client_created",
        "coach_workflow_assignments",
        ["client_user_id", "created_at"],
    )

    op.create_table(
        "coach_communication_drafts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "template_id",
            sa.Integer(),
            sa.ForeignKey("coach_workflow_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "template_version_id",
            sa.Integer(),
            sa.ForeignKey("coach_workflow_template_versions.id", ondelete="RESTRICT"),
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
        sa.Column("subject", sa.String(length=128), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column(
            "notification_id",
            sa.Integer(),
            sa.ForeignKey("notifications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("confirm_idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("confirm_request_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'confirmed')",
            name="ck_coach_communication_draft_status",
        ),
        sa.CheckConstraint(
            "length(trim(subject)) BETWEEN 1 AND 128",
            name="ck_coach_communication_draft_subject",
        ),
        sa.CheckConstraint(
            "length(trim(body)) BETWEEN 1 AND 4000",
            name="ck_coach_communication_draft_body",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "coach_user_id",
            "idempotency_key",
            name="uq_coach_communication_draft_coach_idempotency",
        ),
        sa.UniqueConstraint(
            "coach_user_id",
            "confirm_idempotency_key",
            name="uq_coach_communication_draft_confirm_idempotency",
        ),
    )
    op.create_index(
        "ix_coach_communication_draft_coach_client_updated",
        "coach_communication_drafts",
        ["coach_user_id", "client_user_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_coach_communication_draft_coach_client_updated",
        table_name="coach_communication_drafts",
    )
    op.drop_table("coach_communication_drafts")
    op.drop_index(
        "ix_coach_workflow_assignment_client_created",
        table_name="coach_workflow_assignments",
    )
    op.drop_index(
        "ix_coach_workflow_assignment_coach_template",
        table_name="coach_workflow_assignments",
    )
    op.drop_table("coach_workflow_assignments")
    op.drop_index(
        "ix_coach_workflow_template_version_template_version",
        table_name="coach_workflow_template_versions",
    )
    op.drop_table("coach_workflow_template_versions")
    op.drop_index(
        "ix_coach_workflow_template_coach_kind_updated",
        table_name="coach_workflow_templates",
    )
    op.drop_table("coach_workflow_templates")
