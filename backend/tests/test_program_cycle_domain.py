from __future__ import annotations

from datetime import date, timedelta

import pytest
from test_program_week_cycle import _auth, _payload

from fitminiapp_api.api.v1 import workouts as routes
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.program import (
    ProgramRevision,
    ProgramTemplate,
    ProgramTemplateExerciseWeekPrescription,
    UserProgram,
    UserWorkout,
    UserWorkoutSet,
)
from fitminiapp_api.services import program_versioning, programs

TODAY = date(2026, 10, 5)


@pytest.fixture(autouse=True)
def fixed_calendar(monkeypatch):
    monkeypatch.setattr(programs, "today_for_user", lambda _user: TODAY)
    monkeypatch.setattr(program_versioning, "today_for_user", lambda _user: TODAY)
    monkeypatch.setattr(routes, "recovery_today_for_user", lambda _user: TODAY)


def assigned_cycle(client, *, k=3, n=16, days=1, with_second=False):
    headers = _auth(client, 916200)
    payload = _payload(client, headers)
    strengths = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=headers).json()
        if item["metric_type"] == "strength"
    ]
    strength = strengths[0]
    payload["days"][0]["exercises"][0]["exercise_id"] = strength["id"]
    if with_second:
        payload["days"][0]["exercises"].append(
            {
                **payload["days"][0]["exercises"][0],
                "exercise_id": strengths[1]["id"],
            }
        )
    payload["days"] = [
        {**payload["days"][0], "title": f"День {index}"} for index in range(1, days + 1)
    ]
    payload["week_cycle"] = {"length_weeks": k, "repeat": True}
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    template_id = created.json()["template"]["id"]
    with get_session_context() as db:
        template = db.get(ProgramTemplate, template_id)
        for day in template.days:
            for index, slot in enumerate(day.exercises):
                for week in range(1, k + 1):
                    db.add(
                        ProgramTemplateExerciseWeekPrescription(
                            template_exercise_id=slot.id,
                            exercise_id=strengths[(week - 1 + index) % len(strengths)]["id"],
                            week_number=week,
                            prescribed_sets=2,
                            prescribed_reps=str(week + 5),
                            rest_seconds=90,
                        )
                    )
        slot_id = template.days[0].exercises[0].id
    response = client.post(
        f"/api/v1/programs/templates/{template_id}/assign-to-me",
        headers=headers,
        json={"duration_weeks": n},
    )
    assert response.status_code == 200, response.text
    return headers, response.json()["user_program_id"], slot_id, strength["id"]


def revision(program_id):
    with get_session_context() as db:
        return db.get(UserProgram, program_id).current_revision_number


def test_cycle_replacement_rejects_incompatible_exercise_metric(client):
    headers, program_id, slot, _ = assigned_cycle(client)
    cardio = next(
        item
        for item in client.get("/api/v1/programs/exercises", headers=headers).json()
        if item["metric_type"] == "cardio"
    )
    response = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "effective_scope": "future_program",
            "occurrence_weeks": [7],
            "skip_protected": True,
            "day_number": 1,
            "target_template_exercise_id": slot,
            "exercise_id": cardio["id"],
            "prescribed_duration_minutes": 20,
            "rest_seconds": 0,
        },
    )
    assert response.status_code == 422, response.text
    assert revision(program_id) == 1


def test_long_101_week_cycle_revision_preview_is_paginated(client):
    headers, program_id, _, _ = assigned_cycle(client, k=101, n=116)
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle"
    payload = {
        "expected_revision_number": 1,
        "effective_from_week": 5,
        "source_week_order": list(range(1, 102)),
    }
    for offset, first, last in [(0, 5, 54), (50, 55, 104), (100, 105, 116)]:
        response = client.post(
            f"{endpoint}/revision/preview", headers=headers, json={**payload, "offset": offset}
        )
        assert response.status_code == 200, response.text
        page = response.json()
        assert page["total_weeks"] == 112
        assert [page["weeks"][0]["week_number"], page["weeks"][-1]["week_number"]] == [first, last]
    assert client.patch(endpoint, headers=headers, json=payload).status_code == 200
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        for week, source_week in [(5, 1), (105, 101), (106, 1), (116, 11)]:
            row = program_versioning._cycle_workout_plans(db, program, week)[0]
            assert row["source_cycle_week"] == source_week
            assert row["exercises"][0]["prescribed_reps"] == str(source_week + 5)


def test_cycle_replacement_validates_only_the_selected_occurrence(client):
    from copy import deepcopy

    from fitminiapp_api.services.prescription_semantics import ensure_plan

    headers, program_id, slot, strength = assigned_cycle(client)
    cardio = next(
        item
        for item in client.get("/api/v1/programs/exercises", headers=headers).json()
        if item["metric_type"] == "cardio"
    )
    with get_session_context() as db:
        assigned = (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program_id, change_kind="assigned")
            .one()
        )
        snapshot = deepcopy(assigned.snapshot)
        other_week = next(row for row in snapshot["logical_cycle"] if row["week_number"] == 2)[
            "exercises"
        ][0]
        plan, projection = ensure_plan(
            None,
            metric_type="cardio",
            prescribed_sets=None,
            prescribed_reps=None,
            prescribed_duration_minutes=20,
            rest_seconds=0,
        )
        other_week.update(
            {
                "metric_type": "cardio",
                "exercise_id": cardio["id"],
                "prescribed_sets": projection.prescribed_sets,
                "prescribed_reps": projection.prescribed_reps,
                "prescribed_duration_minutes": projection.prescribed_duration_minutes,
                "rest_seconds": projection.rest_seconds,
                "prescription": plan.model_dump(mode="json"),
                "sets": program_versioning._cycle_plan_sets(plan.model_dump(mode="json")),
            }
        )
        assigned.snapshot = snapshot
    response = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "effective_scope": "future_program",
            "occurrence_weeks": [7],
            "skip_protected": True,
            "day_number": 1,
            "target_template_exercise_id": slot,
            "exercise_id": strength,
            "prescribed_sets": 2,
            "prescribed_reps": "8",
            "rest_seconds": 90,
        },
    )
    assert response.status_code == 200, response.text


def test_duration_change_preserves_existing_future_workout_plan(client):
    headers, program_id, _, _ = assigned_cycle(client)
    with get_session_context() as db:
        workout = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=4).one()
        workout.exercises[0].prescribed_reps = "15"
        workout_id = workout.id
        set_ids = [item.id for item in workout.exercises[0].sets]
    response = client.patch(
        f"/api/v1/programs/assigned/{program_id}/cycle",
        headers=headers,
        json={"expected_revision_number": 1, "effective_from_week": 4, "duration_weeks": 20},
    )
    assert response.status_code == 200, response.text
    with get_session_context() as db:
        workout = db.get(UserWorkout, workout_id)
        assert workout.exercises[0].prescribed_reps == "15"
        assert [item.id for item in workout.exercises[0].sets] == set_ids
        program = db.get(UserProgram, program_id)
        program_versioning.record_program_revision(
            db,
            program,
            actor=None,
            change_kind="block_updated",
            changed_fields={"operation": "metadata_only"},
        )
        assert program_versioning.hydrate_cycle_workout(db, workout)
        assert workout.exercises[0].prescribed_reps == "15"
        assert [item.id for item in workout.exercises[0].sets] == set_ids


def test_cycle_revision_preview_matches_applied_mapping_and_preserves_started_workout(client):
    headers, program_id, _, _ = assigned_cycle(client, k=3, n=116)
    schedule(client, headers, TODAY + timedelta(weeks=4), 21)
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        program_versioning.materialize_next_cycle_window(
            db, program, through_date=TODAY + timedelta(weeks=4)
        )
        started = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=5).one()
        started.status = "in_progress"
        first_set = started.exercises[0].sets[0]
        first_set.actual_weight = 42
        first_set.actual_reps = 7
        first_set.rir = "2"
        first_set.is_completed = True
        original = (
            started.id,
            first_set.id,
            first_set.actual_weight,
            first_set.actual_reps,
            first_set.rir,
        )
    payload = {
        "expected_revision_number": 1,
        "effective_from_week": 5,
        "source_week_order": [1, 2, 3, 1],
        "repeat": True,
    }
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle/revision/preview"
    preview = client.post(endpoint, headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    result = preview.json()
    assert result["total_weeks"] == 112
    assert len(result["weeks"]) == 50
    assert result["weeks"][0]["source_cycle_week"] == 2
    assert result["weeks"][0]["new_source_cycle_week"] == 1
    assert result["weeks"][0]["workouts"][0]["changeable"] is False
    next_page = client.post(endpoint, headers=headers, json={**payload, "offset": 50})
    assert next_page.status_code == 200, next_page.text
    assert next_page.json()["weeks"][0]["week_number"] == 55
    assert revision(program_id) == 1
    applied = client.patch(
        f"/api/v1/programs/assigned/{program_id}/cycle", headers=headers, json=payload
    )
    assert applied.status_code == 200, applied.text
    assert (
        client.patch(
            f"/api/v1/programs/assigned/{program_id}/cycle", headers=headers, json=payload
        ).status_code
        == 409
    )
    with get_session_context() as db:
        workout = db.get(UserWorkout, original[0])
        recorded = workout.exercises[0].sets[0]
        assert (
            workout.id,
            recorded.id,
            recorded.actual_weight,
            recorded.actual_reps,
            recorded.rir,
        ) == original
        assert workout.status == "in_progress"
        program = db.get(UserProgram, program_id)
        assert program_versioning._cycle_workout_plans(db, program, 6)[0]["source_cycle_week"] == 2


def test_cycle_revision_cancels_removed_day_and_its_reminder_atomically(client, monkeypatch):
    from copy import deepcopy
    from datetime import datetime

    from fitminiapp_api.models.notification import Notification

    headers, program_id, _, _ = assigned_cycle(client, k=3, n=16, days=2)
    with get_session_context() as db:
        assigned = (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program_id, change_kind="assigned")
            .one()
        )
        snapshot = deepcopy(assigned.snapshot)
        snapshot["logical_cycle"] = [
            row
            for row in snapshot["logical_cycle"]
            if (row["week_number"], row["day_number"]) != (1, 2)
        ]
        assigned.snapshot = snapshot
    schedule(client, headers, TODAY + timedelta(weeks=4), 7)
    with get_session_context() as db:
        workout = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=5, day_number=2)
            .one()
        )
        workout_id = workout.id
        reminder = Notification(
            user_id=workout.user_program.user_id,
            category="workout_reminder",
            title="Напоминание",
            body="Тест",
            scheduled_for=datetime(2026, 11, 3),
            scheduled_for_utc=datetime(2026, 11, 3),
            dedupe_key=f"workout:{workout_id}:reminder",
            status="queued",
        )
        db.add(reminder)
    payload = {
        "expected_revision_number": 1,
        "effective_from_week": 5,
        "source_week_order": [1, 2, 3],
    }
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle"
    preview = client.post(f"{endpoint}/revision/preview", headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    assert next(row for row in preview.json()["weeks"][0]["workouts"] if row["id"] == workout_id)[
        "removed"
    ]

    original_cancel = program_versioning.cancel_workout_reminder
    monkeypatch.setattr(
        program_versioning,
        "cancel_workout_reminder",
        lambda *_: (_ for _ in ()).throw(program_versioning.ProgramError("rollback test")),
    )
    failed = client.patch(endpoint, headers=headers, json=payload)
    assert failed.status_code == 422, failed.text
    with get_session_context() as db:
        assert db.get(UserWorkout, workout_id).status == "planned"
        assert (
            db.query(Notification)
            .filter_by(dedupe_key=f"workout:{workout_id}:reminder")
            .one()
            .status
            == "queued"
        )
        assert db.get(UserProgram, program_id).current_revision_number == 1

    monkeypatch.setattr(program_versioning, "cancel_workout_reminder", original_cancel)
    applied = client.patch(endpoint, headers=headers, json=payload)
    assert applied.status_code == 200, applied.text
    with get_session_context() as db:
        assert db.get(UserWorkout, workout_id).status == "cancelled"
        assert (
            db.query(Notification)
            .filter_by(dedupe_key=f"workout:{workout_id}:reminder")
            .one()
            .status
            == "cancelled"
        )


def test_cycle_revision_carries_source_week_edits_without_overriding_later_occurrences(client):
    headers, program_id, slot, exercise = assigned_cycle(client, k=3, n=16)
    endpoint = f"/api/v1/programs/assigned/{program_id}/exercises"
    for scope, reps in [
        ({"from_week": 2, "source_cycle_week": 2}, "12"),
        ({"occurrence_weeks": [10]}, "14"),
    ]:
        response = client.post(
            endpoint,
            headers=headers,
            json={
                "expected_revision_number": revision(program_id),
                "effective_scope": "future_program",
                "skip_protected": True,
                "day_number": 1,
                "target_template_exercise_id": slot,
                "exercise_id": exercise,
                "prescribed_sets": 2,
                "prescribed_reps": reps,
                "rest_seconds": 90,
                **scope,
            },
        )
        assert response.status_code == 200, response.text
    for scope, week_type in [
        ({"from_week": 2, "source_cycle_week": 2}, "light"),
        ({"occurrence_weeks": [10]}, "heavy"),
    ]:
        response = client.post(
            f"/api/v1/programs/assigned/{program_id}/cycle/week-type",
            headers=headers,
            json={
                "expected_revision_number": revision(program_id),
                "week_type": week_type,
                **scope,
            },
        )
        assert response.status_code == 200, response.text
    payload = {
        "expected_revision_number": revision(program_id),
        "effective_from_week": 5,
        "source_week_order": [1, 2, 3, 1],
    }
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle"
    preview = client.post(f"{endpoint}/revision/preview", headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    weeks = {item["week_number"]: item for item in preview.json()["weeks"]}
    assert weeks[6]["workouts"][0]["new_exercises"][0]["prescribed_reps"] == "12"
    assert weeks[10]["workouts"][0]["new_exercises"][0]["prescribed_reps"] == "14"
    assert weeks[6]["workouts"][0]["new_week_type"] == "light"
    assert weeks[10]["workouts"][0]["new_week_type"] == "heavy"
    changed = client.patch(endpoint, headers=headers, json=payload)
    assert changed.status_code == 200, changed.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        assert (
            program_versioning._cycle_workout_plans(db, program, 6)[0]["exercises"][0][
                "prescribed_reps"
            ]
            == "12"
        )
        assert (
            program_versioning._cycle_workout_plans(db, program, 10)[0]["exercises"][0][
                "prescribed_reps"
            ]
            == "14"
        )
        program_versioning.materialize_cycle_schedule(
            db, program, TODAY + timedelta(weeks=5), TODAY + timedelta(weeks=9), with_sets=True
        )
        revisions = (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program_id)
            .order_by(ProgramRevision.revision_number)
            .all()
        )
        for week, expected in [(6, "light"), (10, "heavy")]:
            workout = (
                db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=week).one()
            )
            assert program_versioning.workout_cycle_week_type(db, workout, revisions) == (
                expected,
                True,
            )
    second = {
        "expected_revision_number": revision(program_id),
        "effective_from_week": 9,
        "source_week_order": [2, 2, 1, 4],
    }
    preview = client.post(f"{endpoint}/revision/preview", headers=headers, json=second)
    assert preview.status_code == 200, preview.text
    weeks = {item["week_number"]: item for item in preview.json()["weeks"]}
    assert weeks[9]["workouts"][0]["new_exercises"][0]["prescribed_reps"] == "12"
    assert weeks[9]["workouts"][0]["new_week_type"] == "light"
    assert weeks[10]["workouts"][0]["new_exercises"][0]["prescribed_reps"] == "14"
    assert weeks[10]["workouts"][0]["new_week_type"] == "heavy"
    assert client.patch(endpoint, headers=headers, json=second).status_code == 200


