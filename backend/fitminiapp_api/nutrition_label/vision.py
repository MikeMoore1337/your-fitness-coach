from __future__ import annotations

import base64
import json
from decimal import Decimal
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from fitminiapp_api.core.config import settings
from fitminiapp_api.nutrition_label.contracts import (
    CANONICAL_DRAFT_SCHEMA_VERSION,
    NUTRIENT_FIELDS,
    NUTRIENT_UNITS,
    CanonicalDraft,
    CanonicalFact,
    DraftMetadata,
    FieldEvidence,
    NutrientFacts,
    ServingSize,
    SourceFact,
    SourceNutrientFacts,
    empty_confidence,
    empty_daily_values,
    empty_derived_facts,
    validate_canonical_draft,
)
from fitminiapp_api.nutrition_label.parser import (
    PARSER_WARNING_CODES,
    energy_pair_is_consistent,
    macro_energy_is_consistent,
    nutrient_value_exceeds_outlier_limit,
)

VISION_POLICY_REVISION = "nutrition-label-vision-v1"
VISION_MAX_RESPONSE_BYTES = 65_536
VISION_ALLOWED_WARNING_CODES = frozenset({*PARSER_WARNING_CODES, "ocr_budget_exhausted"})
GROQ_VISION_PROMPT_VERSION = "nutrition-label-groq-qwen38-v1"
_GROQ_VISION_SCHEMA_NAME = "nutrition_label_extraction_v1"
_GROQ_VISION_INSTRUCTION = """Read only the nutrition facts that are visibly printed on this package label.
Return null for every value that is absent, unreadable, or uncertain. Never infer nutrients,
serving size, units, or basis from typical product values. Select source_basis only from explicit
label wording. Numeric nutrient values must be the values printed for that basis, not calculated
daily values or percentages. Do not identify the user or infer any health information."""


class VisionExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_language: Literal["ru", "en", "mixed", "unknown"]
    label_format: Literal["ru_standard", "eu_uk", "us_nutrition_facts", "unknown"]
    source_basis: Literal["per_100_g", "per_100_ml", "per_serving", "ambiguous"]
    serving_amount: float | None = Field(ge=0, allow_inf_nan=False)
    serving_unit: Literal["g", "ml"] | None
    energy_kcal: float | None = Field(ge=0, allow_inf_nan=False)
    energy_kj: float | None = Field(ge=0, allow_inf_nan=False)
    protein_g: float | None = Field(ge=0, allow_inf_nan=False)
    fat_g: float | None = Field(ge=0, allow_inf_nan=False)
    saturated_fat_g: float | None = Field(ge=0, allow_inf_nan=False)
    trans_fat_g: float | None = Field(ge=0, allow_inf_nan=False)
    carbohydrate_g: float | None = Field(ge=0, allow_inf_nan=False)
    sugars_g: float | None = Field(ge=0, allow_inf_nan=False)
    added_sugars_g: float | None = Field(ge=0, allow_inf_nan=False)
    fiber_g: float | None = Field(ge=0, allow_inf_nan=False)
    salt_g: float | None = Field(ge=0, allow_inf_nan=False)
    sodium_mg: float | None = Field(ge=0, allow_inf_nan=False)
    cholesterol_mg: float | None = Field(ge=0, allow_inf_nan=False)


