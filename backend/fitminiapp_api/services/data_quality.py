from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from fitminiapp_api.models.program import (
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.schemas.data_quality import (
    DataSufficiencyReasonKey,
    DataSufficiencyStatus,
)

RULESET_VERSION = "data-sufficiency-v1"
NUTRITION_SUFFICIENT_DAYS = 7
BODY_SUFFICIENT_POINTS = 3
BODY_SUFFICIENT_SPAN_DAYS = 14
WORKING_SETS_SUFFICIENT_COUNT = 6
WORKOUT_SESSIONS_SUFFICIENT_COUNT = 2
RIR_SUFFICIENT_RECORDED_COUNT = 3
RIR_SUFFICIENT_COVERAGE_PERCENT = 50.0
ADHERENCE_SUFFICIENT_WORKOUT_COUNT = 3
ANTHROPOMETRY_METRICS = ("chest_cm", "waist_cm", "hips_cm", "biceps_cm", "thigh_cm")


@dataclass(frozen=True)
class TrainingDataCounts:
    completed_workout_count: int = 0
    prescribed_set_count: int = 0
    logged_set_count: int = 0
    workout_session_count: int = 0
    working_set_count: int = 0
    rir_recorded_set_count: int = 0


def _signal(
    status: DataSufficiencyStatus,
    counters: Mapping[str, int | float],
    *reason_keys: DataSufficiencyReasonKey,
) -> dict:
    return {
        "status": status,
        "counters": dict(counters),
        "reason_keys": list(reason_keys),
    }


def _coverage_percent(observed: int, total: int) -> float:
    return round(observed * 100 / total, 1) if total > 0 else 0.0


def build_nutrition_coverage_signal(
    *,
    logged_day_count: int,
    eligible_day_count: int,
    visible: bool,
    exact_entry_count: int = 0,
    approximate_entry_count: int = 0,
    partial_entry_count: int = 0,
) -> dict:
    required = min(NUTRITION_SUFFICIENT_DAYS, eligible_day_count)
    counters = {
        "logged_day_count": logged_day_count,
        "eligible_day_count": eligible_day_count,
        "required_logged_day_count": required,
        "coverage_percent": _coverage_percent(logged_day_count, eligible_day_count),
        "exact_entry_count": exact_entry_count,
        "approximate_entry_count": approximate_entry_count,
        "partial_entry_count": partial_entry_count,
    }
    if not visible:
        return _signal("insufficient", counters, "nutrition_access_not_granted")
    if logged_day_count <= 0:
        return _signal("insufficient", counters, "no_logged_days")
    if logged_day_count >= required:
        return _signal("sufficient", counters, "thresholds_met")
    return _signal("limited", counters, "below_required_coverage")


def build_body_metric_signal(*, point_count: int, span_days: int) -> dict:
    counters = {
        "point_count": point_count,
        "span_days": span_days,
        "required_point_count": BODY_SUFFICIENT_POINTS,
        "required_span_days": BODY_SUFFICIENT_SPAN_DAYS,
    }
    if point_count <= 0:
        return _signal("insufficient", counters, "no_measurements")
    reasons: list[DataSufficiencyReasonKey] = []
    if point_count < BODY_SUFFICIENT_POINTS:
        reasons.append("too_few_points")
    if span_days < BODY_SUFFICIENT_SPAN_DAYS:
        reasons.append("timespan_too_short")
    if reasons:
        return _signal("limited", counters, *reasons)
    return _signal("sufficient", counters, "thresholds_met")


def build_anthropometry_signal(trends: list[dict]) -> dict:
    metric_trends = [trend for trend in trends if trend["metric"] in ANTHROPOMETRY_METRICS]
    sufficient_metric_count = sum(
        trend["point_count"] >= BODY_SUFFICIENT_POINTS
        and trend["span_days"] >= BODY_SUFFICIENT_SPAN_DAYS
        for trend in metric_trends
    )
    counters = {
        "measured_metric_count": len(metric_trends),
        "sufficient_metric_count": sufficient_metric_count,
        "maximum_point_count": max((trend["point_count"] for trend in metric_trends), default=0),
        "maximum_span_days": max((trend["span_days"] for trend in metric_trends), default=0),
        "required_point_count_per_metric": BODY_SUFFICIENT_POINTS,
        "required_span_days_per_metric": BODY_SUFFICIENT_SPAN_DAYS,
    }
    if not metric_trends:
        return _signal("insufficient", counters, "no_anthropometry_measurements")
    if sufficient_metric_count:
        return _signal("sufficient", counters, "thresholds_met")
    if counters["maximum_point_count"] < BODY_SUFFICIENT_POINTS:
        return _signal("limited", counters, "too_few_points")
    return _signal("limited", counters, "timespan_too_short")


def build_workout_logging_signal(counts: TrainingDataCounts) -> dict:
    counters = {
        "completed_workout_count": counts.completed_workout_count,
        "prescribed_set_count": counts.prescribed_set_count,
        "logged_set_count": counts.logged_set_count,
        "coverage_percent": _coverage_percent(
            counts.logged_set_count,
            counts.prescribed_set_count,
        ),
    }
    if counts.completed_workout_count <= 0:
        return _signal("insufficient", counters, "no_completed_workouts")
    if counts.prescribed_set_count <= 0:
        return _signal("insufficient", counters, "no_prescribed_sets")
    if counts.logged_set_count <= 0:
        return _signal("insufficient", counters, "no_logged_working_sets")
    if counts.logged_set_count < counts.prescribed_set_count:
        return _signal("limited", counters, "partial_workout_logging")
    return _signal("sufficient", counters, "thresholds_met")


def build_working_sets_signal(counts: TrainingDataCounts) -> dict:
    counters = {
        "workout_session_count": counts.workout_session_count,
        "working_set_count": counts.working_set_count,
        "required_workout_session_count": WORKOUT_SESSIONS_SUFFICIENT_COUNT,
        "required_working_set_count": WORKING_SETS_SUFFICIENT_COUNT,
    }
    if counts.working_set_count <= 0:
        return _signal("insufficient", counters, "no_working_sets")
    reasons: list[DataSufficiencyReasonKey] = []
    if counts.working_set_count < WORKING_SETS_SUFFICIENT_COUNT:
        reasons.append("too_few_working_sets")
    if counts.workout_session_count < WORKOUT_SESSIONS_SUFFICIENT_COUNT:
        reasons.append("too_few_workout_sessions")
    if reasons:
        return _signal("limited", counters, *reasons)
    return _signal("sufficient", counters, "thresholds_met")


def build_rir_coverage_signal(counts: TrainingDataCounts) -> dict:
    counters = {
        "working_set_count": counts.working_set_count,
        "recorded_set_count": counts.rir_recorded_set_count,
        "required_recorded_set_count": RIR_SUFFICIENT_RECORDED_COUNT,
        "coverage_percent": _coverage_percent(
            counts.rir_recorded_set_count,
            counts.working_set_count,
        ),
        "required_coverage_percent": RIR_SUFFICIENT_COVERAGE_PERCENT,
    }
    if counts.working_set_count <= 0:
        return _signal("insufficient", counters, "no_working_sets")
    if counts.rir_recorded_set_count <= 0:
        return _signal("insufficient", counters, "no_rir_observations")
    reasons: list[DataSufficiencyReasonKey] = []
    if counts.rir_recorded_set_count < RIR_SUFFICIENT_RECORDED_COUNT:
        reasons.append("too_few_rir_observations")
    if counters["coverage_percent"] < RIR_SUFFICIENT_COVERAGE_PERCENT:
        reasons.append("rir_coverage_too_low")
    if reasons:
        return _signal("limited", counters, *reasons)
    return _signal("sufficient", counters, "thresholds_met")


def build_schedule_adherence_signal(*, evaluable_workout_count: int) -> dict:
    counters = {
        "evaluable_workout_count": evaluable_workout_count,
        "required_evaluable_workout_count": ADHERENCE_SUFFICIENT_WORKOUT_COUNT,
    }
    if evaluable_workout_count <= 0:
        return _signal("insufficient", counters, "no_evaluable_planned_workouts")
    if evaluable_workout_count < ADHERENCE_SUFFICIENT_WORKOUT_COUNT:
        return _signal("limited", counters, "too_few_evaluable_workouts")
    return _signal("sufficient", counters, "thresholds_met")


def build_training_data_sufficiency(counts: TrainingDataCounts) -> dict:
    return {
        "ruleset_version": RULESET_VERSION,
        "workout_logging": build_workout_logging_signal(counts),
        "working_sets": build_working_sets_signal(counts),
        "rir_coverage": build_rir_coverage_signal(counts),
    }


def collect_training_data_counts(
    db: Session,
    *,
    user_ids: list[int],
    period_starts: dict[int, date],
    period_ends: dict[int, date],
) -> dict[int, TrainingDataCounts]:
    if not user_ids:
        return {}
    rows = (
        db.query(
            UserProgram.user_id.label("user_id"),
            UserWorkout.id.label("workout_id"),
            UserWorkoutExercise.id.label("workout_exercise_id"),
            UserWorkoutExercise.prescribed_sets.label("prescribed_sets"),
            UserWorkoutSet.id.label("set_id"),
            UserWorkoutSet.actual_reps.label("actual_reps"),
            UserWorkoutSet.set_kind.label("set_kind"),
            UserWorkoutSet.rir.label("rir"),
        )
        .select_from(UserProgram)
        .join(UserWorkout, UserWorkout.user_program_id == UserProgram.id)
        .outerjoin(UserWorkoutExercise, UserWorkoutExercise.workout_id == UserWorkout.id)
        .outerjoin(
            UserWorkoutSet,
            and_(
                UserWorkoutSet.workout_exercise_id == UserWorkoutExercise.id,
                UserWorkoutSet.is_completed.is_(True),
                or_(
                    UserWorkoutSet.set_kind.is_(None),
                    UserWorkoutSet.set_kind.in_(("working", "drop")),
                ),
            ),
        )
        .filter(
            UserWorkout.status == "completed",
            or_(
                *(
                    and_(
                        UserProgram.user_id == user_id,
                        UserWorkout.scheduled_date.between(
                            period_starts[user_id],
                            period_ends[user_id],
                        ),
                    )
                    for user_id in user_ids
                )
            ),
        )
        .all()
    )

    completed_workouts: dict[int, set[int]] = defaultdict(set)
    exercises: dict[int, dict[int, dict[str, int]]] = defaultdict(dict)
    sessions_with_sets: dict[int, set[int]] = defaultdict(set)
    working_set_count: dict[int, int] = defaultdict(int)
    rir_recorded_set_count: dict[int, int] = defaultdict(int)
    for row in rows:
        completed_workouts[row.user_id].add(row.workout_id)
        if row.workout_exercise_id is not None:
            exercise = exercises[row.user_id].setdefault(
                row.workout_exercise_id,
                {"prescribed": int(row.prescribed_sets or 0), "logged": 0},
            )
            if (
                row.set_id is not None
                and row.actual_reps is not None
                and row.set_kind in {None, "working"}
            ):
                exercise["logged"] += 1
        if row.set_id is None:
            continue
        sessions_with_sets[row.user_id].add(row.workout_id)
        working_set_count[row.user_id] += 1
        rir_recorded_set_count[row.user_id] += int(row.rir is not None)

    result: dict[int, TrainingDataCounts] = {}
    for user_id in user_ids:
        user_exercises = exercises[user_id].values()
        result[user_id] = TrainingDataCounts(
            completed_workout_count=len(completed_workouts[user_id]),
            prescribed_set_count=sum(item["prescribed"] for item in user_exercises),
            logged_set_count=sum(
                min(item["logged"], item["prescribed"]) for item in user_exercises
            ),
            workout_session_count=len(sessions_with_sets[user_id]),
            working_set_count=working_set_count[user_id],
            rir_recorded_set_count=rir_recorded_set_count[user_id],
        )
    return result
