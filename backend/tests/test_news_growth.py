from fitminiapp_api.core.config import settings
from fitminiapp_api.services.news_growth import (
    NEWS_FUNNEL_DEFINITIONS,
    article_candidate_handoff,
    canonical_cta_url,
    validate_attribution_event,
)


def test_cta_uses_only_canonical_allowlisted_destination_and_fixed_campaign(monkeypatch) -> None:
    monkeypatch.setattr(settings, "frontend_base_url", "https://app.example.com")
    monkeypatch.setattr(settings, "landing_domain", "www.example.com")
    monkeypatch.setattr(settings, "telegram_bot_username", "yfc_test_bot")

    web = canonical_cta_url("web")
    article = canonical_cta_url(
        "article",
        article_canonical_url="https://app.example.com/articles/strength-recovery",
    )

    assert web == (
        "https://app.example.com/?utm_source=telegram&utm_medium=editorial"
        "&utm_campaign=telegram_editorial_v1"
    )
    assert article is not None
    assert "strength-recovery" in article
    assert canonical_cta_url("web", campaign="contains user text") is None
    assert canonical_cta_url("article", article_canonical_url="https://evil.example/a") is None


def test_attribution_event_separates_click_from_lead_and_rejects_sensitive_fields() -> None:
    assert validate_attribution_event(
        {
            "event": "cta_click",
            "surface": "telegram",
            "environment": "test",
            "campaign": "telegram_editorial_v1",
            "destination": "tma",
        }
    )
    assert not validate_attribution_event(
        {
            "event": "qualified_lead",
            "surface": "telegram",
            "environment": "test",
            "campaign": "telegram_editorial_v1",
            "destination": "tma",
        }
    )
    assert not validate_attribution_event(
        {
            "event": "cta_click",
            "surface": "telegram",
            "environment": "test",
            "campaign": "telegram_editorial_v1",
            "destination": "tma",
            "user_id": 42,
        }
    )


def test_article_handoff_contains_metadata_only_and_has_task_130_owner() -> None:
    handoff = article_candidate_handoff(
        cluster_id="a" * 32,
        draft_revision=2,
        primary_topic="strength_hypertrophy",
        content_type="research",
    )

    assert handoff["kind"] == "article_candidate"
    assert handoff["web_lifecycle_owner"] == "task-130"
    assert handoff["canonical_url"] is None
    assert "draft_text" not in handoff
    assert set(NEWS_FUNNEL_DEFINITIONS) == {
        "reach_view",
        "audience_growth",
        "engagement",
        "cta_click",
        "qualified_lead",
        "product_conversion",
        "activation",
    }
