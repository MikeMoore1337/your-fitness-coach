"""Typed contracts for the bounded generic AI Coach route.

The contracts deliberately do not contain SQLAlchemy models, provider SDK types,
user profile data or arbitrary prompt fields.  They are the boundary between the
application policy and a provider adapter.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal, Protocol
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

AI_COACH_DATA_CLASS = "generic"
AI_COACH_PROMPT_VERSION = "ai-coach-production-v1"
AI_COACH_PERSONAL_PROMPT_VERSION = "ai-coach-personal-v2"
AI_COACH_SCHEMA_VERSION = "ai-coach-answer-v1"
AI_COACH_PERIOD_REPORT_PROMPT_VERSION = "ai-coach-period-report-v2"
AI_COACH_PERIOD_REPORT_INPUT_VERSION = "ai-coach-period-report-input-v1"
AI_COACH_PERIOD_REPORT_OUTPUT_VERSION = "ai-coach-period-report-output-v1"
AI_COACH_CHAT_PROMPT_VERSION = "ai-coach-chat-v2"
AI_COACH_CHAT_OUTPUT_VERSION = "ai-coach-chat-text-v1"
AI_COACH_CHAT_MAX_MESSAGE_LENGTH = 2_000
AI_COACH_CHAT_PROVIDER_MAX_ANSWER_LENGTH = 8_000
_BoundedLimitation = Annotated[str, Field(max_length=240)]
_BoundedAnchor = Annotated[str, Field(min_length=1, max_length=128)]
AiCoachMemoryCategory = Literal[
    "preferred_explanation_style",
    "ai_interaction_preferences",
    "stable_non_medical_preferences",
    "explicit_ai_context",
]
AiCoachMemoryOrigin = Literal["explicit_user", "confirmed_candidate"]


def _validate_https_url(value: str) -> str:
    if any(ord(character) < 0x20 for character in value):
        raise ValueError("URL contains control characters")
    parsed = urlparse(value)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("AI Coach citations must use credential-free HTTPS URLs")
    return value


class AiCoachDataClass(StrEnum):
    GENERIC = AI_COACH_DATA_CLASS
    PERSONALIZED = "personalized"
    UNKNOWN = "unknown"


class AiCoachJob(StrEnum):
    APP_HELP = "app_help"
    PUBLIC_KNOWLEDGE = "public_knowledge"
    METRIC_EXPLANATION = "metric_explanation"
    FITNESS_KNOWLEDGE = "fitness_knowledge"
    NUTRITION_KNOWLEDGE = "nutrition_knowledge"
    PROGRESSION_EXPLANATION = "progression_explanation"


class AiCoachPersonalTool(StrEnum):
    GET_PROGRESS_SUMMARY = "get_progress_summary"
    GET_RECENT_TRAINING_SUMMARY = "get_recent_training_summary"
    GET_NUTRITION_SUMMARY = "get_nutrition_summary"
    GET_PERIOD_REPORT_INSIGHTS = "get_period_report_insights"


class AiCoachChatContextKind(StrEnum):
    """Explicit scope of application context selected for one chat turn."""

    NONE = "none"
    APP_CAPABILITIES = "app_capabilities"
    PUBLIC_KNOWLEDGE = "public_knowledge"
    PROFILE_GOALS = "profile_goals"
    ACTIVE_PROGRAM = "active_program"
    RECENT_WORKOUTS = "recent_workouts"
    BENCH_HISTORY = "bench_history"
    NUTRITION_SUMMARY = "nutrition_summary"


class AiCoachInsightKind(StrEnum):
    FACT = "fact"
    INFERENCE = "inference"
    SUGGESTION = "suggestion"


class AiCoachOutcome(StrEnum):
    ANSWER = "answer"
    UNAVAILABLE = "unavailable"
    RATE_LIMITED = "rate_limited"
    SAFETY_REFUSAL = "safety_refusal"
    INSUFFICIENT_DATA = "insufficient_data"
    INVALID_OUTPUT = "invalid_output"
    CONSENT_REQUIRED = "consent_required"


class AiCoachRateLimitScope(StrEnum):
    """The boundary that blocked a generation request."""

    USER = "user"
    SERVICE = "service"
    PROVIDER = "provider"


class AiCoachQuotaSnapshot(BaseModel):
    """Server-owned user quota state; no prompt or answer data is included."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(..., ge=1)
    used: int = Field(..., ge=0)
    remaining: int = Field(..., ge=0)
    reset_at: datetime
    retry_after_seconds: int = Field(..., ge=0)
    can_send: bool


