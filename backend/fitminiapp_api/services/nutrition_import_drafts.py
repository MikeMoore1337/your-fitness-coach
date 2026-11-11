"""Private nutrition drafts; canonical writes remain disabled until a resolver is connected."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy.orm import Session

from fitminiapp_api.models.food import Food
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.nutrition_import import NutritionImportDraft
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.food_diary import FoodDiaryEntryCreate
from fitminiapp_api.schemas.nutrition_import import (
    NutritionImportV1,
    NutritionImportV2,
    NutritionImportV3,
)
from fitminiapp_api.services.food_diary import (
    FoodDiaryError,
    _calculate_amount,
    _copy_food_snapshot,
    _ensure_day_accepts_entries,
    _set_nutrition_amount,
    _validate_diary_date,
    _visible_food,
)
from fitminiapp_api.services.nutrition_import_validation import (
    validate_adapter_result,
    validate_csv_upload,
    validate_pdf_upload,
)

DRAFT_TTL = timedelta(hours=24)
MAX_ACTIVE_DRAFTS = 3
_KEY = re.compile(r"[A-Za-z0-9._:-]{8,128}\Z")
_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")


@dataclass
class _PlanningCache:
    foods: dict[int, Food] = field(default_factory=dict)
    checked_dates: set[date] = field(default_factory=set)


class NutritionDraftError(ValueError):
    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _lock_user(db: Session, user: User) -> None:
    row = db.query(User.is_active).filter(User.id == user.id).with_for_update().first()
    if row is None or not row.is_active:
        raise NutritionDraftError("access_revoked", 401)


def get_nutrition_import_draft(
    db: Session, user: User, draft_id: str, *, lock: bool = False, allow_confirmed: bool = False
) -> NutritionImportDraft:
    query = db.query(NutritionImportDraft).filter(
        NutritionImportDraft.id == draft_id,
        NutritionImportDraft.owner_user_id == user.id,
    )
    if lock:
        query = query.with_for_update()
    draft = query.first()
    if draft is None:
        raise NutritionDraftError("not_found", 404)
    if (
        draft.status != "pending" and not (allow_confirmed and draft.status == "confirmed")
    ) or draft.expires_at <= _now():
        raise NutritionDraftError("draft_unavailable", 410)
    document = draft.document
    if not isinstance(document, dict) or not isinstance(document.get("source"), dict):
        raise NutritionDraftError("draft_changed", 409)
    fingerprint_data = {
        "content": draft.source_sha256,
        "document": draft.document_sha256,
        "parser": draft.parser_version,
    }
    if draft.adapter_id is not None:
        fingerprint_data["adapter_id"] = draft.adapter_id
    fingerprint = _digest(_canonical(fingerprint_data))
    if (
        _digest(_canonical(document)) != draft.document_sha256
        or draft.upload_fingerprint != fingerprint
        or document["source"].get("provider") != draft.provider
        or document["source"].get("source") != draft.source
        or document.get("schema_version") != draft.schema_version
    ):
        raise NutritionDraftError("draft_changed", 409)
    return draft


def create_nutrition_import_draft(
    db: Session,
    user: User,
    *,
    document: NutritionImportV1 | NutritionImportV2 | NutritionImportV3,
    source: bytes,
    filename: str,
    content_type: str,
    delimiter: Literal[",", ";", "\t"],
    parser_version: str,
    upload_key: str,
    adapter_id: str | None = None,
) -> NutritionImportDraft:
    if (
        not _KEY.fullmatch(upload_key)
        or not _IDENTIFIER.fullmatch(parser_version)
        or (adapter_id is not None and not _IDENTIFIER.fullmatch(adapter_id))
    ):
        raise NutritionDraftError("invalid_metadata", 422)
    if document.source.source_format == "csv":
        validate_csv_upload(
            source, filename=filename, content_type=content_type, delimiter=delimiter
        )
    elif document.source.source_format == "pdf":
        validate_pdf_upload(source, filename=filename, content_type=content_type)
    else:
        raise NutritionDraftError("unsupported_format", 415)
    source_sha256 = _digest(source)
    data = document.model_dump(
        mode="json", exclude_defaults=isinstance(document, NutritionImportV3)
    )
    if isinstance(document, NutritionImportV3):
        for row in data["rows"]:
            row.setdefault("diagnostics", [])
    serialized = _canonical(data)
    validate_adapter_result(
        serialized,
        provider=document.source.provider,
        adapter_version=document.source.adapter_version,
        source_format=document.source.source_format,
    )
    document_sha256 = _digest(serialized)
    fingerprint_data = {
        "content": source_sha256,
        "document": document_sha256,
        "parser": parser_version,
    }
    if adapter_id is not None:
        fingerprint_data["adapter_id"] = adapter_id
    fingerprint = _digest(_canonical(fingerprint_data))
    key_hash = _digest(upload_key.encode("ascii"))
    _lock_user(db, user)
    existing = (
        db.query(NutritionImportDraft)
        .filter_by(owner_user_id=user.id, upload_key_hash=key_hash)
        .first()
    )
    if existing is not None:
        legacy_fingerprint = _digest(
            _canonical(
                {
                    "content": source_sha256,
                    "document": document_sha256,
                    "parser": parser_version,
                }
            )
        )
        if existing.upload_fingerprint != fingerprint and not (
            existing.adapter_id is None and existing.upload_fingerprint == legacy_fingerprint
        ):
            raise NutritionDraftError("upload_key_conflict", 409)
        return get_nutrition_import_draft(db, user, existing.id, allow_confirmed=True)
    active_count = (
        db.query(NutritionImportDraft.id)
        .filter(
            NutritionImportDraft.owner_user_id == user.id,
            NutritionImportDraft.status == "pending",
            NutritionImportDraft.expires_at > _now(),
        )
        .count()
    )
    if active_count >= MAX_ACTIVE_DRAFTS:
        raise NutritionDraftError("draft_limit", 429)
    now = _now()
    draft = NutritionImportDraft(
        id=str(uuid4()),
        owner_user_id=user.id,
        source_sha256=source_sha256,
        upload_key_hash=key_hash,
        upload_fingerprint=fingerprint,
        provider=document.source.provider,
        source=document.source.source,
        parser_version=parser_version,
        adapter_id=adapter_id,
        schema_version=document.schema_version,
        status="pending",
        revision=1,
        document_sha256=document_sha256,
        document=data,
        skipped_rows=[],
        resolutions={},
        created_at=now,
        expires_at=now + DRAFT_TTL,
    )
    db.add(draft)
    db.flush()
    return draft


def set_resolutions(
    db: Session,
    user: User,
    draft_id: str,
    *,
    revision: int,
    matches: dict[int, int],
    skipped_rows: list[int],
) -> NutritionImportDraft:
    _lock_user(db, user)
    draft = get_nutrition_import_draft(db, user, draft_id, lock=True)
    if draft.revision != revision:
        raise NutritionDraftError("stale_revision", 409)
    count = len(draft.document["rows"])
    if (
        any(type(index) is not int or index < 0 or index >= count for index in skipped_rows)
        or len(set(skipped_rows)) != len(skipped_rows)
        or any(type(index) is not int or index < 0 or index >= count for index in matches)
        or any(type(food_id) is not int or food_id <= 0 for food_id in matches.values())
        or bool(set(matches) & set(skipped_rows))
    ):
        raise NutritionDraftError("invalid_rows", 422)
    cache = _PlanningCache()
    for index, food_id in matches.items():
        _planned_entry(db, user, draft.document["rows"][index], food_id, cache=cache)
    draft.skipped_rows = sorted(skipped_rows)
    draft.resolutions = {str(index): food_id for index, food_id in sorted(matches.items())}
    draft.revision += 1
    db.flush()
    return draft


def set_skipped_rows(
    db: Session, user: User, draft_id: str, *, revision: int, skipped_rows: list[int]
) -> NutritionImportDraft:
    return set_resolutions(
        db, user, draft_id, revision=revision, matches={}, skipped_rows=skipped_rows
    )


def _planned_entry(
    db: Session, user: User, row: dict, food_id: int, *, cache: _PlanningCache
) -> FoodDiaryEntry:
    if any(issue["severity"] == "error" for issue in row["diagnostics"]):
        raise NutritionDraftError("invalid_row", 422)
    try:
        payload = FoodDiaryEntryCreate(
            food_id=food_id,
            diary_date=row["diary_date"],
            meal_type=row["meal_type"],
            amount=row["quantity"],
            amount_unit=row["amount_unit"],
        )
        if payload.diary_date not in cache.checked_dates:
            _validate_diary_date(user, payload.diary_date)
            _ensure_day_accepts_entries(db, user, payload.diary_date)
            cache.checked_dates.add(payload.diary_date)
        if food_id not in cache.foods:
            cache.foods[food_id] = _visible_food(db, user, food_id)
        calculation = _calculate_amount(cache.foods[food_id], payload.amount, payload.amount_unit)
        food = cache.foods[food_id]
    except FoodDiaryError, ValidationError:
        raise NutritionDraftError("invalid_match", 422) from None
    entry = FoodDiaryEntry(
        user_id=user.id,
        diary_date=payload.diary_date,
        meal_type=payload.meal_type,
        logged_at=None,
        amount=payload.amount,
        amount_unit=payload.amount_unit,
    )
    _copy_food_snapshot(entry, food)
    entry.weight_g = calculation.weight_g
    _set_nutrition_amount(entry, calculation)
    return entry


def _entry_action(entry: FoodDiaryEntry) -> dict:
    fields = (
        "food_id",
        "food_name",
        "food_brand",
        "diary_date",
        "meal_type",
        "amount",
        "amount_unit",
        "weight_g",
        "energy_kcal_per_100g",
        "protein_g_per_100g",
        "fat_g_per_100g",
        "carbs_g_per_100g",
        "fiber_g_per_100g",
        "nutrition_basis_kind",
        "nutrition_basis_amount",
        "nutrition_basis_unit",
        "nutrition_snapshot",
        "nutrition_amount",
        "serving_amount",
        "serving_unit",
        "serving_weight_g",
    )
    numeric_fields = {
        "amount",
        "weight_g",
        "energy_kcal_per_100g",
        "protein_g_per_100g",
        "fat_g_per_100g",
        "carbs_g_per_100g",
        "fiber_g_per_100g",
        "nutrition_basis_amount",
        "serving_amount",
        "serving_weight_g",
    }
    action = {"kind": "create_diary_entry"}
    for field_name in fields:
        value = getattr(entry, field_name)
        if field_name in numeric_fields and value is not None:
            action[field_name] = format(Decimal(str(value)).normalize(), "f")
        else:
            action[field_name] = str(value) if isinstance(value, date) else value
    return action


def nutrition_import_preview(db: Session, user: User, draft_id: str) -> dict:
    draft = get_nutrition_import_draft(db, user, draft_id)
    document = draft.document
    skipped = set(draft.skipped_rows)
    rows = []
    cache = _PlanningCache()
    for index, row in enumerate(document["rows"]):
        issues = [issue["code"] for issue in row["diagnostics"] if issue["severity"] == "error"]
        issues.extend(
            f"missing_{key}"
            for key in ("diary_date", "meal_type", "quantity", "amount_unit")
            if row.get(key) is None
        )
        if row.get("amount_unit") not in {None, "g", "ml", "serving"}:
            issues.append("unsupported_amount_unit")
        action = None
        food_id = draft.resolutions.get(str(index))
        if index in skipped:
            state = "skipped"
        elif issues:
            state = "invalid"
        elif food_id is None:
            state = "manual_resolution_required"
        else:
            try:
                action = _entry_action(_planned_entry(db, user, row, food_id, cache=cache))
                state = "matched"
            except NutritionDraftError:
                state = "invalid"
                issues.append("match_unavailable")
        rows.append(
            {"index": index, "status": state, "source": row, "action": action, "issues": issues}
        )
    signature = _digest(
        _canonical(
            {
                "draft_id": draft.id,
                "revision": draft.revision,
                "document": draft.document_sha256,
                "rows": [{"status": row["status"], "action": row["action"]} for row in rows],
            }
        )
    )
    return {
        "id": draft.id,
        "revision": draft.revision,
        "expires_at": draft.expires_at.isoformat() + "Z",
        "schema_version": draft.schema_version,
        "parser_version": draft.parser_version,
        "content_sha256": draft.source_sha256,
        "completeness": document["completeness"],
        "source": document["source"],
        "rows": rows,
        "original_totals": document["original_totals"],
        "original_summaries": document.get("original_summaries", []),
        "original_detail_cells": document.get("original_detail_cells", []),
        "diagnostics": document["diagnostics"],
        "preview_signature": signature,
    }


def confirm_nutrition_import_draft(
    db: Session,
    user: User,
    draft_id: str,
    *,
    revision: int,
    preview_signature: str,
    confirm_key: str,
    confirmed: bool,
) -> dict:
    if confirmed is not True or not _KEY.fullmatch(confirm_key):
        raise NutritionDraftError("confirmation_required", 422)
    fingerprint = _digest(
        _canonical(
            {
                "draft_id": draft_id,
                "revision": revision,
                "preview_signature": preview_signature,
            }
        )
    )
    key_hash = _digest(confirm_key.encode("ascii"))
    _lock_user(db, user)
    draft = get_nutrition_import_draft(db, user, draft_id, lock=True, allow_confirmed=True)
    if draft.status == "confirmed":
        if draft.confirm_key_hash != key_hash or draft.confirm_fingerprint != fingerprint:
            raise NutritionDraftError("confirmation_conflict", 409)
        if draft.receipt is None:
            raise NutritionDraftError("draft_changed", 409)
        return draft.receipt
    if draft.revision != revision:
        raise NutritionDraftError("stale_revision", 409)
    if (
        db.query(NutritionImportDraft.id)
        .filter(
            NutritionImportDraft.owner_user_id == user.id,
            NutritionImportDraft.confirm_key_hash == key_hash,
            NutritionImportDraft.id != draft.id,
        )
        .first()
    ):
        raise NutritionDraftError("confirmation_conflict", 409)
    food_ids = sorted(set(draft.resolutions.values()))
    if food_ids:
        db.query(Food).filter(Food.id.in_(food_ids)).order_by(
            Food.id
        ).with_for_update().populate_existing().all()
    preview = nutrition_import_preview(db, user, draft_id)
    if preview["preview_signature"] != preview_signature:
        raise NutritionDraftError("preview_changed", 409)
    rows = preview["rows"]
    if any(row["status"] not in {"matched", "skipped"} for row in rows):
        raise NutritionDraftError("unresolved_rows", 409)
    selected = [row for row in rows if row["status"] == "matched"]
    if not selected:
        raise NutritionDraftError("nothing_to_import", 409)
    keys = [f"nutrition-import:{draft.source_sha256}:{row['index']}" for row in selected]
    if (
        db.query(FoodDiaryEntry.id)
        .filter(
            FoodDiaryEntry.user_id == user.id,
            FoodDiaryEntry.idempotency_key.in_(keys),
        )
        .first()
    ):
        raise NutritionDraftError("duplicate_import", 409)
    entries = []
    cache = _PlanningCache()
    for row, key in zip(selected, keys, strict=True):
        entry = _planned_entry(
            db, user, row["source"], draft.resolutions[str(row["index"])], cache=cache
        )
        if _entry_action(entry) != row["action"]:
            raise NutritionDraftError("preview_changed", 409)
        entry.idempotency_key = key
        entry.request_fingerprint = _digest(_canonical(row["action"]))
        db.add(entry)
        entries.append(entry)
    db.flush()
    receipt = {"entry_ids": [entry.id for entry in entries], "preview_signature": preview_signature}
    draft.status = "confirmed"
    draft.confirm_key_hash = key_hash
    draft.confirm_fingerprint = fingerprint
    draft.receipt = receipt
    db.flush()
    return receipt


def cancel_nutrition_import_draft(db: Session, user: User, draft_id: str, *, revision: int) -> None:
    _lock_user(db, user)
    draft = get_nutrition_import_draft(db, user, draft_id, lock=True)
    if draft.revision != revision:
        raise NutritionDraftError("stale_revision", 409)
    draft.status = "cancelled"
    draft.document = {}
    draft.skipped_rows = []
    draft.resolutions = {}
    draft.catalog_confirm_key_hash = None
    draft.catalog_confirm_fingerprint = None
    draft.catalog_receipt = None
    db.flush()


def expire_nutrition_import_drafts(
    db: Session, *, now: datetime | None = None, limit: int = 100
) -> int:
    rows = (
        db.query(NutritionImportDraft)
        .filter(NutritionImportDraft.expires_at <= (now or _now()))
        .order_by(NutritionImportDraft.expires_at, NutritionImportDraft.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
        .all()
    )
    for row in rows:
        db.delete(row)
    return len(rows)
