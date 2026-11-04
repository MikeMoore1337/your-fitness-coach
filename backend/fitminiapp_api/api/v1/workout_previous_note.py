from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from fitminiapp_api.api.dependencies.auth import require_user
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.workout_previous_note import PreviousWorkoutNoteResponse
from fitminiapp_api.services.workout_previous_note import (
    WorkoutNotFound,
    find_previous_workout_note,
)

router = APIRouter()


@router.get("/{workout_id}/previous-completion-note", response_model=PreviousWorkoutNoteResponse)
def previous_completion_note(
    workout_id: int,
    response: Response,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return {"previous_note": find_previous_workout_note(db, current_user.id, workout_id)}
    except WorkoutNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Тренировка не найдена"
        ) from exc
