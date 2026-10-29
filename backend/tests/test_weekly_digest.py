from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta

import httpx
import pytest

from fitminiapp_api.core.config import settings
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.news import (
    NewsCluster,
    NewsDraftRevision,
    NewsItem,
    NewsPublicationSnapshot,
    NewsReviewDecision,
    NewsSource,
)
from fitminiapp_api.models.notification import NotificationSetting
from fitminiapp_api.models.user import User
from fitminiapp_api.models.weekly_digest import (
    WeeklyDigestDelivery,
    WeeklyDigestIssue,
    WeeklyDigestIssueItem,
    WeeklyDigestPreference,
)
from fitminiapp_api.services import notifications, weekly_digest, worker
from fitminiapp_api.services.weekly_digest import (
    approve_digest_issue,
    claim_due_digest_deliveries,
    create_digest_draft,
    digest_delivery_payload,
    edit_digest_issue,
    get_digest_preference,
    mark_digest_delivery_failed,
    prune_weekly_digest,
    schedule_digest_issue,
    set_digest_preference,
)

NOW = datetime(2026, 8, 26, 10, 0)
ADMIN_ID = 7001


def _configure(monkeypatch, *, enabled: bool = True) -> None:
    monkeypatch.setattr(settings, "admin_telegram_user_ids", str(ADMIN_ID))
    monkeypatch.setattr(settings, "news_channel_username", "yfc_test_news")
    monkeypatch.setattr(settings, "news_publication_timezone", "Europe/Moscow")
    monkeypatch.setattr(settings, "weekly_digest_enabled", enabled)
    monkeypatch.setattr(settings, "weekly_digest_min_items", 3)
    monkeypatch.setattr(weekly_digest, "utcnow", lambda: NOW)


def _published_post(index: int, *, topic: str, score: int = 80, edited: bool = False) -> str:
    suffix = f"{index:032x}"
    source_id = f"source-{index}"
    cluster_id = suffix
    item_id = index + 100
    draft_id = f"{index + 20:032x}"
    decision_id = f"{index + 40:032x}"
    snapshot_id = f"{index + 60:032x}"
    with get_session_context() as db:
        db.add(
            NewsSource(
                id=source_id,
                name=f"Source {index}",
                source_type="official_organization",
                fetch_kind="rss",
                feed_url=f"https://example.com/feed-{index}",
                enabled=True,
            )
        )
        db.add(
            NewsCluster(
                id=cluster_id,
                cluster_key=f"cluster-{index}",
                status="published",
                primary_item_id=item_id,
                topic=topic,
                score=score,
            )
        )
        db.flush()
        db.add(
            NewsItem(
                id=item_id,
                source_id=source_id,
                cluster_id=cluster_id,
                status="clustered",
                external_id=f"post-{index}",
                external_id_hash=f"{index + 1000:064x}",
                canonical_url=f"https://example.com/post-{index}",
                canonical_url_hash=f"{index + 2000:064x}",
                primary_url=f"https://example.com/post-{index}",
                title=f"Материал {index}",
                summary=f"Одобренный вывод материала {index}.",
                content_hash=f"{index + 3000:064x}",
                source_snapshot={},
            )
        )
        db.flush()
        db.add(
            NewsDraftRevision(
                id=draft_id,
                cluster_id=cluster_id,
                primary_item_id=item_id,
                revision=1,
                provider="deterministic",
                model="template",
                prompt_version="news-v1",
                source_digest=f"{index + 4000:064x}",
                evidence_item_ids=[item_id],
                evidence_metadata={
                    "trusted_source_url": f"https://example.com/post-{index}",
                    "topic": topic,
                    "score": score,
                    "score_version": "news-score-v1",
                    "editorial_fields": {
                        "headline": f"Полезный материал {index}",
                        "summary": f"Одобренный вывод материала {index}.",
                        "why_it_matters": f"Это помогает понять тему {index}.",
                    },
                },
                draft_text=f"Материал {index}",
                warnings=[],
            )
        )
        db.flush()
        db.add(
            NewsReviewDecision(
                id=decision_id,
                cluster_id=cluster_id,
                text_revision_id=draft_id,
                image_revision_id=None,
                explicit_no_image=True,
                target_channel_id=-1001234567890,
                publication_mode="immediate",
                scheduled_for_utc=None,
                timezone="Europe/Moscow",
                reviewer_ref="reviewer",
                approved_at=NOW - timedelta(hours=1),
                status="consumed",
            )
        )
        db.flush()
        db.add(
            NewsPublicationSnapshot(
                id=snapshot_id,
                decision_id=decision_id,
                cluster_id=cluster_id,
                text_revision_id=draft_id,
                image_revision_id=None,
                target_channel_id=-1001234567890,
                target_channel_username="yfc_test_news",
                publication_mode="immediate",
                scheduled_for_utc=NOW - timedelta(hours=1),
                publication_local_date=NOW.date(),
                timezone="Europe/Moscow",
                reviewer_ref="reviewer",
                approved_at=NOW - timedelta(hours=1),
                status="published",
                urgent_override=False,
                publication_text=f"<b>Полезный материал {index}</b>",
                renderer_version="news-publication-html-v1",
                transport="message",
                parse_mode="HTML",
                link_preview_disabled=True,
                image_sha256=None,
                content_hash=f"{index + 5000:064x}",
                idempotency_key=f"{index + 6000:064x}",
                attempt_count=1,
                next_attempt_at=NOW - timedelta(hours=1),
                telegram_message_id=index + 900,
                telegram_permalink=f"https://t.me/yfc_test_news/{index + 900}",
                telegram_edited_at=NOW if edited else None,
                post_edit_content_hash=f"{index + 7000:064x}" if edited else None,
                published_at=NOW - timedelta(hours=index),
            )
        )
    return snapshot_id


