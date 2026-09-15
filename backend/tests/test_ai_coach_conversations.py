from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import pytest
from pydantic import SecretStr

from fitminiapp_api.ai_coach.chat_service import AiCoachChatService, ai_coach_chat_service
from fitminiapp_api.ai_coach.contracts import (
    AiCoachChatRequest,
    AiCoachDataClass,
    AiCoachJob,
    AiCoachPersonalTool,
    ChatOutputValidationReason,
    ContextCitation,
    ContextRef,
    NormalizedProviderError,
    ProviderErrorCode,
    ProviderFailureReason,
    ProviderTextResponse,
    ProviderTextResult,
)
from fitminiapp_api.ai_coach.personal_tools import PersonalToolResult
from fitminiapp_api.ai_coach.retrieval import ContextUnavailable
from fitminiapp_api.core.config import settings
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.ai_coach import AiCoachConversationMessageRequest
from fitminiapp_api.models.audit import AuditEvent


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
    repair_answer: str | None = None
    repair_error: NormalizedProviderError | None = None
    repair_calls: list[tuple[object, str, ChatOutputValidationReason]] | None = None

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

    def repair_text(
        self,
        request,
        answer: str,
        reason: ChatOutputValidationReason,
    ) -> ProviderTextResult:
        if self.repair_calls is not None:
            self.repair_calls.append((request, answer, reason))
        if self.repair_error is not None:
            raise self.repair_error
        return ProviderTextResult(
            provider="groq",
            configured_model="openai/gpt-oss-120b",
            actual_model="openai/gpt-oss-120b",
            response=ProviderTextResponse(answer=self.repair_answer or self.answer),
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

    history = client.get("/api/v1/ai-coach/conversations", headers=headers)
    assert history.status_code == 200
    assert history.json()["items"][0]["title"] == "Сколько отдыхать между подходами?"


def test_chat_calls_provider_for_general_question_without_app_context(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    provider = StubTextProvider(calls=[])
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    monkeypatch.setattr(
        "fitminiapp_api.ai_coach.context_selection.retrieve_context_for_message",
        lambda db, *, message, job: (),
    )
    headers = _login(client, 987_109)
    conversation_id = _create_conversation(client, headers)

    response = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "Сколько нужно пить воды?"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "answer"
    assert response.json()["data_class"] == "generic"
    assert len(provider.calls) == 1
    request, context_ids = provider.calls[0]
    assert request.context_kind.value == "none"
    assert request.locale == "ru"
    assert context_ids == ()


def test_generic_question_does_not_forward_prior_personal_history(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    provider = StubTextProvider(calls=[])
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    monkeypatch.setattr(
        "fitminiapp_api.ai_coach.context_selection.retrieve_context_for_message",
        lambda db, *, message, job: (),
    )
    monkeypatch.setattr(
        "fitminiapp_api.api.v1.ai_coach.history_turns",
        lambda db, conversation_id: (
            {"role": "user", "content": "Что у меня по прогрессу?"},
            {"role": "assistant", "content": "Ваш личный показатель: 80 кг."},
            {"role": "user", "content": "Объясни общие правила."},
            {"role": "assistant", "content": "Общий контекст без личных фактов."},
        ),
    )
    headers = _login(client, 987_122)
    conversation_id = _create_conversation(client, headers)

    response = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "Сколько нужно пить воды?"},
    )

    assert response.status_code == 200, response.text
    request, context_ids = provider.calls[0]
    assert request.data_class == AiCoachDataClass.GENERIC
    assert [turn.content for turn in request.conversation_history] == [
        "Объясни общие правила.",
        "Общий контекст без личных фактов.",
    ]
    assert all("80 кг" not in turn.content for turn in request.conversation_history)
    assert context_ids == ()


def test_chat_calls_provider_for_general_kbju_question_without_app_context(
    client, monkeypatch
) -> None:
    _enable_chat(monkeypatch)
    provider = StubTextProvider(calls=[])
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    monkeypatch.setattr(
        "fitminiapp_api.ai_coach.context_selection.retrieve_context_for_message",
        lambda db, *, message, job: (),
    )
    headers = _login(client, 987_116)
    conversation_id = _create_conversation(client, headers)

    response = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "Как рассчитать КБЖУ?"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "answer"
    assert len(provider.calls) == 1
    assert provider.calls[0][0].context_kind.value == "none"
    assert provider.calls[0][1] == ()


def test_chat_follows_current_question_language(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    provider = StubTextProvider(calls=[], answer="A short answer in English.")
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    monkeypatch.setattr(
        "fitminiapp_api.ai_coach.context_selection.retrieve_context_for_message",
        lambda db, *, message, job: (),
    )
    headers = _login(client, 987_110)
    conversation_id = _create_conversation(client, headers)

    response = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "How much water should I drink?"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "answer"
    assert response.json()["answer"] == provider.answer
    assert provider.calls[0][0].locale == "en"


def test_chat_keeps_personal_generation_when_allowed_context_is_insufficient(
    client, monkeypatch
) -> None:
    _enable_chat(monkeypatch)
    provider = StubTextProvider(calls=[])
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 987_111)
    conversation_id = _create_conversation(client, headers)
    assert (
        client.put(
            "/api/v1/ai-coach/consent",
            headers=headers,
            json={"enabled": True},
        ).status_code
        == 200
    )
    personal_result = PersonalToolResult(
        tool=AiCoachPersonalTool.GET_PROGRESS_SUMMARY,
        purpose="Объяснение тестовой сводки.",
        period_start=date(2026, 8, 16),
        period_end=date(2026, 9, 14),
        data_sufficiency="insufficient",
        facts={"completed_workouts": None},
        limitations=("За период нет записанных тренировок.",),
        fallback_path="/progress",
        context_refs=(_context_ref("personal:insufficient"),),
    )
    monkeypatch.setattr(
        "fitminiapp_api.ai_coach.context_selection.run_personal_tool",
        lambda db, user, tool, period_days: personal_result,
    )

    response = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "Объясни мой прогресс за месяц."},
    )

    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "answer"
    assert response.json()["answer"] == provider.answer
    assert len(provider.calls) == 1
    assert provider.calls[0][0].data_class == AiCoachDataClass.PERSONALIZED
    assert provider.calls[0][1] == ("personal:insufficient",)


