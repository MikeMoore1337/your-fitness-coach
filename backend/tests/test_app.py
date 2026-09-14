import hashlib
import hmac
import json
import re
import time
from datetime import UTC, date, datetime, timedelta
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from xml.etree import ElementTree

import pytest
from fastapi import Response
from pydantic import ValidationError
from sqlalchemy import text

from fitminiapp_api.api.v1.auth import issue_token_pair
from fitminiapp_api.core.config import Settings, settings
from fitminiapp_api.core.timezone import to_msk_naive, today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.notification import Notification, NotificationSetting
from fitminiapp_api.models.program import (
    ProgramTemplate,
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import (
    CoachClient,
    CoachClientInvite,
    User,
    UserProfile,
)
from fitminiapp_api.services import notifications as notifications_service
from fitminiapp_api.services.coach_clients import create_coach_invite_link
from fitminiapp_api.services.exercise_guides import get_exercise_guide
from fitminiapp_api.services.notifications import (
    claim_due_notifications,
    mark_delivery_failed,
    sync_workout_reminders,
)
from fitminiapp_api.services.program_common import ProgramError
from fitminiapp_api.services.seed import seed_demo_data
from fitminiapp_api.services.telegram_auth import validate_telegram_init_data
from fitminiapp_api.services.trainer_capability import activate_trainer_capability


def signed_init_data(
    bot_token: str,
    auth_date: int,
    telegram_user_id: int = 555001,
    username: str | None = None,
    user_data: object | None = None,
) -> str:
    user = (
        user_data if user_data is not None else {"id": telegram_user_id, "first_name": "Telegram"}
    )
    if username and isinstance(user, dict):
        user["username"] = username
    data = {
        "auth_date": str(auth_date),
        "user": json.dumps(user, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    data["hash"] = hmac.new(
        key=secret_key,
        msg=data_check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return urlencode(data)


def auth(
    client,
    telegram_user_id=1001,
    is_coach=True,
    is_admin=False,
    username=None,
    full_name=None,
):
    payload = {
        "telegram_user_id": telegram_user_id,
        "is_coach": is_coach,
        "is_admin": is_admin,
    }
    if username is not None:
        payload["username"] = username
    if full_name is not None:
        payload["full_name"] = full_name

    response = client.post(
        "/api/v1/auth/dev-login",
        json=payload,
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def auth_existing_user(client, user_id: int) -> dict[str, str]:
    response = Response()
    with get_session_context() as db:
        user = db.query(User).filter(User.id == user_id).one()
        token_pair = issue_token_pair(db, user, response)
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    client.cookies.set(settings.refresh_cookie_name, cookie[settings.refresh_cookie_name].value)
    return {"Authorization": f"Bearer {token_pair.access_token}"}


def create_coach_invite_token(client, coach_headers):
    created = client.post("/api/v1/coach/invite-links", headers=coach_headers)
    assert created.status_code == 201
    start_param = created.json()["start_param"]
    assert start_param.startswith("trainer_")
    return start_param.removeprefix("trainer_"), created.json()


def accept_coach_invite(client, coach_headers, client_headers):
    token, created = create_coach_invite_token(client, coach_headers)
    preview = client.post(
        "/api/v1/me/coach-invites/link/preview",
        json={"token": token},
        headers=client_headers,
    )
    assert preview.status_code == 200
    assert preview.json()["invite_id"] == created["invite_id"]
    accepted = client.post(
        "/api/v1/me/coach-invites/link/confirm",
        json={"token": token},
        headers=client_headers,
    )
    assert accepted.status_code == 204
    return created, preview.json()


def test_dev_login_and_me(client):
    headers = auth(client)
    response = client.get("/api/v1/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["telegram_user_id"] == 1001
    assert data["is_coach"] is True


def test_onboarding_state_uses_existing_profile_and_resumes_partial_progress(client):
    headers = auth(client, telegram_user_id=1002, is_coach=False)

    initial = client.get("/api/v1/me", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["onboarding"] == {
        "status": "required",
        "required_fields": ["goal"],
        "missing_fields": ["goal"],
    }

    partial = client.patch(
        "/api/v1/me/profile",
        headers=headers,
        json={"height_cm": 180, "weight_kg": 80},
    )
    assert partial.status_code == 200
    assert partial.json()["onboarding"]["status"] == "required"
    assert partial.json()["profile"]["height_cm"] == 180
    assert partial.json()["profile"]["weight_kg"] == 80

    invalid = client.patch(
        "/api/v1/me/profile",
        headers=headers,
        json={"goal": "fast_result"},
    )
    assert invalid.status_code == 422
    after_invalid = client.get("/api/v1/me", headers=headers).json()
    assert after_invalid["onboarding"]["status"] == "required"
    assert after_invalid["profile"]["height_cm"] == 180

    completed = client.patch(
        "/api/v1/me/profile",
        headers=headers,
        json={"goal": "maintenance"},
    )
    assert completed.status_code == 200
    assert completed.json()["onboarding"] == {
        "status": "complete",
        "required_fields": ["goal"],
        "missing_fields": [],
    }
    assert completed.json()["profile"]["height_cm"] == 180
    assert completed.json()["profile"]["weight_kg"] == 80

    with get_session_context() as db:
        user_id = completed.json()["id"]
        assert db.query(UserProfile).filter(UserProfile.user_id == user_id).count() == 1


def test_production_settings_reject_placeholder_secret():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(
            app_env="prod",
            app_name="Your Fitness Coach",
            app_debug=False,
            secret_key="change-me",
            access_token_expire_minutes=60,
            refresh_token_expire_days=30,
            database_url="postgresql+psycopg://app:password@db/app",
            enable_dev_auth=False,
            telegram_bot_token="123456:configured-token",
            frontend_base_url="https://example.test",
        )


def test_versioned_frontend_assets_have_immutable_cache_contract(client):
    response = client.get("/assets/test.js")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_pwa_control_assets_are_same_origin_and_not_cached(client, monkeypatch, tmp_path):
    from fitminiapp_api import main

    (tmp_path / "manifest.webmanifest").write_text(
        '{"id":"/app","start_url":"/app?source=pwa","scope":"/"}',
        encoding="utf-8",
    )
    (tmp_path / "sw.js").write_text(
        "self.addEventListener('fetch', () => undefined);", encoding="utf-8"
    )
    monkeypatch.setattr(main, "FRONTEND_DIST_DIR", tmp_path)

    manifest = client.get("/manifest.webmanifest")
    worker = client.get("/sw.js")

    assert manifest.status_code == 200
    assert manifest.headers["content-type"] == "application/manifest+json"
    assert manifest.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"
    assert worker.status_code == 200
    assert worker.headers["content-type"] == "application/javascript"
    assert worker.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"
    assert "access_token" not in manifest.text
    assert "access_token" not in worker.text


def test_production_settings_reject_placeholder_bot_internal_token():
    with pytest.raises(ValidationError, match="BOT_INTERNAL_TOKEN"):
        Settings(
            app_env="prod",
            app_name="Your Fitness Coach",
            app_debug=False,
            secret_key="a-production-secret-that-is-long-enough",
            access_token_expire_minutes=60,
            refresh_token_expire_days=30,
            database_url="postgresql+psycopg://app:password@db/app",
            enable_dev_auth=False,
            telegram_bot_token="123456:configured-token",
            bot_internal_token="replace-with-a-separate-random-secret-at-least-32-characters",
            frontend_base_url="https://example.test",
        )


def test_production_oauth_does_not_require_smtp_when_email_auth_is_disabled():
    configured = Settings(
        app_env="prod",
        app_name="Your Fitness Coach",
        app_debug=False,
        secret_key="a-production-secret-that-is-long-enough",
        access_token_expire_minutes=60,
        refresh_token_expire_days=30,
        database_url="postgresql+psycopg://app:password@db/app",
        enable_dev_auth=False,
        enable_web_auth=True,
        enable_email_auth=False,
        telegram_bot_token="123456:configured-token",
        bot_internal_token="a-separate-production-token-that-is-long-enough",
        frontend_base_url="https://example.test",
        smtp_host="",
        smtp_from_email="",
        oauth_proxy_url="",
        telegram_oauth_proxy_url="socks5://host.docker.internal:1081",
        telegram_bot_proxy_url="",
    )

    assert configured.enable_web_auth is True
    assert configured.enable_email_auth is False
    assert configured.oauth_http_timeout_seconds == 15
    assert configured.oauth_force_ipv4 is True
    assert configured.oauth_proxy_url == ""
    assert configured.telegram_oauth_proxy_url == "socks5://host.docker.internal:1081"
    assert configured.telegram_bot_proxy_url == ""


def test_oauth_http_timeout_is_bounded():
    common = {
        "app_env": "dev",
        "app_name": "Your Fitness Coach",
        "app_debug": False,
        "secret_key": "test-secret",
        "access_token_expire_minutes": 60,
        "refresh_token_expire_days": 30,
        "database_url": "sqlite://",
        "telegram_bot_token": "test-token",
    }

    with pytest.raises(ValidationError, match="oauth_http_timeout_seconds"):
        Settings(**common, oauth_http_timeout_seconds=4.9)
    with pytest.raises(ValidationError, match="oauth_http_timeout_seconds"):
        Settings(**common, oauth_http_timeout_seconds=61)
    with pytest.raises(ValidationError, match="OAuth proxy URL"):
        Settings(**common, oauth_proxy_url="file:///tmp/proxy")
    with pytest.raises(ValidationError, match="OAuth proxy URL"):
        Settings(**common, oauth_proxy_url="socks5://proxy.example/?unsafe=true")
    with pytest.raises(ValidationError, match="OAuth proxy URL"):
        Settings(**common, telegram_oauth_proxy_url="file:///tmp/proxy")
    with pytest.raises(ValidationError, match="OAuth proxy URL"):
        Settings(**common, telegram_bot_proxy_url="file:///tmp/proxy")


def test_oidc_clients_ignore_ambient_proxy_settings(monkeypatch):
    from fitminiapp_api.services import oauth_login

    captured: dict[str, object] = {}

    def fake_register(name, **kwargs):
        captured["name"] = name
        captured.update(kwargs)

    monkeypatch.setattr(oauth_login.oauth, "register", fake_register)
    monkeypatch.setattr(oauth_login.settings, "oauth_http_timeout_seconds", 17)

    oauth_login._register_oidc(
        "telegram",
        "client-id",
        "client-secret",
        "https://oauth.example/.well-known/openid-configuration",
        "openid profile",
    )

    assert captured["name"] == "telegram"
    assert captured["client_kwargs"] == {
        "scope": "openid profile",
        "timeout": 17,
        "trust_env": False,
    }
    assert captured["client_cls"] is oauth_login.OAuthStarletteOAuth2App


def test_oidc_clients_can_use_default_dual_stack_transport(monkeypatch):
    from fitminiapp_api.services import oauth_login

    captured: dict[str, object] = {}

    def fake_register(name, **kwargs):
        captured["name"] = name
        captured.update(kwargs)

    monkeypatch.setattr(oauth_login.oauth, "register", fake_register)
    monkeypatch.setattr(oauth_login.settings, "oauth_force_ipv4", False)

    oauth_login._register_oidc(
        "telegram",
        "client-id",
        "client-secret",
        "https://oauth.example/.well-known/openid-configuration",
        "openid profile",
    )

    assert captured["client_cls"] is oauth_login.OAuthStarletteOAuth2App


def test_oidc_client_uses_explicit_proxy_before_ipv4_transport(monkeypatch):
    from fitminiapp_api.services import oauth_login

    monkeypatch.setattr(oauth_login.settings, "oauth_proxy_url", "socks5://proxy.test:1081")
    monkeypatch.setattr(oauth_login.settings, "oauth_force_ipv4", True)

    assert oauth_login.oauth_transport_options() == {"proxy": "socks5://proxy.test:1081"}


def test_oidc_client_uses_ipv4_transport_without_an_explicit_proxy(monkeypatch):
    from fitminiapp_api.services import oauth_login

    monkeypatch.setattr(oauth_login.settings, "oauth_proxy_url", "")
    monkeypatch.setattr(oauth_login.settings, "oauth_force_ipv4", True)

    options = oauth_login.oauth_transport_options()

    assert options["transport"].__class__.__name__ == "AsyncHTTPTransport"


def test_telegram_oidc_client_uses_its_dedicated_proxy(monkeypatch):
    from fitminiapp_api.services import oauth_login

    monkeypatch.setattr(oauth_login.settings, "oauth_proxy_url", "")
    monkeypatch.setattr(
        oauth_login.settings, "telegram_oauth_proxy_url", "socks5://telegram-proxy.test:1081"
    )
    monkeypatch.setattr(oauth_login.settings, "oauth_force_ipv4", True)

    direct_options = oauth_login.oauth_transport_options()
    assert direct_options["transport"].__class__.__name__ == "AsyncHTTPTransport"
    assert oauth_login.oauth_transport_options(
        proxy_url=oauth_login.settings.telegram_oauth_proxy_url
    ) == {"proxy": "socks5://telegram-proxy.test:1081"}


def test_telegram_oidc_registration_uses_the_dedicated_client(monkeypatch):
    from fitminiapp_api.services import oauth_login

    captured: dict[str, object] = {}

    def fake_register(name, **kwargs):
        captured["name"] = name
        captured.update(kwargs)

    monkeypatch.setattr(oauth_login.oauth, "register", fake_register)
    oauth_login._register_oidc(
        "telegram",
        "client-id",
        "client-secret",
        "https://oauth.example/.well-known/openid-configuration",
        "openid profile",
        client_cls=oauth_login.TelegramOAuthStarletteOAuth2App,
    )

    assert captured["client_cls"] is oauth_login.TelegramOAuthStarletteOAuth2App


def test_production_email_auth_requires_smtp():
    with pytest.raises(ValidationError, match="SMTP_HOST"):
        Settings(
            app_env="prod",
            app_name="Your Fitness Coach",
            app_debug=False,
            secret_key="a-production-secret-that-is-long-enough",
            access_token_expire_minutes=60,
            refresh_token_expire_days=30,
            database_url="postgresql+psycopg://app:password@db/app",
            enable_dev_auth=False,
            enable_web_auth=True,
            enable_email_auth=True,
            telegram_bot_token="123456:configured-token",
            bot_internal_token="a-separate-production-token-that-is-long-enough",
            frontend_base_url="https://example.test",
            smtp_host="",
            smtp_from_email="",
            oauth_proxy_url="",
        )


def test_dev_login_can_set_admin_role(client):
    headers = auth(client, telegram_user_id=4001, is_coach=True, is_admin=True)
    response = client.get("/api/v1/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["telegram_user_id"] == 4001
    assert data["is_coach"] is True
    assert data["is_admin"] is True


def test_client_can_save_kbju_and_see_it_in_profile(client):
    headers = auth(client, telegram_user_id=6001, is_coach=False)
    payload = {
        "sex": "male",
        "weight_kg": 80.0,
        "height_cm": 180.0,
        "age": 30.0,
        "strength_trainings_per_week": 3,
        "cardio_trainings_per_week": 1,
        "goal": "muscle_gain",
    }

    saved = client.post("/api/v1/nutrition/targets", json=payload, headers=headers)

    assert saved.status_code == 200
    data = saved.json()
    assert data["calories"] == 2420
    assert data["protein_g"] == 144
    assert data["fat_g"] == 72
    assert data["carbs_g"] == 299
    assert data["daily_activity_level"] == "sedentary"
    assert data["strength_training_duration_minutes"] == 60
    assert data["cardio_training_duration_minutes"] == 30
    assert data["cardio_intensity"] == "moderate"

    me = client.get("/api/v1/me", headers=headers).json()
    kbju = me["profile"]["kbju"]
    assert kbju["calories"] == 2420
    assert kbju["assigned_by"]["telegram_user_id"] == 6001


def test_profile_returns_personalized_heart_rates_and_goal_recommendations(client):
    headers = auth(client, telegram_user_id=6009, is_coach=False)
    today = date.today()
    birth_date = today.replace(year=today.year - 34)
    expected_by_goal = {
        "fat_loss": {"min_bpm": 130, "max_bpm": 140},
        "recomposition": {"min_bpm": 124, "max_bpm": 140},
        "maintenance": {"min_bpm": 119, "max_bpm": 140},
        "muscle_gain": {"min_bpm": 119, "max_bpm": 130},
    }
    zones_by_goal = []

    for goal, expected_range in expected_by_goal.items():
        response = client.patch(
            "/api/v1/me/profile",
            headers=headers,
            json={
                "birth_date": birth_date.isoformat(),
                "resting_heart_rate": 75,
                "goal": goal,
            },
        )

        assert response.status_code == 200
        profile = response.json()["profile"]
        assert profile["estimated_max_heart_rate"] == 184
        assert profile["heart_rate_reserve"] == 109
        assert profile["heart_rate_calculation_method"] == "heart_rate_reserve"
        assert profile["recommended_cardio_range"] == expected_range
        zones_by_goal.append(profile["heart_rate_zones"])

    assert all(zones == zones_by_goal[0] for zones in zones_by_goal[1:])
    assert zones_by_goal[0] == [
        {"zone": 1, "title": "Восстановление", "min_bpm": 130, "max_bpm": 140},
        {"zone": 2, "title": "Лёгкая", "min_bpm": 140, "max_bpm": 151},
        {"zone": 3, "title": "Аэробная", "min_bpm": 151, "max_bpm": 162},
        {"zone": 4, "title": "Пороговая", "min_bpm": 162, "max_bpm": 173},
        {"zone": 5, "title": "Максимальная", "min_bpm": 173, "max_bpm": 184},
    ]


def test_profile_without_resting_heart_rate_keeps_fallback(client):
    headers = auth(client, telegram_user_id=6010, is_coach=False)
    today = date.today()
    birth_date = today.replace(year=today.year - 34)

    response = client.patch(
        "/api/v1/me/profile",
        headers=headers,
        json={"birth_date": birth_date.isoformat(), "goal": "fat_loss"},
    )

    assert response.status_code == 200
    profile = response.json()["profile"]
    assert profile["resting_heart_rate"] is None
    assert profile["estimated_max_heart_rate"] == 184
    assert profile["heart_rate_reserve"] is None
    assert profile["heart_rate_calculation_method"] == "percent_maximum"
    assert profile["recommended_cardio_range"] is None
    assert len(profile["heart_rate_zones"]) == 5


def test_heart_rate_preview_does_not_persist_profile_changes(client):
    headers = auth(client, telegram_user_id=6013, is_coach=False)
    today = date.today()
    birth_date = today.replace(year=today.year - 34)

    response = client.post(
        "/api/v1/me/profile/heart-rates/preview",
        headers=headers,
        json={
            "birth_date": birth_date.isoformat(),
            "resting_heart_rate": 75,
            "goal": "recomposition",
        },
    )

    assert response.status_code == 200
    assert response.json()["recommended_cardio_range"] == {"min_bpm": 124, "max_bpm": 140}
    profile = client.get("/api/v1/me", headers=headers).json()["profile"]
    assert profile["birth_date"] is None
    assert profile["resting_heart_rate"] is None


@pytest.mark.parametrize("resting_heart_rate", [29, 121])
def test_profile_rejects_resting_heart_rate_outside_range(client, resting_heart_rate):
    headers = auth(client, telegram_user_id=6011 + resting_heart_rate, is_coach=False)

    response = client.patch(
        "/api/v1/me/profile",
        headers=headers,
        json={"resting_heart_rate": resting_heart_rate},
    )

    assert response.status_code == 422


def test_profile_rejects_resting_heart_rate_at_or_above_maximum(client):
    headers = auth(client, telegram_user_id=6012, is_coach=False)
    today = date.today()
    birth_date = today.replace(year=today.year - 100)

    response = client.patch(
        "/api/v1/me/profile",
        headers=headers,
        json={"birth_date": birth_date.isoformat(), "resting_heart_rate": 138},
    )

    assert response.status_code == 422

    response = client.patch(
        "/api/v1/me/profile",
        headers=headers,
        json={"birth_date": birth_date.isoformat(), "resting_heart_rate": 120},
    )
    assert response.status_code == 200

    response = client.patch(
        "/api/v1/me/profile",
        headers=headers,
        json={"birth_date": birth_date.isoformat(), "resting_heart_rate": 138},
    )
    assert response.status_code == 422


def test_client_can_save_detailed_activity_and_multiple_cardio_trainings(client):
    headers = auth(client, telegram_user_id=6002, is_coach=False)
    payload = {
        "sex": "female",
        "weight_kg": 64,
        "height_cm": 168,
        "age": 28,
        "daily_routine": "mixed",
        "steps_range": "from_7000_to_10000",
        "strength_trainings_per_week": 2,
        "strength_training_duration_minutes": 70,
        "strength_training_type": "heavy",
        "strength_rest": "over_three",
        "cardio_trainings": [
            {
                "kind": "walking",
                "trainings_per_week": 2,
                "duration_minutes": 45,
                "intensity": "light",
            },
            {
                "kind": "swimming",
                "trainings_per_week": 1,
                "duration_minutes": 40,
                "intensity": "hard",
            },
        ],
        "goal": "recomposition",
    }

    saved = client.post("/api/v1/nutrition/targets", json=payload, headers=headers)

    assert saved.status_code == 200
    data = saved.json()
    assert data["daily_routine"] == "mixed"
    assert data["steps_range"] == "from_7000_to_10000"
    assert data["strength_training_type"] == "heavy"
    assert data["strength_rest"] == "over_three"
    assert data["cardio_trainings"] == payload["cardio_trainings"]
    assert data["cardio_trainings_per_week"] == 3
    assert (
        abs(data["protein_g"] * 4 + data["fat_g"] * 9 + data["carbs_g"] * 4 - data["calories"])
        <= 10
    )


def test_coach_can_assign_kbju_to_own_client(client):
    coach_headers = auth(
        client,
        telegram_user_id=6101,
        is_coach=True,
        username="@nutrition_coach",
        full_name="КБЖУ Тренер",
    )
    client_headers = auth(client, telegram_user_id=6102, is_coach=False)
    accept_coach_invite(client, coach_headers, client_headers)

    saved = client.post(
        "/api/v1/nutrition/targets",
        json={
            "target_telegram_user_id": 6102,
            "sex": "female",
            "weight_kg": 64.5,
            "height_cm": 168.0,
            "age": 28.0,
            "strength_trainings_per_week": 2,
            "cardio_trainings_per_week": 2,
            "goal": "fat_loss",
        },
        headers=coach_headers,
    )

    assert saved.status_code == 200
    data = saved.json()
    assert data["telegram_user_id"] == 6102
    assert data["assigned_by"]["username"] == "nutrition_coach"

    me = client.get("/api/v1/me", headers=client_headers).json()
    kbju = me["profile"]["kbju"]
    assert kbju["telegram_user_id"] == 6102
    assert kbju["assigned_by"]["full_name"] == "КБЖУ Тренер"


def test_client_parameter_and_weight_changes_recalculate_kbju_and_notify(client):
    headers = auth(client, telegram_user_id=6103, is_coach=False)
    payload = {
        "sex": "male",
        "weight_kg": 80,
        "height_cm": 180,
        "age": 30,
        "strength_trainings_per_week": 3,
        "cardio_trainings_per_week": 1,
        "goal": "muscle_gain",
    }
    initial = client.post(
        "/api/v1/nutrition/targets",
        json=payload,
        headers=headers,
    ).json()

    profile = client.patch(
        "/api/v1/me/profile",
        json={"goal": "fat_loss"},
        headers=headers,
    )
    assert profile.status_code == 200
    assert profile.json()["profile"]["kbju"]["goal"] == "fat_loss"
    assert profile.json()["profile"]["kbju"]["calories"] != initial["calories"]

    measurement = client.post(
        "/api/v1/workouts/diary",
        json={"measured_on": "2026-08-01", "weight_kg": 75.5},
        headers=headers,
    )
    assert measurement.status_code == 200

    kbju = client.get("/api/v1/me", headers=headers).json()["profile"]["kbju"]
    assert kbju["weight_kg"] == 75.5
    notifications = client.get("/api/v1/notifications", headers=headers).json()
    assert len(notifications) == 3
    assert notifications[0]["title"] == "КБЖУ пересчитаны"
    assert "Новые ориентиры" in notifications[0]["body"]
    assert notifications[0]["status"] == "queued"

    client.post(
        "/api/v1/workouts/diary",
        json={"measured_on": "2026-08-01", "weight_kg": 75.5},
        headers=headers,
    )
    assert len(client.get("/api/v1/notifications", headers=headers).json()) == 3


def test_coach_profile_and_measurement_changes_preserve_explicit_trainer_target(client):
    coach_headers = auth(client, telegram_user_id=6104, is_coach=True)
    client_headers = auth(client, telegram_user_id=6105, is_coach=False)
    client_user = client.get("/api/v1/me", headers=client_headers).json()
    accept_coach_invite(client, coach_headers, client_headers)
    client.post(
        "/api/v1/nutrition/targets",
        json={
            "target_telegram_user_id": 6105,
            "sex": "female",
            "weight_kg": 64.5,
            "height_cm": 168,
            "age": 28,
            "strength_trainings_per_week": 2,
            "cardio_trainings_per_week": 2,
            "goal": "fat_loss",
        },
        headers=coach_headers,
    )

    profile = client.patch(
        f"/api/v1/coach/clients/{client_user['id']}/profile",
        json={"height_cm": 170},
        headers=coach_headers,
    )
    assert profile.status_code == 200
    assert profile.json()["kbju"]["height_cm"] == 168

    measurement = client.post(
        f"/api/v1/coach/clients/{client_user['id']}/measurements",
        json={"measured_on": "2026-08-01", "weight_kg": 63.5},
        headers=coach_headers,
    )
    assert measurement.status_code == 200

    kbju = client.get("/api/v1/me", headers=client_headers).json()["profile"]["kbju"]
    assert kbju["weight_kg"] == 64.5
    assert kbju["assigned_by"]["telegram_user_id"] == 6104
    notifications = client.get("/api/v1/notifications", headers=client_headers).json()
    nutrition_notifications = [
        row for row in notifications if row["title"] == "Ориентиры КБЖУ обновлены"
    ]
    assert len(nutrition_notifications) == 1
    assert "Тренер обновил ориентиры питания" in nutrition_notifications[0]["body"]


def test_nutrition_form_only_notifies_when_calculation_inputs_change(client):
    headers = auth(client, telegram_user_id=6106, is_coach=False)
    payload = {
        "sex": "male",
        "weight_kg": 80,
        "height_cm": 180,
        "age": 30,
        "strength_trainings_per_week": 3,
        "cardio_trainings_per_week": 1,
        "goal": "maintenance",
    }
    client.post("/api/v1/nutrition/targets", json=payload, headers=headers)
    client.post("/api/v1/nutrition/targets", json=payload, headers=headers)
    assert len(client.get("/api/v1/notifications", headers=headers).json()) == 1

    payload["daily_activity_level"] = "high"
    changed = client.post("/api/v1/nutrition/targets", json=payload, headers=headers)
    assert changed.status_code == 200
    assert len(client.get("/api/v1/notifications", headers=headers).json()) == 2


def test_coach_can_update_own_client_profile_and_measurements(client):
    coach_headers = auth(client, telegram_user_id=6110, is_coach=True)
    client_headers = auth(
        client,
        telegram_user_id=6111,
        is_coach=False,
        full_name="Имя клиента",
    )
    other_coach_headers = auth(client, telegram_user_id=6112, is_coach=True)
    client_user = client.get("/api/v1/me", headers=client_headers).json()

    accept_coach_invite(client, coach_headers, client_headers)

    profile = client.patch(
        f"/api/v1/coach/clients/{client_user['id']}/profile",
        json={
            "full_name": "Клиент с анкетой",
            "birth_date": "1990-09-10",
            "goal": "recomposition",
            "level": "intermediate",
            "height_cm": 176,
            "weight_kg": 74,
            "workouts_per_week": 4,
            "cardio_trainings_per_week": 2,
        },
        headers=coach_headers,
    )
    assert profile.status_code == 200
    assert profile.json()["height_cm"] == 176
    assert profile.json()["goal"] == "recomposition"
    assert profile.json()["workouts_per_week"] == 4
    assert profile.json()["cardio_trainings_per_week"] == 2
    assert profile.json()["birth_date"] == "1990-09-10"

    measurement = client.post(
        f"/api/v1/coach/clients/{client_user['id']}/measurements",
        json={"measured_on": "2026-07-31", "weight_kg": 73.5, "waist_cm": 81.2},
        headers=coach_headers,
    )
    assert measurement.status_code == 200
    assert measurement.json()["waist_cm"] == 81.2

    rows = client.get(
        f"/api/v1/coach/clients/{client_user['id']}/measurements",
        headers=coach_headers,
    )
    assert rows.status_code == 200
    assert rows.json()[0]["weight_kg"] == 73.5

    forbidden = client.patch(
        f"/api/v1/coach/clients/{client_user['id']}/profile",
        json={"weight_kg": 90},
        headers=other_coach_headers,
    )
    assert forbidden.status_code == 404

    me = client.get("/api/v1/me", headers=client_headers).json()
    assert me["profile"]["full_name"] == "Имя клиента"
    assert me["profile"]["weight_kg"] == 74
    assert me["profile"]["cardio_trainings_per_week"] == 2

    client_update = client.patch(
        "/api/v1/me/profile",
        json={
            "full_name": "Клиент обновил себя",
            "goal": "fat_loss",
            "height_cm": 174,
            "weight_kg": 72,
            "workouts_per_week": 3,
            "cardio_trainings_per_week": 4,
        },
        headers=client_headers,
    )
    assert client_update.status_code == 200

    coach_view = client.get("/api/v1/coach/clients", headers=coach_headers)
    assert coach_view.status_code == 200
    synced_client = next(row for row in coach_view.json() if row["id"] == client_user["id"])
    assert synced_client["full_name"] == "Клиент с анкетой"
    assert synced_client["goal"] == "fat_loss"
    assert synced_client["height_cm"] == 174
    assert synced_client["weight_kg"] == 72
    assert synced_client["workouts_per_week"] == 3
    assert synced_client["cardio_trainings_per_week"] == 4
    assert synced_client["birth_date"] == "1990-09-10"

    me_after_client_update = client.get("/api/v1/me", headers=client_headers).json()
    assert me_after_client_update["profile"]["full_name"] == "Клиент обновил себя"
    assert me_after_client_update["profile"]["estimated_max_heart_rate"] is not None
    assert len(me_after_client_update["profile"]["heart_rate_zones"]) == 5


def test_coach_can_assign_existing_template_to_own_client(client):
    coach_headers = auth(client, telegram_user_id=6120, is_coach=True)
    client_headers = auth(client, telegram_user_id=6121, is_coach=False)
    other_coach_headers = auth(client, telegram_user_id=6122, is_coach=True)
    client_user = client.get("/api/v1/me", headers=client_headers).json()
    accept_coach_invite(client, coach_headers, client_headers)
    alias = client.patch(
        f"/api/v1/coach/clients/{client_user['id']}/profile",
        json={"full_name": "Клиент в программах"},
        headers=coach_headers,
    )
    assert alias.status_code == 200

    catalog = client.get("/api/v1/programs/exercises", headers=coach_headers).json()
    exercise = next(item for item in catalog if item["metric_type"] == "strength")
    created = client.post(
        "/api/v1/programs/templates",
        json={
            "title": "Шаблон тренера",
            "goal": "maintenance",
            "level": "beginner",
            "mode": "self",
            "assign_after_create": False,
            "days": [
                {
                    "title": "День 1",
                    "exercises": [
                        {
                            "exercise_id": exercise["id"],
                            "prescribed_sets": 2,
                            "prescribed_reps": "10",
                            "rest_seconds": 60,
                        }
                    ],
                }
            ],
        },
        headers=coach_headers,
    )
    assert created.status_code == 200
    assert created.json()["template"]["days"][0]["exercises"][0]["has_guide"] is True
    template_id = created.json()["template"]["id"]
    assignment_start = today_msk() + timedelta(days=1)

    assigned = client.post(
        f"/api/v1/coach/clients/{client_user['id']}/templates/{template_id}/assign",
        json={"start_date": assignment_start.isoformat()},
        headers=coach_headers,
    )
    assert assigned.status_code == 200
    assert assigned.json()["workouts_created"] == 1
    with get_session_context() as db:
        assignment_notice = (
            db.query(Notification)
            .filter(
                Notification.dedupe_key
                == f"program_assignment:{assigned.json()['user_program_id']}"
            )
            .one()
        )
        assert assignment_notice.user_id == client_user["id"]
        assert assignment_notice.status == "queued"
        assert "Шаблон тренера" in assignment_notice.body
    assert client.get("/api/v1/workouts/week", headers=client_headers).status_code == 200

    client_templates = client.get("/api/v1/programs/templates/mine", headers=client_headers).json()
    assigned_template = next(item for item in client_templates if item["id"] == template_id)
    assert assigned_template["is_assigned_to_current_user"] is True
    assert assigned_template["is_active_for_current_user"] is True
    assert assigned_template["assigned_by_user_id"] == created.json()["template"]["owner_user_id"]
    assert assigned_template["can_edit"] is False

    coach_programs = client.get("/api/v1/coach/assigned-programs", headers=coach_headers)
    assert coach_programs.status_code == 200
    assert coach_programs.json() == [
        {
            "id": assigned.json()["user_program_id"],
            "client_id": client_user["id"],
            "client_telegram_user_id": 6121,
            "client_username": client_user["username"],
            "client_full_name": "Клиент в программах",
            "template_id": template_id,
            "title": "Шаблон тренера",
            "goal": "maintenance",
            "level": "beginner",
            "assigned_at": coach_programs.json()[0]["assigned_at"],
            "is_active": True,
            "status": "scheduled",
            "start_date": assignment_start.isoformat(),
            "duration_weeks": 1,
            "schedule_weekdays": [assignment_start.weekday()],
            "completed_at": None,
            "workouts_total": 1,
            "workouts_completed": 0,
            "workouts_planned": 1,
            "next_workout_date": coach_programs.json()[0]["next_workout_date"],
            "current_revision_number": 1,
        }
    ]

    second_exercise = client.get("/api/v1/programs/exercises", headers=coach_headers).json()[1]
    exercise_assignment = client.post(
        f"/api/v1/coach/clients/{client_user['id']}/programs/"
        f"{assigned.json()['user_program_id']}/exercises",
        json={
            "expected_revision_number": 1,
            "exercise_id": second_exercise["id"],
            "day_number": 1,
            "prescribed_sets": 4,
            "prescribed_reps": "12",
            "rest_seconds": 75,
        },
        headers=coach_headers,
    )
    assert exercise_assignment.status_code == 200
    assert exercise_assignment.json() == {
        "workouts_updated": 1,
        "current_revision_number": 2,
    }
    with get_session_context() as db:
        added = (
            db.query(UserWorkoutExercise)
            .join(UserWorkout)
            .filter(
                UserWorkout.user_program_id == assigned.json()["user_program_id"],
                UserWorkoutExercise.exercise_id == second_exercise["id"],
            )
            .one()
        )
        assert added.prescribed_sets == 4
        assert added.prescribed_reps == "12"
        assert added.rest_seconds == 75
        assert (
            db.query(UserWorkoutSet).filter(UserWorkoutSet.workout_exercise_id == added.id).count()
            == 4
        )

    workout_id = client.get("/api/v1/workouts/schedule", headers=client_headers).json()[0]["id"]
    client_date = assignment_start + timedelta(days=1)
    client_rescheduled = client.patch(
        f"/api/v1/workouts/{workout_id}/schedule",
        json={"scheduled_date": client_date.isoformat(), "scheduled_time": "18:30"},
        headers=client_headers,
    )
    assert client_rescheduled.status_code == 200
    assert client_rescheduled.json()["scheduled_time"] == "18:30:00"

    coach_date = assignment_start + timedelta(days=2)
    coach_rescheduled = client.patch(
        f"/api/v1/coach/clients/{client_user['id']}/workouts/{workout_id}/schedule",
        json={"scheduled_date": coach_date.isoformat(), "scheduled_time": "19:00"},
        headers=coach_headers,
    )
    assert coach_rescheduled.status_code == 200
    assert coach_rescheduled.json()["scheduled_time"] == "19:00:00"
    with get_session_context() as db:
        client_change_notice = (
            db.query(Notification)
            .filter(
                Notification.title == "Клиент изменил тренировку",
                Notification.user_id == created.json()["template"]["owner_user_id"],
            )
            .one()
        )
        assert "18:30" in client_change_notice.body
        trainer_change_notice = (
            db.query(Notification)
            .filter(
                Notification.title == "Тренер изменил тренировку",
                Notification.user_id == client_user["id"],
            )
            .one()
        )
        assert "19:00" in trainer_change_notice.body

    assert client.get("/api/v1/coach/assigned-programs", headers=other_coach_headers).json() == []


def test_coach_cannot_assign_kbju_to_non_client(client):
    coach_headers = auth(client, telegram_user_id=6201, is_coach=True)
    auth(client, telegram_user_id=6202, is_coach=False)

    response = client.post(
        "/api/v1/nutrition/targets",
        json={
            "target_telegram_user_id": 6202,
            "sex": "male",
            "weight_kg": 90,
            "height_cm": 185,
            "age": 35,
            "strength_trainings_per_week": 3,
            "cardio_trainings_per_week": 1,
            "goal": "maintenance",
        },
        headers=coach_headers,
    )

    assert response.status_code == 403


def test_admin_cannot_assign_kbju_to_unrelated_user(client):
    admin_headers = auth(client, telegram_user_id=6301, is_coach=True, is_admin=True)
    auth(client, telegram_user_id=6302, is_coach=False)

    response = client.post(
        "/api/v1/nutrition/targets",
        json={
            "target_telegram_user_id": 6302,
            "sex": "male",
            "weight_kg": 77,
            "height_cm": 176,
            "age": 32,
            "strength_trainings_per_week": 4,
            "cardio_trainings_per_week": 0,
            "goal": "recomposition",
        },
        headers=admin_headers,
    )

    assert response.status_code == 403


def test_telegram_login_bootstraps_admin_from_env(client, monkeypatch):
    from fitminiapp_api.core.config import settings

    monkeypatch.setattr(settings, "admin_telegram_user_ids", "555001")
    init_data = signed_init_data(
        bot_token="test-token",
        auth_date=int(time.time()),
        telegram_user_id=555001,
    )

    login = client.post("/api/v1/auth/telegram/init", json={"init_data": init_data})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.get("/api/v1/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["is_admin"] is True


def test_create_program_and_today_workout(client):
    headers = auth(client, telegram_user_id=2001, is_coach=False)
    exercises = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=headers).json()
        if item["metric_type"] == "strength"
    ]
    payload = {
        "title": "Тестовая программа",
        "goal": "recomposition",
        "level": "intermediate",
        "mode": "self",
        "assign_after_create": True,
        "days": [
            {
                "title": "День 1",
                "exercises": [
                    {
                        "exercise_id": exercises[0]["id"],
                        "prescribed_sets": 3,
                        "prescribed_reps": "8-10",
                        "rest_seconds": 90,
                    }
                ],
            }
        ],
    }
    create_res = client.post("/api/v1/programs/templates", json=payload, headers=headers)
    assert create_res.status_code == 200
    today = client.get("/api/v1/workouts/today", headers=headers)
    assert today.status_code == 200
    assert today.json()["title"] == "День 1"


def test_assign_template_to_self_uses_selected_start_date(client):
    headers = auth(client, telegram_user_id=2002, is_coach=False)
    exercises = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=headers).json()
        if item["metric_type"] == "strength"
    ]
    payload = {
        "title": "Программа с выбранной датой",
        "goal": "recomposition",
        "level": "intermediate",
        "mode": "self",
        "assign_after_create": False,
        "days": [
            {
                "title": title,
                "exercises": [
                    {
                        "exercise_id": exercises[0]["id"],
                        "prescribed_sets": 1,
                        "prescribed_reps": "8",
                        "rest_seconds": 90,
                    }
                ],
            }
            for title in ("День 1", "День 2")
        ],
    }
    created = client.post("/api/v1/programs/templates", json=payload, headers=headers)
    assert created.status_code == 200
    template_id = created.json()["template"]["id"]

    start_date = date.today() + timedelta(days=1)
    assigned = client.post(
        f"/api/v1/programs/templates/{template_id}/assign-to-me",
        json={"start_date": start_date.isoformat()},
        headers=headers,
    )
    assert assigned.status_code == 200
    assert assigned.json()["workouts_created"] == 2

    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 2002).one()
        program = (
            db.query(UserProgram)
            .filter(UserProgram.user_id == user.id, UserProgram.is_active.is_(True))
            .one()
        )
        scheduled_dates = [
            str(row.scheduled_date)
            for row in (
                db.query(UserWorkout)
                .filter(UserWorkout.user_program_id == program.id)
                .order_by(UserWorkout.scheduled_date.asc())
                .all()
            )
        ]

    assert scheduled_dates == [
        start_date.isoformat(),
        (start_date + timedelta(days=1)).isoformat(),
    ]


def test_week_schedule_returns_current_active_program(client):
    headers = auth(client, telegram_user_id=2003, is_coach=False)
    exercises = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=headers).json()
        if item["metric_type"] == "strength"
    ]
    payload = {
        "title": "Недельная программа",
        "goal": "recomposition",
        "level": "beginner",
        "mode": "self",
        "assign_after_create": True,
        "days": [
            {
                "title": "Тренировка недели",
                "exercises": [
                    {
                        "exercise_id": exercises[0]["id"],
                        "prescribed_sets": 1,
                        "prescribed_reps": "10",
                        "rest_seconds": 60,
                    }
                ],
            }
        ],
    }
    created = client.post("/api/v1/programs/templates", json=payload, headers=headers)
    assert created.status_code == 200

    response = client.get("/api/v1/workouts/week", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Тренировка недели"
    assert response.json()[0]["status"] == "planned"


def test_user_can_clear_completed_workout_history(client):
    headers = auth(client, telegram_user_id=6401, is_coach=False)
    exercises = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=headers).json()
        if item["metric_type"] == "strength"
    ]
    payload = {
        "title": "Программа для очистки истории",
        "goal": "recomposition",
        "level": "intermediate",
        "mode": "self",
        "assign_after_create": True,
        "days": [
            {
                "title": "День 1",
                "exercises": [
                    {
                        "exercise_id": exercises[0]["id"],
                        "prescribed_sets": 1,
                        "prescribed_reps": "8",
                        "rest_seconds": 90,
                    }
                ],
            }
        ],
    }
    created = client.post("/api/v1/programs/templates", json=payload, headers=headers)
    assert created.status_code == 200

    assert client.get("/api/v1/workouts/history", headers=headers).json() == []
    today = client.get("/api/v1/workouts/today", headers=headers).json()
    started = client.post(f"/api/v1/workouts/{today['id']}/start", headers=headers)
    assert started.status_code == 200
    set_id = today["exercises"][0]["sets"][0]["id"]
    saved = client.patch(
        f"/api/v1/workouts/sets/{set_id}",
        json={"actual_reps": 8, "actual_weight": 20, "is_completed": True},
        headers=headers,
    )
    assert saved.status_code == 200
    finished = client.post(f"/api/v1/workouts/{today['id']}/finish", headers=headers)
    assert finished.status_code == 200

    history = client.get("/api/v1/workouts/history", headers=headers)
    assert history.status_code == 200
    assert len(history.json()) == 1

    cleared = client.delete("/api/v1/workouts/history", headers=headers)
    assert cleared.status_code == 204
    assert client.get("/api/v1/workouts/history", headers=headers).json() == []
    assert client.get("/api/v1/workouts/today", headers=headers).status_code == 404


def test_client_can_save_update_and_delete_body_measurement(client):
    headers = auth(client, telegram_user_id=6402, is_coach=False)

    created = client.post(
        "/api/v1/workouts/diary",
        json={
            "measured_on": "2026-05-01",
            "weight_kg": 74.5,
            "waist_cm": 82.0,
            "note": "утро",
        },
        headers=headers,
    )

    assert created.status_code == 200
    data = created.json()
    assert data["weight_kg"] == 74.5
    assert data["waist_cm"] == 82.0

    updated = client.post(
        "/api/v1/workouts/diary",
        json={
            "measured_on": "2026-05-01",
            "weight_kg": 74.0,
            "chest_cm": 98.5,
        },
        headers=headers,
    )

    assert updated.status_code == 200
    assert updated.json()["id"] == data["id"]
    assert updated.json()["weight_kg"] == 74.0
    assert updated.json()["waist_cm"] == 82.0
    assert updated.json()["chest_cm"] == 98.5

    newer = client.post(
        "/api/v1/workouts/diary",
        json={"measured_on": "2026-05-03", "weight_kg": 73.8},
        headers=headers,
    )
    assert newer.status_code == 200

    rows = client.get("/api/v1/workouts/diary", headers=headers)
    assert rows.status_code == 200
    assert [row["measured_on"] for row in rows.json()] == ["2026-05-03", "2026-05-01"]

    deleted = client.delete(f"/api/v1/workouts/diary/{data['id']}", headers=headers)

    assert deleted.status_code == 204
    deleted_newer = client.delete(f"/api/v1/workouts/diary/{newer.json()['id']}", headers=headers)
    assert deleted_newer.status_code == 204
    assert client.get("/api/v1/workouts/diary", headers=headers).json() == []


def test_workout_set_patch(client):
    headers = auth(client, telegram_user_id=2001, is_coach=False)
    exercises = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=headers).json()
        if item["metric_type"] == "strength"
    ]
    payload = {
        "title": "Программа для валидации сетов",
        "goal": "recomposition",
        "level": "intermediate",
        "mode": "self",
        "assign_after_create": True,
        "days": [
            {
                "title": "День 1",
                "exercises": [
                    {
                        "exercise_id": exercises[0]["id"],
                        "prescribed_sets": 3,
                        "prescribed_reps": "8-10",
                        "rest_seconds": 90,
                    }
                ],
            }
        ],
    }
    create_res = client.post("/api/v1/programs/templates", json=payload, headers=headers)
    assert create_res.status_code == 200
    today = client.get("/api/v1/workouts/today", headers=headers).json()
    exercise = today["exercises"][0]
    set_id = exercise["sets"][0]["id"]
    started = client.post(f"/api/v1/workouts/{today['id']}/start", headers=headers)
    assert started.status_code == 200

    unknown = client.patch(
        "/api/v1/workouts/sets/999999",
        json={"actual_reps": 8, "actual_weight": 80, "is_completed": True},
        headers=headers,
    )
    assert unknown.status_code == 404

    ok = client.patch(
        f"/api/v1/workouts/sets/{set_id}",
        json={"actual_reps": 8, "actual_weight": 80, "is_completed": True},
        headers=headers,
    )
    assert ok.status_code == 200


