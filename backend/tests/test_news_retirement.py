from __future__ import annotations

import asyncio
import secrets
from pathlib import Path

import pytest

from fitminiapp_api.core.config import Settings, settings
from fitminiapp_api.db.session import SessionLocal, engine, get_session_context
from fitminiapp_api.models.news import (
    NewsCluster,
    NewsDraftRevision,
    NewsItem,
    NewsPublicationSnapshot,
    NewsReviewDecision,
    NewsReviewDelivery,
    NewsSource,
)
from fitminiapp_api.services import news_drafts, news_editorial, news_worker
from fitminiapp_api.services.news_drafts import (
    _validated_fields,
    evidence_packet,
    render_draft,
)
from fitminiapp_api.services.news_editorial import (
    NON_HERMES_REVIEW_DELIVERY_DISABLED,
    cancel_non_hermes_review_deliveries,
    quarantine_non_hermes_news_work,
)
from fitminiapp_api.services.news_ingestion import ParsedNewsItem, ingest_items, utcnow
from fitminiapp_api.services.news_origin import HERMES_SUBMISSION_MARKER
from fitminiapp_api.services.news_publication import (
    approve_publication,
    claim_due_publications,
    reconcile_uncertain_publication,
    retry_uncertain_publication,
)
from fitminiapp_api.services.news_sources import (
    apply_source_allowlist,
    parse_source_allowlist,
)
from fitminiapp_api.services.news_state import transition_news_cluster
from fitminiapp_api.services.news_worker import run_news_pipeline_once


def _source_candidate(*, external_id: str = "retirement-1") -> str:
    definitions = parse_source_allowlist(
        [
            {
                "id": "retirement-journal",
                "name": "Retirement Journal",
                "type": "primary_research",
                "fetch_kind": "rss",
                "url": "https://retirement-journal.example/feed",
                "language": "en",
                "enabled": True,
                "fetch_interval_minutes": 60,
                "trust_notes": "Primary publisher",
                "licensing_notes": "Metadata and short excerpt only",
            }
        ]
    )

    with get_session_context() as db:
        apply_source_allowlist(db, definitions)
        source = db.get(NewsSource, "retirement-journal")
        assert source is not None

        counts = ingest_items(
            db,
            source,
            [
                ParsedNewsItem(
                    external_id=external_id,
                    canonical_url=f"https://retirement-journal.example/{external_id}",
                    primary_url=f"https://retirement-journal.example/{external_id}",
                    title="Resistance training study reported practical outcomes",
                    summary="A controlled exercise study reported practical outcomes.",
                    publisher="Retirement Journal",
                    published_at=utcnow(),
                    doi=f"10.1000/{external_id}",
                )
            ],
            candidate_threshold=55,
        )
        assert counts["candidate"] == 1

        item = db.query(NewsItem).filter(NewsItem.external_id == external_id).one()
        assert item.cluster_id is not None
        return item.cluster_id


def _draft(db, cluster: NewsCluster, *, hermes: bool) -> NewsDraftRevision:
    packet = evidence_packet(db, cluster)
    fields = _validated_fields(
        {
            "headline": "Исследование тренировок: результаты для изученной группы",
            "summary": (
                "Авторы описали результаты исследования тренировок и ограничения их интерпретации."
            ),
            "why_it_matters": ("Материал помогает оценивать применимость результатов на практике."),
        }
    )

    metadata = {
        "topic": packet.topic,
        "source_published_at": (
            packet.published_at.isoformat() if packet.published_at is not None else None
        ),
        "source_publisher": packet.publisher or packet.source_name,
        "image_context_headline": packet.title[:180],
        "editorial_contract_version": "news-editorial-v2",
        "editorial_fields": dict(fields),
        "trusted_source_url": packet.primary_url or packet.canonical_url,
        "publication_policy": "manual_required",
    }
    if hermes:
        metadata["submitted_by"] = HERMES_SUBMISSION_MARKER

    revision = cluster.latest_draft_revision + 1
    draft = NewsDraftRevision(
        id=secrets.token_hex(16),
        cluster_id=cluster.id,
        primary_item_id=packet.primary_item_id,
        revision=revision,
        provider="groq-free-candidate" if hermes else "retired-local-test",
        model="test-model",
        prompt_version="test-v1",
        source_digest=packet.source_digest,
        evidence_item_ids=list(packet.evidence_item_ids),
        evidence_metadata=metadata,
        draft_text=render_draft(fields, packet),
        warnings=[],
        generation_latency_ms=0,
    )
    db.add(draft)

    cluster.latest_draft_revision = revision
    cluster.current_image_revision = 0
    cluster.generation_attempt_count += 1

    transition_news_cluster(
        db,
        cluster,
        "image_pending",
        reason_code=("test_hermes_draft_received" if hermes else "test_retired_local_draft"),
    )
    db.flush()
    return draft


