import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.coach_attention import CoachAttentionResponse
from fitminiapp_api.schemas.coach_capacity import CoachCapacityResponse
from fitminiapp_api.schemas.coach_crm import (
    CoachAgendaResponse,
    CoachClientOperationsResponse,
    CoachOperationsTodayResponse,
    CoachPackageResponse,
    CoachPaymentResponse,
    CoachSessionResponse,
    CoachTaskResponse,
)
from fitminiapp_api.schemas.coach_inbox import CoachInboxResponse
from fitminiapp_api.schemas.feedback import WorkoutCommentResponse
from fitminiapp_api.schemas.food_diary import FoodDiaryDayResponse, FoodDiaryEntryResponse
from fitminiapp_api.schemas.hydration import HydrationDayResponse, HydrationEntryResponse
from fitminiapp_api.schemas.nutrition import NutritionResolvedTargetResponse
from fitminiapp_api.schemas.program import (
    ClientResponse,
    CoachAssignedProgramResponse,
    ProgramTemplateResponse,
)
from fitminiapp_api.schemas.progress import NutritionReportResponse, ProgressSummaryResponse
from fitminiapp_api.schemas.user import UserResponse
from fitminiapp_api.schemas.workout import (
    ExerciseHistoryResponse,
    SessionRotationStateResponse,
    TrainingAnalyticsResponse,
    WorkoutScheduleItem,
    WorkoutSetHistoryResponse,
    WorkoutStatusResponse,
    WorkoutTimelineItem,
    WorkoutTodayResponse,
)
from fitminiapp_api.schemas.workout_rest import RestSessionResponse
from fitminiapp_api.services.demo_sessions import (
    DemoSessionExpiredError,
    DemoSessionStore,
    DemoTransitionError,
)


def _create_session(client, scenario: str) -> tuple[str, dict]:
    response = client.post("/api/v1/demo/sessions", json={"scenario": scenario})
    assert response.status_code == 201
    assert "no-store" in response.headers["cache-control"]
    payload = response.json()
    return payload.pop("session_token"), payload


def _transport(client, token: str, path: str, method: str = "GET", body=None):
    return client.post(
        "/api/v1/demo/sessions/current/transport",
        headers={"X-Demo-Session": token},
        json={"path": path, "method": method, "body": body},
    )


def test_demo_scenarios_are_deterministic_and_do_not_write_user_tables(client) -> None:
    with get_session_context() as db:
        users_before = db.query(User).count()

    conversion_title = "Готово. Вы посмотрели основной сценарий"
    for scenario in ("self_training", "nutrition", "trainer"):
        first_token, first = _create_session(client, scenario)
        second_token, second = _create_session(client, scenario)

        assert first_token != second_token
        assert first["capability"] == "demo"
        assert first["fixture_version"] == "demo-curated-v2"
        assert first["scenario"] == scenario
        assert first["state"] == second["state"]
        assert first["cabinet"] == second["cabinet"]
        assert first["cabinet"]["meaningful_action_completed"] is False
        assert first["cabinet"]["conversion_title"] == conversion_title
        assert len(first["cabinet"]["progress"]["training_history"]) == 4
        assert len(first["cabinet"]["progress"]["nutrition_history"]) == 7
        if scenario == "trainer":
            assert {client["id"] for client in first["state"]["clients"]} == {
                "alexey",
                "maria",
                "ivan",
            }

    with get_session_context() as db:
        assert db.query(User).count() == users_before


