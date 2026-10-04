import pytest

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.program import UserProgram, UserWorkout, WorkoutAdaptation


def _auth(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": False},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _assign_today_workout(
    client,
    headers: dict[str, str],
    slugs: list[str],
    *,
    prescribed_sets: int = 3,
    prescribed_duration_minutes: int | None = None,
) -> dict:
    catalog = client.get("/api/v1/programs/exercises", headers=headers).json()
    exercise_ids = {item["slug"]: item["id"] for item in catalog}
    response = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Адаптация на сегодня",
            "goal": "recomposition",
            "level": "intermediate",
            "mode": "self",
            "assign_after_create": True,
            "days": [
                {
                    "title": "Тренировка A",
                    "exercises": [
                        {
                            "exercise_id": exercise_ids[slug],
                            "prescribed_sets": prescribed_sets,
                            "prescribed_reps": "8-10",
                            "rest_seconds": 90,
                            **(
                                {"prescribed_duration_minutes": prescribed_duration_minutes}
                                if prescribed_duration_minutes is not None
                                else {}
                            ),
                        }
                        for slug in slugs
                    ],
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    today = client.get("/api/v1/workouts/today", headers=headers)
    assert today.status_code == 200
    return today.json()


def _bench_replacement(client, headers: dict[str, str], workout: dict) -> dict:
    target_id = workout["exercises"][0]["id"]
    response = client.get(
        f"/api/v1/workouts/{workout['id']}/exercises/{target_id}/alternatives",
        params={
            "available_equipment_ids": ["dumbbell", "bench"],
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return next(item for item in response.json() if item["title"] == "Жим гантелей лежа")


def _bench_replacement_payload(workout: dict, replacement: dict) -> dict:
    return {
        "reason": "replace_exercise",
        "target_workout_exercise_id": workout["exercises"][0]["id"],
        "replacement_exercise_id": replacement["exercise_id"],
        "available_equipment_ids": ["dumbbell", "bench"],
    }


def test_time_budget_preview_cancel_apply_and_history_show_actual_workout(client) -> None:
    headers = _auth(client, 93501)
    original = _assign_today_workout(
        client,
        headers,
        ["bench-press", "squat", "dumbbell-curl", "crunch", "standing-calf-raise"],
    )
    payload = {"reason": "limited_time", "time_budget_minutes": 20}

    preview = client.post(
        f"/api/v1/workouts/{original['id']}/adaptations/preview",
        headers=headers,
        json=payload,
    )
    assert preview.status_code == 200, preview.text
    preview_data = preview.json()
    assert preview_data["status"] == "preview"
    assert preview_data["original_estimated_minutes"] > 20
    assert preview_data["adapted_estimated_minutes"] <= 20
    assert {item["priority"] for item in preview_data["original_exercises"][:2]} == {"core"}
    assert all(
        change["from_title"]
        not in {item["title"] for item in preview_data["original_exercises"][:2]}
        for change in preview_data["changes"]
    )

    # Preview/cancel is read-only: without apply the materialized workout is unchanged.
    unchanged = client.get("/api/v1/workouts/today", headers=headers).json()
    assert [item["exercise_id"] for item in unchanged["exercises"]] == [
        item["exercise_id"] for item in original["exercises"]
    ]
    with get_session_context() as db:
        assert db.query(WorkoutAdaptation).count() == 0

    applied = client.post(
        f"/api/v1/workouts/{original['id']}/adaptations/apply",
        headers=headers,
        json={**payload, "preview_token": preview_data["preview_token"]},
    )
    assert applied.status_code == 200, applied.text
    applied_data = applied.json()
    assert len(applied_data["workout"]["exercises"]) == len(preview_data["adapted_exercises"])
    retried = client.post(
        f"/api/v1/workouts/{original['id']}/adaptations/apply",
        headers=headers,
        json={**payload, "preview_token": preview_data["preview_token"]},
    )
    assert retried.status_code == 200
    assert retried.json()["adaptation_id"] == applied_data["adaptation_id"]
    with get_session_context() as db:
        assert db.query(WorkoutAdaptation).count() == 1

    started = client.post(
        f"/api/v1/workouts/{original['id']}/start",
        headers=headers,
    )
    assert started.status_code == 200
    set_id = started.json()["exercises"][0]["sets"][0]["id"]
    assert (
        client.patch(
            f"/api/v1/workouts/sets/{set_id}",
            headers=headers,
            json={"actual_reps": 8, "actual_weight": 20, "is_completed": True},
        ).status_code
        == 200
    )
    finished = client.post(
        f"/api/v1/workouts/{original['id']}/finish",
        headers=headers,
        json={"confirm_incomplete": True},
    )
    assert finished.status_code == 200

    history = client.get("/api/v1/workouts/history", headers=headers).json()
    assert len(history) == 1
    assert [item["title"] for item in history[0]["exercises"]] == [
        item["title"] for item in preview_data["adapted_exercises"]
    ]
    assert history[0]["adaptations"][0]["reason"] == "limited_time"
    assert history[0]["adaptations"][0]["changes"] == preview_data["changes"]


def test_replacement_requires_curated_compatible_alternative_and_fresh_preview(client) -> None:
    headers = _auth(client, 93502)
    workout = _assign_today_workout(client, headers, ["bench-press"], prescribed_sets=1)
    workout_exercise_id = workout["exercises"][0]["id"]
    query = "available_equipment_ids=dumbbell&available_equipment_ids=bench"
    alternatives = client.get(
        f"/api/v1/workouts/{workout['id']}/exercises/{workout_exercise_id}/alternatives?{query}",
        headers=headers,
    )
    assert alternatives.status_code == 200
    replacement = next(item for item in alternatives.json() if item["title"] == "Жим гантелей лежа")
    avoided = client.patch(
        "/api/v1/me/profile",
        headers=headers,
        json={
            "training_preferences": {
                "avoided_exercises": [{"exercise_id": replacement["exercise_id"]}]
            }
        },
    )
    assert avoided.status_code == 200, avoided.text
    filtered = client.get(
        f"/api/v1/workouts/{workout['id']}/exercises/{workout_exercise_id}/alternatives?{query}",
        headers=headers,
    )
    assert replacement["exercise_id"] not in {item["exercise_id"] for item in filtered.json()}
    assert (
        client.patch(
            "/api/v1/me/profile",
            headers=headers,
            json={"training_preferences": {}},
        ).status_code
        == 200
    )
    payload = {
        "reason": "replace_exercise",
        "target_workout_exercise_id": workout_exercise_id,
        "replacement_exercise_id": replacement["exercise_id"],
        "available_equipment_ids": ["dumbbell", "bench"],
    }
    preview = client.post(
        f"/api/v1/workouts/{workout['id']}/adaptations/preview",
        headers=headers,
        json=payload,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["changes"][0]["to_title"] == "Жим гантелей лежа"

    mismatch = client.post(
        f"/api/v1/workouts/{workout['id']}/adaptations/preview",
        headers=headers,
        json={**payload, "available_equipment_ids": ["bodyweight"]},
    )
    assert mismatch.status_code == 409
    assert "недоступное оборудование" in mismatch.json()["detail"]

    stale = client.post(
        f"/api/v1/workouts/{workout['id']}/adaptations/apply",
        headers=headers,
        json={
            **payload,
            "available_equipment_ids": ["dumbbell", "bench", "bodyweight"],
            "preview_token": preview.json()["preview_token"],
        },
    )
    assert stale.status_code == 409
    assert "preview заново" in stale.json()["detail"]


def test_in_progress_replacement_preserves_other_results_and_is_exported(client) -> None:
    headers = _auth(client, 93505)
    original = _assign_today_workout(
        client,
        headers,
        ["bench-press", "squat"],
        prescribed_sets=1,
    )
    started = client.post(f"/api/v1/workouts/{original['id']}/start", headers=headers)
    assert started.status_code == 200, started.text
    active = started.json()
    target = active["exercises"][0]
    other = active["exercises"][1]
    other_set = other["sets"][0]
    logged_other = client.patch(
        f"/api/v1/workouts/sets/{other_set['id']}",
        headers=headers,
        json={
            "actual_reps": 8,
            "actual_weight": 40,
            "rir": "2",
            "reached_failure": False,
            "is_completed": True,
        },
    )
    assert logged_other.status_code == 200, logged_other.text
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    with get_session_context() as db:
        program = (
            db.query(UserProgram)
            .filter(UserProgram.user_id == user_id, UserProgram.is_active.is_(True))
            .one()
        )
        program_snapshot = {
            "status": program.status,
            "is_active": program.is_active,
            "current_revision_number": program.current_revision_number,
            "template": [
                (item.id, item.exercise_id, item.prescribed_sets, item.prescribed_reps)
                for day in program.template.days
                for item in day.exercises
            ],
            "revisions": [
                (item.revision_number, item.change_kind, item.changed_fields)
                for item in program.revisions
            ],
        }
    replacement = _bench_replacement(client, headers, active)
    payload = _bench_replacement_payload(active, replacement)

    preview = client.post(
        f"/api/v1/workouts/{active['id']}/adaptations/preview",
        headers=headers,
        json=payload,
    )
    assert preview.status_code == 200, preview.text
    preview_data = preview.json()
    assert preview_data["status"] == "preview"
    assert preview_data["ruleset_version"] == "workout-adaptation-v2"
    assert preview_data["changes"][0]["from_exercise_id"] == target["exercise_id"]
    assert preview_data["changes"][0]["to_exercise_id"] == replacement["exercise_id"]
    with get_session_context() as db:
        preview_event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.action == "workout.adaptation_outcome",
                AuditEvent.resource_id == str(active["id"]),
                AuditEvent.details["outcome"].as_string() == "preview_created",
            )
            .one()
        )
        assert preview_event.details["workout_status"] == "in_progress"

    applied = client.post(
        f"/api/v1/workouts/{active['id']}/adaptations/apply",
        headers=headers,
        json={**payload, "preview_token": preview_data["preview_token"]},
    )
    assert applied.status_code == 200, applied.text
    applied_workout = applied.json()["workout"]
    assert applied_workout["status"] == "in_progress"
    replaced = next(item for item in applied_workout["exercises"] if item["id"] == target["id"])
    preserved = next(item for item in applied_workout["exercises"] if item["id"] == other["id"])
    assert replaced["exercise_id"] == replacement["exercise_id"]
    assert replaced["sets"][0]["actual_reps"] is None
    assert replaced["sets"][0]["actual_weight"] is None
    assert preserved["sets"][0]["actual_reps"] == 8
    assert preserved["sets"][0]["actual_weight"] == 40
    assert preserved["sets"][0]["rir"] == "2"
    assert preserved["sets"][0]["reached_failure"] is False
    assert preserved["sets"][0]["is_completed"] is True

    retried = client.post(
        f"/api/v1/workouts/{active['id']}/adaptations/apply",
        headers=headers,
        json={**payload, "preview_token": preview_data["preview_token"]},
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["adaptation_id"] == applied.json()["adaptation_id"]
    conflicting = client.post(
        f"/api/v1/workouts/{active['id']}/adaptations/apply",
        headers=headers,
        json={
            **payload,
            "available_equipment_ids": ["dumbbell", "bench", "bodyweight"],
            "preview_token": preview_data["preview_token"],
        },
    )
    assert conflicting.status_code == 409, conflicting.text

    with get_session_context() as db:
        adaptation = db.query(WorkoutAdaptation).one()
        assert adaptation.original_snapshot["status"] == "in_progress"
        assert adaptation.applied_diff == preview_data["changes"]
        audit = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.action == "workout.adaptation_applied",
                AuditEvent.resource_id == str(active["id"]),
            )
            .one()
        )
        assert audit.details["outcome"] == "applied"
        assert audit.details["workout_status"] == "in_progress"
        program = db.query(UserProgram).filter(UserProgram.user_id == user_id).one()
        assert {
            "status": program.status,
            "is_active": program.is_active,
            "current_revision_number": program.current_revision_number,
            "template": [
                (item.id, item.exercise_id, item.prescribed_sets, item.prescribed_reps)
                for day in program.template.days
                for item in day.exercises
            ],
            "revisions": [
                (item.revision_number, item.change_kind, item.changed_fields)
                for item in program.revisions
            ],
        } == program_snapshot

        stale_event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.action == "workout.adaptation_outcome",
                AuditEvent.resource_id == str(active["id"]),
                AuditEvent.details["outcome"].as_string() == "rejected_stale",
            )
            .one()
        )
        assert stale_event.details["reason"] == "replace_exercise"

    finished = client.post(
        f"/api/v1/workouts/{active['id']}/finish",
        headers=headers,
        json={"confirm_incomplete": True},
    )
    assert finished.status_code == 200, finished.text
    history = client.get("/api/v1/workouts/history", headers=headers)
    assert history.status_code == 200, history.text
    assert history.json()[0]["exercises"][0]["exercise_id"] == replacement["exercise_id"]

    exported = client.get("/api/v1/me/export", headers=headers)
    assert exported.status_code == 200, exported.text
    export_workout = exported.json()["programs"][0]["workouts"][0]
    assert export_workout["adaptations"][0]["applied_diff"] == preview_data["changes"]
    assert export_workout["adaptations"][0]["original_snapshot"]["status"] == "in_progress"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("actual_reps", 8),
        ("actual_weight", 40),
        ("rir", "2"),
        ("reached_failure", False),
        ("is_completed", True),
    ],
)
def test_in_progress_replacement_rejects_strength_execution_evidence(
    client,
    field: str,
    value,
) -> None:
    headers = _auth(client, 93510)
    workout = _assign_today_workout(client, headers, ["bench-press"], prescribed_sets=1)
    started = client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers)
    assert started.status_code == 200, started.text
    replacement = _bench_replacement(client, headers, started.json())
    set_id = started.json()["exercises"][0]["sets"][0]["id"]
    logged = client.patch(
        f"/api/v1/workouts/sets/{set_id}",
        headers=headers,
        json={field: value},
    )
    assert logged.status_code == 200, logged.text
    preview = client.post(
        f"/api/v1/workouts/{workout['id']}/adaptations/preview",
        headers=headers,
        json=_bench_replacement_payload(started.json(), replacement),
    )
    assert preview.status_code == 409, preview.text
    assert "фактические данные" in preview.json()["detail"]
    with get_session_context() as db:
        assert db.query(WorkoutAdaptation).count() == 0
        rejected_event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.action == "workout.adaptation_outcome",
                AuditEvent.resource_id == str(workout["id"]),
                AuditEvent.details["outcome"].as_string() == "rejected_target_started",
            )
            .one()
        )
        assert rejected_event.details["reason"] == "replace_exercise"


