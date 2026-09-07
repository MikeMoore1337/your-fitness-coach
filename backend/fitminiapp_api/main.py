import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from fitminiapp_api.api.router import api_router
from fitminiapp_api.core.config import settings
from fitminiapp_api.core.logging_config import configure_logging
from fitminiapp_api.core.rate_limit import limiter
from fitminiapp_api.db.session import SessionLocal, engine
from fitminiapp_api.middleware.canonical_host import redirect_landing_application_requests
from fitminiapp_api.middleware.request_body_limit import RequestBodyLimitMiddleware
from fitminiapp_api.middleware.request_context import RequestContextMiddleware
from fitminiapp_api.models.news import WebArticle
from fitminiapp_api.seo import (
    NOINDEX_ROBOTS,
    public_origin,
    public_page_paths,
    render_frontend_document,
)
from fitminiapp_api.services.web_articles import published_articles

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
EXERCISE_GUIDES_DIR = BACKEND_DIR / "assets" / "exercise-guides"
LOCAL_FRONTEND_DIST_DIR = Path(
    os.environ.get("FRONTEND_DIST_DIR", BACKEND_DIR.parent / "frontend" / "dist")
)
CONTAINER_FRONTEND_DIST_DIR = Path("/app/frontend-dist")
FRONTEND_DIST_DIR = (
    CONTAINER_FRONTEND_DIST_DIR if CONTAINER_FRONTEND_DIST_DIR.exists() else LOCAL_FRONTEND_DIST_DIR
)

logger = logging.getLogger("app")


def _application_sensitive_values() -> tuple[str, ...]:
    return (
        settings.secret_key,
        settings.telegram_bot_token,
        settings.bot_internal_token,
        settings.smtp_password,
        settings.telegram_oauth_client_secret,
        settings.oauth_proxy_url,
        settings.telegram_oauth_proxy_url,
        settings.google_oauth_client_secret,
        settings.yandex_oauth_client_secret,
        settings.apple_oauth_client_secret,
        settings.database_url,
        settings.google_site_verification,
        settings.yandex_verification,
        settings.news_llm_api_key,
        settings.groq_api_key.get_secret_value(),
        settings.hermes_intake_shared_secret.get_secret_value(),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    configure_logging(
        debug=settings.app_debug,
        service="api",
        sensitive_values=_application_sensitive_values(),
    )
    logger.info("application_started")
    try:
        yield
    finally:
        logger.info("application_stopped")


app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
    lifespan=lifespan,
    docs_url=None if settings.app_env == "prod" else "/docs",
    redoc_url=None if settings.app_env == "prod" else "/redoc",
    openapi_url=None if settings.app_env == "prod" else "/openapi.json",
)

if FRONTEND_DIST_DIR.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(FRONTEND_DIST_DIR / "assets")),
        name="frontend-assets",
    )
app.mount(
    "/static/exercise-guides",
    StaticFiles(directory=str(EXERCISE_GUIDES_DIR)),
    name="exercise-guides",
)
app.include_router(api_router)

app.middleware("http")(redirect_landing_application_requests)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(RequestBodyLimitMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.oauth_session_cookie_name,
    max_age=settings.oauth_transaction_ttl_seconds,
    same_site="none" if settings.app_env == "prod" else "lax",
    https_only=settings.app_env == "prod",
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    # HTTPException и RequestValidationError обрабатываются встроенными хендлерами FastAPI,
    # сюда попадают только остальные исключения.
    rid = getattr(request.state, "request_id", None)
    logger.error("unhandled_exception", exc_info=exc, extra={"request_id": rid})
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Внутренняя ошибка сервера",
            "request_id": rid,
        },
        headers={"X-Request-ID": rid} if rid else None,
    )


@app.get("/health")
def health() -> dict[str, str]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.head("/health")
def health_head() -> Response:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return Response(status_code=200)


@app.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready() -> dict[str, str]:
    return health()


