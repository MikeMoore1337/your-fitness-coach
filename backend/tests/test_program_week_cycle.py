from __future__ import annotations

import pytest

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.program import UserProgram, UserWorkout, UserWorkoutSet
from fitminiapp_api.models.user import User


def test_copy_preserves_weekly_prescriptions_and_cycle(client):
    headers = _auth(client, 918255)
    payload = _payload(client, headers)
    payload["duration_weeks"] = 16
    payload["week_cycle"] = {
        "length_weeks": 3,
        "repeat": True,
        "week_types": ["heavy", None, "heavy"],
    }
    item = payload["days"][0]["exercises"][0]
    item["weekly_prescriptions"] = [
        {
            "exercise_id": item["exercise_id"],
            "week_number": week,
            "prescribed_sets": week,
            "prescribed_reps": str(week + 5),
            "rest_seconds": 90,
        }
        for week in (1, 2, 3)
    ]
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    template = created.json()["template"]
    assert [
        week["prescribed_sets"]
        for week in template["days"][0]["exercises"][0]["weekly_prescriptions"]
    ] == [1, 2, 3]
    assigned = client.post(
        f"/api/v1/programs/templates/{template['id']}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 16},
    )
    assert assigned.status_code == 200, assigned.text
    with get_session_context() as db:
        rows = (
            db.query(UserWorkout)
            .filter_by(user_program_id=assigned.json()["user_program_id"])
            .all()
        )
        assert {row.week_number: row.exercises[0].prescribed_sets for row in rows} == {
            1: 1,
            2: 2,
            3: 3,
            4: 1,
        }


def test_template_edit_preserves_and_updates_each_source_week(client):
    headers = _auth(client, 918257)
    payload = _payload(client, headers)
    payload.update(
        duration_weeks=16,
        week_cycle={"length_weeks": 3, "repeat": True, "week_types": ["heavy", None, "light"]},
    )
    exercise = payload["days"][0]["exercises"][0]
    exercise["weekly_prescriptions"] = [
        {
            "exercise_id": exercise["exercise_id"],
            "week_number": week,
            "prescribed_sets": week,
            "prescribed_reps": "8",
            "rest_seconds": 90,
        }
        for week in (1, 2, 3)
    ]
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    template_id = created.json()["template"]["id"]
    exercise["weekly_prescriptions"][1]["prescribed_sets"] = 4
    exercise["weekly_prescriptions"].append(
        {
            "exercise_id": exercise["exercise_id"],
            "week_number": 4,
            "prescribed_sets": 5,
            "prescribed_reps": "8",
            "rest_seconds": 90,
        }
    )
    payload["week_cycle"] = {
        "length_weeks": 4,
        "repeat": True,
        "week_types": ["heavy", None, "light", "heavy"],
    }
    updated = client.patch(
        f"/api/v1/programs/templates/{template_id}", headers=headers, json=payload
    )
    assert updated.status_code == 200, updated.text
    loaded = client.get(f"/api/v1/programs/templates/{template_id}", headers=headers).json()
    assert [
        item["prescribed_sets"]
        for item in loaded["days"][0]["exercises"][0]["weekly_prescriptions"]
    ] == [1, 4, 3, 5]
    assigned = client.post(
        f"/api/v1/programs/templates/{template_id}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 16},
    )
    assert assigned.status_code == 200, assigned.text
    with get_session_context() as db:
        rows = (
            db.query(UserWorkout)
            .filter_by(user_program_id=assigned.json()["user_program_id"])
            .all()
        )
        assert {row.week_number: row.exercises[0].prescribed_sets for row in rows} == {
            1: 1,
            2: 4,
            3: 3,
            4: 5,
        }


