from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal, cast

from sqlalchemy.orm import Session, selectinload

from fitminiapp_api.core.timezone import get_user_timezone_name, today_for_user
from fitminiapp_api.models.nutrition_plan import (
    NutritionPlan,
    NutritionPlanItem,
    NutritionPlanOperation,
)
from fitminiapp_api.models.nutrition_power import NutritionMealTemplate
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.food import FoodNutrientsInput
from fitminiapp_api.schemas.food_diary import FoodDiaryNutrition, FoodDiaryTargets, MealType
from fitminiapp_api.schemas.nutrition_plan import (
    NutritionPlanCopyRequest,
    NutritionPlanDayResponse,
    NutritionPlanFillItem,
    NutritionPlanFillRequest,
    NutritionPlanItemActionRequest,
    NutritionPlanItemActionResponse,
    NutritionPlanItemCreate,
    NutritionPlanItemResponse,
    NutritionPlanItemUpdate,
    NutritionPlanSlotResponse,
    NutritionPlanWeekResponse,
)
from fitminiapp_api.schemas.nutrition_power import FoodDiaryBatchItem, NutritionSuggestionsResponse
from fitminiapp_api.services.food_diary import FoodDiaryError, create_food_diary_batch
from fitminiapp_api.services.foods import (
    FoodError,
    FoodNutrition,
    calculate_food_amount,
    calculate_food_nutrition,
    get_visible_food,
)
from fitminiapp_api.services.nutrition import get_nutrition_target_for_date
from fitminiapp_api.services.recipes import RecipeError, calculate_recipe, get_owned_recipe

MEAL_TYPES: tuple[MealType, ...] = ("breakfast", "lunch", "dinner", "snacks")
MAX_ITEMS_PER_DAY = 100
ZERO = Decimal("0")


class NutritionPlanError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


class NutritionPlanNotFoundError(NutritionPlanError):
    pass


class NutritionPlanConflictError(NutritionPlanError):
    pass


def _sum_optional(values: Iterable[Decimal | None]) -> Decimal | None:
    items = list(values)
    if any(value is None for value in items):
        return None
    return sum((cast(Decimal, value) for value in items), start=ZERO)


def _sum_nutrition(values: Iterable[FoodDiaryNutrition]) -> FoodDiaryNutrition:
    items = list(values)
    return FoodDiaryNutrition(
        energy_kcal=sum((item.energy_kcal for item in items), start=ZERO),
        protein_g=_sum_optional(item.protein_g for item in items),
        fat_g=_sum_optional(item.fat_g for item in items),
        carbs_g=_sum_optional(item.carbs_g for item in items),
        fiber_g=_sum_optional(item.fiber_g for item in items),
    )