def test_chat_selects_explicit_help_and_personal_context_scopes(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    provider = StubTextProvider(calls=[])
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 987_113)
    assert (
        client.put(
            "/api/v1/ai-coach/consent",
            headers=headers,
            json={"enabled": True},
        ).status_code
        == 200
    )
    shared_ref = _context_ref("scope:test")

    def result_for(tool: AiCoachPersonalTool) -> PersonalToolResult:
        return PersonalToolResult(
            tool=tool,
            purpose="Тестовая разрешённая сводка.",
            period_start=date(2026, 8, 16),
            period_end=date(2026, 9, 14),
            data_sufficiency="sufficient",
            facts={"value": 1},
            limitations=(),
            fallback_path="/progress",
            context_refs=(shared_ref,),
        )

    monkeypatch.setattr(
        "fitminiapp_api.ai_coach.context_selection.retrieve_context_for_message",
        lambda db, *, message, job: (shared_ref,),
    )
    help_conversation = _create_conversation(client, headers)
    help_response = client.post(
        f"/api/v1/ai-coach/conversations/{help_conversation}/messages",
        headers=headers,
        json={"message": "Где посмотреть мой прогресс?"},
    )
    assert help_response.status_code == 200
    assert provider.calls[-1][0].context_kind.value == "app_capabilities"

    monkeypatch.setattr(
        "fitminiapp_api.ai_coach.context_selection.get_workout_context_tool",
        lambda db, user, *, focus: result_for(AiCoachPersonalTool.GET_RECENT_TRAINING_SUMMARY),
    )
    today_conversation = _create_conversation(client, headers)
    today_response = client.post(
        f"/api/v1/ai-coach/conversations/{today_conversation}/messages",
        headers=headers,
        json={"message": "Что у меня сегодня по тренировке?"},
    )
    assert today_response.status_code == 200
    assert provider.calls[-1][0].context_kind.value == "active_program"

    program_conversation = _create_conversation(client, headers)
    program_response = client.post(
        f"/api/v1/ai-coach/conversations/{program_conversation}/messages",
        headers=headers,
        json={"message": "Что у меня в текущей программе?"},
    )
    assert program_response.status_code == 200
    assert provider.calls[-1][0].context_kind.value == "active_program"

    monkeypatch.setattr(
        "fitminiapp_api.ai_coach.context_selection.get_bench_history_tool",
        lambda db, user, period_days: result_for(AiCoachPersonalTool.GET_RECENT_TRAINING_SUMMARY),
    )
    bench_conversation = _create_conversation(client, headers)
    bench_response = client.post(
        f"/api/v1/ai-coach/conversations/{bench_conversation}/messages",
        headers=headers,
        json={"message": "Что у меня по жиму?"},
    )
    assert bench_response.status_code == 200
    assert provider.calls[-1][0].context_kind.value == "bench_history"

    program_bench_conversation = _create_conversation(client, headers)
    program_bench_response = client.post(
        f"/api/v1/ai-coach/conversations/{program_bench_conversation}/messages",
        headers=headers,
        json={"message": "Почему у меня не растёт жим в программе?"},
    )
    assert program_bench_response.status_code == 200
    assert provider.calls[-1][0].context_kind.value == "bench_history"

    ai_coach_chat_service.reset_runtime_state()
    monkeypatch.setattr(
        "fitminiapp_api.ai_coach.context_selection.get_nutrition_summary_tool",
        lambda db, user, period_days, *, include_profile_goals: result_for(
            AiCoachPersonalTool.GET_NUTRITION_SUMMARY
        ),
    )
    nutrition_conversation = _create_conversation(client, headers)
    nutrition_response = client.post(
        f"/api/v1/ai-coach/conversations/{nutrition_conversation}/messages",
        headers=headers,
        json={"message": "Какие у меня цели питания?"},
    )
    assert nutrition_response.status_code == 200
    assert provider.calls[-1][0].context_kind.value == "profile_goals"


