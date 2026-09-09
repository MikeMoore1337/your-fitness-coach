from __future__ import annotations

import asyncio
import base64
import io
import secrets
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest
from PIL import Image, ImageChops
from sqlalchemy import event

from fitminiapp_api.core.config import Settings, settings
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.news import (
    NewsCluster,
    NewsDraftRevision,
    NewsImageRevision,
    NewsItem,
    NewsPublicationSnapshot,
    NewsReviewDelivery,
    NewsSource,
)
from fitminiapp_api.services import news_images, news_publication
from fitminiapp_api.services.news_content import (
    EditorialContent,
    parse_editorial_content,
)
from fitminiapp_api.services.news_drafts import (
    _validated_fields,
    evidence_packet,
    render_draft,
)
from fitminiapp_api.services.news_editorial import (
    compose_review_artifact,
    edit_text_revision,
    enqueue_review_deliveries,
    moderate_draft,
    review_message,
)
from fitminiapp_api.services.news_images import (
    NewsImageError,
    create_image_revision,
    create_uploaded_image_revision,
)
from fitminiapp_api.services.news_ingestion import (
    ParsedNewsItem,
    ingest_items,
    utcnow,
)
from fitminiapp_api.services.news_origin import HERMES_SUBMISSION_MARKER
from fitminiapp_api.services.news_post_management import manage_published_post
from fitminiapp_api.services.news_publication import (
    ARTIFACT_HASH_PREFIX_LENGTH,
    approve_publication,
    claim_due_publications,
    mark_publication_failed,
    mark_publication_succeeded,
    publication_payload,
    reconcile_uncertain_publication,
    retry_uncertain_publication,
)
from fitminiapp_api.services.news_review_schedule import current_news_review_slot
from fitminiapp_api.services.news_sources import (
    apply_source_allowlist,
    parse_source_allowlist,
)
from fitminiapp_api.services.news_state import transition_news_cluster
from fitminiapp_api.services.news_worker import (
    NewsCycleStats,
    deliver_review_queue,
    run_news_pipeline_once,
)
from fitminiapp_api.services.worker import (
    TelegramPublicationError,
    check_news_channel_rights,
    send_telegram_publication,
)


# Test-only stand-in for the state produced by the signed Hermes intake.
# The production YFC-local create_draft_revision capability is intentionally retired.
async def create_draft_revision(db, cluster, *, client=None) -> NewsDraftRevision:
    del client

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
    revision = cluster.latest_draft_revision + 1
    draft = NewsDraftRevision(
        id=secrets.token_hex(16),
        cluster_id=cluster.id,
        primary_item_id=packet.primary_item_id,
        revision=revision,
        provider="groq-free-candidate",
        model="test-hermes-model",
        prompt_version="test-hermes-editorial-v1",
        source_digest=packet.source_digest,
        evidence_item_ids=list(packet.evidence_item_ids),
        evidence_metadata={
            "topic": packet.topic,
            "score": packet.score,
            "score_version": cluster.score_version,
            "score_reasons": list(packet.score_reasons[:10]),
            "risk_flags": list(packet.risk_flags[:10]),
            "conflict_notes": list(cluster.conflict_notes[:10]),
            "supporting_source_count": len(packet.supporting_sources),
            "source_published_at": (
                packet.published_at.isoformat() if packet.published_at is not None else None
            ),
            "source_publisher": packet.publisher or packet.source_name,
            "image_context_headline": packet.title[:180],
            "editorial_contract_version": "news-editorial-v2",
            "editorial_fields": dict(fields),
            "trusted_source_url": packet.primary_url or packet.canonical_url,
            "publication_policy": "manual_required",
            "submitted_by": HERMES_SUBMISSION_MARKER,
        },
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
        reason_code="test_hermes_draft_received",
    )
    db.flush()
    return draft


