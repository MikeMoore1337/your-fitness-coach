from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.news import (
    NewsCluster,
    NewsDraftRevision,
    NewsEditorialAction,
    NewsImageRevision,
    NewsItem,
    NewsPublicationSnapshot,
    NewsReviewDecision,
    NewsReviewDelivery,
    NewsStateTransition,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.news_content import parse_editorial_content
from fitminiapp_api.services.news_drafts import quality_warnings
from fitminiapp_api.services.news_freshness import source_metadata_is_current_month
from fitminiapp_api.services.news_images import create_uploaded_image_revision, current_image
from fitminiapp_api.services.news_ingestion import utcnow
from fitminiapp_api.services.news_publication import (
    ARTIFACT_HASH_PREFIX_LENGTH,
    PUBLICATION_RENDERER_VERSION,
    PublicationArtifact,
    compose_publication_artifact,
    publication_content_hash,
    publication_quality_blockers,
    revoke_active_decisions,
)
from fitminiapp_api.services.news_state import transition_news_cluster

EditorialAction = Literal["skip", "defer", "regenerate", "accept_for_design"]
type ModerationStatus = Literal[
    "accepted",
    "queued",
    "deferred",
    "already_processed",
    "stale",
    "limit_reached",
    "unavailable",
]
TERMINAL_CLUSTER_STATUSES = {
    "rejected",
    "accepted_for_design",
    "rejected_by_rules",
    "published",
}
MAX_REVIEW_MESSAGE_CHARS = 4000
MAX_IMAGE_REVISIONS = 10
REVISION_EDITABLE_STATUSES = {
    "awaiting_review",
    "publication_approved",
    "publication_scheduled",
    "publication_failed",
}
OWNER_EDIT_REVALIDATED_WARNINGS = {
    "deterministic_fallback_requires_editor",
    "invalid_draft_schema",
    "medical_prescription_language",
    "provider_unavailable",
    "unsupported_number",
    "possible_source_copy",
    "sensational_or_guaranteed_claim",
    "telegram_photo_caption_too_long",
}


@dataclass(frozen=True)
class ModerationResult:
    status: ModerationStatus
    cluster_status: str | None = None


@dataclass(frozen=True)
class ReviewArtifact:
    artifact: PublicationArtifact | None
    image: NewsImageRevision | None
    artifact_hash: str | None
    blockers: tuple[str, ...]
    transport: Literal["message", "photo"] | None
    visible_length: int | None
    limit: int | None


HERMES_SUBMISSION_MARKER = "hermes_narrow_intake"
PREVIEW_OPERATIONAL_BLOCKERS = frozenset({"publishing_disabled", "channel_rights_missing"})
LEGACY_REVIEW_DELIVERY_DISABLED = "legacy_review_delivery_disabled"


def is_hermes_origin_draft(draft: NewsDraftRevision) -> bool:
    """Return whether a revision came through the canonical Hermes intake marker."""

    return draft.evidence_metadata.get("submitted_by") == HERMES_SUBMISSION_MARKER


def review_delivery_blockers(
    draft: NewsDraftRevision,
    review: ReviewArtifact,
) -> tuple[str, ...]:
    """Return blockers that make an owner Telegram delivery unsafe or misleading."""

    is_hermes_draft = is_hermes_origin_draft(draft)
    blockers: list[str] = []
    if is_hermes_draft:
        blockers.extend(
            blocker for blocker in review.blockers if blocker not in PREVIEW_OPERATIONAL_BLOCKERS
        )
        blockers.extend(
            f"unresolved_warning:{warning}"
            for warning in draft.warnings
            if isinstance(warning, str) and warning
        )
    if is_hermes_draft and review.artifact is None:
        blockers.append("preview_artifact_unavailable")
    if is_hermes_draft and (review.image is None or not review.image.image_data):
        blockers.append("preview_image_missing")
    return tuple(dict.fromkeys(blockers))


def editorial_actor_ref(telegram_user_id: int) -> str:
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        f"news-admin:{telegram_user_id}".encode("ascii"),
        hashlib.sha256,
    ).hexdigest()[:24]


