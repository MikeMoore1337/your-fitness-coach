from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from fitminiapp_api.schemas.food import FoodResponse
from fitminiapp_api.schemas.food_diary import (
    DiaryAmountUnit,
    FoodDiaryEntryResponse,
    FoodDiaryNutrition,
    MealType,
)

TemplateItemKind = Literal["food", "recipe"]
TemplateAmountUnit = Literal["g", "ml", "serving"]
NaturalInputStatus = Literal["matched", "ambiguous", "unresolved", "excluded"]
NaturalCandidateSource = Literal[
    "alias", "personal", "favorite", "frequent", "recent", "shared", "local"
]


class NutritionMealTemplateItemInput(BaseModel):
    food_id: int | None = Field(default=None, gt=0)
    recipe_id: int | None = Field(default=None, gt=0)
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=3, allow_inf_nan=False)
    amount_unit: TemplateAmountUnit = "g"

    @model_validator(mode="after")
    def require_single_source(self) -> NutritionMealTemplateItemInput:
        if (self.food_id is None) == (self.recipe_id is None):
            raise ValueError("exactly one of food_id or recipe_id must be provided")
        if self.recipe_id is not None and self.amount_unit != "g":
            raise ValueError("recipe template items must use grams")
        return self


class NutritionMealTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    items: list[NutritionMealTemplateItemInput] = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized


class NutritionMealTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    items: list[NutritionMealTemplateItemInput] | None = Field(
        default=None,
        min_length=1,
        max_length=100,
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
    def require_change(self) -> NutritionMealTemplateUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name must not be null")
        if "items" in self.model_fields_set and self.items is None:
            raise ValueError("items must not be null")
        return self


class NutritionMealTemplateItemResponse(BaseModel):
    id: int
    position: int
    item_kind: TemplateItemKind
    food_id: int | None
    recipe_id: int | None
    name: str
    brand: str | None
    amount: Decimal
    amount_unit: TemplateAmountUnit
    weight_g: Decimal | None
    nutrition: FoodDiaryNutrition | None
    available: bool
    message: str | None = None


class NutritionMealTemplateResponse(BaseModel):
    id: int
    name: str
    items: list[NutritionMealTemplateItemResponse]
    total_weight_g: Decimal | None
    totals: FoodDiaryNutrition
    created_at: datetime
    updated_at: datetime


class NutritionMealTemplateListResponse(BaseModel):
    items: list[NutritionMealTemplateResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class NutritionMealTemplateInsertRequest(BaseModel):
    diary_date: date
    meal_type: MealType


class FoodDiaryBatchItem(BaseModel):
    food_id: int | None = Field(default=None, gt=0)
    recipe_id: int | None = Field(default=None, gt=0)
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=3, allow_inf_nan=False)
    amount_unit: DiaryAmountUnit = "g"

    @model_validator(mode="after")
    def require_single_source(self) -> FoodDiaryBatchItem:
        if (self.food_id is None) == (self.recipe_id is None):
            raise ValueError("exactly one of food_id or recipe_id must be provided")
        if self.recipe_id is not None and self.amount_unit != "g":
            raise ValueError("recipe diary entries must use grams")
        return self


class FoodDiaryBatchResponse(BaseModel):
    operation_kind: Literal["meal_template", "natural_input"]
    diary_date: date
    meal_type: MealType
    entries: list[FoodDiaryEntryResponse]
    replayed: bool


class NaturalInputPreviewRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text must not be blank")
        return normalized


class NaturalFoodCandidate(BaseModel):
    food: FoodResponse
    source: NaturalCandidateSource


class NaturalInputRowResponse(BaseModel):
    row_id: str
    raw_text: str
    name: str
    amount: Decimal | None
    amount_unit: TemplateAmountUnit | None
    unit_inferred: bool
    status: NaturalInputStatus
    selected_food_id: int | None
    selected_food: FoodResponse | None
    nutrition: FoodDiaryNutrition | None = None
    candidates: list[NaturalFoodCandidate] = Field(default_factory=list)
    message: str | None = None


class NaturalInputPreviewResponse(BaseModel):
    rows: list[NaturalInputRowResponse]


class NaturalInputCommitItem(BaseModel):
    row_id: str = Field(min_length=1, max_length=32)
    food_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=3, allow_inf_nan=False)
    amount_unit: DiaryAmountUnit = "g"


class NaturalInputCommitRequest(BaseModel):
    diary_date: date
    meal_type: MealType
    items: list[NaturalInputCommitItem] = Field(min_length=1, max_length=100)


class FoodSearchAliasCreate(BaseModel):
    alias: str = Field(min_length=1, max_length=128)
    food_id: int = Field(gt=0)

    @field_validator("alias")
    @classmethod
    def normalize_alias(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("alias must not be blank")
        return normalized


class FoodSearchAliasUpdate(BaseModel):
    alias: str | None = Field(default=None, min_length=1, max_length=128)
    food_id: int | None = Field(default=None, gt=0)

    @field_validator("alias")
    @classmethod
    def normalize_alias(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("alias must not be blank")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> FoodSearchAliasUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        if "alias" in self.model_fields_set and self.alias is None:
            raise ValueError("alias must not be null")
        if "food_id" in self.model_fields_set and self.food_id is None:
            raise ValueError("food_id must not be null")
        return self


class FoodSearchAliasResponse(BaseModel):
    id: int
    alias: str
    food_id: int | None
    food_name: str | None
    food_brand: str | None
    available: bool
    created_at: datetime
    updated_at: datetime


class FoodSearchAliasListResponse(BaseModel):
    items: list[FoodSearchAliasResponse]
