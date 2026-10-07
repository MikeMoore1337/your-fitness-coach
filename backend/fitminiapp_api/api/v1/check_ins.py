from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from fitminiapp_api.api.dependencies.auth import require_user
from fitminiapp_api.core.timezone import today_for_user
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.check_in import (
    WeeklyCheckInCurrentResponse,
    WeeklyCheckInHistoryResponse,
    WeeklyCheckInResponse,
    WeeklyCheckInSubmitRequest,
    WeeklyPlanningReviewConfirmRequest,
    WeeklyPlanningReviewConfirmResponse,
)
from fitminiapp_api.schemas.check_in_templates import (
    AssignedCheckInTemplateListResponse,
    CheckInTemplateResponseItem,
    CheckInTemplateResponseSubmit,
)
from fitminiapp_api.schemas.daily_wellbeing import (
    DailyWellbeingCheckInResponse,
    DailyWellbeingCheckInSaveRequest,
    DailyWellbeingCurrentResponse,
)
from fitminiapp_api.services.check_in_templates import (
    CheckInTemplateError,
    list_assigned_templates,
    submit_response,
)
from fitminiapp_api.services.daily_wellbeing import (
    DailyWellbeingConflictError,
    DailyWellbeingValidationError,
    delete_daily_wellbeing,
    get_daily_wellbeing,
    save_daily_wellbeing,
    serialize_daily_wellbeing,
)
from fitminiapp_api.services.weekly_check_ins import (
    WeeklyCheckInConflictError,
    confirm_weekly_planning_review,
    get_current_weekly_check_in,
    list_weekly_check_ins,
    serialize_weekly_check_in,
    submit_weekly_check_in,
)

router = APIRouter()


def _check_in_template_error(exc: CheckInTemplateError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/daily", response_model=DailyWellbeingCurrentResponse)
def current_daily_wellbeing(
    local_date: date | None = Query(default=None),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    requested_date = local_date or today_for_user(current_user)
    try:
        return get_daily_wellbeing(db, current_user, requested_date)
    except DailyWellbeingValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put(
    "/daily/{local_date}",
    response_model=DailyWellbeingCheckInResponse,
)
def update_daily_wellbeing(
    local_date: date,
    payload: DailyWellbeingCheckInSaveRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        row = save_daily_wellbeing(db, current_user, local_date, payload)
    except DailyWellbeingValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DailyWellbeingConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return serialize_daily_wellbeing(row)


@router.delete("/daily/{local_date}", status_code=status.HTTP_204_NO_CONTENT)
def remove_daily_wellbeing(
    local_date: date,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        delete_daily_wellbeing(db, current_user, local_date)
    except DailyWellbeingValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/weekly/current", response_model=WeeklyCheckInCurrentResponse)
def current_weekly_check_in(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return get_current_weekly_check_in(db, current_user)


@router.post(
    "/weekly/planning-review/confirm",
    response_model=WeeklyPlanningReviewConfirmResponse,
)
def confirm_weekly_planning_review_action(
    payload: WeeklyPlanningReviewConfirmRequest,
    _idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
    ),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        return confirm_weekly_planning_review(db, current_user, payload)
    except WeeklyCheckInConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/weekly", response_model=WeeklyCheckInHistoryResponse)
def weekly_check_in_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return list_weekly_check_ins(db, current_user, limit=limit, offset=offset)


@router.post(
    "/weekly",
    response_model=WeeklyCheckInResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_weekly_check_in(
    payload: WeeklyCheckInSubmitRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        row = submit_weekly_check_in(db, current_user, payload)
    except WeeklyCheckInConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return serialize_weekly_check_in(row)


@router.get("/templates/assigned", response_model=AssignedCheckInTemplateListResponse)
def assigned_check_in_templates(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> AssignedCheckInTemplateListResponse:
    return AssignedCheckInTemplateListResponse.model_validate(
        list_assigned_templates(db, current_user)
    )


@router.post(
    "/templates/assignments/{assignment_id}/responses",
    response_model=CheckInTemplateResponseItem,
    status_code=status.HTTP_201_CREATED,
)
def submit_assigned_check_in_template(
    assignment_id: int,
    payload: CheckInTemplateResponseSubmit,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
    ),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> CheckInTemplateResponseItem:
    try:
        return CheckInTemplateResponseItem.model_validate(
            submit_response(db, current_user, assignment_id, payload, idempotency_key)
        )
    except CheckInTemplateError as exc:
        raise _check_in_template_error(exc) from exc