def callback_data(action: EditorialAction, draft_id: str) -> str:
    code = {
        "skip": "s",
        "defer": "d",
        "regenerate": "r",
        "accept_for_design": "a",
    }[action]
    value = f"news:{code}:{draft_id}"
    if len(value.encode("utf-8")) > 64:
        raise ValueError("callback_data_too_long")
    return value


def publishing_callback_data(
    action: str,
    draft_id: str,
    image_revision: int,
    artifact_hash: str | None = None,
) -> str:
    value = f"newsp:{action}:{draft_id}:{image_revision}"
    if artifact_hash is not None:
        value += f":{artifact_hash[:ARTIFACT_HASH_PREFIX_LENGTH]}"
    if len(value.encode("utf-8")) > 64:
        raise ValueError("callback_data_too_long")
    return value


def latest_draft(db: Session, cluster: NewsCluster) -> NewsDraftRevision | None:
    if cluster.latest_draft_revision < 1:
        return None
    return (
        db.query(NewsDraftRevision)
        .filter(
            NewsDraftRevision.cluster_id == cluster.id,
            NewsDraftRevision.revision == cluster.latest_draft_revision,
        )
        .first()
    )


def edit_text_revision(
    db: Session,
    *,
    draft_id: str,
    expected_image_revision: int,
    admin_telegram_user_id: int,
    draft_text: str,
) -> ModerationResult:
    clean_text = draft_text.strip()
    if not 100 <= len(clean_text) <= settings.news_draft_max_chars:
        return ModerationResult(status="unavailable")
    editorial_content = parse_editorial_content(clean_text)
    if editorial_content is None:
        return ModerationResult(status="unavailable")
    draft = db.get(NewsDraftRevision, draft_id)
    if draft is None:
        return ModerationResult(status="unavailable")
    cluster = db.query(NewsCluster).filter_by(id=draft.cluster_id).with_for_update().first()
    if (
        cluster is None
        or cluster.status not in REVISION_EDITABLE_STATUSES
        or draft.revision != cluster.latest_draft_revision
        or expected_image_revision != cluster.current_image_revision
    ):
        return ModerationResult(status="stale")
    actor_ref = editorial_actor_ref(admin_telegram_user_id)
    primary = db.get(NewsItem, draft.primary_item_id)
    if primary is None:
        return ModerationResult(status="unavailable")
    trusted_source_url = str(
        draft.evidence_metadata.get(
            "trusted_source_url",
            (primary.primary_url or primary.canonical_url) if primary is not None else "",
        )
    )
    if editorial_content.source_url != trusted_source_url:
        return ModerationResult(status="unavailable")
    revalidated_warnings = quality_warnings(
        editorial_content.fields(),
        source_title=primary.title,
        source_summary=primary.summary,
    )
    preserved_warnings = tuple(
        warning for warning in draft.warnings if warning not in OWNER_EDIT_REVALIDATED_WARNINGS
    )
    revoke_active_decisions(db, cluster.id, reason="text_revision_changed")
    revision = cluster.latest_draft_revision + 1
    row = NewsDraftRevision(
        id=secrets.token_hex(16),
        cluster_id=cluster.id,
        primary_item_id=draft.primary_item_id,
        revision=revision,
        provider="owner_edit",
        model="none",
        prompt_version="owner-edit-v1",
        source_digest=draft.source_digest,
        evidence_item_ids=list(draft.evidence_item_ids),
        evidence_metadata={
            **dict(draft.evidence_metadata),
            "editorial_contract_version": "news-editorial-v2",
            "editorial_fields": editorial_content.fields(),
            "trusted_source_url": trusted_source_url,
            "source_published_at": (
                primary.published_at.isoformat()
                if primary.published_at is not None
                else draft.evidence_metadata.get("source_published_at")
            ),
        },
        draft_text=clean_text,
        warnings=list(dict.fromkeys((*preserved_warnings, *revalidated_warnings))),
        generation_latency_ms=0,
    )
    db.add(row)
    cluster.latest_draft_revision = revision
    cluster.current_image_revision = 0
    cluster.delivery_round += 1
    _cancel_pending_deliveries(db, draft.id)
    next_status = (
        "image_pending" if cluster.latest_image_revision < MAX_IMAGE_REVISIONS else "draft_ready"
    )
    transition_news_cluster(
        db,
        cluster,
        next_status,
        reason_code=(
            "owner_text_revision_created"
            if next_status == "image_pending"
            else "owner_text_revision_created_without_image_at_limit"
        ),
        actor_ref=actor_ref,
    )
    record_audit_event(
        db,
        action="news.text_edited",
        resource_type="news_cluster",
        resource_id=cluster.id,
        details={"revision": revision},
    )
    db.flush()
    return ModerationResult(status="queued", cluster_status=cluster.status)