def test_chat_app_help_question_about_ai_coach_uses_capabilities_scope(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    provider = StubTextProvider(calls=[])
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    monkeypatch.setattr(
        "fitminiapp_api.ai_coach.context_selection.retrieve_context_for_message",
        lambda db, *, message, job: (),
    )
    headers = _login(client, 987_117)
    conversation_id = _create_conversation(client, headers)

    response = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "Как пользоваться AI Coach?"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "answer"
    assert response.json()["data_class"] == "generic"
    assert provider.calls[0][0].context_kind.value == "app_capabilities"
    assert provider.calls[0][1] == ()


def test_personal_follow_up_reuses_previous_context_scope(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    provider = StubTextProvider(calls=[])
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 987_116)
    assert (
        client.put(
            "/api/v1/ai-coach/consent",
            headers=headers,
            json={"enabled": True},
        ).status_code
        == 200
    )
    personal_ref = _context_ref("personal:follow-up")
    personal_result = PersonalToolResult(
        tool=AiCoachPersonalTool.GET_RECENT_TRAINING_SUMMARY,
        purpose="Тестовая сводка расписания.",
        period_start=date(2026, 8, 16),
        period_end=date(2026, 9, 14),
        data_sufficiency="sufficient",
        facts={"today_workouts": []},
        limitations=(),
        fallback_path="/today",
        context_refs=(personal_ref,),
    )
    monkeypatch.setattr(
        "fitminiapp_api.ai_coach.context_selection.get_workout_context_tool",
        lambda db, user, *, focus: personal_result,
    )
    conversation_id = _create_conversation(client, headers)

    first = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "Что у меня сегодня по тренировке?"},
    )
    follow_up = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "А если я не успею?"},
    )

    assert first.status_code == 200
    assert follow_up.status_code == 200
    assert provider.calls[1][0].context_kind.value == "active_program"
    assert provider.calls[1][1] == ("personal:follow-up",)


