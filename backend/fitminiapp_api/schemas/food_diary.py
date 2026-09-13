from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MealType = Literal["breakfast", "lunch", "dinner", "snacks"]
DiaryAmountUnit = Literal["g", "ml", "serving"]
DiaryDayStatus = Literal["complete", "incomplete", "unlogged", "fasted"]


class FoodDiaryQuickAdd(BaseModel):
    name: str | None = Field(default=None, max_length=256)
    energy_kcal: Decimal = Field(
        gt=0,
        le=10000,
        max_digits=10,
        decimal_places=2,
        allow_inf_nan=False,
    )
    protein_g: Decimal | None = Field(
        default=None,
        ge=0,
        le=1000,
        max_digits=8,
        decimal_places=3,
        allow_inf_nan=False,
    )
    fat_g: Decimal | None = Field(
        default=None,
        ge=0,
        le=1000,
        max_digits=8,
        decimal_places=3,
        allow_inf_nan=False,
    )
    carbs_g: Decimal | None = Field(
        default=None,
        ge=0,
        le=1000,
        max_digits=8,
        decimal_places=3,
        allow_inf_nan=False,
    )

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        normalized = " ".join(value.split()) if value is not None else ""
        return normalized or None

    @model_validator(mode="after")
    def require_all_or_no_macros(self) -> FoodDiaryQuickAdd:
        macros = (self.protein_g, self.fat_g, self.carbs_g)
        if any(value is not None for value in macros) and not all(
            value is not None for value in macros
        ):
            raise ValueError("protein, fat and carbs must be provided together")
        return self


class FoodDiaryEntryCreate(BaseModel):
    food_id: int | None = Field(default=None, gt=0)
    recipe_id: int | None = Field(default=None, gt=0)
    quick_add: FoodDiaryQuickAdd | None = None
    diary_date: date
    meal_type: MealType
    logged_at: time | None = None
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=3, allow_inf_nan=False)
    amount_unit: DiaryAmountUnit = "g"

    @model_validator(mode="after")
    def require_single_source(self) -> FoodDiaryEntryCreate:
        sources = (self.food_id, self.recipe_id, self.quick_add)
        if sum(source is not None for source in sources) != 1:
            raise ValueError("exactly one of food_id, recipe_id or quick_add must be provided")
        if self.recipe_id is not None and self.amount_unit != "g":
            raise ValueError("recipe diary entries must use grams")
        if self.quick_add is not None and (self.amount != 1 or self.amount_unit != "serving"):
            raise ValueError("quick add entries use one virtual serving")
        return self


class FoodDiaryEntryUpdate(BaseModel):
    food_id: int | None = Field(default=None, gt=0)
    recipe_id: int | None = Field(default=None, gt=0)
    diary_date: date | None = None
    meal_type: MealType | None = None
    logged_at: time | None = None
    amount: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=10,
        decimal_places=3,
        allow_inf_nan=False,
    )
    amount_unit: DiaryAmountUnit | None = None

    @model_validator(mode="after")
    def require_change(self) -> FoodDiaryEntryUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("updated fields must not be null")
        if "food_id" in self.model_fields_set and "recipe_id" in self.model_fields_set:
            raise ValueError("food_id and recipe_id cannot be updated together")
        if self.recipe_id is not None and self.amount_unit == "serving":
            raise ValueError("recipe diary entries must use grams")
        return self


class FoodDiaryNutrition(BaseModel):
    energy_kcal: Decimal
    protein_g: Decimal | None
    fat_g: Decimal | None
    carbs_g: Decimal | None
    fiber_g: Decimal | None


class FoodDiaryEntryResponse(BaseModel):
    id: int
    diary_date: date
    meal_type: MealType
    food_id: int | None
    recipe_id: int | None
    entry_kind: Literal["food", "recipe", "quick_add"]
    logged_at: time | None
    food_name: str
    food_brand: str | None
    amount: Decimal
    amount_unit: DiaryAmountUnit
    weight_g: Decimal | None
    nutrition_basis_kind: Literal["per_100_g", "per_100_ml", "per_serving"] | None = None
    nutrition_basis_amount: Decimal | None = None
    nutrition_basis_unit: Literal["g", "ml", "serving"] | None = None
    serving_amount: Decimal | None
    serving_unit: str | None
    serving_weight_g: Decimal | None
    nutrition: FoodDiaryNutrition
    created_at: datetime
    updated_at: datetime


class FoodDiaryMeal(BaseModel):
    meal_type: MealType
    entries: list[FoodDiaryEntryResponse]
    totals: FoodDiaryNutrition


class FoodDiaryTargets(BaseModel):
    energy_kcal: Decimal
    protein_g: Decimal | None
    fat_g: Decimal | None
    carbs_g: Decimal | None


class FoodDiaryDayResponse(BaseModel):
    diary_date: date
    timezone: str
    meals: list[FoodDiaryMeal]
    totals: FoodDiaryNutrition
    targets: FoodDiaryTargets | None
    remaining: FoodDiaryTargets | None
    status: DiaryDayStatus
    status_is_explicit: bool


class FoodDiaryDayStatusUpdate(BaseModel):
    diary_date: date
    status: DiaryDayStatus


class FoodDiaryCopyProduct(BaseModel):
    source_entry_id: int = Field(gt=0)
    source_date: date
    source_meal_type: MealType
    target_date: date
    target_meal_type: MealType


class FoodDiaryCopyMeal(BaseModel):
    source_date: date
    source_meal_type: MealType
    target_date: date
    target_meal_type: MealType


class FoodDiaryCopyDay(BaseModel):
    source_date: date
    target_date: date


class FoodDiaryCopyResponse(BaseModel):
    copy_scope: Literal["product", "meal", "day"]
    source_date: date
    source_meal_type: MealType | None
    target_date: date
    target_meal_type: MealType | None
    entries: list[FoodDiaryEntryResponse]
    replayed: bool
