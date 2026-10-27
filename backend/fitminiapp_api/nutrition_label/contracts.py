from __future__ import annotations

from decimal import Decimal
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CANONICAL_DRAFT_SCHEMA_VERSION: Final[Literal["nutrition-label-draft-v1"]] = (
    "nutrition-label-draft-v1"
)
CANONICAL_POLICY_REVISION: Final[str] = "nutrition-label-local-v2"
LOCAL_OCR_ENGINE_VERSION: Final[str] = "rapidocr-3.9.2-ppocrv5-cyrillic-mobile-v1"

NUTRIENT_FIELDS = (
    "energy_kcal",
    "energy_kj",
    "protein_g",
    "fat_g",
    "saturated_fat_g",
    "trans_fat_g",
    "carbohydrate_g",
    "sugars_g",
    "added_sugars_g",
    "fiber_g",
    "salt_g",
    "sodium_mg",
    "cholesterol_mg",
)
NUTRIENT_UNITS: dict[str, Literal["g", "mg", "kcal", "kJ"]] = {
    "energy_kcal": "kcal",
    "energy_kj": "kJ",
    "protein_g": "g",
    "fat_g": "g",
    "saturated_fat_g": "g",
    "trans_fat_g": "g",
    "carbohydrate_g": "g",
    "sugars_g": "g",
    "added_sugars_g": "g",
    "fiber_g": "g",
    "salt_g": "g",
    "sodium_mg": "mg",
    "cholesterol_mg": "mg",
}

BasisKind = Literal["per_100_g", "per_100_ml", "per_serving"]
SourceBasis = Literal["per_100_g", "per_100_ml", "per_serving", "ambiguous"]
SourceBasisRef = Literal["per_100_g", "per_100_ml", "per_serving", "ambiguous"]
BasisUnit = Literal["g", "ml", "serving"]
FactUnit = Literal["g", "mg", "kcal", "kJ"]
Evidence = Literal["read", "ambiguous", "unreadable", "absent", "derived"]
SourceEvidence = Literal["read", "ambiguous", "unreadable"]
SourceLanguage = Literal["ru", "en", "mixed", "unknown"]
LabelFormat = Literal["ru_standard", "eu_uk", "us_nutrition_facts", "unknown"]
ConfidenceKind = Literal["provider_native", "calibrated_eval", "none"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ServingSize(StrictModel):
    amount: Decimal = Field(gt=0, allow_inf_nan=False)
    unit: Literal["g", "ml"]


class PackageAmount(ServingSize):
    pass


class CanonicalFact(StrictModel):
    value: Decimal = Field(ge=0, allow_inf_nan=False)
    unit: FactUnit
    basis_ref: BasisKind

    @field_validator("unit")
    @classmethod
    def normalize_unit(cls, value: FactUnit) -> FactUnit:
        return value


class SourceFact(StrictModel):
    value: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    unit: FactUnit
    basis_ref: SourceBasisRef
    column_ref: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    evidence: SourceEvidence

    @model_validator(mode="after")
    def validate_evidence_value(self) -> SourceFact:
        if self.evidence == "read" and self.value is None:
            raise ValueError("read source facts require a value")
        if self.evidence != "read" and self.value is not None:
            raise ValueError("ambiguous or unreadable source facts must be null")
        return self


class DerivedFact(StrictModel):
    value: Decimal = Field(ge=0, allow_inf_nan=False)
    unit: FactUnit
    reason: str = Field(min_length=1, max_length=256)
    source_fields: list[str] = Field(min_length=1, max_length=8)


class NutrientFacts(StrictModel):
    energy_kcal: CanonicalFact | None = None
    energy_kj: CanonicalFact | None = None
    protein_g: CanonicalFact | None = None
    fat_g: CanonicalFact | None = None
    saturated_fat_g: CanonicalFact | None = None
    trans_fat_g: CanonicalFact | None = None
    carbohydrate_g: CanonicalFact | None = None
    sugars_g: CanonicalFact | None = None
    added_sugars_g: CanonicalFact | None = None
    fiber_g: CanonicalFact | None = None
    salt_g: CanonicalFact | None = None
    sodium_mg: CanonicalFact | None = None
    cholesterol_mg: CanonicalFact | None = None


class SourceNutrientFacts(StrictModel):
    energy_kcal: list[SourceFact] | None = None
    energy_kj: list[SourceFact] | None = None
    protein_g: list[SourceFact] | None = None
    fat_g: list[SourceFact] | None = None
    saturated_fat_g: list[SourceFact] | None = None
    trans_fat_g: list[SourceFact] | None = None
    carbohydrate_g: list[SourceFact] | None = None
    sugars_g: list[SourceFact] | None = None
    added_sugars_g: list[SourceFact] | None = None
    fiber_g: list[SourceFact] | None = None
    salt_g: list[SourceFact] | None = None
    sodium_mg: list[SourceFact] | None = None
    cholesterol_mg: list[SourceFact] | None = None

    @model_validator(mode="after")
    def validate_unique_columns(self) -> SourceNutrientFacts:
        for field_name in NUTRIENT_FIELDS:
            cells = getattr(self, field_name)
            if cells is None:
                continue
            columns = [cell.column_ref for cell in cells]
            if len(columns) != len(set(columns)):
                raise ValueError(f"{field_name} source columns must be unique")
        return self


class DerivedNutrientFacts(StrictModel):
    energy_kcal: DerivedFact | None = None
    energy_kj: DerivedFact | None = None
    protein_g: DerivedFact | None = None
    fat_g: DerivedFact | None = None
    saturated_fat_g: DerivedFact | None = None
    trans_fat_g: DerivedFact | None = None
    carbohydrate_g: DerivedFact | None = None
    sugars_g: DerivedFact | None = None
    added_sugars_g: DerivedFact | None = None
    fiber_g: DerivedFact | None = None
    salt_g: DerivedFact | None = None
    sodium_mg: DerivedFact | None = None
    cholesterol_mg: DerivedFact | None = None


class DailyValuePercent(StrictModel):
    energy_kcal: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    protein_g: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    fat_g: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    saturated_fat_g: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    trans_fat_g: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    carbohydrate_g: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    fiber_g: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    sugars_g: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    added_sugars_g: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    salt_g: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    sodium_mg: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    cholesterol_mg: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)


