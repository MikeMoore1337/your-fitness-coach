import hashlib
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.program import (
    ProgramRevision,
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.models.workout_exercise_note import (
    WorkoutExerciseNote,
    WorkoutExerciseNoteMutation,
)
from fitminiapp_api.schemas.workout_exercise_note import (
    ExerciseNoteHistoryWrite,
    ExerciseNoteIdentity,
    ExerciseNoteVersion,
    ExerciseNoteWrite,
)
from fitminiapp_api.services.program_versioning import workout_cycle_week_type
from fitminiapp_api.services.workout_set_history import _completion_bounds


class ExerciseNoteError(Exception):
    def __init__(self, status_code: int, detail: str | dict):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


def _digest(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _identity(workout: UserWorkout, exercise: UserWorkoutExercise) -> dict:
    return {
        "exercise_id": exercise.exercise_id,
        "source_template_exercise_id": exercise.source_template_exercise_id,
        "plan_revision_number": workout.plan_revision_number,
        "week_number": workout.week_number,
        "day_number": workout.day_number,
        "source_cycle_week": workout.source_cycle_week,
        "cycle_iteration": workout.cycle_iteration,
    }


def _context_key(workout: UserWorkout, exercise: UserWorkoutExercise) -> str:
    return _digest(
        {
            "workout_id": workout.id,
            "workout_exercise_id": exercise.id,
            **_identity(workout, exercise),
        }
    )


def _target(
    db: Session, user_id: int, workout_id: int, workout_exercise_id: int, *, write: bool = False
) -> tuple[UserProgram, UserWorkout, UserWorkoutExercise]:
    program_id = (
        db.query(UserWorkout.user_program_id)
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .filter(UserWorkout.id == workout_id, UserProgram.user_id == user_id)
        .scalar()
    )
    if program_id is None:
        raise ExerciseNoteError(404, "Упражнение не найдено")
    program = (
        db.query(UserProgram)
        .filter(UserProgram.id == program_id, UserProgram.user_id == user_id)
        .populate_existing()
        .with_for_update(read=not write)
        .one_or_none()
    )
    if program is None:
        raise ExerciseNoteError(404, "Упражнение не найдено")
    target = (
        db.query(UserWorkout, UserWorkoutExercise)
        .join(UserWorkoutExercise, UserWorkoutExercise.workout_id == UserWorkout.id)
        .filter(
            UserWorkout.id == workout_id,
            UserWorkout.user_program_id == program.id,
            UserWorkoutExercise.id == workout_exercise_id,
        )
        .populate_existing()
        .one_or_none()
    )
    if target is None:
        raise ExerciseNoteError(404, "Упражнение не найдено")
    return program, target[0], target[1]


def _value(note: WorkoutExerciseNote | None) -> dict | None:
    if note is None or (not note.body and not note.tags):
        return None
    return {"id": note.id, "body": note.body, "tags": note.tags, "version": note.version}


def _week_type(db: Session, program: UserProgram, workout: UserWorkout) -> str | None:
    if workout.source_cycle_week is None:
        return None
    revisions = (
        db.query(ProgramRevision)
        .filter_by(user_program_id=program.id)
        .order_by(ProgramRevision.revision_number)
        .all()
    )
    return workout_cycle_week_type(db, workout, revisions)[0]


def _previous(
    db: Session,
    user_id: int,
    program: UserProgram,
    workout: UserWorkout,
    exercise: UserWorkoutExercise,
) -> dict | None:
    slot = exercise.source_template_exercise_id
    if slot is None or workout.plan_materialized is False:
        return None
    if (
        workout.status == "planned"
        and workout.source_cycle_week is not None
        and workout.plan_revision_number != program.current_revision_number
    ):
        return None
    current_slot_count = (
        db.query(UserWorkoutExercise.id)
        .filter_by(workout_id=workout.id, source_template_exercise_id=slot)
        .count()
    )
    if current_slot_count != 1:
        return None

    lineage = (
        select(UserProgram.id, UserProgram.restarted_from_program_id)
        .where(UserProgram.id == program.id, UserProgram.user_id == user_id)
        .cte("exercise_note_lineage", recursive=True)
    )
    lineage = lineage.union(
        select(UserProgram.id, UserProgram.restarted_from_program_id)
        .join(lineage, UserProgram.id == lineage.c.restarted_from_program_id)
        .where(UserProgram.user_id == user_id)
    )
    rows = (
        db.query(WorkoutExerciseNote, UserWorkout, UserWorkoutExercise)
        .join(UserWorkout, UserWorkout.id == WorkoutExerciseNote.workout_id)
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .join(
            UserWorkoutExercise,
            (UserWorkoutExercise.id == WorkoutExerciseNote.workout_exercise_id)
            & (UserWorkoutExercise.workout_id == UserWorkout.id),
        )
        .filter(
            UserProgram.id.in_(select(lineage.c.id)),
            UserProgram.user_id == user_id,
            UserWorkout.id != workout.id,
            UserWorkout.status == "completed",
            UserWorkout.day_number == workout.day_number,
            WorkoutExerciseNote.exercise_id == exercise.exercise_id,
            WorkoutExerciseNote.source_template_exercise_id == slot,
            UserWorkoutExercise.exercise_id == exercise.exercise_id,
            UserWorkoutExercise.source_template_exercise_id == slot,
        )
        .all()
    )
    planned = (
        workout.status == "planned"
        and workout.started_at is None
        and workout.started_at_utc is None
    )
    if planned:
        cutoff_min = cutoff_max = datetime.now(UTC).replace(tzinfo=None)
    elif workout.started_at_utc is not None:
        cutoff_min = cutoff_max = workout.started_at_utc
    elif workout.started_at is not None:
        cutoff_min = workout.started_at - timedelta(days=1)
        cutoff_max = workout.started_at + timedelta(days=1)
    elif workout.completed_at is not None or workout.completed_at_utc is not None:
        cutoff_min, cutoff_max = _completion_bounds(workout)
    else:
        return None
    candidates = []
    for note, source, source_exercise in rows:
        if not _value(note) or note.context_key != _context_key(source, source_exercise):
            continue
        if source.completed_at is None:
            return None
        low, high = _completion_bounds(source)
        if low > cutoff_max or (planned and low == cutoff_max):
            continue
        if not planned and high >= cutoff_min:
            return None
        candidates.append((low, high, note, source, source_exercise))
    if not candidates:
        return None
    latest_lower_bound = max(item[0] for item in candidates)
    possible_latest = [item for item in candidates if item[1] >= latest_lower_bound]
    for _low, _high, _note, source, _source_exercise in possible_latest:
        if source.plan_materialized is False:
            return None
        source_count = (
            db.query(UserWorkoutExercise.id)
            .filter_by(workout_id=source.id, source_template_exercise_id=slot)
            .count()
        )
        if source_count != 1:
            return None
    # Overlapping legacy timestamps cannot order workouts; use the latest saved note.
    _low, _high, note, source, source_exercise = max(
        possible_latest, key=lambda item: (item[2].updated_at, item[2].id)
    )
    latest_set = (
        db.query(UserWorkoutSet)
        .filter(
            UserWorkoutSet.workout_exercise_id == source_exercise.id,
            UserWorkoutSet.is_completed.is_(True),
        )
        .order_by(UserWorkoutSet.set_number.desc(), UserWorkoutSet.id.desc())
        .first()
    )
    load = (
        None
        if latest_set is None
        else {
            "set_number": latest_set.set_number,
            "actual_weight": float(latest_set.actual_weight)
            if latest_set.actual_weight is not None
            else None,
            "actual_reps": latest_set.actual_reps,
            "duration_minutes": latest_set.duration_minutes,
            "distance_km": float(latest_set.distance_km)
            if latest_set.distance_km is not None
            else None,
        }
    )
    value = _value(note)
    assert value is not None
    return {
        **value,
        "workout_id": source.id,
        "workout_exercise_id": source_exercise.id,
        "completed_on": source.completed_at.date(),
        "week_type": note.week_type,
        "load": load,
    }


def read_exercise_note(db: Session, user: User, workout_id: int, workout_exercise_id: int) -> dict:
    program, workout, exercise = _target(db, user.id, workout_id, workout_exercise_id)
    note = (
        db.query(WorkoutExerciseNote)
        .filter_by(workout_id=workout.id, context_key=_context_key(workout, exercise))
        .one_or_none()
    )
    return {
        "workout_id": workout.id,
        "workout_exercise_id": exercise.id,
        **_identity(workout, exercise),
        "version": note.version if note else 0,
        "current_note": _value(note),
        "previous_note": _previous(db, user.id, program, workout, exercise),
    }


def list_workout_exercise_notes(db: Session, user: User, workout_id: int) -> list[dict]:
    owned = (
        db.query(UserWorkout.id)
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .filter(UserWorkout.id == workout_id, UserProgram.user_id == user.id)
        .first()
    )
    if owned is None:
        raise ExerciseNoteError(404, "Тренировка не найдена")
    rows = (
        db.query(WorkoutExerciseNote, Exercise.title)
        .join(UserWorkout, UserWorkout.id == WorkoutExerciseNote.workout_id)
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .outerjoin(Exercise, Exercise.id == WorkoutExerciseNote.exercise_id)
        .filter(WorkoutExerciseNote.workout_id == workout_id, UserProgram.user_id == user.id)
        .order_by(WorkoutExerciseNote.id)
        .all()
    )
    result = []
    for note, title in rows:
        value = _value(note)
        if value is not None:
            result.append(
                {
                    **value,
                    "workout_id": note.workout_id,
                    "workout_exercise_id": note.workout_exercise_id,
                    "exercise_id": note.exercise_id,
                    "exercise_title": title,
                }
            )
    return result


def read_historical_exercise_note(db: Session, user: User, note_id: int) -> dict:
    note = (
        db.query(WorkoutExerciseNote)
        .join(UserWorkout, UserWorkout.id == WorkoutExerciseNote.workout_id)
        .join(UserProgram, UserProgram.id == UserWorkout.user_program_id)
        .filter(WorkoutExerciseNote.id == note_id, UserProgram.user_id == user.id)
        .one_or_none()
    )
    if note is None:
        raise ExerciseNoteError(404, "Заметка не найдена")
    return {"version": note.version, "current_note": _value(note)}


def write_historical_exercise_note(
    db: Session,
    user: User,
    note_id: int,
    payload: ExerciseNoteVersion | ExerciseNoteHistoryWrite,
    *,
    delete: bool = False,
) -> dict:
    program_id = (
        db.query(UserProgram.id)
        .join(UserWorkout, UserWorkout.user_program_id == UserProgram.id)
        .join(WorkoutExerciseNote, WorkoutExerciseNote.workout_id == UserWorkout.id)
        .filter(WorkoutExerciseNote.id == note_id, UserProgram.user_id == user.id)
        .scalar()
    )
    if program_id is None:
        raise ExerciseNoteError(404, "Заметка не найдена")
    program = (
        db.query(UserProgram)
        .filter_by(id=program_id, user_id=user.id)
        .with_for_update()
        .one_or_none()
    )
    if program is None:
        raise ExerciseNoteError(404, "Заметка не найдена")
    note = (
        db.query(WorkoutExerciseNote)
        .join(UserWorkout, UserWorkout.id == WorkoutExerciseNote.workout_id)
        .filter(WorkoutExerciseNote.id == note_id, UserWorkout.user_program_id == program_id)
        .populate_existing()
        .one_or_none()
    )
    if note is None:
        raise ExerciseNoteError(404, "Заметка не найдена")
    fingerprint = _digest(
        {
            "historical_note_id": note_id,
            "delete": delete,
            **payload.model_dump(mode="json", exclude={"mutation_id"}),
        }
    )
    operation = (
        db.query(WorkoutExerciseNoteMutation)
        .filter_by(user_id=user.id, mutation_id=payload.mutation_id)
        .one_or_none()
    )
    if operation is not None:
        if operation.request_fingerprint != fingerprint:
            raise ExerciseNoteError(
                409,
                {
                    "code": "exercise_note_idempotency_conflict",
                    "message": "Это изменение уже отправлено с другими данными.",
                },
            )
        return {"version": note.version, "current_note": _value(note)}
    if note.version != payload.expected_version:
        raise ExerciseNoteError(
            409,
            {
                "code": "exercise_note_version_conflict",
                "message": "Заметка изменилась на другом устройстве.",
                "current": {"version": note.version, "note": _value(note)},
            },
        )
    if delete and _value(note) is None:
        raise ExerciseNoteError(404, "Заметка не найдена")
    if delete:
        note.body, note.tags = None, []
    elif isinstance(payload, ExerciseNoteHistoryWrite):
        note.body, note.tags = payload.body, [str(tag) for tag in payload.tags]
    else:
        raise ExerciseNoteError(422, "Укажите текст или метку")
    note.version += 1
    note.updated_at = now_msk_naive()
    try:
        db.add(
            WorkoutExerciseNoteMutation(
                note_id=note.id,
                user_id=user.id,
                mutation_id=payload.mutation_id,
                request_fingerprint=fingerprint,
                applied_version=note.version,
            )
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        operation = (
            db.query(WorkoutExerciseNoteMutation)
            .filter_by(user_id=user.id, mutation_id=payload.mutation_id)
            .one_or_none()
        )
        if operation is None:
            raise
        if operation.request_fingerprint != fingerprint:
            raise ExerciseNoteError(
                409,
                {
                    "code": "exercise_note_idempotency_conflict",
                    "message": "Это изменение уже отправлено с другими данными.",
                },
            )
        note = db.get(WorkoutExerciseNote, note_id)
        assert note is not None
    return {"version": note.version, "current_note": _value(note)}


def write_exercise_note(
    db: Session,
    user: User,
    workout_id: int,
    workout_exercise_id: int,
    payload: ExerciseNoteIdentity | ExerciseNoteWrite,
    *,
    delete: bool = False,
) -> dict:
    program, workout, exercise = _target(db, user.id, workout_id, workout_exercise_id, write=True)
    identity = _identity(workout, exercise)
    if any(getattr(payload, key) != value for key, value in identity.items()):
        raise ExerciseNoteError(
            409,
            {
                "code": "exercise_note_identity_changed",
                "message": "Упражнение или план изменились. Проверьте сохранённый на устройстве текст.",
            },
        )
    if workout.status not in {"in_progress", "completed"}:
        raise ExerciseNoteError(
            409,
            {
                "code": "exercise_note_workout_inactive",
                "message": "Заметку можно сохранить во время или после тренировки.",
            },
        )
    fingerprint = _digest(
        {
            "workout_id": workout_id,
            "workout_exercise_id": workout_exercise_id,
            "delete": delete,
            **payload.model_dump(mode="json", exclude={"mutation_id"}),
        }
    )
    operation = (
        db.query(WorkoutExerciseNoteMutation)
        .filter_by(user_id=user.id, mutation_id=payload.mutation_id)
        .one_or_none()
    )
    if operation is not None:
        if operation.request_fingerprint != fingerprint:
            raise ExerciseNoteError(
                409,
                {
                    "code": "exercise_note_idempotency_conflict",
                    "message": "Это изменение уже отправлено с другими данными.",
                },
            )
        return read_exercise_note(db, user, workout_id, workout_exercise_id)

    note = (
        db.query(WorkoutExerciseNote)
        .filter_by(workout_id=workout.id, context_key=_context_key(workout, exercise))
        .one_or_none()
    )
    version = note.version if note else 0
    if version != payload.expected_version:
        raise ExerciseNoteError(
            409,
            {
                "code": "exercise_note_version_conflict",
                "message": "Заметка изменилась на другом устройстве.",
                "current": {"version": version, "note": _value(note)},
            },
        )
    if delete and (note is None or _value(note) is None):
        raise ExerciseNoteError(404, "Заметка не найдена")
    if note is None:
        note = WorkoutExerciseNote(
            workout_id=workout.id,
            workout_exercise_id=exercise.id,
            exercise_id=exercise.exercise_id,
            context_key=_context_key(workout, exercise),
            source_template_exercise_id=exercise.source_template_exercise_id,
            plan_revision_number=workout.plan_revision_number,
            week_type=_week_type(db, program, workout),
            body=None,
            tags=[],
            version=0,
        )
        db.add(note)
    if delete:
        note.body = None
        note.tags = []
    elif isinstance(payload, ExerciseNoteWrite):
        note.body = payload.body
        note.tags = [str(tag) for tag in payload.tags]
    else:
        raise ExerciseNoteError(422, "Укажите текст или метку")
    note.version = version + 1
    note.updated_at = now_msk_naive()
    try:
        db.flush()
        db.add(
            WorkoutExerciseNoteMutation(
                note_id=note.id,
                user_id=user.id,
                mutation_id=payload.mutation_id,
                request_fingerprint=fingerprint,
                applied_version=note.version,
            )
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        operation = (
            db.query(WorkoutExerciseNoteMutation)
            .filter_by(user_id=user.id, mutation_id=payload.mutation_id)
            .one_or_none()
        )
        if operation is None:
            raise
        if operation.request_fingerprint != fingerprint:
            raise ExerciseNoteError(
                409,
                {
                    "code": "exercise_note_idempotency_conflict",
                    "message": "Это изменение уже отправлено с другими данными.",
                },
            )
    return read_exercise_note(db, user, workout_id, workout_exercise_id)
