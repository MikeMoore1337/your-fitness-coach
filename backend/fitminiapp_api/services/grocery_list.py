from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, cast

from sqlalchemy.orm import Session, selectinload

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.models.grocery_list import (
    GroceryList,
    GroceryListItem,
    GroceryListItemSource,
)
from fitminiapp_api.models.nutrition_plan import NutritionPlan, NutritionPlanItem
from fitminiapp_api.models.recipe import Recipe, RecipeIngredient
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.grocery_list import (
    GroceryAmountUnit,
    GroceryListItemResponse,
    GroceryListItemSourceResponse,
    GroceryListItemUpdate,
    GroceryListManualItemCreate,
    GroceryListResponse,
    GroceryListStaleSourceResponse,
)
from fitminiapp_api.services.recipes import RecipeError, calculate_recipe

GrocerySourceKind = Literal["generated", "manual"]
GROCERY_UNITS = frozenset(("g", "ml", "piece", "serving"))
AMOUNT_QUANTUM = Decimal("0.001")
WEEK_LENGTH = 7


class GroceryListError(ValueError):
    pass


class GroceryListNotFoundError(GroceryListError):
    pass


class GroceryListConflictError(GroceryListError):
    pass


@dataclass(frozen=True)
class _Source:
    plan_item_id: int
    recipe_id: int | None
    plan_date: date
    meal_type: str
    recipe_name: str


@dataclass
class _DerivedItem:
    aggregation_key: str
    food_id: int | None
    name: str
    brand: str | None
    amount: Decimal
    amount_unit: GroceryAmountUnit
    sources: list[_Source] = field(default_factory=list)


@dataclass(frozen=True)
class _StaleSource:
    plan_item_id: int
    recipe_id: int | None
    plan_date: date
    meal_type: str
    source_name: str
    reason: str


def _week_end(week_start: date) -> date:
    return week_start + timedelta(days=WEEK_LENGTH - 1)


def _normalize_key(value: str | None) -> str:
    return " ".join((value or "").split()).casefold()


def _amount(value: Decimal) -> Decimal:
    return value.quantize(AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)


def _aggregation_key(
    ingredient: RecipeIngredient,
    amount_unit: GroceryAmountUnit,
) -> str:
    if ingredient.food_id is not None:
        identity = f"food:{ingredient.food_id}"
    else:
        identity = f"snapshot:{_normalize_key(ingredient.food_name)}|{_normalize_key(ingredient.food_brand)}"
    return f"{identity}|unit:{amount_unit}"


def _ingredient_amount(
    ingredient: RecipeIngredient,
    scale: Decimal,
) -> tuple[Decimal, GroceryAmountUnit]:
    if ingredient.amount_unit == "g":
        return _amount(ingredient.amount * scale), "g"
    if ingredient.amount_unit != "serving":
        raise RecipeError("recipe ingredient unit is unavailable")
    serving_unit = ingredient.serving_unit
    if ingredient.serving_amount is None or serving_unit not in GROCERY_UNITS:
        raise RecipeError("recipe ingredient serving unit is unavailable")
    return _amount(ingredient.amount * ingredient.serving_amount * scale), cast(
        GroceryAmountUnit, serving_unit
    )


def _stale_source(
    item: NutritionPlanItem,
    *,
    plan_date: date,
    reason: str,
) -> _StaleSource:
    return _StaleSource(
        plan_item_id=item.id,
        recipe_id=item.recipe_id,
        plan_date=plan_date,
        meal_type=item.meal_type,
        source_name=item.source_name,
        reason=reason,
    )