def test_training_demo_supports_full_flow_idempotency_and_reset(client) -> None:
    token, initial = _create_session(client, "self_training")
    headers = {"X-Demo-Session": token}

    started = client.post(
        "/api/v1/demo/sessions/current/actions",
        headers=headers,
        json={"action": "start_workout"},
    )
    assert started.status_code == 200
    assert started.json()["state"]["screen"] == "active_workout"

    repeated = client.post(
        "/api/v1/demo/sessions/current/actions",
        headers=headers,
        json={"action": "start_workout"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["revision"] == started.json()["revision"]

    completed_set = client.post(
        "/api/v1/demo/sessions/current/actions",
        headers=headers,
        json={"action": "complete_set"},
    )
    assert completed_set.json()["state"]["completed_sets"] == 3
    summary = client.post(
        "/api/v1/demo/sessions/current/actions",
        headers=headers,
        json={"action": "finish_workout"},
    )
    assert summary.json()["state"]["screen"] == "summary"
    progress = client.post(
        "/api/v1/demo/sessions/current/actions",
        headers=headers,
        json={"action": "open_progress"},
    )
    assert progress.json()["state"]["screen"] == "progress"
    assert progress.json()["state"]["progress_change_percent"] == 6.5
    assert progress.json()["cabinet"]["meaningful_action_completed"] is True
    assert progress.json()["cabinet"]["progress"]["latest_volume_kg"] == 6840
    assert progress.json()["cabinet"]["progress"]["workouts_completed"] == 12

    reset = client.post("/api/v1/demo/sessions/current/reset", headers=headers)
    assert reset.status_code == 200
    assert reset.json()["state"] == initial["state"]
    assert reset.json()["revision"] > progress.json()["revision"]


def test_nutrition_and_trainer_sessions_are_isolated(client) -> None:
    nutrition_token, _ = _create_session(client, "nutrition")
    trainer_token, _ = _create_session(client, "trainer")

    nutrition = client.post(
        "/api/v1/demo/sessions/current/actions",
        headers={"X-Demo-Session": nutrition_token},
        json={"action": "add_recent"},
    )
    assert nutrition.status_code == 200
    assert nutrition.json()["state"]["calories"] == 1588
    assert nutrition.json()["state"]["protein_g"] == 106.0
    assert nutrition.json()["cabinet"]["nutrition"]["calories"] == 1588
    assert nutrition.json()["cabinet"]["progress"]["nutrition_completion_percent"] == 74
    assert nutrition.json()["cabinet"]["meaningful_action_completed"] is True

    selected_trainer = client.post(
        "/api/v1/demo/sessions/current/actions",
        headers={"X-Demo-Session": trainer_token},
        json={"action": "select_client", "client_id": "maria"},
    )
    assert selected_trainer.status_code == 200
    assert selected_trainer.json()["state"]["selected_client_id"] == "maria"
    assert selected_trainer.json()["cabinet"]["trainer"]["selected_client_id"] == "maria"

    trainer = client.post(
        "/api/v1/demo/sessions/current/actions",
        headers={"X-Demo-Session": trainer_token},
        json={"action": "save_comment", "comment": "  Техника стабильна, сохраняем темп.  "},
    )
    assert trainer.status_code == 200
    assert trainer.json()["state"]["clients"][0]["comment"] is None
    assert trainer.json()["state"]["clients"][1]["comment"] == "Техника стабильна, сохраняем темп."
    assert (
        trainer.json()["cabinet"]["trainer"]["clients"][1]["comment"]
        == "Техника стабильна, сохраняем темп."
    )
    assert trainer.json()["cabinet"]["meaningful_action_completed"] is True

    nutrition_after = client.get(
        "/api/v1/demo/sessions/current",
        headers={"X-Demo-Session": nutrition_token},
    ).json()
    assert nutrition_after["state"]["kind"] == "nutrition"
    assert "comment" not in nutrition_after["state"]


@pytest.mark.parametrize(
    "action",
    [
        "send_notification",
        "invite_client",
        "export_account",
        "delete_account",
        "link_telegram",
        "provider_call",
    ],
)
def test_direct_demo_attempts_cannot_trigger_external_or_account_actions(client, action) -> None:
    token, _ = _create_session(client, "trainer")
    response = client.post(
        "/api/v1/demo/sessions/current/actions",
        headers={"X-Demo-Session": token},
        json={"action": action},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Это действие недоступно в демо-режиме."


def test_demo_token_is_not_an_authenticated_account_credential(client) -> None:
    token, _ = _create_session(client, "self_training")

    header_only = client.get("/api/v1/me", headers={"X-Demo-Session": token})
    bearer_attempt = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert header_only.status_code == 401
    assert bearer_attempt.status_code == 401


def test_demo_session_creation_is_rate_limited(client, monkeypatch) -> None:
    from fitminiapp_api.api.v1 import demo

    monkeypatch.setattr(demo, "demo_session_store", DemoSessionStore())
    for _ in range(20):
        assert client.post("/api/v1/demo/sessions", json={"scenario": "trainer"}).status_code == 201
    assert client.post("/api/v1/demo/sessions", json={"scenario": "trainer"}).status_code == 429


def test_demo_errors_are_not_cached_and_logs_do_not_contain_credentials(client, caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.http")
    token, _ = _create_session(client, "trainer")
    invalid = "A" * 43
    response = client.get("/api/v1/demo/sessions/current", headers={"X-Demo-Session": invalid})
    assert response.status_code == 410
    assert "no-store" in response.headers["cache-control"]
    assert (
        client.get("/api/v1/demo/sessions/current", headers={"X-Demo-Session": token}).status_code
        == 200
    )
    records = [record for record in caplog.records if record.name == "app.http"]
    assert records
    assert all(
        token not in repr(record.__dict__) and invalid not in repr(record.__dict__)
        for record in records
    )


def test_demo_transport_rejects_oversized_request_body_without_mutation(client) -> None:
    token, before = _create_session(client, "trainer")
    payload = {
        "path": "/api/v1/coach/sessions",
        "method": "POST",
        "body": {"private_note": "x" * (1024 * 1024)},
    }
    response = client.post(
        "/api/v1/demo/sessions/current/transport",
        headers={"X-Demo-Session": token, "Content-Type": "application/json"},
        content=json.dumps(payload),
    )
    assert response.status_code == 413
    assert (
        client.get("/api/v1/demo/sessions/current", headers={"X-Demo-Session": token}).json()
        == before
    )


def test_missing_and_unknown_demo_sessions_have_safe_errors(client) -> None:
    missing = client.get("/api/v1/demo/sessions/current")
    unknown = client.get(
        "/api/v1/demo/sessions/current",
        headers={"X-Demo-Session": "A" * 43},
    )

    assert missing.status_code == 401
    assert unknown.status_code == 410
    assert unknown.json()["detail"] == "Демо-сессия истекла. Начните новый сценарий."


def test_expired_session_is_removed_and_reset_cannot_revive_it() -> None:
    now = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    current = [now]
    store = DemoSessionStore(now=lambda: current[0], ttl=timedelta(seconds=5))
    token, _ = store.create("nutrition")

    current[0] = now + timedelta(seconds=6)

    with pytest.raises(DemoSessionExpiredError):
        store.get(token)
    with pytest.raises(DemoSessionExpiredError):
        store.reset(token)


def test_concurrent_demo_sessions_keep_independent_state() -> None:
    store = DemoSessionStore(max_sessions=32)

    def run_session(index: int) -> tuple[str, str | None]:
        scenario = "trainer" if index % 2 else "nutrition"
        token, _ = store.create(scenario)
        if scenario == "trainer":
            state = store.apply_action(token, "save_comment", f"Комментарий {index}")
            return token, state["state"]["clients"][0]["comment"]
        state = store.apply_action(token, "add_recent")
        return token, str(state["state"]["calories"])

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(run_session, range(20)))

    assert len({token for token, _ in results}) == 20
    assert {value for _, value in results if value and value.startswith("Комментарий")} == {
        f"Комментарий {index}" for index in range(1, 20, 2)
    }
    assert {value for _, value in results if value == "1588"} == {"1588"}


def test_demo_frontend_route_is_noindex(client) -> None:
    response = client.get("/demo")

    assert response.status_code == 200
    assert response.headers["x-robots-tag"] == "noindex, nofollow"


def test_demo_transport_returns_production_dtos_and_keeps_set_updates_independent(client) -> None:
    token, _ = _create_session(client, "self_training")

    UserResponse.model_validate(_transport(client, token, "/api/v1/me").json())
    workout_response = _transport(client, token, "/api/v1/workouts/today")
    workout = WorkoutTodayResponse.model_validate(workout_response.json())
    assert [item.is_completed for item in workout.exercises[0].sets] == [True, True, False]
    for item in _transport(client, token, "/api/v1/workouts/week").json():
        WorkoutScheduleItem.model_validate(item)
    progress_summary = _transport(client, token, "/api/v1/workouts/progress/summary").json()
    ProgressSummaryResponse.model_validate(progress_summary)
    assert any(
        trend["label"] == "Пользовательский показатель"
        for trend in progress_summary["body"]["trends"]
    )
    assert all(trend["label"] != "Обхват живота" for trend in progress_summary["body"]["trends"])
    TrainingAnalyticsResponse.model_validate(
        _transport(client, token, "/api/v1/workouts/progress/training-analytics").json()
    )
    NutritionReportResponse.model_validate(
        _transport(client, token, "/api/v1/workouts/progress/nutrition-report").json()
    )
    FoodDiaryDayResponse.model_validate(_transport(client, token, "/api/v1/nutrition/diary").json())
    HydrationDayResponse.model_validate(
        _transport(client, token, "/api/v1/nutrition/hydration").json()
    )
    ProgramTemplateResponse.model_validate(
        _transport(client, token, "/api/v1/programs/templates/mine").json()[0]
    )

    started = _transport(client, token, "/api/v1/workouts/50001/start", "POST")
    assert started.status_code == 200
    pending_set = workout.exercises[0].sets[-1]
    saved = _transport(
        client,
        token,
        f"/api/v1/workouts/sets/{pending_set.id}",
        "PATCH",
        {
            "actual_reps": 9,
            "actual_weight": 17.5,
            "rir": "3",
            "set_kind": "working",
            "reached_failure": False,
            "is_completed": True,
            "expected_version": pending_set.version,
            "mutation_id": "demo-set-mutation-0001",
        },
    )
    assert saved.status_code == 200
    saved_set = WorkoutStatusResponse.model_validate(saved.json())
    assert saved_set.is_completed is True
    assert saved_set.actual_reps == 9
    assert saved_set.actual_weight == 17.5
    assert saved_set.version == pending_set.version + 1
    repeated = _transport(
        client,
        token,
        f"/api/v1/workouts/sets/{pending_set.id}",
        "PATCH",
        {
            "actual_reps": 9,
            "actual_weight": 17.5,
            "rir": "3",
            "set_kind": "working",
            "reached_failure": False,
            "is_completed": True,
            "expected_version": pending_set.version,
            "mutation_id": "demo-set-mutation-0001",
        },
    )
    assert repeated.status_code == 200
    assert repeated.json() == saved.json()
    refreshed = WorkoutTodayResponse.model_validate(
        _transport(client, token, "/api/v1/workouts/today").json()
    )
    assert [item.is_completed for item in refreshed.exercises[0].sets] == [True, True, True]


@pytest.mark.parametrize("scenario", ["self_training", "nutrition", "trainer"])
def test_demo_transport_serves_calendar_and_date_target_without_account_access(
    client, scenario
) -> None:
    token, _ = _create_session(client, scenario)

    rotation = _transport(client, token, "/api/v1/workouts/session-rotation")
    assert rotation.status_code == 200
    state = SessionRotationStateResponse.model_validate(rotation.json())
    assert (state.mode, state.status) == ("calendar", "disabled")

    target = _transport(client, token, "/api/v1/nutrition/targets/for-date?target_date=2026-11-24")
    assert target.status_code == 200
    resolved = NutritionResolvedTargetResponse.model_validate(target.json())
    assert resolved.date.isoformat() == "2026-11-24"
    assert resolved.origin == "base"
    assert resolved.target is not None and resolved.target.calories == 2150

    for path in (
        "/api/v1/nutrition/targets/for-date",
        "/api/v1/nutrition/targets/for-date?target_date=invalid",
        "/api/v1/nutrition/targets/for-date?target_date=2026-11-24&target_telegram_user_id=123",
        "/api/v1/workouts/session-rotation/unknown",
    ):
        assert _transport(client, token, path).status_code == 403


def test_demo_rest_and_set_history_are_session_scoped_and_idempotent(client) -> None:
    token, _ = _create_session(client, "self_training")
    other, _ = _create_session(client, "self_training")
    assert _transport(client, token, "/api/v1/workouts/50001/start", "POST").status_code == 200
    history = _transport(client, token, "/api/v1/workouts/50001/set-history")
    assert history.status_code == 200
    parsed_history = WorkoutSetHistoryResponse.model_validate(history.json())
    assert len(parsed_history.sets) == 3
    assert all(item.history_status == "identity_unproven" for item in parsed_history.sets)

    now = datetime.now(UTC).isoformat()
    start = {"source_set_id": 60002, "started_at": now, "mutation_id": "demo-rest-start-0001"}
    path = "/api/v1/workouts/50001/rest-sessions"
    created = _transport(client, token, path, "POST", start)
    assert created.status_code == 200
    rest = RestSessionResponse.model_validate(created.json())
    assert rest.status == "running" and rest.planned_seconds == 90 and rest.version == 1
    assert _transport(client, token, path, "POST", start).json() == created.json()
    assert (
        _transport(
            client, token, path, "POST", {**start, "mutation_id": "another-start-0001"}
        ).json()
        == created.json()
    )
    assert (
        _transport(client, token, path, "POST", {**start, "source_set_id": 60003}).status_code
        == 409
    )
    assert (
        _transport(
            client,
            token,
            path,
            "POST",
            {**start, "mutation_id": "demo-rest-other-0001", "source_set_id": 99999},
        ).status_code
        == 403
    )
    assert _transport(client, other, path).json() == []
    assert (
        _transport(
            client, other, f"/api/v1/workouts/rest-sessions/{rest.id}/actions", "POST", {}
        ).status_code
        == 403
    )

    action_path = f"/api/v1/workouts/rest-sessions/{rest.id}/actions"
    extend = {
        "action": "add30",
        "mutation_id": "demo-rest-action-0001",
        "expected_version": 1,
        "occurred_at": now,
    }
    updated = _transport(client, token, action_path, "POST", extend)
    assert updated.status_code == 200 and updated.json()["adjusted_seconds"] == 120
    assert _transport(client, token, action_path, "POST", extend).json() == updated.json()
    assert (
        _transport(client, token, action_path, "POST", {**extend, "action": "add60"}).status_code
        == 409
    )
    assert (
        _transport(
            client, token, action_path, "POST", {**extend, "mutation_id": "other-action-001"}
        ).status_code
        == 409
    )

    stop = {
        "action": "complete",
        "mutation_id": "demo-rest-action-0002",
        "expected_version": 2,
        "ended_at": now,
    }
    finished = _transport(client, token, action_path, "POST", stop)
    assert finished.status_code == 200 and finished.json()["status"] == "completed"
    assert _transport(client, token, action_path, "POST", stop).json() == finished.json()
    restart_path = f"/api/v1/workouts/rest-sessions/{rest.id}/restart"
    restart = {"started_at": now, "mutation_id": "demo-rest-restart-001"}
    restarted = _transport(client, token, restart_path, "POST", restart)
    assert restarted.status_code == 200 and restarted.json()["id"] != rest.id
    assert _transport(client, token, restart_path, "POST", restart).json() == restarted.json()
    assert (
        _transport(
            client, token, restart_path, "POST", {**restart, "mutation_id": "another-restart-001"}
        ).status_code
        == 409
    )
    restarted_path = f"/api/v1/workouts/rest-sessions/{restarted.json()['id']}/actions"
    skipped = _transport(
        client,
        token,
        restarted_path,
        "POST",
        {
            "action": "skip",
            "mutation_id": "demo-rest-action-0003",
            "expected_version": 1,
            "occurred_at": now,
        },
    )
    assert skipped.status_code == 200
    assert skipped.json()["status"] == "skipped" and skipped.json()["measured_seconds"] is None
    assert _transport(client, token, "/api/v1/workouts/50002/set-history").status_code == 403

    offline, _ = _create_session(client, "self_training")
    assert _transport(client, offline, "/api/v1/workouts/50001/start", "POST").status_code == 200
    assert (
        _transport(
            client, offline, "/api/v1/workouts/50001/finish", "POST", {"confirm_incomplete": True}
        ).status_code
        == 200
    )
    assert _transport(client, offline, path, "POST", start).status_code == 200


@pytest.mark.parametrize("scenario", ["self_training", "nutrition", "trainer"])
def test_demo_quick_food_preserves_entered_values_and_session_isolation(client, scenario) -> None:
    token, _ = _create_session(client, scenario)
    other, _ = _create_session(client, scenario)
    date = "2026-09-15"
    payload = {
        "diary_date": date,
        "meal_type": "lunch",
        "amount": 1,
        "amount_unit": "serving",
        "quick_add": {"name": "Тестовый приём пищи", "energy_kcal": 420, "protein_g": 17},
        "_demo_food_retry_key": "synthetic-food-retry-key",
        "_demo_food_generation": 0,
    }
    response = _transport(client, token, "/api/v1/nutrition/diary/entries", "POST", payload)
    assert response.status_code == 200
    assert float(response.json()["nutrition"]["energy_kcal"]) == 420
    assert FoodDiaryEntryResponse.model_validate(response.json()).nutrition_confidence == "partial"
    diary = _transport(client, token, f"/api/v1/nutrition/diary?diary_date={date}").json()
    other_diary = _transport(client, other, f"/api/v1/nutrition/diary?diary_date={date}").json()
    assert any(
        entry["food_name"] == "Тестовый приём пищи"
        for meal in diary["meals"]
        for entry in meal["entries"]
    )
    assert all(
        entry["food_name"] != "Тестовый приём пищи"
        for meal in other_diary["meals"]
        for entry in meal["entries"]
    )
    retry = _transport(client, token, "/api/v1/nutrition/diary/entries", "POST", payload)
    assert retry.json() == response.json()
    changed = {**payload, "quick_add": {"energy_kcal": 421}}
    assert (
        _transport(client, token, "/api/v1/nutrition/diary/entries", "POST", changed).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/demo/sessions/current/reset", headers={"X-Demo-Session": token}
        ).status_code
        == 200
    )
    assert (
        _transport(client, token, "/api/v1/nutrition/diary/entries", "POST", payload).status_code
        == 409
    )


def test_demo_food_rejects_unknown_resources_and_missing_retry_guards(client) -> None:
    token, _ = _create_session(client, "self_training")
    payload = {
        "diary_date": "2026-09-15",
        "meal_type": "breakfast",
        "amount": 100,
        "amount_unit": "g",
        "food_id": 1,
        "_demo_food_retry_key": "key",
        "_demo_food_generation": 0,
    }
    assert (
        _transport(client, token, "/api/v1/nutrition/diary/entries", "POST", payload).status_code
        == 403
    )
    assert (
        _transport(
            client,
            token,
            "/api/v1/nutrition/diary/entries",
            "POST",
            {**payload, "food_id": 80001, "_demo_food_generation": None},
        ).status_code
        == 403
    )


def test_trainer_demo_rejects_non_fixture_clients_and_external_actions(client) -> None:
    token, _ = _create_session(client, "trainer")
    for path in (
        "/api/v1/coach/clients/1/operations",
        "/api/v1/coach/clients/1/analytics",
        "/api/v1/coach/clients/1/workouts",
        "/api/v1/coach/invitations",
        "/api/v1/users/1",
    ):
        assert _transport(client, token, path).status_code == 403
    assert _transport(client, token, "/api/v1/coach/invitations", "POST", {}).status_code == 403
    assert _transport(client, token, "/api/v1/notifications").json() == []
    assert _transport(client, token, "/api/v1/notifications", "POST", {}).status_code == 403


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/v1/coach/sessions",
            {
                "client_id": 51001,
                "starts_at": "2026-09-20T18:00:00",
                "timezone": "Europe/Moscow",
                "private_note": "x" * 2001,
            },
        ),
        ("/api/v1/coach/packages", {"client_id": 51001, "name": "x" * 129, "included_sessions": 1}),
        (
            "/api/v1/coach/payments",
            {
                "client_id": 51001,
                "expected_amount_minor": 100,
                "currency": "RUB",
                "note": "x" * 1001,
            },
        ),
        (
            "/api/v1/coach/tasks",
            {
                "client_id": 51001,
                "title": "x" * 241,
                "due_at": "2026-09-20T18:00:00",
                "timezone": "Europe/Moscow",
            },
        ),
        ("/api/v1/coach/clients/51002/workouts/50011/comments", {"body": "x" * 2001}),
    ],
)
def test_demo_coach_rejects_oversized_payloads_without_mutation(client, path, payload) -> None:
    token, _ = _create_session(client, "trainer")
    headers = {"X-Demo-Session": token}
    before = client.get("/api/v1/demo/sessions/current", headers=headers).json()
    assert _transport(client, token, path, "POST", payload).status_code == 403
    assert client.get("/api/v1/demo/sessions/current", headers=headers).json() == before