def _source_and_candidate(*, external_id: str = "publication-1") -> str:
    title = "Resistance training changed a measured strength outcome"
    summary = "A controlled study reported a specific strength outcome."
    if external_id == "daily-0":
        title = "Dietary protein review changed nutrition context"
        summary = "A nutrition review compared dietary protein contexts."
    elif external_id == "daily-1":
        title = "Sleep duration cohort reported recovery associations"
        summary = "A sleep cohort reported recovery associations."
    definitions = parse_source_allowlist(
        [
            {
                "id": "publishing-journal",
                "name": "Publishing Journal",
                "type": "primary_research",
                "fetch_kind": "rss",
                "url": "https://publishing-journal.example/feed",
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
        source = db.get(NewsSource, "publishing-journal")
        assert source is not None
        counts = ingest_items(
            db,
            source,
            [
                ParsedNewsItem(
                    external_id=external_id,
                    canonical_url=f"https://publishing-journal.example/{external_id}",
                    primary_url=f"https://publishing-journal.example/{external_id}",
                    title=title,
                    summary=summary,
                    publisher="Publishing Journal",
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


def _jpeg_bytes(*, exif: bool = False) -> bytes:
    image = Image.new("RGB", (900, 600), "#345221")
    output = io.BytesIO()
    kwargs = {"exif": Image.Exif()} if exif else {}
    if exif:
        kwargs["exif"][0x010E] = "private editorial metadata"
    image.save(output, format="JPEG", **kwargs)
    return output.getvalue()


def _draft(cluster_id: str) -> tuple[str, str]:
    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        assert cluster is not None
        draft = asyncio.run(create_draft_revision(db, cluster))
        return draft.id, cluster.id


def _artifact_hash(db, draft: NewsDraftRevision) -> str:
    review = compose_review_artifact(db, draft)
    assert review.artifact is not None
    assert review.artifact_hash is not None
    return review.artifact_hash[:ARTIFACT_HASH_PREFIX_LENGTH]


def test_html_renderer_escapes_user_text_and_keeps_source_as_named_link() -> None:
    source_url = "https://example.test/research?a=1&b=2"
    content = EditorialContent(
        headline='Рост силы <контекст> & "границы"',
        summary="Первая строка <без HTML> & с кавычками.\n\nВторая строка — без разделителей.",
        why_it_matters="Это важно для корректной интерпретации & сравнения.",
        source_url=source_url,
    )

    composition = news_publication.compose_editorial_artifact(
        content,
        None,
        trusted_source_url=source_url,
    )

    assert composition.blockers == ()
    assert composition.artifact is not None
    artifact = composition.artifact
    assert artifact.parse_mode == "HTML"
    assert artifact.link_preview_disabled is True
    assert "&lt;контекст&gt; &amp;" in artifact.text
    assert "&lt;без HTML&gt; &amp;" in artifact.text
    assert '<a href="https://example.test/research?a=1&amp;b=2">Источник</a>' in artifact.text
    assert "ЗАГОЛОВОК" not in artifact.text
    assert "КРАТКО" not in artifact.text
    assert "────────" not in artifact.text
    assert artifact.text.startswith('<b>Рост силы &lt;контекст&gt; &amp; "границы"</b>')
    assert "<b>Почему это важно:</b>" not in artifact.text
    assert "\n\nЭто важно для корректной интерпретации &amp; сравнения.\n\n" in artifact.text
    assert artifact.text.count("https://") == 1


def test_review_artifact_blocks_source_outside_freshness_window() -> None:
    cluster_id = _source_and_candidate(external_id="stale-review")
    draft_id, _ = _draft(cluster_id)
    with get_session_context() as db:
        draft = db.get(NewsDraftRevision, draft_id)
        assert draft is not None
        stale = utcnow() - timedelta(days=61)
        draft.evidence_metadata = {
            **draft.evidence_metadata,
            "source_published_at": stale.isoformat(),
        }

        review = compose_review_artifact(db, draft, channel_ready=True)
        assert "source_not_current_month" in review.blockers


def test_scheduling_cannot_cross_source_freshness_window(monkeypatch) -> None:
    cluster_id = _source_and_candidate(external_id="cross-month-schedule")
    draft_id, _ = _draft(cluster_id)
    fixed_now = datetime(2026, 8, 26, 12, 0, 0)
    monkeypatch.setattr(settings, "news_publication_enabled", True)
    monkeypatch.setattr(settings, "news_channel_id", -1001234567890)
    monkeypatch.setattr(news_publication, "utcnow", lambda: fixed_now)
    with get_session_context() as db:
        draft = db.get(NewsDraftRevision, draft_id)
        assert draft is not None
        draft.warnings = []
        enqueue_review_deliveries(db, {7001})
        draft.evidence_metadata = {
            **draft.evidence_metadata,
            "source_published_at": "2026-06-28T12:00:00",
        }

        result = approve_publication(
            db,
            draft_id=draft.id,
            expected_image_revision=0,
            admin_telegram_user_id=7001,
            mode="scheduled",
            scheduled_local=datetime(2026, 9, 1, 12, 0, 0),
            timezone_name="Europe/Moscow",
            expected_artifact_hash=_artifact_hash(db, draft),
        )

        assert result.status == "quality_blocked"
        assert result.blockers == ("source_not_current_month_at_publication",)
        assert db.query(NewsPublicationSnapshot).count() == 0


def test_queued_publication_is_failed_after_freshness_window_rollover(monkeypatch) -> None:
    cluster_id = _source_and_candidate(external_id="month-rollover")
    draft_id, _ = _draft(cluster_id)
    august_now = datetime(2026, 8, 26, 12, 0, 0)
    monkeypatch.setattr(settings, "news_publication_enabled", True)
    monkeypatch.setattr(settings, "news_channel_id", -1001234567890)
    monkeypatch.setattr(news_publication, "utcnow", lambda: august_now)
    with get_session_context() as db:
        draft = db.get(NewsDraftRevision, draft_id)
        assert draft is not None
        draft.warnings = []
        enqueue_review_deliveries(db, {7001})
        draft.evidence_metadata = {
            **draft.evidence_metadata,
            "source_published_at": "2026-06-30T00:00:00",
        }
        approved = approve_publication(
            db,
            draft_id=draft.id,
            expected_image_revision=0,
            admin_telegram_user_id=7001,
            mode="immediate",
            expected_artifact_hash=_artifact_hash(db, draft),
        )
        assert approved.snapshot_id is not None
        snapshot = db.get(NewsPublicationSnapshot, approved.snapshot_id)
        assert snapshot is not None
        september_now = datetime(2026, 9, 1, 0, 0, 0)
        snapshot.next_attempt_at = september_now - timedelta(seconds=1)
        monkeypatch.setattr(news_publication, "utcnow", lambda: september_now)

        assert claim_due_publications(db) == []
        assert snapshot.status == "failed"
        assert snapshot.last_error_code == "source_not_current_month"


def test_brand_mark_is_in_the_top_right_safe_area(monkeypatch) -> None:
    cluster_id = _source_and_candidate(external_id="brand-mark-position")
    draft_id, _ = _draft(cluster_id)
    with get_session_context() as db:
        draft = db.get(NewsDraftRevision, draft_id)
        assert draft is not None
        base = Image.new("RGB", news_images.CANVAS_SIZE, "#101310")
        with_mark = news_images._draw_brand_overlay(base, draft)
        monkeypatch.setattr(news_images, "_brand_mark_path", lambda: None)
        without_mark = news_images._draw_brand_overlay(base, draft)

    bounds = ImageChops.difference(with_mark, without_mark).getbbox()
    assert bounds is not None
    left, top, right, bottom = bounds
    mark_x, mark_y = news_images.BRAND_MARK_POSITION
    mark_width, mark_height = news_images.BRAND_MARK_SIZE
    assert mark_x <= left < right <= mark_x + mark_width
    assert mark_y <= top < bottom <= mark_y + mark_height
    assert with_mark.getpixel((mark_x, mark_y)) == without_mark.getpixel((mark_x, mark_y))
    circle_left, circle_top, circle_right, circle_bottom = news_images.BRAND_CIRCLE_BOUNDS
    assert abs((2 * mark_x + mark_width) - (circle_left + circle_right)) <= 1
    assert abs((2 * mark_y + mark_height) - (circle_top + circle_bottom)) <= 1


def test_news_card_headline_is_centered_between_rubric_and_review_label() -> None:
    canvas = Image.new("RGB", news_images.CANVAS_SIZE, "#101310")
    draw = news_images.ImageDraw.Draw(canvas)
    rubric_font = news_images._font(24, bold=True)
    review_label_font = news_images._font(22)
    headline_font = news_images._font(55, bold=True)
    rubric_text = "ПИТАНИЕ И СПОРТПИТ"
    headline_text = "Новый материал о питании и\nспортивных добавках требует\nредакторской проверки"
    review_label_text = "Проверено редактором • Источник — в публикации"
    rubric_bounds = draw.textbbox(news_images.RUBRIC_POSITION, rubric_text, font=rubric_font)
    review_label_bounds = draw.textbbox(
        news_images.REVIEW_LABEL_POSITION,
        review_label_text,
        font=review_label_font,
    )

    headline_y = news_images._centered_headline_y(
        draw,
        headline_text,
        headline_font,
        rubric_bounds=rubric_bounds,
        review_label_bounds=review_label_bounds,
    )
    headline_bounds = draw.multiline_textbbox(
        (news_images.HEADLINE_X, headline_y),
        headline_text,
        font=headline_font,
        spacing=news_images.HEADLINE_SPACING,
    )

    top_gap = headline_bounds[1] - rubric_bounds[3]
    bottom_gap = review_label_bounds[1] - headline_bounds[3]
    assert abs(top_gap - bottom_gap) <= 1


def test_news_card_headline_keeps_all_words_and_fits_available_area() -> None:
    canvas = Image.new("RGB", news_images.CANVAS_SIZE, "#101310")
    draw = news_images.ImageDraw.Draw(canvas)
    rubric_font = news_images._font(24, bold=True)
    review_label_font = news_images._font(22)
    rubric_text = "РЕДАКЦИОННЫЙ РАЗБОР"
    review_label_text = "Проверено редактором • Источник — в публикации"
    headline = "Оценка воспринимаемой нагрузки (RPE) может отражать потерю скорости при приседе со средней нагрузкой"
    rubric_bounds = draw.textbbox(news_images.RUBRIC_POSITION, rubric_text, font=rubric_font)
    review_label_bounds = draw.textbbox(
        news_images.REVIEW_LABEL_POSITION,
        review_label_text,
        font=review_label_font,
    )

    headline_text, headline_font, headline_y = news_images._fit_headline_layout(
        draw,
        headline,
        rubric_bounds=rubric_bounds,
        review_label_bounds=review_label_bounds,
    )
    headline_lines = headline_text.splitlines()
    headline_bounds = draw.multiline_textbbox(
        (news_images.HEADLINE_X, headline_y),
        headline_text,
        font=headline_font,
        spacing=news_images.HEADLINE_SPACING,
    )

    assert " ".join(headline_text.split()) == headline
    assert max(draw.textlength(line, font=headline_font) for line in headline_lines) <= (
        news_images.HEADLINE_MAX_WIDTH
    )
    assert headline_bounds[1] >= rubric_bounds[3]
    assert headline_bounds[3] <= review_label_bounds[1]


def test_renderer_enforces_exact_telegram_photo_and_message_boundaries() -> None:
    source_url = "https://example.test/source"
    image = NewsImageRevision()

    photo_at_limit = news_publication.compose_editorial_artifact(
        EditorialContent(
            headline="Тест",
            summary="Я" * 1008,
            why_it_matters="",
            source_url=source_url,
        ),
        image,
        trusted_source_url=source_url,
    )
    assert photo_at_limit.artifact is not None
    assert photo_at_limit.artifact.visible_length == 1024
    assert photo_at_limit.artifact.limit == news_publication.TELEGRAM_PHOTO_CAPTION_LIMIT
    assert photo_at_limit.artifact.transport == "photo"
    assert "Почему это важно" not in photo_at_limit.artifact.text
    photo_over_limit = news_publication.compose_editorial_artifact(
        EditorialContent(
            headline="Тест",
            summary="Я" * 1009,
            why_it_matters="",
            source_url=source_url,
        ),
        image,
        trusted_source_url=source_url,
    )
    assert photo_over_limit.blockers == ("telegram_photo_caption_too_long",)

    assert photo_over_limit.transport == "photo"
    assert photo_over_limit.visible_length == 1025
    assert photo_over_limit.limit == 1024
    message_at_limit = news_publication.compose_editorial_artifact(
        EditorialContent(
            headline="Тест",
            summary="Я" * 4080,
            why_it_matters="",
            source_url=source_url,
        ),
        None,
        trusted_source_url=source_url,
    )
    assert message_at_limit.artifact is not None
    assert message_at_limit.artifact.visible_length == 4096
    assert message_at_limit.artifact.limit == news_publication.TELEGRAM_MESSAGE_LIMIT
    message_over_limit = news_publication.compose_editorial_artifact(
        EditorialContent(
            headline="Тест",
            summary="Я" * 4081,
            why_it_matters="",
            source_url=source_url,
        ),
        None,
        trusted_source_url=source_url,
    )
    assert message_over_limit.blockers == ("telegram_message_too_long",)

    assert message_over_limit.transport == "message"
    assert message_over_limit.visible_length == 4097
    assert message_over_limit.limit == 4096


def test_renderer_and_content_hash_are_stable_and_bind_delivery_policy() -> None:
    source_url = "https://example.test/source"
    content = EditorialContent("Заголовок", "Проверенная сводка.", "", source_url)
    first = news_publication.compose_editorial_artifact(
        content, None, trusted_source_url=source_url
    ).artifact
    second = news_publication.compose_editorial_artifact(
        content, None, trusted_source_url=source_url
    ).artifact
    assert first is not None and second is not None
    first_hash = news_publication.publication_content_hash(
        first, image_sha256=None, channel_id=-1001
    )
    same_hash = news_publication.publication_content_hash(
        second, image_sha256=None, channel_id=-1001
    )
    other_channel_hash = news_publication.publication_content_hash(
        second, image_sha256=None, channel_id=-1002
    )
    assert first == second
    assert first_hash == same_hash
    assert first_hash != other_channel_hash


def test_image_provider_is_free_only_and_requires_explicit_free_plan() -> None:
    base = {
        "_env_file": None,
        "app_env": "test",
        "secret_key": "task-89-free-provider-secret-key",
        "database_url": "sqlite://",
        "telegram_bot_token": "test",
        "news_image_provider": "cloudflare_workers_ai",
        "news_image_cloudflare_account_id": "account",
        "news_image_cloudflare_api_token": "token",
    }
    with pytest.raises(ValueError, match="FREE_PLAN_CONFIRMED"):
        Settings(**base)
    configured = Settings(**base, news_image_cloudflare_free_plan_confirmed=True)
    assert configured.news_image_model == "@cf/black-forest-labs/flux-1-schnell"
    assert configured.news_image_steps == 4
    with pytest.raises(ValueError):
        Settings(**{**base, "news_image_provider": "openai"})


def test_task88_editorial_contract_is_structured_and_source_bound() -> None:
    cluster_id = _source_and_candidate()
    draft_id, _ = _draft(cluster_id)
    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        draft = db.get(NewsDraftRevision, draft_id)
        assert cluster is not None and draft is not None
        assert draft.evidence_metadata["editorial_contract_version"] == "news-editorial-v2"
        assert draft.evidence_metadata["editorial_fields"]["headline"]
        assert draft.evidence_metadata["trusted_source_url"] == (
            "https://publishing-journal.example/publication-1"
        )
        parsed = parse_editorial_content(draft.draft_text)
        assert parsed is not None
        assert parsed.fields() == draft.evidence_metadata["editorial_fields"]
        asyncio.run(create_image_revision(db, cluster, draft, client=None))
        enqueue_review_deliveries(db, {7001})
        changed_source = edit_text_revision(
            db,
            draft_id=draft.id,
            expected_image_revision=cluster.current_image_revision,
            admin_telegram_user_id=7001,
            draft_text=draft.draft_text.replace(
                "https://publishing-journal.example/publication-1",
                "https://untrusted.example/replacement",
            ),
        )
        assert changed_source.status == "unavailable"
        assert cluster.latest_draft_revision == 1


def test_legacy_task88_revision_remains_parseable_for_existing_rows() -> None:
    legacy_text = (
        "Рубрика: Силовые тренировки\n\n"
        "Заголовок: Исследование уточнило контекст силовой адаптации\n\n"
        "Что произошло\nИсследователи сравнили две группы и описали ограничения выборки.\n\n"
        "Почему это важно\nКонтекст помогает корректно интерпретировать результат.\n\n"
        "Как применять / что не меняется\nНе менять программу только по одной публикации.\n\n"
        "Ограничения\nРезультат не является медицинской рекомендацией.\n\n"
        "Источник: Publishing Journal, 2026-08-25\n"
        "https://publishing-journal.example/legacy-publication"
    )

    parsed = parse_editorial_content(legacy_text)

    assert parsed is not None
    assert parsed.headline == "Исследование уточнило контекст силовой адаптации"
    assert parsed.summary.startswith("Исследователи сравнили две группы")
    assert parsed.why_it_matters == "Контекст помогает корректно интерпретировать результат."
    assert parsed.source_url == "https://publishing-journal.example/legacy-publication"


def test_production_channel_requires_explicit_owner_confirmation() -> None:
    values = {
        "_env_file": None,
        "app_debug": False,
        "secret_key": "task-89-production-secret-key-long-enough",
        "database_url": "sqlite://",
        "enable_dev_auth": False,
        "enable_web_auth": False,
        "enable_email_auth": False,
        "telegram_bot_token": "123456:configured-token",
        "bot_internal_token": "task-89-internal-token-that-is-long-enough",
        "frontend_base_url": "https://example.test",
        "admin_telegram_user_ids": "7001",
        "news_channel_id": -1001234567890,
        "news_channel_environment": "production",
        "news_ingestion_enabled": True,
        "news_publication_enabled": True,
    }
    for app_env in ("dev", "prod"):
        with pytest.raises(ValueError, match="NEWS_PRODUCTION_PUBLICATION_CONFIRMED"):
            Settings(**values, app_env=app_env)

        configured = Settings(
            **values,
            app_env=app_env,
            news_production_publication_confirmed=True,
        )
        assert configured.news_channel_environment == "production"
        assert configured.news_production_publication_confirmed is True


def test_prod_publishing_rejects_staging_channel_even_with_owner_confirmation() -> None:
    with pytest.raises(ValueError, match="NEWS_CHANNEL_ENVIRONMENT must be production"):
        Settings(
            _env_file=None,
            app_env="prod",
            app_debug=False,
            secret_key="task-89-production-secret-key-long-enough",
            database_url="sqlite://",
            enable_dev_auth=False,
            enable_web_auth=False,
            enable_email_auth=False,
            telegram_bot_token="123456:configured-token",
            bot_internal_token="task-89-internal-token-that-is-long-enough",
            frontend_base_url="https://example.test",
            admin_telegram_user_ids="7001",
            news_channel_id=-1001234567890,
            news_channel_environment="staging",
            news_ingestion_enabled=True,
            news_publication_enabled=True,
            news_production_publication_confirmed=True,
        )


def test_cloudflare_free_generation_is_news_specific_and_stores_provenance(monkeypatch) -> None:
    cluster_id = _source_and_candidate()
    draft_id, _ = _draft(cluster_id)
    monkeypatch.setattr(settings, "news_image_provider", "cloudflare_workers_ai")
    monkeypatch.setattr(settings, "news_image_cloudflare_account_id", "account")
    monkeypatch.setattr(settings, "news_image_cloudflare_api_token", "token")
    raw = _jpeg_bytes()

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/@cf/black-forest-labs/flux-1-schnell")
        body = request.content.decode()
        assert "Resistance training changed" in body
        assert "Topic category: fitness" in body
        assert "publishing-journal.example" not in body
        return httpx.Response(
            200,
            json={"success": True, "result": {"image": base64.b64encode(raw).decode()}},
        )

    async def generate() -> str:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with get_session_context() as db:
                cluster = db.get(NewsCluster, cluster_id)
                draft = db.get(NewsDraftRevision, draft_id)
                assert cluster is not None and draft is not None
                image = await create_image_revision(db, cluster, draft, client=client)
                return image.id

    image_id = asyncio.run(generate())
    with get_session_context() as db:
        image = db.get(NewsImageRevision, image_id)
        assert image is not None
        assert image.kind == "generated"
        assert image.provider == "cloudflare_workers_ai_free"
        assert image.generation_cost_microunits == 0
        assert image.safety_status == "generated_pending_review"
        assert image.provenance["source"] == "safe_editorial_summary"


def test_provider_failure_uses_template_and_upload_is_normalized(monkeypatch) -> None:
    cluster_id = _source_and_candidate()
    draft_id, _ = _draft(cluster_id)
    monkeypatch.setattr(settings, "news_image_provider", "cloudflare_workers_ai")
    monkeypatch.setattr(settings, "news_image_cloudflare_account_id", "account")
    monkeypatch.setattr(settings, "news_image_cloudflare_api_token", "token")

    async def generate() -> str:
        transport = httpx.MockTransport(lambda _: httpx.Response(503))
        async with httpx.AsyncClient(transport=transport) as client:
            with get_session_context() as db:
                cluster = db.get(NewsCluster, cluster_id)
                draft = db.get(NewsDraftRevision, draft_id)
                assert cluster is not None and draft is not None
                image = await create_image_revision(db, cluster, draft, client=client)
                return image.id

    image_id = asyncio.run(generate())
    with get_session_context() as db:
        image = db.get(NewsImageRevision, image_id)
        assert image is not None
        assert image.kind == "template"
        assert image.warnings == ["image_provider_unavailable"]
        cluster = db.get(NewsCluster, cluster_id)
        draft = db.get(NewsDraftRevision, draft_id)
        assert cluster is not None and draft is not None
        uploaded = create_uploaded_image_revision(db, cluster, draft, _jpeg_bytes(exif=True))
        with Image.open(io.BytesIO(uploaded.image_data)) as normalized:
            assert normalized.getexif() == {}
            assert normalized.size == (1200, 800)
        with pytest.raises(NewsImageError, match="image_decode_invalid"):
            create_uploaded_image_revision(db, cluster, draft, b"not-an-image")
        monkeypatch.setattr(settings, "news_image_upload_max_bytes", 32)
        with pytest.raises(NewsImageError, match="image_size_invalid"):
            create_uploaded_image_revision(db, cluster, draft, _jpeg_bytes())
        monkeypatch.setattr(settings, "news_image_upload_max_bytes", 8_388_608)
        too_small = io.BytesIO()
        Image.new("RGB", (120, 80), "white").save(too_small, format="JPEG")
        with pytest.raises(NewsImageError, match="image_dimensions_invalid"):
            create_uploaded_image_revision(db, cluster, draft, too_small.getvalue())


def test_exact_approval_is_idempotent_and_edit_revokes_schedule(monkeypatch) -> None:
    cluster_id = _source_and_candidate()
    draft_id, _ = _draft(cluster_id)
    monkeypatch.setattr(settings, "news_image_provider", "disabled")
    monkeypatch.setattr(settings, "news_publication_enabled", True)
    monkeypatch.setattr(settings, "news_channel_id", -1001234567890)
    monkeypatch.setattr(settings, "news_channel_username", "yfc_test_news")
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "7001")
    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        draft = db.get(NewsDraftRevision, draft_id)
        assert cluster is not None and draft is not None
        draft.warnings = []
        asyncio.run(create_image_revision(db, cluster, draft, client=None))
        enqueue_review_deliveries(db, {7001})
        image_revision = cluster.current_image_revision
        insert_order: list[str] = []

        def capture_insert(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
            normalized = statement.lower()
            if normalized.startswith("insert into news_review_decisions"):
                insert_order.append("decision")
            elif normalized.startswith("insert into news_publication_snapshots"):
                insert_order.append("snapshot")

        bind = db.get_bind()
        event.listen(bind, "before_cursor_execute", capture_insert)
        try:
            approved = approve_publication(
                db,
                draft_id=draft.id,
                expected_image_revision=image_revision,
                admin_telegram_user_id=7001,
                mode="immediate",
                expected_artifact_hash=_artifact_hash(db, draft),
            )
        finally:
            event.remove(bind, "before_cursor_execute", capture_insert)
        assert approved.status == "queued"
        assert insert_order == ["decision", "snapshot"]
        repeated = approve_publication(
            db,
            draft_id=draft.id,
            expected_image_revision=image_revision,
            admin_telegram_user_id=7001,
            mode="immediate",
            expected_artifact_hash=_artifact_hash(db, draft),
        )
        assert repeated.status == "already_queued"
        snapshot = db.get(NewsPublicationSnapshot, approved.snapshot_id)
        assert snapshot is not None
        payload = publication_payload(db, snapshot.id)
        assert payload is None  # Snapshot is immutable but not claimed yet.
        draft.warnings = ["deterministic_fallback_requires_editor", "invalid_draft_schema"]
        edited = edit_text_revision(
            db,
            draft_id=draft.id,
            expected_image_revision=image_revision,
            admin_telegram_user_id=7001,
            draft_text=draft.draft_text.replace(
                "Исследование тренировок: результаты для изученной группы",
                "Проверенный материал о фитнесе и тренировках",
            ),
        )
        assert edited.status == "queued"
        assert snapshot.status == "cancelled"
        assert snapshot.publication_text.startswith("<b>")
        assert '<a href="https://publishing-journal.example/publication-1">Источник</a>' in (
            snapshot.publication_text
        )
        assert snapshot.renderer_version == "news-publication-html-v1"
        assert snapshot.transport == "photo"
        assert snapshot.parse_mode == "HTML"
        assert snapshot.link_preview_disabled is True
        latest = (
            db.query(NewsDraftRevision)
            .filter(NewsDraftRevision.cluster_id == cluster.id)
            .order_by(NewsDraftRevision.revision.desc())
            .first()
        )
        assert latest is not None
        assert latest.evidence_metadata["editorial_fields"]["headline"] == (
            "Проверенный материал о фитнесе и тренировках"
        )
        assert latest.evidence_metadata["trusted_source_url"] == (
            "https://publishing-journal.example/publication-1"
        )
        assert latest.warnings == []


def test_no_image_snapshot_and_daily_cap_are_checked_when_claimed(monkeypatch) -> None:
    monkeypatch.setattr(settings, "news_publication_enabled", True)
    monkeypatch.setattr(settings, "news_channel_id", -1001234567890)
    monkeypatch.setattr(settings, "news_channel_username", "yfc_test_news")
    monkeypatch.setattr(settings, "news_daily_publication_limit", 1)
    snapshot_ids: list[str] = []
    for index in range(2):
        cluster_id = _source_and_candidate(external_id=f"daily-{index}")
        draft_id, _ = _draft(cluster_id)
        with get_session_context() as db:
            cluster = db.get(NewsCluster, cluster_id)
            draft = db.get(NewsDraftRevision, draft_id)
            assert cluster is not None and draft is not None
            draft.warnings = []
            enqueue_review_deliveries(db, {7001})
            assert cluster.current_image_revision == 0
            approved = approve_publication(
                db,
                draft_id=draft.id,
                expected_image_revision=0,
                admin_telegram_user_id=7001,
                mode="immediate",
                expected_artifact_hash=_artifact_hash(db, draft),
            )
            assert approved.status == "queued"
            assert approved.snapshot_id is not None
            snapshot_ids.append(approved.snapshot_id)
    with get_session_context() as db:
        first_claim = claim_due_publications(db, limit=1)
        assert len(first_claim) == 1
        claimed_id = first_claim[0]
        assert claimed_id in snapshot_ids
        payload = publication_payload(db, claimed_id)
        assert payload is not None
        assert payload.renderer_version == "news-publication-html-v1"
        assert payload.transport == "message"
        assert payload.parse_mode == "HTML"
        assert payload.link_preview_disabled is True
    with get_session_context() as db:
        second_claim = claim_due_publications(db, limit=5)
        assert second_claim == []
        rejected_id = next(value for value in snapshot_ids if value != claimed_id)
        second = db.get(NewsPublicationSnapshot, rejected_id)
        assert second is not None
        assert second.status == "failed"
        assert second.last_error_code == "daily_cap_reached"


def test_publisher_rejects_tampered_stored_snapshot(monkeypatch) -> None:
    cluster_id = _source_and_candidate(external_id="snapshot-tamper")
    draft_id, _ = _draft(cluster_id)
    monkeypatch.setattr(settings, "news_publication_enabled", True)
    monkeypatch.setattr(settings, "news_channel_id", -1001234567890)
    monkeypatch.setattr(settings, "news_channel_username", "yfc_test_news")
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "7001")
    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        draft = db.get(NewsDraftRevision, draft_id)
        assert cluster is not None and draft is not None
        draft.warnings = []
        enqueue_review_deliveries(db, {7001})
        approved = approve_publication(
            db,
            draft_id=draft.id,
            expected_image_revision=0,
            admin_telegram_user_id=7001,
            mode="immediate",
            expected_artifact_hash=_artifact_hash(db, draft),
        )
        assert approved.snapshot_id is not None
        assert claim_due_publications(db) == [approved.snapshot_id]
        snapshot = db.get(NewsPublicationSnapshot, approved.snapshot_id)
        assert snapshot is not None
        snapshot.publication_text += " "
        assert publication_payload(db, snapshot.id) is None
        assert snapshot.status == "failed"
        assert snapshot.last_error_code == "snapshot_content_hash_mismatch"


def test_channel_preflight_and_exact_text_photo_telegram_serialization(monkeypatch) -> None:
    monkeypatch.setattr(settings, "news_publication_enabled", True)
    monkeypatch.setattr(settings, "news_channel_id", -1001234567890)
    monkeypatch.setattr(settings, "telegram_bot_token", "bot-token")
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/getMe"):
            return httpx.Response(200, json={"ok": True, "result": {"id": 44}})
        if request.url.path.endswith("/getChatMember"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {"status": "administrator", "can_post_messages": True},
                },
            )
        return httpx.Response(
            200,
            json={"ok": True, "result": {"message_id": 91, "date": 1_787_600_000}},
        )

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            assert await check_news_channel_rights(client) is True
            result = await send_telegram_publication(
                client,
                -1001234567890,
                "Источник: https://example.test?a=1&b=<safe>",
                None,
            )
            assert result.message_id == 91
            html_result = await send_telegram_publication(
                client,
                -1001234567890,
                "<b>Проверенный заголовок</b>",
                None,
                parse_mode="HTML",
                link_preview_disabled=True,
            )
            assert html_result.message_id == 91
            photo_result = await send_telegram_publication(
                client,
                -1001234567890,
                "<b>Проверенный заголовок</b>",
                b"fake-jpeg",
                parse_mode="HTML",
                link_preview_disabled=True,
            )
            assert photo_result.message_id == 91

    asyncio.run(exercise())
    sent = requests[-3]
    assert sent.url.path.endswith("/sendMessage")
    body = sent.content.decode()
    assert "parse_mode" not in body
    assert "<safe>" in body
    html_body = requests[-2].content.decode()
    assert '"parse_mode":"HTML"' in html_body
    assert '"link_preview_options":{"is_disabled":true}' in html_body

    photo = requests[-1]
    assert photo.url.path.endswith("/sendPhoto")
    photo_body = photo.content.decode()
    assert 'name="caption"' in photo_body
    assert "<b>Проверенный заголовок</b>" in photo_body
    assert 'name="parse_mode"' in photo_body and "HTML" in photo_body

    async def malformed_success() -> None:
        transport = httpx.MockTransport(
            lambda _: httpx.Response(200, json={"ok": False, "result": {}})
        )
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(TelegramPublicationError) as raised:
                await send_telegram_publication(
                    client,
                    -1001234567890,
                    "Источник: https://example.test",
                    None,
                )
            assert raised.value.uncertain is True

    asyncio.run(malformed_success())


def test_post_edit_and_delete_are_owner_only_and_audited(monkeypatch) -> None:
    cluster_id = _source_and_candidate()
    draft_id, _ = _draft(cluster_id)
    monkeypatch.setattr(settings, "news_publication_enabled", True)
    monkeypatch.setattr(settings, "news_channel_id", -1001234567890)
    monkeypatch.setattr(settings, "news_channel_username", "yfc_test_news")
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "7001")
    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        draft = db.get(NewsDraftRevision, draft_id)
        assert cluster is not None and draft is not None
        draft.warnings = []
        enqueue_review_deliveries(db, {7001})
        invalid_schedule = approve_publication(
            db,
            draft_id=draft.id,
            expected_image_revision=0,
            admin_telegram_user_id=7001,
            mode="scheduled",
            scheduled_local=utcnow(),
            timezone_name="Europe/Moscow",
            expected_artifact_hash=_artifact_hash(db, draft),
        )
        assert invalid_schedule.status == "schedule_invalid"
        approved = approve_publication(
            db,
            draft_id=draft.id,
            expected_image_revision=0,
            admin_telegram_user_id=7001,
            mode="immediate",
            expected_artifact_hash=_artifact_hash(db, draft),
        )
        assert approved.snapshot_id is not None
        assert claim_due_publications(db) == [approved.snapshot_id]
        mark_publication_succeeded(
            db,
            approved.snapshot_id,
            message_id=77,
            message_date=utcnow(),
        )
        snapshot_id = approved.snapshot_id

    edited_text = (
        "ЗАГОЛОВОК\nПроверенная редакционная версия\n\n"
        "КРАТКО\nРедактор уточнил контекст новости, ограничения и границы применимости.\n\n"
        "ПОЧЕМУ ЭТО ВАЖНО\nКонтекст влияет на интерпретацию результата.\n\n"
        "ИСТОЧНИК\nPublishing Journal, 2026-08-25\n"
        "https://publishing-journal.example/publication-1"
    )

    successful_requests: list[httpx.Request] = []

    async def exercise() -> None:
        malformed_transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"ok": False}))
        async with httpx.AsyncClient(transport=malformed_transport) as malformed_client:
            with get_session_context() as db:
                malformed = await manage_published_post(
                    db,
                    snapshot_id=snapshot_id,
                    admin_telegram_user_id=7001,
                    action="edit",
                    text=edited_text,
                    client=malformed_client,
                )
                assert malformed.status == "unavailable"

        def respond(request: httpx.Request) -> httpx.Response:
            successful_requests.append(request)
            return httpx.Response(200, json={"ok": True})

        transport = httpx.MockTransport(respond)
        async with httpx.AsyncClient(transport=transport) as client:
            with get_session_context() as db:
                forbidden = await manage_published_post(
                    db,
                    snapshot_id=snapshot_id,
                    admin_telegram_user_id=7999,
                    action="edit",
                    text=edited_text,
                    client=client,
                )
                assert forbidden.status == "unavailable"
            with get_session_context() as db:
                edited = await manage_published_post(
                    db,
                    snapshot_id=snapshot_id,
                    admin_telegram_user_id=7001,
                    action="edit",
                    text=edited_text,
                    client=client,
                )
                assert edited.status == "updated"
            with get_session_context() as db:
                deleted = await manage_published_post(
                    db,
                    snapshot_id=snapshot_id,
                    admin_telegram_user_id=7001,
                    action="delete",
                    text=None,
                    client=client,
                )
                assert deleted.status == "deleted"

    asyncio.run(exercise())
    edit_request = successful_requests[0]
    assert edit_request.url.path.endswith("/editMessageText")
    edit_body = edit_request.content.decode()
    assert '"parse_mode":"HTML"' in edit_body
    assert '"link_preview_options":{"is_disabled":true}' in edit_body
    with get_session_context() as db:
        snapshot = db.get(NewsPublicationSnapshot, snapshot_id)
        assert snapshot is not None
        assert snapshot.telegram_edited_at is not None
        assert snapshot.telegram_deleted_at is not None
        assert snapshot.post_edit_content_hash is not None
        actions = {
            row.action
            for row in db.query(AuditEvent).filter(AuditEvent.resource_id == snapshot_id).all()
        }
        assert {"news.post_edit", "news.post_delete"}.issubset(actions)


