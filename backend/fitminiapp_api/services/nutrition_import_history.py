"""Private, non-writing preparation of FatSecret diary history."""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from fitminiapp_api.models.food_diary import FoodDiaryDayStatus, FoodDiaryEntry
from fitminiapp_api.models.nutrition_import import NutritionImportDraft
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.nutrition_import import (
    NutritionImportV3,
    OriginalTotal,
    SourceCoordinates,
)
from fitminiapp_api.schemas.nutrition_import_engine import (
    HistoryConfirmRequest,
    HistoryReviewRequest,
)
from fitminiapp_api.services.diary_nutrition import diary_entry_nutrition
from fitminiapp_api.services.food_diary import FoodDiaryError, _validate_diary_date
from fitminiapp_api.services.nutrition_import_drafts import (
    NutritionDraftError,
    _canonical,
    _digest,
    _entry_action,
    _lock_user,
    get_nutrition_import_draft,
)


def _coordinates(value: SourceCoordinates) -> tuple:
    return (value.section, value.section_kind, value.page, value.row)


def _number(value: Decimal | None) -> str | None:
    return format(value.normalize(), "f") if value is not None else None


def _source_amount(total: OriginalTotal | None) -> dict[str, Decimal | None]:
    fields = {
        "energy_kcal": ("energy_kcal", "kcal"),
        "protein_g": ("protein_g", "g"),
        "fat_g": ("fat_g", "g"),
        "carbs_g": ("carbohydrate_g", "g"),
        "fiber_g": ("fiber_g", "g"),
    }
    result = {}
    for target, (source, unit) in fields.items():
        fact = getattr(total.facts, source) if total is not None else None
        result[target] = (
            fact.value
            if fact is not None and fact.evidence == "read" and fact.unit == unit
            else None
        )
    return result


def prepare_history_rows(document: NutritionImportV3) -> list[dict]:
    """Associate source facts and flag identical candidates, not proven duplicate identities."""
    if document.source.provider != "fatsecret":
        raise ValueError("unsupported history source")

    totals = defaultdict(list)
    for source_total in document.original_totals:
        if source_total.scope in {"entry", "unknown"}:
            totals[_coordinates(source_total.coordinates)].append(source_total)
    cells = defaultdict(list)
    for cell in document.original_detail_cells:
        cells[_coordinates(cell.coordinates)].append(cell)

    rows = []
    for index, row in enumerate(document.rows):
        candidates = totals[_coordinates(row.coordinates)]
        total: OriginalTotal | None = candidates[0] if len(candidates) == 1 else None
        if total is not None and (
            total.diary_date != row.diary_date or total.meal_type != row.meal_type
        ):
            total = None
        facts = total.facts if total is not None else None
        identity = {
            "provider": document.source.provider,
            "date": row.diary_date.isoformat() if row.diary_date else None,
            "meal": row.meal_type,
            "food": row.food.model_dump(mode="json"),
            "quantity": _number(row.quantity),
            "unit": row.amount_unit,
            "source_unit": row.source_unit if row.amount_unit is None else None,
            "serving_label": row.serving_label if row.amount_unit is None else None,
            "serving_measure": row.serving_measure.model_dump(mode="json")
            if row.serving_measure
            else None,
            "extra_cells": [
                {
                    "column": cell.source_column,
                    "value": _number(cell.fact.value)
                    if cell.fact.value is not None
                    else cell.source_value,
                    "field": cell.nutrient_field,
                    "mapping": cell.mapping_evidence,
                }
                for cell in sorted(
                    cells[_coordinates(row.coordinates)], key=lambda c: c.source_column
                )
            ],
            "facts": {
                name: {
                    "value": _number(fact.value),
                    "unit": fact.unit,
                    "evidence": fact.evidence,
                }
                if fact is not None
                else None
                for name, fact in facts
            }
            if facts is not None
            else None,
        }
        rows.append(
            {
                "index": index,
                "source": row,
                "original_total": total,
                "nutrition_amount": _source_amount(total),
                "fingerprint": _digest(_canonical(identity)) if total is not None else None,
                "ambiguous_facts": total is None,
            }
        )
    counts = Counter(row["fingerprint"] for row in rows if row["fingerprint"] is not None)
    for item in rows:
        item["ambiguous_duplicate"] = bool(item["fingerprint"] and counts[item["fingerprint"]] > 1)
    return rows