def test_remove_exercise_in_selected_occurrence_preserves_started_workout(client):
    headers, program_id, slot, _ = assigned_cycle(client, k=3, n=16, with_second=True)
    workout = client.get("/api/v1/workouts/today", headers=headers).json()
    started = client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers).json()
    first = started["exercises"][0]["sets"][0]
    fact = client.patch(
        f"/api/v1/workouts/sets/{first['id']}",
        headers=headers,
        json={
            "actual_weight": 40,
            "actual_reps": 8,
            "rir": "2",
            "is_completed": True,
        },
    )
    assert fact.status_code == 200, fact.text
    payload = {
        "expected_revision_number": 1,
        "operation": "remove_exercise",
        "day_number": 1,
        "target_template_exercise_id": slot,
        "occurrence_weeks": [1, 7],
    }
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle/structure"
    preview = client.post(f"{endpoint}/preview", headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    weeks = {item["week_number"]: item for item in preview.json()["weeks"]}
    assert weeks[1]["workouts"][0]["changeable"] is False
    assert len(weeks[1]["workouts"][0]["new_exercises"]) == 2
    assert len(weeks[7]["workouts"][0]["new_exercises"]) == 1
    changed = client.post(endpoint, headers=headers, json=payload)
    assert changed.status_code == 200, changed.text
    assert client.post(endpoint, headers=headers, json=payload).status_code == 409
    with get_session_context() as db:
        current = db.get(UserWorkout, workout["id"])
        assert len(current.exercises) == 2
        assert (
            current.exercises[0].sets[0].id,
            current.exercises[0].sets[0].actual_weight,
            current.exercises[0].sets[0].actual_reps,
            current.exercises[0].sets[0].rir,
        ) == (first["id"], 40, 8, "2")
        program = db.get(UserProgram, program_id)
        assert len(program_versioning._cycle_workout_plans(db, program, 7)[0]["exercises"]) == 1
        assert len(program_versioning._cycle_workout_plans(db, program, 8)[0]["exercises"]) == 2


def test_reorder_future_exercises_keeps_slot_and_set_identities(client):
    headers, program_id, slot, _ = assigned_cycle(client, k=3, n=16, with_second=True)
    with get_session_context() as db:
        workout = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=2).one()
        before = {
            item.source_template_exercise_id: (item.id, [s.id for s in item.sets])
            for item in workout.exercises
        }
        original_order = [item.source_template_exercise_id for item in workout.exercises]
    payload = {
        "expected_revision_number": 1,
        "operation": "move_later",
        "day_number": 1,
        "target_template_exercise_id": slot,
        "occurrence_weeks": [2],
    }
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle/structure"
    preview = client.post(f"{endpoint}/preview", headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    row = preview.json()["weeks"][0]["workouts"][0]
    assert row["structure_changed"] is True
    assert [item["source_template_exercise_id"] for item in row["new_exercises"]] == original_order[
        ::-1
    ]
    response = client.post(endpoint, headers=headers, json=payload)
    assert response.status_code == 200, response.text
    with get_session_context() as db:
        workout = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=2).one()
        assert [item.source_template_exercise_id for item in workout.exercises] == original_order[
            ::-1
        ]
        assert {
            item.source_template_exercise_id: (item.id, [s.id for s in item.sets])
            for item in workout.exercises
        } == before


def test_cycle_structure_authorization_and_group_boundaries(client):
    from copy import deepcopy

    from fitminiapp_api.models.user import CoachClient, User

    headers, program_id, slot, _ = assigned_cycle(client, with_second=True)
    other = _auth(client, 916202)
    trainer = _auth(client, 916203, is_coach=True)
    payload = {
        "expected_revision_number": 1,
        "operation": "remove_exercise",
        "day_number": 1,
        "target_template_exercise_id": slot,
        "occurrence_weeks": [2],
    }
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle/structure"
    assert client.post(f"{endpoint}/preview", headers=other, json=payload).status_code in {403, 404}
    assert client.post(endpoint, headers=trainer, json=payload).status_code in {403, 404}
    with get_session_context() as db:
        assigned = (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program_id, change_kind="assigned")
            .one()
        )
        snapshot = deepcopy(assigned.snapshot)
        exercises = next(row for row in snapshot["logical_cycle"] if row["week_number"] == 2)[
            "exercises"
        ]
        for index, exercise in enumerate(exercises, 1):
            exercise.update(
                {
                    "group_id": 1,
                    "group_kind": "superset",
                    "group_order": index,
                    "superset_group": 1,
                    "superset_order": index,
                }
            )
        assigned.snapshot = snapshot
        coach = db.query(User).filter_by(telegram_user_id=916203).one()
        program = db.get(UserProgram, program_id)
        program.assigned_by_user_id = coach.id
        db.add(CoachClient(coach_user_id=coach.id, client_user_id=program.user_id, status="active"))
    assert client.post(endpoint, headers=headers, json=payload).status_code == 403
    preview = client.post(f"{endpoint}/preview", headers=trainer, json=payload)
    assert preview.status_code == 200, preview.text
    row = preview.json()["weeks"][0]["workouts"][0]
    assert row["structure_changed"] is False
    assert len(row["new_exercises"]) == 2
    result = client.post(endpoint, headers=trainer, json=payload)
    assert result.status_code == 422, result.text
    assert revision(program_id) == 1
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        assert len(program_versioning._cycle_workout_plans(db, program, 2)[0]["exercises"]) == 2


def test_structure_rejects_noop_across_paginated_future_scope(client):
    headers, program_id, _, _ = assigned_cycle(client, k=3, n=116, with_second=True)
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle/structure"
    payload = {
        "expected_revision_number": 1,
        "operation": "remove_exercise",
        "day_number": 1,
        "target_template_exercise_id": 2147483647,
        "from_week": 2,
    }
    preview = client.post(f"{endpoint}/preview", headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    assert preview.json()["total_weeks"] == 115
    assert client.post(endpoint, headers=headers, json=payload).status_code == 422
    assert revision(program_id) == 1


def test_structure_finds_first_applicable_change_on_later_preview_page(client):
    headers, program_id, _, exercise = assigned_cycle(client, k=3, n=116)
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle/structure"
    slot = "b714c414-58ee-4aad-a214-fd21d5ef2f33"
    result = client.post(
        endpoint,
        headers=headers,
        json={
            "expected_revision_number": 1,
            "operation": "add_exercise",
            "day_number": 1,
            "assignment_slot_id": slot,
            "occurrence_weeks": [75],
            "exercise": {
                "exercise_id": exercise,
                "prescribed_sets": 2,
                "prescribed_reps": "8",
                "rest_seconds": 90,
            },
        },
    )
    assert result.status_code == 200, result.text
    payload = {
        "expected_revision_number": 2,
        "operation": "remove_exercise",
        "day_number": 1,
        "target_assignment_slot_id": slot,
        "from_week": 2,
    }
    first = client.post(f"{endpoint}/preview", headers=headers, json=payload)
    assert not any(
        row["structure_changed"] for week in first.json()["weeks"] for row in week["workouts"]
    )
    later = client.post(f"{endpoint}/preview", headers=headers, json={**payload, "offset": 50})
    assert any(
        row["structure_changed"] for week in later.json()["weeks"] for row in week["workouts"]
    )
    result = client.post(endpoint, headers=headers, json=payload)
    assert result.status_code == 200, result.text
    assert revision(program_id) == 3


def test_cycle_count_keeps_protected_day_missing_from_new_source(client):
    from copy import deepcopy

    headers, program_id, _, _ = assigned_cycle(client, k=3, n=16, days=2)
    with get_session_context() as db:
        assigned = (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program_id, change_kind="assigned")
            .one()
        )
        snapshot = deepcopy(assigned.snapshot)
        snapshot["logical_cycle"] = [
            row
            for row in snapshot["logical_cycle"]
            if (row["week_number"], row["day_number"]) != (1, 2)
        ]
        assigned.snapshot = snapshot
    schedule(client, headers, TODAY + timedelta(weeks=4), 7)
    with get_session_context() as db:
        workout = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=5, day_number=2)
            .one()
        )
        workout.status = "in_progress"
        workout_id = workout.id
    response = client.patch(
        f"/api/v1/programs/assigned/{program_id}/cycle",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "effective_from_week": 5,
            "source_week_order": [1, 2, 3],
        },
    )
    assert response.status_code == 200, response.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        assert db.get(UserWorkout, workout_id).status == "in_progress"
        logical = sum(
            len(program_versioning._cycle_workout_plans(db, program, week)) for week in range(1, 17)
        )
        assert program_versioning.cycle_workout_count(db, program) == logical + 1


def test_remove_future_training_day_keeps_past_and_started_workouts(client, monkeypatch):
    headers, program_id, _, _ = assigned_cycle(client, k=3, n=16, days=2)
    middle = TODAY + timedelta(days=1)
    monkeypatch.setattr(program_versioning, "today_for_user", lambda _user: middle)
    with get_session_context() as db:
        day_one = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=1, day_number=1)
            .one()
        )
        day_two = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=1, day_number=2)
            .one()
        )
        day_two.status = "in_progress"
        protected_ids = (day_one.id, day_two.id)
    payload = {"expected_revision_number": 1, "effective_from_week": 1, "remove_day_number": 2}
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle"
    preview = client.post(f"{endpoint}/revision/preview", headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    first = preview.json()["weeks"][0]["workouts"]
    assert next(item for item in first if item["day_number"] == 2)["changeable"] is False
    assert (
        next(item for item in preview.json()["weeks"][1]["workouts"] if item["day_number"] == 2)[
            "removed"
        ]
        is True
    )
    response = client.patch(endpoint, headers=headers, json=payload)
    assert response.status_code == 200, response.text
    with get_session_context() as db:
        assert db.get(UserWorkout, protected_ids[0]).status == "planned"
        assert db.get(UserWorkout, protected_ids[1]).status == "in_progress"
        assert (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=2, day_number=2)
            .one()
            .status
            == "cancelled"
        )
        program = db.get(UserProgram, program_id)
        assert all(
            plan["day_number"] != 2
            for plan in program_versioning._cycle_workout_plans(db, program, 2)
        )


