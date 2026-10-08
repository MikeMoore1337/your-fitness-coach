from __future__ import annotations

import re
from urllib.parse import urlencode

SAFE_AUTH_PATHS = frozenset({"/app", "/coach", "/admin"})
TRAINER_INTENT_PATH = "/app?trainer_intent=1"
SAFE_JOIN_PATH = re.compile(r"/join/[A-Za-z0-9_-]{20,128}\Z")
AUTH_ERROR_CODES = frozenset(
    {
        "unavailable",
        "denied",
        "invalid_state",
        "conflict",
        "blocked",
        "provider_failure",
    }
)
OAUTH_PROVIDERS = frozenset({"telegram", "google", "yandex", "vk", "apple"})


def safe_auth_next_path(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if (
        normalized in SAFE_AUTH_PATHS
        or normalized == TRAINER_INTENT_PATH
        or SAFE_JOIN_PATH.fullmatch(normalized)
    ):
        return normalized
    return None


def _link_error_code(code: str) -> str:
    return {
        "conflict": "oauth_link_conflict",
        "invalid_state": "oauth_link_invalid_state",
        "denied": "oauth_link_denied",
        "provider_failure": "oauth_link_provider_failure",
        "unavailable": "oauth_link_unavailable",
        "blocked": "oauth_link_blocked",
    }.get(code, "oauth_link_provider_failure")


def auth_error_redirect(
    code: str,
    *,
    next_path: str | None = None,
    provider: str | None = None,
    link: bool = False,
) -> str:
    normalized_code = code if code in AUTH_ERROR_CODES else "provider_failure"
    params = {
        "auth_error": _link_error_code(normalized_code) if link else normalized_code,
    }
    if provider in OAUTH_PROVIDERS:
        params["oauth_provider"] = provider
    if not link:
        params = {
            "next": safe_auth_next_path(next_path) or "/app",
            **params,
        }
    return f"/{'app' if link else 'login'}?{urlencode(params)}"


def account_link_error_redirect(code: str) -> str:
    normalized_code = code if code in AUTH_ERROR_CODES else "provider_failure"
    return f"/app?{urlencode({'auth_error': normalized_code})}"
