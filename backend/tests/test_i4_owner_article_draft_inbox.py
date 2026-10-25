"""I4: automated Hermes draft must stay private until explicit Root publication."""

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
ROOT_ID = 939_404


def _auth(client, monkeypatch) -> dict[str, str]:
    monkeypatch.setattr(settings, "admin_telegram_user_ids", str(ROOT_ID))
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": ROOT_ID, "is_admin": True},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _draft() -> str:
    """Use real draft-only Hermes lifecycle with an isolated test candidate."""
    proposal = json.loads(FIXTURE.read_text(encoding="utf-8"))
    with get_session_context() as db:
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
        request = HermesWebArticleIntakeRequest.model_validate(
            {
                "candidate_id": candidate.id,
                "idempotency_key": "i4-owner-inbox-test-001",
                "request_nonce": "i4-owner-inbox-nonce-001",
                "research_version": "i4-offline-v1",
                "article": proposal,
                "provenance": {
                    "provider": "local",
                    "model": "test-generator",
                    "prompt_version": "i4-offline-v1",
                    "skill_version": "yfc-hermes-editorial-v1",
                },
            }
        )
        accepted = accept_hermes_article_submission(
            db,
            request,
            payload_hash=hashlib.sha256(request.model_dump_json().encode()).hexdigest(),
        )
        assert accepted.article_status == "draft"
        return accepted.article_id


def test_hermes_draft_inbox_only_root_reads(client, monkeypatch) -> None:
    draft_id = _draft()
    inbox = "/api/v1/admin/articles/drafts"
    detail = f"{inbox}/{draft_id}"

    assert client.get(inbox).status_code in {401, 403}
    assert client.get(detail).status_code in {401, 403}

    ordinary = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": 939_405, "is_admin": True},
    )
    assert ordinary.status_code == 200
    headers = {"Authorization": f"Bearer {ordinary.json()['access_token']}"}
    assert client.get(inbox, headers=headers).status_code == 403
    assert client.get(detail, headers=headers).status_code == 403

    root = _auth(client, monkeypatch)
    response = client.get(inbox, headers=root)
    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["article_id"] == draft_id
    assert row["article_status"] == "draft"
    assert row["content_version"] == 1
    assert row["pending_claim_count"] == 3
    assert row["claim_count"] == 3
    assert row["source_count"] == 3
    assert "claim_source_matrix_not_fully_verified" in row["review_blockers"]
    assert "domain_reviewer_required" in row["review_blockers"]
    assert "access_token" not in json.dumps(row)

    data = client.get(detail, headers=root)
    assert data.status_code == 200, data.text
    obj = data.json()
    assert obj["content_hash"] == row["content_hash"]
    assert len(obj["sources"]) == 3
    assert len(obj["body_sections"]) == 4
    assert all(item["review_status"] == "pending" for item in obj["claim_source_matrix"])
    assert obj["domain_reviewer"] is None
    assert obj["evidence_level"] == "limited"

    # Neither listing nor detail can move state or make public URLs visible.
    with SessionLocal() as db:
        article = db.get(WebArticle, draft_id)
        assert article is not None and article.status == "draft"
        revisions = db.query(WebArticleRevision).filter(WebArticleRevision.article_id == draft_id).all()
        assert len(revisions) == 1 and revisions[0].status == "draft"
        published = db.query(AuditEvent).filter(
            AuditEvent.action == "web_article.published",
            AuditEvent.resource_id == draft_id,
        ).count()
        assert published == 0
    assert client.get(f"/api/v1/public/articles/{obj['slug']}").status_code == 404


def test_root_inbox_bounded_and_excludes_published(client, monkeypatch) -> None:
    draft_id = _draft()
    root = _auth(client, monkeypatch)
    path = "/api/v1/admin/articles/drafts"
    assert client.get(f"{path}?limit=0", headers=root).status_code == 422
    assert client.get(f"{path}?limit=1000", headers=root).status_code == 422
    assert client.get(f"{path}?offset=-1", headers=root).status_code == 422
    assert client.get(f"{path}?offset=6000", headers=root).status_code == 422
    assert client.get(f"{path}?offset=1", headers=root).json() == []
    assert client.get(f"{path}/broken", headers=root).status_code == 404
    assert client.post(path, json={}, headers=root).status_code == 405

    with get_session_context() as db:
        article = db.get(WebArticle, draft_id)
        assert article is not None
        article.status = "published"

    assert client.get(path, headers=root).json() == []
    assert client.get(f"{path}/{draft_id}", headers=root).status_code == 404