def _subscriber(telegram_id: int = 9001) -> int:
    with get_session_context() as db:
        preference = set_digest_preference(
            db,
            telegram_user_id=telegram_id,
            enabled=True,
            presented_consent_version="weekly-news-v1",
            username="reader",
            first_name="Reader",
        )
        assert preference.enabled is True
        return db.query(User.id).filter(User.telegram_user_id == telegram_id).scalar()


def _approved_issue(monkeypatch) -> str:
    _configure(monkeypatch)
    for index, topic in enumerate(("strength", "nutrition", "recovery"), start=1):
        _published_post(index, topic=topic)
    with get_session_context() as db:
        issue = create_digest_draft(db, admin_telegram_user_id=ADMIN_ID, now=NOW)
        approved = approve_digest_issue(
            db,
            issue_id=issue.issue_id,
            admin_telegram_user_id=ADMIN_ID,
            expected_content_hash=issue.content_hash[:16],
        )
        assert approved.status == "approved"
        return issue.issue_id


def test_digest_is_default_off_and_consent_is_isolated(monkeypatch) -> None:
    _configure(monkeypatch)
    with get_session_context() as db:
        assert get_digest_preference(db, telegram_user_id=9001).enabled is False
        enabled = set_digest_preference(
            db,
            telegram_user_id=9001,
            enabled=True,
            presented_consent_version="weekly-news-v1",
            username="reader",
            first_name="Reader",
        )
        assert enabled.enabled is True
        assert enabled.consent_version == "weekly-news-v1"
        user = db.query(User).filter(User.telegram_user_id == 9001).one()
        assert db.query(NotificationSetting).filter_by(user_id=user.id).count() == 0
        notification_setting = NotificationSetting(user_id=user.id, telegram_enabled=False)
        db.add(notification_setting)
        db.flush()
        disabled = set_digest_preference(db, telegram_user_id=9001, enabled=False)
        assert disabled.enabled is False
        assert notification_setting.telegram_enabled is False
        resumed = set_digest_preference(
            db,
            telegram_user_id=9001,
            enabled=True,
            presented_consent_version="weekly-news-v1",
        )
        assert resumed.enabled is True
        actions = [row.action for row in db.query(AuditEvent).order_by(AuditEvent.id).all()]
        assert actions[-3:] == [
            "weekly_digest.subscribed",
            "weekly_digest.unsubscribed",
            "weekly_digest.subscribed",
        ]


