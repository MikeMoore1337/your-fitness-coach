"""Provider-neutral, non-persisting nutrition import contract (NI-01)."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    WithJsonSchema,
    field_validator,
    model_validator,
)

from fitminiapp_api.core.timezone import is_valid_timezone
from fitminiapp_api.nutrition_label.contracts import NUTRIENT_UNITS, BasisKind
from fitminiapp_api.schemas.food import ServingUnit, validate_gtin
from fitminiapp_api.schemas.food_diary import MealType


def _decimal_input(value: object) -> Decimal:
    if isinstance(value, str) and len(value) <= 64:
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value, re.ASCII):
            raise ValueError("use a decimal string without grouping or a Decimal")
        value = Decimal(value)
    if not isinstance(value, Decimal) or not value.is_finite() or value.is_signed():
        raise ValueError("use a finite decimal string or Decimal")
    parts = value.as_tuple()
    exponent = parts.exponent
    if not isinstance(exponent, int) or not -8 <= exponent <= 0:
        raise ValueError("decimal precision exceeds eight places")
    if len(parts.digits) + max(exponent, 0) > 18:
        raise ValueError("decimal precision exceeds eighteen digits")
    return value


def _date_input(value: object) -> object:
    if value is None or (isinstance(value, date) and not isinstance(value, datetime)):
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return value
    raise ValueError("diary date must be an ISO date or null")


NonnegativeDecimal = Annotated[
    Decimal,
    BeforeValidator(_decimal_input),
    PlainSerializer(lambda value: format(value, "f"), return_type=str, when_used="json"),
    Field(ge=0, allow_inf_nan=False),
    WithJsonSchema({"type": "string", "pattern": r"^[0-9]+(?:\.[0-9]{1,8})?$", "maxLength": 64}),
]
PositiveDecimal = Annotated[
    Decimal,
    BeforeValidator(_decimal_input),
    PlainSerializer(lambda value: format(value, "f"), return_type=str, when_used="json"),
    Field(gt=0, allow_inf_nan=False),
    WithJsonSchema(
        {"type": "string", "pattern": r"^(?=.*[1-9])[0-9]+(?:\.[0-9]{1,8})?$", "maxLength": 64}
    ),
]
Identifier = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]*$")]
DiaryDate = Annotated[date, BeforeValidator(_date_input)]


class ImportModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ImportSource(ImportModel):
    provider: Identifier
    source: Identifier
    source_version: Identifier | None = None
    adapter_version: Identifier
    source_format: Identifier
    transport: Literal["upload", "url"]
    publication_rights: Literal["unknown", "owner_reported", "verified", "prohibited"] = "unknown"


class SourceCoordinates(ImportModel):
    section: Identifier
    section_kind: Literal["detail", "summary", "unknown"]
    page: int | None = Field(default=None, ge=1, strict=True)
    row: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode="after")
    def require_position(self) -> SourceCoordinates:
        if self.page is None and self.row is None:
            raise ValueError("a source page or row is required")
        return self


class ImportDiagnostic(ImportModel):
    code: Identifier
    severity: Literal["warning", "error"]
    coordinates: SourceCoordinates | None = None
    field: Identifier | None = None


class SourceFieldReference(ImportModel):
    coordinates: SourceCoordinates
    field: Identifier


class NutrientFact(ImportModel):
    value: NonnegativeDecimal | None
    unit: Literal["g", "mg", "kcal", "kJ"] | None
    source_unit: str | None = Field(default=None, min_length=1, max_length=32)
    evidence: Literal["read", "derived", "absent", "ambiguous", "unreadable"]
    derivation: Identifier | None = None
    derived_from: list[SourceFieldReference] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def validate_evidence(self) -> NutrientFact:
        if (self.value is not None) != (self.evidence in {"read", "derived"}):
            raise ValueError("only read or derived facts have a value")
        if self.evidence == "derived":
            if self.derivation is None or not self.derived_from:
                raise ValueError("derived facts require a derivation and inputs")
        elif self.derivation is not None or self.derived_from:
            raise ValueError("only derived facts can have derivation inputs")
        return self


class SourceNutrients(ImportModel):
    energy_kcal: NutrientFact | None = None
    energy_kj: NutrientFact | None = None
    protein_g: NutrientFact | None = None
    fat_g: NutrientFact | None = None
    saturated_fat_g: NutrientFact | None = None
    trans_fat_g: NutrientFact | None = None
    carbohydrate_g: NutrientFact | None = None
    sugars_g: NutrientFact | None = None
    added_sugars_g: NutrientFact | None = None
    fiber_g: NutrientFact | None = None
    salt_g: NutrientFact | None = None
    sodium_mg: NutrientFact | None = None
    cholesterol_mg: NutrientFact | None = None
    potassium_mg: NutrientFact | None = None


class ImportNutrients(SourceNutrients):
    @model_validator(mode="after")
    def validate_units(self) -> ImportNutrients:
        for name, unit in {**NUTRIENT_UNITS, "potassium_mg": "mg"}.items():
            fact = getattr(self, name)
            if (
                fact is not None
                and fact.unit != unit
                and not (fact.value is None and fact.unit is None)
            ):
                raise ValueError(f"{name} has an invalid unit")
        return self


class ImportNutrition(ImportModel):
    basis: BasisKind | None
    facts: ImportNutrients

    @model_validator(mode="after")
    def require_known_basis(self) -> ImportNutrition:
        if self.basis is None and any(
            fact is not None and fact.value is not None for fact in self.facts.__dict__.values()
        ):
            raise ValueError("known nutrition facts require an explicit basis")
        return self


class ServingMeasure(ImportModel):
    amount: PositiveDecimal
    unit: Literal["g", "ml"]


class ImportFoodIdentity(ImportModel):
    name: str = Field(min_length=1, max_length=256)
    brand: str | None = Field(default=None, min_length=1, max_length=128)
    variant: str | None = Field(default=None, min_length=1, max_length=128)
    kind: Literal["standard_food", "branded_food", "personal_recipe", "arbitrary", "unknown"]
    identity_source: Identifier | None = None
    source_id: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
    )
    gtin: str | None = None

    @field_validator("gtin")
    @classmethod
    def validate_barcode(cls, value: str | None) -> str | None:
        return validate_gtin(value)

    @model_validator(mode="after")
    def validate_source_identity(self) -> ImportFoodIdentity:
        if (self.identity_source is None) != (self.source_id is None):
            raise ValueError("identity source and source ID must be provided together")
        return self


class ImportFoodRow(ImportModel):
    coordinates: SourceCoordinates
    quantity_coordinates: list[SourceCoordinates] = Field(default_factory=list, max_length=8)
    diary_date: DiaryDate | None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    meal_type: MealType | None
    food: ImportFoodIdentity
    quantity: PositiveDecimal | None
    amount_unit: ServingUnit | None
    source_unit: str | None = Field(default=None, min_length=1, max_length=128)
    serving_label: str | None = Field(default=None, min_length=1, max_length=256)
    serving_measure: ServingMeasure | None = None
    nutrition: ImportNutrition
    diagnostics: list[ImportDiagnostic] = Field(default_factory=list, max_length=128)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is not None and not is_valid_timezone(value):
            raise ValueError("timezone must be a known IANA timezone")
        return value

    @model_validator(mode="after")
    def validate_detail(self) -> ImportFoodRow:
        if self.coordinates.section_kind != "detail" or any(
            coord.section_kind != "detail" for coord in self.quantity_coordinates
        ):
            raise ValueError("food and quantity rows must belong to a detail section")
        if self.quantity is None and self.amount_unit is not None:
            raise ValueError("an amount unit requires a quantity")
        return self


class OriginalTotal(ImportModel):
    scope: Literal["entry", "meal", "day", "period", "unknown"]
    coordinates: SourceCoordinates
    diary_date: DiaryDate | None = None
    meal_type: MealType | None = None
    facts: SourceNutrients

    @model_validator(mode="after")
    def require_original_facts(self) -> OriginalTotal:
        if any(
            fact is not None and fact.evidence == "derived" for fact in self.facts.__dict__.values()
        ):
            raise ValueError("original totals cannot contain derived facts")
        return self


class NutritionImportV1(ImportModel):
    schema_version: Literal["nutrition-import-v1"]
    source: ImportSource
    completeness: Literal["complete", "partial", "unknown"]
    rows: list[ImportFoodRow]
    original_totals: list[OriginalTotal]
    diagnostics: list[ImportDiagnostic]

    @model_validator(mode="after")
    def validate_format_coordinates(self) -> NutritionImportV1:
        coordinates = [row.coordinates for row in self.rows]
        coordinates.extend(coord for row in self.rows for coord in row.quantity_coordinates)
        coordinates.extend(total.coordinates for total in self.original_totals)
        coordinates.extend(
            reference.coordinates
            for row in self.rows
            for fact in row.nutrition.facts.__dict__.values()
            if fact is not None
            for reference in fact.derived_from
        )
        if self.source.source_format == "csv" and any(coord.row is None for coord in coordinates):
            raise ValueError("CSV source coordinates require a row")
        if self.source.source_format == "pdf" and any(coord.page is None for coord in coordinates):
            raise ValueError("PDF source coordinates require a page")
        return self
