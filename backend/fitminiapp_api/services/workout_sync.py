import hashlib
import json
from decimal import Decimal

from sqlalchemy.orm import Session

from fitminiapp_api.models.program import (
    UserWorkout,
    UserWorkoutSet,
    UserWorkoutSetSide,
    WorkoutSetMutation,
)
from fitminiapp_api.services.workout_sides import SIDE_MODES, serialize_sides, side_facts_present


class WorkoutSetSyncError(Exception):
    def __init__(self, status_code: int, detail: str | dict):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


def serialize_workout_set(set_row: UserWorkoutSet) -> dict:
    return {
        "id": set_row.id,
        "set_number": set_row.set_number,
        "execution_mode": set_row.execution_mode,
        "first_side": set_row.first_side,
        "sides": serialize_sides(set_row),
        "actual_reps": set_row.actual_reps,
        "actual_weight": (
            float(set_row.actual_weight) if set_row.actual_weight is not None else None
        ),
        "duration_minutes": set_row.duration_minutes,
        "distance_km": float(set_row.distance_km) if set_row.distance_km is not None else None,
        "average_heart_rate_bpm": set_row.average_heart_rate_bpm,
        "heart_rate_zone": set_row.heart_rate_zone,
        "rir": set_row.rir,
        "set_kind": set_row.set_kind,
        "reached_failure": set_row.reached_failure,
        "planned_role": set_row.planned_role,
        "planned_group_id": set_row.planned_group_id,
        "planned_group_kind": set_row.planned_group_kind,
        "planned_position": set_row.planned_position,
        "planned_round": set_row.planned_round,
        "is_completed": set_row.is_completed,
        "version": set_row.version,
    }


