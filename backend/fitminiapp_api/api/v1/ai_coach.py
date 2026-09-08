"""Authenticated generic-only AI Coach endpoint."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from fitminiapp_api.ai_coach.contracts import (
    AI_COACH_PERSONAL_PROMPT_VERSION,
    AiCoachDataClass,
    AiCoachJob,
    AiCoachOutcome,
    AiCoachRequest,
    AiCoachResponse,
)
from fitminiapp_api.ai_coach.personal_tools import (
    PersonalToolUnavailable,
    PersonalToolUnsafe,
    run_personal_tool,
)
from fitminiapp_api.ai_coach.safety import (
    SafetyCategory,
    classify_message,
    classify_request,
    refusal_text,
)
from fitminiapp_api.ai_coach.service import ai_coach_service
from fitminiapp_api.api.dependencies.auth import require_user
from fitminiapp_api.core.config import settings
from fitminiapp_api.core.rate_limit import limiter
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.ai_coach import (
    AiCoachConsentResponse,
    AiCoachConsentUpdateRequest,
    AiCoachGenerateRequest,
    AiCoachPersonalGenerateRequest,
    AiCoachStatusResponse,
)
from fitminiapp_api.services.ai_coach_consent import (
    get_ai_coach_consent,
    has_active_ai_coach_consent,
    serialize_ai_coach_consent,
    set_ai_coach_consent,
)
from fitminiapp_api.services.audit import record_audit_event

router = APIRouter()


def _generic_runtime_available() -> bool:
    return bool(
        settings.ai_coach_enabled
        and not settings.ai_coach_kill_switch
        and settings.ai_coach_provider == "groq"
        and settings.groq_api_key.get_secret_value().strip()
        and settings.ai_coach_cost_policy == "free_only"
        and settings.ai_coach_cost_class == "free"
        and settings.ai_coach_data_policy == "verified_generic_only"
        and settings.ai_coach_structured_output
    )


@router.get("/status", response_model=AiCoachStatusResponse)
@limiter.limit("60/hour")
def get_ai_coach_status(
    request: Request,
    current_user: User = Depends(require_user),
) -> AiCoachStatusResponse:
    del request
    ui_enabled = bool(
        settings.ai_coach_ui_enabled and current_user.id in settings.ai_coach_internal_user_id_set
    )
    generic_available = ui_enabled and _generic_runtime_available()
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


def _personal_state_response(
    *,
    request_id: str | None,
    outcome: AiCoachOutcome,
    safety_category: SafetyCategory = SafetyCategory.CLEAR,
    limitations: tuple[str, ...],
    answer: str | None = None,
) -> AiCoachResponse:
    return AiCoachResponse(
        outcome=outcome,
        answer=answer,
        limitations=limitations,
        safety_category=safety_category.value,
        prompt_version=AI_COACH_PERSONAL_PROMPT_VERSION,
        request_id=request_id,
    )


@router.post("/generate", response_model=AiCoachResponse)
@limiter.limit("10/minute")
def generate_ai_coach_answer(
    request: Request,
    payload: AiCoachGenerateRequest,
    current_user: User = Depends(require_user),
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


@router.post("/personal/generate", response_model=AiCoachResponse)
@limiter.limit("10/minute")
def generate_personal_ai_coach_answer(
    payload: AiCoachPersonalGenerateRequest,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> AiCoachResponse:
    request_id = getattr(request.state, "request_id", None)
    consent = get_ai_coach_consent(db, current_user.id)
    if not has_active_ai_coach_consent(consent):
        return _personal_state_response(
            request_id=request_id,
            outcome=AiCoachOutcome.CONSENT_REQUIRED,
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
            limitations=(
                "Персональный режим AI Coach сейчас недоступен; основные функции приложения продолжают работать.",
            ),
        )
    try:
        tool_result = run_personal_tool(db, current_user, payload.tool, payload.period_days)
    except PersonalToolUnsafe:
        return _personal_state_response(
            request_id=request_id,
            outcome=AiCoachOutcome.SAFETY_REFUSAL,
            safety_category=SafetyCategory.PROMPT_INJECTION,
            limitations=(),
            answer="Я могу отвечать только по безопасной структурированной сводке и не меняю эти ограничения.",
        )
    except PersonalToolUnavailable:
        return _personal_state_response(
            request_id=request_id,
            outcome=AiCoachOutcome.UNAVAILABLE,
            limitations=(
                "Не удалось безопасно получить эту сводку. Откройте соответствующий экран приложения.",
            ),
        )

    if tool_result.data_sufficiency == "insufficient":
        return _personal_state_response(
            request_id=request_id,
            outcome=AiCoachOutcome.INSUFFICIENT_DATA,
            limitations=(
                *tool_result.limitations,
                f"Проверьте исходные данные на экране {tool_result.fallback_path}.",
            ),
        )
    return ai_coach_service.generate(
        db=db,
        request=internal_request,
        user_key=str(current_user.id),
        request_id=request_id,
        context_refs=tool_result.context_refs,
    )