def queue_image_regeneration(
    db: Session,
    *,
    draft_id: str,
    expected_image_revision: int,
    admin_telegram_user_id: int,
) -> ModerationResult:
    draft = db.get(NewsDraftRevision, draft_id)
    if draft is None:
        return ModerationResult(status="unavailable")
    cluster = db.query(NewsCluster).filter_by(id=draft.cluster_id).with_for_update().first()
    if (
        cluster is None
        or cluster.status not in REVISION_EDITABLE_STATUSES
        or draft.revision != cluster.latest_draft_revision
        or expected_image_revision != cluster.current_image_revision
    ):
        return ModerationResult(status="stale")
    if cluster.latest_image_revision >= MAX_IMAGE_REVISIONS:
        return ModerationResult(status="limit_reached", cluster_status=cluster.status)
    actor_ref = editorial_actor_ref(admin_telegram_user_id)
    revoke_active_decisions(db, cluster.id, reason="image_regeneration_requested")
    cluster.delivery_round += 1
    _cancel_pending_deliveries(db, draft.id)
    transition_news_cluster(
        db,
        cluster,
        "image_pending",
        reason_code="owner_image_regeneration_requested",
        actor_ref=actor_ref,
    )
    return ModerationResult(status="queued", cluster_status=cluster.status)


def remove_current_image(
    db: Session,
    *,
    draft_id: str,
    expected_image_revision: int,
    admin_telegram_user_id: int,
) -> ModerationResult:
    draft = db.get(NewsDraftRevision, draft_id)
    if draft is None:
        return ModerationResult(status="unavailable")
    cluster = db.query(NewsCluster).filter_by(id=draft.cluster_id).with_for_update().first()
    if (
        cluster is None
        or cluster.status not in REVISION_EDITABLE_STATUSES
        or draft.revision != cluster.latest_draft_revision
        or expected_image_revision != cluster.current_image_revision
    ):
        return ModerationResult(status="stale")
    actor_ref = editorial_actor_ref(admin_telegram_user_id)
    revoke_active_decisions(db, cluster.id, reason="image_removed")
    cluster.current_image_revision = 0
    cluster.delivery_round += 1
    _cancel_pending_deliveries(db, draft.id)
    transition_news_cluster(
        db, cluster, "draft_ready", reason_code="owner_image_removed", actor_ref=actor_ref
    )
    record_audit_event(
        db,
        action="news.image_removed",
        resource_type="news_cluster",
        resource_id=cluster.id,
        details={"text_revision": draft.revision},
    )
    return ModerationResult(status="queued", cluster_status=cluster.status)


