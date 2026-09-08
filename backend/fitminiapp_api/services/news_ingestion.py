from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import logging
import re
import socket
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

from fitminiapp_api.models.news import NewsCluster, NewsItem, NewsSource
from fitminiapp_api.services.news_freshness import is_fresh_publication
from fitminiapp_api.services.news_state import transition_news_cluster
from fitminiapp_api.services.news_taxonomy import (
    classify_editorial_text,
    evaluate_publication_policy,
)

logger = logging.getLogger(__name__)

MAX_TITLE_CHARS = 500
MAX_SUMMARY_CHARS = 4000
MAX_SNAPSHOT_SUMMARY_CHARS = 1200
MAX_ITEMS_PER_RESPONSE = 100
MAX_REDIRECTS = 3
TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
}
DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
PROMPT_INJECTION_PATTERN = re.compile(
    r"(?:ignore (?:all |previous )?instructions|system prompt|developer message|"
    r"игнорируй (?:все |предыдущие )?инструкции|системн(?:ый|ого) промпт)",
    re.IGNORECASE,
)
PROHIBITED_PATTERNS = {
    "prescriptive_aas": re.compile(
        r"\b(?:(?:steroid|testosterone|trenbolone|sarm)\w*\s+"
        r"(?:cycle|dosage|protocol)|(?:cycle|dosage|protocol)\s+"
        r"(?:anabolic\s+)?(?:steroid|testosterone|trenbolone|sarm)\w*|"
        r"(?:курс|дозировк|схем)\w*\s+(?:анаболик|стероид|тестостерон|тренболон|сарм)\w*|"
        r"(?:анаболик|стероид|тестостерон|тренболон|сарм)\w*\s+"
        r"(?:курс|дозировк|схем)\w*)\b",
        re.IGNORECASE,
    ),
    "prescriptive_pharmacology": re.compile(
        r"\b(?:peptide cycle|drug dosage|prescription protocol|"
        r"курс пептид\w*|дозировк\w* (?:лекарств|пептид)\w*|"
        r"схем\w* (?:лечени|при[её]м)\w*)\b",
        re.IGNORECASE,
    ),
}
TOPIC_KEYWORDS = {
    "fitness": (
        "fitness",
        "exercise",
        "training",
        "workout",
        "strength",
        "resistance training",
        "hypertrophy",
        "muscle",
        "cardio",
        "aerobic",
        "recovery",
        "sleep",
        "running",
        "фитнес",
        "трениров",
        "упражнен",
        "силов",
        "гипертроф",
        "мышц",
        "кардио",
        "восстанов",
        "сон",
        "бег",
    ),
    "nutrition": (
        "nutrition",
        "diet",
        "food",
        "protein",
        "creatine",
        "caffeine",
        "supplement",
        "питани",
        "диет",
        "рацион",
        "протеин",
        "креатин",
        "кофеин",
        "добавк",
    ),
    "medicine_pharmacology": (
        "medicine",
        "medical",
        "clinical",
        "pharmacology",
        "medication",
        "therapy",
        "patient",
        "disease",
        "drug safety",
        "regulatory",
        "медицин",
        "клиническ",
        "фармаколог",
        "лекарств",
        "терапи",
        "пациент",
        "заболеван",
        "регулятор",
    ),
    "peptides": (
        "peptide",
        "glp-1",
        "glp 1",
        "semaglutide",
        "tirzepatide",
        "пептид",
        "гпп-1",
        "семаглутид",
        "тирзепатид",
    ),
    "bodybuilding": (
        "bodybuilding",
        "bodybuilder",
        "physique competition",
        "contest prep",
        "anabolic steroid",
        "testosterone",
        "trenbolone",
        "sarm",
        "бодибилд",
        "соревновательн",
        "анаболик",
        "стероид",
        "тестостерон",
        "тренболон",
        "сарм",
    ),
}
PRIORITY_KEYWORDS = {
    "practical": (
        "practical",
        "recommend",
        "guideline",
        "how to",
        "примен",
        "рекоменд",
        "практич",
        "инструкц",
    ),
    "new_research": (
        "systematic review",
        "meta-analysis",
        "randomized",
        "clinical trial",
        "study",
        "research",
        "исследован",
        "метаанализ",
        "рандомизир",
        "клиническ испытан",
    ),
    "tools_products": (
        "fitness tool",
        "training tool",
        "nutrition tool",
        "fitness app",
        "training app",
        "nutrition app",
        "health app",
        "wearable",
        "fitness tracker",
        "training platform",
        "health platform",
        "fitness product",
        "gym equipment",
        "фитнес-инструмент",
        "инструмент для трениров",
        "приложение для трениров",
        "приложение для питани",
        "фитнес-трекер",
        "трекер активности",
        "фитнес-платформ",
        "фитнес-продукт",
        "тренажер",
    ),
}
ESPORTS_PHYSICAL_CONTEXT = (
    "physical activity",
    "physical health",
    "exercise",
    "fitness",
    "injury",
    "nutrition",
    "physiological",
    "recovery",
    "sleep",
    "training load",
)
SOURCE_QUALITY = {
    "primary_research": 25,
    "systematic_review": 28,
    "official_organization": 24,
    "official_product": 18,
    "reputable_secondary": 10,
    "yfc": 25,
}
PRIMARY_RANK = {
    "systematic_review": 6,
    "primary_research": 5,
    "official_organization": 4,
    "yfc": 4,
    "official_product": 3,
    "reputable_secondary": 1,
}
TERMINAL_CLUSTER_STATUSES = {"rejected_by_rules", "rejected", "accepted_for_design"}
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "new",
    "study",
    "research",
    "как",
    "для",
    "или",
    "это",
    "при",
    "что",
    "новый",
    "исследование",
}


