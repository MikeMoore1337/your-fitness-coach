from __future__ import annotations

import hashlib
import hmac
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Literal, cast

from sqlalchemy import func, or_
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, selectinload

from fitminiapp_api.core.config import settings
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.nutrition_power import NutritionMealTemplate, NutritionMealTemplateItem
from fitminiapp_api.models.recipe import Recipe, RecipeIngredient
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.food import FoodNutrientsInput
from fitminiapp_api.schemas.food_diary import (
    DiaryAmountUnit,
    FoodDiaryDayResponse,
    FoodDiaryNutrition,
    FoodDiaryTargets,
)
from fitminiapp_api.schemas.nutrition_plan import (
    NutritionPlanDayResponse,
    NutritionPlanItemResponse,
)
from fitminiapp_api.schemas.nutrition_power import (
    FoodDiaryBatchItem,
    FoodDiaryBatchResponse,
    NutritionMealTemplateItemResponse,
    NutritionSuggestionCandidate,
    NutritionSuggestionCommitRequest,
    NutritionSuggestionConstraints,
    NutritionSuggestionItem,
    NutritionSuggestionPreviewRequest,
    NutritionSuggestionPreviewResponse,
    NutritionSuggestionsResponse,
    SuggestionReason,
    SuggestionSource,
)
from fitminiapp_api.services.food_diary import (
    FoodDiaryConflictError,
    FoodDiaryError,
    _batch_request_fingerprint,
    _calculate_amount,
    _ensure_day_accepts_entries,
    _existing_batch_operation,
    _lock_diary_user,
    _normalize_idempotency_key,
    _owned_recipe,
    _recipe_as_food,
    _visible_food,
    create_food_diary_batch,
    ensure_suggestion_day_is_mutable,
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
from fitminiapp_api.services.nutrition import (
    MANUAL_ENERGY_MISMATCH_MIN_KCAL,
    MANUAL_ENERGY_MISMATCH_RATIO,
    get_nutrition_target_for_date,
)
from fitminiapp_api.services.nutrition_power import list_meal_templates
from fitminiapp_api.services.recipes import RecipeError, calculate_recipe, serialize_recipe

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


def _target_macro_energy(targets: FoodDiaryTargets | None) -> Decimal | None:
    if targets is None or any(
        value is None for value in (targets.protein_g, targets.fat_g, targets.carbs_g)
    ):
        return None
    return (
        cast(Decimal, targets.protein_g) * 4
        + cast(Decimal, targets.fat_g) * 9
        + cast(Decimal, targets.carbs_g) * 4
    )


def _incompatible_target(targets: FoodDiaryTargets | None) -> bool:
    energy = _target_macro_energy(targets)
    if targets is None or energy is None:
        return False
    tolerance = max(
        MANUAL_ENERGY_MISMATCH_MIN_KCAL,
        round(targets.energy_kcal * Decimal(str(MANUAL_ENERGY_MISMATCH_RATIO))),
    )
    return abs(energy - targets.energy_kcal) > tolerance


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


def _pending_plan(
    db: Session, user: User, selected_date: date
) -> tuple[NutritionPlanDayResponse, list[NutritionPlanItemResponse], FoodDiaryNutrition | None]:
    from fitminiapp_api.services.nutrition_plan import get_plan_day

    plan = get_plan_day(db, user, selected_date)
    pending = [item for slot in plan.slots for item in slot.items if item.status == "planned"]
    planned = (
        _sum_nutrition([item.nutrition for item in pending if item.nutrition is not None])
        if all(item.available and item.nutrition is not None for item in pending)
        else None
    )
    return plan, pending, planned


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
        and day.remaining.protein_g > ZERO
        and nutrition.protein_g is not None
        and ZERO < nutrition.protein_g <= day.remaining.protein_g
    ):
        result.append("protein_fit")
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
    exceeded = (
        sum(
            1
            for field in ("energy_kcal", "protein_g", "fat_g", "carbs_g")
            if (limit := getattr(remaining, field)) is not None
            and (value := getattr(candidate.nutrition, field)) is not None
            and value > max(limit, ZERO)
        )
        if remaining is not None
        else 0
    )
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
        exceeded,
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
    if day.targets is None:
        limitations.insert(0, "Настройте цель КБЖУ, чтобы рассчитывать остаток на день.")
    elif day.remaining is None:
        limitations.insert(
            0, "Не удалось рассчитать остаток: проверьте доступность продуктов в плане."
        )
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
    *,
    targets_override: FoodDiaryTargets | None = None,
    remaining_override: FoodDiaryTargets | None = None,
    force_context: bool = False,
    remaining_includes_plan: bool = False,
) -> NutritionSuggestionsResponse:
    day = get_food_diary_day(db, user, diary_date, allow_future=force_context)
    includes_plan = remaining_includes_plan
    if force_context or targets_override is not None or remaining_override is not None:
        day = day.model_copy(
            update={
                "targets": (
                    targets_override
                    if force_context or targets_override is not None
                    else day.targets
                ),
                "remaining": remaining_override
                if force_context or remaining_override is not None
                else day.remaining,
            }
        )
    if not force_context and day.remaining is not None:
        from fitminiapp_api.services.nutrition_plan import _subtract_targets

        _, pending, planned = _pending_plan(db, user, day.diary_date)
        includes_plan = bool(pending)
        if includes_plan:
            day = day.model_copy(
                update={
                    "remaining": _subtract_targets(day.remaining, planned)
                    if planned is not None
                    else None
                }
            )
    confidence = _remaining_confidence(day) if day.remaining is not None else None
    limitations = _limitations(day, confidence)
    if includes_plan:
        limitations.append("При подборе учтены запланированные, ещё не съеденные блюда.")
    not_calculable = _incompatible_target(day.targets)
    if not_calculable and day.targets is not None:
        limitations.append(
            f"Калории цели ({day.targets.energy_kcal} ккал) не согласуются с суммой БЖУ "
            f"({_target_macro_energy(day.targets)} ккал). Проверьте цель питания."
        )
    if day.targets is None or day.remaining is None or not_calculable:
        return NutritionSuggestionsResponse(
            diary_date=day.diary_date,
            targets=day.targets,
            remaining=day.remaining,
            remaining_confidence=confidence,
            remaining_includes_plan=includes_plan,
            not_calculable=not_calculable,
            limitations=limitations,
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
        remaining_includes_plan=includes_plan,
        limitations=limitations,
        candidates=candidates[:MAX_CANDIDATES],
        max_candidates=MAX_CANDIDATES,
    )


