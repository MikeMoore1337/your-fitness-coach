from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from fitminiapp_api.api.dependencies.auth import require_root_admin
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.admin import (
    AdminAuditRow,
    AdminFunnelResponse,
    AdminJobRow,
    AdminOperationRequest,
    AdminTrainerCapabilityUpdate,
    AdminUserDetail,
    AdminUserSearchRow,
    AdminUserStatusUpdate,
)
from fitminiapp_api.services.admin_operations import (
    end_relationship,
    funnel_aggregates,
    list_audit_events,
    list_jobs,
    retry_account_export,
    search_users,
    update_trainer_capability,
    update_user_status,
    user_detail,
)

router = APIRouter()


@router.get("/users", response_model=list[AdminUserSearchRow])
def admin_users(
    q: str = Query(min_length=1, max_length=128),
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
) -> list[dict]:
    return search_users(db, q)


@router.get("/users/{user_id}", response_model=AdminUserDetail)
def admin_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
) -> dict:
    return user_detail(db, user_id)


@router.patch("/users/{user_id}/status", response_model=AdminUserDetail)
def admin_update_user_status(
    user_id: int,
    payload: AdminUserStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root_admin),
) -> dict:
    return update_user_status(
        db,
        actor=current_user,
        target_user_id=user_id,
        is_active=payload.is_active,
        reason=payload.reason,
    )


@router.patch("/users/{user_id}/trainer-capability", response_model=AdminUserDetail)
def admin_update_trainer_capability(
    user_id: int,
    payload: AdminTrainerCapabilityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root_admin),
) -> dict:
    return update_trainer_capability(
        db,
        actor=current_user,
        target_user_id=user_id,
        is_active=payload.is_active,
        reason=payload.reason,
    )


@router.post("/relationships/{relationship_id}/end", response_model=AdminUserDetail)
def admin_end_relationship(
    relationship_id: int,
    payload: AdminOperationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root_admin),
) -> dict:
    return end_relationship(
        db,
        actor=current_user,
        relationship_id=relationship_id,
        reason=payload.reason,
    )


@router.get("/jobs", response_model=list[AdminJobRow])
def admin_jobs(
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
) -> list[dict]:
    return list_jobs(db, limit=limit)


@router.post("/exports/{export_id}/retry", response_model=AdminJobRow)
def admin_retry_export(
    export_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root_admin),
) -> dict:
    return retry_account_export(db, actor=current_user, export_id=export_id)


@router.get("/funnel", response_model=AdminFunnelResponse)
def admin_funnel(
    period_days: int = Query(default=30, ge=7, le=730),
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
) -> dict:
    return funnel_aggregates(db, period_days=period_days)


@router.get("/audit", response_model=list[AdminAuditRow])
def admin_audit(
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
) -> list[dict]:
    return list_audit_events(db, limit=limit)
