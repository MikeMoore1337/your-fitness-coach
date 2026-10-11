from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import jwt
import pytest
from fastapi import Request, Response
from starlette.testclient import TestClient

from fitminiapp_api.api.v1 import auth as auth_api
from fitminiapp_api.api.v1.auth import issue_token_pair
from fitminiapp_api.core.config import settings
from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.main import app
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.auth_identity import AuthActionToken, AuthIdentity
from fitminiapp_api.models.token import RefreshToken
from fitminiapp_api.models.user import User
from fitminiapp_api.services.auth_redirects import auth_error_redirect, safe_auth_next_path
from fitminiapp_api.services.jwt import ALGORITHM, decode_token, hash_token
from fitminiapp_api.services.oauth_login import get_or_create_oauth_user
from fitminiapp_api.services.oauth_transactions import transaction_hash_prefix
from fitminiapp_api.services.password_auth import utcnow
from fitminiapp_api.services.telegram_auth import get_or_create_user_from_init_data


@pytest.mark.parametrize(
    ("provider_error", "expected_category"),
    [
        ("access_denied", "denied"),
        ("cancelled", "denied"),
        ("user_cancelled", "denied"),
        ("user_denied", "denied"),
        ("invalid_state", "invalid_state"),
        ("mismatching_state", "invalid_state"),
        ("missing_state", "invalid_state"),
        ("secret-provider-token\r\npassword=private", "provider_failure"),
    ],
)
def test_oauth_log_contains_only_error_category_and_hashed_state(
    provider_error, expected_category, caplog
):
    request = Request({"type": "http"})
    request.state.request_id = "test-oauth-request"
    state = "private-oauth-state-12345678"
    category = auth_api._provider_error_category(provider_error)
    assert category == expected_category

    auth_api._log_oauth_event(
        "oauth_login_failed",
        request,
        provider="google",
        purpose="login",
        reason=category,
        state=state,
    )

    record = caplog.records[-1]
    assert record.reason == expected_category
    assert record.provider == "google"
    assert record.purpose == "login"
    assert record.request_id == "test-oauth-request"
    assert record.transaction_hash_prefix == transaction_hash_prefix(state)
    assert state not in repr(record.__dict__)
    assert "secret-provider-token" not in repr(record.__dict__)
    assert "password=private" not in repr(record.__dict__)


def _login(client: TestClient, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": False},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _authenticate_existing_user(client: TestClient, user_id: int) -> dict[str, str]:
    response = Response()
    with get_session_context() as db:
        user = db.query(User).filter(User.id == user_id).one()
        token_pair = issue_token_pair(db, user, response)
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    client.cookies.set(settings.refresh_cookie_name, cookie[settings.refresh_cookie_name].value)
    return {"Authorization": f"Bearer {token_pair.access_token}"}


class _FakeGoogleClient:
    def __init__(self, claims: dict[str, object]) -> None:
        self.claims = claims

    async def create_authorization_url(self, callback_url):
        state = f"fake-google-state-{id(self)}"
        return {
            "url": f"https://accounts.example/authorize?state={state}",
            "state": state,
            "code_verifier": "fake-google-code-verifier",
            "redirect_uri": callback_url,
        }

    async def authorize_access_token(self, request):
        del request
        return {"userinfo": self.claims}


def test_oauth_link_is_bound_to_owner_session_and_is_one_time(client, monkeypatch):
    claims = {
        "sub": "session-bound-google",
        "email": "session-bound@example.com",
        "email_verified": True,
        "name": "Session Bound",
    }
    monkeypatch.setattr(settings, "enable_web_auth", True)
    monkeypatch.setattr(settings, "google_oauth_client_id", "google-client")
    monkeypatch.setattr(settings, "google_oauth_client_secret", "google-secret")
    monkeypatch.setattr(
        auth_api,
        "configured_oauth_client",
        lambda provider: _FakeGoogleClient(claims) if provider == "google" else None,
    )

    owner_headers = _login(client, 9_110_001)
    owner_id = client.get("/api/v1/me", headers=owner_headers).json()["id"]
    created = client.post("/api/v1/me/auth/oauth-link/google", headers=owner_headers)
    link_url = created.json()["oauth_url"]

    unauthenticated = TestClient(app)
    assert unauthenticated.get(link_url, follow_redirects=False).status_code == 401

    other = TestClient(app)
    _login(other, 9_110_002)
    assert other.get(link_url, follow_redirects=False).status_code == 403

    started = client.get(link_url, follow_redirects=False)
    assert started.status_code in {302, 307}
    state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]
    callback = client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"code": "provider-code", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert callback.headers["location"] == "/app?auth_linked=google"
    assert settings.refresh_cookie_name not in callback.headers.get("set-cookie", "")

    replayed = client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"code": "provider-code", "state": state},
        follow_redirects=False,
    )
    assert replayed.status_code == 303
    assert replayed.headers["location"] == (
        "/login?next=%2Fapp&auth_error=invalid_state&oauth_provider=google"
    )
    with get_session_context() as db:
        identities = db.query(AuthIdentity).filter(AuthIdentity.user_id == owner_id).all()
        assert sorted(identity.provider for identity in identities) == ["google", "telegram"]
        mismatch = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.action == "account.oauth_link_session_mismatch",
                AuditEvent.target_user_id == owner_id,
            )
            .one()
        )
        assert mismatch.details == {"provider": "google"}


