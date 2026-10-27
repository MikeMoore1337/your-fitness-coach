from __future__ import annotations

import hashlib
import time

import pytest
from pydantic import SecretStr, ValidationError

from fitminiapp_api.core.config import settings
from fitminiapp_api.db.session import SessionLocal
from fitminiapp_api.models.news import WebArticle, WebArticleRevision
from fitminiapp_api.schemas.articles import ArticleSource, HermesWebArticleIntakeRequest
from fitminiapp_api.services.news_hermes import hermes_signature
from fitminiapp_api.services.web_articles import (
    ArticleCandidateSignals,
    WebArticleError,
    accept_hermes_article_submission,
    archive_web_article,
    create_article_candidate,
    mark_article_update_required,
    publish_web_article,
    retract_web_article,
    score_article_candidate,
)


def _payload(candidate_id: str, *, risk_level: str = "low") -> HermesWebArticleIntakeRequest:
    return HermesWebArticleIntakeRequest.model_validate(
        {
            "idempotency_key": "article-idempotency-001",
            "request_nonce": "article-request-nonce-001",
            "candidate_id": candidate_id,
            "research_version": "research-v1",
            "article": {
                "slug": "kak-nachat-silovye-trenirovki",
                "title": "Как начать силовые тренировки и не потерять контекст",
                "description": "Понятный старт силовых тренировок: план, факты и ограничения.",
                "lead": "Для старта силовых тренировок важнее повторяемый план и запись фактов, чем сложная программа. Начните с посильной нагрузки и меняйте её только после наблюдения за несколькими занятиями.",
                "body_sections": [
                    {
                        "heading": "С чего начать",
                        "paragraphs": [
                            "Выберите несколько базовых движений и заранее определите дни занятий. Первые недели нужны, чтобы понять технику, восстановление и то, какие записи вы действительно ведёте.",
                        ],
                        "points": [
                            "Планируйте посильную нагрузку",
                            "Записывайте выполненные подходы",
                        ],
                    },
                    {
                        "heading": "Что отслеживать",
                        "paragraphs": [
                            "Смотрите на выполненные подходы, повторения и рабочий вес в контексте всей недели. Одно занятие не показывает устойчивую динамику.",
                        ],
                    },
                ],
                "topics": ["training", "strength_hypertrophy"],
                "article_kind": "evergreen_explainer",
                "search_intent": "informational",
                "primary_query": "как начать силовые тренировки",
                "secondary_queries": ["план силовых тренировок для начинающих"],
                "risk_level": risk_level,
                "evidence_level": "moderate",
                "claims": [
                    {
                        "claim_id": "claim-plan",
                        "claim_text": "Повторяемый план помогает сравнивать фактические записи.",
                        "normalized_claim": "repeatable plan supports comparison of recorded facts",
                    }
                ],
                "sources": [
                    {
                        "source_id": "source-guideline",
                        "title": "Physical activity guidance",
                        "publisher": "World Health Organization",
                        "url": "https://www.who.int/news-room/fact-sheets/detail/physical-activity",
                        "source_type": "official_organization",
                        "limitations": "Общие рекомендации не заменяют индивидуальную оценку.",
                    },
                    {
                        "source_id": "source-review",
                        "title": "Resistance training review",
                        "publisher": "PubMed",
                        "url": "https://pubmed.ncbi.nlm.nih.gov/00000001/",
                        "source_type": "systematic_review",
                        "limitations": "Выводы зависят от популяции и протокола.",
                    },
                ],
                "claim_source_matrix": [
                    {
                        "claim_id": "claim-plan",
                        "source_ids": ["source-guideline", "source-review"],
                        "support_level": "supports",
                        "limitations": "Источники не определяют индивидуальную программу.",
                        "review_status": "pending",
                    }
                ],
                "author": {"name": "Your Fitness Coach", "type": "Organization"},
                "editor": {"name": "YFC Editorial Desk", "type": "Organization"},
                "related_slugs": [],
                "cta": {
                    "destination": "web",
                    "label": "Открыть Your Fitness Coach",
                    "description": "Сохраняйте план и фактические результаты в одном месте.",
                },
                "evergreen_score": 82,
                "product_relevance": 75,
                "editorial_value": 88,
                "web_article_potential_reasons": ["evergreen_gap"],
            },
            "provenance": {
                "provider": "local",
                "model": "hermes-mock",
                "prompt_version": "web-article-v1",
                "skill_version": "yfc-hermes-editorial-v1",
            },
        }
    )


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _candidate(db) -> str:
    candidate = create_article_candidate(
        db,
        source_kind="manual",
        working_title="Как начать силовые тренировки",
        primary_topic="training",
        topics=["training", "strength_hypertrophy"],
        article_kind="evergreen_explainer",
        search_intent="informational",
        primary_query="как начать силовые тренировки",
        secondary_queries=[],
        audience="general",
        risk_level="low",
        evidence_level="moderate",
        signals=ArticleCandidateSignals(
            search_demand=80,
            intent_clarity=90,
            topical_relevance=90,
            product_relevance=70,
            audience_usefulness=85,
            evergreen_potential=90,
            evidence_availability=80,
            existing_content_overlap=10,
            internal_link_potential=70,
            risk_review_cost=10,
            freshness_need=20,
            news_opportunity=25,
        ),
    )
    return candidate.id


