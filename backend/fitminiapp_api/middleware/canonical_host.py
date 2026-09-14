from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from fitminiapp_api.core.config import settings
from fitminiapp_api.seo import (
    canonical_landing_domain,
    frontend_host,
    public_origin,
    public_page_paths,
)

APPLICATION_PATHS = frozenset(
    {
        "/app",
        "/admin",
        "/coach",
        "/login",
        "/verify-email",
        "/reset-password",
    }
)
# Public pages use relative API URLs, so redirecting /api/* to the app origin
# would turn a same-origin browser request into a cross-origin response.
APPLICATION_PATH_PREFIXES = ("/join/",)
PUBLIC_PATHS = frozenset(public_page_paths())


def _is_application_path(path: str) -> bool:
    return path.rstrip("/") in APPLICATION_PATHS or path.startswith(APPLICATION_PATH_PREFIXES)


def _redirect_url(origin: str, request: Request, *, path: str | None = None) -> str:
    target = f"{origin.rstrip('/')}{path if path is not None else request.url.path}"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return target


async def redirect_landing_application_requests(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Keep browser sessions on the canonical application origin."""

    landing_domain = canonical_landing_domain()
    request_host = (request.url.hostname or "").lower().rstrip(".")
    if not landing_domain:
        return await call_next(request)

    normalized_path = request.url.path.rstrip("/") or "/"
    if normalized_path in PUBLIC_PATHS and request.url.path != normalized_path:
        return RedirectResponse(
            _redirect_url(public_origin(), request, path=normalized_path),
            status_code=308,
        )

    if request_host in {landing_domain, f"www.{landing_domain}"} and _is_application_path(
        request.url.path
    ):
        return RedirectResponse(
            _redirect_url(settings.frontend_base_url, request, path=normalized_path),
            status_code=308,
        )

    public_or_discovery_path = normalized_path in PUBLIC_PATHS or request.url.path in {
        "/robots.txt",
        "/sitemap.xml",
    }
    if public_or_discovery_path and request_host in {
        frontend_host(),
        f"www.{landing_domain}",
    }:
        return RedirectResponse(_redirect_url(public_origin(), request), status_code=308)
    return await call_next(request)