class FieldConfidence(StrictModel):
    energy_kcal: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    energy_kj: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    protein_g: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    fat_g: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    saturated_fat_g: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    trans_fat_g: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    carbohydrate_g: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    sugars_g: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    added_sugars_g: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    fiber_g: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    salt_g: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    sodium_mg: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    cholesterol_mg: Decimal | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)


class FieldEvidence(StrictModel):
    energy_kcal: Evidence = "absent"
    energy_kj: Evidence = "absent"
    protein_g: Evidence = "absent"
    fat_g: Evidence = "absent"
    saturated_fat_g: Evidence = "absent"
    trans_fat_g: Evidence = "absent"
    carbohydrate_g: Evidence = "absent"
    sugars_g: Evidence = "absent"
    added_sugars_g: Evidence = "absent"
    fiber_g: Evidence = "absent"
    salt_g: Evidence = "absent"
    sodium_mg: Evidence = "absent"
    cholesterol_mg: Evidence = "absent"


class DraftMetadata(StrictModel):
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)
    prompt_version: str = Field(min_length=1, max_length=128)
    schema_version: Literal["nutrition-label-draft-v1"]
    policy_revision: str = Field(min_length=1, max_length=128)


class CanonicalDraft(StrictModel):
    schema_version: Literal["nutrition-label-draft-v1"]
    source_language: SourceLanguage
    label_format: LabelFormat
    source_basis: SourceBasis
    serving_size: ServingSize | None = None
    servings_per_container: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    package_amount: PackageAmount | None = None
    source_facts: SourceNutrientFacts
    normalized_facts: NutrientFacts
    derived_fields: DerivedNutrientFacts
    displayed_daily_value_percent: DailyValuePercent
    field_evidence: FieldEvidence
    confidence_kind: ConfidenceKind
    confidence: FieldConfidence
    warnings: list[str] = Field(default_factory=list, max_length=32)
    requires_user_review: Literal[True] = True
    metadata: DraftMetadata

    @field_validator("warnings")
    @classmethod
    def validate_warning_codes(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("warning codes must be unique")
        for value in normalized:
            if not value or not value.replace("_", "").isalnum() or not value[0].islower():
                raise ValueError("warning codes must be safe identifiers")
        return normalized

    @model_validator(mode="after")
    def validate_contract(self) -> CanonicalDraft:
        if self.metadata.schema_version != self.schema_version:
            raise ValueError("metadata schema version must match the draft schema version")
        if self.confidence_kind == "none" and any(
            getattr(self.confidence, field_name) is not None for field_name in NUTRIENT_FIELDS
        ):
            raise ValueError("confidence values require a calibrated confidence kind")
        for field_name in NUTRIENT_FIELDS:
            expected_unit = NUTRIENT_UNITS[field_name]
            normalized = getattr(self.normalized_facts, field_name)
            if normalized is not None and normalized.unit != expected_unit:
                raise ValueError(f"{field_name} has an invalid canonical unit")
            source_cells = getattr(self.source_facts, field_name)
            if source_cells is not None:
                for cell in source_cells:
                    if cell.unit != expected_unit:
                        raise ValueError(f"{field_name} has an invalid source unit")
                    if self.source_basis != "ambiguous" and cell.basis_ref == "ambiguous":
                        raise ValueError(
                            f"{field_name} has an ambiguous source basis in a resolved draft"
                        )
        if self.source_basis == "ambiguous" and any(
            getattr(self.normalized_facts, field_name) is not None for field_name in NUTRIENT_FIELDS
        ):
            raise ValueError("ambiguous source basis cannot have normalized facts")
        return self


def validate_canonical_draft(payload: object) -> CanonicalDraft:
    """Strictly validate untrusted extractor output before persistence or response."""

    return CanonicalDraft.model_validate(payload)


def empty_nutrient_facts() -> NutrientFacts:
    return NutrientFacts()


def empty_source_facts() -> SourceNutrientFacts:
    return SourceNutrientFacts()


def empty_derived_facts() -> DerivedNutrientFacts:
    return DerivedNutrientFacts()


def empty_daily_values() -> DailyValuePercent:
    return DailyValuePercent()


def empty_confidence() -> FieldConfidence:
    return FieldConfidence()