def replace_current_image(
    db: Session,
    *,
    draft_id: str,
    expected_image_revision: int,
    admin_telegram_user_id: int,
    image_data: bytes,
) -> ModerationResult:
    draft = db.get(NewsDraftRevision, draft_id)
    if draft is None:
        return ModerationResult(status="unavailable")
    cluster = db.query(NewsCluster).filter_by(id=draft.cluster_id).with_for_update().first()
    if (
        cluster is None
        or cluster.status not in REVISION_EDITABLE_STATUSES
        or draft.revision != cluster.latest_draft_revision
        or expected_image_revision != cluster.current_image_revision
    ):
        return ModerationResult(status="stale")
    if cluster.latest_image_revision >= MAX_IMAGE_REVISIONS:
        return ModerationResult(status="limit_reached", cluster_status=cluster.status)
    revoke_active_decisions(db, cluster.id, reason="image_replaced")
    create_uploaded_image_revision(db, cluster, draft, image_data)
    cluster.delivery_round += 1
    _cancel_pending_deliveries(db, draft.id)
    record_audit_event(
        db,
        action="news.image_replaced",
        resource_type="news_cluster",
        resource_id=cluster.id,
        details={"image_revision": cluster.current_image_revision},
    )
    return ModerationResult(status="queued", cluster_status=cluster.status)


def _cancel_pending_deliveries(db: Session, draft_id: str) -> None:
    db.flush()
    db.query(NewsReviewDelivery).filter(
        NewsReviewDelivery.draft_id == draft_id,
        NewsReviewDelivery.status.in_({"queued", "processing"}),
    ).update(
        {
            NewsReviewDelivery.status: "cancelled",
            NewsReviewDelivery.processing_started_at: None,
        },
        synchronize_session=False,
    )


def moderate_draft(
    db: Session,
    *,
    draft_id: str,
    admin_telegram_user_id: int,
    action: EditorialAction,
) -> ModerationResult:
    draft = db.get(NewsDraftRevision, draft_id)
    if draft is None:
        return ModerationResult(status="unavailable")
    cluster = (
        db.query(NewsCluster).filter(NewsCluster.id == draft.cluster_id).with_for_update().first()
    )
    if cluster is None:
        return ModerationResult(status="unavailable")
    actor_ref = editorial_actor_ref(admin_telegram_user_id)
    prior = (
        db.query(NewsEditorialAction)
        .filter(
            NewsEditorialAction.draft_id == draft.id,
            NewsEditorialAction.actor_ref == actor_ref,
            NewsEditorialAction.action == action,
        )
        .first()
    )
    if prior is not None:
        return ModerationResult(status="already_processed", cluster_status=cluster.status)
    if (
        draft.revision != cluster.latest_draft_revision
        or cluster.status in TERMINAL_CLUSTER_STATUSES
        or cluster.status != "awaiting_review"
    ):
        return ModerationResult(status="stale", cluster_status=cluster.status)

    result_status: ModerationStatus
    outcome = "applied"
    if action == "skip":
        revoke_active_decisions(db, cluster.id, reason="editorial_skip")
        transition_news_cluster(
            db, cluster, "rejected", reason_code="owner_skip", actor_ref=actor_ref
        )
        result_status = "accepted"
    elif action == "accept_for_design":
        revoke_active_decisions(db, cluster.id, reason="editorial_accept_for_design")
        transition_news_cluster(
            db,
            cluster,
            "accepted_for_design",
            reason_code="owner_accept_for_design",
            actor_ref=actor_ref,
        )
        result_status = "accepted"
    elif action == "defer":
        revoke_active_decisions(db, cluster.id, reason="editorial_defer")
        transition_news_cluster(
            db, cluster, "deferred", reason_code="owner_defer", actor_ref=actor_ref
        )
        cluster.deferred_until = utcnow() + timedelta(hours=settings.news_defer_hours)
        cluster.delivery_round += 1
        result_status = "deferred"
    else:
        if cluster.generation_attempt_count > settings.news_max_regenerations:
            result_status = "limit_reached"
            outcome = "limit_reached"
        else:
            revoke_active_decisions(db, cluster.id, reason="editorial_regenerate")
            if is_hermes_origin_draft(draft):
                # There is no Hermes text-generation request contract in YFC. Re-queue the
                # accepted immutable revision instead of routing it through legacy candidate
                # generation, which is intentionally disabled in Hermes production.
                cluster.delivery_round += 1
                transition_news_cluster(
                    db,
                    cluster,
                    "draft_ready",
                    reason_code="owner_regenerate_hermes_revision",
                    actor_ref=actor_ref,
                )
            else:
                transition_news_cluster(
                    db,
                    cluster,
                    "candidate",
                    reason_code="owner_regenerate",
                    actor_ref=actor_ref,
                )
            cluster.deferred_until = None
            result_status = "queued"
    db.add(
        NewsEditorialAction(
            cluster_id=cluster.id,
            draft_id=draft.id,
            actor_ref=actor_ref,
            action=action,
            outcome=outcome,
        )
    )
    if outcome == "applied":
        _cancel_pending_deliveries(db, draft.id)
    record_audit_event(
        db,
        action=f"news.editorial_{action}",
        resource_type="news_cluster",
        resource_id=cluster.id,
        details={"outcome": outcome, "topic": cluster.topic, "revision": draft.revision},
    )
    return ModerationResult(status=result_status, cluster_status=cluster.status)


