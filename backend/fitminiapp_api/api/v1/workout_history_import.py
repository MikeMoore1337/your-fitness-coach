from __future__ import annotations

import csv
import io

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from fitminiapp_api.api.dependencies.auth import require_user
from fitminiapp_api.core.rate_limit import limiter
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.user import User
from fitminiapp_api.models.workout_history_import import WorkoutHistoryImportDraft
from fitminiapp_api.schemas.workout_history_import import (
    HistoryImportCatalogSearch,
    HistoryImportConfirm,
    HistoryImportDraftSummary,
    HistoryImportExerciseCandidate,
    HistoryImportPreview,
    HistoryImportResolve,
)
from fitminiapp_api.services.workout_history_import import (
    HistoryImportError,
    _catalog,
    _get_draft,
    _key,
    cancel_history_import,
    confirm_history_import,
    create_history_import,
    history_import_preview,
    resolve_history_import,
)
from fitminiapp_api.services.workout_history_import_parser import (
    CSV_COLUMNS,
    MAX_BYTES,
    WorkoutHistoryImportError,
)

router = APIRouter()


def _error(exc: HistoryImportError | WorkoutHistoryImportError) -> HTTPException:
    code = exc.status_code if isinstance(exc, HistoryImportError) else 400
    return HTTPException(
        status_code=code,
        detail={"code": exc.code, "message": str(exc)},
        headers={"Cache-Control": "no-store, private"},
    )


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store, private"


def _storage_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "storage_unavailable",
            "message": "Не удалось обработать импорт. Повторите позже",
        },
        headers={"Cache-Control": "no-store, private"},
    )


def _valid_filename(name: str | None) -> bool:
    return bool(
        name
        and len(name) <= 120
        and name.lower().endswith(".csv")
        and ".." not in name
        and not any(c in name for c in "/\\:")
        and not any(ord(c) < 32 or ord(c) == 127 for c in name)
    )


@router.get("/template.csv")
def download_template(current_user: User = Depends(require_user)) -> Response:
    del current_user
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["yfc_workout_history", "1"])
    writer.writerow(CSV_COLUMNS)
    writer.writerow(
        [
            "example-workout",
            "2025-10-12T18:30:00+03:00",
            "Europe/Moscow",
            "Пример",
            "completed",
            "example-exercise",
            "Жим штанги лёжа",
            "1",
            "completed",
            "working",
            "8",
            "50",
            "kg",
            "2",
            "",
            "",
        ]
    )
    return Response(
        content=output.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="yfc-workout-history-v1.csv"',
            "Cache-Control": "no-store, private",
        },
    )


@router.get("", response_model=list[HistoryImportDraftSummary])
def list_drafts(
    response: Response, current_user: User = Depends(require_user), db: Session = Depends(get_db)
):
    _no_store(response)
    from fitminiapp_api.services.workout_history_import import _now

    return [
        {
            "id": draft.id,
            "version": draft.version,
            "status": draft.status,
            "created_at": draft.created_at.isoformat() + "Z",
            "expires_at": draft.expires_at.isoformat() + "Z",
        }
        for draft in db.query(WorkoutHistoryImportDraft)
        .filter(
            WorkoutHistoryImportDraft.owner_user_id == current_user.id,
            WorkoutHistoryImportDraft.status.in_(("pending", "confirmed")),
            WorkoutHistoryImportDraft.expires_at > _now(),
        )
        .order_by(WorkoutHistoryImportDraft.created_at.desc())
        .limit(20)
        .all()
    ]


@router.post("/catalog", response_model=list[HistoryImportExerciseCandidate])
def search_catalog(
    response: Response,
    payload: HistoryImportCatalogSearch,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    _no_store(response)
    by_id, by_name = _catalog(db, current_user)
    key = _key(payload.q)
    if len(key) < 2:
        return []
    ids = {exercise_id for name, values in by_name.items() if key in name for exercise_id in values}
    return sorted((by_id[exercise_id] for exercise_id in ids), key=lambda item: item["title"])[:50]


@router.post("", response_model=HistoryImportPreview, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/hour")
async def upload_history(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    del request
    _no_store(response)
    try:
        if not _valid_filename(file.filename):
            raise HistoryImportError("filename", "Выберите CSV-файл с допустимым именем", 415)
        source = await file.read(MAX_BYTES + 1)
        draft = await run_in_threadpool(create_history_import, db, current_user, source)
        preview_data = await run_in_threadpool(history_import_preview, db, current_user, draft)
        preview = HistoryImportPreview.model_validate(preview_data)
        db.commit()
        return preview
    except (HistoryImportError, WorkoutHistoryImportError) as exc:
        db.rollback()
        raise _error(exc) from exc
    except SQLAlchemyError, ValidationError:
        db.rollback()
        raise _storage_error() from None
    finally:
        await file.close()


@router.get("/{draft_id}", response_model=HistoryImportPreview)
def get_history_import(
    draft_id: str,
    response: Response,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    _no_store(response)
    try:
        return HistoryImportPreview.model_validate(
            history_import_preview(db, current_user, _get_draft(db, current_user, draft_id))
        )
    except HistoryImportError as exc:
        raise _error(exc) from exc
    except SQLAlchemyError, ValidationError:
        db.rollback()
        raise _storage_error() from None


@router.post("/{draft_id}/resolve", response_model=HistoryImportPreview)
def resolve_history(
    draft_id: str,
    payload: HistoryImportResolve,
    response: Response,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    _no_store(response)
    try:
        draft = resolve_history_import(
            db,
            current_user,
            draft_id,
            version=payload.version,
            exercise_choices=payload.exercise_choices,
            excluded_lines=payload.excluded_lines,
            duplicate_choices=payload.duplicate_choices,
        )
        preview = HistoryImportPreview.model_validate(
            history_import_preview(db, current_user, draft)
        )
        db.commit()
        return preview
    except HistoryImportError as exc:
        db.rollback()
        raise _error(exc) from exc
    except SQLAlchemyError, ValidationError:
        db.rollback()
        raise _storage_error() from None


@router.post("/{draft_id}/confirm", response_model=HistoryImportPreview)
def confirm_history(
    draft_id: str,
    payload: HistoryImportConfirm,
    response: Response,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    _no_store(response)
    try:
        draft = confirm_history_import(
            db,
            current_user,
            draft_id,
            version=payload.version,
            preview_signature=payload.preview_signature,
        )
        result = HistoryImportPreview.model_validate(
            history_import_preview(db, current_user, draft)
        )
        db.commit()
        return result
    except HistoryImportError as exc:
        db.rollback()
        raise _error(exc) from exc
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "history_conflict",
                "message": "История изменилась. Обновите предпросмотр",
            },
            headers={"Cache-Control": "no-store, private"},
        ) from None
    except SQLAlchemyError, ValidationError:
        db.rollback()
        raise _storage_error() from None


@router.delete("/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_history(
    draft_id: str,
    version: int = Query(ge=1),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    try:
        cancel_history_import(db, current_user, draft_id, version=version)
        db.commit()
        return Response(status_code=204, headers={"Cache-Control": "no-store, private"})
    except HistoryImportError as exc:
        db.rollback()
        raise _error(exc) from exc
    except SQLAlchemyError:
        db.rollback()
        raise _storage_error() from None
