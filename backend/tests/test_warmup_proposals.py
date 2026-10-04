from __future__ import annotations

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.program import UserWorkoutSet, WorkoutSetMutation
from fitminiapp_api.services.warmup_proposals import _warmup_weights
from fitminiapp_api.services.workouts import counts_toward_working_volume, is_pr_record_set


def _auth(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={
            "telegram_user_id": telegram_user_id,
            "is_coach": False,
            "is_admin": False,
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_today_workout(client, headers: dict[str, str], *, cardio: bool = False) -> dict:
    exercises = client.get("/api/v1/programs/exercises", headers=headers)
    assert exercises.status_code == 200
    exercise = next(
        item
        for item in exercises.json()
        if item["metric_type"] == ("cardio" if cardio else "strength")
    )
    exercise_payload = (
        {
            "exercise_id": exercise["id"],
            "prescribed_duration_minutes": 25,
            "rest_seconds": 90,
        }
        if cardio
        else {
            "exercise_id": exercise["id"],
            "prescribed_sets": 1,
            "prescribed_reps": "8-10",
            "rest_seconds": 90,
        }
    )
    created = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Программа для проверки разминки",
            "goal": "recomposition",
            "level": "intermediate",
            "mode": "self",
            "assign_after_create": True,
            "days": [
                {
                    "title": "День 1",
                    "exercises": [exercise_payload],
                }
            ],
        },
    )
    assert created.status_code == 200
    workout = client.get("/api/v1/workouts/today", headers=headers)
    assert workout.status_code == 200
    return workout.json()


def _proposal_request(workout: dict, client, headers: dict[str, str]) -> tuple[dict, dict]:
    exercise = workout["exercises"][0]
    started = client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers)
    assert started.status_code == 200
    preview = client.post(
        f"/api/v1/workouts/{workout['id']}/exercises/{exercise['id']}/warmup-proposals/preview",
        headers=headers,
        json={"target_set_id": exercise["sets"][0]["id"], "working_weight_kg": 80},
    )
    assert preview.status_code == 200
    return exercise, preview.json()


def test_warmup_preview_is_deterministic_and_does_not_persist_rows(client) -> None:
    headers = _auth(client, 29_501)
    workout = _create_today_workout(client, headers)
    exercise, preview = _proposal_request(workout, client, headers)

    assert preview["status"] == "proposal"
    assert preview["ruleset_version"] == "warmup-proposal-v1"
    assert preview["rows"] == [
        {"weight_kg": 32, "reps": 8},
        {"weight_kg": 48, "reps": 5},
        {"weight_kg": 60, "reps": 3},
    ]
    assert preview["state_token"]
    assert preview["proposal_token"]

    with get_session_context() as db:
        assert (
            db.query(UserWorkoutSet)
            .filter(UserWorkoutSet.workout_exercise_id == exercise["id"])
            .count()
            == 1
        )
        assert db.query(WorkoutSetMutation).count() == 0


