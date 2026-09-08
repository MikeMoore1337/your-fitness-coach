import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from time import monotonic
from unittest.mock import AsyncMock

import httpx
import pytest

from fitminiapp_api.core.logging_config import JsonFormatter
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.notification import Notification, NotificationSetting
from fitminiapp_api.models.program import ProgramTemplate, UserProgram, UserWorkout
from fitminiapp_api.models.user import User, UserProfile
from fitminiapp_api.services import notifications as notification_service
from fitminiapp_api.services import worker
from fitminiapp_api.services.news_review_schedule import current_news_review_slot
from fitminiapp_api.services.notifications import (
    NOTIFICATION_FALLBACK,
    NotificationDeliveryError,
    cancel_workout_reminder,
    mark_delivery_failed,
    safe_delivery_error,
)
from fitminiapp_api.services.worker import (
    TelegramRateLimiter,
    _log_delivery_failure,
    send_telegram_message,
    telegram_transport_options,
)

SECRET_TOKEN = "123456:telegram-secret-token"


def test_worker_uses_dedicated_bot_api_proxy(monkeypatch) -> None:
    monkeypatch.setattr(
        "fitminiapp_api.services.worker.settings.telegram_bot_proxy_url",
        "socks5://bot-proxy.test:1081",
    )
    assert telegram_transport_options() == {
        "trust_env": False,
        "proxy": "socks5://bot-proxy.test:1081",
    }


def test_worker_does_not_reuse_telegram_oauth_proxy(monkeypatch) -> None:
    monkeypatch.setattr(
        "fitminiapp_api.services.worker.settings.telegram_bot_proxy_url",
        "",
    )
    monkeypatch.setattr(
        "fitminiapp_api.services.worker.settings.telegram_oauth_proxy_url",
        "socks5://telegram-proxy.test:1081",
    )

    assert telegram_transport_options() == {"trust_env": False}


def test_worker_does_not_inherit_ambient_proxy(monkeypatch) -> None:
    monkeypatch.setattr(
        "fitminiapp_api.services.worker.settings.telegram_bot_proxy_url",
        "",
    )
    monkeypatch.setattr(
        "fitminiapp_api.services.worker.settings.telegram_oauth_proxy_url",
        "",
    )

    assert telegram_transport_options() == {"trust_env": False}


def telegram_http_error(status_code: int = 500) -> httpx.HTTPStatusError:
    request = httpx.Request(
        "POST",
        f"https://api.telegram.org/bot{SECRET_TOKEN}/sendMessage",
    )
    response = httpx.Response(status_code, request=request, json={"ok": False})
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        return error
    raise AssertionError("expected an HTTPStatusError")


@pytest.mark.parametrize(
    ("status_code", "payload", "expected_code"),
    [
        (
            429,
            {"ok": False, "error_code": 429, "parameters": {"retry_after": 17}},
            "telegram_rate_limited",
        ),
        (500, {"ok": False, "error_code": 500}, "telegram_http_status:500"),
    ],
)
def test_telegram_delivery_classifies_retryable_http_errors(
    status_code: int,
    payload: dict,
    expected_code: str,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, request=request, json=payload)

    async def deliver() -> None:
        transport = httpx.MockTransport(respond)
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(NotificationDeliveryError) as exc_info:
                await send_telegram_message(client, 123456, "test notification")
        assert exc_info.value.code == expected_code
        if status_code == 429:
            assert exc_info.value.retry_after == timedelta(seconds=17)

    asyncio.run(deliver())


@pytest.mark.parametrize(
    ("status_code", "description"),
    [(403, "Forbidden: bot was blocked by the user"), (400, "Bad Request: chat not found")],
)
def test_telegram_delivery_classifies_unavailable_private_chat_as_terminal(
    status_code: int,
    description: str,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            request=request,
            json={"ok": False, "error_code": status_code, "description": description},
        )

    async def deliver() -> None:
        transport = httpx.MockTransport(respond)
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(NotificationDeliveryError) as exc_info:
                await send_telegram_message(client, 123456, "test notification")
        assert exc_info.value.code == "telegram_chat_unavailable"
        assert exc_info.value.terminal_status == "cancelled"

    asyncio.run(deliver())


def test_telegram_delivery_propagates_timeout() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Telegram timed out", request=request)

    async def deliver() -> None:
        transport = httpx.MockTransport(timeout)
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(httpx.ReadTimeout, match="Telegram timed out"):
                await send_telegram_message(client, 123456, "test notification")

    asyncio.run(deliver())


