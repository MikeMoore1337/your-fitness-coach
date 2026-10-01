from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import cast

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
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
    PhotoMealConfirmRequest,
    PhotoMealConfirmResponse,
    PhotoMealDraftResponse,
    PhotoMealDraftStatus,
)
from fitminiapp_api.services.food_diary import FoodDiaryError, create_food_diary_entry


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


def _mark_expired(row: PhotoMealDraft) -> None:
    row.status = "expired"


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
    if row.status == "draft" and row.expires_at <= _now():
        _mark_expired(row)
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
    existing = (
        db.query(PhotoMealDraft)
        .filter(PhotoMealDraft.user_id == user.id, PhotoMealDraft.idempotency_key == key)
        .first()
    )
    if existing is not None:
        if existing.status == "draft" and existing.expires_at > _now():
            return _draft_response(existing)
        if existing.status == "draft":
            _mark_expired(existing)
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
    except IntegrityError as exc:
        db.rollback()
        replay = (
            db.query(PhotoMealDraft)
            .filter(PhotoMealDraft.user_id == user.id, PhotoMealDraft.idempotency_key == key)
            .first()
        )
        if replay is not None and replay.status == "draft" and replay.expires_at > _now():
            return _draft_response(replay)
        raise PhotoMealConflictError("draft_could_not_be_created") from exc
    db.refresh(row)
    return _draft_response(row)


def get_photo_meal_draft(db: Session, user: User, draft_id: str) -> PhotoMealDraftResponse:
    return _draft_response(_get_owned_draft(db, user, draft_id))


def cancel_photo_meal_draft(db: Session, user: User, draft_id: str, revision: int) -> None:
    row = _get_owned_draft(db, user, draft_id)
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
    row = _get_owned_draft(db, user, draft_id, lock_for_update=True)
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
    if any(item.candidate_id not in stored_candidates for item in request.items):
        raise PhotoMealError("unknown_candidate")

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
        )
    except FoodDiaryError as exc:
        raise PhotoMealError(str(exc), status_code=409 if "fasted" in str(exc) else 422) from exc

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
    db.commit()
    return PhotoMealConfirmResponse(draft_id=draft_id, entry=entry, replayed=False)


__all__ = [
    "PhotoMealConflictError",
    "PhotoMealError",
    "PhotoMealNotFoundError",
    "cancel_photo_meal_draft",
    "confirm_photo_meal_draft",
    "create_photo_meal_draft",
    "get_photo_meal_draft",
]
