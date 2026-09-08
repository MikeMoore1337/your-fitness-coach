"""Application orchestration for the generic-only AI Coach beta core."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from fitminiapp_api.ai_coach.contracts import (
    AI_COACH_PERSONAL_PROMPT_VERSION,
    AI_COACH_PROMPT_VERSION,
    AI_COACH_SCHEMA_VERSION,
    AiCoachCitation,
    AiCoachDataClass,
    AiCoachJob,
    AiCoachOutcome,
    AiCoachPolicy,
    AiCoachRequest,
    AiCoachResponse,
    ContextRef,
    LlmPort,
    NormalizedProviderError,
    ProviderErrorCode,
    ProviderResult,
)
from fitminiapp_api.ai_coach.providers import GroqDirectAdapter
from fitminiapp_api.ai_coach.retrieval import ContextUnavailable, ContextUnsafe, retrieve_context
from fitminiapp_api.ai_coach.safety import (
    SafetyCategory,
    classify_request,
    refusal_text,
    validate_provider_output,
)
from fitminiapp_api.core.config import settings

logger = logging.getLogger("app.ai_coach")

_GENERIC_LIMITATION = "Ответ основан только на проверенном публичном материале и не является персональным назначением."
_PERSONAL_LIMITATION = (
    "Ответ основан только на вашей ограниченной структурированной сводке за выбранный "
    "период; AI Coach не делает персональных назначений."
)
_UNAVAILABLE_LIMITATION = (
    "AI Coach сейчас недоступен; основные функции приложения продолжают работать."
)
_INSUFFICIENT_LIMITATION = "Для этого запроса нет опубликованного и актуального контекста."
_INVALID_OUTPUT_LIMITATION = "Ответ не прошёл проверку безопасности и формата. Попробуйте позже."
_RATE_LIMITED_LIMITATION = "Лимит AI Coach исчерпан. Попробуйте позже."


@dataclass(frozen=True)
class ProviderCapability:
    provider: str
    model: str
    cost_class: str
    data_policy: str
    policy_revision: str
    structured_output: bool
    enabled: bool


@dataclass
class _WindowQuota:
    started_at: float
    global_count: int
    per_user_count: dict[str, int]


class InMemoryAiCoachQuota:
    """Bounded process-local quota; no identity or content is sent to the provider."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._window = _WindowQuota(started_at=clock(), global_count=0, per_user_count={})

    def reserve(self, user_key: str) -> bool:
        now = self._clock()
        with self._lock:
            if now - self._window.started_at >= settings.ai_coach_quota_window_seconds:
                self._window = _WindowQuota(
                    started_at=now,
                    global_count=0,
                    per_user_count={},
                )
            if self._window.global_count >= settings.ai_coach_global_request_limit:
                return False
            user_count = self._window.per_user_count.get(user_key, 0)
            if user_count >= settings.ai_coach_per_user_request_limit:
                return False
            self._window.global_count += 1
            self._window.per_user_count[user_key] = user_count + 1
            if len(self._window.per_user_count) > 10_000:
                least_used = min(
                    self._window.per_user_count,
                    key=lambda item: self._window.per_user_count[item],
                )
                del self._window.per_user_count[least_used]
            return True

    def reset(self) -> None:
        with self._lock:
            self._window = _WindowQuota(started_at=self._clock(), global_count=0, per_user_count={})