def test_chat_passes_bounded_follow_up_history_and_survives_reload(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    provider = StubTextProvider(calls=[], answer="Первая строка ответа.\n\nВторая строка ответа.")
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


def test_invalid_provider_text_is_provider_failure_not_safety_failure(client, monkeypatch) -> None:
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
    assert payload["failure_category"] == "provider_failure"
    assert payload["safety_category"] == "clear"
    assert payload["answer"] is None
    assert payload["assistant_message"] is None
    assert payload["user_message"]["status"] == "failed"
    assert "безопасно проверить" not in payload["user_message"]["limitations"][0]


def test_finish_length_retries_once_for_personalized_chat_and_records_reason(
    monkeypatch,
    caplog,
) -> None:
    _enable_chat(monkeypatch)
    monkeypatch.setattr(settings, "ai_coach_max_attempts", 2)

    @dataclass
    class FinishLengthThenSuccessProvider:
        calls: list[object]
        provider_name: str = "stub"

        def generate_text(self, request, context_refs) -> ProviderTextResult:
            del context_refs
            self.calls.append(request)
            if len(self.calls) == 1:
                raise NormalizedProviderError(
                    ProviderErrorCode.INVALID_OUTPUT,
                    retryable=False,
                    provider_failure_reason=ProviderFailureReason.FINISH_REASON_LENGTH,
                    http_status=200,
                    finish_reason="length",
                    response_bytes=128,
                )
            return ProviderTextResult(
                provider="groq",
                configured_model="openai/gpt-oss-120b",
                actual_model="openai/gpt-oss-120b",
                response=ProviderTextResponse(answer="Короткий персональный ответ."),
                latency_ms=2,
                finish_reason="stop",
                response_bytes=256,
            )

        def repair_text(self, request, answer, reason) -> ProviderTextResult:
            del request, answer, reason
            raise AssertionError("presentation repair is not expected")

    provider = FinishLengthThenSuccessProvider(calls=[])
    with caplog.at_level(logging.INFO, logger="app.ai_coach"):
        result = AiCoachChatService(provider=provider).generate(
            request=AiCoachChatRequest(
                job=AiCoachJob.FITNESS_KNOWLEDGE,
                context_id="personal:training",
                message="Объясни мой прогресс.",
                data_class=AiCoachDataClass.PERSONALIZED,
            ),
            user_key="personal-retry-user",
            request_id="personal-retry-request",
            context_refs=(),
        )

    assert result.outcome == "answer"
    assert len(provider.calls) == 2
    assert provider.calls[0].retry_hint is False
    assert provider.calls[1].retry_hint is True
    records = [item for item in caplog.records if item.getMessage() == "ai_coach_chat_generation"]
    assert records[-1].provider_failure_reason == "finish_reason_length"
    assert records[-1].finish_reason == "length"
    assert records[-1].attempts == 2
    assert records[-1].retry_count == 1


def test_repeated_finish_length_fails_closed_without_global_cooldown(monkeypatch) -> None:
    _enable_chat(monkeypatch)
    monkeypatch.setattr(settings, "ai_coach_max_attempts", 2)

    @dataclass
    class AlwaysFinishLengthProvider:
        calls: int = 0
        provider_name: str = "stub"

        def generate_text(self, request, context_refs) -> ProviderTextResult:
            del request, context_refs
            self.calls += 1
            raise NormalizedProviderError(
                ProviderErrorCode.INVALID_OUTPUT,
                retryable=True,
                provider_failure_reason=ProviderFailureReason.FINISH_REASON_LENGTH,
                http_status=200,
                finish_reason="length",
            )

        def repair_text(self, request, answer, reason) -> ProviderTextResult:
            del request, answer, reason
            raise AssertionError("presentation repair is not expected")

    provider = AlwaysFinishLengthProvider()
    service = AiCoachChatService(provider=provider)
    result = service.generate(
        request=AiCoachChatRequest(
            job=AiCoachJob.FITNESS_KNOWLEDGE,
            context_id="knowledge:test",
            message="Сколько отдыхать между подходами?",
            data_class=AiCoachDataClass.GENERIC,
        ),
        user_key="length-failure-user",
        request_id="length-failure-request",
        context_refs=(),
    )

    assert result.outcome == "invalid_output"
    assert result.provider_failure_reason == ProviderFailureReason.FINISH_REASON_LENGTH
    assert provider.calls == 2
    assert service.cooldown.active() is False


def test_timeout_gets_one_bounded_retry_without_global_cooldown(monkeypatch) -> None:
    _enable_chat(monkeypatch)
    monkeypatch.setattr(settings, "ai_coach_max_attempts", 2)

    @dataclass
    class AlwaysTimeoutProvider:
        calls: int = 0
        provider_name: str = "stub"

        def generate_text(self, request, context_refs) -> ProviderTextResult:
            assert request.retry_hint is False
            del context_refs
            self.calls += 1
            raise NormalizedProviderError(
                ProviderErrorCode.TIMEOUT,
                retryable=True,
                provider_failure_reason=ProviderFailureReason.TIMEOUT,
            )

        def repair_text(self, request, answer, reason) -> ProviderTextResult:
            del request, answer, reason
            raise AssertionError("presentation repair is not expected")

    provider = AlwaysTimeoutProvider()
    service = AiCoachChatService(provider=provider)
    result = service.generate(
        request=AiCoachChatRequest(
            job=AiCoachJob.FITNESS_KNOWLEDGE,
            context_id="knowledge:test",
            message="Сколько отдыхать между подходами?",
            data_class=AiCoachDataClass.GENERIC,
        ),
        user_key="timeout-user",
        request_id="timeout-request",
        context_refs=(),
    )

    assert result.outcome == "unavailable"
    assert result.failure_category == "timeout"
    assert result.provider_failure_reason == ProviderFailureReason.TIMEOUT
    assert provider.calls == 2
    assert service.cooldown.active() is False


def test_transient_provider_5xx_gets_one_bounded_retry_and_recovers(monkeypatch, caplog) -> None:
    _enable_chat(monkeypatch)
    monkeypatch.setattr(settings, "ai_coach_max_attempts", 2)

    @dataclass
    class ServerErrorThenSuccessProvider:
        calls: int = 0
        provider_name: str = "stub"

        def generate_text(self, request, context_refs) -> ProviderTextResult:
            del context_refs
            self.calls += 1
            if self.calls == 1:
                assert request.retry_hint is False
                raise NormalizedProviderError(
                    ProviderErrorCode.PROVIDER_UNAVAILABLE,
                    retryable=True,
                    provider_failure_reason=ProviderFailureReason.HTTP_5XX,
                    http_status=503,
                )
            assert request.retry_hint is False
            return ProviderTextResult(
                provider="groq",
                configured_model="openai/gpt-oss-120b",
                actual_model="openai/gpt-oss-120b",
                response=ProviderTextResponse(answer="Ответ после временной ошибки."),
                latency_ms=2,
                finish_reason="stop",
            )

        def repair_text(self, request, answer, reason) -> ProviderTextResult:
            del request, answer, reason
            raise AssertionError("presentation repair is not expected")

    provider = ServerErrorThenSuccessProvider()
    service = AiCoachChatService(provider=provider)
    request = AiCoachChatRequest(
        job=AiCoachJob.FITNESS_KNOWLEDGE,
        context_id="knowledge:test",
        message="Сколько отдыхать между подходами?",
        data_class=AiCoachDataClass.GENERIC,
    )
    with caplog.at_level(logging.INFO, logger="app.ai_coach"):
        result = service.generate(
            request=request,
            user_key="5xx-recovery-user",
            request_id="5xx-recovery-request",
            context_refs=(),
        )

    assert result.outcome == "answer"
    assert provider.calls == 2
    assert service.cooldown.active() is False
    records = [item for item in caplog.records if item.getMessage() == "ai_coach_chat_generation"]
    assert records[-1].provider_failure_reason == "http_5xx"
    assert records[-1].http_status == 503
    assert records[-1].attempts == 2
    assert records[-1].retry_count == 1


def test_rate_limit_is_not_retried_and_honors_cooldown(monkeypatch) -> None:
    _enable_chat(monkeypatch)
    monkeypatch.setattr(settings, "ai_coach_max_attempts", 2)

    @dataclass
    class RateLimitedProvider:
        calls: int = 0
        provider_name: str = "stub"

        def generate_text(self, request, context_refs) -> ProviderTextResult:
            del context_refs
            self.calls += 1
            raise NormalizedProviderError(
                ProviderErrorCode.RATE_LIMITED,
                retry_after_seconds=17,
                provider_failure_reason=ProviderFailureReason.HTTP_429,
                http_status=429,
            )

        def repair_text(self, request, answer, reason) -> ProviderTextResult:
            del request, answer, reason
            raise AssertionError("presentation repair is not expected")

    provider = RateLimitedProvider()
    service = AiCoachChatService(provider=provider)
    result = service.generate(
        request=AiCoachChatRequest(
            job=AiCoachJob.FITNESS_KNOWLEDGE,
            context_id="knowledge:test",
            message="Сколько отдыхать между подходами?",
            data_class=AiCoachDataClass.GENERIC,
        ),
        user_key="rate-limit-user",
        request_id="rate-limit-request",
        context_refs=(),
    )

    assert result.outcome == "rate_limited"
    assert result.provider_failure_reason == ProviderFailureReason.HTTP_429
    assert provider.calls == 1
    assert service.cooldown.active() is True


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (401, ProviderFailureReason.HTTP_401),
        (403, ProviderFailureReason.HTTP_403),
    ],
)
def test_auth_provider_failure_is_not_retried(monkeypatch, status, reason) -> None:
    _enable_chat(monkeypatch)
    monkeypatch.setattr(settings, "ai_coach_max_attempts", 2)

    @dataclass
    class AuthFailureProvider:
        calls: int = 0
        provider_name: str = "stub"

        def generate_text(self, request, context_refs) -> ProviderTextResult:
            del request, context_refs
            self.calls += 1
            raise NormalizedProviderError(
                ProviderErrorCode.AUTHENTICATION_FAILED,
                misconfigured=True,
                provider_failure_reason=reason,
                http_status=status,
            )

        def repair_text(self, request, answer, reason) -> ProviderTextResult:
            del request, answer, reason
            raise AssertionError("presentation repair is not expected")

    provider = AuthFailureProvider()
    service = AiCoachChatService(provider=provider)
    result = service.generate(
        request=AiCoachChatRequest(
            job=AiCoachJob.FITNESS_KNOWLEDGE,
            context_id="knowledge:test",
            message="Сколько отдыхать между подходами?",
            data_class=AiCoachDataClass.GENERIC,
        ),
        user_key=f"auth-user-{status}",
        request_id=f"auth-request-{status}",
        context_refs=(),
    )

    assert result.outcome == "unavailable"
    assert result.provider_failure_reason == reason
    assert provider.calls == 1
    assert service.cooldown.active() is True