def test_uncertain_send_never_retries_until_owner_reconciles(monkeypatch) -> None:
    cluster_id = _source_and_candidate()
    draft_id, _ = _draft(cluster_id)
    monkeypatch.setattr(settings, "news_publication_enabled", True)
    monkeypatch.setattr(settings, "news_channel_id", -1001234567890)
    monkeypatch.setattr(settings, "news_channel_username", "yfc_test_news")
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "7001")
    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        draft = db.get(NewsDraftRevision, draft_id)
        assert cluster is not None and draft is not None
        draft.warnings = []
        enqueue_review_deliveries(db, {7001})
        approved = approve_publication(
            db,
            draft_id=draft.id,
            expected_image_revision=0,
            admin_telegram_user_id=7001,
            mode="immediate",
            expected_artifact_hash=_artifact_hash(db, draft),
        )
        assert approved.snapshot_id is not None
        assert claim_due_publications(db) == [approved.snapshot_id]
        mark_publication_failed(
            db,
            approved.snapshot_id,
            error_code="telegram_send_timeout",
            uncertain=True,
        )
        assert claim_due_publications(db) == []
        assert retry_uncertain_publication(
            db,
            snapshot_id=approved.snapshot_id,
            admin_telegram_user_id=7001,
        )
        assert claim_due_publications(db) == [approved.snapshot_id]
        mark_publication_failed(
            db,
            approved.snapshot_id,
            error_code="telegram_send_timeout",
            uncertain=True,
        )
        assert reconcile_uncertain_publication(
            db,
            snapshot_id=approved.snapshot_id,
            admin_telegram_user_id=7001,
            channel_message_id=501,
        )
        snapshot = db.get(NewsPublicationSnapshot, approved.snapshot_id)
        assert snapshot is not None
        assert snapshot.status == "published"
        assert snapshot.telegram_permalink == "https://t.me/yfc_test_news/501"


