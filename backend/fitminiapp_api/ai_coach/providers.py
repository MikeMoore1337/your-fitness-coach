"""Direct Groq adapter for the provider-neutral AI Coach contract."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from fitminiapp_api.ai_coach.contracts import (
    AI_COACH_SCHEMA_VERSION,
    AiCoachPolicy,
    AiCoachRequest,
    ContextRef,
    NormalizedProviderError,
    ProviderErrorCode,
    ProviderResult,
    ProviderStructuredResponse,
    ProviderUsage,
)
from fitminiapp_api.ai_coach.prompts import build_messages, provider_output_json_schema
from fitminiapp_api.core.config import settings

MAX_PROVIDER_RESPONSE_BYTES = 128_000
PROVIDER_NAME = "groq"


def _safe_retry_after(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value.strip())
    except ValueError:
        return None
    return max(0, min(parsed, 3600))


def _provider_error_for_status(
    status_code: int, retry_after: int | None
) -> NormalizedProviderError:
    if status_code == 429:
        return NormalizedProviderError(
            ProviderErrorCode.RATE_LIMITED,
            retryable=False,
            retry_after_seconds=retry_after,
        )
    if status_code in {401, 403}:
        return NormalizedProviderError(
            ProviderErrorCode.AUTHENTICATION_FAILED,
            misconfigured=True,
        )
    if status_code in {400, 422}:
        return NormalizedProviderError(ProviderErrorCode.REQUEST_REJECTED)
    if status_code in {408, 409, 425} or 500 <= status_code <= 599:
        return NormalizedProviderError(
            ProviderErrorCode.PROVIDER_UNAVAILABLE,
            retryable=True,
            retry_after_seconds=retry_after,
        )
    return NormalizedProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE, retryable=False)


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
    return ProviderUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
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
            "reasoning_format": "hidden",
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": AI_COACH_SCHEMA_VERSION,
                    "strict": True,
                    "schema": provider_output_json_schema(),
                },
            },
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        started = time.monotonic()
        try:
            with httpx.Client(
                timeout=httpx.Timeout(settings.ai_coach_timeout_seconds),
                follow_redirects=False,
            ) as client:
                response = client.post(settings.ai_coach_endpoint, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise NormalizedProviderError(
                ProviderErrorCode.TIMEOUT,
                retryable=True,
            ) from exc
        except httpx.NetworkError as exc:
            raise NormalizedProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise NormalizedProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE) from exc

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
            if not isinstance(decoded, dict) or not {
                "answer",
                "citation_ids",
                "limitations",
            }.issubset(decoded):
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
        )
