from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.coach_attention import CoachAttentionResponse
from fitminiapp_api.schemas.feedback import WorkoutCommentResponse
from fitminiapp_api.schemas.food_diary import FoodDiaryDayResponse
from fitminiapp_api.schemas.hydration import HydrationDayResponse, HydrationEntryResponse
from fitminiapp_api.schemas.program import (
    ClientResponse,
    CoachAssignedProgramResponse,
    ProgramTemplateResponse,
)
from fitminiapp_api.schemas.progress import NutritionReportResponse, ProgressSummaryResponse
from fitminiapp_api.schemas.user import UserResponse
from fitminiapp_api.schemas.workout import (
    TrainingAnalyticsResponse,
    WorkoutScheduleItem,
    WorkoutStatusResponse,
    WorkoutTimelineItem,
    WorkoutTodayResponse,
)
from fitminiapp_api.services.demo_sessions import DemoSessionExpiredError, DemoSessionStore


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


def test_demo_transport_covers_nutrition_and_trainer_feedback_without_external_writes(
    client,
) -> None:
    nutrition_token, _ = _create_session(client, "nutrition")
    before = _transport(client, nutrition_token, "/api/v1/nutrition/hydration").json()
    added_water = _transport(
        client,
        nutrition_token,
        "/api/v1/nutrition/hydration/entries",
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
            client, nutrition_token, f"/api/v1/nutrition/hydration/entries/{entry.id}", "DELETE"
        ).status_code
        == 200
    )

    added_food = _transport(
        client,
        nutrition_token,
        "/api/v1/nutrition/diary/entries",
        "POST",
        {"diary_date": "2026-09-15", "meal_type": "breakfast"},
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
    assert attention.items == []
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