def test_workout_set_validation(client):
    headers = auth(client, telegram_user_id=2001, is_coach=False)
    exercises = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=headers).json()
        if item["metric_type"] == "strength"
    ]
    payload = {
        "title": "Программа для проверки валидации",
        "goal": "recomposition",
        "level": "intermediate",
        "mode": "self",
        "assign_after_create": True,
        "days": [
            {
                "title": "День 1",
                "exercises": [
                    {
                        "exercise_id": exercises[0]["id"],
                        "prescribed_sets": 1,
                        "prescribed_reps": "8-10",
                        "rest_seconds": 90,
                    }
                ],
            }
        ],
    }
    create_res = client.post("/api/v1/programs/templates", json=payload, headers=headers)
    assert create_res.status_code == 200
    today = client.get("/api/v1/workouts/today", headers=headers).json()
    set_id = today["exercises"][0]["sets"][0]["id"]
    started = client.post(f"/api/v1/workouts/{today['id']}/start", headers=headers)
    assert started.status_code == 200

    invalid = client.patch(
        f"/api/v1/workouts/sets/{set_id}",
        json={"actual_reps": -5},
        headers=headers,
    )
    assert invalid.status_code == 422

    ok = client.patch(
        f"/api/v1/workouts/sets/{set_id}",
        json={"is_completed": "false"},
        headers=headers,
    )
    assert ok.status_code == 200
    assert ok.json()["is_completed"] is False