def test_candidate_score_keeps_opportunity_separate_from_approval() -> None:
    result = score_article_candidate(
        ArticleCandidateSignals(search_demand=100, risk_review_cost=100)
    )
    assert result["score"] < 60
    assert "risk_review_cost_requires_manual_path" in result["reasons"]


def _simulate_explicit_human_claim_review(article: WebArticle) -> None:
    """Test-only human approval, never part of Hermes HMAC ingestion."""
    article.claim_source_matrix = [
        {**row, "review_status": "verified"} for row in article.claim_source_matrix
    ]


def test_hermes_article_intake_is_idempotent_and_creates_draft(db_session) -> None:
    candidate_id = _candidate(db_session)
    payload = _payload(candidate_id)
    payload_hash = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()

    first = accept_hermes_article_submission(db_session, payload, payload_hash=payload_hash)
    second = accept_hermes_article_submission(db_session, payload, payload_hash=payload_hash)

    assert first.status == "accepted"
    assert first.article_status == "draft"
    assert second.status == "duplicate"
    assert second.article_id == first.article_id
    assert db_session.query(WebArticle).count() == 1
    assert db_session.query(WebArticleRevision).count() == 1


def test_sensitive_article_requires_domain_reviewer() -> None:
    with pytest.raises(ValidationError, match="domain_reviewer"):
        _payload("a" * 32, risk_level="high")


def test_article_sources_require_https() -> None:
    with pytest.raises(ValidationError, match="must use HTTPS"):
        ArticleSource.model_validate(
            {
                "source_id": "source-one",
                "title": "Source",
                "publisher": "Publisher",
                "url": "http://example.com/source",
                "source_type": "official_organization",
            }
        )


def test_signed_hermes_article_intake_is_idempotent_and_never_publishes(
    client, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "hermes_intake_enabled", True)
    monkeypatch.setattr(settings, "hermes_intake_key_id", "hermes-test")
    monkeypatch.setattr(
        settings,
        "hermes_intake_shared_secret",
        SecretStr("test-hermes-shared-secret-that-is-long-enough"),
    )
    with SessionLocal() as db:
        candidate_id = _candidate(db)
        db.commit()

    payload = _payload(candidate_id)
    body = payload.model_dump_json().encode()
    timestamp = str(int(time.time()))
    nonce = "article-request-nonce-001"
    headers = {
        "X-Hermes-Key-Id": "hermes-test",
        "X-Hermes-Timestamp": timestamp,
        "X-Hermes-Nonce": nonce,
        "X-Hermes-Signature": hermes_signature(
            "test-hermes-shared-secret-that-is-long-enough",
            timestamp=timestamp,
            nonce=nonce,
            body=body,
        ),
    }

    first = client.post("/api/v1/hermes/articles/intake", content=body, headers=headers)
    second = client.post("/api/v1/hermes/articles/intake", content=body, headers=headers)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["status"] == "accepted"
    assert second.json()["status"] == "duplicate"
    assert first.json()["article_status"] == "draft"
    assert first.json()["article_id"] == second.json()["article_id"]

    mismatch_nonce = "article-request-nonce-other"
    mismatch_headers = {
        **headers,
        "X-Hermes-Nonce": mismatch_nonce,
        "X-Hermes-Signature": hermes_signature(
            "test-hermes-shared-secret-that-is-long-enough",
            timestamp=timestamp,
            nonce=mismatch_nonce,
            body=body,
        ),
    }
    mismatch = client.post("/api/v1/hermes/articles/intake", content=body, headers=mismatch_headers)
    assert mismatch.status_code == 422
    assert mismatch.json()["detail"] == "nonce_mismatch"

    with SessionLocal() as db:
        article = db.get(WebArticle, first.json()["article_id"])
        assert article is not None
        assert article.status == "draft"