def _legacy_publication_snapshot(
    db,
    cluster: NewsCluster,
    draft: NewsDraftRevision,
    *,
    status: str,
) -> NewsPublicationSnapshot:
    now = utcnow()
    decision = NewsReviewDecision(
        id=secrets.token_hex(16),
        cluster_id=cluster.id,
        text_revision_id=draft.id,
        image_revision_id=None,
        explicit_no_image=True,
        target_channel_id=-1001234567890,
        publication_mode="immediate",
        scheduled_for_utc=None,
        timezone="UTC",
        reviewer_ref="a" * 24,
        approved_at=now,
        status="active",
    )
    snapshot = NewsPublicationSnapshot(
        id=secrets.token_hex(16),
        decision_id=decision.id,
        cluster_id=cluster.id,
        text_revision_id=draft.id,
        image_revision_id=None,
        target_channel_id=-1001234567890,
        target_channel_username="",
        publication_mode="immediate",
        scheduled_for_utc=now,
        publication_local_date=now.date(),
        timezone="UTC",
        reviewer_ref="a" * 24,
        approved_at=now,
        status=status,
        urgent_override=False,
        publication_text="<b>Retired legacy snapshot</b>",
        renderer_version="news-publication-html-v1",
        transport="message",
        parse_mode="HTML",
        link_preview_disabled=True,
        image_sha256=None,
        content_hash="a" * 64,
        idempotency_key=secrets.token_hex(32),
        attempt_count=1 if status == "processing" else 0,
        next_attempt_at=now,
        processing_started_at=now if status == "processing" else None,
    )
    db.add(decision)
    db.flush()
    db.add(snapshot)
    db.flush()
    return snapshot


def test_retired_configuration_and_runtime_symbols_are_absent() -> None:
    retired_settings = {
        "news_legacy_source_fetch_enabled",
        "news_llm_provider",
        "news_llm_endpoint",
        "news_llm_api_key",
        "news_llm_model",
        "news_llm_timeout_seconds",
        "news_llm_prompt_version",
    }
    assert retired_settings.isdisjoint(Settings.model_fields)

    for name in (
        "TemplateDraftGenerator",
        "OpenAICompatibleDraftGenerator",
        "create_draft_revision",
    ):
        assert not hasattr(news_drafts, name)

    for name in (
        "_fetch_source",
        "fetch_due_sources",
        "generate_candidate_drafts",
    ):
        assert not hasattr(news_worker, name)

    root = Path(__file__).resolve().parents[2]
    env_example = (root / ".env.example").read_text(encoding="utf-8")
    ai_decision = (root / "docs" / "ai" / "ai-beta-product-decision.md").read_text(encoding="utf-8")

    assert "NEWS_LEGACY_SOURCE_FETCH_ENABLED" not in env_example
    assert "NEWS_LLM_PROVIDER" not in env_example
    assert "NEWS_LLM_PROVIDER=disabled" not in ai_decision
    assert not (root / "scripts" / "normalize_production_news_legacy_source_fetch.py").exists()


