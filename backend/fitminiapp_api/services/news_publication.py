from __future__ import annotations

import hashlib
import hmac
import html
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text
from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.models.news import (
    NewsCluster,
    NewsDraftRevision,
    NewsImageRevision,
    NewsItem,
    NewsPublicationSnapshot,
    NewsReviewDecision,
    NewsReviewDelivery,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.news_content import (
    EditorialContent,
    editorial_content_from_metadata,
)
from fitminiapp_api.services.news_freshness import source_metadata_is_fresh
from fitminiapp_api.services.news_images import current_image
from fitminiapp_api.services.news_ingestion import utcnow
from fitminiapp_api.services.news_origin import is_hermes_origin_draft
from fitminiapp_api.services.news_state import transition_news_cluster

logger = logging.getLogger(__name__)

PublicationMode = Literal["immediate", "scheduled"]
ApprovalStatus = Literal[
    "queued",
    "scheduled",
    "already_queued",
    "stale",
    "unavailable",
    "publishing_disabled",
    "quality_blocked",
    "schedule_invalid",
]
CRITICAL_DRAFT_WARNINGS = {
    "deterministic_fallback_requires_editor",
    "medical_prescription_language",
    "unsupported_number",
    "possible_source_copy",
    "sensational_or_guaranteed_claim",
}
PROHIBITED_EDITORIAL_PATTERNS = (
    "дозиров",
    "принимайте",
    "назначьте",
    "курс стероид",
    "стероидный курс",
    "курс анабол",
    "курс sarm",
    "курс сарм",
    "пептидный курс",
    "схема приема",
    "схема приёма",
)
CLICKBAIT_PATTERNS = ("100%", "гарант", "сенсац", "шокир", "результат без усилий")
PROCESSING_TTL = timedelta(minutes=10)
MAX_PUBLICATION_ATTEMPTS = 5
PUBLICATION_RENDERER_VERSION = "news-publication-html-v1"
TELEGRAM_MESSAGE_LIMIT = 4096
TELEGRAM_PHOTO_CAPTION_LIMIT = 1024
ARTIFACT_HASH_PREFIX_LENGTH = 16


@dataclass(frozen=True)
class ApprovalResult:
    status: ApprovalStatus
    snapshot_id: str | None = None
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublicationPayload:
    snapshot_id: str
    channel_id: int
    text: str
    renderer_version: str
    transport: str
    parse_mode: str | None
    link_preview_disabled: bool
    image_data: bytes | None
    image_content_type: str | None


@dataclass(frozen=True)
class PublicationArtifact:
    text: str
    renderer_version: str
    transport: Literal["message", "photo"]
    parse_mode: Literal["HTML"]
    link_preview_disabled: bool
    visible_length: int
    limit: int


@dataclass(frozen=True)
class PublicationComposition:
    artifact: PublicationArtifact | None
    blockers: tuple[str, ...] = ()
    transport: Literal["message", "photo"] | None = None
    visible_length: int | None = None
    limit: int | None = None


def _cancel_review_deliveries(db: Session, cluster_id: str) -> None:
    draft_ids = [
        row.id
        for row in db.query(NewsDraftRevision.id)
        .filter(NewsDraftRevision.cluster_id == cluster_id)
        .all()
    ]
    if not draft_ids:
        return
    db.query(NewsReviewDelivery).filter(
        NewsReviewDelivery.draft_id.in_(draft_ids),
        NewsReviewDelivery.status.in_({"queued", "processing"}),
    ).update(
        {
            NewsReviewDelivery.status: "cancelled",
            NewsReviewDelivery.processing_started_at: None,
        },
        synchronize_session=False,
    )


def revoke_active_decisions(db: Session, cluster_id: str, *, reason: str) -> None:
    now = utcnow()
    decisions = (
        db.query(NewsReviewDecision)
        .filter(
            NewsReviewDecision.cluster_id == cluster_id,
            NewsReviewDecision.status == "active",
        )
        .all()
    )
    decision_ids = []
    for decision in decisions:
        decision.status = "revoked"
        decision.revoked_at = now
        decision.revocation_reason = reason
        decision_ids.append(decision.id)
    if decision_ids:
        snapshots = db.query(NewsPublicationSnapshot).filter(
            NewsPublicationSnapshot.decision_id.in_(decision_ids),
            NewsPublicationSnapshot.status.in_({"queued", "scheduled", "failed"}),
        )
        for snapshot in snapshots:
            snapshot.status = "cancelled"
            snapshot.last_error_code = "approval_revoked"
            snapshot.processing_started_at = None


def _reviewer_ref(admin_telegram_user_id: int) -> str:
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        f"news-admin:{admin_telegram_user_id}".encode("ascii"),
        hashlib.sha256,
    ).hexdigest()[:24]


