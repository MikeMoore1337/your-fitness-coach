from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from sqlalchemy.orm import Session, joinedload

from fitminiapp_api.models.program import (
    TrainingBlock,
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.services.prescription_semantics import (
    is_pr_record_role,
    parse_prescription_plan,
)
from fitminiapp_api.services.workout_metrics import workout_exercise_metric_type
from fitminiapp_api.services.workouts import is_pr_record_set

ProgressionOutcome = Literal[
    "consider_progressing",
    "hold",
    "review",
    "consider_reducing",
]
LoadUnit = Literal["kg", "lb"]

RULESET_VERSION = "progression-guidance-v1"
_REP_RANGE = re.compile(r"^\s*(\d{1,3})(?:\s*[-–—]\s*(\d{1,3}))?\s*$")
_PROGRESS_MESSAGES: dict[ProgressionOutcome, str] = {
    "consider_progressing": "Можно рассмотреть небольшое увеличение веса",
    "hold": "Пока оставьте текущую нагрузку",
    "review": "Данных недостаточно — сначала закрепите текущий диапазон повторений",
    "consider_reducing": "Можно рассмотреть небольшое снижение веса",
}


@dataclass(frozen=True)
class RepTarget:
    minimum: int
    maximum: int


@dataclass(frozen=True)
class SessionFacts:
    workout_id: int
    scheduled_date: date
    working_set_count: int
    load: float | None
    reps_min: int | None
    reps_max: int | None
    rir_values: tuple[str, ...]
    reached_failure: bool
    complete: bool
    completion_feedback: str | None


def parse_rep_target(value: str) -> RepTarget | None:
    match = _REP_RANGE.fullmatch(value)
    if not match:
        return None
    minimum = int(match.group(1))
    maximum = int(match.group(2) or minimum)
    if minimum < 1 or maximum < minimum:
        return None
    return RepTarget(minimum=minimum, maximum=maximum)


def _session_facts(exercise: UserWorkoutExercise) -> SessionFacts:
    working_sets = [item for item in exercise.sets if item.is_completed and is_pr_record_set(item)]
    reps = [item.actual_reps for item in working_sets if item.actual_reps is not None]
    weights = [float(item.actual_weight) for item in working_sets if item.actual_weight is not None]
    unique_weights = set(weights)
    complete = (
        len(working_sets) == exercise.prescribed_sets
        and len(reps) == len(working_sets)
        and len(weights) == len(working_sets)
        and len(unique_weights) == 1
        and bool(weights)
        and weights[0] > 0
    )
    return SessionFacts(
        workout_id=exercise.workout.id,
        scheduled_date=exercise.workout.scheduled_date,
        working_set_count=len(working_sets),
        load=weights[0] if complete else None,
        reps_min=min(reps) if reps else None,
        reps_max=max(reps) if reps else None,
        rir_values=tuple(item.rir for item in working_sets if item.rir is not None),
        reached_failure=any(item.reached_failure is True for item in working_sets),
        complete=complete,
        completion_feedback=exercise.workout.completion_feedback,
    )


def _session_evidence(session: SessionFacts, unit: LoadUnit) -> dict:
    return {
        "workout_id": session.workout_id,
        "scheduled_date": session.scheduled_date,
        "working_set_count": session.working_set_count,
        "load": session.load,
        "load_unit": unit,
        "reps_min": session.reps_min,
        "reps_max": session.reps_max,
        "rir_recorded_set_count": len(session.rir_values),
        "rir_values": list(session.rir_values),
        "reached_failure": session.reached_failure,
        "completion_feedback": session.completion_feedback,
    }


def evaluate_progression(
    *,
    prescribed_sets: int,
    prescribed_reps: str,
    sessions: list[SessionFacts],
    load_unit: LoadUnit = "kg",
    configured_increment: float | None = None,
    context_changed: bool = False,
) -> dict:
    target = parse_rep_target(prescribed_reps)
    reason_keys: list[str] = []
    outcome: ProgressionOutcome = "review"
    required_session_count = 2
    suggested_increment: float | None = None
    suggested_weight: float | None = None

    if target is None:
        reason_keys.append("unsupported_rep_prescription")
    else:
        complete_sessions = [item for item in sessions if item.complete]
        if context_changed:
            reason_keys.append("program_context_changed")
        if len(complete_sessions) < 2:
            reason_keys.append("too_few_comparable_sessions")
            if any(not item.complete for item in sessions):
                reason_keys.append("incomplete_session_facts")
        else:
            latest_two = complete_sessions[:2]
            same_load_two = len({item.load for item in latest_two}) == 1
            all_below = same_load_two and all(
                item.reps_max is not None and item.reps_max < target.minimum for item in latest_two
            )
            if all_below:
                outcome = "consider_reducing"
                reason_keys.append("below_range_two_sessions")
                required_session_count = 2
            else:
                full_positive_rir = all(
                    len(item.rir_values) == item.working_set_count
                    and set(item.rir_values).issubset({"1", "2", "3", "4+"})
                    and not item.reached_failure
                    for item in latest_two
                )
                required_session_count = 2 if full_positive_rir else 3
                considered = complete_sessions[:required_session_count]
                same_load = (
                    len(considered) == required_session_count
                    and len({item.load for item in considered}) == 1
                )
                top_range = same_load and all(
                    item.reps_min is not None and item.reps_min >= target.maximum
                    for item in considered
                )
                unsafe_effort = any(
                    item.reached_failure or "0" in item.rir_values for item in considered
                )
                if top_range and not unsafe_effort:
                    outcome = "consider_progressing"
                    reason_keys.append("top_range_repeated")
                    reason_keys.append(
                        "full_rir_coverage" if full_positive_rir else "conservative_without_rir"
                    )
                else:
                    outcome = "hold"
                    if len(considered) < required_session_count:
                        reason_keys.append("need_one_more_stable_session")
                    elif not same_load:
                        reason_keys.append("load_not_stable")
                    elif unsafe_effort:
                        reason_keys.append("zero_rir_or_failure_recorded")
                    else:
                        reason_keys.append("target_range_not_repeated")

    base_load = next(
        (item.load for item in sessions if item.complete and item.load is not None), None
    )
    if configured_increment is not None and configured_increment > 0 and base_load is not None:
        if outcome == "consider_progressing":
            suggested_increment = configured_increment
            suggested_weight = round(base_load + configured_increment, 6)
        elif outcome == "consider_reducing" and base_load > configured_increment:
            suggested_increment = -configured_increment
            suggested_weight = round(base_load - configured_increment, 6)

    if outcome == "consider_progressing":
        detail = "Верхняя граница повторений стабильно достигнута. " + (
            "Доступный шаг оборудования учтён; решение остаётся за вами."
            if suggested_weight is not None
            else "Проверьте доступный шаг оборудования и примите решение сами."
        )
    elif outcome == "consider_reducing":
        detail = (
            "В двух сопоставимых тренировках рабочие подходы оставались ниже заданного "
            "диапазона. Это не оценка восстановления или перетренированности."
        )
    elif outcome == "hold":
        detail = "Последние результаты ещё не подтверждают устойчивое изменение нагрузки."
    else:
        detail = "Нужны полные сопоставимые рабочие подходы в текущем контексте программы."

    return {
        "ruleset_version": RULESET_VERSION,
        "outcome": outcome,
        "message": _PROGRESS_MESSAGES[outcome],
        "detail": detail,
        "suggested_increment": suggested_increment,
        "suggested_weight": suggested_weight,
        "load_unit": load_unit,
        "evidence": {
            "target_reps_min": target.minimum if target else None,
            "target_reps_max": target.maximum if target else None,
            "prescribed_sets": prescribed_sets,
            "comparable_session_count": len([item for item in sessions if item.complete]),
            "required_session_count": required_session_count,
            "working_set_count": sum(item.working_set_count for item in sessions),
            "rir_recorded_set_count": sum(len(item.rir_values) for item in sessions),
            "reason_keys": reason_keys,
            "sessions": [_session_evidence(item, load_unit) for item in sessions[:3]],
        },
    }


def _block_id_for_date(blocks: list[TrainingBlock], value: date) -> int | None:
    return next((item.id for item in blocks if item.start_date <= value <= item.end_date), None)


def build_progression_guidance(
    db: Session,
    user: User,
    workout: UserWorkout,
) -> dict[int, dict]:
    exercise_ids = {
        item.exercise_id
        for item in workout.exercises
        if workout_exercise_metric_type(item) == "strength"
    }
    if not exercise_ids:
        return {}

    blocks = (
        db.query(TrainingBlock)
        .filter(TrainingBlock.user_program_id == workout.user_program_id)
        .order_by(TrainingBlock.start_date, TrainingBlock.id)
        .all()
    )
    current_block_id = _block_id_for_date(blocks, workout.scheduled_date)
    candidates = (
        db.query(UserWorkoutExercise)
        .join(UserWorkout, UserWorkoutExercise.workout_id == UserWorkout.id)
        .join(UserProgram, UserWorkout.user_program_id == UserProgram.id)
        .options(joinedload(UserWorkoutExercise.sets), joinedload(UserWorkoutExercise.workout))
        .filter(
            UserProgram.user_id == user.id,
            UserWorkout.user_program_id == workout.user_program_id,
            UserWorkout.status == "completed",
            UserWorkout.scheduled_date < workout.scheduled_date,
            UserWorkoutExercise.exercise_id.in_(exercise_ids),
        )
        .order_by(
            UserWorkoutExercise.exercise_id,
            UserWorkout.scheduled_date.desc(),
            UserWorkout.completed_at.desc(),
            UserWorkout.id.desc(),
        )
        .all()
    )

    guidance: dict[int, dict] = {}
    for current in workout.exercises:
        if workout_exercise_metric_type(current) == "cardio":
            continue
        plan = parse_prescription_plan(current.prescription, metric_type="strength")
        if plan is not None and (
            any(not is_pr_record_role(segment.role) for segment in plan.segments)
            or any(group.kind != "sequence" for group in plan.groups)
        ):
            unsupported = evaluate_progression(
                prescribed_sets=current.prescribed_sets,
                prescribed_reps=current.prescribed_reps,
                sessions=[],
                load_unit="kg",
            )
            unsupported["evidence"]["reason_keys"] = [
                "advanced_prescription_requires_method_aware_review"
            ]
            guidance[current.id] = unsupported
            continue
        target = parse_rep_target(current.prescribed_reps)
        same_exercise = [item for item in candidates if item.exercise_id == current.exercise_id]
        comparable = [
            item
            for item in same_exercise
            if item.prescribed_sets == current.prescribed_sets
            and parse_rep_target(item.prescribed_reps) == target
            and _block_id_for_date(blocks, item.workout.scheduled_date) == current_block_id
        ]
        facts = [_session_facts(item) for item in comparable]
        guidance[current.id] = evaluate_progression(
            prescribed_sets=current.prescribed_sets,
            prescribed_reps=current.prescribed_reps,
            sessions=facts,
            load_unit="kg",
            context_changed=bool(same_exercise and not comparable),
        )
    return guidance
