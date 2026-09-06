from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Final

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from fitminiapp_api.core.config import settings

DEFAULT_BODY_LIMIT_BYTES: Final = 1024 * 1024
AUTH_BODY_LIMIT_BYTES: Final = 64 * 1024
AVATAR_BODY_LIMIT_BYTES: Final = 6 * 1024 * 1024
PROGRAM_IMPORT_PATH_PREFIX: Final = "/api/v1/programs/imports"
AUTH_PATH_PREFIX: Final = "/api/v1/auth/"
AVATAR_PATH: Final = "/api/v1/me/avatar"
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")

logger = logging.getLogger("app.http")


def _body_limit(path: str) -> int:
    if path == AUTH_PATH_PREFIX.rstrip("/") or path.startswith(AUTH_PATH_PREFIX):
        return AUTH_BODY_LIMIT_BYTES
    if path == AVATAR_PATH:
        return AVATAR_BODY_LIMIT_BYTES
    if path == PROGRAM_IMPORT_PATH_PREFIX or path.startswith(f"{PROGRAM_IMPORT_PATH_PREFIX}/"):
        return settings.program_import_max_request_bytes
    return DEFAULT_BODY_LIMIT_BYTES


def _request_id(scope: Scope) -> str:
    state = scope.setdefault("state", {})
    current = state.get("request_id")
    if isinstance(current, str) and REQUEST_ID_PATTERN.fullmatch(current):
        return current
    for name, value in scope.get("headers", ()):
        if name.lower() == b"x-request-id":
            supplied = value.decode("latin-1")
            if REQUEST_ID_PATTERN.fullmatch(supplied):
                state["request_id"] = supplied
                return supplied
            break
    generated = str(uuid.uuid4())
    state["request_id"] = generated
    return generated


def _declared_content_length(scope: Scope) -> int | None:
    values = [
        value.strip()
        for name, value in scope.get("headers", ())
        if name.lower() == b"content-length"
    ]
    if not values:
        return None
    if len(values) != 1 or not values[0] or not values[0].isdigit():
        raise ValueError("invalid_content_length")
    return int(values[0])


async def _send_error(
    send: Send,
    *,
    status_code: int,
    code: str,
    detail: str,
    request_id: str,
) -> None:
    content = json.dumps(
        {"detail": detail, "code": code, "request_id": request_id},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(content)).encode("ascii")),
        (b"cache-control", b"no-store, private"),
        (b"x-request-id", request_id.encode("ascii")),
    ]
    await send({"type": "http.response.start", "status": status_code, "headers": headers})
    await send({"type": "http.response.body", "body": content})


class RequestBodyLimitMiddleware:
    """Bound and replay request bodies before downstream parsing."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = _body_limit(scope.get("path", ""))
        request_id = _request_id(scope)
        try:
            declared_length = _declared_content_length(scope)
        except ValueError:
            logger.warning(
                "http_request_rejected",
                extra={
                    "request_id": request_id,
                    "method": scope.get("method", ""),
                    "status_code": 400,
                    "reason": "invalid_content_length",
                    "body_limit_bytes": limit,
                },
            )
            await _send_error(
                send,
                status_code=400,
                code="invalid_content_length",
                detail="Invalid Content-Length header",
                request_id=request_id,
            )
            return

        if declared_length is not None and declared_length > limit:
            logger.warning(
                "http_request_rejected",
                extra={
                    "request_id": request_id,
                    "method": scope.get("method", ""),
                    "status_code": 413,
                    "reason": "request_body_too_large",
                    "body_limit_bytes": limit,
                },
            )
            await _send_error(
                send,
                status_code=413,
                code="request_body_too_large",
                detail="Request body too large",
                request_id=request_id,
            )
            return

        received = 0
        buffered_messages: list[Message] = []
        while True:
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    logger.warning(
                        "http_request_rejected",
                        extra={
                            "request_id": request_id,
                            "method": scope.get("method", ""),
                            "status_code": 413,
                            "reason": "request_body_too_large",
                            "body_limit_bytes": limit,
                        },
                    )
                    await _send_error(
                        send,
                        status_code=413,
                        code="request_body_too_large",
                        detail="Request body too large",
                        request_id=request_id,
                    )
                    return
                buffered_messages.append(message)
                if not message.get("more_body", False):
                    break
            elif message["type"] == "http.disconnect":
                buffered_messages.append(message)
                break

        replay_index = 0

        async def receive_replay() -> Message:
            nonlocal replay_index
            if replay_index < len(buffered_messages):
                message = buffered_messages[replay_index]
                replay_index += 1
                return message
            return {"type": "http.disconnect"}

        await self.app(scope, receive_replay, send)
