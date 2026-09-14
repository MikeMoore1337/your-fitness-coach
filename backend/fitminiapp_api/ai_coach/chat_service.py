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
    ContextRef,
    NormalizedProviderError,
    ProviderErrorCode,
    ProviderTextResult,
)
from fitminiapp_api.ai_coach.providers import GroqDirectAdapter
from fitminiapp_api.ai_coach.safety import (
    SafetyCategory,
    classify_message,
    refusal_text,
    safe_chat_fallback,
    validate_chat_output,
)
from fitminiapp_api.core.config import settings

logger = logging.getLogger("app.ai_coach")

CHAT_FAILURE_PROVIDER = "provider_failure"
CHAT_FAILURE_STRUCTURED_VALIDATION = "structured_validation"
CHAT_FAILURE_TIMEOUT = "timeout"
CHAT_FAILURE_CONTEXT = "context_failure"
CHAT_FAILURE_GENERATION = "generation_failure"
CHAT_FAILURE_RATE_LIMITED = "rate_limited"

_GENERIC_LIMITATION = (
    "Ответ основан на проверенных материалах YFC и не является персональным назначением."
)
_PERSONAL_LIMITATION = (
    "Ответ основан только на разрешённом срезе ваших данных; AI Coach не изменяет "
    "программу, цели или расписание."
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

    def active(self) -> bool:
        with self._lock:
            if self._clock() >= self._until:
                self._until = 0.0
                return False
            return True

    def mark(self, error: NormalizedProviderError) -> None:
        if error.code in {
            ProviderErrorCode.DISABLED,
            ProviderErrorCode.REQUEST_REJECTED,
            ProviderErrorCode.INVALID_OUTPUT,
        }:
            return
        delay = error.retry_after_seconds or settings.ai_coach_cooldown_seconds
        with self._lock:
            self._until = max(self._until, self._clock() + max(1, min(delay, 3600)))

    def reset(self) -> None:
        with self._lock:
            self._until = 0.0


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
        ):
            safety = SafetyCategory.CLEAR
        attempts = 0
        provider_name: str | None = None
        configured_model: str | None = None
        actual_model: str | None = None
        usage = None
        outcome = AiCoachOutcome.UNAVAILABLE
        error_code: str | None = None
        failure_category: str | None = None
        try:
            if safety != SafetyCategory.CLEAR:
                outcome = AiCoachOutcome.SAFETY_REFUSAL
                return AiCoachChatGeneration(
                    outcome=outcome,
                    answer=refusal_text(safety),
                    citations=(),
                    limitations=(),
                    safety_category=safety,
                    failure_category=None,
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
            if not context_refs:
                error_code = "context_unavailable"
                failure_category = CHAT_FAILURE_CONTEXT
                outcome = AiCoachOutcome.INSUFFICIENT_DATA
                return self._failure(
                    request,
                    outcome=outcome,
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
                result, attempts = self._call_provider(request, context_refs)
            except _ChatProviderFailure as failure:
                attempts = failure.attempts
                error_code = failure.error.code.value
                self.cooldown.mark(failure.error)
                if failure.error.code == ProviderErrorCode.RATE_LIMITED:
                    outcome = AiCoachOutcome.RATE_LIMITED
                    failure_category = CHAT_FAILURE_RATE_LIMITED
                elif failure.error.code == ProviderErrorCode.INVALID_OUTPUT:
                    outcome = AiCoachOutcome.INVALID_OUTPUT
                    failure_category = CHAT_FAILURE_STRUCTURED_VALIDATION
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
                )

            provider_name = result.provider
            configured_model = result.configured_model
            actual_model = result.actual_model
            usage = result.usage
            try:
                answer = validate_chat_output(
                    result.response.answer,
                    data_class=request.data_class,
                )
            except ValueError:
                error_code = ProviderErrorCode.INVALID_OUTPUT.value
                outcome = AiCoachOutcome.INVALID_OUTPUT
                failure_category = CHAT_FAILURE_STRUCTURED_VALIDATION
                return self._failure(
                    request,
                    outcome=outcome,
                    safety=safety,
                    failure_category=failure_category,
                    answer=safe_chat_fallback(
                        result.response.answer,
                        data_class=request.data_class,
                    ),
                )
            self.cooldown.reset()
            outcome = AiCoachOutcome.ANSWER
            citations = self._citations(context_refs)
            limitations = (
                (_PERSONAL_LIMITATION,)
                if request.data_class == AiCoachDataClass.PERSONALIZED
                else (_GENERIC_LIMITATION,)
            )
            return AiCoachChatGeneration(
                outcome=outcome,
                answer=answer,
                citations=citations,
                limitations=limitations,
                safety_category=safety,
                failure_category=None,
                prompt_version=AI_COACH_CHAT_PROMPT_VERSION,
                data_class=request.data_class,
            )
        finally:
            logger.info(
                "ai_coach_chat_generation",
                extra={
                    "request_id": request_id,
                    "job": request.job.value,
                    "data_class": request.data_class.value,
                    "prompt_version": AI_COACH_CHAT_PROMPT_VERSION,
                    "schema_version": AI_COACH_CHAT_OUTPUT_VERSION,
                    "policy_revision": settings.ai_coach_policy_revision,
                    "provider": provider_name,
                    "configured_model": configured_model,
                    "actual_model": actual_model,
                    "outcome": outcome.value,
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
    ) -> tuple[ProviderTextResult, int]:
        max_attempts = (
            1
            if request.data_class == AiCoachDataClass.PERSONALIZED
            else settings.ai_coach_max_attempts
        )
        attempts = 0
        while attempts < max_attempts:
            attempts += 1
            try:
                result = self.provider.generate_text(request, context_refs)
                if not isinstance(result, ProviderTextResult):
                    raise NormalizedProviderError(ProviderErrorCode.INVALID_OUTPUT)
                return result, attempts
            except NormalizedProviderError as exc:
                if exc.retryable and attempts < max_attempts:
                    continue
                raise _ChatProviderFailure(exc, attempts) from exc
            except Exception as exc:
                raise _ChatProviderFailure(
                    NormalizedProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE),
                    attempts,
                ) from exc
        raise _ChatProviderFailure(
            NormalizedProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE),
            attempts,
        )

    @staticmethod
    def _citations(context_refs: tuple[ContextRef, ...]) -> tuple[AiCoachCitation, ...]:
        citations: list[AiCoachCitation] = []
        seen: set[str] = set()
        for ref in context_refs:
            for citation in ref.citations:
                url = str(citation.url)
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
    ) -> AiCoachChatGeneration:
        copy = {
            CHAT_FAILURE_PROVIDER: "AI Coach временно недоступен. Попробуйте ещё раз позже.",
            CHAT_FAILURE_STRUCTURED_VALIDATION: "Не удалось безопасно проверить ответ. Попробуйте ещё раз.",
            CHAT_FAILURE_TIMEOUT: "Ответ занял слишком много времени. Попробуйте ещё раз.",
            CHAT_FAILURE_CONTEXT: "Для этого вопроса пока нет подходящего проверенного контекста YFC.",
            CHAT_FAILURE_GENERATION: "Не удалось получить проверенный ответ. Попробуйте ещё раз.",
            CHAT_FAILURE_RATE_LIMITED: "Лимит AI Coach исчерпан. Попробуйте позже.",
        }
        return AiCoachChatGeneration(
            outcome=outcome,
            answer=answer,
            citations=(),
            limitations=(copy[failure_category],),
            safety_category=safety,
            failure_category=failure_category,
            prompt_version=AI_COACH_CHAT_PROMPT_VERSION,
            data_class=request.data_class,
        )


ai_coach_chat_service = AiCoachChatService()

__all__ = [
    "CHAT_FAILURE_CONTEXT",
    "CHAT_FAILURE_GENERATION",
    "CHAT_FAILURE_PROVIDER",
    "CHAT_FAILURE_RATE_LIMITED",
    "CHAT_FAILURE_STRUCTURED_VALIDATION",
    "CHAT_FAILURE_TIMEOUT",
    "AiCoachChatGeneration",
    "AiCoachChatService",
    "ai_coach_chat_service",
]
