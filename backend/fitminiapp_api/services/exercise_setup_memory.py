from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fitminiapp_api.models.exercise_setup_memory import ExerciseSetupMemory
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.exercise_setup import (
    EXERCISE_SETUP_MEMORY_MAX_LENGTH,
    ExerciseSetupMemoryResponse,
)
from fitminiapp_api.services.exercise_catalog import get_visible_exercise_display_map


class ExerciseSetupMemoryError(ValueError):
    """Base error for the owner-scoped setup memory service."""


class ExerciseSetupMemoryNotFoundError(ExerciseSetupMemoryError):
    """The exercise is not visible to the current account."""


class ExerciseSetupMemoryConflictError(ExerciseSetupMemoryError):
    """The memory was changed by another request or has a stale version."""


def _canonical_exercise_id(db: Session, user: User, exercise_id: int) -> int:
    visible = get_visible_exercise_display_map(db, user)
    if exercise_id not in visible:
        raise ExerciseSetupMemoryNotFoundError("Упражнение не найдено")
    return exercise_id


def serialize_exercise_setup_memory(row: ExerciseSetupMemory) -> ExerciseSetupMemoryResponse:
    return ExerciseSetupMemoryResponse(
        id=row.id,
        exercise_id=row.exercise_id,
        body=row.body,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def get_exercise_setup_memory(
    db: Session, user: User, exercise_id: int
) -> ExerciseSetupMemoryResponse | None:
    canonical_id = _canonical_exercise_id(db, user, exercise_id)
    row = (
        db.query(ExerciseSetupMemory)
        .filter(
            ExerciseSetupMemory.user_id == user.id,
            ExerciseSetupMemory.exercise_id == canonical_id,
        )
        .first()
    )
    return serialize_exercise_setup_memory(row) if row is not None else None


def get_exercise_setup_memories_for_workout(
    db: Session,
    user: User,
    exercise_ids: Iterable[int],
) -> dict[int, ExerciseSetupMemoryResponse]:
    requested_ids = set(exercise_ids)
    if not requested_ids:
        return {}
    visible_ids = requested_ids & set(get_visible_exercise_display_map(db, user))
    if not visible_ids:
        return {}
    rows = (
        db.query(ExerciseSetupMemory)
        .filter(
            ExerciseSetupMemory.user_id == user.id,
            ExerciseSetupMemory.exercise_id.in_(visible_ids),
        )
        .all()
    )
    return {row.exercise_id: serialize_exercise_setup_memory(row) for row in rows}


def save_exercise_setup_memory(
    db: Session,
    user: User,
    exercise_id: int,
    body: str,
    expected_version: int | None,
) -> ExerciseSetupMemoryResponse:
    if len(body) > EXERCISE_SETUP_MEMORY_MAX_LENGTH:
        raise ExerciseSetupMemoryError("Заметка слишком длинная")
    canonical_id = _canonical_exercise_id(db, user, exercise_id)
    row = (
        db.query(ExerciseSetupMemory)
        .filter(
            ExerciseSetupMemory.user_id == user.id,
            ExerciseSetupMemory.exercise_id == canonical_id,
        )
        .with_for_update()
        .first()
    )
    if row is None:
        if expected_version is not None:
            raise ExerciseSetupMemoryConflictError(
                "Заметка уже существует. Обновите экран и повторите попытку."
            )
        row = ExerciseSetupMemory(
            user_id=user.id,
            exercise_id=canonical_id,
            body=body,
            version=1,
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ExerciseSetupMemoryConflictError(
                "Заметка уже была сохранена. Обновите экран и повторите попытку."
            ) from exc
        db.refresh(row)
        return serialize_exercise_setup_memory(row)

    if expected_version is None or expected_version != row.version:
        raise ExerciseSetupMemoryConflictError(
            "Заметка уже изменилась. Обновите её перед сохранением."
        )
    if row.body == body:
        return serialize_exercise_setup_memory(row)

    row.body = body
    row.version += 1
    db.commit()
    db.refresh(row)
    return serialize_exercise_setup_memory(row)


def delete_exercise_setup_memory(
    db: Session,
    user: User,
    exercise_id: int,
    expected_version: int | None,
) -> None:
    canonical_id = _canonical_exercise_id(db, user, exercise_id)
    row = (
        db.query(ExerciseSetupMemory)
        .filter(
            ExerciseSetupMemory.user_id == user.id,
            ExerciseSetupMemory.exercise_id == canonical_id,
        )
        .with_for_update()
        .first()
    )
    if row is None:
        return
    if expected_version is None or expected_version != row.version:
        raise ExerciseSetupMemoryConflictError(
            "Заметка уже изменилась. Обновите её перед удалением."
        )
    db.delete(row)
    db.commit()
