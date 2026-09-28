from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from sqlalchemy.orm import Session, joinedload, selectinload

from fitminiapp_api.core.timezone import today_for_user
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.program import (
    ProgramRevision,
    TrainingBlock,
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.program import PrescriptionRepTarget, ProgramCoachingRule
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.prescription_semantics import parse_prescription_plan
from fitminiapp_api.services.program_common import ProgramError
from fitminiapp_api.services.program_versioning import get_program_for_actor
from fitminiapp_api.services.workout_metrics import (
    validate_workout_set_changes,
    workout_exercise_metric_type,
)
from fitminiapp_api.services.workout_sync import (
    WorkoutSetSyncError,
    apply_workout_set_update,
    replayed_workout_set,
)
from fitminiapp_api.services.workouts import is_pr_record_set

ProgressionOutcome = Literal[
    "consider_progressing",
    "hold",
    "review",
    "consider_reducing",
]
LoadUnit = Literal["kg", "lb"]

RULESET_VERSION = "progression-guidance-v2"
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
    source_set_ids: tuple[int, ...] = ()


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
        source_set_ids=tuple(item.id for item in working_sets),
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


@dataclass(frozen=True)
class ProgressionSetSelection:
    role: str | None
    positions: tuple[int, ...]
    expected_count: int
    target_reps: str | None
    relative_backoffs: tuple[tuple[int, float], ...] = ()
    reason_code: str | None = None


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _progression_decision_fingerprint(
    *,
    proposal_id: str,
    program_id: int,
    workout_id: int,
    exercise_id: int,
    decision: Literal["confirm", "reject", "adjust"],
    expected_revision_number: int,
    expected_set_versions: dict[int, int],
    adjusted_weight: float | None,
) -> str:
    return _sha256(
        {
            "proposal_id": proposal_id,
            "target": [program_id, expected_revision_number, workout_id, exercise_id],
            "decision": decision,
            "expected_set_versions": (
                {str(key): value for key, value in sorted(expected_set_versions.items())}
                if decision in {"confirm", "adjust"}
                else {}
            ),
            "adjusted_weight": adjusted_weight if decision == "adjust" else None,
        }
    )


def _rule_snapshot(rule: ProgramCoachingRule | None) -> dict[str, object]:
    return rule.model_dump(mode="json", exclude_none=True) if rule is not None else {}


def _rule_id(rule_snapshot: dict[str, object]) -> str:
    return _sha256({"ruleset_version": RULESET_VERSION, "rule": rule_snapshot})


def _rep_target_text(value: PrescriptionRepTarget | None) -> str | None:
    if value is None:
        return None
    if value.kind == "exact":
        return str(value.value)
    if value.kind == "range":
        return f"{value.min_reps}-{value.max_reps}"
    if value.kind == "amrap":
        return "AMRAP"
    return None


def _progression_set_selection(
    exercise: UserWorkoutExercise,
    *,
    rule_kind: str | None = None,
) -> ProgressionSetSelection:
    try:
        plan = parse_prescription_plan(exercise.prescription, metric_type="strength")
    except ProgramError, TypeError, ValueError:
        return ProgressionSetSelection(None, (), 0, None, reason_code="invalid_prescription")

    if plan is None:
        if rule_kind == "amrap_success_failure" and exercise.prescribed_sets != 1:
            return ProgressionSetSelection(None, (), 0, None, reason_code="ambiguous_amrap_sets")
        return ProgressionSetSelection(
            role=None,
            positions=(),
            expected_count=exercise.prescribed_sets,
            target_reps=exercise.prescribed_reps,
        )

    if rule_kind == "amrap_success_failure":
        selected = [
            segment
            for segment in plan.segments
            if segment.rep_target is not None and segment.rep_target.kind == "amrap"
        ]
        if len(selected) != 1:
            return ProgressionSetSelection(None, (), 0, None, reason_code="ambiguous_amrap_sets")
        anchor = selected[0]
        backoffs = [segment for segment in plan.segments if segment.role == "backoff"]
        amrap_relative_backoffs: list[tuple[int, float]] = []
        for segment in backoffs:
            target = segment.load_target
            if (
                target.kind != "relative_to_top"
                or target.value is None
                or not 0 < target.value <= 1
            ):
                return ProgressionSetSelection(
                    anchor.role,
                    (anchor.position,),
                    1,
                    _rep_target_text(anchor.rep_target),
                    reason_code="advanced_method_requires_review",
                )
            amrap_relative_backoffs.append((segment.position, target.value))
        return ProgressionSetSelection(
            role=anchor.role,
            positions=(anchor.position,),
            expected_count=1,
            target_reps=_rep_target_text(anchor.rep_target),
            relative_backoffs=tuple(amrap_relative_backoffs),
        )

    top_sets = [segment for segment in plan.segments if segment.role == "top"]
    if top_sets:
        if len(top_sets) != 1:
            return ProgressionSetSelection(
                "top", (), 0, None, reason_code="advanced_method_requires_review"
            )
        top_relative_backoffs: list[tuple[int, float]] = []
        for segment in plan.segments:
            if segment.role != "backoff":
                continue
            target = segment.load_target
            if (
                target.kind != "relative_to_top"
                or target.value is None
                or not 0 < target.value <= 1
            ):
                return ProgressionSetSelection(
                    "top",
                    (top_sets[0].position,),
                    1,
                    _rep_target_text(top_sets[0].rep_target),
                    reason_code="advanced_method_requires_review",
                )
            top_relative_backoffs.append((segment.position, target.value))
        return ProgressionSetSelection(
            role="top",
            positions=(top_sets[0].position,),
            expected_count=1,
            target_reps=_rep_target_text(top_sets[0].rep_target),
            relative_backoffs=tuple(top_relative_backoffs),
        )

    if any(group.kind == "circuit" for group in plan.groups):
        return ProgressionSetSelection(
            None, (), 0, None, reason_code="advanced_method_requires_review"
        )
    working = [segment for segment in plan.segments if segment.role == "working"]
    if not working:
        return ProgressionSetSelection(
            None, (), 0, None, reason_code="advanced_method_requires_review"
        )
    target_reps = {_rep_target_text(segment.rep_target) for segment in working}
    if len(target_reps) != 1:
        return ProgressionSetSelection(None, (), 0, None, reason_code="incompatible_prescription")
    return ProgressionSetSelection(
        role="working",
        positions=tuple(segment.position for segment in working),
        expected_count=len(working),
        target_reps=next(iter(target_reps)),
    )


def _driving_set_rows(
    exercise: UserWorkoutExercise,
    selection: ProgressionSetSelection,
) -> list[UserWorkoutSet]:
    if selection.reason_code is not None:
        return []
    if selection.role is None:
        return [
            item for item in exercise.sets if item.planned_role is None and is_pr_record_set(item)
        ]
    positions = set(selection.positions)
    return [
        item
        for item in exercise.sets
        if item.planned_position in positions
        and item.planned_role == selection.role
        and (item.set_kind is None or item.set_kind == "working")
    ]


def _session_facts_for_selection(
    exercise: UserWorkoutExercise,
    selection: ProgressionSetSelection,
) -> SessionFacts:
    rows = _driving_set_rows(exercise, selection)
    completed = [item for item in rows if item.is_completed]
    reps = [item.actual_reps for item in completed if item.actual_reps is not None]
    weights = [float(item.actual_weight) for item in completed if item.actual_weight is not None]
    complete = (
        len(rows) == selection.expected_count
        and len(completed) == selection.expected_count
        and len(reps) == selection.expected_count
        and len(weights) == selection.expected_count
        and len(set(weights)) == 1
        and bool(weights)
        and weights[0] > 0
    )
    return SessionFacts(
        workout_id=exercise.workout.id,
        scheduled_date=exercise.workout.scheduled_date,
        working_set_count=len(completed),
        load=weights[0] if complete else None,
        reps_min=min(reps) if reps else None,
        reps_max=max(reps) if reps else None,
        rir_values=tuple(item.rir for item in completed if item.rir is not None),
        reached_failure=any(item.reached_failure is True for item in completed),
        complete=complete,
        completion_feedback=exercise.workout.completion_feedback,
        source_set_ids=tuple(item.id for item in completed),
    )


def _selection_signature(exercise: UserWorkoutExercise) -> tuple[object, ...]:
    try:
        plan = parse_prescription_plan(exercise.prescription, metric_type="strength")
    except ProgramError, TypeError, ValueError:
        return ("invalid",)
    return (
        exercise.prescribed_sets,
        exercise.prescribed_reps,
        plan.model_dump(mode="json") if plan is not None else None,
    )


def _week_block_number(metadata: object, week_number: int) -> int | None:
    if not isinstance(metadata, dict):
        return None
    blocks = metadata.get("training_blocks")
    if not isinstance(blocks, list):
        return None
    matches = [
        item.get("block_number")
        for item in blocks
        if isinstance(item, dict)
        and isinstance(item.get("block_number"), int)
        and isinstance(item.get("week_start"), int)
        and isinstance(item.get("week_end"), int)
        and item["week_start"] <= week_number <= item["week_end"]
    ]
    return matches[0] if len(set(matches)) == 1 else None


def _resolve_coaching_rule(
    metadata: object,
    *,
    exercise_id: int,
    week_number: int,
) -> tuple[ProgramCoachingRule | None, str | None]:
    if not isinstance(metadata, dict):
        return None, None
    raw_rules = metadata.get("coaching_rules")
    if raw_rules is None:
        return None, None
    if not isinstance(raw_rules, list):
        return None, "invalid_coaching_rule"
    parsed: list[ProgramCoachingRule] = []
    try:
        parsed = [ProgramCoachingRule.model_validate(item) for item in raw_rules]
    except TypeError, ValueError:
        return None, "invalid_coaching_rule"

    block_number = _week_block_number(metadata, week_number)
    applicable: list[tuple[int, ProgramCoachingRule]] = []
    for rule in parsed:
        if rule.week_start is not None and week_number < rule.week_start:
            continue
        if rule.week_end is not None and week_number > rule.week_end:
            continue
        if rule.scope == "exercise":
            if rule.exercise_id != exercise_id:
                continue
            priority = 3
        elif rule.scope == "block":
            if block_number is None or rule.block_number != block_number:
                continue
            priority = 2
        else:
            priority = 1
        applicable.append((priority, rule))

    if not applicable:
        return None, None
    highest = max(priority for priority, _rule in applicable)
    winning = [rule for priority, rule in applicable if priority == highest]
    by_snapshot = {_canonical_json(_rule_snapshot(rule)): rule for rule in winning}
    if len(by_snapshot) != 1:
        return None, "conflicting_coaching_rules"
    return next(iter(by_snapshot.values())), None


def _current_program_snapshot(
    db: Session,
    workout: UserWorkout,
) -> tuple[UserProgram | None, ProgramRevision | None, dict[str, object], str | None]:
    program = (
        db.query(UserProgram)
        .options(joinedload(UserProgram.template))
        .filter(UserProgram.id == workout.user_program_id)
        .one_or_none()
    )
    if program is None:
        return None, None, {}, "program_context_missing"
    revision = (
        db.query(ProgramRevision)
        .filter(
            ProgramRevision.user_program_id == program.id,
            ProgramRevision.revision_number == program.current_revision_number,
        )
        .one_or_none()
        if program.current_revision_number > 0
        else None
    )
    if program.current_revision_number > 0 and revision is None:
        return program, None, {}, "missing_program_revision"
    snapshot = (
        revision.snapshot if revision is not None and isinstance(revision.snapshot, dict) else {}
    )
    snapshot_program = snapshot.get("program") if isinstance(snapshot, dict) else None
    metadata = (
        snapshot_program.get("program_metadata") if isinstance(snapshot_program, dict) else None
    )
    if not isinstance(metadata, dict):
        metadata = program.template.program_metadata if program.template is not None else None
    return program, revision, metadata if isinstance(metadata, dict) else {}, None


def _snapshot_matches_target(
    revision: ProgramRevision | None,
    workout: UserWorkout,
    exercise: UserWorkoutExercise,
) -> bool:
    if revision is None:
        return True
    snapshot = revision.snapshot if isinstance(revision.snapshot, dict) else {}
    workouts = snapshot.get("workouts")
    if not isinstance(workouts, list):
        return False
    workout_snapshot = next(
        (item for item in workouts if isinstance(item, dict) and item.get("id") == workout.id),
        None,
    )
    if workout_snapshot is None or not isinstance(workout_snapshot.get("exercises"), list):
        return False
    exercise_snapshot = next(
        (
            item
            for item in workout_snapshot["exercises"]
            if isinstance(item, dict)
            and item.get("exercise_id") == exercise.exercise_id
            and item.get("source_template_exercise_id") == exercise.source_template_exercise_id
            and item.get("sort_order") == exercise.sort_order
        ),
        None,
    )
    if exercise_snapshot is None:
        return False
    return all(
        exercise_snapshot.get(field) == expected
        for field, expected in (
            ("metric_type", workout_exercise_metric_type(exercise)),
            ("prescribed_sets", exercise.prescribed_sets),
            ("prescribed_reps", exercise.prescribed_reps),
            ("prescribed_duration_minutes", exercise.prescribed_duration_minutes),
            ("rest_seconds", exercise.rest_seconds),
            ("prescription", exercise.prescription),
        )
    )


def _revision_for_completion(
    revisions: list[ProgramRevision],
    completed_at: datetime | None,
) -> int:
    if completed_at is None:
        return 0
    eligible = [item.revision_number for item in revisions if item.created_at <= completed_at]
    return max(eligible, default=0)


def _review_result(
    *,
    prescribed_sets: int,
    prescribed_reps: str,
    reason_code: str,
    detail: str,
) -> dict:
    result = evaluate_progression(
        prescribed_sets=prescribed_sets,
        prescribed_reps=prescribed_reps,
        sessions=[],
        load_unit="kg",
    )
    result["evidence"]["reason_keys"] = [reason_code]
    result["detail"] = detail
    return result


def _progression_failure(session: SessionFacts) -> bool:
    return session.reached_failure or "0" in session.rir_values


def _rule_guidance(
    *,
    rule: ProgramCoachingRule,
    selection: ProgressionSetSelection,
    current: UserWorkoutExercise,
    sessions: list[SessionFacts],
    current_is_deload: bool,
) -> tuple[dict, str, int | None, int | None]:
    base = _review_result(
        prescribed_sets=selection.expected_count or current.prescribed_sets,
        prescribed_reps=selection.target_reps or current.prescribed_reps,
        reason_code="rule_requires_review",
        detail="Для этого правила пока недостаточно проверяемых данных.",
    )
    base["evidence"]["comparable_session_count"] = sum(item.complete for item in sessions)
    base["evidence"]["sessions"] = [_session_evidence(item, "kg") for item in sessions[:3]]
    base["evidence"]["working_set_count"] = sum(item.working_set_count for item in sessions)
    base["evidence"]["rir_recorded_set_count"] = sum(len(item.rir_values) for item in sessions)
    proposed_action = "hold"
    volume_percent = rule.deload_volume_percent
    intensity_percent = rule.deload_intensity_percent

    if selection.reason_code is not None:
        base["evidence"]["reason_keys"] = [selection.reason_code]
        base["detail"] = (
            "Структура подходов не позволяет однозначно выбрать progression-driving set."
        )
        return base, "hold", volume_percent, intensity_percent

    if rule.kind == "fixed_prescription":
        base["outcome"] = "hold"
        base["message"] = "Оставьте назначение без изменений"
        base["detail"] = "Для фиксированного назначения правило не предлагает прогрессию."
        base["evidence"]["reason_keys"] = ["fixed_prescription"]
        return base, "hold", volume_percent, intensity_percent

    if rule.kind == "percentage_training_max":
        base["evidence"]["reason_keys"] = ["missing_training_max_source"]
        base["detail"] = "В программе нет сохранённого тренировочного максимума для этого правила."
        return base, "hold", volume_percent, intensity_percent

    if rule.kind == "deload":
        if current_is_deload:
            base["evidence"]["reason_keys"] = ["scheduled_deload_block"]
            base["detail"] = (
                "Облегчённый блок уже задан в программе; предложение требует проверки параметров."
            )
            return base, "deload", volume_percent, intensity_percent
        base["evidence"]["reason_keys"] = ["missing_deload_trigger"]
        base["detail"] = "В правиле не задано событие, которое запускает облегчённый блок."
        return base, "hold", volume_percent, intensity_percent

    if rule.kind == "rir_rpe" and rule.effort_target is not None:
        if rule.effort_target.kind == "rpe":
            base["evidence"]["reason_keys"] = ["missing_rpe_evidence"]
            base["detail"] = (
                "В данных подходов нет фактического RPE; пересчёт из RIR не выполняется."
            )
            return base, "hold", volume_percent, intensity_percent
        if not sessions or not sessions[0].complete:
            base["evidence"]["reason_keys"] = ["missing_rir_evidence"]
            base["detail"] = "Нужна полная сопоставимая тренировка с фактическим запасом повторов."
            return base, "hold", volume_percent, intensity_percent
        latest = sessions[0]
        if len(latest.rir_values) != latest.working_set_count:
            base["evidence"]["reason_keys"] = ["missing_rir_evidence"]
            base["detail"] = "Не для каждого progression-driving подхода записан RIR."
            return base, "hold", volume_percent, intensity_percent
        if _progression_failure(latest):
            base["outcome"] = "hold"
            base["evidence"]["reason_keys"] = ["zero_rir_or_failure_recorded"]
            base["detail"] = "Отказ или RIR 0 блокирует увеличение нагрузки."
            proposed_action = "reset_recommended" if rule.reset_on_failure else "hold"
            return base, proposed_action, volume_percent, intensity_percent
        target_text = (
            _rep_target_text(rule.rep_target)
            if rule.rep_target is not None
            else selection.target_reps
        )
        target = parse_rep_target(target_text or "")
        if target is None or latest.reps_min is None or latest.reps_min < target.minimum:
            base["outcome"] = "hold"
            base["evidence"]["reason_keys"] = ["minimum_reps_not_met"]
            return base, "hold", volume_percent, intensity_percent
        target_rir = rule.effort_target.value
        target_rir_number = 4 if target_rir == "4+" else float(target_rir or 0)
        recorded_numbers = [4 if value == "4+" else int(value) for value in latest.rir_values]
        if any(value < target_rir_number for value in recorded_numbers):
            base["outcome"] = "hold"
            base["evidence"]["reason_keys"] = ["rir_target_not_met"]
            return base, "hold", volume_percent, intensity_percent
        if rule.increment_value is None:
            base["evidence"]["reason_keys"] = ["missing_configured_increment"]
            return base, "hold", volume_percent, intensity_percent
        if rule.increment_unit not in {"kg", "percent"}:
            base["evidence"]["reason_keys"] = ["incompatible_load_unit"]
            return base, "hold", volume_percent, intensity_percent
        delta = (
            latest.load * rule.increment_value / 100
            if rule.increment_unit == "percent" and latest.load is not None
            else rule.increment_value
        )
        if latest.load is None:
            base["evidence"]["reason_keys"] = ["missing_load_evidence"]
            return base, "hold", volume_percent, intensity_percent
        base.update(
            outcome="consider_progressing",
            message=_PROGRESS_MESSAGES["consider_progressing"],
            detail="Требование по фактическому RIR выполнено; шаг взят из сохранённого правила.",
            suggested_increment=delta,
            suggested_weight=latest.load + delta,
        )
        base["evidence"]["reason_keys"] = ["rir_target_met", "configured_increment"]
        return base, "set_load", volume_percent, intensity_percent

    if rule.kind == "amrap_success_failure":
        if not sessions:
            base["evidence"]["reason_keys"] = ["missing_amrap_evidence"]
            return base, "hold", volume_percent, intensity_percent
        latest = sessions[0]
        actual_reps = latest.reps_max
        if not latest.complete or actual_reps is None:
            base["evidence"]["reason_keys"] = ["missing_amrap_evidence"]
            return base, "hold", volume_percent, intensity_percent
        success = actual_reps >= (rule.amrap_min_reps or 0)
        if success:
            if rule.increment_value is None or rule.increment_unit not in {"kg", "lb"}:
                base["outcome"] = "hold"
                base["evidence"]["reason_keys"] = ["amrap_success_without_increment"]
                base["detail"] = "Порог AMRAP выполнен, но точный шаг нагрузки не задан."
                return base, "hold", volume_percent, intensity_percent
            if rule.increment_unit != "kg":
                base["evidence"]["reason_keys"] = ["incompatible_load_unit"]
                return base, "hold", volume_percent, intensity_percent
            base.update(
                outcome="consider_progressing",
                message=_PROGRESS_MESSAGES["consider_progressing"],
                detail="Порог AMRAP выполнен; шаг взят из сохранённого правила.",
                suggested_increment=rule.increment_value,
                suggested_weight=(latest.load + rule.increment_value)
                if latest.load is not None
                else None,
            )
            if latest.load is None:
                base["evidence"]["reason_keys"] = ["missing_load_evidence"]
                return base, "hold", volume_percent, intensity_percent
            base["evidence"]["reason_keys"] = ["amrap_success", "configured_increment"]
            return base, "set_load", volume_percent, intensity_percent

        base["outcome"] = "review" if rule.amrap_failure_action == "manual_review" else "hold"
        base["evidence"]["reason_keys"] = ["amrap_threshold_not_met"]
        if rule.reset_on_failure:
            base["evidence"]["reason_keys"].append("reset_target_missing")
            base["detail"] = "Порог AMRAP не выполнен; точное значение сброса не задано."
            return base, "reset_recommended", volume_percent, intensity_percent
        if rule.amrap_failure_action == "repeat":
            base["detail"] = "Порог AMRAP не выполнен; правило предписывает повторить нагрузку."
            return base, "hold", volume_percent, intensity_percent
        if rule.amrap_failure_action == "manual_review":
            base["detail"] = "Порог AMRAP не выполнен; требуется ручная проверка."
            return base, "hold", volume_percent, intensity_percent
        if rule.amrap_failure_action == "reduce_load":
            if rule.increment_value is None or rule.increment_unit != "kg" or latest.load is None:
                base["evidence"]["reason_keys"].append("missing_configured_decrement")
                base["detail"] = "Для точного снижения нагрузки не задан совместимый шаг."
                return base, "hold", volume_percent, intensity_percent
            if latest.load <= rule.increment_value:
                base["evidence"]["reason_keys"].append("invalid_reduction_target")
                return base, "hold", volume_percent, intensity_percent
            base.update(
                outcome="consider_reducing",
                message=_PROGRESS_MESSAGES["consider_reducing"],
                detail="Порог AMRAP не выполнен; используется точный шаг снижения из правила.",
                suggested_increment=-rule.increment_value,
                suggested_weight=latest.load - rule.increment_value,
            )
            return base, "set_load", volume_percent, intensity_percent
        if rule.amrap_failure_action == "deload":
            if volume_percent is None and intensity_percent is None:
                base["evidence"]["reason_keys"].append("missing_deload_parameters")
                return base, "hold", volume_percent, intensity_percent
            base["outcome"] = "review"
            base["detail"] = (
                "Порог AMRAP не выполнен; облегчённый блок предлагается с явными параметрами."
            )
            return base, "deload", volume_percent, intensity_percent

    if rule.kind == "linear_load":
        if not sessions or not sessions[0].complete:
            base["evidence"]["reason_keys"] = ["too_few_comparable_sessions"]
            return base, "hold", volume_percent, intensity_percent
        latest = sessions[0]
        if _progression_failure(latest):
            base["outcome"] = "hold"
            base["evidence"]["reason_keys"] = ["zero_rir_or_failure_recorded"]
            base["detail"] = "Отказ или RIR 0 блокирует увеличение нагрузки."
            return (
                base,
                "reset_recommended" if rule.reset_on_failure else "hold",
                volume_percent,
                intensity_percent,
            )
        target = parse_rep_target(selection.target_reps or "")
        if target is None or latest.reps_min is None or latest.reps_min < target.minimum:
            base["outcome"] = "hold"
            base["evidence"]["reason_keys"] = ["minimum_reps_not_met"]
            return base, "hold", volume_percent, intensity_percent
        if rule.increment_value is None:
            base["evidence"]["reason_keys"] = ["missing_configured_increment"]
            return base, "hold", volume_percent, intensity_percent
        if rule.increment_unit != "kg":
            base["evidence"]["reason_keys"] = ["incompatible_load_unit"]
            return base, "hold", volume_percent, intensity_percent
        if latest.load is None:
            base["evidence"]["reason_keys"] = ["missing_load_evidence"]
            return base, "hold", volume_percent, intensity_percent
        base.update(
            outcome="consider_progressing",
            message=_PROGRESS_MESSAGES["consider_progressing"],
            detail="Последняя сопоставимая тренировка выполнила минимум повторений; шаг задан правилом.",
            suggested_increment=rule.increment_value,
            suggested_weight=latest.load + rule.increment_value,
        )
        base["evidence"]["reason_keys"] = ["linear_load_success", "configured_increment"]
        return base, "set_load", volume_percent, intensity_percent

    if rule.kind == "double_progression":
        target_text = _rep_target_text(rule.rep_target)
        target = parse_rep_target(target_text or "")
        current_target = parse_rep_target(selection.target_reps or "")
        if target is None or current_target != target:
            base["evidence"]["reason_keys"] = ["incompatible_prescription"]
            return base, "hold", volume_percent, intensity_percent
        if rule.increment_value is None:
            base["evidence"]["reason_keys"] = ["missing_configured_increment"]
            return base, "hold", volume_percent, intensity_percent
        if rule.increment_unit != "kg":
            base["evidence"]["reason_keys"] = ["incompatible_load_unit"]
            return base, "hold", volume_percent, intensity_percent
        result = evaluate_progression(
            prescribed_sets=selection.expected_count,
            prescribed_reps=target_text or current.prescribed_reps,
            sessions=sessions,
            load_unit="kg",
            configured_increment=rule.increment_value,
        )
        if (
            result["outcome"] == "hold"
            and rule.reset_on_failure
            and any(session.complete and _progression_failure(session) for session in sessions[:3])
        ):
            result["evidence"]["reason_keys"].append("zero_rir_or_failure_recorded")
            result["evidence"]["reason_keys"].append("reset_target_missing")
            result["detail"] = (
                "Отказ или RIR 0 требует сброса, но точное значение правилами не задано."
            )
            return result, "reset_recommended", volume_percent, intensity_percent
        if result["outcome"] == "consider_reducing" and result["suggested_weight"] is None:
            result["outcome"] = "review"
            result["message"] = _PROGRESS_MESSAGES["review"]
            result["evidence"]["reason_keys"].append("invalid_reduction_target")
            result["detail"] = (
                "Для точного снижения веса не получается получить положительную нагрузку."
            )
        return (
            result,
            "set_load" if result.get("suggested_weight") is not None else "hold",
            volume_percent,
            intensity_percent,
        )

    return base, proposed_action, volume_percent, intensity_percent


def _target_set_updates(
    current: UserWorkoutExercise,
    selection: ProgressionSetSelection,
    proposed_weight: float | None,
) -> list[dict[str, object]]:
    if proposed_weight is None:
        return []
    updates: list[dict[str, object]] = []
    direct_rows = _driving_set_rows(current, selection)
    if len(direct_rows) != selection.expected_count or any(
        item.is_completed for item in direct_rows
    ):
        return []
    pending_rows = direct_rows
    for item in pending_rows:
        updates.append(
            {
                "set_id": item.id,
                "set_number": item.set_number,
                "planned_role": item.planned_role,
                "current_weight": float(item.actual_weight)
                if item.actual_weight is not None
                else None,
                "set_version": item.version,
                "relative_to_top": None,
                "proposed_weight": proposed_weight,
            }
        )
    if selection.role == "top" and selection.relative_backoffs:
        try:
            plan = parse_prescription_plan(current.prescription, metric_type="strength")
        except ProgramError, TypeError, ValueError:
            return []
        if plan is None:
            return []
        backoff_rows = []
        for position, factor in selection.relative_backoffs:
            row = next(
                (
                    item
                    for item in current.sets
                    if item.planned_position == position and item.planned_role == "backoff"
                ),
                None,
            )
            if row is None:
                return []
            backoff_rows.append((row, factor))
        if any(row.is_completed for row, _factor in backoff_rows):
            return []
        for row, factor in backoff_rows:
            updates.append(
                {
                    "set_id": row.id,
                    "set_number": row.set_number,
                    "planned_role": row.planned_role,
                    "current_weight": float(row.actual_weight)
                    if row.actual_weight is not None
                    else None,
                    "set_version": row.version,
                    "relative_to_top": factor,
                    "proposed_weight": proposed_weight * factor,
                }
            )
    return updates


def _attach_proposal(
    result: dict,
    *,
    program_id: int,
    revision_number: int,
    workout: UserWorkout,
    exercise: UserWorkoutExercise,
    rule: ProgramCoachingRule | None,
    sessions: list[SessionFacts],
    selection: ProgressionSetSelection,
    proposed_action: str,
    deload_volume_percent: int | None = None,
    deload_intensity_percent: int | None = None,
) -> dict:
    snapshot = _rule_snapshot(rule)
    rule_id = _rule_id(snapshot)
    source_ids = [
        f"workout:{item.workout_id}/set:{set_id}"
        for item in sessions[:3]
        for set_id in item.source_set_ids
    ]
    if not source_ids:
        source_ids = [f"rule:{rule_id}"]
    proposed_weight = result.get("suggested_weight")
    updates = _target_set_updates(exercise, selection, proposed_weight)
    if proposed_action == "set_load" and not updates:
        proposed_action = "hold"
        result["outcome"] = "review"
        result["message"] = _PROGRESS_MESSAGES["review"]
        result["suggested_weight"] = None
        result["suggested_increment"] = None
        result["evidence"]["reason_keys"].append("no_incomplete_target_sets")
        result["detail"] = "Тренировка уже не содержит незавершённых progression-driving подходов."
        proposed_weight = None

    if proposed_action == "set_load" and proposed_weight is not None:
        eligibility = "eligible"
    elif result["outcome"] == "review" or proposed_action in {"reset_recommended", "deload"}:
        eligibility = "review"
    else:
        eligibility = "no_change"
    reasons = list(dict.fromkeys(result["evidence"].get("reason_keys", [])))
    proposal_material = {
        "ruleset_version": RULESET_VERSION,
        "rule_id": rule_id,
        "target": [program_id, revision_number, workout.id, exercise.exercise_id],
        "source_evidence_ids": source_ids,
        "proposed_action": proposed_action,
        "proposed_weight": proposed_weight,
        "target_set_updates": [
            {"set_id": item["set_id"], "proposed_weight": item["proposed_weight"]}
            for item in updates
        ],
        "reason_codes": reasons,
        "eligibility_status": eligibility,
    }
    result["proposal"] = {
        "proposal_id": _sha256(proposal_material),
        "rule_id": rule_id,
        "rule_kind": rule.kind if rule is not None else "legacy_progression_guidance",
        "rule_snapshot": snapshot,
        "target_program_id": program_id,
        "target_revision_number": revision_number,
        "target_exercise_id": exercise.exercise_id,
        "target_workout_id": workout.id,
        "current_weight": sessions[0].load if sessions else None,
        "proposed_weight": proposed_weight,
        "deload_volume_percent": deload_volume_percent,
        "deload_intensity_percent": deload_intensity_percent,
        "proposed_action": proposed_action,
        "target_set_updates": updates,
        "source_evidence_ids": source_ids,
        "comparable_session_count": sum(item.complete for item in sessions),
        "reason_codes": reasons,
        "eligibility_status": eligibility,
        "requires_confirmation": True,
    }
    return result


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

    program, revision, metadata, program_error = _current_program_snapshot(db, workout)
    if program is None:
        return {}
    revision_number = program.current_revision_number
    revisions = (
        db.query(ProgramRevision)
        .filter(ProgramRevision.user_program_id == program.id)
        .order_by(ProgramRevision.revision_number.asc())
        .all()
    )
    blocks = (
        db.query(TrainingBlock)
        .filter(TrainingBlock.user_program_id == workout.user_program_id)
        .order_by(TrainingBlock.start_date, TrainingBlock.id)
        .all()
    )
    current_block_id = _block_id_for_date(blocks, workout.scheduled_date)
    current_block_number = _week_block_number(metadata, workout.week_number)
    current_block = next((item for item in blocks if item.id == current_block_id), None)
    metadata_blocks = metadata.get("training_blocks", []) if isinstance(metadata, dict) else []
    if not isinstance(metadata_blocks, list):
        metadata_blocks = []
    scheduled_deload = bool(current_block and current_block.is_deload) or any(
        isinstance(item, dict)
        and item.get("block_number") == current_block_number
        and item.get("is_deload") is True
        for item in metadata_blocks
    )
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
        if workout.status not in {"planned", "in_progress"}:
            result = _review_result(
                prescribed_sets=current.prescribed_sets,
                prescribed_reps=current.prescribed_reps,
                reason_code="workout_not_actionable",
                detail="Предложение доступно только для запланированной или текущей тренировки.",
            )
            selection = _progression_set_selection(current)
            rule, _error = _resolve_coaching_rule(
                metadata,
                exercise_id=current.exercise_id,
                week_number=workout.week_number,
            )
            guidance[current.id] = _attach_proposal(
                result,
                program_id=program.id,
                revision_number=revision_number,
                workout=workout,
                exercise=current,
                rule=rule,
                sessions=[],
                selection=selection,
                proposed_action="hold",
            )
            continue

        rule, rule_error = _resolve_coaching_rule(
            metadata,
            exercise_id=current.exercise_id,
            week_number=workout.week_number,
        )
        selection = _progression_set_selection(current, rule_kind=rule.kind if rule else None)
        target_reps = (
            _rep_target_text(rule.rep_target)
            if rule is not None and rule.kind == "double_progression"
            else selection.target_reps
        )
        if program_error is not None:
            result = _review_result(
                prescribed_sets=selection.expected_count or current.prescribed_sets,
                prescribed_reps=target_reps or current.prescribed_reps,
                reason_code=program_error,
                detail="Не удалось проверить актуальную версию назначения программы.",
            )
            facts: list[SessionFacts] = []
            action = "hold"
        elif not _snapshot_matches_target(revision, workout, current):
            result = _review_result(
                prescribed_sets=selection.expected_count or current.prescribed_sets,
                prescribed_reps=target_reps or current.prescribed_reps,
                reason_code="stale_program_revision",
                detail="Состав тренировки отличается от снимка текущей версии программы.",
            )
            facts = []
            action = "hold"
        elif rule_error is not None:
            result = _review_result(
                prescribed_sets=selection.expected_count or current.prescribed_sets,
                prescribed_reps=target_reps or current.prescribed_reps,
                reason_code=rule_error,
                detail="В правилах одного уровня есть конфликт или некорректная запись.",
            )
            facts = []
            action = "hold"
        elif selection.reason_code is not None:
            result = _review_result(
                prescribed_sets=current.prescribed_sets,
                prescribed_reps=current.prescribed_reps,
                reason_code=selection.reason_code,
                detail="Структура подходов не позволяет выбрать progression-driving set.",
            )
            facts = []
            action = "hold"
        else:
            same_exercise = [item for item in candidates if item.exercise_id == current.exercise_id]
            comparable: list[UserWorkoutExercise] = []
            for item in same_exercise:
                completed_at = item.workout.completed_at
                if (
                    completed_at is None
                    or _revision_for_completion(revisions, completed_at) != revision_number
                ):
                    continue
                if item.source_template_exercise_id != current.source_template_exercise_id:
                    continue
                if _selection_signature(item) != _selection_signature(current):
                    continue
                if _block_id_for_date(blocks, item.workout.scheduled_date) != current_block_id:
                    continue
                if _week_block_number(metadata, item.workout.week_number) != current_block_number:
                    continue
                historical_rule, historical_error = _resolve_coaching_rule(
                    metadata,
                    exercise_id=item.exercise_id,
                    week_number=item.workout.week_number,
                )
                if historical_error is not None or _rule_snapshot(
                    historical_rule
                ) != _rule_snapshot(rule):
                    continue
                comparable.append(item)
            facts = [_session_facts_for_selection(item, selection) for item in comparable]
            context_changed = bool(same_exercise and not comparable)
            if rule is None:
                if not isinstance(metadata, dict) or not metadata.get("coaching_rules"):
                    result = evaluate_progression(
                        prescribed_sets=selection.expected_count,
                        prescribed_reps=target_reps or current.prescribed_reps,
                        sessions=facts,
                        load_unit="kg",
                        context_changed=context_changed,
                    )
                    if result["outcome"] in {"consider_progressing", "consider_reducing"}:
                        result["evidence"]["reason_keys"].append("missing_configured_increment")
                        result["detail"] += " Точный шаг нагрузки не задан в сохранённом правиле."
                else:
                    result = _review_result(
                        prescribed_sets=selection.expected_count,
                        prescribed_reps=target_reps or current.prescribed_reps,
                        reason_code="no_applicable_coaching_rule",
                        detail="Для этого упражнения и недели программы нет применимого правила.",
                    )
                action = "set_load" if result.get("suggested_weight") is not None else "hold"
            else:
                result, action, _volume, _intensity = _rule_guidance(
                    rule=rule,
                    selection=selection,
                    current=current,
                    sessions=facts,
                    current_is_deload=scheduled_deload,
                )
                if context_changed and not facts:
                    result["evidence"]["reason_keys"].append("program_context_changed")
                    result["outcome"] = "review"
                    result["suggested_weight"] = None
                    result["suggested_increment"] = None
                    action = "hold"

        result["evidence"]["reason_keys"] = list(
            dict.fromkeys(result["evidence"].get("reason_keys", []))
        )
        volume = rule.deload_volume_percent if rule is not None else None
        intensity = rule.deload_intensity_percent if rule is not None else None
        guidance[current.id] = _attach_proposal(
            result,
            program_id=program.id,
            revision_number=revision_number,
            workout=workout,
            exercise=current,
            rule=rule,
            sessions=facts,
            selection=selection,
            proposed_action=action,
            deload_volume_percent=volume,
            deload_intensity_percent=intensity,
        )
    return guidance


def list_assigned_program_progression_proposals(
    db: Session,
    actor: User,
    program_id: int,
) -> dict[str, object]:
    program, _role = get_program_for_actor(db, actor, program_id)
    workout = (
        db.query(UserWorkout)
        .options(
            selectinload(UserWorkout.exercises).selectinload(UserWorkoutExercise.sets),
            selectinload(UserWorkout.exercises).joinedload(UserWorkoutExercise.exercise),
        )
        .filter(
            UserWorkout.user_program_id == program.id,
            UserWorkout.status.in_({"planned", "in_progress"}),
            UserWorkout.scheduled_date >= today_for_user(actor),
        )
        .order_by(
            (UserWorkout.status == "in_progress").desc(),
            UserWorkout.scheduled_date.asc(),
            UserWorkout.id.asc(),
        )
        .first()
    )
    if workout is None:
        raise ProgramError("No upcoming workout for progression review")
    guidance = build_progression_guidance(
        db, db.query(User).filter(User.id == program.user_id).one(), workout
    )
    proposal_ids = [
        item["proposal"]["proposal_id"]
        for item in guidance.values()
        if item.get("proposal") is not None
    ]
    rejected_ids = (
        {
            resource_id
            for (resource_id,) in db.query(AuditEvent.resource_id)
            .filter(
                AuditEvent.action == "progression_proposal.reject",
                AuditEvent.resource_type == "progression_proposal",
                AuditEvent.resource_id.in_(proposal_ids),
            )
            .all()
        }
        if proposal_ids
        else set()
    )
    accepted_details = (
        db.query(AuditEvent.details)
        .filter(
            AuditEvent.action.in_({"progression_proposal.confirm", "progression_proposal.adjust"}),
            AuditEvent.resource_type == "user_workout",
            AuditEvent.resource_id == str(workout.id),
            AuditEvent.target_user_id == program.user_id,
        )
        .all()
        if proposal_ids
        else []
    )
    accepted_ids = {
        details.get("proposal_id")
        for (details,) in accepted_details
        if isinstance(details, dict) and details.get("proposal_id") in proposal_ids
    }
    resolved_ids = rejected_ids | accepted_ids
    return {
        "target_program_id": program.id,
        "target_revision_number": program.current_revision_number,
        "target_workout_id": workout.id,
        "scheduled_date": workout.scheduled_date,
        "exercises": [
            {
                "exercise_id": item.exercise_id,
                "exercise_title": item.exercise.title
                if item.exercise is not None
                else f"Упражнение {item.exercise_id}",
                "guidance": guidance[item.id],
            }
            for item in workout.exercises
            if item.id in guidance
            and guidance[item.id]["proposal"]["proposal_id"] not in resolved_ids
        ],
    }


def review_assigned_program_progression_proposal(
    db: Session,
    actor: User,
    program_id: int,
    proposal_id: str,
    *,
    decision: Literal["confirm", "reject", "adjust"],
    workout_id: int,
    exercise_id: int,
    expected_revision_number: int,
    expected_set_versions: dict[int, int],
    adjusted_weight: float | None = None,
) -> dict[str, object]:
    program, role = get_program_for_actor(db, actor, program_id, lock=True)
    workout = (
        db.query(UserWorkout)
        .options(
            selectinload(UserWorkout.exercises).selectinload(UserWorkoutExercise.sets),
        )
        .filter(
            UserWorkout.id == workout_id,
            UserWorkout.user_program_id == program.id,
        )
        .with_for_update()
        .first()
    )
    if workout is None:
        raise ProgramError("Progression workout is not available")
    exercise = next((item for item in workout.exercises if item.exercise_id == exercise_id), None)
    if exercise is None or workout_exercise_metric_type(exercise) != "strength":
        raise ProgramError("Progression exercise is not available")

    request_fingerprint = _progression_decision_fingerprint(
        proposal_id=proposal_id,
        program_id=program.id,
        workout_id=workout.id,
        exercise_id=exercise_id,
        decision=decision,
        expected_revision_number=expected_revision_number,
        expected_set_versions=expected_set_versions,
        adjusted_weight=adjusted_weight,
    )
    accepted_events = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.action.in_({"progression_proposal.confirm", "progression_proposal.adjust"}),
            AuditEvent.resource_type == "user_workout",
            AuditEvent.resource_id == str(workout.id),
            AuditEvent.target_user_id == program.user_id,
        )
        .order_by(AuditEvent.id.desc())
        .all()
    )
    prior_events = [
        event
        for event in accepted_events
        if event.details.get("proposal_id") == proposal_id
        and event.details.get("exercise_id") == exercise_id
    ]
    rejected_event = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.action == "progression_proposal.reject",
            AuditEvent.resource_type == "progression_proposal",
            AuditEvent.resource_id == proposal_id,
            AuditEvent.target_user_id == program.user_id,
        )
        .order_by(AuditEvent.id.desc())
        .first()
    )
    if rejected_event is not None and rejected_event.details.get("exercise_id") == exercise_id:
        prior_events.append(rejected_event)
    prior_event = max(prior_events, key=lambda event: event.id, default=None)
    if prior_event is not None:
        if (
            prior_event.actor_user_id == actor.id
            and prior_event.action == f"progression_proposal.{decision}"
            and prior_event.details.get("request_fingerprint") == request_fingerprint
            and isinstance(prior_event.details.get("result"), dict)
        ):
            return prior_event.details["result"]
        if prior_event.action == "progression_proposal.reject":
            raise ProgramError("Progression proposal already rejected")
        raise ProgramError("Progression proposal already reviewed")

    if not program.is_active or program.status not in {"scheduled", "active"}:
        raise ProgramError("Assigned program is not editable")
    if program.current_revision_number != expected_revision_number:
        raise ProgramError("Program revision conflict")
    if workout.status not in {"planned", "in_progress"}:
        raise ProgramError("Progression workout is not available")

    owner = db.query(User).filter(User.id == program.user_id).one_or_none()
    if owner is None:
        raise ProgramError("Assigned program not found")
    guidance = build_progression_guidance(db, owner, workout).get(exercise.id)
    proposal = guidance.get("proposal") if guidance is not None else None
    if proposal is None or proposal["proposal_id"] != proposal_id:
        raise ProgramError("Progression proposal is stale")

    if decision == "reject":
        result = {
            "proposal_id": proposal_id,
            "decision": decision,
            "applied_set_ids": [],
            "current_revision_number": program.current_revision_number,
        }
        record_audit_event(
            db,
            actor_user_id=actor.id,
            target_user_id=program.user_id,
            action="progression_proposal.reject",
            resource_type="progression_proposal",
            resource_id=proposal_id,
            details={
                "exercise_id": exercise_id,
                "rule_id": proposal["rule_id"],
                "actor_role": role,
                "request_fingerprint": request_fingerprint,
                "result": result,
            },
        )
        return result

    applied_set_ids: list[int] = []
    if decision in {"confirm", "adjust"}:
        if (
            proposal["eligibility_status"] != "eligible"
            or proposal["proposed_action"] != "set_load"
        ):
            raise ProgramError("Progression proposal has no applicable exact load change")
        target_updates = proposal["target_set_updates"]
        if not target_updates:
            raise ProgramError("Progression proposal has no incomplete target sets")
        expected_ids = {int(item["set_id"]) for item in target_updates}
        if set(expected_set_versions) != expected_ids:
            raise ProgramError("Progression proposal target set versions are incomplete")
        for item in target_updates:
            set_id = int(item["set_id"])
            set_row = next((row for row in exercise.sets if row.id == set_id), None)
            if set_row is None or set_row.is_completed:
                raise ProgramError("Progression proposal target set is no longer available")
            chosen_weight = (
                adjusted_weight if decision == "adjust" else float(item["proposed_weight"])
            )
            if chosen_weight is None:
                raise ProgramError("Adjusted progression load is required")
            if decision == "adjust" and item["relative_to_top"] is not None:
                chosen_weight *= float(item["relative_to_top"])
            changes = {"actual_weight": chosen_weight}
            mutation_id = _sha256(
                {
                    "proposal_id": proposal_id,
                    "decision": decision,
                    "adjusted_weight": adjusted_weight,
                    "set_id": set_id,
                }
            )
            replayed = replayed_workout_set(db, set_row, mutation_id, changes)
            if replayed is not None:
                applied_set_ids.append(set_id)
                continue
            if (
                expected_set_versions[set_id] != set_row.version
                or item["set_version"] != set_row.version
            ):
                raise ProgramError("Progression proposal target set changed")
            try:
                validate_workout_set_changes("strength", changes)
                apply_workout_set_update(
                    db,
                    set_row,
                    workout,
                    changes,
                    expected_version=set_row.version,
                    mutation_id=mutation_id,
                    allow_planned=True,
                )
            except (ValueError, WorkoutSetSyncError) as exc:
                raise ProgramError("Progression proposal could not be applied") from exc
            applied_set_ids.append(set_id)

    result = {
        "proposal_id": proposal_id,
        "decision": decision,
        "applied_set_ids": applied_set_ids,
        "current_revision_number": program.current_revision_number,
    }
    record_audit_event(
        db,
        actor_user_id=actor.id,
        target_user_id=program.user_id,
        action=f"progression_proposal.{decision}",
        resource_type="user_workout",
        resource_id=workout.id,
        details={
            "proposal_id": proposal_id,
            "exercise_id": exercise_id,
            "rule_id": proposal["rule_id"],
            "actor_role": role,
            "changed_set_count": len(applied_set_ids),
            "request_fingerprint": request_fingerprint,
            "result": result,
        },
    )
    return result