def test_demo_coach_rejects_oversized_session_update_without_mutation(client) -> None:
    token, _ = _create_session(client, "trainer")
    before = _transport(client, token, "/api/v1/coach/sessions").json()
    response = _transport(
        client, token, "/api/v1/coach/sessions/71001", "PATCH", {"private_note": "x" * 2001}
    )
    assert response.status_code == 403
    assert _transport(client, token, "/api/v1/coach/sessions").json() == before


@pytest.mark.parametrize(
    ("scenario", "path", "method", "payload"),
    [
        (
            "nutrition",
            "/api/v1/nutrition/hydration/entries/v2",
            "POST",
            {"volume_ml": 200, "beverage_type": []},
        ),
        (
            "nutrition",
            "/api/v1/nutrition/hydration/entries/v2",
            "POST",
            {"volume_ml": 200, "beverage_type": "water", "source": {}},
        ),
        ("nutrition", "/api/v1/nutrition/hydration/goal", "POST", {"source": []}),
        (
            "nutrition",
            "/api/v1/nutrition/hydration/goal",
            "POST",
            {"source": "national_academies_beverages", "sex": {}, "adult_confirmed": True},
        ),
        (
            "nutrition",
            "/api/v1/nutrition/hydration/presets",
            "POST",
            {"label": "Стакан", "volume_ml": 200, "beverage_type": []},
        ),
        ("trainer", "/api/v1/coach/packages/72001/state", "PATCH", {"state": []}),
        ("trainer", "/api/v1/coach/tasks/74001/state", "PATCH", {"state": {}}),
        (
            "trainer",
            "/api/v1/coach/clients/51001/operational-status",
            "PATCH",
            {"operational_status": []},
        ),
        (
            "trainer",
            "/api/v1/coach/program-rollouts/apply",
            "POST",
            {
                "template_id": 1,
                "template_fingerprint": "0" * 64,
                "reason": "Тест",
                "targets": [{"client_id": [], "program_id": 1, "expected_revision_number": 0}],
            },
        ),
    ],
)
def test_demo_malformed_json_types_are_rejected(client, scenario, path, method, payload) -> None:
    token, _ = _create_session(client, scenario)
    before = client.get("/api/v1/demo/sessions/current", headers={"X-Demo-Session": token}).json()
    assert _transport(client, token, path, method, payload).status_code == 403
    assert (
        client.get("/api/v1/demo/sessions/current", headers={"X-Demo-Session": token}).json()
        == before
    )


