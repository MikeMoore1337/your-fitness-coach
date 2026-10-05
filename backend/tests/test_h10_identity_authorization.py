import jwt

from fitminiapp_api.core.config import settings
from fitminiapp_api.services.jwt import ALGORITHM, decode_token


def test_access_token_without_jti_is_rejected(client):
    login = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": 9_109_001, "is_coach": False},
    )
    assert login.status_code == 200

    access_token = login.json()["access_token"]
    payload = decode_token(access_token, expected_type="access")
    payload.pop("jti")
    token_without_jti = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)

    response = client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {token_without_jti}"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Сессия недействительна или истекла"}