def enqueue_review_deliveries(db: Session, admin_telegram_user_ids: set[int]) -> int:
    now = utcnow()
    legacy_source_fetch_enabled = settings.news_legacy_source_fetch_enabled
    if not legacy_source_fetch_enabled:
        cancel_legacy_review_deliveries(db)
    image_pending = db.query(NewsCluster).filter(NewsCluster.status == "image_pending").all()
    for cluster in image_pending:
        draft = latest_draft(db, cluster)
        if not legacy_source_fetch_enabled and (draft is None or not is_hermes_origin_draft(draft)):
            continue
        transition_news_cluster(
            db,
            cluster,
            "draft_ready",
            reason_code="image_generation_degraded_to_no_image",
        )
    deferred = (
        db.query(NewsCluster)
        .filter(
            NewsCluster.status == "deferred",
            NewsCluster.deferred_until.is_not(None),
            NewsCluster.deferred_until <= now,
        )
        .all()
    )
    for cluster in deferred:
        draft = latest_draft(db, cluster)
        if not legacy_source_fetch_enabled and (draft is None or not is_hermes_origin_draft(draft)):
            continue
        transition_news_cluster(
            db,
            cluster,
            "draft_ready",
            reason_code="defer_period_elapsed",
        )
        cluster.deferred_until = None
    db.flush()
    clusters = (
        db.query(NewsCluster)
        .filter(NewsCluster.status.in_({"draft_ready", "publication_failed", "awaiting_review"}))
        .all()
    )
    created = 0
    for cluster in clusters:
        draft = latest_draft(db, cluster)
        if draft is None:
            continue
        if not legacy_source_fetch_enabled and not is_hermes_origin_draft(draft):
            _cancel_pending_deliveries(db, draft.id)
            continue
        if not source_metadata_is_current_month(draft.evidence_metadata, now=now):
            _cancel_pending_deliveries(db, draft.id)
            transition_news_cluster(
                db,
                cluster,
                "clustered",
                reason_code="source_not_current_month",
            )
            continue
        created_for_cluster = 0
        is_preview_upgrade = False
        if cluster.status == "awaiting_review":
            preview_recorded = (
                db.query(AuditEvent.id)
                .filter(
                    AuditEvent.action == "news.preview_created",
                    AuditEvent.resource_type == "news_draft_revision",
                    AuditEvent.resource_id == draft.id,
                )
                .first()
                is not None
            )
            upgrade_queued = (
                db.query(AuditEvent.id)
                .filter(
                    AuditEvent.action == "news.preview_upgrade_queued",
                    AuditEvent.resource_type == "news_draft_revision",
                    AuditEvent.resource_id == draft.id,
                )
                .first()
                is not None
            )
            active_delivery = (
                db.query(NewsReviewDelivery.id)
                .filter(
                    NewsReviewDelivery.draft_id == draft.id,
                    NewsReviewDelivery.delivery_round == cluster.delivery_round,
                    or_(
                        NewsReviewDelivery.status.in_({"queued", "processing"}),
                        and_(
                            NewsReviewDelivery.status == "failed",
                            NewsReviewDelivery.last_error_code == "preview_delivery_blocked",
                        ),
                    ),
                )
                .first()
                is not None
            )
            if preview_recorded or upgrade_queued or active_delivery:
                continue
            if not admin_telegram_user_ids:
                continue
            cluster.delivery_round += 1
            is_preview_upgrade = True
        for telegram_user_id in sorted(admin_telegram_user_ids):
            recipient_ref = editorial_actor_ref(telegram_user_id)
            existing = (
                db.query(NewsReviewDelivery)
                .filter(
                    NewsReviewDelivery.draft_id == draft.id,
                    NewsReviewDelivery.recipient_ref == recipient_ref,
                    NewsReviewDelivery.delivery_round == cluster.delivery_round,
                )
                .first()
            )
            if existing is None:
                db.add(
                    NewsReviewDelivery(
                        draft_id=draft.id,
                        recipient_ref=recipient_ref,
                        delivery_round=cluster.delivery_round,
                        status="queued",
                        next_attempt_at=now,
                    )
                )
                created += 1
                created_for_cluster += 1
        if is_preview_upgrade and created_for_cluster:
            record_audit_event(
                db,
                action="news.preview_upgrade_queued",
                resource_type="news_draft_revision",
                resource_id=draft.id,
                details={
                    "renderer_version": PUBLICATION_RENDERER_VERSION,
                    "delivery_count": created_for_cluster,
                },
            )
        if admin_telegram_user_ids and cluster.status != "awaiting_review":
            transition_news_cluster(
                db,
                cluster,
                "awaiting_review",
                reason_code="owner_delivery_queued",
            )
    db.flush()
    return created


