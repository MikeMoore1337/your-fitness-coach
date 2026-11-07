from __future__ import annotations

import hashlib
import hmac
import uuid
from contextlib import suppress
from datetime import timedelta
from decimal import Decimal
from typing import cast

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import now_msk_naive, today_for_user
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.photo_meal import PhotoMealDraft
from fitminiapp_api.models.user import User
from fitminiapp_api.nutrition_label.image import ImageIngressError, normalize_uploaded_image
from fitminiapp_api.nutrition_label.meal_vision import (
    MEAL_VISION_POLICY_REVISION,
    MealVisionCandidateExtraction,
    MealVisionExtraction,
    validate_meal_vision_proposal,
)
from fitminiapp_api.nutrition_label.vision import (
    VISION_MAX_RESPONSE_BYTES,
    VisionFallbackAdapter,
    VisionProposalError,
)
from fitminiapp_api.schemas.food_diary import FoodDiaryEntryCreate, FoodDiaryQuickAdd
from fitminiapp_api.schemas.photo_meal import (
    PhotoMealCandidate,
    PhotoMealConfirmItem,
    PhotoMealConfirmRequest,
    PhotoMealConfirmResponse,
    PhotoMealDraftResponse,
    PhotoMealDraftStatus,
)
from fitminiapp_api.services.food_diary import (
    FoodDiaryError,
    _lock_diary_user,
    _serialize_entry,
    create_food_diary_entry,
)


class PhotoMealError(ValueError):
    def __init__(self, code: str, *, status_code: int = 422) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class PhotoMealNotFoundError(PhotoMealError):
    def __init__(self) -> None:
        super().__init__("draft_not_found", status_code=404)


class PhotoMealConflictError(PhotoMealError):
    def __init__(self, code: str = "draft_conflict") -> None:
        super().__init__(code, status_code=409)


def _now():
    return now_msk_naive()


def _normalize_idempotency_key(value: str) -> str:
    normalized = value.strip()
    if len(normalized) < 8 or len(normalized) > 128:
        raise PhotoMealError("invalid_idempotency_key")
    return normalized


def _image_hmac(user_id: int, key: str, image: bytes, content_type: str | None) -> str:
    digest = hmac.new(settings.secret_key.encode(), b"photo-meal-draft-v1", hashlib.sha256)
    for value in (
        str(user_id).encode(),
        key.encode(),
        (content_type or "").strip().lower().encode(),
        image,
    ):
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    return digest.hexdigest()


