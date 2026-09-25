from __future__ import annotations

import json
from decimal import Decimal
from typing import Protocol

from pydantic import ValidationError

from fitminiapp_api.nutrition_label.contracts import (
    CANONICAL_DRAFT_SCHEMA_VERSION,
    NUTRIENT_FIELDS,
    CanonicalDraft,
    DraftMetadata,
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
