from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator, model_validator

from fitminiapp_api.nutrition_label.contracts import StrictModel
from fitminiapp_api.schemas.food_diary import FoodDiaryEntryResponse, MealType

PhotoMealDraftStatus = Literal["draft", "confirmed", "cancelled", "expired"]
PhotoMealConfidence = Literal["high", "medium", "low", "unknown"]
PhotoMealPortionUnit = Literal["g", "ml", "serving"]
PhotoMealUncertainty = Literal["identity_uncertain", "portion_uncertain", "nutrition_uncertain"]
PhotoMealWarning = Literal[
    "identity_uncertain",
    "portion_uncertain",
    "nutrition_uncertain",
    "unsupported_image",
    "manual_review_required",
]


class PhotoMealCandidate(StrictModel):
    candidate_id: str = Field(min_length=1, max_length=32, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=128)
    portion_amount: Decimal | None = Field(
        default=None,
        gt=0,
        le=5000,
        max_digits=10,
        decimal_places=3,
        allow_inf_nan=False,
    )
    portion_unit: PhotoMealPortionUnit | None = None
    portion_confidence: PhotoMealConfidence
    identity_confidence: PhotoMealConfidence
    nutrition_confidence: PhotoMealConfidence
    uncertainty_codes: list[PhotoMealUncertainty] = Field(default_factory=list, max_length=3)
    energy_kcal: Decimal | None = Field(
        default=None,
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
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("candidate name must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_portion(self) -> PhotoMealCandidate:
        if (self.portion_amount is None) != (self.portion_unit is None):
            raise ValueError("portion amount and unit must be provided together")
        if len(set(self.uncertainty_codes)) != len(self.uncertainty_codes):
            raise ValueError("uncertainty codes must be unique")
        return self


class PhotoMealDraftResponse(StrictModel):
    draft_id: str
    revision: int = Field(gt=0)
    status: PhotoMealDraftStatus
    expires_at: datetime
    candidates: list[PhotoMealCandidate] = Field(min_length=1, max_length=8)
    warnings: list[PhotoMealWarning] = Field(default_factory=list, max_length=8)
    requires_user_review: Literal[True] = True
    source_photo_retained: Literal[False] = False


class PhotoMealConfirmItem(StrictModel):
    candidate_id: str = Field(min_length=1, max_length=32, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=128)
    portion_amount: Decimal | None = Field(
        default=None,
        gt=0,
        le=5000,
        max_digits=10,
        decimal_places=3,
        allow_inf_nan=False,
    )
    portion_unit: PhotoMealPortionUnit | None = None
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
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("candidate name must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_portion(self) -> PhotoMealConfirmItem:
        if (self.portion_amount is None) != (self.portion_unit is None):
            raise ValueError("portion amount and unit must be provided together")
        return self


class PhotoMealConfirmRequest(StrictModel):
    revision: int = Field(gt=0)
    diary_date: date
    meal_type: MealType
    items: list[PhotoMealConfirmItem] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def require_unique_candidates(self) -> PhotoMealConfirmRequest:
        ids = [item.candidate_id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("candidate_id values must be unique")
        return self


class PhotoMealConfirmResponse(StrictModel):
    draft_id: str
    entry: FoodDiaryEntryResponse
    replayed: Literal[False] = False