class ChatOutputValidationReason(StrEnum):
    """Safe reason codes for provider text that needs presentation repair."""

    TOO_LONG = "too_long"
    WRONG_LANGUAGE = "wrong_language"
    JSON_CONTAINER = "json_container"
    INTERNAL_LABEL = "internal_label"
    URL = "url"
    PROHIBITED_CLAIM = "prohibited_claim"
    UNSAFE_CONTENT = "unsafe_content"
    OTHER = "other"


class AiCoachMemoryContext(BaseModel):
    """A bounded continuity hint; it is never canonical evidence."""

    model_config = ConfigDict(extra="forbid")

    category: AiCoachMemoryCategory
    value: str = Field(..., min_length=1, max_length=240)
    origin: AiCoachMemoryOrigin
    updated_at: str = Field(..., min_length=1, max_length=32)


class ProviderErrorCode(StrEnum):
    DISABLED = "disabled"
    POLICY_BLOCKED = "policy_blocked"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    INVALID_OUTPUT = "invalid_output"
    AUTHENTICATION_FAILED = "authentication_failed"
    REQUEST_REJECTED = "request_rejected"
    COOLDOWN_ACTIVE = "cooldown_active"


class ProviderFailureReason(StrEnum):
    """Privacy-safe provider/protocol reason for routing and metadata-only telemetry."""

    HTTP_429 = "http_429"
    HTTP_401 = "http_401"
    HTTP_403 = "http_403"
    HTTP_400 = "http_400"
    HTTP_5XX = "http_5xx"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    RESPONSE_TOO_LARGE = "response_too_large"
    MALFORMED_JSON = "malformed_json"
    INVALID_CHOICES = "invalid_choices"
    FINISH_REASON_LENGTH = "finish_reason_length"
    FINISH_REASON_OTHER = "finish_reason_other"
    PROVIDER_REFUSAL = "provider_refusal"
    MISSING_CONTENT = "missing_content"
    INVALID_CONTENT = "invalid_content"
    INVALID_PROVIDER_PAYLOAD = "invalid_provider_payload"
    UNKNOWN = "unknown"


class AiCoachRequest(BaseModel):
    """Internal request with a server-assigned trust class."""

    model_config = ConfigDict(extra="forbid")

    job: AiCoachJob
    context_id: str = Field(..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:/-]+$")
    message: str = Field(..., min_length=1, max_length=320)
    data_class: AiCoachDataClass
    tool_name: AiCoachPersonalTool | None = None
    locale: Literal["ru"] = "ru"
    memory_context: tuple[AiCoachMemoryContext, ...] = ()

    @field_validator("context_id")
    @classmethod
    def validate_context_id(cls, value: str) -> str:
        normalized = value.strip()
        if "://" in normalized or "?" in normalized or "#" in normalized:
            raise ValueError("context_id must be a server-known public id, not a URL")
        return normalized

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).strip()
        if len(normalized) > 320 or any(
            ord(char) < 0x20 and char not in "\t" for char in normalized
        ):
            raise ValueError("message must be a single safe text value")
        return normalized


