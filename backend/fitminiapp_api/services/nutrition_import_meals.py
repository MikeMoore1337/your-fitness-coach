from __future__ import annotations

from collections import defaultdict

from sqlalchemy import or_
from sqlalchemy.orm import Session

from fitminiapp_api.models.food import Food
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.nutrition_import import ImportFoodRow, OriginalDetailCell, OriginalTotal
from fitminiapp_api.schemas.nutrition_import_engine import (
    RecurringMealComparison,
    RecurringMealConfirmRequest,
    RecurringMealReview,
    RecurringMealReviewRequest,
)
from fitminiapp_api.schemas.nutrition_power import NutritionMealTemplateCreate
from fitminiapp_api.services.foods import FoodError, calculate_food_amount, get_visible_food
from fitminiapp_api.services.nutrition_import_drafts import (
    NutritionDraftError,
    _canonical,
    _digest,
    _lock_user,
    get_nutrition_import_draft,
)
from fitminiapp_api.services.nutrition_power import (
    create_meal_template,
    find_identical_meal_template,
    serialize_meal_template,
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
        total.coordinates.model_dump_json(): total
        for total in totals
        if total.scope in {"entry", "unknown"}
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
                    "source_index": index,
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


def review_recurring_meal(
    db: Session, user: User, draft_id: str, payload: RecurringMealReviewRequest
) -> RecurringMealReview:
    proposal = recurring_import_meals(db, user, draft_id)
    occurrence = next(
        (
            occurrence
            for meal in proposal["items"]
            if meal["meal_type"] == payload.meal_type
            for occurrence in meal["occurrences"]
            if occurrence["date"] == payload.date
        ),
        None,
    )
    if occurrence is None:
        raise NutritionDraftError("meal_unavailable", 409)
    source_items = {item["source_index"]: item for item in occurrence["items"]}
    if not any(item.source_index is not None for item in payload.items):
        raise NutritionDraftError("invalid_rows", 422)
    comparisons = []
    fields = {
        "energy_kcal": "energy_kcal",
        "protein_g": "protein_g",
        "fat_g": "fat_g",
        "carbohydrate_g": "carbs_g",
    }
    for item in payload.items:
        source = source_items.get(item.source_index) if item.source_index is not None else None
        if item.source_index is not None and source is None:
            raise NutritionDraftError("invalid_rows", 422)
        try:
            food = get_visible_food(db, user, item.food_id)
            calculated = calculate_food_amount(food, item.amount, item.amount_unit)
        except FoodError:
            raise NutritionDraftError("invalid_meal_item", 422) from None
        if calculated.energy_kcal is None:
            raise NutritionDraftError("invalid_meal_item", 422)
        catalog = {key: getattr(calculated, attr) for key, attr in fields.items()}
        comparable = (
            source is not None
            and source["food_id"] == item.food_id
            and source["source"].quantity == item.amount
            and source["source"].amount_unit == item.amount_unit
            and source["original_total"] is not None
            and source["original_total"].scope == "entry"
        )
        comparison = {}
        for key, value in catalog.items():
            fact = getattr(source["original_total"].facts, key) if comparable and source else None
            comparison[key] = (
                "unknown"
                if fact is None
                or fact.value is None
                or value is None
                or fact.unit != ("kcal" if key == "energy_kcal" else "g")
                else "equal"
                if fact.value == value
                else "different"
            )
        comparisons.append(
            {"item": item, "source": source, "catalog_nutrition": catalog, "comparison": comparison}
        )
    checked = [RecurringMealComparison.model_validate(item) for item in comparisons]
    unsigned = {
        "draft_id": draft_id,
        "selection": payload.model_dump(mode="json"),
        "items": [item.model_dump(mode="json") for item in checked],
    }
    signature = _digest(_canonical(unsigned))
    return RecurringMealReview(items=checked, preview_signature=signature)


def confirm_recurring_meal(
    db: Session, user: User, draft_id: str, payload: RecurringMealConfirmRequest
) -> dict:
    _lock_user(db, user)
    get_nutrition_import_draft(db, user, draft_id, lock=True, allow_confirmed=True)
    db.query(Food.id).filter(Food.id.in_({item.food_id for item in payload.items})).order_by(
        Food.id
    ).with_for_update().all()
    review_request = RecurringMealReviewRequest.model_validate(
        payload.model_dump(exclude={"preview_signature", "confirmed", "acknowledge_nutrition"})
    )
    review = review_recurring_meal(db, user, draft_id, review_request)
    if review.preview_signature != payload.preview_signature:
        raise NutritionDraftError("preview_changed", 409)
    data = NutritionMealTemplateCreate.model_validate(
        {
            "name": payload.name,
            "items": [
                {"food_id": item.food_id, "amount": item.amount, "amount_unit": item.amount_unit}
                for item in payload.items
            ],
        }
    )
    existing = find_identical_meal_template(db, user, data.items)
    if existing is not None:
        return {"template": serialize_meal_template(db, user, existing), "existing": True}
    return {"template": create_meal_template(db, user, data), "existing": False}
