"""Privacy-safe Telegram editorial growth and Task 130 handoff contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fitminiapp_api.core.config import settings

NEWS_CAMPAIGN = "telegram_editorial_v1"
CTA_DESTINATIONS = ("tma", "web", "landing", "article")
CTA_SURFACES = ("telegram", "desktop_web", "mobile_web", "tma")
FUNNEL_METRIC_NAMES = (
    "reach_view",
    "audience_growth",
    "engagement",
    "cta_click",
    "qualified_lead",
    "product_conversion",
    "activation",
)
SAFE_CAMPAIGN_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{2,31}$")


@dataclass(frozen=True)
class FunnelMetricDefinition:
    name: str
    meaning: str
    denominator: str
    attribution_window: str
    owner: str


NEWS_FUNNEL_DEFINITIONS = {
    "reach_view": FunnelMetricDefinition(
        "reach_view",
        "Aggregate Telegram/platform view signal; not proof of reading.",
        "available Telegram aggregate views",
        "publication lifetime",
        "channel owner",
    ),
    "audience_growth": FunnelMetricDefinition(
        "audience_growth",
        "Aggregate subscriber-count change available from the owner/platform.",
        "channel subscriber count at comparison points",
        "owner-selected reporting period",
        "channel owner",
    ),
    "engagement": FunnelMetricDefinition(
        "engagement",
        "Aggregate reaction/share/action signal exposed by the platform.",
        "available aggregate post interactions",
        "publication lifetime",
        "channel owner",
    ),
    "cta_click": FunnelMetricDefinition(
        "cta_click",
        "A click on an allowlisted canonical CTA; intent only.",
        "CTA impressions or published-post views when available",
        "30 days from publication",
        "product analytics",
    ),
    "qualified_lead": FunnelMetricDefinition(
        "qualified_lead",
        "Explicit first-party start of Demo, Mini App or sign-up flow.",
        "unique eligible first-party starts",
        "30 days from CTA click",
        "product analytics",
    ),
    "product_conversion": FunnelMetricDefinition(
        "product_conversion",
        "Server-confirmed product outcome attributed to the editorial campaign.",
        "unique server-confirmed outcomes",
        "30 days from qualified lead",
        "product backend",
    ),
    "activation": FunnelMetricDefinition(
        "activation",
        "A separately defined product milestone, never inferred from registration alone.",
        "unique users reaching the owner-defined milestone",
        "owner-defined product window",
        "product owner",
    ),
}


def _safe_url(value: str, *, allowed_hosts: set[str]) -> str | None:
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.fragment
        or (parsed.hostname or "").lower() not in allowed_hosts
    ):
        return None
    query = parse_qsl(parsed.query, keep_blank_values=True)
    if any(key not in {"utm_source", "utm_medium", "utm_campaign"} for key, _ in query):
        return None
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", urlencode(query), ""))


def canonical_cta_url(
    destination: str,
    *,
    campaign: str = NEWS_CAMPAIGN,
    article_canonical_url: str | None = None,
) -> str | None:
    """Return only configured canonical destinations with fixed attribution values."""

    if destination not in CTA_DESTINATIONS or not SAFE_CAMPAIGN_PATTERN.fullmatch(campaign):
        return None
    base_url = settings.frontend_base_url.rstrip("/")
    if destination == "article":
        if article_canonical_url is None:
            return None
        allowed_hosts = {
            host
            for host in (
                urlparse(settings.frontend_base_url).hostname,
                settings.landing_domain.strip().lower() or None,
            )
            if host
        }
        base_url = _safe_url(article_canonical_url, allowed_hosts=allowed_hosts) or ""
        if not base_url:
            return None
    elif destination == "landing":
        landing_domain = settings.landing_domain.strip().lower()
        if not landing_domain:
            return None
        base_url = f"https://{landing_domain}/"
    elif destination == "tma":
        username = settings.telegram_bot_username.strip().removeprefix("@").lower()
        if not username or not re.fullmatch(r"[a-zA-Z0-9_]{5,32}", username):
            return None
        base_url = f"https://t.me/{username}"
    else:
        base_url = f"{base_url}/"
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}utm_source=telegram&utm_medium=editorial&utm_campaign={campaign}"


def validate_attribution_event(event: object) -> bool:
    """Accept a small allowlist-only event; reject PII, arbitrary URLs and source content."""

    if not isinstance(event, dict):
        return False
    allowed_keys = {"event", "surface", "environment", "campaign", "destination"}
    if set(event) != allowed_keys:
        return False
    return (
        event.get("event") == "cta_click"
        and event.get("surface") in CTA_SURFACES
        and event.get("environment") in {"production", "staging", "development", "test"}
        and isinstance(event.get("campaign"), str)
        and bool(SAFE_CAMPAIGN_PATTERN.fullmatch(event["campaign"]))
        and event.get("destination") in CTA_DESTINATIONS
    )


def article_candidate_handoff(
    *,
    cluster_id: str,
    draft_revision: int,
    primary_topic: str,
    content_type: str,
    canonical_url: str | None = None,
) -> dict[str, object]:
    """Expose metadata only; Task 130 remains the source of truth for Web article lifecycle."""

    if not re.fullmatch(r"[0-9a-f]{32}", cluster_id) or draft_revision < 1:
        raise ValueError("invalid_article_candidate_reference")
    return {
        "kind": "article_candidate",
        "candidate_ref": f"news:{cluster_id}:r{draft_revision}",
        "cluster_id": cluster_id,
        "draft_revision": draft_revision,
        "primary_topic": primary_topic,
        "content_type": content_type,
        "canonical_url": canonical_url,
        "web_lifecycle_owner": "task-130",
    }