def test_expired_oauth_link_is_rejected_without_raw_token_details(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_web_auth", True)
    monkeypatch.setattr(settings, "google_oauth_client_id", "google-client")
    monkeypatch.setattr(settings, "google_oauth_client_secret", "google-secret")
    monkeypatch.setattr(
        auth_api,
        "configured_oauth_client",
        lambda provider: _FakeGoogleClient({"sub": "unused"}) if provider == "google" else None,
    )
    headers = _login(client, 9_110_003)
    created = client.post("/api/v1/me/auth/oauth-link/google", headers=headers)
    raw_token = parse_qs(urlparse(created.json()["oauth_url"]).query)["token"][0]
    with get_session_context() as db:
        row = db.query(AuthActionToken).filter(AuthActionToken.purpose == "link_oauth_google").one()
        row.expires_at = utcnow() - timedelta(seconds=1)

    response = client.get(created.json()["oauth_url"], follow_redirects=False)
    assert response.status_code == 400
    assert response.json() == {"detail": "Ссылка привязки недействительна"}
    assert raw_token not in response.text


def test_oauth_browser_errors_are_normalized(client, monkeypatch):
    blocked_claims = {"sub": "blocked-browser-login", "email": "blocked@example.com"}
    with get_session_context() as db:
        blocked = get_or_create_oauth_user(db, provider="google", raw_claims=blocked_claims)
        blocked.is_active = False

    monkeypatch.setattr(settings, "enable_web_auth", True)
    monkeypatch.setattr(settings, "google_oauth_client_id", "google-client")
    monkeypatch.setattr(settings, "google_oauth_client_secret", "google-secret")
    monkeypatch.setattr(
        auth_api,
        "configured_oauth_client",
        lambda provider: _FakeGoogleClient(blocked_claims) if provider == "google" else None,
    )

    started = client.get("/api/v1/auth/oauth/google/start", follow_redirects=False)
    assert started.status_code in {
        302,
        307,
    }
    state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]
    denied = client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"error": "access_denied", "state": state},
        follow_redirects=False,
    )
    assert denied.headers["location"] == (
        "/login?next=%2Fapp&auth_error=denied&oauth_provider=google"
    )

    started = client.get("/api/v1/auth/oauth/google/start", follow_redirects=False)
    state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]
    blocked_response = client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"code": "provider-code", "state": state},
        follow_redirects=False,
    )
    assert blocked_response.headers["location"] == (
        "/login?next=%2Fapp&auth_error=blocked&oauth_provider=google"
    )