def test_copy_training_day_creates_future_occurrences_with_separate_day_identity(client):
    headers, program_id, slot, exercise_id = assigned_cycle(client, k=3, n=16, days=2)
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        old_reps = {
            week: program_versioning._cycle_workout_plans(db, program, week)[0]["exercises"][0][
                "prescribed_reps"
            ]
            for week in range(5, 9)
        }
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle"
    payload = {
        "expected_revision_number": 1,
        "effective_from_week": 5,
        "copy_day_number": 1,
        "new_day_weekday": 2,
        "new_day_title": "Дополнительная тренировка",
    }
    invalid = client.post(
        f"{endpoint}/revision/preview", headers=headers, json={**payload, "new_day_weekday": 1}
    )
    assert invalid.status_code == 422, invalid.text
    preview = client.post(f"{endpoint}/revision/preview", headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    first = preview.json()["weeks"][0]["workouts"]
    added = next(item for item in first if item["title"] == "Дополнительная тренировка")
    assert added["scheduled_date"] == (TODAY + timedelta(weeks=4, days=2)).isoformat()
    assert added["new_exercises"][0]["source_template_exercise_id"] == slot
    assert added["id"] is None
    assert revision(program_id) == 1
    changed = client.patch(endpoint, headers=headers, json=payload)
    assert changed.status_code == 200, changed.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        assert program_versioning.cycle_workout_count(db, program) == 44
        rows = program_versioning._cycle_workout_plans(db, program, 5)
        copied = next(row for row in rows if row["title"] == "Дополнительная тренировка")
        assert copied["day_number"] not in {1, 2}
        assert copied["exercises"][0]["source_template_exercise_id"] == slot
        copied_day = copied["day_number"]
        assert {
            week: next(
                row
                for row in program_versioning._cycle_workout_plans(db, program, week)
                if row["day_number"] == 1
            )["exercises"][0]["prescribed_reps"]
            for week in range(5, 9)
        } == old_reps
    edited = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": 2,
            "effective_scope": "future_program",
            "occurrence_weeks": [5],
            "skip_protected": True,
            "day_number": copied_day,
            "target_template_exercise_id": slot,
            "exercise_id": exercise_id,
            "prescribed_sets": 2,
            "prescribed_reps": "15",
            "rest_seconds": 90,
        },
    )
    assert edited.status_code == 200, edited.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        rows = program_versioning._cycle_workout_plans(db, program, 5)
        assert (
            next(row for row in rows if row["day_number"] == copied_day)["exercises"][0][
                "prescribed_reps"
            ]
            == "15"
        )
        assert (
            next(row for row in rows if row["day_number"] == 1)["exercises"][0]["prescribed_reps"]
            != "15"
        )


def test_copy_day_keeps_source_week_changes_and_rejects_past_weekday(client, monkeypatch):
    headers, program_id, slot, exercise = assigned_cycle(client, k=3, n=16, days=2)
    changed = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "effective_scope": "future_program",
            "from_week": 2,
            "source_cycle_week": 2,
            "day_number": 1,
            "target_template_exercise_id": slot,
            "exercise_id": exercise,
            "prescribed_sets": 2,
            "prescribed_reps": "12",
            "rest_seconds": 90,
        },
    )
    assert changed.status_code == 200, changed.text
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle"
    payload = {
        "expected_revision_number": 2,
        "effective_from_week": 5,
        "copy_day_number": 1,
        "new_day_weekday": 2,
        "new_day_title": "Копия",
    }
    preview = client.post(f"{endpoint}/revision/preview", headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    week_five = next(item for item in preview.json()["weeks"] if item["week_number"] == 5)
    copied = next(item for item in week_five["workouts"] if item["title"] == "Копия")
    assert copied["new_exercises"][0]["prescribed_reps"] == "12"
    result = client.patch(endpoint, headers=headers, json=payload)
    assert result.status_code == 200, result.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        rows = program_versioning._cycle_workout_plans(db, program, 5)
        assert (
            next(row for row in rows if row["title"] == "Копия")["exercises"][0]["prescribed_reps"]
            == "12"
        )
    monkeypatch.setattr(
        program_versioning, "today_for_user", lambda _user: TODAY + timedelta(days=4)
    )
    stale_day = client.post(
        f"{endpoint}/revision/preview",
        headers=headers,
        json={
            "expected_revision_number": 3,
            "effective_from_week": 1,
            "copy_day_number": 1,
            "new_day_weekday": 3,
            "new_day_title": "Вчера",
        },
    )
    assert stale_day.status_code == 422, stale_day.text
    assert revision(program_id) == 3


@pytest.mark.parametrize("operation", ["copy", "remove", "swap"])
def test_day_changes_preserve_later_cycle_phases_and_overrides(client, operation):
    headers, program_id, slot, exercise = assigned_cycle(client, k=3, n=16, days=2)
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle"
    for request in [
        {"from_week": 2, "source_cycle_week": 2, "week_type": "light"},
        {"occurrence_weeks": [10], "week_type": "heavy"},
    ]:
        result = client.post(
            f"{endpoint}/week-type",
            headers=headers,
            json={
                "expected_revision_number": revision(program_id),
                **request,
            },
        )
        assert result.status_code == 200, result.text
    result = client.patch(
        endpoint,
        headers=headers,
        json={
            "expected_revision_number": revision(program_id),
            "effective_from_week": 9,
            "source_week_order": [3, 1, 2],
            "week_types": ["heavy", "medium", "light"],
        },
    )
    assert result.status_code == 200, result.text
    result = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": revision(program_id),
            "effective_scope": "future_program",
            "from_week": 9,
            "source_cycle_week": 2,
            "skip_protected": True,
            "day_number": 1,
            "target_template_exercise_id": slot,
            "exercise_id": exercise,
            "prescribed_sets": 2,
            "prescribed_reps": "17",
            "rest_seconds": 90,
        },
    )
    assert result.status_code == 200, result.text

    def plans():
        with get_session_context() as db:
            program = db.get(UserProgram, program_id)
            revisions = (
                db.query(ProgramRevision)
                .filter_by(user_program_id=program_id)
                .order_by(ProgramRevision.revision_number)
                .all()
            )
            overrides = program_versioning._cycle_occurrence_overrides(
                db, program_id, revisions=revisions
            )
            result = {}
            for week in range(5, 17):
                cycle, _, boundary = program_versioning._cycle_plan_at(
                    db, program, week, revisions=revisions
                )
                for row in program_versioning._cycle_workout_plans(
                    db, program, week, revisions=revisions
                ):
                    source_week = row["source_cycle_week"]
                    week_type = program_versioning._cycle_type_for_date(
                        cycle,
                        overrides,
                        week,
                        source_week,
                        boundary,
                        date.fromisoformat(row["scheduled_date"]),
                    )
                    result[(week, row["day_number"])] = (
                        row["exercises"][0]["exercise_id"],
                        row["exercises"][0]["prescribed_reps"],
                        week_type,
                        row["source_cycle_week"],
                        row["cycle_iteration"],
                    )
            return result

    before = plans()
    change = {
        "copy": {"copy_day_number": 1, "new_day_weekday": 2, "new_day_title": "Копия"},
        "remove": {"remove_day_number": 2},
        "swap": {"swap_day_number": 1, "swap_with_day_number": 2},
    }[operation]
    payload = {"expected_revision_number": revision(program_id), "effective_from_week": 5, **change}
    preview = client.post(f"{endpoint}/revision/preview", headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    for week in preview.json()["weeks"]:
        for workout in week["workouts"]:
            key = (week["week_number"], workout["day_number"])
            if key in before and not workout["removed"]:
                assert (
                    workout["new_exercises"][0]["exercise_id"],
                    workout["new_exercises"][0]["prescribed_reps"],
                    workout["new_week_type"],
                ) == before[key][:3]
    result = client.patch(endpoint, headers=headers, json=payload)
    assert result.status_code == 200, result.text
    after = plans()
    for key, value in before.items():
        if operation != "remove" or key[1] != 2:
            assert after[key] == value
    if operation == "copy":
        for week in range(5, 17):
            assert after[(week, 3)] == before[(week, 1)]


def test_day_change_keeps_source_repeat_scope_and_later_day_change(client):
    headers, program_id, slot, exercise = assigned_cycle(
        client, k=3, n=16, days=2, with_second=True
    )
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle"
    assert (
        client.patch(
            endpoint,
            headers=headers,
            json={
                "expected_revision_number": 1,
                "effective_from_week": 9,
                "remove_day_number": 2,
            },
        ).status_code
        == 200
    )
    assert (
        client.patch(
            endpoint,
            headers=headers,
            json={
                "expected_revision_number": 2,
                "effective_from_week": 5,
                "copy_day_number": 1,
                "new_day_weekday": 2,
                "new_day_title": "Копия",
            },
        ).status_code
        == 200
    )
    request = {
        "expected_revision_number": 3,
        "from_week": 4,
        "source_cycle_week": 1,
        "week_type": "heavy",
    }
    preview = client.post(f"{endpoint}/week-type/preview", headers=headers, json=request)
    assert preview.status_code == 200, preview.text
    assert [week["week_number"] for week in preview.json()["weeks"]] == [4, 7, 10, 13, 16]
    assert client.post(f"{endpoint}/week-type", headers=headers, json=request).status_code == 200
    updated = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": 4,
            "effective_scope": "future_program",
            "from_week": 4,
            "source_cycle_week": 1,
            "skip_protected": True,
            "day_number": 1,
            "target_template_exercise_id": slot,
            "exercise_id": exercise,
            "prescribed_sets": 2,
            "prescribed_reps": "19",
            "rest_seconds": 90,
        },
    )
    assert updated.status_code == 200, updated.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        for week in (4, 7, 10, 13, 16):
            rows = program_versioning._cycle_workout_plans(db, program, week)
            assert (
                next(row for row in rows if row["day_number"] == 1)["exercises"][0][
                    "prescribed_reps"
                ]
                == "19"
            )
            if week >= 9:
                assert all(row["day_number"] != 2 for row in rows)
                assert any(row["title"] == "Копия" for row in rows)


@pytest.mark.parametrize("operation", ["copy", "remove", "swap"])
@pytest.mark.parametrize("scope", ["one", "repeat", "selected"])
def test_day_changes_apply_only_to_selected_occurrences(client, operation, scope):
    headers, program_id, _, _ = assigned_cycle(client, k=3, n=16, days=2)
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle"
    scope_fields, target = {
        "one": ({"occurrence_weeks": [5]}, {5}),
        "repeat": ({"source_cycle_week": 2}, {5, 8, 11, 14}),
        "selected": ({"occurrence_weeks": [5, 7, 10]}, {5, 7, 10}),
    }[scope]
    change = {
        "copy": {"copy_day_number": 1, "new_day_weekday": 2, "new_day_title": "Копия"},
        "remove": {"remove_day_number": 2},
        "swap": {"swap_day_number": 1, "swap_with_day_number": 2},
    }[operation]
    payload = {"expected_revision_number": 1, "effective_from_week": 5, **scope_fields, **change}
    preview = client.post(f"{endpoint}/revision/preview", headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    for week in preview.json()["weeks"]:
        workouts = week["workouts"]
        affected = week["week_number"] in target
        if operation == "copy":
            assert any(row["added"] for row in workouts) is affected
        elif operation == "remove":
            assert next(row for row in workouts if row["day_number"] == 2)["removed"] is affected
        else:
            assert all(
                (row["new_scheduled_date"] != row["scheduled_date"]) is affected for row in workouts
            ), (week["week_number"], workouts)
    result = client.patch(endpoint, headers=headers, json=payload)
    assert result.status_code == 200, result.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        assert program_versioning.cycle_workout_count(db, program) == (
            32
            + (len(target) if operation == "copy" else -len(target) if operation == "remove" else 0)
        )
        for week in range(5, 17):
            rows = program_versioning._cycle_workout_plans(db, program, week)
            assert all(row["source_cycle_week"] == (week - 1) % 3 + 1 for row in rows)
            assert all(row["cycle_iteration"] == (week - 1) // 3 + 1 for row in rows)
            days = {row["day_number"]: date.fromisoformat(row["scheduled_date"]) for row in rows}
            if operation == "copy":
                assert (3 in days) is (week in target)
            elif operation == "remove":
                assert (2 not in days) is (week in target)
            else:
                first = TODAY + timedelta(weeks=week - 1)
                assert days[1] == first + timedelta(days=1 if week in target else 0)
                assert days[2] == first + timedelta(days=0 if week in target else 1)


def test_selected_days_preserve_other_phase_and_later_source_repeat_edit(client):
    headers, program_id, slot, exercise = assigned_cycle(client, k=3, n=16, days=2)
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle"
    configured = client.patch(
        endpoint,
        headers=headers,
        json={
            "expected_revision_number": 1,
            "effective_from_week": 9,
            "source_week_order": [3, 1, 2],
            "week_types": ["heavy", "medium", "light"],
        },
    )
    assert configured.status_code == 200, configured.text
    selected = client.patch(
        endpoint,
        headers=headers,
        json={
            "expected_revision_number": 2,
            "effective_from_week": 5,
            "occurrence_weeks": [5, 10, 13],
            "copy_day_number": 1,
            "new_day_weekday": 2,
            "new_day_title": "Копия",
        },
    )
    assert selected.status_code == 200, selected.text
    preview = client.post(
        f"{endpoint}/week-type/preview",
        headers=headers,
        json={
            "expected_revision_number": 3,
            "from_week": 5,
            "source_cycle_week": 2,
            "week_type": "light",
        },
    )
    assert preview.status_code == 200, preview.text
    assert [week["week_number"] for week in preview.json()["weeks"]] == [5, 8]
    edited = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": 3,
            "effective_scope": "future_program",
            "from_week": 5,
            "source_cycle_week": 2,
            "skip_protected": True,
            "day_number": 1,
            "target_template_exercise_id": slot,
            "exercise_id": exercise,
            "prescribed_sets": 2,
            "prescribed_reps": "18",
            "rest_seconds": 90,
        },
    )
    assert edited.status_code == 200, edited.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        for week in range(5, 17):
            rows = program_versioning._cycle_workout_plans(db, program, week)
            assert any(row["title"] == "Копия" for row in rows) is (week in {5, 10, 13})
            first = next(row for row in rows if row["day_number"] == 1)
            assert (first["exercises"][0]["prescribed_reps"] == "18") is (week in {5, 8})
            assert first["source_cycle_week"] == (
                (week - 1) % 3 + 1 if week < 9 else (week - 9) % 3 + 1
            )


