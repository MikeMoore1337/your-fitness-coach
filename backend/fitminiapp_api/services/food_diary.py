from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Literal, cast

from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import get_user_timezone_name, today_for_user
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.food_diary import (
    FoodDiaryCopyOperation,
    FoodDiaryDayStatus,
    FoodDiaryEntry,
)
from fitminiapp_api.models.recipe import Recipe
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.food_diary import (
    DiaryAmountUnit,
    FoodDiaryCopyDay,
    FoodDiaryCopyMeal,
    FoodDiaryCopyProduct,
    FoodDiaryCopyResponse,
    FoodDiaryDayResponse,
    FoodDiaryDayStatusUpdate,
    FoodDiaryEntryCreate,
    FoodDiaryEntryResponse,
    FoodDiaryEntryUpdate,
    FoodDiaryMeal,
    FoodDiaryNutrition,
    FoodDiaryQuickAdd,
    FoodDiaryTargets,
    MealType,
)
from fitminiapp_api.services.diary_nutrition import diary_entry_nutrition
from fitminiapp_api.services.foods import (
    FoodError,
    FoodNutrition,
    calculate_food_amount,
    get_visible_food,
)
from fitminiapp_api.services.nutrition import get_nutrition_target_for_user
from fitminiapp_api.services.recipes import (
    RecipeCalculation,
    RecipeError,
    RecipeNotFoundError,
    calculate_recipe,
    get_owned_recipe,
)

MEAL_TYPES: tuple[MealType, ...] = ("breakfast", "lunch", "dinner", "snacks")
ZERO = Decimal("0")
CopyScope = Literal["product", "meal", "day"]


class FoodDiaryError(ValueError):
    pass


class FoodDiaryNotFoundError(FoodDiaryError):
    pass


class FoodDiaryConflictError(FoodDiaryError):
    pass


def _validate_diary_date(user: User, value: date) -> None:
    if value > today_for_user(user):
        raise FoodDiaryError("future diary dates are not allowed")


def _stored_day_status(db: Session, user: User, diary_date: date) -> FoodDiaryDayStatus | None:
    return db.get(FoodDiaryDayStatus, (user.id, diary_date))


def _ensure_day_accepts_entries(db: Session, user: User, diary_date: date) -> None:
    status = _stored_day_status(db, user, diary_date)
    if status is not None and status.status == "fasted":
        raise FoodDiaryConflictError(
            "day is marked as fasted; change completeness before adding food"
        )


def _visible_food(db: Session, user: User, food_id: int) -> Food:
    try:
        return get_visible_food(db, user, food_id)
    except FoodError as exc:
        raise FoodDiaryNotFoundError("food not found") from exc


def _owned_recipe(db: Session, user: User, recipe_id: int) -> Recipe:
    try:
        return get_owned_recipe(db, user, recipe_id)
    except RecipeNotFoundError as exc:
        raise FoodDiaryNotFoundError("recipe not found") from exc


def _calculate_amount(
    food: Food,
    amount: Decimal,
    amount_unit: DiaryAmountUnit,
) -> FoodNutrition:
    try:
        return calculate_food_amount(food, amount, amount_unit)
    except FoodError as exc:
        raise FoodDiaryError(str(exc)) from exc


def _recipe_as_food(calculation: RecipeCalculation) -> Food:
    nutrients = calculation.nutrients_per_100g
    return Food(
        energy_kcal_per_100g=nutrients.energy_kcal_per_100g,
        protein_g_per_100g=nutrients.protein_g_per_100g,
        fat_g_per_100g=nutrients.fat_g_per_100g,
        carbs_g_per_100g=nutrients.carbs_g_per_100g,
        fiber_g_per_100g=nutrients.fiber_g_per_100g,
    )