def test_scoped_exercise_change_preserves_other_planned_exercises(client):
    from copy import deepcopy

    from fitminiapp_api.services.program_versioning import (
        hydrate_cycle_workout,
        record_program_revision,
    )

    headers = _auth(client, 918258)
    payload = _payload(client, headers)
    payload["week_cycle"] = {"length_weeks": 1, "repeat": True}
    payload["days"][0]["exercises"].append(deepcopy(payload["days"][0]["exercises"][0]))
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assigned = client.post(
        f"/api/v1/programs/templates/{created.json()['template']['id']}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 16},
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["user_program_id"]
    with get_session_context() as db:
        workout = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=4).one()
        first, second = sorted(workout.exercises, key=lambda item: item.sort_order)
        second.prescribed_reps = "15"
        second.source_template_exercise_id = None
        second_set_ids = [item.id for item in second.sets]
        slot, exercise_id = first.source_template_exercise_id, first.exercise_id
        workout_id = workout.id
    changed = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "effective_scope": "future_program",
            "occurrence_weeks": [4],
            "skip_protected": True,
            "day_number": 1,
            "target_template_exercise_id": slot,
            "exercise_id": exercise_id,
            "prescribed_sets": 3,
            "prescribed_reps": "12",
            "rest_seconds": 90,
        },
    )
    assert changed.status_code == 200, changed.text
    with get_session_context() as db:
        first, second = sorted(
            db.get(UserWorkout, workout_id).exercises, key=lambda item: item.sort_order
        )
        assert first.prescribed_reps == "12"
        assert second.prescribed_reps == "15"
        assert [item.id for item in second.sets] == second_set_ids
    changed_type = client.post(
        f"/api/v1/programs/assigned/{program_id}/cycle/week-type",
        headers=headers,
        json={"expected_revision_number": 2, "occurrence_weeks": [3], "week_type": "light"},
    )
    assert changed_type.status_code == 200, changed_type.text
    with get_session_context() as db:
        row = db.get(UserWorkout, workout_id)
        assert hydrate_cycle_workout(db, row)
        first, second = sorted(row.exercises, key=lambda item: item.sort_order)
        assert first.prescribed_reps == "12" and second.prescribed_reps == "15"
        assert [item.id for item in second.sets] == second_set_ids
    disabled = client.post(
        f"/api/v1/programs/assigned/{program_id}/cycle/disable",
        headers=headers,
        json={"expected_revision_number": 3, "effective_from_week": 4},
    )
    assert disabled.status_code == 200, disabled.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        record_program_revision(
            db,
            program,
            actor=db.get(User, program.user_id),
            change_kind="block_updated",
            changed_fields={"operation": "metadata_only"},
        )
        row = db.get(UserWorkout, workout_id)
        assert hydrate_cycle_workout(db, row)
        second = sorted(row.exercises, key=lambda item: item.sort_order)[1]
        assert second.source_template_exercise_id is None and second.prescribed_reps == "15"
        assert [item.id for item in second.sets] == second_set_ids