def _request_fingerprint(changes: dict) -> str:
    def decimal_value(value):
        if isinstance(value, Decimal):
            return float(value)
        raise TypeError(f"Unsupported fingerprint value: {type(value).__name__}")

    canonical = json.dumps(
        changes,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=decimal_value,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def replayed_workout_set(
    db: Session,
    set_row: UserWorkoutSet,
    mutation_id: str | None,
    changes: dict,
) -> UserWorkoutSet | None:
    if mutation_id is None:
        return None
    operation = (
        db.query(WorkoutSetMutation)
        .filter(
            WorkoutSetMutation.workout_set_id == set_row.id,
            WorkoutSetMutation.mutation_id == mutation_id,
        )
        .one_or_none()
    )
    if operation is None:
        return None
    if operation.request_fingerprint != _request_fingerprint(changes):
        raise WorkoutSetSyncError(
            409,
            {
                "code": "workout_set_idempotency_conflict",
                "message": "Этот идентификатор изменения уже использован с другими данными",
                "current": serialize_workout_set(set_row),
            },
        )
    return set_row


def apply_workout_set_update(
    db: Session,
    set_row: UserWorkoutSet,
    workout: UserWorkout,
    changes: dict,
    *,
    expected_version: int | None,
    mutation_id: str | None,
    allow_planned: bool = False,
) -> UserWorkoutSet:
    if workout.status != "in_progress" and not (allow_planned and workout.status == "planned"):
        raise WorkoutSetSyncError(
            409,
            {
                "code": "workout_not_active",
                "message": "Подходы можно изменять только во время тренировки",
                "current": serialize_workout_set(set_row),
            },
        )
    if expected_version is not None and expected_version != set_row.version:
        raise WorkoutSetSyncError(
            409,
            {
                "code": "workout_set_version_conflict",
                "message": "Подход изменён в другой вкладке. Локальное изменение можно повторить.",
                "current": serialize_workout_set(set_row),
            },
        )

    previous_mode = set_row.execution_mode
    next_mode = changes.get("execution_mode", previous_mode)
    if previous_mode in SIDE_MODES and (
        "execution_mode" not in changes
        or (next_mode in SIDE_MODES and changes.get("sides") is None)
    ):
        raise WorkoutSetSyncError(
            409,
            {
                "code": "workout_set_side_aware_required",
                "message": "Обновите приложение, чтобы изменить подход со сторонами",
                "current": serialize_workout_set(set_row),
            },
        )

    if (previous_mode in SIDE_MODES or next_mode in SIDE_MODES) and (
        expected_version is None or mutation_id is None
    ):
        raise WorkoutSetSyncError(422, "Для изменения сторон нужны версия и идентификатор операции")

    if next_mode in SIDE_MODES:
        if changes.get("execution_mode") not in SIDE_MODES or changes.get("sides") is None:
            raise WorkoutSetSyncError(422, "Укажите обе стороны и способ выполнения")
        if any(
            changes.get(field) is not None
            for field in ("actual_reps", "actual_weight", "rir", "reached_failure")
        ):
            raise WorkoutSetSyncError(422, "Общие значения нельзя смешивать со сторонами")
        sides = changes["sides"]
        completed = changes.get("is_completed")
        if (set_row.is_completed if completed is None else completed) and not all(
            sides.get(side) is not None and sides[side].get("is_completed") is True
            for side in ("left", "right")
        ):
            raise WorkoutSetSyncError(422, "Подтвердите обе стороны перед завершением подхода")
    elif changes.get("sides") is not None:
        raise WorkoutSetSyncError(422, "Стороны доступны только при раздельном выполнении")

    first_side = changes.get("first_side", set_row.first_side)
    if first_side is not None and next_mode != "alternating":
        if "first_side" in changes:
            raise WorkoutSetSyncError(422, "Начальная сторона доступна только при чередовании")
        first_side = None

    if (
        next_mode != previous_mode
        and (
            side_facts_present(set_row)
            or any(
                getattr(set_row, field) is not None
                for field in ("actual_reps", "actual_weight", "rir", "reached_failure")
            )
            or set_row.is_completed
        )
        and not changes.get("confirm_mode_change")
    ):
        raise WorkoutSetSyncError(
            409,
            {
                "code": "workout_set_mode_change_confirmation",
                "message": "Подтвердите изменение способа выполнения: результаты могут измениться",
                "current": serialize_workout_set(set_row),
            },
        )

    applied = False
    if next_mode in SIDE_MODES:
        existing = {item.side: item for item in set_row.side_results}
        for side in ("left", "right"):
            value = sides[side]
            item = existing.get(side)
            if value is None:
                if item is not None:
                    set_row.side_results.remove(item)
                continue
            if item is None:
                item = UserWorkoutSetSide(side=side)
                set_row.side_results.append(item)
            for field in ("actual_reps", "actual_weight", "rir", "reached_failure"):
                setattr(item, field, value.get(field))
            item.is_completed = value.get("is_completed", False)
        for field in ("actual_reps", "actual_weight", "rir", "reached_failure"):
            setattr(set_row, field, None)
        applied = True
    elif previous_mode in SIDE_MODES and next_mode != previous_mode:
        set_row.side_results.clear()
        applied = True

    if "execution_mode" in changes:
        set_row.execution_mode = next_mode
        applied = True
    if "first_side" in changes or first_side != set_row.first_side:
        set_row.first_side = first_side
        applied = True

    for field in (
        "actual_reps",
        "actual_weight",
        "duration_minutes",
        "distance_km",
        "average_heart_rate_bpm",
        "heart_rate_zone",
        "rir",
        "set_kind",
        "reached_failure",
        "is_completed",
    ):
        if field in changes and (field != "is_completed" or changes[field] is not None):
            setattr(set_row, field, changes[field])
            applied = True

    if not applied:
        raise WorkoutSetSyncError(422, "Не указаны изменения подхода")

    set_row.version += 1
    if mutation_id is not None:
        db.add(
            WorkoutSetMutation(
                workout_set_id=set_row.id,
                mutation_id=mutation_id,
                request_fingerprint=_request_fingerprint(changes),
                applied_version=set_row.version,
            )
        )
    return set_row
