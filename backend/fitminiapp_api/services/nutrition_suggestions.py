from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Literal, cast

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from fitminiapp_api.models.food import Food
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.recipe import Recipe
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.food import FoodNutrientsInput
from fitminiapp_api.schemas.food_diary import (
    DiaryAmountUnit,
    FoodDiaryDayResponse,
    FoodDiaryNutrition,
)
from fitminiapp_api.schemas.nutrition_power import (
    FoodDiaryBatchResponse,
    NutritionMealTemplateItemResponse,
    NutritionSuggestionCandidate,
    NutritionSuggestionCommitRequest,
    NutritionSuggestionItem,
    NutritionSuggestionsResponse,
    SuggestionReason,
    SuggestionSource,
)
from fitminiapp_api.services.food_diary import (
    FoodDiaryError,
    create_food_diary_batch,
    get_food_diary_day,
)
from fitminiapp_api.services.foods import (
    FoodError,
    FoodNutrition,
    calculate_food_amount,
    calculate_food_nutrition,
    list_favorite_foods,
    list_frequent_foods,
    list_recent_foods,
)
from fitminiapp_api.services.nutrition_power import list_meal_templates
from fitminiapp_api.services.recipes import RecipeError, calculate_recipe

MAX_CANDIDATES = 6
MAX_SOURCE_ITEMS = 12
ZERO = Decimal("0")
LARGE_DISTANCE = Decimal("999999")
SuggestionConfidence = Literal["exact", "approximate", "partial"]
_SOURCE_ORDER: tuple[SuggestionSource, ...] = (
    "saved_template",
    "personal_recipe",
    "recent",
    "frequent",
    "favorite",
    "used",
)
_SOURCE_PRIORITY = {
    "saved_template": 5,
    "personal_recipe": 4,
    "recent": 3,
    "frequent": 2,
    "favorite": 1,
    "used": 1,
}


class NutritionSuggestionError(FoodDiaryError):
    pass


def _optional_sum(values: list[Decimal | None]) -> Decimal | None:
    if any(value is None for value in values):
        return None
    return sum((cast(Decimal, value) for value in values), start=ZERO)


def _sum_nutrition(values: list[FoodDiaryNutrition]) -> FoodDiaryNutrition:
    if not values:
        return FoodDiaryNutrition(
            energy_kcal=ZERO,
            protein_g=ZERO,
            fat_g=ZERO,
            carbs_g=ZERO,
            fiber_g=ZERO,
        )
    return FoodDiaryNutrition(
        energy_kcal=sum((value.energy_kcal for value in values), start=ZERO),
        protein_g=_optional_sum([value.protein_g for value in values]),
        fat_g=_optional_sum([value.fat_g for value in values]),
        carbs_g=_optional_sum([value.carbs_g for value in values]),
        fiber_g=_optional_sum([value.fiber_g for value in values]),
    )


def _confidence(nutrition: FoodDiaryNutrition) -> SuggestionConfidence:
    if any(value is None for value in (nutrition.protein_g, nutrition.fat_g, nutrition.carbs_g)):
        return "partial"
    return "exact"


def _nutrition_from_calculation(calculation: FoodNutrition) -> FoodDiaryNutrition | None:
    if calculation.energy_kcal is None:
        return None
    return FoodDiaryNutrition(
        energy_kcal=calculation.energy_kcal,
        protein_g=calculation.protein_g,
        fat_g=calculation.fat_g,
        carbs_g=calculation.carbs_g,
        fiber_g=calculation.fiber_g,
    )


def _default_food_amount(food: Food) -> tuple[Decimal, DiaryAmountUnit]:
    if food.nutrition_basis_kind == "per_100_ml" or food.nutrition_basis_unit == "ml":
        return Decimal("100"), "ml"
    if food.nutrition_basis_kind == "per_serving" or food.standard_serving_weight_g is not None:
        return Decimal("1"), "serving"
    return Decimal("100"), "g"


