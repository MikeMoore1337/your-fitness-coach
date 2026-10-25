"""I3 educational draft contract: offline only, no YFC POST or publication."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from fitminiapp_api.schemas.articles import HermesWebArticleProposal
from fitminiapp_api.services.web_articles import (
    _review_blockers,
    validate_article_proposal,
)

DRAFT_FILE = Path(__file__).parent / "fixtures" / "i3_plant_recovery_editorial_draft.json"


def load_draft() -> dict:
    return json.loads(DRAFT_FILE.read_text(encoding="utf-8"))


def test_draft_matches_actual_yfc_proposal_schema() -> None:
    proposal = HermesWebArticleProposal.model_validate(load_draft())
    assert proposal.article_kind == "evidence_review"
    assert proposal.evidence_level == "limited"
    assert proposal.risk_level == "moderate"
    assert len(proposal.body_sections) >= 2
    assert len(proposal.sources) == 3
    assert {claim.claim_id for claim in proposal.claims} == {
        item.claim_id for item in proposal.claim_source_matrix
    }
    assert all(str(source.url).startswith("https://") for source in proposal.sources)


def test_every_claim_requires_real_editorial_review() -> None:
    proposal = HermesWebArticleProposal.model_validate(load_draft())
    assert all(item.review_status == "pending" for item in proposal.claim_source_matrix)
    assert all(item.support_level == "partially_supports" for item in proposal.claim_source_matrix)
    assert proposal.domain_reviewer is None
    warnings = validate_article_proposal(proposal)
    blockers = _review_blockers(proposal, warnings)
    assert "claim_source_matrix_not_fully_verified" in blockers
    assert "domain_reviewer_required" in blockers


def test_not_an_intake_request_and_not_a_publication_authorization() -> None:
    draft = load_draft()
    for prohibited_field in (
        "candidate_id",
        "request_nonce",
        "idempotency_key",
        "provenance",
        "schema_version",
        "publish",
        "publication_allowed",
        "editorial_approval",
        "expert_approval",
    ):
        assert prohibited_field not in draft
    assert draft["cta"] == {}
    assert "sports_nutrition" in draft["topics"]


@pytest.mark.parametrize(
    "change", ["missing_source", "missing_matrix", "http_source", "high_risk_no_reviewer"]
)
def test_schema_refuses_invalid_or_bypassed_draft(change: str) -> None:
    draft = copy.deepcopy(load_draft())
    if change == "missing_source":
        draft["sources"] = draft["sources"][:1]
    elif change == "missing_matrix":
        draft["claim_source_matrix"].pop()
    elif change == "http_source":
        draft["sources"][0]["url"] = "http://example.test/"
    else:
        draft["risk_level"] = "high"
    with pytest.raises(ValidationError):
        HermesWebArticleProposal.model_validate(draft)