@pytest.mark.parametrize("field", ["rir", "set_kind"])
def test_demo_workout_rejects_unhashable_enum_values(client, field) -> None:
    token, _ = _create_session(client, "self_training")
    assert _transport(client, token, "/api/v1/workouts/50001/start", "POST").status_code == 200
    assert (
        _transport(client, token, "/api/v1/workouts/sets/60004", "PATCH", {field: []}).status_code
        == 403
    )


def test_demo_rollout_valid_contract_stays_non_mutating(client) -> None:
    token, _ = _create_session(client, "trainer")
    preview = _transport(
        client,
        token,
        "/api/v1/coach/program-rollouts/preview",
        "POST",
        {"template_id": 1, "client_ids": [51001]},
    )
    assert preview.status_code == 200
    applied = _transport(
        client,
        token,
        "/api/v1/coach/program-rollouts/apply",
        "POST",
        {
            "template_id": 1,
            "template_fingerprint": "0" * 64,
            "targets": [{"client_id": 51001, "program_id": 51001, "expected_revision_number": 0}],
            "confirmed": True,
            "reason": "Демо",
        },
    )
    assert applied.status_code == 200
    assert applied.json()["applied_count"] == 0
    assert applied.json()["failed_count"] == 1
    assert (
        _transport(
            client,
            token,
            "/api/v1/coach/program-rollouts/apply",
            "POST",
            {
                "template_id": True,
                "template_fingerprint": "0" * 64,
                "targets": [
                    {"client_id": 51001, "program_id": 51001, "expected_revision_number": 0}
                ],
                "confirmed": True,
                "reason": "Демо",
            },
        ).status_code
        == 403
    )