class SourceFetchError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ParsedNewsItem:
    external_id: str
    canonical_url: str
    title: str
    summary: str = ""
    primary_url: str | None = None
    author: str | None = None
    publisher: str | None = None
    published_at: datetime | None = None
    updated_at: datetime | None = None
    doi: str | None = None


@dataclass(frozen=True)
class SourceFetchResult:
    status: str
    items: tuple[ParsedNewsItem, ...] = ()
    etag: str | None = None
    last_modified: str | None = None
    body_hash: str | None = None


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonicalize_url(value: str) -> str:
    parsed = urlparse(html.unescape(value).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("invalid_absolute_url")
    if parsed.username or parsed.password:
        raise ValueError("credentialed_url")
    hostname = parsed.hostname.lower().rstrip(".")
    port = parsed.port
    if port and not (
        (parsed.scheme == "https" and port == 443) or (parsed.scheme == "http" and port == 80)
    ):
        netloc = f"{hostname}:{port}"
    else:
        netloc = hostname
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
    ]
    normalized_path = parsed.path or "/"
    if normalized_path != "/":
        normalized_path = normalized_path.rstrip("/")
    return urlunparse(
        (
            parsed.scheme.lower(),
            netloc,
            normalized_path,
            "",
            urlencode(sorted(query)),
            "",
        )
    )


def _item_reference_url(source: NewsSource, value: str, *, doi: str | None = None) -> str:
    normalized = canonicalize_url(value)
    parsed = urlparse(normalized)
    allowed_hosts = {urlparse(source.feed_url).hostname or ""}
    for field in ("allowed_redirect_hosts", "allowed_item_hosts"):
        configured = source.fetch_options.get(field, [])
        if isinstance(configured, list):
            allowed_hosts.update(str(host).lower().rstrip(".") for host in configured)
    if doi:
        allowed_hosts.add("doi.org")
    if (
        parsed.scheme != "https"
        or parsed.port not in {None, 443}
        or (parsed.hostname or "").lower().rstrip(".") not in allowed_hosts
    ):
        raise ValueError("item_url_not_allowed")
    return normalized


