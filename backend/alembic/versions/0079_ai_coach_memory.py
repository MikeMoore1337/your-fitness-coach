"""Add the bounded, consented AI Coach continuity memory domain.

Revision ID: 0079_ai_coach_memory
Revises: 0078_ai_coach_personal_consent
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0079_ai_coach_memory"
down_revision: str | None = "0078_ai_coach_personal_consent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds account-owned consent and bounded structured memory items; no raw prompt, answer "
    "or conversation history is stored."
)


def upgrade() -> None:
    op.create_table(
        "ai_coach_memory_consents",
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
        sa.Column("consent_source", sa.String(length=64), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=True),
        sa.Column("paused_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_ai_coach_memory_consents_user_id"),
        sa.CheckConstraint(
            "status IN ('enabled', 'paused', 'revoked')",
            name="ck_ai_coach_memory_consents_status",
        ),
    )
    op.create_index("ix_ai_coach_memory_consents_user_id", "ai_coach_memory_consents", ["user_id"])
    op.create_table(
        "ai_coach_memories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(length=48), nullable=False),
        sa.Column("value_text", sa.String(length=240), nullable=False),
        sa.Column(
            "source_kind", sa.String(length=24), nullable=False, server_default="explicit_user"
        ),
        sa.Column("confidence", sa.String(length=16), nullable=False, server_default="explicit"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("source_ref", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "category IN ('preferred_explanation_style', 'ai_interaction_preferences', "
            "'stable_non_medical_preferences', 'explicit_ai_context')",
            name="ck_ai_coach_memories_category",
        ),
        sa.CheckConstraint(
            "source_kind IN ('explicit_user', 'confirmed_candidate')",
            name="ck_ai_coach_memories_source_kind",
        ),
        sa.CheckConstraint(
            "confidence IN ('explicit', 'confirmed')",
            name="ck_ai_coach_memories_confidence",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'superseded', 'conflicted', 'deleted')",
            name="ck_ai_coach_memories_status",
        ),
    )
    op.create_index("ix_ai_coach_memories_user_id", "ai_coach_memories", ["user_id"])
    op.create_index(
        "ix_ai_coach_memories_user_status_category",
        "ai_coach_memories",
        ["user_id", "status", "category"],
    )
    op.create_index("ix_ai_coach_memories_expires_at", "ai_coach_memories", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_coach_memories_expires_at", table_name="ai_coach_memories")
    op.drop_index("ix_ai_coach_memories_user_status_category", table_name="ai_coach_memories")
    op.drop_index("ix_ai_coach_memories_user_id", table_name="ai_coach_memories")
    op.drop_table("ai_coach_memories")
    op.drop_index("ix_ai_coach_memory_consents_user_id", table_name="ai_coach_memory_consents")
    op.drop_table("ai_coach_memory_consents")