def test_disabled_telegram_delivery_is_not_marked_as_sent_or_logged_with_chat_id(
    monkeypatch,
    caplog,
) -> None:
    monkeypatch.setattr(worker.settings, "telegram_bot_token", "")

    async def deliver() -> None:
        async with httpx.AsyncClient() as client:
            with pytest.raises(NotificationDeliveryError) as exc_info:
                await send_telegram_message(client, 987654321, "private notification")
            assert exc_info.value.code == "bot_token_not_configured"
            assert exc_info.value.terminal_status == "failed"

    with caplog.at_level(logging.INFO, logger="fitminiapp_api.services.worker"):
        asyncio.run(deliver())

    assert "987654321" not in caplog.text


def test_telegram_delivery_rejects_external_or_non_app_action_urls() -> None:
    async def deliver() -> None:
        async with httpx.AsyncClient() as client:
            with pytest.raises(ValueError, match="unsafe notification action URL"):
                await send_telegram_message(
                    client,
                    123456,
                    "test notification",
                    open_app_path="https://attacker.example/app",
                )
            with pytest.raises(ValueError, match="unsafe notification action URL"):
                await send_telegram_message(
                    client,
                    123456,
                    "test notification",
                    open_app_path="/admin",
                )

    asyncio.run(deliver())


def test_telegram_delivery_serializes_exact_canonical_webapp_destination(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, request=request, json={"ok": True, "result": {}})

    async def deliver() -> None:
        transport = httpx.MockTransport(respond)
        async with httpx.AsyncClient(transport=transport) as client:
            await send_telegram_message(
                client,
                123456,
                "Нейтральный текст",
                open_app_path="/app?section=progress&weekly_review=1",
            )

    monkeypatch.setattr(
        worker.settings,
        "frontend_base_url",
        "https://app.your-fitness-coach.ru",
    )
    asyncio.run(deliver())

    assert captured == {
        "chat_id": 123456,
        "text": "Нейтральный текст",
        "reply_markup": {
            "inline_keyboard": [
                [
                    {
                        "text": "Открыть приложение",
                        "web_app": {
                            "url": (
                                "https://app.your-fitness-coach.ru/"
                                "app?section=progress&weekly_review=1"
                            )
                        },
                    }
                ]
            ]
        },
    }


def test_telegram_rate_limiter_spaces_concurrent_sends() -> None:
    current = 0.0
    delays: list[float] = []

    def clock() -> float:
        return current

    async def sleep(delay: float) -> None:
        nonlocal current
        delays.append(delay)
        current += delay

    async def acquire_three() -> None:
        limiter = TelegramRateLimiter(2, clock=clock, sleep=sleep)
        await asyncio.gather(*(limiter.acquire() for _ in range(3)))

    asyncio.run(acquire_three())
    assert delays == [0.5, 0.5]


def test_worker_rate_limits_send_starts_after_waiting_for_delivery_slot(monkeypatch) -> None:
    fixed_now = datetime(2026, 8, 24, 6)
    monkeypatch.setattr(notification_service, "utcnow", lambda: fixed_now)
    monkeypatch.setattr(worker.settings, "notification_delivery_concurrency", 1)
    send_started_at: list[float] = []

    async def timed_send(_client, _chat_id, _text, *, open_app_path=None) -> None:
        del open_app_path
        send_started_at.append(monotonic())
        if len(send_started_at) == 1:
            await asyncio.sleep(0.2)

    monkeypatch.setattr(worker, "send_telegram_message", timed_send)

    with get_session_context() as session:
        user = User(telegram_user_id=977020, is_coach=False)
        session.add(user)
        session.flush()
        session.add(UserProfile(user_id=user.id, timezone="Europe/Moscow"))
        session.add(NotificationSetting(user_id=user.id))
        session.add_all(
            [
                Notification(
                    user_id=user.id,
                    channel="telegram",
                    category="trainer_program_update",
                    event_kind="transactional",
                    title=f"Программа {index}",
                    body="Body",
                    scheduled_for=fixed_now,
                    scheduled_for_utc=fixed_now,
                    status="queued",
                    action_url="/app?section=programs",
                )
                for index in range(4)
            ]
        )
        session.commit()

    asyncio.run(worker.run_once(sync_reminders=False))

    assert len(send_started_at) == 4
    gaps = [later - earlier for earlier, later in pairwise(send_started_at)]
    assert min(gaps) >= 0.04


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (telegram_http_error(429), "http_status:429"),
        (httpx.ReadTimeout("secret timeout details"), "timeout"),
        (httpx.ConnectError("secret transport details"), "transport_error"),
        (
            NotificationDeliveryError("telegram_chat_unavailable", terminal_status="cancelled"),
            "telegram_chat_unavailable",
        ),
        (RuntimeError("secret unexpected details"), "unexpected:RuntimeError"),
    ],
)
def test_delivery_error_is_reduced_to_safe_diagnostic_code(
    error: Exception,
    expected: str,
) -> None:
    diagnostic = safe_delivery_error(error)

    assert diagnostic == expected
    assert SECRET_TOKEN not in diagnostic
    assert "api.telegram.org" not in diagnostic
    assert "secret" not in diagnostic