def test_immediate_daily_cap_date_is_recomputed_at_claim_time(monkeypatch) -> None:
    cluster_id = _source_and_candidate()
    draft_id, _ = _draft(cluster_id)
    monkeypatch.setattr(settings, "news_publication_enabled", True)
    monkeypatch.setattr(settings, "news_channel_id", -1001234567890)
    monkeypatch.setattr(settings, "news_channel_username", "yfc_test_news")
    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        draft = db.get(NewsDraftRevision, draft_id)
        assert cluster is not None and draft is not None
        draft.warnings = []
        enqueue_review_deliveries(db, {7001})
        approved = approve_publication(
            db,
            draft_id=draft.id,
            expected_image_revision=0,
            admin_telegram_user_id=7001,
            mode="immediate",
            expected_artifact_hash=_artifact_hash(db, draft),
        )
        assert approved.snapshot_id is not None
        snapshot = db.get(NewsPublicationSnapshot, approved.snapshot_id)
        assert snapshot is not None
        fixed_now = utcnow() + timedelta(days=1)
        snapshot.next_attempt_at = fixed_now - timedelta(seconds=1)
        snapshot.publication_local_date = (fixed_now - timedelta(days=2)).date()
        monkeypatch.setattr(news_publication, "utcnow", lambda: fixed_now)
        assert claim_due_publications(db) == [approved.snapshot_id]
        expected_date = fixed_now.replace(tzinfo=UTC).astimezone(ZoneInfo(snapshot.timezone)).date()
        assert snapshot.publication_local_date == expected_date


