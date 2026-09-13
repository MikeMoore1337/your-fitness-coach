from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

FoodType = Literal["system", "branded", "user"]
FoodProvenance = Literal["internal", "external", "user", "user_confirmed_package"]
FoodTrustLevel = Literal["verified", "unverified"]
FoodStatus = Literal["draft", "active", "disabled"]
ServingUnit = Literal["g", "ml", "piece", "serving"]
NutritionBasisKind = Literal["per_100_g", "per_100_ml", "per_serving"]
FoodCatalogQuality = Literal["private", "verified", "community_unverified"]
FoodProviderStatus = Literal[
    "not_requested",
    "not_needed",
    "disabled",
    "available",
    "unavailable",
    "rate_limited",
]
FoodBarcodeLookupStatus = Literal["found", "not_found"]
FoodBarcodeLookupSource = Literal["local", "external"]


def validate_gtin(value: str | None) -> str | None:
    if value is None:
        return None
    barcode = value.strip()
    if len(barcode) not in {8, 12, 13, 14} or not barcode.isascii() or not barcode.isdigit():
        raise ValueError("barcode must be a GTIN-8, UPC-A, EAN-13, or GTIN-14")
    digits = [int(digit) for digit in barcode]
    payload = digits[:-1]
    weighted_sum = sum(
        digit * (3 if (len(payload) - index) % 2 == 1 else 1) for index, digit in enumerate(payload)
    )
    check_digit = (10 - weighted_sum % 10) % 10
    if check_digit != digits[-1]:
        raise ValueError("barcode check digit is invalid")
    return barcode


class FoodNutrientsInput(BaseModel):
    energy_kcal_per_100g: Decimal | None = Field(default=None, ge=0, le=1000)
    protein_g_per_100g: Decimal | None = Field(default=None, ge=0, le=100)
    fat_g_per_100g: Decimal | None = Field(default=None, ge=0, le=100)
    carbs_g_per_100g: Decimal | None = Field(default=None, ge=0, le=100)
    fiber_g_per_100g: Decimal | None = Field(default=None, ge=0, le=100)


class FoodValuesInput(FoodNutrientsInput):
    name: str = Field(min_length=1, max_length=256)
    brand: str | None = Field(default=None, max_length=128)
    barcode: str | None = None
    standard_serving_amount: Decimal | None = Field(default=None, gt=0, max_digits=10)
    standard_serving_unit: ServingUnit | None = None
    standard_serving_weight_g: Decimal | None = Field(default=None, gt=0, max_digits=10)

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
    def validate_serving(self) -> FoodValuesInput:
        values = (
            self.standard_serving_amount,
            self.standard_serving_unit,
            self.standard_serving_weight_g,
        )
        if any(value is not None for value in values) and not all(
            value is not None for value in values
        ):
            raise ValueError("standard serving amount, unit, and weight must be provided together")
        if (
            self.standard_serving_unit == "g"
            and self.standard_serving_amount != self.standard_serving_weight_g
        ):
            raise ValueError("a gram serving amount must equal its weight")
        return self


class ExternalFoodSource(BaseModel):
    provider: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,63}$")
    attribution: str = Field(min_length=1, max_length=256)
    source_url: HttpUrl
    license: str = Field(min_length=1, max_length=128)
    license_url: HttpUrl


class ExternalFoodImportSource(ExternalFoodSource):
    external_id: str = Field(min_length=1, max_length=128)


class UserFoodCreate(FoodValuesInput):
    energy_kcal_per_100g: Decimal = Field(ge=0, le=1000)
    protein_g_per_100g: Decimal = Field(ge=0, le=100)
    fat_g_per_100g: Decimal = Field(ge=0, le=100)
    carbs_g_per_100g: Decimal = Field(ge=0, le=100)
    external_source: ExternalFoodImportSource | None = None


class UserFoodUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    brand: str | None = Field(default=None, max_length=128)
    barcode: str | None = None
    energy_kcal_per_100g: Decimal | None = Field(default=None, ge=0, le=1000)
    protein_g_per_100g: Decimal | None = Field(default=None, ge=0, le=100)
    fat_g_per_100g: Decimal | None = Field(default=None, ge=0, le=100)
    carbs_g_per_100g: Decimal | None = Field(default=None, ge=0, le=100)
    fiber_g_per_100g: Decimal | None = Field(default=None, ge=0, le=100)
    standard_serving_amount: Decimal | None = Field(default=None, gt=0, max_digits=10)
    standard_serving_unit: ServingUnit | None = None
    standard_serving_weight_g: Decimal | None = Field(default=None, gt=0, max_digits=10)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
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