@pytest.mark.parametrize("operation", ["remove", "swap"])
def test_selected_day_change_keeps_started_workout_and_set_facts(client, operation):
    headers, program_id, _, _ = assigned_cycle(client, k=3, n=16, days=2)
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        program_versioning.materialize_cycle_schedule(
            db, program, TODAY + timedelta(weeks=4), TODAY + timedelta(weeks=7), with_sets=True
        )
        started = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=5, day_number=2)
            .one()
        )
        started.status = "in_progress"
        fact = started.exercises[0].sets[0]
        fact.actual_weight, fact.actual_reps, fact.rir, fact.is_completed = 42.5, 7, "2", True
        workout_id, set_id = started.id, fact.id
        counterpart = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=5, day_number=1)
            .one()
        )
        before_date = counterpart.scheduled_date
    change = (
        {"remove_day_number": 2}
        if operation == "remove"
        else {"swap_day_number": 1, "swap_with_day_number": 2}
    )
    payload = {
        "expected_revision_number": 1,
        "effective_from_week": 5,
        "occurrence_weeks": [5, 7],
        **change,
    }
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle"
    preview = client.post(f"{endpoint}/revision/preview", headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    rows = preview.json()["weeks"][0]["workouts"]
    assert next(row for row in rows if row["day_number"] == 2)["changeable"] is False
    if operation == "swap":
        assert all(row["changeable"] is False for row in rows)
    result = client.patch(endpoint, headers=headers, json=payload)
    assert result.status_code == 200, result.text
    with get_session_context() as db:
        started = db.get(UserWorkout, workout_id)
        fact = db.get(UserWorkoutSet, set_id)
        assert started.status == "in_progress"
        assert (fact.actual_weight, fact.actual_reps, fact.rir, fact.is_completed) == (
            42.5,
            7,
            "2",
            True,
        )
        counterpart = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=5, day_number=1)
            .one()
        )
        assert counterpart.scheduled_date == before_date
        later = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=7, day_number=2)
            .one()
        )
        if operation == "remove":
            assert later.status == "cancelled"
            assert program_versioning.cycle_workout_count(db, db.get(UserProgram, program_id)) == 31
        else:
            assert later.status == "planned"
            assert later.scheduled_date == TODAY + timedelta(weeks=6)


def test_single_started_day_cannot_create_an_empty_revision(client):
    headers, program_id, _, _ = assigned_cycle(client, k=3, n=16, days=2)
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        first = TODAY + timedelta(weeks=4)
        program_versioning.materialize_cycle_schedule(
            db, program, first, first + timedelta(days=6), with_sets=True
        )
        workout = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=5, day_number=2)
            .one()
        )
        workout.status = "in_progress"
    payload = {
        "expected_revision_number": 1,
        "effective_from_week": 5,
        "occurrence_weeks": [5],
        "remove_day_number": 2,
    }
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle"
    preview = client.post(f"{endpoint}/revision/preview", headers=headers, json=payload)
    assert preview.status_code == 200
    assert (
        next(row for row in preview.json()["weeks"][0]["workouts"] if row["day_number"] == 2)[
            "changeable"
        ]
        is False
    )
    assert client.patch(endpoint, headers=headers, json=payload).status_code == 422
    assert revision(program_id) == 1


def test_selected_swap_does_not_materialize_unselected_started_week(client):
    headers, program_id, _, _ = assigned_cycle(client, k=3, n=16, days=2)
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        second_day = TODAY + timedelta(weeks=6, days=1)
        program_versioning.materialize_cycle_schedule(
            db, program, second_day, second_day, with_sets=True
        )
        started = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=7, day_number=2)
            .one()
        )
        started.status = "in_progress"
        assert (
            db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=7).count() == 1
        )
    result = client.patch(
        f"/api/v1/programs/assigned/{program_id}/cycle",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "effective_from_week": 5,
            "occurrence_weeks": [5],
            "swap_day_number": 1,
            "swap_with_day_number": 2,
        },
    )
    assert result.status_code == 200, result.text
    with get_session_context() as db:
        rows = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=7).all()
        assert [(row.day_number, row.status) for row in rows] == [(2, "in_progress")]


def test_selected_day_change_does_not_rewrite_unselected_plans(client):
    headers, program_id, _, _ = assigned_cycle(client, k=3, n=16, days=2)
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        program_versioning.materialize_cycle_schedule(
            db, program, TODAY + timedelta(weeks=4), TODAY + timedelta(weeks=7), with_sets=True
        )
        before = {
            (row.week_number, row.day_number): (
                row.id,
                row.plan_revision_number,
                row.source_cycle_week,
                row.cycle_iteration,
                [item.id for ex in row.exercises for item in ex.sets],
            )
            for row in db.query(UserWorkout).filter_by(user_program_id=program_id)
            if row.week_number >= 5 and row.week_number != 5
        }
    result = client.patch(
        f"/api/v1/programs/assigned/{program_id}/cycle",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "effective_from_week": 5,
            "occurrence_weeks": [5],
            "swap_day_number": 1,
            "swap_with_day_number": 2,
        },
    )
    assert result.status_code == 200, result.text
    with get_session_context() as db:
        after = {
            (row.week_number, row.day_number): (
                row.id,
                row.plan_revision_number,
                row.source_cycle_week,
                row.cycle_iteration,
                [item.id for ex in row.exercises for item in ex.sets],
            )
            for row in db.query(UserWorkout).filter_by(user_program_id=program_id)
            if row.week_number >= 5 and row.week_number != 5
        }
        assert after == before


def test_selected_day_copy_materializes_only_new_selected_workout(client):
    headers, program_id, _, _ = assigned_cycle(client, k=3, n=16, days=2)
    with get_session_context() as db:
        assert (
            db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=7).count() == 0
        )
    result = client.patch(
        f"/api/v1/programs/assigned/{program_id}/cycle",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "effective_from_week": 5,
            "occurrence_weeks": [5],
            "copy_day_number": 1,
            "new_day_weekday": 2,
            "new_day_title": "Копия",
        },
    )
    assert result.status_code == 200, result.text
    with get_session_context() as db:
        assert (
            db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=7).count() == 0
        )
        assert (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=5, day_number=3)
            .count()
            == 1
        )


def test_extending_duration_keeps_source_edits_and_does_not_repeat_a_single_day(client):
    headers, program_id, _, exercise = assigned_cycle(client, k=3, n=16, days=2)
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle"
    slot = "b714c414-58ee-4aad-a214-fd21d5ef2f35"
    changed_type = client.post(
        f"{endpoint}/week-type",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "from_week": 4,
            "source_cycle_week": 1,
            "week_type": "light",
        },
    )
    assert changed_type.status_code == 200, changed_type.text
    added = client.post(
        f"{endpoint}/structure",
        headers=headers,
        json={
            "expected_revision_number": 2,
            "from_week": 4,
            "source_cycle_week": 1,
            "operation": "add_exercise",
            "day_number": 1,
            "assignment_slot_id": slot,
            "exercise": {
                "exercise_id": exercise,
                "prescribed_sets": 2,
                "prescribed_reps": "10",
                "rest_seconds": 90,
            },
        },
    )
    assert added.status_code == 200, added.text
    copied = client.patch(
        endpoint,
        headers=headers,
        json={
            "expected_revision_number": 3,
            "effective_from_week": 16,
            "occurrence_weeks": [16],
            "copy_day_number": 1,
            "new_day_weekday": 2,
            "new_day_title": "Один день",
        },
    )
    assert copied.status_code == 200, copied.text
    extended = client.patch(
        endpoint,
        headers=headers,
        json={
            "expected_revision_number": 4,
            "effective_from_week": 17,
            "duration_weeks": 22,
        },
    )
    assert extended.status_code == 200, extended.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        assert program_versioning.cycle_workout_count(db, program) == 45
        assert any(
            row["title"] == "Один день"
            for row in program_versioning._cycle_workout_plans(db, program, 16)
        )
        assert all(
            row["title"] != "Один день"
            for row in program_versioning._cycle_workout_plans(db, program, 19)
        )
        plan = next(
            row
            for row in program_versioning._cycle_workout_plans(db, program, 19)
            if row["day_number"] == 1
        )
        assert any(item.get("source_assignment_slot_id") == slot for item in plan["exercises"])
        program_versioning.materialize_cycle_schedule(
            db, program, TODAY + timedelta(weeks=18), TODAY + timedelta(weeks=18), with_sets=True
        )
        workout = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=19, day_number=1)
            .one()
        )
        revisions = (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program_id)
            .order_by(ProgramRevision.revision_number)
            .all()
        )
        assert program_versioning.workout_cycle_week_type(db, workout, revisions) == ("light", True)


def test_day_change_preserves_phase_beyond_temporarily_shortened_duration(client):
    headers, program_id, _, _ = assigned_cycle(client, k=3, n=16, days=2)
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle"
    assert (
        client.patch(
            endpoint,
            headers=headers,
            json={
                "expected_revision_number": 1,
                "effective_from_week": 12,
                "source_week_order": [3, 1, 2],
                "week_types": ["heavy", "medium", "light"],
            },
        ).status_code
        == 200
    )
    assert (
        client.patch(
            endpoint,
            headers=headers,
            json={
                "expected_revision_number": 2,
                "effective_from_week": 9,
                "duration_weeks": 8,
            },
        ).status_code
        == 200
    )
    changed = client.patch(
        endpoint,
        headers=headers,
        json={
            "expected_revision_number": 3,
            "effective_from_week": 5,
            "copy_day_number": 1,
            "new_day_weekday": 2,
            "new_day_title": "Копия",
        },
    )
    assert changed.status_code == 200, changed.text
    assert (
        client.patch(
            endpoint,
            headers=headers,
            json={
                "expected_revision_number": 4,
                "effective_from_week": 9,
                "duration_weeks": 16,
            },
        ).status_code
        == 200
    )
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        rows = program_versioning._cycle_workout_plans(db, program, 12)
        assert len(rows) == 3
        assert all(row["source_cycle_week"] == 1 for row in rows)
        assert (
            next(row for row in rows if row["day_number"] == 1)["exercises"][0]["prescribed_reps"]
            == "8"
        )
        cycle, _, boundary = program_versioning._cycle_plan_at(db, program, 12)
        overrides = program_versioning._cycle_occurrence_overrides(db, program.id)
        assert (
            program_versioning._cycle_type_for_date(
                cycle, overrides, 12, 1, boundary, TODAY + timedelta(weeks=11)
            )
            == "heavy"
        )
        assert program_versioning.cycle_workout_count(db, program) == 44


def test_swap_future_training_days_preserves_started_and_manually_moved_weeks(client):
    from datetime import datetime

    from fitminiapp_api.models.notification import Notification

    headers, program_id, _, _ = assigned_cycle(client, k=3, n=16, days=2)
    with get_session_context() as db:
        started = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=1, day_number=1)
            .one()
        )
        started.status = "in_progress"
        moved = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=2, day_number=1)
            .one()
        )
        moved.scheduled_date += timedelta(days=2)
        original = {
            (row.week_number, row.day_number): (
                row.id,
                row.scheduled_date,
                [[item.id for item in ex.sets] for ex in row.exercises],
            )
            for row in db.query(UserWorkout).filter(
                UserWorkout.user_program_id == program_id, UserWorkout.week_number <= 3
            )
        }
        future = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=3, day_number=1)
            .one()
        )
        db.add(
            Notification(
                user_id=future.user_program.user_id,
                category="workout_reminder",
                title="Напоминание",
                body="Тест",
                scheduled_for=datetime(2026, 10, 19),
                scheduled_for_utc=datetime(2026, 10, 19),
                dedupe_key=f"workout:{future.id}:reminder",
                status="queued",
            )
        )
    payload = {
        "expected_revision_number": 1,
        "effective_from_week": 1,
        "swap_day_number": 1,
        "swap_with_day_number": 2,
    }
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle"
    preview = client.post(f"{endpoint}/revision/preview", headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    weeks = {item["week_number"]: item for item in preview.json()["weeks"]}
    assert all(not item["changeable"] for item in weeks[1]["workouts"])
    assert all(not item["changeable"] for item in weeks[2]["workouts"])
    third = {item["day_number"]: item for item in weeks[3]["workouts"]}
    assert third[1]["new_scheduled_date"] == original[(3, 2)][1].isoformat()
    assert third[2]["new_scheduled_date"] == original[(3, 1)][1].isoformat()
    response = client.patch(endpoint, headers=headers, json=payload)
    assert response.status_code == 200, response.text
    with get_session_context() as db:
        rows = {
            (row.week_number, row.day_number): row
            for row in db.query(UserWorkout).filter(
                UserWorkout.user_program_id == program_id, UserWorkout.week_number <= 3
            )
        }
        for week in (1, 2):
            for day in (1, 2):
                assert (rows[(week, day)].id, rows[(week, day)].scheduled_date) == original[
                    (week, day)
                ][:2]
        assert rows[(3, 1)].scheduled_date == original[(3, 2)][1]
        assert rows[(3, 2)].scheduled_date == original[(3, 1)][1]
        reminder = (
            db.query(Notification).filter_by(dedupe_key=f"workout:{rows[(3, 1)].id}:reminder").one()
        )
        assert reminder.status == "cancelled"
        for day in (1, 2):
            assert rows[(3, day)].id == original[(3, day)][0]
            assert [[item.id for item in ex.sets] for ex in rows[(3, day)].exercises] == original[
                (3, day)
            ][2]


def test_add_exercise_to_selected_occurrences_has_distinct_stable_identity(client):
    headers, program_id, original_slot, exercise = assigned_cycle(client, k=1, n=16)
    workout = client.get("/api/v1/workouts/today", headers=headers).json()
    started = client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers).json()
    first = started["exercises"][0]["sets"][0]
    logged = client.patch(
        f"/api/v1/workouts/sets/{first['id']}",
        headers=headers,
        json={
            "actual_weight": 40,
            "actual_reps": 8,
            "rir": "2",
            "is_completed": True,
        },
    )
    assert logged.status_code == 200, logged.text
    assignment_slot = "b714c414-58ee-4aad-a214-fd21d5ef2f30"
    payload = {
        "expected_revision_number": 1,
        "operation": "add_exercise",
        "day_number": 1,
        "assignment_slot_id": assignment_slot,
        "occurrence_weeks": [2, 5],
        "exercise": {
            "exercise_id": exercise,
            "prescribed_sets": 2,
            "prescribed_reps": "10",
            "rest_seconds": 90,
        },
    }
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle/structure"
    preview = client.post(f"{endpoint}/preview", headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    for week in preview.json()["weeks"]:
        items = week["workouts"][0]["new_exercises"]
        assert [item["source_template_exercise_id"] for item in items] == [original_slot, None]
        assert items[1]["source_assignment_slot_id"] == assignment_slot
    assert client.post(endpoint, headers=headers, json=payload).status_code == 200
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        for week in (2, 5):
            plan = program_versioning._cycle_workout_plans(db, program, week)[0]
            assert len(plan["exercises"]) == 2
            assert plan["exercises"][1]["source_assignment_slot_id"] == assignment_slot
        assert len(program_versioning._cycle_workout_plans(db, program, 3)[0]["exercises"]) == 1
        original = db.get(UserWorkout, workout["id"]).exercises[0].sets[0]
        assert (original.id, original.actual_weight, original.actual_reps, original.rir) == (
            first["id"],
            40,
            8,
            "2",
        )
    edited = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": 2,
            "effective_scope": "future_program",
            "occurrence_weeks": [5],
            "skip_protected": True,
            "day_number": 1,
            "target_assignment_slot_id": assignment_slot,
            "exercise_id": exercise,
            "prescribed_sets": 2,
            "prescribed_reps": "12",
            "rest_seconds": 90,
        },
    )
    assert edited.status_code == 200, edited.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        rows = program_versioning._cycle_workout_plans(db, program, 5)[0]["exercises"]
        assert rows[0]["prescribed_reps"] != "12"
        assert rows[1]["prescribed_reps"] == "12"


