from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import cast

from sqlalchemy.orm import Session, selectinload

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.recipe import Recipe, RecipeIngredient
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.food import FoodNutrientsInput
from fitminiapp_api.schemas.food_diary import FoodDiaryNutrition
from fitminiapp_api.schemas.recipe import (
    RecipeAmountUnit,
    RecipeCreate,
    RecipeIngredientInput,
    RecipeIngredientResponse,
    RecipeListResponse,
    RecipeNutrientsPer100g,
    RecipeResponse,
    RecipeUpdate,
)
from fitminiapp_api.services.foods import (
    ENERGY_QUANTUM,
    MACRO_QUANTUM,
    WEIGHT_QUANTUM,
    FoodError,
    calculate_food_nutrition,
    calculate_food_servings,
    get_visible_food,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")


class RecipeError(ValueError):
    pass


class RecipeNotFoundError(RecipeError):
    pass


@dataclass(frozen=True)
class RecipeCalculation:
    ingredients_weight_g: Decimal
    effective_weight_g: Decimal
    totals: FoodDiaryNutrition
    nutrients_per_100g: RecipeNutrientsPer100g


def _calculate_food_amount(
    food: Food,
    amount: Decimal,
    amount_unit: RecipeAmountUnit,
):
    try:
        if amount_unit == "serving":
            return calculate_food_servings(food, amount)
        return calculate_food_nutrition(
            FoodNutrientsInput(
                energy_kcal_per_100g=food.energy_kcal_per_100g,
                protein_g_per_100g=food.protein_g_per_100g,
                fat_g_per_100g=food.fat_g_per_100g,
                carbs_g_per_100g=food.carbs_g_per_100g,
                fiber_g_per_100g=food.fiber_g_per_100g,
            ),
            amount,
        )
    except FoodError as exc:
        raise RecipeError(str(exc)) from exc


def _ingredient_nutrition(ingredient: RecipeIngredient) -> FoodDiaryNutrition:
    calculated = calculate_food_nutrition(
        FoodNutrientsInput(
            energy_kcal_per_100g=ingredient.energy_kcal_per_100g,
            protein_g_per_100g=ingredient.protein_g_per_100g,
            fat_g_per_100g=ingredient.fat_g_per_100g,
            carbs_g_per_100g=ingredient.carbs_g_per_100g,
            fiber_g_per_100g=ingredient.fiber_g_per_100g,
        ),
        ingredient.weight_g,
    )
    return FoodDiaryNutrition(
        energy_kcal=cast(Decimal, calculated.energy_kcal),
        protein_g=cast(Decimal, calculated.protein_g),
        fat_g=cast(Decimal, calculated.fat_g),
        carbs_g=cast(Decimal, calculated.carbs_g),
        fiber_g=calculated.fiber_g,
    )


def _sum_nutrition(values: list[FoodDiaryNutrition]) -> FoodDiaryNutrition:
    fiber_values = [value.fiber_g for value in values]
    fiber = None
    if all(value is not None for value in fiber_values):
        fiber = sum((value for value in fiber_values if value is not None), start=ZERO)
    return FoodDiaryNutrition(
        energy_kcal=sum((value.energy_kcal for value in values), start=ZERO),
        protein_g=sum((cast(Decimal, value.protein_g) for value in values), start=ZERO),
        fat_g=sum((cast(Decimal, value.fat_g) for value in values), start=ZERO),
        carbs_g=sum((cast(Decimal, value.carbs_g) for value in values), start=ZERO),
        fiber_g=fiber,
    )


def _per_100(value: Decimal, weight_g: Decimal, quantum: Decimal) -> Decimal:
    return (value * HUNDRED / weight_g).quantize(quantum, rounding=ROUND_HALF_UP)


def calculate_recipe(recipe: Recipe) -> RecipeCalculation:
    ingredient_values = [_ingredient_nutrition(ingredient) for ingredient in recipe.ingredients]
    if not ingredient_values:
        raise RecipeError("recipe must contain at least one ingredient")
    ingredients_weight = sum(
        (ingredient.weight_g for ingredient in recipe.ingredients), start=ZERO
    ).quantize(WEIGHT_QUANTUM, rounding=ROUND_HALF_UP)
    effective_weight = recipe.final_weight_g or ingredients_weight
    effective_weight = effective_weight.quantize(WEIGHT_QUANTUM, rounding=ROUND_HALF_UP)
    totals = _sum_nutrition(ingredient_values)
    nutrients = RecipeNutrientsPer100g(
        energy_kcal_per_100g=_per_100(totals.energy_kcal, effective_weight, ENERGY_QUANTUM),
        protein_g_per_100g=_per_100(
            cast(Decimal, totals.protein_g), effective_weight, MACRO_QUANTUM
        ),
        fat_g_per_100g=_per_100(cast(Decimal, totals.fat_g), effective_weight, MACRO_QUANTUM),
        carbs_g_per_100g=_per_100(cast(Decimal, totals.carbs_g), effective_weight, MACRO_QUANTUM),
        fiber_g_per_100g=(
            None
            if totals.fiber_g is None
            else _per_100(totals.fiber_g, effective_weight, MACRO_QUANTUM)
        ),
    )
    if (
        nutrients.energy_kcal_per_100g > Decimal("1000")
        or nutrients.protein_g_per_100g > HUNDRED
        or nutrients.fat_g_per_100g > HUNDRED
        or nutrients.carbs_g_per_100g > HUNDRED
        or (nutrients.fiber_g_per_100g is not None and nutrients.fiber_g_per_100g > HUNDRED)
    ):
        raise RecipeError("final_weight_g is too low for the recipe nutrient totals")
    return RecipeCalculation(
        ingredients_weight_g=ingredients_weight,
        effective_weight_g=effective_weight,
        totals=totals,
        nutrients_per_100g=nutrients,
    )


def get_owned_recipe(db: Session, owner: User, recipe_id: int) -> Recipe:
    recipe = (
        db.query(Recipe)
        .options(selectinload(Recipe.ingredients))
        .filter(Recipe.id == recipe_id, Recipe.owner_user_id == owner.id)
        .first()
    )
    if recipe is None:
        raise RecipeNotFoundError("recipe not found")
    return recipe


def _serialize_ingredient(ingredient: RecipeIngredient) -> RecipeIngredientResponse:
    return RecipeIngredientResponse(
        id=ingredient.id,
        position=ingredient.position,
        food_id=ingredient.food_id,
        food_name=ingredient.food_name,
        food_brand=ingredient.food_brand,
        amount=ingredient.amount,
        amount_unit=cast(RecipeAmountUnit, ingredient.amount_unit),
        weight_g=ingredient.weight_g,
        serving_amount=ingredient.serving_amount,
        serving_unit=ingredient.serving_unit,
        serving_weight_g=ingredient.serving_weight_g,
        nutrition=_ingredient_nutrition(ingredient),
    )


def serialize_recipe(recipe: Recipe) -> RecipeResponse:
    calculation = calculate_recipe(recipe)
    return RecipeResponse(
        id=recipe.id,
        name=recipe.name,
        ingredients=[_serialize_ingredient(ingredient) for ingredient in recipe.ingredients],
        ingredients_weight_g=calculation.ingredients_weight_g,
        final_weight_g=recipe.final_weight_g,
        effective_weight_g=calculation.effective_weight_g,
        totals=calculation.totals,
        nutrients_per_100g=calculation.nutrients_per_100g,
        created_at=recipe.created_at,
        updated_at=recipe.updated_at,
    )


def _build_ingredient(
    db: Session,
    owner: User,
    recipe: Recipe,
    position: int,
    payload: RecipeIngredientInput,
) -> RecipeIngredient:
    try:
        food = get_visible_food(db, owner, payload.food_id)
    except FoodError as exc:
        raise RecipeNotFoundError("food not found") from exc
    calculation = _calculate_food_amount(food, payload.amount, payload.amount_unit)
    return RecipeIngredient(
        recipe=recipe,
        food_id=food.id,
        position=position,
        amount=payload.amount,
        amount_unit=payload.amount_unit,
        weight_g=calculation.weight_g,
        food_name=food.name,
        food_brand=food.brand,
        energy_kcal_per_100g=cast(Decimal, food.energy_kcal_per_100g),
        protein_g_per_100g=cast(Decimal, food.protein_g_per_100g),
        fat_g_per_100g=cast(Decimal, food.fat_g_per_100g),
        carbs_g_per_100g=cast(Decimal, food.carbs_g_per_100g),
        fiber_g_per_100g=food.fiber_g_per_100g,
        serving_amount=food.standard_serving_amount,
        serving_unit=food.standard_serving_unit,
        serving_weight_g=food.standard_serving_weight_g,
    )


def _replace_ingredients(
    db: Session,
    owner: User,
    recipe: Recipe,
    payloads: list[RecipeIngredientInput],
) -> None:
    recipe.ingredients.clear()
    db.flush()
    recipe.ingredients.extend(
        _build_ingredient(db, owner, recipe, position, payload)
        for position, payload in enumerate(payloads)
    )


def create_recipe(db: Session, owner: User, payload: RecipeCreate) -> RecipeResponse:
    recipe = Recipe(
        owner_user_id=owner.id,
        name=payload.name,
        final_weight_g=payload.final_weight_g,
    )
    db.add(recipe)
    _replace_ingredients(db, owner, recipe, payload.ingredients)
    calculate_recipe(recipe)
    db.commit()
    return serialize_recipe(get_owned_recipe(db, owner, recipe.id))


def list_recipes(
    db: Session,
    owner: User,
    *,
    limit: int,
    offset: int,
) -> RecipeListResponse:
    query = db.query(Recipe).filter(Recipe.owner_user_id == owner.id)
    total = query.count()
    recipes = (
        query.options(selectinload(Recipe.ingredients))
        .order_by(Recipe.updated_at.desc(), Recipe.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return RecipeListResponse(
        items=[serialize_recipe(recipe) for recipe in recipes],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_recipe_response(db: Session, owner: User, recipe_id: int) -> RecipeResponse:
    return serialize_recipe(get_owned_recipe(db, owner, recipe_id))


def update_recipe(
    db: Session,
    owner: User,
    recipe_id: int,
    payload: RecipeUpdate,
) -> RecipeResponse:
    recipe = get_owned_recipe(db, owner, recipe_id)
    if "name" in payload.model_fields_set:
        recipe.name = cast(str, payload.name)
    if "final_weight_g" in payload.model_fields_set:
        recipe.final_weight_g = payload.final_weight_g
    if "ingredients" in payload.model_fields_set:
        _replace_ingredients(
            db, owner, recipe, cast(list[RecipeIngredientInput], payload.ingredients)
        )
    recipe.updated_at = now_msk_naive()
    calculate_recipe(recipe)
    db.commit()
    return serialize_recipe(get_owned_recipe(db, owner, recipe.id))


def delete_recipe(db: Session, owner: User, recipe_id: int) -> None:
    recipe = get_owned_recipe(db, owner, recipe_id)
    db.delete(recipe)
    db.commit()