def _frontend_pwa_asset(filename: str, media_type: str) -> FileResponse:
    asset = FRONTEND_DIST_DIR / filename
    if not asset.is_file():
        raise HTTPException(status_code=404, detail="Frontend PWA asset unavailable")
    return FileResponse(
        asset,
        media_type=media_type,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/manifest.webmanifest", include_in_schema=False)
def pwa_manifest() -> FileResponse:
    return _frontend_pwa_asset("manifest.webmanifest", "application/manifest+json")


@app.get("/sw.js", include_in_schema=False)
def pwa_service_worker() -> FileResponse:
    return _frontend_pwa_asset("sw.js", "application/javascript")


def _frontend_index(
    path: str,
    *,
    article: WebArticle | None = None,
    articles: tuple[WebArticle, ...] = (),
) -> HTMLResponse:
    index = FRONTEND_DIST_DIR / "index.html"
    if not index.exists():
        raise RuntimeError("Frontend build is missing. Run `npm run build` in frontend/.")
    document, metadata = render_frontend_document(
        index.read_text(encoding="utf-8"), path, article=article, articles=articles
    )
    return HTMLResponse(
        document,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Robots-Tag": metadata.robots,
        },
    )


@app.get("/robots.txt", include_in_schema=False)
def robots_txt() -> PlainTextResponse:
    origin = public_origin()
    content = "\n".join(
        (
            "User-agent: *",
            "Allow: /",
            "Disallow: /api/",
            f"Sitemap: {origin}/sitemap.xml",
            "",
        )
    )
    return PlainTextResponse(content, headers={"Cache-Control": "public, max-age=3600"})


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap() -> Response:
    origin = public_origin()
    urls = [f"{origin}/" if path == "/" else f"{origin}{path}" for path in public_page_paths()]
    with SessionLocal() as db:
        articles = published_articles(db)
    entries = [f"  <url>\n    <loc>{url}</loc>\n  </url>" for url in urls]
    entries.extend(
        "  <url>\n"
        f"    <loc>{origin}/articles/{article.slug}</loc>\n"
        f"    <lastmod>{article.updated_at.date().isoformat()}</lastmod>\n"
        "  </url>"
        for article in articles
        if article.updated_at is not None
    )
    entry_text = "\n".join(entries)
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entry_text}\n"
        "</urlset>\n"
    )
    return Response(
        content=content,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/app")
def miniapp() -> HTMLResponse:
    return _frontend_index("/app")


@app.get("/app/report", include_in_schema=False)
def progress_report_page() -> HTMLResponse:
    return _frontend_index("/app/report")


@app.get("/demo")
def demo_page() -> HTMLResponse:
    return _frontend_index("/demo")


@app.get("/")
def landing_page() -> HTMLResponse:
    return _frontend_index("/")


@app.get("/articles")
def articles_index_page() -> HTMLResponse:
    with SessionLocal() as db:
        articles = tuple(published_articles(db))
    return _frontend_index("/articles", articles=articles)


@app.get("/articles/{slug}")
def article_page(slug: str) -> HTMLResponse:
    with SessionLocal() as db:
        article = db.query(WebArticle).filter(WebArticle.slug == slug).one_or_none()
        if article is None:
            raise HTTPException(
                status_code=404,
                detail="Article not found",
                headers={"X-Robots-Tag": NOINDEX_ROBOTS},
            )
        if article.status in {"archived", "retracted"}:
            raise HTTPException(
                status_code=410,
                detail="Article removed",
                headers={"X-Robots-Tag": NOINDEX_ROBOTS},
            )
        if article.status != "published":
            raise HTTPException(
                status_code=404,
                detail="Article not found",
                headers={"X-Robots-Tag": NOINDEX_ROBOTS},
            )
        articles = tuple(published_articles(db))
    return _frontend_index(f"/articles/{slug}", article=article, articles=articles)


def public_content_page(request: Request) -> HTMLResponse:
    return _frontend_index(request.url.path)


for public_path in public_page_paths():
    if public_path == "/":
        continue
    app.add_api_route(
        public_path,
        public_content_page,
        methods=["GET"],
        include_in_schema=False,
        name=f"public_{public_path.strip('/').replace('/', '_').replace('-', '_')}",
    )


@app.get("/admin")
def admin_page() -> HTMLResponse:
    return _frontend_index("/admin")


@app.get("/coach")
def coach_page() -> HTMLResponse:
    return _frontend_index("/coach")


@app.get("/login")
def login_page() -> HTMLResponse:
    return _frontend_index("/login")


@app.get("/verify-email")
def verify_email_page() -> HTMLResponse:
    return _frontend_index("/verify-email")


@app.get("/reset-password")
def reset_password_page() -> HTMLResponse:
    return _frontend_index("/reset-password")


@app.get("/join/{invite_token}")
def join_coach_page(invite_token: str) -> HTMLResponse:
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,128}", invite_token):
        raise HTTPException(status_code=404, detail="Invite not found")
    return _frontend_index("/join")