def test_refresh_replay_revokes_only_its_family_and_logout_revokes_access():
    first = TestClient(app)
    first_headers = _login(first, 9_110_004)
    first_access = first_headers["Authorization"]
    old_refresh = first.cookies.get(settings.refresh_cookie_name)
    assert old_refresh
    assert first.post("/api/v1/auth/refresh").status_code == 200

    second = TestClient(app)
    second_headers = _login(second, 9_110_004)
    second_refresh = second.cookies.get(settings.refresh_cookie_name)
    assert second_refresh and second_refresh != old_refresh

    replay = first.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert replay.status_code == 401
    assert first.cookies.get(settings.refresh_cookie_name) is None
    assert first.get("/api/v1/me", headers={"Authorization": first_access}).status_code == 401
    assert second.post("/api/v1/auth/refresh").status_code == 200

    active_access = second_headers["Authorization"]
    second.cookies.clear()
    assert (
        second.post(
            "/api/v1/auth/logout",
            headers={"Authorization": active_access},
        ).status_code
        == 200
    )
    assert second.get("/api/v1/me", headers={"Authorization": active_access}).status_code == 401

    with get_session_context() as db:
        families = {
            row.family_id
            for row in db.query(RefreshToken).join(User).filter(User.telegram_user_id == 9_110_004)
        }
        assert len(families) == 2
        assert (
            db.query(AuditEvent).filter(AuditEvent.action == "session.refresh_replay").count() == 1
        )


def test_legacy_refresh_token_rotates_once_into_session_family(client):
    headers = _login(client, 9_110_009)
    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 9_110_009).one()
        db.query(RefreshToken).filter(RefreshToken.user_id == user.id).delete()
        now = datetime.now(UTC)
        jti = uuid4().hex
        payload = {
            "sub": str(user.id),
            "type": "refresh",
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=1)).timestamp()),
        }
        legacy_token = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
        db.add(
            RefreshToken(
                user_id=user.id,
                jti=jti,
                family_id=jti,
                token_hash=hash_token(legacy_token),
                expires_at=(now + timedelta(days=1)).replace(tzinfo=None),
            )
        )
    client.cookies.set(settings.refresh_cookie_name, legacy_token)

    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    access_payload = decode_token(refreshed.json()["access_token"], expected_type="access")
    assert access_payload["sid"] == jti
    assert client.get("/api/v1/me", headers=headers).status_code == 401


def test_blocked_account_loses_access_and_refresh(client):
    headers = _login(client, 9_110_005)
    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 9_110_005).one()
        user.is_active = False

    assert client.get("/api/v1/me", headers=headers).status_code == 401
    refresh = client.post("/api/v1/auth/refresh")
    assert refresh.status_code == 403
    assert refresh.json() == {"detail": "Аккаунт заблокирован"}
    assert client.cookies.get(settings.refresh_cookie_name) is None


def test_password_reset_revokes_existing_access_session(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_email_auth", True)
    email = "session-reset@example.com"
    registered = client.post(
        "/api/v1/auth/email/register",
        json={
            "username": "session_reset",
            "email": email,
            "password": "safe-password-before-reset",
        },
    )
    verification_token = registered.json()["verification_token"]
    verified = client.post(
        "/api/v1/auth/email/verify",
        json={"token": verification_token},
    )
    headers = {"Authorization": f"Bearer {verified.json()['access_token']}"}
    assert client.get("/api/v1/me", headers=headers).status_code == 200

    requested = client.post("/api/v1/auth/password/reset/request", json={"email": email})
    reset_token = requested.json()["action_token"]
    confirmed = client.post(
        "/api/v1/auth/password/reset/confirm",
        json={"token": reset_token, "password": "safe-password-after-reset"},
    )
    assert confirmed.status_code == 200
    assert client.get("/api/v1/me", headers=headers).status_code == 401


def test_private_responses_and_auth_cookies_have_safe_policy(client, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "prod")
    login = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": 9_110_006, "is_coach": False},
    )
    cookie = login.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=strict" in cookie
    assert "path=/api/v1/auth" in cookie
    assert login.headers["cache-control"] == "no-store, private"
    assert login.headers["pragma"] == "no-cache"

    me = client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert me.headers["cache-control"] == "no-store, private"
    assert me.headers["pragma"] == "no-cache"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/app", "/app"),
        ("/app?trainer_intent=1", "/app?trainer_intent=1"),
        ("/coach", "/coach"),
        ("/admin", "/admin"),
        ("/join/Abc_12345678901234567890", "/join/Abc_12345678901234567890"),
        ("https://evil.example", None),
        ("//evil.example/path", None),
        ("/%2F%2Fevil.example", None),
        ("%2F%2Fevil.example", None),
        ("/app%3Fnext=https://evil.example", None),
        ("/app?trainer_intent=1&next=https://evil.example", None),
        ("/unknown", None),
    ],
)
def test_safe_auth_next_allowlist(value, expected):
    assert safe_auth_next_path(value) == expected


