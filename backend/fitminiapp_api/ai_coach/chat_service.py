"""Bounded plain-text generation for the conversational AI Coach."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from fitminiapp_api.ai_coach.contracts import (
    AI_COACH_CHAT_OUTPUT_VERSION,
    AI_COACH_CHAT_PROMPT_VERSION,
    AiCoachChatRequest,
    AiCoachCitation,
    AiCoachDataClass,
    AiCoachOutcome,
    ChatLlmPort,
    ChatOutputValidationReason,
    ContextRef,
    NormalizedProviderError,
    ProviderErrorCode,
    ProviderFailureReason,
    ProviderTextResult,
)
from fitminiapp_api.ai_coach.providers import GroqDirectAdapter
from fitminiapp_api.ai_coach.safety import (
    SafetyCategory,
    bound_safe_chat_output,
    classify_message,
    inspect_chat_output,
    refusal_text,
    sanitize_chat_output,
)
from fitminiapp_api.core.config import settings

logger = logging.getLogger("app.ai_coach")

CHAT_FAILURE_PROVIDER = "provider_failure"
CHAT_FAILURE_STRUCTURED_VALIDATION = "structured_validation"
CHAT_FAILURE_SAFETY_REJECTION = "safety_rejection"
CHAT_FAILURE_REPAIR_FAILED = "repair_failed"
CHAT_FAILURE_PRESENTATION_VALIDATION = "presentation_validation_failed"
CHAT_FAILURE_INTERNAL_ERROR = "internal_error"
CHAT_FAILURE_TIMEOUT = "timeout"
CHAT_FAILURE_CONTEXT = "context_failure"
CHAT_FAILURE_GENERATION = "generation_failure"
CHAT_FAILURE_RATE_LIMIT = "rate_limit"
CHAT_FAILURE_RATE_LIMITED = CHAT_FAILURE_RATE_LIMIT
_INTERNAL_APP_PATHS = ("/today", "/nutrition", "/progress", "/training", "/api", "/v1")

_GENERIC_LIMITATION = (
    "Ответ основан на проверенных материалах YFC и не является персональным назначением."
)
_GENERAL_LIMITATION = "Ответ основан на общих знаниях и не является персональным назначением или медицинской рекомендацией."
_PERSONAL_LIMITATION = (
    "Ответ основан только на разрешённом срезе ваших данных; AI Coach не изменяет "
    "программу, цели или расписание."
)
_PERSONAL_NO_CONTEXT_LIMITATION = (
    "В разрешённом персональном срезе нет подходящих фактов; ответ не утверждает личные значения."
)


@dataclass
class _ChatWindow:
    started_at: float
    global_count: int
    per_user_count: dict[str, int]


class _ChatQuota:
    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._window = _ChatWindow(clock(), 0, {})

    def reserve(self, user_key: str) -> bool:
        now = self._clock()
        with self._lock:
            if now - self._window.started_at >= settings.ai_coach_quota_window_seconds:
                self._window = _ChatWindow(now, 0, {})
            if self._window.global_count >= settings.ai_coach_global_request_limit:
                return False
            current = self._window.per_user_count.get(user_key, 0)
            if current >= settings.ai_coach_per_user_request_limit:
                return False
            self._window.global_count += 1
            self._window.per_user_count[user_key] = current + 1
            return True

    def reset(self) -> None:
        with self._lock:
            self._window = _ChatWindow(self._clock(), 0, {})


class _ChatCooldown:
    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._until = 0.0
        self._consecutive_5xx_failures = 0

    def active(self) -> bool:
        with self._lock:
            if self._until and self._clock() >= self._until:
                self._until = 0.0
                self._consecutive_5xx_failures = 0
                return False
            return bool(self._until)

    def mark(self, error: NormalizedProviderError) -> None:
        with self._lock:
            if error.code == ProviderErrorCode.RATE_LIMITED:
                self._consecutive_5xx_failures = 0
                delay = (
                    error.retry_after_seconds
                    if error.retry_after_seconds is not None
                    else settings.ai_coach_cooldown_seconds
                )
                self._until = max(self._until, self._clock() + max(1, min(delay, 3600)))
                return
            if error.misconfigured or error.code == ProviderErrorCode.AUTHENTICATION_FAILED:
                self._consecutive_5xx_failures = 0
                self._until = max(
                    self._until,
                    self._clock() + max(1, min(settings.ai_coach_cooldown_seconds, 3600)),
                )
                return
            if error.provider_failure_reason == ProviderFailureReason.HTTP_5XX:
                self._consecutive_5xx_failures += 1
                if self._consecutive_5xx_failures < 3:
                    return
                delay = settings.ai_coach_cooldown_seconds
                self._until = max(self._until, self._clock() + max(1, min(delay, 3600)))
                return
            self._consecutive_5xx_failures = 0

    def reset(self) -> None:
        with self._lock:
            self._until = 0.0
            self._consecutive_5xx_failures = 0


class _ChatProviderFailure(RuntimeError):
    def __init__(self, error: NormalizedProviderError, attempts: int) -> None:
        super().__init__(error.code.value)
        self.error = error
        self.attempts = attempts


@dataclass(frozen=True)
class AiCoachChatGeneration:
    outcome: AiCoachOutcome
    answer: str | None
    citations: tuple[AiCoachCitation, ...]
    limitations: tuple[str, ...]
    safety_category: SafetyCategory
    failure_category: str | None
    prompt_version: str
    data_class: AiCoachDataClass
    repair_attempted: bool = False
    repair_success: bool = False
    validation_failure_reason: ChatOutputValidationReason | None = None
    provider_failure_reason: ProviderFailureReason | None = None


def _safe_groq_route() -> bool:
    parsed = urlparse(settings.ai_coach_endpoint)
    return bool(
        parsed.scheme == "https"
        and parsed.hostname == "api.groq.com"
        and parsed.path == "/openai/v1/chat/completions"
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )


class AiCoachChatService:
    """Orchestrate safety, policy, quotas and plain-text provider output."""

    def __init__(
        self,
        *,
        provider: ChatLlmPort | None = None,
        quota: _ChatQuota | None = None,
        cooldown: _ChatCooldown | None = None,
    ) -> None:
        self.provider = provider or GroqDirectAdapter()
        self.quota = quota or _ChatQuota()
        self.cooldown = cooldown or _ChatCooldown()

    def reset_runtime_state(self) -> None:
        self.quota.reset()
        self.cooldown.reset()

    def generate(
        self,
        *,
        request: AiCoachChatRequest,
        user_key: str,
        request_id: str | None,
        context_refs: tuple[ContextRef, ...],
    ) -> AiCoachChatGeneration:
        started = time.monotonic()
        safety = classify_message(request.message)
        if (
            request.data_class == AiCoachDataClass.PERSONALIZED
            and safety == SafetyCategory.PERSONAL_DATA
        ) or (
            request.data_class == AiCoachDataClass.GENERIC
            and request.context_kind.value == "app_capabilities"
            and safety == SafetyCategory.PERSONAL_DATA
        ):
            safety = SafetyCategory.CLEAR
        attempts = 0
        provider_name: str | None = getattr(self.provider, "provider_name", None)
        configured_model: str | None = settings.ai_coach_model
        actual_model: str | None = None
        usage = None
        outcome = AiCoachOutcome.UNAVAILABLE
        error_code: str | None = None
        failure_category: str | None = None
        repair_attempted = False
        repair_success = False
        validation_failure_reason: ChatOutputValidationReason | None = None
        provider_failure_reason: ProviderFailureReason | None = None
        http_status: int | None = None
        finish_reason: str | None = None
        provider_response_bytes: int | None = None
        response_payload_type: str | None = None
        choices_count: int | None = None
        choices_item_type: str | None = None
        message_present: bool | None = None
        message_type: str | None = None
        refusal_present: bool | None = None
        content_present: bool | None = None
        content_type: str | None = None
        answer: str | None = None
        try:
            if safety != SafetyCategory.CLEAR:
                outcome = AiCoachOutcome.SAFETY_REFUSAL
                failure_category = CHAT_FAILURE_SAFETY_REJECTION
                return AiCoachChatGeneration(
                    outcome=outcome,
                    answer=refusal_text(safety, locale=request.locale),
                    citations=(),
                    limitations=(),
                    safety_category=safety,
                    failure_category=failure_category,
                    prompt_version=AI_COACH_CHAT_PROMPT_VERSION,
                    data_class=request.data_class,
                )
            if request.data_class not in {
                AiCoachDataClass.GENERIC,
                AiCoachDataClass.PERSONALIZED,
            }:
                error_code = ProviderErrorCode.POLICY_BLOCKED.value
                failure_category = CHAT_FAILURE_GENERATION
                return self._failure(
                    request,
                    outcome=AiCoachOutcome.UNAVAILABLE,
                    safety=safety,
                    failure_category=failure_category,
                )
            if not settings.ai_coach_enabled or settings.ai_coach_kill_switch:
                error_code = ProviderErrorCode.DISABLED.value
                failure_category = CHAT_FAILURE_PROVIDER
                return self._failure(
                    request,
                    outcome=AiCoachOutcome.UNAVAILABLE,
                    safety=safety,
                    failure_category=failure_category,
                )
            gate_error = self._provider_gate(request.data_class)
            if gate_error is not None:
                error_code = gate_error.value
                failure_category = CHAT_FAILURE_PROVIDER
                return self._failure(
                    request,
                    outcome=AiCoachOutcome.UNAVAILABLE,
                    safety=safety,
                    failure_category=failure_category,
                )
            if self.cooldown.active():
                error_code = ProviderErrorCode.COOLDOWN_ACTIVE.value
                failure_category = CHAT_FAILURE_PROVIDER
                return self._failure(
                    request,
                    outcome=AiCoachOutcome.UNAVAILABLE,
                    safety=safety,
                    failure_category=failure_category,
                )
            if not self.quota.reserve(user_key):
                error_code = "quota_exhausted"
                failure_category = CHAT_FAILURE_RATE_LIMITED
                return self._failure(
                    request,
                    outcome=AiCoachOutcome.RATE_LIMITED,
                    safety=safety,
                    failure_category=failure_category,
                )

            try:
                result, attempts, recovered_failure = self._call_provider(request, context_refs)
            except _ChatProviderFailure as failure:
                attempts = failure.attempts
                error_code = failure.error.code.value
                provider_failure_reason = failure.error.provider_failure_reason
                http_status = failure.error.http_status
                finish_reason = failure.error.finish_reason
                provider_response_bytes = failure.error.response_bytes
                response_payload_type = failure.error.response_payload_type
                choices_count = failure.error.choices_count
                choices_item_type = failure.error.choices_item_type
                message_present = failure.error.message_present
                message_type = failure.error.message_type
                refusal_present = failure.error.refusal_present
                content_present = failure.error.content_present
                content_type = failure.error.content_type
                usage = failure.error.usage
                self.cooldown.mark(failure.error)
                if failure.error.code == ProviderErrorCode.RATE_LIMITED:
                    outcome = AiCoachOutcome.RATE_LIMITED
                    failure_category = CHAT_FAILURE_RATE_LIMIT
                elif failure.error.code == ProviderErrorCode.INVALID_OUTPUT:
                    outcome = AiCoachOutcome.INVALID_OUTPUT
                    failure_category = CHAT_FAILURE_PROVIDER
                elif failure.error.code == ProviderErrorCode.TIMEOUT:
                    outcome = AiCoachOutcome.UNAVAILABLE
                    failure_category = CHAT_FAILURE_TIMEOUT
                elif failure.error.code in {
                    ProviderErrorCode.PROVIDER_UNAVAILABLE,
                    ProviderErrorCode.AUTHENTICATION_FAILED,
                    ProviderErrorCode.REQUEST_REJECTED,
                    ProviderErrorCode.DISABLED,
                }:
                    outcome = AiCoachOutcome.UNAVAILABLE
                    failure_category = CHAT_FAILURE_PROVIDER
                else:
                    outcome = AiCoachOutcome.UNAVAILABLE
                    failure_category = CHAT_FAILURE_GENERATION
                return self._failure(
                    request,
                    outcome=outcome,
                    safety=safety,
                    failure_category=failure_category,
                    provider_failure_reason=provider_failure_reason,
                )

            if recovered_failure is not None:
                provider_failure_reason = recovered_failure.provider_failure_reason
                http_status = recovered_failure.http_status
                finish_reason = recovered_failure.finish_reason
                provider_response_bytes = recovered_failure.response_bytes
                response_payload_type = recovered_failure.response_payload_type
                choices_count = recovered_failure.choices_count
                choices_item_type = recovered_failure.choices_item_type
                message_present = recovered_failure.message_present
                message_type = recovered_failure.message_type
                refusal_present = recovered_failure.refusal_present
                content_present = recovered_failure.content_present
                content_type = recovered_failure.content_type

            provider_name = result.provider
            configured_model = result.configured_model
            actual_model = result.actual_model
            usage = result.usage
            if recovered_failure is None:
                http_status = result.http_status
                finish_reason = result.finish_reason
            provider_response_bytes = result.response_bytes
            inspection = inspect_chat_output(
                result.response.answer,
                data_class=request.data_class,
                locale=request.locale,
            )
            if inspection.reason is None:
                answer = inspection.normalized
            else:
                validation_failure_reason = inspection.reason
            if inspection.reason is not None and inspection.safety_category is not None:
                error_code = ProviderErrorCode.INVALID_OUTPUT.value
                outcome = AiCoachOutcome.SAFETY_REFUSAL
                safety = inspection.safety_category
                failure_category = CHAT_FAILURE_SAFETY_REJECTION
                return self._failure(
                    request,
                    outcome=outcome,
                    safety=safety,
                    failure_category=failure_category,
                    answer=refusal_text(safety, locale=request.locale),
                    validation_failure_reason=inspection.reason,
                )
            elif inspection.reason is not None:
                error_code = ProviderErrorCode.INVALID_OUTPUT.value
                answer = sanitize_chat_output(
                    result.response.answer,
                    data_class=request.data_class,
                    locale=request.locale,
                )
                if answer is None:
                    repair_attempted = True
                    try:
                        repaired, _ = self._call_repair(
                            request,
                            result.response.answer,
                            inspection.reason or ChatOutputValidationReason.OTHER,
                        )
                    except _ChatProviderFailure as failure:
                        error_code = failure.error.code.value
                        provider_failure_reason = failure.error.provider_failure_reason
                        http_status = failure.error.http_status
                        finish_reason = failure.error.finish_reason
                        provider_response_bytes = failure.error.response_bytes
                        response_payload_type = failure.error.response_payload_type
                        choices_count = failure.error.choices_count
                        choices_item_type = failure.error.choices_item_type
                        message_present = failure.error.message_present
                        message_type = failure.error.message_type
                        refusal_present = failure.error.refusal_present
                        content_present = failure.error.content_present
                        content_type = failure.error.content_type
                        usage = failure.error.usage
                        outcome = AiCoachOutcome.INVALID_OUTPUT
                        failure_category = CHAT_FAILURE_REPAIR_FAILED
                        return self._failure(
                            request,
                            outcome=outcome,
                            safety=safety,
                            failure_category=failure_category,
                            repair_attempted=repair_attempted,
                            validation_failure_reason=validation_failure_reason,
                            provider_failure_reason=provider_failure_reason,
                        )
                    provider_name = repaired.provider
                    configured_model = repaired.configured_model
                    actual_model = repaired.actual_model
                    usage = repaired.usage
                    http_status = repaired.http_status
                    finish_reason = repaired.finish_reason
                    provider_response_bytes = repaired.response_bytes
                    repaired_inspection = inspect_chat_output(
                        repaired.response.answer,
                        data_class=request.data_class,
                        locale=request.locale,
                    )
                    if repaired_inspection.safety_category is not None:
                        error_code = ProviderErrorCode.INVALID_OUTPUT.value
                        outcome = AiCoachOutcome.SAFETY_REFUSAL
                        safety = repaired_inspection.safety_category
                        validation_failure_reason = repaired_inspection.reason
                        failure_category = CHAT_FAILURE_SAFETY_REJECTION
                        return self._failure(
                            request,
                            outcome=outcome,
                            safety=safety,
                            failure_category=failure_category,
                            answer=refusal_text(safety, locale=request.locale),
                            repair_attempted=repair_attempted,
                            validation_failure_reason=validation_failure_reason,
                        )
                    if repaired_inspection.reason is not None:
                        bounded_repair = bound_safe_chat_output(
                            repaired.response.answer,
                            data_class=request.data_class,
                            locale=request.locale,
                        )
                        if bounded_repair is None:
                            validation_failure_reason = repaired_inspection.reason
                            outcome = AiCoachOutcome.INVALID_OUTPUT
                            failure_category = CHAT_FAILURE_REPAIR_FAILED
                            return self._failure(
                                request,
                                outcome=outcome,
                                safety=safety,
                                failure_category=failure_category,
                                repair_attempted=repair_attempted,
                                validation_failure_reason=validation_failure_reason,
                            )
                        answer = bounded_repair
                    else:
                        answer = repaired_inspection.normalized
                    repair_success = True
            self.cooldown.reset()
            outcome = AiCoachOutcome.ANSWER
            citations = self._citations(context_refs)
            if request.data_class == AiCoachDataClass.PERSONALIZED:
                limitations = (
                    (_PERSONAL_LIMITATION,) if context_refs else (_PERSONAL_NO_CONTEXT_LIMITATION,)
                )
            else:
                limitations = (_GENERIC_LIMITATION,) if context_refs else (_GENERAL_LIMITATION,)
            return AiCoachChatGeneration(
                outcome=outcome,
                answer=answer,
                citations=citations,
                limitations=limitations,
                safety_category=safety,
                failure_category=None,
                prompt_version=AI_COACH_CHAT_PROMPT_VERSION,
                data_class=request.data_class,
                repair_attempted=repair_attempted,
                repair_success=repair_success,
                validation_failure_reason=validation_failure_reason,
                provider_failure_reason=provider_failure_reason,
            )
        finally:
            logger.info(
                "ai_coach_chat_generation",
                extra={
                    "request_id": request_id,
                    "job": request.job.value,
                    "request_type": request.job.value,
                    "data_class": request.data_class.value,
                    "context_kind": request.context_kind.value,
                    "prompt_version": AI_COACH_CHAT_PROMPT_VERSION,
                    "schema_version": AI_COACH_CHAT_OUTPUT_VERSION,
                    "policy_revision": settings.ai_coach_policy_revision,
                    "provider": provider_name,
                    "configured_model": configured_model,
                    "actual_model": actual_model,
                    "outcome": outcome.value,
                    "generation_success": outcome == AiCoachOutcome.ANSWER,
                    "repair_attempted": repair_attempted,
                    "repair_success": repair_success,
                    "validation_failure_reason": (
                        validation_failure_reason.value
                        if validation_failure_reason is not None
                        else None
                    ),
                    "provider_failure_reason": (
                        provider_failure_reason.value
                        if provider_failure_reason is not None
                        else None
                    ),
                    "safety_category": safety.value,
                    "error_code": error_code,
                    "failure_category": failure_category,
                    "attempts": attempts,
                    "retry_count": max(0, attempts - 1),
                    "history_count": len(request.conversation_history),
                    "context_count": len(context_refs),
                    "latency_ms": max(0, round((time.monotonic() - started) * 1000)),
                    "prompt_tokens": usage.prompt_tokens if usage is not None else None,
                    "completion_tokens": usage.completion_tokens if usage is not None else None,
                    "total_tokens": usage.total_tokens if usage is not None else None,
                    "reasoning_tokens": usage.reasoning_tokens if usage is not None else None,
                    "http_status": http_status,
                    "finish_reason": finish_reason,
                    "provider_response_bytes": provider_response_bytes,
                    "response_payload_type": response_payload_type,
                    "choices_count": choices_count,
                    "choices_item_type": choices_item_type,
                    "message_present": message_present,
                    "message_type": message_type,
                    "refusal_present": refusal_present,
                    "content_present": content_present,
                    "content_type": content_type,
                },
            )

    def _provider_gate(
        self,
        data_class: AiCoachDataClass,
    ) -> ProviderErrorCode | None:
        if settings.ai_coach_provider != "groq":
            return ProviderErrorCode.DISABLED
        if not _safe_groq_route():
            return ProviderErrorCode.POLICY_BLOCKED
        if settings.ai_coach_model != "openai/gpt-oss-120b":
            return ProviderErrorCode.POLICY_BLOCKED
        if settings.ai_coach_cost_policy != "free_only" or settings.ai_coach_cost_class != "free":
            return ProviderErrorCode.POLICY_BLOCKED
        if settings.ai_coach_data_policy != "verified_generic_only":
            return ProviderErrorCode.POLICY_BLOCKED
        if data_class == AiCoachDataClass.PERSONALIZED:
            if not settings.ai_coach_personal_enabled:
                return ProviderErrorCode.DISABLED
            if settings.ai_coach_personal_data_policy != "verified_personal_user":
                return ProviderErrorCode.POLICY_BLOCKED
        if not settings.groq_api_key.get_secret_value().strip():
            return ProviderErrorCode.DISABLED
        return None

    def _call_provider(
        self,
        request: AiCoachChatRequest,
        context_refs: tuple[ContextRef, ...],
    ) -> tuple[ProviderTextResult, int, NormalizedProviderError | None]:
        max_attempts = max(1, min(2, settings.ai_coach_max_attempts))
        attempts = 0
        recovered_failure: NormalizedProviderError | None = None
        while attempts < max_attempts:
            attempts += 1
            try:
                provider_request = (
                    request
                    if attempts == 1
                    or recovered_failure is None
                    or recovered_failure.provider_failure_reason
                    != ProviderFailureReason.FINISH_REASON_LENGTH
                    else request.model_copy(update={"retry_hint": True})
                )
                result = self.provider.generate_text(provider_request, context_refs)
                if not isinstance(result, ProviderTextResult):
                    raise NormalizedProviderError(
                        ProviderErrorCode.INVALID_OUTPUT,
                        provider_failure_reason=ProviderFailureReason.INVALID_PROVIDER_PAYLOAD,
                    )
                return result, attempts, recovered_failure
            except NormalizedProviderError as exc:
                length_retry = (
                    exc.provider_failure_reason == ProviderFailureReason.FINISH_REASON_LENGTH
                    and attempts < 2
                )
                if (exc.retryable and attempts < max_attempts) or length_retry:
                    recovered_failure = exc
                    continue
                raise _ChatProviderFailure(exc, attempts) from exc
            except Exception as exc:
                raise _ChatProviderFailure(
                    NormalizedProviderError(
                        ProviderErrorCode.PROVIDER_UNAVAILABLE,
                        provider_failure_reason=ProviderFailureReason.UNKNOWN,
                    ),
                    attempts,
                ) from exc
        raise _ChatProviderFailure(
            NormalizedProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                provider_failure_reason=ProviderFailureReason.UNKNOWN,
            ),
            attempts,
        )

    def _call_repair(
        self,
        request: AiCoachChatRequest,
        answer: str,
        reason: ChatOutputValidationReason,
    ) -> tuple[ProviderTextResult, int]:
        """Call the provider repair path exactly once, without retrying untrusted text."""

        try:
            result = self.provider.repair_text(request, answer, reason)
            if not isinstance(result, ProviderTextResult):
                raise NormalizedProviderError(
                    ProviderErrorCode.INVALID_OUTPUT,
                    provider_failure_reason=ProviderFailureReason.INVALID_PROVIDER_PAYLOAD,
                )
            return result, 1
        except NormalizedProviderError as exc:
            raise _ChatProviderFailure(exc, 1) from exc
        except Exception as exc:
            raise _ChatProviderFailure(
                NormalizedProviderError(
                    ProviderErrorCode.PROVIDER_UNAVAILABLE,
                    provider_failure_reason=ProviderFailureReason.UNKNOWN,
                ),
                1,
            ) from exc

    @staticmethod
    def _citations(context_refs: tuple[ContextRef, ...]) -> tuple[AiCoachCitation, ...]:
        citations: list[AiCoachCitation] = []
        seen: set[str] = set()
        for ref in context_refs:
            for citation in ref.citations:
                if citation.source_type == "personal_tool_screen":
                    continue
                url = str(citation.url)
                path = urlparse(url).path.rstrip("/") or "/"
                if any(
                    path == route or path.startswith(f"{route}/") for route in _INTERNAL_APP_PATHS
                ):
                    continue
                if url in seen:
                    continue
                seen.add(url)
                citations.append(AiCoachCitation.model_validate(citation.model_dump()))
                if len(citations) >= 12:
                    return tuple(citations)
        return tuple(citations)

    @staticmethod
    def _failure(
        request: AiCoachChatRequest,
        *,
        outcome: AiCoachOutcome,
        safety: SafetyCategory,
        failure_category: str,
        answer: str | None = None,
        repair_attempted: bool = False,
        repair_success: bool = False,
        validation_failure_reason: ChatOutputValidationReason | None = None,
        provider_failure_reason: ProviderFailureReason | None = None,
    ) -> AiCoachChatGeneration:
        copy = (
            {
                CHAT_FAILURE_PROVIDER: "AI Coach временно недоступен. Попробуйте ещё раз позже.",
                CHAT_FAILURE_STRUCTURED_VALIDATION: "Не удалось безопасно проверить ответ. Попробуйте ещё раз.",
                CHAT_FAILURE_SAFETY_REJECTION: "Я не могу помочь с этим запросом в таком виде.",
                CHAT_FAILURE_REPAIR_FAILED: "Не удалось сформировать ответ. Повторить.",
                CHAT_FAILURE_PRESENTATION_VALIDATION: "Не удалось сформировать ответ. Повторить.",
                CHAT_FAILURE_INTERNAL_ERROR: "Не удалось сформировать ответ. Повторить.",
                CHAT_FAILURE_TIMEOUT: "Ответ занял слишком много времени. Попробуйте ещё раз.",
                CHAT_FAILURE_CONTEXT: "Не удалось получить материалы для ответа. Попробуйте ещё раз.",
                CHAT_FAILURE_GENERATION: "Не удалось получить проверенный ответ. Попробуйте ещё раз.",
                CHAT_FAILURE_RATE_LIMIT: "Лимит AI Coach исчерпан. Попробуйте позже.",
            }
            if request.locale == "ru"
            else {
                CHAT_FAILURE_PROVIDER: "AI Coach is temporarily unavailable. Please try again later.",
                CHAT_FAILURE_STRUCTURED_VALIDATION: "The answer could not be checked safely. Please try again.",
                CHAT_FAILURE_SAFETY_REJECTION: "I can't help with this request in its current form.",
                CHAT_FAILURE_REPAIR_FAILED: "A usable answer could not be generated. Try again.",
                CHAT_FAILURE_PRESENTATION_VALIDATION: "A usable answer could not be generated. Try again.",
                CHAT_FAILURE_INTERNAL_ERROR: "A usable answer could not be generated. Try again.",
                CHAT_FAILURE_TIMEOUT: "The answer took too long. Please try again.",
                CHAT_FAILURE_CONTEXT: "The approved materials could not be loaded. Please try again.",
                CHAT_FAILURE_GENERATION: "A verified answer could not be generated. Please try again.",
                CHAT_FAILURE_RATE_LIMIT: "The AI Coach limit has been reached. Please try again later.",
            }
        )
        return AiCoachChatGeneration(
            outcome=outcome,
            answer=answer,
            citations=(),
            limitations=(copy[failure_category],),
            safety_category=safety,
            failure_category=failure_category,
            prompt_version=AI_COACH_CHAT_PROMPT_VERSION,
            data_class=request.data_class,
            repair_attempted=repair_attempted,
            repair_success=repair_success,
            validation_failure_reason=validation_failure_reason,
            provider_failure_reason=provider_failure_reason,
        )


ai_coach_chat_service = AiCoachChatService()

__all__ = [
    "CHAT_FAILURE_CONTEXT",
    "CHAT_FAILURE_GENERATION",
    "CHAT_FAILURE_INTERNAL_ERROR",
    "CHAT_FAILURE_PRESENTATION_VALIDATION",
    "CHAT_FAILURE_PROVIDER",
    "CHAT_FAILURE_RATE_LIMIT",
    "CHAT_FAILURE_RATE_LIMITED",
    "CHAT_FAILURE_REPAIR_FAILED",
    "CHAT_FAILURE_SAFETY_REJECTION",
    "CHAT_FAILURE_STRUCTURED_VALIDATION",
    "CHAT_FAILURE_TIMEOUT",
    "AiCoachChatGeneration",
    "AiCoachChatService",
    "ai_coach_chat_service",
]
