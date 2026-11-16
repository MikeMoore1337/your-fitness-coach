from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from fitminiapp_api.api.dependencies.auth import require_user
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.nutrition_notes import NutritionMealNoteUpdate
from fitminiapp_api.services import nutrition_notes


class PrivateNotesRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def private_handler(request: Request):
            try:
                return await original(request)
            except RequestValidationError:
                raise HTTPException(status_code=422, detail="Проверьте данные отметки") from None
            except SQLAlchemyError:
                raise HTTPException(
                    status_code=500, detail="Не удалось обработать отметку"
                ) from None

        return private_handler


router = APIRouter(route_class=PrivateNotesRoute)
MealType = Literal["breakfast", "lunch", "dinner", "snacks"]


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _serialize(row):
    return {
        "local_date": row.local_date,
        "meal_type": row.meal_type,
        "timezone_at_entry": row.timezone_at_entry,
        "hunger_before": row.hunger_before,
        "fullness_after": row.fullness_after,
        "energy": row.energy,
        "note": row.note,
    }


@router.get("/consent")
def consent(response: Response, user: User = Depends(require_user), db: Session = Depends(get_db)):
    _private(response)
    row = nutrition_notes.get_consent(db, user)
    return {"status": row.status if row else "revoked"}


@router.post("/consent/{action}")
def change_consent(
    action: Literal["enable", "disable", "revoke"],
    response: Response,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    _private(response)
    return {"status": nutrition_notes.set_consent(db, user, action)}


@router.get("/{local_date}")
def list_notes(
    local_date: date,
    response: Response,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    _private(response)
    return [_serialize(row) for row in nutrition_notes.get_notes(db, user, local_date)]


@router.put("/{local_date}/{meal_type}")
def save(
    local_date: date,
    meal_type: MealType,
    payload: NutritionMealNoteUpdate,
    response: Response,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    _private(response)
    row = nutrition_notes.save_note(db, user, local_date, meal_type, payload)
    return _serialize(row) if row else None


@router.delete("/{local_date}/{meal_type}", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    local_date: date,
    meal_type: MealType,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    nutrition_notes.delete_note(db, user, local_date, meal_type)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