def test_worker_cycle_has_no_local_fetch_or_candidate_generation(monkeypatch) -> None:
    cluster_id = _source_candidate(external_id="restart-quarantine")
    calls: list[str] = []

    async def publish(*_args, **_kwargs):
        calls.append("publish")
        return 0

    async def images(*_args, **_kwargs):
        calls.append("images")
        return 0

    def enqueue(*_args, **_kwargs):
        calls.append("enqueue")
        return 0

    async def deliver(*_args, **_kwargs):
        calls.append("deliver")
        return 0

    monkeypatch.setattr(news_worker, "publish_due_snapshots", publish)
    monkeypatch.setattr(news_worker, "generate_pending_images", images)
    monkeypatch.setattr(news_worker, "enqueue_review_deliveries", enqueue)
    monkeypatch.setattr(news_worker, "deliver_review_queue", deliver)

    async def unused(*_args, **_kwargs):
        return None

    asyncio.run(
        run_news_pipeline_once(
            send_message=unused,
            send_preview=unused,
            send_publication=unused,
            publication_ready=True,
        )
    )

    assert calls == ["publish", "images", "enqueue", "deliver"]

    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        assert cluster is not None
        assert cluster.status == "rejected"
        assert db.query(NewsDraftRevision).count() == 0


def test_worker_cycle_quarantines_retired_work_once(monkeypatch) -> None:
    quarantine_calls = 0

    def quarantine_once(_db) -> tuple[int, int]:
        nonlocal quarantine_calls
        quarantine_calls += 1
        return 0, 0

    monkeypatch.setattr(news_worker, "quarantine_non_hermes_news_work", quarantine_once)
    monkeypatch.setattr(news_editorial, "quarantine_non_hermes_news_work", quarantine_once)

    async def unused(*_args, **_kwargs):
        return None

    asyncio.run(
        run_news_pipeline_once(
            send_message=unused,
            send_preview=unused,
            send_publication=unused,
            publication_ready=False,
            review_delivery_due=False,
        )
    )

    assert quarantine_calls == 1


@pytest.mark.parametrize(
    "status",
    [
        "candidate",
        "image_pending",
        "draft_ready",
        "awaiting_review",
        "deferred",
        "publication_approved",
        "publication_scheduled",
        "publication_failed",
    ],
)
def test_active_non_hermes_work_is_terminally_quarantined(status: str) -> None:
    cluster_id = _source_candidate(external_id=f"quarantine-{status}")

    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        assert cluster is not None

        if status != "candidate":
            _draft(db, cluster, hermes=False)
            cluster.status = status

        if status == "deferred":
            cluster.deferred_until = utcnow()

        cancelled, quarantined = quarantine_non_hermes_news_work(db)

        assert cancelled == 0
        assert quarantined == 1
        assert cluster.status == "rejected"
        assert cluster.deferred_until is None


@pytest.mark.parametrize("delivery_status", ["queued", "processing"])
def test_non_hermes_owner_delivery_is_cancelled_unconditionally(
    delivery_status: str,
) -> None:
    cluster_id = _source_candidate(external_id=f"delivery-{delivery_status}")

    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        assert cluster is not None

        draft = _draft(db, cluster, hermes=False)
        cluster.status = "awaiting_review"

        delivery = NewsReviewDelivery(
            draft_id=draft.id,
            recipient_ref="a" * 24,
            delivery_round=cluster.delivery_round,
            status=delivery_status,
            next_attempt_at=utcnow(),
            processing_started_at=(utcnow() if delivery_status == "processing" else None),
        )
        db.add(delivery)
        db.flush()

        assert cancel_non_hermes_review_deliveries(db) == 1
        assert delivery.status == "cancelled"
        assert delivery.processing_started_at is None
        assert delivery.next_attempt_at is None
        assert delivery.last_error_code == NON_HERMES_REVIEW_DELIVERY_DISABLED


