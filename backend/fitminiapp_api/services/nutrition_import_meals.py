from __future__ import annotations

from collections import defaultdict

from sqlalchemy import or_
from sqlalchemy.orm import Session

from fitminiapp_api.models.food import Food
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.nutrition_import import ImportFoodRow, OriginalDetailCell, OriginalTotal
from fitminiapp_api.services.nutrition_import_drafts import (
    NutritionDraftError,
    get_nutrition_import_draft,
)


def recurring_import_meals(db: Session, user: User, draft_id: str) -> dict:
    draft = get_nutrition_import_draft(db, user, draft_id, allow_confirmed=True)
    if draft.provider != "fatsecret" or draft.catalog_receipt is None:
        raise NutritionDraftError("catalog_confirmation_required", 409)

    rows = [ImportFoodRow.model_validate(row) for row in draft.document["rows"]]
    totals = [OriginalTotal.model_validate(total) for total in draft.document["original_totals"]]
    cells: dict[str, list[OriginalDetailCell]] = defaultdict(list)
    for value in draft.document.get("original_detail_cells", []):
        cell = OriginalDetailCell.model_validate(value)
        cells[cell.coordinates.model_dump_json()].append(cell)
    # A row without context could belong to any meal; do not suggest an incomplete composition.
    if any(row.diary_date is None or row.meal_type is None for row in rows):
        return {
            "observed_days": len({row.diary_date for row in rows if row.diary_date}),
            "items": [],
        }

    resolved = {
        item["index"]: item["food_id"]
        for item in draft.catalog_receipt["rows"]
        if item["outcome"] in {"publish", "reuse"} and item["food_id"] is not None
    }
    visible_ids = {
        food_id
        for (food_id,) in db.query(Food.id)
        .filter(
            Food.id.in_(set(resolved.values())),
            Food.status == "active",
            or_(Food.food_type != "user", Food.owner_user_id == user.id),
        )
        .all()
    }
    resolved = {index: food_id for index, food_id in resolved.items() if food_id in visible_ids}
    facts = {
        total.coordinates.model_dump_json(): total for total in totals if total.scope == "unknown"
    }
    meals: dict[tuple, list] = defaultdict(list)
    for index, row in enumerate(rows):
        meals[(row.diary_date, row.meal_type)].append((index, row))

    groups: dict[tuple, list] = defaultdict(list)
    for (day, meal_type), entries in sorted(meals.items()):
        if any(index not in resolved for index, _ in entries):
            continue
        identity = tuple(sorted(resolved[index] for index, _ in entries))
        occurrence = {
            "date": day,
            "items": [
                {
                    "food_id": resolved[index],
                    "source": row,
                    "original_total": facts.get(row.coordinates.model_dump_json()),
                    "original_detail_cells": cells.get(row.coordinates.model_dump_json(), []),
                }
                for index, row in entries
            ],
        }
        groups[(meal_type, identity)].append(occurrence)

    return {
        "observed_days": len({row.diary_date for row in rows}),
        "items": [
            {"meal_type": meal_type, "repeat_days": len(occurrences), "occurrences": occurrences}
            for (meal_type, _), occurrences in sorted(groups.items())
            if len(occurrences) >= 2
        ],
    }
