from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from fitminiapp_api.api.dependencies.auth import require_user
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.public_share import (
    PublicShareImportRequest,
    PublicShareImportResponse,
    PublicShareOwnerResponse,
    PublicSharePeriodRequest,
    PublicSharePreviewResponse,
    PublicShareProgramCreateRequest,
    PublicShareProgramPreviewRequest,
    PublicShareProgressCreateRequest,
    PublicShareResponse,
)
from fitminiapp_api.services.public_shares import (
    PublicShareError,
    build_program_share_preview,
    build_progress_share_preview,
    create_program_share,
    create_progress_share,
    import_program_share,
    list_owner_public_shares,
    revoke_public_share,
    serialize_public_share,
)

router = APIRouter()


def _http_error(exc: PublicShareError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("", response_model=list[PublicShareOwnerResponse])
def list_shares(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    return list_owner_public_shares(db, current_user)


@router.post("/progress/preview", response_model=PublicSharePreviewResponse)
def preview_progress_share(
    payload: PublicSharePeriodRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> PublicSharePreviewResponse:
    try:
        return build_progress_share_preview(
            db,
            current_user,
            period=payload.period,
            date_from=payload.date_from,
            date_to=payload.date_to,
        )
    except PublicShareError as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post("/progress", response_model=PublicShareResponse, status_code=status.HTTP_201_CREATED)
def create_progress_public_share(
    payload: PublicShareProgressCreateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        row = create_progress_share(
            db,
            current_user,
            period=payload.period,
            date_from=payload.date_from,
            date_to=payload.date_to,
            preview_hash=payload.preview_hash,
        )
        db.commit()
        return serialize_public_share(row)
    except PublicShareError as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post("/program/preview", response_model=PublicSharePreviewResponse)
def preview_program_share(
    payload: PublicShareProgramPreviewRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> PublicSharePreviewResponse:
    try:
        return build_program_share_preview(db, current_user, template_id=payload.template_id)
    except PublicShareError as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post("/program", response_model=PublicShareResponse, status_code=status.HTTP_201_CREATED)
def create_program_public_share(
    payload: PublicShareProgramCreateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        row = create_program_share(
            db,
            current_user,
            template_id=payload.template_id,
            preview_hash=payload.preview_hash,
        )
        db.commit()
        return serialize_public_share(row)
    except PublicShareError as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post("/{share_id}/import", response_model=PublicShareImportResponse)
def import_shared_program(
    share_id: str,
    payload: PublicShareImportRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        import_status, template_id, program_id, workouts_created = import_program_share(
            db,
            current_user,
            share_id=share_id,
            preview_hash=payload.preview_hash,
            replace_active=payload.replace_active,
        )
        return {
            "share_id": share_id,
            "status": import_status,
            "template_id": template_id,
            "user_program_id": program_id,
            "workouts_created": workouts_created,
        }
    except PublicShareError as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.delete("/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share(
    share_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> None:
    try:
        revoke_public_share(db, current_user, share_id)
        db.commit()
    except PublicShareError as exc:
        db.rollback()
        raise _http_error(exc) from exc