def history_preview(db: Session, user: User, draft_id: str) -> dict:
    draft = get_nutrition_import_draft(db, user, draft_id, allow_confirmed=True)
    if draft.provider != "fatsecret" or draft.schema_version != "nutrition-import-v3":
        raise NutritionDraftError("adapter_unavailable", 415)
    document = NutritionImportV3.model_validate(draft.document)
    rows = prepare_history_rows(document)
    cells = defaultdict(list)
    for cell in document.original_detail_cells:
        cells[_coordinates(cell.coordinates)].append(cell)
    for row in rows:
        row.pop("fingerprint")
        row["original_detail_cells"] = cells[_coordinates(row["source"].coordinates)]

    dates = sorted({row["source"].diary_date for row in rows if row["source"].diary_date})
    contexts = {
        (row["source"].diary_date, row["source"].meal_type)
        for row in rows
        if row["source"].diary_date and row["source"].meal_type
    }
    meals = defaultdict(list)
    state = []
    statuses: list[tuple[str, str]] = []
    for start in range(0, len(dates), 500):
        statuses.extend(
            (status.diary_date.isoformat(), status.status)
            for status in db.query(FoodDiaryDayStatus)
            .filter(
                FoodDiaryDayStatus.user_id == user.id,
                FoodDiaryDayStatus.diary_date.in_(dates[start : start + 500]),
            )
            .order_by(FoodDiaryDayStatus.diary_date)
            .all()
        )
        entries = (
            db.query(FoodDiaryEntry)
            .filter(
                FoodDiaryEntry.user_id == user.id,
                FoodDiaryEntry.diary_date.in_(dates[start : start + 500]),
            )
            .order_by(FoodDiaryEntry.diary_date, FoodDiaryEntry.meal_type, FoodDiaryEntry.id)
            .all()
        )
        for entry in entries:
            context = (entry.diary_date, entry.meal_type)
            if context not in contexts:
                continue
            state.append(
                {
                    "id": entry.id,
                    "updated_at": entry.updated_at.isoformat(),
                    "logged_at": entry.logged_at.isoformat() if entry.logged_at else None,
                    "nutrition_source": entry.nutrition_source,
                    "idempotency_key": entry.idempotency_key,
                    "request_fingerprint": entry.request_fingerprint,
                    "action": _entry_action(entry),
                }
            )
            nutrition = diary_entry_nutrition(entry)
            meals[context].append(
                {
                    "id": entry.id,
                    "food_name": entry.food_name,
                    "amount": entry.amount,
                    "amount_unit": entry.amount_unit,
                    "serving_unit": entry.serving_unit,
                    "nutrition": {
                        "energy_kcal": nutrition.energy_kcal,
                        "protein_g": nutrition.protein_g,
                        "fat_g": nutrition.fat_g,
                        "carbs_g": nutrition.carbs_g,
                        "fiber_g": nutrition.fiber_g,
                    },
                }
            )
    return {
        "revision": draft.revision,
        "preview_signature": _digest(
            _canonical(
                {
                    "draft_id": draft.id,
                    "document": draft.document_sha256,
                    "revision": draft.revision,
                    "diary": state,
                    "statuses": statuses,
                }
            )
        ),
        "dates": dates,
        "rows": rows,
        "existing_meals": [
            {"date": day, "meal_type": meal, "entries": entries}
            for (day, meal), entries in sorted(meals.items())
        ],
    }