def _schedule_utc(
    *,
    mode: PublicationMode,
    scheduled_local: datetime | None,
    timezone_name: str,
    now: datetime,
) -> tuple[datetime, date] | None:
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return None
    if mode == "immediate":
        aware = now.replace(tzinfo=UTC).astimezone(timezone)
        return now, aware.date()
    if scheduled_local is None or scheduled_local.tzinfo is not None:
        return None
    first = scheduled_local.replace(tzinfo=timezone, fold=0)
    second = scheduled_local.replace(tzinfo=timezone, fold=1)
    if first.utcoffset() != second.utcoffset():
        return None
    scheduled_utc = first.astimezone(UTC).replace(tzinfo=None)
    if scheduled_utc.replace(tzinfo=UTC).astimezone(timezone).replace(tzinfo=None) != (
        scheduled_local
    ):
        return None
    minimum = now + timedelta(minutes=settings.news_schedule_min_minutes)
    maximum = now + timedelta(days=settings.news_schedule_max_days)
    if scheduled_utc < minimum or scheduled_utc > maximum:
        return None
    return scheduled_utc, first.date()


def _telegram_character_count(value: str) -> int:
    """Count UTF-16 code units, matching Telegram entity offset semantics."""
    return len(value.encode("utf-16-le")) // 2


def _credential_free_https_url(value: str) -> bool:
    if any(character in value for character in "\r\n<>\"'"):
        return False
    parsed = urlparse(value)
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
    )


def _normalized_paragraphs(value: str) -> tuple[str, ...]:
    return tuple(
        " ".join(paragraph.split())
        for paragraph in re.split(r"\n\s*\n", value.strip())
        if paragraph.strip()
    )


def _sentence_count(value: str) -> int:
    normalized = " ".join(value.split())
    if not normalized:
        return 0
    return len([part for part in re.split(r"(?<=[.!?])\s+", normalized) if part])


def compose_editorial_artifact(
    content: EditorialContent,
    image: NewsImageRevision | None,
    *,
    trusted_source_url: str,
) -> PublicationComposition:
    blockers: list[str] = []
    if content.source_url != trusted_source_url:
        blockers.append("trusted_source_mismatch")
    if not _credential_free_https_url(trusted_source_url):
        blockers.append("trusted_source_invalid")
    paragraphs = _normalized_paragraphs(content.summary)
    if not 1 <= len(paragraphs) <= 2:
        blockers.append("summary_paragraph_count_invalid")
    why_it_matters = " ".join(content.why_it_matters.split())
    if _sentence_count(why_it_matters) > 1:
        blockers.append("why_it_matters_sentence_count_invalid")
    if blockers:
        return PublicationComposition(artifact=None, blockers=tuple(dict.fromkeys(blockers)))

    headline = " ".join(content.headline.split())
    html_parts = [f"<b>{html.escape(headline, quote=False)}</b>"]
    visible_parts = [headline]
    for paragraph in paragraphs:
        html_parts.append(html.escape(paragraph, quote=False))
        visible_parts.append(paragraph)
    if why_it_matters:
        html_parts.append(html.escape(why_it_matters, quote=False))
        visible_parts.append(why_it_matters)
    html_parts.append(f'<a href="{html.escape(trusted_source_url, quote=True)}">Источник</a>')
    visible_parts.append("Источник")
    rendered = "\n\n".join(html_parts)
    visible_length = _telegram_character_count("\n\n".join(visible_parts))
    transport: Literal["message", "photo"] = "photo" if image is not None else "message"
    limit = TELEGRAM_PHOTO_CAPTION_LIMIT if image is not None else TELEGRAM_MESSAGE_LIMIT
    if visible_length > limit:
        blocker = (
            "telegram_photo_caption_too_long" if image is not None else "telegram_message_too_long"
        )
        return PublicationComposition(
            artifact=None,
            blockers=(blocker,),
            transport=transport,
            visible_length=visible_length,
            limit=limit,
        )
    return PublicationComposition(
        artifact=PublicationArtifact(
            text=rendered,
            renderer_version=PUBLICATION_RENDERER_VERSION,
            transport=transport,
            parse_mode="HTML",
            link_preview_disabled=True,
            visible_length=visible_length,
            limit=limit,
        ),
        transport=transport,
        visible_length=visible_length,
        limit=limit,
    )


