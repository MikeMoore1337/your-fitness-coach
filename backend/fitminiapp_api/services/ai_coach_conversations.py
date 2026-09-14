"""Account-owned storage helpers for AI Coach conversation history."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from fitminiapp_api.ai_coach.contracts import AiCoachCitation, AiCoachOutcome
from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.models.ai_coach import (
    AiCoachConversation,
    AiCoachConversationMessage,
)
from fitminiapp_api.schemas.ai_coach import (
    AiCoachConversationMessageResponse,
    AiCoachConversationResponse,
    AiCoachConversationSummaryResponse,
)

MAX_CONVERSATIONS_PER_USER = 50
MAX_MESSAGES_PER_CONVERSATION = 100
LEGACY_INLINE_CONTENT_LIMIT = 1_600


def _message_content(message: AiCoachConversationMessage) -> str:
    return message.content_overflow or message.content


def get_owned_conversation(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
) -> AiCoachConversation | None:
    return (
        db.query(AiCoachConversation)
        .filter(
            AiCoachConversation.id == conversation_id,
            AiCoachConversation.user_id == user_id,
        )
        .one_or_none()
    )


def create_conversation(db: Session, *, user_id: int) -> AiCoachConversation:
    existing_count = (
        db.query(func.count(AiCoachConversation.id))
        .filter(AiCoachConversation.user_id == user_id)
        .scalar()
        or 0
    )
    if existing_count >= MAX_CONVERSATIONS_PER_USER:
        raise ValueError("Достигнут лимит разговоров AI Coach; удалите старый разговор")
    conversation = AiCoachConversation(user_id=user_id, title=None)
    db.add(conversation)
    db.flush()
    return conversation


def list_conversations(
    db: Session,
    *,
    user_id: int,
) -> tuple[AiCoachConversationSummaryResponse, ...]:
    rows = (
        db.query(
            AiCoachConversation,
            func.count(AiCoachConversationMessage.id).label("message_count"),
        )
        .outerjoin(
            AiCoachConversationMessage,
            AiCoachConversationMessage.conversation_id == AiCoachConversation.id,
        )
        .filter(AiCoachConversation.user_id == user_id)
        .group_by(AiCoachConversation.id)
        .order_by(
            AiCoachConversation.updated_at.desc(),
            AiCoachConversation.id.desc(),
        )
        .limit(MAX_CONVERSATIONS_PER_USER)
        .all()
    )
    return tuple(
        AiCoachConversationSummaryResponse(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=int(message_count),
        )
        for conversation, message_count in rows
    )


def list_messages(
    db: Session,
    *,
    conversation_id: int,
) -> list[AiCoachConversationMessage]:
    return (
        db.query(AiCoachConversationMessage)
        .filter(AiCoachConversationMessage.conversation_id == conversation_id)
        .order_by(
            AiCoachConversationMessage.created_at.asc(),
            AiCoachConversationMessage.id.asc(),
        )
        .limit(MAX_MESSAGES_PER_CONVERSATION)
        .all()
    )


def get_conversation_message(
    db: Session,
    *,
    conversation_id: int,
    message_id: int,
) -> AiCoachConversationMessage | None:
    return (
        db.query(AiCoachConversationMessage)
        .filter(
            AiCoachConversationMessage.id == message_id,
            AiCoachConversationMessage.conversation_id == conversation_id,
        )
        .one_or_none()
    )


def conversation_response(
    db: Session,
    conversation: AiCoachConversation,
) -> AiCoachConversationResponse:
    return AiCoachConversationResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=tuple(
            serialize_message(message)
            for message in list_messages(db, conversation_id=conversation.id)
        ),
    )


def history_turns(
    db: Session,
    *,
    conversation_id: int,
) -> tuple[dict[str, str], ...]:
    """Return only the latest complete user/assistant turns for provider context."""

    messages = [
        message
        for message in list_messages(db, conversation_id=conversation_id)
        if message.status == "complete"
        and message.role in {"user", "assistant"}
        and not (
            message.role == "assistant" and message.outcome == AiCoachOutcome.INVALID_OUTPUT.value
        )
    ]
    return tuple(
        {"role": message.role, "content": _message_content(message)} for message in messages[-8:]
    )


def add_user_message(
    db: Session,
    *,
    conversation: AiCoachConversation,
    content: str,
) -> AiCoachConversationMessage:
    inline_content = content[:LEGACY_INLINE_CONTENT_LIMIT]
    overflow_content = content if len(content) > LEGACY_INLINE_CONTENT_LIMIT else None
    message = AiCoachConversationMessage(
        conversation_id=conversation.id,
        role="user",
        content=inline_content,
        content_overflow=overflow_content,
        status="complete",
        outcome=None,
        safety_category="clear",
        failure_category=None,
        request_id=None,
        citations=[],
        limitations=[],
    )
    db.add(message)
    conversation.updated_at = now_msk_naive()
    db.flush()
    trim_messages(db, conversation_id=conversation.id)
    return message


def mark_user_message_result(
    message: AiCoachConversationMessage,
    *,
    outcome: AiCoachOutcome,
    safety_category: str,
    failure_category: str | None,
    request_id: str | None,
    limitations: Iterable[str] = (),
) -> None:
    message.status = (
        "complete"
        if outcome
        in {
            AiCoachOutcome.ANSWER,
            AiCoachOutcome.SAFETY_REFUSAL,
            AiCoachOutcome.CONSENT_REQUIRED,
            AiCoachOutcome.INSUFFICIENT_DATA,
        }
        else "failed"
    )
    message.outcome = outcome.value
    message.safety_category = safety_category
    message.failure_category = failure_category
    message.request_id = request_id
    message.limitations = list(limitations)


def add_assistant_message(
    db: Session,
    *,
    conversation: AiCoachConversation,
    content: str,
    outcome: AiCoachOutcome,
    safety_category: str,
    failure_category: str | None,
    request_id: str | None,
    citations: Iterable[AiCoachCitation] = (),
    limitations: Iterable[str] = (),
) -> AiCoachConversationMessage:
    message = AiCoachConversationMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=content,
        content_overflow=None,
        status="complete",
        outcome=outcome.value,
        safety_category=safety_category,
        failure_category=failure_category,
        request_id=request_id,
        citations=[citation.model_dump(mode="json") for citation in citations],
        limitations=list(limitations),
    )
    db.add(message)
    conversation.updated_at = now_msk_naive()
    db.flush()
    trim_messages(db, conversation_id=conversation.id)
    return message


def update_title_from_message(
    conversation: AiCoachConversation,
    *,
    content: str,
) -> None:
    if conversation.title:
        return
    title = " ".join(content.split()).strip()
    conversation.title = title[:80] or "Новый разговор"


def trim_messages(db: Session, *, conversation_id: int) -> None:
    ids = [
        row.id
        for row in (
            db.query(AiCoachConversationMessage.id)
            .filter(AiCoachConversationMessage.conversation_id == conversation_id)
            .order_by(
                AiCoachConversationMessage.created_at.desc(),
                AiCoachConversationMessage.id.desc(),
            )
            .offset(MAX_MESSAGES_PER_CONVERSATION)
            .all()
        )
    ]
    if ids:
        db.query(AiCoachConversationMessage).filter(AiCoachConversationMessage.id.in_(ids)).delete(
            synchronize_session=False
        )


def serialize_message(
    message: AiCoachConversationMessage,
) -> AiCoachConversationMessageResponse:
    citations: list[AiCoachCitation] = []
    for raw_citation in message.citations if isinstance(message.citations, list) else []:
        if not isinstance(raw_citation, dict):
            continue
        try:
            citations.append(AiCoachCitation.model_validate(raw_citation))
        except ValueError:
            continue
    limitations = (
        tuple(item for item in message.limitations if isinstance(item, str))
        if isinstance(message.limitations, list)
        else ()
    )
    outcome = None
    if message.outcome:
        try:
            outcome = AiCoachOutcome(message.outcome)
        except ValueError:
            outcome = None
    return AiCoachConversationMessageResponse(
        id=message.id,
        role=message.role,
        content=_message_content(message),
        status=message.status,
        outcome=outcome,
        safety_category=message.safety_category,
        failure_category=message.failure_category,
        citations=tuple(citations),
        limitations=limitations,
        created_at=message.created_at,
    )


__all__ = [
    "MAX_CONVERSATIONS_PER_USER",
    "MAX_MESSAGES_PER_CONVERSATION",
    "add_assistant_message",
    "add_user_message",
    "conversation_response",
    "create_conversation",
    "get_conversation_message",
    "get_owned_conversation",
    "history_turns",
    "list_conversations",
    "list_messages",
    "mark_user_message_result",
    "serialize_message",
    "trim_messages",
    "update_title_from_message",
]