def cancel_legacy_review_deliveries(db: Session) -> int:
    """Cancel queued/processing legacy deliveries while source acquisition is disabled."""

    if settings.news_legacy_source_fetch_enabled:
        return 0
    rows = (
        db.query(NewsReviewDelivery)
        .filter(NewsReviewDelivery.status.in_({"queued", "processing"}))
        .all()
    )
    if not rows:
        return 0
    draft_ids = {row.draft_id for row in rows}
    drafts = {
        draft.id: draft
        for draft in db.query(NewsDraftRevision).filter(NewsDraftRevision.id.in_(draft_ids)).all()
    }
    cancelled = 0
    for delivery in rows:
        draft = drafts.get(delivery.draft_id)
        if draft is None or is_hermes_origin_draft(draft):
            continue
        delivery.status = "cancelled"
        delivery.processing_started_at = None
        delivery.next_attempt_at = None
        delivery.last_error_code = LEGACY_REVIEW_DELIVERY_DISABLED
        cancelled += 1
    return cancelled


def compose_review_artifact(
    db: Session,
    draft: NewsDraftRevision,
    *,
    channel_ready: bool | None = None,
) -> ReviewArtifact:
    cluster = db.get(NewsCluster, draft.cluster_id)
    if cluster is None:
        raise ValueError("cluster_missing")
    primary = db.get(NewsItem, draft.primary_item_id)
    if primary is None or primary.id not in draft.evidence_item_ids:
        raise ValueError("primary_source_missing")
    image = current_image(db, cluster)
    trusted_source_url = str(draft.evidence_metadata.get("trusted_source_url", "")) or (
        primary.primary_url or primary.canonical_url
    )
    composition = compose_publication_artifact(
        draft,
        image,
        trusted_source_url=trusted_source_url,
    )
    blockers = list(
        publication_quality_blockers(
            draft,
            image,
            trusted_source_url=trusted_source_url,
        )
    )
    if not settings.news_publication_enabled or settings.news_channel_id is None:
        blockers.append("publishing_disabled")
    if channel_ready is False:
        blockers.append("channel_rights_missing")
    artifact_hash = None
    if composition.artifact is not None and settings.news_channel_id is not None:
        artifact_hash = publication_content_hash(
            composition.artifact,
            image_sha256=image.sha256 if image is not None else None,
            channel_id=settings.news_channel_id,
        )
    return ReviewArtifact(
        artifact=composition.artifact,
        image=image,
        artifact_hash=artifact_hash,
        blockers=tuple(dict.fromkeys(blockers)),
        transport=composition.transport,
        visible_length=composition.visible_length,
        limit=composition.limit,
    )


