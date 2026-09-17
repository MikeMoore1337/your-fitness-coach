from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from pydantic import SecretStr

from fitminiapp_api.ai_coach.chat_service import ai_coach_chat_service
from fitminiapp_api.ai_coach.contracts import (
    AiCoachDataClass,
    NormalizedProviderError,
    ProviderTextResponse,
    ProviderTextResult,
)
from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import now_msk_naive, today_msk
from fitminiapp_api.db.performance import begin_sql_metrics, current_sql_metrics, reset_sql_metrics
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.check_in import WeeklyCheckIn
from fitminiapp_api.models.feedback import WorkoutComment
from fitminiapp_api.models.program import UserProgram, UserWorkout
from fitminiapp_api.models.user import CoachClient, User, UserProfile
from fitminiapp_api.services.coach_attention import build_coach_attention


@dataclass
class _ContextProvider:
    calls: list[object]
    error: NormalizedProviderError | None = None

    def generate_text(self, request, context_refs):
        self.calls.append((request, tuple(ref.ref_id for ref in context_refs)))
        if self.error is not None:
            raise self.error
        return ProviderTextResult(
            provider="groq",
            configured_model="openai/gpt-oss-120b",
            actual_model="openai/gpt-oss-120b",
            response=ProviderTextResponse(answer="Контекстный ответ без личных данных в URL."),
            latency_ms=2,
        )

    def repair_text(self, request, answer, reason):
        del request, answer, reason
        return ProviderTextResult(
            provider="groq",
            configured_model="openai/gpt-oss-120b",
            actual_model="openai/gpt-oss-120b",
            response=ProviderTextResponse(answer="Исправленный ответ."),
            latency_ms=2,
        )


