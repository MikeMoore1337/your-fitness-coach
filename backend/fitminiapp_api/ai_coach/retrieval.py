"""Deterministic exact-context retrieval from reviewed public content."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from fitminiapp_api.ai_coach.contracts import (
    AiCoachJob,
    AiCoachRequest,
    ContextCitation,
    ContextRef,
)
from fitminiapp_api.core.config import settings
from fitminiapp_api.models.news import WebArticle
from fitminiapp_api.seo import public_origin, public_pages
from fitminiapp_api.services.public_exercises import public_exercise

_PROMPT_INJECTION_PATTERN = re.compile(
    r"(?:ignore\s+(?:all\s+)?(?:previous|earlier)\s+instructions|"
    r"игнорируй\s+(?:все\s+)?(?:предыдущие|системные)\s+инструкции|"
    r"reveal\s+(?:the\s+)?(?:system\s+)?prompt|"
    r"раскрой\s+(?:системный\s+)?промпт|"
    r"(?:developer|system)\s+(?:message|instruction)|"
    r"вызови\s+инструмент)",
    re.IGNORECASE,
)
_SAFE_CONTEXT_ID = re.compile(r"^[A-Za-z0-9_.:/-]+$")
_JOB_CATEGORIES: dict[AiCoachJob, frozenset[str]] = {
    AiCoachJob.APP_HELP: frozenset({"training", "nutrition", "progress", "product"}),
    AiCoachJob.PUBLIC_KNOWLEDGE: frozenset(
        {"training", "nutrition", "cardio", "recovery", "progress", "exercises", "product"}
    ),
    AiCoachJob.METRIC_EXPLANATION: frozenset({"training", "nutrition", "progress", "cardio"}),
    AiCoachJob.FITNESS_KNOWLEDGE: frozenset({"training", "cardio", "recovery", "exercises"}),
    AiCoachJob.NUTRITION_KNOWLEDGE: frozenset({"nutrition"}),
    AiCoachJob.PROGRESSION_EXPLANATION: frozenset({"training", "progress"}),
}


class ContextUnavailable(RuntimeError):
    """The requested public context is missing, stale or not eligible for this job."""


class ContextUnsafe(ContextUnavailable):
    """Reviewed content contained an instruction-like payload."""


def _as_text(value: object, *, max_length: int = 1_200) -> str:
    if not isinstance(value, str):
        return ""
    normalized = " ".join(value.split())
    return normalized[:max_length]


def _as_string_list(value: object, *, max_items: int = 12, max_length: int = 600) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_as_text(item, max_length=max_length) for item in value[:max_items] if _as_text(item)]


def _public_url(path: str) -> str:
    return f"{public_origin()}/{path.lstrip('/')}"


def _safe_source(value: object) -> tuple[str, str] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if any(ord(char) < 0x20 for char in normalized):
        return None
    from urllib.parse import urlparse

    parsed = urlparse(normalized)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return None
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return None
    return normalized, parsed.hostname.lower().rstrip(".")


def _is_current(value: object, *, today: date | None = None) -> bool:
    if isinstance(value, datetime):
        current_date = value.date()
    elif isinstance(value, date):
        current_date = value
    elif isinstance(value, str):
        try:
            current_date = date.fromisoformat(value[:10])
        except ValueError:
            return False
    else:
        return False
    now = today or datetime.now(UTC).date()
    return now - timedelta(days=settings.ai_coach_content_max_age_days) <= current_date <= now


def _reviewer_name(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    name = value.get("name")
    return _as_text(name, max_length=160) or None


def _article_content(article: WebArticle) -> str:
    parts = [_as_text(article.title), _as_text(article.description), _as_text(article.lead)]
    for raw_section in article.body_sections if isinstance(article.body_sections, list) else []:
        if not isinstance(raw_section, dict):
            continue
        parts.append(_as_text(raw_section.get("heading"), max_length=180))
        parts.extend(_as_string_list(raw_section.get("paragraphs"), max_items=8))
        parts.extend(_as_string_list(raw_section.get("points"), max_items=12))
    return "\n".join(part for part in parts if part)[: settings.ai_coach_max_context_chars]


def _page_content(page: dict[str, object]) -> str:
    parts = [
        _as_text(page.get("title")),
        _as_text(page.get("description")),
        _as_text(page.get("heading")),
        _as_text(page.get("intro")),
    ]
    parts.extend(_as_string_list(page.get("highlights"), max_items=8))
    raw_sections = page.get("sections")
    if isinstance(raw_sections, list):
        for raw_section in raw_sections[:24]:
            if not isinstance(raw_section, dict):
                continue
            parts.append(_as_text(raw_section.get("heading"), max_length=180))
            parts.extend(_as_string_list(raw_section.get("paragraphs"), max_items=8))
            parts.extend(_as_string_list(raw_section.get("points"), max_items=12))
    disclaimer = _as_text(page.get("disclaimer"), max_length=600)
    if disclaimer:
        parts.append(disclaimer)
    return "\n".join(part for part in parts if part)[: settings.ai_coach_max_context_chars]


def _exercise_content(exercise: dict[str, object]) -> str:
    parts = [
        _as_text(exercise.get("title")),
        _as_text(exercise.get("primary_muscle")),
        _as_text(exercise.get("equipment")),
        _as_text(exercise.get("difficulty_level")),
        _as_text(exercise.get("breathing")),
    ]
    parts.extend(_as_string_list(exercise.get("secondary_muscles"), max_items=8))
    parts.extend(_as_string_list(exercise.get("technique_steps"), max_items=12))
    parts.extend(_as_string_list(exercise.get("common_mistakes"), max_items=12))
    parts.extend(_as_string_list(exercise.get("safety_notes"), max_items=8))
    return "\n".join(part for part in parts if part)[: settings.ai_coach_max_context_chars]


def _article_ref(
    article: WebArticle,
    *,
    allowed_categories: frozenset[str] | None = None,
) -> ContextRef | None:
    if (
        article.status != "published"
        or article.published_at is None
        or article.updated_at is None
        or not _is_current(article.updated_at)
    ):
        return None
    canonical_url = _public_url(f"/articles/{article.slug}")
    canonical = _safe_source(canonical_url)
    if canonical is None:
        return None
    citations = [
        ContextCitation(
            title=article.title,
            publisher="Your Fitness Coach",
            url=canonical[0],
            source_type="canonical_yfc",
        )
    ]
    raw_sources = article.sources if isinstance(article.sources, list) else []
    for raw_source in raw_sources[:7]:
        if not isinstance(raw_source, dict):
            continue
        safe_url = _safe_source(raw_source.get("url"))
        title = _as_text(raw_source.get("title"), max_length=240)
        publisher = _as_text(raw_source.get("publisher"), max_length=160)
        if safe_url is None or not title or not publisher:
            continue
        citations.append(
            ContextCitation(
                title=title,
                publisher=publisher,
                url=safe_url[0],
                source_type=_as_text(raw_source.get("source_type"), max_length=64)
                or "reviewed_source",
            )
        )
    content = _article_content(article)
    if not content:
        return None
    if _PROMPT_INJECTION_PATTERN.search(content):
        raise ContextUnsafe("public_context_contains_instruction_like_text")
    topics = [topic for topic in article.topics if isinstance(topic, str)]
    if allowed_categories is None:
        category = topics[0] if topics else "public"
    else:
        matched_category = next((topic for topic in topics if topic in allowed_categories), None)
        if matched_category is None:
            return None
        category = matched_category
    return ContextRef(
        ref_id=f"article:{article.slug}",
        title=article.title,
        category=category,
        updated_at=article.updated_at.date().isoformat(),
        reviewer=_reviewer_name(article.domain_reviewer) or _reviewer_name(article.editor),
        canonical_url=canonical[0],
        content=content,
        citations=tuple(citations[:8]),
    )


def _page_ref(page: dict[str, object]) -> ContextRef | None:
    if page.get("status", "published") != "published" or page.get("kind") not in {
        "guide",
        "product",
    }:
        return None
    page_id = _as_text(page.get("id"), max_length=128)
    path = _as_text(page.get("path"), max_length=256)
    updated = page.get("updated")
    is_guide = page.get("kind") == "guide"
    if not path or (is_guide and not _is_current(updated)):
        return None
    if not page_id:
        if page.get("kind") != "product":
            return None
        page_id = f"product:{path}"
    if not _SAFE_CONTEXT_ID.fullmatch(page_id):
        return None
    canonical = _safe_source(_public_url(path))
    if canonical is None:
        return None
    citations = [
        ContextCitation(
            title=_as_text(page.get("title"), max_length=240),
            publisher="Your Fitness Coach",
            url=canonical[0],
            source_type="canonical_yfc",
        )
    ]
    raw_source_value = page.get("sources")
    raw_sources: list[object] = raw_source_value if isinstance(raw_source_value, list) else []
    if is_guide and not raw_sources:
        return None
    for raw_source in raw_sources[:7]:
        if not isinstance(raw_source, dict):
            continue
        safe_url = _safe_source(raw_source.get("url"))
        title = _as_text(raw_source.get("title"), max_length=240)
        publisher = _as_text(raw_source.get("publisher"), max_length=160)
        if safe_url is None or not title or not publisher:
            continue
        citations.append(
            ContextCitation(
                title=title,
                publisher=publisher,
                url=safe_url[0],
                source_type=_as_text(raw_source.get("sourceType"), max_length=64)
                or "reviewed_source",
            )
        )
    content = _page_content(page)
    if not content:
        return None
    if _PROMPT_INJECTION_PATTERN.search(content):
        raise ContextUnsafe("public_context_contains_instruction_like_text")
    category = (
        "product"
        if page.get("kind") == "product"
        else _as_text(page.get("category"), max_length=64)
    )
    if not category:
        category = path.strip("/").split("/", 1)[0] or "public"
    reviewer = _reviewer_name(page.get("reviewer")) or _reviewer_name(page.get("author"))
    updated_at = _as_text(updated, max_length=32) or "manifest-current"
    return ContextRef(
        ref_id=page_id,
        title=_as_text(page.get("title"), max_length=240),
        category=category,
        updated_at=updated_at,
        reviewer=reviewer,
        canonical_url=canonical[0],
        content=content,
        citations=tuple(citations[:8]),
    )


def _exercise_ref(slug: str) -> ContextRef | None:
    exercise = public_exercise(slug)
    if exercise is None:
        return None
    canonical = _safe_source(_public_url(f"/exercises/{slug}"))
    source_url = _safe_source(exercise.get("source_url"))
    title = _as_text(exercise.get("title"), max_length=240)
    source_name = _as_text(exercise.get("source_name"), max_length=160)
    content = _exercise_content(exercise)
    if canonical is None or not title or not content:
        return None
    if _PROMPT_INJECTION_PATTERN.search(content):
        raise ContextUnsafe("public_context_contains_instruction_like_text")
    citations = [
        ContextCitation(
            title=title,
            publisher="Your Fitness Coach",
            url=canonical[0],
            source_type="canonical_yfc",
        )
    ]
    if source_url is not None and source_name:
        citations.append(
            ContextCitation(
                title=source_name,
                publisher=source_name,
                url=source_url[0],
                source_type="domain_source",
            )
        )
    return ContextRef(
        ref_id=f"exercise:{slug}",
        title=title,
        category="exercises",
        updated_at="catalog-v2",
        reviewer="Your Fitness Coach domain source",
        canonical_url=canonical[0],
        content=content,
        citations=tuple(citations),
    )


def retrieve_context(db: Session, request: AiCoachRequest) -> tuple[ContextRef, ...]:
    """Resolve exactly one server-known public context; never perform URL retrieval."""

    if not _SAFE_CONTEXT_ID.fullmatch(request.context_id):
        return ()
    ref: ContextRef | None = None
    if request.context_id.startswith("article:"):
        slug = request.context_id.removeprefix("article:")
        article = (
            db.query(WebArticle)
            .filter(WebArticle.slug == slug, WebArticle.status == "published")
            .one_or_none()
        )
        if article is not None:
            ref = _article_ref(article, allowed_categories=_JOB_CATEGORIES[request.job])
    elif request.context_id.startswith("exercise:"):
        ref = _exercise_ref(request.context_id.removeprefix("exercise:"))
    else:
        for raw_page in public_pages():
            if isinstance(raw_page, dict) and (
                raw_page.get("id") == request.context_id
                or raw_page.get("path") == request.context_id
            ):
                ref = _page_ref(raw_page)
                break
    if ref is None or ref.category not in _JOB_CATEGORIES[request.job]:
        return ()
    return (ref,)
