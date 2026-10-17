"""Aggregates only rest intervals explicitly confirmed (or corrected) by their owner."""

from statistics import mean, median

from sqlalchemy.orm import Session

from fitminiapp_api.models.program import UserProgram, UserWorkout
from fitminiapp_api.models.workout_rest import WorkoutRestSession


def rest_statistics(db: Session, user_id: int, start_date, end_date) -> dict:
    values = (
        db.query(WorkoutRestSession.measured_seconds, WorkoutRestSession.adjusted_seconds)
        .join(UserWorkout, UserWorkout.id == WorkoutRestSession.workout_id)
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .filter(
            UserProgram.user_id == user_id,
            WorkoutRestSession.user_id == user_id,
            UserWorkout.scheduled_date >= start_date,
            UserWorkout.scheduled_date <= end_date,
            WorkoutRestSession.status == "completed",
            WorkoutRestSession.measured_seconds.isnot(None),
            WorkoutRestSession.source.in_(("USER_CONFIRMED", "USER_CORRECTED")),
            WorkoutRestSession.quality.in_(("normal", "long")),
        )
        .all()
    )
    actual = [measured for measured, _ in values]
    differences = [measured - planned for measured, planned in values]
    return {
        "observation_count": len(actual),
        "mean_seconds": round(mean(actual), 1) if actual else None,
        "median_seconds": round(median(actual), 1) if actual else None,
        "mean_difference_seconds": round(mean(differences), 1) if differences else None,
    }