def review_message(
    db: Session,
    draft: NewsDraftRevision,
    *,
    channel_ready: bool | None = None,
) -> tuple[str, str, dict]:
    cluster = db.get(NewsCluster, draft.cluster_id)
    if cluster is None:
        raise ValueError("cluster_missing")
    primary = db.get(NewsItem, draft.primary_item_id)
    if primary is None or primary.id not in draft.evidence_item_ids:
        raise ValueError("primary_source_missing")
    review = compose_review_artifact(db, draft, channel_ready=channel_ready)
    metadata = draft.evidence_metadata
    warnings = ", ".join(draft.warnings) if draft.warnings else "нет автоматических флагов"
    score_reasons = ", ".join(metadata.get("score_reasons", [])[:6])
    supporting_count = metadata.get("supporting_source_count", 0)
    if not isinstance(supporting_count, int):
        supporting_count = 0
    artifact_line = "Точный preview: недоступен до исправления блокеров"
    if review.artifact is not None:
        artifact_line = (
            f"Точный preview: {review.artifact.transport} · "
            f"{review.artifact.visible_length}/{review.artifact.limit} символов · "
            f"{review.artifact.renderer_version}"
        )
    elif review.visible_length is not None and review.limit is not None:
        artifact_line = (
            f"Точный preview: недоступен · {review.transport} · "
            f"{review.visible_length}/{review.limit} символов"
        )
    artifact_hash = (
        review.artifact_hash[:ARTIFACT_HASH_PREFIX_LENGTH]
        if review.artifact_hash is not None
        else "—"
    )
    blocker_text = ", ".join(review.blockers) if review.blockers else "нет"
    message = (
        "Черновик — в канал ещё не отправлен\n"
        f"Материал {draft.id[:8]} · text r{draft.revision} · "
        f"image r{cluster.current_image_revision}\n"
        f"Состояние: {cluster.status}\n"
        f"Канал: @{settings.news_channel_username or 'private'} "
        f"({settings.news_channel_environment})\n"
        f"{artifact_line}\n"
        f"Artifact: {artifact_hash}\n"
        f"Блокеры публикации: {blocker_text}\n"
        f"Topic: {metadata.get('topic', 'other')} · score {metadata.get('score', 0)}/100 "
        f"({metadata.get('score_version', 'unknown')})\n"
        f"Причины: {score_reasons}\n"
        f"Supporting sources: {max(0, supporting_count)}\n"
        f"Warnings: {warnings}"
    )
    failure = (
        db.query(NewsPublicationSnapshot)
        .filter(
            NewsPublicationSnapshot.cluster_id == cluster.id,
            NewsPublicationSnapshot.status == "failed",
        )
        .order_by(NewsPublicationSnapshot.created_at.desc())
        .first()
    )
    if failure is not None:
        message += f"\nПредыдущая публикация не выполнена: {failure.last_error_code}"
    source_url = str(metadata.get("trusted_source_url", "")) or (
        primary.primary_url or primary.canonical_url
    )
    buttons = [[{"text": "Открыть источник", "url": source_url}]]
    if not review.blockers and review.artifact_hash is not None:
        buttons.append(
            [
                {
                    "text": "Опубликовать сейчас",
                    "callback_data": publishing_callback_data(
                        "p",
                        draft.id,
                        cluster.current_image_revision,
                        review.artifact_hash,
                    ),
                },
                {
                    "text": "Запланировать",
                    "callback_data": publishing_callback_data(
                        "s",
                        draft.id,
                        cluster.current_image_revision,
                        review.artifact_hash,
                    ),
                },
            ]
        )
    buttons.extend(
        [
            [
                {
                    "text": "Изменить текст",
                    "callback_data": publishing_callback_data(
                        "e", draft.id, cluster.current_image_revision
                    ),
                },
                {
                    "text": "Перегенерировать текст",
                    "callback_data": callback_data("regenerate", draft.id),
                },
            ],
            [
                {
                    "text": "Перегенерировать изображение",
                    "callback_data": publishing_callback_data(
                        "i", draft.id, cluster.current_image_revision
                    ),
                },
            ],
            [
                {
                    "text": "Заменить изображение",
                    "callback_data": publishing_callback_data(
                        "u", draft.id, cluster.current_image_revision
                    ),
                },
                {
                    "text": "Убрать изображение",
                    "callback_data": publishing_callback_data(
                        "n", draft.id, cluster.current_image_revision
                    ),
                },
            ],
            [
                {
                    "text": "Отклонить",
                    "callback_data": publishing_callback_data(
                        "x", draft.id, cluster.current_image_revision
                    ),
                },
                {
                    "text": "Отложить рассмотрение",
                    "callback_data": callback_data("defer", draft.id),
                },
            ],
        ]
    )
    markup = {"inline_keyboard": buttons}
    return message[:MAX_REVIEW_MESSAGE_CHARS], source_url, markup