def test_client_cannot_assign_program_as_coach(client):
    headers = auth(client, telegram_user_id=3001, is_coach=False)
    exercises = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=headers).json()
        if item["metric_type"] == "strength"
    ]
    payload = {
        "title": "Чужая программа",
        "goal": "recomposition",
        "level": "intermediate",
        "mode": "coach",
        "target_telegram_user_id": 3999,
        "target_full_name": "Target",
        "assign_after_create": True,
        "days": [
            {
                "title": "День 1",
                "exercises": [
                    {
                        "exercise_id": exercises[0]["id"],
                        "prescribed_sets": 1,
                        "prescribed_reps": "8",
                        "rest_seconds": 90,
                    }
                ],
            }
        ],
    }

    response = client.post("/api/v1/programs/templates", json=payload, headers=headers)
    assert response.status_code == 400


def test_client_target_fields_do_not_assign_program_to_another_user(client):
    target_headers = auth(client, telegram_user_id=3998, is_coach=False)
    headers = auth(client, telegram_user_id=3002, is_coach=False)
    exercises = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=headers).json()
        if item["metric_type"] == "strength"
    ]
    payload = {
        "title": "Программа только для себя",
        "goal": "recomposition",
        "level": "intermediate",
        "mode": "self",
        "target_telegram_user_id": 3998,
        "target_full_name": "Чужой клиент",
        "assign_after_create": True,
        "days": [
            {
                "title": "День 1",
                "exercises": [
                    {
                        "exercise_id": exercises[0]["id"],
                        "prescribed_sets": 1,
                        "prescribed_reps": "8",
                        "rest_seconds": 90,
                    }
                ],
            }
        ],
    }

    response = client.post("/api/v1/programs/templates", json=payload, headers=headers)

    assert response.status_code == 200
    assert response.json()["target_user"]["telegram_user_id"] == 3002
    assert client.get("/api/v1/workouts/today", headers=headers).status_code == 200
    assert client.get("/api/v1/workouts/today", headers=target_headers).status_code == 404


def test_client_custom_exercise_is_private(client):
    owner_headers = auth(client, telegram_user_id=3101, is_coach=False)
    other_headers = auth(client, telegram_user_id=3102, is_coach=False)
    coach_headers = auth(client, telegram_user_id=1101, is_coach=True)
    title = "Private Client Raise"

    created = client.post(
        "/api/v1/programs/exercises",
        json={"title": title, "primary_muscle": "shoulders", "equipment": "dumbbell"},
        headers=owner_headers,
    )

    assert created.status_code == 201
    assert created.json()["is_custom"] is True
    assert created.json()["is_personalized"] is True

    owner_titles = {
        item["title"]
        for item in client.get("/api/v1/programs/exercises", headers=owner_headers).json()
    }
    other_titles = {
        item["title"]
        for item in client.get("/api/v1/programs/exercises", headers=other_headers).json()
    }
    coach_titles = {
        item["title"]
        for item in client.get("/api/v1/programs/exercises", headers=coach_headers).json()
    }

    assert title in owner_titles
    assert title not in other_titles
    assert title not in coach_titles

    coach_edit = client.patch(
        f"/api/v1/programs/exercises/{created.json()['edit_target_id']}",
        json={"title": "Coach Hijack", "primary_muscle": "back", "equipment": "barbell"},
        headers=coach_headers,
    )
    assert coach_edit.status_code == 403


def test_only_configured_root_custom_exercise_is_global(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "1102")
    admin_headers = auth(client, telegram_user_id=1102, is_coach=True, is_admin=True)
    client_headers = auth(client, telegram_user_id=3103, is_coach=False)
    coach_headers = auth(client, telegram_user_id=1103, is_coach=True)
    title = "Global Admin Press"

    created = client.post(
        "/api/v1/programs/exercises",
        json={"title": title, "primary_muscle": "chest", "equipment": "barbell"},
        headers=admin_headers,
    )

    assert created.status_code == 201
    assert created.json()["created_by_user_id"] is None
    assert created.json()["is_custom"] is False

    client_titles = {
        item["title"]
        for item in client.get("/api/v1/programs/exercises", headers=client_headers).json()
    }
    coach_titles = {
        item["title"]
        for item in client.get("/api/v1/programs/exercises", headers=coach_headers).json()
    }

    assert title in client_titles
    assert title in coach_titles


def test_custom_exercise_metadata_is_optional(client):
    headers = auth(client, telegram_user_id=31031, is_coach=False)

    created = client.post(
        "/api/v1/programs/exercises",
        json={"title": "Minimal Client Move"},
        headers=headers,
    )

    assert created.status_code == 201
    data = created.json()
    assert data["title"] == "Minimal Client Move"
    assert data["primary_muscle"] is None
    assert data["equipment"] is None
    assert data["difficulty_level"] == "intermediate"


def test_custom_exercise_can_be_marked_with_difficulty(client):
    headers = auth(client, telegram_user_id=31036, is_coach=False)

    created = client.post(
        "/api/v1/programs/exercises",
        json={"title": "Technical Client Move", "difficulty_level": "advanced"},
        headers=headers,
    )

    assert created.status_code == 201
    assert created.json()["difficulty_level"] == "advanced"

    invalid = client.post(
        "/api/v1/programs/exercises",
        json={"title": "Invalid Level Move", "difficulty_level": "expert"},
        headers=headers,
    )
    assert invalid.status_code == 422


def test_seeded_catalog_and_strength_templates(client):
    headers = auth(client, telegram_user_id=31032, is_coach=False)

    exercises = client.get("/api/v1/programs/exercises", headers=headers).json()
    templates = client.get("/api/v1/programs/templates/mine", headers=headers).json()

    assert len(exercises) >= 140
    assert {item["difficulty_level"] for item in exercises} == {
        "beginner",
        "intermediate",
        "advanced",
    }
    assert "upper-lower-4x" not in {item["slug"] for item in templates}
    assert {
        "strength-split-5d",
        "strength-push-pull-legs-6d",
        "strength-upper-lower-4d",
        "strength-fullbody-3d",
        "strength-pplf-4d",
        "strength-pplf-8d",
        "strength-pull-legs-push-legs-4d",
        "strength-pull-legs-push-legs-8d",
    }.issubset({item["slug"] for item in templates})
    pplf_templates = {item["slug"]: item for item in templates if "pplf" in item["slug"]}
    assert len(pplf_templates["strength-pplf-4d"]["days"]) == 4
    assert len(pplf_templates["strength-pplf-8d"]["days"]) == 8
    assigned = client.post(
        f"/api/v1/programs/templates/{pplf_templates['strength-pplf-8d']['id']}/assign-to-me",
        json={"start_date": (date.today() + timedelta(days=1)).isoformat()},
        headers=headers,
    )
    assert assigned.status_code == 200
    assert assigned.json()["workouts_created"] == 8
    pull_legs_templates = {
        item["slug"]: item for item in templates if "pull-legs-push-legs" in item["slug"]
    }
    assert [
        day["title"].split(" · ")[0]
        for day in pull_legs_templates["strength-pull-legs-push-legs-4d"]["days"]
    ] == ["Тяни", "Ноги A", "Толкай", "Ноги B"]
    assert len(pull_legs_templates["strength-pull-legs-push-legs-8d"]["days"]) == 8
    assert all(
        template["days"] for template in templates if template["slug"].startswith("strength-")
    )


def test_client_can_hide_and_restore_seeded_program_example(client):
    headers = auth(client, telegram_user_id=31034, is_coach=False)
    other_headers = auth(client, telegram_user_id=31035, is_coach=False)
    templates = client.get("/api/v1/programs/templates/mine", headers=headers).json()
    example = next(item for item in templates if item["slug"] == "strength-fullbody-3d")
    assert example["is_example"] is True

    hidden = client.delete(f"/api/v1/programs/templates/{example['id']}", headers=headers)
    assert hidden.status_code == 204
    assert example["id"] not in {
        item["id"] for item in client.get("/api/v1/programs/templates/mine", headers=headers).json()
    }
    assert example["id"] in {
        item["id"]
        for item in client.get("/api/v1/programs/templates/hidden", headers=headers).json()
    }
    assert example["id"] in {
        item["id"]
        for item in client.get("/api/v1/programs/templates/mine", headers=other_headers).json()
    }

    restored = client.post(f"/api/v1/programs/templates/{example['id']}/restore", headers=headers)
    assert restored.status_code == 204
    assert example["id"] in {
        item["id"] for item in client.get("/api/v1/programs/templates/mine", headers=headers).json()
    }
    assert client.get("/api/v1/programs/templates/hidden", headers=headers).json() == []


