from __future__ import annotations

from sqlalchemy import and_, desc, or_
from sqlalchemy.orm import Session, joinedload

from fitminiapp_api.core.timezone import now_msk_naive, today_for_user
from fitminiapp_api.models.program import (
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.workout import WorkoutSetCreate


class WorkoutStateError(ValueError):
    pass


class WorkoutValidationError(ValueError):
    pass


def counts_toward_working_volume(workout_set: UserWorkoutSet) -> bool:
    """Legacy null kinds retain their historical working-volume behavior."""

    if workout_set.set_kind == "warmup":
        return False
    if workout_set.planned_role in {"warmup", "activation"}:
        return False
    return workout_set.set_kind in {None, "working", "drop"}


def is_pr_record_set(workout_set: UserWorkoutSet) -> bool:
    return counts_toward_working_volume(workout_set) and workout_set.planned_role not in {
        "drop",
        "mini_set",
        "cluster_member",
    }


def set_analytics_bucket(workout_set: UserWorkoutSet) -> str:
    if workout_set.planned_role in {"drop", "mini_set", "cluster_member"}:
        return "intensifier"
    if workout_set.planned_role in {"warmup", "activation"}:
        return "preparation"
    return "working"


def working_volume_set_filter():
    return or_(
        and_(
            UserWorkoutSet.planned_role.is_(None),
            or_(
                UserWorkoutSet.set_kind.is_(None),
                UserWorkoutSet.set_kind.in_(("working", "drop")),
            ),
        ),
        and_(
            UserWorkoutSet.planned_role.notin_(("warmup", "activation")),
            or_(
                UserWorkoutSet.set_kind.is_(None),
                UserWorkoutSet.set_kind.in_(("working", "drop")),
            ),
        ),
    )


def pr_record_set_filter():
    return and_(
        working_volume_set_filter(),
        or_(
            UserWorkoutSet.planned_role.is_(None),
            UserWorkoutSet.planned_role.notin_(("drop", "mini_set", "cluster_member")),
        ),
    )


def get_today_workout(db: Session, user: User) -> UserWorkout | None:
    return (
        db.query(UserWorkout)
        .join(UserProgram, UserWorkout.user_program_id == UserProgram.id)
        .options(
            joinedload(UserWorkout.exercises).joinedload(UserWorkoutExercise.exercise),
            joinedload(UserWorkout.exercises).joinedload(UserWorkoutExercise.sets),
        )
        .filter(
            UserProgram.user_id == user.id,
            UserProgram.is_active.is_(True),
            UserWorkout.scheduled_date == today_for_user(user),
        )
        .first()
    )


def start_workout(db: Session, workout: UserWorkout) -> UserWorkout:
    if workout.status == "completed":
        raise WorkoutStateError("Workout already completed")
    if workout.status == "planned":
        workout.status = "in_progress"
        workout.started_at = now_msk_naive()
        db.commit()
        db.refresh(workout)
    return workout


def add_or_update_set(
    db: Session, workout: UserWorkout, payload: WorkoutSetCreate
) -> UserWorkoutSet:
    if workout.status == "completed":
        raise WorkoutStateError("Cannot log sets for completed workout")
    if workout.status == "planned":
        workout.status = "in_progress"
        workout.started_at = now_msk_naive()

    exercise = next(
        (row for row in workout.exercises if row.id == payload.workout_exercise_id), None
    )
    if exercise is None:
        raise WorkoutValidationError("Exercise does not belong to workout")
    if payload.set_number < 1:
        raise WorkoutValidationError("set_number must be >= 1")
    if payload.set_number > exercise.prescribed_sets:
        raise WorkoutValidationError("set_number exceeds prescribed_sets")

    row = (
        db.query(UserWorkoutSet)
        .filter(
            UserWorkoutSet.workout_exercise_id == payload.workout_exercise_id,
            UserWorkoutSet.set_number == payload.set_number,
        )
        .first()
    )
    if row is None:
        row = UserWorkoutSet(
            workout_exercise_id=payload.workout_exercise_id, set_number=payload.set_number
        )
        db.add(row)

    row.actual_reps = payload.actual_reps
    row.actual_weight = payload.actual_weight
    row.rir = payload.rir
    row.set_kind = payload.set_kind
    row.reached_failure = payload.reached_failure
    row.is_completed = payload.is_completed
    db.commit()
    db.refresh(row)
    return row


def delete_last_set(db: Session, workout: UserWorkout, workout_exercise_id: int) -> None:
    if workout.status == "completed":
        raise WorkoutStateError("Cannot modify sets for completed workout")
    exercise = next((row for row in workout.exercises if row.id == workout_exercise_id), None)
    if exercise is None:
        raise WorkoutValidationError("Exercise does not belong to workout")
    last_set = (
        db.query(UserWorkoutSet)
        .filter(UserWorkoutSet.workout_exercise_id == workout_exercise_id)
        .order_by(UserWorkoutSet.set_number.desc())
        .first()
    )
    if not last_set:
        raise WorkoutValidationError("No logged sets to delete")
    db.delete(last_set)
    db.commit()


def complete_workout(db: Session, workout: UserWorkout) -> UserWorkout:
    if workout.status == "completed":
        return workout
    workout.status = "completed"
    if workout.started_at is None:
        workout.started_at = now_msk_naive()
    workout.completed_at = now_msk_naive()
    db.commit()
    db.refresh(workout)
    return workout


def _sets_volume(sets: list[UserWorkoutSet]) -> float:
    return float(
        sum(
            (row.actual_reps or 0) * (row.actual_weight or 0)
            for row in sets
            if row.is_completed and counts_toward_working_volume(row)
        )
    )


def _top_weight(sets: list[UserWorkoutSet]) -> float | None:
    weights = [
        float(row.actual_weight)
        for row in sets
        if row.is_completed and counts_toward_working_volume(row) and row.actual_weight is not None
    ]
    return max(weights) if weights else None


def get_previous_completed_exercise(
    db: Session, user: User, workout: UserWorkout, exercise: UserWorkoutExercise
) -> UserWorkoutExercise | None:
    return (
        db.query(UserWorkoutExercise)
        .join(UserWorkout, UserWorkoutExercise.workout_id == UserWorkout.id)
        .join(UserProgram, UserWorkout.user_program_id == UserProgram.id)
        .options(joinedload(UserWorkoutExercise.sets), joinedload(UserWorkoutExercise.workout))
        .filter(
            UserProgram.user_id == user.id,
            UserWorkoutExercise.exercise_id == exercise.exercise_id,
            UserWorkout.id != workout.id,
            UserWorkout.status == "completed",
            UserWorkout.scheduled_date <= workout.scheduled_date,
        )
        .order_by(
            desc(UserWorkout.scheduled_date), desc(UserWorkout.completed_at), desc(UserWorkout.id)
        )
        .first()
    )