def test_in_progress_replacement_without_compatible_alternative_is_audited(client) -> None:
    headers = _auth(client, 93525)
    workout = _assign_today_workout(client, headers, ["deadlift"], prescribed_sets=1)
    started = client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers)
    assert started.status_code == 200, started.text
    target_id = started.json()["exercises"][0]["id"]
    preview = client.post(
        f"/api/v1/workouts/{workout['id']}/adaptations/preview",
        headers=headers,
        json={
            "reason": "unavailable_equipment",
            "target_workout_exercise_id": target_id,
            "available_equipment_ids": ["bodyweight"],
        },
    )
    assert preview.status_code == 409, preview.text
    assert "нет проверенной замены" in preview.json()["detail"]
    with get_session_context() as db:
        assert db.query(WorkoutAdaptation).count() == 0
        event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.action == "workout.adaptation_outcome",
                AuditEvent.resource_id == str(workout["id"]),
                AuditEvent.details["outcome"].as_string() == "no_compatible_alternative",
            )
            .one()
        )
        assert event.details["workout_status"] == "in_progress"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("duration_minutes", 20),
        ("distance_km", 3.5),
        ("average_heart_rate_bpm", 145),
        ("heart_rate_zone", 3),
    ],
)
def test_in_progress_cardio_replacement_rejects_cardio_execution_evidence(
    client,
    field: str,
    value,
) -> None:
    headers = _auth(client, 93520)
    workout = _assign_today_workout(
        client,
        headers,
        ["stationary-bike"],
        prescribed_sets=1,
        prescribed_duration_minutes=30,
    )
    started = client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers)
    assert started.status_code == 200, started.text
    set_id = started.json()["exercises"][0]["sets"][0]["id"]
    logged = client.patch(
        f"/api/v1/workouts/sets/{set_id}",
        headers=headers,
        json={field: value},
    )
    assert logged.status_code == 200, logged.text
    target_id = started.json()["exercises"][0]["id"]
    preview = client.post(
        f"/api/v1/workouts/{workout['id']}/adaptations/preview",
        headers=headers,
        json={
            "reason": "replace_exercise",
            "target_workout_exercise_id": target_id,
            "replacement_exercise_id": 1,
            "available_equipment_ids": ["cardio"],
        },
    )
    assert preview.status_code == 409, preview.text
    assert "фактические данные" in preview.json()["detail"]