def test_every_seeded_template_can_be_customized_with_a_personal_exercise(client):
    headers = auth(client, telegram_user_id=31037, is_coach=False)
    custom_exercise = client.post(
        "/api/v1/programs/exercises",
        json={
            "title": "Моё упражнение для шаблона",
            "primary_muscle": "Все тело",
            "equipment": "Своё оборудование",
        },
        headers=headers,
    ).json()
    templates = client.get("/api/v1/programs/templates/mine", headers=headers).json()
    examples = [template for template in templates if template["is_example"]]

    assert examples
    for example in examples:
        days = [
            {
                "title": day["title"],
                "exercises": [
                    {
                        "exercise_id": (
                            custom_exercise["id"]
                            if day_index == 0 and exercise_index == 0
                            else exercise["exercise_id"]
                        ),
                        "prescribed_sets": exercise["prescribed_sets"],
                        "prescribed_reps": exercise["prescribed_reps"],
                        "rest_seconds": exercise["rest_seconds"],
                        "notes": exercise["notes"],
                    }
                    for exercise_index, exercise in enumerate(day["exercises"])
                ],
            }
            for day_index, day in enumerate(example["days"])
        ]
        response = client.post(
            "/api/v1/programs/templates",
            json={
                "title": f"{example['title']} — моя",
                "goal": example["goal"],
                "level": example["level"],
                "mode": "self",
                "assign_after_create": False,
                "schedule_weekdays": None,
                "days": days,
            },
            headers=headers,
        )

        assert response.status_code == 200, (example["slug"], response.text)
        personalized = response.json()["template"]
        assert personalized["is_example"] is False
        assert personalized["can_edit"] is True
        assert personalized["days"][0]["exercises"][0]["exercise_id"] == custom_exercise["id"]


def test_every_seeded_exercise_has_complete_guide_and_local_images(client):
    headers = auth(client, telegram_user_id=31033, is_coach=False)
    exercises = client.get("/api/v1/programs/exercises", headers=headers).json()
    standard_exercises = [item for item in exercises if not item["is_custom"]]
    static_dir = Path(__file__).resolve().parents[2] / "backend" / "assets"

    assert len(standard_exercises) == 182
    assert len(client.get("/api/v1/programs/exercises", headers=headers).content) < 130_000
    assert all(
        exercise["has_guide"] and exercise["guide"] is None for exercise in standard_exercises
    )

    sample = client.get(
        f"/api/v1/programs/exercises/{standard_exercises[0]['id']}/guide",
        headers=headers,
    )
    assert sample.status_code == 200
    assert len(sample.json()["images"]) == 2
    assert len(sample.json()["media"]) == 2
    assert [item["sort_order"] for item in sample.json()["media"]] == [0, 1]

    with get_session_context() as session:
        seeded_guides = [
            (row.slug, get_exercise_guide(row))
            for row in (
                session.query(Exercise)
                .filter(Exercise.created_by_user_id.is_(None), Exercise.is_deleted.is_(False))
                .all()
            )
        ]
    for slug, guide in seeded_guides:
        assert guide is not None, slug
        assert len(guide["technique_steps"]) >= 3
        assert guide["breathing"]
        assert len(guide["common_mistakes"]) >= 3
        assert guide["muscles"]
        assert guide["images"]
        assert guide["media"]
        for media in guide["media"]:
            assert media["type"] == "image"
            assert media["poster"] == media["url"]
            assert media["width"] > 0
            assert media["height"] > 0
            assert media["byte_size"] > 0
            assert media["source_name"] == guide["source_name"]
            assert media["source_license"] == guide["source_license"]
            asset = static_dir / media["url"].removeprefix("/static/")
            assert asset.is_file(), asset
            assert asset.stat().st_size == media["byte_size"]


def test_exercise_guide_assets_have_cache_headers_and_missing_asset_is_safe(client):
    asset = client.get("/static/exercise-guides/bench-press-start.jpg")

    assert asset.status_code == 200
    assert asset.headers["content-type"] == "image/jpeg"
    assert asset.headers["cache-control"] == (
        "public, max-age=2592000, stale-while-revalidate=86400"
    )
    assert asset.headers["etag"]

    missing = client.get("/static/exercise-guides/not-a-real-exercise-start.jpg")
    assert missing.status_code == 404


def test_cardio_exercises_have_specific_guides_and_generated_images(client):
    headers = auth(client, telegram_user_id=31036, is_coach=False)
    exercises = client.get("/api/v1/programs/exercises", headers=headers).json()
    expected_titles = {
        "Бег на улице",
        "Эллиптический тренажёр",
        "Велосипед",
        "Велотренажёр",
        "Ходьба",
        "Ходьба на дорожке",
        "Степпер / лестница",
        "Плавание",
        "Лыжный тренажёр",
    }
    cardio = [exercise for exercise in exercises if exercise["title"] in expected_titles]

    assert {exercise["title"] for exercise in cardio} == expected_titles
    for exercise in cardio:
        response = client.get(
            f"/api/v1/programs/exercises/{exercise['id']}/guide",
            headers=headers,
        )
        assert response.status_code == 200
        guide = response.json()
        assert len(guide["technique_steps"]) >= 3
        assert guide["source_name"] == "Your Fitness Coach"
        assert guide["images"][0]["phase"] == "Техника движения"
        assert guide["media"][0]["source_license"] == "Иллюстрация создана для приложения"


def test_custom_exercise_has_no_incorrect_stock_guide(client):
    headers = auth(client, telegram_user_id=31034, is_coach=False)
    created = client.post(
        "/api/v1/programs/exercises",
        json={"title": "Авторское движение", "primary_muscle": "Кор"},
        headers=headers,
    )

    assert created.status_code == 201
    assert created.json()["guide"] is None
    assert created.json()["has_guide"] is False


def test_seed_refreshes_catalog_exercises_for_templates(client):
    with get_session_context() as session:
        bench = session.query(Exercise).filter(Exercise.slug == "bench-press").one()
        bench.is_deleted = True
        session.add(
            Exercise(
                slug="legacy-global-only",
                title="Legacy Global Only",
                primary_muscle="old",
                equipment="old",
                created_by_user_id=None,
                source_exercise_id=None,
                is_deleted=False,
            )
        )
        session.flush()
        seed_demo_data(session, include_demo_users=False)

        refreshed_bench = session.query(Exercise).filter(Exercise.slug == "bench-press").one()
        obsolete = session.query(Exercise).filter(Exercise.slug == "legacy-global-only").one()

        assert refreshed_bench.is_deleted is False
        assert obsolete.is_deleted is True


def test_coach_can_manage_own_client_exercise(client):
    coach_headers = auth(client, telegram_user_id=1107, is_coach=True)
    client_headers = auth(client, telegram_user_id=3109, is_coach=False)
    other_headers = auth(client, telegram_user_id=3110, is_coach=False)
    client_user = client.get("/api/v1/me", headers=client_headers).json()

    accept_coach_invite(client, coach_headers, client_headers)

    created = client.post(
        "/api/v1/programs/exercises",
        json={
            "title": "Client Managed Row",
            "primary_muscle": "back",
            "equipment": "cable",
            "target_telegram_user_id": 3109,
        },
        headers=coach_headers,
    )
    assert created.status_code == 201
    assert created.json()["created_by_user_id"] == client_user["id"]

    client_titles = {
        item["title"]
        for item in client.get("/api/v1/programs/exercises", headers=client_headers).json()
    }
    coach_titles = {
        item["title"]
        for item in client.get("/api/v1/programs/exercises", headers=coach_headers).json()
    }
    other_titles = {
        item["title"]
        for item in client.get("/api/v1/programs/exercises", headers=other_headers).json()
    }
    assert "Client Managed Row" in client_titles
    assert "Client Managed Row" in coach_titles
    assert "Client Managed Row" not in other_titles

    updated = client.patch(
        f"/api/v1/programs/exercises/{created.json()['edit_target_id']}",
        json={"title": "Client Managed Updated", "primary_muscle": "back", "equipment": "cable"},
        headers=coach_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Client Managed Updated"

    deleted = client.delete(
        f"/api/v1/programs/exercises/{created.json()['edit_target_id']}",
        headers=coach_headers,
    )
    assert deleted.status_code == 204
    client_titles_after_delete = {
        item["title"]
        for item in client.get("/api/v1/programs/exercises", headers=client_headers).json()
    }
    assert "Client Managed Updated" not in client_titles_after_delete


def test_coach_cannot_create_exercise_for_non_client(client):
    coach_headers = auth(client, telegram_user_id=1108, is_coach=True)
    auth(client, telegram_user_id=3111, is_coach=False)

    created = client.post(
        "/api/v1/programs/exercises",
        json={
            "title": "Non Client Row",
            "primary_muscle": "legs",
            "equipment": "machine",
            "target_telegram_user_id": 3111,
        },
        headers=coach_headers,
    )

    assert created.status_code == 403


def test_client_template_is_private(client):
    owner_headers = auth(client, telegram_user_id=3104, is_coach=False)
    other_headers = auth(client, telegram_user_id=3105, is_coach=False)
    exercises = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=owner_headers).json()
        if item["metric_type"] == "strength"
    ]
    title = "Private Client Template"
    payload = {
        "title": title,
        "goal": "recomposition",
        "level": "intermediate",
        "mode": "self",
        "assign_after_create": False,
        "days": [
            {
                "title": "День 1",
                "exercises": [
                    {
                        "exercise_id": exercises[0]["id"],
                        "prescribed_sets": 1,
                        "prescribed_reps": "8",
                        "rest_seconds": 90,
                    }
                ],
            }
        ],
    }

    created = client.post("/api/v1/programs/templates", json=payload, headers=owner_headers)

    assert created.status_code == 200
    assert created.json()["template"]["is_public"] is False

    owner_titles = {
        item["title"]
        for item in client.get("/api/v1/programs/templates/mine", headers=owner_headers).json()
    }
    other_titles = {
        item["title"]
        for item in client.get("/api/v1/programs/templates/mine", headers=other_headers).json()
    }

    assert title in owner_titles
    assert title not in other_titles


def test_only_configured_root_template_is_public(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "1104")
    admin_headers = auth(client, telegram_user_id=1104, is_coach=True, is_admin=True)
    client_headers = auth(client, telegram_user_id=3106, is_coach=False)
    coach_headers = auth(client, telegram_user_id=1105, is_coach=True)
    exercises = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=admin_headers).json()
        if item["metric_type"] == "strength"
    ]
    title = "Global Admin Template"
    payload = {
        "title": title,
        "goal": "recomposition",
        "level": "intermediate",
        "mode": "self",
        "assign_after_create": False,
        "days": [
            {
                "title": "День 1",
                "exercises": [
                    {
                        "exercise_id": exercises[0]["id"],
                        "prescribed_sets": 1,
                        "prescribed_reps": "8",
                        "rest_seconds": 90,
                    }
                ],
            }
        ],
    }

    created = client.post("/api/v1/programs/templates", json=payload, headers=admin_headers)

    assert created.status_code == 200
    assert created.json()["template"]["is_public"] is True

    client_titles = {
        item["title"]
        for item in client.get("/api/v1/programs/templates/mine", headers=client_headers).json()
    }
    coach_titles = {
        item["title"]
        for item in client.get("/api/v1/programs/templates/mine", headers=coach_headers).json()
    }

    assert title in client_titles
    assert title in coach_titles


def test_coach_can_manage_program_for_own_client(client):
    coach_headers = auth(client, telegram_user_id=1109, is_coach=True)
    client_headers = auth(client, telegram_user_id=3112, is_coach=False)
    other_coach_headers = auth(client, telegram_user_id=1110, is_coach=True)
    client_user = client.get("/api/v1/me", headers=client_headers).json()

    accept_coach_invite(client, coach_headers, client_headers)

    exercises = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=client_headers).json()
        if item["metric_type"] == "strength"
    ]
    payload = {
        "title": "Client Managed Program",
        "goal": "recomposition",
        "level": "intermediate",
        "mode": "coach",
        "target_telegram_user_id": 3112,
        "target_full_name": "Клиент программы",
        "assign_after_create": False,
        "days": [
            {
                "title": "День 1",
                "exercises": [
                    {
                        "exercise_id": exercises[0]["id"],
                        "prescribed_sets": 1,
                        "prescribed_reps": "8",
                        "rest_seconds": 90,
                    }
                ],
            }
        ],
    }

    created = client.post("/api/v1/programs/templates", json=payload, headers=coach_headers)
    assert created.status_code == 200
    assert created.json()["template"]["owner_user_id"] == client_user["id"]
    template_id = created.json()["template"]["id"]

    client_titles = {
        item["title"]
        for item in client.get("/api/v1/programs/templates/mine", headers=client_headers).json()
    }
    coach_titles = {
        item["title"]
        for item in client.get("/api/v1/programs/templates/mine", headers=coach_headers).json()
    }
    other_coach_titles = {
        item["title"]
        for item in client.get(
            "/api/v1/programs/templates/mine", headers=other_coach_headers
        ).json()
    }
    assert "Client Managed Program" in client_titles
    assert "Client Managed Program" in coach_titles
    assert "Client Managed Program" not in other_coach_titles

    payload["title"] = "Client Managed Program Updated"
    updated = client.patch(
        f"/api/v1/programs/templates/{template_id}",
        json=payload,
        headers=coach_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Client Managed Program Updated"
    assert updated.json()["can_edit"] is True
    with get_session_context() as db:
        update_notice = (
            db.query(Notification)
            .filter(
                Notification.user_id == client_user["id"],
                Notification.title == "Программа тренировок изменена",
            )
            .one()
        )
        assert "Client Managed Program Updated" in update_notice.body

    blocked_delete = client.delete(
        f"/api/v1/programs/templates/{template_id}",
        headers=other_coach_headers,
    )
    assert blocked_delete.status_code == 403

    deleted = client.delete(f"/api/v1/programs/templates/{template_id}", headers=coach_headers)
    assert deleted.status_code == 204
    assert (
        client.get(f"/api/v1/programs/templates/{template_id}", headers=client_headers).status_code
        == 404
    )


def test_coach_cannot_create_program_for_non_client(client):
    coach_headers = auth(client, telegram_user_id=1111, is_coach=True)
    target_headers = auth(client, telegram_user_id=3113, is_coach=False)
    exercises = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=target_headers).json()
        if item["metric_type"] == "strength"
    ]
    payload = {
        "title": "Forbidden Client Program",
        "goal": "recomposition",
        "level": "intermediate",
        "mode": "coach",
        "target_telegram_user_id": 3113,
        "target_full_name": "Не клиент",
        "assign_after_create": False,
        "days": [
            {
                "title": "День 1",
                "exercises": [
                    {
                        "exercise_id": exercises[0]["id"],
                        "prescribed_sets": 1,
                        "prescribed_reps": "8",
                        "rest_seconds": 90,
                    }
                ],
            }
        ],
    }

    created = client.post("/api/v1/programs/templates", json=payload, headers=coach_headers)

    assert created.status_code == 403


def test_removed_user_delete_route_preserves_private_exercises(client):
    admin_headers = auth(client, telegram_user_id=1106, is_coach=True, is_admin=True)
    user_headers = auth(client, telegram_user_id=3107, is_coach=False)
    other_headers = auth(client, telegram_user_id=3108, is_coach=False)
    user = client.get("/api/v1/me", headers=user_headers).json()
    title = "Deleted User Private Exercise"

    created = client.post(
        "/api/v1/programs/exercises",
        json={"title": title, "primary_muscle": "legs", "equipment": "machine"},
        headers=user_headers,
    )
    assert created.status_code == 201

    deleted = client.delete(f"/api/v1/admin/users/{user['id']}", headers=admin_headers)

    assert deleted.status_code == 405
    other_titles = {
        item["title"]
        for item in client.get("/api/v1/programs/exercises", headers=other_headers).json()
    }
    assert title not in other_titles


def test_coach_can_link_client_with_secure_invite(client):
    headers = auth(client, telegram_user_id=1002, is_coach=True)
    client_headers = auth(client, telegram_user_id=2001, is_coach=False)

    accept_coach_invite(client, headers, client_headers)

    listed = client.get("/api/v1/programs/clients", headers=headers)
    assert listed.status_code == 200
    assert any(row["telegram_user_id"] == 2001 for row in listed.json())


def test_client_approves_coach_change_and_has_only_one_active_coach(client):
    coach_one_headers = auth(
        client,
        telegram_user_id=1201,
        is_coach=True,
        username="@coach_one",
        full_name="Тренер Первый",
    )
    coach_two_headers = auth(
        client,
        telegram_user_id=1202,
        is_coach=True,
        username="@coach_two",
        full_name="Тренер Второй",
    )
    client_headers = auth(client, telegram_user_id=5201, is_coach=False)
    client_user = client.get("/api/v1/me", headers=client_headers).json()

    assert client.get("/api/v1/me", headers=client_headers).json()["trainer"] is None
    _, first_preview = accept_coach_invite(client, coach_one_headers, client_headers)
    assert first_preview["requires_trainer_change"] is False

    trainer = client.get("/api/v1/me", headers=client_headers).json()["trainer"]
    assert trainer["username"] == "coach_one"
    assert trainer["full_name"] == "Тренер Первый"
    assert trainer["chat_url"] == "https://t.me/coach_one"
    assert trainer["can_open_chat"] is True

    trainer_before_accept = client.get("/api/v1/me", headers=client_headers).json()["trainer"]
    assert trainer_before_accept["username"] == "coach_one"
    _, second_preview = accept_coach_invite(client, coach_two_headers, client_headers)
    assert second_preview["requires_trainer_change"] is True
    assert second_preview["current_trainer"]["username"] == "coach_one"

    first_clients = client.get("/api/v1/coach/clients", headers=coach_one_headers).json()
    second_clients = client.get("/api/v1/coach/clients", headers=coach_two_headers).json()
    assert not any(row["id"] == client_user["id"] for row in first_clients)
    assert any(row["id"] == client_user["id"] for row in second_clients)
    assert (
        client.get("/api/v1/me", headers=client_headers).json()["trainer"]["username"]
        == "coach_two"
    )

    with get_session_context() as db:
        relations = (
            db.query(CoachClient)
            .filter(CoachClient.client_user_id == client_user["id"])
            .order_by(CoachClient.id)
            .all()
        )
        assert [relation.status for relation in relations] == ["ended", "active"]
        assert relations[0].ended_at is not None
        assert relations[0].ended_reason == "client_switched_trainer"


def test_legacy_client_code_flow_is_not_public(client):
    coach_headers = auth(client, telegram_user_id=1220, is_coach=True)
    client_headers = auth(client, telegram_user_id=5220, is_coach=False)
    me = client.get("/api/v1/me", headers=client_headers).json()
    assert "client_code" not in me

    requested = client.post(
        "/api/v1/coach/clients",
        json={"client_code": "ABCD-234", "source": "client_code"},
        headers=coach_headers,
    )
    assert requested.status_code == 405
    assert client.get("/api/v1/me/client-code/qr", headers=client_headers).status_code == 404
    assert client.post("/api/v1/me/client-code/rotate", headers=client_headers).status_code == 404