def _collect_derived(
    db: Session,
    user: User,
    week_start: date,
) -> tuple[list[_DerivedItem], list[_StaleSource]]:
    week_end = _week_end(week_start)
    rows = (
        db.query(NutritionPlanItem, NutritionPlan.plan_date)
        .join(NutritionPlan, NutritionPlan.id == NutritionPlanItem.plan_id)
        .filter(
            NutritionPlan.user_id == user.id,
            NutritionPlan.plan_date >= week_start,
            NutritionPlan.plan_date <= week_end,
            NutritionPlanItem.item_kind == "recipe",
        )
        .order_by(
            NutritionPlan.plan_date.asc(),
            NutritionPlanItem.meal_type.asc(),
            NutritionPlanItem.position.asc(),
            NutritionPlanItem.id.asc(),
        )
        .all()
    )
    recipe_ids = {item.recipe_id for item, _ in rows if item.recipe_id is not None}
    recipes = (
        db.query(Recipe)
        .options(selectinload(Recipe.ingredients))
        .filter(Recipe.owner_user_id == user.id, Recipe.id.in_(recipe_ids))
        .all()
        if recipe_ids
        else []
    )
    recipes_by_id = {recipe.id: recipe for recipe in recipes}
    derived: dict[str, _DerivedItem] = {}
    stale: list[_StaleSource] = []

    for item, plan_date in rows:
        recipe = recipes_by_id.get(item.recipe_id) if item.recipe_id is not None else None
        if recipe is None:
            stale.append(
                _stale_source(
                    item,
                    plan_date=plan_date,
                    reason="Рецепт больше недоступен; обновите план или список.",
                )
            )
            continue
        try:
            calculation = calculate_recipe(recipe)
            scale = item.amount / calculation.effective_weight_g
            values = [
                (*_ingredient_amount(ingredient, scale), ingredient)
                for ingredient in recipe.ingredients
            ]
        except RecipeError, ArithmeticError:
            stale.append(
                _stale_source(
                    item,
                    plan_date=plan_date,
                    reason="Состав рецепта недоступен; обновите рецепт и список.",
                )
            )
            continue

        source = _Source(
            plan_item_id=item.id,
            recipe_id=recipe.id,
            plan_date=plan_date,
            meal_type=item.meal_type,
            recipe_name=recipe.name,
        )
        for amount, amount_unit, ingredient in values:
            key = _aggregation_key(ingredient, amount_unit)
            current = derived.get(key)
            if current is None:
                derived[key] = _DerivedItem(
                    aggregation_key=key,
                    food_id=ingredient.food_id,
                    name=ingredient.food_name,
                    brand=ingredient.food_brand,
                    amount=amount,
                    amount_unit=amount_unit,
                    sources=[source],
                )
            else:
                current.amount = _amount(current.amount + amount)
                if source not in current.sources:
                    current.sources.append(source)

    return sorted(
        derived.values(),
        key=lambda value: (value.name.casefold(), value.amount_unit, value.aggregation_key),
    ), stale


def _list_query(
    db: Session,
    user: User,
    week_start: date,
    *,
    for_update: bool = False,
) -> GroceryList | None:
    query = (
        db.query(GroceryList)
        .options(selectinload(GroceryList.items).selectinload(GroceryListItem.sources))
        .filter(GroceryList.user_id == user.id, GroceryList.week_start == week_start)
    )
    if for_update:
        query = query.with_for_update()
    return query.first()


def _get_or_create_list(db: Session, user: User, week_start: date) -> GroceryList:
    grocery_list = _list_query(db, user, week_start, for_update=True)
    if grocery_list is not None:
        return grocery_list
    grocery_list = GroceryList(user_id=user.id, week_start=week_start)
    db.add(grocery_list)
    db.flush()
    return grocery_list


def _source_signature(source: _Source | GroceryListItemSource) -> tuple[object, ...]:
    return (
        source.plan_item_id,
        source.recipe_id,
        source.plan_date,
        source.meal_type,
        source.recipe_name,
    )


