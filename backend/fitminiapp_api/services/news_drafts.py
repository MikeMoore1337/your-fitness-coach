from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.models.news import NewsCluster, NewsItem, NewsSource
from fitminiapp_api.services.news_ingestion import latest_items_by_source
from fitminiapp_api.services.news_publication import TELEGRAM_PHOTO_CAPTION_LIMIT
from fitminiapp_api.services.news_taxonomy import style_checklist_warnings

EDITORIAL_FIELDS = (
    "headline",
    "summary",
    "why_it_matters",
)
HYPE_PATTERN = re.compile(
    r"\b(?:guarantee[sd]?|miracle|breakthrough|cure[sd]?|"
    r"гарантирован\w*|чудо|прорыв\w*|излеч\w*|доказано навсегда)\b",
    re.IGNORECASE,
)
PRESCRIPTION_PATTERN = re.compile(
    r"\b(?:take \d|prescribe|dosage|принимайте \d|назнач(?:ить|ается)|дозировк\w*)\b",
    re.IGNORECASE,
)
NUMBER_PATTERN = re.compile(r"(?<![\w])\d+(?:[.,]\d+)?(?:%|\s?(?:mg|g|kg|мг|г|кг))?")
CYRILLIC_PATTERN = re.compile(r"[А-Яа-яЁё]")
SENTENCE_END_PATTERN = re.compile(r"[.!?…](?=\s|$)")