def test_delivery_failure_does_not_persist_telegram_url_or_token() -> None:
    scheduled_for = datetime(2026, 8, 9, 12)
    with get_session_context() as session:
        user = session.query(User).first()
        assert user is not None
        notification = Notification(
            user_id=user.id,
            title="Sensitive failure test",
            body="Body",
            scheduled_for=scheduled_for,
            scheduled_for_utc=scheduled_for,
            status="processing",
            attempt_count=0,
        )
        session.add(notification)
        session.flush()
        notification_id = notification.id
        mark_delivery_failed(session, notification, telegram_http_error())

    with get_session_context() as session:
        stored = session.query(Notification).filter(Notification.id == notification_id).one()
        assert stored.last_error == "http_status:500"
        assert SECRET_TOKEN not in stored.last_error
        assert "api.telegram.org" not in stored.last_error


def test_delivery_failure_json_log_excludes_exception_and_sensitive_url(caplog) -> None:
    with caplog.at_level(logging.ERROR, logger="fitminiapp_api.services.worker"):
        _log_delivery_failure(42, telegram_http_error())

    record = caplog.records[-1]
    rendered = JsonFormatter(service="notification-worker").format(record)
    payload = json.loads(rendered)

    assert record.exc_info is None
    assert payload["message"] == "notification_delivery_failed"
    assert payload["notification_ref"].startswith("notification:")
    assert payload["notification_ref"] != "notification:42"
    assert "notification_id" not in payload
    assert payload["delivery_error"] == "http_status:500"
    assert SECRET_TOKEN not in rendered
    assert "api.telegram.org" not in rendered


def test_retry_after_and_terminal_chat_outcomes_update_canonical_status(monkeypatch) -> None:
    fixed_now = datetime(2026, 8, 24, 6)
    monkeypatch.setattr(notification_service, "utcnow", lambda: fixed_now)
    with get_session_context() as session:
        user = session.query(User).first()
        assert user is not None
        rate_limited = Notification(
            user_id=user.id,
            title="Rate limited",
            body="Body",
            scheduled_for=fixed_now,
            scheduled_for_utc=fixed_now,
            status="processing",
        )
        blocked = Notification(
            user_id=user.id,
            title="Blocked",
            body="Body",
            scheduled_for=fixed_now,
            scheduled_for_utc=fixed_now,
            status="processing",
        )
        session.add_all([rate_limited, blocked])
        session.flush()

        mark_delivery_failed(
            session,
            rate_limited,
            NotificationDeliveryError(
                "telegram_rate_limited",
                retry_after=timedelta(seconds=23),
            ),
            commit=False,
        )
        mark_delivery_failed(
            session,
            blocked,
            NotificationDeliveryError(
                "telegram_chat_unavailable",
                terminal_status="cancelled",
            ),
            commit=False,
        )
        session.commit()

        assert rate_limited.status == "queued"
        assert rate_limited.next_attempt_at == fixed_now + timedelta(seconds=23)
        assert rate_limited.last_error == "telegram_rate_limited"
        assert blocked.status == "cancelled"
        assert blocked.next_attempt_at is None
        assert blocked.last_error == "telegram_chat_unavailable"


def test_worker_resolves_wrong_or_stale_target_to_safe_fallback(monkeypatch) -> None:
    fixed_now = datetime(2026, 8, 24, 6)
    monkeypatch.setattr(notification_service, "utcnow", lambda: fixed_now)
    send = AsyncMock()
    monkeypatch.setattr(worker, "send_telegram_message", send)

    with get_session_context() as session:
        user = User(telegram_user_id=977001, is_coach=False)
        session.add(user)
        session.flush()
        session.add(UserProfile(user_id=user.id, timezone="Europe/Moscow"))
        session.add(NotificationSetting(user_id=user.id))
        event = Notification(
            user_id=user.id,
            channel="telegram",
            category="trainer_comment",
            event_kind="transactional",
            title="Комментарий",
            body="Чувствительный текст",
            scheduled_for=fixed_now,
            scheduled_for_utc=fixed_now,
            status="queued",
            action_url="/app?workout_id=999999&comment_id=999999",
        )
        session.add(event)
        session.commit()
        event_id = event.id

    asyncio.run(worker.run_once(sync_reminders=False))

    assert send.await_count == 1
    assert send.await_args.kwargs["open_app_path"] == NOTIFICATION_FALLBACK
    assert "Чувствительный" not in send.await_args.args[2]
    with get_session_context() as session:
        stored = session.get(Notification, event_id)
        assert stored is not None
        assert stored.status == "sent"


