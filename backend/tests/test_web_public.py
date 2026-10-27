from __future__ import annotations

from datetime import datetime
from xml.etree import ElementTree

import pytest

from fitminiapp_api.core.config import settings
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.news import WebArticle, WebArticleRevision


def _published_article() -> WebArticle:
    return WebArticle(
        id="a" * 32,
        slug="strength-basics",
        status="published",
        title="Основы силовых тренировок без лишней сложности",
        description="Как начать силовые тренировки: план, записи и честные ограничения.",
        lead="Для старта силовых тренировок достаточно посильного плана и записи фактов. Смотрите на несколько занятий в контексте недели, а не на одну цифру.",
        body_sections=[
            {
                "heading": "Начните с повторяемого плана",
                "paragraphs": [
                    "Выберите посильные движения и заранее определите дни занятий. Так проще заметить, что меняется на практике.",
                ],
                "points": [
                    "Записывайте выполненные подходы",
                    "Оставляйте место для восстановления",
                ],
            },
            {
                "heading": "Читайте записи в контексте",
                "paragraphs": [
                    "Одно занятие не показывает устойчивую динамику. Сверяйте план и факт по нескольким тренировкам.",
                ],
                "points": [],
            },
        ],
        topics=["training", "strength_hypertrophy"],
        article_kind="evergreen_explainer",
        search_intent="informational",
        primary_query="как начать силовые тренировки",
        secondary_queries=["план силовых тренировок"],
        risk_level="low",
        evidence_level="moderate",
        claims=[
            {
                "claim_id": "plan-context",
                "claim_text": "Повторяемый план помогает сравнивать записи.",
                "normalized_claim": "repeatable plan supports comparison",
            }
        ],
        sources=[
            {
                "source_id": "who-activity",
                "title": "Physical activity",
                "publisher": "World Health Organization",
                "url": "https://www.who.int/news-room/fact-sheets/detail/physical-activity",
                "source_type": "official_organization",
                "published_at": None,
                "limitations": "Общие рекомендации.",
            }
        ],
        claim_source_matrix=[
            {
                "claim_id": "plan-context",
                "source_ids": ["who-activity"],
                "support_level": "supports",
                "limitations": "Источник не задаёт индивидуальную программу.",
                "review_status": "verified",
            }
        ],
        author={"name": "Your Fitness Coach", "type": "Organization"},
        editor={"name": "YFC Editorial Desk", "type": "Organization"},
        domain_reviewer=None,
        canonical_url="https://your-fitness-coach.ru/articles/strength-basics",
        related_slugs=[],
        cta={
            "destination": "web",
            "label": "Открыть Your Fitness Coach",
            "description": "Сохраняйте план и фактические результаты.",
        },
        evergreen_score=80,
        product_relevance=75,
        editorial_value=85,
        web_article_potential_reasons=["evergreen_gap"],
        content_version=1,
        research_version="research-v1",
        provider="local",
        model="fixture",
        prompt_version="web-article-v1",
        skill_version="yfc-hermes-editorial-v1",
        schema_version="yfc-web-article-v1",
        generated_with_ai=True,
        research_assistance=True,
        content_hash="b" * 64,
        published_at=datetime(2026, 9, 1, 10, 0),
        updated_at=datetime(2026, 9, 2, 10, 0),
    )


def test_articles_routes_render_published_content_and_metadata(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "landing_domain", "your-fitness-coach.ru")
    with get_session_context() as db:
        article = _published_article()
        db.add(article)
        db.add(
            WebArticleRevision(
                id="c" * 32,
                article_id=article.id,
                content_version=1,
                status="published",
                snapshot={"title": article.title},
            )
        )

    index = client.get("/articles", headers={"Host": "your-fitness-coach.ru"})
    detail = client.get("/articles/strength-basics", headers={"Host": "your-fitness-coach.ru"})
    assert index.status_code == 200
    assert detail.status_code == 200
    assert index.headers["x-robots-tag"] == "index, follow"
    assert "strength-basics" in index.text
    detail_html = detail.content.decode("utf-8")
    assert "Основы силовых тренировок без лишней сложности" in detail_html
    assert '<meta property="og:type" content="article" />' in detail_html
    assert (
        '<link rel="canonical" href="https://your-fitness-coach.ru/articles/strength-basics" />'
        in detail_html
    )
    assert '"datePublished":"2026-09-01"' in detail_html
    assert "Выберите посильные движения" in detail_html

    sitemap = client.get("/sitemap.xml", headers={"Host": "your-fitness-coach.ru"})
    root = ElementTree.fromstring(sitemap.content)
    locs = [
        element.text
        for element in root.findall(
            "{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
        )
    ]
    assert "https://your-fitness-coach.ru/articles/strength-basics" in locs


def test_draft_article_is_not_public_or_in_sitemap(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "landing_domain", "your-fitness-coach.ru")
    with get_session_context() as db:
        draft = _published_article()
        draft.id = "d" * 32
        draft.slug = "internal-draft"
        draft.status = "review"
        draft.canonical_url = "https://your-fitness-coach.ru/articles/internal-draft"
        db.add(draft)

    assert client.get("/articles/internal-draft").status_code == 404
    assert "internal-draft" not in client.get("/sitemap.xml").text


@pytest.mark.parametrize("status", ["archived", "retracted"])
def test_removed_article_returns_explicit_gone_status(client, status) -> None:
    with get_session_context() as db:
        article = _published_article()
        article.status = status
        db.add(article)

    page = client.get("/articles/strength-basics")
    api = client.get("/api/v1/public/articles/strength-basics")
    assert page.status_code == 410
    assert api.status_code == 410
    assert page.headers["x-robots-tag"] == "noindex, nofollow"
    assert api.headers["x-robots-tag"] == "noindex, nofollow"


def test_server_article_fallback_resolves_allowlisted_cta(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "landing_domain", "your-fitness-coach.ru")
    monkeypatch.setattr(settings, "telegram_bot_username", "hermes_yfc_bot")
    with get_session_context() as db:
        article = _published_article()
        article.cta = {
            "destination": "tma",
            "label": "Открыть в Telegram",
            "description": "Продолжить в Mini App.",
        }
        db.add(article)

    response = client.get("/articles/strength-basics", headers={"Host": "your-fitness-coach.ru"})
    assert response.status_code == 200
    assert 'href="https://t.me/hermes_yfc_bot?startapp"' in response.text
    assert ">Открыть в Telegram</a>" in response.text


def test_public_article_api_exposes_only_published_records(client) -> None:
    with get_session_context() as db:
        article = _published_article()
        db.add(article)

    response = client.get("/api/v1/public/articles")
    detail = client.get("/api/v1/public/articles/strength-basics")
    assert response.status_code == 200
    assert response.json()[0]["slug"] == "strength-basics"
    assert detail.status_code == 200
    assert detail.json()["content_version"] == 1
