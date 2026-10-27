from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
from sqlalchemy.orm import Session

from fitminiapp_api.api.dependencies.auth import require_user
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.report_handoff import (
    ReportHandoffCreateRequest,
    ReportHandoffResponse,
    ReportHandoffViewResponse,
)
from fitminiapp_api.services.report_handoffs import (
    ReportHandoffError,
    create_report_handoff,
    get_report_handoff_view,
    list_report_handoffs,
    retry_report_handoff,
)

router = APIRouter()
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=128),
]


def _handoff_error(exc: ReportHandoffError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("", response_model=list[ReportHandoffResponse])
def get_my_report_handoffs(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[ReportHandoffResponse]:
    return list_report_handoffs(db, current_user)


@router.post("", response_model=ReportHandoffResponse, status_code=status.HTTP_201_CREATED)
def create_my_report_handoff(
    payload: ReportHandoffCreateRequest,
    idempotency_key: IdempotencyKey,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> ReportHandoffResponse:
    try:
        return create_report_handoff(db, current_user, payload, idempotency_key)
    except ReportHandoffError as exc:
        raise _handoff_error(exc) from exc


@router.post(
    "/{handoff_id}/retry",
    response_model=ReportHandoffResponse,
)
def retry_my_report_handoff(
    idempotency_key: IdempotencyKey,
    handoff_id: int = Path(ge=1),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> ReportHandoffResponse:
    try:
        return retry_report_handoff(db, current_user, handoff_id, idempotency_key)
    except ReportHandoffError as exc:
        raise _handoff_error(exc) from exc


@router.get("/{handoff_id}", response_model=ReportHandoffViewResponse)
def get_report_handoff(
    handoff_id: int = Path(ge=1),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> ReportHandoffViewResponse:
    try:
        return get_report_handoff_view(db, current_user, handoff_id)
    except ReportHandoffError as exc:
        raise _handoff_error(exc) from exc
