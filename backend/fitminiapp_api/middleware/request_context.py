from __future__ import annotations

import logging
import uuid
from time import perf_counter

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from fitminiapp_api.db.performance import (
    begin_sql_metrics,
    current_sql_metrics,
    pool_snapshot,
    reset_sql_metrics,
)
from fitminiapp_api.db.session import engine
from fitminiapp_api.middleware.request_body_limit import REQUEST_ID_PATTERN

logger = logging.getLogger("app.http")

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' https://telegram.org https://mc.yandex.ru https://yastatic.net; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob: https://t.me https://*.telegram.org "
    "https://*.cdn-telegram.org https://mc.yandex.ru; "
    "connect-src 'self' https://app.your-fitness-coach.ru https://mc.yandex.ru "
    "https://mc.yandex.md wss://mc.yandex.ru; "
    "font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
    "child-src blob: https://mc.yandex.ru https://mc.yandex.md; "
    "worker-src 'self'; "
    "frame-src blob: https://mc.yandex.ru https://mc.yandex.md; "
    "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org "
    "https://metrika.yandex.ru https://metrica.yandex.ru"
)


def _request_id(request: Request) -> str:
    current = getattr(request.state, "request_id", "")
    if REQUEST_ID_PATTERN.fullmatch(current):
        return current
    supplied = request.headers.get("x-request-id", "")
    if REQUEST_ID_PATTERN.fullmatch(supplied):
        return supplied
    return str(uuid.uuid4())


def _is_health_probe(path: str) -> bool:
    return path == "/health" or path.startswith("/health/")


def _log_request(request: Request, *, status_code: int, started_at: float, rid: str) -> None:
    raw_path = request.url.path
    if _is_health_probe(raw_path):
        return
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if not isinstance(path, str):
        path = "unmatched"
    sql_metrics = current_sql_metrics()
    logger.info(
        "http_request_completed",
        extra={
            "request_id": rid,
            "method": request.method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round((perf_counter() - started_at) * 1000, 3),
            "sql_query_count": sql_metrics.query_count,
            "sql_duration_ms": round(sql_metrics.duration_ms, 3),
            **pool_snapshot(engine),
        },
    )


class RequestContextMiddleware:
    """X-Request-ID на запрос и в ответ; базовое логирование после обработки."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        rid = _request_id(request)
        request.state.request_id = rid
        started_at = perf_counter()
        sql_metrics_token = begin_sql_metrics()
        status_code: int | None = None

        async def send_with_context(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = rid
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                headers.setdefault(
                    "Permissions-Policy",
                    "camera=(self), microphone=(), geolocation=()",
                )
                headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)

                path = request.url.path
                if path.startswith("/assets/"):
                    headers["Cache-Control"] = "public, max-age=31536000, immutable"
                elif path.startswith("/static/exercise-guides/"):
                    headers["Cache-Control"] = (
                        "public, max-age=2592000, stale-while-revalidate=86400"
                    )
                elif path.startswith("/api/v1/") and not path.startswith("/api/v1/public/"):
                    headers["Cache-Control"] = "no-store, private"
                    headers["Pragma"] = "no-cache"
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        except Exception:
            _log_request(request, status_code=500, started_at=started_at, rid=rid)
            raise
        else:
            path = request.url.path
            if status_code is not None and not path.startswith("/static"):
                _log_request(
                    request,
                    status_code=status_code,
                    started_at=started_at,
                    rid=rid,
                )
        finally:
            reset_sql_metrics(sql_metrics_token)
