from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from fitminiapp_api.schemas.food_diary import FoodDiaryNutrition

RecipeAmountUnit = Literal["g", "serving"]


class RecipeIngredientInput(BaseModel):
    food_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=3, allow_inf_nan=False)
    amount_unit: RecipeAmountUnit = "g"


class RecipeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    ingredients: list[RecipeIngredientInput] = Field(min_length=1, max_length=100)
    final_weight_g: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=10,
        decimal_places=3,
        allow_inf_nan=False,
    )

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized


class RecipeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    ingredients: list[RecipeIngredientInput] | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    final_weight_g: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=10,
        decimal_places=3,
        allow_inf_nan=False,
    )

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> RecipeUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name must not be null")
        if "ingredients" in self.model_fields_set and self.ingredients is None:
            raise ValueError("ingredients must not be null")
        return self


class RecipeNutrientsPer100g(BaseModel):
    energy_kcal_per_100g: Decimal
    protein_g_per_100g: Decimal
    fat_g_per_100g: Decimal
    carbs_g_per_100g: Decimal
    fiber_g_per_100g: Decimal | None


class RecipeIngredientResponse(BaseModel):
    id: int
    position: int
    food_id: int | None
    food_name: str
    food_brand: str | None
    amount: Decimal
    amount_unit: RecipeAmountUnit
    weight_g: Decimal
    serving_amount: Decimal | None
    serving_unit: str | None
    serving_weight_g: Decimal | None
    nutrition: FoodDiaryNutrition


class RecipeResponse(BaseModel):
    id: int
    name: str
    ingredients: list[RecipeIngredientResponse]
    ingredients_weight_g: Decimal
    final_weight_g: Decimal | None
    effective_weight_g: Decimal
    totals: FoodDiaryNutrition
    nutrients_per_100g: RecipeNutrientsPer100g
    created_at: datetime
    updated_at: datetime


class RecipeListResponse(BaseModel):
    items: list[RecipeResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
