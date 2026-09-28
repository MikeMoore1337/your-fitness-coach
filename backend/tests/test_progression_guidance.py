from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, time, timedelta

import pytest

from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.program import (
    ProgramRevision,
    ProgramTemplate,
    TrainingBlock,
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.services.progression_guidance import (
    SessionFacts,
    evaluate_progression,
    parse_rep_target,
)


def _auth(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _assigned_workout(
    client,
    headers: dict[str, str],
    *,
    prescribed_sets: int = 2,
    prescribed_reps: str = "8–10",
    prescription: dict | None = None,
) -> dict:
    exercises = client.get("/api/v1/programs/exercises", headers=headers).json()
    exercise_id = next(item["id"] for item in exercises if item["metric_type"] == "strength")
    template = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Проверка прогрессии",
            "goal": "recomposition",
            "level": "intermediate",
            "mode": "self",
            "assign_after_create": False,
            "days": [
                {
                    "title": "Силовая тренировка",
                    "exercises": [
                        {
                            "exercise_id": exercise_id,
                            "prescribed_sets": prescribed_sets,
                            "prescribed_reps": prescribed_reps,
                            "rest_seconds": 90,
                            "prescription": prescription,
                        }
                    ],
                }
            ],
        },
    )
    assert template.status_code == 200, template.text
    today = today_msk()
    assigned = client.post(
        f"/api/v1/programs/templates/{template.json()['template']['id']}/assign-to-me",
        headers=headers,
        json={
            "start_date": today.isoformat(),
            "duration_weeks": 2,
            "schedule_weekdays": [today.weekday()],
        },
    )
    assert assigned.status_code == 200, assigned.text
    response = client.get("/api/v1/workouts/today", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _add_history(
    workout_id: int,
    sessions: list[list[tuple[int, float | None, str | None, str | None, bool | None]]],
) -> None:
    with get_session_context() as db:
        current = db.query(UserWorkout).filter(UserWorkout.id == workout_id).one()
        current_exercise = current.exercises[0]
        revision = (
            db.query(ProgramRevision)
            .filter(
                ProgramRevision.user_program_id == current.user_program_id,
                ProgramRevision.revision_number == current.user_program.current_revision_number,
            )
            .one()
        )
        revision.created_at = datetime.combine(
            current.scheduled_date - timedelta(days=30), time(9, 0)
        )
        for session_index, sets in enumerate(sessions, start=1):
            scheduled_date = current.scheduled_date - timedelta(days=7 * session_index)
            previous = UserWorkout(
                user_program_id=current.user_program_id,
                scheduled_date=scheduled_date,
                day_number=1,
                week_number=max(1, current.week_number - session_index),
                title="Предыдущая тренировка",
                status="completed",
                started_at=datetime.combine(scheduled_date, time(10, 0)),
                completed_at=datetime.combine(scheduled_date, time(11, 0)),
            )
            db.add(previous)
            db.flush()
            previous_exercise = UserWorkoutExercise(
                workout_id=previous.id,
                exercise_id=current_exercise.exercise_id,
                source_template_exercise_id=current_exercise.source_template_exercise_id,
                sort_order=1,
                prescribed_sets=current_exercise.prescribed_sets,
                prescribed_reps=current_exercise.prescribed_reps,
                rest_seconds=current_exercise.rest_seconds,
                prescription=current_exercise.prescription,
            )
            db.add(previous_exercise)
            db.flush()
            segments = (current_exercise.prescription or {}).get("segments", [])
            for set_number, (reps, weight, rir, set_kind, failure) in enumerate(sets, start=1):
                segment = segments[set_number - 1] if set_number <= len(segments) else {}
                db.add(
                    UserWorkoutSet(
                        workout_exercise_id=previous_exercise.id,
                        set_number=set_number,
                        actual_reps=reps,
                        actual_weight=weight,
                        rir=rir,
                        set_kind=set_kind,
                        reached_failure=failure,
                        is_completed=True,
                        planned_role=segment.get("role"),
                        planned_position=segment.get("position"),
                    )
                )


def _set_coaching_rules(
    workout_id: int,
    rules: list[dict],
    *,
    training_blocks: list[dict] | None = None,
) -> None:
    with get_session_context() as db:
        workout = db.query(UserWorkout).filter(UserWorkout.id == workout_id).one()
        program = db.query(UserProgram).filter(UserProgram.id == workout.user_program_id).one()
        template = db.query(ProgramTemplate).filter(ProgramTemplate.id == program.template_id).one()
        metadata = deepcopy(template.program_metadata or {})
        metadata["coaching_rules"] = rules
        if training_blocks is not None:
            metadata["training_blocks"] = training_blocks
        template.program_metadata = metadata
        revision = (
            db.query(ProgramRevision)
            .filter(
                ProgramRevision.user_program_id == program.id,
                ProgramRevision.revision_number == program.current_revision_number,
            )
            .one()
        )
        snapshot = deepcopy(revision.snapshot)
        snapshot["program"]["program_metadata"] = metadata
        revision.snapshot = snapshot


def _double_rule(*, increment: float = 2.5, scope: str = "program") -> dict:
    return {
        "kind": "double_progression",
        "scope": scope,
        "rep_target": {"kind": "range", "min_reps": 8, "max_reps": 10},
        "increment_value": increment,
        "increment_unit": "kg",
    }


def _program_id_for_workout(workout_id: int) -> int:
    with get_session_context() as db:
        return db.query(UserWorkout).filter(UserWorkout.id == workout_id).one().user_program_id


def _proposal_exercise(client, headers: dict[str, str], workout_id: int) -> dict:
    program_id = _program_id_for_workout(workout_id)
    response = client.get(
        f"/api/v1/programs/assigned/{program_id}/progression-proposals",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["target_workout_id"] == workout_id
    assert len(data["exercises"]) == 1
    return data["exercises"][0]


def _review_proposal(
    client,
    headers: dict[str, str],
    workout_id: int,
    exercise: dict,
    *,
    decision: str,
    adjusted_weight: float | None = None,
) -> tuple[int, dict]:
    guidance = exercise["guidance"]
    proposal = guidance["proposal"]
    body = {
        "decision": decision,
        "workout_id": workout_id,
        "exercise_id": exercise["exercise_id"],
        "expected_revision_number": proposal["target_revision_number"],
        "expected_set_versions": {
            str(item["set_id"]): item["set_version"] for item in proposal["target_set_updates"]
        },
    }
    if adjusted_weight is not None:
        body["adjusted_weight"] = adjusted_weight
    response = client.post(
        f"/api/v1/programs/assigned/{proposal['target_program_id']}"
        f"/progression-proposals/{proposal['proposal_id']}/review",
        headers=headers,
        json=body,
    )
    return response.status_code, response.json() if response.content else {}


def _facts(
    *,
    day: int,
    reps: tuple[int, ...],
    weight: float = 40,
    rir: tuple[str, ...] = (),
    failure: bool = False,
    complete: bool = True,
) -> SessionFacts:
    return SessionFacts(
        workout_id=day,
        scheduled_date=date(2026, 8, day),
        working_set_count=len(reps),
        load=weight if complete else None,
        reps_min=min(reps),
        reps_max=max(reps),
        rir_values=rir,
        reached_failure=failure,
        complete=complete,
        completion_feedback=None,
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("8", (8, 8)),
        ("8-10", (8, 10)),
        ("8–10", (8, 10)),
        ("10—12", (10, 12)),
        ("AMRAP", None),
        ("10-8", None),
        ("0-8", None),
    ],
)
def test_rep_prescription_parser_is_narrow_and_deterministic(value, expected) -> None:
    parsed = parse_rep_target(value)
    actual = (parsed.minimum, parsed.maximum) if parsed else None
    assert actual == expected


def test_progression_without_rir_requires_three_stable_sessions() -> None:
    two_sessions = [_facts(day=20, reps=(10, 10)), _facts(day=13, reps=(10, 10))]
    held = evaluate_progression(
        prescribed_sets=2,
        prescribed_reps="8-10",
        sessions=two_sessions,
    )
    assert held["outcome"] == "hold"
    assert held["evidence"]["required_session_count"] == 3
    assert "need_one_more_stable_session" in held["evidence"]["reason_keys"]

    progressed = evaluate_progression(
        prescribed_sets=2,
        prescribed_reps="8-10",
        sessions=[*two_sessions, _facts(day=6, reps=(10, 10))],
    )
    assert progressed["outcome"] == "consider_progressing"
    assert progressed["suggested_weight"] is None
    assert "conservative_without_rir" in progressed["evidence"]["reason_keys"]


def test_full_optional_rir_allows_two_sessions_and_preserves_lb_increment() -> None:
    result = evaluate_progression(
        prescribed_sets=2,
        prescribed_reps="8–10",
        sessions=[
            _facts(day=20, reps=(10, 10), weight=100, rir=("1", "2")),
            _facts(day=13, reps=(10, 10), weight=100, rir=("2", "2")),
        ],
        load_unit="lb",
        configured_increment=5,
    )
    assert result["outcome"] == "consider_progressing"
    assert result["suggested_increment"] == 5
    assert result["suggested_weight"] == 105
    assert result["load_unit"] == "lb"
    assert {item["load_unit"] for item in result["evidence"]["sessions"]} == {"lb"}


def test_reduction_is_a_two_session_rule_not_a_diagnosis() -> None:
    result = evaluate_progression(
        prescribed_sets=2,
        prescribed_reps="8-10",
        sessions=[_facts(day=20, reps=(6, 7)), _facts(day=13, reps=(7, 7))],
        configured_increment=2.5,
    )
    assert result["outcome"] == "consider_reducing"
    assert result["suggested_weight"] == 37.5
    assert "перетренированности" in result["detail"]


def test_failure_or_zero_rir_never_strengthens_progression() -> None:
    result = evaluate_progression(
        prescribed_sets=2,
        prescribed_reps="8-10",
        sessions=[
            _facts(day=20, reps=(10, 10), rir=("0", "1"), failure=True),
            _facts(day=13, reps=(10, 10), rir=("1", "2")),
            _facts(day=6, reps=(10, 10), rir=("1", "2")),
        ],
    )
    assert result["outcome"] == "hold"
    assert "zero_rir_or_failure_recorded" in result["evidence"]["reason_keys"]


def test_optional_completion_feedback_is_evidence_not_a_decision_input() -> None:
    sessions = [
        _facts(day=20, reps=(10, 10), rir=("1", "2")),
        _facts(day=13, reps=(10, 10), rir=("2", "2")),
    ]
    easier = [replace(item, completion_feedback="easier_than_expected") for item in sessions]
    harder = [replace(item, completion_feedback="harder_than_expected") for item in sessions]

    easier_result = evaluate_progression(
        prescribed_sets=2,
        prescribed_reps="8-10",
        sessions=easier,
    )
    harder_result = evaluate_progression(
        prescribed_sets=2,
        prescribed_reps="8-10",
        sessions=harder,
    )
    assert easier_result["outcome"] == harder_result["outcome"] == "consider_progressing"
    assert easier_result["evidence"]["sessions"][0]["completion_feedback"] == (
        "easier_than_expected"
    )
    assert harder_result["evidence"]["sessions"][0]["completion_feedback"] == (
        "harder_than_expected"
    )


def test_today_api_excludes_warmup_and_drop_and_repeats_identically(client) -> None:
    headers = _auth(client, 63_001)
    workout = _assigned_workout(client, headers)
    _add_history(
        workout["id"],
        [
            [(10, 40, "2", "warmup", False), (10, 40, "2", "working", False)],
            [(10, 40, "2", "working", False), (10, 35, "2", "drop", False)],
        ],
    )

    first = client.get("/api/v1/workouts/today", headers=headers)
    second = client.get("/api/v1/workouts/today", headers=headers)
    assert first.status_code == second.status_code == 200
    guidance = first.json()["exercises"][0]["progression_guidance"]
    assert guidance == second.json()["exercises"][0]["progression_guidance"]
    assert guidance["outcome"] == "review"
    assert guidance["evidence"]["comparable_session_count"] == 0
    assert "incomplete_session_facts" in guidance["evidence"]["reason_keys"]


def test_today_api_uses_only_completed_working_sets_with_optional_rir(client) -> None:
    headers = _auth(client, 63_002)
    workout = _assigned_workout(client, headers)
    _add_history(
        workout["id"],
        [
            [(10, 40, "1", "working", False), (10, 40, "2", "working", False)],
            [(10, 40, "2", None, False), (10, 40, "2", "working", False)],
        ],
    )

    response = client.get("/api/v1/workouts/today", headers=headers)
    assert response.status_code == 200, response.text
    guidance = response.json()["exercises"][0]["progression_guidance"]
    assert guidance["outcome"] == "consider_progressing"
    assert guidance["load_unit"] == "kg"
    assert guidance["suggested_weight"] is None
    assert guidance["evidence"]["target_reps_min"] == 8
    assert guidance["evidence"]["target_reps_max"] == 10
    assert guidance["evidence"]["rir_recorded_set_count"] == 4


def test_today_api_does_not_cross_a_training_block_boundary(client) -> None:
    headers = _auth(client, 63_003)
    workout = _assigned_workout(client, headers)
    _add_history(
        workout["id"],
        [
            [(10, 40, "1", "working", False), (10, 40, "2", "working", False)],
            [(10, 40, "2", "working", False), (10, 40, "2", "working", False)],
        ],
    )
    with get_session_context() as db:
        current = db.query(UserWorkout).filter(UserWorkout.id == workout["id"]).one()
        db.add(
            TrainingBlock(
                user_program_id=current.user_program_id,
                title="Новый блок",
                start_date=current.scheduled_date,
                end_date=current.scheduled_date,
                purpose="Проверить новый контекст нагрузки.",
                status="active",
            )
        )

    response = client.get("/api/v1/workouts/today", headers=headers)
    assert response.status_code == 200, response.text
    guidance = response.json()["exercises"][0]["progression_guidance"]
    assert guidance["outcome"] == "review"
    assert guidance["evidence"]["comparable_session_count"] == 0
    assert "program_context_changed" in guidance["evidence"]["reason_keys"]


def test_today_api_reviews_history_after_prescription_change(client) -> None:
    headers = _auth(client, 63_004)
    workout = _assigned_workout(client, headers)
    _add_history(
        workout["id"],
        [
            [(10, 40, "1", "working", False), (10, 40, "2", "working", False)],
            [(10, 40, "2", "working", False), (10, 40, "2", "working", False)],
        ],
    )
    with get_session_context() as db:
        current = db.query(UserWorkout).filter(UserWorkout.id == workout["id"]).one()
        for previous in (
            db.query(UserWorkoutExercise)
            .join(UserWorkout, UserWorkoutExercise.workout_id == UserWorkout.id)
            .filter(
                UserWorkout.user_program_id == current.user_program_id,
                UserWorkout.status == "completed",
            )
            .all()
        ):
            previous.prescribed_reps = "6-8"

    response = client.get("/api/v1/workouts/today", headers=headers)
    assert response.status_code == 200, response.text
    guidance = response.json()["exercises"][0]["progression_guidance"]
    assert guidance["outcome"] == "review"
    assert guidance["evidence"]["comparable_session_count"] == 0
    assert "program_context_changed" in guidance["evidence"]["reason_keys"]


def test_today_api_keeps_trainer_assigned_program_owned_by_athlete(client) -> None:
    athlete_headers = _auth(client, 63_005)
    _auth(client, 63_006)
    workout = _assigned_workout(client, athlete_headers)
    _add_history(
        workout["id"],
        [
            [(10, 40, "1", "working", False), (10, 40, "2", "working", False)],
            [(10, 40, "2", "working", False), (10, 40, "2", "working", False)],
        ],
    )
    with get_session_context() as db:
        current = db.query(UserWorkout).filter(UserWorkout.id == workout["id"]).one()
        trainer = db.query(User).filter(User.telegram_user_id == 63_006).one()
        current.user_program.assigned_by_user_id = trainer.id

    response = client.get("/api/v1/workouts/today", headers=athlete_headers)
    assert response.status_code == 200, response.text
    guidance = response.json()["exercises"][0]["progression_guidance"]
    assert guidance["outcome"] == "consider_progressing"
    assert guidance["evidence"]["comparable_session_count"] == 2


@pytest.mark.parametrize(
    (
        "telegram_user_id",
        "rule",
        "sessions",
        "prescribed_sets",
        "prescribed_reps",
        "outcome",
        "action",
        "reason",
        "weight",
    ),
    [
        (
            64_001,
            {
                "kind": "fixed_prescription",
                "rep_target": {"kind": "range", "min_reps": 8, "max_reps": 10},
            },
            [],
            2,
            "8–10",
            "hold",
            "hold",
            "fixed_prescription",
            None,
        ),
        (
            64_002,
            {
                "kind": "percentage_training_max",
                "load_target": {"kind": "percent_training_max", "value": 80},
            },
            [],
            2,
            "8–10",
            "review",
            "hold",
            "missing_training_max_source",
            None,
        ),
        (
            64_003,
            {"kind": "linear_load", "increment_value": 2.5, "increment_unit": "kg"},
            [[(8, 40, None, "working", False), (8, 40, None, "working", False)]],
            2,
            "8–10",
            "consider_progressing",
            "set_load",
            "linear_load_success",
            42.5,
        ),
        (
            64_004,
            {
                "kind": "rir_rpe",
                "effort_target": {"kind": "rir", "value": 2},
                "increment_value": 2.5,
                "increment_unit": "kg",
            },
            [[(8, 40, "2", "working", False), (8, 40, "3", "working", False)]],
            2,
            "8–10",
            "consider_progressing",
            "set_load",
            "rir_target_met",
            42.5,
        ),
        (
            64_005,
            {
                "kind": "rir_rpe",
                "effort_target": {"kind": "rir", "value": 2},
                "increment_value": 2.5,
                "increment_unit": "kg",
            },
            [[(8, 40, None, "working", False), (8, 40, None, "working", False)]],
            2,
            "8–10",
            "review",
            "hold",
            "missing_rir_evidence",
            None,
        ),
        (
            64_006,
            {
                "kind": "rir_rpe",
                "effort_target": {"kind": "rpe", "value": 8},
                "increment_value": 2.5,
                "increment_unit": "kg",
            },
            [[(8, 40, "2", "working", False), (8, 40, "2", "working", False)]],
            2,
            "8–10",
            "review",
            "hold",
            "missing_rpe_evidence",
            None,
        ),
        (
            64_007,
            {
                "kind": "amrap_success_failure",
                "rep_target": {"kind": "amrap"},
                "amrap_min_reps": 10,
                "amrap_failure_action": "repeat",
                "increment_value": 2.5,
                "increment_unit": "kg",
            },
            [[(12, 40, None, "working", False)]],
            1,
            "AMRAP",
            "consider_progressing",
            "set_load",
            "amrap_success",
            42.5,
        ),
        (
            64_008,
            {
                "kind": "amrap_success_failure",
                "rep_target": {"kind": "amrap"},
                "amrap_min_reps": 10,
                "amrap_failure_action": "reduce_load",
                "increment_value": 2.5,
                "increment_unit": "kg",
            },
            [[(7, 40, None, "working", False)]],
            1,
            "AMRAP",
            "consider_reducing",
            "set_load",
            "amrap_threshold_not_met",
            37.5,
        ),
        (
            64_009,
            {
                "kind": "amrap_success_failure",
                "rep_target": {"kind": "amrap"},
                "amrap_min_reps": 10,
                "amrap_failure_action": "reduce_load",
            },
            [[(7, 40, None, "working", False)]],
            1,
            "AMRAP",
            "hold",
            "hold",
            "missing_configured_decrement",
            None,
        ),
        (
            64_010,
            {
                "kind": "amrap_success_failure",
                "rep_target": {"kind": "amrap"},
                "amrap_min_reps": 10,
                "amrap_failure_action": "deload",
            },
            [[(7, 40, None, "working", False)]],
            1,
            "AMRAP",
            "hold",
            "hold",
            "missing_deload_parameters",
            None,
        ),
        (
            64_011,
            {
                "kind": "amrap_success_failure",
                "rep_target": {"kind": "amrap"},
                "amrap_min_reps": 10,
                "amrap_failure_action": "deload",
                "deload_volume_percent": 60,
                "deload_intensity_percent": 80,
            },
            [[(7, 40, None, "working", False)]],
            1,
            "AMRAP",
            "review",
            "deload",
            "amrap_threshold_not_met",
            None,
        ),
        (
            64_012,
            {
                "kind": "double_progression",
                "rep_target": {"kind": "range", "min_reps": 8, "max_reps": 10},
                "increment_value": 2.5,
                "increment_unit": "kg",
                "reset_on_failure": True,
            },
            [
                [(10, 40, "2", "working", False), (10, 40, "2", "working", False)],
                [(10, 40, "0", "working", True), (10, 40, "2", "working", False)],
            ],
            2,
            "8–10",
            "hold",
            "reset_recommended",
            "reset_target_missing",
            None,
        ),
        (
            64_013,
            {
                "kind": "double_progression",
                "rep_target": {"kind": "range", "min_reps": 8, "max_reps": 10},
                "increment_value": 5,
                "increment_unit": "lb",
            },
            [
                [(10, 40, "2", "working", False), (10, 40, "2", "working", False)],
                [(10, 40, "2", "working", False), (10, 40, "2", "working", False)],
            ],
            2,
            "8–10",
            "review",
            "hold",
            "incompatible_load_unit",
            None,
        ),
    ],
)
def test_stored_rule_families_have_explicit_deterministic_outcomes(
    client,
    telegram_user_id,
    rule,
    sessions,
    prescribed_sets,
    prescribed_reps,
    outcome,
    action,
    reason,
    weight,
) -> None:
    headers = _auth(client, telegram_user_id)
    workout = _assigned_workout(
        client,
        headers,
        prescribed_sets=prescribed_sets,
        prescribed_reps=prescribed_reps,
    )
    if sessions:
        _add_history(workout["id"], sessions)
    _set_coaching_rules(workout["id"], [rule])

    response = client.get("/api/v1/workouts/today", headers=headers)
    assert response.status_code == 200, response.text
    guidance = response.json()["exercises"][0]["progression_guidance"]
    proposal = guidance["proposal"]
    assert guidance["outcome"] == outcome
    assert proposal["rule_kind"] == rule["kind"]
    assert proposal["proposed_action"] == action, guidance
    assert reason in proposal["reason_codes"]
    assert proposal["proposed_weight"] == weight
    assert proposal["eligibility_status"] == (
        "eligible"
        if action == "set_load"
        else "review"
        if action in {"deload", "reset_recommended"} or outcome == "review"
        else "no_change"
    ), guidance
    assert proposal["requires_confirmation"] is True


def test_double_progression_proposal_has_stable_id_and_source_set_ids(client) -> None:
    headers = _auth(client, 64_020)
    workout = _assigned_workout(client, headers)
    _add_history(
        workout["id"],
        [
            [(10, 40, "2", "working", False), (10, 40, "2", "working", False)],
            [(10, 40, "1", "working", False), (10, 40, "2", "working", False)],
        ],
    )
    _set_coaching_rules(workout["id"], [_double_rule()])

    first = client.get("/api/v1/workouts/today", headers=headers)
    second = client.get("/api/v1/workouts/today", headers=headers)
    assert first.status_code == second.status_code == 200
    first_guidance = first.json()["exercises"][0]["progression_guidance"]
    second_guidance = second.json()["exercises"][0]["progression_guidance"]
    proposal = first_guidance["proposal"]
    assert proposal == second_guidance["proposal"]
    assert proposal["proposed_weight"] == 42.5
    assert proposal["rule_snapshot"] == _double_rule()
    assert proposal["source_evidence_ids"]
    assert all("/set:" in value for value in proposal["source_evidence_ids"])
    assert len(proposal["target_set_updates"]) == 2


def test_rule_precedence_and_conflicting_same_level_overrides(client) -> None:
    headers = _auth(client, 64_021)
    workout = _assigned_workout(client, headers)
    _add_history(
        workout["id"],
        [
            [(10, 40, "2", "working", False), (10, 40, "2", "working", False)],
            [(10, 40, "2", "working", False), (10, 40, "2", "working", False)],
        ],
    )
    exercise_id = workout["exercises"][0]["exercise_id"]
    program_rule = {"kind": "linear_load", "increment_value": 2.5, "increment_unit": "kg"}
    block_rule = _double_rule(increment=5, scope="block")
    block_rule["block_number"] = 1
    block_metadata = [{"block_number": 1, "week_start": 1, "week_end": 2}]
    _set_coaching_rules(
        workout["id"],
        [program_rule, block_rule],
        training_blocks=block_metadata,
    )

    response = client.get("/api/v1/workouts/today", headers=headers)
    assert response.status_code == 200, response.text
    proposal = response.json()["exercises"][0]["progression_guidance"]["proposal"]
    assert proposal["rule_kind"] == "double_progression"
    assert proposal["proposed_weight"] == 45

    exercise_rule = {
        "kind": "fixed_prescription",
        "scope": "exercise",
        "exercise_id": exercise_id,
        "rep_target": {"kind": "range", "min_reps": 8, "max_reps": 10},
    }
    _set_coaching_rules(
        workout["id"],
        [program_rule, block_rule, exercise_rule],
        training_blocks=block_metadata,
    )
    response = client.get("/api/v1/workouts/today", headers=headers)
    assert response.status_code == 200, response.text
    proposal = response.json()["exercises"][0]["progression_guidance"]["proposal"]
    assert proposal["rule_kind"] == "fixed_prescription"
    assert proposal["proposed_action"] == "hold"
    assert "fixed_prescription" in proposal["reason_codes"]

    _set_coaching_rules(workout["id"], [_double_rule(), _double_rule(increment=5)])
    response = client.get("/api/v1/workouts/today", headers=headers)
    assert response.status_code == 200, response.text
    guidance = response.json()["exercises"][0]["progression_guidance"]
    assert guidance["outcome"] == "review"
    assert guidance["proposal"]["proposed_action"] == "hold"
    assert "conflicting_coaching_rules" in guidance["proposal"]["reason_codes"]


def test_scheduled_deload_is_a_visible_review_proposal(client) -> None:
    headers = _auth(client, 64_022)
    workout = _assigned_workout(client, headers)
    with get_session_context() as db:
        current = db.query(UserWorkout).filter(UserWorkout.id == workout["id"]).one()
        db.add(
            TrainingBlock(
                user_program_id=current.user_program_id,
                title="Облегчённая неделя",
                start_date=current.scheduled_date,
                end_date=current.scheduled_date,
                purpose="Запланированное снижение нагрузки.",
                is_deload=True,
                status="active",
            )
        )
    _set_coaching_rules(
        workout["id"],
        [{"kind": "deload", "deload_volume_percent": 60, "deload_intensity_percent": 80}],
    )

    response = client.get("/api/v1/workouts/today", headers=headers)
    assert response.status_code == 200, response.text
    guidance = response.json()["exercises"][0]["progression_guidance"]
    proposal = guidance["proposal"]
    assert proposal["proposed_action"] == "deload"
    assert proposal["eligibility_status"] == "review"
    assert proposal["deload_volume_percent"] == 60
    assert proposal["deload_intensity_percent"] == 80
    assert "scheduled_deload_block" in proposal["reason_codes"]


def test_partial_skipped_substituted_and_stale_records_are_not_progression_evidence(client) -> None:
    headers = _auth(client, 64_023)
    workout = _assigned_workout(client, headers)
    _add_history(
        workout["id"],
        [
            [(10, 40, "2", "working", False), (10, 40, "2", "working", False)],
            [(10, 40, "2", "working", False), (10, 40, "2", "working", False)],
        ],
    )
    _set_coaching_rules(workout["id"], [_double_rule()])
    with get_session_context() as db:
        current = db.query(UserWorkout).filter(UserWorkout.id == workout["id"]).one()
        recent = (
            db.query(UserWorkout)
            .filter(
                UserWorkout.user_program_id == current.user_program_id,
                UserWorkout.status == "completed",
            )
            .order_by(UserWorkout.scheduled_date.desc())
            .first()
        )
        recent.exercises[0].sets[0].is_completed = False

    response = client.get("/api/v1/workouts/today", headers=headers)
    assert response.status_code == 200, response.text
    guidance = response.json()["exercises"][0]["progression_guidance"]
    assert guidance["outcome"] == "review"
    assert guidance["proposal"]["proposed_weight"] is None
    assert "incomplete_session_facts" in guidance["proposal"]["reason_codes"]

    with get_session_context() as db:
        current = db.query(UserWorkout).filter(UserWorkout.id == workout["id"]).one()
        substituted = (
            db.query(UserWorkoutExercise)
            .join(UserWorkout, UserWorkoutExercise.workout_id == UserWorkout.id)
            .filter(
                UserWorkout.user_program_id == current.user_program_id,
                UserWorkout.status == "completed",
            )
            .order_by(UserWorkout.scheduled_date.desc())
            .first()
        )
        substituted.source_template_exercise_id += 10_000
    response = client.get("/api/v1/workouts/today", headers=headers)
    assert response.status_code == 200, response.text
    guidance = response.json()["exercises"][0]["progression_guidance"]
    assert guidance["outcome"] == "review"
    assert guidance["proposal"]["proposed_weight"] is None

    with get_session_context() as db:
        current = db.query(UserWorkout).filter(UserWorkout.id == workout["id"]).one()
        current.exercises[0].prescribed_reps = "6-8"
    response = client.get("/api/v1/workouts/today", headers=headers)
    assert response.status_code == 200, response.text
    guidance = response.json()["exercises"][0]["progression_guidance"]
    assert guidance["outcome"] == "review"
    assert "stale_program_revision" in guidance["proposal"]["reason_codes"]


def test_skipped_workout_does_not_count_as_completed_evidence(client) -> None:
    headers = _auth(client, 64_024)
    workout = _assigned_workout(client, headers)
    _add_history(
        workout["id"],
        [[(10, 40, "2", "working", False), (10, 40, "2", "working", False)]],
    )
    _set_coaching_rules(workout["id"], [_double_rule()])
    with get_session_context() as db:
        current = db.query(UserWorkout).filter(UserWorkout.id == workout["id"]).one()
        skipped_date = current.scheduled_date - timedelta(days=7)
        db.add(
            UserWorkout(
                user_program_id=current.user_program_id,
                scheduled_date=skipped_date,
                day_number=1,
                week_number=1,
                title="Пропущенная тренировка",
                status="skipped",
            )
        )

    response = client.get("/api/v1/workouts/today", headers=headers)
    assert response.status_code == 200, response.text
    guidance = response.json()["exercises"][0]["progression_guidance"]
    assert guidance["outcome"] == "review"
    assert guidance["proposal"]["comparable_session_count"] == 1
    assert guidance["proposal"]["proposed_weight"] is None


def test_bodyweight_repetition_only_history_never_produces_load_change(client) -> None:
    headers = _auth(client, 64_026)
    workout = _assigned_workout(client, headers)
    _add_history(
        workout["id"],
        [
            [(10, None, "2", "working", False), (10, None, "2", "working", False)],
            [(10, None, "2", "working", False), (10, None, "2", "working", False)],
        ],
    )
    _set_coaching_rules(workout["id"], [_double_rule()])

    response = client.get("/api/v1/workouts/today", headers=headers)
    assert response.status_code == 200, response.text
    guidance = response.json()["exercises"][0]["progression_guidance"]
    assert guidance["outcome"] == "review"
    assert guidance["proposal"]["proposed_action"] == "hold"
    assert guidance["proposal"]["proposed_weight"] is None
    assert "incomplete_session_facts" in guidance["proposal"]["reason_codes"]


def test_incompatible_current_metric_does_not_get_a_strength_proposal(client) -> None:
    headers = _auth(client, 64_027)
    workout = _assigned_workout(client, headers)
    _add_history(
        workout["id"],
        [
            [(10, 40, "2", "working", False), (10, 40, "2", "working", False)],
            [(10, 40, "2", "working", False), (10, 40, "2", "working", False)],
        ],
    )
    _set_coaching_rules(workout["id"], [_double_rule()])
    with get_session_context() as db:
        current = db.query(UserWorkout).filter(UserWorkout.id == workout["id"]).one()
        current.exercises[0].metric_type = "cardio"

    response = client.get("/api/v1/workouts/today", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["exercises"][0]["progression_guidance"] is None


def test_top_set_proposal_updates_top_and_explicit_relative_backoffs(client) -> None:
    headers = _auth(client, 64_025)
    plan = {
        "version": 1,
        "metric_type": "strength",
        "segments": [
            {
                "position": 1,
                "role": "top",
                "rep_target": {"kind": "range", "min_reps": 8, "max_reps": 10},
            },
            {
                "position": 2,
                "role": "backoff",
                "rep_target": {"kind": "range", "min_reps": 8, "max_reps": 10},
                "load_target": {"kind": "relative_to_top", "value": 0.9},
            },
            {
                "position": 3,
                "role": "backoff",
                "rep_target": {"kind": "range", "min_reps": 8, "max_reps": 10},
                "load_target": {"kind": "relative_to_top", "value": 0.8},
            },
        ],
    }
    workout = _assigned_workout(client, headers, prescribed_sets=3, prescription=plan)
    _add_history(
        workout["id"],
        [
            [
                (10, 100, "2", "working", False),
                (8, 90, None, "working", False),
                (8, 80, None, "working", False),
            ],
            [
                (10, 100, "2", "working", False),
                (8, 90, None, "working", False),
                (8, 80, None, "working", False),
            ],
        ],
    )
    _set_coaching_rules(workout["id"], [_double_rule()])

    response = client.get("/api/v1/workouts/today", headers=headers)
    assert response.status_code == 200, response.text
    guidance = response.json()["exercises"][0]["progression_guidance"]
    updates = guidance["proposal"]["target_set_updates"]
    assert guidance["proposal"]["proposed_weight"] == 102.5
    assert [item["planned_role"] for item in updates] == ["top", "backoff", "backoff"]
    assert [item["proposed_weight"] for item in updates] == [102.5, 92.25, 82.0]
    assert [item["relative_to_top"] for item in updates] == [None, 0.9, 0.8]


@pytest.mark.parametrize(
    ("group_kind", "roles", "reason"),
    [
        ("drop_chain", ["working", "drop"], "top_range_repeated"),
        ("rest_pause", ["working", "mini_set"], "top_range_repeated"),
        ("cluster", ["working", "cluster_member"], "top_range_repeated"),
        ("myo_reps", ["activation", "mini_set"], "advanced_method_requires_review"),
        ("circuit", ["working", "working"], "advanced_method_requires_review"),
    ],
)
def test_advanced_method_auxiliary_sets_do_not_drive_progression(
    client, group_kind, roles, reason
) -> None:
    headers = _auth(client, 64_100 + sum(map(ord, group_kind)))
    plan = {
        "version": 1,
        "metric_type": "strength",
        "segments": [
            {
                "position": index,
                "role": role,
                "rep_target": {"kind": "range", "min_reps": 8, "max_reps": 10},
                "group_id": 1,
                "group_position": index,
                **({"round_number": 1} if group_kind == "circuit" else {}),
            }
            for index, role in enumerate(roles, start=1)
        ],
        "groups": [
            {
                "group_id": 1,
                "kind": group_kind,
                **({"rounds": 1} if group_kind == "circuit" else {}),
            }
        ],
    }
    workout = _assigned_workout(client, headers, prescribed_sets=2, prescription=plan)
    _add_history(
        workout["id"],
        [
            [(10, 40, "2", "working", False), (15, 30, "2", "working", False)],
            [(10, 40, "2", "working", False), (15, 30, "2", "working", False)],
        ],
    )
    _set_coaching_rules(workout["id"], [_double_rule()])

    response = client.get("/api/v1/workouts/today", headers=headers)
    assert response.status_code == 200, response.text
    guidance = response.json()["exercises"][0]["progression_guidance"]
    assert reason in guidance["proposal"]["reason_codes"]
    if group_kind in {"myo_reps", "circuit"}:
        assert guidance["outcome"] == "review"
        assert guidance["proposal"]["target_set_updates"] == []
    else:
        assert guidance["outcome"] == "consider_progressing"
        assert guidance["evidence"]["working_set_count"] == 2
        assert len(guidance["proposal"]["target_set_updates"]) == 1


@pytest.mark.parametrize(("decision", "adjusted_weight"), [("confirm", None), ("adjust", 45.0)])
def test_review_apply_and_adjust_are_explicit_idempotent_and_preserve_history(
    client, decision, adjusted_weight
) -> None:
    headers = _auth(client, 64_200 + (1 if decision == "confirm" else 2))
    workout = _assigned_workout(client, headers)
    _add_history(
        workout["id"],
        [
            [(10, 40, "2", "working", False), (10, 40, "2", "working", False)],
            [(10, 40, "2", "working", False), (10, 40, "2", "working", False)],
        ],
    )
    _set_coaching_rules(workout["id"], [_double_rule()])
    exercise = _proposal_exercise(client, headers, workout["id"])
    proposal = exercise["guidance"]["proposal"]
    expected_weight = (
        adjusted_weight if adjusted_weight is not None else proposal["proposed_weight"]
    )
    history_ids = [int(value.rsplit(":", 1)[1]) for value in proposal["source_evidence_ids"]]
    with get_session_context() as db:
        original_history = {
            row.id: (row.actual_weight, row.is_completed)
            for row in db.query(UserWorkoutSet).filter(UserWorkoutSet.id.in_(history_ids)).all()
        }

    status_code, first = _review_proposal(
        client,
        headers,
        workout["id"],
        exercise,
        decision=decision,
        adjusted_weight=adjusted_weight,
    )
    retry_status, retry = _review_proposal(
        client,
        headers,
        workout["id"],
        exercise,
        decision=decision,
        adjusted_weight=adjusted_weight,
    )
    assert status_code == retry_status == 200
    assert first == retry
    assert len(first["applied_set_ids"]) == 2
    target_ids = set(first["applied_set_ids"])
    with get_session_context() as db:
        targets = db.query(UserWorkoutSet).filter(UserWorkoutSet.id.in_(target_ids)).all()
        history = db.query(UserWorkoutSet).filter(UserWorkoutSet.id.in_(history_ids)).all()
        current_workout = db.query(UserWorkout).filter(UserWorkout.id == workout["id"]).one()
        assert all(row.actual_weight == expected_weight for row in targets)
        assert all(not row.is_completed and row.version == 2 for row in targets)
        assert {
            row.id: (row.actual_weight, row.is_completed) for row in history
        } == original_history
        assert current_workout.status == "planned"
        decision_events = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.action == f"progression_proposal.{decision}",
                AuditEvent.resource_type == "user_workout",
                AuditEvent.resource_id == str(workout["id"]),
            )
            .all()
        )
        assert (
            sum(
                event.details.get("proposal_id") == proposal["proposal_id"]
                for event in decision_events
            )
            == 1
        )

    list_response = client.get(
        f"/api/v1/programs/assigned/{_program_id_for_workout(workout['id'])}/progression-proposals",
        headers=headers,
    )
    assert list_response.status_code == 200, list_response.text
    assert list_response.json()["exercises"] == []

    other_decision = "reject" if decision == "confirm" else "confirm"
    conflict_status, _ = _review_proposal(
        client,
        headers,
        workout["id"],
        exercise,
        decision=other_decision,
    )
    assert conflict_status == 409
    if decision == "adjust":
        changed_adjustment_status, _ = _review_proposal(
            client,
            headers,
            workout["id"],
            exercise,
            decision="adjust",
            adjusted_weight=adjusted_weight + 1,
        )
        assert changed_adjustment_status == 409

    with get_session_context() as db:
        current_workout = db.query(UserWorkout).filter(UserWorkout.id == workout["id"]).one()
        current_workout.status = "completed"
        for row in current_workout.exercises[0].sets:
            row.is_completed = True
            row.version += 1
    completed_retry_status, completed_retry = _review_proposal(
        client,
        headers,
        workout["id"],
        exercise,
        decision=decision,
        adjusted_weight=adjusted_weight,
    )
    assert completed_retry_status == 200
    assert completed_retry == first
    with get_session_context() as db:
        targets = db.query(UserWorkoutSet).filter(UserWorkoutSet.id.in_(target_ids)).all()
        assert all(row.actual_weight == expected_weight for row in targets)
        assert all(row.is_completed and row.version == 3 for row in targets)