class VisionFallbackAdapter(Protocol):
    provider_class: str
    model_class: str
    prompt_version: str

    def recognize(
        self,
        normalized_png: bytes,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> bytes: ...


class VisionProposalError(ValueError):
    """A provider proposal failed deterministic validation."""


def _decimal_from_provider(value: float) -> Decimal:
    return Decimal(str(value))


def _canonical_from_extraction(
    extraction: VisionExtraction,
    *,
    provider_class: str,
    model_class: str,
    prompt_version: str,
) -> CanonicalDraft:
    if extraction.source_basis == "ambiguous":
        raise VisionProposalError("ambiguous_basis")
    if (extraction.serving_amount is None) != (extraction.serving_unit is None):
        raise VisionProposalError("invalid_serving_size")
    serving_size = None
    if extraction.serving_amount is not None and extraction.serving_unit is not None:
        if extraction.serving_amount <= 0:
            raise VisionProposalError("invalid_serving_size")
        serving_size = ServingSize(
            amount=_decimal_from_provider(extraction.serving_amount),
            unit=extraction.serving_unit,
        )

    source_payload: dict[str, list[SourceFact] | None] = {}
    normalized_payload: dict[str, CanonicalFact | None] = {}
    evidence_payload: dict[str, str] = {}
    for field_name in NUTRIENT_FIELDS:
        raw_value = getattr(extraction, field_name)
        if raw_value is None:
            source_payload[field_name] = None
            normalized_payload[field_name] = None
            evidence_payload[field_name] = "absent"
            continue

        value = _decimal_from_provider(raw_value)
        unit = NUTRIENT_UNITS[field_name]
        source_payload[field_name] = [
            SourceFact(
                value=value,
                unit=unit,
                basis_ref=extraction.source_basis,
                column_ref="main",
                evidence="read",
            )
        ]
        normalized_value = value
        basis_ref = extraction.source_basis
        if extraction.source_basis == "per_serving" and serving_size is not None:
            normalized_value = value * Decimal(100) / serving_size.amount
            basis_ref = "per_100_g" if serving_size.unit == "g" else "per_100_ml"
        normalized_payload[field_name] = CanonicalFact(
            value=normalized_value,
            unit=unit,
            basis_ref=basis_ref,
        )
        evidence_payload[field_name] = "read"

    return CanonicalDraft(
        schema_version=CANONICAL_DRAFT_SCHEMA_VERSION,
        source_language=extraction.source_language,
        label_format=extraction.label_format,
        source_basis=extraction.source_basis,
        serving_size=serving_size,
        servings_per_container=None,
        package_amount=None,
        source_facts=SourceNutrientFacts(**source_payload),
        normalized_facts=NutrientFacts(**normalized_payload),
        derived_fields=empty_derived_facts(),
        displayed_daily_value_percent=empty_daily_values(),
        field_evidence=FieldEvidence(**evidence_payload),
        confidence_kind="none",
        confidence=empty_confidence(),
        warnings=[],
        requires_user_review=True,
        metadata=DraftMetadata(
            provider=provider_class,
            model=model_class,
            prompt_version=prompt_version,
            schema_version=CANONICAL_DRAFT_SCHEMA_VERSION,
            policy_revision=VISION_POLICY_REVISION,
        ),
    )


class GroqNutritionLabelVisionAdapter:
    provider_class = "groq"
    prompt_version = GROQ_VISION_PROMPT_VERSION

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str,
        model: str,
        proxy_url: str,
        max_output_tokens: int,
    ) -> None:
        self._api_key = api_key
        self._endpoint = endpoint
        self.model_class = model
        self._proxy_url = proxy_url
        self._max_output_tokens = max_output_tokens

    def recognize(
        self,
        normalized_png: bytes,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> bytes:
        if not normalized_png.startswith(b"\x89PNG\r\n\x1a\n"):
            raise VisionProposalError("invalid_normalized_image")
        encoded = base64.b64encode(normalized_png).decode("ascii")
        payload = {
            "model": self.model_class,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _GROQ_VISION_INSTRUCTION},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{encoded}"},
                        },
                    ],
                }
            ],
            "max_completion_tokens": self._max_output_tokens,
            "reasoning_effort": "none",
            "store": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": _GROQ_VISION_SCHEMA_NAME,
                    "strict": True,
                    "schema": VisionExtraction.model_json_schema(),
                },
            },
        }
        try:
            with httpx.Client(
                timeout=httpx.Timeout(timeout_seconds),
                follow_redirects=False,
                trust_env=False,
                proxy=self._proxy_url or None,
            ) as client:
                response = client.post(
                    self._endpoint,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise TimeoutError("vision_provider_timeout") from exc
        except httpx.HTTPError as exc:
            raise OSError("vision_provider_unavailable") from exc

        if response.status_code != 200:
            raise OSError("vision_provider_http_error")
        try:
            raw_payload = response.json()
            choices = raw_payload.get("choices") if isinstance(raw_payload, dict) else None
            if (
                not isinstance(choices, list)
                or len(choices) != 1
                or not isinstance(choices[0], dict)
                or choices[0].get("finish_reason") != "stop"
            ):
                raise VisionProposalError("invalid_provider_response")
            message = choices[0].get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, str):
                raise VisionProposalError("invalid_provider_response")
            content_bytes = content.encode("utf-8")
            if not content_bytes or len(content_bytes) > max_response_bytes:
                raise VisionProposalError("response_size")
            extraction = VisionExtraction.model_validate(
                json.loads(
                    content,
                    object_pairs_hook=_unique_object,
                    parse_constant=_reject_non_finite,
                )
            )
            canonical = _canonical_from_extraction(
                extraction,
                provider_class=self.provider_class,
                model_class=self.model_class,
                prompt_version=self.prompt_version,
            )
            return canonical.model_dump_json().encode("utf-8")
        except VisionProposalError:
            raise
        except (ValueError, TypeError, ValidationError, RecursionError) as exc:
            raise VisionProposalError("invalid_provider_response") from exc


