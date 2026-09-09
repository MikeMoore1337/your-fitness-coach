"""Narrow Hermes -> YFC editorial intake.

Hermes is treated as an untrusted external worker.  This module accepts only a bounded source
packet and draft proposal, revalidates both, and hands them to the canonical YFC news models.
There is intentionally no Telegram client, channel credential, shell, or provider fallback here.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.models.news import (
    HermesEditorialSubmission,
    NewsCluster,
    NewsDraftRevision,
    NewsItem,
    NewsSource,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.news_drafts import (
    _validated_fields,
    evidence_packet,
    quality_warnings,
    render_draft,
)
from fitminiapp_api.services.news_freshness import is_fresh_publication
from fitminiapp_api.services.news_growth import article_candidate_handoff
from fitminiapp_api.services.news_ingestion import (
    ParsedNewsItem,
    _item_reference_url,
    ingest_items,
    plain_text,
    sha256_text,
    utcnow,
)
from fitminiapp_api.services.news_origin import HERMES_SUBMISSION_MARKER
from fitminiapp_api.services.news_state import transition_news_cluster
from fitminiapp_api.services.news_taxonomy import (
    RISK_POLICY_VERSION,
    TAXONOMY_VERSION,
    VOICE_PROFILE_VERSION,
    classify_editorial_text,
    evaluate_publication_policy,
)

HERMES_INTAKE_SCHEMA_VERSION = "hermes-editorial-intake-v1"
HERMES_INTAKE_ENDPOINT = "/api/v1/hermes/editorial/intake"
SUPPORTED_HERMES_SKILL_VERSIONS = frozenset({"yfc-hermes-editorial-v1"})
HERMES_SIGNATURE_PREFIX = "sha256="
HEX64_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class HermesIntakeError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class HermesIntakeResult:
    status: str
    submission_id: str
    cluster_id: str
    draft_id: str
    publication_policy: str
    risk_reasons: tuple[str, ...]
    preview_text: str


def hermes_signature(
    secret: str,
    *,
    timestamp: str,
    nonce: str,
    body: bytes,
) -> str:
    """Build the documented signature for tests and an external worker adapter."""

    message = timestamp.encode("ascii") + b"\n" + nonce.encode("ascii") + b"\n" + body
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return HERMES_SIGNATURE_PREFIX + digest


def verify_hermes_signature(
    *,
    key_id: str,
    timestamp: str,
    nonce: str,
    signature: str,
    body: bytes,
    now: float | None = None,
) -> None:
    if not settings.hermes_intake_enabled:
        raise HermesIntakeError("intake_disabled")
    if key_id != settings.hermes_intake_key_id:
        raise HermesIntakeError("key_not_found")
    if not re.fullmatch(r"[0-9]+", timestamp) or not re.fullmatch(
        r"[A-Za-z0-9_.:-]{16,128}", nonce
    ):
        raise HermesIntakeError("signature_headers_invalid")
    try:
        timestamp_value = int(timestamp)
    except ValueError as exc:
        raise HermesIntakeError("signature_headers_invalid") from exc
    current = time.time() if now is None else now
    if abs(current - timestamp_value) > settings.hermes_intake_clock_skew_seconds:
        raise HermesIntakeError("signature_expired")
    if not signature.startswith(HERMES_SIGNATURE_PREFIX):
        raise HermesIntakeError("signature_invalid")
    presented = signature.removeprefix(HERMES_SIGNATURE_PREFIX)
    if not HEX64_PATTERN.fullmatch(presented):
        raise HermesIntakeError("signature_invalid")
    expected = hermes_signature(
        settings.hermes_intake_shared_secret.get_secret_value(),
        timestamp=timestamp,
        nonce=nonce,
        body=body,
    ).removeprefix(HERMES_SIGNATURE_PREFIX)
    if not hmac.compare_digest(presented, expected):
        raise HermesIntakeError("signature_invalid")


def _canonical_source_hash(
    *,
    title: str,
    summary: str,
    canonical_url: str,
    published_at: datetime | None,
) -> str:
    return sha256_text(
        json.dumps(
            {
                "title": title,
                "summary": summary,
                "url": canonical_url,
                "published_at": published_at.isoformat() if published_at else None,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _submission_response(
    db: Session,
    submission: HermesEditorialSubmission,
    *,
    status: str,
) -> HermesIntakeResult:
    if not submission.cluster_id or not submission.draft_id:
        raise HermesIntakeError("submission_result_missing")
    draft = db.get(NewsDraftRevision, submission.draft_id)
    if draft is None:
        raise HermesIntakeError("submission_result_missing")
    policy = str(draft.evidence_metadata.get("publication_policy", "manual_required"))
    if policy not in {"blocked", "manual_required", "auto_eligible"}:
        policy = "manual_required"
    reasons = draft.evidence_metadata.get("risk_reasons", [])
    risk_reasons = tuple(value for value in reasons if isinstance(value, str))
    return HermesIntakeResult(
        status=status,
        submission_id=submission.submission_id,
        cluster_id=submission.cluster_id,
        draft_id=submission.draft_id,
        publication_policy=policy,
        risk_reasons=risk_reasons,
        preview_text=draft.draft_text,
    )


def _find_existing_submission(
    db: Session,
    *,
    idempotency_key: str,
    request_nonce: str,
    payload_hash: str,
    now: datetime,
) -> HermesEditorialSubmission | None:
    existing = (
        db.query(HermesEditorialSubmission)
        .filter(HermesEditorialSubmission.idempotency_key == idempotency_key)
        .one_or_none()
    )
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise HermesIntakeError("idempotency_conflict")
        if existing.expires_at <= now:
            raise HermesIntakeError("replay_expired")
        if existing.request_nonce != request_nonce:
            raise HermesIntakeError("idempotency_nonce_conflict")
        return existing
    nonce_match = (
        db.query(HermesEditorialSubmission)
        .filter(HermesEditorialSubmission.request_nonce == request_nonce)
        .one_or_none()
    )
    if nonce_match is not None:
        raise HermesIntakeError("replay_detected")
    return None


def accept_hermes_submission(
    db: Session,
    payload,
    *,
    payload_hash: str,
    now: datetime | None = None,
) -> HermesIntakeResult:
    if not settings.hermes_intake_enabled:
        raise HermesIntakeError("intake_disabled")
    current = now or utcnow()
    existing = _find_existing_submission(
        db,
        idempotency_key=payload.idempotency_key,
        request_nonce=payload.request_nonce,
        payload_hash=payload_hash,
        now=current,
    )
    if existing is not None:
        return _submission_response(db, existing, status="duplicate")
    if payload.schema_version != HERMES_INTAKE_SCHEMA_VERSION:
        raise HermesIntakeError("schema_version_unsupported")
    if payload.provenance.skill_version not in SUPPORTED_HERMES_SKILL_VERSIONS:
        raise HermesIntakeError("skill_version_unsupported")
    recent_count = (
        db.query(HermesEditorialSubmission)
        .filter(HermesEditorialSubmission.created_at >= current - timedelta(minutes=1))
        .count()
    )
    if recent_count >= settings.hermes_intake_rate_limit_per_minute:
        raise HermesIntakeError("rate_limited")
    if not is_fresh_publication(payload.source.published_at, now=current):
        raise HermesIntakeError("source_publication_not_fresh")

    source = db.get(NewsSource, payload.source.source_id)
    if source is None or not source.enabled:
        raise HermesIntakeError("source_not_allowlisted")
    try:
        canonical_url = _item_reference_url(
            source, payload.source.canonical_url, doi=payload.source.doi
        )
        primary_url = (
            _item_reference_url(source, payload.source.primary_url, doi=payload.source.doi)
            if payload.source.primary_url
            else None
        )
        title = plain_text(payload.source.title, maximum=500)
        summary = plain_text(payload.source.summary, maximum=4000)
    except (ValueError, TypeError) as exc:
        raise HermesIntakeError("source_packet_invalid") from exc
    expected_source_hash = _canonical_source_hash(
        title=title,
        summary=summary,
        canonical_url=canonical_url,
        published_at=payload.source.published_at,
    )
    if payload.source.content_hash != expected_source_hash:
        raise HermesIntakeError("source_content_hash_mismatch")

    parsed = ParsedNewsItem(
        external_id=payload.source.external_id,
        canonical_url=canonical_url,
        primary_url=primary_url,
        title=title,
        summary=summary,
        author=payload.source.author,
        publisher=payload.source.publisher,
        published_at=payload.source.published_at,
        updated_at=payload.source.updated_at,
        doi=payload.source.doi,
    )
    counts = ingest_items(
        db,
        source,
        [parsed],
        candidate_threshold=settings.news_candidate_score_threshold,
        fetched_at=current,
        allow_sensitive_manual_review=True,
    )
    if counts["rejected"]:
        raise HermesIntakeError("source_packet_rejected")
    external_hash = sha256_text(payload.source.external_id.strip()[:512] or canonical_url)
    item = (
        db.query(NewsItem)
        .filter(
            NewsItem.source_id == source.id,
            NewsItem.external_id_hash == external_hash,
            NewsItem.content_hash == expected_source_hash,
        )
        .order_by(NewsItem.id.desc())
        .first()
    )
    if item is None or item.cluster_id is None:
        raise HermesIntakeError("source_item_missing")
    cluster = db.get(NewsCluster, item.cluster_id)
    if cluster is None:
        raise HermesIntakeError("cluster_missing")

    try:
        fields = _validated_fields(payload.draft.model_dump())
    except Exception as exc:
        raise HermesIntakeError("draft_schema_invalid") from exc
    classification = classify_editorial_text(
        f"{title} {fields['headline']}",
        f"{summary} {fields['summary']} {fields['why_it_matters']}",
        source_type=source.source_type,
    )
    warnings = tuple(
        quality_warnings(
            fields,
            source_title=title,
            source_summary=summary,
            source_context=canonical_url,
        )
    )
    policy = evaluate_publication_policy(
        classification,
        quality_warnings=warnings,
        source_provenance_valid=True,
        auto_publish_enabled=settings.news_auto_publish_low_risk,
    )
    packet = evidence_packet(db, cluster)
    draft_text = render_draft(fields, packet)
    submission_id = secrets.token_hex(24)
    revision = cluster.latest_draft_revision + 1
    draft = NewsDraftRevision(
        id=secrets.token_hex(16),
        cluster_id=cluster.id,
        primary_item_id=packet.primary_item_id,
        revision=revision,
        provider=payload.provenance.provider,
        model=payload.provenance.model,
        prompt_version=payload.provenance.prompt_version,
        source_digest=packet.source_digest,
        evidence_item_ids=list(packet.evidence_item_ids),
        evidence_metadata={
            "source_packet_hash": payload.source.content_hash,
            "trusted_source_url": packet.primary_url or packet.canonical_url,
            "source_published_at": (
                payload.source.published_at.isoformat() if payload.source.published_at else None
            ),
            "primary_topic": classification.primary_topic,
            "topics": list(classification.topics),
            "content_type": classification.content_type,
            "product_class": classification.product_class,
            "evidence_level": classification.evidence_level,
            "risk_level": classification.risk_level,
            "audience": classification.audience,
            "geography": list(classification.geography),
            "classification_version": TAXONOMY_VERSION,
            "classification_reasons": list(classification.classification_reasons),
            "publication_policy": policy.publication_policy,
            "risk_reasons": list(policy.risk_reasons),
            "risk_policy_version": RISK_POLICY_VERSION,
            "voice_profile_version": VOICE_PROFILE_VERSION,
            "editorial_profile": settings.news_draft_profile,
            "submitted_by": HERMES_SUBMISSION_MARKER,
            "hermes_skill_version": payload.provenance.skill_version,
            "hermes_schema_version": payload.schema_version,
            "hermes_submission_id": submission_id,
            "article_candidate": article_candidate_handoff(
                cluster_id=cluster.id,
                draft_revision=revision,
                primary_topic=classification.primary_topic,
                content_type=classification.content_type,
            ),
        },
        draft_text=draft_text,
        warnings=list(warnings),
        generation_latency_ms=0,
    )
    db.add(draft)
    cluster.latest_draft_revision = revision
    cluster.current_image_revision = 0
    cluster.primary_topic = classification.primary_topic
    cluster.topics = list(classification.topics)
    cluster.content_type = classification.content_type
    cluster.product_class = classification.product_class
    cluster.evidence_level = classification.evidence_level
    cluster.risk_level = classification.risk_level
    cluster.audience = classification.audience
    cluster.geography = list(classification.geography)
    cluster.classification_version = TAXONOMY_VERSION
    cluster.classification_reasons = list(classification.classification_reasons)
    cluster.publication_policy = policy.publication_policy
    cluster.risk_reasons = list(policy.risk_reasons)
    cluster.risk_policy_version = RISK_POLICY_VERSION
    cluster.generation_attempt_count += 1
    transition_news_cluster(db, cluster, "image_pending", reason_code="hermes_draft_received")
    db.flush()
    expires_at = current + timedelta(seconds=settings.hermes_intake_replay_ttl_seconds)
    submission = HermesEditorialSubmission(
        submission_id=submission_id,
        source_id=source.id,
        idempotency_key=payload.idempotency_key,
        request_nonce=payload.request_nonce,
        payload_hash=payload_hash,
        schema_version=payload.schema_version,
        status="accepted",
        cluster_id=cluster.id,
        draft_id=draft.id,
        provider=payload.provenance.provider,
        model=payload.provenance.model,
        prompt_version=payload.provenance.prompt_version,
        skill_version=payload.provenance.skill_version,
        taxonomy_version=TAXONOMY_VERSION,
        risk_policy_version=RISK_POLICY_VERSION,
        source_count=1,
        response_metadata={
            "endpoint": HERMES_INTAKE_ENDPOINT,
            "source_id": source.id,
            "source_content_hash": payload.source.content_hash,
            "publication_policy": policy.publication_policy,
            "risk_reason_count": len(policy.risk_reasons),
        },
        expires_at=expires_at,
        processed_at=current,
    )
    db.add(submission)
    record_audit_event(
        db,
        action="news.hermes_intake_accepted",
        resource_type="hermes_editorial_submission",
        resource_id=submission_id,
        details={
            "source_id": source.id,
            "cluster_id": cluster.id,
            "draft_id": draft.id,
            "schema_version": payload.schema_version,
            "taxonomy_version": TAXONOMY_VERSION,
            "risk_policy_version": RISK_POLICY_VERSION,
            "policy": policy.publication_policy,
        },
    )
    db.flush()
    return _submission_response(db, submission, status="accepted")
