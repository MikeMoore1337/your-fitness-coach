from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError
from test_offline_workout_sync import _auth, _create_started_workout

from fitminiapp_api.ai_coach.personal_tools import _get_workout_context_tool
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.program import UserWorkoutSet, UserWorkoutSetSide
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.services.account_export import build_account_export
from fitminiapp_api.services.account_exports import _workout_rows
from fitminiapp_api.services.accounts import delete_user_cascade
from fitminiapp_api.services.analytics import build_workout_timeline


def test_side_contract_marker_is_rejected_by_legacy_boolean_schema():
    with pytest.raises(ValidationError):
        TypeAdapter(bool).validate_python("sides-v1")


def test_side_facts_are_atomic_versioned_and_reject_legacy_overwrite(client):
    owner = _auth(client, 93_810)
    workout, logged = _create_started_workout(client, owner)
    endpoint = f"/api/v1/workouts/sets/{logged['id']}"
    left = {
        "actual_reps": 10,
        "actual_weight": 18,
        "rir": "2",
        "reached_failure": False,
        "is_completed": True,
    }
    right = {
        "actual_reps": 8,
        "actual_weight": 16,
        "rir": "0",
        "reached_failure": True,
        "is_completed": True,
    }
    partial = {
        "execution_mode": "per_side",
        "sides": {"left": left, "right": None},
        "is_completed": "sides-v1",
        "side_is_completed": False,
        "expected_version": 1,
        "mutation_id": "side-partial-0000000001",
    }
    saved = client.patch(endpoint, headers=owner, json=partial)
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 2
    assert saved.json()["is_completed"] is False
    assert saved.json()["sides"]["left"] == left
    assert saved.json()["sides"]["right"] is None
    assert saved.json()["actual_reps"] is None
    assert saved.json()["actual_weight"] is None

    reread = client.get("/api/v1/workouts/today", headers=owner).json()["exercises"][0]["sets"][0]
    assert reread["sides"] == saved.json()["sides"]
    legacy = client.patch(endpoint, headers=owner, json={"actual_reps": 12, "is_completed": True})
    assert legacy.status_code == 409
    assert legacy.json()["detail"]["code"] == "workout_set_side_aware_required"

    incomplete = client.patch(
        endpoint,
        headers=owner,
        json={
            **partial,
            "side_is_completed": True,
            "expected_version": 2,
            "mutation_id": "side-incomplete-0000002",
        },
    )
    assert incomplete.status_code == 422
    finished_payload = {
        **partial,
        "sides": {"left": left, "right": right},
        "side_is_completed": True,
        "expected_version": 2,
        "mutation_id": "side-completed-00000003",
    }
    finished = client.patch(endpoint, headers=owner, json=finished_payload)
    assert finished.status_code == 200, finished.text
    assert finished.json()["version"] == 3
    assert finished.json()["is_completed"] is True
    assert finished.json()["sides"] == {"left": left, "right": right}
    clear_side = dict(finished_payload)
    clear_side.update(
        {
            "sides": {"left": left, "right": None},
            "expected_version": 3,
            "mutation_id": "side-clear-completed-001",
        }
    )
    assert client.patch(endpoint, headers=owner, json=clear_side).status_code == 422
    assert client.patch(endpoint, headers=owner, json=finished_payload).json() == finished.json()
    reused = client.patch(
        endpoint,
        headers=owner,
        json={**finished_payload, "sides": {"left": left, "right": None}},
    )
    assert reused.status_code == 409
    assert reused.json()["detail"]["code"] == "workout_set_idempotency_conflict"
    stale = client.patch(
        endpoint,
        headers=owner,
        json={**partial, "mutation_id": "side-stale-00000000004"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["current"]["sides"] == finished.json()["sides"]

    other = _auth(client, 93_811)
    assert client.patch(endpoint, headers=other, json=finished_payload).status_code == 404
    assert client.post(f"/api/v1/workouts/{workout['id']}/finish", headers=owner).status_code == 200


def test_alternating_remembers_only_explicit_first_side(client):
    owner = _auth(client, 93_812)
    _, logged = _create_started_workout(client, owner)
    payload = {
        "execution_mode": "alternating",
        "first_side": "right",
        "sides": {
            "left": {"actual_reps": 10, "actual_weight": 18, "is_completed": True},
            "right": {"actual_reps": 8, "actual_weight": 16, "is_completed": True},
        },
        "is_completed": "sides-v1",
        "side_is_completed": True,
        "expected_version": 1,
        "mutation_id": "side-alternating-0000001",
    }
    saved = client.patch(f"/api/v1/workouts/sets/{logged['id']}", headers=owner, json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["first_side"] == "right"
    assert saved.json()["sides"]["left"]["actual_reps"] == 10
    assert saved.json()["sides"]["right"]["actual_reps"] == 8


def test_completed_sides_count_as_one_set_and_keep_independent_loads(client):
    owner = _auth(client, 93_813)
    workout, logged = _create_started_workout(client, owner)
    saved = client.patch(
        f"/api/v1/workouts/sets/{logged['id']}",
        headers=owner,
        json={
            "execution_mode": "per_side",
            "sides": {
                "left": {"actual_reps": 10, "actual_weight": 18, "rir": "2", "is_completed": True},
                "right": {
                    "actual_reps": 8,
                    "actual_weight": 16,
                    "rir": "0",
                    "reached_failure": True,
                    "is_completed": True,
                },
            },
            "is_completed": "sides-v1",
            "side_is_completed": True,
            "expected_version": 1,
            "mutation_id": "side-analytics-0000001",
        },
    )
    assert saved.status_code == 200, saved.text
    finished = client.post(f"/api/v1/workouts/{workout['id']}/finish", headers=owner)
    assert finished.status_code == 200, finished.text
    summary = finished.json()["completion_summary"]
    assert summary["completed_sets"] == 1
    assert summary["reps_total"] == 18
    assert summary["reps_recorded_sets"] == 1
    analytics = client.get(
        "/api/v1/workouts/progress/training-analytics?period_days=7", headers=owner
    )
    assert analytics.status_code == 200, analytics.text
    payload = analytics.json()
    assert payload["completed_set_count"] == 1
    assert payload["reps_total"] == 18
    assert payload["external_load_volume_kg"] == 308
    exercise = payload["exercises"][0]
    assert exercise["max_external_load_kg"] is None
    assert exercise["best_set_volume_kg"] is None
    previous_set = exercise["sessions"][0]["sets"][0]
    assert previous_set["sides"]["left"]["actual_weight"] == 18
    assert previous_set["sides"]["right"]["actual_weight"] == 16
    assert payload["rir"]["mixed_side_set_count"] == 1
    assert payload["rir"]["recorded_set_count"] == 1
    assert payload["rir"]["missing_set_count"] == 0
    workout_history = client.get("/api/v1/workouts/history", headers=owner).json()[0]
    assert workout_history["volume_kg"] == 308
    side_set = workout_history["exercises"][0]["side_sets"][0]
    assert side_set["sides"]["left"]["actual_weight"] == 18
    assert side_set["sides"]["right"]["reached_failure"] is True
    assert client.get("/api/v1/workouts/history/summary", headers=owner).json()["volume_kg"] == 308
    period = client.get("/api/v1/workouts/progress/summary?period_days=7", headers=owner).json()
    assert period["training"]["volume_kg"] == 308
    assert period["training"]["new_personal_records"] == 0
    with get_session_context() as db:
        db.add(
            UserWorkoutSet(
                workout_exercise_id=workout["exercises"][0]["id"], set_number=2, is_completed=False
            )
        )
    progress = client.get("/api/v1/workouts/progress", headers=owner).json()
    assert progress["weekly_volume"][-1]["volume_kg"] == 308
    assert progress["personal_records"] == []

    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 93_813).one()
        exported = build_account_export(db, user)
        timeline_set = build_workout_timeline(db, user)[0]["exercises"][0]["sets"][0]
        assert timeline_set["sides"]["left"]["actual_weight"] == 18
        assert timeline_set["sides"]["right"]["actual_weight"] == 16
        context = _get_workout_context_tool(db, user, focus="recent")
        ai_set = context.facts["nearby_workouts"][0]["exercises"][0]["sets"][0]
        assert ai_set["sides"]["left"]["actual_weight"] == 18
        assert ai_set["sides"]["right"]["reached_failure"] is True
    row = next(item for item in _workout_rows(exported) if item["set_id"] == logged["id"])
    assert row["execution_mode"] == "per_side"
    assert row["left_actual_weight"] == 18
    assert row["right_actual_weight"] == 16
    assert row["left_rir"] == "2"
    assert row["right_reached_failure"] is True
    history = client.get(
        f"/api/v1/programs/exercises/{workout['exercises'][0]['exercise_id']}/history",
        headers=owner,
    )
    assert history.status_code == 200, history.text
    assert history.json()["best_authoritative_load"] is None
    assert history.json()["rep_prs"] == []
    side_records = {item["side"]: item for item in history.json()["side_records"]}
    assert side_records["left"]["best_authoritative_load"]["value_kg"] == 18
    assert side_records["right"]["best_authoritative_load"]["value_kg"] == 16
    assert side_records["left"]["rep_prs"][0]["best_reps"] == 10
    assert side_records["right"]["rep_prs"][0]["best_reps"] == 8
    history_set = history.json()["recent_sessions"][0]["sets"][0]
    assert history_set["sides"]["left"]["actual_weight"] == 18
    assert history_set["sides"]["right"]["actual_weight"] == 16
    assert history_set["pr_eligible"] is False
    coach_login = client.post(
        "/api/v1/auth/dev-login", json={"telegram_user_id": 93820, "is_coach": True}
    )
    outsider_login = client.post(
        "/api/v1/auth/dev-login", json={"telegram_user_id": 93821, "is_coach": True}
    )
    coach = {"Authorization": f"Bearer {coach_login.json()['access_token']}"}
    outsider = {"Authorization": f"Bearer {outsider_login.json()['access_token']}"}
    with get_session_context() as db:
        athlete_id = db.query(User.id).filter_by(telegram_user_id=93813).scalar()
        coach_id = db.query(User.id).filter_by(telegram_user_id=93820).scalar()
        db.add(CoachClient(coach_user_id=coach_id, client_user_id=athlete_id))
    timeline = client.get(f"/api/v1/coach/clients/{athlete_id}/workouts", headers=coach)
    assert timeline.status_code == 200, timeline.text
    assert timeline.json()[0]["exercises"][0]["sets"][0]["sides"]["right"]["actual_weight"] == 16
    assert (
        client.get(f"/api/v1/coach/clients/{athlete_id}/workouts", headers=outsider).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/workouts/sets/{logged['id']}",
            headers=coach,
            json={
                "actual_reps": 1,
                "expected_version": saved.json()["version"],
                "mutation_id": "coach-other-user-832",
            },
        ).status_code
        == 404
    )


def test_partial_side_is_visible_without_completed_set_statistics(client):
    owner = _auth(client, 93_814)
    workout, logged = _create_started_workout(client, owner)
    result = client.patch(
        f"/api/v1/workouts/sets/{logged['id']}",
        headers=owner,
        json={
            "execution_mode": "per_side",
            "sides": {
                "left": {"actual_reps": 10, "actual_weight": 18, "is_completed": True},
                "right": None,
            },
            "is_completed": "sides-v1",
            "side_is_completed": False,
            "expected_version": 1,
            "mutation_id": "side-partial-history-001",
        },
    )
    assert result.status_code == 200, result.text
    with get_session_context() as db:
        db.add(
            UserWorkoutSet(
                workout_exercise_id=workout["exercises"][0]["id"],
                set_number=2,
                actual_reps=5,
                actual_weight=4,
                is_completed=True,
            )
        )
        db.commit()
    finished = client.post(
        f"/api/v1/workouts/{workout['id']}/finish", headers=owner, json={"confirm_incomplete": True}
    )
    assert finished.status_code == 200, finished.text
    assert finished.json()["completion_summary"]["completed_sets"] == 1
    assert finished.json()["completion_summary"]["reps_total"] == 5
    history = client.get(
        f"/api/v1/programs/exercises/{workout['exercises'][0]['exercise_id']}/history",
        headers=owner,
    )
    assert history.status_code == 200, history.text
    session = history.json()["recent_sessions"][0]
    assert session["completed_set_count"] == 1
    assert session["reps_total"] == 5
    assert session["sets"][0]["is_completed"] is False
    assert session["sets"][0]["sides"]["left"]["actual_weight"] == 18
    assert session["sets"][0]["sides"]["right"] is None
    history = client.get("/api/v1/workouts/history", headers=owner).json()[0]
    assert history["exercises"][0]["side_sets"][0]["is_completed"] is False


def test_missing_side_load_is_not_reported_as_complete_volume(client):
    owner = _auth(client, 93_815)
    workout, logged = _create_started_workout(client, owner)
    saved = client.patch(
        f"/api/v1/workouts/sets/{logged['id']}",
        headers=owner,
        json={
            "execution_mode": "per_side",
            "sides": {
                "left": {"actual_reps": 10, "actual_weight": 18, "is_completed": True},
                "right": {"actual_reps": 8, "actual_weight": None, "is_completed": True},
            },
            "is_completed": "sides-v1",
            "side_is_completed": True,
            "expected_version": 1,
            "mutation_id": "missing-side-load-0001",
        },
    )
    assert saved.status_code == 200, saved.text
    assert client.post(f"/api/v1/workouts/{workout['id']}/finish", headers=owner).status_code == 200
    history = client.get("/api/v1/workouts/history", headers=owner).json()[0]
    assert history["volume_incomplete"] is True
    summary = client.get("/api/v1/workouts/history/summary", headers=owner).json()
    assert summary["volume_incomplete"] is True
    period = client.get("/api/v1/workouts/progress/summary?period_days=7", headers=owner).json()
    assert period["training"]["volume_incomplete"] is True
    assert period["training"]["new_personal_records"] == 0
    progress = client.get("/api/v1/workouts/progress", headers=owner).json()
    assert progress["weekly_volume"][-1]["volume_incomplete"] is True
    checkin = client.get("/api/v1/check-ins/weekly/current", headers=owner).json()
    assert checkin["summary"]["progression"]["training_volume_kg"] is None
    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 93_815).one()
        assert build_workout_timeline(db, user)[0]["volume_incomplete"] is True


def test_account_deletion_removes_side_facts_for_owner_only(client):
    first = _auth(client, 93830)
    second = _auth(client, 93831)
    for owner in (first, second):
        _, workout_set = _create_started_workout(client, owner)
        response = client.patch(
            f"/api/v1/workouts/sets/{workout_set['id']}",
            headers=owner,
            json={
                "execution_mode": "per_side",
                "sides": {
                    "left": {"actual_reps": 10, "actual_weight": 18, "is_completed": True},
                    "right": None,
                },
                "is_completed": "sides-v1",
                "side_is_completed": False,
                "expected_version": 1,
                "mutation_id": "account-delete-sides-832",
            },
        )
        assert response.status_code == 200, response.text
    with get_session_context() as db:
        owner = db.query(User).filter_by(telegram_user_id=93830).one()
        assert db.query(UserWorkoutSetSide).count() == 2
        delete_user_cascade(db, owner)
        db.flush()
        assert db.query(UserWorkoutSetSide).count() == 1
