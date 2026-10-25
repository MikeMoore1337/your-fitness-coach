"""Root owner can release an educational article without fabricated scientific signoff."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fitminiapp_api.core.config import settings
from fitminiapp_api.db.session import SessionLocal, get_session_context
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.news import WebArticle, WebArticleRevision
from fitminiapp_api.schemas.articles import HermesWebArticleIntakeRequest
from fitminiapp_api.services.web_articles import (
    ArticleCandidateSignals,
    accept_hermes_article_submission,
    create_article_candidate,
)

FIXTURE = Path(__file__).parent / "fixtures" / "i3_plant_recovery_editorial_draft.json"
OWNER_ID = 930_081


def _proposal() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _root(client, monkeypatch) -> dict[str, str]:
    monkeypatch.setattr(settings, "admin_telegram_user_ids", str(OWNER_ID))
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": OWNER_ID, "is_admin": True},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _body(*, acknowledge: bool = True) -> dict:
    return {
        "article": _proposal(),
        "acknowledge_unverified_evidence": acknowledge,
        "generated_with_ai": True,
    }


def test_owner_direct_publish_preserves_unverified_claims(client, monkeypatch) -> None:
    headers = _root(client, monkeypatch)
    monkeypatch.setattr(settings, "hermes_intake_enabled", False)
    path = "/api/v1/admin/articles/publish"
    assert client.post(path, json=_body()).status_code in {401, 403}
    public = client.post(path, json=_body(), headers=headers)
    assert public.status_code == 200, public.text
    result = public.json()
    assert result["article_status"] == "published"
    assert result["scientific_verification"] == "not_attested"
    assert result["editorial_decision"] == "root_owner_publication"
    assert result["canonical_url"].endswith(f"/articles/{_proposal()['slug']}")

    replay = client.post(path, json=_body(), headers=headers)
    assert replay.status_code == 200
    assert replay.json()["article_id"] == result["article_id"]
    assert replay.json()["content_version"] == 1

    with SessionLocal() as db:
        article = db.get(WebArticle, result["article_id"])
        assert article is not None
        assert article.status == "published"
        assert article.candidate_id is None
        assert all(entry["review_status"] == "pending" for entry in article.claim_source_matrix)
        assert article.domain_reviewer is None
        assert article.evidence_level == "limited"
        revision = (
            db.query(WebArticleRevision).filter(WebArticleRevision.article_id == article.id).one()
        )
        assert revision.status == "published"
        assert revision.snapshot["metadata"]["independent_scientific_review"] == "not_attested"
        events = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.action == "web_article.published",
                AuditEvent.resource_id == article.id,
            )
            .all()
        )
        assert len(events) == 1
        assert events[0].details["editorial_decision"] == "root_owner_publication"
        assert events[0].actor_user_id is not None

    article_api = client.get(f"/api/v1/public/articles/{_proposal()['slug']}")
    assert article_api.status_code == 200, article_api.text
    assert article_api.json()["evidence_level"] == "limited"
    assert all(
        item["review_status"] == "pending" for item in article_api.json()["claim_source_matrix"]
    )
    assert _proposal()["slug"] in client.get("/sitemap.xml").text


def test_only_verified_root_may_direct_publish(client, monkeypatch) -> None:
    path = "/api/v1/admin/articles/publish"
    ordinary_login = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": 930_082, "is_admin": True},
    )
    assert ordinary_login.status_code == 200
    ordinary_headers = {"Authorization": f"Bearer {ordinary_login.json()['access_token']}"}
    assert client.post(path, json=_body(), headers=ordinary_headers).status_code == 403
    assert (
        client.post(
            path, json=_body(acknowledge=False), headers=_root(client, monkeypatch)
        ).status_code
        == 422
    )


def test_blocked_claims_not_silently_approved(client, monkeypatch) -> None:
    root = _root(client, monkeypatch)
    article = _proposal()
    article["claim_source_matrix"][0]["review_status"] = "blocked"
    response = client.post(
        "/api/v1/admin/articles/publish",
        json={
            "article": article,
            "acknowledge_unverified_evidence": True,
        },
        headers=root,
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "claim_source_explicitly_blocked"


def test_owner_can_release_same_exact_hermes_draft(client, monkeypatch) -> None:
    with get_session_context() as db:
        proposal = _proposal()
        candidate = create_article_candidate(
            db,
            source_kind="manual",
            working_title=proposal["title"],
            primary_topic="sports_nutrition",
            topics=proposal["topics"],
            article_kind=proposal["article_kind"],
            search_intent=proposal["search_intent"],
            primary_query=proposal["primary_query"],
            secondary_queries=proposal["secondary_queries"],
            audience="general",
            risk_level=proposal["risk_level"],
            evidence_level=proposal["evidence_level"],
            signals=ArticleCandidateSignals(),
        )
        payload = HermesWebArticleIntakeRequest.model_validate(
            {
                "candidate_id": candidate.id,
                "idempotency_key": "owner-i3-draft-intake-001",
                "request_nonce": "owner-i3-draft-nonce-001",
                "research_version": "i3-offline",
                "article": proposal,
                "provenance": {
                    "provider": "local",
                    "model": "test-model",
                    "prompt_version": "i3-test",
                    "skill_version": "yfc-hermes-editorial-v1",
                },
            }
        )
        accepted = accept_hermes_article_submission(
            db,
            payload,
            payload_hash=hashlib.sha256(payload.model_dump_json().encode()).hexdigest(),
        )
    assert accepted.article_status == "draft"

    response = client.post(
        "/api/v1/admin/articles/publish",
        json=_body(),
        headers=_root(client, monkeypatch),
    )
    assert response.status_code == 200, response.text
    assert response.json()["article_id"] == accepted.article_id
    with SessionLocal() as db:
        article = db.get(WebArticle, accepted.article_id)
        assert article is not None
        assert article.status == "published"
        assert article.content_version == 1


def test_changed_existing_slug_does_not_overwrite_article(client, monkeypatch) -> None:
    root = _root(client, monkeypatch)
    first = client.post("/api/v1/admin/articles/publish", json=_body(), headers=root)
    assert first.status_code == 200
    changed = _body()
    changed["article"]["title"] += " обновлено"
    response = client.post(
        "/api/v1/admin/articles/publish",
        json=changed,
        headers=root,
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "slug_conflict"
