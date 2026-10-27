"""Local mobile DEV accepts only server-declared role fixtures."""

import pytest

from fitminiapp_api.core.config import settings


def test_fixed_dev_logins_only_allow_the_three_roles(client, monkeypatch):
    monkeypatch.setattr(settings, "dev_auth_fixed_accounts_only", True)
    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "1001")

    fixtures = (
        (2001, False, False),
        (1002, True, False),
        (1001, True, True),
    )
    for user_id, coach, admin in fixtures:
        login = client.post(
            "/api/v1/auth/dev-login",
            json={"telegram_user_id": user_id, "is_coach": coach, "is_admin": admin},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]
        me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["is_coach"] is coach
        assert me.json()["is_root"] is (user_id == 1001)

    disallowed = (
        (9000000, True, True),
        (2001, True, True),
        (1002, True, True),
        (1001, False, False),
    )
    for user_id, coach, admin in disallowed:
        login = client.post(
            "/api/v1/auth/dev-login",
            json={"telegram_user_id": user_id, "is_coach": coach, "is_admin": admin},
        )
        assert login.status_code == 403


def test_fixed_dev_logins_disable_telegram_endpoint(client, monkeypatch):
    monkeypatch.setattr(settings, "dev_auth_fixed_accounts_only", True)
    result = client.post("/api/v1/auth/telegram/init", json={"init_data": "invalid"})
    assert result.status_code == 403


@pytest.mark.parametrize("method", ["POST", "DELETE"])
@pytest.mark.parametrize(
    "user_id,coach,admin", [(2001, False, False), (1002, True, False), (1001, True, True)]
)
def test_fixed_dev_roles_cannot_change_through_profile(
    client, monkeypatch, method, user_id, coach, admin
):
    monkeypatch.setattr(settings, "dev_auth_fixed_accounts_only", True)
    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "1001")
    login = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": user_id, "is_coach": coach, "is_admin": admin},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = client.request(
        method,
        "/api/v1/me/trainer-capability",
        json={"accepted_terms": True} if method == "POST" else None,
        headers=headers,
    )
    assert response.status_code == 403
    me = client.get("/api/v1/me", headers=headers).json()
    assert (me["is_coach"], me["is_root"]) == (coach, admin)
    state = client.get("/api/v1/me/trainer-capability", headers=headers).json()
    assert state["can_disable"] is False


@pytest.mark.parametrize("target_id,coach", [(2001, False), (1002, True)])
def test_fixed_dev_roles_cannot_change_through_root(client, monkeypatch, target_id, coach):
    monkeypatch.setattr(settings, "dev_auth_fixed_accounts_only", True)
    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "1001")
    target = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": target_id, "is_coach": coach},
    )
    target_headers = {"Authorization": f"Bearer {target.json()['access_token']}"}
    user_id = client.get("/api/v1/me", headers=target_headers).json()["id"]
    root = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": 1001, "is_coach": True, "is_admin": True},
    )
    response = client.patch(
        f"/api/v1/admin/users/{user_id}/trainer-capability",
        json={"is_active": not coach, "reason": "support_request"},
        headers={"Authorization": f"Bearer {root.json()['access_token']}"},
    )
    assert response.status_code == 403
    assert client.get("/api/v1/me", headers=target_headers).json()["is_coach"] is coach
