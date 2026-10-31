from __future__ import annotations

from decimal import Decimal

from sqlalchemy import case, func, select

from fitminiapp_api.models.program import UserWorkoutSet, UserWorkoutSetSide

SIDE_MODES = frozenset({"per_side", "alternating"})


def serialize_sides(workout_set: UserWorkoutSet) -> dict | None:
    if workout_set.execution_mode not in SIDE_MODES:
        return None
    return serialize_side_results(workout_set.side_results)


def serialize_side_results(results: list[UserWorkoutSetSide]) -> dict:
    sides: dict[str, dict | None] = {"left": None, "right": None}
    for item in results:
        sides[item.side] = {
            "actual_reps": item.actual_reps,
            "actual_weight": float(item.actual_weight) if item.actual_weight is not None else None,
            "rir": item.rir,
            "reached_failure": item.reached_failure,
            "is_completed": item.is_completed,
        }
    return sides


def side_facts_present(workout_set: UserWorkoutSet) -> bool:
    return workout_set.execution_mode in SIDE_MODES and any(
        item.is_completed
        or item.actual_reps is not None
        or item.actual_weight is not None
        or item.rir is not None
        or item.reached_failure is not None
        for item in workout_set.side_results
    )


def completed_set_reps(workout_set: UserWorkoutSet) -> int | None:
    if workout_set.execution_mode not in SIDE_MODES:
        return workout_set.actual_reps
    sides = workout_set.side_results
    if len(sides) != 2 or any(not side.is_completed or side.actual_reps is None for side in sides):
        return None
    return sum(side.actual_reps for side in sides if side.actual_reps is not None)


def completed_set_has_load(workout_set: UserWorkoutSet) -> bool:
    if workout_set.execution_mode not in SIDE_MODES:
        return workout_set.actual_weight is not None
    return len(workout_set.side_results) == 2 and all(
        side.is_completed and side.actual_weight is not None for side in workout_set.side_results
    )


def completed_set_volume(workout_set: UserWorkoutSet) -> Decimal | None:
    if workout_set.execution_mode not in SIDE_MODES:
        if workout_set.actual_weight is None or workout_set.actual_reps is None:
            return None
        return workout_set.actual_weight * workout_set.actual_reps
    sides = workout_set.side_results
    if len(sides) != 2 or any(
        not side.is_completed or side.actual_weight is None or side.actual_reps is None
        for side in sides
    ):
        return None
    return sum(
        (
            side.actual_weight * side.actual_reps
            for side in sides
            if side.actual_weight is not None and side.actual_reps is not None
        ),
        Decimal(0),
    )


def _side_sum(value, *required):
    rows = select(
        case((func.count(UserWorkoutSetSide.id) == 2, func.sum(value)), else_=None)
    ).where(
        UserWorkoutSetSide.workout_set_id == UserWorkoutSet.id,
        UserWorkoutSetSide.is_completed.is_(True),
        *(column.is_not(None) for column in required),
    )
    return rows.correlate(UserWorkoutSet).scalar_subquery()


def sql_completed_set_reps():
    return case(
        (
            UserWorkoutSet.execution_mode.in_(SIDE_MODES),
            _side_sum(UserWorkoutSetSide.actual_reps, UserWorkoutSetSide.actual_reps),
        ),
        else_=UserWorkoutSet.actual_reps,
    )


def sql_completed_set_volume():
    return case(
        (
            UserWorkoutSet.execution_mode.in_(SIDE_MODES),
            _side_sum(
                UserWorkoutSetSide.actual_reps * UserWorkoutSetSide.actual_weight,
                UserWorkoutSetSide.actual_reps,
                UserWorkoutSetSide.actual_weight,
            ),
        ),
        else_=UserWorkoutSet.actual_reps * UserWorkoutSet.actual_weight,
    )


def sql_side_rir_count():
    return (
        select(func.count(UserWorkoutSetSide.id))
        .where(
            UserWorkoutSetSide.workout_set_id == UserWorkoutSet.id,
            UserWorkoutSetSide.is_completed.is_(True),
            UserWorkoutSetSide.rir.is_not(None),
        )
        .correlate(UserWorkoutSet)
        .scalar_subquery()
    )


def sql_common_rir():
    common_side_rir = (
        select(
            case(
                (
                    func.count(UserWorkoutSetSide.id) == 2,
                    case(
                        (
                            func.min(UserWorkoutSetSide.rir) == func.max(UserWorkoutSetSide.rir),
                            func.min(UserWorkoutSetSide.rir),
                        ),
                        else_=None,
                    ),
                ),
                else_=None,
            )
        )
        .where(
            UserWorkoutSetSide.workout_set_id == UserWorkoutSet.id,
            UserWorkoutSetSide.is_completed.is_(True),
            UserWorkoutSetSide.rir.is_not(None),
        )
        .correlate(UserWorkoutSet)
        .scalar_subquery()
    )
    return case(
        (UserWorkoutSet.execution_mode.in_(SIDE_MODES), common_side_rir),
        else_=UserWorkoutSet.rir,
    )
