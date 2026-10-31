from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from fitminiapp_api.core.timezone import today_for_user
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.program import (
    ProgramRevision,
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
    UserWorkoutSetSide,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.models.workout_history_import import ImportedWorkout
from fitminiapp_api.services.exercise_catalog import get_visible_exercise_display_map
from fitminiapp_api.services.program_versioning import workout_cycle_week_type
from fitminiapp_api.services.progression_guidance import (
    _matches_cycle_plan,
    _metadata_block_context,
    _revision_for_completion,
    _snapshot_block_context,
    _snapshot_metadata,
)
from fitminiapp_api.services.workout_metrics import exercise_metric_type
from fitminiapp_api.services.workout_ownership import workout_owner_id
from fitminiapp_api.services.workout_sides import (
    SIDE_MODES,
    completed_set_reps,
    completed_set_volume,
    serialize_sides,
)
from fitminiapp_api.services.workouts import (
    counts_toward_working_volume,
    is_pr_record_set,
    set_analytics_bucket,
)

EXERCISE_HISTORY_SESSION_LIMIT = 100
EXERCISE_HISTORY_RECENT_SESSION_LIMIT = 8
_REP_RANGES = (
    ("1-5", "1–5 повторений", 1, 5),
    ("6-10", "6–10 повторений", 6, 10),
    ("11-15", "11–15 повторений", 11, 15),
    ("16+", "16+ повторений", 16, None),
)


class ExerciseHistoryNotFound(ValueError):
    pass


def _round_estimated_weight(value: float) -> float:
    return math.floor(value * 2 + 0.5) / 2


def _estimated_1rm(weight: float | None, repetitions: int | None) -> float | None:
    if (
        weight is None
        or repetitions is None
        or not 1 <= repetitions <= 10
        or not 0.5 <= weight <= 500
    ):
        return None
    raw_value = weight / (1.0278 - 0.0278 * repetitions)
    return _round_estimated_weight(raw_value)


def _workout_ref(workout: UserWorkout) -> dict:
    return {
        "workout_id": workout.id,
        "workout_title": workout.title,
        "performed_on": workout.scheduled_date,
        "completed_at": workout.completed_at,
    }


def _as_int(value: object) -> int | None:
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _as_float(value: object) -> float | None:
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except TypeError, ValueError:
        return None


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _session_payload(
    workout: UserWorkout,
    exercise: UserWorkoutExercise,
    sets: list,
    *,
    strength_metrics: bool,
) -> dict:
    completed = [item for item in sets if item.is_completed]
    authoritative = [item for item in completed if is_pr_record_set(item)]
    scalar_authoritative = [item for item in authoritative if item.execution_mode not in SIDE_MODES]
    reps = [value for item in completed if (value := completed_set_reps(item)) is not None]
    authoritative_loads = [
        float(item.actual_weight)
        for item in scalar_authoritative
        if strength_metrics and item.actual_weight is not None and float(item.actual_weight) > 0
    ]
    volumes = [
        float(item.actual_reps) * float(item.actual_weight)
        for item in scalar_authoritative
        if strength_metrics and item.actual_reps is not None and item.actual_weight is not None
    ]
    estimates = [
        estimate
        for item in scalar_authoritative
        if strength_metrics
        if (
            estimate := _estimated_1rm(
                float(item.actual_weight) if item.actual_weight is not None else None,
                item.actual_reps,
            )
        )
        is not None
    ]
    serialized_sets = []
    for item in sets:
        load = (
            float(item.actual_weight)
            if strength_metrics and item.actual_weight is not None
            else None
        )
        reps_value = completed_set_reps(item) if item.is_completed else None
        volume_value = (
            completed_set_volume(item) if item.is_completed and strength_metrics else None
        )
        serialized = {
            "set_number": item.set_number,
            "reps": reps_value,
            "load_kg": load,
            "volume_kg": round(float(volume_value), 2) if volume_value is not None else None,
            "rir": item.rir,
            "set_kind": item.set_kind,
            "planned_role": item.planned_role,
            "analytics_bucket": set_analytics_bucket(item),
            "pr_eligible": (
                strength_metrics
                and item.is_completed
                and item.execution_mode not in SIDE_MODES
                and is_pr_record_set(item)
            ),
        }
        if item.execution_mode in SIDE_MODES:
            serialized.update(
                {
                    "execution_mode": item.execution_mode,
                    "first_side": item.first_side,
                    "sides": serialize_sides(item),
                    "is_completed": item.is_completed,
                }
            )
        serialized_sets.append(serialized)
    return {
        "workout": _workout_ref(workout),
        "workout_exercise_id": exercise.id,
        "prescribed_reps": exercise.prescribed_reps,
        "completed_set_count": len(completed),
        "authoritative_set_count": len(authoritative),
        "reps_total": sum(reps) if reps else None,
        "max_authoritative_load_kg": max(authoritative_loads) if authoritative_loads else None,
        "best_set_volume_kg": round(max(volumes), 2) if volumes else None,
        "estimated_1rm_kg": max(estimates) if estimates else None,
        "sets": serialized_sets,
        "_authoritative": authoritative,
    }


def _best_metric(session_facts: list[dict], key: str) -> dict | None:
    candidates = [
        (fact[key], fact)
        for fact in session_facts
        if fact.get(key) is not None and float(fact[key]) > 0
    ]
    if not candidates:
        return None
    value, fact = max(
        candidates,
        key=lambda item: (
            float(item[0]),
            item[1]["workout"]["performed_on"],
            item[1]["workout"]["workout_id"],
        ),
    )
    return {
        "value_kg": float(value),
        "workout": fact["workout"],
        "reps": next(
            (
                item["reps"]
                for item in fact["sets"]
                if item["pr_eligible"] and item["load_kg"] == value
            ),
            None,
        ),
    }


def _rep_prs(session_facts: list[dict]) -> list[dict]:
    result: list[dict[str, object]] = []
    for range_key, label, minimum, maximum in _REP_RANGES:
        matching: list[tuple[dict, dict]] = []
        for fact in session_facts:
            for item in fact["sets"]:
                reps = item["reps"]
                if not item["pr_eligible"] or reps is None or reps < minimum:
                    continue
                if maximum is not None and reps > maximum:
                    continue
                matching.append((fact, item))
        if not matching:
            continue
        best_reps_fact, best_reps_set = max(
            matching,
            key=lambda pair: (
                pair[1]["reps"],
                pair[0]["workout"]["performed_on"],
                pair[0]["workout"]["workout_id"],
                pair[1]["set_number"],
            ),
        )
        loaded = [
            pair for pair in matching if pair[1]["load_kg"] is not None and pair[1]["load_kg"] > 0
        ]
        if loaded:
            best_load_fact, best_load_set = max(
                loaded,
                key=lambda pair: (
                    pair[1]["load_kg"],
                    pair[1]["reps"],
                    pair[0]["workout"]["performed_on"],
                    pair[0]["workout"]["workout_id"],
                    pair[1]["set_number"],
                ),
            )
            best_load = best_load_set["load_kg"]
            best_load_workout = best_load_fact["workout"]
        else:
            best_load = None
            best_load_workout = None
        result.append(
            {
                "range_key": range_key,
                "range_label": label,
                "min_reps": minimum,
                "max_reps": maximum,
                "best_reps": best_reps_set["reps"],
                "best_reps_workout": best_reps_fact["workout"],
                "best_load_kg": best_load,
                "best_load_workout": best_load_workout,
            }
        )
    return result


def _windows(session_facts: list[dict], today: date) -> list[dict]:
    result = []
    for days in (7, 30, 90):
        period_start = today - timedelta(days=days - 1)
        scoped = [
            fact
            for fact in session_facts
            if period_start <= fact["workout"]["performed_on"] <= today
        ]
        reps = [fact["reps_total"] for fact in scoped if fact["reps_total"] is not None]
        loads = [
            fact["max_authoritative_load_kg"]
            for fact in scoped
            if fact["max_authoritative_load_kg"] is not None
        ]
        estimates = [
            fact["estimated_1rm_kg"] for fact in scoped if fact["estimated_1rm_kg"] is not None
        ]
        result.append(
            {
                "days": days,
                "period_start": period_start,
                "period_end": today,
                "performed_session_count": len(scoped),
                "completed_set_count": sum(fact["completed_set_count"] for fact in scoped),
                "authoritative_set_count": sum(fact["authoritative_set_count"] for fact in scoped),
                "reps_total": sum(reps) if reps else None,
                "best_authoritative_load_kg": max(loads) if loads else None,
                "estimated_1rm_kg": max(estimates) if estimates else None,
            }
        )
    return result


def _progression(session_facts: list[dict]) -> list[dict]:
    selected = list(reversed(session_facts[:EXERCISE_HISTORY_SESSION_LIMIT]))
    return [
        {
            "performed_on": fact["workout"]["performed_on"],
            "workout_id": fact["workout"]["workout_id"],
            "max_reps": max(
                (item["reps"] for item in fact["sets"] if item["pr_eligible"] and item["reps"]),
                default=None,
            ),
            "max_authoritative_load_kg": fact["max_authoritative_load_kg"],
            "estimated_1rm_kg": fact["estimated_1rm_kg"],
            "authoritative_set_count": fact["authoritative_set_count"],
        }
        for fact in selected
    ]


def _side_records(db: Session, rows: list) -> list[dict]:
    side_rows = [
        (exercise, workout, workout_set)
        for exercise, workout, workout_set in rows
        if workout_set.is_completed
        and workout_set.execution_mode in SIDE_MODES
        and is_pr_record_set(workout_set)
    ]
    if not side_rows:
        return []
    program_ids = {
        workout.user_program_id for _, workout, _ in side_rows if workout.user_program_id
    }
    revisions: dict[int, list[ProgramRevision]] = defaultdict(list)
    for revision in db.query(ProgramRevision).filter(
        ProgramRevision.user_program_id.in_(program_ids)
    ):
        revisions[revision.user_program_id].append(revision)

    grouped: dict[tuple, dict] = {}
    for exercise, workout, workout_set in side_rows:
        program_revisions = revisions.get(workout.user_program_id, [])
        revision_number = workout.plan_revision_number or _revision_for_completion(
            program_revisions, workout.completed_at
        )
        revision = next(
            (item for item in program_revisions if item.revision_number == revision_number), None
        )
        week_type, week_known = workout_cycle_week_type(db, workout, program_revisions)
        block = _snapshot_block_context(revision, workout) if revision is not None else ("invalid",)
        metadata = _snapshot_metadata(revision)
        metadata_block = (
            _metadata_block_context(metadata, workout.week_number)
            if (metadata is not None and workout.week_number is not None)
            else "invalid"
        )
        verified = bool(
            workout.user_program_id is not None
            and workout.completed_at is not None
            and revision is not None
            and week_known
            and block != ("invalid",)
            and metadata_block != "invalid"
        )
        if verified and workout.source_cycle_week is not None:
            verified = _matches_cycle_plan(
                db, workout.user_program, program_revisions, workout, exercise
            )
        context = {
            "program_id": workout.user_program_id,
            "revision_number": revision_number or None,
            "day_number": workout.day_number,
            "source_template_exercise_id": exercise.source_template_exercise_id,
            "week_type": week_type if week_known else None,
            "planned_role": workout_set.planned_role,
            "planned_position": workout_set.planned_position,
            "verified": verified,
        }
        signature = json.dumps(exercise.prescription, sort_keys=True, ensure_ascii=False)
        for side in workout_set.side_results:
            if not side.is_completed:
                continue
            key = (
                workout_set.execution_mode,
                side.side,
                workout.user_program_id,
                revision_number,
                workout.day_number,
                exercise.exercise_id,
                exercise.source_template_exercise_id,
                exercise.sort_order,
                exercise.prescribed_sets,
                exercise.prescribed_reps,
                signature,
                workout_set.planned_role,
                workout_set.planned_position,
                week_type,
                block,
                metadata_block,
                None if verified else workout.id,
            )
            group = grouped.setdefault(key, {"context": context, "sessions": {}})
            session = group["sessions"].setdefault(
                (workout.id, exercise.id),
                {"workout": _workout_ref(workout), "sets": []},
            )
            session["sets"].append(
                {
                    "set_number": workout_set.set_number,
                    "reps": side.actual_reps,
                    "load_kg": float(side.actual_weight)
                    if side.actual_weight is not None
                    else None,
                    "pr_eligible": True,
                }
            )

    result = []
    for key, group in grouped.items():
        facts = list(group["sessions"].values())
        for fact in facts:
            weights = [
                item["load_kg"]
                for item in fact["sets"]
                if item["load_kg"] is not None and item["load_kg"] > 0
            ]
            estimates = [
                estimate
                for item in fact["sets"]
                if (estimate := _estimated_1rm(item["load_kg"], item["reps"])) is not None
            ]
            fact["max_authoritative_load_kg"] = max(weights) if weights else None
            fact["estimated_1rm_kg"] = max(estimates) if estimates else None
            fact["authoritative_set_count"] = len(fact["sets"])
        facts.sort(
            key=lambda item: (item["workout"]["performed_on"], item["workout"]["workout_id"]),
            reverse=True,
        )
        estimates = [
            fact["estimated_1rm_kg"] for fact in facts if fact["estimated_1rm_kg"] is not None
        ]
        result.append(
            {
                "execution_mode": key[0],
                "side": key[1],
                "context": group["context"],
                "best_authoritative_load": _best_metric(facts, "max_authoritative_load_kg"),
                "estimated_1rm_kg": max(estimates) if estimates else None,
                "rep_prs": _rep_prs(facts),
                "progression": _progression(facts),
            }
        )
    return result


def _progression_events(
    db: Session,
    user: User,
    stored_exercise_ids: set[int],
) -> list[dict]:
    events = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.target_user_id == user.id,
            AuditEvent.action.in_(
                {
                    "progression_proposal.confirm",
                    "progression_proposal.adjust",
                    "progression_proposal.reject",
                }
            ),
        )
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(100)
        .all()
    )
    result: list[dict[str, object]] = []
    for event in events:
        details = event.details if isinstance(event.details, dict) else {}
        exercise_id = _as_int(details.get("exercise_id"))
        if exercise_id is None or exercise_id not in stored_exercise_ids:
            continue
        proposal_id = details.get("proposal_id") or event.resource_id
        if not isinstance(proposal_id, str) or not proposal_id:
            continue
        event_kind = event.action.rsplit(".", 1)[-1]
        target_workout_id = _as_int(details.get("target_workout_id"))
        if target_workout_id is None and event.resource_type == "user_workout":
            target_workout_id = _as_int(event.resource_id)
        result.append(
            {
                "event_id": event.id,
                "event_kind": event_kind,
                "proposal_id": proposal_id,
                "target_workout_id": target_workout_id,
                "exercise_id": exercise_id,
                "rule_id": details.get("rule_id")
                if isinstance(details.get("rule_id"), str)
                else None,
                "rule_kind": details.get("rule_kind")
                if isinstance(details.get("rule_kind"), str)
                else None,
                "rule_snapshot": details.get("rule_snapshot")
                if isinstance(details.get("rule_snapshot"), dict)
                else {},
                "source_evidence_ids": _as_string_list(details.get("source_evidence_ids")),
                "reason_codes": _as_string_list(details.get("reason_codes")),
                "proposed_weight_kg": _as_float(details.get("proposed_weight")),
                "adjusted_weight_kg": _as_float(details.get("adjusted_weight")),
                "result": details.get("result")
                if isinstance(details.get("result"), dict)
                else None,
                "created_at": event.created_at,
            }
        )
    return result


