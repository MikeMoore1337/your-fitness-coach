from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, time, timedelta
from hashlib import sha256

import pytest
from test_program_week_cycle import _auth, _payload

from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.program import ProgramTemplate, TrainingBlock, UserProgram, UserWorkout
from fitminiapp_api.models.user import User
from fitminiapp_api.services.program_versioning import (
    materialize_next_cycle_window,
    record_program_revision,
)
from fitminiapp_api.services.progression_guidance import (
    build_progression_guidance,
    parse_rep_target,
)


def _cycle(client, week_types):
    headers = _auth(client, 917001)
    payload = _payload(client, headers)
    exercise = next(
        item
        for item in client.get("/api/v1/programs/exercises", headers=headers).json()
        if item["metric_type"] == "strength"
    )
    payload["days"][0]["exercises"][0].update(
        exercise_id=exercise["id"], prescribed_sets=2, prescribed_reps="8-10"
    )
    payload["week_cycle"] = {
        "length_weeks": len(week_types),
        "week_types": week_types,
        "repeat": True,
    }
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    template_id = created.json()["template"]["id"]
    with get_session_context() as db:
        template = db.get(ProgramTemplate, template_id)
        metadata = deepcopy(template.program_metadata)
        metadata["coaching_rules"] = [
            {
                "kind": "double_progression",
                "scope": "program",
                "rep_target": {"kind": "range", "min_reps": 8, "max_reps": 10},
                "increment_value": 2.5,
                "increment_unit": "kg",
            }
        ]
        template.program_metadata = metadata
    assigned = client.post(
        f"/api/v1/programs/templates/{template_id}/assign-to-me",
        headers=headers,
        json={"start_date": today_msk().isoformat(), "duration_weeks": 16},
    )
    assert assigned.status_code == 200, assigned.text
    return headers, assigned.json()["user_program_id"]


def _workouts(program_id, through_week):
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        for week in range(1, through_week + 1, 4):
            materialize_next_cycle_window(
                db, program, through_date=program.start_date + timedelta(weeks=week - 1)
            )
        return {
            row.week_number: row.id
            for row in db.query(UserWorkout).filter_by(user_program_id=program_id).all()
        }


def _complete(workout_ids, weeks, *, high_weight_weeks=(), reps=10):
    with get_session_context() as db:
        for week in weeks:
            workout = db.get(UserWorkout, workout_ids[week])
            workout.status = "completed"
            workout.started_at = datetime.combine(workout.scheduled_date, time(10))
            workout.completed_at = datetime.combine(workout.scheduled_date, time(11))
            for row in workout.exercises[0].sets:
                row.is_completed = True
                row.actual_reps = reps
                row.actual_weight = 100 if week in high_weight_weeks else 40
                row.rir = "2"


def _guidance(program_id, workout_id):
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        workout = db.get(UserWorkout, workout_id)
        return build_progression_guidance(db, db.get(User, program.user_id), workout)[
            workout.exercises[0].id
        ]


@pytest.mark.parametrize(
    "same,other", [("heavy", "light"), ("medium", "heavy"), ("light", "medium")]
)
def test_repeated_week_type_uses_only_comparable_facts(client, same, other):
    _headers, program_id = _cycle(client, [same, other, same])
    workouts = _workouts(program_id, 7)
    _complete(workouts, range(1, 7), high_weight_weeks=(2, 5))
    result = _guidance(program_id, workouts[7])
    assert result["outcome"] == "consider_progressing", result
    assert result["suggested_weight"] == 42.5
    assert result["ruleset_version"] == "progression-guidance-v3"
    rule_material = json.dumps(
        {"ruleset_version": "progression-guidance-v3", "rule": result["proposal"]["rule_snapshot"]},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    assert result["proposal"]["rule_id"] == sha256(rule_material).hexdigest()
    assert [row["workout_id"] for row in result["evidence"]["sessions"]] == [
        workouts[6],
        workouts[4],
        workouts[3],
    ]
    evidence = result["proposal"]["source_evidence_ids"]
    assert all(
        f"workout:{workouts[5]}/" not in item and f"workout:{workouts[2]}/" not in item
        for item in evidence
    )


def test_incompatible_history_does_not_propose_a_weight(client):
    _headers, program_id = _cycle(client, ["heavy", "light", "heavy"])
    workouts = _workouts(program_id, 3)
    _complete(workouts, [1, 2], high_weight_weeks=(2,))
    result = _guidance(program_id, workouts[3])
    assert result["outcome"] in {"hold", "review"}
    assert result["suggested_weight"] is None
    assert [row["workout_id"] for row in result["evidence"]["sessions"]] == [workouts[1]]
    assert all(
        f"workout:{workouts[2]}/" not in item for item in result["proposal"]["source_evidence_ids"]
    )


def test_untyped_week_does_not_use_typed_history_in_a_mixed_cycle(client):
    _headers, program_id = _cycle(client, ["heavy", None, "heavy"])
    workouts = _workouts(program_id, 5)
    _complete(workouts, [1, 2, 3, 4], high_weight_weeks=(1, 3, 4))
    result = _guidance(program_id, workouts[5])
    assert [row["workout_id"] for row in result["evidence"]["sessions"]] == [workouts[2]]
    assert all(
        f"workout:{workouts[week]}/" not in item
        for week in (1, 3, 4)
        for item in result["proposal"]["source_evidence_ids"]
    )


def test_untyped_new_phase_does_not_use_typed_history(client):
    headers, program_id = _cycle(client, ["heavy", "heavy", "heavy"])
    workouts = _workouts(program_id, 7)
    _complete(workouts, [1, 2, 3], high_weight_weeks=(1, 2, 3))
    changed = client.patch(
        f"/api/v1/programs/assigned/{program_id}/cycle",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "effective_from_week": 7,
            "week_types": [None, None, None],
        },
    )
    assert changed.status_code == 200, changed.text
    guidance = _guidance(program_id, workouts[7])
    assert guidance["evidence"]["sessions"] == []
    assert guidance["suggested_weight"] is None


