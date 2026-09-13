from __future__ import annotations

import html
import json
import os
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import cast
from urllib.parse import quote, urlparse

from fitminiapp_api.core.config import settings
from fitminiapp_api.models.news import WebArticle
from fitminiapp_api.services.public_exercises import public_exercise

INDEX_ROBOTS = "index, follow"
NOINDEX_ROBOTS = "noindex, nofollow"
SOCIAL_IMAGE_PATH = "/assets/brand/yfc-social-preview.png"
SOCIAL_IMAGE_ALT = "Your Fitness Coach — тренировки, питание и прогресс в браузере и Telegram"
ARTICLE_INDEX_TITLE = "Статьи о тренировках, питании и прогрессе — Your Fitness Coach"
ARTICLE_INDEX_DESCRIPTION = (
    "Понятные статьи о тренировках, питании, спортивном питании и прогрессе: "
    "источники, ограничения и практический смысл без громких обещаний."
)
_PUBLIC_FALLBACK_PATTERN = re.compile(
    r"<!-- public-fallback-start -->.*?<!-- public-fallback-end -->",
    re.DOTALL,
)
_YANDEX_METRICA_NOSCRIPT = (
    '<noscript><div><img src="https://mc.yandex.ru/watch/112530718" '
    'style="position:absolute; left:-9999px;" alt="" /></div></noscript>'
)


@dataclass(frozen=True)
class SeoMetadata:
    title: str
    description: str
    robots: str
    canonical_url: str | None = None
    og_description: str | None = None
    og_type: str = "website"
    structured_data: tuple[dict[str, object], ...] = ()


