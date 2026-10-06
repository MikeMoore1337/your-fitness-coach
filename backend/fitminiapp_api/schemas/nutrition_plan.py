from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from fitminiapp_api.schemas.food_diary import (
    DiaryAmountUnit,
    FoodDiaryNutrition,
    FoodDiaryTargets,
    MealType,
)

PlanItemKind = Literal["food", "recipe"]
PlanItemAmountUnit = DiaryAmountUnit
PlanItemStatus = Literal["planned", "consumed", "skipped"]
PlanItemAction = Literal["consume", "edit_and_consume", "skip"]


class NutritionPlanItemCreate(BaseModel):
    food_id: int | None = Field(default=None, gt=0)
    recipe_id: int | None = Field(default=None, gt=0)
    template_id: int | None = Field(default=None, gt=0)
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=3, allow_inf_nan=False)
    amount_unit: PlanItemAmountUnit = "g"

    @model_validator(mode="after")
    def require_single_source(self) -> NutritionPlanItemCreate:
        sources = (self.food_id, self.recipe_id, self.template_id)
        if sum(source is not None for source in sources) != 1:
            raise ValueError("exactly one of food_id, recipe_id or template_id must be provided")
        if self.recipe_id is not None and self.amount_unit != "g":
            raise ValueError("recipe plan items must use grams")
        if self.template_id is not None and self.amount_unit != "serving":
            raise ValueError("template plan items use servings as a repeat count")
        return self


class NutritionPlanItemUpdate(BaseModel):
    meal_type: MealType | None = None
    amount: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=10,
        decimal_places=3,
        allow_inf_nan=False,
    )
    amount_unit: PlanItemAmountUnit | None = None
    expected_revision: int = Field(ge=0)

    @model_validator(mode="after")
    def require_change(self) -> NutritionPlanItemUpdate:
        if not any(
            field in self.model_fields_set for field in ("meal_type", "amount", "amount_unit")
        ):
            raise ValueError("at least one item field must be provided")
        return self


class NutritionPlanCopyRequest(BaseModel):
    source_date: date
    target_date: date
    expected_revision: int = Field(ge=0)

    @model_validator(mode="after")
    def require_different_dates(self) -> NutritionPlanCopyRequest:
        if self.source_date == self.target_date:
            raise ValueError("source and target dates must differ")
        return self


class NutritionPlanFillItem(BaseModel):
    position: int = Field(ge=0, lt=100)
    food_id: int | None = Field(default=None, gt=0)
    recipe_id: int | None = Field(default=None, gt=0)
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=3, allow_inf_nan=False)
    amount_unit: PlanItemAmountUnit = "g"

    @model_validator(mode="after")
    def require_single_source(self) -> NutritionPlanFillItem:
        if (self.food_id is None) == (self.recipe_id is None):
            raise ValueError("exactly one of food_id or recipe_id must be provided")
        if self.recipe_id is not None and self.amount_unit != "g":
            raise ValueError("recipe plan items must use grams")
        return self


class NutritionPlanFillRequest(BaseModel):
    plan_date: date
    meal_type: MealType
    candidate_id: str = Field(min_length=1, max_length=128)
    items: list[NutritionPlanFillItem] = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=0)

    @model_validator(mode="after")
    def require_unique_positions(self) -> NutritionPlanFillRequest:
        positions = [item.position for item in self.items]
        if len(positions) != len(set(positions)):
            raise ValueError("candidate item positions must be unique")
        return self


class NutritionPlanItemActionRequest(BaseModel):
    action: PlanItemAction
    amount: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=10,
        decimal_places=3,
        allow_inf_nan=False,
    )
    amount_unit: PlanItemAmountUnit | None = None
    meal_type: MealType | None = None
    expected_revision: int = Field(ge=0)

    @model_validator(mode="after")
    def require_explicit_edit(self) -> NutritionPlanItemActionRequest:
        edit_fields = ("amount", "amount_unit", "meal_type")
        supplied_edit = any(field in self.model_fields_set for field in edit_fields)
        if self.action == "edit_and_consume":
            if self.amount is None or self.amount_unit is None:
                raise ValueError("edit_and_consume requires amount and amount_unit")
        elif supplied_edit:
            raise ValueError("consume and skip do not accept planned item edits")
        return self


class NutritionPlanItemResponse(BaseModel):
    id: int
    meal_type: MealType
    position: int
    item_kind: PlanItemKind
    food_id: int | None
    recipe_id: int | None
    source_template_id: int | None
    name: str
    brand: str | None
    amount: Decimal
    amount_unit: PlanItemAmountUnit
    weight_g: Decimal | None
    nutrition: FoodDiaryNutrition | None
    available: bool
    status: PlanItemStatus
    diary_entry_id: int | None
    message: str | None = None


class NutritionPlanSlotResponse(BaseModel):
    meal_type: MealType
    items: list[NutritionPlanItemResponse]
    planned: FoodDiaryNutrition


class NutritionPlanDayResponse(BaseModel):
    plan_date: date
    timezone: str
    revision: int
    slots: list[NutritionPlanSlotResponse]
    planned: FoodDiaryNutrition
    targets: FoodDiaryTargets | None
    remaining: FoodDiaryTargets | None
    nutrition_complete: bool
    updated_at: datetime | None
    replayed: bool = False


class NutritionPlanItemActionResponse(BaseModel):
    action: PlanItemAction
    item: NutritionPlanItemResponse
    day: NutritionPlanDayResponse
    diary_entry_id: int | None
    replayed: bool
    diagnostic: str


class NutritionPlanWeekResponse(BaseModel):
    week_start: date
    week_end: date
    timezone: str
    days: list[NutritionPlanDayResponse]
    planned: FoodDiaryNutrition
    targets: FoodDiaryTargets | None
    remaining: FoodDiaryTargets | None
    nutrition_complete: bool
