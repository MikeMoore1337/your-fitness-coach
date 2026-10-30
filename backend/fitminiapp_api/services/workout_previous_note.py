from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from fitminiapp_api.models.program import UserProgram, UserWorkout, UserWorkoutExercise


class WorkoutNotFound(ValueError):
    pass


def _same_day_context(
    current: list[UserWorkoutExercise], previous: list[UserWorkoutExercise]
) -> bool:
    current_slots = {item.source_template_exercise_id for item in current}
    previous_slots = {item.source_template_exercise_id for item in previous}
    current_slots.discard(None)
    previous_slots.discard(None)
    if current_slots or previous_slots:
        return bool(current_slots & previous_slots)
    current_exercises = sorted((item.sort_order, item.exercise_id) for item in current)
    previous_exercises = sorted((item.sort_order, item.exercise_id) for item in previous)
    return bool(current_exercises) and current_exercises == previous_exercises


def _completion_bounds(workout: UserWorkout) -> tuple[datetime, datetime] | None:
    if workout.completed_at is None:
        return None
    if workout.completed_at_utc is not None:
        return workout.completed_at_utc, workout.completed_at_utc
    # shortcut: legacy completion offsets are unknown; use exact UTC after backfill exists.
    return workout.completed_at - timedelta(days=1), workout.completed_at + timedelta(days=1)


def find_previous_workout_note(db: Session, user_id: int, workout_id: int) -> dict | None:
    target = (
        select(UserWorkout.user_program_id, UserWorkout.day_number)
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .where(UserWorkout.id == workout_id, UserProgram.user_id == user_id)
        .subquery()
    )
    # One statement keeps the target plan, revision, and history on one database snapshot.
    with db.no_autoflush:
        rows = (
            db.query(UserWorkout, UserWorkoutExercise, UserProgram.current_revision_number)
            .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
            .join(
                target,
                and_(
                    UserWorkout.user_program_id == target.c.user_program_id,
                    or_(
                        UserWorkout.id == workout_id,
                        and_(
                            UserWorkout.day_number == target.c.day_number,
                            UserWorkout.status == "completed",
                        ),
                    ),
                ),
            )
            .outerjoin(UserWorkoutExercise, UserWorkoutExercise.workout_id == UserWorkout.id)
            .filter(UserProgram.user_id == user_id)
            .all()
        )
    workouts: dict[int, UserWorkout] = {}
    exercises: dict[int, list[UserWorkoutExercise]] = {}
    revision = 0
    for row, exercise, current_revision in rows:
        workouts[row.id] = row
        if exercise is not None:
            exercises.setdefault(row.id, []).append(exercise)
        if row.id == workout_id:
            revision = current_revision
    workout = workouts.get(workout_id)
    if workout is None:
        raise WorkoutNotFound
    if workout.status not in {"planned", "in_progress"}:
        return None
    if (
        workout.status == "planned"
        and workout.source_cycle_week is not None
        and (workout.plan_materialized is False or workout.plan_revision_number != revision)
    ):
        return None
    if workout.started_at is not None:
        # shortcut: start timezone is not stored; narrow these bounds when UTC starts exist.
        cutoff = (workout.started_at - timedelta(days=1), workout.started_at + timedelta(days=1))
    else:
        now = datetime.now(UTC).replace(tzinfo=None)
        cutoff = (now, now)

    candidates: list[tuple[datetime, datetime, UserWorkout]] = []
    for previous in workouts.values():
        if previous.id == workout_id:
            continue
        bounds = _completion_bounds(previous)
        if bounds is None:
            return None
        low, high = bounds
        if low >= cutoff[1]:
            continue
        if high >= cutoff[0]:
            return None
        candidates.append((low, high, previous))

    candidates.sort(key=lambda item: item[0], reverse=True)
    for index, (low, _high, previous) in enumerate(candidates):
        if index + 1 < len(candidates) and low <= candidates[index + 1][1]:
            return None
        if not _same_day_context(exercises.get(workout_id, []), exercises.get(previous.id, [])):
            return None
        if previous.completion_note and previous.completion_note.strip():
            assert previous.completed_at is not None
            return {
                "note": previous.completion_note,
                "completed_on": previous.completed_at.date(),
                "day_number": previous.day_number,
                "workout_title": previous.title,
                "is_latest_completion": index == 0,
            }
    return None