def test_week_type_preview_and_scoped_revision_preserve_started_history(client):
    from fitminiapp_api.models.program import ProgramRevision
    from fitminiapp_api.services.program_versioning import workout_cycle_week_type

    headers, program_id = _cycle(client, ["heavy", None, "heavy"])
    workouts = _workouts(program_id, 8)
    _complete(workouts, [2])
    with get_session_context() as db:
        started = db.get(UserWorkout, workouts[5])
        started.status = "in_progress"
        started.started_at = datetime.combine(started.scheduled_date, time(10))
        completed = db.get(UserWorkout, workouts[2])
        fact = completed.exercises[0].sets[0]
        before = (fact.id, fact.actual_weight, fact.actual_reps, fact.version)
        revision = db.get(UserProgram, program_id).current_revision_number

    path = f"/api/v1/programs/assigned/{program_id}/cycle/week-type"
    payload = {
        "expected_revision_number": revision,
        "week_type": "light",
        "occurrence_weeks": [2, 5, 8],
    }
    preview = client.post(path + "/preview", headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    assert [item["week_number"] for item in preview.json()["weeks"]] == [2, 5, 8]
    assert [item["workouts"][0]["changeable"] for item in preview.json()["weeks"]] == [
        False,
        False,
        True,
    ]
    with get_session_context() as db:
        assert db.get(UserProgram, program_id).current_revision_number == revision

    applied = client.post(path, headers=headers, json=payload)
    assert applied.status_code == 200, applied.text
    assert applied.json()["current_revision_number"] == revision + 1
    assert client.post(path, headers=headers, json=payload).status_code == 409
    assert client.post(path + "/preview", headers=headers, json=payload).status_code == 409
    other = _auth(client, 918099)
    assert client.post(path + "/preview", headers=other, json=payload).status_code in (403, 404)

    with get_session_context() as db:
        revisions = (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program_id)
            .order_by(ProgramRevision.revision_number)
            .all()
        )
        rows = [db.get(UserWorkout, workouts[week]) for week in (2, 5, 8)]
        assert [workout_cycle_week_type(db, row, revisions) for row in rows] == [
            (None, True),
            (None, True),
            ("light", True),
        ]
        fact = rows[0].exercises[0].sets[0]
        assert (fact.id, fact.actual_weight, fact.actual_reps, fact.version) == before
        assert rows[1].status == "in_progress"


def test_scoped_exercise_change_skips_protected_workouts(client):
    headers, program_id = _cycle(client, ["heavy", "light", "heavy"])
    workouts = _workouts(program_id, 8)
    _complete(workouts, [2])
    with get_session_context() as db:
        started = db.get(UserWorkout, workouts[5])
        started.status = "in_progress"
        started.started_at = datetime.combine(started.scheduled_date, time(10))
        exercise = db.get(UserWorkout, workouts[8]).exercises[0]
        slot, exercise_id = exercise.source_template_exercise_id, exercise.exercise_id
        completed = db.get(UserWorkout, workouts[2]).exercises[0]
        facts = [
            (item.id, item.actual_weight, item.actual_reps, item.version) for item in completed.sets
        ]
    body = {
        "expected_revision_number": 1,
        "effective_scope": "future_program",
        "occurrence_weeks": [2, 5, 8],
        "skip_protected": True,
        "day_number": 1,
        "target_template_exercise_id": slot,
        "exercise_id": exercise_id,
        "prescribed_sets": 2,
        "prescribed_reps": "12",
        "rest_seconds": 90,
    }
    result = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises", headers=headers, json=body
    )
    assert result.status_code == 200, result.text
    assert result.json()["workouts_updated"] == 1
    with get_session_context() as db:
        assert db.get(UserWorkout, workouts[8]).exercises[0].prescribed_reps == "12"
        assert db.get(UserWorkout, workouts[5]).exercises[0].prescribed_reps == "8-10"
        completed = db.get(UserWorkout, workouts[2]).exercises[0]
        assert [
            (item.id, item.actual_weight, item.actual_reps, item.version) for item in completed.sets
        ] == facts


def test_future_source_repeats_skip_started_occurrence(client):
    headers, program_id = _cycle(client, ["heavy", None, "light"])
    workouts = _workouts(program_id, 11)
    with get_session_context() as db:
        started = db.get(UserWorkout, workouts[7])
        started.status = "in_progress"
        started.started_at = datetime.combine(started.scheduled_date, time(10))
        exercise = started.exercises[0]
        slot, exercise_id = exercise.source_template_exercise_id, exercise.exercise_id
    body = {
        "expected_revision_number": 1,
        "effective_scope": "future_program",
        "from_week": 4,
        "source_cycle_week": 1,
        "skip_protected": True,
        "day_number": 1,
        "target_template_exercise_id": slot,
        "exercise_id": exercise_id,
        "prescribed_sets": 2,
        "prescribed_reps": "12",
        "rest_seconds": 90,
    }
    result = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises", headers=headers, json=body
    )
    assert result.status_code == 200, result.text
    with get_session_context() as db:
        assert db.get(UserWorkout, workouts[4]).exercises[0].prescribed_reps == "12"
        assert db.get(UserWorkout, workouts[7]).exercises[0].prescribed_reps == "8-10"
        assert db.get(UserWorkout, workouts[10]).exercises[0].prescribed_reps == "12"


