from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from pydantic import SecretStr

from fitminiapp_api.ai_coach.chat_service import ai_coach_chat_service
from fitminiapp_api.ai_coach.contracts import (
    AiCoachDataClass,
    AiCoachPersonalTool,
    ContextCitation,
    ContextRef,
    NormalizedProviderError,
    ProviderErrorCode,
    ProviderTextResponse,
    ProviderTextResult,
)
from fitminiapp_api.ai_coach.personal_tools import PersonalToolResult
from fitminiapp_api.ai_coach.retrieval import ContextUnavailable
from fitminiapp_api.core.config import settings


def _login(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "username": f"chat_{telegram_user_id}"},
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
    monkeypatch.setattr(settings, "ai_coach_personal_enabled", True)
    monkeypatch.setattr(settings, "ai_coach_personal_data_policy", "verified_personal_user")
    ai_coach_chat_service.reset_runtime_state()


def _context_ref(ref_id: str = "public:test") -> ContextRef:
    citation = ContextCitation(
        title="Материал YFC",
        publisher="Your Fitness Coach",
        url="https://app.your-fitness-coach.ru/knowledge/training/rest-between-sets",
        source_type="public_page",
    )
    return ContextRef(
        ref_id=ref_id,
        title="Проверенный материал YFC",
        category="training",
        updated_at="2026-09-14",
        reviewer="YFC",
        canonical_url=str(citation.url),
        content="Проверенный контекст для тестового ответа на русском языке.",
        citations=(citation,),
    )


@dataclass
class StubTextProvider:
    calls: list[tuple[object, tuple[str, ...]]]
    answer: str = "Короткий проверенный ответ на русском языке."
    error: NormalizedProviderError | None = None

    provider_name: str = "stub"

    def generate_text(self, request, context_refs) -> ProviderTextResult:
        self.calls.append((request, tuple(ref.ref_id for ref in context_refs)))
        if self.error is not None:
            raise self.error
        return ProviderTextResult(
            provider="groq",
            configured_model="openai/gpt-oss-120b",
            actual_model="openai/gpt-oss-120b",
            response=ProviderTextResponse(answer=self.answer),
            latency_ms=2,
        )


def _create_conversation(client, headers: dict[str, str]) -> int:
    response = client.post("/api/v1/ai-coach/conversations", headers=headers)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def test_chat_accepts_arbitrary_question_without_period_report_json(
    client,
    monkeypatch,
) -> None:
    _enable_chat(monkeypatch)
    provider = StubTextProvider(calls=[])
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 987_100)
    conversation_id = _create_conversation(client, headers)

    response = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "Сколько отдыхать между подходами?"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["outcome"] == "answer"
    assert payload["data_class"] == "generic"
    assert payload["answer"] == provider.answer
    assert payload["assistant_message"]["content"] == provider.answer
    assert len(provider.calls) == 1
    request, context_ids = provider.calls[0]
    assert request.data_class == AiCoachDataClass.GENERIC
    assert request.message == "Сколько отдыхать между подходами?"
    assert request.conversation_history == ()
    assert request.memory_context == ()
    assert context_ids

    detail = client.get(f"/api/v1/ai-coach/conversations/{conversation_id}", headers=headers)
    assert detail.status_code == 200
    assert [item["role"] for item in detail.json()["messages"]] == ["user", "assistant"]


def test_chat_passes_bounded_follow_up_history_and_survives_reload(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    provider = StubTextProvider(calls=[])
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 987_101)
    conversation_id = _create_conversation(client, headers)

    first = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "Как читать прогресс в YFC?"},
    )
    second = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "А если одна запись недостаточна?"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(provider.calls) == 2
    follow_up_request = provider.calls[1][0]
    assert [turn.role for turn in follow_up_request.conversation_history] == [
        "user",
        "assistant",
    ]
    assert follow_up_request.conversation_history[0].content == "Как читать прогресс в YFC?"
    assert follow_up_request.conversation_history[1].content == provider.answer

    reloaded = client.get(
        f"/api/v1/ai-coach/conversations/{conversation_id}",
        headers=headers,
    )
    assert reloaded.status_code == 200
    assert len(reloaded.json()["messages"]) == 4
    assert reloaded.json()["messages"][-1]["content"] == provider.answer