def _preview_item(
    db: Session, user: User, item: FoodDiaryBatchItem, position: int
) -> NutritionSuggestionItem:
    if item.food_id is not None:
        food = _visible_food(db, user, item.food_id)
        calculation = _calculate_amount(food, item.amount, item.amount_unit)
        kind, name, brand = "food", food.name, food.brand
    else:
        recipe = _owned_recipe(db, user, cast(int, item.recipe_id))
        try:
            calculation = _calculate_amount(
                _recipe_as_food(calculate_recipe(recipe)), item.amount, "g"
            )
        except RecipeError as exc:
            raise NutritionSuggestionError(str(exc)) from exc
        kind, name, brand = "recipe", recipe.name, None
    nutrition = _nutrition_from_calculation(calculation)
    if nutrition is None:
        raise NutritionSuggestionError("Неизвестна калорийность выбранного продукта.")
    return NutritionSuggestionItem(
        position=position,
        item_kind=cast(Literal["food", "recipe"], kind),
        food_id=item.food_id,
        recipe_id=item.recipe_id,
        name=name,
        brand=brand,
        amount=item.amount,
        amount_unit=item.amount_unit,
        nutrition=nutrition,
        nutrition_confidence=_confidence(nutrition),
    )


def lock_suggestion_sources(
    db: Session,
    user: User,
    selected_date: date,
    items: list[FoodDiaryBatchItem],
    constraints: NutritionSuggestionConstraints | None,
    candidate_id: str | None = None,
) -> None:
    plan, _, _ = _pending_plan(db, user, selected_date)
    food_ids = {item.food_id for item in items if item.food_id is not None}
    recipe_ids = {item.recipe_id for item in items if item.recipe_id is not None}
    if constraints is not None:
        food_ids.update(constraints.excluded_food_ids + constraints.preferred_food_ids)
    for food_id in food_ids:
        _visible_food(db, user, food_id)
    for recipe_id in recipe_ids:
        _owned_recipe(db, user, recipe_id)
    for slot in plan.slots:
        for item in slot.items:
            if item.food_id is not None:
                food_ids.add(item.food_id)
            if item.recipe_id is not None:
                recipe_ids.add(item.recipe_id)
    try:
        if food_ids:
            (
                db.query(Food.id)
                .filter(
                    Food.id.in_(food_ids),
                    or_(Food.food_type != "user", Food.owner_user_id == user.id),
                )
                .order_by(Food.id)
                .with_for_update(read=True, nowait=True)
                .all()
            )
        if recipe_ids:
            locked_recipe_ids = [
                recipe_id
                for (recipe_id,) in (
                    db.query(Recipe.id)
                    .filter(Recipe.id.in_(recipe_ids), Recipe.owner_user_id == user.id)
                    .order_by(Recipe.id)
                    .with_for_update(read=True, nowait=True)
                    .all()
                )
            ]
            if locked_recipe_ids:
                (
                    db.query(RecipeIngredient.id)
                    .filter(RecipeIngredient.recipe_id.in_(locked_recipe_ids))
                    .order_by(RecipeIngredient.id)
                    .with_for_update(read=True, nowait=True)
                    .all()
                )
        prefix, _, raw_id = (candidate_id or "").partition(":")
        if (
            prefix == "template"
            and raw_id.isascii()
            and raw_id.isdecimal()
            and 0 < int(raw_id) <= 2_147_483_647
        ):
            template_id = int(raw_id)
            owned = (
                db.query(NutritionMealTemplate.id)
                .filter_by(id=template_id, owner_user_id=user.id)
                .with_for_update(read=True, nowait=True)
                .first()
            )
            if owned is not None:
                (
                    db.query(NutritionMealTemplateItem.id)
                    .filter_by(template_id=template_id)
                    .order_by(NutritionMealTemplateItem.id)
                    .with_for_update(read=True, nowait=True)
                    .all()
                )
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) == "55P03":
            raise FoodDiaryConflictError("Данные изменяются. Обновите расчёт и повторите.") from exc
        raise
    db.expire_all()