def test_private_preview_matches_exact_artifact_and_retry_does_not_duplicate_it(
    monkeypatch,
) -> None:
    cluster_id = _source_and_candidate(external_id="preview-parity")
    draft_id, _ = _draft(cluster_id)
    monkeypatch.setattr(settings, "news_image_provider", "disabled")
    monkeypatch.setattr(settings, "news_publication_enabled", True)
    monkeypatch.setattr(settings, "news_channel_id", -1001234567890)
    monkeypatch.setattr(settings, "news_channel_username", "yfc_test_news")
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "7001")
    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        draft = db.get(NewsDraftRevision, draft_id)
        assert cluster is not None and draft is not None
        draft.warnings = []
        asyncio.run(create_image_revision(db, cluster, draft, client=None))
        enqueue_review_deliveries(db, {7001})
        expected = compose_review_artifact(db, draft, channel_ready=True)
        assert expected.artifact is not None
        assert expected.artifact_hash is not None
        assert expected.image is not None
        expected_text = expected.artifact.text
        expected_image_data = expected.image.image_data
        expected_hash = expected.artifact_hash

    preview_calls: list[dict[str, object]] = []
    control_calls: list[dict[str, object]] = []

    async def send_preview(
        _client,
        chat_id,
        text,
        image_data,
        *,
        parse_mode,
        link_preview_disabled,
    ):
        preview_calls.append(
            {
                "chat_id": chat_id,
                "text": text,
                "image_data": image_data,
                "parse_mode": parse_mode,
                "link_preview_disabled": link_preview_disabled,
            }
        )
        return SimpleNamespace(message_id=101, message_date=utcnow())

    async def send_control(_client, chat_id, text, *, reply_markup):
        control_calls.append(
            {
                "chat_id": chat_id,
                "text": text,
                "reply_markup": reply_markup,
            }
        )
        if len(control_calls) == 1:
            raise RuntimeError("simulated control-card failure")
        return 202

    stats = NewsCycleStats()

    async def deliver() -> int:
        async with httpx.AsyncClient() as client:
            return await deliver_review_queue(
                client,
                send_control,
                send_preview,
                channel_ready=True,
                cycle_stats=stats,
            )

    assert asyncio.run(deliver()) == 0
    assert stats.telegram_delivery_failures == 1
    with get_session_context() as db:
        delivery = db.query(NewsReviewDelivery).one()
        assert delivery.status == "queued"
        assert delivery.telegram_message_id == 101
        delivery.next_attempt_at = utcnow() - timedelta(seconds=1)

    assert asyncio.run(deliver()) == 1
    assert stats.telegram_delivery_failures == 1
    assert len(preview_calls) == 1
    assert len(control_calls) == 2
    preview = preview_calls[0]
    assert preview["chat_id"] == 7001
    assert preview["text"] == expected_text
    assert preview["image_data"] == expected_image_data
    assert preview["parse_mode"] == "HTML"
    assert preview["link_preview_disabled"] is True
    control = control_calls[-1]
    assert expected_text not in control["text"]
    callback_values = [
        button["callback_data"]
        for row in control["reply_markup"]["inline_keyboard"]
        for button in row
        if "callback_data" in button
    ]
    assert any(expected_hash[:16] in value for value in callback_values)
    with get_session_context() as db:
        delivery = db.query(NewsReviewDelivery).one()
        assert delivery.status == "sent"
        event = db.query(AuditEvent).filter_by(action="news.preview_created").one()
        assert event.details["artifact_hash"] == expected_hash
        assert event.details["preview_message_id"] == 101
        assert event.details["control_message_id"] == 202


