from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from fitminiapp_api.api.dependencies.auth import require_user
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.workout_exercise_note import (
    ExerciseNoteHistoryItem,
    ExerciseNoteHistoryResult,
    ExerciseNoteHistoryWrite,
    ExerciseNoteIdentity,
    ExerciseNoteResponse,
    ExerciseNoteVersion,
    ExerciseNoteWrite,
)
from fitminiapp_api.services.workout_exercise_notes import (
    ExerciseNoteError,
    list_workout_exercise_notes,
    read_exercise_note,
    read_historical_exercise_note,
    write_exercise_note,
    write_historical_exercise_note,
)

router = APIRouter()
PATH = "/{workout_id}/exercise-notes/{workout_exercise_id}"


@router.get("/{workout_id}/exercise-notes", response_model=list[ExerciseNoteHistoryItem])
def list_exercise_notes(
    workout_id: int,
    response: Response,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return list_workout_exercise_notes(db, current_user, workout_id)
    except ExerciseNoteError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.put("/exercise-notes/history/{note_id}", response_model=ExerciseNoteHistoryResult)
def put_historical_exercise_note(
    note_id: int,
    payload: ExerciseNoteHistoryWrite,
    response: Response,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return write_historical_exercise_note(db, current_user, note_id, payload)
    except ExerciseNoteError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/exercise-notes/history/{note_id}", response_model=ExerciseNoteHistoryResult)
def get_historical_exercise_note(
    note_id: int,
    response: Response,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return read_historical_exercise_note(db, current_user, note_id)
    except ExerciseNoteError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.delete("/exercise-notes/history/{note_id}", response_model=ExerciseNoteHistoryResult)
def delete_historical_exercise_note(
    note_id: int,
    payload: ExerciseNoteVersion,
    response: Response,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return write_historical_exercise_note(db, current_user, note_id, payload, delete=True)
    except ExerciseNoteError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get(PATH, response_model=ExerciseNoteResponse)
def get_exercise_note(
    workout_id: int,
    workout_exercise_id: int,
    response: Response,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return read_exercise_note(db, current_user, workout_id, workout_exercise_id)
    except ExerciseNoteError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.put(PATH, response_model=ExerciseNoteResponse)
def put_exercise_note(
    workout_id: int,
    workout_exercise_id: int,
    payload: ExerciseNoteWrite,
    response: Response,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return write_exercise_note(db, current_user, workout_id, workout_exercise_id, payload)
    except ExerciseNoteError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.delete(PATH, response_model=ExerciseNoteResponse)
def delete_exercise_note(
    workout_id: int,
    workout_exercise_id: int,
    payload: ExerciseNoteIdentity,
    response: Response,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return write_exercise_note(
            db, current_user, workout_id, workout_exercise_id, payload, delete=True
        )
    except ExerciseNoteError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