def test_in_progress_replacement_rejects_target_started_after_preview(client) -> None:
    headers = _auth(client, 93530)
    workout = _assign_today_workout(client, headers, ["bench-press"], prescribed_sets=1)
    started = client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers)
    assert started.status_code == 200, started.text
    active = started.json()
    replacement = _bench_replacement(client, headers, active)
    payload = _bench_replacement_payload(active, replacement)
    preview = client.post(
        f"/api/v1/workouts/{workout['id']}/adaptations/preview",
        headers=headers,
        json=payload,
    )
    assert preview.status_code == 200, preview.text
    target_set_id = active["exercises"][0]["sets"][0]["id"]
    logged = client.patch(
        f"/api/v1/workouts/sets/{target_set_id}",
        headers=headers,
        json={"actual_reps": 8},
    )
    assert logged.status_code == 200, logged.text

    applied = client.post(
        f"/api/v1/workouts/{workout['id']}/adaptations/apply",
        headers=headers,
        json={**payload, "preview_token": preview.json()["preview_token"]},
    )
    assert applied.status_code == 409, applied.text
    assert "фактические данные" in applied.json()["detail"]
    current = client.get("/api/v1/workouts/today", headers=headers)
    assert current.status_code == 200, current.text
    assert current.json()["exercises"][0]["exercise_id"] == active["exercises"][0]["exercise_id"]
    with get_session_context() as db:
        assert db.query(WorkoutAdaptation).count() == 0
        rejected_event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.action == "workout.adaptation_outcome",
                AuditEvent.resource_id == str(workout["id"]),
                AuditEvent.details["outcome"].as_string() == "rejected_target_started",
            )
            .one()
        )
        assert rejected_event.details["reason"] == "replace_exercise"