def _subtract_optional(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None or right is None:
        return None
    return left - right


def _subtract_targets(
    targets: FoodDiaryTargets,
    planned: FoodDiaryNutrition,
) -> FoodDiaryTargets:
    return FoodDiaryTargets(
        energy_kcal=targets.energy_kcal - planned.energy_kcal,
        protein_g=_subtract_optional(targets.protein_g, planned.protein_g),
        fat_g=_subtract_optional(targets.fat_g, planned.fat_g),
        carbs_g=_subtract_optional(targets.carbs_g, planned.carbs_g),
    )


def _target_response(db: Session, user: User, target_date: date) -> FoodDiaryTargets | None:
    target = get_nutrition_target_for_date(db, user.id, target_date)
    if target is None:
        return None
    return FoodDiaryTargets(
        energy_kcal=Decimal(target.calories),
        protein_g=Decimal(target.protein_g),
        fat_g=Decimal(target.fat_g),
        carbs_g=Decimal(target.carbs_g),
    )


def _nutrition_from_calculation(calculation: FoodNutrition) -> FoodDiaryNutrition:
    if calculation.energy_kcal is None:
        raise NutritionPlanError("nutrition for this item is incomplete")
    return FoodDiaryNutrition(
        energy_kcal=calculation.energy_kcal,
        protein_g=calculation.protein_g,
        fat_g=calculation.fat_g,
        carbs_g=calculation.carbs_g,
        fiber_g=calculation.fiber_g,
    )


def _recipe_calculation(
    db: Session,
    user: User,
    recipe_id: int,
    amount: Decimal,
) -> tuple[str, FoodDiaryNutrition]:
    recipe = get_owned_recipe(db, user, recipe_id)
    nutrients = calculate_recipe(recipe).nutrients_per_100g
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
    return recipe.name, nutrition


def _item_calculation(
    db: Session,
    user: User,
    item: NutritionPlanItem,
) -> tuple[str, str | None, Decimal | None, FoodDiaryNutrition | None, bool, str | None]:
    try:
        if item.item_kind == "food":
            if item.food_id is None:
                raise FoodError("food is no longer available")
            food = get_visible_food(db, user, item.food_id)
            calculation = calculate_food_amount(food, item.amount, item.amount_unit)
            return (
                food.name,
                food.brand,
                calculation.weight_g,
                _nutrition_from_calculation(calculation),
                True,
                None,
            )
        if item.recipe_id is None:
            raise RecipeError("recipe is no longer available")
        name, nutrition = _recipe_calculation(db, user, item.recipe_id, item.amount)
        return name, None, item.amount, nutrition, True, None
    except (FoodError, RecipeError, NutritionPlanError) as exc:
        return item.source_name, item.source_brand, None, None, False, str(exc)


def _serialize_item(
    db: Session,
    user: User,
    item: NutritionPlanItem,
) -> NutritionPlanItemResponse:
    name, brand, weight_g, nutrition, available, message = _item_calculation(db, user, item)
    return NutritionPlanItemResponse(
        id=item.id,
        meal_type=cast(MealType, item.meal_type),
        position=item.position,
        item_kind=cast(Literal["food", "recipe"], item.item_kind),
        food_id=item.food_id,
        recipe_id=item.recipe_id,
        source_template_id=item.source_template_id,
        name=name,
        brand=brand,
        amount=item.amount,
        amount_unit=cast(Literal["g", "ml", "serving"], item.amount_unit),
        weight_g=weight_g,
        nutrition=nutrition,
        available=available,
        status=cast(Literal["planned", "consumed", "skipped"], item.status or "planned"),
        diary_entry_id=item.diary_entry_id,
        message=message,
    )


def _plan_query(db: Session, user: User, plan_date: date) -> NutritionPlan | None:
    return (
        db.query(NutritionPlan)
        .options(selectinload(NutritionPlan.items))
        .filter(NutritionPlan.user_id == user.id, NutritionPlan.plan_date == plan_date)
        .first()
    )


def _build_day(
    db: Session,
    user: User,
    plan_date: date,
    *,
    replayed: bool = False,
) -> NutritionPlanDayResponse:
    plan = _plan_query(db, user, plan_date)
    grouped: dict[MealType, list[NutritionPlanItemResponse]] = {
        meal_type: [] for meal_type in MEAL_TYPES
    }
    if plan is not None:
        for item in plan.items:
            grouped[cast(MealType, item.meal_type)].append(_serialize_item(db, user, item))

    slots: list[NutritionPlanSlotResponse] = []
    nutrition_complete = True
    for meal_type in MEAL_TYPES:
        items = grouped[meal_type]
        nutrition_complete = nutrition_complete and all(item.available for item in items)
        slots.append(
            NutritionPlanSlotResponse(
                meal_type=meal_type,
                items=items,
                planned=_sum_nutrition(
                    item.nutrition for item in items if item.nutrition is not None
                ),
            )
        )
    planned = _sum_nutrition(
        item.nutrition for slot in slots for item in slot.items if item.nutrition is not None
    )
    targets = _target_response(db, user, plan_date)
    return NutritionPlanDayResponse(
        plan_date=plan_date,
        timezone=get_user_timezone_name(user),
        revision=plan.revision if plan is not None else 0,
        slots=slots,
        planned=planned,
        targets=targets,
        remaining=_subtract_targets(targets, planned) if targets and nutrition_complete else None,
        nutrition_complete=nutrition_complete,
        updated_at=plan.updated_at if plan is not None else None,
        replayed=replayed,
    )


def get_plan_day(db: Session, user: User, plan_date: date | None) -> NutritionPlanDayResponse:
    return _build_day(db, user, plan_date or today_for_user(user))


def get_plan_fill_suggestions(
    db: Session,
    user: User,
    plan_date: date | None,
) -> NutritionSuggestionsResponse:
    from fitminiapp_api.services.nutrition_suggestions import get_nutrition_suggestions

    day = get_plan_day(db, user, plan_date)
    return get_nutrition_suggestions(
        db,
        user,
        day.plan_date,
        targets_override=day.targets,
        remaining_override=day.remaining,
        force_context=True,
    )


def _monday(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _sum_targets(days: Iterable[NutritionPlanDayResponse]) -> FoodDiaryTargets | None:
    values = [day.targets for day in days]
    if not values or any(value is None for value in values):
        return None
    targets = cast(list[FoodDiaryTargets], values)
    return FoodDiaryTargets(
        energy_kcal=sum((value.energy_kcal for value in targets), start=ZERO),
        protein_g=_sum_optional(value.protein_g for value in targets),
        fat_g=_sum_optional(value.fat_g for value in targets),
        carbs_g=_sum_optional(value.carbs_g for value in targets),
    )


def get_plan_week(db: Session, user: User, week_start: date | None) -> NutritionPlanWeekResponse:
    first = _monday(week_start or today_for_user(user))
    days = [_build_day(db, user, first + timedelta(days=index)) for index in range(7)]
    planned = _sum_nutrition(day.planned for day in days)
    targets = _sum_targets(days)
    nutrition_complete = all(day.nutrition_complete for day in days)
    return NutritionPlanWeekResponse(
        week_start=first,
        week_end=first + timedelta(days=6),
        timezone=get_user_timezone_name(user),
        days=days,
        planned=planned,
        targets=targets,
        remaining=_subtract_targets(targets, planned) if targets and nutrition_complete else None,
        nutrition_complete=nutrition_complete,
    )


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _lock_user(db: Session, user: User) -> None:
    db.query(User.id).filter(User.id == user.id).with_for_update().one()


def _plan_for_write(db: Session, user: User, plan_date: date) -> NutritionPlan:
    plan = (
        db.query(NutritionPlan)
        .options(selectinload(NutritionPlan.items))
        .filter(NutritionPlan.user_id == user.id, NutritionPlan.plan_date == plan_date)
        .with_for_update()
        .first()
    )
    if plan is None:
        plan = NutritionPlan(user_id=user.id, plan_date=plan_date)
        db.add(plan)
        db.flush()
    return plan


def _check_revision(plan: NutritionPlan, expected_revision: int) -> None:
    if plan.revision != expected_revision:
        raise NutritionPlanConflictError(
            "plan revision is stale; reload the plan and retry",
            code="stale_plan",
            details={"expected_revision": expected_revision, "current_revision": plan.revision},
        )


def _operation(
    db: Session,
    user: User,
    *,
    key: str,
    fingerprint: str,
    kind: Literal["add", "copy", "fill"],
    target_date: date,
) -> tuple[NutritionPlanOperation, bool]:
    existing = (
        db.query(NutritionPlanOperation)
        .filter(
            NutritionPlanOperation.user_id == user.id,
            NutritionPlanOperation.idempotency_key == key,
        )
        .first()
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise NutritionPlanConflictError(
                "idempotency key was reused for another plan request",
                code="plan_idempotency_conflict",
            )
        return existing, True
    operation = NutritionPlanOperation(
        user_id=user.id,
        idempotency_key=key,
        request_fingerprint=fingerprint,
        operation_kind=kind,
        target_date=target_date,
    )
    db.add(operation)
    db.flush()
    return operation, False


def _next_position(plan: NutritionPlan, meal_type: MealType) -> int:
    return (
        max((item.position for item in plan.items if item.meal_type == meal_type), default=-1) + 1
    )


def copy_pending_plan_items(
    db: Session,
    user: User,
    *,
    source_date: date,
    target_date: date,
    expected_source_revision: int,
    expected_target_revision: int,
) -> int:
    source = _plan_query(db, user, source_date)
    if source is None or source.revision != expected_source_revision:
        raise NutritionPlanConflictError(
            "source plan changed; reload the weekly review and retry",
            code="stale_planning_review",
        )
    target = _plan_for_write(db, user, target_date)
    _check_revision(target, expected_target_revision)
    pending_items = [item for item in source.items if (item.status or "planned") == "planned"]
    if not pending_items:
        raise NutritionPlanConflictError(
            "there are no pending planned items to move",
            code="stale_planning_review",
        )
    if len(target.items) + len(pending_items) > MAX_ITEMS_PER_DAY:
        raise NutritionPlanError("daily plan item limit reached")
    for source_item in pending_items:
        item = NutritionPlanItem(
            plan=target,
            source_template_id=source_item.source_template_id,
            food_id=source_item.food_id,
            recipe_id=source_item.recipe_id,
            item_kind=source_item.item_kind,
            meal_type=source_item.meal_type,
            position=_next_position(target, cast(MealType, source_item.meal_type)),
            amount=source_item.amount,
            amount_unit=source_item.amount_unit,
            source_name=source_item.source_name,
            source_brand=source_item.source_brand,
        )
        db.add(item)
    target.revision += 1
    return len(pending_items)


def _food_source(
    db: Session,
    user: User,
    food_id: int,
    amount: Decimal,
    amount_unit: str,
) -> tuple[int, str, str | None]:
    food = get_visible_food(db, user, food_id)
    _nutrition_from_calculation(calculate_food_amount(food, amount, amount_unit))
    return food.id, food.name, food.brand


def _recipe_source(
    db: Session,
    user: User,
    recipe_id: int,
    amount: Decimal,
) -> tuple[int, str]:
    recipe = get_owned_recipe(db, user, recipe_id)
    nutrients = calculate_recipe(recipe).nutrients_per_100g
    _nutrition_from_calculation(
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
    return recipe.id, recipe.name


def _item_from_source(
    db: Session,
    user: User,
    plan: NutritionPlan,
    meal_type: MealType,
    payload: NutritionPlanItemCreate,
    *,
    position: int,
    source_template_id: int | None = None,
    amount: Decimal | None = None,
) -> NutritionPlanItem:
    item_amount = amount if amount is not None else payload.amount
    if payload.food_id is not None:
        try:
            food_id, name, brand = _food_source(
                db, user, payload.food_id, item_amount, payload.amount_unit
            )
        except (FoodError, NutritionPlanError) as exc:
            raise NutritionPlanNotFoundError("food not found or has incomplete nutrition") from exc
        return NutritionPlanItem(
            plan=plan,
            source_template_id=source_template_id,
            item_kind="food",
            food_id=food_id,
            meal_type=meal_type,
            position=position,
            amount=item_amount,
            amount_unit=payload.amount_unit,
            source_name=name,
            source_brand=brand,
        )
    if payload.recipe_id is not None:
        try:
            recipe_id, name = _recipe_source(db, user, payload.recipe_id, item_amount)
        except (RecipeError, FoodError, NutritionPlanError) as exc:
            raise NutritionPlanNotFoundError(
                "recipe not found or has incomplete nutrition"
            ) from exc
        return NutritionPlanItem(
            plan=plan,
            source_template_id=source_template_id,
            item_kind="recipe",
            recipe_id=recipe_id,
            meal_type=meal_type,
            position=position,
            amount=item_amount,
            amount_unit="g",
            source_name=name,
            source_brand=None,
        )
    raise NutritionPlanNotFoundError("meal template not found")


def _template_sources(
    db: Session,
    user: User,
    template_id: int,
    multiplier: Decimal,
) -> list[tuple[int | None, int | None, Decimal, str, str, str | None]]:
    template = (
        db.query(NutritionMealTemplate)
        .options(selectinload(NutritionMealTemplate.items))
        .filter(
            NutritionMealTemplate.id == template_id,
            NutritionMealTemplate.owner_user_id == user.id,
        )
        .first()
    )
    if template is None:
        raise NutritionPlanNotFoundError("meal template not found")
    if not template.items:
        raise NutritionPlanError("meal template is empty")

    items: list[tuple[int | None, int | None, Decimal, str, str, str | None]] = []
    for source in template.items:
        amount = source.amount * multiplier
        try:
            if source.item_kind == "food":
                if source.food_id is None:
                    raise FoodError("food is no longer available")
                food_id, name, brand = _food_source(
                    db, user, source.food_id, amount, source.amount_unit
                )
                items.append((food_id, None, amount, source.amount_unit, name, brand))
            else:
                if source.recipe_id is None:
                    raise RecipeError("recipe is no longer available")
                recipe_id, name = _recipe_source(db, user, source.recipe_id, amount)
                items.append((None, recipe_id, amount, "g", name, None))
        except (FoodError, RecipeError, NutritionPlanError) as exc:
            raise NutritionPlanNotFoundError(
                "meal template contains an unavailable or incomplete source"
            ) from exc
    return items


def _fill_item_matches_candidate(
    item: NutritionPlanFillItem,
    candidate_item: object,
) -> bool:
    return item.food_id == getattr(candidate_item, "food_id", None) and item.recipe_id == getattr(
        candidate_item, "recipe_id", None
    )


def fill_plan_from_suggestion(
    db: Session,
    user: User,
    payload: NutritionPlanFillRequest,
    idempotency_key: str,
) -> NutritionPlanDayResponse:
    try:
        fingerprint = _fingerprint(payload.model_dump(mode="json"))
        _lock_user(db, user)
        operation, replayed = _operation(
            db,
            user,
            key=idempotency_key,
            fingerprint=fingerprint,
            kind="fill",
            target_date=payload.plan_date,
        )
        if replayed:
            return _build_day(db, user, operation.target_date, replayed=True)

        plan = _plan_for_write(db, user, payload.plan_date)
        _check_revision(plan, payload.expected_revision)
        suggestions = get_plan_fill_suggestions(db, user, payload.plan_date)
        candidate = next(
            (item for item in suggestions.candidates if item.candidate_id == payload.candidate_id),
            None,
        )
        if candidate is None:
            raise NutritionPlanConflictError(
                "selected plan variant is stale; reload suggestions",
                code="suggestion_stale",
                details={"candidate_id": payload.candidate_id},
            )
        candidate_items = {item.position: item for item in candidate.items}
        if len(plan.items) + len(payload.items) > MAX_ITEMS_PER_DAY:
            raise NutritionPlanError("daily plan item limit reached")
        for fill_item in payload.items:
            candidate_item = candidate_items.get(fill_item.position)
            if candidate_item is None or not _fill_item_matches_candidate(
                fill_item, candidate_item
            ):
                raise NutritionPlanConflictError(
                    "selected plan variant no longer matches the available source",
                    code="suggestion_stale",
                    details={"candidate_id": payload.candidate_id, "position": fill_item.position},
                )
            source = NutritionPlanItemCreate(
                food_id=fill_item.food_id,
                recipe_id=fill_item.recipe_id,
                amount=fill_item.amount,
                amount_unit=fill_item.amount_unit,
            )
            db.add(
                _item_from_source(
                    db,
                    user,
                    plan,
                    payload.meal_type,
                    source,
                    position=_next_position(plan, payload.meal_type),
                    source_template_id=(
                        candidate.identity_id if candidate.candidate_kind == "template" else None
                    ),
                )
            )
        plan.revision += 1
        db.commit()
        return _build_day(db, user, payload.plan_date)
    except Exception:
        db.rollback()
        raise


def _validate_item_source(db: Session, user: User, item: NutritionPlanItem) -> None:
    try:
        if item.item_kind == "food" and item.food_id is not None:
            food = get_visible_food(db, user, item.food_id)
            _nutrition_from_calculation(calculate_food_amount(food, item.amount, item.amount_unit))
            return
        if item.recipe_id is not None and item.amount_unit == "g":
            _recipe_calculation(db, user, item.recipe_id, item.amount)
            return
    except (FoodError, RecipeError, NutritionPlanError) as exc:
        raise NutritionPlanError("planned source cannot be recalculated") from exc
    raise NutritionPlanError("planned source cannot be recalculated")


def _action_response(
    db: Session,
    user: User,
    item: NutritionPlanItem,
    *,
    action: Literal["consume", "edit_and_consume", "skip"],
    replayed: bool,
    diagnostic: str,
) -> NutritionPlanItemActionResponse:
    day = _build_day(db, user, item.plan.plan_date, replayed=replayed)
    response_item = next(
        plan_item for slot in day.slots for plan_item in slot.items if plan_item.id == item.id
    )
    return NutritionPlanItemActionResponse(
        action=action,
        item=response_item,
        day=day,
        diary_entry_id=item.diary_entry_id,
        replayed=replayed,
        diagnostic=diagnostic,
    )


def perform_plan_item_action(
    db: Session,
    user: User,
    item_id: int,
    payload: NutritionPlanItemActionRequest,
    idempotency_key: str,
) -> NutritionPlanItemActionResponse:
    try:
        _lock_user(db, user)
        item = _owned_item_query(db, user, item_id)
        if item is None:
            raise NutritionPlanNotFoundError("planned item not found")
        plan = _plan_for_write(db, user, item.plan.plan_date)
        fingerprint = _fingerprint(
            {
                "item_id": item_id,
                "action": payload.action,
                "amount": payload.amount,
                "amount_unit": payload.amount_unit,
                "meal_type": payload.meal_type,
                "expected_revision": payload.expected_revision,
            }
        )
        if item.action_idempotency_key is not None:
            if item.action_idempotency_key != idempotency_key:
                raise NutritionPlanConflictError(
                    "planned item has already been resolved",
                    code="planned_item_already_resolved",
                    details={
                        "item_id": item.id,
                        "status": item.status,
                        "diary_entry_id": item.diary_entry_id,
                    },
                )
            if item.action_request_fingerprint != fingerprint:
                raise NutritionPlanConflictError(
                    "idempotency key was reused for another planned item action",
                    code="planned_item_idempotency_conflict",
                    details={"item_id": item.id},
                )
            return _action_response(
                db,
                user,
                item,
                action=payload.action,
                replayed=True,
                diagnostic="planned_item_action_replayed",
            )
        if (item.status or "planned") != "planned":
            raise NutritionPlanConflictError(
                "planned item has already been resolved",
                code="planned_item_already_resolved",
                details={
                    "item_id": item.id,
                    "status": item.status,
                    "diary_entry_id": item.diary_entry_id,
                },
            )
        _check_revision(plan, payload.expected_revision)
        if payload.action == "skip":
            item.action_idempotency_key = idempotency_key
            item.action_request_fingerprint = fingerprint
            item.status = "skipped"
            plan.revision += 1
            db.commit()
            return _action_response(
                db,
                user,
                item,
                action=payload.action,
                replayed=False,
                diagnostic="planned_item_skipped",
            )

        if payload.action == "edit_and_consume":
            if payload.meal_type is not None and payload.meal_type != item.meal_type:
                item.meal_type = payload.meal_type
                item.position = _next_position(plan, payload.meal_type)
            item.amount = cast(Decimal, payload.amount)
            item.amount_unit = cast(str, payload.amount_unit)
            if item.item_kind == "recipe" and item.amount_unit != "g":
                raise NutritionPlanError("recipe plan items must use grams")
        _validate_item_source(db, user, item)
        item.action_idempotency_key = idempotency_key
        item.action_request_fingerprint = fingerprint
        diary_item = FoodDiaryBatchItem(
            food_id=item.food_id,
            recipe_id=item.recipe_id,
            amount=item.amount,
            amount_unit=cast(Literal["g", "ml", "serving"], item.amount_unit),
        )
        try:
            batch = create_food_diary_batch(
                db,
                user,
                diary_date=plan.plan_date,
                meal_type=cast(MealType, item.meal_type),
                items=[diary_item],
                idempotency_key=f"planned-item-{item.id}",
                operation_kind="planned_item",
                commit=False,
            )
        except FoodDiaryError as exc:
            raise NutritionPlanError(str(exc), code="planned_item_diary_write_failed") from exc
        if len(batch.entries) != 1:
            raise NutritionPlanError("planned item diary write returned no entry")
        item.diary_entry_id = batch.entries[0].id
        item.status = "consumed"
        plan.revision += 1
        db.commit()
        return _action_response(
            db,
            user,
            item,
            action=payload.action,
            replayed=False,
            diagnostic="planned_item_consumed",
        )
    except Exception:
        db.rollback()
        raise


def add_plan_item(
    db: Session,
    user: User,
    payload: NutritionPlanItemCreate,
    *,
    plan_date: date,
    meal_type: MealType,
    expected_revision: int,
    idempotency_key: str,
) -> NutritionPlanDayResponse:
    try:
        fingerprint = _fingerprint(
            {
                "plan_date": plan_date,
                "meal_type": meal_type,
                "expected_revision": expected_revision,
                **payload.model_dump(mode="json"),
            }
        )
        _lock_user(db, user)
        operation, replayed = _operation(
            db,
            user,
            key=idempotency_key,
            fingerprint=fingerprint,
            kind="add",
            target_date=plan_date,
        )
        if replayed:
            return _build_day(db, user, operation.target_date, replayed=True)

        plan = _plan_for_write(db, user, plan_date)
        _check_revision(plan, expected_revision)
        if payload.template_id is not None:
            template_items = _template_sources(db, user, payload.template_id, payload.amount)
            if len(plan.items) + len(template_items) > MAX_ITEMS_PER_DAY:
                raise NutritionPlanError("daily plan item limit reached")
            for food_id, recipe_id, amount, amount_unit, name, brand in template_items:
                item = NutritionPlanItem(
                    plan=plan,
                    source_template_id=payload.template_id,
                    item_kind="food" if food_id is not None else "recipe",
                    food_id=food_id,
                    recipe_id=recipe_id,
                    meal_type=meal_type,
                    position=_next_position(plan, meal_type),
                    amount=amount,
                    amount_unit=amount_unit,
                    source_name=name,
                    source_brand=brand,
                )
                db.add(item)
        else:
            if len(plan.items) >= MAX_ITEMS_PER_DAY:
                raise NutritionPlanError("daily plan item limit reached")
            item = _item_from_source(
                db,
                user,
                plan,
                meal_type,
                payload,
                position=_next_position(plan, meal_type),
            )
            db.add(item)
        plan.revision += 1
        db.commit()
        return _build_day(db, user, plan_date)
    except Exception:
        db.rollback()
        raise


def _owned_item_query(db: Session, user: User, item_id: int) -> NutritionPlanItem | None:
    return (
        db.query(NutritionPlanItem)
        .join(NutritionPlan, NutritionPlan.id == NutritionPlanItem.plan_id)
        .filter(NutritionPlanItem.id == item_id, NutritionPlan.user_id == user.id)
        .first()
    )


def update_plan_item(
    db: Session,
    user: User,
    item_id: int,
    payload: NutritionPlanItemUpdate,
) -> NutritionPlanDayResponse:
    try:
        item = _owned_item_query(db, user, item_id)
        if item is None:
            raise NutritionPlanNotFoundError("planned item not found")
        if (item.status or "planned") != "planned":
            raise NutritionPlanConflictError(
                "resolved planned items cannot be edited",
                code="planned_item_already_resolved",
                details={"item_id": item.id, "status": item.status},
            )
        plan_date = item.plan.plan_date
        _lock_user(db, user)
        plan = _plan_for_write(db, user, plan_date)
        _check_revision(plan, payload.expected_revision)
        if payload.meal_type is not None and payload.meal_type != item.meal_type:
            position = _next_position(plan, payload.meal_type)
            item.meal_type = payload.meal_type
            item.position = position
        if payload.amount is not None:
            item.amount = payload.amount
        if payload.amount_unit is not None:
            item.amount_unit = payload.amount_unit
        if item.item_kind == "recipe" and item.amount_unit != "g":
            raise NutritionPlanError("recipe plan items must use grams")
        if item.item_kind == "food" and item.food_id is not None:
            try:
                food = get_visible_food(db, user, item.food_id)
                _nutrition_from_calculation(
                    calculate_food_amount(food, item.amount, item.amount_unit)
                )
            except (FoodError, NutritionPlanError) as exc:
                raise NutritionPlanError("planned source cannot be recalculated") from exc
        else:
            try:
                _recipe_calculation(db, user, cast(int, item.recipe_id), item.amount)
            except (RecipeError, FoodError, NutritionPlanError) as exc:
                raise NutritionPlanError("planned source cannot be recalculated") from exc
        plan.revision += 1
        db.commit()
        return _build_day(db, user, plan.plan_date)
    except Exception:
        db.rollback()
        raise


def delete_plan_item(
    db: Session,
    user: User,
    item_id: int,
    expected_revision: int,
) -> NutritionPlanDayResponse:
    try:
        item = _owned_item_query(db, user, item_id)
        if item is None:
            raise NutritionPlanNotFoundError("planned item not found")
        if item.status != "planned":
            raise NutritionPlanConflictError(
                "resolved planned items cannot be deleted",
                code="planned_item_already_resolved",
                details={"item_id": item.id, "status": item.status},
            )
        plan_date = item.plan.plan_date
        _lock_user(db, user)
        plan = _plan_for_write(db, user, plan_date)
        _check_revision(plan, expected_revision)
        db.delete(item)
        plan.revision += 1
        db.commit()
        return _build_day(db, user, plan_date)
    except Exception:
        db.rollback()
        raise


def copy_plan_day(
    db: Session,
    user: User,
    payload: NutritionPlanCopyRequest,
    idempotency_key: str,
) -> NutritionPlanDayResponse:
    try:
        _lock_user(db, user)
        operation, replayed = _operation(
            db,
            user,
            key=idempotency_key,
            fingerprint=_fingerprint(payload.model_dump(mode="json")),
            kind="copy",
            target_date=payload.target_date,
        )
        if replayed:
            return _build_day(db, user, operation.target_date, replayed=True)

        source = _plan_query(db, user, payload.source_date)
        target = _plan_for_write(db, user, payload.target_date)
        _check_revision(target, payload.expected_revision)
        source_items = list(source.items) if source is not None else []
        if len(target.items) + len(source_items) > MAX_ITEMS_PER_DAY:
            raise NutritionPlanError("daily plan item limit reached")
        for source_item in source_items:
            item = NutritionPlanItem(
                plan=target,
                source_template_id=source_item.source_template_id,
                food_id=source_item.food_id,
                recipe_id=source_item.recipe_id,
                item_kind=source_item.item_kind,
                meal_type=source_item.meal_type,
                position=_next_position(target, cast(MealType, source_item.meal_type)),
                amount=source_item.amount,
                amount_unit=source_item.amount_unit,
                source_name=source_item.source_name,
                source_brand=source_item.source_brand,
            )
            db.add(item)
        if source_items:
            target.revision += 1
        db.commit()
        return _build_day(db, user, payload.target_date)
    except Exception:
        db.rollback()
        raise