def test_hermes_article_intake_enforces_shared_source_limit(db_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "hermes_intake_max_source_count", 1)
    candidate_id = _candidate(db_session)
    payload = _payload(candidate_id)
    payload_hash = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()

    with pytest.raises(WebArticleError, match="source_count_exceeded"):
        accept_hermes_article_submission(db_session, payload, payload_hash=payload_hash)


def test_publish_requires_approval_and_update_preserves_revision(db_session) -> None:
    candidate_id = _candidate(db_session)
    payload = _payload(candidate_id)
    payload_hash = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
    result = accept_hermes_article_submission(db_session, payload, payload_hash=payload_hash)
    article = db_session.get(WebArticle, result.article_id)
    assert article is not None

    with pytest.raises(WebArticleError, match="article_not_approved"):
        publish_web_article(db_session, article, actor_ref="owner")

    _simulate_explicit_human_claim_review(article)
    article.status = "approved"
    publish_web_article(db_session, article, actor_ref="owner")
    assert article.status == "published"
    assert article.published_at is not None
    published_at = article.published_at

    revision_id = db_session.query(WebArticleRevision.id).scalar()
    mark_article_update_required(db_session, article, reason="Источник обновился")
    assert article.status == "update_required"
    assert db_session.query(WebArticleRevision.id).scalar() == revision_id

    updated_proposal = payload.article.model_copy(
        update={
            "title": "Как начать силовые тренировки: обновлённый разбор",
            "lead": "Обновлённый разбор сохраняет прежний intent и canonical URL, но проходит новый review.",
        }
    )
    update_payload = payload.model_copy(
        update={
            "idempotency_key": "article-idempotency-update-001",
            "request_nonce": "article-request-nonce-update-001",
            "research_version": "research-v2",
            "article": updated_proposal,
        }
    )
    update_hash = hashlib.sha256(update_payload.model_dump_json().encode()).hexdigest()
    update_result = accept_hermes_article_submission(
        db_session, update_payload, payload_hash=update_hash
    )

    assert update_result.status == "accepted"
    assert update_result.article_id == article.id
    assert update_result.content_version == 2
    assert article.status == "draft"
    assert article.slug == payload.article.slug
    assert article.canonical_url == (
        f"{settings.frontend_base_url.rstrip('/')}/articles/kak-nachat-silovye-trenirovki"
    )
    assert article.published_at == published_at
    assert db_session.query(WebArticleRevision).count() == 2
    old_revision = db_session.get(WebArticleRevision, revision_id)
    assert old_revision is not None
    assert old_revision.status == "published"
    assert old_revision.snapshot["title"] == payload.article.title

    _simulate_explicit_human_claim_review(article)
    article.status = "approved"
    publish_web_article(db_session, article, actor_ref="owner")
    assert article.status == "published"
    assert article.content_version == 2
    assert article.updated_at is not None


def test_archive_and_retract_preserve_article_history(db_session) -> None:
    candidate_id = _candidate(db_session)
    payload = _payload(candidate_id)
    payload_hash = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
    result = accept_hermes_article_submission(db_session, payload, payload_hash=payload_hash)
    article = db_session.get(WebArticle, result.article_id)
    assert article is not None
    _simulate_explicit_human_claim_review(article)
    article.status = "approved"
    publish_web_article(db_session, article, actor_ref="owner")

    archive_web_article(db_session, article, reason="Intent устарел", actor_ref="editor")
    assert article.status == "archived"
    assert article.correction_reason == "Intent устарел"
    assert db_session.query(WebArticleRevision).count() == 1

    retract_web_article(
        db_session, article, reason="Обнаружена фактическая ошибка", actor_ref="owner"
    )
    assert article.status == "retracted"
    assert article.correction_reason == "Обнаружена фактическая ошибка"
    assert db_session.query(WebArticleRevision).count() == 1