def test_invite_link_preview_is_nonmutating_and_confirm_is_one_time(client):
    coach_headers = auth(client, telegram_user_id=1230, is_coach=True)
    first_client_headers = auth(client, telegram_user_id=5230, is_coach=False)
    other_client_headers = auth(client, telegram_user_id=5231, is_coach=False)
    first_user_id = client.get("/api/v1/me", headers=first_client_headers).json()["id"]

    created = client.post("/api/v1/coach/invite-links", headers=coach_headers)
    assert created.status_code == 201
    start_param = created.json()["start_param"]
    assert start_param.startswith("trainer_")
    token = start_param.removeprefix("trainer_")
    assert created.json()["code"] == token
    assert created.json()["web_url"] == f"https://app.your-fitness-coach.ru/join/{token}"
    assert created.json()["telegram_url"] == created.json()["url"]
    invite_page = client.get(f"/join/{token}")
    assert invite_page.status_code == 200
    assert '<div id="root"></div>' in invite_page.text
    invite_id = created.json()["invite_id"]

    for _ in range(2):
        preview = client.post(
            "/api/v1/me/coach-invites/link/preview",
            json={"token": token},
            headers=first_client_headers,
        )
        assert preview.status_code == 200
        assert preview.json()["invite_id"] == invite_id

    assert client.get("/api/v1/me/coach-invites", headers=first_client_headers).status_code == 404
    with get_session_context() as db:
        invite = db.query(CoachClientInvite).filter(CoachClientInvite.id == invite_id).one()
        assert invite.status == "pending"
        assert invite.client_user_id is None
        assert invite.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert token not in invite.token_hash

    accepted = client.post(
        "/api/v1/me/coach-invites/link/confirm",
        json={"token": token},
        headers=first_client_headers,
    )
    assert accepted.status_code == 204
    repeated = client.post(
        "/api/v1/me/coach-invites/link/confirm",
        json={"token": token},
        headers=first_client_headers,
    )
    assert repeated.status_code == 409
    stolen_after_use = client.post(
        "/api/v1/me/coach-invites/link/confirm",
        json={"token": token},
        headers=other_client_headers,
    )
    assert stolen_after_use.status_code == 409

    relogged_headers = auth(client, telegram_user_id=5230, is_coach=False)
    assert client.get("/api/v1/me", headers=relogged_headers).json()["id"] == first_user_id
    with get_session_context() as db:
        assert db.query(User).filter(User.telegram_user_id == 5230).count() == 1
        assert (
            db.query(CoachClient)
            .filter(
                CoachClient.client_user_id == first_user_id,
                CoachClient.status == "active",
            )
            .count()
            == 1
        )
        assert (
            db.query(CoachClientInvite).filter(CoachClientInvite.id == invite_id).one().status
            == "accepted"
        )


def test_legacy_username_client_lookup_is_not_public(client):
    coach_headers = auth(client, telegram_user_id=1240, is_coach=True)
    missing = client.get(
        "/api/v1/coach/client-search?username=not_registered",
        headers=coach_headers,
    )
    assert missing.status_code == 404
    rejected = client.post(
        "/api/v1/coach/clients",
        json={"username": "not_registered", "source": "username_search"},
        headers=coach_headers,
    )
    assert rejected.status_code == 405

    auth(
        client,
        telegram_user_id=5240,
        is_coach=False,
        username="registered_client",
        full_name="Зарегистрированный клиент",
    )
    found = client.get(
        "/api/v1/coach/client-search?username=@registered_client",
        headers=coach_headers,
    )
    assert found.status_code == 404


def test_unbound_token_invite_cannot_be_accepted_by_database_id(client):
    coach_headers = auth(client, telegram_user_id=1210, is_coach=True)
    client_headers = auth(client, telegram_user_id=5210, is_coach=False)
    other_headers = auth(client, telegram_user_id=5211, is_coach=False)

    token, created = create_coach_invite_token(client, coach_headers)
    invite_id = created["invite_id"]
    assert client.get("/api/v1/me/coach-invites", headers=client_headers).status_code == 404
    assert client.get("/api/v1/me/coach-invites", headers=other_headers).status_code == 404
    forbidden = client.post(
        f"/api/v1/me/coach-invites/{invite_id}/accept",
        headers=other_headers,
    )
    assert forbidden.status_code == 404

    forbidden_for_intended_client = client.post(
        f"/api/v1/me/coach-invites/{invite_id}/accept",
        headers=client_headers,
    )
    assert forbidden_for_intended_client.status_code == 404
    confirmed = client.post(
        "/api/v1/me/coach-invites/link/confirm",
        json={"token": token},
        headers=client_headers,
    )
    assert confirmed.status_code == 204


def test_coach_can_remove_client_link(client):
    coach_headers = auth(client, telegram_user_id=1203, is_coach=True, username="@unlink_coach")
    client_headers = auth(client, telegram_user_id=5202, is_coach=False)
    client_user = client.get("/api/v1/me", headers=client_headers).json()

    accept_coach_invite(client, coach_headers, client_headers)
    assert client.get("/api/v1/me", headers=client_headers).json()["trainer"]

    removed = client.delete(f"/api/v1/coach/clients/{client_user['id']}", headers=coach_headers)

    assert removed.status_code == 204
    assert client.get("/api/v1/me", headers=client_headers).json()["trainer"] is None
    rows = client.get("/api/v1/coach/clients", headers=coach_headers).json()
    assert not any(row["id"] == client_user["id"] for row in rows)


def test_client_can_detach_trainer(client):
    coach_headers = auth(client, telegram_user_id=1204, is_coach=True, username="@detach_coach")
    client_headers = auth(client, telegram_user_id=5203, is_coach=False)
    client_user = client.get("/api/v1/me", headers=client_headers).json()

    accept_coach_invite(client, coach_headers, client_headers)

    detached = client.delete("/api/v1/me/trainer", headers=client_headers)

    assert detached.status_code == 204
    assert client.get("/api/v1/me", headers=client_headers).json()["trainer"] is None
    rows = client.get("/api/v1/coach/clients", headers=coach_headers).json()
    assert not any(row["id"] == client_user["id"] for row in rows)


def test_trainer_info_without_username_is_not_clickable(client):
    coach_headers = auth(
        client,
        telegram_user_id=1205,
        is_coach=True,
        username="",
        full_name="Тренер Без Username",
    )
    client_headers = auth(client, telegram_user_id=5204, is_coach=False)

    accept_coach_invite(client, coach_headers, client_headers)

    trainer = client.get("/api/v1/me", headers=client_headers).json()["trainer"]
    assert trainer["full_name"] == "Тренер Без Username"
    assert trainer["can_open_chat"] is False
    assert trainer["chat_url"] is None
    assert "username" in trainer["chat_unavailable_reason"]


def test_invite_link_does_not_depend_on_username_and_client_confirms_after_login(client):
    coach_headers = auth(client, telegram_user_id=1002, is_coach=True)
    token, created = create_coach_invite_token(client, coach_headers)

    init_data = signed_init_data(
        bot_token="test-token",
        auth_date=int(time.time()),
        telegram_user_id=5001,
        username="future_client",
    )
    login = client.post("/api/v1/auth/telegram/init", json={"init_data": init_data})
    assert login.status_code == 200
    client_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert client.get("/api/v1/me/coach-invites", headers=client_headers).status_code == 404
    preview = client.post(
        "/api/v1/me/coach-invites/link/preview",
        json={"token": token},
        headers=client_headers,
    )
    assert preview.status_code == 200
    assert preview.json()["invite_id"] == created["invite_id"]
    confirmed = client.post(
        "/api/v1/me/coach-invites/link/confirm",
        json={"token": token},
        headers=client_headers,
    )
    assert confirmed.status_code == 204

    listed = client.get("/api/v1/programs/clients", headers=coach_headers)
    assert listed.status_code == 200
    rows = listed.json()
    assert any(row["telegram_user_id"] == 5001 and row["status"] == "active" for row in rows)


def test_me_requires_auth(client):
    response = client.get("/api/v1/me")
    assert response.status_code == 401


def test_invalid_token_treated_as_unauthorized(client):
    response = client.get("/api/v1/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


def test_telegram_init_data_rejects_stale_auth_date():
    bot_token = "test-token"
    stale_init_data = signed_init_data(
        bot_token=bot_token,
        auth_date=int(time.time()) - 2 * 24 * 60 * 60,
    )

    with pytest.raises(ValueError, match="устарел"):
        validate_telegram_init_data(stale_init_data, bot_token)


def test_telegram_init_data_rejects_non_object_user():
    init_data = signed_init_data(
        bot_token="test-token",
        auth_date=int(time.time()),
        user_data=[],
    )

    with pytest.raises(ValueError, match="Некорректный user"):
        validate_telegram_init_data(init_data, "test-token")


@pytest.mark.parametrize("invalid_id", [True, 0, -1, "555001", 2**63])
def test_telegram_init_data_rejects_invalid_user_id(invalid_id):
    init_data = signed_init_data(
        bot_token="test-token",
        auth_date=int(time.time()),
        user_data={"id": invalid_id, "first_name": "Telegram"},
    )

    with pytest.raises(ValueError, match="Некорректный id пользователя"):
        validate_telegram_init_data(init_data, "test-token")


def test_telegram_init_endpoint_rejects_oversized_payload(client):
    response = client.post("/api/v1/auth/telegram/init", json={"init_data": "x" * 16_385})

    assert response.status_code == 422


def test_refresh_token_rotation(client):
    login = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": 2001, "is_coach": False},
    )
    assert login.status_code == 200

    refresh_token = client.cookies.get("fit_refresh_token")
    assert refresh_token
    refreshed = client.post("/api/v1/auth/refresh", json={})
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]
    assert "refresh_token" not in refreshed.json()
    assert client.cookies.get("fit_refresh_token") != refresh_token

    reused = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert reused.status_code == 401


def test_admin_users_forbidden_for_client(client):
    headers = auth(client, telegram_user_id=2001, is_coach=False)
    response = client.get("/api/v1/admin/users", headers=headers)
    assert response.status_code == 403


def test_admin_users_forbidden_for_coach(client):
    headers = auth(client, telegram_user_id=1002, is_coach=True)
    response = client.get("/api/v1/admin/users", headers=headers)
    assert response.status_code == 403


def test_admin_users_ok_for_verified_root(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "1001")
    headers = auth(client, telegram_user_id=1001, is_coach=True, is_admin=True)
    response = client.get("/api/v1/admin/users?q=1001", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_admin_users_supports_bounded_safe_identifier_search(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "1001")
    headers = auth(client, telegram_user_id=1001, is_coach=True, is_admin=True)
    first = auth(client, telegram_user_id=6011, is_coach=False, full_name="Искомый клиент")
    auth(client, telegram_user_id=6012, is_coach=True, full_name="Другой тренер")
    first_user = client.get("/api/v1/me", headers=first).json()

    page = client.get(
        f"/api/v1/admin/users?q={first_user['username']}",
        headers=headers,
    )
    assert page.status_code == 200
    assert len(page.json()) == 1

    filtered = client.get(
        "/api/v1/admin/users?q=6011",
        headers=headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()[0]["telegram_user_id"] == 6011


def test_user_activates_trainer_capability_directly_and_idempotently(client):
    headers = auth(client, telegram_user_id=6021, is_coach=False)

    initial = client.get("/api/v1/me/trainer-capability", headers=headers)
    assert initial.status_code == 200
    assert initial.json() == {
        "is_active": False,
        "activated_now": False,
        "active_client_count": 0,
        "pending_invite_count": 0,
        "can_disable": False,
        "terms_version": "trainer-capability-v1",
    }
    rejected_terms = client.post(
        "/api/v1/me/trainer-capability",
        json={"accepted_terms": False},
        headers=headers,
    )
    assert rejected_terms.status_code == 422

    activated = client.post(
        "/api/v1/me/trainer-capability",
        json={"accepted_terms": True},
        headers=headers,
    )
    assert activated.status_code == 200
    assert activated.json()["is_active"] is True
    assert activated.json()["activated_now"] is True
    assert client.get("/api/v1/me", headers=headers).json()["is_coach"] is True

    repeated = client.post(
        "/api/v1/me/trainer-capability",
        json={"accepted_terms": True},
        headers=headers,
    )
    assert repeated.status_code == 200
    assert repeated.json()["is_active"] is True
    assert repeated.json()["activated_now"] is False

    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    with get_session_context() as db:
        events = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.target_user_id == user_id,
                AuditEvent.action == "trainer_capability.activated",
            )
            .all()
        )
        assert len(events) == 1
        assert events[0].details == {
            "source": "profile",
            "terms_version": "trainer-capability-v1",
        }


def test_trainer_capability_lock_refreshes_auth_identity_state(client):
    headers = auth(client, telegram_user_id=6028, is_coach=False)
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]

    with get_session_context() as db:
        stale_user = db.query(User).filter(User.id == user_id).one()
        assert stale_user.is_coach is False
        db.execute(
            text("UPDATE users SET is_coach = :is_coach WHERE id = :user_id"),
            {"is_coach": True, "user_id": user_id},
        )

        state = activate_trainer_capability(db, stale_user)

        assert state["is_active"] is True
        assert state["activated_now"] is False
        assert (
            db.query(AuditEvent)
            .filter(
                AuditEvent.target_user_id == user_id,
                AuditEvent.action == "trainer_capability.activated",
            )
            .count()
            == 0
        )


def test_invite_creation_lock_rejects_stale_trainer_capability(client):
    headers = auth(client, telegram_user_id=6029, is_coach=True)
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]

    with get_session_context() as db:
        stale_user = db.query(User).filter(User.id == user_id).one()
        assert stale_user.is_coach is True
        db.execute(
            text("UPDATE users SET is_coach = :is_coach WHERE id = :user_id"),
            {"is_coach": False, "user_id": user_id},
        )

        with pytest.raises(ProgramError, match="Режим тренера недоступен"):
            create_coach_invite_link(db, stale_user)


def test_admin_remains_without_trainer_capability_until_self_activation(client):
    headers = auth(client, telegram_user_id=6022, is_coach=False, is_admin=True)
    assert client.get("/api/v1/me", headers=headers).json()["is_coach"] is False

    activated = client.post(
        "/api/v1/me/trainer-capability",
        json={"accepted_terms": True},
        headers=headers,
    )
    assert activated.status_code == 200
    current = client.get("/api/v1/me", headers=headers).json()
    assert current["is_admin"] is True
    assert current["is_coach"] is True


def test_trainer_disables_capability_without_erasing_history(client):
    headers = auth(client, telegram_user_id=6023, is_coach=True)
    invite = client.post("/api/v1/coach/invite-links", headers=headers)
    assert invite.status_code == 201

    disabled = client.delete("/api/v1/me/trainer-capability", headers=headers)
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False
    assert disabled.json()["pending_invite_count"] == 0
    assert client.get("/api/v1/me", headers=headers).json()["is_coach"] is False

    repeated = client.delete("/api/v1/me/trainer-capability", headers=headers)
    assert repeated.status_code == 200
    assert repeated.json()["is_active"] is False

    with get_session_context() as db:
        saved_invite = db.query(CoachClientInvite).filter_by(id=invite.json()["invite_id"]).one()
        assert saved_invite.status == "revoked"
        assert (
            db.query(AuditEvent)
            .filter(AuditEvent.action == "trainer_capability.deactivated")
            .count()
            == 1
        )


def test_trainer_cannot_disable_capability_with_active_clients(client):
    headers = auth(client, telegram_user_id=6024, is_coach=True)
    client_headers = auth(client, telegram_user_id=6025, is_coach=False)
    trainer_id = client.get("/api/v1/me", headers=headers).json()["id"]
    client_id = client.get("/api/v1/me", headers=client_headers).json()["id"]
    with get_session_context() as db:
        db.add(CoachClient(coach_user_id=trainer_id, client_user_id=client_id, status="active"))
        db.commit()

    state = client.get("/api/v1/me/trainer-capability", headers=headers)
    assert state.json()["active_client_count"] == 1
    assert state.json()["can_disable"] is False

    blocked = client.delete("/api/v1/me/trainer-capability", headers=headers)
    assert blocked.status_code == 409
    assert "Сначала завершите активные отношения" in blocked.json()["detail"]
    assert client.get("/api/v1/me", headers=headers).json()["is_coach"] is True
    with get_session_context() as db:
        relation = (
            db.query(CoachClient)
            .filter_by(coach_user_id=trainer_id, client_user_id=client_id)
            .one()
        )
        assert relation.status == "active"


def test_coach_application_and_admin_role_routes_are_removed(client):
    user_headers = auth(client, telegram_user_id=6026, is_coach=False)
    admin_headers = auth(client, telegram_user_id=6027, is_coach=False, is_admin=True)
    user_id = client.get("/api/v1/me", headers=user_headers).json()["id"]

    assert client.get("/api/v1/me/coach-application", headers=user_headers).status_code == 404
    assert client.post("/api/v1/me/coach-application", headers=user_headers).status_code == 404
    assert client.get("/api/v1/admin/coach-applications", headers=admin_headers).status_code == 404
    assert (
        client.patch(
            f"/api/v1/admin/users/{user_id}/role",
            json={"role": "coach"},
            headers=admin_headers,
        ).status_code
        == 404
    )


def test_verified_root_can_block_and_unblock_user(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "1001")
    admin_headers = auth(client, telegram_user_id=1001, is_coach=True, is_admin=True)
    user_headers = auth(client, telegram_user_id=5010, is_coach=False)
    user = client.get("/api/v1/me", headers=user_headers).json()

    blocked = client.patch(
        f"/api/v1/admin/users/{user['id']}/status",
        json={"is_active": False, "reason": "security_incident"},
        headers=admin_headers,
    )
    assert blocked.status_code == 200
    assert blocked.json()["is_active"] is False

    assert client.get("/api/v1/me", headers=user_headers).status_code == 401
    relogin = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": 5010, "is_coach": False},
    )
    assert relogin.status_code == 403

    unblocked = client.patch(
        f"/api/v1/admin/users/{user['id']}/status",
        json={"is_active": True, "reason": "account_recovery"},
        headers=admin_headers,
    )
    assert unblocked.status_code == 200
    assert unblocked.json()["is_active"] is True
    assert auth(client, telegram_user_id=5010, is_coach=False)


def test_root_cannot_block_or_delete_self(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "1001")
    admin_headers = auth(client, telegram_user_id=1001, is_coach=True, is_admin=True)
    admin_user = client.get("/api/v1/me", headers=admin_headers).json()

    block = client.patch(
        f"/api/v1/admin/users/{admin_user['id']}/status",
        json={"is_active": False, "reason": "security_incident"},
        headers=admin_headers,
    )
    assert block.status_code == 403

    delete = client.delete(f"/api/v1/admin/users/{admin_user['id']}", headers=admin_headers)
    assert delete.status_code == 405


