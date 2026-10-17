"""Owner-scoped durable rest session API. Plan remains on the exercise prescription."""

import hashlib
import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from fitminiapp_api.api.dependencies.auth import require_user
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.program import (
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.models.workout_rest import WorkoutRestAction, WorkoutRestSession
from fitminiapp_api.services.workout_recovery import recovery_user_local_naive_to_utc_naive
from fitminiapp_api.schemas.workout_rest import (
    RestActionRequest,
    RestSessionResponse,
    RestStartRequest,
)

router = APIRouter()


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        # ISO timestamps must specify an offset so browser-local times cannot be ambiguous.
        raise HTTPException(status_code=422, detail="Время должно содержать часовой пояс")
    return value.astimezone(UTC).replace(tzinfo=None)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _as_response(row: WorkoutRestSession) -> RestSessionResponse:
    return RestSessionResponse(
        id=row.id,
        workout_id=row.workout_id,
        source_set_id=row.source_set_id,
        started_at=row.started_at.replace(tzinfo=UTC),
        ended_at=row.ended_at.replace(tzinfo=UTC) if row.ended_at else None,
        planned_seconds=row.planned_seconds,
        adjusted_seconds=row.adjusted_seconds,
        measured_seconds=row.measured_seconds,
        status=row.status,
        source=row.source,
        quality=row.quality,
        version=row.version,
    )


def _owned_workout(db: Session, user_id: int, workout_id: int) -> UserWorkout:
    workout = (
        db.query(UserWorkout)
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .filter(UserWorkout.id == workout_id, UserProgram.user_id == user_id)
        .first()
    )
    if workout is None:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    return workout


@router.get("/{workout_id}/rest-sessions", response_model=list[RestSessionResponse])
def list_rest_sessions(
    workout_id: int,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    _owned_workout(db, current_user.id, workout_id)
    rows = (
        db.query(WorkoutRestSession)
        .filter(
            WorkoutRestSession.workout_id == workout_id,
            WorkoutRestSession.user_id == current_user.id,
        )
        .order_by(WorkoutRestSession.started_at.asc(), WorkoutRestSession.id.asc())
        .all()
    )
    return [_as_response(row) for row in rows]


@router.post("/{workout_id}/rest-sessions", response_model=RestSessionResponse)
def start_rest_session(
    workout_id: int,
    payload: RestStartRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    workout = _owned_workout(db, current_user.id, workout_id)
    candidate = (
        db.query(UserWorkoutSet, UserWorkoutExercise)
        .join(UserWorkoutExercise, UserWorkoutExercise.id == UserWorkoutSet.workout_exercise_id)
        .filter(
            UserWorkoutSet.id == payload.source_set_id,
            UserWorkoutExercise.workout_id == workout_id,
        )
        .with_for_update(of=UserWorkoutSet)
        .first()
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Подход не найден")
    set_row, exercise = candidate
    existing = (
        db.query(WorkoutRestSession).filter(WorkoutRestSession.source_set_id == set_row.id).first()
    )
    if existing is not None:
        return _as_response(existing)
    started_at = _utc_naive(payload.started_at)
    if not set_row.is_completed or workout.status not in ("in_progress", "completed"):
        raise HTTPException(status_code=409, detail="Сначала завершите подход")
    # Offline completion and rest may reach the server after the workout finish.
    # Preserve accepted, owner-scoped measurements that began before its completion.
    if (
        workout.status == "completed"
        and workout.completed_at is not None
        and started_at
        > recovery_user_local_naive_to_utc_naive(workout.completed_at, current_user)
        + timedelta(minutes=1)
    ):
        raise HTTPException(status_code=409, detail="Отдых начался после окончания тренировки")
    if (
        (set_row.set_kind or "working") != "working"
        or set_row.planned_role in ("warmup", "activation")
        or exercise.metric_type == "cardio"
        or exercise.rest_seconds <= 0
    ):
        raise HTTPException(status_code=422, detail="Отдых для этого подхода не предусмотрен")
    now = _now()
    # Offline workouts may sync after several days; do not strand their rest journals.
    if started_at > now + timedelta(minutes=1) or started_at < now - timedelta(days=90):
        raise HTTPException(status_code=422, detail="Время начала отдыха вне допустимого диапазона")
    row = WorkoutRestSession(
        user_id=current_user.id,
        workout_id=workout_id,
        source_set_id=set_row.id,
        started_at=started_at,
        planned_seconds=exercise.rest_seconds,
        adjusted_seconds=exercise.rest_seconds,
        status="running",
        quality="normal",
        version=1,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _as_response(row)


@router.post("/rest-sessions/{session_id}/actions", response_model=RestSessionResponse)
def mutate_rest_session(
    session_id: int,
    payload: RestActionRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(WorkoutRestSession)
        .filter(WorkoutRestSession.id == session_id, WorkoutRestSession.user_id == current_user.id)
        .with_for_update()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Отдых не найден")
    _owned_workout(db, current_user.id, row.workout_id)
    fingerprint = hashlib.sha256(
        json.dumps(
            payload.model_dump(mode="json", exclude={"mutation_id"}), sort_keys=True
        ).encode()
    ).hexdigest()
    replay = (
        db.query(WorkoutRestAction)
        .filter(
            WorkoutRestAction.session_id == row.id,
            WorkoutRestAction.mutation_id == payload.mutation_id,
        )
        .first()
    )
    if replay is not None:
        if replay.fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="Идентификатор операции уже использован")
        return _as_response(row)
    if row.version != payload.expected_version or row.status != "running":
        raise HTTPException(status_code=409, detail="Состояние отдыха изменилось")
    if payload.action in ("add30", "add60"):
        if (
            payload.ended_at is not None
            or payload.corrected
            or payload.corrected_seconds is not None
        ):
            raise HTTPException(status_code=422, detail="Время окончания здесь не требуется")
        applied_at = _utc_naive(payload.occurred_at) if payload.occurred_at else _now()
        if applied_at < row.started_at or applied_at > _now() + timedelta(minutes=1):
            raise HTTPException(status_code=422, detail="Недопустимое время корректировки")
        elapsed = max(0, int((applied_at - row.started_at).total_seconds()))
        row.adjusted_seconds = max(row.adjusted_seconds, elapsed) + (
            30 if payload.action == "add30" else 60
        )
    else:
        if payload.action == "complete":
            if payload.corrected != (payload.corrected_seconds is not None):
                raise HTTPException(
                    status_code=422, detail="Для исправления укажите фактическую длительность"
                )
            if payload.ended_at is None:
                raise HTTPException(status_code=422, detail="Укажите время остановки")
            ended = _utc_naive(payload.ended_at)
            if ended > _now() + timedelta(minutes=1):
                raise HTTPException(status_code=422, detail="Недопустимое время окончания")
            if payload.corrected:
                # The owner explicitly reports the duration after returning from background.
                # Do not derive a fictitious interval from wall clock time while absent.
                row.measured_seconds = payload.corrected_seconds
            else:
                if ended < row.started_at:
                    raise HTTPException(status_code=422, detail="Недопустимое время окончания")
                row.measured_seconds = max(0, int((ended - row.started_at).total_seconds()))
            row.ended_at = ended
            row.status = "completed"
            row.source = "USER_CORRECTED" if payload.corrected else "USER_CONFIRMED"
            row.quality = "normal"
        else:
            if (
                payload.ended_at is not None
                or payload.corrected
                or payload.corrected_seconds is not None
            ):
                raise HTTPException(status_code=422, detail="Конечное время не требуется")
            row.ended_at = _now()
            row.status = {"skip": "skipped", "interrupt": "interrupted", "unknown": "unknown"}[
                payload.action
            ]
            row.measured_seconds = None
            row.source = "SYSTEM_RECOVERY" if payload.action == "unknown" else None
            row.quality = "unknown" if payload.action == "unknown" else "normal"
    row.version += 1
    db.add(
        WorkoutRestAction(
            session_id=row.id,
            mutation_id=payload.mutation_id,
            fingerprint=fingerprint,
            applied_version=row.version,
        )
    )
    db.commit()
    db.refresh(row)
    return _as_response(row)
