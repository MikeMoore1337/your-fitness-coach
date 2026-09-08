from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import logging
import signal
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic

import httpx
from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.logging_config import configure_logging
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.notification import (
    Notification,
    NotificationDelivery,
    NotificationSetting,
    WebPushSubscription,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.models.weekly_digest import WeeklyDigestDelivery
from fitminiapp_api.services.account_exports import prune_account_exports
from fitminiapp_api.services.audit import prune_audit_events
from fitminiapp_api.services.bot_support import prune_support_cases
from fitminiapp_api.services.news_ingestion import utcnow
from fitminiapp_api.services.news_review_schedule import current_news_review_slot
from fitminiapp_api.services.news_worker import run_news_pipeline_once
from fitminiapp_api.services.notifications import (
    MAX_DELIVERY_ATTEMPTS,
    NotificationDeliveryError,
    cancel_web_push_delivery,
    claim_due_notifications,
    claim_due_web_push_deliveries,
    enqueue_web_push_deliveries,
    mark_delivery_failed,
    mark_delivery_succeeded,
    mark_web_push_delivery_failed,
    mark_web_push_delivery_succeeded,
    neutral_telegram_text,
    quiet_hours_retry_at,
    reminder_category_enabled,
    resolve_notification_destination,
    safe_delivery_error,
    sync_measurement_reminders,
    sync_weekly_check_in_reminders,
    sync_workout_reminders,
    validate_notification_destination,
)
from fitminiapp_api.services.program_imports import expire_program_imports
from fitminiapp_api.services.reminder_templates import sync_contextual_reminders
from fitminiapp_api.services.web_push import send_web_push
from fitminiapp_api.services.weekly_digest import (
    claim_due_digest_deliveries,
    digest_delivery_counts,
    digest_delivery_payload,
    finalize_digest_issues,
    mark_digest_delivery_failed,
    mark_digest_delivery_succeeded,
    prune_weekly_digest,
)

logger = logging.getLogger(__name__)
TELEGRAM_DELIVERY_RATE_PER_SECOND = 20
WORKER_HEARTBEAT_PATH = Path("/tmp/fitminiapp-worker-heartbeat")


@dataclass(frozen=True)
class TelegramPublicationResult:
    message_id: int
    message_date: datetime


class TelegramPublicationError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        retry_after: timedelta | None = None,
        terminal: bool = False,
        uncertain: bool = False,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after
        self.terminal = terminal
        self.uncertain = uncertain


class TelegramRateLimiter:
    """Keep one worker below Telegram's global bulk-send limit."""

    def __init__(
        self,
        rate_per_second: int,
        *,
        clock: Callable[[], float] = monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._interval = 1 / rate_per_second
        self._clock = clock
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._next_send_at = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = self._clock()
            if now < self._next_send_at:
                await self._sleep(self._next_send_at - now)
                now = self._clock()
            self._next_send_at = max(now, self._next_send_at) + self._interval

    async def defer(self, delay_seconds: float) -> None:
        async with self._lock:
            self._next_send_at = max(
                self._next_send_at,
                self._clock() + delay_seconds,
            )


def _telegram_delivery_error(response: httpx.Response) -> NotificationDeliveryError:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    error_code = payload.get("error_code")
    if not isinstance(error_code, int):
        error_code = response.status_code
    description = payload.get("description")
    normalized_description = description.lower() if isinstance(description, str) else ""

    if error_code == 429:
        parameters = payload.get("parameters")
        retry_after_seconds = (
            parameters.get("retry_after") if isinstance(parameters, dict) else None
        )
        retry_after = (
            timedelta(seconds=retry_after_seconds)
            if isinstance(retry_after_seconds, int) and retry_after_seconds > 0
            else None
        )
        return NotificationDeliveryError("telegram_rate_limited", retry_after=retry_after)

    if error_code == 403 or (
        error_code == 400
        and any(
            marker in normalized_description for marker in ("chat not found", "user is deactivated")
        )
    ):
        return NotificationDeliveryError(
            "telegram_chat_unavailable",
            terminal_status="cancelled",
        )

    if 400 <= error_code < 500:
        return NotificationDeliveryError(
            f"telegram_http_status:{error_code}",
            terminal_status="failed",
        )
    return NotificationDeliveryError(f"telegram_http_status:{error_code}")


def telegram_transport_options() -> dict[str, object]:
    """Return an explicit Bot API route without inheriting ambient proxy settings."""

    options: dict[str, object] = {"trust_env": False}
    if settings.bot_api_proxy_url:
        options["proxy"] = settings.bot_api_proxy_url
    return options


def _log_delivery_failure(
    notification_id: int,
    error: Exception,
    *,
    provider: str | None = None,
    category: str | None = None,
    outcome: str | None = None,
) -> None:
    notification_ref = hmac.new(
        settings.secret_key.encode("utf-8"),
        str(notification_id).encode("ascii"),
        hashlib.sha256,
    ).hexdigest()[:16]
    extra: dict[str, object] = {
        "notification_ref": f"notification:{notification_ref}",
        "delivery_error": safe_delivery_error(error),
    }
    if provider is not None:
        extra["provider"] = provider
    if category is not None:
        extra["notification_category"] = category
    if outcome is not None:
        extra["outcome"] = outcome
    logger.error("notification_delivery_failed", extra=extra)


def _log_delivery_completed(notification_id: int, category: str) -> None:
    notification_ref = hmac.new(
        settings.secret_key.encode("utf-8"),
        str(notification_id).encode("ascii"),
        hashlib.sha256,
    ).hexdigest()[:16]
    logger.info(
        "notification_delivery_completed",
        extra={
            "notification_ref": f"notification:{notification_ref}",
            "notification_category": category,
            "provider": "web_push",
            "outcome": "sent",
        },
    )


async def send_telegram_message(
    client: httpx.AsyncClient,
    chat_id: int,
    text: str,
    *,
    open_app_path: str | None = None,
    reply_markup: dict | None = None,
    parse_mode: str | None = None,
    link_preview_disabled: bool = False,
) -> int | None:
    if not settings.telegram_bot_token or settings.telegram_bot_token in {
        "change-me",
        "replace-me",
    }:
        raise NotificationDeliveryError(
            "bot_token_not_configured",
            terminal_status="failed",
        )
    payload: dict = {"chat_id": chat_id, "text": text}
    if parse_mode is not None:
        payload["parse_mode"] = parse_mode
    if link_preview_disabled:
        payload["link_preview_options"] = {"is_disabled": True}
    if open_app_path and reply_markup is not None:
        raise ValueError("Only one Telegram reply markup contract may be used")
    if open_app_path:
        destination = validate_notification_destination(open_app_path)
        payload["reply_markup"] = {
            "inline_keyboard": [
                [
                    {
                        "text": "Открыть приложение",
                        "web_app": {
                            "url": f"{settings.frontend_base_url.rstrip('/')}{destination}"
                        },
                    }
                ]
            ]
        }
    elif reply_markup is not None:
        payload["reply_markup"] = reply_markup
    response = await client.post(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
        json=payload,
    )
    try:
        response_payload = response.json()
    except ValueError:
        response_payload = None
    if (
        response.is_success
        and isinstance(response_payload, dict)
        and response_payload.get("ok") is True
    ):
        result = response_payload.get("result")
        message_id = result.get("message_id") if isinstance(result, dict) else None
        return message_id if isinstance(message_id, int) else None
    raise _telegram_delivery_error(response)


async def run_weekly_digest_once() -> None:
    with get_session_context() as db:
        delivery_ids = claim_due_digest_deliveries(db)
        issue_by_delivery = {
            row.id: row.issue_id
            for row in db.query(WeeklyDigestDelivery)
            .filter(WeeklyDigestDelivery.id.in_(delivery_ids))
            .all()
        }
    if not delivery_ids:
        return

    semaphore = asyncio.Semaphore(settings.weekly_digest_delivery_concurrency)
    rate_limiter = TelegramRateLimiter(TELEGRAM_DELIVERY_RATE_PER_SECOND)
    async with httpx.AsyncClient(timeout=20) as client:

        async def deliver(delivery_id: int) -> tuple[int, Exception | None, int | None]:
            try:
                async with semaphore:
                    await rate_limiter.acquire()
                    with get_session_context() as preflight_db:
                        payload = digest_delivery_payload(preflight_db, delivery_id)
                    if payload is None:
                        return delivery_id, None, None
                    message_id = await send_telegram_message(
                        client,
                        payload.chat_id,
                        payload.text,
                        reply_markup={
                            "inline_keyboard": [
                                [{"text": "Открыть Telegram-канал", "url": payload.channel_url}],
                                [
                                    {
                                        "text": "Отключить еженедельный дайджест",
                                        "callback_data": "wd:off",
                                    }
                                ],
                            ]
                        },
                        parse_mode="HTML",
                        link_preview_disabled=True,
                    )
                    if message_id is None:
                        raise TelegramPublicationError(
                            "telegram_malformed_success",
                            uncertain=True,
                        )
                    return delivery_id, None, message_id
            except httpx.TimeoutException:
                return (
                    delivery_id,
                    TelegramPublicationError("telegram_send_timeout", uncertain=True),
                    None,
                )
            except NotificationDeliveryError as exc:
                if exc.retry_after is not None:
                    await rate_limiter.defer(exc.retry_after.total_seconds())
                return delivery_id, exc, None
            except Exception as exc:
                return delivery_id, exc, None

        results = await asyncio.gather(*(deliver(delivery_id) for delivery_id in delivery_ids))

    issue_ids = set(issue_by_delivery.values())
    with get_session_context() as db:
        for delivery_id, error, message_id in results:
            row = db.get(WeeklyDigestDelivery, delivery_id)
            if row is None or row.status != "processing":
                continue
            if error is None and message_id is not None:
                mark_digest_delivery_succeeded(
                    db,
                    delivery_id,
                    telegram_message_id=message_id,
                )
            elif error is not None:
                if isinstance(error, NotificationDeliveryError):
                    mark_digest_delivery_failed(
                        db,
                        delivery_id,
                        error_code=error.code,
                        retry_after=error.retry_after,
                        terminal=error.terminal_status is not None,
                    )
                elif isinstance(error, TelegramPublicationError) and error.uncertain:
                    mark_digest_delivery_failed(
                        db,
                        delivery_id,
                        error_code=error.code,
                        uncertain=True,
                    )
                else:
                    mark_digest_delivery_failed(
                        db,
                        delivery_id,
                        error_code=type(error).__name__,
                    )
        finalize_digest_issues(db, issue_ids)
        counts = {
            status: sum(
                digest_delivery_counts(db, issue_id).get(status, 0) for issue_id in issue_ids
            )
            for status in (
                "queued",
                "processing",
                "sent",
                "failed",
                "cancelled",
                "uncertain",
            )
        }
    logger.info(
        "weekly_digest_delivery_batch_completed",
        extra={"issue_count": len(issue_ids), **counts},
    )


async def check_news_channel_rights(client: httpx.AsyncClient) -> bool:
    if not settings.news_publication_enabled or settings.news_channel_id is None:
        return False
    try:
        me_response = await client.get(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/getMe"
        )
        me_payload = me_response.json()
        bot_id = me_payload["result"]["id"]
        member_response = await client.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/getChatMember",
            json={"chat_id": settings.news_channel_id, "user_id": bot_id},
        )
        member_payload = member_response.json()
        member = member_payload["result"]
        ready = member.get("status") == "creator" or (
            member.get("status") == "administrator" and member.get("can_post_messages") is True
        )
    except httpx.HTTPError, KeyError, TypeError, ValueError:
        ready = False
    logger.log(
        logging.INFO if ready else logging.ERROR,
        "news_channel_rights_checked",
        extra={
            "pipeline_stage": "channel_preflight",
            "outcome": "ready" if ready else "missing_can_post_messages",
            "channel_environment": settings.news_channel_environment,
        },
    )
    return ready


async def send_telegram_preview(
    client: httpx.AsyncClient,
    chat_id: int,
    text: str,
    image_data: bytes | None,
    *,
    parse_mode: str | None = None,
    link_preview_disabled: bool = False,
) -> TelegramPublicationResult:
    endpoint = "sendPhoto" if image_data is not None else "sendMessage"
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/{endpoint}"
    try:
        if image_data is None:
            request_payload: dict[str, object] = {"chat_id": chat_id, "text": text}
            if parse_mode is not None:
                request_payload["parse_mode"] = parse_mode
            if link_preview_disabled:
                request_payload["link_preview_options"] = {"is_disabled": True}
            response = await client.post(url, json=request_payload)
        else:
            form_data: dict[str, str] = {"chat_id": str(chat_id), "caption": text}
            if parse_mode is not None:
                form_data["parse_mode"] = parse_mode
            response = await client.post(
                url,
                data=form_data,
                files={"photo": ("approved-news.jpg", image_data, "image/jpeg")},
            )
    except httpx.TimeoutException as exc:
        raise TelegramPublicationError("telegram_send_timeout", uncertain=True) from exc
    except httpx.RequestError as exc:
        raise TelegramPublicationError("telegram_network_error") from exc
    if not response.is_success:
        error = _telegram_delivery_error(response)
        raise TelegramPublicationError(
            safe_delivery_error(error),
            retry_after=error.retry_after,
            terminal=error.terminal_status is not None,
        )
    try:
        payload = response.json()
        if payload.get("ok") is not True:
            raise TypeError
        result = payload["result"]
        if not isinstance(result, dict):
            raise TypeError
        message_id = result["message_id"]
        message_date = datetime.fromtimestamp(result["date"], tz=UTC).replace(tzinfo=None)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise TelegramPublicationError("telegram_malformed_success", uncertain=True) from exc
    if not isinstance(message_id, int):
        raise TelegramPublicationError("telegram_malformed_success", uncertain=True)
    return TelegramPublicationResult(message_id=message_id, message_date=message_date)


async def send_telegram_publication(
    client: httpx.AsyncClient,
    channel_id: int,
    text: str,
    image_data: bytes | None,
    *,
    parse_mode: str | None = None,
    link_preview_disabled: bool = False,
) -> TelegramPublicationResult:
    if channel_id != settings.news_channel_id:
        raise TelegramPublicationError("channel_mismatch", terminal=True)
    return await send_telegram_preview(
        client,
        channel_id,
        text,
        image_data,
        parse_mode=parse_mode,
        link_preview_disabled=link_preview_disabled,
    )


def _prepare_delivery(
    db: Session,
    row: Notification,
    user: User | None,
    setting: NotificationSetting | None,
) -> tuple[int, str, str] | None:
    if row.status != "processing":
        return None
    if user is None or not user.is_active:
        row.status = "cancelled"
        row.last_error = "account_unavailable"
        row.processing_started_at = None
        return None
    if row.channel != "telegram":
        mark_delivery_succeeded(db, row, user, commit=False)
        return None
    if user.telegram_user_id is None:
        row.status = "cancelled"
        row.last_error = "telegram_identity_not_linked"
        row.processing_started_at = None
        return None
    if setting is None or not setting.telegram_enabled:
        row.status = "cancelled"
        row.last_error = "telegram_channel_disabled"
        row.processing_started_at = None
        return None
    if not reminder_category_enabled(row, setting):
        row.status = "cancelled"
        row.last_error = "reminder_category_disabled"
        row.processing_started_at = None
        return None
    if row.event_kind != "security":
        retry_at = quiet_hours_retry_at(setting, user)
        if retry_at is not None:
            row.status = "queued"
            row.next_attempt_at = retry_at
            row.processing_started_at = None
            return None
    open_app_path, _ = resolve_notification_destination(db, user, row)
    return user.telegram_user_id, neutral_telegram_text(row), open_app_path


def _prepare_web_push_delivery(
    db: Session,
    delivery: NotificationDelivery,
) -> dict[str, object] | None:
    if delivery.status != "processing":
        return None
    notification = db.get(Notification, delivery.notification_id)
    subscription = db.get(WebPushSubscription, delivery.subscription_id)
    if notification is None:
        cancel_web_push_delivery(db, delivery, "notification_unavailable")
        return None
    if subscription is None:
        cancel_web_push_delivery(db, delivery, "subscription_unavailable")
        return None
    if subscription.user_id != notification.user_id:
        cancel_web_push_delivery(db, delivery, "subscription_ownership_changed")
        return None
    user = db.get(User, notification.user_id)
    if user is None or not user.is_active:
        cancel_web_push_delivery(db, delivery, "account_unavailable")
        return None
    if notification.last_error in {
        "workout_reminder_invalidated",
        "account_unavailable",
    }:
        cancel_web_push_delivery(db, delivery, notification.last_error)
        return None
    setting = db.query(NotificationSetting).filter(NotificationSetting.user_id == user.id).first()
    if notification.event_kind == "reminder" and setting is None:
        cancel_web_push_delivery(db, delivery, "notification_settings_unavailable")
        return None
    if setting is not None and not reminder_category_enabled(notification, setting):
        cancel_web_push_delivery(db, delivery, "reminder_category_disabled")
        return None
    if notification.event_kind != "security" and setting is not None:
        retry_at = quiet_hours_retry_at(setting, user)
        if retry_at is not None:
            delivery.status = "queued"
            delivery.next_attempt_at = retry_at
            delivery.processing_started_at = None
            return None
    return {
        "notification_id": notification.id,
        "category": notification.category,
        "subscription_id": subscription.id,
        "subscription": {
            "endpoint": subscription.endpoint,
            "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
        },
    }


async def _run_web_push_delivery_batch() -> None:
    if not settings.web_push_enabled:
        return
    with get_session_context() as db:
        delivery_ids = [delivery.id for delivery in claim_due_web_push_deliveries(db)]
    if not delivery_ids:
        return

    semaphore = asyncio.Semaphore(settings.notification_delivery_concurrency)

    async def deliver(delivery_id: int) -> tuple[int, bool, Exception | None]:
        try:
            async with semaphore:
                with get_session_context() as preflight_db:
                    delivery = preflight_db.get(NotificationDelivery, delivery_id)
                    prepared = (
                        _prepare_web_push_delivery(preflight_db, delivery)
                        if delivery is not None
                        else None
                    )
                if prepared is None:
                    return delivery_id, False, None
                target = prepared["subscription"]
                if not isinstance(target, dict):
                    raise RuntimeError("web_push_target_malformed")
                await send_web_push(target)
            return delivery_id, True, None
        except Exception as exc:
            return delivery_id, True, exc

    results = await asyncio.gather(*(deliver(delivery_id) for delivery_id in delivery_ids))
    with get_session_context() as db:
        for delivery_id, attempted, error in results:
            if not attempted:
                continue
            delivery = db.get(NotificationDelivery, delivery_id)
            if delivery is None or delivery.status != "processing":
                continue
            notification = db.get(Notification, delivery.notification_id)
            if notification is None:
                cancel_web_push_delivery(db, delivery, "notification_unavailable")
                continue
            subscription = db.get(WebPushSubscription, delivery.subscription_id)
            if error is None:
                if subscription is None or subscription.user_id != notification.user_id:
                    cancel_web_push_delivery(db, delivery, "subscription_ownership_changed")
                    continue
                mark_web_push_delivery_succeeded(
                    db,
                    delivery,
                    subscription,
                    commit=False,
                )
                _log_delivery_completed(notification.id, notification.category)
                continue
            mark_web_push_delivery_failed(
                db,
                delivery,
                error,
                subscription=subscription,
                commit=False,
            )
            if getattr(error, "remove_subscription", False):
                outcome = "expired"
            elif getattr(error, "terminal_status", None) is not None or (
                delivery.attempt_count >= MAX_DELIVERY_ATTEMPTS
            ):
                outcome = "failed"
            else:
                outcome = "retry"
            _log_delivery_failure(
                notification.id,
                error,
                provider="web_push",
                category=notification.category,
                outcome=outcome,
            )


async def run_once(*, sync_reminders: bool = True) -> None:
    with get_session_context() as db:
        prune_account_exports(db)
        expire_program_imports(db)
        if sync_reminders:
            prune_audit_events(db, retention_days=settings.audit_event_retention_days)
            prune_weekly_digest(db, retention_days=settings.news_retention_days)
            prune_support_cases(db)
            sync_workout_reminders(db)
            sync_weekly_check_in_reminders(db)
            sync_measurement_reminders(db)
            sync_contextual_reminders(db)
        rows = claim_due_notifications(db)
        users = {
            user.id: user
            for user in db.query(User).filter(User.id.in_({row.user_id for row in rows})).all()
        }
        notification_settings = {
            row.user_id: row
            for row in db.query(NotificationSetting)
            .filter(NotificationSetting.user_id.in_(users))
            .all()
        }
        deliveries: list[int] = []
        for row in rows:
            user = users.get(row.user_id)
            setting = notification_settings.get(user.id) if user is not None else None
            if _prepare_delivery(db, row, user, setting) is not None:
                deliveries.append(row.id)
        enqueue_web_push_deliveries(db, rows)
        db.commit()

        if deliveries:
            semaphore = asyncio.Semaphore(settings.notification_delivery_concurrency)
            rate_limiter = TelegramRateLimiter(TELEGRAM_DELIVERY_RATE_PER_SECOND)

            async with httpx.AsyncClient(timeout=20, **telegram_transport_options()) as client:

                async def deliver(
                    notification_id: int,
                ) -> tuple[int, bool, Exception | None]:
                    try:
                        async with semaphore:
                            await rate_limiter.acquire()
                            with get_session_context() as preflight_db:
                                current_row = preflight_db.get(Notification, notification_id)
                                current_user = (
                                    preflight_db.get(User, current_row.user_id)
                                    if current_row is not None
                                    else None
                                )
                                current_setting = (
                                    preflight_db.query(NotificationSetting)
                                    .filter(NotificationSetting.user_id == current_user.id)
                                    .first()
                                    if current_user is not None
                                    else None
                                )
                                prepared = (
                                    _prepare_delivery(
                                        preflight_db,
                                        current_row,
                                        current_user,
                                        current_setting,
                                    )
                                    if current_row is not None
                                    else None
                                )
                            if prepared is None:
                                return notification_id, False, None
                            chat_id, text, open_app_path = prepared
                            await send_telegram_message(
                                client, chat_id, text, open_app_path=open_app_path
                            )
                        return notification_id, True, None
                    except NotificationDeliveryError as exc:
                        if exc.retry_after is not None:
                            await rate_limiter.defer(exc.retry_after.total_seconds())
                        return notification_id, True, exc
                    except Exception as exc:
                        return notification_id, True, exc

                results = await asyncio.gather(
                    *(deliver(notification_id) for notification_id in deliveries)
                )

            attempted_results = [
                (notification_id, error)
                for notification_id, attempted, error in results
                if attempted
            ]
            if attempted_results:
                result_by_id = dict(attempted_results)
                db.expire_all()
                delivered_rows: dict[int, Notification] = {
                    row.id: row
                    for row in db.query(Notification)
                    .filter(Notification.id.in_(result_by_id))
                    .all()
                }
                delivered_users = {
                    user.id: user
                    for user in db.query(User)
                    .filter(User.id.in_({row.user_id for row in delivered_rows.values()}))
                    .all()
                }
                for notification_id, error in attempted_results:
                    delivered_row = delivered_rows.get(notification_id)
                    if delivered_row is None or delivered_row.status != "processing":
                        continue
                    if error is None:
                        user = delivered_users.get(delivered_row.user_id)
                        if user is not None and user.is_active:
                            mark_delivery_succeeded(db, delivered_row, user, commit=False)
                        else:
                            delivered_row.status = "cancelled"
                            delivered_row.processing_started_at = None
                    else:
                        mark_delivery_failed(db, delivered_row, error, commit=False)
                        _log_delivery_failure(delivered_row.id, error)
                db.commit()

    await _run_web_push_delivery_batch()


async def run_until_stopped(
    stop_requested: asyncio.Event,
    *,
    news_publication_ready: bool,
) -> None:
    next_reminder_sync = 0.0
    next_news_sync = 0.0
    last_news_review_slot_key: str | None = None
    WORKER_HEARTBEAT_PATH.touch()
    while not stop_requested.is_set():
        current = monotonic()
        should_sync = current >= next_reminder_sync
        await run_once(sync_reminders=should_sync)
        if settings.weekly_digest_enabled:
            await run_weekly_digest_once()
        if should_sync:
            next_reminder_sync = current + settings.reminder_sync_seconds
        if settings.news_ingestion_enabled:
            should_fetch_news = current >= next_news_sync
            review_slot = current_news_review_slot(utcnow())
            review_delivery_due = (
                review_slot is not None and review_slot.key != last_news_review_slot_key
            )
            try:
                await run_news_pipeline_once(
                    send_message=send_telegram_message,
                    send_preview=send_telegram_preview,
                    send_publication=send_telegram_publication,
                    publication_ready=news_publication_ready,
                    fetch_sources=should_fetch_news,
                    review_delivery_due=review_delivery_due,
                    review_slot=review_slot,
                )
            except Exception as exc:
                logger.error(
                    "news_pipeline_cycle_failed",
                    extra={
                        "pipeline_stage": "cycle",
                        "reason": type(exc).__name__,
                    },
                )
            else:
                if review_delivery_due and review_slot is not None:
                    last_news_review_slot_key = review_slot.key
            if should_fetch_news:
                next_news_sync = current + settings.news_ingestion_cycle_seconds
        WORKER_HEARTBEAT_PATH.touch()
        if stop_requested.is_set():
            break
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_requested.wait(), timeout=settings.worker_poll_seconds)