class FoodResponse(BaseModel):
    id: int
    name: str
    brand: str | None
    barcode: str | None
    energy_kcal_per_100g: Decimal | None
    protein_g_per_100g: Decimal | None
    fat_g_per_100g: Decimal | None
    carbs_g_per_100g: Decimal | None
    fiber_g_per_100g: Decimal | None
    nutrition_basis_kind: NutritionBasisKind = "per_100_g"
    nutrition_basis_amount: Decimal = Decimal("100")
    nutrition_basis_unit: Literal["g", "ml", "serving"] = "g"
    canonical_facts: dict | None = None
    nutrition_provenance: dict | None = None
    catalog_quality: FoodCatalogQuality = "verified"
    provenance: FoodProvenance
    trust_level: FoodTrustLevel
    canonical_complete: bool = True
    standard_serving_amount: Decimal | None
    standard_serving_unit: ServingUnit | None
    standard_serving_weight_g: Decimal | None
    food_type: FoodType
    is_favorite: bool
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime


class FoodListResponse(BaseModel):
    items: list[FoodResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class ExternalFoodResponse(FoodValuesInput):
    energy_kcal_per_100g: Decimal = Field(ge=0, le=1000)
    protein_g_per_100g: Decimal = Field(ge=0, le=100)
    fat_g_per_100g: Decimal = Field(ge=0, le=100)
    carbs_g_per_100g: Decimal = Field(ge=0, le=100)
    barcode: str | None = None
    external_id: str
    source: ExternalFoodSource


class FoodProviderStatusResponse(BaseModel):
    provider: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,63}$")
    status: FoodProviderStatus
    result_count: int = Field(default=0, ge=0)


class FoodSearchResponse(FoodListResponse):
    external_items: list[ExternalFoodResponse] = Field(default_factory=list)
    provider_status: FoodProviderStatus = "not_requested"
    provider_statuses: list[FoodProviderStatusResponse] = Field(default_factory=list)


class FoodBarcodeLookupResponse(BaseModel):
    barcode: str
    status: FoodBarcodeLookupStatus
    source: FoodBarcodeLookupSource | None = None
    local_item: FoodResponse | None = None
    external_item: ExternalFoodResponse | None = None
    provider_status: FoodProviderStatus
    provider_statuses: list[FoodProviderStatusResponse] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result_shape(self) -> FoodBarcodeLookupResponse:
        if self.status == "not_found":
            if (
                self.source is not None
                or self.local_item is not None
                or self.external_item is not None
            ):
                raise ValueError("a not-found barcode lookup cannot contain a result")
            return self
        if self.source == "local" and self.local_item is not None and self.external_item is None:
            return self
        if self.source == "external" and self.external_item is not None and self.local_item is None:
            if self.external_item.barcode != self.barcode:
                raise ValueError("an external barcode result must match the requested barcode")
            return self
        raise ValueError(
            "a found barcode lookup must contain exactly one result matching its source"
        )


class FoodCatalogSource(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,63}$")
    version: str = Field(min_length=1, max_length=64)
    source_url: HttpUrl
    license: str = Field(min_length=1, max_length=128)
    license_url: HttpUrl
    reviewed_by: str = Field(min_length=1, max_length=128)
    reviewed_at: date
    license_verified: Literal[True]

    @field_validator("version", "license", "reviewed_by")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("reviewed_at")
    @classmethod
    def reject_future_review_date(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("reviewed_at must not be in the future")
        return value


class FoodCatalogItem(FoodValuesInput):
    external_id: str = Field(min_length=1, max_length=128)
    food_type: Literal["system", "branded"]
    status: Literal["active", "disabled"] = "active"

    @field_validator("external_id")
    @classmethod
    def normalize_external_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("external_id must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_active_nutrients(self) -> FoodCatalogItem:
        if self.status == "active" and any(
            value is None
            for value in (
                self.energy_kcal_per_100g,
                self.protein_g_per_100g,
                self.fat_g_per_100g,
                self.carbs_g_per_100g,
            )
        ):
            raise ValueError("active catalog foods require energy, protein, fat, and carbs")
        return self


class FoodCatalog(BaseModel):
    schema_version: Literal[1]
    source: FoodCatalogSource
    foods: list[FoodCatalogItem]

    @model_validator(mode="after")
    def validate_unique_source_ids(self) -> FoodCatalog:
        source_ids = [food.external_id for food in self.foods]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("catalog external_id values must be unique")
        return self
