from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from fitminiapp_api.api.dependencies.auth import require_user
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.workout_copy import WorkoutCopyResponse
from fitminiapp_api.services.workout_copy import (
    CompletedWorkoutNotFound,
    get_completed_workout_copy,
)

router = APIRouter()


@router.get("/{workout_id}/copy", response_model=WorkoutCopyResponse)
def copy_completed_workout(
    workout_id: int,
    response: Response,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> WorkoutCopyResponse:
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return get_completed_workout_copy(db, current_user, workout_id)
    except CompletedWorkoutNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Тренировка не найдена"
        ) from exc
