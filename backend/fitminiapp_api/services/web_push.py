from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import hashlib
import hmac
import json
import math
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Literal
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.models.notification import (
    NotificationDelivery,
    WebPushSubscription,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.services.notifications import (
    NotificationDeliveryError,
    validate_notification_destination,
)

WEB_PUSH_FALLBACK_PATH = "/app?section=profile#profile-notifications"
WEB_PUSH_PAYLOAD_VERSION = 2
WEB_PUSH_TTL_SECONDS = 300
_BASE64URL_PATTERN = re.compile(r"[A-Za-z0-9_-]+={0,2}\Z")


class WebPushDisabledError(RuntimeError):
    """The server-side rollout switch is off or has no usable VAPID config."""


class WebPushConfigurationError(RuntimeError):
    """The delivery worker cannot use its server-side VAPID configuration."""


class WebPushSubscriptionError(ValueError):
    """A browser supplied subscription is not safe to persist."""


class WebPushDeliveryError(NotificationDeliveryError):
    """A bounded Web Push outcome, optionally requiring subscription removal."""

    def __init__(
        self,
        code: str,
        *,
        retry_after: timedelta | None = None,
        terminal_status: Literal["cancelled", "failed"] | None = None,
        remove_subscription: bool = False,
    ) -> None:
        super().__init__(
            code,
            retry_after=retry_after,
            terminal_status=terminal_status,
        )
        self.remove_subscription = remove_subscription


def _decode_base64url(value: str, *, field: str) -> bytes:
    normalized = value.strip()
    if not _BASE64URL_PATTERN.fullmatch(normalized):
        raise WebPushSubscriptionError(f"invalid {field}")
    unpadded = normalized.rstrip("=")
    if len(unpadded) % 4 == 1:
        raise WebPushSubscriptionError(f"invalid {field}")
    try:
        return base64.urlsafe_b64decode(unpadded + "=" * (-len(unpadded) % 4))
    except (binascii.Error, ValueError) as exc:
        raise WebPushSubscriptionError(f"invalid {field}") from exc


def normalize_web_push_endpoint(endpoint: str, *, require_allowed_host: bool = True) -> str:
    normalized = endpoint.strip()
    if len(normalized) > 2048:
        raise WebPushSubscriptionError("invalid endpoint")
    try:
        parsed = urlsplit(normalized)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise WebPushSubscriptionError("invalid endpoint") from exc
    if (
        parsed.scheme.lower() != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in (None, 443)
        or not parsed.path
    ):
        raise WebPushSubscriptionError("invalid endpoint")
    hostname = hostname.rstrip(".").lower()
    if not re.fullmatch(
        r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*", hostname
    ):
        raise WebPushSubscriptionError("invalid endpoint")
    if require_allowed_host and not any(
        _host_matches(hostname, pattern) for pattern in settings.web_push_endpoint_host_allowlist
    ):
        raise WebPushSubscriptionError("unsupported endpoint provider")
    return normalized


def _host_matches(hostname: str, pattern: str) -> bool:
    if pattern.startswith("*."):
        suffix = pattern[2:]
        return hostname.endswith(f".{suffix}") and hostname != suffix
    return hostname == pattern


def _endpoint_hash(endpoint: str) -> str:
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        endpoint.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def validate_subscription(endpoint: str, p256dh: str, auth: str) -> tuple[str, str, str]:
    normalized_endpoint = normalize_web_push_endpoint(endpoint)
    p256dh_bytes = _decode_base64url(p256dh, field="p256dh")
    if len(p256dh_bytes) != 65 or p256dh_bytes[0] != 4:
        raise WebPushSubscriptionError("invalid p256dh")
    try:
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), p256dh_bytes)
    except ValueError as exc:
        raise WebPushSubscriptionError("invalid p256dh") from exc
    auth_bytes = _decode_base64url(auth, field="auth")
    if len(auth_bytes) != 16:
        raise WebPushSubscriptionError("invalid auth")
    return normalized_endpoint, p256dh.strip(), auth.strip()


def register_subscription(
    db: Session,
    user: User,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
) -> WebPushSubscription:
    if not settings.web_push_enabled:
        raise WebPushDisabledError
    if (
        not settings.web_push_vapid_public_key
        or not settings.web_push_vapid_private_key.get_secret_value()
    ):
        raise WebPushDisabledError

    normalized_endpoint, normalized_p256dh, normalized_auth = validate_subscription(
        endpoint,
        p256dh,
        auth,
    )
    endpoint_hash = _endpoint_hash(normalized_endpoint)
    subscription = (
        db.query(WebPushSubscription)
        .filter(WebPushSubscription.endpoint_hash == endpoint_hash)
        .with_for_update()
        .first()
    )
    if subscription is None:
        subscription = WebPushSubscription(
            user_id=user.id,
            endpoint=normalized_endpoint,
            endpoint_hash=endpoint_hash,
            p256dh=normalized_p256dh,
            auth=normalized_auth,
        )
        db.add(subscription)
        try:
            db.flush()
        except IntegrityError:
            # A second tab may register the same browser capability concurrently.
            db.rollback()
            subscription = (
                db.query(WebPushSubscription)
                .filter(WebPushSubscription.endpoint_hash == endpoint_hash)
                .with_for_update()
                .one()
            )

    if subscription.user_id != user.id:
        # A browser capability must not carry queued events across an account switch.
        db.query(NotificationDelivery).filter(
            NotificationDelivery.subscription_id == subscription.id
        ).delete(synchronize_session=False)
        subscription.user_id = user.id
    subscription.endpoint = normalized_endpoint
    subscription.p256dh = normalized_p256dh
    subscription.auth = normalized_auth
    subscription.updated_at = now_msk_naive()
    subscription.failure_count = 0
    subscription.last_error = None
    db.flush()
    return subscription


