from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fitminiapp_api.api.dependencies.auth import require_coach, require_user
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.coach_nutrition_proposal import (
    CoachNutritionPlanPreview,
    CoachNutritionProposalCreate,
    CoachNutritionProposalDecision,
    CoachNutritionProposalResponse,
    CoachNutritionTargetAssignments,
)
from fitminiapp_api.schemas.nutrition import NutritionTargetHistoryResponse
from fitminiapp_api.services.coach_clients import get_client_with_nutrition_access
from fitminiapp_api.services.coach_nutrition_proposals import (
    CoachNutritionProposalError,
    create_proposal,
    decide_proposal,
    list_proposals,
)
from fitminiapp_api.services.nutrition import (
    NutritionError,
    get_nutrition_target_for_date,
    list_nutrition_date_overrides,
    list_nutrition_target_history,
    read_nutrition_program_day,
)
from fitminiapp_api.services.nutrition_plan import NutritionPlanError, get_plan_day
from fitminiapp_api.services.nutrition_schedule_write import (
    list_nutrition_schedule_rules,
    read_nutrition_schedule_binding,
    read_nutrition_schedule_program,
)
from fitminiapp_api.services.program_common import ProgramError

router = APIRouter()
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, CoachNutritionProposalError):
        return HTTPException(status_code=exc.status_code, detail=str(exc))
    if isinstance(exc, IntegrityError):
        return HTTPException(status_code=409, detail="Изменение уже обработано; обновите данные")
    return HTTPException(status_code=409, detail=str(exc))


@router.get("", response_model=list[CoachNutritionProposalResponse])
def get_proposals(
    client_id: int | None = Query(default=None, ge=1),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if client_id is not None and not user.is_coach:
        raise HTTPException(status_code=404, detail="Предложение недоступно")
    try:
        return list_proposals(db, user, client_id=client_id)
    except CoachNutritionProposalError as exc:
        raise _error(exc) from exc


@router.post("/clients/{client_id}", response_model=CoachNutritionProposalResponse, status_code=201)
def post_proposal(
    client_id: int,
    payload: CoachNutritionProposalCreate,
    idempotency_key: IdempotencyKey,
    coach: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    try:
        return create_proposal(db, coach, client_id, payload, idempotency_key)
    except (CoachNutritionProposalError, NutritionError, NutritionPlanError, IntegrityError) as exc:
        db.rollback()
        raise _error(exc) from exc


@router.get("/clients/{client_id}/day", response_model=CoachNutritionPlanPreview)
def get_client_day(
    client_id: int,
    target_date: date,
    coach: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    try:
        client = get_client_with_nutrition_access(db, coach, client_id)
    except ProgramError as exc:
        raise HTTPException(status_code=404, detail="План недоступен") from exc
    target = get_nutrition_target_for_date(db, client.id, target_date)
    program = read_nutrition_schedule_program(db, client, None)
    program_day = None
    if program is not None:
        try:
            program_day = read_nutrition_program_day(
                db, client, None, program.program_id, program.revision_number, target_date
            )
        except NutritionError as exc:
            if str(exc) != "Program revision not found":
                raise
    return CoachNutritionPlanPreview(
        target_id=target.id if target else None,
        day=get_plan_day(db, client, target_date),
        program=program,
        program_day=program_day,
        binding=read_nutrition_schedule_binding(db, client, None, target_date),
    )


@router.get("/clients/{client_id}/target-history", response_model=NutritionTargetHistoryResponse)
def get_client_target_history(
    client_id: int,
    coach: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    try:
        client = get_client_with_nutrition_access(db, coach, client_id)
    except ProgramError as exc:
        raise HTTPException(status_code=404, detail="История недоступна") from exc
    return {"items": list_nutrition_target_history(db, client)}


@router.get(
    "/clients/{client_id}/target-assignments", response_model=CoachNutritionTargetAssignments
)
def get_client_target_assignments(
    client_id: int,
    coach: User = Depends(require_coach),
    db: Session = Depends(get_db),
):
    try:
        client = get_client_with_nutrition_access(db, coach, client_id)
    except ProgramError as exc:
        raise HTTPException(status_code=404, detail="История недоступна") from exc
    return CoachNutritionTargetAssignments(
        dates=list_nutrition_date_overrides(db, client),
        schedule=list_nutrition_schedule_rules(db, client),
    )


@router.post("/{proposal_id}/decision", response_model=CoachNutritionProposalResponse)
def post_decision(
    proposal_id: int,
    payload: CoachNutritionProposalDecision,
    idempotency_key: IdempotencyKey,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return decide_proposal(db, user, proposal_id, payload, idempotency_key)
    except (CoachNutritionProposalError, NutritionError, NutritionPlanError, IntegrityError) as exc:
        db.rollback()
        raise _error(exc) from exc