def compose_publication_artifact(
    draft: NewsDraftRevision,
    image: NewsImageRevision | None,
    *,
    trusted_source_url: str,
) -> PublicationComposition:
    content = editorial_content_from_metadata(
        draft.evidence_metadata,
        fallback_text=draft.draft_text,
    )
    if content is None:
        return PublicationComposition(
            artifact=None,
            blockers=("editorial_structure_invalid",),
        )
    return compose_editorial_artifact(
        content,
        image,
        trusted_source_url=trusted_source_url,
    )


def publication_content_hash(
    artifact: PublicationArtifact,
    *,
    image_sha256: str | None,
    channel_id: int,
) -> str:
    return hashlib.sha256(
        "\x00".join(
            (
                artifact.text,
                image_sha256 or "none",
                str(channel_id),
                artifact.renderer_version,
                artifact.transport,
                artifact.parse_mode,
                "link-preview-disabled"
                if artifact.link_preview_disabled
                else "link-preview-default",
            )
        ).encode("utf-8")
    ).hexdigest()


def publication_quality_blockers(
    draft: NewsDraftRevision,
    image: NewsImageRevision | None,
    *,
    trusted_source_url: str,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if not draft.evidence_item_ids or not draft.source_digest:
        blockers.append("source_missing")
    blockers.extend(
        f"unresolved_warning:{warning}"
        for warning in draft.warnings
        if warning in CRITICAL_DRAFT_WARNINGS
    )
    text_value = draft.draft_text
    composition = compose_publication_artifact(
        draft,
        image,
        trusted_source_url=trusted_source_url,
    )
    blockers.extend(composition.blockers)
    content = editorial_content_from_metadata(
        draft.evidence_metadata,
        fallback_text=text_value,
    )
    if not isinstance(draft.evidence_metadata.get("source_published_at"), str):
        blockers.append("source_date_missing")
    elif not source_metadata_is_fresh(draft.evidence_metadata, now=utcnow()):
        blockers.append("source_not_current_month")
    if content is not None and draft.evidence_metadata.get("topic") == "research":
        research_context = f"{content.summary} {content.why_it_matters}".casefold()
        if not any(
            marker in research_context
            for marker in ("огранич", "контекст", "групп", "выборк", "применим")
        ):
            blockers.append("research_context_or_limitations_missing")
    lowered = text_value.casefold()
    if any(pattern in lowered for pattern in PROHIBITED_EDITORIAL_PATTERNS):
        blockers.append("prohibited_medical_or_aas_language")
    if any(pattern in lowered for pattern in CLICKBAIT_PATTERNS):
        blockers.append("clickbait_or_guarantee_language")
    return tuple(dict.fromkeys(blockers))


def _idempotency_key(
    *,
    draft: NewsDraftRevision,
    image: NewsImageRevision | None,
    channel_id: int,
    mode: PublicationMode,
    scheduled_for_utc: datetime,
    reviewer_ref: str,
    urgent_override: bool,
    content_hash: str,
) -> str:
    value = ":".join(
        (
            draft.id,
            image.id if image is not None else "none",
            str(channel_id),
            mode,
            scheduled_for_utc.isoformat(timespec="seconds"),
            reviewer_ref,
            "urgent" if urgent_override else "normal",
            content_hash,
        )
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def approve_publication(
    db: Session,
    *,
    draft_id: str,
    expected_image_revision: int,
    admin_telegram_user_id: int,
    mode: PublicationMode,
    scheduled_local: datetime | None = None,
    timezone_name: str | None = None,
    urgent_override: bool = False,
    expected_artifact_hash: str,
) -> ApprovalResult:
    if not settings.news_publication_enabled or settings.news_channel_id is None:
        return ApprovalResult(status="publishing_disabled")
    draft = db.get(NewsDraftRevision, draft_id)
    if draft is None:
        return ApprovalResult(status="unavailable")
    if not is_hermes_origin_draft(draft):
        return ApprovalResult(status="unavailable")
    cluster = (
        db.query(NewsCluster).filter(NewsCluster.id == draft.cluster_id).with_for_update().first()
    )
    if cluster is None:
        return ApprovalResult(status="unavailable")
    existing_exact = (
        db.query(NewsPublicationSnapshot)
        .filter(
            NewsPublicationSnapshot.cluster_id == cluster.id,
            NewsPublicationSnapshot.target_channel_id == settings.news_channel_id,
            NewsPublicationSnapshot.renderer_version == PUBLICATION_RENDERER_VERSION,
            NewsPublicationSnapshot.text_revision_id == draft.id,
            NewsPublicationSnapshot.image_revision_id
            == (
                db.query(NewsImageRevision.id)
                .filter(
                    NewsImageRevision.cluster_id == cluster.id,
                    NewsImageRevision.revision == expected_image_revision,
                )
                .scalar_subquery()
                if expected_image_revision > 0
                else None
            ),
            NewsPublicationSnapshot.status.in_(
                {"queued", "scheduled", "processing", "published", "uncertain"}
            ),
        )
        .order_by(NewsPublicationSnapshot.created_at.desc())
        .first()
    )
    if existing_exact is not None:
        if not re.fullmatch(r"[0-9a-f]{16}", expected_artifact_hash) or not (
            hmac.compare_digest(
                existing_exact.content_hash[:ARTIFACT_HASH_PREFIX_LENGTH],
                expected_artifact_hash,
            )
        ):
            return ApprovalResult(status="stale")
        logger.info(
            "news_publication_duplicate_suppressed",
            extra={"pipeline_stage": "approval", "outcome": "already_queued"},
        )
        return ApprovalResult(status="already_queued", snapshot_id=existing_exact.id)
    if (
        cluster.status != "awaiting_review"
        or draft.revision != cluster.latest_draft_revision
        or expected_image_revision != cluster.current_image_revision
    ):
        return ApprovalResult(status="stale")
    image = current_image(db, cluster)
    if expected_image_revision > 0 and (image is None or image.text_revision_id != draft.id):
        return ApprovalResult(status="stale")
    primary = db.get(NewsItem, draft.primary_item_id)
    trusted_source_url = str(draft.evidence_metadata.get("trusted_source_url", "")) or (
        (primary.primary_url or primary.canonical_url) if primary is not None else ""
    )
    blockers = publication_quality_blockers(
        draft,
        image,
        trusted_source_url=trusted_source_url,
    )
    composition = compose_publication_artifact(
        draft,
        image,
        trusted_source_url=trusted_source_url,
    )
    if blockers or composition.artifact is None:
        logger.info(
            "news_publication_quality_blocked",
            extra={
                "pipeline_stage": "approval",
                "outcome": "quality_blocked",
                "blocker_count": len(blockers),
            },
        )
        return ApprovalResult(status="quality_blocked", blockers=blockers)
    artifact = composition.artifact
    content_hash = publication_content_hash(
        artifact,
        image_sha256=image.sha256 if image is not None else None,
        channel_id=settings.news_channel_id,
    )
    if not re.fullmatch(r"[0-9a-f]{16}", expected_artifact_hash) or not (
        hmac.compare_digest(
            content_hash[:ARTIFACT_HASH_PREFIX_LENGTH],
            expected_artifact_hash,
        )
    ):
        return ApprovalResult(status="stale")
    timezone_value = timezone_name or settings.news_publication_timezone
    now = utcnow()
    schedule = _schedule_utc(
        mode=mode,
        scheduled_local=scheduled_local,
        timezone_name=timezone_value,
        now=now,
    )
    if schedule is None:
        return ApprovalResult(status="schedule_invalid")
    scheduled_for_utc, local_date = schedule
    if not source_metadata_is_fresh(
        draft.evidence_metadata,
        now=scheduled_for_utc,
    ):
        return ApprovalResult(
            status="quality_blocked",
            blockers=("source_not_current_month_at_publication",),
        )
    reviewer_ref = _reviewer_ref(admin_telegram_user_id)
    key = _idempotency_key(
        draft=draft,
        image=image,
        channel_id=settings.news_channel_id,
        mode=mode,
        scheduled_for_utc=scheduled_for_utc,
        reviewer_ref=reviewer_ref,
        urgent_override=urgent_override,
        content_hash=content_hash,
    )
    existing = (
        db.query(NewsPublicationSnapshot)
        .filter(NewsPublicationSnapshot.idempotency_key == key)
        .first()
    )
    if existing is not None:
        return ApprovalResult(status="already_queued", snapshot_id=existing.id)
    revoke_active_decisions(db, cluster.id, reason="new_exact_approval")
    approved_at = now
    decision = NewsReviewDecision(
        id=secrets.token_hex(16),
        cluster_id=cluster.id,
        text_revision_id=draft.id,
        image_revision_id=image.id if image is not None else None,
        explicit_no_image=image is None,
        target_channel_id=settings.news_channel_id,
        publication_mode=mode,
        scheduled_for_utc=scheduled_for_utc if mode == "scheduled" else None,
        timezone=timezone_value,
        reviewer_ref=reviewer_ref,
        approved_at=approved_at,
        status="active",
    )
    snapshot = NewsPublicationSnapshot(
        id=secrets.token_hex(16),
        decision_id=decision.id,
        cluster_id=cluster.id,
        text_revision_id=draft.id,
        image_revision_id=image.id if image is not None else None,
        target_channel_id=settings.news_channel_id,
        target_channel_username=settings.news_channel_username,
        publication_mode=mode,
        scheduled_for_utc=scheduled_for_utc,
        publication_local_date=local_date,
        timezone=timezone_value,
        reviewer_ref=reviewer_ref,
        approved_at=approved_at,
        status="queued" if mode == "immediate" else "scheduled",
        urgent_override=urgent_override,
        publication_text=artifact.text,
        renderer_version=artifact.renderer_version,
        transport=artifact.transport,
        parse_mode=artifact.parse_mode,
        link_preview_disabled=artifact.link_preview_disabled,
        image_sha256=image.sha256 if image is not None else None,
        content_hash=content_hash,
        idempotency_key=key,
        next_attempt_at=scheduled_for_utc,
    )
    db.add(decision)
    db.flush()
    db.add(snapshot)
    _cancel_review_deliveries(db, cluster.id)
    transition_news_cluster(
        db,
        cluster,
        "publication_approved" if mode == "immediate" else "publication_scheduled",
        reason_code="owner_exact_revision_approved",
        actor_ref=reviewer_ref,
    )
    record_audit_event(
        db,
        action="news.publication_approved",
        resource_type="news_publication_snapshot",
        resource_id=snapshot.id,
        details={
            "mode": mode,
            "image_revision": expected_image_revision,
            "urgent_override": urgent_override,
            "content_hash": content_hash,
        },
    )
    db.flush()
    logger.info(
        "news_publication_approved",
        extra={
            "pipeline_stage": "approval",
            "outcome": mode,
            "urgent_override": urgent_override,
        },
    )
    return ApprovalResult(
        status="queued" if mode == "immediate" else "scheduled", snapshot_id=snapshot.id
    )


def _publication_lock(db: Session, row: NewsPublicationSnapshot) -> None:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        lock_value = int.from_bytes(
            hashlib.sha256(
                f"{row.target_channel_id}:{row.publication_local_date.isoformat()}".encode()
            ).digest()[:8],
            signed=True,
        )
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_value})