def test_draft_uses_only_published_snapshots_and_revision_bound_owner_approval(monkeypatch) -> None:
    _configure(monkeypatch)
    for index, topic in enumerate(("strength", "nutrition", "recovery", "strength", "other"), 1):
        _published_post(index, topic=topic, score=90 - index)
    _published_post(6, topic="nutrition", score=99, edited=True)

    with get_session_context() as db:
        mutable_cluster = db.get(NewsCluster, f"{1:032x}")
        mutable_cluster.score = 0
        mutable_cluster.topic = "changed_after_publication"

    with get_session_context() as db:
        issue = create_digest_draft(db, admin_telegram_user_id=ADMIN_ID, now=NOW)
        assert len(issue.items) == 5
        assert len({item.category for item in issue.items[:3]}) == 3
        assert issue.items[1].category == "strength"
        assert issue.rendered_text.count("Читать в канале") == 5
        assert "example.com" not in issue.rendered_text
        assert "item_1_owner_review_required" in issue.blockers

        changed = edit_digest_issue(
            db,
            issue_id=issue.issue_id,
            admin_telegram_user_id=ADMIN_ID,
            expected_content_hash=issue.content_hash[:16],
            action="edit_item",
            position=1,
            text_value="Исправленный владельцем вывод без нового утверждения.",
        )
        assert changed.status == "updated"
        assert changed.issue is not None
        assert changed.issue.revision == 2
        assert db.get(WeeklyDigestIssue, issue.issue_id).status == "superseded"
        assert (
            db.query(WeeklyDigestIssueItem)
            .filter_by(issue_id=issue.issue_id, position=1)
            .one()
            .takeaway
            != "Исправленный владельцем вывод без нового утверждения."
        )
        assert (
            approve_digest_issue(
                db,
                issue_id=changed.issue.issue_id,
                admin_telegram_user_id=ADMIN_ID,
                expected_content_hash="0" * 16,
            ).status
            == "stale"
        )


def test_insufficient_content_cannot_be_approved_or_scheduled(monkeypatch) -> None:
    _configure(monkeypatch)
    _published_post(1, topic="strength")
    with get_session_context() as db:
        issue = create_digest_draft(db, admin_telegram_user_id=ADMIN_ID, now=NOW)
        assert issue.blockers == ("insufficient_content",)
        result = approve_digest_issue(
            db,
            issue_id=issue.issue_id,
            admin_telegram_user_id=ADMIN_ID,
            expected_content_hash=issue.content_hash[:16],
        )
        assert result.status == "quality_blocked"
        assert db.query(WeeklyDigestDelivery).count() == 0


def test_schedule_snapshots_recipients_and_unsubscribe_during_batch_cancels(monkeypatch) -> None:
    issue_id = _approved_issue(monkeypatch)
    user_id = _subscriber()
    with get_session_context() as db:
        issue = db.get(WeeklyDigestIssue, issue_id)
        result = schedule_digest_issue(
            db,
            issue_id=issue_id,
            admin_telegram_user_id=ADMIN_ID,
            expected_content_hash=issue.content_hash[:16],
            scheduled_local=datetime(2026, 8, 26, 15, 0),
            timezone_name="Europe/Moscow",
        )
        assert result.status == "scheduled"
        delivery = db.query(WeeklyDigestDelivery).filter_by(user_id=user_id).one()
        delivery.next_attempt_at = NOW - timedelta(minutes=1)

    with get_session_context() as db:
        delivery_id = claim_due_digest_deliveries(db)[0]
    with get_session_context() as db:
        set_digest_preference(db, telegram_user_id=9001, enabled=False)
    with get_session_context() as db:
        assert digest_delivery_payload(db, delivery_id) is None
        assert db.get(WeeklyDigestDelivery, delivery_id).status == "cancelled"