def test_demo_hydration_limit_keeps_retry_idempotent(client) -> None:
    token, _ = _create_session(client, "nutrition")
    path = "/api/v1/nutrition/hydration/entries/v2"
    payload = {"volume_ml": 200, "beverage_type": "water", "_hydration_retry_key": "first"}
    first = _transport(client, token, path, "POST", payload)
    assert first.status_code == 200
    for index in range(99):
        assert (
            _transport(
                client, token, path, "POST", {**payload, "_hydration_retry_key": f"key-{index}"}
            ).status_code
            == 200
        )
    assert _transport(client, token, path, "POST", payload).json() == first.json()
    assert (
        _transport(
            client, token, path, "POST", {**payload, "_hydration_retry_key": "overflow"}
        ).status_code
        == 409
    )


def test_demo_coach_session_collection_is_bounded() -> None:
    store = DemoSessionStore()
    token, _ = store.create("trainer")
    payload = {
        "client_id": 51001,
        "starts_at": "2026-09-20T18:00:00",
        "timezone": "Europe/Moscow",
        "private_note": "x" * 2000,
    }
    for _ in range(96):
        store.transport(token, "/api/v1/coach/sessions", "POST", payload)
    before = store.get(token)
    with pytest.raises(DemoTransitionError):
        store.transport(token, "/api/v1/coach/sessions", "POST", payload)
    assert store.get(token) == before


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/v1/coach/sessions",
            {"client_id": 51001, "starts_at": "2026-09-20T18:00:00", "timezone": "Europe/Moscow"},
        ),
        ("/api/v1/coach/packages", {"client_id": 51001, "name": "Пакет", "included_sessions": 1}),
        (
            "/api/v1/coach/payments",
            {"client_id": 51001, "expected_amount_minor": 100, "currency": "RUB"},
        ),
        (
            "/api/v1/coach/tasks",
            {
                "client_id": 51001,
                "title": "Задача",
                "due_at": "2026-09-20T18:00:00",
                "timezone": "Europe/Moscow",
            },
        ),
        ("/api/v1/nutrition/hydration/presets", {"label": "Стакан", "volume_ml": 250}),
    ],
)
def test_demo_collection_limit_does_not_affect_other_sessions(monkeypatch, path, payload) -> None:
    from fitminiapp_api.services import demo_transport

    monkeypatch.setattr(demo_transport, "MAX_DEMO_COLLECTION_SIZE", 5)
    store = DemoSessionStore()
    token, _ = store.create("trainer")
    other, _ = store.create("trainer")
    created = 0
    for _ in range(6):
        try:
            store.transport(token, path, "POST", payload)
            created += 1
        except DemoTransitionError:
            break
    assert 1 <= created <= 5
    before = store.get(token)
    with pytest.raises(DemoTransitionError):
        store.transport(token, path, "POST", payload)
    assert store.get(token) == before
    assert store.transport(other, path, "POST", payload)