def _food_item(food: Food) -> NutritionSuggestionItem | None:
    amount, amount_unit = _default_food_amount(food)
    try:
        calculation = calculate_food_amount(food, amount, amount_unit)
    except FoodError:
        return None
    nutrition = _nutrition_from_calculation(calculation)
    if nutrition is None:
        return None
    return NutritionSuggestionItem(
        position=0,
        item_kind="food",
        food_id=food.id,
        recipe_id=None,
        name=food.name,
        brand=food.brand,
        amount=amount,
        amount_unit=amount_unit,
        nutrition=nutrition,
        nutrition_confidence=_confidence(nutrition),
    )


def _recipe_item(recipe: Recipe) -> NutritionSuggestionItem | None:
    try:
        calculation = calculate_recipe(recipe)
        nutrients = calculation.nutrients_per_100g
        amount = Decimal("100")
        nutrition = _nutrition_from_calculation(
            calculate_food_nutrition(
                FoodNutrientsInput(
                    energy_kcal_per_100g=nutrients.energy_kcal_per_100g,
                    protein_g_per_100g=nutrients.protein_g_per_100g,
                    fat_g_per_100g=nutrients.fat_g_per_100g,
                    carbs_g_per_100g=nutrients.carbs_g_per_100g,
                    fiber_g_per_100g=nutrients.fiber_g_per_100g,
                ),
                amount,
            )
        )
    except FoodError, RecipeError:
        return None
    if nutrition is None:
        return None
    return NutritionSuggestionItem(
        position=0,
        item_kind="recipe",
        food_id=None,
        recipe_id=recipe.id,
        name=recipe.name,
        brand=None,
        amount=amount,
        amount_unit="g",
        nutrition=nutrition,
        nutrition_confidence=_confidence(nutrition),
    )


def _template_item(
    item: NutritionMealTemplateItemResponse, position: int
) -> NutritionSuggestionItem:
    if item.nutrition is None or not item.available:
        raise NutritionSuggestionError("template item is not available")
    return NutritionSuggestionItem(
        position=position,
        item_kind=item.item_kind,
        food_id=item.food_id,
        recipe_id=item.recipe_id,
        name=item.name,
        brand=item.brand,
        amount=item.amount,
        amount_unit=item.amount_unit,
        nutrition=item.nutrition,
        nutrition_confidence=_confidence(item.nutrition),
    )


def _ordered_sources(values: set[SuggestionSource]) -> list[SuggestionSource]:
    return [source for source in _SOURCE_ORDER if source in values]


def _reasons(
    sources: list[SuggestionSource],
    *,
    kind: Literal["food", "recipe", "template"],
    nutrition: FoodDiaryNutrition,
    day: FoodDiaryDayResponse,
) -> list[SuggestionReason]:
    result: list[SuggestionReason] = []
    result.extend(cast(list[SuggestionReason], sources))
    if kind == "recipe" and "personal_recipe" not in result:
        result.append("personal_recipe")
    if (
        day.remaining is not None
        and day.remaining.protein_g is not None
        and nutrition.protein_g is not None
        and nutrition.protein_g <= max(day.remaining.protein_g, ZERO)
    ):
        result.append("protein_fit")
    if (
        day.remaining is not None
        and day.remaining.fat_g is not None
        and nutrition.fat_g is not None
        and nutrition.fat_g <= max(day.remaining.fat_g, ZERO)
    ):
        result.append("lower_known_fat")
    if _confidence(nutrition) == "partial":
        result.append("partial_nutrition")
    return result or ["used"]


def _food_sources(db: Session, user: User) -> tuple[list[Food], dict[int, set[SuggestionSource]]]:
    sources_by_food: dict[int, set[SuggestionSource]] = defaultdict(set)
    for source, response in (
        ("recent", list_recent_foods(db, user, limit=MAX_SOURCE_ITEMS, offset=0)),
        ("frequent", list_frequent_foods(db, user, limit=MAX_SOURCE_ITEMS, offset=0)),
        ("favorite", list_favorite_foods(db, user, limit=MAX_SOURCE_ITEMS, offset=0)),
    ):
        typed_source = cast(SuggestionSource, source)
        for item in response.items:
            sources_by_food[item.id].add(typed_source)

    used_rows = (
        db.query(FoodDiaryEntry.food_id)
        .filter(FoodDiaryEntry.user_id == user.id, FoodDiaryEntry.food_id.is_not(None))
        .group_by(FoodDiaryEntry.food_id)
        .order_by(func.max(FoodDiaryEntry.diary_date).desc(), FoodDiaryEntry.food_id.asc())
        .limit(MAX_SOURCE_ITEMS)
        .all()
    )
    for (food_id,) in used_rows:
        if food_id is not None:
            sources_by_food[food_id].add("used")

    if not sources_by_food:
        return [], sources_by_food
    foods = (
        db.query(Food)
        .filter(
            Food.id.in_(sources_by_food),
            Food.status == "active",
            or_(Food.food_type != "user", Food.owner_user_id == user.id),
        )
        .order_by(Food.id.asc())
        .all()
    )
    return foods, sources_by_food