class DraftGenerationError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class NewsEvidencePacket:
    cluster_id: str
    primary_item_id: int
    evidence_item_ids: tuple[int, ...]
    topic: str
    score: int
    score_reasons: tuple[str, ...]
    risk_flags: tuple[str, ...]
    source_id: str
    source_type: str
    source_name: str
    canonical_url: str
    primary_url: str | None
    title: str
    summary: str
    author: str | None
    publisher: str | None
    published_at: datetime | None
    doi: str | None
    supporting_sources: tuple[dict[str, str], ...]

    @property
    def source_digest(self) -> str:
        payload = json.dumps(
            {
                "cluster_id": self.cluster_id,
                "primary_item_id": self.primary_item_id,
                "evidence_item_ids": self.evidence_item_ids,
                "source_id": self.source_id,
                "url": self.canonical_url,
                "primary_url": self.primary_url,
                "title": self.title,
                "summary": self.summary,
                "published_at": self.published_at.isoformat() if self.published_at else None,
                "doi": self.doi,
                "supporting_sources": self.supporting_sources,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def evidence_packet(db: Session, cluster: NewsCluster) -> NewsEvidencePacket:
    primary = db.get(NewsItem, cluster.primary_item_id)
    if primary is None or primary.cluster_id != cluster.id:
        raise DraftGenerationError("primary_source_missing")
    source = db.get(NewsSource, primary.source_id)
    if source is None:
        raise DraftGenerationError("source_missing")
    cluster_items = db.query(NewsItem).filter(NewsItem.cluster_id == cluster.id).all()
    representative_items = latest_items_by_source(cluster_items)
    supporting_items = sorted(
        (item for item in representative_items if item.source_id != primary.source_id),
        key=lambda item: (item.published_at or datetime.max, item.id),
    )[:10]
    supporting_sources = tuple(
        {
            "source_id": item.source_id,
            "canonical_url": item.canonical_url,
            "title": item.title,
            "published_at": item.published_at.isoformat() if item.published_at else "unknown",
        }
        for item in supporting_items
    )
    return NewsEvidencePacket(
        cluster_id=cluster.id,
        primary_item_id=primary.id,
        evidence_item_ids=(primary.id, *(item.id for item in supporting_items)),
        topic=cluster.topic,
        score=cluster.score,
        score_reasons=tuple(cluster.score_reasons),
        risk_flags=tuple(cluster.risk_flags),
        source_id=source.id,
        source_type=source.source_type,
        source_name=source.name,
        canonical_url=primary.canonical_url,
        primary_url=primary.primary_url,
        title=primary.title,
        summary=primary.summary,
        author=primary.author,
        publisher=primary.publisher,
        published_at=primary.published_at,
        doi=primary.doi,
        supporting_sources=supporting_sources,
    )


def _safe_field(value: object, *, maximum: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise DraftGenerationError("invalid_draft_schema")
    normalized = " ".join(value.split())
    if not normalized:
        if allow_empty:
            return ""
        raise DraftGenerationError("invalid_draft_schema")
    if len(normalized) > maximum or not CYRILLIC_PATTERN.search(normalized):
        raise DraftGenerationError("invalid_draft_schema")
    return normalized


def _safe_summary(value: object, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise DraftGenerationError("invalid_draft_schema")
    paragraphs = [
        " ".join(paragraph.split())
        for paragraph in re.split(r"\n\s*\n", value.strip())
        if paragraph.strip()
    ]
    if not paragraphs:
        raise DraftGenerationError("invalid_draft_schema")
    if len(paragraphs) > 2:
        paragraphs = [paragraphs[0], " ".join(paragraphs[1:])]
    normalized = "\n\n".join(paragraphs)
    if len(normalized) > maximum or not CYRILLIC_PATTERN.search(normalized):
        raise DraftGenerationError("invalid_draft_schema")
    return normalized


def _validated_fields(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict) or set(raw) != set(EDITORIAL_FIELDS):
        raise DraftGenerationError("invalid_draft_schema")
    fields = {
        "headline": _safe_field(raw["headline"], maximum=180),
        "summary": _safe_summary(raw["summary"], maximum=1200),
        "why_it_matters": _safe_field(raw["why_it_matters"], maximum=320, allow_empty=True),
    }
    first_sentence_end = SENTENCE_END_PATTERN.search(fields["why_it_matters"])
    if first_sentence_end and fields["why_it_matters"][first_sentence_end.end() :].strip():
        fields["why_it_matters"] = fields["why_it_matters"][: first_sentence_end.end()]
    return fields


def quality_warnings(
    fields: dict[str, str],
    *,
    source_title: str,
    source_summary: str,
    source_context: str = "",
) -> list[str]:
    output = " ".join(fields.values())
    warnings: list[str] = []
    if HYPE_PATTERN.search(output):
        warnings.append("sensational_or_guaranteed_claim")
    if PRESCRIPTION_PATTERN.search(output):
        warnings.append("medical_prescription_language")
    source_text = f"{source_title} {source_summary} {source_context}"
    source_numbers = set(NUMBER_PATTERN.findall(source_text))
    output_numbers = set(NUMBER_PATTERN.findall(output))
    if output_numbers - source_numbers:
        warnings.append("unsupported_number")
    if (
        source_summary
        and SequenceMatcher(None, output.lower(), source_summary.lower())
        .find_longest_match(0, len(output), 0, len(source_summary))
        .size
        > 140
    ):
        warnings.append("possible_source_copy")
    visible_parts = [fields["headline"]]
    visible_parts.extend(fields["summary"].split("\n\n"))
    if fields["why_it_matters"]:
        visible_parts.append(fields["why_it_matters"])
    visible_parts.append("Источник")
    visible_length = len("\n\n".join(visible_parts).encode("utf-16-le")) // 2
    if visible_length > TELEGRAM_PHOTO_CAPTION_LIMIT:
        warnings.append("telegram_photo_caption_too_long")
    warnings.extend(style_checklist_warnings(output))
    return warnings


def grounded_number_tokens(
    *,
    source_title: str,
    source_summary: str,
    source_context: str = "",
) -> tuple[str, ...]:
    """Return bounded numeric evidence tokens without retaining the source body."""

    source_text = f"{source_title} {source_summary} {source_context}"
    return tuple(sorted(set(NUMBER_PATTERN.findall(source_text))))


def render_draft(fields: dict[str, str], packet: NewsEvidencePacket) -> str:
    source_url = packet.primary_url or packet.canonical_url
    sections = [
        f"ЗАГОЛОВОК\n{fields['headline']}",
        f"КРАТКО\n{fields['summary']}",
    ]
    if fields["why_it_matters"]:
        sections.append(f"ПОЧЕМУ ЭТО ВАЖНО\n{fields['why_it_matters']}")
    sections.append(f"ИСТОЧНИК\n{source_url}")
    rendered = "\n\n──────────\n\n".join(sections)
    if len(rendered) > settings.news_draft_max_chars:
        raise DraftGenerationError("draft_too_long")
    return rendered
