from __future__ import annotations

from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from fitminiapp_api.api.dependencies.auth import require_root_admin, require_user
from fitminiapp_api.core.rate_limit import limiter
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.token import RefreshToken
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.nutrition_import_engine import (
    CatalogAliasConfirmRequest,
    CatalogAliasReceipt,
    CatalogConflict,
    CatalogImportConfirmRequest,
    CatalogImportPreview,
    CatalogImportReceipt,
    ImportCancelRequest,
    ImportConfirmRequest,
    ImportPreview,
    ImportReceipt,
    ImportResolveRequest,
)
from fitminiapp_api.services.nutrition_catalog_import import (
    catalog_import_preview,
    confirm_catalog_alias,
    confirm_catalog_import,
    list_catalog_conflicts,
)
from fitminiapp_api.services.nutrition_import_drafts import (
    NutritionDraftError,
    _lock_user,
    cancel_nutrition_import_draft,
    confirm_nutrition_import_draft,
    create_nutrition_import_draft,
    nutrition_import_preview,
    set_resolutions,
)
from fitminiapp_api.services.nutrition_import_limits import (
    acquire_parser_slot,
    reserve_upload_attempt,
)
from fitminiapp_api.services.nutrition_import_runner import ADAPTERS, run_nutrition_import_adapter
from fitminiapp_api.services.nutrition_import_validation import (
    MAX_UPLOAD_BYTES,
    NutritionImportValidationError,
)
from fitminiapp_api.services.root_admin import has_verified_root_identity

router = APIRouter()


def _error(exc: NutritionDraftError | NutritionImportValidationError) -> HTTPException:
    code = exc.code
    if isinstance(exc, NutritionDraftError):
        status = exc.status_code
    elif code in {
        "adapter_unavailable",
        "unsupported_type",
        "invalid_filename",
        "unsupported_bytes",
    }:
        status = 415
    elif code == "upload_size":
        status = 413
    elif code in {"adapter_execution_unavailable", "adapter_timeout", "adapter_failed"}:
        status = 503
    else:
        status = 400
    messages = {
        "not_found": "Черновик не найден",
        "access_revoked": "Сессия недействительна или истекла",
        "draft_unavailable": "Черновик больше недоступен",
        "draft_changed": "Черновик изменился. Загрузите файл снова",
        "stale_revision": "Черновик изменился. Обновите предпросмотр",
        "preview_changed": "Данные изменились. Проверьте предпросмотр снова",
        "unresolved_rows": "Исправьте или исключите проблемные строки",
        "duplicate_import": "Эти строки уже были импортированы",
        "adapter_unavailable": "Этот источник импорта пока не поддерживается",
        "invalid_encoding": "Сохраните файл в кодировке UTF-8",
        "pdf_no_text": "В PDF не найден текст. Загрузите файл CSV",
        "rate_limited": "Слишком много загрузок. Повторите позже",
        "parser_busy": "Импорт занят. Попробуйте позже",
    }
    return HTTPException(
        status_code=status,
        detail={"code": code, "message": messages.get(code, "Не удалось обработать импорт")},
        headers={"Cache-Control": "no-store, private"},
    )


def _storage_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"code": "storage_unavailable", "message": "Не удалось обработать импорт"},
        headers={"Cache-Control": "no-store, private"},
    )


def _process_upload(
    db: Session,
    user: User,
    source: bytes,
    filename: str | None,
    content_type: str | None,
    adapter_id: str,
    upload_key: str,
) -> dict:
    reserve_upload_attempt(db, user)
    acquire_parser_slot(db, user)
    document = run_nutrition_import_adapter(
        adapter_id, source, filename=filename, content_type=content_type
    )
    adapter = ADAPTERS[adapter_id]
    draft = create_nutrition_import_draft(
        db,
        user,
        document=document,
        source=source,
        filename=filename or "",
        content_type=content_type or "",
        delimiter=adapter.delimiter,
        parser_version=adapter.parser_version,
        upload_key=upload_key,
        adapter_id=adapter_id,
    )
    if draft.status == "confirmed":
        raise NutritionDraftError("already_confirmed", 409)
    preview = ImportPreview.model_validate(nutrition_import_preview(db, user, draft.id))
    db.commit()
    return preview.model_dump(mode="json")