def claim_due_publications(db: Session, *, limit: int = 5) -> list[str]:
    now = utcnow()
    stale_before = now - PROCESSING_TTL
    stale_rows = (
        db.query(NewsPublicationSnapshot)
        .filter(
            NewsPublicationSnapshot.status == "processing",
            NewsPublicationSnapshot.processing_started_at < stale_before,
        )
        .all()
    )
    for row in stale_rows:
        row.status = "uncertain"
        row.last_error_code = "worker_interrupted_send_uncertain"
        row.processing_started_at = None
    candidates = (
        db.query(NewsPublicationSnapshot)
        .filter(
            NewsPublicationSnapshot.status.in_({"queued", "scheduled"}),
            NewsPublicationSnapshot.next_attempt_at <= now,
        )
        .order_by(
            NewsPublicationSnapshot.next_attempt_at.asc(),
            NewsPublicationSnapshot.created_at.asc(),
        )
        .limit(limit)
        .with_for_update(skip_locked=True)
        .all()
    )
    claimed: list[str] = []
    missed_before = now - timedelta(minutes=settings.news_schedule_missed_minutes)
    for row in candidates:
        cluster = db.get(NewsCluster, row.cluster_id)
        draft = db.get(NewsDraftRevision, row.text_revision_id)
        if draft is None or not is_hermes_origin_draft(draft):
            row.status = "cancelled"
            row.last_error_code = "non_hermes_news_pipeline_retired"
            row.processing_started_at = None
            if cluster is not None and cluster.status not in {
                "published",
                "rejected",
                "rejected_by_rules",
            }:
                transition_news_cluster(
                    db,
                    cluster,
                    "rejected",
                    reason_code="non_hermes_news_pipeline_retired",
                )
            continue

        if not source_metadata_is_fresh(
            draft.evidence_metadata,
            now=now,
        ):
            row.status = "failed"
            row.last_error_code = "source_not_current_month"
            if cluster is not None:
                transition_news_cluster(
                    db,
                    cluster,
                    "publication_failed",
                    reason_code="source_not_current_month",
                )
                cluster.delivery_round += 1
            continue
        if row.publication_mode == "immediate":
            try:
                publication_timezone = ZoneInfo(row.timezone)
            except ZoneInfoNotFoundError:
                row.status = "failed"
                row.last_error_code = "publication_timezone_invalid"
                if cluster is not None:
                    transition_news_cluster(
                        db,
                        cluster,
                        "publication_failed",
                        reason_code="publication_timezone_invalid",
                    )
                    cluster.delivery_round += 1
                continue
            row.publication_local_date = (
                now.replace(tzinfo=UTC).astimezone(publication_timezone).date()
            )
        if row.publication_mode == "scheduled" and row.scheduled_for_utc < missed_before:
            row.status = "failed"
            row.last_error_code = "schedule_missed"
            if cluster is not None:
                transition_news_cluster(
                    db, cluster, "publication_failed", reason_code="schedule_missed"
                )
                cluster.delivery_round += 1
            continue
        _publication_lock(db, row)
        if not row.urgent_override:
            occupied = (
                db.query(NewsPublicationSnapshot.id)
                .filter(
                    NewsPublicationSnapshot.target_channel_id == row.target_channel_id,
                    NewsPublicationSnapshot.publication_local_date == row.publication_local_date,
                    NewsPublicationSnapshot.id != row.id,
                    NewsPublicationSnapshot.urgent_override.is_(False),
                    NewsPublicationSnapshot.status.in_({"processing", "published", "uncertain"}),
                )
                .count()
            )
            if occupied >= settings.news_daily_publication_limit:
                row.status = "failed"
                row.last_error_code = "daily_cap_reached"
                if cluster is not None:
                    transition_news_cluster(
                        db, cluster, "publication_failed", reason_code="daily_cap_reached"
                    )
                    cluster.delivery_round += 1
                continue
        row.status = "processing"
        row.processing_started_at = now
        row.attempt_count += 1
        claimed.append(row.id)
    return claimed