def test_scheduled_review_delivery_sends_at_most_five_distinct_drafts(monkeypatch) -> None:
    definitions = parse_source_allowlist(
        [
            {
                "id": "batch-journal",
                "name": "Batch Journal",
                "type": "primary_research",
                "fetch_kind": "rss",
                "url": "https://batch-journal.example/feed",
                "language": "en",
                "enabled": True,
                "fetch_interval_minutes": 60,
                "trust_notes": "Primary publisher",
                "licensing_notes": "Metadata and short excerpt only",
            }
        ]
    )
    titles = (
        "Resistance training changed measured strength outcome",
        "Dietary protein review changed nutrition context",
        "Sleep duration cohort reported recovery associations",
        "Cardio interval study measured endurance outcome",
        "Mobility exercise study reported flexibility outcome",
        "Creatine supplement trial measured performance outcome",
    )
    with get_session_context() as db:
        apply_source_allowlist(db, definitions)
        source = db.get(NewsSource, "batch-journal")
        assert source is not None
        for index, title in enumerate(titles):
            counts = ingest_items(
                db,
                source,
                [
                    ParsedNewsItem(
                        external_id=f"batch-{index}",
                        canonical_url=f"https://batch-journal.example/batch-{index}",
                        primary_url=f"https://batch-journal.example/batch-{index}",
                        title=title,
                        summary=f"A controlled study reported the {title.lower()}.",
                        publisher="Batch Journal",
                        published_at=utcnow(),
                        doi=f"10.1000/batch-{index}",
                    )
                ],
                candidate_threshold=55,
            )
            assert counts["candidate"] == 1
            item = db.query(NewsItem).filter(NewsItem.external_id == f"batch-{index}").one()
            assert item.cluster_id is not None
            cluster = db.get(NewsCluster, item.cluster_id)
            assert cluster is not None
            draft = asyncio.run(create_draft_revision(db, cluster))
            draft.evidence_metadata = {
                **draft.evidence_metadata,
                "submitted_by": "hermes_narrow_intake",
            }
            draft.warnings = []
            asyncio.run(create_image_revision(db, cluster, draft, client=None))
        assert enqueue_review_deliveries(db, {7001}) == len(titles)

    monkeypatch.setattr(settings, "news_image_provider", "disabled")
    monkeypatch.setattr(settings, "news_publication_enabled", True)
    monkeypatch.setattr(settings, "news_channel_id", -1001234567890)
    monkeypatch.setattr(settings, "news_channel_username", "yfc_test_news")
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "7001")
    slot = current_news_review_slot(datetime(2026, 9, 8, 5, 5, 0, tzinfo=UTC))
    assert slot is not None
    preview_calls: list[int] = []
    control_calls: list[int] = []

    async def send_preview(_client, chat_id, *_args, **_kwargs):
        preview_calls.append(chat_id)
        return SimpleNamespace(message_id=700 + len(preview_calls), message_date=utcnow())

    async def send_control(_client, chat_id, *_args, **_kwargs):
        control_calls.append(chat_id)
        return 800 + len(control_calls)

    async def deliver() -> int:
        async with httpx.AsyncClient() as client:
            return await deliver_review_queue(
                client,
                send_control,
                send_preview,
                channel_ready=True,
                review_slot=slot,
            )

    assert asyncio.run(deliver()) == 5
    assert len(preview_calls) == 5
    assert len(control_calls) == 5
    with get_session_context() as db:
        statuses = [
            row.status for row in db.query(NewsReviewDelivery).order_by(NewsReviewDelivery.id)
        ]
        assert statuses.count("sent") == 5
        assert statuses.count("queued") == 1

    assert asyncio.run(deliver()) == 0
    assert len(preview_calls) == 5
    assert len(control_calls) == 5
    with get_session_context() as db:
        assert (
            db.query(NewsReviewDelivery).filter(NewsReviewDelivery.status == "queued").count() == 1
        )