def _default_resolver(host: str, port: int) -> list[str]:
    try:
        return sorted(
            {str(row[4][0]) for row in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
        )
    except OSError as exc:
        raise SourceFetchError("dns_error") from exc


def validate_public_source_url(
    value: str,
    *,
    allowed_hosts: set[str],
    resolver: Callable[[str, int], list[str]] = _default_resolver,
) -> str:
    try:
        normalized = canonicalize_url(value)
        parsed = urlparse(normalized)
    except (TypeError, ValueError) as exc:
        raise SourceFetchError("invalid_url") from exc
    hostname = parsed.hostname or ""
    if parsed.scheme != "https" or parsed.port not in {None, 443}:
        raise SourceFetchError("https_required")
    if hostname not in allowed_hosts or hostname == "localhost" or hostname.endswith(".local"):
        raise SourceFetchError("host_not_allowed")
    addresses = resolver(hostname, 443)
    if not addresses:
        raise SourceFetchError("dns_error")
    try:
        if any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise SourceFetchError("private_network_blocked")
    except ValueError as exc:
        raise SourceFetchError("dns_error") from exc
    return normalized


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def plain_text(value: str, *, maximum: int) -> str:
    parser = _TextExtractor()
    parser.feed(value)
    return " ".join(" ".join(parser.parts).split())[:maximum]


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(normalized)
        except TypeError, ValueError, OverflowError:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _element_text(element: ET.Element, names: set[str]) -> str | None:
    for child in element.iter():
        if child.tag.rsplit("}", 1)[-1].lower() in names and child.text:
            value = child.text.strip()
            if value:
                return value
    return None


def _element_link(element: ET.Element) -> str | None:
    for child in element.iter():
        if child.tag.rsplit("}", 1)[-1].lower() != "link":
            continue
        href = child.attrib.get("href")
        rel = child.attrib.get("rel", "alternate")
        if href and rel in {"alternate", "canonical"}:
            return href.strip()
        if child.text and child.text.strip():
            return child.text.strip()
    return None


def _doi(*values: str | None) -> str | None:
    for value in values:
        if not value:
            continue
        match = DOI_PATTERN.search(value)
        if match:
            return match.group(0).rstrip(".,;)").lower()
    return None


def parse_rss(body: bytes, base_url: str) -> tuple[ParsedNewsItem, ...]:
    lowered = body.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise SourceFetchError("unsafe_xml")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise SourceFetchError("malformed_content") from exc
    entries = [
        element
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}
    ][:MAX_ITEMS_PER_RESPONSE]
    result: list[ParsedNewsItem] = []
    for entry in entries:
        title = plain_text(_element_text(entry, {"title"}) or "", maximum=MAX_TITLE_CHARS)
        link = _element_link(entry)
        if not title or not link:
            continue
        absolute_link = urljoin(base_url, link)
        summary = plain_text(
            _element_text(entry, {"summary", "description", "content", "encoded"}) or "",
            maximum=MAX_SUMMARY_CHARS,
        )
        external_id = _element_text(entry, {"guid", "id"}) or absolute_link
        doi = _doi(_element_text(entry, {"doi", "identifier"}), absolute_link, summary)
        result.append(
            ParsedNewsItem(
                external_id=external_id[:512],
                canonical_url=absolute_link,
                title=title,
                summary=summary,
                primary_url=f"https://doi.org/{doi}" if doi else None,
                author=plain_text(_element_text(entry, {"author", "creator"}) or "", maximum=256)
                or None,
                published_at=_parse_datetime(
                    _element_text(entry, {"published", "pubdate", "date"})
                ),
                updated_at=_parse_datetime(_element_text(entry, {"updated", "modified"})),
                doi=doi,
            )
        )
    return tuple(result)


def parse_json_feed(body: bytes, base_url: str) -> tuple[ParsedNewsItem, ...]:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceFetchError("malformed_content") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise SourceFetchError("malformed_content")
    publisher = plain_text(str(payload.get("title", "")), maximum=160) or None
    result: list[ParsedNewsItem] = []
    for raw in payload["items"][:MAX_ITEMS_PER_RESPONSE]:
        if not isinstance(raw, dict):
            continue
        title = plain_text(str(raw.get("title", "")), maximum=MAX_TITLE_CHARS)
        link = raw.get("url") or raw.get("external_url")
        if not title or not isinstance(link, str):
            continue
        absolute_link = urljoin(base_url, link)
        summary_value = raw.get("summary") or raw.get("content_text") or raw.get("content_html")
        summary = plain_text(str(summary_value or ""), maximum=MAX_SUMMARY_CHARS)
        authors = raw.get("authors")
        author = None
        if isinstance(authors, list) and authors and isinstance(authors[0], dict):
            author = plain_text(str(authors[0].get("name", "")), maximum=256) or None
        doi = _doi(str(raw.get("id", "")), absolute_link, summary)
        result.append(
            ParsedNewsItem(
                external_id=str(raw.get("id") or absolute_link)[:512],
                canonical_url=absolute_link,
                title=title,
                summary=summary,
                primary_url=f"https://doi.org/{doi}" if doi else None,
                author=author,
                publisher=publisher,
                published_at=_parse_datetime(raw.get("date_published")),
                updated_at=_parse_datetime(raw.get("date_modified")),
                doi=doi,
            )
        )
    return tuple(result)


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.metadata: dict[str, str] = {}
        self.canonical: str | None = None
        self.in_title = False
        self.title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value for key, value in attrs if value is not None}
        if tag.lower() == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            content = values.get("content")
            if key and content and len(content) <= MAX_SUMMARY_CHARS:
                self.metadata[key] = content
        if tag.lower() == "link" and values.get("rel", "").lower() == "canonical":
            self.canonical = values.get("href")
        if tag.lower() == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)