def test_root_user_deletion_operation_is_not_exposed(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "1001")
    admin_headers = auth(client, telegram_user_id=1001, is_coach=True, is_admin=True)
    user_headers = auth(client, telegram_user_id=5011, is_coach=False)
    user = client.get("/api/v1/me", headers=user_headers).json()
    exercises = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=user_headers).json()
        if item["metric_type"] == "strength"
    ]
    payload = {
        "title": "Программа удаляемого пользователя",
        "goal": "recomposition",
        "level": "intermediate",
        "mode": "self",
        "assign_after_create": True,
        "days": [
            {
                "title": "День 1",
                "exercises": [
                    {
                        "exercise_id": exercises[0]["id"],
                        "prescribed_sets": 1,
                        "prescribed_reps": "8",
                        "rest_seconds": 90,
                    }
                ],
            }
        ],
    }
    created = client.post("/api/v1/programs/templates", json=payload, headers=user_headers)
    assert created.status_code == 200

    deleted = client.delete(f"/api/v1/admin/users/{user['id']}", headers=admin_headers)
    assert deleted.status_code == 405
    assert client.get("/api/v1/me", headers=user_headers).status_code == 200

    rows = client.get("/api/v1/admin/users?q=5011", headers=admin_headers).json()
    assert any(row["telegram_user_id"] == 5011 for row in rows)


def test_root_template_deletion_operation_is_not_exposed(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "1001")
    admin_headers = auth(client, telegram_user_id=1001, is_coach=True, is_admin=True)
    exercises = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=admin_headers).json()
        if item["metric_type"] == "strength"
    ]
    payload = {
        "title": "Админ удаляет шаблон",
        "goal": "recomposition",
        "level": "intermediate",
        "mode": "self",
        "assign_after_create": True,
        "days": [
            {
                "title": "День 1",
                "exercises": [
                    {
                        "exercise_id": exercises[0]["id"],
                        "prescribed_sets": 1,
                        "prescribed_reps": "8",
                        "rest_seconds": 90,
                    }
                ],
            }
        ],
    }
    created = client.post("/api/v1/programs/templates", json=payload, headers=admin_headers)
    assert created.status_code == 200
    template_id = created.json()["template"]["id"]

    deleted = client.delete(f"/api/v1/admin/templates/{template_id}", headers=admin_headers)
    assert deleted.status_code == 404

    missing = client.get(f"/api/v1/programs/templates/{template_id}", headers=admin_headers)
    assert missing.status_code == 200


def test_removed_admin_template_route_is_absent_for_coach(client):
    coach_headers = auth(client, telegram_user_id=1002, is_coach=True)
    response = client.delete("/api/v1/admin/templates/1", headers=coach_headers)
    assert response.status_code == 404


def test_billing_and_admin_payment_routes_are_not_exposed(client):
    headers = auth(client, telegram_user_id=1001, is_coach=True, is_admin=True)
    routes = [
        ("GET", "/api/v1/billing/plans"),
        ("POST", "/api/v1/billing/checkout"),
        ("POST", "/api/v1/billing/mock/complete/legacy-checkout"),
        ("GET", "/api/v1/billing/subscription"),
        ("GET", "/api/v1/admin/payments"),
    ]

    for method, path in routes:
        response = client.request(method, path, headers=headers)
        assert response.status_code == 404

    openapi_paths = client.get("/openapi.json").json()["paths"]
    assert not any("billing" in path for path in openapi_paths)
    assert "/api/v1/admin/payments" not in openapi_paths


def test_notification_reminder_hour_validation(client):
    headers = auth(client, telegram_user_id=2001, is_coach=False)
    response = client.patch(
        "/api/v1/notifications/settings",
        headers=headers,
        json={"workout_reminders_enabled": True, "reminder_hour": 25},
    )
    assert response.status_code in (400, 422)


def test_create_notification_and_list(client):
    headers = auth(client, telegram_user_id=2001, is_coach=False)
    scheduled = (datetime.now(UTC) + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    create = client.post(
        "/api/v1/notifications",
        headers=headers,
        json={"title": "Test напоминание", "body": "Текст", "scheduled_for": scheduled},
    )
    assert create.status_code == 201
    listed = client.get("/api/v1/notifications", headers=headers)
    assert listed.status_code == 200
    rows = listed.json()
    assert any(row["title"] == "Test напоминание" for row in rows)


def test_notification_scheduled_for_is_stored_as_msk_wall_time(client):
    headers = auth(client, telegram_user_id=6501, is_coach=False)

    response = client.post(
        "/api/v1/notifications",
        headers=headers,
        json={
            "title": "MSK напоминание",
            "body": "Текст",
            "scheduled_for": "2026-04-25T07:30:00Z",
        },
    )

    assert response.status_code == 201
    assert response.json()["scheduled_for"] == "2026-04-25T10:30:00"


def test_workout_reminders_are_deduplicated_claimed_and_retried(client, monkeypatch):
    fixed_local_now = datetime(2026, 4, 25, 12)
    fixed_utc_now = datetime(2026, 4, 25, 9)
    monkeypatch.setattr(
        notifications_service,
        "now_for_user_naive",
        lambda _user: fixed_local_now,
    )
    monkeypatch.setattr(notifications_service, "utcnow", lambda: fixed_utc_now)

    auth(client, telegram_user_id=6510, is_coach=False)
    with get_session_context() as session:
        user = session.query(User).filter(User.telegram_user_id == 6510).one()
        template = session.query(ProgramTemplate).first()
        program = UserProgram(user_id=user.id, template_id=template.id, is_active=True)
        session.add(program)
        session.flush()
        workout = UserWorkout(
            user_program_id=program.id,
            scheduled_date=fixed_local_now.date(),
            day_number=1,
            title="Тестовая тренировка",
            status="planned",
        )
        session.add(workout)
        session.flush()
        user_id = user.id
        workout_id = workout.id

        setting = session.query(NotificationSetting).filter_by(user_id=user.id).one()
        setting.workout_reminders_enabled = True
        setting.reminder_hour = 0

    with get_session_context() as session:
        assert sync_workout_reminders(session) == 1
        assert sync_workout_reminders(session) == 0
        rows = session.query(Notification).filter(Notification.user_id == user_id).all()
        assert len(rows) == 1
        assert rows[0].dedupe_key == f"workout:{workout_id}:reminder"

        rows[0].status = "cancelled"
        rows[0].attempt_count = 3
        rows[0].last_error = "disabled"
        rows[0].next_attempt_at = fixed_utc_now
        session.commit()
        assert sync_workout_reminders(session) == 0
        session.refresh(rows[0])
        assert rows[0].status == "queued"
        assert rows[0].attempt_count == 0
        assert rows[0].last_error is None
        assert rows[0].next_attempt_at is None

        claimed = claim_due_notifications(session)
        assert [row.id for row in claimed] == [rows[0].id]
        assert claim_due_notifications(session) == []

        mark_delivery_failed(session, claimed[0], RuntimeError("temporary"))
        session.refresh(claimed[0])
        assert claimed[0].status == "queued"
        assert claimed[0].attempt_count == 1
        assert claimed[0].next_attempt_at is not None


def test_bot_can_set_user_timezone_and_notifications_use_it(client):
    updated = client.post(
        "/api/v1/bot/timezone",
        headers={"X-Bot-Token": settings.bot_internal_token},
        json={
            "telegram_user_id": 6502,
            "timezone": "Asia/Tokyo",
            "username": "tokyo_user",
            "first_name": "Tokyo",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["timezone"] == "Asia/Tokyo"

    headers = auth(client, telegram_user_id=6502, is_coach=False)
    me = client.get("/api/v1/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["profile"]["timezone"] == "Asia/Tokyo"

    response = client.post(
        "/api/v1/notifications",
        headers=headers,
        json={
            "title": "Tokyo напоминание",
            "body": "Текст",
            "scheduled_for": "2026-04-25T00:30:00Z",
        },
    )

    assert response.status_code == 201
    assert response.json()["scheduled_for"] == "2026-04-25T09:30:00"


def test_bot_rejects_invalid_timezone(client):
    response = client.post(
        "/api/v1/bot/timezone",
        headers={"X-Bot-Token": settings.bot_internal_token},
        json={"telegram_user_id": 6503, "timezone": "Mars/Olympus"},
    )

    assert response.status_code == 400


def test_bot_internal_api_does_not_accept_telegram_bot_token(client, monkeypatch):
    from fitminiapp_api.core.config import settings

    monkeypatch.setattr(settings, "telegram_bot_token", "telegram-api-token")
    monkeypatch.setattr(settings, "bot_internal_token", "separate-internal-token")
    payload = {
        "telegram_user_id": 6504,
        "timezone": "Europe/Moscow",
        "first_name": "Internal",
    }

    rejected = client.post(
        "/api/v1/bot/timezone",
        headers={"X-Bot-Token": "telegram-api-token"},
        json=payload,
    )
    accepted = client.post(
        "/api/v1/bot/timezone",
        headers={"X-Bot-Token": "separate-internal-token"},
        json=payload,
    )

    assert rejected.status_code == 403
    assert accepted.status_code == 200


def test_to_msk_naive_converts_aware_utc_datetime():
    converted = to_msk_naive(datetime(2026, 4, 25, 7, 30, tzinfo=UTC))

    assert converted == datetime(2026, 4, 25, 10, 30)


def test_health_includes_request_id(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "x-request-id" in {k.lower(): v for k, v in response.headers.items()}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_request_id_accepts_safe_value_and_replaces_untrusted_value(client):
    accepted = client.get("/health/live", headers={"X-Request-ID": "edge-request_123.abc"})
    replaced = client.get("/health/live", headers={"X-Request-ID": "x" * 129})

    assert accepted.headers["x-request-id"] == "edge-request_123.abc"
    assert replaced.headers["x-request-id"] != "x" * 129
    assert re.fullmatch(r"[0-9a-f-]{36}", replaced.headers["x-request-id"])


def test_health_supports_head(client):
    response = client.head("/health")
    assert response.status_code == 200
    assert response.content == b""
    assert "x-request-id" in {k.lower(): v for k, v in response.headers.items()}


def test_auth_uses_httponly_refresh_cookie(client):
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": 4050, "is_coach": False},
    )

    assert response.status_code == 200
    assert "refresh_token" not in response.json()
    cookie = response.headers["set-cookie"].lower()
    assert "fit_refresh_token=" in cookie
    assert "httponly" in cookie
    assert "samesite=strict" in cookie


def test_workout_state_machine_rejects_invalid_transitions(client):
    headers = auth(client, telegram_user_id=2050, is_coach=False)
    exercises = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=headers).json()
        if item["metric_type"] == "strength"
    ]
    payload = {
        "title": "Проверка состояний",
        "goal": "recomposition",
        "level": "beginner",
        "mode": "self",
        "assign_after_create": True,
        "days": [
            {
                "title": "Сегодня",
                "exercises": [
                    {
                        "exercise_id": exercises[0]["id"],
                        "prescribed_sets": 1,
                        "prescribed_reps": "8",
                        "rest_seconds": 60,
                    }
                ],
            }
        ],
    }
    assert (
        client.post("/api/v1/programs/templates", json=payload, headers=headers).status_code == 200
    )
    workout = client.get("/api/v1/workouts/today", headers=headers).json()

    assert (
        client.post(f"/api/v1/workouts/{workout['id']}/finish", headers=headers).status_code == 409
    )
    assert (
        client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers).status_code == 200
    )
    assert (
        client.post(f"/api/v1/workouts/{workout['id']}/finish", headers=headers).status_code == 409
    )

    set_id = workout["exercises"][0]["sets"][0]["id"]
    saved = client.patch(
        f"/api/v1/workouts/sets/{set_id}",
        json={"actual_reps": 8, "is_completed": True},
        headers=headers,
    )
    assert saved.status_code == 200
    assert (
        client.post(f"/api/v1/workouts/{workout['id']}/finish", headers=headers).status_code == 200
    )
    assert (
        client.post(f"/api/v1/workouts/{workout['id']}/finish", headers=headers).status_code == 200
    )


def test_invites_do_not_mutate_profile_or_delete_other_coach_invites(client):
    client_headers = auth(
        client,
        telegram_user_id=5250,
        is_coach=False,
        username="@real_client",
        full_name="Настоящее имя",
    )
    coach_one = auth(client, telegram_user_id=1250, is_coach=True)
    coach_two = auth(client, telegram_user_id=1251, is_coach=True)

    first_token, first_created = create_coach_invite_token(client, coach_one)
    second_token, second_created = create_coach_invite_token(client, coach_two)
    for token in (first_token, second_token):
        preview = client.post(
            "/api/v1/me/coach-invites/link/preview",
            json={"token": token},
            headers=client_headers,
        )
        assert preview.status_code == 200

    me = client.get("/api/v1/me", headers=client_headers).json()
    assert me["profile"]["full_name"] == "Настоящее имя"
    assert me["username"] == "real_client"
    assert client.get("/api/v1/me/coach-invites", headers=client_headers).status_code == 404

    confirmed = client.post(
        "/api/v1/me/coach-invites/link/confirm",
        json={"token": first_token},
        headers=client_headers,
    )
    assert confirmed.status_code == 204
    with get_session_context() as db:
        first = (
            db.query(CoachClientInvite)
            .filter(CoachClientInvite.id == first_created["invite_id"])
            .one()
        )
        second = (
            db.query(CoachClientInvite)
            .filter(CoachClientInvite.id == second_created["invite_id"])
            .one()
        )
        assert first.status == "accepted"
        assert first.full_name == "Настоящее имя"
        assert second.status == "pending"


def test_removed_template_delete_route_preserves_template_and_assigned_program(client):
    headers = auth(client, telegram_user_id=4051, is_coach=True, is_admin=True)
    user = client.get("/api/v1/me", headers=headers).json()
    exercises = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=headers).json()
        if item["metric_type"] == "strength"
    ]
    payload = {
        "title": "Архивируемый шаблон",
        "goal": "maintenance",
        "level": "beginner",
        "mode": "self",
        "assign_after_create": True,
        "days": [
            {
                "title": "Сохранённая тренировка",
                "exercises": [
                    {
                        "exercise_id": exercises[0]["id"],
                        "prescribed_sets": 1,
                        "prescribed_reps": "8",
                        "rest_seconds": 60,
                    }
                ],
            }
        ],
    }
    created = client.post("/api/v1/programs/templates", json=payload, headers=headers)
    assert created.status_code == 200
    template_id = created.json()["template"]["id"]
    program_id = created.json()["assigned_program_id"]

    assert (
        client.delete(f"/api/v1/admin/templates/{template_id}", headers=headers).status_code == 404
    )

    with get_session_context() as db:
        program = db.query(UserProgram).filter(UserProgram.id == program_id).one()
        assert program.user_id == user["id"]
        assert program.template_id == template_id
        assert db.query(ProgramTemplate).filter(ProgramTemplate.id == template_id).count() == 1
        assert db.query(UserWorkout).filter(UserWorkout.user_program_id == program.id).count() == 1


def test_removed_user_delete_route_preserves_coach_program_and_workouts(client):
    admin_headers = auth(client, telegram_user_id=4052, is_coach=True, is_admin=True)
    coach_headers = auth(client, telegram_user_id=1352, is_coach=True)
    client_headers = auth(client, telegram_user_id=5352, is_coach=False)
    coach_user = client.get("/api/v1/me", headers=coach_headers).json()

    accept_coach_invite(client, coach_headers, client_headers)

    exercises = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=coach_headers).json()
        if item["metric_type"] == "strength"
    ]
    created = client.post(
        "/api/v1/programs/templates",
        json={
            "title": "Программа, переживающая удаление тренера",
            "goal": "maintenance",
            "level": "beginner",
            "mode": "coach",
            "target_telegram_user_id": 5352,
            "assign_after_create": True,
            "days": [
                {
                    "title": "День клиента",
                    "exercises": [
                        {
                            "exercise_id": exercises[0]["id"],
                            "prescribed_sets": 1,
                            "prescribed_reps": "8",
                            "rest_seconds": 60,
                        }
                    ],
                }
            ],
        },
        headers=coach_headers,
    )
    assert created.status_code == 200
    program_id = created.json()["assigned_program_id"]

    deleted = client.delete(
        f"/api/v1/admin/users/{coach_user['id']}",
        headers=admin_headers,
    )
    assert deleted.status_code == 405
    assert client.get("/api/v1/workouts/today", headers=client_headers).status_code == 200

    with get_session_context() as db:
        program = db.query(UserProgram).filter(UserProgram.id == program_id).one()
        assert program.template_id is not None
        assert program.assigned_by_user_id == coach_user["id"]
        assert db.query(UserWorkout).filter(UserWorkout.user_program_id == program.id).count() == 1


def test_csp_blocks_unhashed_inline_scripts(client):
    response = client.get("/app")
    policy = response.headers["content-security-policy"]
    script_policy = policy.split("script-src", 1)[1].split(";", 1)[0]

    assert response.headers["permissions-policy"] == (
        "camera=(self), microphone=(), geolocation=()"
    )
    assert "img-src 'self' data: blob:" in policy
    assert "https://t.me https://*.telegram.org https://*.cdn-telegram.org" in policy
    assert "'unsafe-inline'" not in script_policy
    assert "'sha256-" not in script_policy

    html = response.text
    inline_sources = re.findall(r"<script(?:\s+[^>]*)?>([\s\S]*?)</script>", html)
    assert all(not source.strip() for source in inline_sources)

    source_template = (Path(__file__).resolve().parents[2] / "frontend" / "index.html").read_text(
        encoding="utf-8"
    )
    assert '<link rel="manifest" href="/manifest.webmanifest" />' in source_template
    assert '<script src="/assets/theme-bootstrap-20260826.js"></script>' in source_template
    source_inline_scripts = re.findall(r"<script(?:\s+[^>]*)?>([\s\S]*?)</script>", source_template)
    assert all(not source.strip() for source in source_inline_scripts)
    assert (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "public"
        / "assets"
        / "theme-bootstrap-20260826.js"
    ).is_file()

    api_client = (
        Path(__file__).resolve().parents[2] / "frontend" / "src" / "shared" / "api" / "client.ts"
    ).read_text(encoding="utf-8")
    assert "localStorage.setItem(ACCESS_TOKEN_KEY" not in api_client
    assert "sessionStorage.setItem(ACCESS_TOKEN_KEY" in api_client


def test_versioned_static_assets_are_cached_but_html_is_not(client):
    page = client.get("/app")
    asset_path = re.search(r'href="(/assets/[^"]+\.css)"', page.text).group(1)
    asset = client.get(asset_path)
    assert asset.status_code == 200
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"

    for brand_asset_path in (
        "/assets/brand/fitness-logo-v2.png",
        "/assets/brand/favicon-v2.png",
    ):
        brand_asset = client.get(brand_asset_path)
        assert brand_asset.status_code == 200
        assert brand_asset.headers["content-type"] == "image/png"
        assert brand_asset.headers["cache-control"] == "public, max-age=31536000, immutable"

    assert page.status_code == 200
    assert "no-store" in page.headers["cache-control"]


def test_root_serves_public_landing_spa(client):
    response = client.get("/")

    assert response.status_code == 200
    assert '<main class="seo-fallback">' in response.text
    assert "Тренировки, питание и прогресс" in response.text
    assert "no-store" in response.headers["cache-control"]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/app"),
        ("GET", "/login"),
        ("GET", "/join/abcdefghijklmnopqrstuvwxyz"),
    ],
)
def test_landing_host_redirects_browser_application_requests_to_canonical_origin(
    client, monkeypatch, method, path
):
    from fitminiapp_api.core.config import settings

    monkeypatch.setattr(settings, "landing_domain", "your-fitness-coach.ru")
    monkeypatch.setattr(settings, "frontend_base_url", "https://app.your-fitness-coach.ru")

    response = client.request(
        method,
        path,
        headers={"Host": "your-fitness-coach.ru"},
        follow_redirects=False,
    )

    assert response.status_code == 308
    assert response.headers["location"] == f"https://app.your-fitness-coach.ru{path}"


