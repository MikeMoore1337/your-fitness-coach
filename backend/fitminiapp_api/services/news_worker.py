from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Protocol

import httpx
from sqlalchemy import func

from fitminiapp_api.core.config import settings
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.news import (
    NewsCluster,
    NewsDraftRevision,
    NewsReviewDelivery,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.news_editorial import (
    NON_HERMES_REVIEW_DELIVERY_DISABLED,
    cancel_non_hermes_review_deliveries,
    compose_review_artifact,
    editorial_actor_ref,
    enqueue_review_deliveries,
    is_hermes_origin_draft,
    prune_news_editorial,
    quarantine_non_hermes_news_work,
    review_delivery_blockers,
    review_message,
)
from fitminiapp_api.services.news_images import create_image_revision
from fitminiapp_api.services.news_ingestion import utcnow
from fitminiapp_api.services.news_publication import (
    claim_due_publications,
    mark_publication_failed,
    mark_publication_succeeded,
    publication_payload,
)
from fitminiapp_api.services.news_review_schedule import (
    NEWS_REVIEW_BATCH_SIZE,
    NewsReviewSlot,
)
from fitminiapp_api.services.notifications import safe_delivery_error
from fitminiapp_api.services.telegram_transport import (
    TelegramPublicationError,
    telegram_transport_options,
)

logger = logging.getLogger(__name__)
MAX_GENERATIONS_PER_CYCLE = 10
MAX_DELIVERIES_PER_CYCLE = 20
MAX_DELIVERY_ATTEMPTS = 5
PROCESSING_TTL = timedelta(minutes=10)


@dataclass
class NewsCycleStats:
    sources_total: int = 0
    sources_checked: int = 0
    sources_success: int = 0
    sources_failed: int = 0
    candidates_fetched: int = 0
    candidates_new: int = 0
    candidates_duplicate: int = 0
    candidates_stale: int = 0
    candidates_below_threshold: int = 0
    candidates_eligible: int = 0
    drafts_created: int = 0
    drafts_skipped_daily_limit: int = 0
    llm_failures: int = 0
    telegram_delivery_failures: int = 0

    def log_fields(self) -> dict[str, int]:
        return {
            "sources_total": self.sources_total,
            "sources_checked": self.sources_checked,
            "sources_success": self.sources_success,
            "sources_failed": self.sources_failed,
            "candidates_fetched": self.candidates_fetched,
            "candidates_new": self.candidates_new,
            "candidates_duplicate": self.candidates_duplicate,
            "candidates_stale": self.candidates_stale,
            "candidates_below_threshold": self.candidates_below_threshold,
            "candidates_eligible": self.candidates_eligible,
            "drafts_created": self.drafts_created,
            "drafts_skipped_daily_limit": self.drafts_skipped_daily_limit,
            "llm_failures": self.llm_failures,
            "telegram_delivery_failures": self.telegram_delivery_failures,
        }


SendMessage = Callable[
    [httpx.AsyncClient, int, str],
    Awaitable[int | None],
]


class PublicationResult(Protocol):
    @property
    def message_id(self) -> int: ...

    @property
    def message_date(self) -> datetime: ...


async def generate_pending_images(client: httpx.AsyncClient) -> int:
    with get_session_context() as db:
        cluster_ids = [
            row.id
            for row in db.query(NewsCluster.id)
            .filter(NewsCluster.status == "image_pending")
            .order_by(NewsCluster.updated_at.asc())
            .limit(MAX_GENERATIONS_PER_CYCLE)
            .all()
        ]
    generated = 0
    for cluster_id in cluster_ids:
        with get_session_context() as db:
            cluster = (
                db.query(NewsCluster)
                .filter(NewsCluster.id == cluster_id, NewsCluster.status == "image_pending")
                .with_for_update()
                .first()
            )
            if cluster is None:
                continue
            draft = (
                db.query(NewsDraftRevision)
                .filter(
                    NewsDraftRevision.cluster_id == cluster.id,
                    NewsDraftRevision.revision == cluster.latest_draft_revision,
                )
                .first()
            )
            if draft is None:
                continue
            await create_image_revision(db, cluster, draft, client=client)
            generated += 1
    return generated


def _claim_deliveries(
    *,
    draft_limit: int | None = None,
    review_slot: NewsReviewSlot | None = None,
) -> list[int]:
    now = utcnow()
    stale_before = now - PROCESSING_TTL
    with get_session_context() as db:
        db.query(NewsReviewDelivery).filter(
            NewsReviewDelivery.status == "processing",
            NewsReviewDelivery.processing_started_at < stale_before,
        ).update(
            {
                NewsReviewDelivery.status: "queued",
                NewsReviewDelivery.processing_started_at: None,
                NewsReviewDelivery.next_attempt_at: now,
            },
            synchronize_session=False,
        )
        eligible = db.query(NewsReviewDelivery).filter(
            NewsReviewDelivery.status == "queued",
            NewsReviewDelivery.next_attempt_at <= now,
        )
        effective_draft_limit = draft_limit
        if review_slot is not None:
            slot_start_utc = review_slot.local_start.astimezone(UTC).replace(tzinfo=None)
            sent_drafts_in_slot = (
                db.query(NewsReviewDelivery.draft_id)
                .filter(
                    NewsReviewDelivery.status == "sent",
                    NewsReviewDelivery.sent_at.is_not(None),
                    NewsReviewDelivery.sent_at >= slot_start_utc,
                )
                .distinct()
            )
            eligible = eligible.filter(~NewsReviewDelivery.draft_id.in_(sent_drafts_in_slot))
            remaining_batch_size = max(0, NEWS_REVIEW_BATCH_SIZE - sent_drafts_in_slot.count())
            effective_draft_limit = (
                remaining_batch_size
                if effective_draft_limit is None
                else min(effective_draft_limit, remaining_batch_size)
            )
        if effective_draft_limit is None:
            rows = (
                eligible.order_by(
                    NewsReviewDelivery.next_attempt_at.asc(), NewsReviewDelivery.id.asc()
                )
                .limit(MAX_DELIVERIES_PER_CYCLE)
                .with_for_update(skip_locked=True)
                .all()
            )
        else:
            selected_drafts = (
                eligible.with_entities(
                    NewsReviewDelivery.draft_id,
                    func.min(NewsReviewDelivery.next_attempt_at).label("next_attempt_at"),
                    func.min(NewsReviewDelivery.id).label("delivery_id"),
                )
                .group_by(NewsReviewDelivery.draft_id)
                .order_by(
                    func.min(NewsReviewDelivery.next_attempt_at).asc(),
                    func.min(NewsReviewDelivery.id).asc(),
                )
                .limit(effective_draft_limit)
                .all()
            )
            draft_ids = [row[0] for row in selected_drafts]
            rows = (
                eligible.filter(NewsReviewDelivery.draft_id.in_(draft_ids))
                .order_by(NewsReviewDelivery.next_attempt_at.asc(), NewsReviewDelivery.id.asc())
                .with_for_update(skip_locked=True)
                .all()
                if draft_ids
                else []
            )
        result = []
        for row in rows:
            row.status = "processing"
            row.processing_started_at = now
            row.attempt_count += 1
            result.append(row.id)
        return result


def _mark_review_delivery_blocked(
    delivery_id: int,
    *,
    draft_id: str,
    text_revision: int,
    image_revision: int,
    attempt_count: int,
    blockers: tuple[str, ...],
) -> None:
    with get_session_context() as db:
        delivery = db.get(NewsReviewDelivery, delivery_id)
        if delivery is None or delivery.status != "processing":
            return
        delivery.status = "failed"
        delivery.processing_started_at = None
        delivery.last_error_code = "preview_delivery_blocked"
        record_audit_event(
            db,
            action="news.preview_delivery_blocked",
            resource_type="news_draft_revision",
            resource_id=draft_id,
            details={
                "blockers": list(blockers),
                "delivery_id": delivery_id,
                "text_revision": text_revision,
                "image_revision": image_revision,
            },
        )
    logger.warning(
        "news_review_delivery_blocked",
        extra={
            "pipeline_stage": "owner_delivery",
            "reason": "preview_not_deliverable",
            "blockers": ",".join(blockers),
            "attempt_count": attempt_count,
        },
    )


async def deliver_review_queue(
    client: httpx.AsyncClient,
    send_message: Callable[..., Awaitable[int | None]],
    send_preview: Callable[..., Awaitable[PublicationResult]],
    channel_ready: bool,
    *,
    cycle_stats: NewsCycleStats | None = None,
    review_slot: NewsReviewSlot | None = None,
) -> int:
    recipient_ids = {
        editorial_actor_ref(telegram_id): telegram_id
        for telegram_id in settings.admin_telegram_id_set
    }
    with get_session_context() as db:
        cancel_non_hermes_review_deliveries(db)
    delivered = 0
    for delivery_id in _claim_deliveries(
        draft_limit=NEWS_REVIEW_BATCH_SIZE if review_slot is not None else None,
        review_slot=review_slot,
    ):
        with get_session_context() as db:
            delivery = db.get(NewsReviewDelivery, delivery_id)
            if delivery is None or delivery.status != "processing":
                continue
            draft = db.get(NewsDraftRevision, delivery.draft_id)
            cluster = db.get(NewsCluster, draft.cluster_id) if draft is not None else None
            chat_id = recipient_ids.get(delivery.recipient_ref)
            if (
                draft is None
                or cluster is None
                or cluster.status != "awaiting_review"
                or draft.revision != cluster.latest_draft_revision
                or chat_id is None
            ):
                delivery.status = "cancelled"
                delivery.processing_started_at = None
                continue
            if not is_hermes_origin_draft(draft):
                delivery.status = "cancelled"
                delivery.processing_started_at = None
                delivery.next_attempt_at = None
                delivery.last_error_code = NON_HERMES_REVIEW_DELIVERY_DISABLED
                continue
            review = compose_review_artifact(db, draft, channel_ready=channel_ready)
            delivery_blockers = review_delivery_blockers(draft, review)
            if not delivery_blockers:
                message, _, markup = review_message(db, draft, channel_ready=channel_ready)
            image_data = review.image.image_data if review.image is not None else None
            preview_message_id = delivery.telegram_message_id
            artifact = review.artifact
            artifact_hash = review.artifact_hash
            draft_resource_id = draft.id
            text_revision = draft.revision
            image_revision = cluster.current_image_revision
            attempt_count = delivery.attempt_count
            queue_age = max(0, round((utcnow() - delivery.created_at).total_seconds()))
        if delivery_blockers:
            _mark_review_delivery_blocked(
                delivery_id,
                draft_id=draft_resource_id,
                text_revision=text_revision,
                image_revision=image_revision,
                attempt_count=attempt_count,
                blockers=delivery_blockers,
            )
            continue
        try:
            if artifact is not None and preview_message_id is None:
                preview_result = await send_preview(
                    client,
                    chat_id,
                    artifact.text,
                    image_data,
                    parse_mode=artifact.parse_mode,
                    link_preview_disabled=artifact.link_preview_disabled,
                )
                preview_message_id = preview_result.message_id
                with get_session_context() as db:
                    current_delivery = db.get(NewsReviewDelivery, delivery_id)
                    if current_delivery is None or current_delivery.status != "processing":
                        continue
                    current_delivery.telegram_message_id = preview_message_id
            control_message_id = await send_message(
                client,
                chat_id,
                message,
                reply_markup=markup,
            )
        except Exception as exc:
            if cycle_stats is not None:
                cycle_stats.telegram_delivery_failures += 1
            error_code = safe_delivery_error(exc)
            with get_session_context() as db:
                delivery = db.get(NewsReviewDelivery, delivery_id)
                if delivery is None or delivery.status != "processing":
                    continue
                terminal_status = getattr(exc, "terminal_status", None)
                if terminal_status or delivery.attempt_count >= MAX_DELIVERY_ATTEMPTS:
                    delivery.status = "failed"
                else:
                    delivery.status = "queued"
                    delivery.next_attempt_at = utcnow() + timedelta(
                        minutes=min(60, 2**delivery.attempt_count)
                    )
                delivery.processing_started_at = None
                delivery.last_error_code = error_code
            logger.error(
                "news_review_delivery_failed",
                extra={
                    "pipeline_stage": "owner_delivery",
                    "delivery_error": error_code,
                    "attempt_count": attempt_count,
                    "queue_age_seconds": queue_age,
                },
            )
            continue
        with get_session_context() as db:
            delivery = db.get(NewsReviewDelivery, delivery_id)
            if delivery is None or delivery.status != "processing":
                continue
            delivery.status = "sent"
            delivery.sent_at = utcnow()
            delivery.telegram_message_id = preview_message_id or control_message_id
            delivery.processing_started_at = None
            delivery.last_error_code = None
            record_audit_event(
                db,
                action="news.preview_created",
                resource_type="news_draft_revision",
                resource_id=draft_resource_id,
                details={
                    "artifact_hash": artifact_hash,
                    "preview_message_id": preview_message_id,
                    "control_message_id": control_message_id,
                    "text_revision": text_revision,
                    "image_revision": image_revision,
                },
            )
        delivered += 1
        logger.info(
            "news_review_delivery_succeeded",
            extra={
                "pipeline_stage": "owner_delivery",
                "outcome": "sent",
                "attempt_count": attempt_count,
                "queue_age_seconds": queue_age,
            },
        )
    return delivered


async def publish_due_snapshots(
    client: httpx.AsyncClient,
    send_publication: Callable[..., Awaitable[PublicationResult]],
    send_message: Callable[..., Awaitable[int | None]],
) -> int:
    with get_session_context() as db:
        snapshot_ids = claim_due_publications(db)
    published = 0
    for snapshot_id in snapshot_ids:
        with get_session_context() as db:
            payload = publication_payload(db, snapshot_id)
        if payload is None:
            continue
        try:
            result = await send_publication(
                client,
                payload.channel_id,
                payload.text,
                payload.image_data,
                parse_mode=payload.parse_mode,
                link_preview_disabled=payload.link_preview_disabled,
            )
        except TelegramPublicationError as exc:
            with get_session_context() as db:
                mark_publication_failed(
                    db,
                    snapshot_id,
                    error_code=exc.code,
                    retry_after=exc.retry_after,
                    uncertain=exc.uncertain,
                    terminal=exc.terminal,
                )
            logger.error(
                "news_publication_failed",
                extra={"pipeline_stage": "publication", "reason": exc.code},
            )
            if exc.uncertain:
                markup = {
                    "inline_keyboard": [
                        [
                            {
                                "text": "Указать найденный message ID",
                                "callback_data": f"newsrec:r:{snapshot_id}",
                            }
                        ],
                        [
                            {
                                "text": "Публикации нет — повторить",
                                "callback_data": f"newsrec:t:{snapshot_id}",
                            }
                        ],
                    ]
                }
                for admin_id in sorted(settings.admin_telegram_id_set):
                    try:
                        await send_message(
                            client,
                            admin_id,
                            "Отправка новости имеет неопределённый результат. "
                            "Проверьте канал; автоматический повтор остановлен.",
                            reply_markup=markup,
                        )
                    except Exception as notify_exc:
                        logger.error(
                            "news_uncertain_owner_notice_failed",
                            extra={"reason": safe_delivery_error(notify_exc)},
                        )
            continue
        with get_session_context() as db:
            mark_publication_succeeded(
                db,
                snapshot_id,
                message_id=result.message_id,
                message_date=result.message_date,
            )
        markup = {
            "inline_keyboard": [
                [
                    {
                        "text": "Изменить опубликованный текст",
                        "callback_data": f"newspost:e:{snapshot_id}",
                    }
                ],
                [
                    {
                        "text": "Удалить публикацию",
                        "callback_data": f"newspost:d:{snapshot_id}",
                    }
                ],
            ]
        }
        for admin_id in sorted(settings.admin_telegram_id_set):
            try:
                await send_message(
                    client,
                    admin_id,
                    f"Новость опубликована · snapshot {snapshot_id}",
                    reply_markup=markup,
                )
            except Exception as exc:
                logger.error(
                    "news_owner_publication_receipt_failed",
                    extra={"reason": safe_delivery_error(exc)},
                )
        published += 1
    return published


async def run_news_pipeline_once(
    *,
    send_message: Callable[..., Awaitable[int | None]],
    send_preview: Callable[..., Awaitable[PublicationResult]],
    send_publication: Callable[..., Awaitable[PublicationResult]],
    publication_ready: bool,
    review_delivery_due: bool = True,
    review_slot: NewsReviewSlot | None = None,
) -> NewsCycleStats:
    """Run the Hermes-origin downstream editorial pipeline once."""

    started = monotonic()
    cycle_stats = NewsCycleStats()
    delivered = 0

    with get_session_context() as db:
        prune_news_editorial(db, retention_days=settings.news_retention_days)
        quarantine_non_hermes_news_work(db)

    timeout = httpx.Timeout(settings.news_source_timeout_seconds)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        **telegram_transport_options(),
    ) as client:
        published = (
            await publish_due_snapshots(client, send_publication, send_message)
            if publication_ready
            else 0
        )

        await generate_pending_images(client)

        with get_session_context() as db:
            enqueue_review_deliveries(db, settings.admin_telegram_id_set)

        if review_delivery_due:
            delivered = await deliver_review_queue(
                client,
                send_message,
                send_preview,
                publication_ready,
                cycle_stats=cycle_stats,
                review_slot=review_slot,
            )

    if any((delivered, published, cycle_stats.telegram_delivery_failures)):
        logger.info(
            "news_pipeline_cycle_completed",
            extra={
                "pipeline_stage": "cycle",
                "outcome": "completed",
                **cycle_stats.log_fields(),
                "attempt_count": delivered,
                "published_count": published,
                "latency_ms": round((monotonic() - started) * 1000, 2),
            },
        )

    return cycle_stats
