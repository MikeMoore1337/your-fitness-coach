"""Canonical Web editorial lifecycle and the narrow long-form Hermes handoff."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.news import (
    HermesWebArticleSubmission,
    WebArticle,
    WebArticleCandidate,
    WebArticleRevision,
)
from fitminiapp_api.schemas.articles import (
    HermesWebArticleProposal,
    WebArticleCard,
    WebArticleResponse,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.news_drafts import style_checklist_warnings
from fitminiapp_api.services.news_ingestion import utcnow
from fitminiapp_api.services.news_taxonomy import (
    EDITORIAL_TOPICS,
    EVIDENCE_LEVELS,
    RISK_LEVELS,
    classify_editorial_text,
)

ARTICLE_SCHEMA_VERSION = "yfc-web-article-v1"
HERMES_WEB_ARTICLE_SCHEMA_VERSION = "hermes-web-article-intake-v1"
HERMES_WEB_ARTICLE_SKILL_VERSION = "yfc-hermes-editorial-v1"
ARTICLE_STATUSES = (
    "candidate",
    "researching",
    "draft",
    "review",
    "approved",
    "published",
    "update_required",
    "archived",
    "retracted",
)
ARTICLE_CANDIDATE_SOURCE_KINDS = ("manual", "seo_import", "news_handoff")
ARTICLE_KINDS = (
    "evergreen_explainer",
    "practical_guide",
    "evidence_review",
    "myth_busting",
    "research_update",
    "comparison",
    "product_education",
)
SEARCH_INTENTS = ("informational", "how_to", "comparison", "definition", "evidence", "mixed")
ARTICLE_CTA_DESTINATIONS = ("tma", "web", "landing")
SENSITIVE_ARTICLE_TOPICS = {
    "medicine",
    "peptides",
    "sports_medicine_injuries",
    "dietary_supplements",
    "sports_nutrition",
}
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SAFE_REF_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
NUMBER_PATTERN = re.compile(r"(?<![\w])\d+(?:[.,]\d+)?(?:%|\s?(?:mg|g|kg|мг|г|кг))?", re.IGNORECASE)


class WebArticleError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ArticleCandidateSignals:
    search_demand: int = 0
    intent_clarity: int = 0
    topical_relevance: int = 0
    product_relevance: int = 0
    audience_usefulness: int = 0
    evergreen_potential: int = 0
    evidence_availability: int = 0
    existing_content_overlap: int = 0
    internal_link_potential: int = 0
    risk_review_cost: int = 0
    freshness_need: int = 0
    news_opportunity: int = 0

    def validate(self) -> None:
        for value in self.__dict__.values():
            if not isinstance(value, int) or not 0 <= value <= 100:
                raise ValueError("article_candidate_signal_out_of_range")


@dataclass(frozen=True)
class HermesWebArticleIntakeResult:
    status: str
    submission_id: str
    article_id: str
    article_status: str
    content_version: int
    review_blockers: tuple[str, ...]


def score_article_candidate(signals: ArticleCandidateSignals) -> dict[str, Any]:
    """Score opportunity, not approval; overlap/risk/freshness remain separate dimensions."""

    signals.validate()
    weights = {
        "search_demand": 12,
        "intent_clarity": 10,
        "topical_relevance": 12,
        "product_relevance": 10,
        "audience_usefulness": 12,
        "evergreen_potential": 10,
        "evidence_availability": 12,
        "existing_content_overlap": -8,
        "internal_link_potential": 6,
        "risk_review_cost": -8,
        "freshness_need": -3,
        "news_opportunity": 5,
    }
    breakdown = {key: getattr(signals, key) * weight for key, weight in weights.items()}
    denominator = sum(weight for weight in weights.values() if weight > 0)
    raw_score = (
        sum(getattr(signals, key) / 100 * weight for key, weight in weights.items())
        / denominator
        * 100
    )
    score = max(0, min(100, round(raw_score)))
    reasons = [
        key
        for key in ("search_demand", "intent_clarity", "evidence_availability", "product_relevance")
        if getattr(signals, key) >= 70
    ]
    if signals.existing_content_overlap >= 70:
        reasons.append("existing_content_overlap_requires_merge_or_rejection")
    if signals.risk_review_cost >= 60:
        reasons.append("risk_review_cost_requires_manual_path")
    return {"score": score, "breakdown": breakdown, "reasons": reasons}


def create_article_candidate(
    db: Session,
    *,
    source_kind: str,
    working_title: str,
    primary_topic: str,
    topics: list[str],
    article_kind: str,
    search_intent: str,
    primary_query: str,
    secondary_queries: list[str],
    audience: str,
    risk_level: str,
    evidence_level: str,
    signals: ArticleCandidateSignals,
    source_ref: str | None = None,
    candidate_id: str | None = None,
) -> WebArticleCandidate:
    if source_kind not in ARTICLE_CANDIDATE_SOURCE_KINDS:
        raise WebArticleError("candidate_source_kind_invalid")
    if article_kind not in ARTICLE_KINDS or search_intent not in SEARCH_INTENTS:
        raise WebArticleError("candidate_contract_invalid")
    normalized_title = working_title.strip()
    normalized_primary_query = primary_query.strip()
    normalized_audience = audience.strip()
    normalized_topics = list(dict.fromkeys(topic.strip() for topic in topics))
    normalized_secondary_queries = list(dict.fromkeys(query.strip() for query in secondary_queries))
    if (
        not normalized_title
        or len(normalized_title) > 240
        or not normalized_primary_query
        or len(normalized_primary_query) > 240
        or not normalized_audience
        or len(normalized_audience) > 32
        or not normalized_topics
        or len(normalized_topics) > 12
        or any(not topic or len(topic) > 64 for topic in normalized_topics)
        or any(not query or len(query) > 240 for query in normalized_secondary_queries)
        or len(normalized_secondary_queries) > 20
    ):
        raise WebArticleError("candidate_contract_invalid")
    if (
        primary_topic not in EDITORIAL_TOPICS
        or any(topic not in EDITORIAL_TOPICS for topic in normalized_topics)
        or primary_topic not in normalized_topics
    ):
        raise WebArticleError("candidate_topic_invalid")
    if risk_level not in RISK_LEVELS or evidence_level not in EVIDENCE_LEVELS:
        raise WebArticleError("candidate_contract_invalid")
    normalized_source_ref = source_ref.strip() if source_ref is not None else None
    if source_kind != "manual" and not normalized_source_ref:
        raise WebArticleError("candidate_source_ref_invalid")
    if normalized_source_ref is not None and not SAFE_REF_PATTERN.fullmatch(normalized_source_ref):
        raise WebArticleError("candidate_source_ref_invalid")
    scored = score_article_candidate(signals)
    candidate = WebArticleCandidate(
        id=candidate_id or secrets.token_hex(16),
        source_kind=source_kind,
        source_ref=normalized_source_ref,
        working_title=normalized_title,
        primary_topic=primary_topic,
        topics=normalized_topics,
        article_kind=article_kind,
        search_intent=search_intent,
        primary_query=normalized_primary_query,
        secondary_queries=normalized_secondary_queries,
        audience=normalized_audience,
        risk_level=risk_level,
        evidence_level=evidence_level,
        search_demand_signal=signals.search_demand,
        intent_clarity=signals.intent_clarity,
        topical_relevance=signals.topical_relevance,
        product_relevance=signals.product_relevance,
        audience_usefulness=signals.audience_usefulness,
        evergreen_potential=signals.evergreen_potential,
        evidence_availability=signals.evidence_availability,
        existing_content_overlap=signals.existing_content_overlap,
        internal_link_potential=signals.internal_link_potential,
        risk_review_cost=signals.risk_review_cost,
        freshness_need=signals.freshness_need,
        news_opportunity=signals.news_opportunity,
        priority_score=scored["score"],
        score_breakdown=scored["breakdown"],
        web_article_potential_reasons=scored["reasons"],
    )
    db.add(candidate)
    db.flush()
    return candidate


def validate_article_proposal(proposal: HermesWebArticleProposal) -> tuple[str, ...]:
    """Return review warnings; this is intentionally not an AI-authorship detector."""

    body = "\n\n".join(
        [proposal.title, proposal.description, proposal.lead]
        + [paragraph for section in proposal.body_sections for paragraph in section.paragraphs]
        + [point for section in proposal.body_sections for point in section.points]
    )
    warnings = list(style_checklist_warnings(body))
    if body.count("?") > 12:
        warnings.append("mechanical_question_density")
    if len({query.casefold() for query in proposal.secondary_queries}) != len(
        proposal.secondary_queries
    ):
        warnings.append("duplicate_secondary_query")
    source_ids = [source.source_id for source in proposal.sources]
    if len(source_ids) != len(set(source_ids)):
        warnings.append("duplicate_source_id")
    matrix_claim_ids = [item.claim_id for item in proposal.claim_source_matrix]
    if len(matrix_claim_ids) != len(set(matrix_claim_ids)):
        warnings.append("duplicate_claim_matrix_entry")
    if proposal.evidence_level in {"preliminary", "conflicting"}:
        warnings.append(f"evidence_{proposal.evidence_level}")
    if NUMBER_PATTERN.search(body) and not any(
        item.support_level == "supports" and item.review_status == "verified"
        for item in proposal.claim_source_matrix
    ):
        warnings.append("unsupported_number")
    if proposal.risk_level in {"high", "critical"}:
        warnings.append("sensitive_content_requires_domain_review")
    return tuple(dict.fromkeys(warnings))


def _review_blockers(
    proposal: HermesWebArticleProposal, warnings: tuple[str, ...]
) -> tuple[str, ...]:
    blockers = list(warnings)
    if not proposal.claim_source_matrix:
        blockers.append("claim_source_matrix_missing")
    if any(item.review_status != "verified" for item in proposal.claim_source_matrix):
        blockers.append("claim_source_matrix_not_fully_verified")
    if any(
        item.support_level in {"does_not_support", "unclear"}
        for item in proposal.claim_source_matrix
    ):
        blockers.append("claim_source_support_unclear")
    if proposal.domain_reviewer is None and (
        proposal.risk_level in {"high", "critical"}
        or any(topic in SENSITIVE_ARTICLE_TOPICS for topic in proposal.topics)
    ):
        blockers.append("domain_reviewer_required")
    if proposal.evidence_level in {"preliminary", "conflicting"}:
        blockers.append("evidence_limitation_requires_manual_review")
    return tuple(dict.fromkeys(blockers))


def _article_content_payload(proposal: HermesWebArticleProposal) -> dict[str, Any]:
    payload = proposal.model_dump(mode="json")
    payload["sources"] = [dict(source) for source in payload["sources"]]
    return payload


def _content_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _article_origin() -> str:
    from fitminiapp_api.seo import public_origin

    return public_origin()


def _safe_cta(raw: dict[str, str]) -> dict[str, str]:
    allowed = {"destination", "label", "description"}
    if set(raw) - allowed:
        raise WebArticleError("cta_contains_unallowed_fields")
    destination = raw.get("destination", "web")
    if destination not in ARTICLE_CTA_DESTINATIONS:
        raise WebArticleError("cta_destination_invalid")
    label = raw.get("label", "Открыть Your Fitness Coach").strip()
    description = raw.get(
        "description", "Перейдите в Your Fitness Coach, чтобы продолжить работу с фактами."
    ).strip()
    if not label or len(label) > 120 or not description or len(description) > 320:
        raise WebArticleError("cta_copy_invalid")
    return {"destination": destination, "label": label, "description": description}


def _find_existing_submission(
    db: Session,
    *,
    idempotency_key: str,
    request_nonce: str,
    payload_hash: str,
    now: datetime,
) -> HermesWebArticleSubmission | None:
    existing = (
        db.query(HermesWebArticleSubmission)
        .filter(HermesWebArticleSubmission.idempotency_key == idempotency_key)
        .one_or_none()
    )
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise WebArticleError("idempotency_conflict")
        if existing.expires_at <= now:
            raise WebArticleError("replay_expired")
        if existing.request_nonce != request_nonce:
            raise WebArticleError("idempotency_nonce_conflict")
        return existing
    nonce_match = (
        db.query(HermesWebArticleSubmission)
        .filter(HermesWebArticleSubmission.request_nonce == request_nonce)
        .one_or_none()
    )
    if nonce_match is not None:
        raise WebArticleError("replay_detected")
    return None


def _to_snapshot(proposal: HermesWebArticleProposal, **metadata: object) -> dict[str, object]:
    payload = _article_content_payload(proposal)
    payload["metadata"] = metadata
    return payload


def _assign_article_fields(
    article: WebArticle,
    proposal: HermesWebArticleProposal,
    *,
    content_version: int,
    research_version: str,
    provider: str,
    model: str,
    prompt_version: str,
    skill_version: str,
    status: str,
    blockers: tuple[str, ...],
) -> None:
    if not SLUG_PATTERN.fullmatch(proposal.slug):
        raise WebArticleError("slug_invalid")
    payload = _article_content_payload(proposal)
    article.slug = proposal.slug
    article.status = status
    article.title = proposal.title.strip()
    article.description = proposal.description.strip()
    article.lead = proposal.lead.strip()
    article.body_sections = payload["body_sections"]
    article.topics = list(dict.fromkeys(proposal.topics))
    article.article_kind = proposal.article_kind
    article.search_intent = proposal.search_intent
    article.primary_query = proposal.primary_query.strip()
    article.secondary_queries = list(dict.fromkeys(proposal.secondary_queries))
    article.risk_level = proposal.risk_level
    article.evidence_level = proposal.evidence_level
    article.claims = payload["claims"]
    article.sources = payload["sources"]
    article.claim_source_matrix = payload["claim_source_matrix"]
    article.author = payload["author"]
    article.editor = payload["editor"]
    article.domain_reviewer = payload["domain_reviewer"]
    article.canonical_url = f"{_article_origin()}/articles/{proposal.slug}"
    article.related_slugs = list(dict.fromkeys(proposal.related_slugs))
    article.cta = _safe_cta(proposal.cta)
    article.evergreen_score = proposal.evergreen_score
    article.product_relevance = proposal.product_relevance
    article.editorial_value = proposal.editorial_value
    article.web_article_potential_reasons = list(
        dict.fromkeys([*proposal.web_article_potential_reasons, *blockers])
    )
    article.content_version = content_version
    article.research_version = research_version
    article.provider = provider
    article.model = model
    article.prompt_version = prompt_version
    article.skill_version = skill_version
    article.schema_version = ARTICLE_SCHEMA_VERSION
    article.generated_with_ai = True
    article.research_assistance = True
    article.content_hash = _content_hash(payload)


def _article_result(
    submission: HermesWebArticleSubmission,
    article: WebArticle,
    *,
    status: str,
    blockers: tuple[str, ...],
) -> HermesWebArticleIntakeResult:
    return HermesWebArticleIntakeResult(
        status=status,
        submission_id=submission.submission_id,
        article_id=article.id,
        article_status=article.status,
        content_version=article.content_version,
        review_blockers=blockers,
    )


def accept_hermes_article_submission(
    db: Session,
    payload,
    *,
    payload_hash: str,
    now: datetime | None = None,
) -> HermesWebArticleIntakeResult:
    current = now or utcnow()
    existing = _find_existing_submission(
        db,
        idempotency_key=payload.idempotency_key,
        request_nonce=payload.request_nonce,
        payload_hash=payload_hash,
        now=current,
    )
    if existing is not None:
        article = db.get(WebArticle, existing.article_id)
        if article is None:
            raise WebArticleError("submission_result_missing")
        blockers = tuple(existing.response_metadata.get("review_blockers", []))
        return _article_result(existing, article, status="duplicate", blockers=blockers)
    if payload.schema_version != HERMES_WEB_ARTICLE_SCHEMA_VERSION:
        raise WebArticleError("schema_version_unsupported")
    if payload.provenance.skill_version != HERMES_WEB_ARTICLE_SKILL_VERSION:
        raise WebArticleError("skill_version_unsupported")
    if len(payload.article.sources) > settings.hermes_intake_max_source_count:
        raise WebArticleError("source_count_exceeded")
    recent_count = (
        db.query(HermesWebArticleSubmission)
        .filter(HermesWebArticleSubmission.created_at >= current - timedelta(minutes=1))
        .count()
    )
    if recent_count >= settings.hermes_intake_rate_limit_per_minute:
        raise WebArticleError("rate_limited")
    candidate = db.get(WebArticleCandidate, payload.candidate_id)
    if candidate is None:
        raise WebArticleError("candidate_missing")
    existing_article = (
        db.query(WebArticle).filter(WebArticle.slug == payload.article.slug).one_or_none()
    )
    is_update = existing_article is not None
    if candidate.status not in {"candidate", "approved", "researching", "draft", "review"}:
        raise WebArticleError("candidate_not_ready")
    if is_update and (
        existing_article.status != "update_required"
        or existing_article.candidate_id != candidate.id
    ):
        raise WebArticleError("slug_conflict")
    warnings = validate_article_proposal(payload.article)
    blockers = _review_blockers(payload.article, warnings)
    classification = classify_editorial_text(
        f"{payload.article.title} {payload.article.primary_query} {' '.join(payload.article.topics)}",
        payload.article.lead,
    )
    if any(topic in SENSITIVE_ARTICLE_TOPICS for topic in payload.article.topics):
        blockers = tuple(dict.fromkeys((*blockers, "sensitive_topic_manual_review")))
    if classification.risk_level in {"high", "critical"}:
        blockers = tuple(dict.fromkeys((*blockers, "taxonomy_risk_manual_review")))
    content_version = existing_article.content_version + 1 if is_update else 1
    article = existing_article or WebArticle(id=secrets.token_hex(16), candidate_id=candidate.id)
    if not is_update:
        db.add(article)
    _assign_article_fields(
        article,
        payload.article,
        content_version=content_version,
        research_version=payload.research_version,
        provider=payload.provenance.provider,
        model=payload.provenance.model,
        prompt_version=payload.provenance.prompt_version,
        skill_version=payload.provenance.skill_version,
        status="draft",
        blockers=blockers,
    )
    db.flush()
    change_reason = "hermes_research_update" if is_update else "hermes_research_submission"
    db.add(
        WebArticleRevision(
            id=secrets.token_hex(16),
            article_id=article.id,
            content_version=content_version,
            status="draft",
            snapshot=_to_snapshot(
                payload.article,
                article_schema_version=ARTICLE_SCHEMA_VERSION,
                research_version=payload.research_version,
                provider=payload.provenance.provider,
                model=payload.provenance.model,
                prompt_version=payload.provenance.prompt_version,
                skill_version=payload.provenance.skill_version,
                review_blockers=list(blockers),
                style_warnings=list(warnings),
                change_reason=change_reason,
                correction_reason=article.correction_reason,
            ),
            change_reason=change_reason,
        )
    )
    candidate.status = "draft"
    submission = HermesWebArticleSubmission(
        submission_id=secrets.token_hex(24),
        candidate_id=candidate.id,
        article_id=article.id,
        idempotency_key=payload.idempotency_key,
        request_nonce=payload.request_nonce,
        payload_hash=payload_hash,
        schema_version=payload.schema_version,
        research_version=payload.research_version,
        provider=payload.provenance.provider,
        model=payload.provenance.model,
        prompt_version=payload.provenance.prompt_version,
        skill_version=payload.provenance.skill_version,
        response_metadata={
            "article_schema_version": ARTICLE_SCHEMA_VERSION,
            "review_blockers": list(blockers),
            "style_warnings": list(warnings),
            "source_count": len(payload.article.sources),
            "claim_count": len(payload.article.claims),
        },
        expires_at=current + timedelta(seconds=settings.hermes_intake_replay_ttl_seconds),
        processed_at=current,
    )
    db.add(submission)
    record_audit_event(
        db,
        action="web_article.hermes_intake_accepted",
        resource_type="web_article",
        resource_id=article.id,
        details={
            "candidate_id": candidate.id,
            "submission_id": submission.submission_id,
            "status": article.status,
            "content_version": article.content_version,
            "review_blocker_count": len(blockers),
            "change_reason": change_reason,
        },
    )
    db.flush()
    return _article_result(submission, article, status="accepted", blockers=blockers)


def article_card(article: WebArticle) -> WebArticleCard:
    if article.status != "published" or article.published_at is None or article.updated_at is None:
        raise WebArticleError("article_not_public")
    canonical_url = f"{_article_origin()}/articles/{article.slug}"
    return WebArticleCard.model_validate(
        {
            "slug": article.slug,
            "title": article.title,
            "description": article.description,
            "lead": article.lead,
            "topics": list(article.topics),
            "article_kind": article.article_kind,
            "published_at": article.published_at,
            "updated_at": article.updated_at,
            "canonical_url": canonical_url,
        }
    )


def article_public_response(article: WebArticle) -> WebArticleResponse:
    card = article_card(article)
    return WebArticleResponse.model_validate(
        {
            **card.model_dump(),
            "body_sections": article.body_sections,
            "search_intent": article.search_intent,
            "primary_query": article.primary_query,
            "secondary_queries": list(article.secondary_queries),
            "risk_level": article.risk_level,
            "evidence_level": article.evidence_level,
            "claims": article.claims,
            "sources": article.sources,
            "claim_source_matrix": article.claim_source_matrix,
            "author": article.author,
            "editor": article.editor,
            "domain_reviewer": article.domain_reviewer,
            "related_slugs": list(article.related_slugs),
            "cta": dict(article.cta),
            "content_version": article.content_version,
            "generated_with_ai": article.generated_with_ai,
            "research_assistance": article.research_assistance,
        }
    )


def published_articles(db: Session) -> list[WebArticle]:
    return (
        db.query(WebArticle)
        .filter(WebArticle.status == "published")
        .order_by(WebArticle.published_at.desc(), WebArticle.slug.asc())
        .all()
    )


def mark_article_update_required(db: Session, article: WebArticle, *, reason: str) -> None:
    if article.status != "published":
        raise WebArticleError("article_not_published")
    normalized_reason = reason.strip()
    if not normalized_reason or len(normalized_reason) > 256:
        raise WebArticleError("correction_reason_invalid")
    article.status = "update_required"
    article.correction_reason = normalized_reason
    record_audit_event(
        db,
        action="web_article.update_required",
        resource_type="web_article",
        resource_id=article.id,
        details={"content_version": article.content_version, "reason": normalized_reason},
    )


def _transition_removed_article(
    db: Session,
    article: WebArticle,
    *,
    target_status: str,
    reason: str,
    actor_ref: str,
    allowed_statuses: set[str],
) -> None:
    normalized_reason = reason.strip()
    if not normalized_reason or len(normalized_reason) > 256:
        raise WebArticleError("correction_reason_invalid")
    if article.status == target_status:
        return
    if article.status not in allowed_statuses:
        raise WebArticleError("article_transition_invalid")
    article.status = target_status
    article.correction_reason = normalized_reason
    record_audit_event(
        db,
        action=f"web_article.{target_status}",
        resource_type="web_article",
        resource_id=article.id,
        details={
            "content_version": article.content_version,
            "reason": normalized_reason,
            "actor_ref": actor_ref,
        },
    )


def archive_web_article(db: Session, article: WebArticle, *, reason: str, actor_ref: str) -> None:
    """Remove an article from the public surface while preserving its revisions and audit trail."""

    _transition_removed_article(
        db,
        article,
        target_status="archived",
        reason=reason,
        actor_ref=actor_ref,
        allowed_statuses={"draft", "review", "approved", "published", "update_required"},
    )


def retract_web_article(db: Session, article: WebArticle, *, reason: str, actor_ref: str) -> None:
    """Retract a public article explicitly; no content or revision is deleted."""

    _transition_removed_article(
        db,
        article,
        target_status="retracted",
        reason=reason,
        actor_ref=actor_ref,
        allowed_statuses={"published", "update_required", "archived"},
    )


def publish_web_article(
    db: Session,
    article: WebArticle,
    *,
    actor_ref: str,
    owner_editorial_decision: bool = False,
    owner_user_id: int | None = None,
) -> None:
    """Publish via strict editorial checks or a separately authenticated owner decision.

    An owner decision is not scientific verification: pending matrix entries stay pending.
    The caller of the owner path must enforce verified Root authentication.
    """
    if owner_editorial_decision and (owner_user_id is None or owner_user_id <= 0):
        raise WebArticleError("owner_identity_required")

    if article.status != "approved":
        raise WebArticleError("article_not_approved")
    revision = (
        db.query(WebArticleRevision)
        .filter(
            WebArticleRevision.article_id == article.id,
            WebArticleRevision.content_version == article.content_version,
        )
        .one_or_none()
    )
    if revision is None:
        raise WebArticleError("article_revision_missing")
    if not isinstance(article.claim_source_matrix, list) or not article.claim_source_matrix:
        raise WebArticleError("claim_source_matrix_missing")
    if any(
        not isinstance(item, dict)
        or item.get("review_status") == "blocked"
        or item.get("support_level") == "does_not_support"
        for item in article.claim_source_matrix
    ):
        raise WebArticleError("claim_source_explicitly_blocked")
    if not owner_editorial_decision:
        if any(
            item.get("review_status") != "verified" or item.get("support_level") == "unclear"
            for item in article.claim_source_matrix
        ):
            raise WebArticleError("claim_source_review_incomplete")
        if not article.domain_reviewer and (
            article.risk_level in {"high", "critical"}
            or any(topic in SENSITIVE_ARTICLE_TOPICS for topic in article.topics)
        ):
            raise WebArticleError("domain_reviewer_required")
    now = utcnow()
    article.status = "published"
    article.published_at = article.published_at or now
    article.updated_at = now
    revision.status = "published"
    record_audit_event(
        db,
        action="web_article.published",
        resource_type="web_article",
        resource_id=article.id,
        actor_user_id=owner_user_id,
        details={
            "content_version": article.content_version,
            "actor_ref": actor_ref,
            "editorial_decision": (
                "root_owner_publication" if owner_editorial_decision else "standard_review"
            ),
            "independent_scientific_review": (
                "not_attested" if owner_editorial_decision else "standard_review"
            ),
        },
    )


def publish_existing_owner_article(
    db: Session,
    *,
    article_id: str,
    expected_content_hash: str,
    expected_content_version: int,
    actor_user_id: int,
) -> WebArticle:
    """One Root owner's exact-revision release of a previously ingested draft.

    Hermes HMAC, scheduler and GitHub OAuth alone cannot call this operation.
    A row lock keeps concurrent owner approvals and draft changes consistent.
    """
    if actor_user_id <= 0:
        raise WebArticleError("owner_identity_required")
    article = (
        db.query(WebArticle).filter(WebArticle.id == article_id).with_for_update().one_or_none()
    )
    if article is None:
        raise WebArticleError("article_not_found")
    if (
        article.content_hash != expected_content_hash
        or article.content_version != expected_content_version
    ):
        raise WebArticleError("article_revision_conflict")
    if article.status == "published":
        # A replay must not misattribute another publication path or Root actor
        # to this exact interactive Control Center approval.
        last = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.action == "web_article.published",
                AuditEvent.resource_type == "web_article",
                AuditEvent.resource_id == article_id,
            )
            .order_by(AuditEvent.id.desc())
            .first()
        )
        if (
            last is None
            or last.actor_user_id != actor_user_id
            or not isinstance(last.details, dict)
            or last.details.get("actor_ref") != "root_owner_control_center"
            or last.details.get("content_version") != expected_content_version
        ):
            raise WebArticleError("article_already_published_by_other_path")
        return article
    if article.status not in {"draft", "review", "approved"}:
        raise WebArticleError("article_transition_invalid")
    revision = (
        db.query(WebArticleRevision)
        .filter(
            WebArticleRevision.article_id == article_id,
            WebArticleRevision.content_version == expected_content_version,
        )
        .one_or_none()
    )
    if revision is None:
        raise WebArticleError("article_revision_missing")
    if revision.status not in {"draft", "review", "approved"}:
        raise WebArticleError("article_revision_status_invalid")
    article.status = "approved"
    revision.status = "approved"
    publish_web_article(
        db,
        article,
        actor_ref="root_owner_control_center",
        owner_editorial_decision=True,
        owner_user_id=actor_user_id,
    )
    return article


def publish_owner_web_article(
    db: Session,
    proposal: HermesWebArticleProposal,
    *,
    actor_user_id: int,
    generated_with_ai: bool,
) -> WebArticle:
    """Single authenticated owner operation: validate, version, publish and audit.

    This does not turn pending science reviews into verified evidence.
    The caller must first pass require_root_admin; no Hermes secret or candidate is needed.
    """
    if actor_user_id <= 0:
        raise WebArticleError("owner_identity_required")
    if any(
        entry.review_status == "blocked" or entry.support_level == "does_not_support"
        for entry in proposal.claim_source_matrix
    ):
        raise WebArticleError("claim_source_explicitly_blocked")

    content_hash = _content_hash(_article_content_payload(proposal))
    existing = db.query(WebArticle).filter(WebArticle.slug == proposal.slug).one_or_none()
    if existing is not None:
        if existing.content_hash != content_hash:
            raise WebArticleError("slug_conflict")
        if existing.status == "published":
            return existing
        if existing.status not in {"draft", "review", "approved"}:
            raise WebArticleError("article_transition_invalid")
        revision = (
            db.query(WebArticleRevision)
            .filter(
                WebArticleRevision.article_id == existing.id,
                WebArticleRevision.content_version == existing.content_version,
            )
            .one_or_none()
        )
        if revision is None:
            raise WebArticleError("article_revision_missing")
        existing.status = "approved"
        revision.status = "approved"
        publish_web_article(
            db,
            existing,
            actor_ref="root_owner",
            owner_editorial_decision=True,
            owner_user_id=actor_user_id,
        )
        return existing

    warnings = validate_article_proposal(proposal)
    blockers = _review_blockers(proposal, warnings)
    article = WebArticle(id=secrets.token_hex(16), candidate_id=None)
    _assign_article_fields(
        article,
        proposal,
        content_version=1,
        research_version="owner-editorial-v1",
        provider="owner",
        model="manual-editorial",
        prompt_version="owner-editorial-v1",
        skill_version="yfc-editorial-v1",
        status="approved",
        blockers=blockers,
    )
    article.generated_with_ai = generated_with_ai
    article.research_assistance = generated_with_ai
    db.add(article)
    db.flush()

    db.add(
        WebArticleRevision(
            id=secrets.token_hex(16),
            article_id=article.id,
            content_version=1,
            status="approved",
            snapshot=_to_snapshot(
                proposal,
                article_schema_version=ARTICLE_SCHEMA_VERSION,
                research_version="owner-editorial-v1",
                provider="owner",
                model="manual-editorial",
                generated_with_ai=generated_with_ai,
                editorial_decision="root_owner_publication",
                independent_scientific_review="not_attested",
                review_blockers=list(blockers),
            ),
            change_reason="root_owner_editorial_publication",
        )
    )
    db.flush()
    publish_web_article(
        db,
        article,
        actor_ref="root_owner",
        owner_editorial_decision=True,
        owner_user_id=actor_user_id,
    )
    return article


def public_article_path(slug: str) -> str:
    if not SLUG_PATTERN.fullmatch(slug):
        raise WebArticleError("slug_invalid")
    return f"/articles/{slug}"