def test_enable_cycle_on_legacy_assignment_preserves_history_and_expands_future(client):
    from datetime import datetime, time, timedelta

    from fitminiapp_api.models.program import ProgramRevision
    from fitminiapp_api.services.program_versioning import (
        cycle_workout_count,
        materialize_next_cycle_window,
        workout_cycle_week_type,
    )

    headers = _auth(client, 918256)
    created = client.post(
        "/api/v1/programs/templates", headers=headers, json=_payload(client, headers)
    )
    assigned = client.post(
        f"/api/v1/programs/templates/{created.json()['template']['id']}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 8},
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["user_program_id"]
    with get_session_context() as db:
        first = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=1).one()
        first.status = "completed"
        first.started_at = datetime.combine(first.scheduled_date, time(10))
        first.completed_at = datetime.combine(first.scheduled_date, time(11))
        fact = first.exercises[0].sets[0]
        fact.is_completed = True
        fact.actual_weight = 40
        fact.actual_reps = 8
        history = (first.id, fact.id, fact.actual_weight, fact.actual_reps, fact.version)
    path = f"/api/v1/programs/assigned/{program_id}/cycle/enable"
    payload = {
        "expected_revision_number": 1,
        "effective_from_week": 3,
        "duration_weeks": 16,
        "week_cycle": {"length_weeks": 3, "repeat": True, "week_types": ["heavy", None, "light"]},
    }
    preview = client.post(path + "/preview", headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    assert preview.json()["weeks"][-1]["week_number"] == 16
    assert preview.json()["weeks"][-1]["source_cycle_week"] == 2
    result = client.post(path, headers=headers, json=payload)
    assert result.status_code == 200, result.text
    assert client.post(path, headers=headers, json=payload).status_code == 409
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        assert cycle_workout_count(db, program) == 16
        materialize_next_cycle_window(
            db, program, through_date=program.start_date + timedelta(weeks=12)
        )
        revisions = (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program_id)
            .order_by(ProgramRevision.revision_number)
            .all()
        )
        rows = {
            row.week_number: row
            for row in db.query(UserWorkout).filter_by(user_program_id=program_id)
        }
        assert rows[2].source_cycle_week is None
        assert workout_cycle_week_type(db, rows[3], revisions) == ("heavy", True)
        assert workout_cycle_week_type(db, rows[4], revisions) == (None, True)
        assert rows[16].source_cycle_week == 2
        fact = rows[1].exercises[0].sets[0]
        assert (rows[1].id, fact.id, fact.actual_weight, fact.actual_reps, fact.version) == history


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
    assigned = client.post(
        f"/api/v1/programs/templates/{template_id}/assign-to-me", headers=headers
    )
    assert assigned.status_code == 200, assigned.text
    repeated = client.post(
        f"/api/v1/programs/templates/{template_id}/assign-to-me", headers=headers
    )
    assert repeated.status_code == 409
    with get_session_context() as db:
        user = db.query(User).filter_by(telegram_user_id=916000 + weeks).one()
        assert db.query(UserProgram).filter_by(user_id=user.id).count() == 1


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
            "duration_weeks": 2,
            "week_cycle": {"length_weeks": 1, "week_types": ["light"], "repeat": False},
        },
    )
    assert response.status_code == 400
    assert (
        response.json()["detail"] == "Длительность программы превышает длину цикла без повторения"
    )
    assert client.get("/api/v1/programs/templates/mine", headers=headers).json() == before


def test_cycle_without_week_types_is_preserved_and_assigned(client):
    headers = _auth(client, 916105)
    payload = _payload(client, headers)
    payload["week_cycle"] = {"length_weeks": 3, "repeat": True}
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    cycle = created.json()["template"]["program_metadata"]["week_cycle"]
    assert cycle == {"schema_version": 1, "length_weeks": 3, "week_types": None, "repeat": True}
    template_id = created.json()["template"]["id"]
    blocked = client.post(f"/api/v1/programs/templates/{template_id}/assign-to-me", headers=headers)
    assert blocked.status_code == 200, blocked.text


def test_mixed_week_types_roundtrip_and_resolve_without_a_default(client):
    from fitminiapp_api.models.program import ProgramRevision
    from fitminiapp_api.services.program_versioning import workout_cycle_week_type

    headers = _auth(client, 918001)
    payload = _payload(client, headers)
    payload["week_cycle"] = {
        "length_weeks": 3,
        "week_types": ["heavy", None, "heavy"],
        "repeat": True,
    }
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    template_id = created.json()["template"]["id"]
    assert created.json()["template"]["program_metadata"]["week_cycle"]["week_types"] == [
        "heavy",
        None,
        "heavy",
    ]
    assigned = client.post(
        f"/api/v1/programs/templates/{template_id}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 4},
    )
    assert assigned.status_code == 200, assigned.text
    with get_session_context() as db:
        program_id = assigned.json()["user_program_id"]
        workouts = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id)
            .order_by(UserWorkout.week_number)
            .all()
        )
        revisions = (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program_id)
            .order_by(ProgramRevision.revision_number)
            .all()
        )
        assert [row.source_cycle_week for row in workouts] == [1, 2, 3, 1]
        assert [workout_cycle_week_type(db, row, revisions) for row in workouts] == [
            ("heavy", True),
            (None, True),
            ("heavy", True),
            ("heavy", True),
        ]