def review_history(db: Session, user: User, draft_id: str, request: HistoryReviewRequest) -> dict:
    preview = history_preview(db, user, draft_id)
    if preview["revision"] != request.revision:
        raise NutritionDraftError("stale_revision", 409)
    if preview["preview_signature"] != request.preview_signature:
        raise NutritionDraftError("preview_changed", 409)
    if (
        request.date_from not in preview["dates"]
        or request.date_to not in preview["dates"]
        or request.date_from > request.date_to
    ):
        raise NutritionDraftError("invalid_rows", 422)

    indexes = request.selected_rows
    decisions = {decision.index: decision.action for decision in request.decisions}
    if len(indexes) != len(set(indexes)) or len(decisions) != len(request.decisions):
        raise NutritionDraftError("invalid_rows", 422)
    rows = preview["rows"]
    in_range = {
        row["index"]
        for row in rows
        if row["source"].diary_date is not None
        and request.date_from <= row["source"].diary_date <= request.date_to
    }
    if request.mode == "manual":
        selected = set(indexes)
        if not selected or not selected <= in_range:
            raise NutritionDraftError("invalid_rows", 422)
    else:
        if indexes:
            raise NutritionDraftError("invalid_rows", 422)
        selected = in_range
    if not set(decisions) <= selected:
        raise NutritionDraftError("invalid_rows", 422)

    existing = {
        (meal["date"], meal["meal_type"]): meal["entries"] for meal in preview["existing_meals"]
    }
    draft = get_nutrition_import_draft(db, user, draft_id, allow_confirmed=True)
    source_rows = prepare_history_rows(NutritionImportV3.model_validate(draft.document))
    previous_fingerprints = {
        fingerprint
        for (fingerprint,) in db.query(FoodDiaryEntry.request_fingerprint)
        .filter(
            FoodDiaryEntry.user_id == user.id,
            FoodDiaryEntry.diary_date.between(request.date_from, request.date_to),
            FoodDiaryEntry.idempotency_key.like("nutrition-history:v1:%"),
        )
        .all()
        if fingerprint is not None
    }
    statuses = {
        status.diary_date: status.status
        for status in db.query(FoodDiaryDayStatus)
        .filter(
            FoodDiaryDayStatus.user_id == user.id,
            FoodDiaryDayStatus.diary_date.between(request.date_from, request.date_to),
        )
        .all()
    }
    plan = []
    for row in rows:
        index, source = row["index"], row["source"]
        if index not in selected:
            plan.append(
                {"index": index, "action": "skip", "reason": "outside_selection", "conflict": False}
            )
            continue
        context = (source.diary_date, source.meal_type)
        matches = existing.get(context, [])
        source_name = " ".join(source.food.name.split()).casefold()
        conflict = (
            bool(row["ambiguous_duplicate"])
            or source_rows[index]["fingerprint"] in previous_fingerprints
            or any(
                " ".join(entry["food_name"].split()).casefold() == source_name for entry in matches
            )
        )
        decision = decisions.get(index)
        reason = None
        if decision == "skip":
            action, reason = "skip", "user_skipped"
        elif request.mode == "keep" and matches:
            action, reason = "skip", "existing_meal"
        else:
            try:
                amount = source.quantity
                amount_fits = (
                    amount is not None
                    and amount <= Decimal("9999999.999")
                    and amount == amount.quantize(Decimal("0.001"))
                )
            except InvalidOperation:
                amount_fits = False
            try:
                if source.diary_date is None:
                    raise FoodDiaryError("unknown date")
                _validate_diary_date(user, source.diary_date)
                valid_date = True
            except FoodDiaryError:
                valid_date = False
            invalid = (
                not valid_date
                or source.meal_type is None
                or source.amount_unit not in {"g", "ml", "piece", "serving"}
                or not amount_fits
                or row["ambiguous_facts"]
                or row["nutrition_amount"]["energy_kcal"] is None
                or any(item.severity == "error" for item in source.diagnostics)
            )
            if statuses.get(source.diary_date) in {"complete", "fasted"}:
                action, reason = "invalid", "day_status_conflict"
            elif invalid:
                action, reason = "invalid", "source_incomplete"
            else:
                if conflict and decision is None:
                    action, reason = "conflict", "explicit_decision_required"
                else:
                    action = "add"
        plan.append({"index": index, "action": action, "reason": reason, "conflict": conflict})
    review_data = request.model_dump(mode="json")
    review_data["selected_rows"] = sorted(indexes)
    review_data["decisions"] = sorted(review_data["decisions"], key=lambda item: item["index"])
    return {
        "preview_signature": request.preview_signature,
        "review_signature": _digest(_canonical({"request": review_data, "rows": plan})),
        "rows": plan,
    }


