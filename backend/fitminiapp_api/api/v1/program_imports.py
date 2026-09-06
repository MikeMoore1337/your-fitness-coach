from __future__ import annotations

from pathlib import PurePath

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from fitminiapp_api.api.dependencies.auth import require_user
from fitminiapp_api.core.rate_limit import limiter
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.program_import import (
    ProgramImportConfirmResponse,
    ProgramImportResolveRequest,
    ProgramImportResponse,
)
from fitminiapp_api.services.program_imports import (
    PROGRAM_IMPORT_SUPPORTED_FORMATS,
    ProgramImportError,
    build_program_import_template,
    cancel_program_import,
    confirm_program_import,
    create_program_import,
    get_program_import,
    resolve_program_import,
    serialize_import,
)
from fitminiapp_api.services.programs import build_template_response

router = APIRouter()


def _http_error(exc: ProgramImportError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _format_from_filename(filename: str | None) -> str:
    suffix = PurePath(filename or "").suffix.casefold().removeprefix(".")
    return suffix


@router.get("/template.csv", response_class=Response)
def download_csv_template(
    current_user: User = Depends(require_user),
) -> Response:
    del current_user
    content, media_type, filename = build_program_import_template("csv")
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, private",
        },
    )


@router.get("/template.xlsx", response_class=Response)
def download_xlsx_template(
    current_user: User = Depends(require_user),
) -> Response:
    del current_user
    content, media_type, filename = build_program_import_template("xlsx")
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, private",
        },
    )


@router.post("", response_model=ProgramImportResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/hour")
async def upload_program_import(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    del request
    source_format = _format_from_filename(file.filename)
    if source_format not in PROGRAM_IMPORT_SUPPORTED_FORMATS:
        raise HTTPException(status_code=415, detail="Поддерживаются только файлы .xlsx и .csv")
    try:
        source = await file.read()
        import_row = create_program_import(
            db,
            current_user,
            source=source,
            source_format=source_format,
        )
        db.commit()
        return serialize_import(import_row)
    except ProgramImportError as exc:
        db.rollback()
        raise _http_error(exc) from exc
    finally:
        await file.close()


@router.get("/{import_id}", response_model=ProgramImportResponse)
def get_import_preview(
    import_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        import_row = get_program_import(db, current_user, import_id)
        if import_row.status in {"cancelled", "expired"}:
            raise ProgramImportError(
                "import_unavailable", "Предпросмотр импорта больше недоступен", 410
            )
        return serialize_import(import_row)
    except ProgramImportError as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post("/{import_id}/resolve", response_model=ProgramImportResponse)
def resolve_import_preview(
    import_id: str,
    payload: ProgramImportResolveRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        import_row = resolve_program_import(
            db,
            current_user,
            import_id,
            title=payload.title,
            goal=payload.goal,
            level=payload.level,
            row_resolutions=[(item.row_number, item.exercise_id) for item in payload.rows],
        )
        return serialize_import(import_row)
    except ProgramImportError as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post("/{import_id}/confirm", response_model=ProgramImportConfirmResponse)
def confirm_import_preview(
    import_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        import_row, template = confirm_program_import(db, current_user, import_id)
        return {
            "import_id": import_row.id,
            "template": build_template_response(template, db, current_user),
            "assigned_program_id": None,
            "workouts_created": 0,
            "target_user": {
                "id": current_user.id,
                "telegram_user_id": current_user.telegram_user_id,
                "full_name": getattr(getattr(current_user, "profile", None), "full_name", None),
            },
        }
    except ProgramImportError as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post("/{import_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_import_preview(
    import_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> None:
    try:
        cancel_program_import(db, current_user, import_id)
    except ProgramImportError as exc:
        db.rollback()
        raise _http_error(exc) from exc