def _food_candidate(
    food: Food,
    sources_by_food: dict[int, set[SuggestionSource]],
    day: FoodDiaryDayResponse,
) -> NutritionSuggestionCandidate | None:
    item = _food_item(food)
    if item is None:
        return None
    sources = _ordered_sources(sources_by_food[food.id])
    return NutritionSuggestionCandidate(
        candidate_id=f"food:{food.id}",
        candidate_kind="food",
        identity_id=food.id,
        name=food.name,
        items=[item],
        nutrition=item.nutrition,
        nutrition_confidence=item.nutrition_confidence,
        sources=sources,
        reasons=_reasons(sources, kind="food", nutrition=item.nutrition, day=day),
    )


def _recipe_candidate(
    recipe: Recipe, day: FoodDiaryDayResponse
) -> NutritionSuggestionCandidate | None:
    item = _recipe_item(recipe)
    if item is None:
        return None
    sources: list[SuggestionSource] = ["personal_recipe"]
    return NutritionSuggestionCandidate(
        candidate_id=f"recipe:{recipe.id}",
        candidate_kind="recipe",
        identity_id=recipe.id,
        name=recipe.name,
        items=[item],
        nutrition=item.nutrition,
        nutrition_confidence=item.nutrition_confidence,
        sources=sources,
        reasons=_reasons(sources, kind="recipe", nutrition=item.nutrition, day=day),
    )


def _template_candidate(template, day: FoodDiaryDayResponse) -> NutritionSuggestionCandidate | None:
    if any(not item.available or item.nutrition is None for item in template.items):
        return None
    items = [_template_item(item, position) for position, item in enumerate(template.items)]
    nutrition = _sum_nutrition([item.nutrition for item in items])
    sources: list[SuggestionSource] = ["saved_template"]
    return NutritionSuggestionCandidate(
        candidate_id=f"template:{template.id}",
        candidate_kind="template",
        identity_id=template.id,
        name=template.name,
        items=items,
        nutrition=nutrition,
        nutrition_confidence=_confidence(nutrition),
        sources=sources,
        reasons=_reasons(sources, kind="template", nutrition=nutrition, day=day),
    )


def _candidate_sort_key(candidate: NutritionSuggestionCandidate, day: FoodDiaryDayResponse):
    remaining = day.remaining
    protein_target = (
        max(remaining.protein_g, ZERO)
        if remaining is not None and remaining.protein_g is not None
        else None
    )
    protein_distance = (
        abs(candidate.nutrition.protein_g - protein_target)
        if protein_target is not None and candidate.nutrition.protein_g is not None
        else LARGE_DISTANCE
    )
    fat_target = (
        max(remaining.fat_g, ZERO)
        if remaining is not None and remaining.fat_g is not None
        else None
    )
    fat_distance = (
        abs(candidate.nutrition.fat_g - fat_target)
        if fat_target is not None and candidate.nutrition.fat_g is not None
        else LARGE_DISTANCE
    )
    source_priority = max((_SOURCE_PRIORITY[source] for source in candidate.sources), default=0)
    return (
        candidate.nutrition_confidence == "partial",
        protein_distance,
        fat_distance,
        -source_priority,
        candidate.candidate_kind,
        candidate.identity_id,
    )