def test_demo_food_preserves_unknown_nutrients_in_day_and_snapshot(client) -> None:
    token, _ = _create_session(client, "nutrition")
    today = datetime.now(UTC).date().isoformat()
    payload = {
        "diary_date": today,
        "meal_type": "lunch",
        "amount": 1,
        "amount_unit": "serving",
        "quick_add": {"energy_kcal": 420},
        "_demo_food_retry_key": "unknown-nutrients",
        "_demo_food_generation": 0,
    }
    assert (
        _transport(client, token, "/api/v1/nutrition/diary/entries", "POST", payload).status_code
        == 200
    )
    day = _transport(client, token, "/api/v1/nutrition/diary").json()
    assert day["totals"]["protein_g"] is None
    assert day["totals"]["fat_g"] is None
    assert day["remaining"]["protein_g"] is None
    snapshot = client.get("/api/v1/demo/sessions/current", headers={"X-Demo-Session": token})
    assert snapshot.status_code == 200
    assert snapshot.json()["state"]["protein_g"] is None
    report = _transport(client, token, "/api/v1/workouts/progress/nutrition-report").json()
    assert report["daily"][0]["protein_g"] is None


def test_demo_transport_maps_coach_capacity_to_current_response_dto(client) -> None:
    token, _ = _create_session(client, "trainer")

    response = _transport(client, token, "/api/v1/coach/capacity")

    assert response.status_code == 200, response.text
    payload = CoachCapacityResponse.model_validate(response.json())
    assert payload.active_client_count == 3
    assert payload.pending_invite_count == 1
    assert payload.clients_with_active_program_count == 2
    assert payload.roster_coverage_percent == 66.7
    assert payload.capacity_band == "0_9"
    assert payload.next_capacity_boundary == 10
    assert payload.scale_boundaries == (10, 30, 100)
    assert payload.bottlenecks[0].key == "attention"


def test_demo_transport_exposes_synthetic_coach_inbox_without_account_access(client) -> None:
    with get_session_context() as db:
        users_before = db.query(User).count()

    trainer_token, _ = _create_session(client, "trainer")
    response = _transport(client, trainer_token, "/api/v1/coach/inbox?limit=50")

    assert response.status_code == 200, response.text
    inbox = CoachInboxResponse.model_validate(response.json())
    tasks = _transport(client, trainer_token, "/api/v1/coach/tasks").json()
    open_tasks = [task for task in tasks if task["state"] == "open"]
    assert inbox.total == 1 + len(open_tasks)
    assert inbox.counts.tasks == len(open_tasks)
    assert {item.source_id for item in inbox.items if item.kind == "task"} == {
        task["id"] for task in open_tasks
    }
    assert inbox.items[0].client.id == 51_003
    assert inbox.items[0].action == "assign_program"
    limited = CoachInboxResponse.model_validate(
        _transport(client, trainer_token, "/api/v1/coach/inbox?limit=1").json()
    )
    assert len(limited.items) == 1
    assert limited.total == inbox.total
    assert limited.counts.tasks == inbox.counts.tasks
    assert (
        _transport(client, trainer_token, "/api/v1/coach/inbox?limit=1&limit=2").status_code == 403
    )
    task_id = open_tasks[0]["id"]
    changed = _transport(
        client,
        trainer_token,
        f"/api/v1/coach/tasks/{task_id}/state",
        "PATCH",
        {"state": "completed"},
    )
    assert changed.status_code == 200
    after = CoachInboxResponse.model_validate(
        _transport(client, trainer_token, "/api/v1/coach/inbox").json()
    )
    assert after.counts.tasks == len(open_tasks) - 1
    assert task_id not in {item.source_id for item in after.items if item.kind == "task"}

    self_token, _ = _create_session(client, "self_training")
    assert _transport(client, self_token, "/api/v1/coach/inbox?limit=50").status_code == 403
    for path in (
        "/api/v1/coach/capacity",
        "/api/v1/coach/tasks",
        "/api/v1/coach/clients/51001/operations",
    ):
        assert _transport(client, self_token, path).status_code == 403

    with get_session_context() as db:
        assert db.query(User).count() == users_before