def test_non_hermes_draft_cannot_create_publication_approval(monkeypatch) -> None:
    cluster_id = _source_candidate(external_id="approval-blocked")

    monkeypatch.setattr(settings, "news_publication_enabled", True)
    monkeypatch.setattr(settings, "news_channel_id", -1001234567890)

    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        assert cluster is not None

        draft = _draft(db, cluster, hermes=False)
        cluster.status = "awaiting_review"

        result = approve_publication(
            db,
            draft_id=draft.id,
            expected_image_revision=0,
            admin_telegram_user_id=7001,
            mode="immediate",
            expected_artifact_hash="0" * 16,
        )

        assert result.status == "unavailable"


def test_processing_non_hermes_publication_remains_reconcilable() -> None:
    cluster_id = _source_candidate(external_id="processing-publication")

    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        assert cluster is not None

        draft = _draft(db, cluster, hermes=False)
        cluster.status = "publication_approved"
        snapshot = _legacy_publication_snapshot(
            db,
            cluster,
            draft,
            status="processing",
        )

        cancelled, quarantined = quarantine_non_hermes_news_work(db)

        assert cancelled == 0
        assert quarantined == 1
        assert cluster.status == "rejected"

        db.expire(snapshot)
        assert snapshot.status == "uncertain"
        assert snapshot.processing_started_at is None
        assert snapshot.last_error_code == "worker_interrupted_send_uncertain"

        assert reconcile_uncertain_publication(
            db,
            snapshot_id=snapshot.id,
            admin_telegram_user_id=7001,
            channel_message_id=12345,
        )
        assert snapshot.status == "published"
        assert snapshot.telegram_message_id == 12345
        assert cluster.status == "published"


def test_reconciling_old_snapshot_preserves_new_hermes_flow() -> None:
    cluster_id = _source_candidate(external_id="uncertain-legacy-reconcile-hermes")

    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        assert cluster is not None
        legacy_draft = _draft(db, cluster, hermes=False)
        cluster.status = "publication_approved"
        snapshot = _legacy_publication_snapshot(
            db,
            cluster,
            legacy_draft,
            status="uncertain",
        )

        hermes_draft = _draft(db, cluster, hermes=True)
        hermes_revision = hermes_draft.revision

        assert reconcile_uncertain_publication(
            db,
            snapshot_id=snapshot.id,
            admin_telegram_user_id=7001,
            channel_message_id=12346,
        )
        db.flush()
        db.expire(snapshot)
        db.expire(cluster)
        assert snapshot.status == "published"
        assert snapshot.telegram_message_id == 12346
        assert cluster.status == "image_pending"
        assert cluster.latest_draft_revision == hermes_revision


