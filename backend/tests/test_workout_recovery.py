from __future__ import annotations

from datetime import timedelta

from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.program import UserProgram, UserWorkout


def _auth(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": False},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_one_day_program(client, headers: dict[str, str]) -> int:
    exercises = client.get("/api/v1/programs/exercises", headers=headers)
    assert exercises.status_code == 200, exercises.text
    exercise = next(item for item in exercises.json() if item["metric_type"] == "strength")
    created = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Recovery contract",
            "goal": "maintenance",
            "level": "beginner",
            "mode": "self",
            "assign_after_create": True,
            "start_date": today_msk().isoformat(),
            "days": [
                {
                    "title": "День 1",
                    "exercises": [
                        {
                            "exercise_id": exercise["id"],
                            "prescribed_sets": 2,
                            "prescribed_reps": "8-10",
                            "rest_seconds": 90,
                        }
                    ],
                }
            ],
        },
    )
    assert created.status_code == 200, created.text
    return created.json()["assigned_program_id"]


def test_recovery_preview_is_non_mutating_and_apply_records_lineage(client) -> None:
    headers = _auth(client, 519_001)
    program_id = _create_one_day_program(client, headers)
    missed_date = today_msk() - timedelta(days=1)

    with get_session_context() as db:
        workout = db.query(UserWorkout).filter(UserWorkout.user_program_id == program_id).one()
        workout.scheduled_date = missed_date
        db.commit()
        workout_id = workout.id
        expected_time = workout.scheduled_time

    state = client.get("/api/v1/workouts/recovery", headers=headers)
    assert state.status_code == 200, state.text
    assert state.json()["status"] == "missed"
    assert state.json()["missed_workouts"] == [
        {
            "id": workout_id,
            "scheduled_date": missed_date.isoformat(),
            "scheduled_time": expected_time.isoformat() if expected_time else None,
            "title": "День 1",
            "status": "missed",
            "day_number": 1,
            "week_number": 1,
        }
    ]

    payload = {
        "action": "move",
        "expected_scheduled_date": missed_date.isoformat(),
        "expected_scheduled_time": expected_time.isoformat() if expected_time else None,
        "scheduled_date": (today_msk() + timedelta(days=1)).isoformat(),
        "scheduled_time": "18:30",
    }
    preview = client.post(
        f"/api/v1/workouts/{workout_id}/recovery/preview",
        headers=headers,
        json=payload,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["status"] == "preview"
    assert preview.json()["changes"][0]["kind"] == "moved"
    assert preview.json()["preview_token"]

    with get_session_context() as db:
        unchanged = db.get(UserWorkout, workout_id)
        assert unchanged is not None
        assert unchanged.scheduled_date == missed_date
        assert unchanged.scheduled_time == expected_time

    applied = client.post(
        f"/api/v1/workouts/{workout_id}/recovery/apply",
        headers=headers,
        json={**payload, "preview_token": preview.json()["preview_token"]},
    )
    assert applied.status_code == 200, applied.text
    assert (
        applied.json()["workout"]["scheduled_date"] == (today_msk() + timedelta(days=1)).isoformat()
    )
    assert applied.json()["workout"]["scheduled_time"] == "18:30:00"

    with get_session_context() as db:
        updated = db.get(UserWorkout, workout_id)
        assert updated is not None
        assert updated.scheduled_date == today_msk() + timedelta(days=1)
        assert updated.scheduled_time is not None
        assert updated.scheduled_time.isoformat() == "18:30:00"

    revisions = client.get(f"/api/v1/programs/assigned/{program_id}/revisions", headers=headers)
    assert revisions.status_code == 200, revisions.text
    assert revisions.json()[0]["change_kind"] == "plan_updated"
    assert revisions.json()[0]["changed_fields"]["operation"] == "workout_recovery_move"


def test_recovery_apply_fails_closed_when_schedule_is_stale(client) -> None:
    headers = _auth(client, 519_002)
    program_id = _create_one_day_program(client, headers)
    missed_date = today_msk() - timedelta(days=1)
    with get_session_context() as db:
        workout = db.query(UserWorkout).filter(UserWorkout.user_program_id == program_id).one()
        workout.scheduled_date = missed_date
        db.commit()
        workout_id = workout.id

    payload = {
        "action": "move",
        "expected_scheduled_date": missed_date.isoformat(),
        "expected_scheduled_time": None,
        "scheduled_date": (today_msk() + timedelta(days=1)).isoformat(),
        "scheduled_time": None,
    }
    preview = client.post(
        f"/api/v1/workouts/{workout_id}/recovery/preview",
        headers=headers,
        json=payload,
    )
    assert preview.status_code == 200, preview.text

    with get_session_context() as db:
        db.get(UserWorkout, workout_id).scheduled_date = today_msk()
        db.commit()

    applied = client.post(
        f"/api/v1/workouts/{workout_id}/recovery/apply",
        headers=headers,
        json={**payload, "preview_token": preview.json()["preview_token"]},
    )
    assert applied.status_code == 409, applied.text
    assert "изменилось" in applied.json()["detail"].lower()


def test_recovery_skip_requires_confirmation_and_closes_finished_program(client) -> None:
    headers = _auth(client, 519_005)
    program_id = _create_one_day_program(client, headers)
    missed_date = today_msk() - timedelta(days=1)
    with get_session_context() as db:
        workout = db.query(UserWorkout).filter(UserWorkout.user_program_id == program_id).one()
        workout.scheduled_date = missed_date
        db.commit()
        workout_id = workout.id

    payload = {
        "action": "skip",
        "expected_scheduled_date": missed_date.isoformat(),
        "expected_scheduled_time": None,
    }
    preview = client.post(
        f"/api/v1/workouts/{workout_id}/recovery/preview",
        headers=headers,
        json=payload,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["preview_token"]
    with get_session_context() as db:
        assert db.get(UserWorkout, workout_id).status == "planned"

    applied = client.post(
        f"/api/v1/workouts/{workout_id}/recovery/apply",
        headers=headers,
        json={**payload, "preview_token": preview.json()["preview_token"]},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["workout"]["status"] == "skipped"
    with get_session_context() as db:
        stored = db.get(UserWorkout, workout_id)
        assert stored is not None
        assert stored.status == "skipped"

    state = client.get("/api/v1/workouts/recovery", headers=headers)
    assert state.status_code == 200, state.text
    assert state.json()["status"] == "no_active_program"


def test_recovery_surfaces_paused_program_for_existing_resume_flow(client) -> None:
    headers = _auth(client, 519_006)
    program_id = _create_one_day_program(client, headers)

    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        assert program is not None
        program.status = "paused"
        program.is_active = False
        db.commit()

    state = client.get("/api/v1/workouts/recovery", headers=headers)
    assert state.status_code == 200, state.text
    assert state.json()["status"] == "paused"
    assert state.json()["paused_program_id"] == program_id


def test_recovery_is_owner_scoped(client) -> None:
    owner_headers = _auth(client, 519_003)
    other_headers = _auth(client, 519_004)
    program_id = _create_one_day_program(client, owner_headers)
    with get_session_context() as db:
        workout = db.query(UserWorkout).filter(UserWorkout.user_program_id == program_id).one()
        workout.scheduled_date = today_msk() - timedelta(days=1)
        db.commit()
        workout_id = workout.id

    response = client.post(
        f"/api/v1/workouts/{workout_id}/recovery/preview",
        headers=other_headers,
        json={
            "action": "skip",
            "expected_scheduled_date": (today_msk() - timedelta(days=1)).isoformat(),
            "expected_scheduled_time": None,
        },
    )
    assert response.status_code == 404, response.text