def parse_html_metadata(body: bytes, base_url: str) -> tuple[ParsedNewsItem, ...]:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceFetchError("malformed_content") from exc
    parser = _MetadataParser()
    parser.feed(text)
    title = plain_text(
        parser.metadata.get("og:title") or " ".join(parser.title_parts), maximum=MAX_TITLE_CHARS
    )
    if not title:
        raise SourceFetchError("malformed_content")
    link = urljoin(base_url, parser.canonical or parser.metadata.get("og:url") or base_url)
    summary = plain_text(
        parser.metadata.get("og:description") or parser.metadata.get("description") or "",
        maximum=MAX_SUMMARY_CHARS,
    )
    doi = _doi(parser.metadata.get("citation_doi"), link, summary)
    return (
        ParsedNewsItem(
            external_id=link,
            canonical_url=link,
            title=title,
            summary=summary,
            primary_url=f"https://doi.org/{doi}" if doi else None,
            author=plain_text(
                parser.metadata.get("author") or parser.metadata.get("article:author") or "",
                maximum=256,
            )
            or None,
            publisher=plain_text(parser.metadata.get("og:site_name") or "", maximum=160) or None,
            published_at=_parse_datetime(parser.metadata.get("article:published_time")),
            updated_at=_parse_datetime(parser.metadata.get("article:modified_time")),
            doi=doi,
        ),
    )


PARSERS = {
    "rss": parse_rss,
    "json_feed": parse_json_feed,
    "html_metadata": parse_html_metadata,
}
CONTENT_TYPES = {
    "rss": ("application/rss+xml", "application/atom+xml", "application/xml", "text/xml"),
    "json_feed": ("application/feed+json", "application/json"),
    "html_metadata": ("text/html",),
}