def preview_nutrition_suggestion(
    db: Session,
    user: User,
    payload: NutritionSuggestionPreviewRequest,
    *,
    plan_mode: bool = False,
    signed_context: dict | None = None,
) -> NutritionSuggestionPreviewResponse:
    day = get_food_diary_day(db, user, payload.diary_date, allow_future=plan_mode)
    ensure_suggestion_day_is_mutable(db, user, payload.diary_date)
    if not plan_mode:
        _ensure_day_accepts_entries(db, user, payload.diary_date)
    target = get_nutrition_target_for_date(db, user.id, payload.diary_date)
    if target is None or day.targets is None:
        raise NutritionSuggestionError("На выбранную дату не задана цель КБЖУ.")
    if _incompatible_target(day.targets):
        raise NutritionSuggestionError(
            "Калории цели не согласуются с суммой БЖУ. Проверьте цель питания."
        )
    items = [_preview_item(db, user, item, index) for index, item in enumerate(payload.items)]
    addition = _sum_nutrition([item.nutrition for item in items])
    plan, pending, planned = _pending_plan(db, user, payload.diary_date)
    if plan_mode and not plan.nutrition_complete:
        raise NutritionSuggestionError("Не удалось проверить состав всех блюд плана.")
    before = plan.planned if plan_mode else day.totals
    after = _sum_nutrition([before, addition])
    projected_after = (
        _sum_nutrition([day.totals, planned, addition]) if planned is not None else None
    )

    constraints = payload.constraints
    messages: list[str] = []
    statuses: list[Literal["satisfied", "violated", "unknown"]] = []
    preference_message = None
    if constraints is not None:
        for food_id in set(constraints.excluded_food_ids + constraints.preferred_food_ids):
            _visible_food(db, user, food_id)
        selected_food_ids: set[int] = set()
        ingredients_unknown = False
        for item in payload.items:
            if item.food_id is not None:
                selected_food_ids.add(item.food_id)
            else:
                recipe = _owned_recipe(db, user, cast(int, item.recipe_id))
                selected_food_ids.update(
                    ingredient.food_id
                    for ingredient in recipe.ingredients
                    if ingredient.food_id is not None
                )
                ingredients_unknown |= any(
                    ingredient.food_id is None for ingredient in recipe.ingredients
                )
        excluded = set(constraints.excluded_food_ids)
        if excluded:
            messages.append(
                "Проверяются совпадения продуктов и известные ингредиенты рецептов; "
                "состав готовых продуктов не проверяется."
            )
            if selected_food_ids & excluded:
                statuses.append("violated")
                messages.append("Выбранный вариант содержит исключённый продукт.")
            elif ingredients_unknown:
                statuses.append("unknown")
                messages.append("Не удалось проверить все продукты в составе рецепта.")
            else:
                statuses.append("satisfied")
            for planned_item in pending:
                if not planned_item.available:
                    statuses.append("unknown")
                    messages.append("Не удалось проверить состав запланированного блюда.")
                    continue
                if planned_item.food_id in excluded:
                    statuses.append("violated")
                    messages.append("В плане есть исключённый продукт.")
                elif planned_item.recipe_id is not None:
                    recipe = _owned_recipe(db, user, planned_item.recipe_id)
                    if any(ingredient.food_id in excluded for ingredient in recipe.ingredients):
                        statuses.append("violated")
                        messages.append("В запланированном рецепте есть исключённый продукт.")
                    elif any(ingredient.food_id is None for ingredient in recipe.ingredients):
                        statuses.append("unknown")
                        messages.append("Не удалось проверить состав запланированного рецепта.")
        preferred = set(constraints.preferred_food_ids)
        if preferred:
            if selected_food_ids & preferred:
                preference_message = "В варианте есть указанный предпочитаемый продукт."
            elif ingredients_unknown:
                preference_message = "Не удалось проверить все продукты в составе рецепта."
            else:
                preference_message = "В варианте нет указанных предпочитаемых продуктов."
        for field, maximum, label in (
            ("energy_kcal", constraints.max_energy_kcal, "калорий"),
            ("protein_g", constraints.max_protein_g, "белка"),
            ("fat_g", constraints.max_fat_g, "жиров"),
            ("carbs_g", constraints.max_carbs_g, "углеводов"),
        ):
            if maximum is None:
                continue
            value = getattr(projected_after, field) if projected_after is not None else None
            if value is None:
                statuses.append("unknown")
                messages.append(f"Нельзя проверить заданный предел {label}: данных недостаточно.")
            elif value > maximum:
                statuses.append("violated")
                messages.append(f"После добавления будет превышен заданный предел {label}.")
            else:
                statuses.append("satisfied")
    constraint_status: Literal["not_set", "satisfied", "violated", "unknown"] = (
        "violated"
        if "violated" in statuses
        else "unknown"
        if "unknown" in statuses
        else "satisfied"
        if statuses
        else "not_set"
    )

    def remaining(target_value: Decimal | None, actual: Decimal | None) -> Decimal | None:
        return target_value - actual if target_value is not None and actual is not None else None

    remaining_after = FoodDiaryTargets(
        energy_kcal=day.targets.energy_kcal - after.energy_kcal,
        protein_g=remaining(day.targets.protein_g, after.protein_g),
        fat_g=remaining(day.targets.fat_g, after.fat_g),
        carbs_g=remaining(day.targets.carbs_g, after.carbs_g),
    )
    recipe_ids = {item.recipe_id for item in payload.items if item.recipe_id is not None}
    recipe_ids.update(
        item.recipe_id
        for slot in plan.slots
        for item in slot.items
        if item.available and item.recipe_id is not None
    )
    try:
        recipe_sources = [
            serialize_recipe(_owned_recipe(db, user, recipe_id)).model_dump(mode="json")
            for recipe_id in sorted(recipe_ids)
        ]
    except RecipeError as exc:
        raise NutritionSuggestionError("Не удалось проверить состав рецепта.") from exc
    snapshot = {
        "user_id": user.id,
        "plan_mode": plan_mode,
        "context": signed_context,
        "request": payload.model_dump(mode="json", exclude={"preview_token"}),
        "day": day.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
        "target": {
            "id": target.id,
            "source": target.source,
            "effective_from": target.effective_from.isoformat(),
            "weight_kg": str(target.weight_kg) if target.weight_kg is not None else None,
            "goal": target.goal,
            "estimated_bmr_kcal": target.bmr,
            "estimated_tdee_kcal": target.tdee,
        },
        "items": [item.model_dump(mode="json") for item in items],
        "recipe_sources": recipe_sources,
        "constraint_status": constraint_status,
        "constraint_messages": messages,
        "preference_message": preference_message,
    }
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    token = hmac.new(
        settings.secret_key.encode("utf-8"),
        b"nutrition-suggestion-preview-v1:" + canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return NutritionSuggestionPreviewResponse(
        diary_date=day.diary_date,
        meal_type=payload.meal_type,
        items=items,
        before=before,
        addition=addition,
        after=after,
        diary=day.totals,
        planned=planned,
        projected_after=projected_after,
        targets=day.targets,
        remaining_after=remaining_after,
        target_id=target.id,
        target_source=target.source,
        target_effective_from=target.effective_from,
        target_weight_kg=target.weight_kg,
        target_goal=target.goal,
        target_estimated_bmr_kcal=target.bmr,
        target_estimated_tdee_kcal=target.tdee,
        constraint_status=constraint_status,
        constraint_messages=list(dict.fromkeys(messages)),
        preference_message=preference_message,
        preview_token=token,
    )


def confirm_nutrition_suggestion(
    db: Session, user: User, payload: NutritionSuggestionCommitRequest, idempotency_key: str
) -> FoodDiaryBatchResponse:
    try:
        _lock_diary_user(db, user)
        key = _normalize_idempotency_key(idempotency_key)
        if payload.preview_token is None:
            if payload.constraints is not None:
                raise FoodDiaryConflictError("Сначала проверьте расчёт варианта.")
            legacy_fingerprint = _batch_request_fingerprint(
                "suggestion", payload.diary_date, payload.meal_type, payload.items, None
            )
            replay = _existing_batch_operation(db, user, key, legacy_fingerprint)
            if replay is not None:
                return replay
            raise FoodDiaryConflictError("Сначала проверьте расчёт варианта.")
        request_context: dict[str, object] = {
            "preview_token": payload.preview_token,
            "constraints": payload.constraints.model_dump(mode="json")
            if payload.constraints is not None
            else None,
        }
        fingerprint = _batch_request_fingerprint(
            "suggestion",
            payload.diary_date,
            payload.meal_type,
            payload.items,
            None,
            request_context,
        )
        replay = _existing_batch_operation(db, user, key, fingerprint)
        if replay is not None:
            return replay
        lock_suggestion_sources(db, user, payload.diary_date, payload.items, payload.constraints)
        preview = preview_nutrition_suggestion(db, user, payload)
        if not hmac.compare_digest(preview.preview_token, payload.preview_token):
            raise FoodDiaryConflictError("Данные изменились. Обновите расчёт перед подтверждением.")
        if preview.constraint_status in {"violated", "unknown"}:
            raise FoodDiaryConflictError("Ограничения не выполнены или не могут быть проверены.")
        result = create_food_diary_batch(
            db,
            user,
            diary_date=payload.diary_date,
            meal_type=payload.meal_type,
            items=payload.items,
            idempotency_key=key,
            operation_kind="suggestion",
            commit=False,
            request_context=request_context,
        )
        if (
            not result.replayed
            and _sum_nutrition([entry.nutrition for entry in result.entries]) != preview.addition
        ):
            raise FoodDiaryConflictError("Состав продукта изменился. Обновите расчёт.")
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