def test_week_type_preview_expands_only_requested_source_week(client):
    headers, program_id = _cycle(client, ["heavy", None, "heavy"])
    payload = {
        "expected_revision_number": 1,
        "week_type": None,
        "from_week": 4,
        "source_cycle_week": 1,
    }
    response = client.post(
        f"/api/v1/programs/assigned/{program_id}/cycle/week-type/preview",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 200, response.text
    assert [week["week_number"] for week in response.json()["weeks"]] == [4, 7, 10, 13, 16]
    assert response.json()["total_weeks"] == 5


def test_today_exposes_saved_type_without_defaulting_unset_weeks(client):
    headers, program_id = _cycle(client, ["heavy", None, "light"])
    today = client.get("/api/v1/workouts/today", headers=headers)
    assert today.status_code == 200, today.text
    assert today.json()["week_type"] == "heavy" and today.json()["week_type_known"] is True
    changed = client.post(
        f"/api/v1/programs/assigned/{program_id}/cycle/week-type",
        headers=headers,
        json={"expected_revision_number": 1, "week_type": None, "occurrence_weeks": [1]},
    )
    assert changed.status_code == 200, changed.text
    today = client.get("/api/v1/workouts/today", headers=headers)
    assert today.status_code == 200, today.text
    assert today.json()["week_type"] is None and today.json()["week_type_known"] is True


def test_duration_preview_and_revision_extend_cycle_without_losing_history(client):
    headers, program_id = _cycle(client, ["heavy", None, "light"])
    workouts = _workouts(program_id, 3)
    _complete(workouts, [1])
    payload = {"expected_revision_number": 1, "effective_from_week": 4, "duration_weeks": 20}
    path = f"/api/v1/programs/assigned/{program_id}/cycle"
    preview = client.post(path + "/duration/preview", headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    assert [
        item["week_number"] for item in preview.json()["weeks"] if item["change"] == "added"
    ] == [17, 18, 19, 20]
    revised = client.patch(path, headers=headers, json=payload)
    assert revised.status_code == 200, revised.text
    assert client.post(path + "/duration/preview", headers=headers, json=payload).status_code == 409
    with get_session_context() as db:
        assert db.get(UserProgram, program_id).duration_weeks == 20
        assert db.get(UserWorkout, workouts[1]).status == "completed"


def test_disabling_cycle_freezes_future_plan_and_preserves_started_history(client):
    from fitminiapp_api.models.program import ProgramRevision
    from fitminiapp_api.services.program_versioning import (
        _cycle_workout_plans,
        workout_cycle_week_type,
    )

    headers, program_id = _cycle(client, ["heavy", None, "light"])
    workouts = _workouts(program_id, 8)
    _complete(workouts, [2])
    with get_session_context() as db:
        started = db.get(UserWorkout, workouts[5])
        started.status = "in_progress"
        started.started_at = datetime.combine(started.scheduled_date, time(10))
        program = db.get(UserProgram, program_id)
        before = {week: _cycle_workout_plans(db, program, week) for week in range(4, 17)}
        fact = db.get(UserWorkout, workouts[2]).exercises[0].sets[0]
        history = (fact.id, fact.actual_weight, fact.actual_reps, fact.version)
    path = f"/api/v1/programs/assigned/{program_id}/cycle/disable"
    payload = {"expected_revision_number": 1, "effective_from_week": 4}
    preview = client.post(path + "/preview", headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    assert preview.json()["total_weeks"] == 13
    assert preview.json()["weeks"][1]["workouts"][0]["changeable"] is False
    result = client.post(path, headers=headers, json=payload)
    assert result.status_code == 200, result.text
    assert client.post(path, headers=headers, json=payload).status_code == 409
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        revisions = (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program_id)
            .order_by(ProgramRevision.revision_number)
            .all()
        )
        for week in range(4, 17):
            after = _cycle_workout_plans(db, program, week)
            assert [(item["scheduled_date"], item["exercises"]) for item in after] == [
                (item["scheduled_date"], item["exercises"]) for item in before[week]
            ]
        assert workout_cycle_week_type(db, db.get(UserWorkout, workouts[5]), revisions) == (
            None,
            True,
        )
        assert workout_cycle_week_type(db, db.get(UserWorkout, workouts[7]), revisions) == (
            None,
            True,
        )
        fact = db.get(UserWorkout, workouts[2]).exercises[0].sets[0]
        assert (fact.id, fact.actual_weight, fact.actual_reps, fact.version) == history


def test_disabling_cycle_does_not_reapply_older_overrides(client):
    from fitminiapp_api.services.program_versioning import _cycle_workout_plans

    headers, program_id = _cycle(client, ["heavy", "light", "heavy"])
    workouts = _workouts(program_id, 8)
    with get_session_context() as db:
        exercise = db.get(UserWorkout, workouts[8]).exercises[0]
        slot, exercise_id = exercise.source_template_exercise_id, exercise.exercise_id
    url = f"/api/v1/programs/assigned/{program_id}/exercises"
    common = {
        "effective_scope": "future_program",
        "day_number": 1,
        "target_template_exercise_id": slot,
        "exercise_id": exercise_id,
        "prescribed_sets": 2,
        "rest_seconds": 90,
    }
    first = client.post(
        url,
        headers=headers,
        json={
            **common,
            "expected_revision_number": 1,
            "occurrence_weeks": [8],
            "prescribed_reps": "6",
        },
    )
    assert first.status_code == 200, first.text
    second = client.post(
        url,
        headers=headers,
        json={
            **common,
            "expected_revision_number": 2,
            "from_week": 5,
            "source_cycle_week": 2,
            "prescribed_reps": "10",
        },
    )
    assert second.status_code == 200, second.text
    disabled = client.post(
        f"/api/v1/programs/assigned/{program_id}/cycle/disable",
        headers=headers,
        json={"expected_revision_number": 3, "effective_from_week": 7},
    )
    assert disabled.status_code == 200, disabled.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        assert _cycle_workout_plans(db, program, 8)[0]["exercises"][0]["prescribed_reps"] == "10"


def test_reenable_after_disable_preserves_future_plan(client):
    from fitminiapp_api.models.program import ProgramRevision
    from fitminiapp_api.services.program_versioning import (
        _cycle_workout_plans,
        workout_cycle_week_type,
    )

    headers, program_id = _cycle(client, ["heavy", None, "light"])
    workouts = _workouts(program_id, 8)
    disabled = client.post(
        f"/api/v1/programs/assigned/{program_id}/cycle/disable",
        headers=headers,
        json={"expected_revision_number": 1, "effective_from_week": 4},
    )
    assert disabled.status_code == 200, disabled.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        before = _cycle_workout_plans(db, program, 7)[0]["exercises"]
    enabled = client.post(
        f"/api/v1/programs/assigned/{program_id}/cycle/enable",
        headers=headers,
        json={
            "expected_revision_number": 2,
            "effective_from_week": 7,
            "duration_weeks": 16,
            "week_cycle": {"length_weeks": 2, "repeat": True, "week_types": ["light", "heavy"]},
        },
    )
    assert enabled.status_code == 200, enabled.text
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        revisions = (
            db.query(ProgramRevision)
            .filter_by(user_program_id=program_id)
            .order_by(ProgramRevision.revision_number)
            .all()
        )
        assert _cycle_workout_plans(db, program, 7)[0]["exercises"] == before
        assert workout_cycle_week_type(db, db.get(UserWorkout, workouts[7]), revisions) == (
            "light",
            True,
        )


def test_future_revision_keeps_compatible_completed_facts(client):
    headers, program_id = _cycle(client, ["heavy", "light", "heavy"])
    workouts = _workouts(program_id, 7)
    _complete(workouts, [1, 2, 3], high_weight_weeks=(2,))
    with get_session_context() as db:
        before = [
            (row.id, row.actual_weight, row.actual_reps, row.rir)
            for week in (1, 3)
            for row in db.get(UserWorkout, workouts[week]).exercises[0].sets
        ]
    changed = client.patch(
        f"/api/v1/programs/assigned/{program_id}/cycle",
        headers=headers,
        json={"expected_revision_number": 1, "effective_from_week": 7, "duration_weeks": 17},
    )
    assert changed.status_code == 200, changed.text
    result = _guidance(program_id, workouts[7])
    assert result["suggested_weight"] == 42.5, result
    assert [row["workout_id"] for row in result["evidence"]["sessions"]] == [
        workouts[3],
        workouts[1],
    ]
    with get_session_context() as db:
        assert db.get(UserWorkout, workouts[7]).plan_revision_number == 2
        assert [
            (row.id, row.actual_weight, row.actual_reps, row.rir)
            for week in (1, 3)
            for row in db.get(UserWorkout, workouts[week]).exercises[0].sets
        ] == before


def test_editing_week_eight_preserves_history_and_later_iteration(client):
    headers, program_id = _cycle(client, ["heavy", "light", "heavy"])
    workouts = _workouts(program_id, 8)
    _complete(workouts, range(1, 7), high_weight_weeks=(2, 5))
    with get_session_context() as db:
        exercise = db.get(UserWorkout, workouts[8]).exercises[0]
        slot, exercise_id = exercise.source_template_exercise_id, exercise.exercise_id
        before = [
            (row.id, row.actual_weight, row.actual_reps, row.rir)
            for week in range(1, 7)
            for row in db.get(UserWorkout, workouts[week]).exercises[0].sets
        ]
    body = {
        "expected_revision_number": 1,
        "effective_scope": "future_program",
        "day_number": 1,
        "target_template_exercise_id": slot,
        "exercise_id": exercise_id,
        "prescribed_sets": 2,
        "prescribed_reps": "12",
        "rest_seconds": 90,
        "occurrence_weeks": [8],
    }
    url = f"/api/v1/programs/assigned/{program_id}/exercises"
    changed = client.post(url, headers=headers, json=body)
    assert changed.status_code == 200, changed.text
    assert client.post(url, headers=headers, json=body).status_code == 409
    workouts = _workouts(program_id, 10)
    result = _guidance(program_id, workouts[10])
    assert result["suggested_weight"] == 42.5, result
    assert [row["workout_id"] for row in result["evidence"]["sessions"]] == [
        workouts[6],
        workouts[4],
        workouts[3],
    ]
    with get_session_context() as db:
        assert db.get(UserWorkout, workouts[8]).exercises[0].prescribed_reps == "12"
        assert db.get(UserWorkout, workouts[10]).plan_revision_number == 2
        assert [
            (row.id, row.actual_weight, row.actual_reps, row.rir)
            for week in range(1, 7)
            for row in db.get(UserWorkout, workouts[week]).exercises[0].sets
        ] == before


@pytest.mark.parametrize("change", ["position", "prescription", "set_kind", "exercise", "slot"])
def test_changed_history_cannot_drive_promotion(client, change):
    _headers, program_id = _cycle(client, ["heavy", "light", "heavy"])
    workouts = _workouts(program_id, 7)
    _complete(workouts, [1, 3])
    with get_session_context() as db:
        for week in (1, 3):
            exercise = db.get(UserWorkout, workouts[week]).exercises[0]
            if change == "position":
                exercise.sort_order += 1
            elif change == "prescription":
                exercise.prescribed_reps = "6-8"
            elif change == "set_kind":
                exercise.sets[0].set_kind = "warmup"
            elif change == "slot":
                exercise.source_template_exercise_id += 100000
            else:
                exercise.exercise_id = (
                    db.query(Exercise.id).filter(Exercise.id != exercise.exercise_id).first()[0]
                )
    result = _guidance(program_id, workouts[7])
    assert result["outcome"] in {"hold", "review"}, result
    assert result["suggested_weight"] is None
    assert result["proposal"]["source_evidence_ids"] == []


def test_changed_rule_revision_does_not_reuse_old_facts(client):
    _headers, program_id = _cycle(client, ["heavy", "light", "heavy"])
    workouts = _workouts(program_id, 7)
    _complete(workouts, [1, 3])
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        metadata = deepcopy(program.template.program_metadata)
        metadata["coaching_rules"][0]["increment_value"] = 5
        program.template.program_metadata = metadata
        revision = record_program_revision(
            db,
            program,
            actor=db.get(User, program.user_id),
            change_kind="plan_updated",
            changed_fields={},
        )
        db.get(UserWorkout, workouts[7]).plan_revision_number = revision.revision_number
    result = _guidance(program_id, workouts[7])
    assert result["outcome"] in {"hold", "review"}, result
    assert result["suggested_weight"] is None
    assert result["proposal"]["source_evidence_ids"] == []


def test_changed_future_cycle_does_not_reclassify_old_workouts(client):
    headers, program_id = _cycle(client, ["heavy", "light", "heavy"])
    workouts = _workouts(program_id, 7)
    _complete(workouts, range(1, 7), high_weight_weeks=(2, 5))
    changed = client.patch(
        f"/api/v1/programs/assigned/{program_id}/cycle",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "effective_from_week": 7,
            "week_types": ["light", "heavy", "heavy"],
        },
    )
    assert changed.status_code == 200, changed.text
    result = _guidance(program_id, workouts[7])
    assert result["evidence"]["week_type"] == "light"
    assert result["suggested_weight"] == 102.5, result
    assert [row["workout_id"] for row in result["evidence"]["sessions"]] == [
        workouts[5],
        workouts[2],
    ]


def test_sixteen_week_cycle_uses_real_facts_from_multiple_iterations(client):
    _headers, program_id = _cycle(client, ["heavy", "light", "heavy"])
    workouts = _workouts(program_id, 16)
    _complete(workouts, range(1, 16), high_weight_weeks=(2, 5, 8, 11, 14))
    result = _guidance(program_id, workouts[16])
    assert result["suggested_weight"] == 42.5, result
    assert result["evidence"]["comparable_session_count"] == 10
    assert [item["workout_id"] for item in result["evidence"]["sessions"]] == [
        workouts[15],
        workouts[13],
        workouts[12],
    ]
    assert all(
        f"workout:{workouts[14]}/" not in item for item in result["proposal"]["source_evidence_ids"]
    )


def test_missing_plan_revision_fails_closed(client):
    _headers, program_id = _cycle(client, ["heavy", "light", "heavy"])
    workouts = _workouts(program_id, 3)
    _complete(workouts, [1, 2])
    with get_session_context() as db:
        db.get(UserWorkout, workouts[3]).plan_revision_number = 999
    result = _guidance(program_id, workouts[3])
    assert result["outcome"] == "review"
    assert result["suggested_weight"] is None
    assert "week_type_unverifiable" in result["proposal"]["reason_codes"]
    assert result["proposal"]["source_evidence_ids"] == []


def test_typed_proposal_conflict_and_duplicate_confirm_keep_history(client):
    headers, program_id = _cycle(client, ["heavy", "light", "heavy"])
    workouts = _workouts(program_id, 4)
    _complete(workouts, [1, 2, 3], high_weight_weeks=(2,))
    list_url = f"/api/v1/programs/assigned/{program_id}/progression-proposals"
    response = client.get(list_url, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["target_workout_id"] == workouts[4]
    proposal = response.json()["exercises"][0]["guidance"]["proposal"]
    assert proposal["proposed_weight"] == 42.5
    versions = {str(item["set_id"]): item["set_version"] for item in proposal["target_set_updates"]}
    body = {
        "decision": "confirm",
        "workout_id": workouts[4],
        "exercise_id": proposal["target_exercise_id"],
        "expected_revision_number": proposal["target_revision_number"],
        "expected_set_versions": {key: value + 1 for key, value in versions.items()},
    }
    review_url = f"{list_url}/{proposal['proposal_id']}/review"
    assert client.post(review_url, headers=headers, json=body).status_code == 409
    body["expected_set_versions"] = versions
    confirmed = client.post(review_url, headers=headers, json=body)
    assert confirmed.status_code == 200, confirmed.text
    replayed = client.post(review_url, headers=headers, json=body)
    assert replayed.status_code == 200, replayed.text
    assert replayed.json() == confirmed.json()
    with get_session_context() as db:
        target = db.get(UserWorkout, workouts[4])
        assert [float(item.actual_weight) for item in target.exercises[0].sets] == [42.5, 42.5]
        assert all(
            item.actual_weight == 100 for item in db.get(UserWorkout, workouts[2]).exercises[0].sets
        )


@pytest.mark.parametrize("missing", ["rir", "set"])
def test_missing_rir_or_incomplete_facts_cannot_drive_promotion(client, missing):
    _headers, program_id = _cycle(client, ["heavy", "light", "heavy"])
    workouts = _workouts(program_id, 7)
    _complete(workouts, [1, 3])
    with get_session_context() as db:
        for week in (1, 3):
            sets = db.get(UserWorkout, workouts[week]).exercises[0].sets
            if missing == "rir":
                for row in sets:
                    row.rir = None
            else:
                sets[0].actual_weight = None
    result = _guidance(program_id, workouts[7])
    assert result["outcome"] in {"hold", "review"}, result
    assert result["suggested_weight"] is None


def test_latest_incomplete_same_type_does_not_promote_from_older_facts(client):
    _headers, program_id = _cycle(client, ["heavy", "light", "heavy"])
    workouts = _workouts(program_id, 7)
    _complete(workouts, [1, 3, 4, 6])
    with get_session_context() as db:
        db.get(UserWorkout, workouts[6]).exercises[0].sets[0].actual_weight = None
    result = _guidance(program_id, workouts[7])
    assert result["outcome"] == "review", result
    assert result["suggested_weight"] is None
    assert "incomplete_session_facts" in result["evidence"]["reason_keys"]
    assert [item["workout_id"] for item in result["evidence"]["sessions"]] == [
        workouts[6],
        workouts[4],
        workouts[3],
    ]
    assert all(
        f"workout:{workouts[1]}/" not in value
        for value in result["proposal"]["source_evidence_ids"]
    )


def test_missing_rir_is_not_reported_as_missing_same_type_history(client):
    _headers, program_id = _cycle(client, ["heavy", "light", "heavy"])
    workouts = _workouts(program_id, 7)
    _complete(workouts, [1, 3, 4])
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        metadata = deepcopy(program.template.program_metadata)
        metadata["coaching_rules"] = [
            {
                "kind": "rir_rpe",
                "effort_target": {"kind": "rir", "value": 2},
                "increment_value": 2.5,
                "increment_unit": "kg",
            }
        ]
        program.template.program_metadata = metadata
        revision = program.revisions[0]
        snapshot = deepcopy(revision.snapshot)
        snapshot["program"]["program_metadata"] = metadata
        revision.snapshot = snapshot
        for week in (1, 3, 4):
            for item in db.get(UserWorkout, workouts[week]).exercises[0].sets:
                item.rir = None
    result = _guidance(program_id, workouts[7])
    assert result["outcome"] == "review"
    assert result["suggested_weight"] is None
    assert "missing_rir_evidence" in result["proposal"]["reason_codes"]
    assert result["detail"] == (
        "Запас повторов (RIR) записан не для каждого подхода, который учитывается в прогрессии."
    )
    assert "insufficient_same_type_history" not in result["proposal"]["reason_codes"]
    assert result["evidence"]["comparable_session_count"] == 3


def test_no_applicable_rule_does_not_claim_unused_factual_evidence(client):
    _headers, program_id = _cycle(client, ["heavy", "light", "heavy"])
    workouts = _workouts(program_id, 7)
    _complete(workouts, [3, 4])
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        metadata = deepcopy(program.template.program_metadata)
        metadata["coaching_rules"][0].update(week_start=1, week_end=1)
        program.template.program_metadata = metadata
        revision = program.revisions[0]
        snapshot = deepcopy(revision.snapshot)
        snapshot["program"]["program_metadata"] = metadata
        revision.snapshot = snapshot
    result = _guidance(program_id, workouts[7])
    assert result["outcome"] == "review"
    assert result["proposal"]["reason_codes"] == ["no_applicable_coaching_rule"]
    assert result["proposal"]["source_evidence_ids"] == []
    assert result["evidence"]["sessions"] == []


def test_incompatible_recent_same_type_stops_reuse_of_older_history(client):
    _headers, program_id = _cycle(client, ["heavy", "light", "heavy"])
    workouts = _workouts(program_id, 7)
    _complete(workouts, [1, 3, 4, 6])
    with get_session_context() as db:
        db.get(UserWorkout, workouts[6]).exercises[0].prescribed_reps = "6-8"
    result = _guidance(program_id, workouts[7])
    assert result["outcome"] in {"hold", "review"}, result
    assert result["suggested_weight"] is None
    assert result["proposal"]["source_evidence_ids"] == []


def test_new_block_does_not_reuse_other_block_history(client):
    _headers, program_id = _cycle(client, ["heavy", "light", "heavy"])
    workouts = _workouts(program_id, 7)
    _complete(workouts, [1, 3])
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        target = db.get(UserWorkout, workouts[7])
        db.add(
            TrainingBlock(
                user_program_id=program_id,
                title="Новый блок",
                purpose="Новый контекст",
                start_date=target.scheduled_date,
                end_date=target.scheduled_date + timedelta(days=6),
                status="planned",
            )
        )
        db.flush()
        revision = record_program_revision(
            db,
            program,
            actor=db.get(User, program.user_id),
            change_kind="block_created",
            changed_fields={},
        )
        target.plan_revision_number = revision.revision_number
    result = _guidance(program_id, workouts[7])
    assert result["outcome"] in {"hold", "review"}, result
    assert result["suggested_weight"] is None
    assert result["proposal"]["source_evidence_ids"] == []


def test_type_analytics_is_additional_and_preserves_global_totals(client, monkeypatch):
    from fitminiapp_api.services import analytics, period_bounds

    headers, program_id = _cycle(client, ["heavy", "light", "heavy"])
    workouts = _workouts(program_id, 7)
    _complete(workouts, range(1, 7), high_weight_weeks=(2, 5))
    fake_today = today_msk() + timedelta(weeks=6)
    monkeypatch.setattr(period_bounds, "today_for_user", lambda _user: fake_today)
    monkeypatch.setattr(analytics, "today_for_user", lambda _user: fake_today)
    root = "/api/v1/workouts/progress"
    global_before = client.get(root, headers=headers)
    all_before = client.get(root + "/training-analytics?period_days=90", headers=headers)
    assert global_before.status_code == all_before.status_code == 200
    heavy = client.get(
        root + "/training-analytics/week-type?period_days=90&week_type=heavy", headers=headers
    )
    light = client.get(
        root + "/training-analytics/week-type?period_days=90&week_type=light", headers=headers
    )
    assert heavy.status_code == light.status_code == 200, (heavy.text, light.text)
    assert (
        heavy.json()["completed_workout_count"],
        heavy.json()["completed_set_count"],
        heavy.json()["external_load_volume_kg"],
    ) == (4, 8, 3200)
    assert (
        light.json()["completed_workout_count"],
        light.json()["completed_set_count"],
        light.json()["external_load_volume_kg"],
    ) == (2, 4, 4000)
    assert {row["workout_id"] for row in heavy.json()["exercises"][0]["sessions"]} == {
        workouts[w] for w in (1, 3, 4, 6)
    }
    assert client.get(root, headers=headers).json() == global_before.json()
    assert (
        client.get(root + "/training-analytics?period_days=90", headers=headers).json()
        == all_before.json()
    )
    assert all_before.json()["completed_workout_count"] == 6
    assert all_before.json()["completed_set_count"] == 12
    assert all_before.json()["external_load_volume_kg"] == 7200
    assert global_before.json()["personal_records"][0]["max_weight_kg"] == 100
    assert (
        client.get(
            root + "/training-analytics/week-type?week_type=deload", headers=headers
        ).status_code
        == 422
    )
    other = _auth(client, 917002)
    assert (
        client.get(root + "/training-analytics/week-type?week_type=heavy", headers=other).json()[
            "completed_workout_count"
        ]
        == 0
    )


def _configure_source_template(template_id):
    # The week-cycle editor is not yet available; use the existing backend contract in the fixture.
    with get_session_context() as db:
        template = db.get(ProgramTemplate, template_id)
        target = parse_rep_target(template.days[0].exercises[0].prescribed_reps)
        assert target is not None
        metadata = deepcopy(template.program_metadata or {})
        metadata["week_cycle"] = {
            "schema_version": 1,
            "length_weeks": 3,
            "week_types": ["heavy", "light", "heavy"],
            "repeat": True,
        }
        metadata["coaching_rules"] = [
            {
                "kind": "double_progression",
                "scope": "program",
                "rep_target": {
                    "kind": "range",
                    "min_reps": target.minimum,
                    "max_reps": target.maximum,
                },
                "increment_value": 2.5,
                "increment_unit": "kg",
            }
        ]
        template.program_metadata = metadata
        return target.maximum


def _source_workouts(program_id):
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        for week in range(1, 8, 4):
            materialize_next_cycle_window(
                db, program, through_date=program.start_date + timedelta(weeks=week - 1)
            )
        rows = (
            db.query(UserWorkout)
            .filter_by(user_program_id=program_id)
            .order_by(UserWorkout.week_number, UserWorkout.day_number, UserWorkout.id)
            .all()
        )
        first_day = rows[0].day_number
        return {row.week_number: row.id for row in rows if row.day_number == first_day}


def _assert_typed_source_history(program_id, reps):
    workouts = _source_workouts(program_id)
    _complete(workouts, range(1, 7), high_weight_weeks=(2, 5), reps=reps)
    result = _guidance(program_id, workouts[7])
    assert result["evidence"]["week_type"] == "heavy"
    assert result["suggested_weight"] == 42.5, json.dumps(result, ensure_ascii=False, default=str)
    assert [item["workout_id"] for item in result["evidence"]["sessions"]] == [
        workouts[6],
        workouts[4],
        workouts[3],
    ]
    assert all(
        f"workout:{workouts[week]}/" not in source
        for week in (2, 5)
        for source in result["proposal"]["source_evidence_ids"]
    )


@pytest.mark.parametrize("source", ["generated", "imported"])
def test_typed_generated_and_imported_programs_isolate_factual_history(client, source):
    headers = _auth(client, 917010)
    if source == "generated":
        from test_program_generator import _preview

        preview = _preview(client, headers)
        confirmed = client.post(
            "/api/v1/programs/generator/confirm",
            headers=headers,
            json={"draft_token": preview.json()["draft_token"]},
        )
        assert confirmed.status_code == 200, confirmed.text
        template = confirmed.json()["template"]
        assert template["provenance_type"] == "SOURCE_ADAPTATION"
    else:
        from test_program_import import _csv_payload, _upload, _valid_row

        exercise = next(
            item
            for item in client.get("/api/v1/programs/exercises", headers=headers).json()
            if item["slug"] == "squat"
        )
        source_bytes = _csv_payload(
            [_valid_row(exercise_name=exercise["title"], exercise_slug=exercise["slug"])]
        )
        preview = _upload(client, headers, "program.csv", source_bytes)
        assert preview.status_code == 201, preview.text
        assert preview.json()["summary"]["blocking_issue_count"] == 0, preview.json()
        confirmed = client.post(
            f"/api/v1/programs/imports/{preview.json()['id']}/confirm", headers=headers
        )
        assert confirmed.status_code == 200, confirmed.text
        template = confirmed.json()["template"]
        assert template["provenance"]["source_type"] == "file_upload"

    reps = _configure_source_template(template["id"])
    assigned = client.post(
        f"/api/v1/programs/templates/{template['id']}/assign-to-me",
        headers=headers,
        json={
            "start_date": today_msk().isoformat(),
            "duration_weeks": 16,
            "replace_active": source == "generated",
        },
    )
    assert assigned.status_code == 200, assigned.text
    _assert_typed_source_history(assigned.json()["user_program_id"], reps)


def test_typed_coach_assignment_keeps_athlete_isolation_and_comparable_history(client):
    from test_coach_program_rollout import _setup_coach_clients, _template_payload

    coach, athletes, clients = _setup_coach_clients(client, count=1)
    exercises = client.get("/api/v1/programs/exercises", headers=coach).json()
    exercise_id = next(item["id"] for item in exercises if item["metric_type"] == "strength")
    payload = _template_payload(
        exercise_id, title="Типы недель тренера", sets=2, telegram_user_id=clients[0][1]
    )
    payload["week_cycle"] = {
        "length_weeks": 3,
        "week_types": ["heavy", "light", "heavy"],
        "repeat": True,
    }
    created = client.post("/api/v1/programs/templates", headers=coach, json=payload)
    assert created.status_code == 200, created.text
    template_id = created.json()["template"]["id"]
    reps = _configure_source_template(template_id)
    assigned = client.post(
        f"/api/v1/coach/clients/{clients[0][0]}/templates/{template_id}/assign",
        headers=coach,
        json={"start_date": today_msk().isoformat(), "duration_weeks": 16},
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["user_program_id"]
    _assert_typed_source_history(program_id, reps)
    url = f"/api/v1/programs/assigned/{program_id}/progression-proposals"
    coach_result = client.get(url, headers=coach)
    athlete_result = client.get(url, headers=athletes[0])
    assert coach_result.status_code == athlete_result.status_code == 200
    assert coach_result.json() == athlete_result.json()
    assert coach_result.json()["exercises"][0]["guidance"]["evidence"]["week_type"] == "heavy"
    outsider = _auth(client, 917011)
    assert client.get(url, headers=outsider).status_code in (403, 404)


def test_cycle_revision_respects_coach_relationship_and_athlete_isolation(client):
    from test_coach_program_rollout import _setup_coach_clients, _template_payload

    from fitminiapp_api.models.user import CoachClient

    coach, athletes, clients = _setup_coach_clients(client, count=1)
    exercise = next(
        item
        for item in client.get("/api/v1/programs/exercises", headers=coach).json()
        if item["metric_type"] == "strength"
    )
    payload = _template_payload(
        exercise["id"], title="План клиента", sets=2, telegram_user_id=clients[0][1]
    )
    payload["week_cycle"] = {
        "length_weeks": 3,
        "repeat": True,
        "week_types": ["heavy", None, "light"],
    }
    created = client.post("/api/v1/programs/templates", headers=coach, json=payload)
    assert created.status_code == 200, created.text
    assigned = client.post(
        f"/api/v1/coach/clients/{clients[0][0]}/templates/{created.json()['template']['id']}/assign",
        headers=coach,
        json={"duration_weeks": 16},
    )
    assert assigned.status_code == 200, assigned.text
    path = f"/api/v1/programs/assigned/{assigned.json()['user_program_id']}/cycle/week-type"
    change = {"expected_revision_number": 1, "week_type": "light", "occurrence_weeks": [7]}
    outsider = _auth(client, 918999)
    assert client.post(path + "/preview", headers=athletes[0], json=change).status_code == 200
    assert client.post(path + "/preview", headers=outsider, json=change).status_code in (403, 404)
    assert client.post(path, headers=coach, json=change).status_code == 200
    with get_session_context() as db:
        link = db.query(CoachClient).filter_by(client_user_id=clients[0][0]).one()
        link.status = "ended"
    assert client.post(
        path + "/preview", headers=coach, json={**change, "expected_revision_number": 2}
    ).status_code in (403, 404)