def test_replacement_does_not_leak_foreign_workout_and_completed_workout_is_blocked(client) -> None:
    owner_headers = _auth(client, 93531)
    foreign_headers = _auth(client, 93532)
    workout = _assign_today_workout(client, owner_headers, ["bench-press"], prescribed_sets=1)
    replacement = _bench_replacement(client, owner_headers, workout)
    payload = _bench_replacement_payload(workout, replacement)

    foreign_preview = client.post(
        f"/api/v1/workouts/{workout['id']}/adaptations/preview",
        headers=foreign_headers,
        json=payload,
    )
    assert foreign_preview.status_code == 404
    foreign_alternatives = client.get(
        f"/api/v1/workouts/{workout['id']}/exercises/{workout['exercises'][0]['id']}/alternatives",
        params={"available_equipment_ids": ["dumbbell", "bench"]},
        headers=foreign_headers,
    )
    assert foreign_alternatives.status_code == 404

    started = client.post(f"/api/v1/workouts/{workout['id']}/start", headers=owner_headers)
    assert started.status_code == 200, started.text
    target_set_id = started.json()["exercises"][0]["sets"][0]["id"]
    logged = client.patch(
        f"/api/v1/workouts/sets/{target_set_id}",
        headers=owner_headers,
        json={"actual_reps": 8, "actual_weight": 40, "is_completed": True},
    )
    assert logged.status_code == 200, logged.text
    finished = client.post(f"/api/v1/workouts/{workout['id']}/finish", headers=owner_headers)
    assert finished.status_code == 200, finished.text
    completed_preview = client.post(
        f"/api/v1/workouts/{workout['id']}/adaptations/preview",
        headers=owner_headers,
        json=payload,
    )
    assert completed_preview.status_code == 409, completed_preview.text
    assert client.get("/api/v1/workouts/today", headers=owner_headers).status_code == 404