def prune_news_editorial(db: Session, *, retention_days: int, batch_size: int = 200) -> int:
    cutoff = utcnow() - timedelta(days=retention_days)
    cluster_ids = [
        row.id
        for row in db.query(NewsCluster.id)
        .filter(
            NewsCluster.status.in_(TERMINAL_CLUSTER_STATUSES),
            NewsCluster.updated_at < cutoff,
        )
        .order_by(NewsCluster.updated_at.asc(), NewsCluster.id.asc())
        .limit(batch_size)
        .all()
    ]
    if cluster_ids:
        draft_ids = [
            row.id
            for row in db.query(NewsDraftRevision.id)
            .filter(NewsDraftRevision.cluster_id.in_(cluster_ids))
            .all()
        ]
        if draft_ids:
            decision_ids = [
                row.id
                for row in db.query(NewsReviewDecision.id)
                .filter(NewsReviewDecision.cluster_id.in_(cluster_ids))
                .all()
            ]
            if decision_ids:
                db.query(NewsPublicationSnapshot).filter(
                    NewsPublicationSnapshot.decision_id.in_(decision_ids)
                ).delete(synchronize_session=False)
            db.query(NewsReviewDecision).filter(
                NewsReviewDecision.cluster_id.in_(cluster_ids)
            ).delete(synchronize_session=False)
            db.query(NewsImageRevision).filter(
                NewsImageRevision.cluster_id.in_(cluster_ids)
            ).delete(synchronize_session=False)
            db.query(NewsReviewDelivery).filter(NewsReviewDelivery.draft_id.in_(draft_ids)).delete(
                synchronize_session=False
            )
            db.query(NewsEditorialAction).filter(
                NewsEditorialAction.draft_id.in_(draft_ids)
            ).delete(synchronize_session=False)
            db.query(NewsDraftRevision).filter(NewsDraftRevision.id.in_(draft_ids)).delete(
                synchronize_session=False
            )
        db.query(NewsStateTransition).filter(
            NewsStateTransition.cluster_id.in_(cluster_ids)
        ).delete(synchronize_session=False)
        db.query(NewsItem).filter(NewsItem.cluster_id.in_(cluster_ids)).delete(
            synchronize_session=False
        )
        db.query(NewsCluster).filter(NewsCluster.id.in_(cluster_ids)).delete(
            synchronize_session=False
        )
    return len(cluster_ids)
