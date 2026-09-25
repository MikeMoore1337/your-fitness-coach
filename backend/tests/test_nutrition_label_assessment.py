from __future__ import annotations

import json
from decimal import Decimal

import pytest

from fitminiapp_api.nutrition_label.contracts import NUTRIENT_FIELDS
from fitminiapp_api.nutrition_label.parser import build_draft_from_ocr
from fitminiapp_api.nutrition_label.recognition_assessment import (
    RecognitionOutcome,
    assess_recognition,
)
from fitminiapp_api.nutrition_label.vision import VisionProposalError, validate_vision_proposal


def _complete_label(*, energy: str = "250 kcal 1046 kJ", protein: str = "10 g") -> str:
    return "\n".join(
        (
            "Nutrition Facts",
            "Per 100 g",
            f"Energy {energy}",
            f"Protein {protein}",
            "Fat 5 g",
            "Carbohydrate 30 g",
        )
    )


def _proposal_payload(text: str | None = None) -> dict:
    payload = build_draft_from_ocr(text or _complete_label()).model_dump(mode="json")
    for cells in payload["source_facts"].values():
        for cell in cells or []:
            cell["column_ref"] = "main"
    return payload


def _validate_payload(payload: dict):
    return validate_vision_proposal(
        json.dumps(payload, separators=(",", ":")).encode(),
        provider_class="test_provider",
        model_class="test_model",
        prompt_version="test-prompt-v1",
    )


def test_complete_label_stays_local_and_review_is_still_required() -> None:
    assessment = assess_recognition(build_draft_from_ocr(_complete_label()))

    assert assessment.outcome == RecognitionOutcome.LOCAL_REVIEW
    assert assessment.required_facts_complete is True
    assert assessment.usable_read_fact_count >= 4
    assert assessment.has_reviewable_source_signal is True
    assert "required_facts_complete" in assessment.reasons
    assert build_draft_from_ocr(_complete_label()).requires_user_review is True


def test_no_recognized_nutrition_signal_requires_retake() -> None:
    assessment = assess_recognition(build_draft_from_ocr("blurry package text"))

    assert assessment.outcome == RecognitionOutcome.RETAKE_REQUIRED
    assert "no_nutrition_signal" in assessment.reasons
    assert "no_usable_read_facts" in assessment.reasons


def test_ambiguous_basis_and_missing_required_facts_are_bounded_candidates() -> None:
    text = "\n".join(("Nutrition Facts", "Energy 250 kcal", "Protein 10 g", "Fat 5 g"))
    assessment = assess_recognition(build_draft_from_ocr(text))

    assert assessment.outcome == RecognitionOutcome.VISION_CANDIDATE
    assert "ambiguous_basis" in assessment.reasons
    assert "required_facts_missing" in assessment.reasons


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        (_complete_label(energy="250 1046"), "energy_unit_ambiguous"),
        (_complete_label(energy="80 kcal 1046 kJ"), "energy_unit_conflict"),
        (_complete_label(energy="1100 kcal 4600 kJ"), "energy_outlier"),
        (_complete_label(protein="10 g 12 g"), "ambiguous_column"),
        (_complete_label(protein="10"), "untrusted_numeric_token"),
        (_complete_label().replace("Carbohydrate 30 g", "Carbohydrate 101 g"), "nutrient_outlier"),
    ],
)
def test_parser_warnings_are_stable_assessment_reasons(text: str, reason: str) -> None:
    assessment = assess_recognition(build_draft_from_ocr(text))

    assert reason in assessment.reasons
    assert assessment.outcome == RecognitionOutcome.VISION_CANDIDATE


def test_ocr_budget_exhaustion_with_partial_evidence_is_a_candidate() -> None:
    partial = build_draft_from_ocr(_complete_label().replace("Carbohydrate 30 g", ""))
    partial = partial.model_copy(update={"warnings": [*partial.warnings, "ocr_budget_exhausted"]})

    assessment = assess_recognition(partial)

    assert assessment.outcome == RecognitionOutcome.VISION_CANDIDATE
    assert "ocr_budget_exhausted" in assessment.reasons
    assert assessment.usable_read_fact_count >= 3


