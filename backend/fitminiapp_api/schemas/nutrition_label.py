from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator, model_validator

from fitminiapp_api.nutrition_label.contracts import (
    CanonicalDraft,
    PackageAmount,
    ServingSize,
    SourceBasis,
    StrictModel,
)
from fitminiapp_api.schemas.food import FoodResponse, validate_gtin

LabelVisibility = Literal["private", "share_to_yfc_catalog"]
LabelDraftStatus = Literal["draft", "confirmed", "cancelled", "expired"]


class NutritionLabelFactsEdit(StrictModel):
    source_basis: SourceBasis
    serving_size: ServingSize | None = None
    servings_per_container: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    package_amount: PackageAmount | None = None
    energy_kcal: Decimal | None = Field(default=None, ge=0, le=10000, allow_inf_nan=False)
    energy_kj: Decimal | None = Field(default=None, ge=0, le=50000, allow_inf_nan=False)
    protein_g: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    fat_g: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    saturated_fat_g: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    trans_fat_g: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    carbohydrate_g: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    sugars_g: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    added_sugars_g: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    fiber_g: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    salt_g: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    sodium_mg: Decimal | None = Field(default=None, ge=0, le=100000, allow_inf_nan=False)
    cholesterol_mg: Decimal | None = Field(default=None, ge=0, le=100000, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_basis(self) -> NutritionLabelFactsEdit:
        if self.source_basis == "ambiguous":
            raise ValueError("basis must be resolved before confirmation")
        if (
            self.source_basis == "per_serving"
            and self.serving_size is not None
            and self.serving_size.unit not in {"g", "ml"}
        ):
            raise ValueError("serving size must use grams or millilitres")
        return self


class NutritionLabelConfirmRequest(StrictModel):
    revision: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=256)
    brand: str | None = Field(default=None, max_length=128)
    barcode: str | None = None
    visibility: LabelVisibility
    nutrition: NutritionLabelFactsEdit

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized

    @field_validator("brand")
    @classmethod
    def normalize_brand(cls, value: str | None) -> str | None:
        normalized = " ".join((value or "").split())
        return normalized or None

    @field_validator("barcode")
    @classmethod
    def validate_barcode(cls, value: str | None) -> str | None:
        return validate_gtin(value)

    @model_validator(mode="after")
    def validate_visibility(self) -> NutritionLabelConfirmRequest:
        if self.visibility == "share_to_yfc_catalog" and self.barcode is None:
            raise ValueError("sharing requires a valid GTIN barcode")
        return self


class NutritionLabelDraftResponse(StrictModel):
    draft_id: str
    revision: int
    status: LabelDraftStatus
    expires_at: datetime
    product_name: str | None
    product_brand: str | None
    product_barcode: str | None
    nutrition: CanonicalDraft
    warnings: list[str]
    requires_user_review: Literal[True]


class NutritionLabelConfirmResponse(StrictModel):
    food: FoodResponse
    visibility: LabelVisibility
    contribution_state: Literal["private", "accepted", "duplicate", "conflict"]
    catalog_quality: Literal["private", "verified", "community_unverified"]
    provenance: str
    diary_entry_created: Literal[False] = False
