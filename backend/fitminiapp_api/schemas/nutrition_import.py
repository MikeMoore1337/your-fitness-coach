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


class SummaryAggregation(ImportModel):
    kind: Literal["unknown", "total", "daily_average", "target"]
    evidence: Literal["unknown", "source_label", "source_profile", "provider_documentation"]
    denominator: Literal["unknown", "calendar_days", "logged_days"] | None = None
    denominator_days: int | None = Field(default=None, ge=0, strict=True, repr=False)

    @model_validator(mode="after")
    def validate_aggregation(self) -> SummaryAggregation:
        if (self.kind == "unknown") != (self.evidence == "unknown"):
            raise ValueError("known aggregation requires evidence; unknown aggregation has none")
        if self.kind == "daily_average":
            if self.denominator is None:
                raise ValueError("daily average requires a denominator or unknown")
        elif self.denominator is not None or self.denominator_days is not None:
            raise ValueError("only a daily average can have a denominator")
        return self


class OriginalSummaryValue(ImportModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    source_column: int | None = Field(default=None, ge=1, strict=True)
    source_header: str | None = Field(default=None, max_length=256, strict=True, repr=False)
    source_value: str | None = Field(default=None, max_length=128, strict=True, repr=False)
    nutrient_field: Identifier | None = None
    mapping_evidence: Literal[
        "unknown", "source_label", "source_profile", "provider_documentation"
    ] = "unknown"
    fact: NutrientFact = Field(repr=False)

    @field_validator("nutrient_field")
    @classmethod
    def validate_nutrient_field(cls, value: str | None) -> str | None:
        if value is not None and value not in SourceNutrients.model_fields:
            raise ValueError("unsupported nutrient field")
        return value

    @model_validator(mode="after")
    def require_original_fact(self) -> OriginalSummaryValue:
        if (self.nutrient_field is None) != (self.mapping_evidence == "unknown"):
            raise ValueError("known nutrient mapping requires evidence; unknown mapping has none")
        if self.mapping_evidence == "source_label" and (
            self.source_header is None or not self.source_header.strip()
        ):
            raise ValueError("source-label mapping evidence requires a source header")
        if self.fact.evidence == "derived":
            raise ValueError("original summary facts cannot be derived")
        if self.fact.evidence == "read" and (
            self.source_value is None or not self.source_value.strip()
        ):
            raise ValueError("read summary facts require a source value")
        return self


class OriginalDetailCell(OriginalSummaryValue):
    coordinates: SourceCoordinates = Field(repr=False)
    source_column: int = Field(ge=1, strict=True)

    @model_validator(mode="after")
    def require_detail(self) -> OriginalDetailCell:
        if self.coordinates.section_kind != "detail":
            raise ValueError("detail cells require detail coordinates")
        return self


class OriginalSummaryRow(ImportModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    coordinates: SourceCoordinates = Field(repr=False)
    source_label: str | None = Field(default=None, max_length=256, strict=True, repr=False)
    scope: Literal["meal", "overall", "unknown"]
    meal_type: MealType | None = Field(default=None, repr=False)
    values: list[OriginalSummaryValue] = Field(max_length=128, repr=False)

    @model_validator(mode="after")
    def validate_row(self) -> OriginalSummaryRow:
        if self.scope == "overall" and self.meal_type is not None:
            raise ValueError("an overall summary cannot name a meal")
        columns = [value.source_column for value in self.values if value.source_column is not None]
        if len(columns) != len(set(columns)):
            raise ValueError("summary source columns must be unique within a row")
        return self


class OriginalSummary(ImportModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    header_coordinates: SourceCoordinates = Field(repr=False)
    header_label: str | None = Field(default=None, max_length=256, strict=True, repr=False)
    aggregation: SummaryAggregation
    period_label: str | None = Field(default=None, max_length=256, strict=True, repr=False)
    period_start: DiaryDate | None = Field(default=None, repr=False)
    period_end: DiaryDate | None = Field(default=None, repr=False)
    period_coordinates: SourceCoordinates | None = Field(default=None, repr=False)
    timezone: str | None = Field(default=None, min_length=1, max_length=64, repr=False)
    rows: list[OriginalSummaryRow] = Field(repr=False)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is not None and not is_valid_timezone(value):
            raise ValueError("timezone must be a known IANA timezone")
        return value

    @model_validator(mode="after")
    def validate_period(self) -> OriginalSummary:
        if self.aggregation.evidence == "source_label" and (
            self.header_label is None or not self.header_label.strip()
        ):
            raise ValueError("source-label aggregation evidence requires a header label")
        if (
            self.period_start is not None
            and self.period_end is not None
            and self.period_start > self.period_end
        ):
            raise ValueError("summary period start must not be after end")
        return self


def _validate_import_coordinates(
    source: ImportSource,
    rows: list[ImportFoodRow],
    totals: list[OriginalTotal],
    extra: tuple[SourceCoordinates, ...] = (),
) -> None:
    coordinates = [row.coordinates for row in rows]
    coordinates.extend(coord for row in rows for coord in row.quantity_coordinates)
    coordinates.extend(total.coordinates for total in totals)
    coordinates.extend(
        reference.coordinates
        for row in rows
        for fact in row.nutrition.facts.__dict__.values()
        if fact is not None
        for reference in fact.derived_from
    )
    coordinates.extend(extra)
    if source.source_format == "csv" and any(coord.row is None for coord in coordinates):
        raise ValueError("CSV source coordinates require a row")
    if source.source_format == "pdf" and any(coord.page is None for coord in coordinates):
        raise ValueError("PDF source coordinates require a page")


class NutritionImportV1(ImportModel):
    schema_version: Literal["nutrition-import-v1"]
    source: ImportSource
    completeness: Literal["complete", "partial", "unknown"]
    rows: list[ImportFoodRow]
    original_totals: list[OriginalTotal]
    diagnostics: list[ImportDiagnostic]

    @model_validator(mode="after")
    def validate_format_coordinates(self) -> NutritionImportV1:
        _validate_import_coordinates(self.source, self.rows, self.original_totals)
        return self


class NutritionImportV2(ImportModel):
    schema_version: Literal["nutrition-import-v2"]
    source: ImportSource
    completeness: Literal["complete", "partial", "unknown"]
    rows: list[ImportFoodRow] = Field(repr=False)
    original_totals: list[OriginalTotal] = Field(repr=False)
    original_summaries: list[OriginalSummary] = Field(repr=False)
    diagnostics: list[ImportDiagnostic] = Field(repr=False)

    @model_validator(mode="after")
    def validate_format_coordinates(self) -> NutritionImportV2:
        coordinates: list[SourceCoordinates] = []
        for summary in self.original_summaries:
            coordinates.append(summary.header_coordinates)
            if summary.period_coordinates is not None:
                coordinates.append(summary.period_coordinates)
            coordinates.extend(row.coordinates for row in summary.rows)
        coordinates.extend(
            diagnostic.coordinates
            for diagnostic in self.diagnostics
            if diagnostic.coordinates is not None
        )
        coordinates.extend(
            diagnostic.coordinates
            for row in self.rows
            for diagnostic in row.diagnostics
            if diagnostic.coordinates is not None
        )
        _validate_import_coordinates(
            self.source, self.rows, self.original_totals, tuple(coordinates)
        )
        return self


class NutritionImportV3(ImportModel):
    schema_version: Literal["nutrition-import-v3"]
    source: ImportSource
    completeness: Literal["complete", "partial", "unknown"]
    rows: list[ImportFoodRow] = Field(repr=False)
    original_totals: list[OriginalTotal] = Field(repr=False)
    original_summaries: list[OriginalSummary] = Field(repr=False)
    original_detail_cells: list[OriginalDetailCell] = Field(max_length=2000, repr=False)
    diagnostics: list[ImportDiagnostic] = Field(repr=False)

    @model_validator(mode="after")
    def validate_format_coordinates(self) -> NutritionImportV3:
        coordinates: list[SourceCoordinates] = []
        for summary in self.original_summaries:
            coordinates.append(summary.header_coordinates)
            if summary.period_coordinates is not None:
                coordinates.append(summary.period_coordinates)
            coordinates.extend(row.coordinates for row in summary.rows)
        coordinates.extend(cell.coordinates for cell in self.original_detail_cells)
        coordinates.extend(
            diagnostic.coordinates
            for diagnostic in self.diagnostics
            if diagnostic.coordinates is not None
        )
        coordinates.extend(
            diagnostic.coordinates
            for row in self.rows
            for diagnostic in row.diagnostics
            if diagnostic.coordinates is not None
        )
        _validate_import_coordinates(
            self.source, self.rows, self.original_totals, tuple(coordinates)
        )
        cells = [
            (
                cell.coordinates.section,
                cell.coordinates.page,
                cell.coordinates.row,
                cell.source_column,
            )
            for cell in self.original_detail_cells
        ]
        if len(cells) != len(set(cells)):
            raise ValueError("detail cells must have unique coordinates")
        source_rows = {
            (item.coordinates.section, item.coordinates.page, item.coordinates.row)
            for item in (*self.rows, *self.original_totals)
        }
        if any(cell[:3] not in source_rows for cell in cells):
            raise ValueError("detail cells must refer to a source row")
        return self