async def refresh_worker_heartbeat(
    stop_requested: asyncio.Event,
    *,
    interval_seconds: float = 30,
) -> None:
    """Keep health tied to event-loop liveness while long async provider calls run."""
    while not stop_requested.is_set():
        WORKER_HEARTBEAT_PATH.touch()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_requested.wait(), timeout=interval_seconds)


async def main() -> None:
    configure_logging(
        debug=settings.app_debug,
        service="notification-worker",
        sensitive_values=(
            settings.secret_key,
            settings.telegram_bot_token,
            settings.bot_internal_token,
            settings.smtp_password,
            settings.telegram_oauth_client_secret,
            settings.google_oauth_client_secret,
            settings.yandex_oauth_client_secret,
            settings.apple_oauth_client_secret,
            settings.database_url,
            settings.news_llm_api_key,
            settings.news_image_cloudflare_api_token,
            settings.web_push_vapid_private_key.get_secret_value(),
        ),
    )
    stop_requested = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_stop() -> None:
        if not stop_requested.is_set():
            logger.info("worker_drain_requested")
            stop_requested.set()

    for signal_name in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signal_name, request_stop)
    logger.info("worker_started")
    heartbeat_task = asyncio.create_task(refresh_worker_heartbeat(stop_requested))
    try:
        async with httpx.AsyncClient(timeout=15) as preflight_client:
            news_publication_ready = await check_news_channel_rights(preflight_client)
        await run_until_stopped(
            stop_requested,
            news_publication_ready=news_publication_ready,
        )
    finally:
        stop_requested.set()
        await heartbeat_task
    logger.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
