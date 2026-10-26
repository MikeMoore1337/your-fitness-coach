"""I3 article handoff through the actual FastAPI route, isolated test DB only.

No network request to production, no promotion of human-review status.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from pydantic import SecretStr

from fitminiapp_api.core.config import settings
from fitminiapp_api.db.session import SessionLocal
from fitminiapp_api.models.news import WebArticle, WebArticleCandidate
from fitminiapp_api.schemas.articles import HermesWebArticleIntakeRequest
from fitminiapp_api.services.news_hermes import hermes_signature
from fitminiapp_api.services.web_articles import (
    ArticleCandidateSignals,
    WebArticleError,
    create_article_candidate,
    publish_web_article,
    _i4_candidate_receipt,
)

ARTICLE_FIXTURE = Path(__file__).parent / "fixtures" / "i3_plant_recovery_editorial_draft.json"
TEST_KEY_ID = "hermes-i3-tests"
TEST_SECRET = "synthetic-hermes-intake-secret-for-local-tests-only"


def _candidate_id() -> str:
    with SessionLocal() as db:
        candidate = create_article_candidate(
            db,
            source_kind="manual",
            working_title="Болезненность после тренировки: научный обзор",
            primary_topic="sports_nutrition",
            topics=["sports_nutrition", "mobility_recovery_sleep"],
            article_kind="evidence_review",
            search_intent="evidence",
            primary_query="растительные продукты и мышечная болезненность",
            secondary_queries=[],
            audience="general",
            risk_level="moderate",
            evidence_level="limited",
            signals=ArticleCandidateSignals(),
        )
        db.commit()
        return candidate.id


def _request(candidate_id: str) -> HermesWebArticleIntakeRequest:
    proposal = json.loads(ARTICLE_FIXTURE.read_text(encoding="utf-8"))
    return HermesWebArticleIntakeRequest.model_validate(
        {
            "idempotency_key": "i3-plant-editorial-test-key-001",
            "request_nonce": "i3-plant-editorial-test-nonce-001",
            "candidate_id": candidate_id,
            "research_version": "i3-reviewed-20261025",
            "article": proposal,
            "provenance": {
                "provider": "local",
                "model": "hermes-offline-test",
                "prompt_version": "i3-editorial-review-v1",
                "skill_version": "yfc-hermes-editorial-v1",
            },
        }
    )


def _headers(body: bytes, *, nonce: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    return {
        "X-Hermes-Key-Id": TEST_KEY_ID,
        "X-Hermes-Timestamp": timestamp,
        "X-Hermes-Nonce": nonce,
        "X-Hermes-Signature": hermes_signature(
            TEST_SECRET, timestamp=timestamp, nonce=nonce, body=body
        ),
    }


def test_real_route_accepts_i3_draft_but_never_publishes(client, monkeypatch) -> None:
    """Exercise HMAC -> Pydantic -> DB -> review blockers -> replay -> public route."""
    monkeypatch.setattr(settings, "hermes_intake_enabled", True)
    monkeypatch.setattr(settings, "hermes_intake_key_id", TEST_KEY_ID)
    monkeypatch.setattr(settings, "hermes_intake_shared_secret", SecretStr(TEST_SECRET))

    payload = _request(_candidate_id())
    body = payload.model_dump_json().encode("utf-8")
    headers = _headers(body, nonce=payload.request_nonce)

    rejected = client.post(
        "/api/v1/hermes/articles/intake",
        content=body,
        headers={**headers, "X-Hermes-Signature": "0" * 64},
    )
    assert rejected.status_code == 403

    first = client.post("/api/v1/hermes/articles/intake", content=body, headers=headers)
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["status"] == "accepted"
    assert result["article_status"] == "draft"
    assert "claim_source_matrix_not_fully_verified" in result["review_blockers"]
    assert "domain_reviewer_required" in result["review_blockers"]

    second = client.post("/api/v1/hermes/articles/intake", content=body, headers=headers)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "duplicate"
    assert second.json()["article_id"] == result["article_id"]

    with SessionLocal() as db:
        article = db.get(WebArticle, result["article_id"])
        assert article is not None
        assert article.status == "draft"
        with pytest.raises(WebArticleError, match="article_not_approved"):
            publish_web_article(db, article, actor_ref="synthetic-test")
        article.status = "approved"
        with pytest.raises(WebArticleError, match="claim_source_review_incomplete"):
            publish_web_article(db, article, actor_ref="synthetic-test")

    slug = payload.article.slug
    public = client.get(f"/api/v1/public/articles/{slug}")
    assert public.status_code == 404


def _i4_signed_request():
    req = _request("0" * 32)
    cid, ref = _i4_candidate_receipt(req.article)
    return req.model_copy(update={
        "candidate_id": cid, "research_version": "i4-reviewed-v1",
        "idempotency_key": "i4-auto-test-unique-idempotency-20261026",
        "request_nonce": "i4-auto-test-unique-nonce-20261026",
    }), ref


def _i4_auth(monkeypatch):
    monkeypatch.setattr(settings, "hermes_intake_enabled", True)
    monkeypatch.setattr(settings, "hermes_intake_key_id", TEST_KEY_ID)
    monkeypatch.setattr(settings, "hermes_intake_shared_secret", SecretStr(TEST_SECRET))


def _i4_post(client, req):
    body = req.model_dump_json().encode("utf-8")
    return client.post("/api/v1/hermes/articles/intake", content=body,
                       headers=_headers(body, nonce=req.request_nonce))


def test_i4_signed_new_candidate_provisioning_and_no_publication(client, monkeypatch):
    _i4_auth(monkeypatch)
    req, ref = _i4_signed_request()
    body = req.model_dump_json().encode("utf-8")
    headers = _headers(body, nonce=req.request_nonce)
    invalid = client.post("/api/v1/hermes/articles/intake", content=body,
                          headers={**headers, "X-Hermes-Signature": "0" * 64})
    assert invalid.status_code == 403
    with SessionLocal() as db:
        assert db.get(WebArticleCandidate, req.candidate_id) is None
    first = _i4_post(client, req)
    assert first.status_code == 200, first.text
    answer = first.json()
    assert answer["status"] == "accepted"
    assert answer["article_status"] == "draft"
    with SessionLocal() as db:
        candidate = db.get(WebArticleCandidate, req.candidate_id)
        article = db.get(WebArticle, answer["article_id"])
        assert candidate is not None and article is not None
        assert candidate.source_ref == ref
        assert candidate.source_kind == "news_handoff"
        assert candidate.status == article.status == "draft"
        assert all(row["review_status"] == "pending" for row in article.claim_source_matrix)
    second = _i4_post(client, req)
    assert second.status_code == 200 and second.json()["status"] == "duplicate"
    assert second.json()["article_id"] == answer["article_id"]
    assert client.get(f"/api/v1/public/articles/{req.article.slug}").status_code == 404


def test_i4_reject_unknown_candidate_forged_claim_and_unsafe_source(client, monkeypatch):
    _i4_auth(monkeypatch)
    req, ref = _i4_signed_request()
    bad = req.model_copy(update={"candidate_id": "f" * 32})
    res = _i4_post(client, bad)
    assert res.status_code == 422 and res.json()["detail"] == "candidate_missing"
    proposal = req.article.model_copy(deep=True)
    proposal.claim_source_matrix[0].review_status = "verified"
    forged = req.model_copy(update={"candidate_id": _candidate_id(),
                                    "article": proposal})
    res = _i4_post(client, forged)
    assert res.status_code == 422
    assert res.json()["detail"] == "hermes_review_attestation_forbidden"
    untrusted = req.article.model_copy(deep=True)
    untrusted.sources[0].url = "https://untrusted.invalid/article"
    bad = req.model_copy(update={"candidate_id": "e" * 32, "article": untrusted})
    res = _i4_post(client, bad)
    assert res.status_code == 422
    assert res.json()["detail"] == "hermes_source_untrusted"
    with SessionLocal() as db:
        assert db.get(WebArticleCandidate, req.candidate_id) is None


def test_i4_signed_replay_with_new_nonce_cannot_overwrite_slug(client, monkeypatch):
    _i4_auth(monkeypatch)
    req, ref = _i4_signed_request()
    original = _i4_post(client, req)
    assert original.status_code == 200, original.text
    second = req.model_copy(update={
        "idempotency_key": "i4-second-idempotency-key-20261026",
        "request_nonce": "i4-second-nonce-for-same-slug-20261026",
    })
    denied = _i4_post(client, second)
    assert denied.status_code == 409 and denied.json()["detail"] == "slug_conflict"
    with SessionLocal() as db:
        original_article = db.get(WebArticle, original.json()["article_id"])
        assert original_article is not None
        assert original_article.status == "draft"
        assert original_article.content_version == 1