def test_added_exercise_enforces_visibility_and_rejects_duplicate_slot(client):
    from fitminiapp_api.models.exercise import Exercise
    from fitminiapp_api.models.user import User

    headers, program_id, _, exercise = assigned_cycle(client, k=1, n=16)
    other = _auth(client, 916204)
    with get_session_context() as db:
        owner = db.query(User).filter_by(telegram_user_id=916204).one()
        private = Exercise(
            slug="issue-920-private",
            title="Чужое упражнение",
            metric_type="strength",
            difficulty_level="beginner",
            created_by_user_id=owner.id,
        )
        db.add(private)
        db.flush()
        private_id = private.id
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle/structure"
    payload = {
        "expected_revision_number": 1,
        "operation": "add_exercise",
        "day_number": 1,
        "assignment_slot_id": "b714c414-58ee-4aad-a214-fd21d5ef2f32",
        "occurrence_weeks": [2],
        "exercise": {
            "exercise_id": private_id,
            "prescribed_sets": 2,
            "prescribed_reps": "8",
            "rest_seconds": 90,
        },
    }
    assert client.post(endpoint, headers=other, json=payload).status_code in {403, 404}
    assert client.post(f"{endpoint}/preview", headers=headers, json=payload).status_code == 422
    assert client.post(endpoint, headers=headers, json=payload).status_code == 422
    assert revision(program_id) == 1
    payload["exercise"]["exercise_id"] = exercise
    assert client.post(endpoint, headers=headers, json=payload).status_code == 200
    assert client.post(endpoint, headers=headers, json=payload).status_code == 409
    payload["expected_revision_number"] = 2
    assert client.post(endpoint, headers=headers, json=payload).status_code == 422
    assert revision(program_id) == 2


def test_added_exercise_history_and_notes_do_not_mix_with_original_slot(client):
    from datetime import datetime

    headers, program_id, _, exercise = assigned_cycle(client, k=1, n=16)
    assignment_slot = "b714c414-58ee-4aad-a214-fd21d5ef2f31"
    added = client.post(
        f"/api/v1/programs/assigned/{program_id}/cycle/structure",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "operation": "add_exercise",
            "day_number": 1,
            "assignment_slot_id": assignment_slot,
            "from_week": 2,
            "source_cycle_week": 1,
            "exercise": {
                "exercise_id": exercise,
                "prescribed_sets": 2,
                "prescribed_reps": "8",
                "rest_seconds": 90,
            },
        },
    )
    assert added.status_code == 200, added.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        program_versioning.materialize_cycle_schedule(
            db, program, TODAY + timedelta(weeks=1), TODAY + timedelta(weeks=2), with_sets=True
        )
        previous = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=2).one()
        current = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=3).one()
        previous.status = "completed"
        previous.started_at = previous.started_at_utc = datetime(2026, 10, 12, 10)
        previous.completed_at = previous.completed_at_utc = datetime(2026, 10, 12, 11)
        current.status = "in_progress"
        current.started_at = current.started_at_utc = datetime(2026, 10, 19, 10)
        for item in previous.exercises[0].sets:
            item.actual_weight, item.actual_reps, item.is_completed = 99, 8, True
        added_previous = next(
            item for item in previous.exercises if item.source_assignment_slot_id == assignment_slot
        )
        added_current = next(
            item for item in current.exercises if item.source_assignment_slot_id == assignment_slot
        )
        for item in added_previous.sets:
            item.actual_weight, item.actual_reps, item.is_completed = 40, 8, True
        previous_id, previous_ex_id = previous.id, added_previous.id
        current_id, current_ex_id = current.id, added_current.id
        current_set_ids = [item.id for item in added_current.sets]
    history = client.get(f"/api/v1/workouts/{current_id}/set-history", headers=headers)
    assert history.status_code == 200, history.text
    rows = [item for item in history.json()["sets"] if item["set_id"] in current_set_ids]
    assert all(item["source_assignment_slot_id"] == assignment_slot for item in rows)
    assert all(item["previous_workout"]["actual_weight"] == 40 for item in rows)
    previous_note_path = f"/api/v1/workouts/{previous_id}/exercise-notes/{previous_ex_id}"
    identity = client.get(previous_note_path, headers=headers).json()
    fields = (
        "exercise_id",
        "source_template_exercise_id",
        "source_assignment_slot_id",
        "plan_revision_number",
        "week_number",
        "day_number",
        "source_cycle_week",
        "cycle_iteration",
    )
    note = client.put(
        previous_note_path,
        headers=headers,
        json={
            **{key: identity[key] for key in fields},
            "expected_version": 0,
            "mutation_id": "added-slot-note-1",
            "body": "Другая позиция",
            "tags": [],
        },
    )
    assert note.status_code == 200, note.text
    assert (
        client.put(
            previous_note_path,
            headers=headers,
            json={
                **{key: identity[key] for key in fields},
                "expected_version": 0,
                "mutation_id": "added-slot-note-1",
                "body": "Другая позиция",
                "tags": [],
            },
        ).status_code
        == 200
    )
    current_note = client.get(
        f"/api/v1/workouts/{current_id}/exercise-notes/{current_ex_id}", headers=headers
    )
    assert current_note.status_code == 200, current_note.text
    assert current_note.json()["previous_note"]["body"] == "Другая позиция"


def schedule(client, headers, start, days=93):
    response = client.get(
        "/api/v1/workouts/schedule",
        headers=headers,
        params={
            "date_from": start.isoformat(),
            "date_to": (start + timedelta(days=days - 1)).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("k", [1, 3, 7])
@pytest.mark.parametrize("days_per_week", [1, 3, 7])
@pytest.mark.parametrize("range_days", [7, 30, 93])
def test_schedule_returns_complete_range_without_future_sets(client, k, days_per_week, range_days):
    headers, program_id, _, _ = assigned_cycle(client, k=k, n=30, days=days_per_week)
    start = TODAY + timedelta(weeks=8)
    expected = [
        (TODAY + timedelta(weeks=week - 1, days=day - 1), week, day)
        for week in range(1, 31)
        for day in range(1, days_per_week + 1)
        if start
        <= TODAY + timedelta(weeks=week - 1, days=day - 1)
        <= start + timedelta(days=range_days - 1)
    ]
    expected.sort()
    before = None
    for _ in range(2):
        result = schedule(client, headers, start, range_days)
        assert [
            (date.fromisoformat(row["scheduled_date"]), row["week_number"], row["day_number"])
            for row in result
        ] == expected
        assert all(row["status"] == "planned" for row in result)
        ids = [row["id"] for row in result]
        if before is not None:
            assert ids == before
        before = ids
    with get_session_context() as db:
        assert (
            db.query(UserWorkoutSet)
            .join(UserWorkoutSet.workout_exercise)
            .join(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id)
            .count()
            == 4 * days_per_week * 2
        )
        assert (
            db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=1).count()
            == days_per_week
        )
        assert (
            not db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=5).first()
        )
    assert schedule(client, headers, TODAY + timedelta(weeks=4), 28)


@pytest.mark.parametrize(
    "scope,affected",
    [
        ({"occurrence_weeks": [8]}, {8}),
        ({"from_week": 8, "source_cycle_week": 2}, {8, 11, 14}),
        ({"from_week": 8}, set(range(8, 17))),
    ],
)
def test_scoped_edits_materialized_and_unmaterialized(client, scope, affected):
    headers, program_id, slot, exercise = assigned_cycle(client)
    schedule(client, headers, TODAY + timedelta(weeks=7), 21)
    with get_session_context() as db:
        version = db.get(UserProgram, program_id).current_revision_number
        original_revision = (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program_id, change_kind="assigned")
            .one()
            .snapshot
        )
        old_ids = {
            row.week_number: row.id
            for row in db.query(UserWorkout).filter_by(user_program_id=program_id)
        }
    edited = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": version,
            "effective_scope": "future_program",
            "day_number": 1,
            "target_template_exercise_id": slot,
            "exercise_id": exercise,
            "prescribed_sets": 3,
            "prescribed_reps": "12",
            "rest_seconds": 90,
            **scope,
        },
    )
    assert edited.status_code == 200, edited.text
    stale = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": version,
            "effective_scope": "future_program",
            "day_number": 1,
            "target_template_exercise_id": slot,
            "exercise_id": exercise,
            "prescribed_sets": 3,
            "prescribed_reps": "12",
            **scope,
        },
    )
    assert stale.status_code == 409, stale.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        for first in [1, 5, 9, 13]:
            program_versioning.materialize_next_cycle_window(
                db, program, through_date=TODAY + timedelta(weeks=first - 1)
            )
        rows = db.query(UserWorkout).filter_by(user_program_id=program_id).all()
        assert {row.week_number for row in rows} == set(range(1, 17))
        for row in rows:
            assert row.exercises[0].prescribed_reps == (
                "12" if row.week_number in affected else str((row.week_number - 1) % 3 + 6)
            )
            if row.week_number in old_ids:
                assert row.id == old_ids[row.week_number]
        assert (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program_id, change_kind="assigned")
            .one()
            .snapshot
            == original_revision
        )