def test_non_candidate_parser_warning_on_complete_label_stays_local() -> None:
    text = _complete_label().replace("Carbohydrate 30 g", "Carbohydrate 30 g\nFiber 101 g")

    assessment = assess_recognition(build_draft_from_ocr(text))

    assert "nutrient_outlier" in assessment.reasons
    assert assessment.outcome == RecognitionOutcome.LOCAL_REVIEW


def test_unrecognized_warning_fails_closed_to_manual_review() -> None:
    canonical = build_draft_from_ocr(_complete_label()).model_copy(
        update={"warnings": ["unknown_parser_warning"]}
    )

    assert assess_recognition(canonical).outcome == RecognitionOutcome.MANUAL_REVIEW


def test_valid_proposal_is_canonical_and_keeps_user_review_required() -> None:
    result = _validate_payload(_proposal_payload())

    assert result.requires_user_review is True
    assert result.confidence_kind == "none"
    assert all(getattr(result.confidence, name) is None for name in NUTRIENT_FIELDS)
    assert result.metadata.provider == "test_provider"
    assert result.metadata.policy_revision == "nutrition-label-vision-v1"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(barcode="0000000000000"),
        lambda payload: payload.update(product_name="invented product"),
        lambda payload: payload["normalized_facts"]["protein_g"].update(value="20"),
        lambda payload: payload["confidence"].update(protein_g="0.99"),
        lambda payload: payload.update(confidence_kind="provider_native"),
    ],
)
def test_schema_valid_or_extra_provider_identity_and_values_are_rejected(mutate) -> None:
    payload = _proposal_payload()
    mutate(payload)

    with pytest.raises(VisionProposalError):
        _validate_payload(payload)


def test_provider_cannot_claim_user_corrections() -> None:
    payload = _proposal_payload()
    payload["warnings"] = ["user_corrected_fields"]

    with pytest.raises(VisionProposalError, match="unknown_warning"):
        _validate_payload(payload)


def test_provider_cannot_mix_source_columns() -> None:
    payload = _proposal_payload()
    payload["source_facts"]["protein_g"][0]["column_ref"] = "alternate"

    with pytest.raises(VisionProposalError, match="mixed_source_columns"):
        _validate_payload(payload)


def test_energy_outlier_and_inconsistent_energy_pair_are_rejected() -> None:
    outlier = _proposal_payload()
    outlier["source_facts"]["energy_kcal"][0]["value"] = "1100"
    outlier["normalized_facts"]["energy_kcal"]["value"] = "1100"
    conflict = _proposal_payload()
    conflict["source_facts"]["energy_kj"][0]["value"] = "500"
    conflict["normalized_facts"]["energy_kj"]["value"] = "500"

    for payload in (outlier, conflict):
        with pytest.raises(VisionProposalError):
            _validate_payload(payload)


def test_macro_energy_disagreement_warns_without_replacing_label_energy() -> None:
    payload = _proposal_payload()
    payload["source_facts"]["protein_g"][0]["value"] = "50"
    payload["normalized_facts"]["protein_g"]["value"] = "50"

    result = _validate_payload(payload)

    assert result.normalized_facts.energy_kcal is not None
    assert result.normalized_facts.energy_kcal.value == Decimal("250")
    assert "energy_sanity_warning" in result.warnings


def test_malformed_duplicate_and_oversized_responses_fail_closed() -> None:
    valid = json.dumps(_proposal_payload()).encode()
    malformed = b"not json"
    duplicate = b'{"schema_version":"one","schema_version":"two"}'
    oversized = b" " * (65_536 + 1)

    for response in (malformed, duplicate, oversized):
        with pytest.raises(VisionProposalError):
            validate_vision_proposal(
                response,
                provider_class="test_provider",
                model_class="test_model",
                prompt_version="test-prompt-v1",
            )

    assert valid