def test_worker_rechecks_workout_invalidation_immediately_before_send(monkeypatch) -> None:
    fixed_now = datetime(2026, 8, 24, 6)
    monkeypatch.setattr(notification_service, "utcnow", lambda: fixed_now)
    send = AsyncMock()
    monkeypatch.setattr(worker, "send_telegram_message", send)

    with get_session_context() as session:
        user = User(telegram_user_id=977002, is_coach=False)
        session.add(user)
        session.flush()
        session.add(UserProfile(user_id=user.id, timezone="Europe/Moscow"))
        session.add(NotificationSetting(user_id=user.id))
        template = session.query(ProgramTemplate).first()
        assert template is not None
        program = UserProgram(user_id=user.id, template_id=template.id, is_active=True)
        session.add(program)
        session.flush()
        workout = UserWorkout(
            user_program_id=program.id,
            scheduled_date=fixed_now.date(),
            scheduled_time=None,
            day_number=1,
            title="Тренировка",
            status="planned",
        )
        session.add(workout)
        session.flush()
        event = Notification(
            user_id=user.id,
            channel="telegram",
            category="workout_reminder",
            event_kind="reminder",
            title="Скоро тренировка",
            body="Внутренние подробности",
            scheduled_for=fixed_now,
            scheduled_for_utc=fixed_now,
            status="queued",
            dedupe_key=f"workout:{workout.id}:reminder",
            action_url="/app?section=today",
        )
        session.add(event)
        session.commit()
        workout_id = workout.id
        event_id = event.id

    async def cancel_before_preflight(_limiter) -> None:
        with get_session_context() as session:
            workout = session.get(UserWorkout, workout_id)
            assert workout is not None
            workout.status = "skipped"
            assert cancel_workout_reminder(session, workout.id) == 1

    monkeypatch.setattr(worker.TelegramRateLimiter, "acquire", cancel_before_preflight)

    asyncio.run(worker.run_once(sync_reminders=False))

    send.assert_not_awaited()
    with get_session_context() as session:
        stored = session.get(Notification, event_id)
        assert stored is not None
        assert stored.status == "cancelled"
        assert stored.last_error == "workout_reminder_invalidated"


