import asyncio
import base64
import json
import sys
import types
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import SecretStr, ValidationError

from fitminiapp_api.core.config import Settings, settings
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.notification import (
    Notification,
    NotificationDelivery,
    NotificationSetting,
    WebPushSubscription,
)
from fitminiapp_api.models.user import User, UserProfile
from fitminiapp_api.services import worker
from fitminiapp_api.services.notifications import enqueue_web_push_deliveries
from fitminiapp_api.services.web_push import (
    WebPushConfigurationError,
    WebPushDeliveryError,
    _classify_delivery_exception,
    _send_web_push_sync,
    register_subscription,
)


def _valid_subscription_payload(suffix: str) -> dict[str, object]:
    def encoded(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    p256dh = (
        ec.generate_private_key(ec.SECP256R1())
        .public_key()
        .public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
    )
    return {
        "endpoint": f"https://fcm.googleapis.com/fcm/send/{suffix}",
        "keys": {
            "p256dh": encoded(p256dh),
            "auth": encoded(b"a" * 16),
        },
    }


def _enable_web_push(monkeypatch) -> None:
    monkeypatch.setattr(settings, "web_push_enabled", True)
    monkeypatch.setattr(settings, "web_push_vapid_public_key", "test-public-key")
    monkeypatch.setattr(settings, "web_push_vapid_private_key", SecretStr("test-private-key"))


def _valid_vapid_keys() -> tuple[str, str]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_raw = private_key.private_numbers().private_value.to_bytes(32, "big")
    private_value = base64.urlsafe_b64encode(private_raw).rstrip(b"=").decode("ascii")
    public_value = (
        base64.urlsafe_b64encode(
            private_key.public_key().public_bytes(
                serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint,
            )
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    return public_value, private_value


def _settings_base() -> dict[str, object]:
    return {
        "app_env": "dev",
        "app_name": "Your Fitness Coach",
        "app_debug": False,
        "secret_key": "test-secret",
        "access_token_expire_minutes": 60,
        "refresh_token_expire_days": 30,
        "database_url": "sqlite://",
        "telegram_bot_token": "test-token",
    }


def _login(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": False},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_due_event_with_subscriptions(
    telegram_user_id: int = 9_860_001,
) -> tuple[int, list[str]]:
    with get_session_context() as db:
        user = User(telegram_user_id=telegram_user_id, is_coach=False)
        db.add(user)
        db.flush()
        db.add(UserProfile(user_id=user.id, timezone="Europe/Moscow"))
        db.add(NotificationSetting(user_id=user.id))
        subscription_endpoints: list[str] = []
        for suffix in ("device-a", "device-b"):
            payload = _valid_subscription_payload(suffix)
            register_subscription(
                db,
                user,
                endpoint=payload["endpoint"],
                p256dh=payload["keys"]["p256dh"],
                auth=payload["keys"]["auth"],
            )
            subscription_endpoints.append(payload["endpoint"])
        notification = Notification(
            user_id=user.id,
            category="trainer_program_update",
            event_kind="transactional",
            title="Программа обновлена",
            body="Скрытое содержимое",
            scheduled_for=datetime(2026, 8, 24, 9),
            scheduled_for_utc=datetime(2026, 8, 24, 6),
            status="queued",
            action_url="/app?section=programs",
        )
        db.add(notification)
        db.flush()
        enqueue_web_push_deliveries(db, [notification])
        return notification.id, subscription_endpoints


def test_web_push_settings_require_valid_vapid_pair_and_safe_hosts() -> None:
    public_key, private_key = _valid_vapid_keys()
    configured = Settings(
        **_settings_base(),
        web_push_enabled=True,
        web_push_vapid_subject="mailto:push@example.test",
        web_push_vapid_public_key=public_key,
        web_push_vapid_private_key=SecretStr(private_key),
    )
    assert configured.web_push_endpoint_host_allowlist[0] == "fcm.googleapis.com"

    with pytest.raises(ValidationError, match="WEB_PUSH_ENDPOINT_HOSTS"):
        Settings(
            **_settings_base(),
            web_push_endpoint_hosts="fcm..googleapis.com",
            web_push_enabled=True,
            web_push_vapid_subject="mailto:push@example.test",
            web_push_vapid_public_key=public_key,
            web_push_vapid_private_key=SecretStr(private_key),
        )
    with pytest.raises(ValidationError, match="credential-free"):
        Settings(
            **_settings_base(),
            web_push_enabled=True,
            web_push_vapid_subject="https://user:password@example.test/push",
            web_push_vapid_public_key=public_key,
            web_push_vapid_private_key=SecretStr(private_key),
        )
    with pytest.raises(ValidationError, match="credential-free"):
        Settings(
            **_settings_base(),
            web_push_enabled=True,
            web_push_vapid_subject="https://example.test/push",
            web_push_vapid_public_key=public_key,
            web_push_vapid_private_key=SecretStr(private_key),
        )
    with pytest.raises(ValidationError, match="credential-free"):
        Settings(
            **_settings_base(),
            web_push_enabled=True,
            web_push_vapid_subject="https://localhost:bad",
            web_push_vapid_public_key=public_key,
            web_push_vapid_private_key=SecretStr(private_key),
        )
    other_public_key, _other_private_key = _valid_vapid_keys()
    with pytest.raises(ValidationError, match="does not match"):
        Settings(
            **_settings_base(),
            web_push_enabled=True,
            web_push_vapid_subject="mailto:push@example.test",
            web_push_vapid_public_key=other_public_key,
            web_push_vapid_private_key=SecretStr(private_key),
        )


def test_web_push_api_is_idempotent_and_transfers_one_capability_safely(
    client, monkeypatch
) -> None:
    _enable_web_push(monkeypatch)
    first_headers = _login(client, 9_860_010)
    second_headers = _login(client, 9_860_011)
    payload = _valid_subscription_payload("shared-device")

    config = client.get("/api/v1/notifications/web-push/config", headers=first_headers)
    assert config.status_code == 200
    assert config.json() == {"enabled": True, "application_server_key": "test-public-key"}
    assert client.get("/api/v1/notifications/web-push/status", headers=first_headers).json() == {
        "enabled": True,
        "registered": False,
    }

    for headers in (first_headers, first_headers):
        registered = client.post(
            "/api/v1/notifications/web-push/subscription",
            headers=headers,
            json=payload,
        )
        assert registered.status_code == 201
        assert registered.json() == {"status": "registered"}

    with get_session_context() as db:
        assert db.query(WebPushSubscription).count() == 1

    transferred = client.post(
        "/api/v1/notifications/web-push/subscription",
        headers=second_headers,
        json=payload,
    )
    assert transferred.status_code == 201
    assert (
        client.request(
            "DELETE",
            "/api/v1/notifications/web-push/subscription",
            headers=first_headers,
            json={"endpoint": payload["endpoint"]},
        ).status_code
        == 204
    )
    assert client.get("/api/v1/notifications/web-push/status", headers=second_headers).json() == {
        "enabled": True,
        "registered": True,
    }

    invalid = client.post(
        "/api/v1/notifications/web-push/subscription",
        headers=second_headers,
        json={**payload, "endpoint": "http://fcm.googleapis.com/not-safe"},
    )
    assert invalid.status_code == 422
    invalid_point = client.post(
        "/api/v1/notifications/web-push/subscription",
        headers=second_headers,
        json={
            **payload,
            "keys": {
                **payload["keys"],
                "p256dh": base64.urlsafe_b64encode(b"\x04" + b"p" * 64)
                .rstrip(b"=")
                .decode("ascii"),
            },
        },
    )
    assert invalid_point.status_code == 422


def test_web_push_fanout_is_per_device_and_delivery_is_idempotent(monkeypatch) -> None:
    _enable_web_push(monkeypatch)
    with get_session_context() as db:
        user = User(telegram_user_id=9_860_020, is_coach=False)
        db.add(user)
        db.flush()
        db.add(UserProfile(user_id=user.id, timezone="Europe/Moscow"))
        db.add(NotificationSetting(user_id=user.id))
        for suffix in ("one", "two"):
            payload = _valid_subscription_payload(f"fanout-{suffix}")
            register_subscription(
                db,
                user,
                endpoint=payload["endpoint"],
                p256dh=payload["keys"]["p256dh"],
                auth=payload["keys"]["auth"],
            )
        event = Notification(
            user_id=user.id,
            category="trainer_program_update",
            event_kind="transactional",
            title="Программа обновлена",
            body="Private body",
            scheduled_for=datetime(2026, 8, 24, 9),
            scheduled_for_utc=datetime(2026, 8, 24, 6),
            status="queued",
        )
        db.add(event)
        db.flush()
        assert enqueue_web_push_deliveries(db, [event]) == 2
        assert enqueue_web_push_deliveries(db, [event]) == 0
        db.commit()
        assert db.query(NotificationDelivery).count() == 2


def test_web_push_worker_sends_each_device_and_removes_expired_capability(
    monkeypatch,
    caplog,
) -> None:
    _enable_web_push(monkeypatch)
    notification_id, endpoints = _create_due_event_with_subscriptions()
    send = AsyncMock()
    monkeypatch.setattr(worker, "send_web_push", send)

    asyncio.run(worker._run_web_push_delivery_batch())

    assert send.await_count == 2
    assert {call.args[0]["endpoint"] for call in send.await_args_list} == set(endpoints)
    with get_session_context() as db:
        rows = db.query(NotificationDelivery).all()
        assert len(rows) == 2
        assert {row.status for row in rows} == {"sent"}
        assert db.get(Notification, notification_id).body == "Скрытое содержимое"

    notification_id, endpoints = _create_due_event_with_subscriptions(9_860_002)
    expired = WebPushDeliveryError(
        "web_push_subscription_expired",
        terminal_status="cancelled",
        remove_subscription=True,
    )
    send = AsyncMock(side_effect=expired)
    monkeypatch.setattr(worker, "send_web_push", send)
    with caplog.at_level("ERROR", logger="fitminiapp_api.services.worker"):
        asyncio.run(worker._run_web_push_delivery_batch())

    assert notification_id
    assert send.await_count == 2
    assert all(endpoint not in caplog.text for endpoint in endpoints)
    assert all(
        getattr(record, "delivery_error", None) == "web_push_subscription_expired"
        for record in caplog.records
    )
    with get_session_context() as db:
        assert db.query(WebPushSubscription).count() == 0
        assert db.query(NotificationDelivery).count() == 0


def test_web_push_worker_passes_only_the_resolved_internal_destination(monkeypatch) -> None:
    _enable_web_push(monkeypatch)
    send = AsyncMock()
    monkeypatch.setattr(worker, "send_web_push", send)

    _create_due_event_with_subscriptions()
    asyncio.run(worker._run_web_push_delivery_batch())

    assert send.await_count == 2
    for call in send.await_args_list:
        target = call.args[0]
        assert target["action_url"] == "/app?section=programs"
        assert "title" not in target
        assert "body" not in target


def test_web_push_payload_keeps_context_route_but_not_notification_content(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_webpush(**kwargs):
        calls.append(kwargs)
        return types.SimpleNamespace(status_code=201, text="", headers={})

    monkeypatch.setitem(sys.modules, "pywebpush", types.SimpleNamespace(webpush=fake_webpush))
    monkeypatch.setattr(
        "fitminiapp_api.services.web_push._vapid_key_for_delivery",
        lambda: object(),
    )
    monkeypatch.setattr(settings, "web_push_enabled", True)
    payload = _valid_subscription_payload("context-route")
    payload["action_url"] = "/app?section=nutrition&date=2026-08-24&meal=breakfast"

    _send_web_push_sync(payload)

    assert json.loads(calls[0]["data"]) == {
        "version": 2,
        "url": "/app?section=nutrition&date=2026-08-24&meal=breakfast",
    }


def test_account_delete_removes_push_capabilities_and_delivery_rows(client, monkeypatch) -> None:
    _enable_web_push(monkeypatch)
    headers = _login(client, 9_860_030)
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    with get_session_context() as db:
        notification = Notification(
            user_id=user_id,
            category="trainer_program_update",
            event_kind="transactional",
            title="Программа обновлена",
            body="Private body",
            scheduled_for=datetime(2026, 8, 24, 9),
            scheduled_for_utc=datetime(2026, 8, 24, 6),
            status="queued",
        )
        db.add(notification)
        db.flush()
        subscription = WebPushSubscription(
            user_id=user_id,
            endpoint="https://fcm.googleapis.com/fcm/send/delete-me",
            endpoint_hash="delete-me-hash",
            p256dh="test-p256dh",
            auth="test-auth",
        )
        db.add(subscription)
        db.flush()
        db.add(
            NotificationDelivery(
                notification_id=notification.id,
                subscription_id=subscription.id,
            )
        )

    deleted = client.request(
        "DELETE",
        "/api/v1/me/account",
        headers=headers,
        json={"confirmation": "DELETE"},
    )
    assert deleted.status_code == 204
    with get_session_context() as db:
        assert db.get(User, user_id) is None
        assert db.query(WebPushSubscription).filter_by(user_id=user_id).count() == 0
        assert db.query(NotificationDelivery).count() == 0


@pytest.mark.parametrize(
    ("status_code", "expected_code", "remove"),
    [
        (400, "web_push_subscription_invalid", True),
        (404, "web_push_subscription_expired", True),
        (410, "web_push_subscription_expired", True),
        (429, "web_push_rate_limited", False),
        (503, "web_push_provider_unavailable", False),
    ],
)
def test_web_push_provider_outcomes_are_bounded(status_code, expected_code, remove) -> None:
    error = type("ProviderError", (Exception,), {"status_code": status_code})()
    classified = _classify_delivery_exception(error)
    assert classified.code == expected_code
    assert classified.remove_subscription is remove


def test_invalid_vapid_configuration_does_not_remove_subscriptions() -> None:
    classified = _classify_delivery_exception(WebPushConfigurationError())

    assert classified.code == "web_push_configuration_invalid"
    assert classified.terminal_status == "failed"
    assert classified.remove_subscription is False


def test_web_push_provider_redirects_are_disabled(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_webpush(**kwargs):
        session = kwargs["requests_session"]
        calls.append({"max_redirects": session.max_redirects, "trust_env": session.trust_env})
        return types.SimpleNamespace(status_code=201, text="", headers={})

    monkeypatch.setitem(sys.modules, "pywebpush", types.SimpleNamespace(webpush=fake_webpush))
    monkeypatch.setattr(
        "fitminiapp_api.services.web_push._vapid_key_for_delivery",
        lambda: object(),
    )
    monkeypatch.setattr(settings, "web_push_enabled", True)

    _send_web_push_sync(_valid_subscription_payload("redirect-test"))

    assert calls == [{"max_redirects": 0, "trust_env": False}]