def test_reject_is_audited_once_and_cannot_be_applied_later(client) -> None:
    headers = _auth(client, 64_203)
    workout = _assigned_workout(client, headers)
    _add_history(
        workout["id"],
        [
            [(10, 40, "2", "working", False), (10, 40, "2", "working", False)],
            [(10, 40, "2", "working", False), (10, 40, "2", "working", False)],
        ],
    )
    _set_coaching_rules(workout["id"], [_double_rule()])
    exercise = _proposal_exercise(client, headers, workout["id"])
    proposal_id = exercise["guidance"]["proposal"]["proposal_id"]

    first_status, first = _review_proposal(
        client, headers, workout["id"], exercise, decision="reject"
    )
    retry_status, retry = _review_proposal(
        client, headers, workout["id"], exercise, decision="reject"
    )
    assert first_status == retry_status == 200
    assert first == retry
    assert first["applied_set_ids"] == []
    with get_session_context() as db:
        assert (
            db.query(AuditEvent)
            .filter(
                AuditEvent.action == "progression_proposal.reject",
                AuditEvent.resource_id == proposal_id,
            )
            .count()
            == 1
        )
        current = db.query(UserWorkout).filter(UserWorkout.id == workout["id"]).one()
        assert all(
            item.actual_weight is None and not item.is_completed
            for item in current.exercises[0].sets
        )
    list_response = client.get(
        f"/api/v1/programs/assigned/{_program_id_for_workout(workout['id'])}/progression-proposals",
        headers=headers,
    )
    assert list_response.status_code == 200, list_response.text
    assert list_response.json()["exercises"] == []
    apply_status, _ = _review_proposal(client, headers, workout["id"], exercise, decision="confirm")
    assert apply_status == 409


