"""Read-only (except DEV token issuance) local Windows role smoke for #1237.

Usage: py -3.14 scripts/verify_dev_roles.py
Only sends requests to 127.0.0.1:18080. Never prints access tokens.
"""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:18080"


def _request(path: str, *, token: str | None = None, payload: dict | None = None) -> tuple[int, object]:
    if not path.startswith("/") or "//" in path:
        raise ValueError("only same-origin relative paths are supported")
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(BASE + path, data=data, headers=headers)
    try:
        with urlopen(request, timeout=8) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, {}


def _login(telegram_id: int, *, coach: bool, admin: bool = False) -> str:
    status, data = _request(
        "/api/v1/auth/dev-login",
        payload={"telegram_user_id": telegram_id, "is_coach": coach, "is_admin": admin},
    )
    if status != 200 or not isinstance(data, dict):
        raise AssertionError(f"fixed DEV identity {telegram_id} failed: HTTP {status}")
    token = data.get("access_token")
    if not isinstance(token, str) or not token:
        raise AssertionError(f"fixed DEV identity {telegram_id} has no access token")
    return token


def _expect_status(path: str, token: str | None, expected: int) -> object:
    status, data = _request(path, token=token)
    if status != expected:
        raise AssertionError(f"{path}: expected HTTP {expected}, got HTTP {status}")
    return data


def main() -> int:
    status, ready = _request("/health/ready")
    if status != 200 or ready != {"status": "ok"}:
        raise AssertionError("isolated YFC DEV is not ready")

    client = _login(2001, coach=False)
    trainer = _login(1002, coach=True)
    root = _login(1001, coach=True, admin=True)
    for name, token, expected_coach, expected_root in (
        ("client", client, False, False),
        ("trainer", trainer, True, False),
        ("root", root, True, True),
    ):
        me = _expect_status("/api/v1/me", token, 200)
        if not isinstance(me, dict):
            raise AssertionError(f"{name}: malformed /me response")
        if (me.get("is_coach"), me.get("is_root")) != (expected_coach, expected_root):
            raise AssertionError(f"{name}: unexpected server-owned role")

    _expect_status("/api/v1/coach/clients", client, 403)
    visible = _expect_status("/api/v1/coach/clients", trainer, 200)
    if not isinstance(visible, list) or len(visible) < 3:
        raise AssertionError("trainer cannot see three seeded DEV clients")

    admin_path = "/api/v1/admin/users?q=2001"
    _expect_status(admin_path, None, 401)
    _expect_status(admin_path, client, 403)
    _expect_status(admin_path, trainer, 403)
    _expect_status(admin_path, root, 200)

    status, _ = _request(
        "/api/v1/auth/dev-login",
        payload={"telegram_user_id": 2002, "is_coach": False, "is_admin": False},
    )
    if status != 403:
        raise AssertionError("noninteractive extra client can log in")
    status, _ = _request(
        "/api/v1/auth/dev-login",
        payload={"telegram_user_id": 2001, "is_coach": True, "is_admin": True},
    )
    if status != 403:
        raise AssertionError("client role escalation was not blocked")

    print("PASS | DEV /health/ready | 200")
    print("PASS | Client 2001 / Trainer 1002 / Root 1001")
    print("PASS | Trainer has >=3 linked synthetic clients")
    print("PASS | Client cannot use trainer or Root functions")
    print("PASS | Trainer cannot use Root functions")
    print("PASS | Unauthorized and escalated DEV logins denied")
    print("LOCAL_DEV_ROLE_SMOKE=PASS | no tokens printed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, URLError, TimeoutError) as exc:
        print(f"LOCAL_DEV_ROLE_SMOKE=FAIL | {type(exc).__name__}: {exc}")
        raise SystemExit(1) from None