@pytest.mark.parametrize(
    ("method", "path", "expected_status"),
    [
        ("GET", "/api/v1/public/articles", 200),
        ("GET", "/api/v1/public/config", 200),
        ("GET", "/api/v1/public/exercises", 200),
        ("GET", "/api/v1/me", 401),
        ("POST", "/api/v1/auth/refresh", 401),
    ],
)
def test_landing_host_keeps_api_requests_same_origin(
    client, monkeypatch, method, path, expected_status
):
    from fitminiapp_api.core.config import settings

    monkeypatch.setattr(settings, "landing_domain", "your-fitness-coach.ru")
    monkeypatch.setattr(settings, "frontend_base_url", "https://app.your-fitness-coach.ru")

    response = client.request(
        method,
        path,
        headers={"Host": "your-fitness-coach.ru", "Origin": "https://evil.example"},
        follow_redirects=False,
    )

    assert response.status_code == expected_status
    assert "location" not in response.headers
    assert "access-control-allow-origin" not in response.headers


def test_landing_host_keeps_public_home_on_landing_domain(client, monkeypatch):
    from fitminiapp_api.core.config import settings

    monkeypatch.setattr(settings, "landing_domain", "your-fitness-coach.ru")
    response = client.get("/", headers={"Host": "your-fitness-coach.ru"})

    assert response.status_code == 200
    assert '<main class="seo-fallback">' in response.text


def test_public_seo_response_uses_canonical_metadata_and_truthful_structured_data(
    client, monkeypatch
):
    from fitminiapp_api.core.config import settings

    monkeypatch.setattr(settings, "landing_domain", "your-fitness-coach.ru")
    response = client.get("/", headers={"Host": "your-fitness-coach.ru"})

    assert response.status_code == 200
    assert response.headers["x-robots-tag"] == "index, follow"
    assert '<meta name="robots" content="index, follow" />' in response.text
    assert '<link rel="canonical" href="https://your-fitness-coach.ru/" />' in response.text
    assert '<meta property="og:url" content="https://your-fitness-coach.ru/" />' in response.text
    assert (
        '<noscript><div><img src="https://mc.yandex.ru/watch/112530718" '
        'style="position:absolute; left:-9999px;" alt="" /></div></noscript>' in response.text
    )
    assert (
        '<meta property="og:image" '
        'content="https://your-fitness-coach.ru/assets/brand/yfc-social-preview.png" />'
        in response.text
    )
    assert '<meta property="og:image:width" content="1200" />' in response.text
    assert '<meta property="og:image:height" content="630" />' in response.text
    assert '<meta name="twitter:card" content="summary_large_image" />' in response.text
    structured_data = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', response.text, re.DOTALL
    )
    assert structured_data is not None
    payload = json.loads(structured_data.group(1))
    assert [entry["@type"] for entry in payload["@graph"]] == [
        "Organization",
        "WebSite",
        "SoftwareApplication",
    ]
    assert "aggregateRating" not in structured_data.group(1)
    assert "offers" not in structured_data.group(1)


def test_public_seo_response_does_not_inject_webmaster_verification_tags(client, monkeypatch):
    from fitminiapp_api.core.config import settings

    monkeypatch.setattr(settings, "landing_domain", "your-fitness-coach.ru")

    landing = client.get("/", headers={"Host": "your-fitness-coach.ru"})
    private = client.get("/app")

    assert "google-site-verification" not in landing.text
    assert "yandex-verification" not in landing.text
    assert "google-site-verification" not in private.text
    assert "yandex-verification" not in private.text
    assert "mc.yandex.ru/watch/112530718" not in private.text


def test_yandex_verification_file_is_served_directly(client):
    response = client.get("/yandex_bce1658cc6fe44e5.html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["x-robots-tag"] == "noindex, nofollow"
    assert (
        response.text
        == """<html>
    <head>
        <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
    </head>
    <body>Verification: bce1658cc6fe44e5</body>
</html>
"""
    )


def test_robots_and_sitemap_publish_only_canonical_public_urls(client, monkeypatch):
    from fitminiapp_api.core.config import settings

    monkeypatch.setattr(settings, "landing_domain", "your-fitness-coach.ru")
    robots = client.get("/robots.txt", headers={"Host": "your-fitness-coach.ru"})
    sitemap = client.get("/sitemap.xml", headers={"Host": "your-fitness-coach.ru"})

    assert robots.status_code == 200
    assert "User-agent: *" in robots.text
    assert "Allow: /" in robots.text
    assert "Disallow: /api/" in robots.text
    assert "Disallow: /app" not in robots.text
    assert "Sitemap: https://your-fitness-coach.ru/sitemap.xml" in robots.text
    assert sitemap.status_code == 200
    root = ElementTree.fromstring(sitemap.content)
    urls = [
        element.text
        for element in root.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url")
        for element in element.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
    ]
    assert len(urls) == 25
    assert len(urls) == len(set(urls))
    assert {
        "https://your-fitness-coach.ru/",
        "https://your-fitness-coach.ru/articles",
        "https://your-fitness-coach.ru/knowledge",
        "https://your-fitness-coach.ru/knowledge/training/repetitions-in-reserve",
        "https://your-fitness-coach.ru/knowledge/nutrition/creatine-monohydrate",
        "https://your-fitness-coach.ru/knowledge/cardio/heart-rate-zones",
        "https://your-fitness-coach.ru/knowledge/progress/how-to-read-progress",
        "https://your-fitness-coach.ru/knowledge/nutrition/glycemic-index",
        "https://your-fitness-coach.ru/knowledge/nutrition/food-sources-for-kbju",
        "https://your-fitness-coach.ru/knowledge/progress/bmi-calculator",
        "https://your-fitness-coach.ru/knowledge/nutrition/hydration-and-water",
        "https://your-fitness-coach.ru/exercises",
        "https://your-fitness-coach.ru/exercises/bench-press",
        "https://your-fitness-coach.ru/exercises/lat-pulldown",
        "https://your-fitness-coach.ru/exercises/squat",
    }.issubset(urls)
    assert all(
        segment not in sitemap.text for segment in ("/app", "/admin", "/coach", "/join", "/login")
    )


@pytest.mark.parametrize(
    ("path", "heading"),
    [
        ("/training", "План тренировки, который остаётся перед глазами"),
        ("/nutrition", "Ориентиры КБЖУ без обещаний"),
        ("/progress", "Прогресс, который можно проверить"),
        ("/for-trainers", "Кабинет тренера для программ"),
        ("/knowledge", "Материалы, которые помогают понять"),
        (
            "/knowledge/nutrition/glycemic-index",
            "Гликемический индекс описывает продукт, а не весь приём пищи",
        ),
        (
            "/knowledge/nutrition/food-sources-for-kbju",
            "Источники КБЖУ — это варианты, а не рейтинг продуктов",
        ),
        (
            "/knowledge/progress/bmi-calculator",
            "ИМТ — скрининговый ориентир, а не диагноз",
        ),
        (
            "/knowledge/nutrition/hydration-and-water",
            "Гидратация: ориентир помогает, но не заменяет контекст",
        ),
    ],
)
def test_public_content_routes_render_unique_crawlable_pages(client, monkeypatch, path, heading):
    from fitminiapp_api.core.config import settings

    monkeypatch.setattr(settings, "landing_domain", "your-fitness-coach.ru")
    response = client.get(path, headers={"Host": "your-fitness-coach.ru"})

    assert response.status_code == 200
    assert response.headers["x-robots-tag"] == "index, follow"
    assert f'<link rel="canonical" href="https://your-fitness-coach.ru{path}" />' in response.text
    assert response.text.count("<h1>") == 1
    assert heading in response.text
    assert '<a href="/knowledge">База знаний</a>' in response.text
    assert "Личный интерфейс Your Fitness Coach" not in response.text


def test_public_campaign_url_keeps_clean_canonical_metadata(client, monkeypatch):
    from fitminiapp_api.core.config import settings

    monkeypatch.setattr(settings, "landing_domain", "your-fitness-coach.ru")
    response = client.get(
        "/training?utm_source=telegram&utm_medium=organic_social"
        "&utm_campaign=strength_start_guide&utm_content=channel_post",
        headers={"Host": "your-fitness-coach.ru"},
    )

    assert response.status_code == 200
    assert '<link rel="canonical" href="https://your-fitness-coach.ru/training" />' in response.text
    assert (
        '<meta property="og:url" content="https://your-fitness-coach.ru/training" />'
        in response.text
    )
    assert "utm_" not in response.text


def test_public_guide_has_visible_editorial_metadata_and_truthful_schema(client, monkeypatch):
    from fitminiapp_api.core.config import settings

    monkeypatch.setattr(settings, "landing_domain", "your-fitness-coach.ru")
    response = client.get(
        "/knowledge/training/how-to-start-strength-training",
        headers={"Host": "your-fitness-coach.ru"},
    )

    assert response.status_code == 200
    assert '<nav aria-label="Хлебные крошки">' in response.text
    assert "Редакция Your Fitness Coach" in response.text
    assert '<time datetime="2026-08-22">' in response.text
    assert "World Health Organization" in response.text
    structured_data = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', response.text, re.DOTALL
    )
    assert structured_data is not None
    payload = json.loads(structured_data.group(1))
    assert [entry["@type"] for entry in payload["@graph"]] == [
        "Article",
        "BreadcrumbList",
    ]
    assert "review" not in structured_data.group(1).lower()

    knowledge = client.get("/knowledge", headers={"Host": "your-fitness-coach.ru"})
    assert "Опубликованные руководства" in knowledge.text
    assert (
        '<a href="/knowledge/training/how-to-start-strength-training">'
        "Full Body и Split: выберите схему, которую сможете повторять</a>" in knowledge.text
    )


def test_public_exercise_api_uses_allowlisted_domain_data_and_excludes_private_rows(client):
    catalog = client.get("/api/v1/public/exercises")

    assert catalog.status_code == 200
    assert [item["slug"] for item in catalog.json()] == [
        "bench-press",
        "lat-pulldown",
        "squat",
    ]
    assert all("created_by_user_id" not in item for item in catalog.json())

    squat = client.get("/api/v1/public/exercises/squat")
    assert squat.status_code == 200
    assert squat.json()["title"] == "Приседания"
    assert squat.json()["primary_muscle"] == "Квадрицепс"
    assert squat.json()["technique_steps"]
    assert squat.json()["source_name"] == "free-exercise-db"

    private_slug = client.get("/api/v1/public/exercises/squat-u-private")
    assert private_slug.status_code == 404


def test_public_exercise_route_has_domain_fallback_and_webpage_schema(client, monkeypatch):
    from fitminiapp_api.core.config import settings

    monkeypatch.setattr(settings, "landing_domain", "your-fitness-coach.ru")
    response = client.get("/exercises/squat", headers={"Host": "your-fitness-coach.ru"})

    assert response.status_code == 200
    assert response.headers["x-robots-tag"] == "index, follow"
    assert "Основная группа: Квадрицепс" in response.text
    assert "Техника выполнения" in response.text
    assert "Колени заваливаются внутрь" in response.text
    assert "free-exercise-db" in response.text
    structured_data = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', response.text, re.DOTALL
    )
    assert structured_data is not None
    payload = json.loads(structured_data.group(1))
    assert [entry["@type"] for entry in payload["@graph"]] == ["WebPage", "BreadcrumbList"]


def test_draft_public_content_is_noindex_and_absent_from_sitemap_source(monkeypatch):
    from fitminiapp_api import seo

    monkeypatch.setattr(
        seo,
        "public_pages",
        lambda: (
            {"path": "/published", "status": "published"},
            {"path": "/draft", "status": "draft"},
            {"path": "/review", "status": "review"},
        ),
    )

    assert seo.public_page_paths() == ("/published",)
    assert seo.metadata_for_path("/draft").robots == "noindex, nofollow"
    assert seo.metadata_for_path("/review").canonical_url is None


def test_public_content_manifest_accepts_null_reviewer(tmp_path, monkeypatch):
    from fitminiapp_api import seo

    source = (
        Path(__file__).resolve().parents[2] / "frontend" / "src" / "content" / "publicContent.json"
    )
    payload = json.loads(source.read_text(encoding="utf-8"))
    guide = next(page for page in payload["pages"] if page.get("kind") == "guide")
    guide["reviewer"] = None
    manifest = tmp_path / "publicContent.json"
    manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(seo, "_public_content_path", lambda: manifest)
    seo.public_pages.cache_clear()

    try:
        loaded_guide = next(page for page in seo.public_pages() if page.get("id") == guide["id"])
        assert loaded_guide["reviewer"] is None
    finally:
        seo.public_pages.cache_clear()


def test_knowledge_fallback_lists_only_published_guides(monkeypatch):
    from fitminiapp_api import seo

    monkeypatch.setattr(
        seo,
        "public_pages",
        lambda: (
            {
                "kind": "knowledge-index",
                "path": "/knowledge",
                "status": "published",
                "heading": "База знаний",
                "intro": "Проверенные материалы.",
            },
            {
                "kind": "guide",
                "path": "/knowledge/published",
                "status": "published",
                "heading": "Опубликованный материал",
                "description": "Доступен читателям.",
            },
            {
                "kind": "guide",
                "path": "/knowledge/draft",
                "status": "draft",
                "heading": "Черновой материал",
                "description": "Не готов к публикации.",
            },
        ),
    )

    fallback = seo.render_public_fallback("/knowledge")

    assert "Опубликованный материал" in fallback
    assert "Черновой материал" not in fallback


def test_public_fallback_replaces_the_built_vite_marker_without_stale_landing_copy():
    from fitminiapp_api.seo import render_frontend_document

    template = (Path(__file__).resolve().parents[2] / "frontend" / "index.html").read_text(
        encoding="utf-8"
    )
    guide, _ = render_frontend_document(template, "/knowledge/nutrition/kbju-as-a-reference")
    private, _ = render_frontend_document(template, "/app")

    assert guide.count("<!-- public-fallback-start -->") == 1
    assert guide.count("<h1>") == 1
    assert "КБЖУ как ориентир, а не обещание результата" in guide
    assert "Выбирайте программу под свою задачу" not in guide
    assert '<main class="seo-fallback">' not in private