def test_personal_context_requires_consent_before_reading_user_data(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    provider = StubTextProvider(calls=[])
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 987_102)
    conversation_id = _create_conversation(client, headers)

    without_consent = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "Что у меня сегодня по тренировке?"},
    )

    assert without_consent.status_code == 200
    assert without_consent.json()["outcome"] == "consent_required"
    assert provider.calls == []

    consent = client.put(
        "/api/v1/ai-coach/consent",
        headers=headers,
        json={"enabled": True},
    )
    assert consent.status_code == 200

    personal_ref = _context_ref("personal:test")
    personal_result = PersonalToolResult(
        tool=AiCoachPersonalTool.GET_PROGRESS_SUMMARY,
        purpose="Объяснение тестовой сводки.",
        period_start=date(2026, 8, 16),
        period_end=date(2026, 9, 14),
        data_sufficiency="sufficient",
        facts={"completed_workouts": 2},
        limitations=("Показаны только записанные данные.",),
        fallback_path="/progress",
        context_refs=(personal_ref,),
    )
    monkeypatch.setattr(
        "fitminiapp_api.ai_coach.context_selection.run_personal_tool",
        lambda db, user, tool, period_days: personal_result,
    )

    with_consent = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "Объясни мой прогресс за месяц."},
    )

    assert with_consent.status_code == 200, with_consent.text
    assert with_consent.json()["outcome"] == "answer"
    assert len(provider.calls) == 1
    personal_request, context_ids = provider.calls[0]
    assert personal_request.data_class == AiCoachDataClass.PERSONALIZED
    assert personal_request.memory_context == ()
    assert context_ids == ("personal:test",)


def test_invalid_provider_text_is_structured_failure_not_safety_failure(
    client, monkeypatch
) -> None:
    _enable_chat(monkeypatch)
    provider = StubTextProvider(
        calls=[],
        error=NormalizedProviderError(ProviderErrorCode.INVALID_OUTPUT),
    )
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 987_103)
    conversation_id = _create_conversation(client, headers)

    response = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "Объясни, зачем нужен отдых между подходами."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["outcome"] == "invalid_output"
    assert payload["failure_category"] == "structured_validation"
    assert payload["safety_category"] == "clear"
    assert payload["answer"] is None
    assert payload["assistant_message"] is None
    assert payload["user_message"]["status"] == "failed"
    assert "безопасно проверить" in payload["user_message"]["limitations"][0]


def test_public_context_failure_is_structured_without_provider_call(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    provider = StubTextProvider(calls=[])
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)

    def raise_context_failure(db, *, message, job):
        del db, message, job
        raise ContextUnavailable("public_context_unavailable")

    monkeypatch.setattr(
        "fitminiapp_api.ai_coach.context_selection.retrieve_context_for_message",
        raise_context_failure,
    )
    headers = _login(client, 987_108)
    conversation_id = _create_conversation(client, headers)

    response = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "Сколько отдыхать между подходами?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["outcome"] == "insufficient_data"
    assert payload["data_class"] == "generic"
    assert payload["failure_category"] == "context_failure"
    assert payload["safety_category"] == "clear"
    assert payload["assistant_message"]["content"]
    assert provider.calls == []


def test_invalid_provider_text_keeps_safe_prose_without_url(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    provider = StubTextProvider(
        calls=[],
        answer="Отдыхайте между подходами по самочувствию: https://example.org/guide",
    )
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 987_107)
    conversation_id = _create_conversation(client, headers)

    response = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "Сколько отдыхать между подходами?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["outcome"] == "invalid_output"
    assert payload["failure_category"] == "structured_validation"
    assert payload["safety_category"] == "clear"
    assert payload["answer"] == "Отдыхайте между подходами по самочувствию:"
    assert payload["assistant_message"]["content"] == payload["answer"]
    assert "https://" not in payload["answer"]


def test_conversation_isolation_and_delete(client) -> None:
    owner_headers = _login(client, 987_104)
    other_headers = _login(client, 987_105)
    conversation_id = _create_conversation(client, owner_headers)

    foreign_detail = client.get(
        f"/api/v1/ai-coach/conversations/{conversation_id}",
        headers=other_headers,
    )
    foreign_send = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=other_headers,
        json={"message": "Чужой разговор"},
    )
    assert foreign_detail.status_code == 404
    assert foreign_send.status_code == 404

    deleted = client.delete(
        f"/api/v1/ai-coach/conversations/{conversation_id}",
        headers=owner_headers,
    )
    assert deleted.status_code == 204
    assert (
        client.get(
            f"/api/v1/ai-coach/conversations/{conversation_id}",
            headers=owner_headers,
        ).status_code
        == 404
    )


def test_unsafe_chat_request_is_refused_without_provider_call(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    provider = StubTextProvider(calls=[])
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 987_106)
    conversation_id = _create_conversation(client, headers)

    response = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "Поставь мне диагноз по боли в колене."},
    )

    assert response.status_code == 200
    assert response.json()["outcome"] == "safety_refusal"
    assert response.json()["safety_category"] == "medical"
    assert response.json()["assistant_message"]["content"]
    assert provider.calls == []