def build_vision_fallback_adapter() -> VisionFallbackAdapter | None:
    if (
        not settings.nutrition_label_vision_enabled
        or settings.nutrition_label_vision_kill_switch
        or settings.nutrition_label_vision_provider != "groq"
        or settings.nutrition_label_vision_data_policy != "zdr_verified"
    ):
        return None
    api_key = settings.groq_api_key.get_secret_value().strip()
    if not api_key:
        return None
    return GroqNutritionLabelVisionAdapter(
        api_key=api_key,
        endpoint=settings.nutrition_label_vision_endpoint,
        model=settings.nutrition_label_vision_model,
        proxy_url=settings.nutrition_label_vision_proxy_url,
        max_output_tokens=settings.nutrition_label_vision_max_output_tokens,
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise VisionProposalError("duplicate_key")
        result[key] = value
    return result


def _reject_non_finite(value: str) -> None:
    raise VisionProposalError("non_finite_number")


def _source_value(canonical: CanonicalDraft, field_name: str) -> Decimal | None:
    cells = getattr(canonical.source_facts, field_name)
    if cells is None or len(cells) != 1 or cells[0].evidence != "read":
        return None
    return cells[0].value


def _validate_evidence(canonical: CanonicalDraft) -> None:
    if canonical.source_basis == "ambiguous":
        raise VisionProposalError("ambiguous_basis")
    if canonical.confidence_kind != "none":
        raise VisionProposalError("unvalidated_confidence")
    if any(
        getattr(canonical.derived_fields, field_name) is not None for field_name in NUTRIENT_FIELDS
    ):
        raise VisionProposalError("derived_facts_not_allowed")
    source_columns: set[str] = set()
    for field_name in NUTRIENT_FIELDS:
        cells = getattr(canonical.source_facts, field_name)
        if cells is not None:
            source_columns.update(cell.column_ref for cell in cells)
    if len(source_columns) > 1:
        raise VisionProposalError("mixed_source_columns")

    for field_name in NUTRIENT_FIELDS:
        evidence = getattr(canonical.field_evidence, field_name)
        cells = getattr(canonical.source_facts, field_name)
        fact = getattr(canonical.normalized_facts, field_name)
        if evidence == "derived":
            raise VisionProposalError("derived_facts_not_allowed")
        if evidence == "absent":
            if cells is not None or fact is not None:
                raise VisionProposalError("source_evidence_mismatch")
            continue
        if cells is None or len(cells) != 1:
            raise VisionProposalError("source_evidence_mismatch")

        cell = cells[0]
        if cell.basis_ref != canonical.source_basis:
            raise VisionProposalError("source_basis_mismatch")
        if evidence == "read":
            if cell.evidence != "read" or cell.value is None or fact is None:
                raise VisionProposalError("source_evidence_mismatch")
            if canonical.source_basis == "per_serving" and canonical.serving_size is not None:
                serving = canonical.serving_size
                basis_ref = "per_100_g" if serving.unit == "g" else "per_100_ml"
                value = cell.value * Decimal(100) / serving.amount
            else:
                basis_ref = canonical.source_basis
                value = cell.value
            if fact.basis_ref != basis_ref or fact.value != value:
                raise VisionProposalError("normalized_fact_mismatch")
            if nutrient_value_exceeds_outlier_limit(field_name, fact.value, fact.basis_ref):
                raise VisionProposalError("nutrient_outlier")
        elif evidence in {"ambiguous", "unreadable"}:
            if cell.evidence != evidence or fact is not None:
                raise VisionProposalError("source_evidence_mismatch")
        else:
            raise VisionProposalError("invalid_field_evidence")


def validate_vision_proposal(
    response: bytes,
    *,
    provider_class: str,
    model_class: str,
    prompt_version: str,
) -> CanonicalDraft:
    if not isinstance(response, bytes) or not response or len(response) > VISION_MAX_RESPONSE_BYTES:
        raise VisionProposalError("response_size")
    try:
        payload = json.loads(
            response.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_non_finite,
        )
        canonical = validate_canonical_draft(payload)
        _validate_evidence(canonical)

        kj = _source_value(canonical, "energy_kj")
        kcal = _source_value(canonical, "energy_kcal")
        if kj is not None and kcal is not None and not energy_pair_is_consistent(kj, kcal):
            raise VisionProposalError("energy_unit_conflict")

        warnings = set(canonical.warnings)
        if warnings - VISION_ALLOWED_WARNING_CODES:
            raise VisionProposalError("unknown_warning")
        facts = canonical.normalized_facts
        energy = facts.energy_kcal
        protein = facts.protein_g
        fat = facts.fat_g
        carbohydrate = facts.carbohydrate_g
        if (
            energy is not None
            and protein is not None
            and fat is not None
            and carbohydrate is not None
            and not macro_energy_is_consistent(
                energy.value, protein.value, fat.value, carbohydrate.value
            )
        ):
            warnings.add("energy_sanity_warning")

        if not any(getattr(canonical.source_facts, name) is not None for name in NUTRIENT_FIELDS):
            raise VisionProposalError("no_source_evidence")
        if not any(getattr(canonical.field_evidence, name) == "read" for name in NUTRIENT_FIELDS):
            raise VisionProposalError("no_readable_facts")

        metadata = DraftMetadata(
            provider=provider_class,
            model=model_class,
            prompt_version=prompt_version,
            schema_version=CANONICAL_DRAFT_SCHEMA_VERSION,
            policy_revision=VISION_POLICY_REVISION,
        )
        return validate_canonical_draft(
            canonical.model_dump(
                mode="python",
                exclude={"metadata", "warnings"},
            )
            | {"metadata": metadata, "warnings": sorted(warnings)}
        )
    except VisionProposalError:
        raise
    except (UnicodeDecodeError, ValidationError, ValueError, TypeError, RecursionError) as exc:
        raise VisionProposalError("invalid_provider_response") from exc