def test_old_non_hermes_snapshot_does_not_reject_new_hermes_revision() -> None:
    cluster_id = _source_candidate(external_id="legacy-snapshot-hermes-revision")

    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        assert cluster is not None

        legacy_draft = _draft(db, cluster, hermes=False)
        cluster.status = "publication_approved"
        snapshot = _legacy_publication_snapshot(
            db,
            cluster,
            legacy_draft,
            status="queued",
        )

        hermes_draft = _draft(db, cluster, hermes=True)
        assert cluster.latest_draft_revision == hermes_draft.revision
        assert cluster.status == "image_pending"
        assert claim_due_publications(db) == []

        db.flush()
        db.expire(snapshot)
        assert snapshot.status == "cancelled"
        assert snapshot.last_error_code == "non_hermes_news_pipeline_retired"
        assert cluster.status == "image_pending"
        assert cluster.latest_draft_revision == hermes_draft.revision


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_claim_refreshes_cluster_after_hermes_revision_commits() -> None:
    cluster_id = _source_candidate(external_id="queued-legacy-concurrent-hermes")

    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        assert cluster is not None
        legacy_draft = _draft(db, cluster, hermes=False)
        cluster.status = "publication_approved"
        snapshot = _legacy_publication_snapshot(
            db,
            cluster,
            legacy_draft,
            status="queued",
        )
        snapshot_id = snapshot.id

    claim_db = SessionLocal()
    try:
        locked_snapshot = (
            claim_db.query(NewsPublicationSnapshot)
            .filter(NewsPublicationSnapshot.id == snapshot_id)
            .with_for_update()
            .one()
        )
        stale_legacy_draft = claim_db.get(NewsDraftRevision, locked_snapshot.text_revision_id)
        stale_cluster = claim_db.get(NewsCluster, cluster_id)
        assert stale_legacy_draft is not None
        assert stale_cluster is not None
        assert stale_cluster.latest_draft_revision == stale_legacy_draft.revision

        with get_session_context() as hermes_db:
            hermes_cluster = hermes_db.get(NewsCluster, cluster_id)
            assert hermes_cluster is not None
            hermes_draft = _draft(hermes_db, hermes_cluster, hermes=True)
            hermes_revision = hermes_draft.revision

        assert stale_cluster.latest_draft_revision == stale_legacy_draft.revision
        assert claim_due_publications(claim_db) == []
        claim_db.commit()
    finally:
        claim_db.rollback()
        claim_db.close()

    with get_session_context() as db:
        persisted_cluster = db.get(NewsCluster, cluster_id)
        persisted_snapshot = db.get(NewsPublicationSnapshot, snapshot_id)
        assert persisted_cluster is not None
        assert persisted_snapshot is not None
        assert persisted_snapshot.status == "cancelled"
        assert persisted_snapshot.last_error_code == "non_hermes_news_pipeline_retired"
        assert persisted_cluster.status == "image_pending"
        assert persisted_cluster.latest_draft_revision == hermes_revision


def test_retrying_uncertain_retired_snapshot_cannot_rewind_hermes_flow() -> None:
    cluster_id = _source_candidate(external_id="uncertain-legacy-before-hermes")

    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        assert cluster is not None

        legacy_draft = _draft(db, cluster, hermes=False)
        cluster.status = "publication_approved"
        snapshot = _legacy_publication_snapshot(
            db,
            cluster,
            legacy_draft,
            status="processing",
        )

        cancelled, quarantined = quarantine_non_hermes_news_work(db)
        assert cancelled == 0
        assert quarantined == 1
        db.expire(snapshot)
        assert snapshot.status == "uncertain"
        assert snapshot.last_error_code == "worker_interrupted_send_uncertain"

        hermes_draft = _draft(db, cluster, hermes=True)
        hermes_revision = hermes_draft.revision
        assert cluster.status == "image_pending"
        assert cluster.latest_draft_revision == hermes_revision

        assert (
            retry_uncertain_publication(
                db,
                snapshot_id=snapshot.id,
                admin_telegram_user_id=7001,
            )
            == "cancelled"
        )
        db.expire(snapshot)
        db.expire(cluster)
        assert snapshot.status == "cancelled"
        assert snapshot.last_error_code == "non_hermes_news_pipeline_retired"
        assert cluster.status == "image_pending"
        assert cluster.latest_draft_revision == hermes_revision
        assert claim_due_publications(db) == []

    async def unused(*_args, **_kwargs):
        return None

    asyncio.run(
        run_news_pipeline_once(
            send_message=unused,
            send_preview=unused,
            send_publication=unused,
            publication_ready=True,
        )
    )

    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        snapshot = db.query(NewsPublicationSnapshot).one()
        assert cluster is not None
        assert snapshot.status == "cancelled"
        assert cluster.status in {"draft_ready", "awaiting_review"}
        assert cluster.latest_draft_revision == hermes_revision
        assert claim_due_publications(db) == []