def _entry_snapshot_as_food(entry: FoodDiaryEntry) -> Food:
    return Food(
        energy_kcal_per_100g=entry.energy_kcal_per_100g,
        protein_g_per_100g=entry.protein_g_per_100g,
        fat_g_per_100g=entry.fat_g_per_100g,
        carbs_g_per_100g=entry.carbs_g_per_100g,
        fiber_g_per_100g=entry.fiber_g_per_100g,
        standard_serving_weight_g=entry.serving_weight_g,
        nutrition_basis_kind=entry.nutrition_basis_kind or "per_100_g",
        nutrition_basis_amount=entry.nutrition_basis_amount or Decimal("100"),
        nutrition_basis_unit=entry.nutrition_basis_unit or "g",
        canonical_facts=entry.nutrition_snapshot,
    )


def _copy_food_snapshot(entry: FoodDiaryEntry, food: Food) -> None:
    entry.entry_kind = "food"
    entry.food_id = food.id
    entry.recipe_id = None
    entry.food_name = food.name
    entry.food_brand = food.brand
    entry.energy_kcal_per_100g = food.energy_kcal_per_100g
    entry.protein_g_per_100g = food.protein_g_per_100g
    entry.fat_g_per_100g = food.fat_g_per_100g
    entry.carbs_g_per_100g = food.carbs_g_per_100g
    entry.fiber_g_per_100g = food.fiber_g_per_100g
    entry.nutrition_basis_kind = food.nutrition_basis_kind
    entry.nutrition_basis_amount = food.nutrition_basis_amount
    entry.nutrition_basis_unit = food.nutrition_basis_unit
    entry.nutrition_snapshot = food.canonical_facts
    entry.serving_amount = food.standard_serving_amount
    entry.serving_unit = food.standard_serving_unit
    entry.serving_weight_g = food.standard_serving_weight_g


def _copy_recipe_snapshot(
    entry: FoodDiaryEntry,
    recipe: Recipe,
    calculation: RecipeCalculation,
) -> None:
    entry.entry_kind = "recipe"
    nutrients = calculation.nutrients_per_100g
    entry.food_id = None
    entry.recipe_id = recipe.id
    entry.food_name = recipe.name
    entry.food_brand = None
    entry.energy_kcal_per_100g = nutrients.energy_kcal_per_100g
    entry.protein_g_per_100g = nutrients.protein_g_per_100g
    entry.fat_g_per_100g = nutrients.fat_g_per_100g
    entry.carbs_g_per_100g = nutrients.carbs_g_per_100g
    entry.fiber_g_per_100g = nutrients.fiber_g_per_100g
    entry.serving_amount = None
    entry.serving_unit = None
    entry.serving_weight_g = None
    entry.nutrition_basis_kind = "per_100_g"
    entry.nutrition_basis_amount = Decimal("100")
    entry.nutrition_basis_unit = "g"
    entry.nutrition_snapshot = None


def _entry_nutrition(entry: FoodDiaryEntry) -> FoodDiaryNutrition:
    values = diary_entry_nutrition(entry)
    if values.energy_kcal is None:
        raise FoodDiaryError("historical entry has no nutrition snapshot")
    return FoodDiaryNutrition(
        energy_kcal=values.energy_kcal,
        protein_g=values.protein_g,
        fat_g=values.fat_g,
        carbs_g=values.carbs_g,
        fiber_g=values.fiber_g,
    )


def _set_nutrition_amount(entry: FoodDiaryEntry, calculation: FoodNutrition) -> None:
    entry.nutrition_amount = {
        "energy_kcal": str(calculation.energy_kcal)
        if calculation.energy_kcal is not None
        else None,
        "protein_g": str(calculation.protein_g) if calculation.protein_g is not None else None,
        "fat_g": str(calculation.fat_g) if calculation.fat_g is not None else None,
        "carbs_g": str(calculation.carbs_g) if calculation.carbs_g is not None else None,
        "fiber_g": str(calculation.fiber_g) if calculation.fiber_g is not None else None,
    }