def publication_payload(db: Session, snapshot_id: str) -> PublicationPayload | None:
    row = db.get(NewsPublicationSnapshot, snapshot_id)
    if row is None or row.status != "processing":
        return None
    draft = db.get(NewsDraftRevision, row.text_revision_id)
    if draft is None or not is_hermes_origin_draft(draft):
        row.status = "cancelled"
        row.last_error_code = "non_hermes_news_pipeline_retired"
        row.processing_started_at = None
        return None
    image = db.get(NewsImageRevision, row.image_revision_id) if row.image_revision_id else None
    if image is not None and image.sha256 != row.image_sha256:
        row.status = "failed"
        row.last_error_code = "snapshot_image_hash_mismatch"
        row.processing_started_at = None
        return None
    expected_transport: Literal["message", "photo"] = "photo" if image is not None else "message"
    if row.transport != expected_transport:
        row.status = "failed"
        row.last_error_code = "snapshot_transport_mismatch"
        row.processing_started_at = None
        return None
    if (
        row.renderer_version != PUBLICATION_RENDERER_VERSION
        or row.parse_mode != "HTML"
        or not row.link_preview_disabled
    ):
        row.status = "failed"
        row.last_error_code = "snapshot_renderer_contract_mismatch"
        row.processing_started_at = None
        return None
    stored_artifact = PublicationArtifact(
        text=row.publication_text,
        renderer_version=row.renderer_version,
        transport=expected_transport,
        parse_mode="HTML",
        link_preview_disabled=row.link_preview_disabled,
        visible_length=0,
        limit=0,
    )
    if (
        publication_content_hash(
            stored_artifact,
            image_sha256=row.image_sha256,
            channel_id=row.target_channel_id,
        )
        != row.content_hash
    ):
        row.status = "failed"
        row.last_error_code = "snapshot_content_hash_mismatch"
        row.processing_started_at = None
        return None
    return PublicationPayload(
        snapshot_id=row.id,
        channel_id=row.target_channel_id,
        text=row.publication_text,
        renderer_version=row.renderer_version,
        transport=row.transport,
        parse_mode=row.parse_mode,
        link_preview_disabled=row.link_preview_disabled,
        image_data=image.image_data if image is not None else None,
        image_content_type=image.content_type if image is not None else None,
    )