@router.post("", response_model=ImportPreview, status_code=201)
@limiter.limit("30/hour")
async def upload(
    request: Request,
    file: UploadFile = File(...),
    adapter_id: str = Form(..., min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]*$"),
    upload_key: str = Header(
        ..., alias="Idempotency-Key", min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    ),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    del request
    try:
        source = await file.read(MAX_UPLOAD_BYTES + 1)
        return await run_in_threadpool(
            _process_upload,
            db,
            current_user,
            source,
            file.filename,
            file.content_type,
            adapter_id,
            upload_key,
        )
    except (NutritionDraftError, NutritionImportValidationError) as exc:
        db.rollback()
        raise _error(exc) from exc
    except SQLAlchemyError, ValidationError, KeyError:
        db.rollback()
        raise _storage_error() from None
    finally:
        await file.close()


@router.get("/{draft_id}", response_model=ImportPreview)
def preview(
    draft_id: str, current_user: User = Depends(require_user), db: Session = Depends(get_db)
):
    try:
        return ImportPreview.model_validate(nutrition_import_preview(db, current_user, draft_id))
    except NutritionDraftError as exc:
        raise _error(exc) from exc
    except SQLAlchemyError, ValidationError:
        db.rollback()
        raise _storage_error() from None


@router.post("/{draft_id}/resolve", response_model=ImportPreview)
def resolve(
    draft_id: str,
    payload: ImportResolveRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        indexes = [item.index for item in payload.matches]
        if len(set(indexes)) != len(indexes):
            raise NutritionDraftError("invalid_rows", 422)
        set_resolutions(
            db,
            current_user,
            draft_id,
            revision=payload.revision,
            matches={item.index: item.food_id for item in payload.matches},
            skipped_rows=payload.skipped_rows,
        )
        result = ImportPreview.model_validate(nutrition_import_preview(db, current_user, draft_id))
        db.commit()
        return result
    except NutritionDraftError as exc:
        db.rollback()
        raise _error(exc) from exc
    except SQLAlchemyError, ValidationError:
        db.rollback()
        raise _storage_error() from None


def _lock_active_session(db: Session, user: User, family_id: str | None) -> None:
    _lock_user(db, user)
    if not family_id:
        raise NutritionDraftError("access_revoked", 401)
    active = (
        db.query(RefreshToken.id)
        .filter(
            RefreshToken.user_id == user.id,
            RefreshToken.family_id == family_id,
            RefreshToken.is_revoked.is_(False),
            RefreshToken.is_used.is_(False),
            RefreshToken.expires_at >= datetime.now(UTC).replace(tzinfo=None),
        )
        .with_for_update()
        .first()
    )
    if active is None:
        raise NutritionDraftError("access_revoked", 401)


@router.get("/catalog/conflicts", response_model=list[CatalogConflict])
def catalog_conflicts(
    response: Response,
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    _: User = Depends(require_root_admin),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store, private"
    return list_catalog_conflicts(db, after_id=after_id, limit=limit)


@router.post(
    "/catalog/conflicts/{contribution_id}/confirm-alias", response_model=CatalogAliasReceipt
)
def catalog_confirm_alias(
    contribution_id: int,
    payload: CatalogAliasConfirmRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(require_root_admin),
    db: Session = Depends(get_db),
):
    try:
        _lock_active_session(db, current_user, getattr(request.state, "session_family_id", None))
        if not has_verified_root_identity(db, current_user):
            raise NutritionDraftError("access_revoked", 401)
        result = confirm_catalog_alias(
            db, current_user, contribution_id, preview_signature=payload.preview_signature
        )
        receipt = CatalogAliasReceipt.model_validate(result)
        db.commit()
        response.headers["Cache-Control"] = "no-store, private"
        return receipt
    except NutritionDraftError as exc:
        db.rollback()
        raise _error(exc) from exc
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "alias_conflict", "message": "Обновите предпросмотр импорта"},
            headers={"Cache-Control": "no-store, private"},
        ) from None
    except SQLAlchemyError, ValidationError:
        db.rollback()
        raise _storage_error() from None


@router.get("/{draft_id}/catalog", response_model=CatalogImportPreview)
@limiter.limit("30/minute")
def preview_catalog(
    draft_id: str,
    request: Request,
    response: Response,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    del request
    try:
        response.headers["Cache-Control"] = "no-store, private"
        return CatalogImportPreview.model_validate(
            catalog_import_preview(db, current_user, draft_id)
        )
    except NutritionDraftError as exc:
        raise _error(exc) from exc
    except SQLAlchemyError, ValidationError:
        db.rollback()
        raise _storage_error() from None


@router.post("/{draft_id}/catalog/confirm", response_model=CatalogImportReceipt)
@limiter.limit("30/minute")
def confirm_catalog(
    draft_id: str,
    payload: CatalogImportConfirmRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        _lock_active_session(db, current_user, getattr(request.state, "session_family_id", None))
        result = CatalogImportReceipt.model_validate(
            confirm_catalog_import(
                db,
                current_user,
                draft_id,
                revision=payload.revision,
                preview_signature=payload.preview_signature,
                confirm_key=payload.confirm_key,
                row_indexes=payload.row_indexes,
                confirmed=payload.confirmed,
            )
        )
        db.commit()
        response.headers["Cache-Control"] = "no-store, private"
        return result
    except NutritionDraftError as exc:
        db.rollback()
        raise _error(exc) from exc
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "import_conflict", "message": "Обновите предпросмотр импорта"},
            headers={"Cache-Control": "no-store, private"},
        ) from None
    except SQLAlchemyError, ValidationError:
        db.rollback()
        raise _storage_error() from None


@router.post("/{draft_id}/confirm", response_model=ImportReceipt)
def confirm(
    draft_id: str,
    payload: ImportConfirmRequest,
    request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        _lock_active_session(db, current_user, getattr(request.state, "session_family_id", None))
        result = ImportReceipt.model_validate(
            confirm_nutrition_import_draft(
                db,
                current_user,
                draft_id,
                revision=payload.revision,
                preview_signature=payload.preview_signature,
                confirm_key=payload.confirm_key,
                confirmed=payload.confirmed,
            )
        )
        db.commit()
        return result
    except NutritionDraftError as exc:
        db.rollback()
        raise _error(exc) from exc
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "import_conflict", "message": "Обновите предпросмотр импорта"},
        ) from None
    except SQLAlchemyError, ValidationError:
        db.rollback()
        raise _storage_error() from None


@router.post("/{draft_id}/cancel", status_code=204)
def cancel(
    draft_id: str,
    payload: ImportCancelRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        cancel_nutrition_import_draft(db, current_user, draft_id, revision=payload.revision)
        db.commit()
        return Response(status_code=204, headers={"Cache-Control": "no-store, private"})
    except NutritionDraftError as exc:
        db.rollback()
        raise _error(exc) from exc
    except SQLAlchemyError:
        db.rollback()
        raise _storage_error() from None
