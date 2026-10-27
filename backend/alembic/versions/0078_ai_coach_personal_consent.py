"""Store the current personal AI Coach consent decision per account.

Revision ID: 0078_ai_coach_personal_consent
Revises: 0077_periodized_templates
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0078_ai_coach_personal_consent"
down_revision: str | None = "0077_periodized_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = "Adds one bounded account-owned consent row; no prompt, answer or tool payload is stored."


def upgrade() -> None:
    op.create_table(
        "ai_coach_consents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="revoked"),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("consent_version", sa.String(length=64), nullable=False),
        sa.Column("provider_name", sa.String(length=64), nullable=False),
        sa.Column("provider_policy_revision", sa.String(length=64), nullable=False),
        sa.Column("consent_source", sa.String(length=64), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_ai_coach_consents_user_id"),
        sa.CheckConstraint(
            "status IN ('granted', 'revoked')",
            name="ck_ai_coach_consents_status",
        ),
    )
    op.create_index("ix_ai_coach_consents_user_id", "ai_coach_consents", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_coach_consents_user_id", table_name="ai_coach_consents")
    op.drop_table("ai_coach_consents")
