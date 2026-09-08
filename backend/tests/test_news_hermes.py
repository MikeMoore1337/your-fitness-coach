import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime
from types import SimpleNamespace

from pydantic import SecretStr

from fitminiapp_api.core.config import settings
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.news import (
    HermesEditorialSubmission,
    NewsCluster,
    NewsDraftRevision,
    NewsReviewDelivery,
    NewsSource,
)
from fitminiapp_api.services import news_worker
from fitminiapp_api.services.news_hermes import _canonical_source_hash, hermes_signature
from fitminiapp_api.services.news_worker import run_news_pipeline_once


def _payload() -> dict:
    published_at = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    source = {
        "source_id": "journal-one",
        "external_id": "hermes-1",
        "canonical_url": "https://example.com/story",
        "primary_url": None,
        "title": "Исследование связало силовые тренировки с восстановлением",
        "summary": "Авторы изучили силовые тренировки и восстановление у взрослых.",
        "author": None,
        "publisher": "Journal One",
        "published_at": published_at.isoformat(),
        "updated_at": None,
        "doi": None,
    }
    source["content_hash"] = _canonical_source_hash(
        title=source["title"],
        summary=source["summary"],
        canonical_url=source["canonical_url"],
        published_at=published_at,
    )
    return {
        "schema_version": "hermes-editorial-intake-v1",
        "idempotency_key": "hermes-test-idempotency-1",
        "request_nonce": "hermes-test-nonce-1",
        "source": source,
        "draft": {
            "headline": "Силовые тренировки и восстановление: что показало исследование",
            "summary": "Авторы изучили связь силовых тренировок с восстановлением у взрослых. "
            "Результат относится к исследованной группе и не заменяет индивидуальную оценку.",
            "why_it_matters": "Данные помогают точнее обсуждать восстановление после нагрузки.",
        },
        "provenance": {
            "provider": "hermes",
            "model": "test-model",
            "prompt_version": "hermes-editorial-v1",
            "skill_version": "yfc-hermes-editorial-v1",
        },
    }


def _signed_headers(body: bytes) -> dict[str, str]:
    timestamp = str(int(time.time()))
    nonce = "hermes-test-nonce-1"
    return {
        "X-Hermes-Key-Id": "hermes-test",
        "X-Hermes-Timestamp": timestamp,
        "X-Hermes-Nonce": nonce,
        "X-Hermes-Signature": hermes_signature(
            "test-hermes-shared-secret-that-is-long-enough",
            timestamp=timestamp,
            nonce=nonce,
            body=body,
        ),
    }


def test_signed_hermes_intake_creates_preview_and_is_idempotent(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "hermes_intake_enabled", True)
    monkeypatch.setattr(settings, "hermes_intake_key_id", "hermes-test")
    monkeypatch.setattr(
        settings,
        "hermes_intake_shared_secret",
        SecretStr("test-hermes-shared-secret-that-is-long-enough"),
    )
    with get_session_context() as db:
        db.add(
            NewsSource(
                id="journal-one",
                name="Journal One",
                source_type="primary_research",
                fetch_kind="rss",
                feed_url="https://example.com/feed",
                language="en",
                enabled=True,
            )
        )

    body = json.dumps(_payload(), ensure_ascii=False, separators=(",", ":")).encode()
    headers = _signed_headers(body)
    first = client.post("/api/v1/hermes/editorial/intake", content=body, headers=headers)
    assert first.status_code == 200, first.text
    first_payload = first.json()
    assert first_payload["status"] == "accepted"
    assert first_payload["publication_policy"] == "manual_required"
    assert "силовые тренировки" in first_payload["preview_text"].lower()

    second = client.post("/api/v1/hermes/editorial/intake", content=body, headers=headers)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "duplicate"
    assert second.json()["draft_id"] == first_payload["draft_id"]
    with get_session_context() as db:
        assert db.query(HermesEditorialSubmission).count() == 1