def test_warmup_apply_is_editable_ordered_and_idempotent(client) -> None:
    headers = _auth(client, 29_502)
    workout = _create_today_workout(client, headers)
    exercise, preview = _proposal_request(workout, client, headers)
    apply_payload = {
        "target_set_id": exercise["sets"][0]["id"],
        "working_weight_kg": 80,
        "rows": [
            {"weight_kg": 30, "reps": 10},
            {"weight_kg": 45.5, "reps": 6},
            {"weight_kg": 60, "reps": 3},
        ],
        "state_token": preview["state_token"],
        "proposal_token": preview["proposal_token"],
        "mutation_id": "warmup-test-mutation-29502",
    }

    applied = client.post(
        f"/api/v1/workouts/{workout['id']}/exercises/{exercise['id']}/warmup-proposals/apply",
        headers=headers,
        json=apply_payload,
    )
    assert applied.status_code == 200, applied.text
    body = applied.json()
    assert body["idempotent"] is False
    assert len(body["materialized_set_ids"]) == 3
    returned_sets = body["workout"]["exercises"][0]["sets"]
    assert [item["set_kind"] for item in returned_sets] == ["warmup"] * 3 + ["working"]
    assert [item["planned_role"] for item in returned_sets[:3]] == ["warmup"] * 3
    assert [(item["actual_weight"], item["actual_reps"]) for item in returned_sets[:3]] == [
        (30, 10),
        (45.5, 6),
        (60, 3),
    ]
    assert returned_sets[-1]["set_number"] == 1
    assert returned_sets[-1]["actual_weight"] is None
    assert returned_sets[-1]["is_completed"] is False

    replayed = client.post(
        f"/api/v1/workouts/{workout['id']}/exercises/{exercise['id']}/warmup-proposals/apply",
        headers=headers,
        json=apply_payload,
    )
    assert replayed.status_code == 200, replayed.text
    assert replayed.json()["idempotent"] is True
    assert replayed.json()["materialized_set_ids"] == body["materialized_set_ids"]

    changed_payload = {**apply_payload, "rows": [{"weight_kg": 32, "reps": 8}] * 3}
    conflict = client.post(
        f"/api/v1/workouts/{workout['id']}/exercises/{exercise['id']}/warmup-proposals/apply",
        headers=headers,
        json=changed_payload,
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "warmup_idempotency_conflict"

    with get_session_context() as db:
        rows = (
            db.query(UserWorkoutSet)
            .filter(UserWorkoutSet.workout_exercise_id == exercise["id"])
            .all()
        )
        assert len(rows) == 4
        assert db.query(WorkoutSetMutation).count() == 3
        assert all(
            not counts_toward_working_volume(row) for row in rows if row.set_kind == "warmup"
        )
        assert all(not is_pr_record_set(row) for row in rows if row.set_kind == "warmup")


def test_warmup_apply_fails_closed_when_target_changes_after_preview(client) -> None:
    headers = _auth(client, 29_503)
    workout = _create_today_workout(client, headers)
    exercise, preview = _proposal_request(workout, client, headers)
    target_set_id = exercise["sets"][0]["id"]
    changed = client.patch(
        f"/api/v1/workouts/sets/{target_set_id}",
        headers=headers,
        json={"set_kind": "working"},
    )
    assert changed.status_code == 200

    response = client.post(
        f"/api/v1/workouts/{workout['id']}/exercises/{exercise['id']}/warmup-proposals/apply",
        headers=headers,
        json={
            "target_set_id": target_set_id,
            "working_weight_kg": 80,
            "rows": preview["rows"],
            "state_token": preview["state_token"],
            "proposal_token": preview["proposal_token"],
            "mutation_id": "warmup-test-stale-29503",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "warmup_stale"

    with get_session_context() as db:
        assert db.query(UserWorkoutSet).count() == 1


def test_warmup_preview_rejects_started_or_unsupported_workout(client) -> None:
    headers = _auth(client, 29_504)
    workout = _create_today_workout(client, headers)
    exercise = workout["exercises"][0]
    assert (
        client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers).status_code == 200
    )
    started = client.patch(
        f"/api/v1/workouts/sets/{exercise['sets'][0]['id']}",
        headers=headers,
        json={"actual_weight": 40},
    )
    assert started.status_code == 200
    rejected = client.post(
        f"/api/v1/workouts/{workout['id']}/exercises/{exercise['id']}/warmup-proposals/preview",
        headers=headers,
        json={"target_set_id": exercise["sets"][0]["id"], "working_weight_kg": 80},
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "warmup_target_started"

    cardio_headers = _auth(client, 29_506)
    cardio_workout = _create_today_workout(client, cardio_headers, cardio=True)
    cardio_exercise = cardio_workout["exercises"][0]
    assert (
        client.post(
            f"/api/v1/workouts/{cardio_workout['id']}/start", headers=cardio_headers
        ).status_code
        == 200
    )
    unsupported = client.post(
        f"/api/v1/workouts/{cardio_workout['id']}/exercises/{cardio_exercise['id']}/warmup-proposals/preview",
        headers=cardio_headers,
        json={"target_set_id": cardio_exercise["sets"][0]["id"], "working_weight_kg": 80},
    )
    assert unsupported.status_code == 409
    assert unsupported.json()["detail"]["code"] == "warmup_metric_unsupported"


def test_warmup_preview_returns_unavailable_at_low_working_weight(client) -> None:
    headers = _auth(client, 29_505)
    workout = _create_today_workout(client, headers)
    exercise, _ = _proposal_request(workout, client, headers)
    response = client.post(
        f"/api/v1/workouts/{workout['id']}/exercises/{exercise['id']}/warmup-proposals/preview",
        headers=headers,
        json={"target_set_id": exercise["sets"][0]["id"], "working_weight_kg": 20},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["rows"] == []
    assert response.json()["state_token"] is None
    assert response.json()["proposal_token"] is None


def test_warmup_rounding_boundaries_are_deterministic() -> None:
    assert _warmup_weights(20) == []
    assert _warmup_weights(21) == []
    assert _warmup_weights(49) == [29.5, 37]
    assert _warmup_weights(50) == [20, 30, 37.5]
    assert _warmup_weights(80) == [32, 48, 60]
    assert _warmup_weights(1000) == [400, 600, 750]