def test_cycle_boundary_and_duration_revision_preserve_completed_facts(client, monkeypatch):
    headers, program_id, _, _ = assigned_cycle(client)
    first = client.get("/api/v1/workouts/today", headers=headers).json()
    started = client.post(f"/api/v1/workouts/{first['id']}/start", headers=headers)
    assert started.status_code == 200, started.text
    for item in started.json()["exercises"][0]["sets"]:
        response = client.patch(
            f"/api/v1/workouts/sets/{item['id']}",
            headers=headers,
            json={"actual_reps": 8, "actual_weight": 40, "rir": "2", "is_completed": True},
        )
        assert response.status_code == 200, response.text
    assert client.post(f"/api/v1/workouts/{first['id']}/finish", headers=headers).status_code == 200
    for week in range(2, 6):
        current_day = TODAY + timedelta(weeks=week - 1)
        monkeypatch.setattr(
            routes, "recovery_today_for_user", lambda _user, current_day=current_day: current_day
        )
        workout = client.get("/api/v1/workouts/today", headers=headers)
        assert workout.status_code == 200, workout.text
        started = client.post(f"/api/v1/workouts/{workout.json()['id']}/start", headers=headers)
        assert started.status_code == 200, started.text
        for item in started.json()["exercises"][0]["sets"]:
            logged = client.patch(
                f"/api/v1/workouts/sets/{item['id']}",
                headers=headers,
                json={"actual_reps": 8, "actual_weight": 40, "rir": "2", "is_completed": True},
            )
            assert logged.status_code == 200, logged.text
        assert (
            client.post(
                f"/api/v1/workouts/{workout.json()['id']}/finish", headers=headers
            ).status_code
            == 200
        )
    schedule(client, headers, TODAY, 93)
    with get_session_context() as db:
        row = db.get(UserWorkout, first["id"])
        all_completed_facts = [
            (
                workout.id,
                workout.completed_at,
                [
                    (item.id, item.actual_weight, item.actual_reps, item.rir, item.version)
                    for exercise in workout.exercises
                    for item in exercise.sets
                ],
            )
            for workout in db.query(UserWorkout)
            .filter_by(user_program_id=program_id, status="completed")
            .order_by(UserWorkout.id)
        ]
        assert len(all_completed_facts) == 5
        original = (
            row.completed_at,
            [
                (item.id, item.actual_weight, item.actual_reps, item.rir, item.version)
                for item in row.exercises[0].sets
            ],
        )
    for duration in [20, 10, 30]:
        response = client.patch(
            f"/api/v1/programs/assigned/{program_id}/cycle",
            headers=headers,
            json={
                "expected_revision_number": revision(program_id),
                "effective_from_week": 6,
                "duration_weeks": duration,
            },
        )
        assert response.status_code == 200, response.text
    changed = client.patch(
        f"/api/v1/programs/assigned/{program_id}/cycle",
        headers=headers,
        json={
            "expected_revision_number": revision(program_id),
            "effective_from_week": 6,
            "source_week_order": [1, 2, 3, 1],
        },
    )
    assert changed.status_code == 200, changed.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        program_versioning.materialize_next_cycle_window(
            db, program, through_date=TODAY + timedelta(weeks=5)
        )
        row = db.get(UserWorkout, first["id"])
        assert (
            row.completed_at,
            [
                (item.id, item.actual_weight, item.actual_reps, item.rir, item.version)
                for item in row.exercises[0].sets
            ],
        ) == original
        assert program_versioning._cycle_workout_plans(db, program, 6)[0]["source_cycle_week"] == 1
        assert program_versioning._cycle_workout_plans(db, program, 9)[0]["source_cycle_week"] == 4
        assert program_versioning._cycle_workout_plans(db, program, 10)[0]["source_cycle_week"] == 1
        assert db.get(UserWorkout, first["id"]).source_cycle_week == 1
        assert [
            (
                workout.id,
                workout.completed_at,
                [
                    (item.id, item.actual_weight, item.actual_reps, item.rir, item.version)
                    for exercise in workout.exercises
                    for item in exercise.sets
                ],
            )
            for workout in db.query(UserWorkout)
            .filter_by(user_program_id=program_id, status="completed")
            .order_by(UserWorkout.id)
        ] == all_completed_facts
    assert len(schedule(client, headers, TODAY + timedelta(weeks=9), 93)) == 14


@pytest.mark.parametrize(
    "k,n,repeat", [(7, 2, True), (7, 7, False), (3, 30, True), (7, 30, True), (1, 45, True)]
)
def test_finite_cycle_and_long_duration(client, k, n, repeat):
    headers, program_id, _, _ = assigned_cycle(client, k=k, n=n)
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        assert len(program.workouts) == min(4, n)
        before = program.current_revision_number
    if not repeat:
        changed = client.patch(
            f"/api/v1/programs/assigned/{program_id}/cycle",
            headers=headers,
            json={"expected_revision_number": before, "effective_from_week": 1, "repeat": False},
        )
        assert changed.status_code == 200, changed.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        program_versioning.materialize_next_cycle_window(
            db, program, through_date=TODAY + timedelta(weeks=n - 1)
        )
        last = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=n).one()
        assert last.source_cycle_week == (n - 1) % k + 1
        assert last.cycle_iteration == (n - 1) // k + 1
        assert last.exercises[0].prescribed_reps == str((n - 1) % k + 6)
        assert db.query(UserWorkout).filter_by(user_program_id=program_id).count() <= 5


def test_cycle_shared_copy_and_export_keep_logical_plan(client):
    from fitminiapp_api.models.user import User
    from fitminiapp_api.services.account_export import build_account_export

    headers, program_id, _, _ = assigned_cycle(client, k=7, n=30)
    with get_session_context() as db:
        template_id = db.get(UserProgram, program_id).template_id
    preview = client.post(
        "/api/v1/shares/program/preview", headers=headers, json={"template_id": template_id}
    )
    assert preview.status_code == 200, preview.text
    created = client.post(
        "/api/v1/shares/program",
        headers=headers,
        json={"template_id": template_id, "preview_hash": preview.json()["preview_hash"]},
    )
    assert created.status_code == 201, created.text
    other = _auth(client, 916201)
    imported = client.post(
        f"/api/v1/shares/{created.json()['share_id']}/import",
        headers=other,
        json={"preview_hash": created.json()["preview_hash"]},
    )
    assert imported.status_code == 200, imported.text
    with get_session_context() as db:
        copy = db.query(UserProgram).filter(UserProgram.id != program_id).one()
        assert copy.template.program_metadata["week_cycle"]["length_weeks"] == 7
        assert len(copy.workouts) == 4
        owner = db.query(User).filter_by(telegram_user_id=916200).one()
        exported = build_account_export(db, owner)
        assert exported["programs"][0]["duration_weeks"] == 30
        assert len(exported["programs"][0]["revisions"][0]["snapshot"]["logical_cycle"]) == 7


def test_cycle_import_revision_updates_logical_source_and_restart(client):
    from fitminiapp_api.models.user import User

    headers, program_id, _, _ = assigned_cycle(client, k=3, n=30)
    payload = _payload(client, headers)
    payload["days"][0]["exercises"][0]["prescribed_reps"] = "14"
    replacement = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert replacement.status_code == 200, replacement.text
    with get_session_context() as db:
        owner = db.query(User).filter_by(telegram_user_id=916200).one()
        program = db.get(UserProgram, program_id)
        updated, _, version = program_versioning.apply_imported_template_revision(
            db,
            owner,
            program_id,
            db.get(ProgramTemplate, replacement.json()["template"]["id"]),
            expected_revision_number=program.current_revision_number,
            import_id="synthetic-cycle-import",
            allow_structure_changes=True,
        )
        assert updated.duration_weeks == 30
        program_versioning.materialize_next_cycle_window(
            db, program, through_date=TODAY + timedelta(weeks=9)
        )
        assert (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=10)
            .one()
            .exercises[0]
            .prescribed_reps
            == "14"
        )
    restarted = client.post(
        f"/api/v1/programs/assigned/{program_id}/lifecycle",
        headers=headers,
        json={
            "action": "restart",
            "expected_revision_number": version,
            "reason": "Повторить импортированный план",
        },
    )
    assert restarted.status_code == 200, restarted.text
    with get_session_context() as db:
        new_program = db.get(UserProgram, restarted.json()["new_program_id"])
        assert len(new_program.workouts) == 4
        assert all(row.exercises[0].prescribed_reps == "14" for row in new_program.workouts)


def test_import_cannot_replace_an_active_coach_managed_cycle(client):
    from test_program_import import _csv_payload, _upload, _valid_row

    from fitminiapp_api.models.program_import import ProgramImport
    from fitminiapp_api.models.user import CoachClient, User

    headers, program_id, _, _ = assigned_cycle(client)
    _auth(client, 916205, is_coach=True)
    with get_session_context() as db:
        coach = db.query(User).filter_by(telegram_user_id=916205).one()
        program = db.get(UserProgram, program_id)
        program.assigned_by_user_id = coach.id
        db.add(CoachClient(coach_user_id=coach.id, client_user_id=program.user_id, status="active"))
    uploaded = _upload(client, headers, "cycle.csv", _csv_payload([_valid_row()]))
    assert uploaded.status_code == 201, uploaded.text
    import_id = uploaded.json()["id"]
    with get_session_context() as db:
        templates_before = db.query(ProgramTemplate).count()
        version_before = db.get(UserProgram, program_id).current_revision_number
    result = client.post(
        f"/api/v1/programs/imports/{import_id}/confirm",
        headers=headers,
        json={"target_program_id": program_id, "expected_revision_number": version_before},
    )
    assert result.status_code == 403, result.text
    with get_session_context() as db:
        assert db.get(UserProgram, program_id).current_revision_number == version_before
        assert db.query(ProgramTemplate).count() == templates_before
        assert db.get(ProgramImport, import_id).status == "pending"


def test_reminders_extend_logical_schedule_without_future_sets(client, monkeypatch):
    from datetime import datetime, time

    from fitminiapp_api.models.notification import Notification, NotificationSetting
    from fitminiapp_api.models.user import User
    from fitminiapp_api.services import notifications

    _, program_id, _, _ = assigned_cycle(client, k=3, n=30)
    current = TODAY + timedelta(weeks=8)
    monkeypatch.setattr(
        notifications, "now_for_user_naive", lambda _user: datetime.combine(current, time(8))
    )
    with get_session_context() as db:
        owner = db.query(User).filter_by(telegram_user_id=916200).one()
        setting = db.query(NotificationSetting).filter_by(user_id=owner.id).first()
        if setting is None:
            setting = NotificationSetting(user_id=owner.id)
            db.add(setting)
        setting.workout_reminders_enabled = True
        db.flush()
        notifications.sync_workout_reminders(db)
        db.flush()
        future = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=9).one()
        assert future.plan_materialized is False and not future.exercises
        assert (
            db.query(Notification)
            .filter_by(user_id=owner.id, dedupe_key=f"workout:{future.id}:reminder")
            .one()
            .status
            == "queued"
        )
        notifications.sync_workout_reminders(db)
        assert (
            db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=9).count() == 1
        )


def test_thirty_week_completion_and_missing_days_are_not_lost(client):
    headers, program_id, _, _ = assigned_cycle(client, k=3, n=30, days=3)
    # A one-day read must not make a partially projected week count as complete.
    schedule(client, headers, TODAY + timedelta(weeks=8), 1)
    for _ in range(32):
        with get_session_context() as db:
            program = db.get(UserProgram, program_id)
            planned = [
                row.id
                for row in db.query(UserWorkout).filter_by(
                    user_program_id=program_id, status="planned"
                )
            ]
            if not program.is_active:
                break
        for workout_id in planned:
            response = client.post(f"/api/v1/workouts/{workout_id}/skip", headers=headers)
            assert response.status_code == 200, response.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        assert program.status == "completed" and not program.is_active
        actual = {(row.week_number, row.day_number) for row in program.workouts}
        assert actual == {(week, day) for week in range(1, 31) for day in range(1, 4)}


def test_reschedule_pause_resume_keep_occurrence_identity(client):
    headers, program_id, _, _ = assigned_cycle(client, k=3, n=30)
    source_day = TODAY + timedelta(weeks=8)
    item = schedule(client, headers, source_day, 1)[0]
    moved_day = source_day + timedelta(days=2)
    moved = client.patch(
        f"/api/v1/workouts/{item['id']}/schedule",
        headers=headers,
        json={"scheduled_date": moved_day.isoformat()},
    )
    assert moved.status_code == 200, moved.text
    assert schedule(client, headers, source_day, 1) == []
    assert schedule(client, headers, moved_day, 1)[0]["id"] == item["id"]
    for action in ["pause", "resume"]:
        result = client.post(
            f"/api/v1/programs/assigned/{program_id}/lifecycle",
            headers=headers,
            json={
                "action": action,
                "expected_revision_number": revision(program_id),
                "reason": "Проверка расписания",
            },
        )
        assert result.status_code == 200, result.text
        items = schedule(client, headers, moved_day, 1)
        assert items == [] if action == "pause" else items[0]["id"] == item["id"]
    with get_session_context() as db:
        row = db.get(UserWorkout, item["id"])
        assert (row.week_number, row.day_number, row.source_cycle_week, row.cycle_iteration) == (
            9,
            1,
            3,
            3,
        )
        assert (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=9, day_number=1)
            .count()
            == 1
        )


def test_repeat_block_uses_unmaterialized_cycle_source(client):
    headers, program_id, _, _ = assigned_cycle(client, k=3, n=30)
    created = client.post(
        f"/api/v1/programs/assigned/{program_id}/blocks",
        headers=headers,
        json={
            "expected_revision_number": revision(program_id),
            "title": "Повторяемый блок",
            "purpose": "Проверка источника",
            "start_date": (TODAY + timedelta(weeks=9)).isoformat(),
            "end_date": (TODAY + timedelta(weeks=11) - timedelta(days=1)).isoformat(),
            "is_deload": True,
        },
    )
    assert created.status_code == 201, created.text
    block_id = created.json()["block"]["id"]
    for state in ["active", "completed"]:
        changed = client.patch(
            f"/api/v1/programs/assigned/{program_id}/blocks/{block_id}",
            headers=headers,
            json={"expected_revision_number": revision(program_id), "status": state},
        )
        assert changed.status_code == 200, changed.text
    with get_session_context() as db:
        assert (
            not db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=10).first()
        )
    repeated = client.post(
        f"/api/v1/programs/assigned/{program_id}/blocks/{block_id}/repeat",
        headers=headers,
        json={
            "expected_revision_number": revision(program_id),
            "reason": "Повторить логический план",
        },
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["duration_weeks"] == 32
    assert repeated.json()["block"]["is_deload"] is True
    with get_session_context() as db:
        rows = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id, UserWorkout.week_number > 30)
            .order_by(UserWorkout.week_number)
            .all()
        )
        assert [row.week_number for row in rows] == [31, 32]
        assert [row.exercises[0].prescribed_reps for row in rows] == ["6", "7"]
        assert all(
            not item.is_completed and item.actual_weight is None
            for row in rows
            for exercise in row.exercises
            for item in exercise.sets
        )