def test_worker_delivery_is_idempotent_and_blocked_chat_disables_future_digest(
    monkeypatch,
) -> None:
    issue_id = _approved_issue(monkeypatch)
    _subscriber()
    with get_session_context() as db:
        issue = db.get(WeeklyDigestIssue, issue_id)
        schedule_digest_issue(
            db,
            issue_id=issue_id,
            admin_telegram_user_id=ADMIN_ID,
            expected_content_hash=issue.content_hash[:16],
            scheduled_local=datetime(2026, 8, 26, 15, 0),
            timezone_name="Europe/Moscow",
        )
        delivery = db.query(WeeklyDigestDelivery).one()
        delivery.next_attempt_at = NOW - timedelta(minutes=1)

    sent: list[int] = []

    async def send(_client, chat_id, _text, **_kwargs):
        sent.append(chat_id)
        return 123

    async def no_wait(_self):
        return None

    monkeypatch.setattr(worker, "send_telegram_message", send)
    monkeypatch.setattr(worker.TelegramRateLimiter, "acquire", no_wait)
    asyncio.run(worker.run_weekly_digest_once())
    asyncio.run(worker.run_weekly_digest_once())
    assert sent == [9001]
    with get_session_context() as db:
        assert db.query(WeeklyDigestDelivery).one().status == "sent"
        assert db.get(WeeklyDigestIssue, issue_id).status == "sent"
        preference = db.query(WeeklyDigestPreference).one()
        assert preference.last_digest_issue_id == issue_id

    with get_session_context() as db:
        preference = db.query(WeeklyDigestPreference).one()
        preference.weekly_news_digest_enabled = True
        issue = db.get(WeeklyDigestIssue, issue_id)
        issue.status = "scheduled"
        delivery = db.query(WeeklyDigestDelivery).one()
        delivery.status = "processing"
        delivery.processing_started_at = NOW
        mark_digest_delivery_failed(
            db,
            delivery.id,
            error_code="telegram_chat_unavailable",
            terminal=True,
        )
        assert preference.weekly_news_digest_enabled is False
        assert preference.disabled_reason == "telegram_chat_unavailable"


def test_429_retry_after_is_persisted(monkeypatch) -> None:
    issue_id = _approved_issue(monkeypatch)
    _subscriber()
    with get_session_context() as db:
        issue = db.get(WeeklyDigestIssue, issue_id)
        schedule_digest_issue(
            db,
            issue_id=issue_id,
            admin_telegram_user_id=ADMIN_ID,
            expected_content_hash=issue.content_hash[:16],
            scheduled_local=datetime(2026, 8, 26, 15, 0),
            timezone_name="Europe/Moscow",
        )
        delivery = db.query(WeeklyDigestDelivery).one()
        delivery.status = "processing"
        delivery.processing_started_at = NOW
        mark_digest_delivery_failed(
            db,
            delivery.id,
            error_code="telegram_rate_limited",
            retry_after=timedelta(seconds=12),
        )
        assert delivery.status == "queued"
        assert delivery.next_attempt_at == NOW + timedelta(seconds=12)


@pytest.mark.parametrize("local_now", [datetime(2026, 8, 26, 23, 59), datetime(2026, 8, 27, 0, 0)])
def test_quiet_hours_delay_does_not_consult_product_notification_toggle(
    monkeypatch, local_now
) -> None:
    monkeypatch.setattr(notifications, "now_for_user_naive", lambda _user: local_now)
    issue_id = _approved_issue(monkeypatch)
    user_id = _subscriber()
    with get_session_context() as db:
        setting = NotificationSetting(
            user_id=user_id,
            telegram_enabled=False,
            quiet_hours_start=time(23, 0),
            quiet_hours_end=time(1, 0),
        )
        db.add(setting)
        db.flush()
        issue = db.get(WeeklyDigestIssue, issue_id)
        schedule_digest_issue(
            db,
            issue_id=issue_id,
            admin_telegram_user_id=ADMIN_ID,
            expected_content_hash=issue.content_hash[:16],
            scheduled_local=datetime(2026, 8, 26, 15, 0),
            timezone_name="Europe/Moscow",
        )
        delivery = db.query(WeeklyDigestDelivery).one()
        delivery.status = "processing"
        assert digest_delivery_payload(db, delivery.id) is None
        assert delivery.status == "queued"
        assert delivery.last_error_code == "quiet_hours"
        assert db.query(WeeklyDigestPreference).one().weekly_news_digest_enabled is True


