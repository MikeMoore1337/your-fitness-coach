from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import get_timezone, get_user_timezone_name
from fitminiapp_api.models.program import (
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.services.workouts import working_volume_set_filter


def build_activity_heatmap(
    db: Session, user: User, *, now: datetime | None = None, year: int | None = None
) -> dict:
    timezone_name = get_user_timezone_name(user)
    timezone = get_timezone(timezone_name)
    today = (now or datetime.now(UTC)).astimezone(timezone).date()
    if year is not None and not 1970 <= year <= today.year:
        raise ValueError("Год должен быть между 1970 и текущим годом")
    start = date(year, 1, 1) if year is not None else today - timedelta(days=364)
    end = date(year, 12, 31) if year is not None else today
    start_utc = datetime.combine(start, time.min, timezone).astimezone(UTC).replace(tzinfo=None)
    end_utc = (
        datetime.combine(min(end, today) + timedelta(days=1), time.min, timezone)
        .astimezone(UTC)
        .replace(tzinfo=None)
    )
    owned = (UserProgram.user_id == user.id, UserWorkout.status == "completed")
    undated = (
        db.query(func.count(UserWorkout.id))
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .filter(*owned, UserWorkout.completed_at_utc.is_(None))
        .scalar()
        or 0
    )
    sets = (
        db.query(
            UserWorkoutExercise.workout_id.label("workout_id"),
            func.count(UserWorkoutSet.id).label("sets"),
        )
        .join(UserWorkoutSet, UserWorkoutSet.workout_exercise_id == UserWorkoutExercise.id)
        .join(UserWorkout, UserWorkout.id == UserWorkoutExercise.workout_id)
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .filter(
            *owned,
            UserWorkout.completed_at_utc >= start_utc,
            UserWorkout.completed_at_utc < end_utc,
            UserWorkoutSet.is_completed.is_(True),
            working_volume_set_filter(),
        )
        .group_by(UserWorkoutExercise.workout_id)
        .subquery()
    )
    rows = (
        db.query(UserWorkout.completed_at_utc, func.coalesce(sets.c.sets, 0))
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .outerjoin(sets, sets.c.workout_id == UserWorkout.id)
        .filter(
            *owned,
            UserWorkout.completed_at_utc >= start_utc,
            UserWorkout.completed_at_utc < end_utc,
        )
        .all()
    )
    totals: defaultdict[date, list[int]] = defaultdict(lambda: [0, 0])
    for completed_at, working_sets in rows:
        day = completed_at.replace(tzinfo=UTC).astimezone(timezone).date()
        totals[day][0] += 1
        totals[day][1] += working_sets
    days = []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        counts = totals.get(day)
        unavailable = bool(undated) or day > today
        days.append(
            {
                "date": day,
                "is_future": day > today,
                "completed_workouts": counts[0] if counts else (None if unavailable else 0),
                "working_sets": counts[1] if counts else (None if unavailable else 0),
            }
        )
    return {
        "timezone": timezone_name,
        "start_date": start,
        "end_date": end,
        "history_complete": not bool(undated),
        "undated_workouts": undated,
        "days": days,
    }
