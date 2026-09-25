import hashlib
import json

from sqlalchemy.orm import Session

from fitminiapp_api.models.program import UserWorkout, UserWorkoutSet, WorkoutSetMutation


class WorkoutSetSyncError(Exception):
    def __init__(self, status_code: int, detail: str | dict):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


def serialize_workout_set(set_row: UserWorkoutSet) -> dict:
    return {
        "id": set_row.id,
        "set_number": set_row.set_number,
        "actual_reps": set_row.actual_reps,
        "actual_weight": set_row.actual_weight,
        "duration_minutes": set_row.duration_minutes,
        "distance_km": set_row.distance_km,
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
    canonical = json.dumps(changes, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
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
) -> UserWorkoutSet:
    if workout.status != "in_progress":
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