def _public_content_path() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    configured_dist = Path(os.environ.get("FRONTEND_DIST_DIR", project_root / "frontend" / "dist"))
    candidates = (
        Path("/app/frontend-dist/publicContent.json"),
        configured_dist / "publicContent.json",
        project_root / "frontend" / "src" / "content" / "publicContent.json",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError("Public content manifest is missing from the frontend build")


def _required_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Public content field {field!r} must be a non-empty string")
    return value


@lru_cache
def public_pages() -> tuple[dict[str, object], ...]:
    payload = json.loads(_public_content_path().read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("pages"), list):
        raise RuntimeError("Public content manifest must contain a pages array")
    pages: list[dict[str, object]] = []
    seen_paths: set[str] = set()
    seen_ids: set[str] = set()
    for raw_page in payload["pages"]:
        if not isinstance(raw_page, dict):
            raise RuntimeError("Every public content page must be an object")
        page = cast(dict[str, object], raw_page)
        path = _required_string(page.get("path"), field="path")
        if not path.startswith("/") or (path != "/" and path.endswith("/")):
            raise RuntimeError(f"Public content path is not canonical: {path!r}")
        if path in seen_paths:
            raise RuntimeError(f"Duplicate public content path: {path!r}")
        for field in ("kind", "title", "description", "ogDescription", "heading", "intro"):
            _required_string(page.get(field), field=field)
        content_id = page.get("id")
        if isinstance(content_id, str):
            if content_id in seen_ids:
                raise RuntimeError(f"Duplicate public content id: {content_id!r}")
            seen_ids.add(content_id)
        status = page.get("status", "published")
        if status not in {"draft", "review", "published", "archived"}:
            raise RuntimeError(f"Unsupported public content status: {status!r}")
        kind = page["kind"]
        if kind in {"guide", "exercise", "exercise-index"}:
            _required_string(content_id, field="id")
            _required_string(page.get("slug"), field="slug")
            if "status" not in page:
                raise RuntimeError(f"Public content {content_id!r} must declare a status")
        if kind == "guide":
            for field in ("published", "updated", "reviewed"):
                _required_string(page.get(field), field=field)
            for field in ("tags", "appContexts", "sections", "sources"):
                if not isinstance(page.get(field), list) or not page[field]:
                    raise RuntimeError(
                        f"Public guide {content_id!r} field {field!r} must be a non-empty list"
                    )
            author = page.get("author")
            if not isinstance(author, dict):
                raise RuntimeError(
                    f"Public guide {content_id!r} field 'author' must identify an editor"
                )
            reviewer = page.get("reviewer")
            if reviewer is not None and not isinstance(reviewer, dict):
                raise RuntimeError(
                    f"Public guide {content_id!r} field 'reviewer' must identify an editor or be null"
                )
            for field, editor in (("author", author), ("reviewer", reviewer)):
                if not isinstance(editor, dict):
                    continue
                _required_string(editor.get("name"), field=f"{field}.name")
                editor_type = _required_string(editor.get("type"), field=f"{field}.type")
                if editor_type not in {"Organization", "Person"}:
                    raise RuntimeError(
                        f"Public content field '{field}.type' must be Organization or Person"
                    )
        seen_paths.add(path)
        pages.append(page)
    return tuple(pages)


def public_page_paths() -> tuple[str, ...]:
    return tuple(
        _required_string(page["path"], field="path")
        for page in public_pages()
        if page.get("status", "published") == "published"
    )


def public_sitemap_paths() -> tuple[str, ...]:
    """Return the published manifest paths plus the published article index."""

    return tuple(dict.fromkeys((*public_page_paths(), "/articles")))


def public_page_lastmod(path: str) -> str | None:
    """Return a source-controlled last modification date when the manifest has one."""

    page = public_page_for_path(path)
    raw_updated = page.get("updated") if page else None
    if not isinstance(raw_updated, str):
        return None
    try:
        return date.fromisoformat(raw_updated).isoformat()
    except ValueError:
        return None


def canonical_landing_domain() -> str:
    """Return the configured public host without its non-canonical www prefix."""

    return settings.landing_domain.strip().lower().rstrip(".").removeprefix("www.")


def public_origin() -> str:
    """Return the one production origin allowed in the public search surface."""

    landing_domain = canonical_landing_domain()
    if landing_domain:
        return f"https://{landing_domain}"
    return settings.frontend_base_url.rstrip("/")


def frontend_host() -> str:
    return (urlparse(settings.frontend_base_url).hostname or "").lower().rstrip(".")


def public_page_for_path(path: str) -> dict[str, object] | None:
    return next(
        (
            page
            for page in public_pages()
            if page.get("status", "published") == "published"
            and _required_string(page["path"], field="path") == path
        ),
        None,
    )


def _absolute_public_url(path: str) -> str:
    return f"{public_origin()}/" if path == "/" else f"{public_origin()}{path}"


def public_article_cta_url(destination: object) -> str:
    """Resolve the allowlisted article CTA destinations for server-rendered HTML."""

    if destination == "landing":
        return _absolute_public_url("/")
    if destination == "tma":
        username = settings.telegram_bot_username.strip().removeprefix("@")
        if not username:
            username = "your_fitness_coach_bot"
        return f"https://t.me/{quote(username, safe='')}?startapp"
    return f"{settings.frontend_base_url.rstrip('/')}/app"


def _safe_https_url(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if any(ord(character) < 0x20 for character in normalized):
        return None
    parsed = urlparse(normalized)
    if parsed.scheme.lower() != "https" or not parsed.netloc or parsed.username or parsed.password:
        return None
    return normalized


def _breadcrumbs_schema(page: dict[str, object]) -> dict[str, object] | None:
    raw_breadcrumbs = page.get("breadcrumbs")
    if not isinstance(raw_breadcrumbs, list) or len(raw_breadcrumbs) < 2:
        return None
    items: list[dict[str, object]] = []
    for position, raw_item in enumerate(raw_breadcrumbs, start=1):
        if not isinstance(raw_item, dict):
            raise RuntimeError("Public content breadcrumbs must be objects")
        item = cast(dict[str, object], raw_item)
        item_path = _required_string(item.get("path"), field="breadcrumbs.path")
        items.append(
            {
                "@type": "ListItem",
                "position": position,
                "name": _required_string(item.get("label"), field="breadcrumbs.label"),
                "item": _absolute_public_url(item_path),
            }
        )
    return {"@type": "BreadcrumbList", "itemListElement": items}


def _structured_data_for_page(page: dict[str, object]) -> tuple[dict[str, object], ...]:
    kind = _required_string(page["kind"], field="kind")
    path = _required_string(page["path"], field="path")
    canonical_url = _absolute_public_url(path)
    description = _required_string(page["description"], field="description")
    if kind == "landing":
        return (
            {
                "@context": "https://schema.org",
                "@graph": [
                    {
                        "@type": "Organization",
                        "name": "Your Fitness Coach",
                        "url": canonical_url,
                    },
                    {
                        "@type": "WebSite",
                        "name": "Your Fitness Coach",
                        "url": canonical_url,
                    },
                    {
                        "@type": "SoftwareApplication",
                        "name": "Your Fitness Coach",
                        "applicationCategory": "HealthApplication",
                        "operatingSystem": "Web, Telegram",
                        "url": canonical_url,
                        "description": description,
                    },
                ],
            },
        )

    if kind == "guide":
        author = page.get("author")
        author_schema: dict[str, object] | None = None
        if isinstance(author, dict):
            typed_author = cast(dict[str, object], author)
            author_schema = {
                "@type": _required_string(typed_author.get("type"), field="author.type"),
                "name": _required_string(typed_author.get("name"), field="author.name"),
            }
        main_entity: dict[str, object] = {
            "@type": "Article",
            "headline": _required_string(page["heading"], field="heading"),
            "description": description,
            "mainEntityOfPage": canonical_url,
            "publisher": {"@type": "Organization", "name": "Your Fitness Coach"},
        }
        if author_schema:
            main_entity["author"] = author_schema
        if isinstance(page.get("updated"), str):
            main_entity["dateModified"] = page["updated"]
        if isinstance(page.get("published"), str):
            main_entity["datePublished"] = page["published"]
    else:
        main_entity = {
            "@type": "CollectionPage" if kind == "knowledge-index" else "WebPage",
            "name": _required_string(page["heading"], field="heading"),
            "description": description,
            "url": canonical_url,
            "isPartOf": {
                "@type": "WebSite",
                "name": "Your Fitness Coach",
                "url": _absolute_public_url("/"),
            },
        }

    graph = [main_entity]
    breadcrumbs = _breadcrumbs_schema(page)
    if breadcrumbs:
        graph.append(breadcrumbs)
    return ({"@context": "https://schema.org", "@graph": graph},)


def metadata_for_path(path: str) -> SeoMetadata:
    """Keep indexability decisions in one place for browser and crawler responses."""

    page = public_page_for_path(path)
    if page:
        return SeoMetadata(
            title=_required_string(page["title"], field="title"),
            description=_required_string(page["description"], field="description"),
            robots=INDEX_ROBOTS,
            canonical_url=_absolute_public_url(path),
            og_description=_required_string(page["ogDescription"], field="ogDescription"),
            og_type="article" if page["kind"] == "guide" else "website",
            structured_data=_structured_data_for_page(page),
        )
    return SeoMetadata(
        title="Your Fitness Coach",
        description="Личный интерфейс Your Fitness Coach.",
        robots=NOINDEX_ROBOTS,
    )


def metadata_for_articles() -> SeoMetadata:
    return SeoMetadata(
        title=ARTICLE_INDEX_TITLE,
        description=ARTICLE_INDEX_DESCRIPTION,
        robots=INDEX_ROBOTS,
        canonical_url=_absolute_public_url("/articles"),
        og_description=ARTICLE_INDEX_DESCRIPTION,
        structured_data=(
            {
                "@context": "https://schema.org",
                "@type": "CollectionPage",
                "name": ARTICLE_INDEX_TITLE,
                "description": ARTICLE_INDEX_DESCRIPTION,
                "url": _absolute_public_url("/articles"),
                "isPartOf": {
                    "@type": "WebSite",
                    "name": "Your Fitness Coach",
                    "url": _absolute_public_url("/"),
                },
            },
        ),
    )


def metadata_for_article(article: WebArticle) -> SeoMetadata:
    if article.status != "published" or article.published_at is None or article.updated_at is None:
        return metadata_for_path("/articles")
    canonical_url = _absolute_public_url(f"/articles/{article.slug}")
    author = article.author if isinstance(article.author, dict) else {}
    editor = article.editor if isinstance(article.editor, dict) else {}
    reviewer = article.domain_reviewer if isinstance(article.domain_reviewer, dict) else None
    entity: dict[str, object] = {
        "@type": "Article",
        "headline": article.title,
        "description": article.description,
        "url": canonical_url,
        "mainEntityOfPage": canonical_url,
        "datePublished": article.published_at.date().isoformat(),
        "dateModified": article.updated_at.date().isoformat(),
        "author": {
            "@type": author.get("type", "Organization"),
            "name": author.get("name", "Your Fitness Coach"),
        },
        "editor": {
            "@type": editor.get("type", "Organization"),
            "name": editor.get("name", "YFC Editorial Desk"),
        },
        "publisher": {"@type": "Organization", "name": "Your Fitness Coach"},
    }
    if reviewer:
        entity["reviewedBy"] = {
            "@type": reviewer.get("type", "Organization"),
            "name": reviewer.get("name", "YFC Domain Review"),
        }
    return SeoMetadata(
        title=article.title,
        description=article.description,
        robots=INDEX_ROBOTS,
        canonical_url=canonical_url,
        og_description=article.description,
        og_type="article",
        structured_data=(
            {
                "@context": "https://schema.org",
                **entity,
            },
        ),
    )


def render_metadata(metadata: SeoMetadata) -> str:
    """Render only server-controlled metadata; no user content is inserted here."""

    tags = [
        f"<title>{html.escape(metadata.title)}</title>",
        f'<meta name="description" content="{html.escape(metadata.description, quote=True)}" />',
        f'<meta name="robots" content="{metadata.robots}" />',
        f'<meta name="yandex" content="{metadata.robots}" />',
    ]
    if metadata.canonical_url:
        canonical = html.escape(metadata.canonical_url, quote=True)
        social_image = html.escape(_absolute_public_url(SOCIAL_IMAGE_PATH), quote=True)
        social_image_alt = html.escape(SOCIAL_IMAGE_ALT, quote=True)
        tags.extend(
            [
                f'<link rel="canonical" href="{canonical}" />',
                f'<meta property="og:title" content="{html.escape(metadata.title, quote=True)}" />',
                '<meta property="og:description" content="'
                f'{html.escape(metadata.og_description or metadata.description, quote=True)}" />',
                f'<meta property="og:type" content="{metadata.og_type}" />',
                f'<meta property="og:url" content="{canonical}" />',
                '<meta property="og:site_name" content="Your Fitness Coach" />',
                '<meta property="og:locale" content="ru_RU" />',
                f'<meta property="og:image" content="{social_image}" />',
                '<meta property="og:image:type" content="image/png" />',
                '<meta property="og:image:width" content="1200" />',
                '<meta property="og:image:height" content="630" />',
                f'<meta property="og:image:alt" content="{social_image_alt}" />',
                '<meta name="twitter:card" content="summary_large_image" />',
                f'<meta name="twitter:title" content="{html.escape(metadata.title, quote=True)}" />',
                '<meta name="twitter:description" content="'
                f'{html.escape(metadata.og_description or metadata.description, quote=True)}" />',
                f'<meta name="twitter:image" content="{social_image}" />',
                f'<meta name="twitter:image:alt" content="{social_image_alt}" />',
            ]
        )
    for item in metadata.structured_data:
        payload = json.dumps(item, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        tags.append(f'<script type="application/ld+json">{payload}</script>')
    return "\n    ".join(tags)


def _link_markup(item: dict[str, object]) -> str:
    path = html.escape(_required_string(item.get("path"), field="link.path"), quote=True)
    label = html.escape(_required_string(item.get("label"), field="link.label"))
    description = item.get("description")
    detail = f"<span>{html.escape(description)}</span>" if isinstance(description, str) else ""
    return f'<li><a href="{path}">{label}</a>{detail}</li>'


def _article_person_markup(label: str, person: object) -> str:
    if not isinstance(person, dict):
        return ""
    name = person.get("name")
    if not isinstance(name, str) or not name.strip():
        return ""
    return f"<dt>{html.escape(label)}</dt><dd>{html.escape(name)}</dd>"


def render_article_fallback(article: WebArticle, related: tuple[WebArticle, ...] = ()) -> str:
    """Render published article meaningfully before React hydration."""

    published_at = article.published_at
    updated_at = article.updated_at
    if article.status != "published" or published_at is None or updated_at is None:
        return ""
    parts = [
        '<main class="seo-fallback seo-article-fallback">',
        '<nav aria-label="Публичные разделы"><a href="/">Главная</a> '
        '<a href="/articles">Статьи</a></nav>',
        f'<p class="landing-kicker">{html.escape(article.article_kind)}</p>',
        f"<h1>{html.escape(article.title)}</h1>",
        f'<p class="public-hero__lead">{html.escape(article.lead)}</p>',
        '<dl class="public-guide-meta">',
        _article_person_markup("Автор", article.author),
        _article_person_markup("Редактор", article.editor),
        _article_person_markup("Проверил", article.domain_reviewer),
        f'<dt>Опубликовано</dt><dd><time datetime="{published_at.date().isoformat()}">'
        f"{published_at.date().isoformat()}</time></dd>",
        f'<dt>Обновлено</dt><dd><time datetime="{updated_at.date().isoformat()}">'
        f"{updated_at.date().isoformat()}</time></dd>",
        "</dl>",
    ]
    for raw_section in article.body_sections:
        if not isinstance(raw_section, dict):
            continue
        heading = raw_section.get("heading")
        paragraphs = raw_section.get("paragraphs", [])
        if not isinstance(heading, str) or not isinstance(paragraphs, list):
            continue
        parts.append(f"<section><h2>{html.escape(heading)}</h2>")
        parts.extend(
            f"<p>{html.escape(value)}</p>" for value in paragraphs if isinstance(value, str)
        )
        points = raw_section.get("points", [])
        if isinstance(points, list):
            items = "".join(
                f"<li>{html.escape(value)}</li>" for value in points if isinstance(value, str)
            )
            if items:
                parts.append(f"<ul>{items}</ul>")
        parts.append("</section>")
    sources = article.sources if isinstance(article.sources, list) else []
    if sources:
        parts.append("<section><h2>Источники</h2><ol>")
        for source in sources:
            if not isinstance(source, dict):
                continue
            url = _safe_https_url(source.get("url"))
            title = source.get("title")
            publisher = source.get("publisher")
            if not (isinstance(url, str) and isinstance(title, str) and isinstance(publisher, str)):
                continue
            parts.append(
                f'<li><a href="{html.escape(url, quote=True)}">{html.escape(title)}</a>'
                f" — {html.escape(publisher)}</li>"
            )
        parts.append("</ol></section>")
    if related:
        parts.append("<section><h2>Связанные статьи</h2><ul>")
        for item in related:
            parts.append(
                f'<li><a href="/articles/{html.escape(item.slug, quote=True)}">'
                f"{html.escape(item.title)}</a></li>"
            )
        parts.append("</ul></section>")
    cta = article.cta if isinstance(article.cta, dict) else {}
    cta_label = cta.get("label", "Открыть Your Fitness Coach")
    cta_description = cta.get("description", "Продолжите работу с фактами в приложении.")
    cta_destination = cta.get("destination", "web")
    if isinstance(cta_label, str) and isinstance(cta_description, str):
        cta_href = public_article_cta_url(cta_destination)
        parts.append(
            f"<section><h2>{html.escape(cta_label)}</h2><p>{html.escape(cta_description)}</p>"
            f'<a href="{html.escape(cta_href, quote=True)}">{html.escape(cta_label)}</a></section>'
        )
    parts.append("</main>")
    return "".join(parts)


def render_articles_index_fallback(articles: tuple[WebArticle, ...]) -> str:
    parts = [
        '<main class="seo-fallback seo-articles-index-fallback">',
        '<nav aria-label="Публичные разделы"><a href="/">Главная</a> '
        '<a href="/articles">Статьи</a></nav>',
        f"<h1>{html.escape(ARTICLE_INDEX_TITLE)}</h1>",
        f"<p>{html.escape(ARTICLE_INDEX_DESCRIPTION)}</p>",
        "<section><h2>Опубликованные статьи</h2><ul>",
    ]
    for article in articles:
        parts.append(
            f'<li><a href="/articles/{html.escape(article.slug, quote=True)}">'
            f"{html.escape(article.title)}</a> — {html.escape(article.description)}</li>"
        )
    parts.extend(("</ul></section>", "</main>"))
    return "".join(parts)


def render_public_fallback(path: str) -> str:
    """Render the public page's meaningful text and links without requiring JavaScript."""

    page = public_page_for_path(path)
    if not page:
        return ""
    parts = [
        '<main class="seo-fallback">',
        '<nav aria-label="Публичные разделы"><a href="/">Главная</a> '
        '<a href="/training">Тренировки</a> <a href="/nutrition">Питание</a> '
        '<a href="/progress">Прогресс</a> <a href="/knowledge">База знаний</a> '
        '<a href="/exercises">Упражнения</a> '
        '<a href="/for-trainers">Для тренеров</a></nav>',
    ]
    breadcrumbs = page.get("breadcrumbs")
    if isinstance(breadcrumbs, list) and len(breadcrumbs) >= 2:
        breadcrumb_items = "".join(
            _link_markup(cast(dict[str, object], item))
            for item in breadcrumbs
            if isinstance(item, dict)
        )
        parts.append(f'<nav aria-label="Хлебные крошки"><ol>{breadcrumb_items}</ol></nav>')
    parts.extend(
        (
            f"<h1>{html.escape(_required_string(page['heading'], field='heading'))}</h1>",
            f"<p>{html.escape(_required_string(page['intro'], field='intro'))}</p>",
        )
    )
    if isinstance(page.get("author"), dict) and isinstance(page.get("updated"), str):
        author = cast(dict[str, object], page["author"])
        parts.append(
            "<p>Автор: "
            f"{html.escape(_required_string(author.get('name'), field='author.name'))}. "
            f'<time datetime="{html.escape(cast(str, page["updated"]), quote=True)}">'
            f"Обновлено {html.escape(cast(str, page['updated']))}</time>.</p>"
        )
    if isinstance(page.get("disclaimer"), str):
        parts.append(f"<aside>{html.escape(cast(str, page['disclaimer']))}</aside>")
    raw_sections = page.get("sections")
    if isinstance(raw_sections, list):
        for raw_section in raw_sections:
            if not isinstance(raw_section, dict):
                continue
            section = cast(dict[str, object], raw_section)
            parts.append(
                f"<section><h2>{html.escape(_required_string(section.get('heading'), field='section.heading'))}</h2>"
            )
            paragraphs = section.get("paragraphs")
            if isinstance(paragraphs, list):
                parts.extend(
                    f"<p>{html.escape(paragraph)}</p>"
                    for paragraph in paragraphs
                    if isinstance(paragraph, str)
                )
            points = section.get("points")
            if isinstance(points, list):
                items = "".join(
                    f"<li>{html.escape(point)}</li>" for point in points if isinstance(point, str)
                )
                if items:
                    parts.append(f"<ul>{items}</ul>")
            parts.append("</section>")
    if page.get("kind") == "knowledge-index":
        guide_links = "".join(
            _link_markup(
                {
                    "path": guide["path"],
                    "label": guide["heading"],
                    "description": guide["description"],
                }
            )
            for guide in public_pages()
            if guide.get("kind") == "guide" and guide.get("status", "published") == "published"
        )
        parts.append(
            f"<section><h2>Опубликованные руководства</h2><ul>{guide_links}</ul></section>"
        )
    if page.get("kind") == "exercise-index":
        exercise_links = "".join(
            _link_markup(
                {
                    "path": exercise_page["path"],
                    "label": exercise_page["heading"],
                    "description": exercise_page["description"],
                }
            )
            for exercise_page in public_pages()
            if exercise_page.get("kind") == "exercise"
            and exercise_page.get("status", "published") == "published"
        )
        parts.append(
            f"<section><h2>Опубликованные карточки упражнений</h2><ul>{exercise_links}</ul></section>"
        )
    if page.get("kind") == "exercise" and isinstance(page.get("slug"), str):
        exercise = public_exercise(cast(str, page["slug"]))
        if exercise is None:
            raise RuntimeError(f"Published exercise {page['slug']!r} has no domain record")
        facts = (
            f"Основная группа: {html.escape(cast(str, exercise['primary_muscle']))}. "
            f"Оборудование: {html.escape(cast(str, exercise['equipment']))}."
        )
        parts.append(f"<section><h2>Краткие сведения</h2><p>{facts}</p></section>")
        steps = "".join(
            f"<li>{html.escape(step)}</li>" for step in cast(list[str], exercise["technique_steps"])
        )
        parts.append(f"<section><h2>Техника выполнения</h2><ol>{steps}</ol></section>")
        parts.append(
            "<section><h2>Дыхание</h2><p>"
            f"{html.escape(cast(str, exercise['breathing']))}</p></section>"
        )
        mistakes = "".join(
            f"<li>{html.escape(item)}</li>" for item in cast(list[str], exercise["common_mistakes"])
        )
        parts.append(f"<section><h2>Частые ошибки</h2><ul>{mistakes}</ul></section>")
        source_url = html.escape(cast(str, exercise["source_url"]), quote=True)
        source_name = html.escape(cast(str, exercise["source_name"]))
        source_license = html.escape(cast(str, exercise["source_license"]))
        parts.append(
            "<footer><strong>Источник данных и лицензия</strong> "
            f'<a href="{source_url}">{source_name}</a> — {source_license}</footer>'
        )
    sources = page.get("sources")
    if isinstance(sources, list) and sources:
        parts.append("<section><h2>Источники</h2><ol>")
        for raw_source in sources:
            if not isinstance(raw_source, dict):
                continue
            source = cast(dict[str, object], raw_source)
            url = html.escape(_required_string(source.get("url"), field="source.url"), quote=True)
            title = html.escape(_required_string(source.get("title"), field="source.title"))
            publisher = html.escape(
                _required_string(source.get("publisher"), field="source.publisher")
            )
            parts.append(f'<li><a href="{url}">{title}</a> — {publisher}</li>')
        parts.append("</ol></section>")
    related = page.get("related")
    if isinstance(related, list) and related:
        links = "".join(
            _link_markup(cast(dict[str, object], item))
            for item in related
            if isinstance(item, dict)
        )
        parts.append(f"<section><h2>Связанные страницы</h2><ul>{links}</ul></section>")
    cta = page.get("cta")
    if isinstance(cta, dict):
        typed_cta = cast(dict[str, object], cta)
        app_url = f"{settings.frontend_base_url.rstrip('/')}/app"
        parts.append(
            "<section><h2>"
            f"{html.escape(_required_string(typed_cta.get('label'), field='cta.label'))}"
            "</h2><p>"
            f"{html.escape(_required_string(typed_cta.get('description'), field='cta.description'))}"
            f'</p><a href="{html.escape(app_url, quote=True)}">Открыть приложение</a></section>'
        )
    parts.append("</main>")
    return "".join(parts)


def render_frontend_document(
    template: str,
    path: str,
    *,
    article: WebArticle | None = None,
    articles: tuple[WebArticle, ...] = (),
) -> tuple[str, SeoMetadata]:
    """Inject route metadata and public fallback into the Vite HTML entry."""

    if article is not None:
        metadata = metadata_for_article(article)
        fallback = render_article_fallback(
            article, tuple(item for item in articles if item.slug in article.related_slugs)
        )
    elif path == "/articles":
        metadata = metadata_for_articles()
        fallback = render_articles_index_fallback(articles)
    else:
        metadata = metadata_for_path(path)
        fallback = render_public_fallback(path)
    rendered = template.replace("<!-- seo-head -->", render_metadata(metadata))
    if rendered == template:
        rendered = template.replace("</head>", f"    {render_metadata(metadata)}\n  </head>")

    marked_fallback = f"<!-- public-fallback-start -->{fallback}<!-- public-fallback-end -->"
    if _PUBLIC_FALLBACK_PATTERN.search(rendered):
        rendered = _PUBLIC_FALLBACK_PATTERN.sub(marked_fallback, rendered, count=1)
    elif fallback:
        rendered = rendered.replace('<div id="root"></div>', f'<div id="root">{fallback}</div>')
    rendered = rendered.replace(
        "<!-- yandex-metrica-noscript -->",
        _YANDEX_METRICA_NOSCRIPT if metadata.canonical_url else "",
    )
    return rendered, metadata
