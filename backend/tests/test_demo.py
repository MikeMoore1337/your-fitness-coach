from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.user import User
from fitminiapp_api.services.demo_sessions import DemoSessionExpiredError, DemoSessionStore


def _create_session(client, scenario: str) -> tuple[str, dict]:
    response = client.post("/api/v1/demo/sessions", json={"scenario": scenario})
    assert response.status_code == 201
    assert "no-store" in response.headers["cache-control"]
    payload = response.json()
    return payload.pop("session_token"), payload


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