def _enable_context_chat(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_coach_enabled", True)
    monkeypatch.setattr(settings, "ai_coach_kill_switch", False)
    monkeypatch.setattr(settings, "ai_coach_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", SecretStr("test-chat-key"))
    monkeypatch.setattr(settings, "ai_coach_cost_policy", "free_only")
    monkeypatch.setattr(settings, "ai_coach_cost_class", "free")
    monkeypatch.setattr(settings, "ai_coach_data_policy", "verified_generic_only")
    monkeypatch.setattr(settings, "ai_coach_personal_enabled", True)
    monkeypatch.setattr(settings, "ai_coach_personal_data_policy", "verified_personal_user")
    ai_coach_chat_service.reset_runtime_state()


def _conversation(client, headers: dict[str, str]) -> int:
    response = client.post("/api/v1/ai-coach/conversations", headers=headers)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _login(client, telegram_user_id: int, *, is_coach: bool) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={
            "telegram_user_id": telegram_user_id,
            "username": f"attention_{telegram_user_id}",
            "is_coach": is_coach,
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _user(db, telegram_user_id: int) -> User:
    return db.query(User).filter(User.telegram_user_id == telegram_user_id).one()


def _program(db, client: User) -> UserProgram:
    program = UserProgram(
        user_id=client.id,
        start_date=today_msk() - timedelta(days=14),
        duration_weeks=8,
        status="active",
        is_active=True,
    )
    db.add(program)
    db.flush()
    return program


def _workout(
    db,
    program: UserProgram,
    *,
    scheduled_date,
    status: str,
    title: str = "Тренировка клиента",
    feedback: str | None = None,
    note: str | None = None,
    event_at=None,
) -> UserWorkout:
    workout = UserWorkout(
        user_program_id=program.id,
        scheduled_date=scheduled_date,
        day_number=1,
        week_number=1,
        title=title,
        status=status,
        completed_at=event_at if status == "completed" else None,
        completion_feedback=feedback,
        completion_note=note,
        completion_feedback_updated_at=event_at,
    )
    db.add(workout)
    db.flush()
    return workout


def test_attention_returns_all_concrete_kinds_without_private_url_data(client) -> None:
    coach_headers = _login(client, 984_001, is_coach=True)
    for telegram_user_id in range(984_010, 984_015):
        _login(client, telegram_user_id, is_coach=False)

    now = now_msk_naive()
    today = today_msk()
    with get_session_context() as db:
        coach = _user(db, 984_001)
        feedback_client, checkin_client, skipped_client, missed_client, empty_client = (
            _user(db, telegram_user_id) for telegram_user_id in range(984_010, 984_015)
        )
        for target in (
            feedback_client,
            checkin_client,
            skipped_client,
            missed_client,
            empty_client,
        ):
            db.add(
                CoachClient(
                    coach_user_id=coach.id,
                    client_user_id=target.id,
                    private_name=f"Локальное имя {target.id}",
                )
            )
        db.flush()

        feedback_program = _program(db, feedback_client)
        _workout(
            db,
            feedback_program,
            scheduled_date=today - timedelta(days=1),
            status="completed",
            feedback="harder_than_expected",
            note="Секретная заметка клиента",
            event_at=now - timedelta(hours=1),
        )
        _program(db, checkin_client)
        db.add(
            WeeklyCheckIn(
                user_id=checkin_client.id,
                week_start=today - timedelta(days=7),
                week_end=today - timedelta(days=1),
                submitted_on=today - timedelta(days=1),
                timezone="Europe/Moscow",
                status="completed",
                summary_version="test-v1",
                summary={"note": "Секретный итог клиента"},
                note="Секретная заметка check-in",
                created_at=now - timedelta(hours=2),
            )
        )
        skipped_program = _program(db, skipped_client)
        _workout(
            db,
            skipped_program,
            scheduled_date=today - timedelta(days=2),
            status="skipped",
        )
        missed_program = _program(db, missed_client)
        _workout(
            db,
            missed_program,
            scheduled_date=today - timedelta(days=3),
            status="planned",
        )
        db.commit()

        response = client.get("/api/v1/coach/attention", headers=coach_headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert {item["kind"] for item in payload["items"]} == {
        "workout_feedback",
        "weekly_check_in",
        "skipped_workout",
        "missed_workout",
        "without_program",
    }
    assert len({item["key"] for item in payload["items"]}) == len(payload["items"])
    assert payload["total"] == len(payload["items"])
    for item in payload["items"]:
        assert "Секретная" not in item["destination"]
        assert "Локальное" not in item["destination"]
        assert item["destination"].startswith("/coach?client_id=")


def test_attention_deduplicates_and_resolves_authoritative_state(client) -> None:
    coach_headers = _login(client, 984_101, is_coach=True)
    _login(client, 984_110, is_coach=False)
    with get_session_context() as db:
        coach = _user(db, 984_101)
        managed = _user(db, 984_110)
        relation = CoachClient(coach_user_id=coach.id, client_user_id=managed.id)
        db.add(relation)
        db.flush()
        program = _program(db, managed)
        older = _workout(
            db,
            program,
            scheduled_date=today_msk() - timedelta(days=2),
            status="completed",
            feedback="as_expected",
            event_at=now_msk_naive() - timedelta(days=2),
        )
        latest = _workout(
            db,
            program,
            scheduled_date=today_msk() - timedelta(days=1),
            status="completed",
            feedback="easier_than_expected",
            event_at=now_msk_naive() - timedelta(hours=1),
        )
        db.add(
            WeeklyCheckIn(
                user_id=managed.id,
                week_start=today_msk() - timedelta(days=7),
                week_end=today_msk() - timedelta(days=1),
                submitted_on=today_msk() - timedelta(days=1),
                timezone="Europe/Moscow",
                status="completed",
                summary_version="test-v1",
                summary={},
                created_at=now_msk_naive() - timedelta(hours=1),
            )
        )
        db.commit()

        first = build_coach_attention(db, coach)
        assert [
            item["source_id"] for item in first["items"] if item["kind"] == "workout_feedback"
        ] == [latest.id]

        db.add(
            WorkoutComment(
                coach_client_id=relation.id,
                trainer_author_id=coach.id,
                client_user_id=managed.id,
                workout_id=latest.id,
                body="Разобрано тренером",
                created_at=now_msk_naive(),
            )
        )
        db.add(
            WorkoutComment(
                coach_client_id=relation.id,
                trainer_author_id=coach.id,
                client_user_id=managed.id,
                workout_id=older.id,
                body="Предыдущая запись разобрана",
                created_at=now_msk_naive(),
            )
        )
        db.commit()
        resolved = build_coach_attention(db, coach)

        assert not any(item["kind"] == "workout_feedback" for item in resolved["items"])
        assert not any(
            item["kind"] == "workout_feedback" and item["source_id"] == older.id
            for item in resolved["items"]
        )

        latest.status = "skipped"
        latest.completion_feedback = None
        latest.completion_feedback_updated_at = None
        db.commit()
        state_changed = build_coach_attention(db, coach)
        assert any(item["kind"] == "skipped_workout" for item in state_changed["items"])
        assert not any(item["kind"] == "workout_feedback" for item in state_changed["items"])

        program.is_active = False
        program.status = "archived"
        db.commit()
        no_program = build_coach_attention(db, coach)
        assert any(item["kind"] == "without_program" for item in no_program["items"])
        assert not any(item["kind"] == "skipped_workout" for item in no_program["items"])

    assert client.get("/api/v1/coach/attention", headers=coach_headers).status_code == 200


def test_attention_isolated_to_coach_and_requires_coach_role(client) -> None:
    coach_headers = _login(client, 984_201, is_coach=True)
    other_coach_headers = _login(client, 984_202, is_coach=True)
    client_headers = _login(client, 984_210, is_coach=False)
    _login(client, 984_211, is_coach=False)
    with get_session_context() as db:
        first = _user(db, 984_201)
        second = _user(db, 984_202)
        first_client = _user(db, 984_210)
        second_client = _user(db, 984_211)
        first_client_id = first_client.id
        second_client_id = second_client.id
        db.add_all(
            [
                CoachClient(coach_user_id=first.id, client_user_id=first_client.id),
                CoachClient(coach_user_id=second.id, client_user_id=second_client.id),
            ]
        )
        db.commit()

    own = client.get("/api/v1/coach/attention", headers=coach_headers)
    other = client.get("/api/v1/coach/attention", headers=other_coach_headers)
    forbidden = client.get("/api/v1/coach/attention", headers=client_headers)
    assert own.status_code == 200
    assert other.status_code == 200
    assert forbidden.status_code == 403
    assert {item["client"]["id"] for item in own.json()["items"]} == {first_client_id}
    assert {item["client"]["id"] for item in other.json()["items"]} == {second_client_id}


def test_attention_query_count_is_constant_for_many_clients(client) -> None:
    _login(client, 984_301, is_coach=True)
    with get_session_context() as db:
        coach = _user(db, 984_301)
        clients: list[User] = []
        for telegram_user_id in range(984_310, 984_340):
            managed = User(
                telegram_user_id=telegram_user_id,
                username=f"attention_{telegram_user_id}",
            )
            db.add(managed)
            db.flush()
            db.add(UserProfile(user_id=managed.id, full_name=f"Client {telegram_user_id}"))
            clients.append(managed)
        db.add_all(
            [CoachClient(coach_user_id=coach.id, client_user_id=managed.id) for managed in clients]
        )
        db.commit()
        db.refresh(coach)
        token = begin_sql_metrics()
        try:
            result = build_coach_attention(db, coach)
            metrics = current_sql_metrics()
        finally:
            reset_sql_metrics(token)

    assert result["total"] == 30
    assert metrics.query_count <= 7


def test_contextual_chat_resolves_each_allowed_surface_without_auto_send(
    client, monkeypatch
) -> None:
    _enable_context_chat(monkeypatch)
    provider = _ContextProvider(calls=[])
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 984_401, is_coach=False)
    assert (
        client.put(
            "/api/v1/ai-coach/consent",
            headers=headers,
            json={"enabled": True},
        ).status_code
        == 200
    )
    with get_session_context() as db:
        user = _user(db, 984_401)
        program = _program(db, user)
        workout = _workout(
            db,
            program,
            scheduled_date=today_msk(),
            status="planned",
        )
        workout_id = workout.id
        db.commit()

    contexts = (
        {"surface": "today"},
        {"surface": "workout", "resource_id": workout_id},
        {"surface": "nutrition", "period_days": 7},
        {"surface": "program"},
        {"surface": "progress", "period_days": 30},
    )
    for context in contexts:
        conversation_id = _conversation(client, headers)
        response = client.post(
            f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
            headers=headers,
            json={"message": "Сформулируй короткий ответ", "context": context},
        )
        assert response.status_code == 200, response.text
        assert response.json()["outcome"] == "answer"
        assert response.json()["context"]["surface"] == context["surface"]

    assert len(provider.calls) == len(contexts)
    assert all(request.data_class == AiCoachDataClass.PERSONALIZED for request, _ in provider.calls)
    assert [request.context_id for request, _ in provider.calls] == [
        "personal:context:today",
        "personal:context:workout",
        "personal:context:nutrition",
        "personal:context:program",
        "personal:context:progress",
    ]


def test_contextual_workout_rejects_foreign_resource_without_account_leak(
    client, monkeypatch
) -> None:
    _enable_context_chat(monkeypatch)
    provider = _ContextProvider(calls=[])
    monkeypatch.setattr(ai_coach_chat_service, "provider", provider)
    headers = _login(client, 984_501, is_coach=False)
    _login(client, 984_502, is_coach=False)
    assert (
        client.put(
            "/api/v1/ai-coach/consent",
            headers=headers,
            json={"enabled": True},
        ).status_code
        == 200
    )
    with get_session_context() as db:
        foreign = _user(db, 984_502)
        foreign_program = _program(db, foreign)
        foreign_workout = _workout(
            db,
            foreign_program,
            scheduled_date=today_msk(),
            status="completed",
            title="Чужая приватная тренировка",
            note="Чужая приватная заметка",
            event_at=now_msk_naive(),
        )
        foreign_workout_id = foreign_workout.id
        db.commit()

    conversation_id = _conversation(client, headers)
    response = client.post(
        f"/api/v1/ai-coach/conversations/{conversation_id}/messages",
        headers=headers,
        json={
            "message": "Что здесь важно?",
            "context": {"surface": "workout", "resource_id": foreign_workout_id},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "unavailable"
    assert response.json()["context"] == {
        "surface": "workout",
        "label": "Эта тренировка",
    }
    assert provider.calls == []
    assert "Чужая приватная" not in response.text