def test_unassigned_template_can_enable_change_and_disable_cycle(client):
    headers = _auth(client, 918002)
    other = _auth(client, 918003)
    payload = _payload(client, headers)
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    template_id = created.json()["template"]["id"]
    payload["week_cycle"] = {
        "length_weeks": 3,
        "week_types": [None, "heavy", "heavy"],
        "repeat": True,
    }
    payload["duration_weeks"] = 16
    denied = client.patch(f"/api/v1/programs/templates/{template_id}", headers=other, json=payload)
    assert denied.status_code in (403, 404)
    edited = client.patch(
        f"/api/v1/programs/templates/{template_id}", headers=headers, json=payload
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["program_metadata"]["week_cycle"]["week_types"] == [None, "heavy", "heavy"]
    assert edited.json()["default_duration_weeks"] == 16
    del payload["week_cycle"]
    preserved = client.patch(
        f"/api/v1/programs/templates/{template_id}", headers=headers, json=payload
    )
    assert preserved.status_code == 200, preserved.text
    assert preserved.json()["program_metadata"]["week_cycle"]["length_weeks"] == 3
    payload["week_cycle"] = None
    disabled = client.patch(
        f"/api/v1/programs/templates/{template_id}", headers=headers, json=payload
    )
    assert disabled.status_code == 200, disabled.text
    assert not (disabled.json()["program_metadata"] or {}).get("week_cycle")


@pytest.mark.parametrize(("length", "duration"), [(1, 16), (3, 16), (7, 16), (3, 30)])
def test_cycle_template_persists_duration_and_expands_assignment(client, length, duration):
    from fitminiapp_api.services.program_versioning import _cycle_workout_plans

    headers = _auth(client, 918010 + length + duration)
    payload = _payload(client, headers)
    payload["duration_weeks"] = duration
    payload["week_cycle"] = {"length_weeks": length, "week_types": None, "repeat": True}
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    template = created.json()["template"]
    assert template["default_duration_weeks"] == duration
    reopened = client.get(f"/api/v1/programs/templates/{template['id']}", headers=headers)
    assert reopened.json()["default_duration_weeks"] == duration
    assigned = client.post(
        f"/api/v1/programs/templates/{template['id']}/assign-to-me",
        headers=headers,
        json={"duration_weeks": duration},
    )
    assert assigned.status_code == 200, assigned.text
    with get_session_context() as db:
        program = db.get(UserProgram, assigned.json()["user_program_id"])
        final = _cycle_workout_plans(db, program, duration)
        assert len(final) == 1
        assert final[0]["source_cycle_week"] == (duration - 1) % length + 1
        assert final[0]["cycle_iteration"] == (duration - 1) // length + 1


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


def test_other_user_cannot_read_or_edit_cycle_and_owner_can_preserve_it(client):
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
        == 200
    )
    assert client.get(f"/api/v1/programs/templates/{template_id}", headers=other).status_code in (
        403,
        404,
    )
    assert client.patch(
        f"/api/v1/programs/templates/{template_id}", headers=other, json=payload
    ).status_code in (403, 404)
    assert (
        client.patch(
            f"/api/v1/programs/templates/{template_id}", headers=owner, json=payload
        ).status_code
        == 200
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


def test_coach_clone_preserves_cycle_and_can_assign_it(client):
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
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["user_program_id"] > 0


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
@pytest.mark.parametrize("weeks_absent", [4, 8])
@pytest.mark.parametrize("schedule_route", ["today", "week", "schedule"])
def test_cycle_retains_future_window_with_unfinished_workout(
    client, monkeypatch, restart, weeks_absent, schedule_route
):
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
    monkeypatch.setattr(
        routes, "recovery_today_for_user", lambda _user: start + timedelta(weeks=weeks_absent)
    )
    for _ in range(2):
        response = client.get(f"/api/v1/workouts/{schedule_route}", headers=headers)
        assert response.status_code == 200, response.text
    with get_session_context() as db:
        rows = db.query(UserWorkout).filter_by(user_program_id=program_id).all()
        assert sorted(row.week_number for row in rows) == list(range(1, 5)) + list(
            range(
                weeks_absent + 1,
                weeks_absent + {"today": 4, "week": 1, "schedule": 8}[schedule_route] + 1,
            )
        )
        assert db.get(UserWorkout, original).status == "planned"
        assert all(
            not item.is_completed and item.actual_weight is None
            for row in rows
            for exercise in row.exercises
            for item in exercise.sets
        )


@pytest.mark.parametrize("restart_after_edit", [False, True])
@pytest.mark.parametrize("edit_week", [3, 10])
def test_future_week_ten_override_is_materialized(client, restart_after_edit, edit_week):
    from datetime import timedelta

    from fitminiapp_api.services.program_versioning import materialize_next_cycle_window

    headers = _auth(client, 916109)
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
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        source = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=1).one()
        exercise_id = source.exercises[0].exercise_id
        slot = source.exercises[0].source_template_exercise_id
        version = program.current_revision_number
    edited = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": version,
            "effective_scope": "future_program",
            "occurrence_weeks": [edit_week],
            "day_number": 1,
            "target_template_exercise_id": slot,
            "exercise_id": exercise_id,
            "prescribed_sets": 3,
            "prescribed_reps": "12",
            "rest_seconds": 90,
        },
    )
    assert edited.status_code == 200, edited.text
    if restart_after_edit:
        restarted = client.post(
            f"/api/v1/programs/assigned/{program_id}/lifecycle",
            headers=headers,
            json={
                "action": "restart",
                "expected_revision_number": edited.json()["current_revision_number"],
                "reason": "Повторить изменённый план",
            },
        )
        assert restarted.status_code == 200, restarted.text
        program_id = restarted.json()["new_program_id"]
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        for _ in range(2):
            materialize_next_cycle_window(
                db, program, through_date=program.start_date + timedelta(weeks=8)
            )
        rows = {
            row.week_number: row
            for row in db.query(UserWorkout).filter_by(user_program_id=program_id).all()
        }
        assert rows[edit_week].exercises[0].prescribed_sets == 3
        assert rows[edit_week].exercises[0].prescribed_reps == "12"
        assert len(rows[edit_week].exercises[0].sets) == 3
        assert rows[9].exercises[0].prescribed_sets == 2
        assert rows[1].exercises[0].prescribed_sets == 2