def _needs_refresh(grocery_list: GroceryList, derived: list[_DerivedItem]) -> bool:
    stored = {
        item.aggregation_key: item
        for item in grocery_list.items
        if item.source_kind == "generated" and item.aggregation_key is not None
    }
    if set(stored) != {item.aggregation_key for item in derived}:
        return True
    for item in derived:
        existing = stored[item.aggregation_key]
        if (
            existing.food_id != item.food_id
            or existing.name != item.name
            or existing.brand != item.brand
            or existing.amount != item.amount
            or existing.amount_unit != item.amount_unit
            or sorted(
                (_source_signature(source) for source in existing.sources),
                key=lambda signature: tuple(repr(value) for value in signature),
            )
            != sorted(
                (_source_signature(source) for source in item.sources),
                key=lambda signature: tuple(repr(value) for value in signature),
            )
        ):
            return True
    return False


def _serialize_item(item: GroceryListItem) -> GroceryListItemResponse:
    return GroceryListItemResponse(
        id=item.id,
        source_kind=cast(GrocerySourceKind, item.source_kind),
        food_id=item.food_id,
        name=item.name,
        brand=item.brand,
        amount=item.amount,
        amount_unit=(cast(GroceryAmountUnit, item.amount_unit) if item.amount_unit else None),
        checked=item.checked,
        owned=item.owned,
        sources=[
            GroceryListItemSourceResponse(
                plan_item_id=source.plan_item_id,
                recipe_id=source.recipe_id,
                plan_date=source.plan_date,
                meal_type=cast(Literal["breakfast", "lunch", "dinner", "snacks"], source.meal_type),
                recipe_name=source.recipe_name,
            )
            for source in item.sources
        ],
    )


def _serialize_list(
    db: Session,
    user: User,
    grocery_list: GroceryList,
    *,
    derived: list[_DerivedItem] | None = None,
    stale: list[_StaleSource] | None = None,
) -> GroceryListResponse:
    current_derived = derived
    current_stale = stale
    if grocery_list.generated_at is not None and current_derived is None:
        current_derived, current_stale = _collect_derived(db, user, grocery_list.week_start)
    current_stale = current_stale or []
    return GroceryListResponse(
        id=grocery_list.id,
        week_start=grocery_list.week_start,
        week_end=_week_end(grocery_list.week_start),
        generated=grocery_list.generated_at is not None,
        refresh_required=(
            bool(current_stale)
            or (current_derived is not None and _needs_refresh(grocery_list, current_derived))
        ),
        updated_at=grocery_list.updated_at,
        items=[_serialize_item(item) for item in grocery_list.items],
        stale_sources=[
            GroceryListStaleSourceResponse(
                plan_item_id=source.plan_item_id,
                recipe_id=source.recipe_id,
                plan_date=source.plan_date,
                meal_type=cast(Literal["breakfast", "lunch", "dinner", "snacks"], source.meal_type),
                source_name=source.source_name,
                reason=source.reason,
            )
            for source in current_stale
        ],
    )


def _empty_response(week_start: date) -> GroceryListResponse:
    return GroceryListResponse(
        id=None,
        week_start=week_start,
        week_end=_week_end(week_start),
        generated=False,
        refresh_required=False,
        updated_at=None,
        items=[],
        stale_sources=[],
    )


def get_grocery_list(db: Session, user: User, week_start: date) -> GroceryListResponse:
    grocery_list = _list_query(db, user, week_start)
    return (
        _empty_response(week_start)
        if grocery_list is None
        else _serialize_list(db, user, grocery_list)
    )


def _lock_user(db: Session, user: User) -> None:
    db.query(User.id).filter(User.id == user.id).with_for_update().one()


