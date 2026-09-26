"""Direct Groq adapter for the provider-neutral AI Coach contract."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from fitminiapp_api.ai_coach.contracts import (
    AiCoachChatRequest,
    AiCoachPersonalTool,
    AiCoachPolicy,
    AiCoachRequest,
    ChatOutputValidationReason,
    ContextRef,
    NormalizedProviderError,
    ProviderErrorCode,
    ProviderFailureReason,
    ProviderResult,
    ProviderStructuredResponse,
    ProviderTextResponse,
    ProviderTextResult,
    ProviderUsage,
)
from fitminiapp_api.ai_coach.prompts import (
    build_chat_messages,
    build_chat_repair_messages,
    build_messages,
    provider_output_json_schema,
)
from fitminiapp_api.core.config import settings

MAX_PROVIDER_RESPONSE_BYTES = 128_000
PROVIDER_NAME = "groq"
MAX_CHAT_RETRY_OUTPUT_TOKENS = 2_048


def _response_bytes(response: Any) -> int | None:
    content = getattr(response, "content", None)
    return len(content) if isinstance(content, (bytes, bytearray)) else None


def _payload_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _safe_finish_reason(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > 64
        or any(ord(character) < 0x20 for character in normalized)
    ):
        return None
    return normalized


def _invalid_plain_response(
    reason: ProviderFailureReason,
    *,
    response_bytes: int | None,
    http_status: int | None = 200,
    finish_reason: str | None = None,
    response_payload_type: str | None = None,
    choices_count: int | None = None,
    choices_item_type: str | None = None,
    message_present: bool | None = None,
    message_type: str | None = None,
    refusal_present: bool | None = None,
    content_present: bool | None = None,
    content_type: str | None = None,
    usage: ProviderUsage | None = None,
) -> NormalizedProviderError:
    return NormalizedProviderError(
        ProviderErrorCode.INVALID_OUTPUT,
        retryable=reason
        in {
            ProviderFailureReason.MALFORMED_JSON,
            ProviderFailureReason.INVALID_CHOICES,
            ProviderFailureReason.FINISH_REASON_LENGTH,
        },
        provider_failure_reason=reason,
        http_status=http_status,
        finish_reason=finish_reason,
        response_bytes=response_bytes,
        response_payload_type=response_payload_type,
        choices_count=choices_count,
        choices_item_type=choices_item_type,
        message_present=message_present,
        message_type=message_type,
        refusal_present=refusal_present,
        content_present=content_present,
        content_type=content_type,
        usage=usage,
    )


def _safe_retry_after(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value.strip())
    except ValueError:
        return None
    return max(0, min(parsed, 3600))


def _provider_error_for_status(
    status_code: int, retry_after: int | None, *, response_bytes: int | None = None
) -> NormalizedProviderError:
    if status_code == 429:
        return NormalizedProviderError(
            ProviderErrorCode.RATE_LIMITED,
            retryable=False,
            retry_after_seconds=retry_after,
            provider_failure_reason=ProviderFailureReason.HTTP_429,
            http_status=status_code,
            response_bytes=response_bytes,
        )
    if status_code in {401, 403}:
        return NormalizedProviderError(
            ProviderErrorCode.AUTHENTICATION_FAILED,
            misconfigured=True,
            provider_failure_reason=(
                ProviderFailureReason.HTTP_401
                if status_code == 401
                else ProviderFailureReason.HTTP_403
            ),
            http_status=status_code,
            response_bytes=response_bytes,
        )
    if status_code in {400, 422}:
        return NormalizedProviderError(
            ProviderErrorCode.REQUEST_REJECTED,
            provider_failure_reason=ProviderFailureReason.HTTP_400,
            http_status=status_code,
            response_bytes=response_bytes,
        )
    if status_code == 408:
        return NormalizedProviderError(
            ProviderErrorCode.TIMEOUT,
            retryable=True,
            retry_after_seconds=retry_after,
            provider_failure_reason=ProviderFailureReason.TIMEOUT,
            http_status=status_code,
            response_bytes=response_bytes,
        )
    if status_code in {409, 425} or 500 <= status_code <= 599:
        return NormalizedProviderError(
            ProviderErrorCode.PROVIDER_UNAVAILABLE,
            retryable=True,
            retry_after_seconds=retry_after,
            provider_failure_reason=(
                ProviderFailureReason.HTTP_5XX
                if 500 <= status_code <= 599
                else ProviderFailureReason.UNKNOWN
            ),
            http_status=status_code,
            response_bytes=response_bytes,
        )
    return NormalizedProviderError(
        ProviderErrorCode.PROVIDER_UNAVAILABLE,
        retryable=False,
        provider_failure_reason=ProviderFailureReason.UNKNOWN,
        http_status=status_code,
        response_bytes=response_bytes,
    )


def _usage_from_payload(payload: dict[str, Any]) -> ProviderUsage | None:
    raw_usage = payload.get("usage")
    if not isinstance(raw_usage, dict):
        return None

    def integer(name: str) -> int | None:
        value = raw_usage.get(name)
        return value if isinstance(value, int) and value >= 0 else None

    prompt_tokens = integer("prompt_tokens")
    completion_tokens = integer("completion_tokens")
    total_tokens = integer("total_tokens")
    details = raw_usage.get("completion_tokens_details")
    reasoning_tokens = details.get("reasoning_tokens") if isinstance(details, dict) else None
    if not isinstance(reasoning_tokens, int) or reasoning_tokens < 0:
        reasoning_tokens = None
    return ProviderUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        reasoning_tokens=reasoning_tokens,
    )


def _parse_plain_text_response(response: Any, *, started: float) -> ProviderTextResult:
    retry_after = _safe_retry_after(response.headers.get("retry-after"))
    response_bytes = _response_bytes(response)
    if response.status_code != 200:
        raise _provider_error_for_status(
            response.status_code,
            retry_after,
            response_bytes=response_bytes,
        )
    if response_bytes is not None and response_bytes > MAX_PROVIDER_RESPONSE_BYTES:
        raise _invalid_plain_response(
            ProviderFailureReason.RESPONSE_TOO_LARGE,
            response_bytes=response_bytes,
        )

    try:
        raw_payload = response.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise _invalid_plain_response(
            ProviderFailureReason.MALFORMED_JSON,
            response_bytes=response_bytes,
        ) from exc
    payload_type_name = _payload_type(raw_payload)
    if not isinstance(raw_payload, dict):
        raise _invalid_plain_response(
            ProviderFailureReason.INVALID_PROVIDER_PAYLOAD,
            response_bytes=response_bytes,
            response_payload_type=payload_type_name,
        )

    choices = raw_payload.get("choices")
    choices_count = len(choices) if isinstance(choices, list) else None
    choices_item_type = _payload_type(choices[0]) if isinstance(choices, list) and choices else None
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise _invalid_plain_response(
            ProviderFailureReason.INVALID_CHOICES,
            response_bytes=response_bytes,
            response_payload_type=payload_type_name,
            choices_count=choices_count,
            choices_item_type=choices_item_type,
        )
    choice = choices[0]
    finish_reason = _safe_finish_reason(choice.get("finish_reason"))
    if finish_reason != "stop":
        reason = (
            ProviderFailureReason.FINISH_REASON_LENGTH
            if finish_reason == "length"
            else ProviderFailureReason.FINISH_REASON_OTHER
            if finish_reason is not None
            else ProviderFailureReason.INVALID_PROVIDER_PAYLOAD
        )
        raise _invalid_plain_response(
            reason,
            response_bytes=response_bytes,
            response_payload_type=payload_type_name,
            choices_count=choices_count,
            choices_item_type=choices_item_type,
            finish_reason=finish_reason,
            usage=_usage_from_payload(raw_payload),
        )
    message = choice.get("message")
    if not isinstance(message, dict):
        raise _invalid_plain_response(
            ProviderFailureReason.INVALID_PROVIDER_PAYLOAD,
            response_bytes=response_bytes,
            response_payload_type=payload_type_name,
            choices_count=choices_count,
            choices_item_type=choices_item_type,
            finish_reason=finish_reason,
            message_present="message" in choice,
            message_type=_payload_type(message),
            usage=_usage_from_payload(raw_payload),
        )
    refusal_present = "refusal" in message
    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal.strip():
        raise _invalid_plain_response(
            ProviderFailureReason.PROVIDER_REFUSAL,
            response_bytes=response_bytes,
            response_payload_type=payload_type_name,
            choices_count=choices_count,
            choices_item_type=choices_item_type,
            finish_reason=finish_reason,
            message_present=True,
            message_type=_payload_type(message),
            refusal_present=refusal_present,
            usage=_usage_from_payload(raw_payload),
        )
    if refusal_present and refusal is not None and not isinstance(refusal, str):
        raise _invalid_plain_response(
            ProviderFailureReason.INVALID_PROVIDER_PAYLOAD,
            response_bytes=response_bytes,
            response_payload_type=payload_type_name,
            choices_count=choices_count,
            choices_item_type=choices_item_type,
            finish_reason=finish_reason,
            message_present=True,
            message_type=_payload_type(message),
            refusal_present=True,
            content_present="content" in message,
            content_type=_payload_type(message.get("content")) if "content" in message else None,
            usage=_usage_from_payload(raw_payload),
        )
    content_present = "content" in message and message.get("content") is not None
    if not content_present:
        raise _invalid_plain_response(
            ProviderFailureReason.MISSING_CONTENT,
            response_bytes=response_bytes,
            response_payload_type=payload_type_name,
            choices_count=choices_count,
            choices_item_type=choices_item_type,
            finish_reason=finish_reason,
            message_present=True,
            message_type=_payload_type(message),
            refusal_present=refusal_present,
            content_present=False,
            content_type=_payload_type(message.get("content")) if "content" in message else None,
            usage=_usage_from_payload(raw_payload),
        )
    content = message.get("content")
    content_type = _payload_type(content)
    if not isinstance(content, str):
        raise _invalid_plain_response(
            ProviderFailureReason.INVALID_CONTENT,
            response_bytes=response_bytes,
            response_payload_type=payload_type_name,
            choices_count=choices_count,
            choices_item_type=choices_item_type,
            finish_reason=finish_reason,
            message_present=True,
            message_type=_payload_type(message),
            refusal_present=refusal_present,
            content_present=True,
            content_type=content_type,
            usage=_usage_from_payload(raw_payload),
        )
    if len(content.encode("utf-8")) > MAX_PROVIDER_RESPONSE_BYTES:
        raise _invalid_plain_response(
            ProviderFailureReason.RESPONSE_TOO_LARGE,
            response_bytes=response_bytes,
            response_payload_type=payload_type_name,
            choices_count=choices_count,
            choices_item_type=choices_item_type,
            finish_reason=finish_reason,
            message_present=True,
            message_type=_payload_type(message),
            refusal_present=refusal_present,
            content_present=True,
            content_type=content_type,
            usage=_usage_from_payload(raw_payload),
        )
    try:
        text_response = ProviderTextResponse(answer=content.strip())
    except (ValueError, TypeError) as exc:
        raise _invalid_plain_response(
            ProviderFailureReason.INVALID_CONTENT,
            response_bytes=response_bytes,
            response_payload_type=payload_type_name,
            choices_count=choices_count,
            choices_item_type=choices_item_type,
            finish_reason=finish_reason,
            message_present=True,
            message_type=_payload_type(message),
            refusal_present=refusal_present,
            content_present=True,
            content_type=content_type,
            usage=_usage_from_payload(raw_payload),
        ) from exc

    actual_model = raw_payload.get("model")
    if (
        not isinstance(actual_model, str)
        or not actual_model.strip()
        or len(actual_model) > 128
        or any(ord(character) < 0x20 for character in actual_model)
    ):
        actual_model = None
    return ProviderTextResult(
        provider=PROVIDER_NAME,
        configured_model=settings.ai_coach_model,
        actual_model=actual_model,
        response=text_response,
        usage=_usage_from_payload(raw_payload),
        latency_ms=max(0, round((time.monotonic() - started) * 1000)),
        http_status=response.status_code,
        finish_reason=finish_reason,
        response_bytes=response_bytes,
    )



def _provider_http_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(settings.ai_coach_timeout_seconds),
        follow_redirects=False,
        trust_env=False,
        proxy=settings.ai_coach_proxy_url.strip() or None,
    )


class GroqDirectAdapter:
    """Small OpenAI-compatible adapter with no tools and no provider types upstream."""

    provider_name = PROVIDER_NAME

    def generate(
        self,
        request: AiCoachRequest,
        policy: AiCoachPolicy,
        context_refs: tuple[ContextRef, ...],
    ) -> ProviderResult:
        if not context_refs:
            raise NormalizedProviderError(ProviderErrorCode.INVALID_OUTPUT)

        api_key = settings.groq_api_key.get_secret_value().strip()
        if not api_key or settings.ai_coach_provider != "groq":
            raise NormalizedProviderError(ProviderErrorCode.DISABLED)

        payload = {
            "model": settings.ai_coach_model,
            "messages": build_messages(request, policy, context_refs),
            "max_completion_tokens": settings.ai_coach_max_output_tokens,
            "reasoning_effort": "low",
            "include_reasoning": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": policy.schema_version,
                    "strict": True,
                    "schema": provider_output_json_schema(request),
                },
            },
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        started = time.monotonic()
        try:
            with _provider_http_client() as client:
                response = client.post(settings.ai_coach_endpoint, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise NormalizedProviderError(
                ProviderErrorCode.TIMEOUT,
                retryable=True,
                provider_failure_reason=ProviderFailureReason.TIMEOUT,
            ) from exc
        except httpx.NetworkError as exc:
            raise NormalizedProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                retryable=True,
                provider_failure_reason=ProviderFailureReason.NETWORK_ERROR,
            ) from exc
        except httpx.HTTPError as exc:
            raise NormalizedProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                provider_failure_reason=ProviderFailureReason.NETWORK_ERROR,
            ) from exc

        retry_after = _safe_retry_after(response.headers.get("retry-after"))
        if response.status_code != 200:
            raise _provider_error_for_status(response.status_code, retry_after)
        if len(response.content) > MAX_PROVIDER_RESPONSE_BYTES:
            raise NormalizedProviderError(ProviderErrorCode.INVALID_OUTPUT)

        try:
            raw_payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise NormalizedProviderError(ProviderErrorCode.INVALID_OUTPUT) from exc
        if not isinstance(raw_payload, dict):
            raise NormalizedProviderError(ProviderErrorCode.INVALID_OUTPUT)

        choices = raw_payload.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise NormalizedProviderError(ProviderErrorCode.INVALID_OUTPUT)
        choice = choices[0]
        if choice.get("finish_reason") != "stop":
            raise NormalizedProviderError(ProviderErrorCode.INVALID_OUTPUT)
        message = choice.get("message")
        if not isinstance(message, dict):
            raise NormalizedProviderError(ProviderErrorCode.INVALID_OUTPUT)
        if isinstance(message.get("refusal"), str) and message["refusal"].strip():
            raise NormalizedProviderError(ProviderErrorCode.INVALID_OUTPUT)
        content = message.get("content")
        if (
            not isinstance(content, str)
            or len(content.encode("utf-8")) > MAX_PROVIDER_RESPONSE_BYTES
        ):
            raise NormalizedProviderError(ProviderErrorCode.INVALID_OUTPUT)
        try:
            decoded = json.loads(content)
            required_fields = {"answer", "citation_ids", "limitations"}
            if request.tool_name == AiCoachPersonalTool.GET_PERIOD_REPORT_INSIGHTS:
                required_fields.add("insights")
            if not isinstance(decoded, dict) or not required_fields.issubset(decoded):
                raise ValueError("provider response does not satisfy the complete output schema")
            structured = ProviderStructuredResponse.model_validate(decoded)
        except (ValueError, TypeError) as exc:
            raise NormalizedProviderError(ProviderErrorCode.INVALID_OUTPUT) from exc

        actual_model = raw_payload.get("model")
        if (
            not isinstance(actual_model, str)
            or not actual_model.strip()
            or len(actual_model) > 128
            or any(ord(character) < 0x20 for character in actual_model)
        ):
            actual_model = None
        return ProviderResult(
            provider=PROVIDER_NAME,
            configured_model=settings.ai_coach_model,
            actual_model=actual_model,
            response=structured,
            usage=_usage_from_payload(raw_payload),
            latency_ms=max(0, round((time.monotonic() - started) * 1000)),
            http_status=response.status_code,
        )

    def _generate_plain_text(
        self,
        messages: list[dict[str, str]],
        *,
        retry_hint: bool = False,
    ) -> ProviderTextResult:
        api_key = settings.groq_api_key.get_secret_value().strip()
        if not api_key or settings.ai_coach_provider != "groq":
            raise NormalizedProviderError(ProviderErrorCode.DISABLED)

        max_output_tokens = settings.ai_coach_max_output_tokens
        if retry_hint:
            max_output_tokens = min(
                MAX_CHAT_RETRY_OUTPUT_TOKENS,
                max(
                    settings.ai_coach_max_output_tokens + 512,
                    settings.ai_coach_max_output_tokens * 2,
                ),
            )
        payload = {
            "model": settings.ai_coach_model,
            "messages": messages,
            "max_completion_tokens": max_output_tokens,
            "reasoning_effort": "low",
            "include_reasoning": False,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        started = time.monotonic()
        try:
            with _provider_http_client() as client:
                response = client.post(settings.ai_coach_endpoint, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise NormalizedProviderError(
                ProviderErrorCode.TIMEOUT,
                retryable=True,
                provider_failure_reason=ProviderFailureReason.TIMEOUT,
            ) from exc
        except httpx.NetworkError as exc:
            raise NormalizedProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                retryable=True,
                provider_failure_reason=ProviderFailureReason.NETWORK_ERROR,
            ) from exc
        except httpx.HTTPError as exc:
            raise NormalizedProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                provider_failure_reason=ProviderFailureReason.NETWORK_ERROR,
            ) from exc

        return _parse_plain_text_response(response, started=started)

    def generate_text(
        self,
        request: AiCoachChatRequest,
        context_refs: tuple[ContextRef, ...],
    ) -> ProviderTextResult:
        """Generate ordinary chat text without response_format or report JSON."""

        return self._generate_plain_text(
            build_chat_messages(request, context_refs),
            retry_hint=request.retry_hint,
        )

    def repair_text(
        self,
        request: AiCoachChatRequest,
        answer: str,
        reason: ChatOutputValidationReason,
    ) -> ProviderTextResult:
        """Make one bounded plain-text repair request; the draft remains untrusted data."""

        return self._generate_plain_text(build_chat_repair_messages(request, answer, reason.value))