def test_signed_hermes_intake_preserves_missing_source_publication_date(
    client, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "hermes_intake_enabled", True)
    monkeypatch.setattr(settings, "hermes_intake_key_id", "hermes-test")
    monkeypatch.setattr(
        settings,
        "hermes_intake_shared_secret",
        SecretStr("test-hermes-shared-secret-that-is-long-enough"),
    )
    with get_session_context() as db:
        db.add(
            NewsSource(
                id="journal-one",
                name="Journal One",
                source_type="primary_research",
                fetch_kind="rss",
                feed_url="https://example.com/feed",
                language="en",
                enabled=True,
            )
        )

    payload = _payload()
    payload["idempotency_key"] = "hermes-test-missing-published-at"
    payload["request_nonce"] = "hermes-test-nonce-1"
    payload["source"]["published_at"] = None
    payload["source"]["content_hash"] = _canonical_source_hash(
        title=payload["source"]["title"],
        summary=payload["source"]["summary"],
        canonical_url=payload["source"]["canonical_url"],
        published_at=None,
    )
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()

    response = client.post(
        "/api/v1/hermes/editorial/intake",
        content=body,
        headers=_signed_headers(body),
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "accepted"
    with get_session_context() as db:
        submission = db.query(HermesEditorialSubmission).one()
        draft = db.get(NewsDraftRevision, submission.draft_id)
        assert draft is not None
        assert draft.evidence_metadata["source_published_at"] is None


def test_hermes_intake_rejects_bad_signature_without_source_processing(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "hermes_intake_enabled", True)
    monkeypatch.setattr(settings, "hermes_intake_key_id", "hermes-test")
    monkeypatch.setattr(
        settings,
        "hermes_intake_shared_secret",
        SecretStr("test-hermes-shared-secret-that-is-long-enough"),
    )
    body = json.dumps(_payload(), ensure_ascii=False).encode()
    headers = _signed_headers(body)
    headers["X-Hermes-Signature"] = "sha256=" + hashlib.sha256(b"wrong").hexdigest()

    response = client.post("/api/v1/hermes/editorial/intake", content=body, headers=headers)

    assert response.status_code == 403


def test_hermes_image_pending_downstream_survives_disabled_legacy_fetch(
    client, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "hermes_intake_enabled", True)
    monkeypatch.setattr(settings, "hermes_intake_key_id", "hermes-test")
    monkeypatch.setattr(
        settings,
        "hermes_intake_shared_secret",
        SecretStr("test-hermes-shared-secret-that-is-long-enough"),
    )
    monkeypatch.setattr(settings, "news_ingestion_enabled", True)
    monkeypatch.setattr(settings, "news_legacy_source_fetch_enabled", False)
    monkeypatch.setattr(settings, "news_image_provider", "disabled")
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "7001")

    with get_session_context() as db:
        db.add(
            NewsSource(
                id="journal-one",
                name="Journal One",
                source_type="primary_research",
                fetch_kind="rss",
                feed_url="https://example.com/feed",
                language="en",
                enabled=True,
            )
        )

    body = json.dumps(_payload(), ensure_ascii=False, separators=(",", ":")).encode()
    intake = client.post(
        "/api/v1/hermes/editorial/intake",
        content=body,
        headers=_signed_headers(body),
    )
    assert intake.status_code == 200, intake.text
    assert intake.json()["status"] == "accepted"

    async def unexpected_fetch(_client):
        raise AssertionError("legacy source fetching must be disabled")

    async def unexpected_candidate_generation(*_args, **_kwargs):
        raise AssertionError("legacy candidate draft generation must be disabled")

    monkeypatch.setattr(news_worker, "fetch_due_sources", unexpected_fetch)
    monkeypatch.setattr(news_worker, "generate_candidate_drafts", unexpected_candidate_generation)
    preview_calls: list[int] = []
    control_calls: list[int] = []

    async def send_preview(_client, chat_id, *_args, **_kwargs):
        preview_calls.append(chat_id)
        return SimpleNamespace(message_id=501, message_date=datetime.now(UTC))

    async def send_control(_client, chat_id, *_args, **_kwargs):
        control_calls.append(chat_id)
        return 502

    async def send_publication(*_args, **_kwargs):
        raise AssertionError("publication is not part of this manual-required flow")

    asyncio.run(
        run_news_pipeline_once(
            send_message=send_control,
            send_preview=send_preview,
            send_publication=send_publication,
            publication_ready=True,
            fetch_sources=True,
        )
    )

    with get_session_context() as db:
        submission = db.query(HermesEditorialSubmission).one()
        draft = db.get(NewsDraftRevision, submission.draft_id)
        assert draft is not None
        assert draft.evidence_metadata["source_published_at"]
    assert preview_calls == [7001]
    assert control_calls == [7001]
    with get_session_context() as db:
        submission = db.query(HermesEditorialSubmission).one()
        cluster = db.get(NewsCluster, submission.cluster_id)
        assert cluster is not None
        assert cluster.status == "awaiting_review"
        assert cluster.current_image_revision == 1
        delivery = db.query(NewsReviewDelivery).one()
        assert delivery.status == "sent"