@pytest.mark.parametrize(
    "path",
    [
        "/app",
        "/app/report?period=days_30",
        "/admin",
        "/coach",
        "/login",
        "/verify-email",
        "/reset-password",
        "/join/abcdefghijklmnopqrstuvwxyz",
    ],
)
def test_private_frontend_routes_send_noindex_contract(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["x-robots-tag"] == "noindex, nofollow"
    assert '<meta name="robots" content="noindex, nofollow" />' in response.text
    assert 'rel="canonical"' not in response.text
    assert "application/ld+json" not in response.text
    assert '<main class="seo-fallback">' not in response.text


def test_canonical_hosts_and_missing_routes_do_not_create_duplicate_or_soft_404_pages(
    client, monkeypatch
):
    from fitminiapp_api.core.config import settings

    monkeypatch.setattr(settings, "landing_domain", "your-fitness-coach.ru")
    monkeypatch.setattr(settings, "frontend_base_url", "https://app.your-fitness-coach.ru")

    app_home = client.get(
        "/", headers={"Host": "app.your-fitness-coach.ru"}, follow_redirects=False
    )
    www_home = client.get(
        "/", headers={"Host": "www.your-fitness-coach.ru"}, follow_redirects=False
    )
    landing_app_slash = client.get(
        "/app/", headers={"Host": "your-fitness-coach.ru"}, follow_redirects=False
    )
    app_host_public_page = client.get(
        "/training", headers={"Host": "app.your-fitness-coach.ru"}, follow_redirects=False
    )
    trailing_public_page = client.get(
        "/training/", headers={"Host": "your-fitness-coach.ru"}, follow_redirects=False
    )
    missing = client.get("/does-not-exist")

    assert app_home.status_code == 308
    assert app_home.headers["location"] == "https://your-fitness-coach.ru/"
    assert www_home.status_code == 308
    assert www_home.headers["location"] == "https://your-fitness-coach.ru/"
    assert landing_app_slash.status_code == 308
    assert landing_app_slash.headers["location"] == "https://app.your-fitness-coach.ru/app"
    assert app_host_public_page.status_code == 308
    assert app_host_public_page.headers["location"] == "https://your-fitness-coach.ru/training"
    assert trailing_public_page.status_code == 308
    assert trailing_public_page.headers["location"] == "https://your-fitness-coach.ru/training"
    assert missing.status_code == 404


@pytest.mark.parametrize("path", ["/login", "/verify-email", "/reset-password"])
def test_browser_auth_routes_serve_spa(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert '<div id="root"></div>' in response.text
    assert "no-store" in response.headers["cache-control"]


def test_dev_login_provisions_one_idempotent_telegram_identity(client):
    from fitminiapp_api.models.auth_identity import AuthIdentity

    payload = {
        "telegram_user_id": 8_800_101,
        "username": "identity_client",
        "full_name": "Identity Client",
    }
    assert client.post("/api/v1/auth/dev-login", json=payload).status_code == 200
    assert client.post("/api/v1/auth/dev-login", json=payload).status_code == 200

    with get_session_context() as db:
        identities = (
            db.query(AuthIdentity)
            .filter(
                AuthIdentity.provider == "telegram",
                AuthIdentity.subject == str(payload["telegram_user_id"]),
            )
            .all()
        )
        assert len(identities) == 1
        assert identities[0].user.telegram_user_id == payload["telegram_user_id"]


def test_email_auth_stays_disabled_when_browser_oauth_is_enabled(client, monkeypatch):
    from fitminiapp_api.core.config import settings

    monkeypatch.setattr(settings, "enable_web_auth", True)
    response = client.post(
        "/api/v1/auth/email/register",
        json={
            "username": "browser_user",
            "email": "browser@example.com",
            "password": "a-long-browser-password",
        },
    )

    assert response.status_code == 404


def test_email_registration_verification_and_login_share_internal_account(client, monkeypatch):
    from fitminiapp_api.core.config import settings

    monkeypatch.setattr(settings, "enable_email_auth", True)
    payload = {
        "username": "browser_user",
        "email": "Browser@Example.com",
        "password": "a-long-browser-password",
    }
    registered = client.post("/api/v1/auth/email/register", json=payload)
    assert registered.status_code == 201
    verification_token = registered.json()["verification_token"]
    assert verification_token

    before_verification = client.post(
        "/api/v1/auth/email/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert before_verification.status_code == 401
    assert "Подтвердите email" in before_verification.json()["detail"]

    verified = client.post(
        "/api/v1/auth/email/verify",
        json={"token": verification_token},
    )
    assert verified.status_code == 200
    headers = {"Authorization": f"Bearer {verified.json()['access_token']}"}
    me = client.get("/api/v1/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["telegram_user_id"] is None
    assert me.json()["username"] == payload["username"]

    reused_token = client.post(
        "/api/v1/auth/email/verify",
        json={"token": verification_token},
    )
    assert reused_token.status_code == 400

    logged_in = client.post(
        "/api/v1/auth/email/login",
        json={"email": payload["email"].lower(), "password": payload["password"]},
    )
    assert logged_in.status_code == 200


def test_email_registration_rejects_duplicate_identity_and_weak_password(client, monkeypatch):
    from fitminiapp_api.core.config import settings

    monkeypatch.setattr(settings, "enable_email_auth", True)
    weak = client.post(
        "/api/v1/auth/email/register",
        json={
            "username": "weak_user",
            "email": "weak@example.com",
            "password": "password1234",
        },
    )
    assert weak.status_code == 422

    payload = {
        "username": "unique_user",
        "email": "unique@example.com",
        "password": "correct horse battery staple",
    }
    assert client.post("/api/v1/auth/email/register", json=payload).status_code == 201
    duplicate = client.post(
        "/api/v1/auth/email/register",
        json={**payload, "username": "another_user"},
    )
    assert duplicate.status_code == 409


def test_password_reset_revokes_old_password_and_tokens(client, monkeypatch):
    from fitminiapp_api.core.config import settings

    monkeypatch.setattr(settings, "enable_email_auth", True)
    email = "reset@example.com"
    old_password = "old-password-for-browser"
    registered = client.post(
        "/api/v1/auth/email/register",
        json={"username": "reset_user", "email": email, "password": old_password},
    )
    verified = client.post(
        "/api/v1/auth/email/verify",
        json={"token": registered.json()["verification_token"]},
    )
    assert verified.status_code == 200

    requested = client.post("/api/v1/auth/password/reset/request", json={"email": email})
    reset_token = requested.json()["action_token"]
    assert reset_token
    new_password = "new-password-for-browser"
    confirmed = client.post(
        "/api/v1/auth/password/reset/confirm",
        json={"token": reset_token, "password": new_password},
    )
    assert confirmed.status_code == 200

    assert (
        client.post(
            "/api/v1/auth/email/login",
            json={"email": email, "password": old_password},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/email/login",
            json={"email": email, "password": new_password},
        ).status_code
        == 200
    )


def test_password_reset_request_does_not_reveal_unknown_email(client, monkeypatch):
    from fitminiapp_api.core.config import settings

    monkeypatch.setattr(settings, "enable_email_auth", True)
    response = client.post(
        "/api/v1/auth/password/reset/request",
        json={"email": "missing@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["action_token"] is None


def test_unconfigured_oauth_provider_is_not_exposed(client, monkeypatch):
    from fitminiapp_api.core.config import settings

    monkeypatch.setattr(settings, "enable_web_auth", True)
    monkeypatch.setattr(settings, "telegram_oauth_client_id", "")
    monkeypatch.setattr(settings, "telegram_oauth_client_secret", "")
    monkeypatch.setattr(settings, "google_oauth_client_id", "")
    monkeypatch.setattr(settings, "google_oauth_client_secret", "")
    monkeypatch.setattr(settings, "yandex_oauth_client_id", "")
    monkeypatch.setattr(settings, "yandex_oauth_client_secret", "")
    monkeypatch.setattr(settings, "vk_oauth_client_id", "")
    monkeypatch.setattr(settings, "apple_oauth_client_id", "")
    monkeypatch.setattr(settings, "apple_oauth_client_secret", "")
    config = client.get("/api/v1/public/config")
    assert config.status_code == 200
    assert config.json()["enable_email_auth"] is False
    assert config.json()["oauth_providers"] == []

    started = client.get("/api/v1/auth/oauth/google/start", follow_redirects=False)
    assert started.status_code == 303
    assert started.headers["location"] == "/login?next=%2Fapp&auth_error=unavailable"


def test_browser_telegram_login_reuses_existing_telegram_user(client):
    from fitminiapp_api.models.auth_identity import AuthIdentity
    from fitminiapp_api.models.user import User
    from fitminiapp_api.services.oauth_login import get_or_create_oauth_user

    headers = auth(client, telegram_user_id=8_810_001, username="telegram_browser")
    current_id = client.get("/api/v1/me", headers=headers).json()["id"]

    with get_session_context() as db:
        user = get_or_create_oauth_user(
            db,
            provider="telegram",
            raw_claims={
                "id": 8_810_001,
                "sub": "telegram-oidc-subject",
                "preferred_username": "telegram_browser",
                "name": "Telegram Browser",
            },
        )
        assert user.id == current_id
        assert db.query(User).filter(User.telegram_user_id == 8_810_001).count() == 1
        assert (
            db.query(AuthIdentity)
            .filter(AuthIdentity.user_id == user.id, AuthIdentity.provider == "telegram")
            .count()
            == 1
        )


def test_browser_telegram_login_accepts_standard_oidc_subject(client):
    from fitminiapp_api.services.oauth_login import get_or_create_oauth_user

    with get_session_context() as db:
        user = get_or_create_oauth_user(
            db,
            provider="telegram",
            raw_claims={
                "sub": "8810003",
                "preferred_username": "telegram_oidc_subject",
                "name": "Telegram OIDC Subject",
            },
        )
        assert user.telegram_user_id == 8_810_003
        assert user.username == "telegram_oidc_subject"


def test_browser_telegram_login_rejects_invalid_oidc_subject(client):
    from fitminiapp_api.services.oauth_login import normalize_oauth_claims

    with pytest.raises(ValueError, match="valid user id"):
        normalize_oauth_claims("telegram", {"sub": "not-a-telegram-id"})


def test_oauth_callback_creates_browser_session_without_exposing_access_token(client, monkeypatch):
    from fitminiapp_api.api.v1 import auth as auth_api
    from fitminiapp_api.core.config import settings

    class FakeTelegramClient:
        async def create_authorization_url(self, callback_url):
            state = "fake-telegram-state"
            return {
                "url": f"https://telegram.example/authorize?state={state}",
                "state": state,
                "code_verifier": "fake-telegram-code-verifier",
                "redirect_uri": callback_url,
            }

        async def authorize_access_token(self, request):
            del request
            return {
                "userinfo": {
                    "id": 8_810_002,
                    "sub": "telegram-oidc-subject-002",
                    "preferred_username": "oauth_callback_user",
                    "name": "OAuth Callback User",
                }
            }

    monkeypatch.setattr(settings, "enable_web_auth", True)
    monkeypatch.setattr(
        auth_api,
        "configured_oauth_client",
        lambda provider: FakeTelegramClient() if provider == "telegram" else None,
    )
    started = client.get("/api/v1/auth/oauth/telegram/start", follow_redirects=False)
    state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]
    response = client.get(
        "/api/v1/auth/oauth/telegram/callback",
        params={"code": "provider-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/app"
    assert "access_token" not in response.headers["location"]
    assert "fit_refresh_token=" in response.headers["set-cookie"]


def test_social_login_does_not_auto_link_only_by_matching_email(client, monkeypatch):
    from fitminiapp_api.core.config import settings
    from fitminiapp_api.services.oauth_login import get_or_create_oauth_user

    monkeypatch.setattr(settings, "enable_email_auth", True)
    email = "shared@example.com"
    registered = client.post(
        "/api/v1/auth/email/register",
        json={
            "username": "email_owner",
            "email": email,
            "password": "safe-password-for-email-owner",
        },
    )
    verified = client.post(
        "/api/v1/auth/email/verify",
        json={"token": registered.json()["verification_token"]},
    )
    local_headers = {"Authorization": f"Bearer {verified.json()['access_token']}"}
    local_id = client.get("/api/v1/me", headers=local_headers).json()["id"]

    with get_session_context() as db:
        google_user = get_or_create_oauth_user(
            db,
            provider="google",
            raw_claims={
                "sub": "google-subject-001",
                "email": email,
                "email_verified": True,
                "name": "Google User",
            },
        )
        assert google_user.id != local_id


def test_web_account_explicitly_links_telegram_and_keeps_its_data(client, monkeypatch):
    from fitminiapp_api.services.oauth_login import get_or_create_oauth_user

    monkeypatch.setattr(settings, "telegram_bot_username", "your_fitness_coach_bot")
    with get_session_context() as db:
        web_user = get_or_create_oauth_user(
            db,
            provider="google",
            raw_claims={
                "sub": "google-link-subject-001",
                "email": "link-owner@example.com",
                "email_verified": True,
                "name": "Web Link Owner",
            },
        )
        web_user_id = web_user.id

    web_headers = auth_existing_user(client, web_user_id)
    profile = client.patch(
        "/api/v1/me/profile",
        headers=web_headers,
        json={"goal": "muscle_gain"},
    )
    assert profile.status_code == 200

    created = client.post("/api/v1/me/auth/telegram-link", headers=web_headers)
    assert created.status_code == 200
    assert created.json()["expires_in_seconds"] == 600
    parsed = urlparse(created.json()["telegram_url"])
    assert parsed.netloc == "t.me"
    assert parsed.path == "/your_fitness_coach_bot"
    start_payload = parse_qs(parsed.query)["start"][0]
    assert start_payload.startswith("link_")

    linked = client.post(
        "/api/v1/bot/link-telegram",
        headers={"X-Bot-Token": settings.bot_internal_token},
        json={
            "token": start_payload.removeprefix("link_"),
            "telegram_user_id": 8_820_001,
            "username": "linked_telegram",
            "first_name": "Linked",
            "last_name": "Telegram",
        },
    )
    assert linked.status_code == 200
    assert linked.json() == {"status": "linked"}

    me = client.get("/api/v1/me", headers=web_headers)
    assert me.status_code == 200
    assert me.json()["id"] == web_user_id
    assert me.json()["telegram_user_id"] == 8_820_001
    assert me.json()["profile"]["goal"] == "muscle_gain"

    telegram_headers = auth(client, telegram_user_id=8_820_001, username="linked_telegram")
    telegram_me = client.get("/api/v1/me", headers=telegram_headers)
    assert telegram_me.json()["id"] == web_user_id
    assert telegram_me.json()["profile"]["goal"] == "muscle_gain"

    repeated = client.post(
        "/api/v1/bot/link-telegram",
        headers={"X-Bot-Token": settings.bot_internal_token},
        json={
            "token": start_payload.removeprefix("link_"),
            "telegram_user_id": 8_820_001,
        },
    )
    assert repeated.status_code == 400


def test_telegram_link_rejects_existing_account_and_consumes_token(client, monkeypatch):
    from fitminiapp_api.services.oauth_login import get_or_create_oauth_user

    monkeypatch.setattr(settings, "telegram_bot_username", "your_fitness_coach_bot")
    existing_headers = auth(client, telegram_user_id=8_820_002, username="existing_owner")
    existing_id = client.get("/api/v1/me", headers=existing_headers).json()["id"]
    with get_session_context() as db:
        web_user = get_or_create_oauth_user(
            db,
            provider="yandex",
            raw_claims={
                "id": "yandex-link-subject-002",
                "default_email": "conflict@example.com",
                "display_name": "Conflict Target",
            },
        )
        web_user_id = web_user.id

    web_headers = auth_existing_user(client, web_user_id)
    created = client.post("/api/v1/me/auth/telegram-link", headers=web_headers)
    start_payload = parse_qs(urlparse(created.json()["telegram_url"]).query)["start"][0]
    raw_token = start_payload.removeprefix("link_")
    conflict = client.post(
        "/api/v1/bot/link-telegram",
        headers={"X-Bot-Token": settings.bot_internal_token},
        json={"token": raw_token, "telegram_user_id": 8_820_002},
    )
    assert conflict.status_code == 409

    burned = client.post(
        "/api/v1/bot/link-telegram",
        headers={"X-Bot-Token": settings.bot_internal_token},
        json={"token": raw_token, "telegram_user_id": 8_820_003},
    )
    assert burned.status_code == 400
    assert client.get("/api/v1/me", headers=web_headers).json()["telegram_user_id"] is None
    assert client.get("/api/v1/me", headers=existing_headers).json()["id"] == existing_id


def test_telegram_user_cannot_create_another_link(client):
    telegram_headers = auth(client, telegram_user_id=8_820_004)

    response = client.post("/api/v1/me/auth/telegram-link", headers=telegram_headers)

    assert response.status_code == 409


def test_telegram_account_explicitly_links_google_login(client, monkeypatch):
    from fitminiapp_api.api.v1 import auth as auth_api
    from fitminiapp_api.services.oauth_login import get_or_create_oauth_user

    google_claims = {
        "sub": "google-explicit-link-001",
        "email": "telegram-owner@example.com",
        "email_verified": True,
        "name": "Telegram Owner",
    }

    class FakeGoogleClient:
        async def create_authorization_url(self, callback_url):
            state = "fake-google-link-state"
            return {
                "url": f"https://accounts.example/authorize?state={state}",
                "state": state,
                "code_verifier": "fake-google-link-code-verifier",
                "redirect_uri": callback_url,
            }

        async def authorize_access_token(self, request):
            del request
            return {"userinfo": google_claims}

    monkeypatch.setattr(settings, "enable_web_auth", True)
    monkeypatch.setattr(settings, "google_oauth_client_id", "google-client")
    monkeypatch.setattr(settings, "google_oauth_client_secret", "google-secret")
    monkeypatch.setattr(
        auth_api,
        "configured_oauth_client",
        lambda provider: FakeGoogleClient() if provider == "google" else None,
    )
    telegram_headers = auth(client, telegram_user_id=8_820_005, username="oauth_link_owner")
    telegram_id = client.get("/api/v1/me", headers=telegram_headers).json()["id"]

    created = client.post("/api/v1/me/auth/oauth-link/google", headers=telegram_headers)
    assert created.status_code == 200
    assert created.json()["expires_in_seconds"] == 600
    assert created.json()["oauth_url"].startswith("/api/v1/auth/oauth/google/link/start?token=")

    started = client.get(created.json()["oauth_url"], follow_redirects=False)
    assert started.status_code in {302, 307}
    assert started.headers["location"].startswith("https://accounts.example/authorize?")
    state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]

    callback = client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"code": "provider-code", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert callback.headers["location"] == "/app?auth_linked=google"

    me = client.get("/api/v1/me", headers=telegram_headers)
    assert me.json()["id"] == telegram_id
    assert me.json()["auth_providers"] == ["google", "telegram"]

    with get_session_context() as db:
        reused = get_or_create_oauth_user(db, provider="google", raw_claims=google_claims)
        assert reused.id == telegram_id


def test_oauth_link_refuses_identity_owned_by_another_account(client, monkeypatch):
    from fitminiapp_api.api.v1 import auth as auth_api
    from fitminiapp_api.services.oauth_login import get_or_create_oauth_user

    google_claims = {
        "sub": "google-explicit-link-conflict",
        "email": "owned@example.com",
        "email_verified": True,
        "name": "Existing Google Owner",
    }
    with get_session_context() as db:
        existing_google = get_or_create_oauth_user(
            db,
            provider="google",
            raw_claims=google_claims,
        )
        existing_google_id = existing_google.id

    class FakeGoogleClient:
        async def create_authorization_url(self, callback_url):
            state = "fake-google-link-conflict-state"
            return {
                "url": f"https://accounts.example/authorize?state={state}",
                "state": state,
                "code_verifier": "fake-google-link-conflict-code-verifier",
                "redirect_uri": callback_url,
            }

        async def authorize_access_token(self, request):
            del request
            return {"userinfo": google_claims}

    monkeypatch.setattr(settings, "enable_web_auth", True)
    monkeypatch.setattr(settings, "google_oauth_client_id", "google-client")
    monkeypatch.setattr(settings, "google_oauth_client_secret", "google-secret")
    monkeypatch.setattr(
        auth_api,
        "configured_oauth_client",
        lambda provider: FakeGoogleClient() if provider == "google" else None,
    )
    telegram_headers = auth(client, telegram_user_id=8_820_006)
    telegram_id = client.get("/api/v1/me", headers=telegram_headers).json()["id"]

    created = client.post("/api/v1/me/auth/oauth-link/google", headers=telegram_headers)
    started = client.get(created.json()["oauth_url"], follow_redirects=False)
    state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]
    callback = client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"code": "provider-code", "state": state},
        follow_redirects=False,
    )

    assert callback.status_code == 303
    assert (
        callback.headers["location"] == "/app?auth_error=oauth_link_conflict&oauth_provider=google"
    )
    me = client.get("/api/v1/me", headers=telegram_headers).json()
    assert me["id"] == telegram_id
    assert me["auth_providers"] == ["telegram"]
    with get_session_context() as db:
        owner = get_or_create_oauth_user(db, provider="google", raw_claims=google_claims)
        assert owner.id == existing_google_id


def test_alembic_revision_ids_fit_version_table_column():
    versions_dir = Path(__file__).resolve().parents[2] / "backend" / "alembic" / "versions"
    for migration in versions_dir.glob("*.py"):
        source = migration.read_text(encoding="utf-8")
        match = re.search(
            r'^revision(?:\s*:\s*[^=]+)?\s*=\s*["\']([^"\']+)["\']',
            source,
            re.MULTILINE,
        )
        assert match, f"Revision id not found in {migration.name}"
        assert len(match.group(1)) <= 32, f"Revision id is too long in {migration.name}"


def test_tma_navigation_excludes_root_admin_entry():
    source = (
        Path(__file__).resolve().parents[2] / "frontend" / "src" / "app" / "AppShell.tsx"
    ).read_text(encoding="utf-8")
    assert "to: '/coach'" in source
    assert "to: '/admin'" in source
    assert "user.is_coach || user.is_admin" not in source
    assert "visible: Boolean(user?.is_coach)" in source
    assert "visible: Boolean(user?.is_root) && !isMiniApp" in source


def test_client_management_is_consolidated_in_coach_section():
    root = Path(__file__).resolve().parents[2] / "frontend" / "src"
    coach = (root / "pages" / "coach" / "CoachPage.tsx").read_text(encoding="utf-8")
    miniapp = (root / "pages" / "miniapp" / "MiniAppPage.tsx").read_text(encoding="utf-8")
    assert "/api/v1/coach/clients" in coach
    assert "ClientProfileEditor" in coach
    assert "targetTelegramId" in coach
    assert "/api/v1/coach/clients" not in miniapp


def test_exercise_catalog_can_add_exercises_to_program_builder():
    root = Path(__file__).resolve().parents[2] / "frontend" / "src" / "features"
    catalog = (root / "exercises" / "ExerciseCatalog.tsx").read_text(encoding="utf-8")
    builder = (root / "programs" / "ProgramBuilder.tsx").read_text(encoding="utf-8")
    assert "/api/v1/programs/exercises" in catalog
    assert "Добавить упражнение" in builder
    assert "exercise_id" in builder


def test_program_builder_uses_difficulty_and_level_specific_day_limits():
    source = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "src"
        / "features"
        / "programs"
        / "ProgramBuilder.tsx"
    ).read_text(encoding="utf-8")
    assert "difficulty_level" in source or "level" in source
    assert "Добавить день" in source
    assert "prescribed_sets" in source
