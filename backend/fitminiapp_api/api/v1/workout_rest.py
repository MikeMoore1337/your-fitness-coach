"""Owner-scoped durable rest session API. Plan remains on the exercise prescription."""

import hashlib
import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
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
from fitminiapp_api.schemas.workout_rest import (
    RestActionRequest,
    RestSessionResponse,
    RestStartRequest,
    RestRestartRequest,
)
from fitminiapp_api.services.workout_recovery import recovery_user_local_naive_to_utc_naive

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
        start_mutation_id=row.start_mutation_id,
    )


def _owned_workout(
    db: Session, user_id: int, workout_id: int, *, lock: bool = False
) -> UserWorkout:
    query = (
        db.query(UserWorkout)
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .filter(UserWorkout.id == workout_id, UserProgram.user_id == user_id)
    )
    # Global order for rest starts: workout -> set or predecessor -> rest row.
    if lock:
        query = query.with_for_update(of=UserWorkout)
    workout = query.first()
    if workout is None:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    return workout


def _fingerprint(*, started_at: datetime, source_set_id: int, predecessor_id: int | None) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "started_at": started_at.isoformat(),
                "source_set_id": source_set_id,
                "predecessor_id": predecessor_id,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


def _valid_start_time(started_at: datetime) -> None:
    now = _now()
    if started_at > now + timedelta(minutes=1) or started_at < now - timedelta(days=90):
        raise HTTPException(status_code=422, detail="Время начала отдыха вне допустимого диапазона")


def _validate_source_set(set_row: UserWorkoutSet, exercise: UserWorkoutExercise) -> None:
    if (
        (set_row.set_kind or "working") != "working"
        or set_row.planned_role in ("warmup", "activation")
        or exercise.metric_type == "cardio"
        or exercise.rest_seconds <= 0
    ):
        raise HTTPException(status_code=422, detail="Отдых для этого подхода не предусмотрен")


def _commit_rest(db: Session, row: WorkoutRestSession) -> RestSessionResponse:
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Конфликт интервалов отдыха") from None
    db.refresh(row)
    return _as_response(row)


def _replayed_start(
    db: Session, *, workout_id: int, mutation_id: str, fingerprint: str
) -> WorkoutRestSession | None:
    row = (
        db.query(WorkoutRestSession)
        .filter(
            WorkoutRestSession.workout_id == workout_id,
            WorkoutRestSession.start_mutation_id == mutation_id,
        )
        .first()
    )
    if row is not None and row.start_fingerprint != fingerprint:
        raise HTTPException(status_code=409, detail="Идентификатор операции уже использован")
    return row


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
    # Lock the workout first, not just the source set. Starts from different
    # source sets are serialized; the partial DB index independently enforces
    # the invariant for every writer.
    workout = _owned_workout(db, current_user.id, workout_id, lock=True)
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
    started_at = _utc_naive(payload.started_at)
    fingerprint = _fingerprint(
        started_at=started_at, source_set_id=set_row.id, predecessor_id=None
    )
    replay = _replayed_start(
        db, workout_id=workout_id, mutation_id=payload.mutation_id, fingerprint=fingerprint
    )
    if replay is not None:
        return _as_response(replay)
    existing = (
        db.query(WorkoutRestSession)
        .filter(
            WorkoutRestSession.source_set_id == set_row.id,
            WorkoutRestSession.predecessor_id.is_(None),
        )
        .first()
    )
    if existing is not None:
        # Historical v1 journals had no persisted start mutation. Keep the old
        # initial-start contract; manual repeat always uses /restart instead.
        return _as_response(existing)
    if not set_row.is_completed or workout.status not in ("in_progress", "completed"):
        raise HTTPException(status_code=409, detail="Сначала завершите подход")
    if workout.status == "completed" and workout.completed_at is not None:
        completed_utc = recovery_user_local_naive_to_utc_naive(
            workout.completed_at, current_user
        )
        if started_at > completed_utc + timedelta(minutes=1):
            raise HTTPException(status_code=409, detail="Отдых начался после окончания тренировки")
    _validate_source_set(set_row, exercise)
    _valid_start_time(started_at)
    running = (
        db.query(WorkoutRestSession.id)
        .filter(
            WorkoutRestSession.workout_id == workout_id,
            WorkoutRestSession.status == "running",
        )
        .first()
    )
    if running is not None:
        raise HTTPException(status_code=409, detail="Другой отдых уже выполняется")
    return _commit_rest(
        db,
        WorkoutRestSession(
            user_id=current_user.id,
            workout_id=workout_id,
            source_set_id=set_row.id,
            predecessor_id=None,
            start_mutation_id=payload.mutation_id,
            start_fingerprint=fingerprint,
            started_at=started_at,
            planned_seconds=exercise.rest_seconds,
            adjusted_seconds=exercise.rest_seconds,
            status="running",
            quality="normal",
            version=1,
        ),
    )