class AiCoachConversationTurn(BaseModel):
    """One bounded turn supplied to the text-generation adapter."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=AI_COACH_CHAT_MAX_MESSAGE_LENGTH)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = (
            unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n").strip()
        )
        if not normalized or any(ord(char) < 0x20 and char not in "\t\n" for char in normalized):
            raise ValueError("conversation content must be a single safe text value")
        return normalized


class AiCoachChatRequest(BaseModel):
    """Provider-neutral request for the ordinary conversational AI Coach path."""

    model_config = ConfigDict(extra="forbid")

    job: AiCoachJob
    context_id: str = Field(..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:/-]+$")
    message: str = Field(..., min_length=1, max_length=AI_COACH_CHAT_MAX_MESSAGE_LENGTH)
    data_class: AiCoachDataClass
    context_kind: AiCoachChatContextKind = AiCoachChatContextKind.NONE
    locale: Literal["ru", "en"] = "ru"
    # Internal bounded retry hint; it is never accepted from the public API or sent as metadata.
    retry_hint: bool = False
    conversation_history: tuple[AiCoachConversationTurn, ...] = Field(default=(), max_length=8)
    memory_context: tuple[AiCoachMemoryContext, ...] = Field(default=(), max_length=20)

    @field_validator("context_id")
    @classmethod
    def validate_context_id(cls, value: str) -> str:
        normalized = value.strip()
        if "://" in normalized or "?" in normalized or "#" in normalized:
            raise ValueError("context_id must be a server-known context id, not a URL")
        return normalized

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).strip()
        if not normalized or any(ord(char) < 0x20 and char not in "\t" for char in normalized):
            raise ValueError("message must be a single safe text value")
        return normalized


class AiCoachPolicy(BaseModel):
    """Application policy passed to the provider-neutral LLM port."""

    model_config = ConfigDict(extra="forbid")

    job: AiCoachJob
    data_class: AiCoachDataClass
    prompt_version: str = Field(..., min_length=1, max_length=64)
    schema_version: str = Field(..., min_length=1, max_length=64)
    locale: Literal["ru"] = "ru"
    required_capabilities: tuple[Literal["structured_output"], ...] = ("structured_output",)
    cost_policy: Literal["free_only"] = "free_only"


class ContextCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=240)
    publisher: str = Field(..., min_length=1, max_length=160)
    url: str
    source_type: str = Field(..., min_length=1, max_length=64)

    _require_https = field_validator("url")(_validate_https_url)


class ContextRef(BaseModel):
    """A bounded, reviewed public context item prepared by the backend."""

    model_config = ConfigDict(extra="forbid")

    ref_id: str = Field(..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:/-]+$")
    title: str = Field(..., min_length=1, max_length=240)
    category: str = Field(..., min_length=1, max_length=64)
    updated_at: str = Field(..., min_length=1, max_length=32)
    reviewer: str | None = Field(default=None, max_length=160)
    canonical_url: str
    content: str = Field(..., min_length=1, max_length=16_000)
    citations: tuple[ContextCitation, ...] = Field(..., min_length=1, max_length=8)

    _require_https = field_validator("canonical_url")(_validate_https_url)


class ProviderInsight(BaseModel):
    """One bounded, evidence-linked claim in a period-report response."""

    model_config = ConfigDict(extra="forbid")

    kind: AiCoachInsightKind
    text: str = Field(..., min_length=1, max_length=400)
    evidence_ids: tuple[_BoundedAnchor, ...] = Field(..., min_length=1, max_length=4)
    reason_keys: tuple[_BoundedAnchor, ...] = Field(default=(), max_length=4)

    @field_validator("evidence_ids", "reason_keys")
    @classmethod
    def validate_anchor_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not re.fullmatch(r"[A-Za-z0-9_.:/-]+", item) for item in value):
            raise ValueError("insight anchors contain an invalid reference")
        return value


class ProviderStructuredResponse(BaseModel):
    """The only model output accepted from a provider."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(..., min_length=1, max_length=1_600)
    citation_ids: tuple[str, ...] = Field(..., min_length=1, max_length=5)
    limitations: tuple[_BoundedLimitation, ...] = Field(default=(), max_length=4)
    insights: tuple[ProviderInsight, ...] = Field(default=(), max_length=11)

    @field_validator("citation_ids")
    @classmethod
    def validate_citation_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not re.fullmatch(r"[A-Za-z0-9_.:/-]+", item) for item in value):
            raise ValueError("citation_ids contain an invalid reference")
        return value


class AiCoachInsight(BaseModel):
    """Stable user-facing representation of a grounded claim."""

    model_config = ConfigDict(extra="forbid")

    kind: AiCoachInsightKind
    text: str = Field(..., min_length=1, max_length=400)
    evidence_ids: tuple[_BoundedAnchor, ...] = Field(..., min_length=1, max_length=4)
    reason_keys: tuple[_BoundedAnchor, ...] = Field(default=(), max_length=4)

    @field_validator("evidence_ids", "reason_keys")
    @classmethod
    def validate_anchor_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not re.fullmatch(r"[A-Za-z0-9_.:/-]+", item) for item in value):
            raise ValueError("insight anchors contain an invalid reference")
        return value


class AiCoachResponseMetadata(BaseModel):
    """Version and period metadata attached only to grounded report responses."""

    model_config = ConfigDict(extra="forbid")

    report_version: str = Field(..., min_length=1, max_length=64)
    input_version: str = Field(..., min_length=1, max_length=64)
    output_version: str = Field(..., min_length=1, max_length=64)
    report_revision: str = Field(..., min_length=1, max_length=128)
    period_start: date
    period_end: date
    timezone: str = Field(..., min_length=1, max_length=64)


class ProviderUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    cost_microunits: int | None = Field(default=None, ge=0)


class ProviderResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(..., min_length=1, max_length=64)
    configured_model: str = Field(..., min_length=1, max_length=128)
    actual_model: str | None = Field(default=None, max_length=128)
    response: ProviderStructuredResponse
    usage: ProviderUsage | None = None
    latency_ms: int = Field(..., ge=0)
    http_status: int | None = Field(default=None, ge=100, le=599)
    finish_reason: str | None = Field(default=None, max_length=64)
    response_bytes: int | None = Field(default=None, ge=0)


class ProviderTextResponse(BaseModel):
    """Plain text output for chat; no period-report JSON schema is involved."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(..., min_length=1, max_length=AI_COACH_CHAT_PROVIDER_MAX_ANSWER_LENGTH)


class ProviderTextResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(..., min_length=1, max_length=64)
    configured_model: str = Field(..., min_length=1, max_length=128)
    actual_model: str | None = Field(default=None, max_length=128)
    response: ProviderTextResponse
    usage: ProviderUsage | None = None
    latency_ms: int = Field(..., ge=0)
    http_status: int | None = Field(default=None, ge=100, le=599)
    finish_reason: str | None = Field(default=None, max_length=64)
    response_bytes: int | None = Field(default=None, ge=0)


class AiCoachCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=240)
    publisher: str = Field(..., min_length=1, max_length=160)
    url: str
    source_type: str = Field(..., min_length=1, max_length=64)

    _require_https = field_validator("url")(_validate_https_url)


class AiCoachResponse(BaseModel):
    """Stable user-facing response; provider topology is intentionally absent."""

    model_config = ConfigDict(extra="forbid")

    outcome: AiCoachOutcome
    answer: str | None = Field(default=None, max_length=1_600)
    citations: tuple[AiCoachCitation, ...] = Field(default=(), max_length=12)
    insights: tuple[AiCoachInsight, ...] = Field(default=(), max_length=11)
    limitations: tuple[_BoundedLimitation, ...] = Field(default=(), max_length=6)
    safety_category: str = Field(..., min_length=1, max_length=48)
    prompt_version: str = Field(..., min_length=1, max_length=64)
    request_id: str | None = Field(default=None, max_length=128)
    report_version: str | None = Field(default=None, max_length=64)
    input_version: str | None = Field(default=None, max_length=64)
    output_version: str | None = Field(default=None, max_length=64)
    report_revision: str | None = Field(default=None, max_length=128)
    period_start: date | None = None
    period_end: date | None = None
    timezone: str | None = Field(default=None, max_length=64)
    quota: AiCoachQuotaSnapshot | None = None
    rate_limit_scope: AiCoachRateLimitScope | None = None
    rate_limit_retry_after_seconds: int | None = Field(default=None, ge=0)


@dataclass(frozen=True)
class NormalizedProviderError(RuntimeError):
    """Provider error safe for routing and metadata-only logging."""

    code: ProviderErrorCode
    retryable: bool = False
    retry_after_seconds: int | None = None
    misconfigured: bool = False
    provider_failure_reason: ProviderFailureReason = ProviderFailureReason.UNKNOWN
    http_status: int | None = None
    finish_reason: str | None = None
    response_bytes: int | None = None
    response_payload_type: str | None = None
    choices_count: int | None = None
    choices_item_type: str | None = None
    message_present: bool | None = None
    message_type: str | None = None
    refusal_present: bool | None = None
    content_present: bool | None = None
    content_type: str | None = None
    usage: ProviderUsage | None = None

    def __str__(self) -> str:
        return self.code.value


class LlmPort(Protocol):
    provider_name: str

    def generate(
        self,
        request: AiCoachRequest,
        policy: AiCoachPolicy,
        context_refs: tuple[ContextRef, ...],
    ) -> ProviderResult: ...


class ChatLlmPort(Protocol):
    provider_name: str

    def generate_text(
        self,
        request: AiCoachChatRequest,
        context_refs: tuple[ContextRef, ...],
    ) -> ProviderTextResult: ...

    def repair_text(
        self,
        request: AiCoachChatRequest,
        answer: str,
        reason: ChatOutputValidationReason,
    ) -> ProviderTextResult: ...