def test_retired_uncertain_retry_api_reports_cancelled_status(client, monkeypatch) -> None:
    cluster_id = _source_candidate(external_id="uncertain-legacy-api-status")
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "7001")

    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        assert cluster is not None
        legacy_draft = _draft(db, cluster, hermes=False)
        cluster.status = "publication_approved"
        snapshot = _legacy_publication_snapshot(
            db,
            cluster,
            legacy_draft,
            status="uncertain",
        )
        snapshot_id = snapshot.id

    response = client.post(
        f"/api/v1/bot/news/publications/{snapshot_id}/retry",
        headers={"X-Bot-Token": settings.bot_internal_token},
        json={"admin_telegram_user_id": 7001},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    with get_session_context() as db:
        persisted = db.get(NewsPublicationSnapshot, snapshot_id)
        assert persisted is not None
        assert persisted.status == "cancelled"


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_retry_refreshes_cluster_after_hermes_revision_commits() -> None:
    cluster_id = _source_candidate(external_id="uncertain-legacy-concurrent-hermes")

    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        assert cluster is not None
        legacy_draft = _draft(db, cluster, hermes=False)
        cluster.status = "publication_approved"
        snapshot = _legacy_publication_snapshot(
            db,
            cluster,
            legacy_draft,
            status="uncertain",
        )
        snapshot_id = snapshot.id

    retry_db = SessionLocal()
    try:
        locked_snapshot = (
            retry_db.query(NewsPublicationSnapshot)
            .filter(NewsPublicationSnapshot.id == snapshot_id)
            .with_for_update()
            .one()
        )
        stale_legacy_draft = retry_db.get(NewsDraftRevision, locked_snapshot.text_revision_id)
        stale_cluster = retry_db.get(NewsCluster, cluster_id)
        assert stale_legacy_draft is not None
        assert stale_cluster is not None
        assert stale_cluster.latest_draft_revision == stale_legacy_draft.revision

        with get_session_context() as hermes_db:
            hermes_cluster = hermes_db.get(NewsCluster, cluster_id)
            assert hermes_cluster is not None
            hermes_draft = _draft(hermes_db, hermes_cluster, hermes=True)
            hermes_revision = hermes_draft.revision

        assert stale_cluster.latest_draft_revision == stale_legacy_draft.revision
        assert (
            retry_uncertain_publication(
                retry_db,
                snapshot_id=snapshot_id,
                admin_telegram_user_id=7001,
            )
            == "cancelled"
        )
        retry_db.commit()
    finally:
        retry_db.rollback()
        retry_db.close()

    with get_session_context() as db:
        persisted_cluster = db.get(NewsCluster, cluster_id)
        persisted_snapshot = db.get(NewsPublicationSnapshot, snapshot_id)
        assert persisted_cluster is not None
        assert persisted_snapshot is not None
        assert persisted_snapshot.status == "cancelled"
        assert persisted_cluster.status == "image_pending"
        assert persisted_cluster.latest_draft_revision == hermes_revision


def test_hermes_origin_is_not_quarantined() -> None:
    cluster_id = _source_candidate(external_id="hermes-preserved")

    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        assert cluster is not None

        draft = _draft(db, cluster, hermes=True)
        cluster.status = "draft_ready"

        cancelled, quarantined = quarantine_non_hermes_news_work(db)

        assert cancelled == 0
        assert quarantined == 0
        assert cluster.status == "draft_ready"
        assert db.get(NewsDraftRevision, draft.id) is not None


@pytest.mark.parametrize("status", ["published", "accepted_for_design"])
def test_terminal_non_hermes_news_history_remains_readable(status: str) -> None:
    cluster_id = _source_candidate(external_id=f"historical-{status}")

    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        assert cluster is not None

        draft = _draft(db, cluster, hermes=False)
        cluster.status = status

        cancelled, quarantined = quarantine_non_hermes_news_work(db)

        assert cancelled == 0
        assert quarantined == 0
        assert cluster.status == status

        stored = db.get(NewsDraftRevision, draft.id)
        assert stored is not None
        assert stored.draft_text == draft.draft_text
