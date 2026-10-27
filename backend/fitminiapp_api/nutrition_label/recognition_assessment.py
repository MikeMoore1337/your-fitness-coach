from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from fitminiapp_api.nutrition_label.contracts import NUTRIENT_FIELDS, CanonicalDraft
from fitminiapp_api.nutrition_label.parser import PARSER_WARNING_CODES, REQUIRED_NUTRIENT_FIELDS

OCR_BUDGET_EXHAUSTED_WARNING = "ocr_budget_exhausted"
_VISION_CANDIDATE_WARNINGS = frozenset(
    {
        "ambiguous_basis",
        "serving_size_required_for_normalization",
        "missing_required_fact",
        "energy_unit_ambiguous",
        "ambiguous_column",
        "untrusted_numeric_token",
        "energy_outlier",
        "nutrient_outlier",
        "energy_unit_conflict",
        "energy_sanity_warning",
        "unreadable_field",
        OCR_BUDGET_EXHAUSTED_WARNING,
    }
)


class RecognitionOutcome(StrEnum):
    LOCAL_REVIEW = "local_review"
    VISION_CANDIDATE = "vision_candidate"
    RETAKE_REQUIRED = "retake_required"
    MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True)
class RecognitionAssessment:
    outcome: RecognitionOutcome
    reasons: tuple[str, ...]
    usable_read_fact_count: int
    has_reviewable_source_signal: bool
    required_facts_complete: bool

    def with_outcome(self, outcome: RecognitionOutcome, reason: str) -> RecognitionAssessment:
        return RecognitionAssessment(
            outcome=outcome,
            reasons=(*self.reasons, reason) if reason not in self.reasons else self.reasons,
            usable_read_fact_count=self.usable_read_fact_count,
            has_reviewable_source_signal=self.has_reviewable_source_signal,
            required_facts_complete=self.required_facts_complete,
        )


def usable_read_fact_count(canonical: CanonicalDraft) -> int:
    return sum(
        getattr(canonical.field_evidence, field_name) == "read" for field_name in NUTRIENT_FIELDS
    )


def has_reviewable_source_signal(canonical: CanonicalDraft) -> bool:
    return any(
        getattr(canonical.source_facts, field_name) is not None for field_name in NUTRIENT_FIELDS
    )


def assess_recognition(canonical: CanonicalDraft) -> RecognitionAssessment:
    read_count = usable_read_fact_count(canonical)
    has_signal = has_reviewable_source_signal(canonical)
    required_complete = all(
        getattr(canonical.normalized_facts, field_name) is not None
        for field_name in REQUIRED_NUTRIENT_FIELDS
    )
    reasons: list[str] = [
        "required_facts_complete" if required_complete else "required_facts_missing",
        "reviewable_source_signal" if has_signal else "no_nutrition_signal",
        "usable_read_facts_present" if read_count else "no_usable_read_facts",
    ]

    evidence_states = {
        getattr(canonical.field_evidence, field_name) for field_name in NUTRIENT_FIELDS
    }
    for state in ("read", "ambiguous", "unreadable"):
        if state in evidence_states:
            reasons.append(f"source_facts_{state}")

    reasons.extend(canonical.warnings)
    unknown_warnings = (
        set(canonical.warnings) - set(PARSER_WARNING_CODES) - {OCR_BUDGET_EXHAUSTED_WARNING}
    )
    vision_reasons = set(canonical.warnings) & _VISION_CANDIDATE_WARNINGS

    if not has_signal and read_count == 0:
        outcome = RecognitionOutcome.RETAKE_REQUIRED
    elif unknown_warnings:
        outcome = RecognitionOutcome.MANUAL_REVIEW
    elif not required_complete and vision_reasons:
        outcome = RecognitionOutcome.VISION_CANDIDATE
    elif required_complete:
        outcome = RecognitionOutcome.LOCAL_REVIEW
    else:
        outcome = RecognitionOutcome.MANUAL_REVIEW

    return RecognitionAssessment(
        outcome=outcome,
        reasons=tuple(dict.fromkeys(reasons)),
        usable_read_fact_count=read_count,
        has_reviewable_source_signal=has_signal,
        required_facts_complete=required_complete,
    )