def test_worker_rechecks_invalidation_after_waiting_for_delivery_slot(monkeypatch) -> None:
    fixed_now = datetime(2026, 8, 24, 6)
    monkeypatch.setattr(notification_service, "utcnow", lambda: fixed_now)
    monkeypatch.setattr(worker.settings, "notification_delivery_concurrency", 1)
    first_send_started = asyncio.Event()
    release_first_send = asyncio.Event()
    delivered_chat_ids: list[int] = []

    async def no_rate_delay(_limiter) -> None:
        return None

    async def blocking_send(_client, chat_id, _text, *, open_app_path=None) -> None:
        del open_app_path
        delivered_chat_ids.append(chat_id)
        if chat_id == 977010:
            first_send_started.set()
            await release_first_send.wait()

    monkeypatch.setattr(worker.TelegramRateLimiter, "acquire", no_rate_delay)
    monkeypatch.setattr(worker, "send_telegram_message", blocking_send)

    with get_session_context() as session:
        first_user = User(telegram_user_id=977010, is_coach=False)
        reminder_user = User(telegram_user_id=977011, is_coach=False)
        session.add_all([first_user, reminder_user])
        session.flush()
        session.add_all(
            [
                UserProfile(user_id=first_user.id, timezone="Europe/Moscow"),
                UserProfile(user_id=reminder_user.id, timezone="Europe/Moscow"),
                NotificationSetting(user_id=first_user.id),
                NotificationSetting(user_id=reminder_user.id),
            ]
        )
        template = session.query(ProgramTemplate).first()
        assert template is not None
        program = UserProgram(
            user_id=reminder_user.id,
            template_id=template.id,
            is_active=True,
        )
        session.add(program)
        session.flush()
        workout = UserWorkout(
            user_program_id=program.id,
            scheduled_date=fixed_now.date(),
            day_number=1,
            title="Тренировка",
            status="planned",
        )
        session.add(workout)
        session.flush()
        first_event = Notification(
            user_id=first_user.id,
            channel="telegram",
            category="trainer_program_update",
            event_kind="transactional",
            title="Программа",
            body="Body",
            scheduled_for=fixed_now,
            scheduled_for_utc=fixed_now,
            status="queued",
            action_url="/app?section=programs",
        )
        reminder = Notification(
            user_id=reminder_user.id,
            channel="telegram",
            category="workout_reminder",
            event_kind="reminder",
            title="Скоро тренировка",
            body="Body",
            scheduled_for=fixed_now,
            scheduled_for_utc=fixed_now,
            status="queued",
            dedupe_key=f"workout:{workout.id}:reminder",
            action_url="/app?section=today",
        )
        session.add_all([first_event, reminder])
        session.commit()
        workout_id = workout.id
        reminder_id = reminder.id

    async def exercise_race() -> None:
        delivery_task = asyncio.create_task(worker.run_once(sync_reminders=False))
        await first_send_started.wait()
        with get_session_context() as session:
            workout = session.get(UserWorkout, workout_id)
            assert workout is not None
            workout.status = "skipped"
            assert cancel_workout_reminder(session, workout.id) == 1
        release_first_send.set()
        await delivery_task

    asyncio.run(exercise_race())

    assert delivered_chat_ids == [977010]
    with get_session_context() as session:
        stored = session.get(Notification, reminder_id)
        assert stored is not None
        assert stored.status == "cancelled"


def test_worker_finishes_current_cycle_before_graceful_stop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []

    async def scenario() -> None:
        stop_requested = asyncio.Event()

        async def run_once(*, sync_reminders: bool) -> None:
            events.append(f"cycle:{sync_reminders}")
            stop_requested.set()

        monkeypatch.setattr(worker, "run_once", run_once)
        monkeypatch.setattr(worker, "WORKER_HEARTBEAT_PATH", tmp_path / "worker-heartbeat")
        monkeypatch.setattr(worker.settings, "weekly_digest_enabled", False)
        monkeypatch.setattr(worker.settings, "news_ingestion_enabled", False)

        await worker.run_until_stopped(
            stop_requested,
            news_publication_ready=False,
        )

    asyncio.run(scenario())

    assert events == ["cycle:True"]


def test_worker_dispatches_news_review_once_per_active_slot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[dict[str, object]] = []

    async def scenario() -> None:
        stop_requested = asyncio.Event()
        iterations = 0
        slot = current_news_review_slot(datetime(2026, 9, 8, 5, 5, tzinfo=UTC))
        assert slot is not None

        async def run_once(*, sync_reminders: bool) -> None:
            del sync_reminders
            nonlocal iterations
            iterations += 1
            if iterations == 2:
                stop_requested.set()

        async def run_news_pipeline_once(**kwargs) -> None:
            events.append(kwargs)

        monkeypatch.setattr(worker, "run_once", run_once)
        monkeypatch.setattr(worker, "run_news_pipeline_once", run_news_pipeline_once)
        monkeypatch.setattr(worker, "current_news_review_slot", lambda _now: slot)
        monkeypatch.setattr(worker, "WORKER_HEARTBEAT_PATH", tmp_path / "worker-heartbeat")
        monkeypatch.setattr(worker.settings, "weekly_digest_enabled", False)
        monkeypatch.setattr(worker.settings, "news_ingestion_enabled", True)

        await worker.run_until_stopped(
            stop_requested,
            news_publication_ready=False,
        )

    asyncio.run(scenario())

    assert len(events) == 2
    assert [event["review_delivery_due"] for event in events] == [True, False]
    assert events[0]["review_slot"] is events[1]["review_slot"]


def test_worker_heartbeat_refreshes_during_long_async_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    touches = 0

    async def scenario() -> None:
        nonlocal touches
        stop_requested = asyncio.Event()

        class HeartbeatPath:
            def touch(self) -> None:
                nonlocal touches
                touches += 1
                if touches == 2:
                    stop_requested.set()

        monkeypatch.setattr(worker, "WORKER_HEARTBEAT_PATH", HeartbeatPath())
        await worker.refresh_worker_heartbeat(stop_requested, interval_seconds=0.001)

    asyncio.run(scenario())

    assert touches == 2