def test_demo_transport_exposes_owned_fixture_history_and_denies_unknown_exercises(client) -> None:
    trainer_token, _ = _create_session(client, "trainer")

    response = _transport(client, trainer_token, "/api/v1/programs/exercises/1001/history")

    assert response.status_code == 200, response.text
    history = ExerciseHistoryResponse.model_validate(response.json())
    assert history.exercise_id == 1001
    assert history.recent_sessions[0].workout_exercise_id == 61_001
    assert history.recent_sessions[0].sets[0].rir == "2"

    assert (
        _transport(client, trainer_token, "/api/v1/programs/exercises/1002/history").status_code
        == 403
    )


def test_demo_hydration_rejects_delayed_request_after_reset(client) -> None:
    token, _ = _create_session(client, "nutrition")
    path = "/api/v1/nutrition/hydration/entries/v2"
    day = _transport(client, token, "/api/v1/nutrition/hydration").json()
    generation = day["demo_generation"]
    body = {
        "volume_ml": 250,
        "beverage_type": "water",
        "source": "quick_preset",
        "_hydration_retry_key": "before-reset",
        "_hydration_generation": generation,
    }
    # An old tab still using the legacy transport path must be denied.
    assert (
        _transport(client, token, "/api/v1/nutrition/hydration/entries", "POST", body).status_code
        == 409
    )
    assert _transport(client, token, path, "POST", body).status_code == 200
    assert (
        client.post(
            "/api/v1/demo/sessions/current/reset", headers={"X-Demo-Session": token}
        ).status_code
        == 200
    )
    assert _transport(client, token, path, "POST", body).status_code == 409
    next_day = _transport(client, token, "/api/v1/nutrition/hydration").json()
    assert next_day["demo_generation"] != generation
    assert next_day["total_ml"] == 1350
    assert (
        _transport(client, token, path, "POST", {**body, "_hydration_generation": True}).status_code
        == 403
    )
    assert (
        _transport(
            client,
            token,
            path,
            "POST",
            {
                **body,
                "_hydration_retry_key": "after-reset",
                "_hydration_generation": next_day["demo_generation"],
            },
        ).status_code
        == 200
    )
    assert _transport(client, token, "/api/v1/nutrition/hydration").json()["total_ml"] == 1600


def test_demo_hydration_retry_reuses_entry_and_rejects_key_conflicts(client) -> None:
    token, _ = _create_session(client, "nutrition")
    other_token, _ = _create_session(client, "nutrition")
    path = "/api/v1/nutrition/hydration/entries/v2"
    body = {
        "volume_ml": 250,
        "beverage_type": "water",
        "source": "quick_preset",
        "diary_date": "2026-09-01",
        "_hydration_retry_key": "synthetic-key",
    }

    first = _transport(client, token, path, "POST", body)
    retry = _transport(client, token, path, "POST", body)
    assert first.status_code == retry.status_code == 200
    assert retry.json() == first.json()
    assert "_hydration_retry_key" not in first.json()
    assert _transport(client, token, path, "POST", {**body, "volume_ml": 500}).status_code == 409
    assert (
        _transport(client, other_token, path, "POST", {**body, "volume_ml": 500}).status_code == 200
    )
    another = _transport(client, token, path, "POST", {**body, "_hydration_retry_key": "new-key"})
    assert another.status_code == 200
    assert another.json()["id"] != first.json()["id"]


def test_demo_hydration_undo_rejects_edits_and_reset_reuse(client) -> None:
    token, _ = _create_session(client, "nutrition")
    path = "/api/v1/nutrition/hydration/entries"
    generation = _transport(client, token, "/api/v1/nutrition/hydration").json()["demo_generation"]
    create = {"volume_ml": 250, "beverage_type": "water", "source": "manual"}
    entry = _transport(client, token, path + "/v2", "POST", create).json()
    snapshot = {
        **{key: entry[key] for key in ("created_at", "updated_at", "diary_date")},
        "_hydration_generation": generation,
    }
    entry_path = f"{path}/{entry['id']}"
    assert _transport(client, token, entry_path, "DELETE").status_code == 409
    edited = _transport(
        client,
        token,
        entry_path,
        "PATCH",
        {"volume_ml": 400, "beverage_type": "tea", "occurred_at": "2026-08-20T08:30:00Z"},
    )
    assert edited.status_code == 200
    assert _transport(client, token, entry_path + "-undo", "DELETE", snapshot).status_code == 409
    assert (
        _transport(client, token, "/api/v1/nutrition/hydration?diary_date=2026-08-20").json()[
            "entries"
        ][0]["volume_ml"]
        == 400
    )
    assert (
        client.post(
            "/api/v1/demo/sessions/current/reset", headers={"X-Demo-Session": token}
        ).status_code
        == 200
    )
    replacement = _transport(client, token, path + "/v2", "POST", create).json()
    assert replacement["id"] == entry["id"]
    assert _transport(client, token, entry_path + "-undo", "DELETE", snapshot).status_code == 409
    new_generation = _transport(client, token, "/api/v1/nutrition/hydration").json()[
        "demo_generation"
    ]
    new_snapshot = {
        **{key: replacement[key] for key in ("created_at", "updated_at", "diary_date")},
        "_hydration_generation": new_generation,
    }
    assert (
        _transport(client, token, entry_path + "-undo", "DELETE", new_snapshot).status_code == 200
    )