def test_unavailable_equipment_without_curated_alternative_is_controlled(client) -> None:
    headers = _auth(client, 93503)
    workout = _assign_today_workout(client, headers, ["deadlift"], prescribed_sets=1)
    target_id = workout["exercises"][0]["id"]

    preview = client.post(
        f"/api/v1/workouts/{workout['id']}/adaptations/preview",
        headers=headers,
        json={
            "reason": "unavailable_equipment",
            "target_workout_exercise_id": target_id,
            "available_equipment_ids": ["bodyweight"],
        },
    )
    assert preview.status_code == 409
    assert "нет проверенной замены" in preview.json()["detail"]


def test_pain_boundary_never_changes_workout_or_offers_medical_workaround(client) -> None:
    headers = _auth(client, 93504)
    workout = _assign_today_workout(client, headers, ["squat"], prescribed_sets=1)
    assert (
        client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers).status_code == 200
    )

    response = client.post(
        f"/api/v1/workouts/{workout['id']}/adaptations/preview",
        headers=headers,
        json={"reason": "pain_or_injury"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "safety_stop"
    assert data["changes"] == []
    assert data["preview_token"] is None
    assert "не подбирает медицинскую замену" in data["message"]
    with get_session_context() as db:
        stored = db.get(UserWorkout, workout["id"])
        assert stored is not None
        assert stored.status == "in_progress"
        assert db.query(WorkoutAdaptation).count() == 0
        safety_event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.action == "workout.adaptation_outcome",
                AuditEvent.resource_id == str(workout["id"]),
                AuditEvent.details["outcome"].as_string() == "safety_stop",
            )
            .one()
        )
        assert safety_event.details["workout_status"] == "in_progress"