class ProviderCooldown:
    """Small circuit breaker with an explicit cooldown reason and no busy retry loop."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._until = 0.0
        self._reason = ""

    def active(self) -> bool:
        with self._lock:
            if self._clock() >= self._until:
                self._until = 0.0
                self._reason = ""
                return False
            return True

    def mark(self, error: NormalizedProviderError) -> None:
        if error.code in {
            ProviderErrorCode.DISABLED,
            ProviderErrorCode.REQUEST_REJECTED,
            ProviderErrorCode.INVALID_OUTPUT,
        }:
            return
        cooldown = error.retry_after_seconds or settings.ai_coach_cooldown_seconds
        cooldown = max(1, min(cooldown, 3600))
        with self._lock:
            self._until = max(self._until, self._clock() + cooldown)
            self._reason = error.code.value

    def reset(self) -> None:
        with self._lock:
            self._until = 0.0
            self._reason = ""


class _ProviderCallFailure(RuntimeError):
    def __init__(self, error: NormalizedProviderError, attempts: int) -> None:
        super().__init__(error.code.value)
        self.error = error
        self.attempts = attempts


def _policy_for(request: AiCoachRequest) -> AiCoachPolicy:
    prompt_version = (
        AI_COACH_PERSONAL_PROMPT_VERSION
        if request.data_class == AiCoachDataClass.PERSONALIZED
        else AI_COACH_PROMPT_VERSION
    )
    return AiCoachPolicy(
        job=request.job,
        data_class=request.data_class,
        prompt_version=prompt_version,
        schema_version=AI_COACH_SCHEMA_VERSION,
        locale=request.locale,
    )


def _prompt_version_for(request: AiCoachRequest) -> str:
    return (
        AI_COACH_PERSONAL_PROMPT_VERSION
        if request.data_class == AiCoachDataClass.PERSONALIZED
        else AI_COACH_PROMPT_VERSION
    )


def _provider_capability() -> ProviderCapability:
    return ProviderCapability(
        provider=settings.ai_coach_provider,
        model=settings.ai_coach_model,
        cost_class=settings.ai_coach_cost_class,
        data_policy=settings.ai_coach_data_policy,
        policy_revision=settings.ai_coach_policy_revision,
        structured_output=settings.ai_coach_structured_output,
        enabled=settings.ai_coach_enabled and not settings.ai_coach_kill_switch,
    )


def _safe_groq_route() -> bool:
    parsed = urlparse(settings.ai_coach_endpoint)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "api.groq.com"
        and parsed.path == "/openai/v1/chat/completions"
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )


class AiCoachService:
    """One bounded generation path; the route cannot load personalized data."""

    def __init__(
        self,
        *,
        provider: LlmPort | None = None,
        quota: InMemoryAiCoachQuota | None = None,
        cooldown: ProviderCooldown | None = None,
    ) -> None:
        self.provider = provider or GroqDirectAdapter()
        self.quota = quota or InMemoryAiCoachQuota()
        self.cooldown = cooldown or ProviderCooldown()

    def reset_runtime_state(self) -> None:
        self.quota.reset()
        self.cooldown.reset()

    def generate(
        self,
        *,
        db: Session,
        request: AiCoachRequest,
        user_key: str,
        request_id: str | None,
        context_refs: tuple[ContextRef, ...] | None = None,
    ) -> AiCoachResponse:
        started = time.monotonic()
        safety = classify_request(request)
        attempts = 0
        provider_name: str | None = None
        configured_model: str | None = None
        actual_model: str | None = None
        usage = None
        outcome = AiCoachOutcome.UNAVAILABLE
        error_code: str | None = None
        try:
            if safety != SafetyCategory.CLEAR:
                outcome = AiCoachOutcome.SAFETY_REFUSAL
                return self._safety_response(request, request_id, safety)
            if request.data_class not in {
                AiCoachDataClass.GENERIC,
                AiCoachDataClass.PERSONALIZED,
            }:
                error_code = ProviderErrorCode.POLICY_BLOCKED.value
                return self._unavailable_response(request, request_id, safety)
            if not settings.ai_coach_enabled or settings.ai_coach_kill_switch:
                error_code = ProviderErrorCode.DISABLED.value
                return self._unavailable_response(request, request_id, safety)

            policy = _policy_for(request)
            resolved_context_refs = (
                context_refs
                if request.data_class == AiCoachDataClass.PERSONALIZED
                else retrieve_context(db, request)
            )
            if not resolved_context_refs:
                outcome = AiCoachOutcome.INSUFFICIENT_DATA
                return self._insufficient_response(request, request_id, safety)

            capability = _provider_capability()
            provider_name = capability.provider or None
            configured_model = capability.model or None
            gate_error = self._provider_gate(capability, policy)
            if gate_error is not None:
                error_code = gate_error.value
                return self._unavailable_response(request, request_id, safety)
            if self.cooldown.active():
                error_code = ProviderErrorCode.COOLDOWN_ACTIVE.value
                return self._unavailable_response(request, request_id, safety)
            if not self.quota.reserve(user_key):
                outcome = AiCoachOutcome.RATE_LIMITED
                error_code = "quota_exhausted"
                return self._rate_limited_response(request, request_id, safety)

            try:
                result, attempts = self._call_provider(request, policy, resolved_context_refs)
            except _ProviderCallFailure as failure:
                attempts = failure.attempts
                error_code = failure.error.code.value
                self.cooldown.mark(failure.error)
                if failure.error.code == ProviderErrorCode.RATE_LIMITED:
                    outcome = AiCoachOutcome.RATE_LIMITED
                    return self._rate_limited_response(request, request_id, safety)
                if failure.error.code == ProviderErrorCode.INVALID_OUTPUT:
                    outcome = AiCoachOutcome.INVALID_OUTPUT
                    return self._invalid_output_response(request, request_id, safety)
                return self._unavailable_response(request, request_id, safety)

            provider_name = result.provider
            configured_model = result.configured_model
            actual_model = result.actual_model
            usage = result.usage
            try:
                validate_provider_output(
                    result.response,
                    allowed_ref_ids=frozenset(ref.ref_id for ref in resolved_context_refs),
                    data_class=request.data_class,
                )
            except ValueError:
                error_code = ProviderErrorCode.INVALID_OUTPUT.value
                outcome = AiCoachOutcome.INVALID_OUTPUT
                return self._invalid_output_response(request, request_id, safety)
            self.cooldown.reset()
            outcome = AiCoachOutcome.ANSWER
            return self._answer_response(request, request_id, safety, result, resolved_context_refs)
        except ContextUnsafe:
            safety = SafetyCategory.PROMPT_INJECTION
            error_code = "context_safety_blocked"
            outcome = AiCoachOutcome.SAFETY_REFUSAL
            return self._safety_response(request, request_id, safety)
        except ContextUnavailable:
            error_code = "context_unavailable"
            return self._unavailable_response(request, request_id, safety)
        finally:
            logger.info(
                "ai_coach_generation",
                extra={
                    "request_id": request_id,
                    "job": request.job.value,
                    "data_class": request.data_class.value,
                    "tool_name": request.tool_name.value if request.tool_name else None,
                    "prompt_version": _prompt_version_for(request),
                    "schema_version": AI_COACH_SCHEMA_VERSION,
                    "policy_revision": settings.ai_coach_policy_revision,
                    "provider": provider_name,
                    "configured_model": configured_model,
                    "actual_model": actual_model,
                    "outcome": outcome.value,
                    "safety_category": safety.value,
                    "error_code": error_code,
                    "attempts": attempts,
                    "retry_count": max(0, attempts - 1),
                    "latency_ms": max(0, round((time.monotonic() - started) * 1000)),
                    "prompt_tokens": usage.prompt_tokens if usage is not None else None,
                    "completion_tokens": usage.completion_tokens if usage is not None else None,
                    "total_tokens": usage.total_tokens if usage is not None else None,
                    "cost_microunits": usage.cost_microunits if usage is not None else None,
                },
            )

    def _provider_gate(
        self,
        capability: ProviderCapability,
        policy: AiCoachPolicy,
    ) -> ProviderErrorCode | None:
        if not capability.enabled or capability.provider == "disabled":
            return ProviderErrorCode.DISABLED
        if policy.data_class == AiCoachDataClass.PERSONALIZED:
            if not settings.ai_coach_personal_enabled:
                return ProviderErrorCode.DISABLED
            if settings.ai_coach_personal_data_policy != "verified_personal_user":
                return ProviderErrorCode.POLICY_BLOCKED
            if policy.job != AiCoachJob.METRIC_EXPLANATION:
                return ProviderErrorCode.POLICY_BLOCKED
        elif policy.data_class != AiCoachDataClass.GENERIC:
            return ProviderErrorCode.POLICY_BLOCKED
        if capability.provider != "groq" or not _safe_groq_route():
            return ProviderErrorCode.POLICY_BLOCKED
        if capability.model != "openai/gpt-oss-120b":
            return ProviderErrorCode.POLICY_BLOCKED
        if policy.cost_policy != "free_only" or capability.cost_class != "free":
            return ProviderErrorCode.POLICY_BLOCKED
        if capability.data_policy != "verified_generic_only":
            return ProviderErrorCode.POLICY_BLOCKED
        if not capability.structured_output:
            return ProviderErrorCode.POLICY_BLOCKED
        if not settings.groq_api_key.get_secret_value().strip():
            return ProviderErrorCode.DISABLED
        return None

    def _call_provider(
        self,
        request: AiCoachRequest,
        policy: AiCoachPolicy,
        context_refs: tuple[ContextRef, ...],
    ) -> tuple[ProviderResult, int]:
        max_attempts = (
            1
            if request.data_class == AiCoachDataClass.PERSONALIZED
            else settings.ai_coach_max_attempts
        )
        attempts = 0
        while attempts < max_attempts:
            attempts += 1
            try:
                result = self.provider.generate(request, policy, context_refs)
                if not isinstance(result, ProviderResult):
                    raise NormalizedProviderError(ProviderErrorCode.INVALID_OUTPUT)
                return result, attempts
            except NormalizedProviderError as exc:
                if exc.retryable and attempts < max_attempts:
                    continue
                raise _ProviderCallFailure(exc, attempts) from exc
            except Exception as exc:
                normalized = NormalizedProviderError(
                    ProviderErrorCode.PROVIDER_UNAVAILABLE,
                    retryable=False,
                )
                raise _ProviderCallFailure(normalized, attempts) from exc
        raise _ProviderCallFailure(
            NormalizedProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE),
            attempts,
        )

    def _base_response(
        self,
        request: AiCoachRequest,
        request_id: str | None,
        safety: SafetyCategory,
        outcome: AiCoachOutcome,
        *,
        answer: str | None = None,
        citations=(),
        limitations=(),
    ) -> AiCoachResponse:
        return AiCoachResponse(
            outcome=outcome,
            answer=answer,
            citations=tuple(citations),
            limitations=tuple(limitations),
            safety_category=safety.value,
            prompt_version=_prompt_version_for(request),
            request_id=request_id,
        )

    def _unavailable_response(
        self,
        request: AiCoachRequest,
        request_id: str | None,
        safety: SafetyCategory,
    ) -> AiCoachResponse:
        return self._base_response(
            request,
            request_id,
            safety,
            AiCoachOutcome.UNAVAILABLE,
            limitations=(_UNAVAILABLE_LIMITATION,),
        )

    def _insufficient_response(
        self,
        request: AiCoachRequest,
        request_id: str | None,
        safety: SafetyCategory,
    ) -> AiCoachResponse:
        return self._base_response(
            request,
            request_id,
            safety,
            AiCoachOutcome.INSUFFICIENT_DATA,
            limitations=(_INSUFFICIENT_LIMITATION,),
        )

    def _rate_limited_response(
        self,
        request: AiCoachRequest,
        request_id: str | None,
        safety: SafetyCategory,
    ) -> AiCoachResponse:
        return self._base_response(
            request,
            request_id,
            safety,
            AiCoachOutcome.RATE_LIMITED,
            limitations=(_RATE_LIMITED_LIMITATION,),
        )

    def _invalid_output_response(
        self,
        request: AiCoachRequest,
        request_id: str | None,
        safety: SafetyCategory,
    ) -> AiCoachResponse:
        return self._base_response(
            request,
            request_id,
            safety,
            AiCoachOutcome.INVALID_OUTPUT,
            limitations=(_INVALID_OUTPUT_LIMITATION,),
        )

    def _safety_response(
        self,
        request: AiCoachRequest,
        request_id: str | None,
        safety: SafetyCategory,
    ) -> AiCoachResponse:
        return self._base_response(
            request,
            request_id,
            safety,
            AiCoachOutcome.SAFETY_REFUSAL,
            answer=refusal_text(safety),
        )

    def _answer_response(
        self,
        request: AiCoachRequest,
        request_id: str | None,
        safety: SafetyCategory,
        result: ProviderResult,
        context_refs: tuple[ContextRef, ...],
    ) -> AiCoachResponse:
        ref_by_id = {ref.ref_id: ref for ref in context_refs}
        citations = []
        seen_urls: set[str] = set()
        for ref_id in result.response.citation_ids:
            ref = ref_by_id.get(ref_id)
            if ref is None:
                continue
            for citation in ref.citations:
                url = str(citation.url)
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                citations.append(AiCoachCitation.model_validate(citation.model_dump()))
        default_limitation = (
            _PERSONAL_LIMITATION
            if request.data_class == AiCoachDataClass.PERSONALIZED
            else _GENERIC_LIMITATION
        )
        limitations = tuple(dict.fromkeys((default_limitation, *result.response.limitations)))
        return self._base_response(
            request,
            request_id,
            safety,
            AiCoachOutcome.ANSWER,
            answer=result.response.answer,
            citations=citations,
            limitations=limitations[:6],
        )


ai_coach_service = AiCoachService()

__all__ = [
    "AiCoachService",
    "InMemoryAiCoachQuota",
    "ProviderCapability",
    "ProviderCooldown",
    "ai_coach_service",
]