def test_review_enforces_revision_and_set_version_conflicts(client) -> None:
    headers = _auth(client, 64_204)
    workout = _assigned_workout(client, headers)
    _add_history(
        workout["id"],
        [
            [(10, 40, "2", "working", False), (10, 40, "2", "working", False)],
            [(10, 40, "2", "working", False), (10, 40, "2", "working", False)],
        ],
    )
    _set_coaching_rules(workout["id"], [_double_rule()])
    exercise = _proposal_exercise(client, headers, workout["id"])
    proposal = exercise["guidance"]["proposal"]
    first_target_id = proposal["target_set_updates"][0]["set_id"]
    with get_session_context() as db:
        target = db.query(UserWorkoutSet).filter(UserWorkoutSet.id == first_target_id).one()
        target.version += 1
    status_code, _ = _review_proposal(client, headers, workout["id"], exercise, decision="confirm")
    assert status_code == 409

    with get_session_context() as db:
        program = (
            db.query(UserProgram).filter(UserProgram.id == proposal["target_program_id"]).one()
        )
        program.current_revision_number += 1
    status_code, _ = _review_proposal(client, headers, workout["id"], exercise, decision="confirm")
    assert status_code == 409


def test_trainer_can_review_client_proposal_and_unrelated_user_cannot(client) -> None:
    athlete_headers = _auth(client, 64_205)
    trainer_headers = _auth(client, 64_206)
    unrelated_headers = _auth(client, 64_207)
    workout = _assigned_workout(client, athlete_headers)
    _add_history(
        workout["id"],
        [
            [(10, 40, "2", "working", False), (10, 40, "2", "working", False)],
            [(10, 40, "2", "working", False), (10, 40, "2", "working", False)],
        ],
    )
    _set_coaching_rules(workout["id"], [_double_rule()])
    with get_session_context() as db:
        athlete = db.query(User).filter(User.telegram_user_id == 64_205).one()
        trainer = db.query(User).filter(User.telegram_user_id == 64_206).one()
        athlete_id = athlete.id
        trainer_id = trainer.id
        trainer.is_coach = True
        current = db.query(UserWorkout).filter(UserWorkout.id == workout["id"]).one()
        program = db.query(UserProgram).filter(UserProgram.id == current.user_program_id).one()
        program_id = program.id
        program.assigned_by_user_id = trainer.id
        db.add(
            CoachClient(
                coach_user_id=trainer_id,
                client_user_id=athlete_id,
                status="active",
                operational_status="active",
            )
        )
    denied = client.get(
        f"/api/v1/programs/assigned/{program_id}/progression-proposals",
        headers=unrelated_headers,
    )
    assert denied.status_code == 404
    exercise = _proposal_exercise(client, trainer_headers, workout["id"])
    status_code, _ = _review_proposal(
        client, trainer_headers, workout["id"], exercise, decision="confirm"
    )
    assert status_code == 200
    with get_session_context() as db:
        event = (
            db.query(AuditEvent).filter(AuditEvent.action == "progression_proposal.confirm").one()
        )
        assert event.actor_user_id == trainer_id
        assert event.target_user_id == athlete_id
        assert event.details["actor_role"] == "trainer"