def mark_publication_succeeded(
    db: Session,
    snapshot_id: str,
    *,
    message_id: int,
    message_date: datetime,
) -> None:
    row = db.get(NewsPublicationSnapshot, snapshot_id)
    if row is None or row.status != "processing":
        return
    row.status = "published"
    row.telegram_message_id = message_id
    row.telegram_message_date = message_date
    row.published_at = utcnow()
    row.processing_started_at = None
    row.last_error_code = None
    if row.target_channel_username:
        row.telegram_permalink = f"https://t.me/{row.target_channel_username}/{message_id}"
    decision = db.get(NewsReviewDecision, row.decision_id)
    if decision is not None:
        decision.status = "consumed"
    cluster = db.get(NewsCluster, row.cluster_id)
    if cluster is not None:
        transition_news_cluster(db, cluster, "published", reason_code="telegram_publish_succeeded")
    record_audit_event(
        db,
        action="news.published",
        resource_type="news_publication_snapshot",
        resource_id=row.id,
        details={"message_id": message_id, "content_hash": row.content_hash},
    )
    logger.info(
        "news_publication_succeeded",
        extra={
            "pipeline_stage": "publication",
            "outcome": "published",
            "attempt_count": row.attempt_count,
            "telegram_message_id": message_id,
        },
    )