def confirm_history(db: Session, user: User, draft_id: str, request: HistoryConfirmRequest) -> dict:
    review_request = HistoryReviewRequest.model_validate(
        request.model_dump(exclude={"review_signature", "confirm_key", "confirmed"})
    )
    request_data = review_request.model_dump(mode="json")
    request_data["selected_rows"] = sorted(request_data["selected_rows"])
    request_data["decisions"] = sorted(request_data["decisions"], key=lambda item: item["index"])
    confirm_fingerprint = _digest(
        _canonical(
            {
                "kind": "fatsecret-history-v1",
                "draft_id": draft_id,
                "request": request_data,
                "review_signature": request.review_signature,
            }
        )
    )
    key_hash = _digest(request.confirm_key.encode("ascii"))
    _lock_user(db, user)
    draft = get_nutrition_import_draft(db, user, draft_id, lock=True, allow_confirmed=True)
    if draft.status == "confirmed":
        if draft.confirm_key_hash != key_hash or draft.confirm_fingerprint != confirm_fingerprint:
            raise NutritionDraftError("confirmation_conflict", 409)
        if draft.receipt is None or "added" not in draft.receipt:
            raise NutritionDraftError("draft_changed", 409)
        return draft.receipt
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
    review = review_history(db, user, draft_id, review_request)
    if review["review_signature"] != request.review_signature:
        raise NutritionDraftError("preview_changed", 409)
    if any(row["action"] in {"conflict", "invalid"} for row in review["rows"]):
        raise NutritionDraftError("unresolved_rows", 409)
    document = NutritionImportV3.model_validate(draft.document)
    rows = prepare_history_rows(document)
    cells = defaultdict(list)
    for cell in document.original_detail_cells:
        cells[_coordinates(cell.coordinates)].append(cell.model_dump(mode="json"))
    selected_dates = sorted(
        {
            rows[item["index"]]["source"].diary_date
            for item in review["rows"]
            if item["action"] == "add"
        }
    )
    existing_keys: list[str] = []
    for start in range(0, len(selected_dates), 500):
        existing_keys.extend(
            key
            for (key,) in db.query(FoodDiaryEntry.idempotency_key)
            .filter(
                FoodDiaryEntry.user_id == user.id,
                FoodDiaryEntry.diary_date.in_(selected_dates[start : start + 500]),
                FoodDiaryEntry.idempotency_key.like("nutrition-history:v1:%"),
            )
            .all()
        )
    used = set(existing_keys)
    created = []
    for item in review["rows"]:
        if item["action"] != "add":
            continue
        row = rows[item["index"]]
        source, total, fingerprint = row["source"], row["original_total"], row["fingerprint"]
        if (
            source.diary_date is None
            or source.quantity is None
            or total is None
            or fingerprint is None
        ):
            raise NutritionDraftError("invalid_rows", 422)
        prefix = f"nutrition-history:v1:{fingerprint}:"
        ordinal = 0
        while f"{prefix}{ordinal}" in used:
            ordinal += 1
        key = f"{prefix}{ordinal}"
        used.add(key)
        unit = "serving" if source.amount_unit == "piece" else source.amount_unit
        entry = FoodDiaryEntry(
            user_id=user.id,
            diary_date=source.diary_date,
            meal_type=source.meal_type,
            logged_at=None,
            entry_kind="food",
            nutrition_source="fatsecret",
            food_name=source.food.name,
            food_brand=source.food.brand,
            amount=source.quantity,
            amount_unit=unit,
            weight_g=source.quantity if unit == "g" else None,
            serving_amount=Decimal("1") if unit == "serving" else None,
            serving_unit=("piece" if source.amount_unit == "piece" else "serving")
            if unit == "serving"
            else None,
            serving_weight_g=None,
            nutrition_snapshot={
                "source": "fatsecret",
                "source_record_fingerprint": fingerprint,
                "source_provenance": document.source.model_dump(mode="json"),
                "source_row": source.model_dump(mode="json"),
                "source_unit": source.source_unit,
                "serving_label": source.serving_label,
                "original_total": total.model_dump(mode="json"),
                "original_detail_cells": cells[_coordinates(source.coordinates)],
            },
            nutrition_amount={
                key: str(value) if value is not None else None
                for key, value in row["nutrition_amount"].items()
            },
            idempotency_key=key,
            request_fingerprint=fingerprint,
        )
        db.add(entry)
        created.append(entry)
    db.flush()
    receipt = {
        "added": len(created),
        "skipped": sum(
            item["action"] == "skip" and item["reason"] != "outside_selection"
            for item in review["rows"]
        ),
        "conflicts": sum(item["conflict"] for item in review["rows"]),
        "entry_ids": [entry.id for entry in created],
        "review_signature": request.review_signature,
    }
    draft.status = "confirmed"
    draft.confirm_key_hash = key_hash
    draft.confirm_fingerprint = confirm_fingerprint
    draft.receipt = receipt
    db.flush()
    return receipt
