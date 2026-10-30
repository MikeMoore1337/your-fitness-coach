from sqlalchemy.orm import Session, joinedload

from fitminiapp_api.models.program import UserProgram, UserWorkout, UserWorkoutExercise
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.workout_copy import (
    WorkoutCopyExercise,
    WorkoutCopyResponse,
)
from fitminiapp_api.services.exercise_catalog import get_visible_exercise_display_map
from fitminiapp_api.services.workout_metrics import workout_exercise_metric_type


class CompletedWorkoutNotFound(LookupError):
    pass


def get_completed_workout_copy(db: Session, user: User, workout_id: int) -> WorkoutCopyResponse:
    workout = (
        db.query(UserWorkout)
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .options(
            joinedload(UserWorkout.exercises).joinedload(UserWorkoutExercise.exercise),
            joinedload(UserWorkout.exercises).joinedload(UserWorkoutExercise.sets),
        )
        .filter(
            UserWorkout.id == workout_id,
            UserProgram.user_id == user.id,
            UserWorkout.status == "completed",
        )
        .first()
    )
    if workout is None:
        raise CompletedWorkoutNotFound

    titles = get_visible_exercise_display_map(db, user)
    exercises = []
    for exercise in sorted(workout.exercises, key=lambda item: (item.sort_order, item.id)):
        visible = titles.get(exercise.exercise_id) or exercise.exercise
        completed = [item for item in exercise.sets if item.is_completed]
        completed.sort(
            key=lambda item: (
                0 if item.set_kind == "warmup" or item.planned_role == "warmup" else 1,
                item.set_number,
                item.id,
            )
        )
        exercises.append(
            WorkoutCopyExercise.model_validate(
                {
                    "exercise_title": visible.title if visible else "Упражнение без названия",
                    "metric_type": workout_exercise_metric_type(exercise),
                    "sort_order": exercise.sort_order,
                    "sets": [
                        {
                            "set_number": item.set_number,
                            "actual_reps": item.actual_reps,
                            "actual_weight": item.actual_weight,
                            "duration_minutes": item.duration_minutes,
                            "distance_km": item.distance_km,
                            "average_heart_rate_bpm": item.average_heart_rate_bpm,
                            "heart_rate_zone": item.heart_rate_zone,
                            "set_kind": item.set_kind,
                            "planned_role": item.planned_role,
                        }
                        for item in completed
                    ],
                }
            )
        )
    return WorkoutCopyResponse(
        title=workout.title,
        scheduled_date=workout.scheduled_date,
        completed_at=workout.completed_at,
        exercises=exercises,
    )
