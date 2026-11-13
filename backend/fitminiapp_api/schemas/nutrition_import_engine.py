from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fitminiapp_api.schemas.food_diary import MealType
from fitminiapp_api.schemas.nutrition_import import (
    ImportDiagnostic,
    ImportFoodRow,
    ImportSource,
    OriginalDetailCell,
    OriginalSummary,
    OriginalTotal,
)
from fitminiapp_api.schemas.nutrition_label import NutritionLabelFactsEdit


class RowResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int = Field(ge=0, strict=True)
    food_id: int = Field(gt=0, strict=True)


class ImportResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1, strict=True)
    matches: list[RowResolution] = Field(max_length=2000)
    skipped_rows: list[Annotated[int, Field(ge=0, strict=True)]] = Field(max_length=2000)


class ImportConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1, strict=True)
    preview_signature: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirm_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def require_explicit_true(cls, value: object) -> object:
        if value is not True:
            raise ValueError("explicit confirmation is required")
        return value


class ImportCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1, strict=True)


class ImportPreviewRow(BaseModel):
    index: int
    status: Literal[
        "matched", "new", "ambiguous", "invalid", "skipped", "manual_resolution_required"
    ]
    source: ImportFoodRow
    action: dict[str, Any] | None
    issues: list[str]


class ImportPreview(BaseModel):
    id: str
    revision: int
    expires_at: datetime
    schema_version: Literal["nutrition-import-v1", "nutrition-import-v2", "nutrition-import-v3"]
    parser_version: str
    content_sha256: str
    completeness: Literal["complete", "partial", "unknown"]
    source: ImportSource
    rows: list[ImportPreviewRow]
    original_totals: list[OriginalTotal]
    original_summaries: list[OriginalSummary]
    original_detail_cells: list[OriginalDetailCell] = Field(default_factory=list)
    diagnostics: list[ImportDiagnostic]
    preview_signature: str


class ImportReceipt(BaseModel):
    entry_ids: list[int]
    preview_signature: str


class CatalogImportRow(BaseModel):
    index: int
    outcome: Literal["reuse", "publish", "conflict", "needs_review", "private_only", "skipped"]
    reason: str | None
    food_id: int | None


class CatalogProductPreview(BaseModel):
    name: str
    brand: str | None
    barcode: str | None
    kind: Literal["standard_food", "branded_food"]
    nutrition: dict[str, Any]
    provenance: dict[str, Any]


class CatalogCandidate(BaseModel):
    food_id: int
    name: str
    brand: str | None


class CatalogImportPreviewRow(CatalogImportRow):
    product: CatalogProductPreview | None
    suggestions: list[CatalogCandidate]
    suggestions_evaluated: bool


class CatalogImportPreview(BaseModel):
    id: str
    revision: int
    expires_at: datetime
    source: ImportSource
    rows: list[CatalogImportPreviewRow]
    preview_signature: str


class CatalogProductCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    index: int = Field(ge=0, strict=True)
    name: str = Field(min_length=1, max_length=256)
    brand: str | None = Field(default=None, max_length=128)
    kind: Literal["standard_food", "branded_food", "personal_recipe", "arbitrary"]
    nutrition: NutritionLabelFactsEdit | None = None
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def require_explicit_true(cls, value: object) -> object:
        if value is not True:
            raise ValueError("explicit confirmation is required")
        return value

    @model_validator(mode="after")
    def require_nutrition_for_public_products(self) -> CatalogProductCorrection:
        if self.kind in {"standard_food", "branded_food"} and self.nutrition is None:
            raise ValueError("public products require reviewed nutrition")
        return self


class CatalogConflictChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int = Field(ge=0, strict=True)
    action: Literal["reuse", "skip"]
    food_id: int | None = Field(default=None, gt=0, strict=True)


class CatalogReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1, strict=True)
    corrections: list[CatalogProductCorrection] = Field(max_length=2000)
    choices: list[CatalogConflictChoice] = Field(default_factory=list, max_length=2000)


class CatalogImportConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1, strict=True)
    preview_signature: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirm_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    row_indexes: list[Annotated[int, Field(ge=0, strict=True)]] = Field(max_length=2000)
    corrections: list[CatalogProductCorrection] = Field(default_factory=list, max_length=2000)
    choices: list[CatalogConflictChoice] = Field(default_factory=list, max_length=2000)
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def require_explicit_true(cls, value: object) -> object:
        if value is not True:
            raise ValueError("explicit confirmation is required")
        return value


class CatalogImportReceipt(BaseModel):
    rows: list[CatalogImportRow]
    excluded_rows: list[CatalogImportRow] = Field(default_factory=list)
    preview_signature: str


class RecurringImportMealItem(BaseModel):
    food_id: int
    source: ImportFoodRow
    original_total: OriginalTotal | None
    original_detail_cells: list[OriginalDetailCell]


class RecurringImportMealOccurrence(BaseModel):
    date: date
    items: list[RecurringImportMealItem]


class RecurringImportMeal(BaseModel):
    meal_type: MealType
    repeat_days: int
    occurrences: list[RecurringImportMealOccurrence]


class RecurringImportMeals(BaseModel):
    observed_days: int
    items: list[RecurringImportMeal]


class CatalogConflict(BaseModel):
    id: int
    food_id: int
    payload: dict[str, Any]
    preview_signature: str


class CatalogAliasConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_signature: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def require_explicit_true(cls, value: object) -> object:
        if value is not True:
            raise ValueError("explicit confirmation is required")
        return value


class CatalogAliasReceipt(BaseModel):
    food_id: int
    contribution_id: int