def _lock_creation(db: Session, user_id: int, key: str) -> None:
    if db.get_bind().dialect.name != "postgresql":
        # shortcut: SQLite uploads are not serialized here; use PostgreSQL for concurrent uploads.
        return
    scope = f"photo-meal-create\0{user_id}\0{key}".encode()
    lock_id = int.from_bytes(hashlib.sha256(scope).digest()[:8], "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})


def _replay_created_draft(row: PhotoMealDraft, fingerprint: str) -> PhotoMealDraftResponse:
    stored = row.canonical_payload.get("image_hmac")
    if (
        not isinstance(stored, str)
        or not stored.isascii()
        or not hmac.compare_digest(stored, fingerprint)
    ):
        raise PhotoMealConflictError("idempotency_key_already_used")
    return _draft_response(row)


def _candidate_uncertainty(candidate: MealVisionCandidateExtraction) -> list[str]:
    result: list[str] = []
    if candidate.identity_confidence in {"low", "unknown"}:
        result.append("identity_uncertain")
    if candidate.portion_confidence in {"low", "unknown"}:
        result.append("portion_uncertain")
    if candidate.nutrition_confidence in {"low", "unknown"}:
        result.append("nutrition_uncertain")
    return result


def _candidate_payload(
    extraction: MealVisionExtraction,
) -> tuple[list[PhotoMealCandidate], list[str]]:
    candidates: list[PhotoMealCandidate] = []
    for index, candidate in enumerate(extraction.candidates, start=1):
        candidates.append(
            PhotoMealCandidate.model_validate(
                {
                    **candidate.model_dump(mode="json"),
                    "candidate_id": f"food-{index}",
                    "uncertainty_codes": _candidate_uncertainty(candidate),
                }
            )
        )
    warnings = list(dict.fromkeys([*extraction.warnings, "manual_review_required"]))
    return candidates, warnings


def _draft_response(row: PhotoMealDraft) -> PhotoMealDraftResponse:
    try:
        candidates = [
            PhotoMealCandidate.model_validate(item)
            for item in row.canonical_payload.get("candidates", [])
        ]
        warnings = row.canonical_payload.get("warnings", [])
        if not isinstance(warnings, list):
            raise ValueError("invalid warnings")
        return PhotoMealDraftResponse(
            draft_id=row.id,
            revision=row.revision,
            status=cast(PhotoMealDraftStatus, row.status),
            expires_at=row.expires_at,
            candidates=candidates,
            warnings=warnings,
            source_photo_retained=False,
        )
    except (AttributeError, TypeError, ValueError, ValidationError) as exc:
        raise PhotoMealError("invalid_persisted_draft", status_code=500) from exc


def _discard_expired_payload(row: PhotoMealDraft) -> None:
    if row.status == "draft":
        row.status = "expired"
    row.canonical_payload = {"retention_cleaned": True}


def expire_photo_meal_drafts(db: Session, *, limit: int = 100) -> int:
    rows = (
        db.query(PhotoMealDraft)
        .filter(
            PhotoMealDraft.expires_at <= _now(),
            PhotoMealDraft.canonical_payload["retention_cleaned"].as_string().is_(None),
        )
        .order_by(PhotoMealDraft.expires_at, PhotoMealDraft.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
        .all()
    )
    for row in rows:
        _discard_expired_payload(row)
    return len(rows)


def _get_owned_draft(
    db: Session,
    user: User,
    draft_id: str,
    *,
    lock_for_update: bool = False,
) -> PhotoMealDraft:
    query = db.query(PhotoMealDraft).filter(
        PhotoMealDraft.id == draft_id,
        PhotoMealDraft.user_id == user.id,
    )
    if lock_for_update:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise PhotoMealNotFoundError()
    if row.canonical_payload.get("retention_cleaned") is True:
        raise PhotoMealConflictError("draft_expired")
    if row.status == "draft" and row.expires_at <= _now():
        _discard_expired_payload(row)
        db.commit()
        raise PhotoMealConflictError("draft_expired")
    return row


def _has_reviewable_candidate(candidates: list[PhotoMealCandidate]) -> bool:
    return any(
        candidate.energy_kcal is not None
        and candidate.identity_confidence in {"high", "medium"}
        and candidate.nutrition_confidence in {"high", "medium"}
        for candidate in candidates
    )


def create_photo_meal_draft(
    db: Session,
    user: User,
    *,
    image_bytes: bytes,
    content_type: str | None,
    idempotency_key: str,
    vision_adapter: VisionFallbackAdapter | None,
) -> PhotoMealDraftResponse:
    key = _normalize_idempotency_key(idempotency_key)
    _lock_creation(db, user.id, key)
    fingerprint = _image_hmac(user.id, key, image_bytes, content_type)
    existing = (
        db.query(PhotoMealDraft)
        .filter(PhotoMealDraft.user_id == user.id, PhotoMealDraft.idempotency_key == key)
        .with_for_update()
        .first()
    )
    if existing is not None:
        if existing.status == "draft" and existing.expires_at > _now():
            return _replay_created_draft(existing, fingerprint)
        if existing.status == "draft":
            _discard_expired_payload(existing)
            db.commit()
        raise PhotoMealConflictError("idempotency_key_already_used")
    if vision_adapter is None:
        raise PhotoMealError("vision_unavailable", status_code=503)

    try:
        normalized_image = normalize_uploaded_image(
            image_bytes,
            content_type,
            max_bytes=settings.nutrition_label_scan_max_image_bytes,
            max_pixels=settings.nutrition_label_scan_max_pixels,
        )
    except ImageIngressError as exc:
        raise PhotoMealError(exc.code) from exc

    try:
        proposal = vision_adapter.recognize(
            normalized_image.data,
            timeout_seconds=settings.nutrition_label_vision_timeout_seconds,
            max_response_bytes=VISION_MAX_RESPONSE_BYTES,
        )
        extraction = validate_meal_vision_proposal(
            proposal,
            provider_class=vision_adapter.provider_class,
            model_class=vision_adapter.model_class,
            prompt_version=vision_adapter.prompt_version,
        )
    except TimeoutError as exc:
        raise PhotoMealError("vision_timeout", status_code=503) from exc
    except VisionProposalError as exc:
        raise PhotoMealError("vision_invalid_response", status_code=503) from exc
    except OSError as exc:
        raise PhotoMealError("vision_unavailable", status_code=503) from exc
    except Exception as exc:
        raise PhotoMealError("vision_failed", status_code=503) from exc

    candidates, warnings = _candidate_payload(extraction)
    if not candidates or not _has_reviewable_candidate(candidates):
        raise PhotoMealError("manual_fallback_required")

    row = PhotoMealDraft(
        id=str(uuid.uuid4()),
        user_id=user.id,
        idempotency_key=key,
        revision=1,
        status="draft",
        canonical_payload={
            "schema_version": "photo-meal-draft-v1",
            "policy_revision": MEAL_VISION_POLICY_REVISION,
            "provider": vision_adapter.provider_class,
            "model": vision_adapter.model_class,
            "prompt_version": vision_adapter.prompt_version,
            "image_hmac": fingerprint,
            "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
            "warnings": warnings,
            "source_photo_retained": False,
        },
        source_mime=normalized_image.mime,
        expires_at=_now() + timedelta(minutes=settings.nutrition_label_scan_draft_ttl_minutes),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        try:
            db.rollback()
            replay = (
                db.query(PhotoMealDraft)
                .filter(PhotoMealDraft.user_id == user.id, PhotoMealDraft.idempotency_key == key)
                .with_for_update()
                .first()
            )
        except SQLAlchemyError:
            raise PhotoMealError("draft_could_not_be_created", status_code=503) from None
        if replay is not None and replay.status == "draft" and replay.expires_at > _now():
            return _replay_created_draft(replay, fingerprint)
        raise PhotoMealConflictError("draft_could_not_be_created") from None
    except SQLAlchemyError:
        with suppress(SQLAlchemyError):
            db.rollback()
        raise PhotoMealError("draft_could_not_be_created", status_code=503) from None
    db.refresh(row)
    return _draft_response(row)


def get_photo_meal_draft(db: Session, user: User, draft_id: str) -> PhotoMealDraftResponse:
    return _draft_response(_get_owned_draft(db, user, draft_id, lock_for_update=True))


def cancel_photo_meal_draft(db: Session, user: User, draft_id: str, revision: int) -> None:
    row = _get_owned_draft(db, user, draft_id, lock_for_update=True)
    if row.status != "draft":
        raise PhotoMealConflictError("draft_not_active")
    if row.revision != revision:
        raise PhotoMealConflictError("stale_draft_revision")
    row.status = "cancelled"
    db.commit()


def _sum_optional(values: list[Decimal | None]) -> Decimal | None:
    if any(value is None for value in values):
        return None
    return sum((cast(Decimal, value) for value in values), start=Decimal("0"))


def confirm_photo_meal_draft(
    db: Session,
    user: User,
    draft_id: str,
    request: PhotoMealConfirmRequest,
) -> PhotoMealConfirmResponse:
    _lock_diary_user(db, user)
    row = _get_owned_draft(db, user, draft_id, lock_for_update=True)
    if row.status == "confirmed":
        if row.revision != request.revision + 1:
            raise PhotoMealConflictError("stale_draft_revision")
        try:
            confirmed_items = [
                PhotoMealConfirmItem.model_validate(item)
                for item in row.canonical_payload["confirmed_items"]
            ]
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise PhotoMealError("invalid_persisted_draft", status_code=500) from exc
        entry_row = (
            db.query(FoodDiaryEntry)
            .filter(
                FoodDiaryEntry.id == row.confirmed_entry_id,
                FoodDiaryEntry.user_id == user.id,
                FoodDiaryEntry.idempotency_key == f"photo-meal-{draft_id}",
            )
            .first()
        )
        if (
            confirmed_items != request.items
            or entry_row is None
            or entry_row.diary_date != request.diary_date
            or entry_row.meal_type != request.meal_type
            or entry_row.logged_at is not None
        ):
            raise PhotoMealConflictError("draft_not_active")
        return PhotoMealConfirmResponse(
            draft_id=draft_id, entry=_serialize_entry(entry_row), replayed=True
        )
    if row.status != "draft":
        raise PhotoMealConflictError("draft_not_active")
    if row.revision != request.revision:
        raise PhotoMealConflictError("stale_draft_revision")
    if request.diary_date > today_for_user(user):
        raise PhotoMealError("future_diary_date")

    stored_candidates = {
        candidate.candidate_id: candidate
        for candidate in (
            PhotoMealCandidate.model_validate(item)
            for item in row.canonical_payload.get("candidates", [])
        )
    }
    if {item.candidate_id for item in request.items} != set(stored_candidates):
        raise PhotoMealError("unknown_candidate")
    existing = (
        db.query(FoodDiaryEntry.id)
        .filter(
            FoodDiaryEntry.user_id == user.id,
            FoodDiaryEntry.idempotency_key == f"photo-meal-{draft_id}",
        )
        .first()
    )
    if existing is not None:
        raise PhotoMealConflictError("draft_not_active")

    calories = sum((item.energy_kcal for item in request.items), start=Decimal("0"))
    quick_add = FoodDiaryQuickAdd(
        name="Фото блюда: " + ", ".join(item.name for item in request.items)[:245],
        nutrition_source="photo",
        energy_kcal=calories,
        protein_g=_sum_optional([item.protein_g for item in request.items]),
        fat_g=_sum_optional([item.fat_g for item in request.items]),
        carbs_g=_sum_optional([item.carbs_g for item in request.items]),
    )
    payload = FoodDiaryEntryCreate(
        quick_add=quick_add,
        diary_date=request.diary_date,
        meal_type=request.meal_type,
        amount=Decimal("1"),
        amount_unit="serving",
    )
    try:
        entry = create_food_diary_entry(
            db,
            user,
            payload,
            idempotency_key=f"photo-meal-{draft_id}",
            commit=False,
        )
        entry_row = db.get(FoodDiaryEntry, entry.id)
        if entry_row is None:
            raise PhotoMealError("diary_entry_not_found", status_code=500)
        entry_row.nutrition_snapshot = {
            "kind": "photo_meal",
            "source_photo_retained": False,
            "candidates": [item.model_dump(mode="json") for item in request.items],
        }
        row.status = "confirmed"
        row.revision += 1
        row.confirmed_entry_id = entry.id
        row.canonical_payload = {
            **row.canonical_payload,
            "confirmed_items": [item.model_dump(mode="json") for item in request.items],
        }
        db.flush()
        db.refresh(entry_row)
        confirmed_entry = _serialize_entry(entry_row)
        db.commit()
    except FoodDiaryError as exc:
        db.rollback()
        raise PhotoMealError(str(exc), status_code=409 if "fasted" in str(exc) else 422) from exc
    except SQLAlchemyError:
        with suppress(SQLAlchemyError):
            db.rollback()
        raise PhotoMealError("draft_could_not_be_confirmed", status_code=503) from None
    except Exception:
        db.rollback()
        raise
    return PhotoMealConfirmResponse(draft_id=draft_id, entry=confirmed_entry, replayed=False)


__all__ = [
    "PhotoMealConflictError",
    "PhotoMealError",
    "PhotoMealNotFoundError",
    "cancel_photo_meal_draft",
    "confirm_photo_meal_draft",
    "create_photo_meal_draft",
    "expire_photo_meal_drafts",
    "get_photo_meal_draft",
]