def test_hermes_sensitive_source_reaches_full_owner_card(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "hermes_intake_enabled", True)
    monkeypatch.setattr(settings, "hermes_intake_key_id", "hermes-test")
    monkeypatch.setattr(
        settings,
        "hermes_intake_shared_secret",
        SecretStr("test-hermes-shared-secret-that-is-long-enough"),
    )
    monkeypatch.setattr(settings, "news_ingestion_enabled", True)
    monkeypatch.setattr(settings, "news_legacy_source_fetch_enabled", False)
    monkeypatch.setattr(settings, "news_image_provider", "disabled")
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "7001")

    with get_session_context() as db:
        db.add(
            NewsSource(
                id="journal-one",
                name="Journal One",
                source_type="primary_research",
                fetch_kind="rss",
                feed_url="https://example.com/feed",
                language="en",
                enabled=True,
            )
        )

    payload = _payload()
    payload["idempotency_key"] = "hermes-sensitive-idempotency"
    payload["request_nonce"] = "hermes-sensitive-nonce"
    payload["source"]["title"] = "Исследование дозировки пептида для спорта"
    payload["source"]["summary"] = (
        "Фармакологическая работа рассмотрела дозировку пептида и ограничения "
        "результатов для самостоятельной интерпретации."
    )
    payload["draft"]["headline"] = "Исследование пептида: контекст результатов"
    payload["draft"]["summary"] = (
        "Работа описывает дозировку пептида и ограничения результатов без "
        "индивидуального назначения."
    )
    payload["source"]["content_hash"] = _canonical_source_hash(
        title=payload["source"]["title"],
        summary=payload["source"]["summary"],
        canonical_url=payload["source"]["canonical_url"],
        published_at=datetime.fromisoformat(payload["source"]["published_at"]),
    )
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    intake = client.post(
        "/api/v1/hermes/editorial/intake",
        content=body,
        headers=_signed_headers(body),
    )
    assert intake.status_code == 200, intake.text
    assert intake.json()["status"] == "accepted"
    assert intake.json()["publication_policy"] == "manual_required"

    preview_calls: list[int] = []
    control_calls: list[int] = []

    async def send_preview(_client, chat_id, *_args, **_kwargs):
        preview_calls.append(chat_id)
        return SimpleNamespace(message_id=511, message_date=datetime.now(UTC))

    async def send_control(_client, chat_id, *_args, **_kwargs):
        control_calls.append(chat_id)
        return 512

    async def send_publication(*_args, **_kwargs):
        raise AssertionError("manual-sensitive intake must not publish automatically")

    asyncio.run(
        run_news_pipeline_once(
            send_message=send_control,
            send_preview=send_preview,
            send_publication=send_publication,
            publication_ready=True,
            fetch_sources=True,
        )
    )

    assert preview_calls == [7001]
    assert control_calls == [7001]
    with get_session_context() as db:
        submission = db.query(HermesEditorialSubmission).one()
        draft = db.get(NewsDraftRevision, submission.draft_id)
        cluster = db.get(NewsCluster, submission.cluster_id)
        delivery = db.query(NewsReviewDelivery).one()
        assert draft is not None and cluster is not None
        assert "medical_prescription_language" in draft.warnings
        assert any(flag.startswith("prohibited_") for flag in cluster.risk_flags)
        assert cluster.status == "awaiting_review"
        assert delivery.status == "sent"
