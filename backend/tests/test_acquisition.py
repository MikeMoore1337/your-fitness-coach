from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.acquisition import FirstTouchAttribution
from fitminiapp_api.schemas.acquisition import FirstTouchAttributionRequest


def _login(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": False},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "first_touch_source": "utm",
        "first_touch_medium": "cpc",
        "first_touch_campaign": "autumn",
        "first_landing_path": "/public/programs/strength",
        "first_referrer": "https://www.google.com/search",
        "first_touch_at": "2026-09-13T09:30:00+03:00",
        "utm_source": "google",
        "utm_medium": "cpc",
        "utm_campaign": "autumn",
        "utm_content": "hero",
        "utm_term": "fitness",
    }
    payload.update(overrides)
    return payload


def test_first_touch_request_is_strict_and_privacy_safe() -> None:
    request = FirstTouchAttributionRequest.model_validate(_payload())
    assert request.first_touch_at == datetime(
        2026, 9, 13, 9, 30, tzinfo=timezone(timedelta(hours=3))
    )

    with pytest.raises(ValidationError):
        FirstTouchAttributionRequest.model_validate(_payload(extra="unexpected"))
    with pytest.raises(ValidationError):
        FirstTouchAttributionRequest.model_validate(_payload(first_landing_path="/public?email=a"))
    with pytest.raises(ValidationError):
        FirstTouchAttributionRequest.model_validate(
            _payload(first_referrer="https://example.test/path?email=a@example.test")
        )
    with pytest.raises(ValidationError):
        FirstTouchAttributionRequest.model_validate(_payload(first_touch_at="2026-09-13T09:30:00"))
    with pytest.raises(ValidationError):
        FirstTouchAttributionRequest.model_validate(_payload(utm_source="a@example.test"))


def test_first_touch_is_authenticated_immutable_and_exported(client) -> None:
    headers = _login(client, 9_824_001)
    first = client.post("/api/v1/me/acquisition", headers=headers, json=_payload())
    assert first.status_code == 204

    replay = client.post(
        "/api/v1/me/acquisition",
        headers=headers,
        json=_payload(
            first_touch_source="direct",
            first_touch_medium="none",
            first_touch_campaign=None,
            first_referrer=None,
            utm_source=None,
            utm_medium=None,
            utm_campaign=None,
            utm_content=None,
            utm_term=None,
        ),
    )
    assert replay.status_code == 204

    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    current = client.get("/api/v1/me", headers=headers)
    assert current.status_code == 200
    assert current.json()["has_food_history"] is False
    with get_session_context() as db:
        row = db.get(FirstTouchAttribution, user_id)
        assert row is not None
        assert row.first_touch_source == "utm"
        assert row.first_landing_path == "/public/programs/strength"
        assert row.first_referrer == "https://www.google.com/search"

    export = client.get("/api/v1/me/export", headers=headers)
    assert export.status_code == 200
    exported = export.json()["first_touch_attribution"]
    assert exported["first_touch_source"] == "utm"
    assert exported["first_landing_path"] == "/public/programs/strength"
    assert "user_id" not in exported

    deleted = client.request(
        "DELETE",
        "/api/v1/me/account",
        headers=headers,
        json={"confirmation": "DELETE"},
    )
    assert deleted.status_code == 204
    with get_session_context() as db:
        assert db.get(FirstTouchAttribution, user_id) is None


def test_first_touch_requires_authentication_and_rejects_unknown_payload(client) -> None:
    unauthenticated = client.post("/api/v1/me/acquisition", json=_payload())
    assert unauthenticated.status_code == 401

    headers = _login(client, 9_824_002)
    invalid = client.post(
        "/api/v1/me/acquisition",
        headers=headers,
        json=_payload(email="user@example.test"),
    )
    assert invalid.status_code == 422
