from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from fitminiapp_api.schemas.food_diary import MealType

GroceryAmountUnit = Literal["g", "ml", "piece", "serving"]
GrocerySourceKind = Literal["generated", "manual"]


class GroceryListGenerateRequest(BaseModel):
    week_start: date


class GroceryListManualItemCreate(BaseModel):
    week_start: date
    name: str = Field(min_length=1, max_length=256)
    amount: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=3,
        allow_inf_nan=False,
    )
    amount_unit: GroceryAmountUnit | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized

    @model_validator(mode="after")
    def require_complete_amount(self) -> GroceryListManualItemCreate:
        if (self.amount is None) != (self.amount_unit is None):
            raise ValueError("amount and amount_unit must be provided together")
        return self


class GroceryListItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    amount: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=3,
        allow_inf_nan=False,
    )
    amount_unit: GroceryAmountUnit | None = None
    checked: bool | None = None
    owned: bool | None = None

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
    def require_change(self) -> GroceryListItemUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name must not be null")
        if "checked" in self.model_fields_set and self.checked is None:
            raise ValueError("checked must not be null")
        if "owned" in self.model_fields_set and self.owned is None:
            raise ValueError("owned must not be null")
        return self


class GroceryListItemSourceResponse(BaseModel):
    plan_item_id: int | None
    recipe_id: int | None
    plan_date: date
    meal_type: MealType
    recipe_name: str


class GroceryListItemResponse(BaseModel):
    id: int
    source_kind: GrocerySourceKind
    food_id: int | None
    name: str
    brand: str | None
    amount: Decimal | None
    amount_unit: GroceryAmountUnit | None
    checked: bool
    owned: bool
    sources: list[GroceryListItemSourceResponse]


class GroceryListStaleSourceResponse(BaseModel):
    plan_item_id: int
    recipe_id: int | None
    plan_date: date
    meal_type: MealType
    source_name: str
    reason: str


class GroceryListResponse(BaseModel):
    id: int | None
    week_start: date
    week_end: date
    generated: bool
    refresh_required: bool
    updated_at: datetime | None
    items: list[GroceryListItemResponse]
    stale_sources: list[GroceryListStaleSourceResponse]