def build_exercise_history(
    db: Session,
    user: User,
    exercise_id: int,
) -> dict:
    visible = get_visible_exercise_display_map(db, user)
    exercise = visible.get(exercise_id)
    if exercise is None:
        raise ExerciseHistoryNotFound("Exercise not found")

    metric_type = exercise_metric_type(exercise)
    stored_exercise_ids = {exercise_id, exercise.id}
    if exercise.source_exercise_id is not None:
        stored_exercise_ids.add(exercise.source_exercise_id)

    rows = (
        db.query(UserWorkoutExercise, UserWorkout, UserWorkoutSet)
        .join(UserWorkout, UserWorkout.id == UserWorkoutExercise.workout_id)
        .outerjoin(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .outerjoin(ImportedWorkout, ImportedWorkout.workout_id == UserWorkout.id)
        .join(UserWorkoutSet, UserWorkoutSet.workout_exercise_id == UserWorkoutExercise.id)
        .options(selectinload(UserWorkoutSet.side_results))
        .filter(
            workout_owner_id() == user.id,
            UserWorkout.status == "completed",
            UserWorkoutExercise.exercise_id.in_(stored_exercise_ids),
            or_(
                UserWorkoutExercise.metric_type.is_(None),
                UserWorkoutExercise.metric_type == metric_type,
            ),
            or_(
                UserWorkoutSet.is_completed.is_(True),
                UserWorkoutSet.side_results.any(
                    or_(
                        UserWorkoutSetSide.is_completed.is_(True),
                        UserWorkoutSetSide.actual_reps.is_not(None),
                        UserWorkoutSetSide.actual_weight.is_not(None),
                        UserWorkoutSetSide.rir.is_not(None),
                        UserWorkoutSetSide.reached_failure.is_not(None),
                    )
                ),
            ),
        )
        .order_by(
            UserWorkout.scheduled_date.desc(),
            UserWorkout.id.desc(),
            UserWorkoutExercise.id.desc(),
            UserWorkoutSet.set_number.asc(),
            UserWorkoutSet.id.asc(),
        )
        .all()
    )
    grouped: dict[int, dict] = {}
    for workout_exercise, workout, workout_set in rows:
        if not counts_toward_working_volume(workout_set):
            continue
        group = grouped.setdefault(
            workout_exercise.id,
            {"workout": workout, "exercise": workout_exercise, "sets": []},
        )
        group["sets"].append(workout_set)
    session_facts = [
        _session_payload(
            item["workout"],
            item["exercise"],
            item["sets"],
            strength_metrics=metric_type == "strength",
        )
        for item in grouped.values()
    ]
    session_facts.sort(
        key=lambda item: (
            item["workout"]["performed_on"],
            item["workout"]["workout_id"],
            item["workout_exercise_id"],
        ),
        reverse=True,
    )
    estimated_candidates = []
    for fact in session_facts:
        for item in fact["sets"]:
            estimate = _estimated_1rm(item["load_kg"], item["reps"])
            if item["pr_eligible"] and estimate is not None:
                estimated_candidates.append(
                    {
                        "value_kg": estimate,
                        "workout": fact["workout"],
                        "reps": item["reps"],
                        "load_kg": item["load_kg"],
                    }
                )
    estimated = (
        max(
            estimated_candidates,
            key=lambda item: (
                item["value_kg"],
                item["workout"]["performed_on"],
                item["workout"]["workout_id"],
            ),
        )
        if estimated_candidates
        else None
    )
    history_limit_reached = len(session_facts) > EXERCISE_HISTORY_SESSION_LIMIT
    recent_facts = session_facts[:EXERCISE_HISTORY_RECENT_SESSION_LIMIT]
    all_facts_for_progression = session_facts
    progression_events = _progression_events(db, user, stored_exercise_ids)
    return {
        "exercise_id": exercise_id,
        "exercise_title": exercise.title,
        "metric_type": metric_type,
        "load_unit": "kg" if metric_type == "strength" else None,
        "last_performed": session_facts[0]["workout"] if session_facts else None,
        "best_authoritative_load": _best_metric(
            session_facts if metric_type == "strength" else [],
            "max_authoritative_load_kg",
        ),
        "estimated_1rm": estimated if metric_type == "strength" else None,
        "rep_prs": _rep_prs(session_facts),
        "side_records": _side_records(db, rows) if metric_type == "strength" else [],
        "windows": _windows(session_facts, today_for_user(user)),
        "recent_sessions": recent_facts,
        "progression": _progression(all_facts_for_progression),
        "progression_events": progression_events,
        "history_truncated": history_limit_reached,
    }