def test_sensitive_hermes_warning_reaches_owner_card_but_not_publish_button(monkeypatch) -> None:
    cluster_id = _source_and_candidate(external_id="hermes-sensitive-card")
    draft_id, _ = _draft(cluster_id)
    monkeypatch.setattr(settings, "news_image_provider", "disabled")
    monkeypatch.setattr(settings, "news_publication_enabled", True)
    monkeypatch.setattr(settings, "news_channel_id", -1001234567890)
    monkeypatch.setattr(settings, "news_channel_username", "yfc_test_news")
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "7001")
    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        draft = db.get(NewsDraftRevision, draft_id)
        assert cluster is not None and draft is not None
        draft.evidence_metadata = {
            **draft.evidence_metadata,
            "submitted_by": "hermes_narrow_intake",
        }
        draft.warnings = ["medical_prescription_language"]
        asyncio.run(create_image_revision(db, cluster, draft, client=None))
        assert enqueue_review_deliveries(db, {7001}) == 1

    control_calls: list[dict[str, object]] = []

    async def send_preview(_client, _chat_id, *_args, **_kwargs):
        return SimpleNamespace(message_id=631, message_date=utcnow())

    async def send_control(_client, _chat_id, text, *, reply_markup):
        control_calls.append({"text": text, "reply_markup": reply_markup})
        return 632

    async def deliver() -> int:
        async with httpx.AsyncClient() as client:
            return await deliver_review_queue(
                client,
                send_control,
                send_preview,
                channel_ready=True,
            )

    assert asyncio.run(deliver()) == 1
    assert len(control_calls) == 1
    callback_values = [
        button["callback_data"]
        for row in control_calls[0]["reply_markup"]["inline_keyboard"]
        for button in row
        if "callback_data" in button
    ]
    assert "medical_prescription_language" in control_calls[0]["text"]
    assert not any(value.startswith("newsp:p:") for value in callback_values)
    with get_session_context() as db:
        assert db.query(NewsReviewDelivery).one().status == "sent"


def test_hermes_draft_reaches_telegram_when_legacy_fetch_is_disabled(monkeypatch) -> None:
    cluster_id = _source_and_candidate(external_id="hermes-downstream-enabled")
    draft_id, _ = _draft(cluster_id)
    monkeypatch.setattr(settings, "news_image_provider", "disabled")
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "7001")
    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        draft = db.get(NewsDraftRevision, draft_id)
        assert cluster is not None and draft is not None
        draft.evidence_metadata = {
            **draft.evidence_metadata,
            "submitted_by": "hermes_narrow_intake",
        }
        draft.warnings = []
        asyncio.run(create_image_revision(db, cluster, draft, client=None))
        assert enqueue_review_deliveries(db, {7001}) == 1

    preview_calls: list[int] = []
    control_calls: list[int] = []

    async def send_preview(_client, chat_id, *_args, **_kwargs):
        preview_calls.append(chat_id)
        return SimpleNamespace(message_id=611, message_date=utcnow())

    async def send_control(_client, chat_id, *_args, **_kwargs):
        control_calls.append(chat_id)
        return 612

    async def deliver() -> int:
        async with httpx.AsyncClient() as client:
            return await deliver_review_queue(
                client,
                send_control,
                send_preview,
                channel_ready=True,
            )

    assert asyncio.run(deliver()) == 1
    assert preview_calls == [7001]
    assert control_calls == [7001]
    with get_session_context() as db:
        delivery = db.query(NewsReviewDelivery).one()
        assert delivery.status == "sent"
        assert db.get(NewsDraftRevision, draft_id).evidence_metadata["submitted_by"] == (
            "hermes_narrow_intake"
        )


def test_owner_edited_hermes_revision_keeps_delivery_eligibility(monkeypatch) -> None:
    cluster_id = _source_and_candidate(external_id="hermes-owner-edit-marker")
    draft_id, _ = _draft(cluster_id)
    monkeypatch.setattr(settings, "news_image_provider", "disabled")
    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        draft = db.get(NewsDraftRevision, draft_id)
        assert cluster is not None and draft is not None
        draft.evidence_metadata = {
            **draft.evidence_metadata,
            "submitted_by": "hermes_narrow_intake",
        }
        draft.warnings = []
        asyncio.run(create_image_revision(db, cluster, draft, client=None))
        cluster.status = "awaiting_review"
        result = edit_text_revision(
            db,
            draft_id=draft.id,
            expected_image_revision=cluster.current_image_revision,
            admin_telegram_user_id=7001,
            draft_text=draft.draft_text,
        )
        assert result.status == "queued"
        edited = (
            db.query(NewsDraftRevision)
            .filter(NewsDraftRevision.cluster_id == cluster.id)
            .order_by(NewsDraftRevision.revision.desc())
            .first()
        )
        assert edited is not None and edited.id != draft.id
        assert edited.evidence_metadata["submitted_by"] == "hermes_narrow_intake"
        asyncio.run(create_image_revision(db, cluster, edited, client=None))
        assert enqueue_review_deliveries(db, {7001}) == 1


def test_hermes_regenerate_requeues_revision_without_legacy_candidate_generation(
    monkeypatch,
) -> None:
    cluster_id = _source_and_candidate(external_id="hermes-regenerate-disabled-legacy")
    draft_id, _ = _draft(cluster_id)
    monkeypatch.setattr(settings, "news_ingestion_enabled", True)
    monkeypatch.setattr(settings, "news_image_provider", "disabled")
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "7001")
    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        draft = db.get(NewsDraftRevision, draft_id)
        assert cluster is not None and draft is not None
        draft.evidence_metadata = {
            **draft.evidence_metadata,
            "submitted_by": "hermes_narrow_intake",
        }
        draft.warnings = []
        asyncio.run(create_image_revision(db, cluster, draft, client=None))
        assert enqueue_review_deliveries(db, {7001}) == 1
        result = moderate_draft(
            db,
            draft_id=draft.id,
            admin_telegram_user_id=7001,
            action="regenerate",
        )
        assert result.status == "queued"
        assert result.cluster_status == "draft_ready"
        assert cluster.status == "draft_ready"
        assert cluster.delivery_round == 1
        assert db.query(NewsReviewDelivery).one().status == "cancelled"

    preview_calls: list[int] = []
    control_calls: list[int] = []

    async def send_preview(_client, chat_id, *_args, **_kwargs):
        preview_calls.append(chat_id)
        return SimpleNamespace(message_id=621, message_date=utcnow())

    async def send_control(_client, chat_id, *_args, **_kwargs):
        control_calls.append(chat_id)
        return 622

    async def unused_publication(*_args, **_kwargs):
        raise AssertionError("publication is not part of Hermes regenerate review flow")

    asyncio.run(
        run_news_pipeline_once(
            send_message=send_control,
            send_preview=send_preview,
            send_publication=unused_publication,
            publication_ready=False,
        )
    )
    assert preview_calls == [7001]
    assert control_calls == [7001]
    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        assert cluster is not None and cluster.status == "awaiting_review"
        deliveries = db.query(NewsReviewDelivery).order_by(NewsReviewDelivery.id).all()
        assert [delivery.status for delivery in deliveries] == ["cancelled", "sent"]


def test_hermes_fallback_draft_is_not_delivered_or_requeued(monkeypatch) -> None:
    cluster_id = _source_and_candidate(external_id="hermes-fallback-delivery")
    draft_id, _ = _draft(cluster_id)
    monkeypatch.setattr(settings, "news_image_provider", "disabled")
    monkeypatch.setattr(settings, "news_publication_enabled", True)
    monkeypatch.setattr(settings, "news_channel_id", -1001234567890)
    monkeypatch.setattr(settings, "news_channel_username", "yfc_test_news")
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "7001")
    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        draft = db.get(NewsDraftRevision, draft_id)
        assert cluster is not None and draft is not None
        draft.evidence_metadata = {
            **draft.evidence_metadata,
            "submitted_by": "hermes_narrow_intake",
        }
        draft.warnings = [
            "deterministic_fallback_requires_editor",
            "provider_response_too_large",
        ]
        asyncio.run(create_image_revision(db, cluster, draft, client=None))
        assert enqueue_review_deliveries(db, {7001}) == 1

    preview_calls: list[int] = []
    control_calls: list[int] = []

    async def send_preview(_client, chat_id, *_args, **_kwargs):
        preview_calls.append(chat_id)
        return SimpleNamespace(message_id=601, message_date=utcnow())

    async def send_control(_client, chat_id, *_args, **_kwargs):
        control_calls.append(chat_id)
        return 602

    async def deliver() -> int:
        async with httpx.AsyncClient() as client:
            return await deliver_review_queue(
                client,
                send_control,
                send_preview,
                channel_ready=True,
            )

    delivered = asyncio.run(deliver())
    assert delivered == 0
    assert preview_calls == []
    assert control_calls == []
    with get_session_context() as db:
        delivery = db.query(NewsReviewDelivery).one()
        assert delivery.status == "failed"
        assert delivery.last_error_code == "preview_delivery_blocked"
        event = db.query(AuditEvent).filter_by(action="news.preview_delivery_blocked").one()
        assert (
            "unresolved_warning:deterministic_fallback_requires_editor" in event.details["blockers"]
        )
        assert "unresolved_warning:provider_response_too_large" in event.details["blockers"]
        assert enqueue_review_deliveries(db, {7001}) == 0