def generate_grocery_list(db: Session, user: User, week_start: date) -> GroceryListResponse:
    try:
        _lock_user(db, user)
        grocery_list = _get_or_create_list(db, user, week_start)
        derived, _stale = _collect_derived(db, user, week_start)
        existing_generated = {
            item.aggregation_key: item
            for item in grocery_list.items
            if item.source_kind == "generated" and item.aggregation_key is not None
        }
        seen_keys: set[str] = set()
        for position, value in enumerate(derived):
            seen_keys.add(value.aggregation_key)
            item = existing_generated.get(value.aggregation_key)
            if item is None:
                item = GroceryListItem(
                    grocery_list=grocery_list,
                    source_kind="generated",
                    aggregation_key=value.aggregation_key,
                    checked=False,
                    owned=False,
                )
                db.add(item)
            item.food_id = value.food_id
            item.name = value.name
            item.brand = value.brand
            item.amount = value.amount
            item.amount_unit = value.amount_unit
            item.position = position
            if item.sources:
                item.sources.clear()
                db.flush()
            item.sources.extend(
                GroceryListItemSource(
                    plan_item_id=source.plan_item_id,
                    recipe_id=source.recipe_id,
                    plan_date=source.plan_date,
                    meal_type=source.meal_type,
                    recipe_name=source.recipe_name,
                )
                for source in value.sources
            )
        for key, item in existing_generated.items():
            if key not in seen_keys:
                db.delete(item)
        manual_items = [item for item in grocery_list.items if item.source_kind == "manual"]
        for manual_position, item in enumerate(manual_items, start=len(derived)):
            if item.position != manual_position:
                item.position = manual_position
        grocery_list.generated_at = now_msk_naive()
        db.commit()
        return get_grocery_list(db, user, week_start)
    except Exception:
        db.rollback()
        raise


def add_manual_item(
    db: Session,
    user: User,
    payload: GroceryListManualItemCreate,
) -> GroceryListResponse:
    try:
        _lock_user(db, user)
        grocery_list = _get_or_create_list(db, user, payload.week_start)
        position = max((item.position for item in grocery_list.items), default=-1) + 1
        db.add(
            GroceryListItem(
                grocery_list=grocery_list,
                source_kind="manual",
                name=payload.name,
                amount=payload.amount,
                amount_unit=payload.amount_unit,
                position=position,
            )
        )
        db.commit()
        return get_grocery_list(db, user, payload.week_start)
    except Exception:
        db.rollback()
        raise


def _owned_item_query(db: Session, user: User, item_id: int) -> GroceryListItem | None:
    return (
        db.query(GroceryListItem)
        .join(GroceryList, GroceryList.id == GroceryListItem.grocery_list_id)
        .options(selectinload(GroceryListItem.sources), selectinload(GroceryListItem.grocery_list))
        .filter(GroceryListItem.id == item_id, GroceryList.user_id == user.id)
        .first()
    )


def update_grocery_item(
    db: Session,
    user: User,
    item_id: int,
    payload: GroceryListItemUpdate,
) -> GroceryListResponse:
    try:
        item = _owned_item_query(db, user, item_id)
        if item is None:
            raise GroceryListNotFoundError("grocery list item not found")
        fields = payload.model_fields_set
        content_fields = fields & {"name", "amount", "amount_unit"}
        if item.source_kind == "generated" and content_fields:
            raise GroceryListConflictError("generated grocery items are refreshed from the plan")
        if "checked" in fields:
            item.checked = cast(bool, payload.checked)
        if "owned" in fields:
            item.owned = cast(bool, payload.owned)
        if item.source_kind == "manual":
            if "name" in fields:
                item.name = cast(str, payload.name)
            next_amount = payload.amount if "amount" in fields else item.amount
            next_unit = payload.amount_unit if "amount_unit" in fields else item.amount_unit
            if (next_amount is None) != (next_unit is None):
                raise GroceryListError("amount and amount_unit must be provided together")
            item.amount = next_amount
            item.amount_unit = next_unit
        db.commit()
        return get_grocery_list(db, user, item.grocery_list.week_start)
    except Exception:
        db.rollback()
        raise


def delete_grocery_item(db: Session, user: User, item_id: int) -> GroceryListResponse:
    try:
        item = _owned_item_query(db, user, item_id)
        if item is None:
            raise GroceryListNotFoundError("grocery list item not found")
        if item.source_kind != "manual":
            raise GroceryListConflictError("generated grocery items are refreshed from the plan")
        week_start = item.grocery_list.week_start
        db.delete(item)
        db.commit()
        return get_grocery_list(db, user, week_start)
    except Exception:
        db.rollback()
        raise
