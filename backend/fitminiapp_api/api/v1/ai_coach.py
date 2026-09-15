"""Authenticated, bounded AI Coach endpoints."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from fitminiapp_api.ai_coach.chat_service import (
    CHAT_FAILURE_CONTEXT,
    CHAT_FAILURE_PROVIDER,
    AiCoachChatGeneration,
    ai_coach_chat_service,
)
from fitminiapp_api.ai_coach.context_selection import (
    ChatContextSelection,
    history_without_personal_context,
    message_requires_personal_context,
    select_chat_context,
)
from fitminiapp_api.ai_coach.contracts import (
    AI_COACH_CHAT_PROMPT_VERSION,
    AI_COACH_PERIOD_REPORT_PROMPT_VERSION,
    AI_COACH_PERSONAL_PROMPT_VERSION,
    AiCoachChatRequest,
    AiCoachCitation,
    AiCoachConversationTurn,
    AiCoachDataClass,
    AiCoachInsight,
    AiCoachInsightKind,
    AiCoachJob,
    AiCoachOutcome,
    AiCoachPersonalTool,
    AiCoachRequest,
    AiCoachResponse,
    AiCoachResponseMetadata,
)
from fitminiapp_api.ai_coach.personal_tools import (
    PersonalToolUnavailable,
    PersonalToolUnsafe,
    run_period_report_tool,
    run_personal_tool,
)
from fitminiapp_api.ai_coach.retrieval import ContextUnavailable
from fitminiapp_api.ai_coach.safety import (
    SafetyCategory,
    classify_message,
    classify_request,
    detect_chat_locale,
    refusal_text,
)
from fitminiapp_api.ai_coach.service import ai_coach_service
from fitminiapp_api.api.dependencies.auth import (
    require_ai_coach_user,
    require_user,
)
from fitminiapp_api.core.config import settings
from fitminiapp_api.core.rate_limit import limiter
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.ai_coach import (
    AiCoachConsentResponse,
    AiCoachConsentUpdateRequest,
    AiCoachConversationFeedbackRequest,
    AiCoachConversationListResponse,
    AiCoachConversationResponse,
    AiCoachConversationSendRequest,
    AiCoachConversationSendResponse,
    AiCoachGenerateRequest,
    AiCoachMemoryClearResponse,
    AiCoachMemoryConsentUpdateRequest,
    AiCoachMemoryCreateRequest,
    AiCoachMemoryItemResponse,
    AiCoachMemoryResponse,
    AiCoachMemoryUpdateRequest,
    AiCoachPersonalGenerateRequest,
    AiCoachStatusResponse,
)
from fitminiapp_api.schemas.progress import NutritionReportPeriod
from fitminiapp_api.services.ai_coach_consent import (
    get_ai_coach_consent,
    has_active_ai_coach_consent,
    serialize_ai_coach_consent,
    set_ai_coach_consent,
)
from fitminiapp_api.services.ai_coach_conversations import (
    add_assistant_message,
    add_user_message,
    conversation_response,
    create_conversation,
    get_conversation_message,
    get_owned_conversation,
    has_later_messages,
    history_turns,
    list_conversations,
    mark_user_message_result,
    serialize_message,
    update_title_from_message,
)
from fitminiapp_api.services.ai_coach_memory import (
    AiCoachMemoryValidationError,
    clear_ai_coach_memories,
    create_ai_coach_memory,
    delete_ai_coach_memory,
    get_ai_coach_memory_consent,
    get_ai_coach_memory_context,
    get_owned_ai_coach_memory,
    has_active_ai_coach_memory_consent,
    list_ai_coach_memories,
    serialize_ai_coach_memory,
    serialize_ai_coach_memory_consent,
    set_ai_coach_memory_consent,
    update_ai_coach_memory,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.period_bounds import PeriodBoundsError, progress_period_for_days

router = APIRouter()


def _chat_runtime_available() -> bool:
    """Check the plain-text chat gate without requiring report JSON support."""

    return bool(
        settings.ai_coach_enabled
        and not settings.ai_coach_kill_switch
        and settings.ai_coach_provider == "groq"
        and settings.groq_api_key.get_secret_value().strip()
        and settings.ai_coach_cost_policy == "free_only"
        and settings.ai_coach_cost_class == "free"
        and settings.ai_coach_data_policy == "verified_generic_only"
    )


@router.get("/status", response_model=AiCoachStatusResponse)
@limiter.limit("60/hour")
def get_ai_coach_status(
    request: Request,
    current_user: User = Depends(require_user),
) -> AiCoachStatusResponse:
    del request
    ui_enabled = True
    generic_available = _chat_runtime_available()
    personal_available = bool(
        generic_available
        and settings.ai_coach_personal_enabled
        and settings.ai_coach_personal_data_policy == "verified_personal_user"
    )
    return AiCoachStatusResponse(
        ui_enabled=ui_enabled,
        generic_available=generic_available,
        personal_available=personal_available,
    )


def _chat_state_generation(
    *,
    outcome: AiCoachOutcome,
    data_class: AiCoachDataClass,
    answer: str | None = None,
    limitations: tuple[str, ...] = (),
    safety_category: SafetyCategory = SafetyCategory.CLEAR,
    failure_category: str | None = None,
    citations: tuple[AiCoachCitation, ...] = (),
) -> AiCoachChatGeneration:
    return AiCoachChatGeneration(
        outcome=outcome,
        answer=answer,
        citations=citations,
        limitations=limitations,
        safety_category=safety_category,
        failure_category=failure_category,
        prompt_version=AI_COACH_CHAT_PROMPT_VERSION,
        data_class=data_class,
    )


def _chat_consent_generation(*, locale: str = "ru") -> AiCoachChatGeneration:
    return _chat_state_generation(
        outcome=AiCoachOutcome.CONSENT_REQUIRED,
        data_class=AiCoachDataClass.PERSONALIZED,
        answer=(
            "To answer about your training, progress, or nutrition, first enable "
            "separate consent for personal AI Coach answers. I do not access your data without it."
            if locale == "en"
            else "Чтобы ответить по вашим тренировкам, прогрессу или питанию, сначала "
            "включите отдельное согласие на персональный режим AI Coach. "
            "Без него я не открываю ваши данные."
        ),
    )


def _chat_personal_unavailable_generation(*, locale: str = "ru") -> AiCoachChatGeneration:
    return _chat_state_generation(
        outcome=AiCoachOutcome.UNAVAILABLE,
        data_class=AiCoachDataClass.PERSONALIZED,
        limitations=(
            (
                "Personal AI Coach answers are temporarily unavailable; the main app "
                "features are still available."
                if locale == "en"
                else "Персональный режим AI Coach сейчас недоступен; основные функции приложения "
                "продолжают работать."
            ),
        ),
        failure_category=CHAT_FAILURE_PROVIDER,
    )


def _chat_context_failure_generation(
    *,
    data_class: AiCoachDataClass,
    locale: str = "ru",
    citations: tuple[AiCoachCitation, ...] = (),
) -> AiCoachChatGeneration:
    return _chat_state_generation(
        outcome=AiCoachOutcome.UNAVAILABLE,
        data_class=data_class,
        answer=(
            "The approved materials could not be loaded. Please try again later."
            if locale == "en"
            else "Не удалось получить материалы для ответа. Попробуйте ещё раз позже."
        ),
        citations=citations,
        failure_category=CHAT_FAILURE_CONTEXT,
    )


def _chat_request_for_selection(
    *,
    message: str,
    history: tuple[AiCoachConversationTurn, ...],
    selection: ChatContextSelection,
    memory_context=(),
) -> AiCoachChatRequest:
    provider_history = (
        history_without_personal_context(history)
        if selection.data_class == AiCoachDataClass.GENERIC
        else history
    )
    return AiCoachChatRequest(
        job=selection.job,
        context_id=selection.context_id,
        message=message,
        data_class=selection.data_class,
        context_kind=selection.context_kind,
        locale=detect_chat_locale(message),
        conversation_history=provider_history,
        memory_context=memory_context,
    )


def _generate_chat(
    *,
    db: Session,
    current_user: User,
    message: str,
    history: tuple[AiCoachConversationTurn, ...],
    request_id: str | None,
) -> AiCoachChatGeneration:
    safety_category = classify_message(message)
    personal_needed = message_requires_personal_context(message, history)
    # A capability question can mention a user's own screen (for example, "my progress")
    # without requesting personal data. Let the explicit intent selector resolve that case;
    # all other safety categories remain fail-closed.
    if safety_category == SafetyCategory.PERSONAL_DATA and not personal_needed:
        safety_category = SafetyCategory.CLEAR
    personal_needed = personal_needed or safety_category == SafetyCategory.PERSONAL_DATA

    if safety_category not in {SafetyCategory.CLEAR, SafetyCategory.PERSONAL_DATA}:
        request = AiCoachChatRequest(
            job=AiCoachJob.FITNESS_KNOWLEDGE,
            context_id="public:safety",
            message=message,
            data_class=AiCoachDataClass.UNKNOWN,
            locale=detect_chat_locale(message),
            conversation_history=history,
        )
        return ai_coach_chat_service.generate(
            request=request,
            user_key=str(current_user.id),
            request_id=request_id,
            context_refs=(),
        )

    if personal_needed:
        if not has_active_ai_coach_consent(get_ai_coach_consent(db, current_user.id)):
            return _chat_consent_generation(locale=detect_chat_locale(message))
        if not (
            _chat_runtime_available()
            and settings.ai_coach_personal_enabled
            and settings.ai_coach_personal_data_policy == "verified_personal_user"
        ):
            return _chat_personal_unavailable_generation(locale=detect_chat_locale(message))
        selection = select_chat_context(
            db,
            current_user,
            message=message,
            history=history,
        )
        request = _chat_request_for_selection(
            message=message,
            history=history,
            selection=selection,
            memory_context=get_ai_coach_memory_context(db, user_id=current_user.id),
        )
    else:
        selection = select_chat_context(
            db,
            current_user,
            message=message,
            history=history,
        )
        request = _chat_request_for_selection(
            message=message,
            history=history,
            selection=selection,
        )

    return ai_coach_chat_service.generate(
        request=request,
        user_key=str(current_user.id),
        request_id=request_id,
        context_refs=selection.context_refs,
    )


def _conversation_or_404(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
):
    conversation = get_owned_conversation(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Разговор AI Coach не найден")
    return conversation


def _generate_conversation_message(
    *,
    db: Session,
    current_user: User,
    message: str,
    history: tuple[AiCoachConversationTurn, ...],
    request_id: str | None,
) -> AiCoachChatGeneration:
    try:
        return _generate_chat(
            db=db,
            current_user=current_user,
            message=message,
            history=history,
            request_id=request_id,
        )
    except PersonalToolUnsafe:
        return _chat_state_generation(
            outcome=AiCoachOutcome.SAFETY_REFUSAL,
            data_class=AiCoachDataClass.PERSONALIZED,
            answer=refusal_text(
                SafetyCategory.PROMPT_INJECTION,
                locale=detect_chat_locale(message),
            ),
            safety_category=SafetyCategory.PROMPT_INJECTION,
        )
    except PersonalToolUnavailable:
        return _chat_context_failure_generation(
            data_class=AiCoachDataClass.PERSONALIZED,
            locale=detect_chat_locale(message),
        )
    except ContextUnavailable:
        return _chat_context_failure_generation(
            data_class=AiCoachDataClass.GENERIC,
            locale=detect_chat_locale(message),
        )


def _persist_conversation_generation(
    *,
    db: Session,
    conversation,
    user_message,
    generation: AiCoachChatGeneration,
    request_id: str | None,
) -> AiCoachConversationSendResponse:
    mark_user_message_result(
        user_message,
        outcome=generation.outcome,
        safety_category=generation.safety_category.value,
        failure_category=generation.failure_category,
        request_id=request_id,
        limitations=generation.limitations,
    )
    assistant_message = None
    if generation.answer is not None:
        assistant_message = add_assistant_message(
            db,
            conversation=conversation,
            content=generation.answer,
            outcome=generation.outcome,
            safety_category=generation.safety_category.value,
            failure_category=generation.failure_category,
            request_id=request_id,
            citations=generation.citations,
            limitations=generation.limitations,
        )
    db.commit()
    return AiCoachConversationSendResponse(
        conversation_id=conversation.id,
        user_message=serialize_message(user_message),
        assistant_message=serialize_message(assistant_message)
        if assistant_message is not None
        else None,
        outcome=generation.outcome,
        data_class=generation.data_class,
        answer=generation.answer,
        citations=generation.citations,
        limitations=generation.limitations,
        safety_category=generation.safety_category.value,
        failure_category=generation.failure_category,
        prompt_version=generation.prompt_version,
        request_id=request_id,
    )


@router.get("/conversations", response_model=AiCoachConversationListResponse)
@limiter.limit("60/hour")
def get_ai_coach_conversations(
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> AiCoachConversationListResponse:
    del request
    return AiCoachConversationListResponse(items=list_conversations(db, user_id=current_user.id))


@router.post(
    "/conversations",
    response_model=AiCoachConversationResponse,
    status_code=201,
)
@limiter.limit("20/hour")
def create_ai_coach_conversation(
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> AiCoachConversationResponse:
    del request
    try:
        conversation = create_conversation(db, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    record_audit_event(
        db,
        action="ai_coach.conversation_created",
        resource_type="ai_coach_conversation",
        resource_id=conversation.id,
        actor_user_id=current_user.id,
        target_user_id=current_user.id,
    )
    db.commit()
    return conversation_response(db, conversation)


@router.get(
    "/conversations/{conversation_id}",
    response_model=AiCoachConversationResponse,
)
@limiter.limit("60/hour")
def get_ai_coach_conversation(
    conversation_id: int,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> AiCoachConversationResponse:
    del request
    conversation = _conversation_or_404(
        db,
        user_id=current_user.id,
        conversation_id=conversation_id,
    )
    return conversation_response(db, conversation)


@router.delete("/conversations/{conversation_id}", status_code=204)
@limiter.limit("10/hour")
def delete_ai_coach_conversation(
    conversation_id: int,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    del request
    conversation = _conversation_or_404(
        db,
        user_id=current_user.id,
        conversation_id=conversation_id,
    )
    db.delete(conversation)
    record_audit_event(
        db,
        action="ai_coach.conversation_deleted",
        resource_type="ai_coach_conversation",
        resource_id=conversation_id,
        actor_user_id=current_user.id,
        target_user_id=current_user.id,
    )
    db.commit()
    return Response(status_code=204)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=AiCoachConversationSendResponse,
)
@limiter.limit("10/minute")
def send_ai_coach_conversation_message(
    conversation_id: int,
    payload: AiCoachConversationSendRequest,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> AiCoachConversationSendResponse:
    conversation = _conversation_or_404(
        db,
        user_id=current_user.id,
        conversation_id=conversation_id,
    )
    request_id = getattr(request.state, "request_id", None)
    history = tuple(
        AiCoachConversationTurn.model_validate(item)
        for item in history_turns(db, conversation_id=conversation.id)
    )
    user_message = add_user_message(
        db,
        conversation=conversation,
        content=payload.message,
    )
    update_title_from_message(conversation, content=payload.message)
    generation = _generate_conversation_message(
        db=db,
        current_user=current_user,
        message=payload.message,
        history=history,
        request_id=request_id,
    )
    return _persist_conversation_generation(
        db=db,
        conversation=conversation,
        user_message=user_message,
        generation=generation,
        request_id=request_id,
    )


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}/retry",
    response_model=AiCoachConversationSendResponse,
)
@limiter.limit("10/minute")
def retry_ai_coach_conversation_message(
    conversation_id: int,
    message_id: int,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> AiCoachConversationSendResponse:
    conversation = _conversation_or_404(
        db,
        user_id=current_user.id,
        conversation_id=conversation_id,
    )
    user_message = get_conversation_message(
        db,
        conversation_id=conversation.id,
        message_id=message_id,
        for_update=True,
    )
    if (
        user_message is None
        or user_message.role != "user"
        or user_message.status != "failed"
        or has_later_messages(
            db,
            conversation_id=conversation.id,
            message_id=message_id,
        )
    ):
        raise HTTPException(
            status_code=409,
            detail="Повторить можно только последнее неудачное сообщение AI Coach",
        )
    content = user_message.content_overflow or user_message.content
    history = tuple(
        AiCoachConversationTurn.model_validate(item)
        for item in history_turns(db, conversation_id=conversation.id)
    )
    request_id = getattr(request.state, "request_id", None)
    generation = _generate_conversation_message(
        db=db,
        current_user=current_user,
        message=content,
        history=history,
        request_id=request_id,
    )
    return _persist_conversation_generation(
        db=db,
        conversation=conversation,
        user_message=user_message,
        generation=generation,
        request_id=request_id,
    )


@router.post("/conversations/{conversation_id}/messages/{message_id}/feedback", status_code=204)
@limiter.limit("60/hour")
def submit_ai_coach_conversation_feedback(
    conversation_id: int,
    message_id: int,
    payload: AiCoachConversationFeedbackRequest,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    del request
    _conversation_or_404(
        db,
        user_id=current_user.id,
        conversation_id=conversation_id,
    )
    message = get_conversation_message(
        db,
        conversation_id=conversation_id,
        message_id=message_id,
    )
    if message is None or message.role != "assistant":
        raise HTTPException(status_code=404, detail="Сообщение AI Coach не найдено")
    record_audit_event(
        db,
        action="ai_coach.conversation_feedback",
        resource_type="ai_coach_conversation_message",
        resource_id=message_id,
        actor_user_id=current_user.id,
        target_user_id=current_user.id,
        details={"value": payload.value},
    )
    db.commit()
    return Response(status_code=204)


def _personal_state_response(
    *,
    request_id: str | None,
    outcome: AiCoachOutcome,
    safety_category: SafetyCategory = SafetyCategory.CLEAR,
    limitations: tuple[str, ...],
    answer: str | None = None,
    citations: tuple[AiCoachCitation, ...] = (),
    prompt_version: str = AI_COACH_PERSONAL_PROMPT_VERSION,
    insights: tuple[AiCoachInsight, ...] = (),
    response_metadata: AiCoachResponseMetadata | None = None,
) -> AiCoachResponse:
    return AiCoachResponse(
        outcome=outcome,
        answer=answer,
        citations=citations,
        insights=insights,
        limitations=limitations,
        safety_category=safety_category.value,
        prompt_version=prompt_version,
        request_id=request_id,
        report_version=response_metadata.report_version if response_metadata else None,
        input_version=response_metadata.input_version if response_metadata else None,
        output_version=response_metadata.output_version if response_metadata else None,
        report_revision=response_metadata.report_revision if response_metadata else None,
        period_start=response_metadata.period_start if response_metadata else None,
        period_end=response_metadata.period_end if response_metadata else None,
        timezone=response_metadata.timezone if response_metadata else None,
    )


def _period_for_payload(
    payload: AiCoachPersonalGenerateRequest,
) -> tuple[NutritionReportPeriod, date | None, date | None, int]:
    if payload.period is None:
        return progress_period_for_days(payload.period_days), None, None, payload.period_days
    period_map = {
        "days_7": NutritionReportPeriod.DAYS_7,
        "days_30": NutritionReportPeriod.DAYS_30,
        "days_90": NutritionReportPeriod.DAYS_90,
        "custom": NutritionReportPeriod.CUSTOM,
    }
    period = period_map[payload.period]
    if period == NutritionReportPeriod.CUSTOM:
        if payload.tool != AiCoachPersonalTool.GET_PERIOD_REPORT_INSIGHTS:
            raise HTTPException(
                status_code=422, detail="Произвольный период доступен только для итога отчёта"
            )
        return period, payload.date_from, payload.date_to, payload.period_days
    return period, None, None, {7: 7, 30: 30, 90: 90}[int(period.value.split("_")[-1])]


def _period_report_insufficient_response(
    *,
    request_id: str | None,
    result,
) -> AiCoachResponse:
    metadata = result.response_metadata
    reason_key = result.reason_keys[0] if result.reason_keys else "report_data_insufficient"
    facts = result.facts.get("facts", []) if isinstance(result.facts, dict) else []
    period_days = next(
        (
            item.get("value")
            for item in facts
            if isinstance(item, dict) and item.get("evidence_id") == "report.period_days"
        ),
        (result.period_end - result.period_start).days + 1,
    )
    coverage = result.facts.get("coverage", {}) if isinstance(result.facts, dict) else {}
    status_sections = [
        section
        for section, value in coverage.items()
        if isinstance(value, dict) and value.get("status") != "sufficient"
    ]
    status_text = ", ".join(status_sections) if status_sections else "отчёт"
    answer = (
        "Главное за период\n\n"
        f"- Канонический отчёт охватывает {period_days} дн. и доступен без новых расчётов.\n"
        f"- Для устойчивого итога пока недостаточно данных в разделах: {status_text}.\n\n"
        "Ограничения данных\n\n"
        + "\n".join(f"- {item}" for item in result.limitations[:4])
        + "\n\nЧто можно сделать дальше\n\n"
        "- Сначала заполните пропущенные записи в исходном разделе и повторите запрос.\n\n"
        f"Почему\n\n- Основание: {reason_key}."
    )
    insights = (
        AiCoachInsight(
            kind=AiCoachInsightKind.FACT,
            text=f"Канонический отчёт охватывает {period_days} дней.",
            evidence_ids=("report.period_days",),
            reason_keys=(f"report_version:{metadata.report_version}",) if metadata else (),
        ),
        AiCoachInsight(
            kind=AiCoachInsightKind.FACT,
            text=f"Устойчивый персональный вывод ограничен разделами: {status_text}.",
            evidence_ids=("report.period_days",),
            reason_keys=(reason_key,),
        ),
        AiCoachInsight(
            kind=AiCoachInsightKind.SUGGESTION,
            text="Заполните пропущенные записи в исходном разделе и повторите запрос.",
            evidence_ids=("report.period_days",),
            reason_keys=(reason_key,),
        ),
    )
    return _personal_state_response(
        request_id=request_id,
        outcome=AiCoachOutcome.INSUFFICIENT_DATA,
        limitations=tuple(result.limitations[:6]),
        answer=answer[:1600],
        citations=tuple(
            AiCoachCitation.model_validate(citation.model_dump())
            for ref in result.context_refs
            for citation in ref.citations
        ),
        prompt_version=AI_COACH_PERIOD_REPORT_PROMPT_VERSION,
        insights=insights,
        response_metadata=metadata,
    )


@router.post("/generate", response_model=AiCoachResponse)
@limiter.limit("10/minute")
def generate_ai_coach_answer(
    request: Request,
    payload: AiCoachGenerateRequest,
    current_user: User = Depends(require_ai_coach_user),
    db: Session = Depends(get_db),
) -> AiCoachResponse:
    # This route is physically generic-only: no profile, diary, workout,
    # trainer object or conversation history is loaded or passed downstream.
    # A message that looks personal is never labelled as trusted generic input;
    # the service still re-checks the content before any provider call.
    safety_category = classify_message(payload.message)
    data_class = (
        AiCoachDataClass.UNKNOWN
        if safety_category != SafetyCategory.CLEAR
        else AiCoachDataClass.GENERIC
    )
    internal_request = AiCoachRequest(
        job=payload.job,
        context_id=payload.context_id,
        message=payload.message,
        data_class=data_class,
    )
    return ai_coach_service.generate(
        db=db,
        request=internal_request,
        user_key=str(current_user.id),
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/consent", response_model=AiCoachConsentResponse)
@limiter.limit("30/hour")
def get_personal_ai_coach_consent(
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> AiCoachConsentResponse:
    del request
    return AiCoachConsentResponse.model_validate(
        serialize_ai_coach_consent(get_ai_coach_consent(db, current_user.id))
    )


@router.put("/consent", response_model=AiCoachConsentResponse)
@limiter.limit("10/hour")
def update_personal_ai_coach_consent(
    payload: AiCoachConsentUpdateRequest,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> AiCoachConsentResponse:
    consent = set_ai_coach_consent(db, user_id=current_user.id, enabled=payload.enabled)
    record_audit_event(
        db,
        action=(
            "ai_coach.personal_consent_granted"
            if payload.enabled
            else "ai_coach.personal_consent_revoked"
        ),
        resource_type="ai_coach_personal_consent",
        actor_user_id=current_user.id,
        target_user_id=current_user.id,
        details={
            "scope": consent.scope,
            "consent_version": consent.consent_version,
            "provider_policy_revision": consent.provider_policy_revision,
        },
    )
    db.commit()
    return AiCoachConsentResponse.model_validate(serialize_ai_coach_consent(consent))


def _memory_response(db: Session, user_id: int) -> AiCoachMemoryResponse:
    consent = get_ai_coach_memory_consent(db, user_id)
    return AiCoachMemoryResponse.model_validate(
        {
            **serialize_ai_coach_memory_consent(consent),
            "items": tuple(
                serialize_ai_coach_memory(memory) for memory in list_ai_coach_memories(db, user_id)
            ),
        }
    )


def _require_active_memory_consent(db: Session, user_id: int) -> None:
    if not has_active_ai_coach_memory_consent(get_ai_coach_memory_consent(db, user_id)):
        raise HTTPException(
            status_code=409,
            detail="Сначала включите отдельную память AI Coach",
        )


@router.get("/memory", response_model=AiCoachMemoryResponse)
@limiter.limit("30/hour")
def get_ai_coach_memory(
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> AiCoachMemoryResponse:
    del request
    return _memory_response(db, current_user.id)


@router.put("/memory/consent", response_model=AiCoachMemoryResponse)
@limiter.limit("20/hour")
def update_ai_coach_memory_consent(
    payload: AiCoachMemoryConsentUpdateRequest,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> AiCoachMemoryResponse:
    del request
    consent = set_ai_coach_memory_consent(
        db,
        user_id=current_user.id,
        status=payload.status,
    )
    record_audit_event(
        db,
        action=f"ai_coach.memory_consent_{payload.status}",
        resource_type="ai_coach_memory_consent",
        actor_user_id=current_user.id,
        target_user_id=current_user.id,
        details={
            "scope": consent.scope,
            "consent_version": consent.consent_version,
            "status": payload.status,
        },
    )
    db.commit()
    return _memory_response(db, current_user.id)


@router.post("/memory", response_model=AiCoachMemoryItemResponse)
@limiter.limit("30/hour")
def create_ai_coach_memory_item(
    payload: AiCoachMemoryCreateRequest,
    request: Request,
    current_user: User = Depends(require_ai_coach_user),
    db: Session = Depends(get_db),
) -> AiCoachMemoryItemResponse:
    del request
    _require_active_memory_consent(db, current_user.id)
    try:
        memory = create_ai_coach_memory(
            db,
            user_id=current_user.id,
            category=payload.category,
            value=payload.value,
        )
    except AiCoachMemoryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record_audit_event(
        db,
        action="ai_coach.memory_created",
        resource_type="ai_coach_memory",
        resource_id=str(memory.id),
        actor_user_id=current_user.id,
        target_user_id=current_user.id,
        details={"category": memory.category, "source_kind": memory.source_kind},
    )
    db.commit()
    return AiCoachMemoryItemResponse.model_validate(serialize_ai_coach_memory(memory))


@router.delete("/memory", response_model=AiCoachMemoryClearResponse)
@limiter.limit("10/hour")
def clear_ai_coach_memory(
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> AiCoachMemoryClearResponse:
    del request
    deleted_count = clear_ai_coach_memories(db, user_id=current_user.id)
    record_audit_event(
        db,
        action="ai_coach.memory_cleared",
        resource_type="ai_coach_memory",
        actor_user_id=current_user.id,
        target_user_id=current_user.id,
        details={"deleted_count": deleted_count},
    )
    db.commit()
    return AiCoachMemoryClearResponse(deleted_count=deleted_count)


@router.patch("/memory/{memory_id}", response_model=AiCoachMemoryItemResponse)
@limiter.limit("30/hour")
def update_ai_coach_memory_item(
    memory_id: int,
    payload: AiCoachMemoryUpdateRequest,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> AiCoachMemoryItemResponse:
    del request
    _require_active_memory_consent(db, current_user.id)
    memory = get_owned_ai_coach_memory(db, user_id=current_user.id, memory_id=memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Элемент AI Coach memory не найден")
    try:
        update_ai_coach_memory(db, memory=memory, value=payload.value)
    except AiCoachMemoryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record_audit_event(
        db,
        action="ai_coach.memory_updated",
        resource_type="ai_coach_memory",
        resource_id=str(memory.id),
        actor_user_id=current_user.id,
        target_user_id=current_user.id,
        details={"category": memory.category, "version": memory.version},
    )
    db.commit()
    return AiCoachMemoryItemResponse.model_validate(serialize_ai_coach_memory(memory))


@router.delete("/memory/{memory_id}", response_model=AiCoachMemoryClearResponse)
@limiter.limit("30/hour")
def delete_ai_coach_memory_item(
    memory_id: int,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> AiCoachMemoryClearResponse:
    del request
    memory = get_owned_ai_coach_memory(db, user_id=current_user.id, memory_id=memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Элемент AI Coach memory не найден")
    category = memory.category
    delete_ai_coach_memory(db, memory=memory)
    record_audit_event(
        db,
        action="ai_coach.memory_deleted",
        resource_type="ai_coach_memory",
        resource_id=str(memory_id),
        actor_user_id=current_user.id,
        target_user_id=current_user.id,
        details={"category": category},
    )
    db.commit()
    return AiCoachMemoryClearResponse(deleted_count=1)


@router.post("/personal/generate", response_model=AiCoachResponse)
@limiter.limit("10/minute")
def generate_personal_ai_coach_answer(
    payload: AiCoachPersonalGenerateRequest,
    request: Request,
    current_user: User = Depends(require_ai_coach_user),
    db: Session = Depends(get_db),
) -> AiCoachResponse:
    request_id = getattr(request.state, "request_id", None)
    period_report_request = payload.tool == AiCoachPersonalTool.GET_PERIOD_REPORT_INSIGHTS
    response_prompt_version = (
        AI_COACH_PERIOD_REPORT_PROMPT_VERSION
        if period_report_request
        else AI_COACH_PERSONAL_PROMPT_VERSION
    )
    consent = get_ai_coach_consent(db, current_user.id)
    if not has_active_ai_coach_consent(consent):
        return _personal_state_response(
            request_id=request_id,
            outcome=AiCoachOutcome.CONSENT_REQUIRED,
            prompt_version=response_prompt_version,
            limitations=(
                "Сначала включите отдельное согласие на передачу ограниченной персональной сводки AI Coach.",
            ),
        )

    internal_request = AiCoachRequest(
        job=AiCoachJob.METRIC_EXPLANATION,
        context_id=f"personal:{payload.tool.value}",
        message=payload.message,
        data_class=AiCoachDataClass.PERSONALIZED,
        tool_name=payload.tool,
    )
    safety = classify_request(internal_request)
    if safety != SafetyCategory.CLEAR:
        return _personal_state_response(
            request_id=request_id,
            outcome=AiCoachOutcome.SAFETY_REFUSAL,
            safety_category=safety,
            limitations=(),
            answer=refusal_text(safety),
            prompt_version=response_prompt_version,
        )
    internal_request = internal_request.model_copy(
        update={
            "memory_context": get_ai_coach_memory_context(
                db,
                user_id=current_user.id,
            )
        }
    )
    if (
        not settings.ai_coach_enabled
        or settings.ai_coach_kill_switch
        or not settings.ai_coach_personal_enabled
        or settings.ai_coach_personal_data_policy != "verified_personal_user"
    ):
        return _personal_state_response(
            request_id=request_id,
            outcome=AiCoachOutcome.UNAVAILABLE,
            prompt_version=response_prompt_version,
            limitations=(
                "Персональный режим AI Coach сейчас недоступен; основные функции приложения продолжают работать.",
            ),
        )
    try:
        period, date_from, date_to, period_days = _period_for_payload(payload)
        if payload.tool == AiCoachPersonalTool.GET_PERIOD_REPORT_INSIGHTS:
            tool_result = run_period_report_tool(
                db,
                current_user,
                period=period,
                date_from=date_from,
                date_to=date_to,
            )
        else:
            tool_result = run_personal_tool(db, current_user, payload.tool, period_days)
    except PersonalToolUnsafe:
        return _personal_state_response(
            request_id=request_id,
            outcome=AiCoachOutcome.SAFETY_REFUSAL,
            safety_category=SafetyCategory.PROMPT_INJECTION,
            limitations=(),
            answer="Я могу отвечать только по безопасной структурированной сводке и не меняю эти ограничения.",
            prompt_version=response_prompt_version,
        )
    except PeriodBoundsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PersonalToolUnavailable:
        return _personal_state_response(
            request_id=request_id,
            outcome=AiCoachOutcome.UNAVAILABLE,
            prompt_version=response_prompt_version,
            limitations=(
                "Не удалось безопасно получить эту сводку. Откройте соответствующий экран приложения.",
            ),
        )

    if tool_result.data_sufficiency == "insufficient":
        if payload.tool == AiCoachPersonalTool.GET_PERIOD_REPORT_INSIGHTS:
            return _period_report_insufficient_response(request_id=request_id, result=tool_result)
        return _personal_state_response(
            request_id=request_id,
            outcome=AiCoachOutcome.INSUFFICIENT_DATA,
            prompt_version=response_prompt_version,
            limitations=(
                *tool_result.limitations,
                "Проверьте исходные записи, если хотите дополнить эту сводку.",
            ),
        )
    return ai_coach_service.generate(
        db=db,
        request=internal_request,
        user_key=str(current_user.id),
        request_id=request_id,
        context_refs=tool_result.context_refs,
        response_metadata=tool_result.response_metadata,
        evidence_ids=frozenset(tool_result.evidence_ids),
        reason_keys=frozenset(tool_result.reason_keys),
    )