def test_bounded_future_edit_refreshes_stale_plan_before_start(client, monkeypatch):
    headers, program_id, slot, exercise = assigned_cycle(client, k=1, n=30)
    with get_session_context() as db:
        row = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=2).one()
        workout_id = row.id
        old_ids = [item.id for item in row.exercises[0].sets]
        old_versions = [item.version for item in row.exercises[0].sets]
    monkeypatch.setattr(program_versioning, "MAX_GENERATED_SETS", 3)
    edited = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": revision(program_id),
            "effective_scope": "future_program",
            "from_week": 1,
            "day_number": 1,
            "target_template_exercise_id": slot,
            "exercise_id": exercise,
            "prescribed_sets": 2,
            "prescribed_reps": "14",
            "rest_seconds": 90,
        },
    )
    assert edited.status_code == 200, edited.text
    with get_session_context() as db:
        row = db.get(UserWorkout, workout_id)
        assert row.exercises[0].prescribed_reps == "6"
        assert row.plan_revision_number < db.get(UserProgram, program_id).current_revision_number
    monkeypatch.setattr(routes, "recovery_today_for_user", lambda _user: TODAY + timedelta(weeks=1))
    started = client.post(f"/api/v1/workouts/{workout_id}/start", headers=headers)
    assert started.status_code == 200, started.text
    actual = started.json()["exercises"][0]
    assert actual["prescribed_reps"] == "14"
    assert [item["id"] for item in actual["sets"]] == old_ids
    assert [item["version"] for item in actual["sets"]] == [version + 1 for version in old_versions]
    stale = client.patch(
        f"/api/v1/workouts/sets/{old_ids[0]}",
        headers=headers,
        json={
            "actual_reps": 8,
            "actual_weight": 40,
            "is_completed": True,
            "expected_version": old_versions[0],
            "mutation_id": "916-stale-plan-mutation",
        },
    )
    assert stale.status_code == 409, stale.text


def test_future_edit_does_not_touch_a_started_workout(client):
    headers, program_id, slot, exercise = assigned_cycle(client)
    workout = client.get("/api/v1/workouts/today", headers=headers).json()
    assert (
        client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers).status_code == 200
    )
    before = revision(program_id)
    attempted = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": before,
            "effective_scope": "future_program",
            "occurrence_weeks": [1],
            "day_number": 1,
            "target_template_exercise_id": slot,
            "exercise_id": exercise,
            "prescribed_sets": 3,
            "prescribed_reps": "15",
        },
    )
    assert attempted.status_code == 422, attempted.text
    assert revision(program_id) == before
    with get_session_context() as db:
        row = db.get(UserWorkout, workout["id"])
        assert row.status == "in_progress" and row.exercises[0].prescribed_reps == "6"


def test_offline_set_retry_survives_future_edit_without_changing_started_workout(client):
    headers, program_id, slot, exercise = assigned_cycle(client)
    workout_id = client.get("/api/v1/workouts/today", headers=headers).json()["id"]
    started = client.post(f"/api/v1/workouts/{workout_id}/start", headers=headers)
    assert started.status_code == 200, started.text
    first, second = started.json()["exercises"][0]["sets"]
    first_change = {
        "actual_reps": 8,
        "actual_weight": 40,
        "rir": "2",
        "is_completed": True,
        "expected_version": first["version"],
        "mutation_id": "920-offline-first-mutation",
    }
    recorded = client.patch(
        f"/api/v1/workouts/sets/{first['id']}", headers=headers, json=first_change
    )
    assert recorded.status_code == 200, recorded.text
    edit = {
        "expected_revision_number": revision(program_id),
        "effective_scope": "future_program",
        "from_week": 1,
        "source_cycle_week": 1,
        "skip_protected": True,
        "day_number": 1,
        "target_template_exercise_id": slot,
        "exercise_id": exercise,
        "prescribed_sets": 3,
        "prescribed_reps": "12",
        "rest_seconds": 90,
    }
    updated = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises", headers=headers, json=edit
    )
    assert updated.status_code == 200, updated.text
    replayed = client.patch(
        f"/api/v1/workouts/sets/{first['id']}", headers=headers, json=first_change
    )
    assert replayed.status_code == 200, replayed.text
    assert replayed.json() == recorded.json()
    pending = client.patch(
        f"/api/v1/workouts/sets/{second['id']}",
        headers=headers,
        json={
            "actual_reps": 7,
            "actual_weight": 37.5,
            "rir": "3",
            "is_completed": True,
            "expected_version": second["version"],
            "mutation_id": "920-offline-second-mutation",
        },
    )
    assert pending.status_code == 200, pending.text
    assert (
        client.post(
            f"/api/v1/programs/assigned/{program_id}/exercises", headers=headers, json=edit
        ).status_code
        == 409
    )
    with get_session_context() as db:
        active = db.get(UserWorkout, workout_id)
        assert active.status == "in_progress"
        assert active.exercises[0].prescribed_reps == "6"
        assert [item.id for item in active.exercises[0].sets] == [first["id"], second["id"]]
        assert [
            (item.actual_reps, float(item.actual_weight), item.rir)
            for item in active.exercises[0].sets
        ] == [
            (8, 40, "2"),
            (7, 37.5, "3"),
        ]
        future = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=4).one()
        assert future.exercises[0].prescribed_reps == "12"


def test_live_set_plan_change_is_versioned_and_preserves_recorded_facts(client):
    headers, program_id, _, _ = assigned_cycle(client)
    workout = client.get("/api/v1/workouts/today", headers=headers).json()
    started = client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers).json()
    first, second = started["exercises"][0]["sets"]
    recorded = client.patch(
        f"/api/v1/workouts/sets/{first['id']}",
        headers=headers,
        json={
            "actual_reps": 8,
            "actual_weight": 40,
            "rir": "2",
            "is_completed": True,
            "expected_version": first["version"],
            "mutation_id": "920-live-record-first-set",
        },
    )
    assert recorded.status_code == 200, recorded.text
    plan_change = {
        "expected_version": second["version"],
        "mutation_id": "920-live-plan-target-edit",
        "planned_target": {"weight_kg": "37.50", "reps": 8, "confirmed": True},
    }
    path = f"/api/v1/workouts/sets/{second['id']}"
    changed = client.patch(path, headers=headers, json=plan_change)
    assert changed.status_code == 200, changed.text
    assert changed.json()["version"] == second["version"] + 1
    assert changed.json()["actual_weight"] is None
    assert changed.json()["actual_reps"] is None
    assert client.patch(path, headers=headers, json=plan_change).json() == changed.json()
    offline_fact = {
        "actual_reps": 7,
        "actual_weight": 35,
        "is_completed": False,
        "expected_version": second["version"],
        "mutation_id": "920-live-offline-actual-result",
    }
    conflict = client.patch(path, headers=headers, json=offline_fact)
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["detail"]["code"] == "workout_set_plan_conflict"
    assert conflict.json()["detail"]["current_plan"]["load_target"]["value"] == 37.5
    retried = client.patch(
        path, headers=headers, json={**offline_fact, "expected_version": changed.json()["version"]}
    )
    assert retried.status_code == 200, retried.text
    reused = client.patch(
        path,
        headers=headers,
        json={**plan_change, "planned_target": {"weight_kg": "38", "reps": 8, "confirmed": True}},
    )
    assert reused.status_code == 409, reused.text
    stale = client.patch(
        path,
        headers=headers,
        json={**plan_change, "mutation_id": "920-live-plan-stale-edit"},
    )
    assert stale.status_code == 409, stale.text
    denied = client.patch(path, headers=_auth(client, 916299), json=plan_change)
    assert denied.status_code == 404
    completed = client.patch(
        f"/api/v1/workouts/sets/{first['id']}",
        headers=headers,
        json={
            **plan_change,
            "expected_version": recorded.json()["version"],
            "mutation_id": "920-live-plan-completed-set",
        },
    )
    assert completed.status_code == 409, completed.text
    current = client.get("/api/v1/workouts/today", headers=headers).json()
    exercise = current["exercises"][0]
    assert [item["id"] for item in exercise["sets"]] == [first["id"], second["id"]]
    assert exercise["sets"][0]["actual_reps"] == 8
    assert exercise["sets"][0]["actual_weight"] == 40
    assert exercise["sets"][0]["rir"] == "2"
    assert exercise["prescription"]["segments"][0]["rep_target"]["value"] == 6
    assert exercise["prescription"]["segments"][0]["load_target"]["kind"] == "user_selected"
    assert exercise["prescription"]["segments"][1]["load_target"] == {
        "kind": "absolute",
        "value": 37.5,
    }
    assert exercise["prescription"]["segments"][1]["rep_target"]["value"] == 8
    assert revision(program_id) == 1


@pytest.mark.parametrize("invalid", ["unconfirmed", "numeric_confirmation", "no_version", "mixed"])
def test_live_set_plan_rejects_unconfirmed_or_mixed_changes(client, invalid):
    headers, program_id, _, _ = assigned_cycle(client)
    workout = client.get("/api/v1/workouts/today", headers=headers).json()
    started = client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers).json()
    item = started["exercises"][0]["sets"][0]
    body = {
        "expected_version": item["version"],
        "mutation_id": "920-live-plan-invalid-change",
        "planned_target": {"weight_kg": "37.50", "reps": 8, "confirmed": True},
    }
    if invalid == "unconfirmed":
        body["planned_target"]["confirmed"] = False
    elif invalid == "numeric_confirmation":
        body["planned_target"]["confirmed"] = 1
    elif invalid == "no_version":
        body.pop("expected_version")
        body.pop("mutation_id")
    else:
        body["actual_weight"] = 99
    response = client.patch(f"/api/v1/workouts/sets/{item['id']}", headers=headers, json=body)
    assert response.status_code == 422, response.text
    current = client.get("/api/v1/workouts/today", headers=headers).json()
    assert current["exercises"][0]["sets"][0] == item
    assert revision(program_id) == 1


def test_live_set_plan_cannot_change_a_planned_or_completed_workout(client):
    headers, _, _, _ = assigned_cycle(client)
    workout = client.get("/api/v1/workouts/today", headers=headers).json()
    first, second = workout["exercises"][0]["sets"]
    body = {
        "expected_version": second["version"],
        "mutation_id": "920-live-plan-closed-workout",
        "planned_target": {"weight_kg": "37.50", "reps": 8, "confirmed": True},
    }
    path = f"/api/v1/workouts/sets/{second['id']}"
    assert client.patch(path, headers=headers, json=body).status_code == 409
    assert (
        client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers).status_code == 200
    )
    logged = client.patch(
        f"/api/v1/workouts/sets/{first['id']}",
        headers=headers,
        json={"actual_reps": 8, "actual_weight": 40, "rir": "2", "is_completed": True},
    )
    assert logged.status_code == 200, logged.text
    finished = client.post(
        f"/api/v1/workouts/{workout['id']}/finish",
        headers=headers,
        json={"confirm_incomplete": True},
    )
    assert finished.status_code == 200, finished.text
    response = client.patch(path, headers=headers, json=body)
    assert response.status_code == 409, response.text
    with get_session_context() as db:
        completed = db.get(UserWorkout, workout["id"])
        assert completed.status == "completed"
        assert completed.exercises[0].prescription is None
        assert completed.exercises[0].sets[0].actual_weight == 40
        assert completed.exercises[0].sets[0].actual_reps == 8
        assert completed.exercises[0].sets[0].rir == "2"


def test_live_set_plan_preserves_legacy_unicode_rep_range(client):
    headers, program_id, _, _ = assigned_cycle(client)
    workout = client.get("/api/v1/workouts/today", headers=headers).json()
    started = client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers).json()
    target = started["exercises"][0]["sets"][1]
    with get_session_context() as db:
        db.get(UserWorkout, workout["id"]).exercises[0].prescribed_reps = "8–10"
    response = client.patch(
        f"/api/v1/workouts/sets/{target['id']}",
        headers=headers,
        json={
            "expected_version": target["version"],
            "mutation_id": "920-live-unicode-reps-range",
            "planned_target": {"weight_kg": "37.5", "reps": 8, "confirmed": True},
        },
    )
    assert response.status_code == 200, response.text
    with get_session_context() as db:
        exercise = db.get(UserWorkout, workout["id"]).exercises[0]
        assert exercise.prescribed_reps == "8–10"
        target = exercise.prescription["segments"][0]["rep_target"]
        assert (target["kind"], target["min_reps"], target["max_reps"]) == ("range", 8, 10)
        assert db.get(UserProgram, program_id).current_revision_number == 1


def test_future_edit_in_current_week_uses_workout_date(client, monkeypatch):
    headers, program_id, _, exercise = assigned_cycle(client, days=3)
    middle = TODAY + timedelta(days=1)
    monkeypatch.setattr(program_versioning, "today_for_user", lambda _user: middle)
    with get_session_context() as db:
        row = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=1, day_number=3)
            .one()
        )
        slot = row.exercises[0].source_template_exercise_id
        workout_id = row.id
    response = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": revision(program_id),
            "effective_scope": "future_program",
            "day_number": 3,
            "target_template_exercise_id": slot,
            "exercise_id": exercise,
            "prescribed_sets": 2,
            "prescribed_reps": "17",
            "rest_seconds": 90,
        },
    )
    assert response.status_code == 200, response.text
    with get_session_context() as db:
        assert db.get(UserWorkout, workout_id).exercises[0].prescribed_reps == "17"
        assert (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id, week_number=1, day_number=1)
            .one()
            .exercises[0]
            .prescribed_reps
            == "6"
        )