def test_global_cooldown_waits_for_repeated_provider_5xx(monkeypatch) -> None:
    _enable_chat(monkeypatch)
    monkeypatch.setattr(settings, "ai_coach_max_attempts", 1)

    @dataclass
    class AlwaysServerErrorProvider:
        calls: int = 0
        provider_name: str = "stub"

        def generate_text(self, request, context_refs) -> ProviderTextResult:
            del request, context_refs
            self.calls += 1
            raise NormalizedProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                retryable=True,
                provider_failure_reason=ProviderFailureReason.HTTP_5XX,
                http_status=503,
            )

        def repair_text(self, request, answer, reason) -> ProviderTextResult:
            del request, answer, reason
            raise AssertionError("presentation repair is not expected")

    provider = AlwaysServerErrorProvider()
    service = AiCoachChatService(provider=provider)
    request = AiCoachChatRequest(
        job=AiCoachJob.FITNESS_KNOWLEDGE,
        context_id="knowledge:test",
        message="Сколько отдыхать между подходами?",
        data_class=AiCoachDataClass.GENERIC,
    )
    for index in range(3):
        result = service.generate(
            request=request,
            user_key=f"5xx-user-{index}",
            request_id=f"5xx-request-{index}",
            context_refs=(),
        )
        assert result.outcome == "unavailable"
    assert service.cooldown.active() is True
    blocked = service.generate(
        request=request,
        user_key="5xx-user-blocked",
        request_id="5xx-request-blocked",
        context_refs=(),
    )
    assert blocked.outcome == "unavailable"
    assert provider.calls == 3


def test_conversation_retry_reuses_failed_user_message_without_duplicate_history(
    client,
    monkeypatch,
) -> None:
    _enable_chat(monkeypatch)

    @dataclass
    class FailOnceProvider:
        calls: int = 0
        provider_name: str = "stub"

        def generate_text(self, request, context_refs) -> ProviderTextResult:
            del request, context_refs
            self.calls += 1
            if self.calls == 1:
                raise NormalizedProviderError(
                    ProviderErrorCode.INVALID_OUTPUT,
                    provider_failure_reason=ProviderFailureReason.FINISH_REASON_OTHER,
                    finish_reason="content_filter",
                )
            return ProviderTextResult(
                provider="groq",
                configured_model="openai/gpt-oss-120b",
                actual_model="openai/gpt-oss-120b",
                response=ProviderTextResponse(answer="Ответ после повторной попытки."),
                latency_ms=2,
                finish_reason="stop",
            )

        def repair_text(self, request, answer, reason) -> ProviderTextResult:
            del request, answer, reason
            raise AssertionError("presentation repair is not expected")

    provider = FailOnceProvider()
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 987_106)
    conversation_id = _create_conversation(client, headers)
    initial = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "Сколько отдыхать между подходами?"},
    )

    assert initial.status_code == 200, initial.text
    failed_message_id = initial.json()["user_message"]["id"]
    assert initial.json()["user_message"]["status"] == "failed"

    retried = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages/{failed_message_id}/retry",
        headers=headers,
    )

    assert retried.status_code == 200, retried.text
    assert retried.json()["user_message"]["id"] == failed_message_id
    assert retried.json()["user_message"]["status"] == "complete"
    assert retried.json()["assistant_message"]["content"] == "Ответ после повторной попытки."
    detail = client.get(
        f"/api/v1/ai-coach/conversations/{conversation_id}",
        headers=headers,
    )
    assert [item["role"] for item in detail.json()["messages"]] == ["user", "assistant"]
    assert [item["id"] for item in detail.json()["messages"]].count(failed_message_id) == 1
    assert provider.calls == 2


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
    assert payload["outcome"] == "unavailable"
    assert payload["data_class"] == "generic"
    assert payload["failure_category"] == "context_failure"
    assert payload["safety_category"] == "clear"
    assert payload["assistant_message"]["content"] == (
        "Не удалось получить материалы для ответа. Попробуйте ещё раз позже."
    )
    assert provider.calls == []


