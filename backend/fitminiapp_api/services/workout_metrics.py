from __future__ import annotations

from dataclasses import dataclass

from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.program import UserWorkoutExercise
from fitminiapp_api.services.program_common import ProgramError


def exercise_metric_type(exercise: Exercise | None) -> str:
    """Return the safe legacy fallback without guessing from a title at runtime."""

    return "cardio" if exercise and exercise.metric_type == "cardio" else "strength"


def workout_exercise_metric_type(exercise: UserWorkoutExercise) -> str:
    if exercise.metric_type in {"strength", "cardio"}:
        return exercise.metric_type
    return exercise_metric_type(exercise.exercise)


@dataclass(frozen=True)
class ExercisePrescription:
    prescribed_sets: int
    prescribed_reps: str
    prescribed_duration_minutes: int | None
    rest_seconds: int


def normalize_exercise_prescription(
    exercise: Exercise,
    *,
    prescribed_sets: int | None,
    prescribed_reps: str | None,
    prescribed_duration_minutes: int | None,
    rest_seconds: int,
) -> ExercisePrescription:
    metric_type = exercise_metric_type(exercise)
    if metric_type == "cardio":
        if prescribed_duration_minutes is None:
            raise ProgramError("Cardio duration is required")
        return ExercisePrescription(
            prescribed_sets=1,
            prescribed_reps="",
            prescribed_duration_minutes=prescribed_duration_minutes,
            rest_seconds=0,
        )

    if prescribed_sets is None or not prescribed_reps:
        raise ProgramError("Strength sets and repetitions are required")
    if rest_seconds < 15:
        raise ProgramError("Strength rest must be at least 15 seconds")
    if prescribed_duration_minutes is not None:
        raise ProgramError("Strength exercise does not use cardio duration")
    return ExercisePrescription(
        prescribed_sets=prescribed_sets,
        prescribed_reps=prescribed_reps,
        prescribed_duration_minutes=None,
        rest_seconds=rest_seconds,
    )


def validate_workout_set_changes(
    metric_type: str,
    changes: dict,
    *,
    current_duration_minutes: int | None = None,
) -> None:
    strength_fields = {
        "actual_reps",
        "actual_weight",
        "rir",
        "set_kind",
        "reached_failure",
        "execution_mode",
        "first_side",
        "sides",
    }
    cardio_fields = {
        "duration_minutes",
        "distance_km",
        "average_heart_rate_bpm",
        "heart_rate_zone",
    }
    if metric_type == "cardio":
        if any(changes.get(field) is not None for field in strength_fields):
            raise ValueError("Кардио не использует вес, повторы и параметры силового подхода")
        duration = changes.get("duration_minutes", current_duration_minutes)
        if changes.get("is_completed") and duration is None:
            raise ValueError("Укажите длительность кардио")
    elif any(changes.get(field) is not None for field in cardio_fields):
        raise ValueError("Силовое упражнение не использует кардио-показатели")
