"""Local mobile DEV accepts only server-declared role fixtures."""

from fitminiapp_api.core.config import settings


def test_fixed_dev_logins_only_allow_the_three_roles(client, monkeypatch):
    monkeypatch.setattr(settings, "dev_auth_fixed_accounts_only", True)

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