class SafeNewsFetcher:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        max_bytes: int,
        resolver: Callable[[str, int], list[str]] = _default_resolver,
        enforce_connected_peer: bool = True,
    ) -> None:
        self.client = client
        self.max_bytes = max_bytes
        self.resolver = resolver
        self.enforce_connected_peer = enforce_connected_peer

    def _validate_connected_peer(self, response: httpx.Response) -> None:
        if not self.enforce_connected_peer:
            return
        stream = response.extensions.get("network_stream")
        if stream is None or not hasattr(stream, "get_extra_info"):
            raise SourceFetchError("peer_address_unavailable")
        peer = stream.get_extra_info("server_addr")
        address = peer[0] if isinstance(peer, tuple) and peer else None
        try:
            if not isinstance(address, str) or not ipaddress.ip_address(address).is_global:
                raise SourceFetchError("private_network_blocked")
        except ValueError as exc:
            raise SourceFetchError("peer_address_unavailable") from exc

    async def fetch(self, source: NewsSource) -> SourceFetchResult:
        initial_host = (urlparse(source.feed_url).hostname or "").lower().rstrip(".")
        configured_hosts = source.fetch_options.get("allowed_redirect_hosts", [])
        if not isinstance(configured_hosts, list):
            raise SourceFetchError("invalid_source_config")
        allowed_hosts = {initial_host} | {
            host.lower().rstrip(".") for host in configured_hosts if isinstance(host, str)
        }
        current_url = source.feed_url
        headers = {
            "Accept": ", ".join(CONTENT_TYPES[source.fetch_kind]),
            "User-Agent": "YourFitnessCoach-NewsIngestion/1.0",
        }
        if source.etag:
            headers["If-None-Match"] = source.etag
        if source.last_modified:
            headers["If-Modified-Since"] = source.last_modified

        for redirect_count in range(MAX_REDIRECTS + 1):
            current_url = validate_public_source_url(
                current_url, allowed_hosts=allowed_hosts, resolver=self.resolver
            )
            try:
                request = self.client.build_request("GET", current_url, headers=headers)
                response = await self.client.send(request, stream=True)
            except httpx.TimeoutException as exc:
                raise SourceFetchError("timeout") from exc
            except httpx.RequestError as exc:
                raise SourceFetchError("network_error") from exc
            try:
                self._validate_connected_peer(response)
                if response.status_code == 304:
                    return SourceFetchResult(status="not_modified")
                if response.is_redirect:
                    if redirect_count >= MAX_REDIRECTS:
                        raise SourceFetchError("too_many_redirects")
                    location = response.headers.get("location")
                    if not location:
                        raise SourceFetchError("invalid_redirect")
                    current_url = urljoin(current_url, location)
                    headers.pop("If-None-Match", None)
                    headers.pop("If-Modified-Since", None)
                    continue
                if response.status_code == 429:
                    raise SourceFetchError("rate_limited")
                if response.status_code >= 500:
                    raise SourceFetchError("upstream_error")
                if not response.is_success:
                    raise SourceFetchError(f"http_status_{response.status_code}")
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if content_type not in CONTENT_TYPES[source.fetch_kind]:
                    raise SourceFetchError("unexpected_content_type")
                content_length = response.headers.get("content-length")
                if (
                    content_length
                    and content_length.isdigit()
                    and int(content_length) > self.max_bytes
                ):
                    raise SourceFetchError("content_too_large")
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > self.max_bytes:
                        raise SourceFetchError("content_too_large")
                    chunks.append(chunk)
                body = b"".join(chunks)
            finally:
                await response.aclose()
            try:
                items = PARSERS[source.fetch_kind](body, current_url)
            except KeyError as exc:
                raise SourceFetchError("invalid_source_config") from exc
            return SourceFetchResult(
                status="fetched",
                items=items,
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
                body_hash=hashlib.sha256(body).hexdigest(),
            )
        raise SourceFetchError("too_many_redirects")


def _title_tokens(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-zа-яё0-9]{3,}", value.lower()) if token not in STOPWORDS
    }


def _title_similarity(left: str, right: str) -> float:
    left_tokens = _title_tokens(left)
    right_tokens = _title_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _event_match(
    db: Session, item: ParsedNewsItem, canonical_hash: str
) -> tuple[NewsItem | None, str, bool]:
    exact = (
        db.query(NewsItem)
        .filter(NewsItem.canonical_url_hash == canonical_hash)
        .order_by(NewsItem.id.asc())
        .first()
    )
    if exact is not None:
        return exact, "exact_url", False
    if item.doi:
        doi_match = (
            db.query(NewsItem).filter(NewsItem.doi == item.doi).order_by(NewsItem.id.asc()).first()
        )
        if doi_match is not None:
            return doi_match, "same_doi", False
    cutoff = (item.published_at or utcnow()) - timedelta(days=4)
    candidates = (
        db.query(NewsItem)
        .filter(or_(NewsItem.published_at.is_(None), NewsItem.published_at >= cutoff))
        .order_by(NewsItem.id.desc())
        .limit(200)
        .all()
    )
    uncertain = False
    for candidate in candidates:
        similarity = _title_similarity(item.title, candidate.title)
        if similarity >= 0.82:
            return candidate, "same_title_and_date", False
        uncertain = uncertain or similarity >= 0.67
    return None, "new_event", uncertain


def _topic(text: str) -> str:
    normalized = text.lower()
    if "esport" in normalized and not any(
        marker in normalized for marker in ESPORTS_PHYSICAL_CONTEXT
    ):
        return "other"
    scored = {
        topic: sum(1 for keyword in keywords if keyword in normalized)
        for topic, keywords in TOPIC_KEYWORDS.items()
    }
    selected, count = max(scored.items(), key=lambda pair: pair[1])
    return selected if count else "other"


def prohibited_flags(text: str) -> list[str]:
    return [name for name, pattern in PROHIBITED_PATTERNS.items() if pattern.search(text)]


