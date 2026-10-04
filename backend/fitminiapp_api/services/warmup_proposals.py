from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import today_for_user
from fitminiapp_api.models.program import (
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
    WorkoutSetMutation,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.workout import (
    WarmupProposalApplyRequest,
    WarmupProposalPreviewRequest,
    WarmupProposalRow,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.workout_metrics import workout_exercise_metric_type

RULESET_VERSION = "warmup-proposal-v1"
MAX_ROWS = 5
MIN_WORKING_WEIGHT_KG = 20.0
DEFAULT_REPS = (8, 5, 3)


class WarmupProposalError(ValueError):
    def __init__(
        self,
        detail: str,
        *,
        status_code: int = 409,
        code: str = "warmup_proposal_invalid",
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.code = code


def _digest(document: object) -> str:
    encoded = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _round_to_half(value: float) -> float:
    return math.floor(value * 2 + 0.5) / 2


def _is_half_increment(value: float) -> bool:
    return math.isclose(value * 2, round(value * 2), abs_tol=1e-9)


def _warmup_weights(working_weight_kg: float) -> list[float]:
    if working_weight_kg <= MIN_WORKING_WEIGHT_KG:
        return []
    weights: list[float] = []
    for ratio in (0.4, 0.6, 0.75):
        weight = _round_to_half(working_weight_kg * ratio)
        if weight < MIN_WORKING_WEIGHT_KG or weight in weights:
            continue
        weights.append(weight)
    return weights


def _default_rows(working_weight_kg: float) -> list[dict[str, float | int]]:
    return [
        {"weight_kg": weight, "reps": DEFAULT_REPS[index]}
        for index, weight in enumerate(_warmup_weights(working_weight_kg))
    ]


def _validate_weight(value: float, *, field: str) -> None:
    if not math.isfinite(value) or value <= 0 or value > 1000:
        raise WarmupProposalError(
            f"{field} должен быть от 0,5 до 1000 кг",
            status_code=422,
            code="warmup_value_invalid",
        )
    if not _is_half_increment(value):
        raise WarmupProposalError(
            f"{field} указывайте с шагом 0,5 кг",
            status_code=422,
            code="warmup_value_invalid",
        )


def _validate_working_weight(value: float) -> None:
    _validate_weight(value, field="Рабочий вес")


def _normalize_rows(
    rows: list[WarmupProposalRow],
    *,
    working_weight_kg: float,
) -> list[dict[str, float | int]]:
    if not rows or len(rows) > MAX_ROWS:
        raise WarmupProposalError(
            f"Добавьте от одного до {MAX_ROWS} разминочных подходов",
            status_code=422,
            code="warmup_rows_invalid",
        )
    normalized: list[dict[str, float | int]] = []
    for row in rows:
        _validate_weight(row.weight_kg, field="Вес разминки")
        if row.weight_kg > working_weight_kg:
            raise WarmupProposalError(
                "Вес разминки не может быть выше рабочего веса",
                status_code=422,
                code="warmup_rows_invalid",
            )
        normalized.append(
            {
                "weight_kg": _round_to_half(row.weight_kg),
                "reps": row.reps,
            }
        )
    return normalized


def _validate_active_workout(workout: UserWorkout, current_user: User) -> None:
    if workout.scheduled_date != today_for_user(current_user):
        raise WarmupProposalError(
            "Разминку можно добавить только в сегодняшнюю тренировку",
            code="warmup_workout_stale",
        )
    if workout.status != "in_progress":
        raise WarmupProposalError(
            "Разминку можно добавить только во время тренировки",
            code="warmup_workout_not_active",
        )
    if not workout.user_program.is_active:
        raise WarmupProposalError("Программа сейчас неактивна", code="warmup_workout_not_active")


def _find_target(workout: UserWorkout, workout_exercise_id: int) -> UserWorkoutExercise:
    target = next((item for item in workout.exercises if item.id == workout_exercise_id), None)
    if target is None:
        raise WarmupProposalError(
            "Упражнение не входит в эту тренировку",
            status_code=404,
            code="warmup_target_not_found",
        )
    if workout_exercise_metric_type(target) != "strength":
        raise WarmupProposalError(
            "Разминочное предложение доступно только для силовых упражнений",
            code="warmup_metric_unsupported",
        )
    return target


def _find_target_set(target: UserWorkoutExercise, target_set_id: int) -> UserWorkoutSet:
    target_set = next((item for item in target.sets if item.id == target_set_id), None)
    if target_set is None:
        raise WarmupProposalError(
            "Целевой подход больше не входит в упражнение",
            status_code=409,
            code="warmup_target_stale",
        )
    if target_set.set_kind == "warmup" or target_set.planned_role == "warmup":
        raise WarmupProposalError(
            "Для уже добавленной разминки новое предложение не нужно",
            code="warmup_already_present",
        )
    return target_set


def _has_execution_evidence(workout_set: UserWorkoutSet) -> bool:
    return bool(
        workout_set.is_completed
        or workout_set.actual_reps is not None
        or workout_set.actual_weight is not None
        or workout_set.duration_minutes is not None
        or workout_set.distance_km is not None
        or workout_set.average_heart_rate_bpm is not None
        or workout_set.heart_rate_zone is not None
        or workout_set.rir is not None
        or workout_set.reached_failure is not None
    )


def _ensure_target_unstarted(target: UserWorkoutExercise) -> None:
    if any(_has_execution_evidence(item) for item in target.sets):
        raise WarmupProposalError(
            "Разминку нельзя добавить: в этом упражнении уже есть фактические данные",
            code="warmup_target_started",
        )
    if any(item.set_kind == "warmup" or item.planned_role == "warmup" for item in target.sets):
        raise WarmupProposalError(
            "Разминочные подходы для этого упражнения уже добавлены",
            code="warmup_already_present",
        )


def _state_token(workout: UserWorkout, target: UserWorkoutExercise) -> str:
    return _digest(
        {
            "workout_id": workout.id,
            "status": workout.status,
            "scheduled_date": workout.scheduled_date.isoformat(),
            "workout_exercise_id": target.id,
            "exercise_id": target.exercise_id,
            "prescribed_sets": target.prescribed_sets,
            "prescribed_reps": target.prescribed_reps,
            "sets": [
                {
                    "id": item.id,
                    "set_number": item.set_number,
                    "version": item.version,
                    "actual_reps": item.actual_reps,
                    "actual_weight": item.actual_weight,
                    "duration_minutes": item.duration_minutes,
                    "distance_km": item.distance_km,
                    "average_heart_rate_bpm": item.average_heart_rate_bpm,
                    "heart_rate_zone": item.heart_rate_zone,
                    "rir": item.rir,
                    "set_kind": item.set_kind,
                    "reached_failure": item.reached_failure,
                    "planned_role": item.planned_role,
                    "is_completed": item.is_completed,
                }
                for item in sorted(target.sets, key=lambda row: (row.set_number, row.id))
            ],
        }
    )


def _proposal_token(
    *,
    state_token: str,
    workout_exercise_id: int,
    target_set_id: int,
    working_weight_kg: float,
    rows: list[dict[str, float | int]],
) -> str:
    return _digest(
        {
            "ruleset_version": RULESET_VERSION,
            "state_token": state_token,
            "workout_exercise_id": workout_exercise_id,
            "target_set_id": target_set_id,
            "working_weight_kg": working_weight_kg,
            "rows": rows,
        }
    )


def _request_fingerprint(document: object) -> str:
    return _digest(document)


def _operation_ids(mutation_id: str, row_count: int) -> list[str]:
    return [
        _digest({"ruleset_version": RULESET_VERSION, "mutation_id": mutation_id, "row": index})
        for index in range(row_count)
    ]


def _warmup_row_changes(
    *,
    workout_id: int,
    workout_exercise_id: int,
    working_weight_kg: float,
    row: dict[str, float | int],
    row_index: int,
) -> dict[str, Any]:
    return {
        "workout_id": workout_id,
        "workout_exercise_id": workout_exercise_id,
        "working_weight_kg": working_weight_kg,
        "row_index": row_index,
        "actual_reps": row["reps"],
        "actual_weight": row["weight_kg"],
        "set_kind": "warmup",
        "planned_role": "warmup",
        "reached_failure": None,
        "is_completed": False,
    }


def _find_replayed_rows(
    db: Session,
    *,
    workout: UserWorkout,
    target: UserWorkoutExercise,
    operation_ids: list[str],
    expected_fingerprints: list[str],
) -> list[UserWorkoutSet] | None:
    operations = (
        db.query(WorkoutSetMutation, UserWorkoutSet)
        .join(UserWorkoutSet, UserWorkoutSet.id == WorkoutSetMutation.workout_set_id)
        .join(UserWorkoutExercise, UserWorkoutExercise.id == UserWorkoutSet.workout_exercise_id)
        .join(UserWorkout, UserWorkout.id == UserWorkoutExercise.workout_id)
        .filter(WorkoutSetMutation.mutation_id.in_(operation_ids))
        .all()
    )
    if not operations:
        return None
    by_operation = {operation.mutation_id: (operation, row) for operation, row in operations}
    if set(by_operation) != set(operation_ids) or len(operations) != len(operation_ids):
        raise WarmupProposalError(
            "Это изменение уже выполняется частично. Повторите предложение заново.",
            code="warmup_idempotency_conflict",
        )
    result: list[UserWorkoutSet] = []
    for operation_id, expected_fingerprint in zip(
        operation_ids, expected_fingerprints, strict=True
    ):
        operation, row = by_operation[operation_id]
        if (
            row.workout_exercise_id != target.id
            or row.workout_exercise.workout_id != workout.id
            or operation.request_fingerprint != expected_fingerprint
        ):
            raise WarmupProposalError(
                "Этот идентификатор уже использован для другого изменения",
                code="warmup_idempotency_conflict",
            )
        result.append(row)
    return result


def build_warmup_proposal(
    db: Session,
    current_user: User,
    workout: UserWorkout,
    workout_exercise_id: int,
    payload: WarmupProposalPreviewRequest,
) -> dict[str, Any]:
    _validate_active_workout(workout, current_user)
    target = _find_target(workout, workout_exercise_id)
    _find_target_set(target, payload.target_set_id)
    _ensure_target_unstarted(target)
    _validate_working_weight(payload.working_weight_kg)
    rows = _default_rows(payload.working_weight_kg)
    if not rows:
        return {
            "status": "unavailable",
            "workout_id": workout.id,
            "workout_exercise_id": target.id,
            "ruleset_version": RULESET_VERSION,
            "working_weight_kg": payload.working_weight_kg,
            "rows": [],
            "max_rows": MAX_ROWS,
            "state_token": None,
            "proposal_token": None,
            "message": "Для рабочего веса больше 20 кг появится понятное предложение разминки.",
        }
    state_token = _state_token(workout, target)
    return {
        "status": "proposal",
        "workout_id": workout.id,
        "workout_exercise_id": target.id,
        "ruleset_version": RULESET_VERSION,
        "working_weight_kg": payload.working_weight_kg,
        "rows": rows,
        "max_rows": MAX_ROWS,
        "state_token": state_token,
        "proposal_token": _proposal_token(
            state_token=state_token,
            workout_exercise_id=target.id,
            target_set_id=payload.target_set_id,
            working_weight_kg=payload.working_weight_kg,
            rows=rows,
        ),
        "message": (
            "Предложение рассчитано от рабочего веса: 40%, 60% и 75% с округлением до 0,5 кг. "
            "Измените его перед добавлением, если нужно."
        ),
    }


def apply_warmup_proposal(
    db: Session,
    current_user: User,
    workout: UserWorkout,
    workout_exercise_id: int,
    payload: WarmupProposalApplyRequest,
) -> dict[str, Any]:
    _validate_working_weight(payload.working_weight_kg)
    rows = _normalize_rows(payload.rows, working_weight_kg=payload.working_weight_kg)
    operation_ids = _operation_ids(payload.mutation_id, len(rows))
    expected_fingerprints = [
        _request_fingerprint(
            _warmup_row_changes(
                workout_id=workout.id,
                workout_exercise_id=workout_exercise_id,
                working_weight_kg=payload.working_weight_kg,
                row=row,
                row_index=index,
            )
        )
        for index, row in enumerate(rows)
    ]

    target = _find_target(workout, workout_exercise_id)
    replayed = _find_replayed_rows(
        db,
        workout=workout,
        target=target,
        operation_ids=operation_ids,
        expected_fingerprints=expected_fingerprints,
    )
    if replayed is not None:
        return {
            "workout_id": workout.id,
            "workout_exercise_id": target.id,
            "ruleset_version": RULESET_VERSION,
            "idempotent": True,
            "materialized_set_ids": [row.id for row in replayed],
        }

    _validate_active_workout(workout, current_user)
    target_set = _find_target_set(target, payload.target_set_id)
    _ensure_target_unstarted(target)
    current_state_token = _state_token(workout, target)
    if current_state_token != payload.state_token:
        raise WarmupProposalError(
            "Тренировка изменилась после предложения. Сформируйте разминку заново.",
            code="warmup_stale",
        )
    default_rows = _default_rows(payload.working_weight_kg)
    expected_proposal_token = _proposal_token(
        state_token=current_state_token,
        workout_exercise_id=target.id,
        target_set_id=target_set.id,
        working_weight_kg=payload.working_weight_kg,
        rows=default_rows,
    )
    if expected_proposal_token != payload.proposal_token:
        raise WarmupProposalError(
            "Предложение разминки больше недействительно. Сформируйте его заново.",
            code="warmup_stale",
        )

    last_set_number = max((item.set_number for item in target.sets), default=0)
    materialized: list[UserWorkoutSet] = []
    for index, row in enumerate(rows):
        materialized_row = UserWorkoutSet(
            workout_exercise_id=target.id,
            set_number=last_set_number + index + 1,
            actual_reps=int(row["reps"]),
            actual_weight=float(row["weight_kg"]),
            set_kind="warmup",
            reached_failure=None,
            planned_role="warmup",
            is_completed=False,
            version=1,
        )
        db.add(materialized_row)
        materialized.append(materialized_row)
    db.flush()
    for _index, (row, operation_id, fingerprint) in enumerate(
        zip(materialized, operation_ids, expected_fingerprints, strict=True)
    ):
        db.add(
            WorkoutSetMutation(
                workout_set_id=row.id,
                mutation_id=operation_id,
                request_fingerprint=fingerprint,
                applied_version=row.version,
            )
        )
    record_audit_event(
        db,
        actor_user_id=current_user.id,
        target_user_id=current_user.id,
        action="workout.warmup_proposal_applied",
        resource_type="user_workout",
        resource_id=workout.id,
        details={
            "outcome": "applied",
            "ruleset_version": RULESET_VERSION,
            "workout_exercise_id": target.id,
            "row_count": len(materialized),
        },
    )
    db.commit()
    return {
        "workout_id": workout.id,
        "workout_exercise_id": target.id,
        "ruleset_version": RULESET_VERSION,
        "idempotent": False,
        "materialized_set_ids": [row.id for row in materialized],
    }
