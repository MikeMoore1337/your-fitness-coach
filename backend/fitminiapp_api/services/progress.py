from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from math import floor
from typing import Literal, cast

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from fitminiapp_api.core.timezone import (
    get_user_timezone_name,
    local_naive_to_utc_naive,
    today_for_user,
    utc_naive_to_timezone_naive,
)
from fitminiapp_api.models.cardio import CardioSession
from fitminiapp_api.models.food_diary import FoodDiaryDayStatus, FoodDiaryEntry
from fitminiapp_api.models.nutrition import NutritionTarget
from fitminiapp_api.models.program import (
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import (
    BodyMeasurement,
    CoachClient,
    User,
    UserProfile,
    UserProfilePriorityMuscle,
)
from fitminiapp_api.services.data_quality import (
    build_anthropometry_signal,
    build_body_metric_signal,
    build_nutrition_coverage_signal,
    build_schedule_adherence_signal,
    build_training_data_sufficiency,
    collect_training_data_counts,
)
from fitminiapp_api.services.diary_nutrition import DiaryDayNutrition, aggregate_diary_entries
from fitminiapp_api.services.period_bounds import (
    MAX_REPORT_DAYS,
    resolve_progress_bounds,
)
from fitminiapp_api.services.profile import serialize_body_priority
from fitminiapp_api.services.workouts import working_volume_set_filter

FORMULA_VERSION = "adherence-v1"
CALORIE_TOLERANCE = 0.10
ADHERENCE_WEIGHTS = {
    "workouts": 0.40,
    "cardio": 0.20,
    "calories": 0.20,
    "protein": 0.20,
}
BODY_METRICS = ("weight_kg", "chest_cm", "waist_cm", "hips_cm", "biceps_cm", "thigh_cm")
BODY_TREND_MIN_POINTS = 3
BODY_TREND_MIN_SPAN_DAYS = 14
BODY_MEASUREMENT_GUIDANCE = {
    "comparison_basis": "self",
    "minimum_points_for_interpretation": BODY_TREND_MIN_POINTS,
    "minimum_span_days_for_interpretation": BODY_TREND_MIN_SPAN_DAYS,
    "consistency_tips": [
        "Снимайте замеры в похожее время суток и в одинаковых условиях.",
        "Используйте одну технику и одно место наложения измерительной ленты.",
        "Оценивайте последовательность замеров, а не отдельное колебание.",
    ],
    "circumference_limitations": [
        "Окружность плеча не измеряет отдельно бицепс или трицепс.",
        "Окружность бедра не измеряет отдельно квадрицепс или другие мышцы бедра.",
        "Окружности сами по себе не показывают рост конкретной мышцы.",
    ],
}
AdherenceStatus = Literal["available", "not_applicable", "insufficient_data", "unsupported"]
NutritionDiaryStatus = Literal["complete", "incomplete", "fasted"]


@dataclass(frozen=True)
class NutritionDiaryDay:
    user_id: int
    diary_date: date
    calories: Decimal | None
    protein_g: Decimal | None
    status: NutritionDiaryStatus
    has_entries: bool


def calculate_adherence_component(
    *,
    achieved: int,
    evaluated: int,
    weight: float,
    unavailable_status: AdherenceStatus,
    unavailable_reason: str,
) -> dict:
    """Calculate one factual adherence ratio without inventing missing observations."""
    if evaluated <= 0:
        return {
            "status": unavailable_status,
            "percent": None,
            "achieved": 0,
            "evaluated": 0,
            "weight": weight,
            "reason": unavailable_reason,
        }
    if achieved < 0 or achieved > evaluated:
        raise ValueError("achieved must be between zero and evaluated")
    return {
        "status": "available",
        "percent": round(achieved * 100 / evaluated, 1),
        "achieved": achieved,
        "evaluated": evaluated,
        "weight": weight,
        "reason": None,
    }


def calculate_overall_adherence(components: dict[str, dict]) -> tuple[float | None, list[str]]:
    """Return the weighted mean of available components, renormalizing omitted weights."""
    included = [
        name for name, component in components.items() if component["status"] == "available"
    ]
    total_weight = sum(float(components[name]["weight"]) for name in included)
    if not included or total_weight <= 0:
        return None, []
    value = (
        sum(
            float(components[name]["percent"]) * float(components[name]["weight"])
            for name in included
        )
        / total_weight
    )
    return round(value, 1), included


def is_calorie_target_met(actual: Decimal, target: int) -> bool:
    if target <= 0:
        return False
    lower = Decimal(target) * Decimal(str(1 - CALORIE_TOLERANCE))
    upper = Decimal(target) * Decimal(str(1 + CALORIE_TOLERANCE))
    return lower <= actual <= upper


def is_protein_target_met(actual: Decimal, target: int) -> bool:
    return target > 0 and actual >= Decimal(target)


def _effective_nutrition_target(
    targets: list[NutritionTarget],
    target_date: date,
) -> NutritionTarget | None:
    return next(
        (
            target
            for target in targets
            if target.effective_from <= target_date
            and (target.effective_to is None or target_date < target.effective_to)
        ),
        None,
    )


def _user_date_filter(
    user_ids: Iterable[int],
    starts: dict[int, date],
    ends: dict[int, date],
    user_column,
    date_column,
):
    return or_(
        *(
            and_(user_column == user_id, date_column.between(starts[user_id], ends[user_id]))
            for user_id in user_ids
        )
    )


def _body_trends(rows: list) -> list[dict]:
    trends: list[dict] = []
    for metric in BODY_METRICS:
        points = [row for row in rows if getattr(row, metric) is not None]
        if not points:
            continue
        first = points[0]
        latest = points[-1]
        first_value = float(getattr(first, metric))
        latest_value = float(getattr(latest, metric))
        span_days = (latest.measured_on - first.measured_on).days
        if len(points) == 1:
            interpretation_status = "single_point"
        elif len(points) < BODY_TREND_MIN_POINTS:
            interpretation_status = "insufficient_points"
        elif span_days < BODY_TREND_MIN_SPAN_DAYS:
            interpretation_status = "insufficient_period"
        else:
            interpretation_status = "available"
        trends.append(
            {
                "metric": metric,
                "first_value": first_value,
                "latest_value": latest_value,
                "change": round(latest_value - first_value, 2) if len(points) >= 2 else None,
                "first_measured_on": first.measured_on,
                "latest_measured_on": latest.measured_on,
                "point_count": len(points),
                "span_days": span_days,
                "interpretation_status": interpretation_status,
                "points": [
                    {
                        "measured_on": point.measured_on,
                        "value": float(getattr(point, metric)),
                    }
                    for point in points
                ],
            }
        )
    return trends


def _active_clients(
    db: Session,
    coach: User,
    *,
    limit: int,
    offset: int,
) -> tuple[list[tuple[User, str | None]], int]:
    query = (
        db.query(User, CoachClient.private_name)
        .join(CoachClient, CoachClient.client_user_id == User.id)
        .filter(
            CoachClient.coach_user_id == coach.id,
            CoachClient.status == "active",
            User.is_active.is_(True),
        )
    )
    total = query.count()
    rows = (
        query.options(
            joinedload(User.profile)
            .joinedload(UserProfile.body_priority_links)
            .joinedload(UserProfilePriorityMuscle.muscle)
        )
        .order_by(User.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [(client, private_name) for client, private_name in rows], total


def build_trainer_client_summaries(
    db: Session,
    coach: User,
    period_days: int | None = None,
    *,
    limit: int,
    offset: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    client_rows, total = _active_clients(db, coach, limit=limit, offset=offset)
    clients = [client for client, _private_name in client_rows]
    period_bounds = None
    effective_period_days = 30 if period_days is None else int(period_days)
    if date_from is not None or date_to is not None:
        if period_days is not None:
            resolve_progress_bounds(
                coach,
                period_days,
                date_from=date_from,
                date_to=date_to,
            )
        period_bounds = {
            client.id: (
                bounds.start,
                bounds.end,
            )
            for client in clients
            for bounds in [
                resolve_progress_bounds(
                    client,
                    date_from=date_from,
                    date_to=date_to,
                )
            ]
        }
        if period_bounds:
            first_start, first_end = next(iter(period_bounds.values()))
            effective_period_days = (first_end - first_start).days + 1
        else:
            bounds = resolve_progress_bounds(coach, date_from=date_from, date_to=date_to)
            effective_period_days = (bounds.end - bounds.start).days + 1
    summaries = build_progress_summaries(
        db,
        clients,
        effective_period_days,
        nutrition_visible_user_ids={client.id for client in clients},
        period_bounds=period_bounds,
    )
    names = {
        client.id: private_name or (client.profile.full_name if client.profile else None)
        for client, private_name in client_rows
    }
    for summary in summaries:
        summary["client_name"] = names[summary["user_id"]]
    return {
        "items": summaries,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def build_progress_summary(db: Session, user: User, period_days: int) -> dict:
    bounds = resolve_progress_bounds(user, period_days)
    return build_progress_summaries(
        db,
        [user],
        (bounds.end - bounds.start).days + 1,
        nutrition_visible_user_ids={user.id},
        period_bounds={user.id: (bounds.start, bounds.end)},
    )[0]


def build_progress_summary_for_range(
    db: Session,
    user: User,
    period_start: date,
    period_end: date,
) -> dict:
    if period_end < period_start:
        raise ValueError("period_end must not be before period_start")
    period_days = (period_end - period_start).days + 1
    if period_days > MAX_REPORT_DAYS:
        raise ValueError(f"period cannot exceed {MAX_REPORT_DAYS} days")
    return build_progress_summaries(
        db,
        [user],
        period_days,
        nutrition_visible_user_ids={user.id},
        period_bounds={user.id: (period_start, period_end)},
    )[0]


def build_progress_summaries(
    db: Session,
    users: list[User],
    period_days: int,
    *,
    nutrition_visible_user_ids: set[int],
    period_bounds: dict[int, tuple[date, date]] | None = None,
) -> list[dict]:
    if period_days < 1 or period_days > MAX_REPORT_DAYS:
        raise ValueError(f"period_days must be between 1 and {MAX_REPORT_DAYS}")
    if period_bounds is None and period_days not in {1, 7, 30, 90, 365}:
        raise ValueError("period_days must be 1, 7, 30, or 90, or 365")
    if not users:
        return []

    user_ids = [user.id for user in users]
    if period_bounds is None:
        today_by_user = {user.id: today_for_user(user) for user in users}
        start_by_user = {
            user_id: current_day - timedelta(days=period_days - 1)
            for user_id, current_day in today_by_user.items()
        }
    else:
        if set(period_bounds) != set(user_ids):
            raise ValueError("period bounds must be provided for every user")
        start_by_user = {user_id: bounds[0] for user_id, bounds in period_bounds.items()}
        today_by_user = {user_id: bounds[1] for user_id, bounds in period_bounds.items()}
        if any(today_by_user[user_id] < start_by_user[user_id] for user_id in user_ids):
            raise ValueError("period end must not be before period start")
    actual_today_by_user = {user.id: today_for_user(user) for user in users}

    workout_rows = (
        db.query(
            UserProgram.user_id,
            UserWorkout.id,
            UserWorkout.scheduled_date,
            UserWorkout.scheduled_time,
            UserWorkout.title,
            UserWorkout.status,
        )
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .filter(
            _user_date_filter(
                user_ids,
                start_by_user,
                today_by_user,
                UserProgram.user_id,
                UserWorkout.scheduled_date,
            )
        )
        .order_by(UserProgram.user_id, UserWorkout.scheduled_date, UserWorkout.id)
        .all()
    )
    workouts_by_user: dict[int, list] = defaultdict(list)
    for workout_row in workout_rows:
        workouts_by_user[workout_row.user_id].append(workout_row)

    cardio_rows = (
        db.query(CardioSession)
        .filter(
            or_(
                *(
                    and_(
                        CardioSession.user_id == user.id,
                        CardioSession.scheduled_at
                        >= local_naive_to_utc_naive(
                            datetime.combine(start_by_user[user.id], time.min),
                            get_user_timezone_name(user),
                        ),
                        CardioSession.scheduled_at
                        < local_naive_to_utc_naive(
                            datetime.combine(today_by_user[user.id] + timedelta(days=1), time.min),
                            get_user_timezone_name(user),
                        ),
                    )
                    for user in users
                )
            )
        )
        .order_by(CardioSession.user_id, CardioSession.scheduled_at, CardioSession.id)
        .all()
    )
    cardio_by_user: dict[int, list[CardioSession]] = defaultdict(list)
    for cardio_row in cardio_rows:
        cardio_by_user[cardio_row.user_id].append(cardio_row)

    next_candidates = (
        db.query(
            UserProgram.user_id.label("user_id"),
            UserWorkout.id.label("id"),
            UserWorkout.scheduled_date.label("scheduled_date"),
            UserWorkout.scheduled_time.label("scheduled_time"),
            UserWorkout.title.label("title"),
            UserWorkout.status.label("status"),
            func.row_number()
            .over(
                partition_by=UserProgram.user_id,
                order_by=(
                    UserWorkout.scheduled_date.asc(),
                    UserWorkout.scheduled_time.asc(),
                    UserWorkout.id.asc(),
                ),
            )
            .label("row_number"),
        )
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .filter(
            UserWorkout.status.in_({"planned", "in_progress"}),
            or_(
                *(
                    and_(
                        UserProgram.user_id == user_id,
                        UserWorkout.scheduled_date >= today_by_user[user_id],
                    )
                    for user_id in user_ids
                )
            ),
        )
        .subquery()
    )
    next_rows = db.query(next_candidates).filter(next_candidates.c.row_number == 1).all()
    next_by_user = {row.user_id: row for row in next_rows}

    last_completed_rows = (
        db.query(
            UserProgram.user_id,
            func.max(UserWorkout.completed_at).label("completed_at"),
            func.max(UserWorkout.scheduled_date).label("scheduled_on"),
        )
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .filter(UserProgram.user_id.in_(user_ids), UserWorkout.status == "completed")
        .group_by(UserProgram.user_id)
        .all()
    )
    last_completed_by_user = {
        row.user_id: row.completed_at.date() if row.completed_at else row.scheduled_on
        for row in last_completed_rows
    }

    measurement_rows = (
        db.query(BodyMeasurement)
        .filter(
            _user_date_filter(
                user_ids,
                start_by_user,
                today_by_user,
                BodyMeasurement.user_id,
                BodyMeasurement.measured_on,
            )
        )
        .order_by(BodyMeasurement.user_id, BodyMeasurement.measured_on, BodyMeasurement.id)
        .all()
    )
    measurements_by_user: dict[int, list[BodyMeasurement]] = defaultdict(list)
    for measurement_row in measurement_rows:
        measurements_by_user[measurement_row.user_id].append(measurement_row)

    latest_measurement_candidates = (
        db.query(
            BodyMeasurement,
            func.row_number()
            .over(
                partition_by=BodyMeasurement.user_id,
                order_by=(BodyMeasurement.measured_on.desc(), BodyMeasurement.id.desc()),
            )
            .label("row_number"),
        )
        .filter(
            or_(
                *(
                    and_(
                        BodyMeasurement.user_id == user_id,
                        BodyMeasurement.measured_on <= today_by_user[user_id],
                    )
                    for user_id in user_ids
                )
            )
        )
        .subquery()
    )
    latest_measurement_rows = (
        db.query(latest_measurement_candidates)
        .filter(latest_measurement_candidates.c.row_number == 1)
        .all()
    )
    latest_measurement_by_user = {
        row.user_id: {
            "measured_on": row.measured_on,
            **{
                metric: float(getattr(row, metric)) if getattr(row, metric) is not None else None
                for metric in BODY_METRICS
            },
        }
        for row in latest_measurement_rows
    }

    visible_nutrition_ids = set(user_ids) & nutrition_visible_user_ids
    targets = (
        db.query(NutritionTarget).filter(NutritionTarget.user_id.in_(visible_nutrition_ids)).all()
        if visible_nutrition_ids
        else []
    )
    target_history_by_user: dict[int, list[NutritionTarget]] = defaultdict(list)
    for target_row in sorted(targets, key=lambda row: (row.effective_from, row.id), reverse=True):
        target_history_by_user[target_row.user_id].append(target_row)
    targets_by_user = {
        user_id: next((row for row in rows if row.effective_to is None), None)
        for user_id, rows in target_history_by_user.items()
    }
    nutrition_end_by_user = {
        user_id: min(current_day, actual_today_by_user[user_id] - timedelta(days=1))
        for user_id, current_day in today_by_user.items()
    }
    diary_status_rows = []
    diary_totals: dict[tuple[int, date], DiaryDayNutrition] = {}
    if visible_nutrition_ids:
        diary_entries = (
            db.query(FoodDiaryEntry)
            .filter(
                _user_date_filter(
                    visible_nutrition_ids,
                    start_by_user,
                    nutrition_end_by_user,
                    FoodDiaryEntry.user_id,
                    FoodDiaryEntry.diary_date,
                )
            )
            .order_by(FoodDiaryEntry.user_id, FoodDiaryEntry.diary_date)
            .all()
        )
        diary_totals = aggregate_diary_entries(diary_entries)
        diary_status_rows = (
            db.query(FoodDiaryDayStatus)
            .filter(
                _user_date_filter(
                    visible_nutrition_ids,
                    start_by_user,
                    nutrition_end_by_user,
                    FoodDiaryDayStatus.user_id,
                    FoodDiaryDayStatus.diary_date,
                )
            )
            .all()
        )
    statuses_by_key = {(row.user_id, row.diary_date): row.status for row in diary_status_rows}
    diary_by_user: dict[int, list[NutritionDiaryDay]] = defaultdict(list)
    for (diary_user_id, diary_date), totals in sorted(diary_totals.items()):
        diary_by_user[diary_user_id].append(
            NutritionDiaryDay(
                user_id=diary_user_id,
                diary_date=diary_date,
                calories=totals.calories,
                protein_g=None if totals.missing_macros else totals.protein_g,
                status=cast(
                    NutritionDiaryStatus,
                    statuses_by_key.get((diary_user_id, diary_date), "incomplete"),
                ),
                has_entries=True,
            )
        )
    populated_keys = set(diary_totals)
    for status_row in diary_status_rows:
        key = (status_row.user_id, status_row.diary_date)
        if key in populated_keys:
            continue
        diary_by_user[status_row.user_id].append(
            NutritionDiaryDay(
                user_id=status_row.user_id,
                diary_date=status_row.diary_date,
                calories=Decimal("0") if status_row.status == "fasted" else None,
                protein_g=Decimal("0") if status_row.status == "fasted" else None,
                status=cast(NutritionDiaryStatus, status_row.status),
                has_entries=False,
            )
        )

    training_counts_by_user = collect_training_data_counts(
        db,
        user_ids=user_ids,
        period_starts=start_by_user,
        period_ends=today_by_user,
    )

    set_rows = (
        db.query(
            UserProgram.user_id,
            UserWorkoutExercise.exercise_id,
            UserWorkout.scheduled_date,
            UserWorkoutSet.actual_weight,
            UserWorkoutSet.actual_reps,
        )
        .join(UserWorkout, UserWorkout.user_program_id == UserProgram.id)
        .join(UserWorkoutExercise, UserWorkoutExercise.workout_id == UserWorkout.id)
        .join(UserWorkoutSet, UserWorkoutSet.workout_exercise_id == UserWorkoutExercise.id)
        .filter(
            UserWorkout.status == "completed",
            UserWorkoutSet.is_completed.is_(True),
            working_volume_set_filter(),
            _user_date_filter(
                user_ids,
                start_by_user,
                today_by_user,
                UserProgram.user_id,
                UserWorkout.scheduled_date,
            ),
        )
        .all()
    )
    period_best: dict[tuple[int, int], tuple[float, float]] = {}
    volume_by_user: dict[int, float] = defaultdict(float)
    for set_row in set_rows:
        weight = float(set_row.actual_weight or 0)
        volume = weight * float(set_row.actual_reps or 0)
        volume_by_user[set_row.user_id] += volume
        set_key = (set_row.user_id, cast(int, set_row.exercise_id))
        best_weight, best_volume = period_best.get(set_key, (0.0, 0.0))
        period_best[set_key] = (max(best_weight, weight), max(best_volume, volume))

    previous_best_rows = (
        db.query(
            UserProgram.user_id,
            UserWorkoutExercise.exercise_id,
            func.max(UserWorkoutSet.actual_weight).label("max_weight"),
            func.max(UserWorkoutSet.actual_weight * UserWorkoutSet.actual_reps).label(
                "max_set_volume"
            ),
        )
        .join(UserWorkout, UserWorkout.user_program_id == UserProgram.id)
        .join(UserWorkoutExercise, UserWorkoutExercise.workout_id == UserWorkout.id)
        .join(UserWorkoutSet, UserWorkoutSet.workout_exercise_id == UserWorkoutExercise.id)
        .filter(
            UserWorkout.status == "completed",
            UserWorkoutSet.is_completed.is_(True),
            working_volume_set_filter(),
            or_(
                *(
                    and_(
                        UserProgram.user_id == user_id,
                        UserWorkout.scheduled_date < start_by_user[user_id],
                    )
                    for user_id in user_ids
                )
            ),
        )
        .group_by(UserProgram.user_id, UserWorkoutExercise.exercise_id)
        .all()
    )
    previous_best = {
        (row.user_id, row.exercise_id): (
            float(row.max_weight or 0),
            float(row.max_set_volume or 0),
        )
        for row in previous_best_rows
    }
    new_records_by_user: dict[int, int] = defaultdict(int)
    for (user_id, exercise_id), current in period_best.items():
        previous = previous_best.get((user_id, exercise_id), (0.0, 0.0))
        if current[0] > previous[0] or current[1] > previous[1]:
            new_records_by_user[user_id] += 1

    summaries: list[dict] = []
    for user in users:
        current_day = today_by_user[user.id]
        eligible_nutrition_days = max(
            0,
            (nutrition_end_by_user[user.id] - start_by_user[user.id]).days + 1,
        )
        workouts = [row for row in workouts_by_user[user.id] if row.status != "cancelled"]
        evaluated_workouts = [
            row
            for row in workouts
            if row.scheduled_date < actual_today_by_user[user.id]
            or row.status in {"completed", "skipped"}
        ]
        completed_workouts = [row for row in evaluated_workouts if row.status == "completed"]
        skipped_workouts = [row for row in evaluated_workouts if row.status == "skipped"]
        workout_adherence = calculate_adherence_component(
            achieved=len(completed_workouts),
            evaluated=len(evaluated_workouts),
            weight=ADHERENCE_WEIGHTS["workouts"],
            unavailable_status="not_applicable",
            unavailable_reason="no_evaluable_planned_workouts",
        )

        nutrition_visible = user.id in visible_nutrition_ids
        target = targets_by_user.get(user.id)
        diary_days = diary_by_user[user.id]
        complete_diary_days = [
            row
            for row in diary_days
            if row.status in {"complete", "fasted"} and row.calories is not None
        ]
        adherence_target_days = [
            (row, effective_target)
            for row in complete_diary_days
            if (
                effective_target := _effective_nutrition_target(
                    target_history_by_user[user.id],
                    row.diary_date,
                )
            )
            is not None
        ]
        protein_adherence_days = [
            (row, effective_target)
            for row, effective_target in adherence_target_days
            if row.protein_g is not None
        ]
        calorie_achieved = 0
        protein_achieved = 0
        if target is not None:
            calorie_achieved = sum(
                is_calorie_target_met(cast(Decimal, row.calories), effective_target.calories)
                for row, effective_target in adherence_target_days
            )
            protein_achieved = sum(
                is_protein_target_met(
                    cast(Decimal, row.protein_g),
                    effective_target.protein_g,
                )
                for row, effective_target in protein_adherence_days
            )

        nutrition_status: AdherenceStatus = "insufficient_data" if target else "not_applicable"
        nutrition_reason = (
            "no_logged_days_for_current_target" if target else "nutrition_target_missing"
        )
        calories_adherence = calculate_adherence_component(
            achieved=calorie_achieved,
            evaluated=len(adherence_target_days),
            weight=ADHERENCE_WEIGHTS["calories"],
            unavailable_status=nutrition_status,
            unavailable_reason=nutrition_reason,
        )
        protein_adherence = calculate_adherence_component(
            achieved=protein_achieved,
            evaluated=len(protein_adherence_days),
            weight=ADHERENCE_WEIGHTS["protein"],
            unavailable_status=nutrition_status,
            unavailable_reason=nutrition_reason,
        )
        if not nutrition_visible:
            calories_adherence = calculate_adherence_component(
                achieved=0,
                evaluated=0,
                weight=ADHERENCE_WEIGHTS["calories"],
                unavailable_status="unsupported",
                unavailable_reason="nutrition_access_not_granted",
            )
            protein_adherence = calculate_adherence_component(
                achieved=0,
                evaluated=0,
                weight=ADHERENCE_WEIGHTS["protein"],
                unavailable_status="unsupported",
                unavailable_reason="nutrition_access_not_granted",
            )

        completed_cardio = [row for row in cardio_by_user[user.id] if row.status == "completed"]
        planned_cardio = [row for row in cardio_by_user[user.id] if row.status == "planned"]
        target_dates: dict[date, NutritionTarget] = {}
        for day_offset in range((current_day - start_by_user[user.id]).days + 1):
            cardio_day = start_by_user[user.id] + timedelta(days=day_offset)
            effective_target = _effective_nutrition_target(
                target_history_by_user[user.id],
                cardio_day,
            )
            if effective_target and (effective_target.cardio_trainings_per_week or 0) > 0:
                target_dates[cardio_day] = effective_target
        expected_cardio = floor(
            sum((row.cardio_trainings_per_week or 0) / 7 for row in target_dates.values()) + 0.5
        )
        completed_for_target = sum(
            1
            for row in completed_cardio
            if utc_naive_to_timezone_naive(row.scheduled_at, get_user_timezone_name(user)).date()
            in target_dates
        )
        cardio_adherence = calculate_adherence_component(
            achieved=min(completed_for_target, expected_cardio),
            evaluated=expected_cardio,
            weight=ADHERENCE_WEIGHTS["cardio"],
            unavailable_status="insufficient_data" if target_dates else "not_applicable",
            unavailable_reason=(
                "cardio_target_period_too_short" if target_dates else "cardio_not_planned"
            ),
        )
        components = {
            "workouts": workout_adherence,
            "cardio": cardio_adherence,
            "calories": calories_adherence,
            "protein": protein_adherence,
        }
        overall, included = calculate_overall_adherence(components)

        next_row = next_by_user.get(user.id)
        next_workout = None
        if next_row is not None:
            next_workout = {
                "id": next_row.id,
                "scheduled_date": next_row.scheduled_date,
                "scheduled_time": next_row.scheduled_time,
                "title": next_row.title,
                "status": next_row.status,
            }
        average_calories = (
            round(
                sum(float(cast(Decimal, row.calories)) for row in complete_diary_days)
                / len(complete_diary_days),
                1,
            )
            if complete_diary_days
            else None
        )
        protein_days = [row for row in complete_diary_days if row.protein_g is not None]
        average_protein = (
            round(
                sum(float(cast(Decimal, row.protein_g)) for row in protein_days)
                / len(protein_days),
                1,
            )
            if protein_days
            else None
        )
        logged_day_count = len(complete_diary_days)
        complete_day_count = sum(row.status == "complete" for row in diary_days)
        incomplete_day_count = sum(row.status == "incomplete" for row in diary_days)
        fasted_day_count = sum(row.status == "fasted" for row in diary_days)
        observed_day_count = len({row.diary_date for row in diary_days})
        unlogged_day_count = max(0, eligible_nutrition_days - observed_day_count)
        body_trends = _body_trends(measurements_by_user[user.id])
        weight_trend = next(
            (trend for trend in body_trends if trend["metric"] == "weight_kg"),
            None,
        )
        training_sufficiency = build_training_data_sufficiency(training_counts_by_user[user.id])
        cardio_duration = sum(row.duration_minutes for row in completed_cardio)
        cardio_distance = sum(
            (row.distance_km for row in completed_cardio if row.distance_km is not None),
            Decimal("0"),
        )
        zone_duration: dict[int, int] = defaultdict(int)
        for row in completed_cardio:
            if row.heart_rate_zone is not None:
                zone_duration[row.heart_rate_zone] += row.duration_minutes
        summary = {
            "user_id": user.id,
            "period_days": period_days,
            "period_start": start_by_user[user.id],
            "period_end": current_day,
            "training": {
                "planned_workouts": len(evaluated_workouts),
                "completed_workouts": len(completed_workouts),
                "skipped_workouts": len(skipped_workouts),
                "frequency_per_week": round(len(completed_workouts) * 7 / period_days, 2),
                "volume_kg": round(volume_by_user[user.id], 2),
                "new_personal_records": new_records_by_user[user.id],
                "last_completed_workout_on": last_completed_by_user.get(user.id),
                "next_workout": next_workout,
            },
            "cardio": {
                "completed_sessions": len(completed_cardio),
                "planned_sessions": len(planned_cardio),
                "frequency_per_week": round(len(completed_cardio) * 7 / period_days, 2),
                "duration_minutes": cardio_duration,
                "distance_km": round(float(cardio_distance), 2) if cardio_distance else None,
                "zone_duration": [
                    {"zone": zone, "duration_minutes": duration}
                    for zone, duration in sorted(zone_duration.items())
                ],
            },
            "nutrition": {
                "visible": nutrition_visible,
                "logged_days": logged_day_count if nutrition_visible else 0,
                "complete_days": complete_day_count if nutrition_visible else 0,
                "incomplete_days": incomplete_day_count if nutrition_visible else 0,
                "fasted_days": fasted_day_count if nutrition_visible else 0,
                "unlogged_days": unlogged_day_count if nutrition_visible else 0,
                "adherence_evaluated_days": (
                    len(adherence_target_days) if nutrition_visible else 0
                ),
                "average_calories": average_calories if nutrition_visible else None,
                "target_calories": target.calories if target and nutrition_visible else None,
                "average_protein_g": average_protein if nutrition_visible else None,
                "target_protein_g": target.protein_g if target and nutrition_visible else None,
                "target_effective_on": (
                    target.effective_from if target and nutrition_visible else None
                ),
            },
            "body": {
                "latest_measurement": latest_measurement_by_user.get(user.id),
                "trends": body_trends,
                "priority": serialize_body_priority(user.profile),
                "guidance": BODY_MEASUREMENT_GUIDANCE,
            },
            "adherence": {
                "formula_version": FORMULA_VERSION,
                "overall_percent": overall,
                "included_components": included,
                **components,
            },
            "data_sufficiency": {
                **training_sufficiency,
                "nutrition_coverage": build_nutrition_coverage_signal(
                    logged_day_count=logged_day_count if nutrition_visible else 0,
                    eligible_day_count=eligible_nutrition_days,
                    visible=nutrition_visible,
                ),
                "weight_trend": build_body_metric_signal(
                    point_count=weight_trend["point_count"] if weight_trend else 0,
                    span_days=weight_trend["span_days"] if weight_trend else 0,
                ),
                "anthropometry": build_anthropometry_signal(body_trends),
                "schedule_adherence": build_schedule_adherence_signal(
                    evaluable_workout_count=len(evaluated_workouts),
                ),
            },
        }
        summaries.append(summary)
    return summaries