def test_demo_transport_covers_nutrition_and_trainer_feedback_without_external_writes(
    client,
) -> None:
    nutrition_token, _ = _create_session(client, "nutrition")
    before = _transport(client, nutrition_token, "/api/v1/nutrition/hydration").json()
    added_water = _transport(
        client,
        nutrition_token,
        "/api/v1/nutrition/hydration/entries/v2",
        "POST",
        {"volume_ml": 350, "beverage_type": "water", "source": "quick_preset"},
    )
    entry = HydrationEntryResponse.model_validate(added_water.json())
    assert entry.volume_ml == 350
    after = HydrationDayResponse.model_validate(
        _transport(client, nutrition_token, "/api/v1/nutrition/hydration").json()
    )
    assert after.total_ml == before["total_ml"] + 350
    assert any(item.id == entry.id for item in after.entries)
    assert (
        _transport(
            client,
            nutrition_token,
            f"/api/v1/nutrition/hydration/entries/{entry.id}-delete",
            "DELETE",
            {
                **{
                    key: added_water.json()[key]
                    for key in ("created_at", "updated_at", "diary_date")
                },
                "_hydration_generation": before["demo_generation"],
            },
        ).status_code
        == 200
    )

    added_food = _transport(
        client,
        nutrition_token,
        "/api/v1/nutrition/diary/entries",
        "POST",
        {
            "diary_date": datetime.now(UTC).date().isoformat(),
            "meal_type": "breakfast",
            "amount": 1,
            "amount_unit": "serving",
            "quick_add": {"energy_kcal": 428, "protein_g": 24},
            "_demo_food_retry_key": "nutrition-test-key",
            "_demo_food_generation": 0,
        },
    )
    assert added_food.status_code == 200
    FoodDiaryDayResponse.model_validate(
        _transport(client, nutrition_token, "/api/v1/nutrition/diary").json()
    )
    report = NutritionReportResponse.model_validate(
        _transport(client, nutrition_token, "/api/v1/workouts/progress/nutrition-report").json()
    )
    assert report.summary.current_day_status == "complete"
    assert report.daily[0].calories == 1_588
    assert (
        _transport(
            client,
            nutrition_token,
            "/api/v1/exports/current",
            "POST",
            {},
        ).status_code
        == 403
    )

    trainer_token, _ = _create_session(client, "trainer")
    for item in _transport(client, trainer_token, "/api/v1/coach/clients").json():
        ClientResponse.model_validate(item)
    for item in _transport(client, trainer_token, "/api/v1/coach/assigned-programs").json():
        CoachAssignedProgramResponse.model_validate(item)
    attention = CoachAttentionResponse.model_validate(
        _transport(client, trainer_token, "/api/v1/coach/attention").json()
    )
    assert attention.total == 1
    assert attention.items[0].kind == "without_program"
    assert attention.items[0].client.id == 51003
    CoachOperationsTodayResponse.model_validate(
        _transport(client, trainer_token, "/api/v1/coach/operations/today").json()
    )
    agenda = CoachAgendaResponse.model_validate(
        _transport(client, trainer_token, "/api/v1/coach/agenda").json()
    )
    assert {item.status for item in agenda.items} >= {"scheduled", "completed", "no_show"}
    packages = _transport(client, trainer_token, "/api/v1/coach/packages").json()
    assert {item["state"] for item in packages} >= {"active", "finished", "cancelled"}
    for item in packages:
        CoachPackageResponse.model_validate(item)
    payments = _transport(client, trainer_token, "/api/v1/coach/payments").json()
    assert {item["status"] for item in payments} >= {"expected", "partial", "paid"}
    for item in payments:
        CoachPaymentResponse.model_validate(item)
    for item in _transport(client, trainer_token, "/api/v1/coach/tasks").json():
        CoachTaskResponse.model_validate(item)
    CoachClientOperationsResponse.model_validate(
        _transport(client, trainer_token, "/api/v1/coach/clients/51001/operations").json()
    )
    created_task = _transport(
        client,
        trainer_token,
        "/api/v1/coach/tasks",
        "POST",
        {
            "client_id": 51001,
            "title": "Подтвердить план",
            "due_at": "2026-09-19T12:00:00",
            "timezone": "Europe/Moscow",
            "fold": 0,
        },
    )
    CoachTaskResponse.model_validate(created_task.json())
    created_session = _transport(
        client,
        trainer_token,
        "/api/v1/coach/sessions",
        "POST",
        {
            "client_id": 51001,
            "starts_at": "2026-09-20T18:00:00",
            "timezone": "Europe/Moscow",
            "fold": 0,
            "duration_minutes": 60,
            "format": "online",
        },
    )
    CoachSessionResponse.model_validate(created_session.json()[0])
    created_payment = _transport(
        client,
        trainer_token,
        "/api/v1/coach/payments",
        "POST",
        {
            "client_id": 51001,
            "expected_amount_minor": 20_000,
            "paid_amount_minor": 0,
            "currency": "RUB",
        },
    )
    CoachPaymentResponse.model_validate(created_payment.json())
    edited_payment = _transport(
        client,
        trainer_token,
        f"/api/v1/coach/payments/{created_payment.json()['id']}",
        "PATCH",
        {"paid_amount_minor": 20_000},
    )
    assert CoachPaymentResponse.model_validate(edited_payment.json()).status == "paid"
    timeline = _transport(client, trainer_token, "/api/v1/coach/clients/51002/workouts?limit=30")
    WorkoutTimelineItem.model_validate(timeline.json()[0])
    comment = _transport(
        client,
        trainer_token,
        "/api/v1/coach/clients/51002/workouts/50011/comments",
        "POST",
        {"body": "Техника стабильна", "workout_exercise_id": 62001},
    )
    WorkoutCommentResponse.model_validate(comment.json())
    saved_comments = _transport(
        client,
        trainer_token,
        "/api/v1/coach/clients/51002/workouts/50011/comments",
    )
    assert saved_comments.json()[0]["client_user_id"] == 51002


def test_demo_transport_rejects_unknown_path_extensions(client) -> None:
    token, _ = _create_session(client, "self_training")

    for path in (
        "/api/v1/workouts/cardio/unknown",
        "/api/v1/coach/clients/51002/workouts/50011/comments/extra",
    ):
        response = _transport(client, token, path)
        assert response.status_code == 403


def test_demo_transport_bounds_progress_period(client) -> None:
    token, _ = _create_session(client, "self_training")

    valid = _transport(client, token, "/api/v1/workouts/progress/summary?period_days=366")
    assert valid.status_code == 200

    too_long = _transport(client, token, "/api/v1/workouts/progress/summary?period_days=999999999")
    assert too_long.status_code == 403

    out_of_range = _transport(client, token, "/api/v1/workouts/progress/summary?period_days=0")
    assert out_of_range.status_code == 403
