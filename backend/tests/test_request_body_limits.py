import asyncio
import json
import re
from collections.abc import Sequence
from pathlib import Path

import pytest

from fitminiapp_api.core.config import settings
from fitminiapp_api.main import app as production_app
from fitminiapp_api.middleware.request_body_limit import (
    AUTH_BODY_LIMIT_BYTES,
    AVATAR_BODY_LIMIT_BYTES,
    DEFAULT_BODY_LIMIT_BYTES,
    PROGRAM_IMPORT_PATH_PREFIX,
    RequestBodyLimitMiddleware,
)


def _run_request(
    *,
    path: str,
    chunks: Sequence[bytes],
    headers: Sequence[tuple[bytes, bytes]] = (),
    application=None,
) -> tuple[list[dict], int]:
    messages = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]
    sent: list[dict] = []
    receive_calls = 0

    async def downstream(scope, receive, send) -> None:
        del scope
        body = bytearray()
        while True:
            message = await receive()
            body.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-length", str(len(body)).encode("ascii"))],
            }
        )
        await send({"type": "http.response.body", "body": bytes(body)})

    async def receive() -> dict:
        nonlocal receive_calls
        receive_calls += 1
        if messages:
            return messages.pop(0)
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": list(headers),
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
    }
    asgi_app = application or RequestBodyLimitMiddleware(downstream)
    asyncio.run(asgi_app(scope, receive, send))
    return sent, receive_calls


def _status(messages: list[dict]) -> int:
    return next(
        message["status"] for message in messages if message["type"] == "http.response.start"
    )


def _response_json(messages: list[dict]) -> dict:
    body = b"".join(
        message.get("body", b"") for message in messages if message["type"] == "http.response.body"
    )
    return json.loads(body)


@pytest.mark.parametrize(
    ("path", "limit"),
    [
        ("/api/v1/auth/dev-login", AUTH_BODY_LIMIT_BYTES),
        ("/api/v1/me/avatar", AVATAR_BODY_LIMIT_BYTES),
        (PROGRAM_IMPORT_PATH_PREFIX, settings.program_import_max_request_bytes),
        ("/api/v1/workouts", DEFAULT_BODY_LIMIT_BYTES),
    ],
)
@pytest.mark.parametrize("offset", [-1, 0])
def test_body_at_or_below_each_limit_passes(path: str, limit: int, offset: int) -> None:
    body = b"x" * (limit + offset)
    messages, calls = _run_request(
        path=path,
        chunks=(body,),
        headers=((b"content-length", str(len(body)).encode("ascii")),),
    )

    assert _status(messages) == 200
    assert calls == 1


@pytest.mark.parametrize(
    ("path", "limit"),
    [
        ("/api/v1/auth/oauth/google/callback", AUTH_BODY_LIMIT_BYTES),
        ("/api/v1/profile", DEFAULT_BODY_LIMIT_BYTES),
    ],
)
def test_declared_body_one_byte_over_limit_is_rejected_without_reading(
    path: str, limit: int
) -> None:
    messages, calls = _run_request(
        path=path,
        chunks=(b"not-read",),
        headers=(
            (b"content-length", str(limit + 1).encode("ascii")),
            (b"x-request-id", b"limit-test-123"),
        ),
    )

    assert _status(messages) == 413
    assert calls == 0
    assert _response_json(messages) == {
        "detail": "Request body too large",
        "code": "request_body_too_large",
        "request_id": "limit-test-123",
    }


def test_unknown_length_stream_stops_as_soon_as_limit_is_exceeded() -> None:
    messages, calls = _run_request(
        path="/api/v1/profile",
        chunks=(b"x" * DEFAULT_BODY_LIMIT_BYTES, b"y", b"secret-tail"),
    )

    assert _status(messages) == 413
    assert calls == 2
    assert _response_json(messages)["code"] == "request_body_too_large"


def test_false_small_content_length_does_not_bypass_streaming_limit() -> None:
    messages, _ = _run_request(
        path="/api/v1/auth/telegram/init",
        chunks=(b"x" * AUTH_BODY_LIMIT_BYTES, b"y"),
        headers=((b"content-length", b"1"),),
    )

    assert _status(messages) == 413


@pytest.mark.parametrize(
    "headers",
    [
        ((b"content-length", b"invalid"),),
        ((b"content-length", b"1"), (b"content-length", b"1")),
        ((b"content-length", b"-1"),),
    ],
)
def test_malformed_content_length_is_rejected(headers: tuple[tuple[bytes, bytes], ...]) -> None:
    messages, calls = _run_request(path="/api/v1/profile", chunks=(b"x",), headers=headers)

    assert _status(messages) == 400
    assert calls == 0
    assert _response_json(messages)["code"] == "invalid_content_length"


def test_real_app_rejects_oversized_auth_json_with_unknown_field(client) -> None:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": 123, "unknown": "x" * AUTH_BODY_LIMIT_BYTES},
        headers={"X-Request-ID": "oversized-auth-test"},
    )

    assert response.status_code == 413
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["x-request-id"] == "oversized-auth-test"
    assert response.json() == {
        "detail": "Request body too large",
        "code": "request_body_too_large",
        "request_id": "oversized-auth-test",
    }


def test_real_app_rejects_chunked_auth_body_without_turning_it_into_500() -> None:
    messages, calls = _run_request(
        path="/api/v1/auth/dev-login",
        chunks=(b"x" * AUTH_BODY_LIMIT_BYTES, b"y"),
        headers=(
            (b"content-type", b"application/json"),
            (b"x-request-id", b"chunked-auth-test"),
        ),
        application=production_app,
    )

    assert _status(messages) == 413
    assert calls == 2
    assert _response_json(messages)["code"] == "request_body_too_large"


def test_edge_and_asgi_limits_share_the_reviewed_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    caddyfile = (root / "deploy" / "Caddyfile.edge").read_text(encoding="utf-8")
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")

    configured_sizes = [int(value) for value in re.findall(r"max_size (\d+)", caddyfile)]
    assert configured_sizes == [
        AVATAR_BODY_LIMIT_BYTES,
        AUTH_BODY_LIMIT_BYTES,
        settings.program_import_max_request_bytes,
        DEFAULT_BODY_LIMIT_BYTES,
    ]
    assert "path /api/v1/programs/imports /api/v1/programs/imports/*" in caddyfile
    assert "reverse_proxy {$YFC_ACTIVE_UPSTREAM}" in caddyfile
    assert "reverse_proxy {$YFC_ASSET_FALLBACK_UPSTREAM}" in caddyfile
    assert 'Cache-Control "no-store, private"' in caddyfile
    assert "reverse_proxy edge:8080" in compose
    assert "http://backend:8000" not in compose.split("  cloudflared:", maxsplit=1)[1]