def test_nonrepeating_duration_extension_requires_explicit_repeat(client):
    headers, program_id, _, _ = assigned_cycle(client, k=3, n=3)
    response = client.patch(
        f"/api/v1/programs/assigned/{program_id}/cycle",
        headers=headers,
        json={
            "expected_revision_number": revision(program_id),
            "effective_from_week": 1,
            "repeat": False,
        },
    )
    assert response.status_code == 200, response.text
    before = revision(program_id)
    for extra in ({}, {"repeat": True}):
        response = client.patch(
            f"/api/v1/programs/assigned/{program_id}/cycle",
            headers=headers,
            json={
                "expected_revision_number": before,
                "effective_from_week": 1,
                "duration_weeks": 16,
                **extra,
            },
        )
        assert response.status_code == (200 if extra else 422), response.text
        if not extra:
            assert revision(program_id) == before


def test_coach_and_progress_count_full_logical_plan_after_absence(client, monkeypatch):
    from fitminiapp_api.models.user import CoachClient, User
    from fitminiapp_api.services import progress

    headers, program_id, _, _ = assigned_cycle(client, k=3, n=30, days=3)
    coach_headers = _auth(client, 916201, is_coach=True)
    later = TODAY + timedelta(weeks=8)
    monkeypatch.setattr(programs, "today_for_user", lambda _user: later)
    monkeypatch.setattr(progress, "today_for_user", lambda _user: later)
    with get_session_context() as db:
        coach = db.query(User).filter_by(telegram_user_id=916201).one()
        program = db.get(UserProgram, program_id)
        program.assigned_by_user_id = coach.id
        db.add(CoachClient(coach_user_id=coach.id, client_user_id=program.user_id, status="active"))
        # A moved occurrence is counted at its actual scheduled date, not again at its source date.
        moved = next(
            row for row in program.workouts if row.week_number == 2 and row.day_number == 1
        )
        moved.scheduled_date = later + timedelta(days=1)
    response = client.get("/api/v1/coach/assigned-programs", headers=coach_headers)
    assert response.status_code == 200, response.text
    item = next(row for row in response.json() if row["id"] == program_id)
    assert item["workouts_total"] == 90 and item["workouts_planned"] == 90
    assert item["next_workout_date"] == later.isoformat()
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        owner = db.get(User, program.user_id)
        result = progress.build_progress_summary_for_range(db, owner, TODAY, later)
        assert result["training"]["planned_workouts"] == 23
        assert result["training"]["completed_workouts"] == 0
        assert program_versioning.cycle_workout_count(db, program) == 90
        assert (
            db.query(UserWorkoutSet)
            .join(UserWorkoutSet.workout_exercise)
            .join(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id)
            .count()
            == 24
        )
    # Existing athlete reads keep the same projected occurrence identifiers.
    assert schedule(client, headers, later, 7)


def test_cycle_revision_checks_current_trainer_and_assignment_owner(client):
    from fitminiapp_api.models.user import CoachClient, User

    headers, program_id, _, _ = assigned_cycle(client)
    other = _auth(client, 916202)
    trainer = _auth(client, 916203, is_coach=True)
    change = {
        "expected_revision_number": revision(program_id),
        "effective_from_week": 2,
        "duration_weeks": 20,
    }
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle"
    assert client.patch(endpoint, headers=other, json=change).status_code in {403, 404}
    assert client.patch(endpoint, headers=trainer, json=change).status_code in {403, 404}
    with get_session_context() as db:
        coach = db.query(User).filter_by(telegram_user_id=916203).one()
        program = db.get(UserProgram, program_id)
        program.assigned_by_user_id = coach.id
        db.add(CoachClient(coach_user_id=coach.id, client_user_id=program.user_id, status="active"))
    response = client.patch(endpoint, headers=trainer, json=change)
    assert response.status_code == 200, response.text
    with get_session_context() as db:
        db.query(CoachClient).filter_by(
            client_user_id=db.get(UserProgram, program_id).user_id
        ).one().status = "inactive"
    change["expected_revision_number"] = revision(program_id)
    change["duration_weeks"] = 22
    assert client.patch(endpoint, headers=trainer, json=change).status_code in {403, 404}
    assert revision(program_id) == change["expected_revision_number"]
    response = client.patch(endpoint, headers=headers, json=change)
    assert response.status_code == 200, response.text


def test_cycle_impact_preview_supports_all_future_weeks_and_rejects_stale_revision(client):
    headers, program_id, _, _ = assigned_cycle(client, k=3, n=116)
    endpoint = f"/api/v1/programs/assigned/{program_id}/cycle/week-type/preview"
    expected_revision = revision(program_id)
    page_request = {"expected_revision_number": expected_revision, "from_week": 8}
    all_weeks = []
    for offset, first, last in ((0, 8, 57), (50, 58, 107), (100, 108, 116)):
        response = client.post(endpoint, headers=headers, json={**page_request, "offset": offset})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total_weeks"] == 109
        assert body["offset"] == offset
        assert [row["week_number"] for row in body["weeks"]] == list(range(first, last + 1))
        all_weeks.extend(body["weeks"])
    assert [row["week_number"] for row in all_weeks] == list(range(8, 117))
    assert [(row["source_cycle_week"], row["cycle_iteration"]) for row in all_weeks[:4]] == [
        (2, 3),
        (3, 3),
        (1, 4),
        (2, 4),
    ]
    assert [row["workouts"][0]["exercises"][0]["prescribed_reps"] for row in all_weeks[:3]] == [
        "7",
        "8",
        "6",
    ]
    repeating = client.post(
        endpoint, headers=headers, json={**page_request, "source_cycle_week": 2}
    )
    assert repeating.status_code == 200, repeating.text
    assert [row["week_number"] for row in repeating.json()["weeks"][:3]] == [8, 11, 14]
    mutation_endpoint = f"/api/v1/programs/assigned/{program_id}/cycle/week-type"
    invalid_write = client.post(
        mutation_endpoint,
        headers=headers,
        json={"expected_revision_number": expected_revision, "week_type": "heavy"},
    )
    assert invalid_write.status_code == 422, invalid_write.text
    all_future_write = client.post(
        mutation_endpoint,
        headers=headers,
        json={**page_request, "week_type": "heavy"},
    )
    assert all_future_write.status_code == 200, all_future_write.text
    assert all_future_write.json()["current_revision_number"] == expected_revision + 1
    stale = client.post(
        endpoint, headers=headers, json={**page_request, "expected_revision_number": 0}
    )
    assert stale.status_code == 409, stale.text
    other = _auth(client, 916204)
    unauthorized = client.post(endpoint, headers=other, json=page_request)
    assert unauthorized.status_code in {403, 404}, unauthorized.text


def test_cycle_preview_keeps_saved_exercises_for_started_and_completed_after_future_edit(client):
    from fitminiapp_api.core.timezone import now_msk_naive

    headers, program_id, slot, exercise_id = assigned_cycle(client, k=3, n=16)
    with get_session_context() as db:
        completed = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=1).one()
        started = db.query(UserWorkout).filter_by(user_program_id=program_id, week_number=4).one()
        now = now_msk_naive()
        completed.status = "completed"
        completed.started_at = now
        completed.completed_at = now
        completed_set = completed.exercises[0].sets[0]
        completed_set.is_completed = True
        completed_set.actual_reps = 6
        completed_set.actual_weight = 40
        started.status = "in_progress"
        started.started_at = now
        started_set = started.exercises[0].sets[0]
        started_set.is_completed = True
        started_set.actual_reps = 5
        started_set.actual_weight = 35
        recorded = {
            1: (completed.id, completed_set.id, completed_set.actual_reps),
            4: (started.id, started_set.id, started_set.actual_reps),
        }

    edited = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": revision(program_id),
            "effective_scope": "future_program",
            "from_week": 1,
            "source_cycle_week": 1,
            "skip_protected": True,
            "day_number": 1,
            "target_template_exercise_id": slot,
            "exercise_id": exercise_id,
            "prescribed_sets": 3,
            "prescribed_reps": "12",
            "rest_seconds": 90,
        },
    )
    assert edited.status_code == 200, edited.text
    preview = client.post(
        f"/api/v1/programs/assigned/{program_id}/cycle/week-type/preview",
        headers=headers,
        json={
            "expected_revision_number": edited.json()["current_revision_number"],
            "occurrence_weeks": [1, 4, 7],
        },
    )
    assert preview.status_code == 200, preview.text
    rows = {row["week_number"]: row["workouts"][0] for row in preview.json()["weeks"]}
    assert rows[1]["status"] == "completed" and rows[1]["changeable"] is False
    assert rows[4]["status"] == "in_progress" and rows[4]["changeable"] is False
    assert rows[7]["changeable"] is True
    assert [rows[week]["exercises"][0]["prescribed_reps"] for week in (1, 4, 7)] == ["6", "6", "12"]
    assert [len(rows[week]["exercises"]) for week in (1, 4, 7)] == [1, 1, 1]
    with get_session_context() as db:
        for week, (workout_id, set_id, reps) in recorded.items():
            workout = db.get(UserWorkout, workout_id)
            assert workout.status == ("completed" if week == 1 else "in_progress")
            assert workout.exercises[0].prescribed_reps == "6"
            result_set = db.get(UserWorkoutSet, set_id)
            assert result_set.actual_reps == reps
            assert result_set.is_completed is True


@pytest.mark.parametrize(
    ("scope", "affected"),
    [
        ({"occurrence_weeks": [8]}, {8}),
        ({"from_week": 8, "source_cycle_week": 2}, {8, 11, 14}),
    ],
)
def test_first_five_completed_weeks_keep_facts_after_week_eight_edit(
    client, monkeypatch, scope, affected
):
    headers, program_id, slot, exercise_id = assigned_cycle(client, k=3, n=16)
    for week in range(1, 6):
        current_day = TODAY + timedelta(weeks=week - 1)
        monkeypatch.setattr(routes, "recovery_today_for_user", lambda _user, day=current_day: day)
        workout = client.get("/api/v1/workouts/today", headers=headers)
        assert workout.status_code == 200, workout.text
        started = client.post(f"/api/v1/workouts/{workout.json()['id']}/start", headers=headers)
        assert started.status_code == 200, started.text
        for item in started.json()["exercises"][0]["sets"]:
            recorded = client.patch(
                f"/api/v1/workouts/sets/{item['id']}",
                headers=headers,
                json={
                    "actual_reps": 8,
                    "actual_weight": 40,
                    "rir": "2",
                    "is_completed": True,
                },
            )
            assert recorded.status_code == 200, recorded.text
        finished = client.post(f"/api/v1/workouts/{workout.json()['id']}/finish", headers=headers)
        assert finished.status_code == 200, finished.text

    def completed_facts():
        with get_session_context() as db:
            workouts = (
                db.query(UserWorkout)
                .filter_by(user_program_id=program_id, status="completed")
                .order_by(UserWorkout.week_number)
                .all()
            )
            return [
                (
                    workout.id,
                    workout.week_number,
                    workout.completed_at,
                    tuple(
                        (
                            item.id,
                            item.actual_reps,
                            item.actual_weight,
                            item.rir,
                            item.is_completed,
                            item.version,
                        )
                        for exercise in workout.exercises
                        for item in exercise.sets
                    ),
                )
                for workout in workouts
            ]

    before = completed_facts()
    assert [item[1] for item in before] == [1, 2, 3, 4, 5]
    assert sum(len(item[3]) for item in before) == 10
    assert sum(set_data[1] * set_data[2] for row in before for set_data in row[3]) == 3200

    request = {
        "expected_revision_number": revision(program_id),
        "effective_scope": "future_program",
        "day_number": 1,
        "target_template_exercise_id": slot,
        "exercise_id": exercise_id,
        "prescribed_sets": 3,
        "prescribed_reps": "12",
        "rest_seconds": 90,
        **scope,
    }
    endpoint = f"/api/v1/programs/assigned/{program_id}/exercises"
    applied = client.post(endpoint, headers=headers, json=request)
    assert applied.status_code == 200, applied.text
    stale = client.post(endpoint, headers=headers, json=request)
    assert stale.status_code == 409, stale.text
    assert completed_facts() == before

    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        for week in (2, 5, 8, 11, 14):
            plan = program_versioning._cycle_workout_plans(db, program, week)
            assert len(plan) == 1
            assert plan[0]["exercises"][0]["prescribed_reps"] == ("12" if week in affected else "7")
        assert (
            db.query(UserWorkout).filter_by(user_program_id=program_id, status="completed").count()
            == 5
        )
    preview = client.post(
        f"/api/v1/programs/assigned/{program_id}/cycle/week-type/preview",
        headers=headers,
        json={
            "expected_revision_number": applied.json()["current_revision_number"],
            "occurrence_weeks": [2, 5, 8, 11, 14],
        },
    )
    assert preview.status_code == 200, preview.text
    projected = {row["week_number"]: row["workouts"][0] for row in preview.json()["weeks"]}
    for week in (2, 5):
        assert projected[week]["status"] == "completed"
        assert projected[week]["changeable"] is False
        assert projected[week]["exercises"][0]["prescribed_reps"] == "7"
    for week in (8, 11, 14):
        assert projected[week]["exercises"][0]["prescribed_reps"] == (
            "12" if week in affected else "7"
        )
    assert completed_facts() == before
