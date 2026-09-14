from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.base import Base


class AiCoachConsent(Base):
    """Current account decision for the separately gated personal AI Coach route."""

    __tablename__ = "ai_coach_consents"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_ai_coach_consents_user_id"),
        CheckConstraint(
            "status IN ('granted', 'revoked')",
            name="ck_ai_coach_consents_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="revoked")
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_policy_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    consent_source: Mapped[str] = mapped_column(String(64), nullable=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=now_msk_naive, onupdate=now_msk_naive
    )


class AiCoachMemoryConsent(Base):
    """Separate user decision for the optional continuity memory layer."""

    __tablename__ = "ai_coach_memory_consents"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_ai_coach_memory_consents_user_id"),
        CheckConstraint(
            "status IN ('enabled', 'paused', 'revoked')",
            name="ck_ai_coach_memory_consents_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="revoked")
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(64), nullable=False)
    consent_source: Mapped[str] = mapped_column(String(64), nullable=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=now_msk_naive, onupdate=now_msk_naive
    )


class AiCoachMemory(Base):
    """One bounded, account-owned and explicitly confirmed memory item."""

    __tablename__ = "ai_coach_memories"
    __table_args__ = (
        CheckConstraint(
            "category IN ('preferred_explanation_style', 'ai_interaction_preferences', "
            "'stable_non_medical_preferences', 'explicit_ai_context')",
            name="ck_ai_coach_memories_category",
        ),
        CheckConstraint(
            "source_kind IN ('explicit_user', 'confirmed_candidate')",
            name="ck_ai_coach_memories_source_kind",
        ),
        CheckConstraint(
            "confidence IN ('explicit', 'confirmed')",
            name="ck_ai_coach_memories_confidence",
        ),
        CheckConstraint(
            "status IN ('active', 'superseded', 'conflicted', 'deleted')",
            name="ck_ai_coach_memories_status",
        ),
        Index(
            "ix_ai_coach_memories_user_status_category",
            "user_id",
            "status",
            "category",
        ),
        Index("ix_ai_coach_memories_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    value_text: Mapped[str] = mapped_column(String(240), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(24), nullable=False, default="explicit_user")
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="explicit")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    source_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=now_msk_naive, onupdate=now_msk_naive
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AiCoachConversation(Base):
    """Account-owned conversation shell; separate from durable AI Coach memory."""

    __tablename__ = "ai_coach_conversations"
    __table_args__ = (
        Index(
            "ix_ai_coach_conversations_user_updated",
            "user_id",
            "updated_at",
        ),
        CheckConstraint(
            "title IS NULL OR length(title) BETWEEN 1 AND 80",
            name="ck_ai_coach_conversations_title_length",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=now_msk_naive, onupdate=now_msk_naive
    )


class AiCoachConversationMessage(Base):
    """Bounded user/assistant text and safe display metadata for one conversation."""

    __tablename__ = "ai_coach_conversation_messages"
    __table_args__ = (
        Index(
            "ix_ai_coach_conversation_messages_conversation_created",
            "conversation_id",
            "created_at",
            "id",
        ),
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="ck_ai_coach_conversation_messages_role",
        ),
        CheckConstraint(
            "status IN ('complete', 'failed')",
            name="ck_ai_coach_conversation_messages_status",
        ),
        CheckConstraint(
            "length(content) BETWEEN 1 AND 1600",
            name="ck_ai_coach_conversation_messages_content_length",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("ai_coach_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="complete")
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    safety_category: Mapped[str] = mapped_column(
        String(48), nullable=False, default="clear", server_default="clear"
    )
    failure_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    citations: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False, default=list)
    limitations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)


__all__ = [
    "AiCoachConsent",
    "AiCoachConversation",
    "AiCoachConversationMessage",
    "AiCoachMemory",
    "AiCoachMemoryConsent",
]