def _remaining_confidence(day: FoodDiaryDayResponse) -> SuggestionConfidence:
    confidences: list[SuggestionConfidence] = []
    for meal in day.meals:
        for entry in meal.entries:
            if entry.nutrition_confidence is not None:
                confidences.append(entry.nutrition_confidence)
            elif any(
                value is None
                for value in (
                    entry.nutrition.protein_g,
                    entry.nutrition.fat_g,
                    entry.nutrition.carbs_g,
                )
            ):
                confidences.append("partial")
            else:
                confidences.append("approximate" if entry.entry_kind == "quick_add" else "exact")
    if day.remaining is not None and any(
        value is None
        for value in (day.remaining.protein_g, day.remaining.fat_g, day.remaining.carbs_g)
    ):
        return "partial"
    if "partial" in confidences:
        return "partial"
    if "approximate" in confidences:
        return "approximate"
    return "exact"


def _limitations(day: FoodDiaryDayResponse, confidence: SuggestionConfidence | None) -> list[str]:
    limitations: list[str] = [
        "Это варианты из уже сохранённых продуктов, рецептов и шаблонов, а не предписание.",
        "Проверьте состав и количество перед добавлением.",
    ]
    if day.targets is None or day.remaining is None:
        limitations.insert(0, "Настройте цель КБЖУ, чтобы рассчитывать остаток на день.")
    elif any(
        value is None
        for value in (day.remaining.protein_g, day.remaining.fat_g, day.remaining.carbs_g)
    ):
        limitations.insert(
            0,
            "Часть БЖУ неизвестна: неполные записи не превращаются в нули.",
        )
    if confidence == "approximate":
        limitations.insert(
            0, "В дневнике есть приблизительные значения; учитывайте это при проверке."
        )
    elif confidence == "partial":
        limitations.insert(0, "В дневнике или вариантах есть неполные значения БЖУ.")
    return limitations


def get_nutrition_suggestions(
    db: Session,
    user: User,
    diary_date: date | None,
) -> NutritionSuggestionsResponse:
    day = get_food_diary_day(db, user, diary_date)
    confidence = _remaining_confidence(day) if day.remaining is not None else None
    if day.targets is None or day.remaining is None:
        return NutritionSuggestionsResponse(
            diary_date=day.diary_date,
            targets=day.targets,
            remaining=day.remaining,
            remaining_confidence=confidence,
            limitations=_limitations(day, confidence),
            candidates=[],
            max_candidates=MAX_CANDIDATES,
        )

    candidates: list[NutritionSuggestionCandidate] = []
    foods, sources_by_food = _food_sources(db, user)
    for food in foods:
        candidate = _food_candidate(food, sources_by_food, day)
        if candidate is not None:
            candidates.append(candidate)

    recipes = (
        db.query(Recipe)
        .options(selectinload(Recipe.ingredients))
        .filter(Recipe.owner_user_id == user.id)
        .order_by(Recipe.updated_at.desc(), Recipe.id.desc())
        .limit(MAX_SOURCE_ITEMS)
        .all()
    )
    for recipe in recipes:
        candidate = _recipe_candidate(recipe, day)
        if candidate is not None:
            candidates.append(candidate)

    templates = list_meal_templates(db, user, limit=MAX_SOURCE_ITEMS, offset=0)
    for template in templates.items:
        candidate = _template_candidate(template, day)
        if candidate is not None:
            candidates.append(candidate)

    candidates.sort(key=lambda candidate: _candidate_sort_key(candidate, day))
    return NutritionSuggestionsResponse(
        diary_date=day.diary_date,
        targets=day.targets,
        remaining=day.remaining,
        remaining_confidence=confidence,
        limitations=_limitations(day, confidence),
        candidates=candidates[:MAX_CANDIDATES],
        max_candidates=MAX_CANDIDATES,
    )


def commit_nutrition_suggestion(
    db: Session,
    user: User,
    payload: NutritionSuggestionCommitRequest,
    idempotency_key: str,
) -> FoodDiaryBatchResponse:
    return create_food_diary_batch(
        db,
        user,
        diary_date=payload.diary_date,
        meal_type=payload.meal_type,
        items=payload.items,
        idempotency_key=idempotency_key,
        operation_kind="suggestion",
    )