def test_schedule_without_current_consent_recipients_stays_approved(monkeypatch) -> None:
    issue_id = _approved_issue(monkeypatch)
    with get_session_context() as db:
        issue = db.get(WeeklyDigestIssue, issue_id)
        result = schedule_digest_issue(
            db,
            issue_id=issue_id,
            admin_telegram_user_id=ADMIN_ID,
            expected_content_hash=issue.content_hash[:16],
            scheduled_local=datetime(2026, 8, 26, 15, 0),
            timezone_name="Europe/Moscow",
        )
        assert result.status == "no_recipients"
        assert issue.status == "approved"
        assert db.query(WeeklyDigestDelivery).count() == 0


def test_stale_or_mismatched_consent_version_cannot_authorize_delivery(
    monkeypatch,
) -> None:
    _configure(monkeypatch)
    with get_session_context() as db:
        with pytest.raises(ValueError, match="digest_consent_version_mismatch"):
            set_digest_preference(
                db,
                telegram_user_id=9001,
                enabled=True,
                presented_consent_version="weekly-news-v0",
            )
        assert db.query(WeeklyDigestPreference).count() == 0


def test_ambiguous_telegram_timeout_is_not_retried(monkeypatch) -> None:
    issue_id = _approved_issue(monkeypatch)
    _subscriber()
    with get_session_context() as db:
        issue = db.get(WeeklyDigestIssue, issue_id)
        schedule_digest_issue(
            db,
            issue_id=issue_id,
            admin_telegram_user_id=ADMIN_ID,
            expected_content_hash=issue.content_hash[:16],
            scheduled_local=datetime(2026, 8, 26, 15, 0),
            timezone_name="Europe/Moscow",
        )
        db.query(WeeklyDigestDelivery).one().next_attempt_at = NOW - timedelta(minutes=1)

    attempts = 0

    async def timeout_send(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("response lost after send")

    async def no_wait(_self):
        return None

    monkeypatch.setattr(worker, "send_telegram_message", timeout_send)
    monkeypatch.setattr(worker.TelegramRateLimiter, "acquire", no_wait)
    asyncio.run(worker.run_weekly_digest_once())
    asyncio.run(worker.run_weekly_digest_once())

    assert attempts == 1
    with get_session_context() as db:
        assert db.query(WeeklyDigestDelivery).one().status == "uncertain"
        assert db.get(WeeklyDigestIssue, issue_id).status == "sent"


def test_terminal_digest_retention_releases_publication_snapshots(monkeypatch) -> None:
    issue_id = _approved_issue(monkeypatch)
    _subscriber()
    with get_session_context() as db:
        issue = db.get(WeeklyDigestIssue, issue_id)
        issue.status = "sent"
        issue.created_at = NOW - timedelta(days=91)
        preference = db.query(WeeklyDigestPreference).one()
        preference.last_digest_issue_id = issue_id
        db.add(
            WeeklyDigestDelivery(
                issue_id=issue_id,
                user_id=preference.user_id,
                telegram_chat_id=9001,
                status="sent",
                attempt_count=1,
                sent_at=NOW - timedelta(days=90),
            )
        )
    with get_session_context() as db:
        assert prune_weekly_digest(db, retention_days=90) == 1
    with get_session_context() as db:
        assert db.get(WeeklyDigestIssue, issue_id) is None
        assert db.query(WeeklyDigestIssueItem).count() == 0
        assert db.query(WeeklyDigestDelivery).count() == 0
        assert db.query(WeeklyDigestPreference).one().last_digest_issue_id is None


def test_bot_api_rejects_non_admin_digest_draft(client, monkeypatch) -> None:
    _configure(monkeypatch)
    response = client.post(
        "/api/v1/bot/digest/issues/draft",
        headers={"X-Bot-Token": settings.bot_internal_token},
        json={"admin_telegram_user_id": 7999},
    )
    assert response.status_code == 403


def test_bot_api_preference_never_treats_start_or_read_as_consent(client, monkeypatch) -> None:
    _configure(monkeypatch)
    response = client.post(
        "/api/v1/bot/digest/preference",
        headers={"X-Bot-Token": settings.bot_internal_token},
        json={"telegram_user_id": 9001},
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    with get_session_context() as db:
        assert db.query(WeeklyDigestPreference).count() == 0
