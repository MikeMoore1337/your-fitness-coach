from __future__ import annotations

import pytest

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.program import UserProgram, UserWorkout, UserWorkoutSet
from fitminiapp_api.models.user import User


def _auth(client, user_id, *, is_coach=False):
    response = client.post(
        "/api/v1/auth/dev-login", json={"telegram_user_id": user_id, "is_coach": is_coach}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _payload(client, headers):
    exercises = client.get("/api/v1/programs/exercises", headers=headers).json()
    return {
        "title": "Тестовая программа",
        "goal": "strength",
        "level": "beginner",
        "assign_after_create": False,
        "days": [
            {
                "title": "День",
                "exercises": [
                    {
                        "exercise_id": exercises[0]["id"],
                        "prescribed_sets": 2,
                        "prescribed_reps": "8",
                        "rest_seconds": 90,
                    }
                ],
            }
        ],
    }


@pytest.mark.parametrize("weeks", [1, 2, 3, 5, 7, 12, 24, 30])
def test_week_cycle_persists_without_materializing_workouts(client, weeks):
    headers = _auth(client, 916000 + weeks)
    payload = _payload(client, headers)
    cycle = {
        "length_weeks": weeks,
        "week_types": ["heavy", "light", "medium"] * weeks,
        "repeat": False,
    }
    cycle["week_types"] = cycle["week_types"][:weeks]
    payload["week_cycle"] = cycle
    response = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["template"]["program_metadata"]["week_cycle"] == {"schema_version": 1, **cycle}
    assert body["assigned_program_id"] is None and body["workouts_created"] == 0
    template_id = body["template"]["id"]
    assert client.get(f"/api/v1/programs/templates/{template_id}", headers=headers).json()[
        "program_metadata"
    ]["week_cycle"] == {"schema_version": 1, **cycle}
    for _ in range(2):
        blocked = client.post(
            f"/api/v1/programs/templates/{template_id}/assign-to-me", headers=headers
        )
        assert blocked.status_code == 403
        assert blocked.json()["detail"] == "Назначение программы с циклом недель пока недоступно"
    with get_session_context() as db:
        user = db.query(User).filter_by(telegram_user_id=916000 + weeks).one()
        assert db.query(UserProgram).filter_by(user_id=user.id).count() == 0


def test_invalid_cycles_and_assignment_are_rejected_without_partial_creation(client):
    headers = _auth(client, 916100)
    payload = _payload(client, headers)
    before = client.get("/api/v1/programs/templates/mine", headers=headers).json()
    for cycle in (
        {"length_weeks": 0, "repeat": True},
        {"length_weeks": True, "repeat": True},
        {"length_weeks": 3, "week_types": ["light", "heavy"], "repeat": True},
        {"length_weeks": 1, "week_types": [], "repeat": False},
        {"length_weeks": 1, "week_types": ["deload"], "repeat": False},
        {"length_weeks": 1, "week_types": ["light"], "repeat": "true"},
        {"length_weeks": 1, "week_types": ["heavy"], "repeat": False, "unknown": 1},
    ):
        response = client.post(
            "/api/v1/programs/templates", headers=headers, json={**payload, "week_cycle": cycle}
        )
        assert response.status_code == 422
    response = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            **payload,
            "assign_after_create": True,
            "week_cycle": {"length_weeks": 1, "week_types": ["light"], "repeat": False},
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Назначение программы с циклом недель пока недоступно"
    assert client.get("/api/v1/programs/templates/mine", headers=headers).json() == before


def test_cycle_without_week_types_is_preserved_and_not_assigned(client):
    headers = _auth(client, 916105)
    payload = _payload(client, headers)
    payload["week_cycle"] = {"length_weeks": 3, "repeat": True}
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    cycle = created.json()["template"]["program_metadata"]["week_cycle"]
    assert cycle == {"schema_version": 1, "length_weeks": 3, "week_types": None, "repeat": True}
    template_id = created.json()["template"]["id"]
    blocked = client.post(f"/api/v1/programs/templates/{template_id}/assign-to-me", headers=headers)
    assert blocked.status_code == 403


def test_one_week_cycle_assigns_16_weeks_with_empty_actual_results(client):
    headers = _auth(client, 916106)
    payload = _payload(client, headers)
    payload["week_cycle"] = {"length_weeks": 1, "repeat": True}
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    template_id = created.json()["template"]["id"]
    assigned = client.post(
        f"/api/v1/programs/templates/{template_id}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 16},
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["user_program_id"]
    with get_session_context() as db:
        assert db.query(UserProgram).filter_by(id=program_id).one().duration_weeks == 16
        workouts = db.query(UserWorkout).filter_by(user_program_id=program_id).all()
        assert workouts
        assert all(row.status == "planned" and row.completed_at is None for row in workouts)
        sets = (
            db.query(UserWorkoutSet)
            .join(UserWorkoutSet.workout_exercise)
            .join(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id)
            .all()
        )
        assert sets and all(
            not row.is_completed and row.actual_weight is None and row.actual_reps is None
            for row in sets
        )


def test_other_user_cannot_read_cycle_and_edit_cannot_replace_it(client):
    owner = _auth(client, 916101)
    other = _auth(client, 916102)
    payload = _payload(client, owner)
    payload["week_cycle"] = {"length_weeks": 2, "week_types": ["heavy", "light"], "repeat": True}
    created = client.post("/api/v1/programs/templates", headers=owner, json=payload)
    assert created.status_code == 200, created.text
    template_id = created.json()["template"]["id"]
    assert (
        client.post(
            "/api/v1/shares/program/preview", headers=owner, json={"template_id": template_id}
        ).status_code
        == 422
    )
    assert client.get(f"/api/v1/programs/templates/{template_id}", headers=other).status_code in (
        403,
        404,
    )
    assert (
        client.patch(
            f"/api/v1/programs/templates/{template_id}", headers=owner, json=payload
        ).status_code
        == 400
    )
    assert client.get(f"/api/v1/programs/templates/{template_id}", headers=owner).json()[
        "program_metadata"
    ]["week_cycle"]["week_types"] == ["heavy", "light"]
    del payload["week_cycle"]
    edited = client.patch(f"/api/v1/programs/templates/{template_id}", headers=owner, json=payload)
    assert edited.status_code == 200, edited.text
    assert edited.json()["program_metadata"]["week_cycle"]["week_types"] == ["heavy", "light"]


def test_legacy_template_remains_assignable_without_week_cycle(client):
    headers = _auth(client, 916104)
    payload = _payload(client, headers)
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    assert created.json()["template"]["program_metadata"] is None
    template_id = created.json()["template"]["id"]
    assigned = client.post(
        f"/api/v1/programs/templates/{template_id}/assign-to-me", headers=headers
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["workouts_created"] > 0


def test_coach_clone_preserves_cycle_and_cannot_assign_it(client):
    headers = _auth(client, 916103, is_coach=True)
    payload = _payload(client, headers)
    payload["week_cycle"] = {"length_weeks": 2, "week_types": ["light", "heavy"], "repeat": True}
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    template_id = created.json()["template"]["id"]
    clone = client.post(f"/api/v1/programs/templates/{template_id}/clone", headers=headers)
    assert clone.status_code == 201, clone.text
    assert clone.json()["program_metadata"]["week_cycle"] == {
        "schema_version": 1,
        "length_weeks": 2,
        "week_types": ["light", "heavy"],
        "repeat": True,
    }
    blocked = client.post(
        f"/api/v1/programs/templates/{clone.json()['id']}/assign-to-me", headers=headers
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Назначение программы с циклом недель пока недоступно"


def test_one_week_cycle_execution_and_rolling_snapshot(client):
    from fitminiapp_api.services.program_versioning import materialize_next_cycle_window

    headers = _auth(client, 916107)
    payload = _payload(client, headers)
    payload["week_cycle"] = {"length_weeks": 1, "repeat": True}
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    template_id = created.json()["template"]["id"]
    assigned = client.post(
        f"/api/v1/programs/templates/{template_id}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 16},
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["user_program_id"]
    with get_session_context() as db:
        workouts = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id)
            .order_by(UserWorkout.week_number)
            .all()
        )
        assert [row.week_number for row in workouts] == [1, 2, 3, 4]
        workout_id = workouts[0].id
    started = client.post(f"/api/v1/workouts/{workout_id}/start", headers=headers)
    assert started.status_code == 200, started.text
    for item in started.json()["exercises"][0]["sets"]:
        saved = client.patch(
            f"/api/v1/workouts/sets/{item['id']}",
            headers=headers,
            json={"actual_reps": 8, "actual_weight": 40, "is_completed": True},
        )
        assert saved.status_code == 200, saved.text
    finished = client.post(f"/api/v1/workouts/{workout_id}/finish", headers=headers)
    assert finished.status_code == 200, finished.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        assert program.is_active
        completed = db.get(UserWorkout, workout_id)
        assert completed.status == "completed"
        original_sets = [
            (row.id, row.actual_reps, row.actual_weight) for row in completed.exercises[0].sets
        ]
        for row in program.workouts:
            if row.status == "planned":
                row.status = "skipped"
        db.flush()
        assert materialize_next_cycle_window(db, program) == 4
        assert materialize_next_cycle_window(db, program) == 0
        assert [
            (row.id, row.actual_reps, row.actual_weight) for row in completed.exercises[0].sets
        ] == original_sets
        generated = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id, UserWorkout.week_number > 4)
            .all()
        )
        assert {row.week_number for row in generated} == {5, 6, 7, 8}
        assert all(
            not item.is_completed and item.actual_weight is None and item.actual_reps is None
            for row in generated
            for exercise in row.exercises
            for item in exercise.sets
        )

    for _ in range(3):
        with get_session_context() as db:
            planned_ids = [
                row.id
                for row in db.query(UserWorkout)
                .filter_by(user_program_id=program_id, status="planned")
                .all()
            ]
        for pending_id in planned_ids:
            skipped = client.post(f"/api/v1/workouts/{pending_id}/skip", headers=headers)
            assert skipped.status_code == 200, skipped.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        assert program.status == "completed" and not program.is_active
        assert db.query(UserWorkout).filter_by(user_program_id=program_id).count() == 16
        completed = db.get(UserWorkout, workout_id)
        assert [
            (row.id, row.actual_reps, row.actual_weight) for row in completed.exercises[0].sets
        ] == original_sets


@pytest.mark.parametrize("restart", [False, True])
def test_cycle_retains_future_window_with_unfinished_workout(client, monkeypatch, restart):
    from datetime import timedelta

    from fitminiapp_api.api.v1 import workouts as routes

    headers = _auth(client, 916108)
    payload = _payload(client, headers)
    payload["week_cycle"] = {"length_weeks": 1, "repeat": True}
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assigned = client.post(
        f"/api/v1/programs/templates/{created.json()['template']['id']}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 16},
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["user_program_id"]
    if restart:
        state = client.get(f"/api/v1/programs/assigned/{program_id}/lifecycle", headers=headers)
        response = client.post(
            f"/api/v1/programs/assigned/{program_id}/lifecycle",
            headers=headers,
            json={
                "action": "restart",
                "expected_revision_number": state.json()["current_revision_number"],
                "reason": "Повторить программу",
            },
        )
        assert response.status_code == 200, response.text
        program_id = response.json()["new_program_id"]
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        assert program.duration_weeks == 16
        start = program.start_date
        original = (
            db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=1).one().id
        )
    monkeypatch.setattr(routes, "recovery_today_for_user", lambda _user: start + timedelta(weeks=4))
    for _ in range(2):
        response = client.get("/api/v1/workouts/today", headers=headers)
        assert response.status_code == 200, response.text
    with get_session_context() as db:
        rows = db.query(UserWorkout).filter_by(user_program_id=program_id).all()
        assert sorted(row.week_number for row in rows) == list(range(1, 9))
        assert db.get(UserWorkout, original).status == "planned"
        assert all(
            not item.is_completed and item.actual_weight is None
            for row in rows
            for exercise in row.exercises
            for item in exercise.sets
        )