def mark_publication_failed(
    db: Session,
    snapshot_id: str,
    *,
    error_code: str,
    retry_after: timedelta | None = None,
    uncertain: bool = False,
    terminal: bool = False,
) -> None:
    row = db.get(NewsPublicationSnapshot, snapshot_id)
    if row is None or row.status != "processing":
        return
    row.processing_started_at = None
    row.last_error_code = error_code
    if uncertain:
        row.status = "uncertain"
    elif terminal or row.attempt_count >= MAX_PUBLICATION_ATTEMPTS:
        row.status = "failed"
    else:
        row.status = "queued" if row.publication_mode == "immediate" else "scheduled"
        row.next_attempt_at = utcnow() + (retry_after or timedelta(minutes=2**row.attempt_count))
    if row.status == "failed":
        cluster = db.get(NewsCluster, row.cluster_id)
        if cluster is not None:
            transition_news_cluster(
                db, cluster, "publication_failed", reason_code="telegram_publish_failed"
            )
            cluster.delivery_round += 1
    db.flush()
    logger.warning(
        "news_publication_attempt_recorded",
        extra={
            "pipeline_stage": "publication",
            "outcome": row.status,
            "reason": error_code,
            "attempt_count": row.attempt_count,
        },
    )


def reconcile_uncertain_publication(
    db: Session,
    *,
    snapshot_id: str,
    admin_telegram_user_id: int,
    channel_message_id: int,
) -> bool:
    row = db.get(NewsPublicationSnapshot, snapshot_id)
    if row is None or row.status != "uncertain" or channel_message_id < 1:
        return False
    reviewer_ref = _reviewer_ref(admin_telegram_user_id)
    row.status = "published"
    row.telegram_message_id = channel_message_id
    row.telegram_message_date = utcnow()
    row.published_at = utcnow()
    row.last_error_code = "owner_reconciled_uncertain_send"
    if row.target_channel_username:
        row.telegram_permalink = f"https://t.me/{row.target_channel_username}/{channel_message_id}"
    cluster = db.get(NewsCluster, row.cluster_id)
    if cluster is not None:
        transition_news_cluster(
            db,
            cluster,
            "published",
            reason_code="owner_reconciled_uncertain_send",
            actor_ref=reviewer_ref,
        )
    record_audit_event(
        db,
        action="news.publication_reconciled",
        resource_type="news_publication_snapshot",
        resource_id=row.id,
        details={"message_id": channel_message_id},
    )
    return True


def retry_uncertain_publication(
    db: Session,
    *,
    snapshot_id: str,
    admin_telegram_user_id: int,
) -> bool:
    row = db.query(NewsPublicationSnapshot).filter_by(id=snapshot_id).with_for_update().first()
    if row is None or row.status != "uncertain":
        return False
    row.status = "queued" if row.publication_mode == "immediate" else "scheduled"
    row.next_attempt_at = utcnow()
    row.last_error_code = "owner_confirmed_message_not_found_retry"
    row.processing_started_at = None
    reviewer_ref = _reviewer_ref(admin_telegram_user_id)
    record_audit_event(
        db,
        action="news.publication_retry_confirmed",
        resource_type="news_publication_snapshot",
        resource_id=row.id,
        details={"attempt_count": row.attempt_count},
    )
    cluster = db.get(NewsCluster, row.cluster_id)
    if cluster is not None:
        transition_news_cluster(
            db,
            cluster,
            "publication_approved"
            if row.publication_mode == "immediate"
            else "publication_scheduled",
            reason_code="owner_confirmed_message_not_found_retry",
            actor_ref=reviewer_ref,
        )
    db.flush()
    return True