def _serialize_entry(entry: FoodDiaryEntry) -> FoodDiaryEntryResponse:
    return FoodDiaryEntryResponse(
        id=entry.id,
        diary_date=entry.diary_date,
        meal_type=cast(MealType, entry.meal_type),
        food_id=entry.food_id,
        recipe_id=entry.recipe_id,
        entry_kind=cast(Literal["food", "recipe", "quick_add"], entry.entry_kind),
        logged_at=entry.logged_at,
        food_name=entry.food_name,
        food_brand=entry.food_brand,
        amount=entry.amount,
        amount_unit=cast(DiaryAmountUnit, entry.amount_unit),
        weight_g=entry.weight_g,
        nutrition_basis_kind=cast(
            Literal["per_100_g", "per_100_ml", "per_serving"] | None,
            entry.nutrition_basis_kind,
        ),
        nutrition_basis_amount=entry.nutrition_basis_amount,
        nutrition_basis_unit=cast(Literal["g", "ml", "serving"] | None, entry.nutrition_basis_unit),
        serving_amount=entry.serving_amount,
        serving_unit=entry.serving_unit,
        serving_weight_g=entry.serving_weight_g,
        nutrition=_entry_nutrition(entry),
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def _sum_nutrition(values: list[FoodDiaryNutrition]) -> FoodDiaryNutrition:
    fiber_values = [value.fiber_g for value in values]
    fiber = ZERO if not fiber_values else None
    if fiber_values and all(value is not None for value in fiber_values):
        fiber = sum((value for value in fiber_values if value is not None), start=ZERO)

    def optional_sum(items: list[Decimal | None]) -> Decimal | None:
        if any(item is None for item in items):
            return None
        return sum((cast(Decimal, item) for item in items), start=ZERO)

    return FoodDiaryNutrition(
        energy_kcal=sum((value.energy_kcal for value in values), start=ZERO),
        protein_g=optional_sum([value.protein_g for value in values]),
        fat_g=optional_sum([value.fat_g for value in values]),
        carbs_g=optional_sum([value.carbs_g for value in values]),
        fiber_g=fiber,
    )


def create_food_diary_entry(
    db: Session,
    user: User,
    payload: FoodDiaryEntryCreate,
    idempotency_key: str | None = None,
) -> FoodDiaryEntryResponse:
    _validate_diary_date(user, payload.diary_date)
    _ensure_day_accepts_entries(db, user, payload.diary_date)
    key = _normalize_idempotency_key(idempotency_key) if idempotency_key is not None else None
    fingerprint = _request_fingerprint("entry", payload) if key is not None else None
    if key is not None:
        existing = (
            db.query(FoodDiaryEntry)
            .filter(
                FoodDiaryEntry.user_id == user.id,
                FoodDiaryEntry.idempotency_key == key,
            )
            .first()
        )
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise FoodDiaryConflictError("Idempotency-Key was already used for another request")
            return _serialize_entry(existing)
    entry = FoodDiaryEntry(
        user_id=user.id,
        diary_date=payload.diary_date,
        meal_type=payload.meal_type,
        logged_at=payload.logged_at,
        amount=payload.amount,
        amount_unit=payload.amount_unit,
        idempotency_key=key,
        request_fingerprint=fingerprint,
    )
    if payload.food_id is not None:
        food = _visible_food(db, user, payload.food_id)
        calculation = _calculate_amount(food, payload.amount, payload.amount_unit)
        _copy_food_snapshot(entry, food)
        entry.entry_kind = "food"
        entry.weight_g = calculation.weight_g
        _set_nutrition_amount(entry, calculation)
    elif payload.recipe_id is not None:
        recipe = _owned_recipe(db, user, payload.recipe_id)
        try:
            recipe_calculation = calculate_recipe(recipe)
        except RecipeError as exc:
            raise FoodDiaryError(str(exc)) from exc
        calculation = _calculate_amount(_recipe_as_food(recipe_calculation), payload.amount, "g")
        _copy_recipe_snapshot(entry, recipe, recipe_calculation)
        entry.entry_kind = "recipe"
        entry.weight_g = calculation.weight_g
        _set_nutrition_amount(entry, calculation)
    else:
        quick_add = cast(FoodDiaryQuickAdd, payload.quick_add)
        entry.entry_kind = "quick_add"
        entry.food_name = quick_add.name or "Быстрый ввод"
        entry.food_brand = None
        entry.weight_g = Decimal("1")
        entry.energy_kcal_per_100g = ZERO
        entry.protein_g_per_100g = ZERO
        entry.fat_g_per_100g = ZERO
        entry.carbs_g_per_100g = ZERO
        entry.fiber_g_per_100g = None
        entry.serving_amount = Decimal("1")
        entry.serving_unit = "serving"
        entry.serving_weight_g = Decimal("1")
        entry.nutrition_basis_kind = "per_serving"
        entry.nutrition_basis_amount = Decimal("1")
        entry.nutrition_basis_unit = "serving"
        entry.nutrition_snapshot = None
        entry.nutrition_amount = {
            "energy_kcal": str(quick_add.energy_kcal),
            "protein_g": str(quick_add.protein_g) if quick_add.protein_g is not None else None,
            "fat_g": str(quick_add.fat_g) if quick_add.fat_g is not None else None,
            "carbs_g": str(quick_add.carbs_g) if quick_add.carbs_g is not None else None,
            "fiber_g": None,
        }
        entry.quick_energy_kcal = quick_add.energy_kcal
        entry.quick_protein_g = quick_add.protein_g
        entry.quick_fat_g = quick_add.fat_g
        entry.quick_carbs_g = quick_add.carbs_g
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if key is None:
            raise
        existing = (
            db.query(FoodDiaryEntry)
            .filter(
                FoodDiaryEntry.user_id == user.id,
                FoodDiaryEntry.idempotency_key == key,
            )
            .first()
        )
        if existing is None:
            raise FoodDiaryConflictError("diary entry could not be created")
        if existing.request_fingerprint != fingerprint:
            raise FoodDiaryConflictError("Idempotency-Key was already used for another request")
        return _serialize_entry(existing)
    db.refresh(entry)
    return _serialize_entry(entry)


def update_food_diary_entry(
    db: Session,
    user: User,
    entry_id: int,
    payload: FoodDiaryEntryUpdate,
) -> FoodDiaryEntryResponse:
    entry = (
        db.query(FoodDiaryEntry)
        .filter(FoodDiaryEntry.id == entry_id, FoodDiaryEntry.user_id == user.id)
        .first()
    )
    if entry is None:
        raise FoodDiaryNotFoundError("diary entry not found")

    if (
        entry.entry_kind == "quick_add"
        and {
            "food_id",
            "recipe_id",
            "amount",
            "amount_unit",
        }
        & payload.model_fields_set
    ):
        raise FoodDiaryError("quick add totals cannot be changed through quantity editing")

    diary_date = payload.diary_date if payload.diary_date is not None else entry.diary_date
    _validate_diary_date(user, diary_date)
    if diary_date != entry.diary_date:
        _ensure_day_accepts_entries(db, user, diary_date)
    food = _visible_food(db, user, payload.food_id) if payload.food_id is not None else None
    recipe = _owned_recipe(db, user, payload.recipe_id) if payload.recipe_id is not None else None
    amount = payload.amount if payload.amount is not None else entry.amount
    amount_unit = (
        payload.amount_unit
        if payload.amount_unit is not None
        else cast(DiaryAmountUnit, entry.amount_unit)
    )

    if (
        recipe is not None or (food is None and entry.recipe_id is not None)
    ) and amount_unit != "g":
        raise FoodDiaryError("recipe diary entries must use grams")
    if food is not None:
        calculation_food = food
    elif recipe is not None:
        try:
            recipe_calculation = calculate_recipe(recipe)
        except RecipeError as exc:
            raise FoodDiaryError(str(exc)) from exc
        calculation_food = _recipe_as_food(recipe_calculation)
    else:
        calculation_food = _entry_snapshot_as_food(entry)
    calculation = _calculate_amount(calculation_food, amount, amount_unit)

    if food is not None:
        _copy_food_snapshot(entry, food)
    elif recipe is not None:
        _copy_recipe_snapshot(entry, recipe, recipe_calculation)
    entry.diary_date = diary_date
    if payload.meal_type is not None:
        entry.meal_type = payload.meal_type
    if payload.logged_at is not None:
        entry.logged_at = payload.logged_at
    entry.amount = amount
    entry.amount_unit = amount_unit
    entry.weight_g = calculation.weight_g
    _set_nutrition_amount(entry, calculation)
    db.commit()
    db.refresh(entry)
    return _serialize_entry(entry)


def delete_food_diary_entry(db: Session, user: User, entry_id: int) -> None:
    entry = (
        db.query(FoodDiaryEntry)
        .filter(FoodDiaryEntry.id == entry_id, FoodDiaryEntry.user_id == user.id)
        .first()
    )
    if entry is None:
        raise FoodDiaryNotFoundError("diary entry not found")
    status = _stored_day_status(db, user, entry.diary_date)
    db.delete(entry)
    db.flush()
    if status is not None and status.status == "complete":
        remaining = (
            db.query(FoodDiaryEntry.id)
            .filter(
                FoodDiaryEntry.user_id == user.id,
                FoodDiaryEntry.diary_date == entry.diary_date,
            )
            .first()
        )
        if remaining is None:
            db.delete(status)
    db.commit()


def get_food_diary_day(
    db: Session,
    user: User,
    diary_date: date | None,
) -> FoodDiaryDayResponse:
    selected_date = diary_date or today_for_user(user)
    _validate_diary_date(user, selected_date)
    entries = (
        db.query(FoodDiaryEntry)
        .filter(
            FoodDiaryEntry.user_id == user.id,
            FoodDiaryEntry.diary_date == selected_date,
        )
        .order_by(FoodDiaryEntry.meal_type.asc(), FoodDiaryEntry.id.asc())
        .all()
    )
    serialized = [_serialize_entry(entry) for entry in entries]
    meals = []
    for meal_type in MEAL_TYPES:
        meal_entries = [entry for entry in serialized if entry.meal_type == meal_type]
        meals.append(
            FoodDiaryMeal(
                meal_type=meal_type,
                entries=meal_entries,
                totals=_sum_nutrition([entry.nutrition for entry in meal_entries]),
            )
        )
    totals = _sum_nutrition([entry.nutrition for entry in serialized])
    stored_status = _stored_day_status(db, user, selected_date)
    day_status = (
        stored_status.status
        if stored_status is not None
        else ("incomplete" if serialized else "unlogged")
    )

    nutrition_target = get_nutrition_target_for_user(db, user)
    targets = None
    remaining = None
    if nutrition_target is not None:
        targets = FoodDiaryTargets(
            energy_kcal=Decimal(nutrition_target.calories),
            protein_g=Decimal(nutrition_target.protein_g),
            fat_g=Decimal(nutrition_target.fat_g),
            carbs_g=Decimal(nutrition_target.carbs_g),
        )
        remaining = FoodDiaryTargets(
            energy_kcal=targets.energy_kcal - totals.energy_kcal,
            protein_g=(
                cast(Decimal, targets.protein_g) - totals.protein_g
                if totals.protein_g is not None
                else None
            ),
            fat_g=(
                cast(Decimal, targets.fat_g) - totals.fat_g if totals.fat_g is not None else None
            ),
            carbs_g=(
                cast(Decimal, targets.carbs_g) - totals.carbs_g
                if totals.carbs_g is not None
                else None
            ),
        )

    return FoodDiaryDayResponse(
        diary_date=selected_date,
        timezone=get_user_timezone_name(user),
        meals=meals,
        totals=totals,
        targets=targets,
        remaining=remaining,
        status=cast(Literal["complete", "incomplete", "unlogged", "fasted"], day_status),
        status_is_explicit=stored_status is not None,
    )


def set_food_diary_day_status(
    db: Session,
    user: User,
    payload: FoodDiaryDayStatusUpdate,
) -> FoodDiaryDayResponse:
    _validate_diary_date(user, payload.diary_date)
    stored = _stored_day_status(db, user, payload.diary_date)
    has_entries = (
        db.query(FoodDiaryEntry.id)
        .filter(
            FoodDiaryEntry.user_id == user.id,
            FoodDiaryEntry.diary_date == payload.diary_date,
        )
        .first()
        is not None
    )
    if payload.status == "fasted" and has_entries:
        raise FoodDiaryConflictError("a day with food entries cannot be marked as fasted")
    if payload.status == "complete" and not has_entries:
        raise FoodDiaryError("an empty day must be marked as fasted instead of complete")
    if payload.status == "unlogged":
        if stored is not None:
            db.delete(stored)
    elif stored is None:
        db.add(
            FoodDiaryDayStatus(
                user_id=user.id,
                diary_date=payload.diary_date,
                status=payload.status,
            )
        )
    else:
        stored.status = payload.status
    db.commit()
    return get_food_diary_day(db, user, payload.diary_date)


def _request_fingerprint(scope: str, payload: BaseModel) -> str:
    canonical = json.dumps(
        {"copy_scope": scope, **payload.model_dump(mode="json")},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _normalize_idempotency_key(value: str) -> str:
    normalized = value.strip()
    if len(normalized) < 8 or len(normalized) > 128:
        raise FoodDiaryError("Idempotency-Key must contain 8 to 128 characters")
    return normalized


def _copy_response(
    db: Session,
    operation: FoodDiaryCopyOperation,
    *,
    replayed: bool,
) -> FoodDiaryCopyResponse:
    entries = (
        db.query(FoodDiaryEntry)
        .filter(FoodDiaryEntry.copy_operation_id == operation.id)
        .order_by(FoodDiaryEntry.id.asc())
        .all()
    )
    return FoodDiaryCopyResponse(
        copy_scope=cast(CopyScope, operation.copy_scope),
        source_date=operation.source_date,
        source_meal_type=cast(MealType | None, operation.source_meal_type),
        target_date=operation.target_date,
        target_meal_type=cast(MealType | None, operation.target_meal_type),
        entries=[_serialize_entry(entry) for entry in entries],
        replayed=replayed,
    )


def _existing_copy_operation(
    db: Session,
    user: User,
    idempotency_key: str,
    fingerprint: str,
) -> FoodDiaryCopyResponse | None:
    operation = (
        db.query(FoodDiaryCopyOperation)
        .filter(
            FoodDiaryCopyOperation.user_id == user.id,
            FoodDiaryCopyOperation.idempotency_key == idempotency_key,
        )
        .first()
    )
    if operation is None:
        return None
    if operation.request_fingerprint != fingerprint:
        raise FoodDiaryConflictError("Idempotency-Key was already used for another request")
    return _copy_response(db, operation, replayed=True)


def _clone_entry(
    source: FoodDiaryEntry,
    *,
    target_date: date,
    target_meal_type: MealType,
    operation_id: int,
) -> FoodDiaryEntry:
    return FoodDiaryEntry(
        user_id=source.user_id,
        food_id=source.food_id,
        recipe_id=source.recipe_id,
        copy_operation_id=operation_id,
        copied_from_entry_id=source.id,
        diary_date=target_date,
        meal_type=target_meal_type,
        logged_at=source.logged_at,
        entry_kind=source.entry_kind,
        amount=source.amount,
        amount_unit=source.amount_unit,
        weight_g=source.weight_g,
        food_name=source.food_name,
        food_brand=source.food_brand,
        energy_kcal_per_100g=source.energy_kcal_per_100g,
        protein_g_per_100g=source.protein_g_per_100g,
        fat_g_per_100g=source.fat_g_per_100g,
        carbs_g_per_100g=source.carbs_g_per_100g,
        fiber_g_per_100g=source.fiber_g_per_100g,
        quick_energy_kcal=source.quick_energy_kcal,
        quick_protein_g=source.quick_protein_g,
        quick_fat_g=source.quick_fat_g,
        quick_carbs_g=source.quick_carbs_g,
        serving_amount=source.serving_amount,
        serving_unit=source.serving_unit,
        serving_weight_g=source.serving_weight_g,
        nutrition_basis_kind=source.nutrition_basis_kind,
        nutrition_basis_amount=source.nutrition_basis_amount,
        nutrition_basis_unit=source.nutrition_basis_unit,
        nutrition_snapshot=source.nutrition_snapshot,
        nutrition_amount=source.nutrition_amount,
    )


def _perform_copy(
    db: Session,
    user: User,
    *,
    scope: CopyScope,
    payload: BaseModel,
    idempotency_key: str,
    source_entry_id: int | None,
    source_date: date,
    source_meal_type: MealType | None,
    target_date: date,
    target_meal_type: MealType | None,
) -> FoodDiaryCopyResponse:
    key = _normalize_idempotency_key(idempotency_key)
    fingerprint = _request_fingerprint(scope, payload)
    replay = _existing_copy_operation(db, user, key, fingerprint)
    if replay is not None:
        return replay

    _validate_diary_date(user, source_date)
    _validate_diary_date(user, target_date)
    _ensure_day_accepts_entries(db, user, target_date)
    if scope == "meal" and (source_date, source_meal_type) == (
        target_date,
        target_meal_type,
    ):
        raise FoodDiaryError("source and target meal must differ")
    if scope == "day" and source_date == target_date:
        raise FoodDiaryError("source and target day must differ")

    source_query = db.query(FoodDiaryEntry).filter(
        FoodDiaryEntry.user_id == user.id,
        FoodDiaryEntry.diary_date == source_date,
    )
    if scope == "product":
        source_query = source_query.filter(
            FoodDiaryEntry.id == source_entry_id,
            FoodDiaryEntry.meal_type == source_meal_type,
        )
    elif scope == "meal":
        source_query = source_query.filter(FoodDiaryEntry.meal_type == source_meal_type)
    source_entries = source_query.order_by(FoodDiaryEntry.id.asc()).all()
    if not source_entries:
        if scope == "product":
            raise FoodDiaryNotFoundError("source diary entry not found")
        raise FoodDiaryError(f"source {scope} is empty")

    operation = FoodDiaryCopyOperation(
        user_id=user.id,
        idempotency_key=key,
        request_fingerprint=fingerprint,
        copy_scope=scope,
        source_entry_id=source_entry_id,
        source_date=source_date,
        source_meal_type=source_meal_type,
        target_date=target_date,
        target_meal_type=target_meal_type,
    )
    db.add(operation)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        replay = _existing_copy_operation(db, user, key, fingerprint)
        if replay is None:
            raise FoodDiaryConflictError("copy request could not be completed")
        return replay

    for source in source_entries:
        destination_meal = (
            cast(MealType, source.meal_type) if scope == "day" else cast(MealType, target_meal_type)
        )
        db.add(
            _clone_entry(
                source,
                target_date=target_date,
                target_meal_type=destination_meal,
                operation_id=operation.id,
            )
        )
    db.commit()
    return _copy_response(db, operation, replayed=False)


def copy_diary_product(
    db: Session,
    user: User,
    payload: FoodDiaryCopyProduct,
    idempotency_key: str,
) -> FoodDiaryCopyResponse:
    return _perform_copy(
        db,
        user,
        scope="product",
        payload=payload,
        idempotency_key=idempotency_key,
        source_entry_id=payload.source_entry_id,
        source_date=payload.source_date,
        source_meal_type=payload.source_meal_type,
        target_date=payload.target_date,
        target_meal_type=payload.target_meal_type,
    )


def copy_diary_meal(
    db: Session,
    user: User,
    payload: FoodDiaryCopyMeal,
    idempotency_key: str,
) -> FoodDiaryCopyResponse:
    return _perform_copy(
        db,
        user,
        scope="meal",
        payload=payload,
        idempotency_key=idempotency_key,
        source_entry_id=None,
        source_date=payload.source_date,
        source_meal_type=payload.source_meal_type,
        target_date=payload.target_date,
        target_meal_type=payload.target_meal_type,
    )


def copy_diary_day(
    db: Session,
    user: User,
    payload: FoodDiaryCopyDay,
    idempotency_key: str,
) -> FoodDiaryCopyResponse:
    return _perform_copy(
        db,
        user,
        scope="day",
        payload=payload,
        idempotency_key=idempotency_key,
        source_entry_id=None,
        source_date=payload.source_date,
        source_meal_type=None,
        target_date=payload.target_date,
        target_meal_type=None,
    )