@pytest.mark.parametrize("cycle_length", [3, 7])
def test_cycle_maps_week_sixteen_to_source_prescription(client, cycle_length):
    from datetime import timedelta

    from fitminiapp_api.models.program import (
        ProgramTemplate,
        ProgramTemplateExerciseWeekPrescription,
    )
    from fitminiapp_api.services.program_versioning import materialize_next_cycle_window

    headers = _auth(client, 916110)
    payload = _payload(client, headers)
    payload["week_cycle"] = {"length_weeks": cycle_length, "repeat": True}
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    template_id = created.json()["template"]["id"]
    with get_session_context() as db:
        slot = db.get(ProgramTemplate, template_id).days[0].exercises[0]
        for week in range(1, cycle_length + 1):
            db.add(
                ProgramTemplateExerciseWeekPrescription(
                    template_exercise_id=slot.id,
                    exercise_id=slot.exercise_id,
                    week_number=week,
                    prescribed_sets=week,
                    prescribed_reps=str(week * 3),
                    rest_seconds=90,
                )
            )
    assigned = client.post(
        f"/api/v1/programs/templates/{template_id}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 16},
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["user_program_id"]
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        initial = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id)
            .order_by(UserWorkout.week_number)
            .all()
        )
        assert [row.exercises[0].prescribed_sets for row in initial] == [
            (week % cycle_length) + 1 for week in range(4)
        ]
        assert (
            materialize_next_cycle_window(
                db, program, through_date=program.start_date + timedelta(weeks=15)
            )
            == 1
        )
        last = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=16).one()
        assert last.exercises[0].prescribed_sets == ((16 - 1) % cycle_length) + 1
        assert last.exercises[0].prescribed_reps == str((((16 - 1) % cycle_length) + 1) * 3)
        assert (
            last.exercises[0].source_weekly_prescription_id
            == initial[(16 - 1) % cycle_length].exercises[0].source_weekly_prescription_id
        )


def test_oversized_logical_cycle_is_rejected_before_snapshot_generation(client):
    headers = _auth(client, 916111)
    payload = _payload(client, headers)
    payload["week_cycle"] = {"length_weeks": 1000000000, "repeat": True}
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    response = client.post(
        f"/api/v1/programs/templates/{created.json()['template']['id']}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 16},
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == "Размер плана превышает допустимый объём одного назначения"
    with get_session_context() as db:
        user = db.query(User).filter_by(telegram_user_id=916111).one()
        assert db.query(UserProgram).filter_by(user_id=user.id).count() == 0