def test_chat_accepts_two_thousand_character_input_and_rejects_more(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    provider = StubTextProvider(calls=[])
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    monkeypatch.setattr(
        "fitminiapp_api.ai_coach.context_selection.retrieve_context_for_message",
        lambda db, *, message, job: (),
    )
    headers = _login(client, 987_112)
    conversation_id = _create_conversation(client, headers)
    accepted = "а" * 2_000

    response = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": accepted},
    )

    assert response.status_code == 200, response.text
    assert response.json()["user_message"]["content"] == accepted
    follow_up = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "Продолжим?"},
    )
    assert follow_up.status_code == 200, follow_up.text
    assert provider.calls[1][0].conversation_history[0].content == accepted
    too_long = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": accepted + "а"},
    )
    assert too_long.status_code == 422


def test_invalid_provider_text_keeps_safe_prose_without_url(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    provider = StubTextProvider(
        calls=[],
        answer="Отдыхайте между подходами по самочувствию: https://example.org/guide",
        repair_calls=[],
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
    assert payload["outcome"] == "answer"
    assert payload["failure_category"] is None
    assert payload["safety_category"] == "clear"
    assert payload["answer"] == "Отдыхайте между подходами по самочувствию:"
    assert payload["assistant_message"]["content"] == payload["answer"]
    assert "https://" not in payload["answer"]
    assert provider.repair_calls == []


def test_personal_chat_does_not_expose_internal_screen_citations(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    provider = StubTextProvider(calls=[])
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 987_114)
    conversation_id = _create_conversation(client, headers)
    assert (
        client.put(
            "/api/v1/ai-coach/consent",
            headers=headers,
            json={"enabled": True},
        ).status_code
        == 200
    )
    internal_citation = ContextCitation(
        title="Сводка питания",
        publisher="Your Fitness Coach",
        url="https://your-fitness-coach.ru/nutrition",
        source_type="personal_tool_screen",
    )
    personal_result = PersonalToolResult(
        tool=AiCoachPersonalTool.GET_NUTRITION_SUMMARY,
        purpose="Объяснение тестовой сводки.",
        period_start=date(2026, 8, 16),
        period_end=date(2026, 9, 14),
        data_sufficiency="sufficient",
        facts={"logged_days": 3},
        limitations=(),
        fallback_path="/nutrition",
        context_refs=(
            ContextRef(
                ref_id="personal-tool:get_nutrition_summary",
                title="Сводка питания",
                category="personal_tool",
                updated_at="2026-09-14",
                reviewer="YFC",
                canonical_url=internal_citation.url,
                content='{"facts":{"logged_days":3}}',
                citations=(internal_citation,),
            ),
        ),
    )
    monkeypatch.setattr(
        "fitminiapp_api.ai_coach.context_selection.run_personal_tool",
        lambda db, user, tool, period_days: personal_result,
    )

    response = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "Как у меня питание?"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "answer"
    assert response.json()["citations"] == []
    assert "/nutrition" not in response.text


def test_json_chat_output_is_repaired_to_plain_text(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    provider = StubTextProvider(
        calls=[],
        answer='{"answer":"Текст"}',
        repair_answer="Отдых между подходами зависит от цели и интенсивности.",
        repair_calls=[],
    )
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 987_115)
    conversation_id = _create_conversation(client, headers)

    response = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "Сколько отдыхать между подходами?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["outcome"] == "answer"
    assert payload["answer"] == provider.repair_answer
    assert payload["assistant_message"]["content"] == provider.repair_answer
    assert provider.repair_calls[0][2].value == "json_container"


def test_long_chat_output_is_repaired_at_conversation_endpoint(client, monkeypatch) -> None:
    _enable_chat(monkeypatch)
    long_draft = "Безопасное объяснение отдыха между подходами. " + (
        "Длительность зависит от цели и интенсивности тренировки. " * 48
    )
    provider = StubTextProvider(
        calls=[],
        answer=long_draft,
        repair_answer="Для тяжёлых подходов обычно нужен более длинный отдых, чтобы восстановить силу и технику.",
        repair_calls=[],
    )
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 987_116)
    conversation_id = _create_conversation(client, headers)

    response = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={"message": "Сколько отдыхать между подходами и почему?"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["outcome"] == "answer"
    assert payload["answer"] == provider.repair_answer
    assert payload["failure_category"] is None
    assert payload["user_message"]["status"] == "complete"
    assert payload["assistant_message"]["content"] == provider.repair_answer
    assert provider.repair_calls[0][2] == ChatOutputValidationReason.TOO_LONG


def _direct_chat_request(
    message: str,
    *,
    data_class: AiCoachDataClass = AiCoachDataClass.GENERIC,
    locale: str = "ru",
) -> AiCoachChatRequest:
    return AiCoachChatRequest(
        job=AiCoachJob.FITNESS_KNOWLEDGE,
        context_id="direct-chat-regression-v1",
        message=message,
        data_class=data_class,
        locale=locale,
    )


def _generate_direct_chat(monkeypatch, provider: StubTextProvider, request: AiCoachChatRequest):
    _enable_chat(monkeypatch)
    return AiCoachChatService(provider=provider).generate(
        request=request,
        user_key="direct-chat-user",
        request_id="direct-chat-request",
        context_refs=(),
    )


def test_production_like_long_safe_draft_is_repaired_once(monkeypatch) -> None:
    long_draft = "Безопасное объяснение отдыха между подходами. " + (
        "Длительность зависит от цели и интенсивности тренировки. " * 48
    )
    provider = StubTextProvider(
        calls=[],
        answer=long_draft,
        repair_answer="Для тяжёлых подходов обычно нужен более длинный отдых, чтобы восстановить силу и технику.",
        repair_calls=[],
    )

    result = _generate_direct_chat(
        monkeypatch,
        provider,
        _direct_chat_request("Сколько отдыхать между подходами и почему?"),
    )

    assert len(long_draft) > 1_600
    assert result.outcome == "answer"
    assert result.answer == provider.repair_answer
    assert result.failure_category is None
    assert result.repair_attempted is True
    assert result.repair_success is True
    assert result.validation_failure_reason.value == "too_long"
    assert len(provider.repair_calls) == 1
    assert provider.repair_calls[0][2].value == "too_long"


def test_overlong_safe_repair_is_bounded_without_second_provider_call(monkeypatch) -> None:
    long_draft = "Безопасное объяснение отдыха между подходами. " + (
        "Длительность зависит от цели и интенсивности тренировки. " * 48
    )
    overlong_repair = "Сохраняйте технику и качество повторений. " + (
        "Отдых подбирают по цели и восстановлению. " * 80
    )
    provider = StubTextProvider(
        calls=[],
        answer=long_draft,
        repair_answer=overlong_repair,
        repair_calls=[],
    )

    result = _generate_direct_chat(
        monkeypatch,
        provider,
        _direct_chat_request("Сколько отдыхать между подходами и почему?"),
    )

    assert len(overlong_repair) > 1_600
    assert result.outcome == "answer"
    assert result.answer is not None
    assert len(result.answer) <= 1_600
    assert result.failure_category is None
    assert result.repair_attempted is True
    assert result.repair_success is True
    assert len(provider.repair_calls) == 1


@pytest.mark.parametrize(
    "answer",
    [
        "**Отдых между подходами** обычно дольше в тяжёлых базовых упражнениях.",
        "Используй RIR/RPE и Top Set как ориентиры интенсивности, а не как служебные метки.",
        "Рекомендую отдыхать достаточно, чтобы сохранить технику, скорость и качество повторений.",
        "Покажи пример разминки перед лёгкой тренировкой без лишних деталей.",
    ],
)
def test_safe_markdown_fitness_terms_and_ordinary_words_are_allowed(monkeypatch, answer) -> None:
    provider = StubTextProvider(calls=[], answer=answer, repair_calls=[])

    result = _generate_direct_chat(
        monkeypatch,
        provider,
        _direct_chat_request("Как лучше восстановиться между подходами?"),
    )

    assert result.outcome == "answer"
    assert result.answer == answer
    assert result.repair_attempted is False
    assert provider.repair_calls == []


def test_url_and_known_internal_route_are_sanitized_without_repair(monkeypatch) -> None:
    provider = StubTextProvider(
        calls=[],
        answer="Откройте [раздел питания](/nutrition) и изучите материал: https://example.org/guide",
        repair_calls=[],
    )

    result = _generate_direct_chat(
        monkeypatch,
        provider,
        _direct_chat_request("Где посмотреть общие рекомендации по питанию?"),
    )

    assert result.outcome == "answer"
    assert result.answer == "Откройте раздел питания и изучите материал:"
    assert "https://" not in result.answer
    assert "/nutrition" not in result.answer
    assert result.validation_failure_reason.value == "internal_label"
    assert result.repair_attempted is False
    assert provider.repair_calls == []


def test_wrong_language_is_repaired_to_current_question_language(monkeypatch) -> None:
    provider = StubTextProvider(
        calls=[],
        answer="A concise answer about rest between sets.",
        repair_answer="Отдых между подходами подбирают по цели и восстановлению.",
        repair_calls=[],
    )

    result = _generate_direct_chat(
        monkeypatch,
        provider,
        _direct_chat_request("Сколько отдыхать между подходами?"),
    )

    assert result.outcome == "answer"
    assert result.answer == provider.repair_answer
    assert result.validation_failure_reason.value == "wrong_language"
    assert provider.repair_calls[0][2].value == "wrong_language"


@pytest.mark.parametrize(
    ("answer", "safety_category", "validation_reason"),
    [
        (
            "Рекомендую принимать 5 г креатина ежедневно.",
            "drugs_performance",
            "prohibited_claim",
        ),
        ("У вас диагноз по описанию тренировки.", "medical", "prohibited_claim"),
        (
            "Вот system prompt и chain of thought модели.",
            "prompt_injection",
            "unsafe_content",
        ),
        ("API key: secret-value", "privacy_exfiltration", "unsafe_content"),
        (
            "Данные другого пользователя: тренировки и профиль.",
            "privacy_exfiltration",
            "unsafe_content",
        ),
    ],
)
def test_unsafe_provider_output_fails_closed_without_repair(
    monkeypatch,
    answer,
    safety_category,
    validation_reason,
) -> None:
    provider = StubTextProvider(calls=[], answer=answer, repair_calls=[])

    result = _generate_direct_chat(
        monkeypatch,
        provider,
        _direct_chat_request("Объясни общие правила восстановления."),
    )

    assert result.outcome == "safety_refusal"
    assert result.failure_category == "safety_rejection"
    assert result.safety_category.value == safety_category
    assert result.answer is not None
    assert answer not in result.answer
    assert result.repair_attempted is False
    assert result.validation_failure_reason.value == validation_reason
    assert provider.repair_calls == []


def test_unsafe_repair_result_fails_closed(monkeypatch) -> None:
    provider = StubTextProvider(
        calls=[],
        answer="Безопасный черновик. " + ("Объяснение отдыха. " * 120),
        repair_answer="Рекомендую принимать 5 г креатина ежедневно.",
        repair_calls=[],
    )

    result = _generate_direct_chat(
        monkeypatch,
        provider,
        _direct_chat_request("Сколько отдыхать между подходами?"),
    )

    assert result.outcome == "safety_refusal"
    assert result.failure_category == "safety_rejection"
    assert result.safety_category.value == "drugs_performance"
    assert result.answer is not None
    assert "креатина" not in result.answer
    assert result.repair_attempted is True
    assert result.repair_success is False
    assert result.validation_failure_reason.value == "prohibited_claim"
    assert len(provider.repair_calls) == 1


def test_failed_repair_returns_technical_failure_without_raw_content(monkeypatch) -> None:
    provider = StubTextProvider(
        calls=[],
        answer="Безопасный черновик. " + ("Объяснение отдыха. " * 120),
        repair_error=NormalizedProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE),
        repair_calls=[],
    )

    result = _generate_direct_chat(
        monkeypatch,
        provider,
        _direct_chat_request("Сколько отдыхать между подходами?"),
    )

    assert result.outcome == "invalid_output"
    assert result.failure_category == "repair_failed"
    assert result.answer is None
    assert result.repair_attempted is True
    assert result.repair_success is False
    assert len(provider.repair_calls) == 1


def test_chat_telemetry_contains_repair_metadata_without_content(monkeypatch, caplog) -> None:
    provider = StubTextProvider(
        calls=[],
        answer="Безопасный черновик. " + ("Объяснение отдыха. " * 120),
        repair_answer="Короткий ответ о восстановлении между подходами.",
        repair_calls=[],
    )

    with caplog.at_level(logging.INFO, logger="app.ai_coach"):
        result = _generate_direct_chat(
            monkeypatch,
            provider,
            _direct_chat_request("Сколько отдыхать между подходами?"),
        )

    assert result.outcome == "answer"
    records = [item for item in caplog.records if item.getMessage() == "ai_coach_chat_generation"]
    assert records
    record = records[-1]
    assert record.repair_attempted is True
    assert record.repair_success is True
    assert record.validation_failure_reason == "too_long"
    assert "answer" not in record.__dict__
    assert "prompt" not in record.__dict__


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
    assert (
        client.delete(
            f"/api/v1/ai-coach/conversations/{conversation_id}",
            headers=owner_headers,
        ).status_code
        == 404
    )


def test_conversation_history_clear_is_scoped_and_preserves_other_ai_coach_state(
    client, monkeypatch
) -> None:
    _enable_chat(monkeypatch)
    provider = StubTextProvider(calls=[])
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    owner_headers = _login(client, 987_140)
    other_headers = _login(client, 987_141)

    owner_conversation_ids = [_create_conversation(client, owner_headers) for _ in range(2)]
    other_conversation_id = _create_conversation(client, other_headers)
    for conversation_id, message in zip(
        owner_conversation_ids,
        ("Первый тестовый разговор", "Второй тестовый разговор"),
        strict=True,
    ):
        response = client.post(
            f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
            headers=owner_headers,
            json={"message": message},
        )
        assert response.status_code == 200, response.text

    assert (
        client.put(
            "/api/v1/ai-coach/consent",
            headers=owner_headers,
            json={"enabled": True},
        ).status_code
        == 200
    )
    assert (
        client.put(
            "/api/v1/ai-coach/memory/consent",
            headers=owner_headers,
            json={"status": "enabled"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/ai-coach/memory",
            headers=owner_headers,
            json={
                "category": "ai_interaction_preferences",
                "value": "Короткие ответы",
                "confirmation": True,
            },
        ).status_code
        == 200
    )
    quota_before = client.get("/api/v1/ai-coach/quota", headers=owner_headers).json()
    consent_before = client.get("/api/v1/ai-coach/consent", headers=owner_headers).json()
    memory_before = client.get("/api/v1/ai-coach/memory", headers=owner_headers).json()

    cleared = client.delete("/api/v1/ai-coach/conversations", headers=owner_headers)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json() == {"deleted_count": 2}
    assert client.get("/api/v1/ai-coach/conversations", headers=owner_headers).json() == {
        "items": []
    }
    assert [
        item["id"]
        for item in client.get("/api/v1/ai-coach/conversations", headers=other_headers).json()[
            "items"
        ]
    ] == [other_conversation_id]
    assert (
        client.get(
            f"/api/v1/ai-coach/conversations/{owner_conversation_ids[0]}",
            headers=owner_headers,
        ).status_code
        == 404
    )
    assert client.get("/api/v1/ai-coach/quota", headers=owner_headers).json() == quota_before
    assert client.get("/api/v1/ai-coach/consent", headers=owner_headers).json() == consent_before
    assert client.get("/api/v1/ai-coach/memory", headers=owner_headers).json() == memory_before
    with get_session_context() as db:
        audit = (
            db.query(AuditEvent)
            .filter(AuditEvent.action == "ai_coach.conversation_history_cleared")
            .order_by(AuditEvent.id.desc())
            .first()
        )
        assert audit is not None
        assert audit.resource_type == "ai_coach_conversation_history"
        assert audit.details == {
            "conversation_count_before_clear": 2,
            "conversation_count_after_clear": 0,
        }
        assert db.query(AiCoachConversationMessageRequest).count() == 0

    empty_clear = client.delete("/api/v1/ai-coach/conversations", headers=owner_headers)
    assert empty_clear.status_code == 200, empty_clear.text
    assert empty_clear.json() == {"deleted_count": 0}


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