def test_overlong_hermes_preview_sends_recovery_control_card(monkeypatch) -> None:
    cluster_id = _source_and_candidate(external_id="overlong-delivery-guard")
    draft_id, _ = _draft(cluster_id)
    monkeypatch.setattr(settings, "news_image_provider", "disabled")
    monkeypatch.setattr(settings, "news_publication_enabled", True)
    monkeypatch.setattr(settings, "news_channel_id", -1001234567890)
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "7001")
    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        draft = db.get(NewsDraftRevision, draft_id)
        assert cluster is not None and draft is not None
        draft.evidence_metadata = {
            **draft.evidence_metadata,
            "submitted_by": "hermes_narrow_intake",
            "editorial_fields": {
                "headline": "Тест",
                "summary": "Я" * 1009,
                "why_it_matters": "",
            },
        }
        draft.warnings = []
        asyncio.run(create_image_revision(db, cluster, draft, client=None))
        assert enqueue_review_deliveries(db, {7001}) == 1

    preview_calls: list[int] = []
    control_calls: list[int] = []

    async def send_preview(_client, chat_id, *_args, **_kwargs):
        preview_calls.append(chat_id)
        return SimpleNamespace(message_id=603, message_date=utcnow())

    async def send_control(_client, chat_id, *_args, **_kwargs):
        control_calls.append(chat_id)
        return 604

    async def deliver() -> int:
        async with httpx.AsyncClient() as client:
            return await deliver_review_queue(
                client,
                send_control,
                send_preview,
                channel_ready=True,
            )

    delivered = asyncio.run(deliver())
    assert delivered == 1
    assert preview_calls == []
    assert control_calls == [7001]
    with get_session_context() as db:
        delivery = db.query(NewsReviewDelivery).one()
        assert delivery.status == "sent"
        assert delivery.last_error_code is None


def test_hermes_without_image_is_not_delivered_as_text_only(monkeypatch) -> None:
    cluster_id = _source_and_candidate(external_id="hermes-image-required")
    draft_id, _ = _draft(cluster_id)
    monkeypatch.setattr(settings, "news_publication_enabled", True)
    monkeypatch.setattr(settings, "news_channel_id", -1001234567890)
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "7001")
    with get_session_context() as db:
        draft = db.get(NewsDraftRevision, draft_id)
        assert draft is not None
        draft.evidence_metadata = {
            **draft.evidence_metadata,
            "submitted_by": "hermes_narrow_intake",
        }
        assert enqueue_review_deliveries(db, {7001}) == 1

    async def unexpected_send(*_args, **_kwargs):
        raise AssertionError("Hermes delivery requires an image preview")

    async def deliver() -> int:
        async with httpx.AsyncClient() as client:
            return await deliver_review_queue(
                client,
                unexpected_send,
                unexpected_send,
                channel_ready=True,
            )

    assert asyncio.run(deliver()) == 0
    with get_session_context() as db:
        delivery = db.query(NewsReviewDelivery).one()
        assert delivery.last_error_code == "preview_delivery_blocked"


def test_over_limit_photo_control_card_shows_measurement_and_recovery_actions(
    monkeypatch,
) -> None:
    cluster_id = _source_and_candidate(external_id="over-limit-control")
    draft_id, _ = _draft(cluster_id)
    monkeypatch.setattr(settings, "news_image_provider", "disabled")
    monkeypatch.setattr(settings, "news_publication_enabled", True)
    monkeypatch.setattr(settings, "news_channel_id", -1001234567890)
    monkeypatch.setattr(settings, "news_channel_username", "yfc_test_news")
    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        draft = db.get(NewsDraftRevision, draft_id)
        assert cluster is not None and draft is not None
        metadata = dict(draft.evidence_metadata)
        metadata["editorial_fields"] = {
            "headline": "Тест",
            "summary": "Я" * 1009,
            "why_it_matters": "",
        }
        draft.evidence_metadata = metadata
        draft.warnings = []
        asyncio.run(create_image_revision(db, cluster, draft, client=None))
        message, _, markup = review_message(db, draft, channel_ready=True)
        labels = {button["text"] for row in markup["inline_keyboard"] for button in row}
        assert "Точный preview: недоступен · photo · 1025/1024 символов" in message
        assert "telegram_photo_caption_too_long" in message
        assert "Опубликовать сейчас" not in labels
        assert {
            "Изменить текст",
            "Перегенерировать текст",
            "Убрать изображение",
            "Отклонить",
        }.issubset(labels)


def test_legacy_plain_snapshot_does_not_block_html_renderer_approval(monkeypatch) -> None:
    cluster_id = _source_and_candidate(external_id="renderer-cutover")
    draft_id, _ = _draft(cluster_id)
    monkeypatch.setattr(settings, "news_publication_enabled", True)
    monkeypatch.setattr(settings, "news_channel_id", -1001234567890)
    monkeypatch.setattr(settings, "news_channel_username", "yfc_test_news")
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "7001")
    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        draft = db.get(NewsDraftRevision, draft_id)
        assert cluster is not None and draft is not None
        draft.warnings = []
        enqueue_review_deliveries(db, {7001})
        artifact_hash = _artifact_hash(db, draft)
        first = approve_publication(
            db,
            draft_id=draft.id,
            expected_image_revision=0,
            admin_telegram_user_id=7001,
            mode="immediate",
            expected_artifact_hash=artifact_hash,
        )
        assert first.snapshot_id is not None
        old_snapshot = db.get(NewsPublicationSnapshot, first.snapshot_id)
        assert old_snapshot is not None
        old_snapshot.renderer_version = "news-publication-plain-v0"
        old_snapshot.content_hash = "0" * 64
        old_snapshot.idempotency_key = "1" * 64
        old_snapshot.publication_text = draft.draft_text
        old_snapshot.parse_mode = None
        old_snapshot.link_preview_disabled = False
        cluster.status = "awaiting_review"
        db.flush()
        second = approve_publication(
            db,
            draft_id=draft.id,
            expected_image_revision=0,
            admin_telegram_user_id=7001,
            mode="immediate",
            expected_artifact_hash=_artifact_hash(db, draft),
        )
        assert second.status == "queued"
        assert second.snapshot_id is not None and second.snapshot_id != old_snapshot.id
        assert old_snapshot.status == "cancelled"
        current = db.get(NewsPublicationSnapshot, second.snapshot_id)
        assert current is not None
        assert current.renderer_version == "news-publication-html-v1"
        assert current.parse_mode == "HTML"
        assert current.link_preview_disabled is True


def test_hermes_unsupported_number_reaches_owner_review_but_cannot_publish(
    monkeypatch,
) -> None:
    cluster_id = _source_and_candidate(external_id="hermes-unsupported-number-review")
    draft_id, _ = _draft(cluster_id)

    monkeypatch.setattr(settings, "news_image_provider", "disabled")
    monkeypatch.setattr(settings, "news_publication_enabled", True)
    monkeypatch.setattr(settings, "news_channel_id", -1001234567890)
    monkeypatch.setattr(settings, "news_channel_username", "yfc_test_news")
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "7001")

    with get_session_context() as db:
        cluster = db.get(NewsCluster, cluster_id)
        draft = db.get(NewsDraftRevision, draft_id)
        assert cluster is not None and draft is not None

        draft.evidence_metadata = {
            **draft.evidence_metadata,
            "submitted_by": "hermes_narrow_intake",
        }
        draft.warnings = ["unsupported_number"]

        asyncio.run(create_image_revision(db, cluster, draft, client=None))
        assert enqueue_review_deliveries(db, {7001}) == 1

    preview_calls: list[int] = []
    control_calls: list[dict[str, object]] = []

    async def send_preview(_client, chat_id, *_args, **_kwargs):
        preview_calls.append(chat_id)
        return SimpleNamespace(message_id=901, message_date=utcnow())

    async def send_control(_client, chat_id, text, *, reply_markup):
        control_calls.append(
            {
                "chat_id": chat_id,
                "text": text,
                "reply_markup": reply_markup,
            }
        )
        return 902

    async def deliver() -> int:
        async with httpx.AsyncClient() as client:
            return await deliver_review_queue(
                client,
                send_control,
                send_preview,
                channel_ready=True,
            )

    assert asyncio.run(deliver()) == 1
    assert preview_calls == [7001]
    assert len(control_calls) == 1

    control = control_calls[0]
    assert "unsupported_number" in control["text"]

    callback_values = [
        button["callback_data"]
        for row in control["reply_markup"]["inline_keyboard"]
        for button in row
        if "callback_data" in button
    ]

    assert not any(value.startswith("newsp:p:") for value in callback_values)
    assert not any(value.startswith("newsp:s:") for value in callback_values)

    with get_session_context() as db:
        delivery = db.query(NewsReviewDelivery).one()
        assert delivery.status == "sent"
        assert delivery.last_error_code is None