def revoke_subscription(db: Session, user: User, endpoint: str) -> None:
    try:
        normalized_endpoint = normalize_web_push_endpoint(
            endpoint,
            require_allowed_host=False,
        )
    except WebPushSubscriptionError:
        return
    db.query(WebPushSubscription).filter(
        WebPushSubscription.user_id == user.id,
        WebPushSubscription.endpoint_hash == _endpoint_hash(normalized_endpoint),
    ).delete(synchronize_session=False)


def has_registered_subscription(db: Session, user: User) -> bool:
    return (
        db.query(WebPushSubscription.id).filter(WebPushSubscription.user_id == user.id).first()
        is not None
    )


def _subscription_info(subscription: Mapping[str, object]) -> dict[str, object]:
    endpoint = subscription.get("endpoint")
    keys = subscription.get("keys")
    if not isinstance(endpoint, str) or not isinstance(keys, dict):
        raise WebPushSubscriptionError("invalid subscription")
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")
    if not isinstance(p256dh, str) or not isinstance(auth, str):
        raise WebPushSubscriptionError("invalid subscription")
    normalized_endpoint, normalized_p256dh, normalized_auth = validate_subscription(
        endpoint, p256dh, auth
    )
    return {
        "endpoint": normalized_endpoint,
        "keys": {"p256dh": normalized_p256dh, "auth": normalized_auth},
    }


def _vapid_key_for_delivery():
    try:
        from py_vapid import Vapid

        value = settings.web_push_vapid_private_key.get_secret_value().strip().replace("\\n", "\n")
        if "-----BEGIN" in value:
            return Vapid.from_pem(value.encode("utf-8"))
        decoded = _decode_base64url(value, field="vapid private key")
        if len(decoded) == 32:
            return Vapid.from_raw(value.encode("utf-8"))
        return Vapid.from_der(value.encode("utf-8"))
    except Exception as exc:
        raise WebPushConfigurationError from exc


def _web_push_payload(action_url: object) -> str:
    destination = WEB_PUSH_FALLBACK_PATH
    if isinstance(action_url, str):
        with contextlib.suppress(ValueError):
            destination = validate_notification_destination(action_url)
    return json.dumps(
        {"version": WEB_PUSH_PAYLOAD_VERSION, "url": destination},
        separators=(",", ":"),
    )


def _send_web_push_sync(subscription: Mapping[str, object]) -> None:
    if not settings.web_push_enabled:
        raise WebPushDisabledError
    subscription_info = _subscription_info(subscription)
    import requests
    from pywebpush import webpush

    # Push endpoints are client-provided capabilities. Do not let an allowed provider
    # redirect the worker to an arbitrary host.
    with requests.Session() as session:
        session.trust_env = False
        session.max_redirects = 0
        webpush(
            subscription_info=subscription_info,
            data=_web_push_payload(subscription.get("action_url")),
            vapid_private_key=_vapid_key_for_delivery(),
            vapid_claims={"sub": settings.web_push_vapid_subject},
            content_encoding="aes128gcm",
            timeout=settings.web_push_delivery_timeout_seconds,
            ttl=WEB_PUSH_TTL_SECONDS,
            requests_session=session,
            verbose=False,
        )


def _parse_retry_after(value: object) -> timedelta | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    try:
        seconds = float(normalized)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(normalized)
        except TypeError, ValueError, OverflowError:
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        seconds = (retry_at - datetime.now(UTC)).total_seconds()
    if not math.isfinite(seconds):
        return None
    if seconds <= 0:
        return timedelta(seconds=1)
    return timedelta(seconds=min(seconds, 3600))


def _classify_delivery_exception(error: Exception) -> WebPushDeliveryError:
    if isinstance(error, WebPushDeliveryError):
        return error
    if isinstance(error, WebPushDisabledError):
        return WebPushDeliveryError("web_push_disabled", terminal_status="cancelled")
    if isinstance(error, WebPushConfigurationError):
        return WebPushDeliveryError(
            "web_push_configuration_invalid",
            terminal_status="failed",
        )
    if isinstance(error, WebPushSubscriptionError):
        return WebPushDeliveryError(
            "web_push_subscription_invalid",
            terminal_status="cancelled",
            remove_subscription=True,
        )

    status_code = getattr(error, "status_code", None)
    retry_after = _parse_retry_after(getattr(error, "retry_after", None))
    if status_code in (404, 410):
        return WebPushDeliveryError(
            "web_push_subscription_expired",
            terminal_status="cancelled",
            remove_subscription=True,
        )
    if status_code == 400:
        return WebPushDeliveryError(
            "web_push_subscription_invalid",
            terminal_status="cancelled",
            remove_subscription=True,
        )
    if status_code == 429:
        return WebPushDeliveryError("web_push_rate_limited", retry_after=retry_after)
    if isinstance(status_code, int) and 500 <= status_code <= 599:
        return WebPushDeliveryError("web_push_provider_unavailable", retry_after=retry_after)
    if isinstance(status_code, int) and 400 <= status_code <= 499:
        return WebPushDeliveryError(
            "web_push_provider_rejected",
            terminal_status="failed",
        )

    error_name = type(error).__name__.lower()
    error_module = type(error).__module__.lower()
    if "timeout" in error_name or "timeout" in error_module:
        return WebPushDeliveryError("web_push_timeout")
    if "request" in error_module or "connection" in error_name:
        return WebPushDeliveryError("web_push_transport_error")
    return WebPushDeliveryError("web_push_unexpected", terminal_status="failed")


async def send_web_push(subscription: Mapping[str, object]) -> None:
    try:
        await asyncio.to_thread(_send_web_push_sync, subscription)
    except Exception as error:
        classified = _classify_delivery_exception(error)
        raise classified from None