def _candidate_ref(item: ParsedNewsItem) -> str:
    identity = item.external_id.strip() or item.canonical_url
    digest = hashlib.sha256(identity.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"candidate:{digest}"


def _log_candidate(
    item: ParsedNewsItem,
    *,
    outcome: str,
    reason: str,
    score: int = 0,
    topic: str = "other",
) -> None:
    logger.info(
        "news_candidate_evaluated",
        extra={
            "pipeline_stage": "scoring",
            "candidate_ref": _candidate_ref(item),
            "outcome": outcome,
            "reason": reason,
            "score": score,
            "topic": topic,
        },
    )


def score_candidate(
    source: NewsSource,
    item: NewsItem,
    *,
    supporting_source_count: int,
    uncertain_duplicate: bool,
    now: datetime,
    allow_sensitive_manual_review: bool = False,
) -> tuple[int, str, list[str], list[str]]:
    """Score a source item; Hermes may retain sensitive topics for owner review only."""

    text = f"{item.title} {item.summary}"
    topic = _topic(text)
    reasons = [f"source_quality:{SOURCE_QUALITY[source.source_type]}"]
    risks: list[str] = []
    score = SOURCE_QUALITY[source.source_type]
    if topic != "other":
        score += 25
        reasons.append(f"topic:{topic}")
    else:
        reasons.append("topic:not_allowlisted")
        risks.append("topic_not_allowlisted")
    normalized_text = text.lower()
    for priority, keywords in PRIORITY_KEYWORDS.items():
        if any(keyword in normalized_text for keyword in keywords):
            score += 10
            reasons.append(f"priority:{priority}")
    fresh = is_fresh_publication(item.published_at, now=now)
    if fresh:
        score += 15
        reasons.append("freshness:60_days")
    else:
        risks.append("source_not_current_month")
        reasons.append("freshness_gate_failed")
    if supporting_source_count > 0:
        score += min(10, supporting_source_count * 5)
        reasons.append("supporting_sources")
    if source.source_type == "reputable_secondary" and not item.doi and not item.primary_url:
        score -= 25
        risks.append("missing_primary_source")
        reasons.append("secondary_without_primary")
    if PROMPT_INJECTION_PATTERN.search(text):
        risks.append("source_prompt_injection")
    if uncertain_duplicate:
        risks.append("possible_duplicate")
        score -= 10
    prohibited = prohibited_flags(text)
    risks.extend(f"prohibited_{flag}" for flag in prohibited)
    # Only the authenticated Hermes intake opts into sensitive-topic recall. Legacy source
    # acquisition keeps the strict rejection path, while publication gates remain unchanged.
    if prohibited and not allow_sensitive_manual_review:
        score = 0
        reasons.append("prohibited_topic")
    elif prohibited:
        reasons.append("sensitive_topic_manual_review")
    if not fresh or topic == "other":
        score = 0
    return max(0, min(100, score)), topic, reasons, list(dict.fromkeys(risks))


def latest_items_by_source(items: list[NewsItem]) -> list[NewsItem]:
    latest: dict[str, NewsItem] = {}
    for item in items:
        current = latest.get(item.source_id)
        if current is None or (item.fetched_at, item.id) > (current.fetched_at, current.id):
            latest[item.source_id] = item
    return list(latest.values())


def _pick_primary(db: Session, cluster: NewsCluster) -> NewsItem:
    items = db.query(NewsItem).filter(NewsItem.cluster_id == cluster.id).all()
    representative_items = latest_items_by_source(items)
    sources = {
        row.id: row
        for row in db.query(NewsSource)
        .filter(NewsSource.id.in_({item.source_id for item in representative_items}))
        .all()
    }
    return max(
        representative_items,
        key=lambda item: (
            PRIMARY_RANK[sources[item.source_id].source_type],
            bool(item.doi or item.primary_url),
            -(item.published_at or datetime.max).toordinal(),
            -item.id,
        ),
    )


def ingest_items(
    db: Session,
    source: NewsSource,
    parsed_items: Iterable[ParsedNewsItem],
    *,
    candidate_threshold: int,
    fetched_at: datetime | None = None,
    allow_sensitive_manual_review: bool = False,
) -> dict[str, int]:
    current = fetched_at or utcnow()
    counts = {
        "new": 0,
        "duplicate": 0,
        "clustered": 0,
        "candidate": 0,
        "rejected": 0,
        "stale": 0,
        "below_threshold": 0,
        "eligible": 0,
    }
    for parsed in parsed_items:
        try:
            canonical_url = _item_reference_url(source, parsed.canonical_url)
            primary_url = (
                _item_reference_url(source, parsed.primary_url, doi=parsed.doi)
                if parsed.primary_url
                else None
            )
        except ValueError:
            counts["rejected"] += 1
            _log_candidate(item=parsed, outcome="rejected", reason="invalid_item_url")
            continue
        title = plain_text(parsed.title, maximum=MAX_TITLE_CHARS)
        summary = plain_text(parsed.summary, maximum=MAX_SUMMARY_CHARS)
        if not title:
            counts["rejected"] += 1
            _log_candidate(item=parsed, outcome="rejected", reason="missing_title")
            continue
        external_id = parsed.external_id.strip()[:512] or canonical_url
        external_hash = sha256_text(external_id)
        canonical_hash = sha256_text(canonical_url)
        content_hash = sha256_text(
            json.dumps(
                {
                    "title": title,
                    "summary": summary,
                    "url": canonical_url,
                    "published_at": parsed.published_at.isoformat()
                    if parsed.published_at
                    else None,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        existing_revision = (
            db.query(NewsItem)
            .filter(
                NewsItem.source_id == source.id,
                NewsItem.external_id_hash == external_hash,
                NewsItem.content_hash == content_hash,
            )
            .first()
        )
        if existing_revision is not None:
            counts["duplicate"] += 1
            _log_candidate(item=parsed, outcome="duplicate", reason="duplicate_revision")
            continue
        matched, merge_reason, uncertain = _event_match(db, parsed, canonical_hash)
        cluster = (
            db.get(NewsCluster, matched.cluster_id) if matched and matched.cluster_id else None
        )
        if cluster is None:
            cluster = NewsCluster(
                id=hashlib.sha256(
                    f"{source.id}:{external_hash}:{content_hash}".encode()
                ).hexdigest()[:32],
                cluster_key=hashlib.sha256(
                    f"{parsed.doi or canonical_hash}:{parsed.published_at.date() if parsed.published_at else ''}".encode()
                ).hexdigest(),
                status="clustered",
                merge_reason=merge_reason,
            )
            db.add(cluster)
            db.flush()
            transition_news_cluster(
                db,
                cluster,
                "clustered",
                from_status="fetched",
                reason_code="new_event_clustered",
            )
        item = NewsItem(
            source_id=source.id,
            cluster_id=cluster.id,
            status="fetched",
            external_id=external_id,
            external_id_hash=external_hash,
            canonical_url=canonical_url,
            canonical_url_hash=canonical_hash,
            primary_url=primary_url,
            title=title,
            summary=summary,
            author=plain_text(parsed.author or "", maximum=256) or None,
            publisher=plain_text(parsed.publisher or source.name, maximum=160) or source.name,
            published_at=parsed.published_at,
            source_updated_at=parsed.updated_at,
            doi=parsed.doi.lower() if parsed.doi else None,
            merge_reason=merge_reason,
            content_hash=content_hash,
            source_snapshot={
                "source_id": source.id,
                "external_id_hash": external_hash,
                "canonical_url_hash": canonical_hash,
                "content_hash": content_hash,
                "fetched_at": current.isoformat(),
                "summary_excerpt": summary[:MAX_SNAPSHOT_SUMMARY_CHARS],
            },
            fetched_at=current,
        )
        db.add(item)
        db.flush()
        counts["new"] += 1
        items = db.query(NewsItem).filter(NewsItem.cluster_id == cluster.id).all()
        representative_items = latest_items_by_source(items)
        primary = _pick_primary(db, cluster)
        cluster.primary_item_id = primary.id
        primary_source = db.get(NewsSource, primary.source_id)
        assert primary_source is not None
        score, topic, reasons, risks = score_candidate(
            primary_source,
            primary,
            supporting_source_count=max(0, len(representative_items) - 1),
            uncertain_duplicate=uncertain,
            now=current,
            allow_sensitive_manual_review=allow_sensitive_manual_review,
        )
        classification = classify_editorial_text(
            primary.title,
            primary.summary,
            source_type=primary_source.source_type,
            geography=tuple(primary_source.fetch_options.get("jurisdiction", []))
            if isinstance(primary_source.fetch_options, dict)
            else (),
        )
        policy = evaluate_publication_policy(classification)
        cluster.score = score
        cluster.topic = topic
        cluster.score_reasons = reasons
        cluster.risk_flags = risks
        cluster.primary_topic = classification.primary_topic
        cluster.topics = list(classification.topics)
        cluster.content_type = classification.content_type
        cluster.product_class = classification.product_class
        cluster.evidence_level = classification.evidence_level
        cluster.risk_level = classification.risk_level
        cluster.audience = classification.audience
        cluster.geography = list(classification.geography)
        cluster.classification_version = classification.classification_version
        cluster.classification_reasons = list(classification.classification_reasons)
        cluster.publication_policy = policy.publication_policy
        cluster.risk_reasons = list(dict.fromkeys((*classification.risk_reasons, *risks)))
        cluster.risk_policy_version = policy.risk_policy_version
        cluster.merge_reason = merge_reason
        conflicts: list[str] = []
        dates = [value.published_at for value in items if value.published_at]
        if dates and max(dates) - min(dates) > timedelta(days=2):
            conflicts.append("publication_dates_conflict")
        if any(_title_similarity(primary.title, value.title) < 0.35 for value in items):
            conflicts.append("title_claim_conflict")
        cluster.conflict_notes = conflicts
        if cluster.status in TERMINAL_CLUSTER_STATUSES:
            item.status = "clustered"
            counts["clustered"] += 1
            continue
        prohibited = any(flag.startswith("prohibited_") for flag in risks)
        hard_prohibited = prohibited and not allow_sensitive_manual_review
        fresh = "source_not_current_month" not in risks
        broad_recall_candidate = (
            fresh
            and source.source_type
            in {"primary_research", "systematic_review", "official_organization", "yfc"}
            and topic == "other"
            and bool(classification.topics)
            and not (
                "esport" in f"{primary.title} {primary.summary}".lower()
                and not any(
                    marker in f"{primary.title} {primary.summary}".lower()
                    for marker in ESPORTS_PHYSICAL_CONTEXT
                )
            )
            and not hard_prohibited
        )
        discovery_eligible = not hard_prohibited and (
            score >= candidate_threshold or broad_recall_candidate
        )
        cluster.discovery_eligible = discovery_eligible
        cluster.discovery_reasons = list(
            dict.fromkeys(
                [
                    "score_threshold_met"
                    if score >= candidate_threshold
                    else "broad_source_recall",
                    *classification.classification_reasons,
                    *(["source_not_current_month"] if not fresh else []),
                    *(["prohibited_content"] if hard_prohibited else []),
                    *(
                        ["sensitive_topic_manual_review"]
                        if prohibited and allow_sensitive_manual_review
                        else []
                    ),
                ]
            )
        )
        if hard_prohibited:
            transition_news_cluster(
                db,
                cluster,
                "rejected_by_rules",
                reason_code="prohibited_content_rule",
            )
            item.status = "rejected_by_rules"
            counts["rejected"] += 1
            _log_candidate(
                item=parsed,
                outcome="rejected",
                reason="prohibited_content_rule",
                score=score,
                topic=topic,
            )
        else:
            item.status = "clustered"
            if discovery_eligible:
                if cluster.status in {"clustered", "candidate"}:
                    transition_news_cluster(
                        db,
                        cluster,
                        "candidate",
                        reason_code="score_threshold_met",
                    )
                counts["candidate"] += 1
                counts["eligible"] += 1
                _log_candidate(
                    item=parsed,
                    outcome="eligible",
                    reason="score_threshold_met",
                    score=score,
                    topic=topic,
                )
            else:
                transition_news_cluster(
                    db,
                    cluster,
                    "clustered",
                    reason_code="score_below_threshold",
                )
                counts["clustered"] += 1
                if "source_not_current_month" in risks:
                    counts["stale"] += 1
                    reason = "source_not_current_month"
                elif "topic_not_allowlisted" in risks and not broad_recall_candidate:
                    reason = "topic_not_allowlisted"
                else:
                    counts["below_threshold"] += 1
                    reason = "score_below_threshold"
                _log_candidate(
                    item=parsed,
                    outcome="rejected",
                    reason=reason,
                    score=score,
                    topic=topic,
                )
    return counts
