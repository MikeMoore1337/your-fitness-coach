"""Account-owned storage helpers for AI Coach conversation history."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, cast

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from fitminiapp_api.ai_coach.contracts import (
    AiCoachCitation,
    AiCoachOutcome,
    AiCoachRateLimitScope,
)
from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.models.ai_coach import (
    AiCoachConversation,
    AiCoachConversationMessage,
    AiCoachConversationMessageRequest,
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


def is_processing_message(message: AiCoachConversationMessage) -> bool:
    """Return whether a message is in-flight under the durable marker contract."""

    return message.processing_started_at is not None or message.status == "processing"


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


def delete_conversation_history(db: Session, *, user_id: int) -> int:
    """Delete every conversation owned by one account and return its row count."""

    conversation_ids = [
        row.id
        for row in db.query(AiCoachConversation.id)
        .filter(AiCoachConversation.user_id == user_id)
        .all()
    ]
    if not conversation_ids:
        return 0
    # Delete children explicitly so the operation is deterministic on the
    # SQLite test runtime as well as on PostgreSQL. Request-key rows cascade
    # from their message/conversation foreign keys and are content-free.
    db.query(AiCoachConversationMessage).filter(
        AiCoachConversationMessage.conversation_id.in_(conversation_ids)
    ).delete(synchronize_session=False)
    return int(
        db.query(AiCoachConversation)
        .filter(
            AiCoachConversation.user_id == user_id,
            AiCoachConversation.id.in_(conversation_ids),
        )
        .delete(synchronize_session=False)
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


def list_processing_user_messages(
    db: Session,
    *,
    conversation_id: int,
    for_update: bool = False,
) -> list[AiCoachConversationMessage]:
    """Return in-flight user messages that may need crash recovery."""

    query = db.query(AiCoachConversationMessage).filter(
        AiCoachConversationMessage.conversation_id == conversation_id,
        AiCoachConversationMessage.role == "user",
        or_(
            AiCoachConversationMessage.processing_started_at.is_not(None),
            # Compatibility with rows created by the short-lived pre-migration
            # implementation before processing_started_at was persisted.
            AiCoachConversationMessage.status == "processing",
        ),
    )
    if for_update:
        query = query.with_for_update()
    return query.order_by(AiCoachConversationMessage.id.asc()).all()


def get_conversation_message(
    db: Session,
    *,
    conversation_id: int,
    message_id: int,
    for_update: bool = False,
) -> AiCoachConversationMessage | None:
    query = db.query(AiCoachConversationMessage).filter(
        AiCoachConversationMessage.id == message_id,
        AiCoachConversationMessage.conversation_id == conversation_id,
    )
    if for_update:
        query = query.with_for_update()
    return query.one_or_none()


def get_message_by_request_id(
    db: Session,
    *,
    conversation_id: int,
    request_id: str,
    for_update: bool = False,
) -> AiCoachConversationMessage | None:
    request_query = db.query(AiCoachConversationMessageRequest).filter(
        AiCoachConversationMessageRequest.conversation_id == conversation_id,
        AiCoachConversationMessageRequest.request_id == request_id,
    )
    if for_update:
        request_query = request_query.with_for_update()
    request_row = request_query.one_or_none()
    if request_row is not None:
        message_query = db.query(AiCoachConversationMessage).filter(
            AiCoachConversationMessage.id == request_row.message_id,
            AiCoachConversationMessage.conversation_id == conversation_id,
            AiCoachConversationMessage.role == "user",
        )
        if for_update:
            message_query = message_query.with_for_update()
        return message_query.one_or_none()

    # Rows written before the durable request-key table was introduced remain
    # discoverable through the legacy column. New rows always create the
    # unique request-key row in the same transaction as their message.
    legacy_query = db.query(AiCoachConversationMessage).filter(
        AiCoachConversationMessage.conversation_id == conversation_id,
        AiCoachConversationMessage.request_id == request_id,
        AiCoachConversationMessage.role == "user",
    )
    if for_update:
        legacy_query = legacy_query.with_for_update()
    return legacy_query.order_by(AiCoachConversationMessage.id.desc()).first()


def get_following_assistant_message(
    db: Session,
    *,
    conversation_id: int,
    user_message_id: int,
) -> AiCoachConversationMessage | None:
    next_message = (
        db.query(AiCoachConversationMessage)
        .filter(
            AiCoachConversationMessage.conversation_id == conversation_id,
            AiCoachConversationMessage.id > user_message_id,
        )
        .order_by(AiCoachConversationMessage.id.asc())
        .first()
    )
    return next_message if next_message is not None and next_message.role == "assistant" else None


def has_later_messages(
    db: Session,
    *,
    conversation_id: int,
    message_id: int,
) -> bool:
    return (
        db.query(AiCoachConversationMessage.id)
        .filter(
            AiCoachConversationMessage.conversation_id == conversation_id,
            AiCoachConversationMessage.id > message_id,
        )
        .first()
        is not None
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
        and message.processing_started_at is None
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
    request_id: str | None = None,
    status: str = "complete",
    data_class: str | None = None,
    prompt_version: str | None = None,
) -> AiCoachConversationMessage:
    inline_content = content[:LEGACY_INLINE_CONTENT_LIMIT]
    overflow_content = content if len(content) > LEGACY_INLINE_CONTENT_LIMIT else None
    persisted_status = "failed" if status == "processing" else status
    message = AiCoachConversationMessage(
        conversation_id=conversation.id,
        role="user",
        content=inline_content,
        content_overflow=overflow_content,
        # The deployed status check intentionally remains complete/failed. A
        # non-null processing_started_at is the durable in-flight marker.
        status=persisted_status,
        outcome=None,
        safety_category="clear",
        failure_category=None,
        request_id=request_id,
        data_class=data_class,
        prompt_version=prompt_version,
        processing_started_at=now_msk_naive() if status == "processing" else None,
        citations=[],
        limitations=[],
    )
    db.add(message)
    conversation.updated_at = now_msk_naive()
    db.flush()
    if request_id is not None:
        add_message_request(db, message=message, request_id=request_id)
    trim_messages(db, conversation_id=conversation.id)
    return message


def add_message_request(
    db: Session,
    *,
    message: AiCoachConversationMessage,
    request_id: str,
) -> AiCoachConversationMessageRequest:
    """Bind a new opaque request key to a message in the current transaction."""

    request_row = AiCoachConversationMessageRequest(
        conversation_id=message.conversation_id,
        message_id=message.id,
        request_id=request_id,
    )
    db.add(request_row)
    # The unique request key is flushed in the same transaction as the
    # message so a concurrent duplicate rolls back its entire message.
    db.flush()
    return request_row


def mark_user_message_result(
    message: AiCoachConversationMessage,
    *,
    outcome: AiCoachOutcome,
    safety_category: str,
    failure_category: str | None,
    request_id: str | None,
    limitations: Iterable[str] = (),
    data_class: str | None = None,
    prompt_version: str | None = None,
    rate_limit_scope: AiCoachRateLimitScope | None = None,
    rate_limit_retry_after_seconds: int | None = None,
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
    message.data_class = data_class or message.data_class
    message.prompt_version = prompt_version or message.prompt_version
    message.rate_limit_scope = rate_limit_scope.value if rate_limit_scope is not None else None
    message.rate_limit_retry_after_seconds = rate_limit_retry_after_seconds
    message.processing_started_at = None
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
    data_class: str | None = None,
    prompt_version: str | None = None,
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
        data_class=data_class,
        prompt_version=prompt_version,
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
    effective_status = "processing" if is_processing_message(message) else message.status
    return AiCoachConversationMessageResponse(
        id=message.id,
        role=cast(Literal["user", "assistant"], message.role),
        content=_message_content(message),
        status=cast(Literal["processing", "complete", "failed"], effective_status),
        outcome=outcome,
        safety_category=message.safety_category,
        failure_category=cast(
            Literal[
                "provider_failure",
                "structured_validation",
                "timeout",
                "rate_limit",
                "repair_failed",
                "presentation_validation_failed",
                "internal_error",
                "safety_rejection",
                "context_failure",
                "generation_failure",
                "rate_limited",
            ]
            | None,
            message.failure_category,
        ),
        rate_limit_scope=(
            AiCoachRateLimitScope(message.rate_limit_scope)
            if message.rate_limit_scope in {scope.value for scope in AiCoachRateLimitScope}
            else None
        ),
        rate_limit_retry_after_seconds=message.rate_limit_retry_after_seconds,
        citations=tuple(citations),
        limitations=limitations,
        created_at=message.created_at,
    )


__all__ = [
    "MAX_CONVERSATIONS_PER_USER",
    "MAX_MESSAGES_PER_CONVERSATION",
    "add_assistant_message",
    "add_message_request",
    "add_user_message",
    "conversation_response",
    "create_conversation",
    "delete_conversation_history",
    "get_conversation_message",
    "get_following_assistant_message",
    "get_message_by_request_id",
    "get_owned_conversation",
    "has_later_messages",
    "history_turns",
    "is_processing_message",
    "list_conversations",
    "list_messages",
    "list_processing_user_messages",
    "mark_user_message_result",
    "serialize_message",
    "trim_messages",
    "update_title_from_message",
]