@router.post("/rest-sessions/{predecessor_id}/restart", response_model=RestSessionResponse)
def restart_rest_session(
    predecessor_id: int,
    payload: RestRestartRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    # Resolve ownership before locking the shared workout. A foreign/unknown
    # predecessor is 404; no client-supplied workout or source identity is trusted.
    candidate = (
        db.query(WorkoutRestSession)
        .filter(
            WorkoutRestSession.id == predecessor_id,
            WorkoutRestSession.user_id == current_user.id,
        )
        .first()
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Предыдущий отдых не найден")
    workout = _owned_workout(db, current_user.id, candidate.workout_id, lock=True)
    predecessor = (
        db.query(WorkoutRestSession)
        .filter(
            WorkoutRestSession.id == predecessor_id,
            WorkoutRestSession.user_id == current_user.id,
            WorkoutRestSession.workout_id == workout.id,
        )
        .with_for_update()
        .first()
    )
    if predecessor is None:
        raise HTTPException(status_code=404, detail="Предыдущий отдых не найден")
    started_at = _utc_naive(payload.started_at)
    fingerprint = _fingerprint(
        started_at=started_at,
        source_set_id=predecessor.source_set_id,
        predecessor_id=predecessor.id,
    )
    replay = _replayed_start(
        db, workout_id=workout.id, mutation_id=payload.mutation_id, fingerprint=fingerprint
    )
    if replay is not None:
        return _as_response(replay)
    if predecessor.status not in ("completed", "skipped"):
        raise HTTPException(status_code=409, detail="Предыдущий отдых ещё не завершён")
    if workout.status != "in_progress":
        raise HTTPException(status_code=409, detail="Тренировка неактивна")
    if predecessor.ended_at is None or started_at < predecessor.ended_at:
        raise HTTPException(status_code=422, detail="Недопустимое начало нового отдыха")
    successor = (
        db.query(WorkoutRestSession.id)
        .filter(WorkoutRestSession.predecessor_id == predecessor.id)
        .first()
    )
    if successor is not None:
        raise HTTPException(status_code=409, detail="Отдых уже был запущен повторно")
    candidate_set = (
        db.query(UserWorkoutSet, UserWorkoutExercise)
        .join(UserWorkoutExercise, UserWorkoutExercise.id == UserWorkoutSet.workout_exercise_id)
        .filter(
            UserWorkoutSet.id == predecessor.source_set_id,
            UserWorkoutExercise.workout_id == workout.id,
        )
        .with_for_update(of=UserWorkoutSet)
        .first()
    )
    if candidate_set is None:
        raise HTTPException(status_code=404, detail="Подход не найден")
    set_row, exercise = candidate_set
    if not set_row.is_completed:
        raise HTTPException(status_code=409, detail="Сначала завершите подход")
    _validate_source_set(set_row, exercise)
    _valid_start_time(started_at)
    if (
        db.query(WorkoutRestSession.id)
        .filter(
            WorkoutRestSession.workout_id == workout.id,
            WorkoutRestSession.status == "running",
        )
        .first()
        is not None
    ):
        raise HTTPException(status_code=409, detail="Другой отдых уже выполняется")
    return _commit_rest(
        db,
        WorkoutRestSession(
            user_id=current_user.id,
            workout_id=workout.id,
            source_set_id=set_row.id,
            predecessor_id=predecessor.id,
            start_mutation_id=payload.mutation_id,
            start_fingerprint=fingerprint,
            started_at=started_at,
            planned_seconds=exercise.rest_seconds,
            adjusted_seconds=exercise.rest_seconds,
            status="running",
            quality="normal",
            version=1,
        ),
    )


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
            if ended < row.started_at:
                raise HTTPException(status_code=422, detail="Недопустимое время окончания")
            if payload.corrected:
                # The owner explicitly reports the duration after returning from background.
                # Do not derive a fictitious interval from wall clock time while absent.
                row.measured_seconds = payload.corrected_seconds
            else:
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
