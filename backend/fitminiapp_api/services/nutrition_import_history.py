"""Private, non-writing preparation of FatSecret diary history."""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.nutrition_import import (
    NutritionImportV3,
    OriginalTotal,
    SourceCoordinates,
)
from fitminiapp_api.services.diary_nutrition import diary_entry_nutrition
from fitminiapp_api.services.nutrition_import_drafts import (
    NutritionDraftError,
    _canonical,
    _digest,
    get_nutrition_import_draft,
)


def _coordinates(value: SourceCoordinates) -> tuple:
    return (value.section, value.section_kind, value.page, value.row)


def _number(value: Decimal | None) -> str | None:
    return format(value.normalize(), "f") if value is not None else None


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
            "source_unit": row.source_unit,
            "serving_label": row.serving_label,
            "serving_measure": row.serving_measure.model_dump(mode="json")
            if row.serving_measure
            else None,
            "extra_cells": [
                {
                    "column": cell.source_column,
                    "value": cell.source_value,
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
    for start in range(0, len(dates), 500):
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
            nutrition = diary_entry_nutrition(entry)
            meals[context].append(
                {
                    "id": entry.id,
                    "food_name": entry.food_name,
                    "amount": entry.amount,
                    "amount_unit": entry.amount_unit,
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
        "dates": dates,
        "rows": rows,
        "existing_meals": [
            {"date": day, "meal_type": meal, "entries": entries}
            for (day, meal), entries in sorted(meals.items())
        ],
    }