def test_auth_error_redirect_keeps_only_a_safe_continuation():
    assert auth_error_redirect("denied", next_path="/coach") == (
        "/login?next=%2Fcoach&auth_error=denied"
    )
    assert auth_error_redirect("denied", next_path="/app?trainer_intent=1") == (
        "/login?next=%2Fapp%3Ftrainer_intent%3D1&auth_error=denied"
    )
    assert auth_error_redirect("provider-secret", next_path="https://evil.example") == (
        "/login?next=%2Fapp&auth_error=provider_failure"
    )


def test_root_telegram_identity_cannot_be_transferred_by_link(client, monkeypatch):
    root_telegram_id = 9_110_007
    monkeypatch.setattr(settings, "admin_telegram_user_ids", str(root_telegram_id))
    monkeypatch.setattr(settings, "telegram_bot_username", "your_fitness_coach_bot")
    with get_session_context() as db:
        user = get_or_create_oauth_user(
            db,
            provider="google",
            raw_claims={"sub": "root-link-target", "email": "target@example.com"},
        )
        target_user_id = user.id
    headers = _authenticate_existing_user(client, target_user_id)
    created = client.post("/api/v1/me/auth/telegram-link", headers=headers)
    token = parse_qs(urlparse(created.json()["telegram_url"]).query)["start"][0].removeprefix(
        "link_"
    )

    linked = client.post(
        "/api/v1/bot/link-telegram",
        headers={"X-Bot-Token": settings.bot_internal_token},
        json={"token": token, "telegram_user_id": root_telegram_id},
    )
    assert linked.status_code == 409
    with get_session_context() as db:
        target = db.query(User).filter(User.id == target_user_id).one()
        assert target.telegram_user_id is None
        assert (
            db.query(AuditEvent)
            .filter(
                AuditEvent.action == "account.root_telegram_link_rejected",
                AuditEvent.target_user_id == target_user_id,
            )
            .count()
            == 1
        )


def test_legacy_telegram_user_gets_one_consistent_identity():
    with get_session_context() as db:
        legacy = User(telegram_user_id=9_110_008, username="legacy", is_active=True)
        db.add(legacy)
        db.flush()
        legacy_id = legacy.id

    with get_session_context() as db:
        user = get_or_create_user_from_init_data(
            db,
            {"user": {"id": 9_110_008, "username": "legacy", "first_name": "Legacy"}},
        )
        assert user.id == legacy_id
        identities = (
            db.query(AuthIdentity)
            .filter(AuthIdentity.provider == "telegram", AuthIdentity.subject == "9110008")
            .all()
        )
        assert len(identities) == 1
        assert identities[0].user_id == legacy_id


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL locking")
def test_concurrent_first_oauth_login_creates_one_account():
    claims = {"sub": "concurrent-first-login", "email": "concurrent@example.com"}

    def login_once() -> int:
        with get_session_context() as db:
            return get_or_create_oauth_user(db, provider="google", raw_claims=claims).id

    with ThreadPoolExecutor(max_workers=4) as executor:
        user_ids = list(executor.map(lambda _: login_once(), range(4)))

    assert len(set(user_ids)) == 1
    with get_session_context() as db:
        assert (
            db.query(AuthIdentity)
            .filter(
                AuthIdentity.provider == "google",
                AuthIdentity.subject == "concurrent-first-login",
            )
            .count()
            == 1
        )
