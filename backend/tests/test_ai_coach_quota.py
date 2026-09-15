from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from pydantic import SecretStr

from fitminiapp_api.ai_coach.chat_service import ai_coach_chat_service
from fitminiapp_api.ai_coach.contracts import (
    AiCoachRateLimitScope,
    ChatOutputValidationReason,
    NormalizedProviderError,
    ProviderErrorCode,
    ProviderFailureReason,
    ProviderTextResponse,
    ProviderTextResult,
)
from fitminiapp_api.ai_coach.quota import PersistentAiCoachQuota
from fitminiapp_api.core.config import settings
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.ai_coach import AiCoachQuotaReservation
from fitminiapp_api.models.user import User
from fitminiapp_api.services.ai_coach_conversations import add_user_message, get_owned_conversation


def _login(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "username": f"quota_{telegram_user_id}"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _enable_chat(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_coach_enabled", True)
    monkeypatch.setattr(settings, "ai_coach_kill_switch", False)
    monkeypatch.setattr(settings, "ai_coach_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", SecretStr("test-chat-key"))
    monkeypatch.setattr(settings, "ai_coach_model", "openai/gpt-oss-120b")
    monkeypatch.setattr(
        settings, "ai_coach_endpoint", "https://api.groq.com/openai/v1/chat/completions"
    )
    monkeypatch.setattr(settings, "ai_coach_cost_policy", "free_only")
    monkeypatch.setattr(settings, "ai_coach_cost_class", "free")
    monkeypatch.setattr(settings, "ai_coach_data_policy", "verified_generic_only")
    ai_coach_chat_service.reset_runtime_state()


@dataclass
class CountingProvider:
    calls: int = 0
    repair_calls: int = 0
    answer: str = "Короткий проверенный ответ на русском языке."
    repair_answer: str | None = None
    error: NormalizedProviderError | None = None
    raise_exception: Exception | None = None

    provider_name: str = "stub"

    def generate_text(self, request, context_refs) -> ProviderTextResult:
        del request, context_refs
        self.calls += 1
        if self.raise_exception is not None:
            raise self.raise_exception
        if self.error is not None:
            raise self.error
        return ProviderTextResult(
            provider="groq",
            configured_model="openai/gpt-oss-120b",
            actual_model="openai/gpt-oss-120b",
            response=ProviderTextResponse(answer=self.answer),
            latency_ms=1,
        )

    def repair_text(
        self, request, answer: str, reason: ChatOutputValidationReason
    ) -> ProviderTextResult:
        del request, answer, reason
        self.repair_calls += 1
        return ProviderTextResult(
            provider="groq",
            configured_model="openai/gpt-oss-120b",
            actual_model="openai/gpt-oss-120b",
            response=ProviderTextResponse(answer=self.repair_answer or self.answer),
            latency_ms=1,
        )


def _create_conversation(client, headers: dict[str, str]) -> int:
    response = client.post("/api/v1/ai-coach/conversations", headers=headers)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _send(client, conversation_id: int, headers: dict[str, str], *, request_id: str, message: str):
    return client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers={**headers, "X-Request-ID": request_id},
        json={"message": message},
    )


def test_quota_endpoint_and_success_response_report_server_owned_snapshot(
    client, monkeypatch
) -> None:
    _enable_chat(monkeypatch)
    provider = CountingProvider()
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 987_276_001)
    conversation_id = _create_conversation(client, headers)

    initial = client.get("/api/v1/ai-coach/quota", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["limit"] == 20
    assert initial.json()["remaining"] == 20
    assert initial.json()["can_send"] is True
    assert initial.json()["reset_at"].endswith("+03:00")

    response = _send(
        client,
        conversation_id,
        headers,
        request_id="quota-success-1",
        message="Сколько отдыхать между подходами?",
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["outcome"] == "answer"
    assert payload["quota"]["limit"] == 20
    assert payload["quota"]["used"] == 1
    assert payload["quota"]["remaining"] == 19
    assert payload["rate_limit_scope"] is None

    refreshed = client.get("/api/v1/ai-coach/quota", headers=headers)
    assert refreshed.json()["remaining"] == 19
    assert provider.calls == 1


def test_provider_429_is_distinguished_and_does_not_consume_user_quota(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    provider = CountingProvider(
        error=NormalizedProviderError(
            ProviderErrorCode.RATE_LIMITED,
            retry_after_seconds=23,
            provider_failure_reason=ProviderFailureReason.HTTP_429,
        )
    )
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 987_276_002)
    conversation_id = _create_conversation(client, headers)

    response = _send(
        client,
        conversation_id,
        headers,
        request_id="quota-provider-429",
        message="Как читать прогресс в YFC?",
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["outcome"] == "rate_limited"
    assert payload["rate_limit_scope"] == AiCoachRateLimitScope.PROVIDER.value
    assert payload["rate_limit_retry_after_seconds"] == 23
    assert payload["quota"]["used"] == 0
    assert payload["quota"]["remaining"] == 20
    assert provider.calls == 1

    replay = _send(
        client,
        conversation_id,
        headers,
        request_id="quota-provider-429",
        message="Как читать прогресс в YFC?",
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["rate_limit_scope"] == AiCoachRateLimitScope.PROVIDER.value
    assert replay.json()["rate_limit_retry_after_seconds"] == 23
    assert provider.calls == 1

    conversation = client.get(
        f"/api/v1/ai-coach/conversations/{conversation_id}",
        headers=headers,
    )
    assert conversation.status_code == 200, conversation.text
    persisted_message = conversation.json()["messages"][0]
    assert persisted_message["rate_limit_scope"] == AiCoachRateLimitScope.PROVIDER.value
    assert persisted_message["rate_limit_retry_after_seconds"] == 23


def test_invalid_provider_output_is_released_without_quota_charge(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    provider = CountingProvider(error=NormalizedProviderError(ProviderErrorCode.INVALID_OUTPUT))
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 987_276_003)
    conversation_id = _create_conversation(client, headers)

    response = _send(
        client,
        conversation_id,
        headers,
        request_id="quota-invalid-output",
        message="Сколько отдыхать между подходами?",
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["outcome"] in {"answer", "invalid_output"}
    assert payload["quota"]["used"] == 0
    assert payload["quota"]["remaining"] == 20


@pytest.mark.parametrize(
    "provider_error",
    [
        pytest.param(
            NormalizedProviderError(
                ProviderErrorCode.TIMEOUT,
                provider_failure_reason=ProviderFailureReason.TIMEOUT,
            ),
            id="timeout",
        ),
        pytest.param(
            NormalizedProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                provider_failure_reason=ProviderFailureReason.HTTP_5XX,
            ),
            id="http-5xx",
        ),
    ],
)
def test_transport_failures_release_reservation_without_quota_charge(
    client, monkeypatch, provider_error
) -> None:
    _enable_chat(monkeypatch)
    provider = CountingProvider(error=provider_error)
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 987_276_005)
    conversation_id = _create_conversation(client, headers)

    response = _send(
        client,
        conversation_id,
        headers,
        request_id=f"quota-{provider_error.code.value}",
        message="Сколько отдыхать между подходами?",
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["outcome"] == "unavailable"
    assert payload["quota"]["used"] == 0
    assert payload["quota"]["remaining"] == 20
    assert provider.calls == 1


def test_unexpected_provider_error_is_safe_and_does_not_charge_quota(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    provider = CountingProvider(raise_exception=RuntimeError("provider internals"))
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 987_276_006)
    conversation_id = _create_conversation(client, headers)

    response = _send(
        client,
        conversation_id,
        headers,
        request_id="quota-provider-internal",
        message="Сколько отдыхать между подходами?",
    )

    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "unavailable"
    assert response.json()["quota"]["used"] == 0
    assert response.json()["quota"]["remaining"] == 20
    assert "provider internals" not in response.text


def test_safety_refusal_and_validation_do_not_reserve_quota(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    provider = CountingProvider()
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 987_276_007)
    conversation_id = _create_conversation(client, headers)

    safety_response = _send(
        client,
        conversation_id,
        headers,
        request_id="quota-safety",
        message="Поставь мне диагноз по боли в колене.",
    )
    validation_response = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers={**headers, "X-Request-ID": "quota-validation"},
        json={},
    )

    assert safety_response.status_code == 200
    assert safety_response.json()["outcome"] == "safety_refusal"
    assert safety_response.json()["quota"]["used"] == 0
    assert validation_response.status_code == 422
    assert client.get("/api/v1/ai-coach/quota", headers=headers).json()["remaining"] == 20
    assert provider.calls == 0


def test_repair_path_consumes_one_unit_for_one_successful_message(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    provider = CountingProvider(
        answer="Безопасный черновик. " + ("Объяснение отдыха. " * 120),
        repair_answer="Короткий исправленный ответ.",
    )
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 987_276_008)
    conversation_id = _create_conversation(client, headers)

    response = _send(
        client,
        conversation_id,
        headers,
        request_id="quota-repair-success",
        message="Сколько отдыхать между подходами?",
    )

    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "answer"
    assert response.json()["quota"]["used"] == 1
    assert response.json()["quota"]["remaining"] == 19
    assert provider.calls == 1
    assert provider.repair_calls == 1


def test_same_request_id_returns_persisted_response_without_second_provider_call(
    client, monkeypatch
) -> None:
    _enable_chat(monkeypatch)
    provider = CountingProvider()
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 987_276_004)
    conversation_id = _create_conversation(client, headers)

    first = _send(
        client,
        conversation_id,
        headers,
        request_id="quota-idempotent",
        message="Сколько отдыхать между подходами?",
    )
    second = _send(
        client,
        conversation_id,
        headers,
        request_id="quota-idempotent",
        message="Сколько отдыхать между подходами?",
    )
    conflict = _send(
        client,
        conversation_id,
        headers,
        request_id="quota-idempotent",
        message="Другой вопрос с тем же request id",
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["answer"] == first.json()["answer"]
    assert second.json()["quota"]["used"] == 1
    assert conflict.status_code == 409
    assert provider.calls == 1


def test_user_and_service_limits_are_atomic_and_report_the_blocking_scope(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_coach_per_user_request_limit", 1)
    monkeypatch.setattr(settings, "ai_coach_global_request_limit", 1)
    now = datetime(2026, 9, 15, 12, 0, 0)
    quota = PersistentAiCoachQuota(clock=lambda: now)

    with get_session_context() as db:
        first = quota.reserve(db, user_id=None, account_key="user-a", request_key="scope-1")
        assert first.granted
        assert quota.consume(db, request_key="scope-1")
        db.commit()

        user_blocked = quota.reserve(db, user_id=None, account_key="user-a", request_key="scope-2")
        assert not user_blocked.granted
        assert user_blocked.rate_limit_scope == AiCoachRateLimitScope.USER
        assert user_blocked.user_snapshot.remaining == 0
        assert user_blocked.service_snapshot.remaining == 0

        other_user = quota.reserve(db, user_id=None, account_key="user-b", request_key="scope-3")
        assert not other_user.granted
        assert other_user.rate_limit_scope == AiCoachRateLimitScope.SERVICE
        assert other_user.user_snapshot.remaining == 1


def test_expired_reservation_is_reclaimed_after_process_crash_window(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_coach_per_user_request_limit", 1)
    monkeypatch.setattr(settings, "ai_coach_global_request_limit", 10)
    current = [datetime(2026, 9, 15, 12, 0, 0)]
    quota = PersistentAiCoachQuota(clock=lambda: current[0])

    with get_session_context() as db:
        first = quota.reserve(db, user_id=None, account_key="crash-user", request_key="crash-1")
        assert first.granted
        current[0] += timedelta(minutes=11)
        recovered = quota.reserve(
            db,
            user_id=None,
            account_key="crash-user",
            request_key="crash-2",
        )

    assert recovered.granted
    assert recovered.user_snapshot.used == 0
    assert recovered.user_snapshot.remaining == 0


def test_reset_runtime_state_does_not_reset_durable_accounting(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_coach_per_user_request_limit", 2)
    monkeypatch.setattr(settings, "ai_coach_global_request_limit", 10)
    quota = PersistentAiCoachQuota(clock=lambda: datetime(2026, 9, 15, 12, 0, 0))

    with get_session_context() as db:
        reserved = quota.reserve(
            db, user_id=None, account_key="restart-user", request_key="restart-1"
        )
        assert reserved.granted
        assert quota.consume(db, request_key="restart-1")
        db.commit()
        quota.reset_runtime_state()
        next_request = quota.reserve(
            db,
            user_id=None,
            account_key="restart-user",
            request_key="restart-2",
        )

    assert next_request.granted
    assert next_request.user_snapshot.used == 1
    assert next_request.user_snapshot.remaining == 0


def test_stale_processing_is_recovered_on_conversation_reload_without_charge(
    client, monkeypatch
) -> None:
    _enable_chat(monkeypatch)
    telegram_user_id = 987_276_009
    headers = _login(client, telegram_user_id)
    conversation_id = _create_conversation(client, headers)
    request_id = "quota-stale-processing"

    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == telegram_user_id).one()
        conversation = get_owned_conversation(
            db,
            user_id=user.id,
            conversation_id=conversation_id,
        )
        assert conversation is not None
        reservation = ai_coach_chat_service.quota.reserve(
            db,
            user_id=user.id,
            request_key=request_id,
        )
        assert reservation.granted
        message = add_user_message(
            db,
            conversation=conversation,
            content="Восстановить зависший запрос",
            request_id=request_id,
            status="processing",
        )
        assert message.status == "failed"
        assert message.processing_started_at is not None
        message.processing_started_at = datetime.now() - timedelta(seconds=120)
        db.commit()

    response = client.get(
        f"/api/v1/ai-coach/conversations/{conversation_id}",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    recovered_message = response.json()["messages"][0]
    assert recovered_message["status"] == "failed"
    assert recovered_message["failure_category"] == "internal_error"
    assert "повторить" in recovered_message["limitations"][0].lower()
    quota = client.get("/api/v1/ai-coach/quota", headers=headers)
    assert quota.json()["used"] == 0
    assert quota.json()["remaining"] == 20
    with get_session_context() as db:
        persisted_reservation = (
            db.query(AiCoachQuotaReservation)
            .filter(AiCoachQuotaReservation.request_key == request_id)
            .one()
        )
        assert persisted_reservation.status == "released"
