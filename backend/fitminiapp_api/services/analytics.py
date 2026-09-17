from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session, joinedload

from fitminiapp_api.core.timezone import today_for_user
from fitminiapp_api.models.exercise import (
    Equipment,
    Exercise,
    ExerciseEquipment,
    ExerciseMuscle,
    Muscle,
)
from fitminiapp_api.models.program import (
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import BodyMeasurement, User
from fitminiapp_api.services.data_quality import (
    build_training_data_sufficiency,
    collect_training_data_counts,
)
from fitminiapp_api.services.exercise_catalog import get_visible_exercise_display_map
from fitminiapp_api.services.period_bounds import MAX_REPORT_DAYS, resolve_progress_bounds
from fitminiapp_api.services.workouts import (
    counts_toward_working_volume,
    working_volume_set_filter,
)


def _completed_set_volume(workout_set) -> float:
    if not workout_set.is_completed or not counts_toward_working_volume(workout_set):
        return 0.0
    return float((workout_set.actual_reps or 0) * (workout_set.actual_weight or 0))


def _load_workouts(
    db: Session,
    user: User,
    *,
    workout_id: int | None = None,
) -> list[UserWorkout]:
    query = (
        db.query(UserWorkout)
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .options(
            joinedload(UserWorkout.exercises).joinedload(UserWorkoutExercise.exercise),
            joinedload(UserWorkout.exercises).joinedload(UserWorkoutExercise.sets),
        )
    )
    filters = [UserProgram.user_id == user.id]
    if workout_id is not None:
        filters.append(UserWorkout.id == workout_id)
    return (
        query.filter(*filters)
        .order_by(UserWorkout.scheduled_date.asc(), UserWorkout.id.asc())
        .all()
    )


def build_user_progress(db: Session, user: User) -> dict:
    today = today_for_user(user)
    workouts = _load_workouts(db, user)
    due_workouts = [
        workout
        for workout in workouts
        if workout.scheduled_date <= today and workout.status != "cancelled"
    ]
    completed = [workout for workout in due_workouts if workout.status == "completed"]
    skipped = [workout for workout in due_workouts if workout.status == "skipped"]
    missed = [
        workout
        for workout in due_workouts
        if workout.status in {"planned", "in_progress"} and workout.scheduled_date < today
    ]
    adherence_base = len(completed) + len(skipped) + len(missed)
    adherence = round(len(completed) * 100 / adherence_base, 1) if adherence_base else 0.0

    streak = 0
    for workout in reversed(due_workouts):
        if workout.status == "completed":
            streak += 1
        elif workout.scheduled_date == today and workout.status in {"planned", "in_progress"}:
            continue
        elif workout.status in {"skipped", "planned", "in_progress"}:
            break

    measurements = (
        db.query(BodyMeasurement)
        .filter(
            BodyMeasurement.user_id == user.id,
            BodyMeasurement.measured_on <= today,
            BodyMeasurement.weight_kg.is_not(None),
        )
        .order_by(BodyMeasurement.measured_on.asc(), BodyMeasurement.id.asc())
        .all()
    )
    weight_points = [
        (row.measured_on, float(row.weight_kg)) for row in measurements if row.weight_kg is not None
    ]
    weights = [
        {"measured_on": measured_on, "weight_kg": weight_kg}
        for measured_on, weight_kg in weight_points
    ]
    weight_change = (
        round(weight_points[-1][1] - weight_points[0][1], 2) if len(weight_points) >= 2 else None
    )

    weekly: dict = defaultdict(lambda: {"completed_workouts": 0, "volume_kg": 0.0})
    display_map = get_visible_exercise_display_map(db, user)
    records: dict[int, dict] = {}
    for workout in completed:
        week_start = workout.scheduled_date - timedelta(days=workout.scheduled_date.weekday())
        weekly[week_start]["completed_workouts"] += 1
        for exercise in workout.exercises:
            exercise_title = (
                display_map[exercise.exercise_id].title
                if exercise.exercise_id in display_map
                else (
                    exercise.exercise.title
                    if exercise.exercise is not None
                    else f"Упражнение {exercise.exercise_id}"
                )
            )
            record = records.setdefault(
                exercise.exercise_id,
                {
                    "exercise_id": exercise.exercise_id,
                    "exercise_title": exercise_title,
                    "max_weight_kg": None,
                    "best_set_volume_kg": 0.0,
                    "last_performed_on": workout.scheduled_date,
                },
            )
            record["last_performed_on"] = max(record["last_performed_on"], workout.scheduled_date)
            for workout_set in exercise.sets:
                volume = _completed_set_volume(workout_set)
                weekly[week_start]["volume_kg"] += volume
                record["best_set_volume_kg"] = max(record["best_set_volume_kg"], volume)
                if (
                    workout_set.is_completed
                    and counts_toward_working_volume(workout_set)
                    and workout_set.actual_weight is not None
                ):
                    current_max = record["max_weight_kg"]
                    record["max_weight_kg"] = max(
                        float(workout_set.actual_weight),
                        float(current_max) if current_max is not None else 0.0,
                    )

    return {
        "workouts_total": len(due_workouts),
        "workouts_completed": len(completed),
        "workouts_skipped": len(skipped),
        "workouts_missed": len(missed),
        "adherence_percent": adherence,
        "current_streak": streak,
        "weight_change_kg": weight_change,
        "weights": weights,
        "weekly_volume": [
            {
                "week_start": week_start,
                "completed_workouts": values["completed_workouts"],
                "volume_kg": round(values["volume_kg"], 2),
            }
            for week_start, values in sorted(weekly.items())
        ],
        "personal_records": sorted(
            records.values(),
            key=lambda item: (item["last_performed_on"], item["exercise_title"]),
            reverse=True,
        ),
    }


RIR_VALUES = ("0", "1", "2", "3", "4+")


def _period_exercise_aggregates(db: Session, user: User, period_start, period_end) -> list:
    set_volume = UserWorkoutSet.actual_reps * UserWorkoutSet.actual_weight
    return (
        db.query(
            UserWorkoutExercise.exercise_id.label("exercise_id"),
            func.count(func.distinct(UserWorkoutExercise.id)).label("performed_session_count"),
            func.count(UserWorkoutSet.id).label("completed_set_count"),
            func.min(UserWorkout.scheduled_date).label("first_performed_on"),
            func.max(UserWorkout.scheduled_date).label("last_performed_on"),
            func.sum(UserWorkoutSet.actual_reps).label("reps_total"),
            func.count(UserWorkoutSet.actual_reps).label("reps_recorded_sets"),
            func.max(UserWorkoutSet.actual_weight).label("max_external_load_kg"),
            func.max(set_volume).label("best_set_volume_kg"),
            func.sum(set_volume).label("external_load_volume_kg"),
            func.count(set_volume).label("volume_recorded_sets"),
            func.sum(case((UserWorkoutSet.rir == "0", 1), else_=0)).label("rir_0"),
            func.sum(case((UserWorkoutSet.rir == "1", 1), else_=0)).label("rir_1"),
            func.sum(case((UserWorkoutSet.rir == "2", 1), else_=0)).label("rir_2"),
            func.sum(case((UserWorkoutSet.rir == "3", 1), else_=0)).label("rir_3"),
            func.sum(case((UserWorkoutSet.rir == "4+", 1), else_=0)).label("rir_4_plus"),
        )
        .select_from(UserProgram)
        .join(UserWorkout, UserWorkout.user_program_id == UserProgram.id)
        .join(UserWorkoutExercise, UserWorkoutExercise.workout_id == UserWorkout.id)
        .join(UserWorkoutSet, UserWorkoutSet.workout_exercise_id == UserWorkoutExercise.id)
        .filter(
            UserProgram.user_id == user.id,
            UserWorkout.status == "completed",
            UserWorkout.scheduled_date.between(period_start, period_end),
            UserWorkoutSet.is_completed.is_(True),
            working_volume_set_filter(),
        )
        .group_by(UserWorkoutExercise.exercise_id)
        .all()
    )


def _bounded_exercise_history(
    db: Session,
    user: User,
    period_start,
    period_end,
    history_limit: int,
) -> list:
    performed = (
        db.query(
            UserWorkoutExercise.id.label("workout_exercise_id"),
            UserWorkoutExercise.exercise_id.label("exercise_id"),
            UserWorkout.id.label("workout_id"),
            UserWorkout.scheduled_date.label("performed_on"),
        )
        .select_from(UserProgram)
        .join(UserWorkout, UserWorkout.user_program_id == UserProgram.id)
        .join(UserWorkoutExercise, UserWorkoutExercise.workout_id == UserWorkout.id)
        .join(UserWorkoutSet, UserWorkoutSet.workout_exercise_id == UserWorkoutExercise.id)
        .filter(
            UserProgram.user_id == user.id,
            UserWorkout.status == "completed",
            UserWorkout.scheduled_date.between(period_start, period_end),
            UserWorkoutSet.is_completed.is_(True),
            working_volume_set_filter(),
        )
        .group_by(
            UserWorkoutExercise.id,
            UserWorkoutExercise.exercise_id,
            UserWorkout.id,
            UserWorkout.scheduled_date,
        )
        .subquery()
    )
    ranked = db.query(
        performed,
        func.row_number()
        .over(
            partition_by=performed.c.exercise_id,
            order_by=(
                performed.c.performed_on.desc(),
                performed.c.workout_id.desc(),
                performed.c.workout_exercise_id.desc(),
            ),
        )
        .label("history_position"),
    ).subquery()
    return (
        db.query(
            ranked.c.exercise_id,
            ranked.c.workout_id,
            ranked.c.workout_exercise_id,
            ranked.c.performed_on,
            UserWorkoutSet.set_number,
            UserWorkoutSet.actual_reps,
            UserWorkoutSet.actual_weight,
            UserWorkoutSet.rir,
            UserWorkoutSet.set_kind,
            UserWorkoutSet.reached_failure,
        )
        .join(
            UserWorkoutSet,
            UserWorkoutSet.workout_exercise_id == ranked.c.workout_exercise_id,
        )
        .filter(
            ranked.c.history_position <= history_limit,
            UserWorkoutSet.is_completed.is_(True),
            working_volume_set_filter(),
        )
        .order_by(
            ranked.c.exercise_id,
            ranked.c.performed_on.desc(),
            ranked.c.workout_id.desc(),
            ranked.c.workout_exercise_id.desc(),
            UserWorkoutSet.set_number.asc(),
            UserWorkoutSet.id.asc(),
        )
        .all()
    )


def _exercise_metadata(db: Session, user: User, exercise_ids: set[int]) -> dict[int, dict]:
    if not exercise_ids:
        return {}
    rows = (
        db.query(
            Exercise.id.label("exercise_id"),
            Exercise.source_exercise_id,
            Exercise.created_by_user_id,
            Exercise.title,
            Exercise.is_deleted,
            ExerciseMuscle.role.label("muscle_role"),
            Muscle.identifier.label("muscle_id"),
            Muscle.name.label("muscle_name"),
            Equipment.identifier.label("equipment_id"),
        )
        .select_from(Exercise)
        .outerjoin(ExerciseMuscle, ExerciseMuscle.exercise_id == Exercise.id)
        .outerjoin(Muscle, Muscle.id == ExerciseMuscle.muscle_id)
        .outerjoin(ExerciseEquipment, ExerciseEquipment.exercise_id == Exercise.id)
        .outerjoin(Equipment, Equipment.id == ExerciseEquipment.equipment_id)
        .filter(
            or_(
                Exercise.id.in_(exercise_ids),
                and_(
                    Exercise.created_by_user_id == user.id,
                    Exercise.source_exercise_id.in_(exercise_ids),
                ),
            )
        )
        .order_by(Exercise.id)
        .all()
    )
    stored: dict[int, dict] = {}
    for row in rows:
        item = stored.setdefault(
            row.exercise_id,
            {
                "id": row.exercise_id,
                "source_exercise_id": row.source_exercise_id,
                "created_by_user_id": row.created_by_user_id,
                "title": row.title,
                "is_deleted": row.is_deleted,
                "muscles": set(),
                "equipment": set(),
            },
        )
        if row.muscle_id is not None:
            item["muscles"].add((row.muscle_role, row.muscle_id, row.muscle_name))
        if row.equipment_id is not None:
            item["equipment"].add(row.equipment_id)

    overrides = {
        item["source_exercise_id"]: item
        for item in stored.values()
        if item["source_exercise_id"] in exercise_ids
        and item["created_by_user_id"] == user.id
        and not item["is_deleted"]
    }
    return {
        exercise_id: overrides.get(exercise_id, stored.get(exercise_id, {}))
        for exercise_id in exercise_ids
    }


def _serialize_training_session(rows: list) -> dict:
    sets: list[dict] = []
    reps_total = 0
    reps_recorded_sets = 0
    max_external_load: float | None = None
    external_load_volume = 0.0
    volume_recorded_sets = 0
    for row in rows:
        reps = row.actual_reps
        external_load = float(row.actual_weight) if row.actual_weight is not None else None
        set_volume = (
            float(reps) * external_load if reps is not None and external_load is not None else None
        )
        if reps is not None:
            reps_total += reps
            reps_recorded_sets += 1
        if external_load is not None:
            max_external_load = (
                external_load
                if max_external_load is None
                else max(max_external_load, external_load)
            )
        if set_volume is not None:
            external_load_volume += set_volume
            volume_recorded_sets += 1
        sets.append(
            {
                "set_number": row.set_number,
                "reps": reps,
                "external_load_kg": external_load,
                "external_load_volume_kg": (
                    round(set_volume, 2) if set_volume is not None else None
                ),
                "rir": row.rir,
                "set_kind": row.set_kind,
                "reached_failure": row.reached_failure,
            }
        )
    first = rows[0]
    return {
        "workout_id": first.workout_id,
        "workout_exercise_id": first.workout_exercise_id,
        "performed_on": first.performed_on,
        "completed_set_count": len(rows),
        "reps_total": reps_total if reps_recorded_sets else None,
        "reps_recorded_sets": reps_recorded_sets,
        "max_external_load_kg": max_external_load,
        "external_load_volume_kg": (
            round(external_load_volume, 2) if volume_recorded_sets else None
        ),
        "volume_recorded_sets": volume_recorded_sets,
        "sets": sets,
    }


def build_training_analytics(
    db: Session,
    user: User,
    period_days: int,
    *,
    exercise_history_limit: int,
) -> dict:
    bounds = resolve_progress_bounds(user, period_days)
    return _build_training_analytics(
        db,
        user,
        bounds.start,
        bounds.end,
        exercise_history_limit=exercise_history_limit,
    )


def build_training_analytics_for_range(
    db: Session,
    user: User,
    period_start,
    period_end,
    *,
    exercise_history_limit: int,
) -> dict:
    if period_end < period_start:
        raise ValueError("period_end must not be before period_start")
    if (period_end - period_start).days + 1 > MAX_REPORT_DAYS:
        raise ValueError(f"period cannot exceed {MAX_REPORT_DAYS} days")
    return _build_training_analytics(
        db,
        user,
        period_start,
        period_end,
        exercise_history_limit=exercise_history_limit,
    )


def _build_training_analytics(
    db: Session,
    user: User,
    period_start,
    period_end,
    *,
    exercise_history_limit: int,
) -> dict:
    if not 1 <= exercise_history_limit <= 100:
        raise ValueError("exercise_history_limit must be between 1 and 100")

    period_days = (period_end - period_start).days + 1
    training_counts = collect_training_data_counts(
        db,
        user_ids=[user.id],
        period_starts={user.id: period_start},
        period_ends={user.id: period_end},
    )[user.id]
    aggregates = _period_exercise_aggregates(db, user, period_start, period_end)
    exercise_ids = {row.exercise_id for row in aggregates}
    history_rows = _bounded_exercise_history(
        db,
        user,
        period_start,
        period_end,
        exercise_history_limit,
    )
    metadata = _exercise_metadata(db, user, exercise_ids)

    history_groups: dict[tuple[int, int], list] = defaultdict(list)
    for row in history_rows:
        history_groups[(row.exercise_id, row.workout_exercise_id)].append(row)
    sessions_by_exercise: dict[int, list[dict]] = defaultdict(list)
    for (exercise_id, _workout_exercise_id), rows in history_groups.items():
        sessions_by_exercise[exercise_id].append(_serialize_training_session(rows))

    primary_exposure: dict[tuple[str, str], int] = defaultdict(int)
    secondary_exposure: dict[tuple[str, str], int] = defaultdict(int)
    completed_sets_without_muscle_metadata = 0
    rir_distribution = dict.fromkeys(RIR_VALUES, 0)
    exercises: list[dict] = []

    for row in aggregates:
        item_metadata = metadata.get(row.exercise_id, {})
        muscles = item_metadata.get("muscles", set())
        if not muscles:
            completed_sets_without_muscle_metadata += row.completed_set_count
        for role, muscle_id, muscle_name in muscles:
            target = primary_exposure if role == "primary" else secondary_exposure
            target[(muscle_id, muscle_name)] += row.completed_set_count

        for value in RIR_VALUES:
            rir_distribution[value] += int(getattr(row, f"rir_{value.replace('+', '_plus')}") or 0)

        sessions = sessions_by_exercise[row.exercise_id]
        sessions.sort(
            key=lambda session: (
                session["performed_on"],
                session["workout_id"],
                session["workout_exercise_id"],
            ),
            reverse=True,
        )
        exercises.append(
            {
                "exercise_id": row.exercise_id,
                "exercise_title": item_metadata.get("title", f"Упражнение {row.exercise_id}"),
                "uses_bodyweight_equipment": "bodyweight" in item_metadata.get("equipment", set()),
                "performed_session_count": row.performed_session_count,
                "completed_set_count": row.completed_set_count,
                "first_performed_on": row.first_performed_on,
                "last_performed_on": row.last_performed_on,
                "reps_total": int(row.reps_total) if row.reps_total is not None else None,
                "reps_recorded_sets": row.reps_recorded_sets,
                "max_external_load_kg": (
                    float(row.max_external_load_kg)
                    if row.max_external_load_kg is not None
                    else None
                ),
                "best_set_volume_kg": (
                    round(float(row.best_set_volume_kg), 2)
                    if row.best_set_volume_kg is not None
                    else None
                ),
                "external_load_volume_kg": (
                    round(float(row.external_load_volume_kg), 2)
                    if row.external_load_volume_kg is not None
                    else None
                ),
                "volume_recorded_sets": row.volume_recorded_sets,
                "history_truncated": row.performed_session_count > len(sessions),
                "sessions": sessions,
            }
        )

    exercises.sort(
        key=lambda item: (item["last_performed_on"], item["exercise_title"]),
        reverse=True,
    )
    completed_set_count = sum(row.completed_set_count for row in aggregates)
    reps_recorded_sets = sum(row.reps_recorded_sets for row in aggregates)
    volume_recorded_sets = sum(row.volume_recorded_sets for row in aggregates)
    rir_recorded_sets = sum(rir_distribution.values())

    def exposure_payload(values: dict[tuple[str, str], int]) -> list[dict]:
        return [
            {
                "muscle_id": muscle_id,
                "muscle_name": muscle_name,
                "completed_set_count": completed_sets,
            }
            for (muscle_id, muscle_name), completed_sets in sorted(
                values.items(), key=lambda item: (-item[1], item[0][1])
            )
        ]

    return {
        "period_days": period_days,
        "period_start": period_start,
        "period_end": period_end,
        "exercise_history_limit": exercise_history_limit,
        "completed_set_count": completed_set_count,
        "reps_total": (
            sum(int(row.reps_total or 0) for row in aggregates) if reps_recorded_sets else None
        ),
        "reps_recorded_sets": reps_recorded_sets,
        "external_load_volume_kg": (
            round(sum(float(row.external_load_volume_kg or 0) for row in aggregates), 2)
            if volume_recorded_sets
            else None
        ),
        "volume_recorded_sets": volume_recorded_sets,
        "exercises": exercises,
        "rir": {
            "completed_set_count": completed_set_count,
            "recorded_set_count": rir_recorded_sets,
            "missing_set_count": completed_set_count - rir_recorded_sets,
            "distribution": [
                {"value": value, "completed_set_count": rir_distribution[value]}
                for value in RIR_VALUES
            ],
        },
        "primary_muscle_exposure": exposure_payload(primary_exposure),
        "secondary_muscle_exposure": exposure_payload(secondary_exposure),
        "completed_sets_without_muscle_metadata": completed_sets_without_muscle_metadata,
        "data_sufficiency": build_training_data_sufficiency(training_counts),
    }


def build_workout_timeline(
    db: Session,
    user: User,
    limit: int = 30,
    *,
    workout_id: int | None = None,
) -> list[dict]:
    display_map = get_visible_exercise_display_map(db, user)
    workouts = list(reversed(_load_workouts(db, user, workout_id=workout_id)))[:limit]
    result: list[dict] = []
    for workout in workouts:
        completed_sets = 0
        volume = 0.0
        exercises: list[dict] = []
        for exercise in sorted(workout.exercises, key=lambda item: item.sort_order):
            sets = []
            for workout_set in sorted(exercise.sets, key=lambda item: item.set_number):
                completed_sets += int(workout_set.is_completed)
                volume += _completed_set_volume(workout_set)
                sets.append(
                    {
                        "set_number": workout_set.set_number,
                        "actual_reps": workout_set.actual_reps,
                        "actual_weight": workout_set.actual_weight,
                        "rir": workout_set.rir,
                        "set_kind": workout_set.set_kind,
                        "reached_failure": workout_set.reached_failure,
                        "is_completed": workout_set.is_completed,
                    }
                )
            exercises.append(
                {
                    "workout_exercise_id": exercise.id,
                    "exercise_id": exercise.exercise_id,
                    "exercise_title": (
                        display_map[exercise.exercise_id].title
                        if exercise.exercise_id in display_map
                        else (
                            exercise.exercise.title
                            if exercise.exercise is not None
                            else f"Упражнение {exercise.exercise_id}"
                        )
                    ),
                    "notes": exercise.notes,
                    "superset_group": exercise.superset_group,
                    "superset_order": exercise.superset_order,
                    "sets": sets,
                }
            )
        result.append(
            {
                "id": workout.id,
                "scheduled_date": workout.scheduled_date,
                "scheduled_time": workout.scheduled_time,
                "title": workout.title,
                "status": workout.status,
                "completed_at": workout.completed_at,
                "completed_sets": completed_sets,
                "volume_kg": round(volume, 2),
                "completion_feedback": workout.completion_feedback,
                "completion_note": workout.completion_note,
                "exercises": exercises,
            }
        )
    return result
