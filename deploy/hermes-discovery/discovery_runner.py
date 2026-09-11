"""Bounded, source-only discovery runner for Task 129.

The runner is deliberately independent from the editorial worker.  It reads a
versioned allowlist rendered from the canonical YFC source registry, fetches only
those public feeds/pages, and writes immutable ``hermes-editorial-job-v1`` files
to a local outbox.  It has no provider, YFC, Telegram, database, shell, browser,
plugin or publication capability.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import html
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows unit-test fallback
    fcntl = None

SCHEMA_VERSION = "hermes-source-definitions-v1"
GENERATOR_VERSION = "task129-yfc-source-registry-renderer-v1"
SOURCE_REGISTRY_PATH = "backend/fitminiapp_api/resources/news_sources.json"
JOB_SCHEMA_VERSION = "hermes-editorial-job-v1"
STATE_SCHEMA_VERSION = "hermes-discovery-state-v1"
LOCAL_MOCK_MODE = "local_mock"
EXTERNAL_MODE = "external"
DISCOVERY_MODES = frozenset({LOCAL_MOCK_MODE, EXTERNAL_MODE})
SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
HOST_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$")
HEX_64_PATTERN = re.compile(r"^[0-9a-f]{64}$")
FETCH_KINDS = frozenset({"rss", "json_feed", "html_metadata"})
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "host.docker.internal"})
BLOCKED_HOSTS = frozenset(
    {
        "localhost.localdomain",
        "metadata",
        "metadata.google.internal",
        "instance-data.ec2.internal",
    }
)
SUPPORTED_TOPICS = frozenset(
    {
        "sports_nutrition",
        "dietary_supplements",
        "medicine",
        "health",
        "fitness",
        "exercise",
        "training",
        "cardio_endurance",
        "sports_medicine_injuries",
        "bodybuilding",
        "peptides",
        "nutrition",
        "food_products",
        "public_health",
        "healthy_lifestyle",
        "fitness_technology",
        "research",
        "guideline",
        "regulation",
        "product",
        "safety",
    }
)
MAX_DEFINITIONS_BYTES = 512 * 1024
MAX_SOURCES = 50
MAX_ITEMS_PER_SOURCE = 50
MAX_SOURCE_RESPONSE_BYTES = 512 * 1024
MAX_TITLE_CHARS = 500
MAX_SUMMARY_CHARS = 4000
MAX_CONTENT_CHARS = 32 * 1024
MAX_JOB_BYTES = 96 * 1024
MAX_REDIRECTS = 3
MAX_CANDIDATES_IN_STATE = 2000
MAX_SOURCE_STATE_ENTRIES = 100
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_CONCURRENCY = 4
DEFAULT_MAX_ITEMS_PER_SOURCE = 20
DEFAULT_LOCK_STALE_SECONDS = 900.0
USER_AGENT = "YourFitnessCoach-HermesDiscovery/1.0"
TRACKING_PARAMS = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src"})


class DiscoveryError(RuntimeError):
    """Stable error code that is safe to emit without source content or secrets."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SourceDefinition:
    source_id: str
    name: str
    source_type: str
    fetch_kind: str
    url: str
    language: str
    enabled: bool
    topics: tuple[str, ...]
    authoritative: bool
    allowed_redirect_hosts: tuple[str, ...]
    allowed_item_hosts: tuple[str, ...]


@dataclass(frozen=True)
class ParsedCandidate:
    external_id: str
    canonical_url: str
    title: str
    summary: str
    content: str
    primary_url: str | None = None
    author: str | None = None
    publisher: str | None = None
    published_at: datetime | None = None
    updated_at: datetime | None = None
    doi: str | None = None


@dataclass(frozen=True)
class FetchResult:
    status: str
    items: tuple[ParsedCandidate, ...] = ()
    etag: str | None = None
    last_modified: str | None = None
    body_hash: str | None = None


@dataclass(frozen=True)
class SourceFetchOutcome:
    source: SourceDefinition
    result: FetchResult | None = None
    error_code: str | None = None


def _normalise_host(value: object) -> str:
    if not isinstance(value, str):
        raise DiscoveryError("source_host_invalid")
    host = value.strip().casefold().rstrip(".")
    if (
        not host
        or not HOST_PATTERN.fullmatch(host)
        or ".." in host
        or "*" in host
        or host in BLOCKED_HOSTS
    ):
        raise DiscoveryError("source_host_invalid")
    return host


def _clean_text(value: object, *, maximum: int) -> str:
    text = html.unescape(str(value or ""))
    text = "".join(char for char in text if ord(char) >= 32 or char in "\n\t")
    return " ".join(text.split())[:maximum].strip()


class _PlainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_text(value: object, *, maximum: int) -> str:
    parser = _PlainTextParser()
    try:
        parser.feed(str(value or ""))
        parser.close()
    except (RecursionError, ValueError) as exc:
        raise DiscoveryError("source_markup_invalid") from exc
    return _clean_text(" ".join(parser.parts), maximum=maximum)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(normalized)
        except (TypeError, ValueError, OverflowError):  # fmt: skip
            return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(UTC).replace(tzinfo=None)


def _iso_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _canonical_url(value: str) -> str:
    if any(ord(char) < 32 for char in value):
        raise DiscoveryError("source_url_invalid")
    parsed = urlsplit(html.unescape(value.strip()))
    if not parsed.scheme or not parsed.hostname or parsed.username or parsed.password:
        raise DiscoveryError("source_url_invalid")
    try:
        port = parsed.port
    except ValueError as exc:
        raise DiscoveryError("source_url_invalid") from exc
    hostname = parsed.hostname.casefold().rstrip(".")
    _normalise_host(hostname)
    if port and not (
        (parsed.scheme.casefold() == "https" and port == 443)
        or (parsed.scheme.casefold() == "http" and port == 80)
    ):
        netloc = f"{hostname}:{port}"
    else:
        netloc = hostname
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() not in TRACKING_PARAMS and not key.casefold().startswith("utm_")
    ]
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            netloc,
            parsed.path or "/",
            urlencode(sorted(query_pairs)),
            "",
        )
    )


def _validate_fetch_url(
    value: str,
    *,
    mode: str,
    allowed_hosts: frozenset[str],
) -> str:
    try:
        normalized = _canonical_url(value)
        parsed = urlsplit(normalized)
        port = parsed.port
    except DiscoveryError:
        raise
    except ValueError as exc:
        raise DiscoveryError("source_url_invalid") from exc
    hostname = (parsed.hostname or "").casefold().rstrip(".")
    try:
        literal_address = ipaddress.ip_address(hostname)
    except ValueError:
        literal_address = None
    if literal_address is not None and not (mode == LOCAL_MOCK_MODE and hostname in LOCAL_HOSTS):
        if not literal_address.is_global:
            raise DiscoveryError("source_private_network_blocked")
        raise DiscoveryError("source_host_not_allowlisted")
    if hostname not in allowed_hosts:
        raise DiscoveryError("source_host_not_allowlisted")
    if parsed.fragment or parsed.username or parsed.password:
        raise DiscoveryError("source_url_invalid")
    if mode == LOCAL_MOCK_MODE:
        if parsed.scheme != "http" or hostname not in LOCAL_HOSTS or port is None:
            raise DiscoveryError("local_source_url_not_allowlisted")
        return normalized
    if parsed.scheme != "https" or port not in {None, 443}:
        raise DiscoveryError("source_https_required")
    return normalized


def _validate_item_url(
    value: str,
    *,
    base_url: str,
    mode: str,
    allowed_hosts: frozenset[str],
) -> str:
    try:
        normalized = _canonical_url(urljoin(base_url, value))
        parsed = urlsplit(normalized)
        port = parsed.port
    except (DiscoveryError, ValueError) as exc:
        raise DiscoveryError("item_url_invalid") from exc
    hostname = (parsed.hostname or "").casefold().rstrip(".")
    if hostname not in allowed_hosts or parsed.username or parsed.password or parsed.fragment:
        raise DiscoveryError("item_url_not_allowlisted")
    if mode == LOCAL_MOCK_MODE:
        if hostname in LOCAL_HOSTS and (parsed.scheme != "http" or port is None):
            raise DiscoveryError("item_url_not_allowlisted")
        if hostname not in LOCAL_HOSTS and (parsed.scheme != "https" or port not in {None, 443}):
            raise DiscoveryError("item_url_not_allowlisted")
    elif parsed.scheme != "https" or port not in {None, 443}:
        raise DiscoveryError("item_url_not_allowlisted")
    if mode == EXTERNAL_MODE:
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            raise DiscoveryError("item_url_not_allowlisted")
    return normalized


def _first_text(element: ET.Element, names: frozenset[str]) -> str | None:
    for child in element.iter():
        if child.tag.rsplit("}", 1)[-1].casefold() in names:
            text = "".join(child.itertext()).strip()
            if text:
                return text
    return None


def _first_link(element: ET.Element) -> str | None:
    for child in element.iter():
        if child.tag.rsplit("}", 1)[-1].casefold() != "link":
            continue
        href = child.attrib.get("href")
        rel = child.attrib.get("rel", "alternate").casefold()
        if href and rel in {"alternate", "canonical"}:
            return href.strip()
        if child.text and child.text.strip():
            return child.text.strip()
    return None


def _doi(*values: str | None) -> str | None:
    pattern = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
    for value in values:
        if not value:
            continue
        match = pattern.search(value)
        if match:
            return match.group(0).rstrip(".,;)").casefold()
    return None


def _candidate_from_values(
    *,
    external_id: object,
    link: object,
    title: object,
    summary: object,
    content: object,
    base_url: str,
    publisher: str | None = None,
    author: str | None = None,
    published_at: object = None,
    updated_at: object = None,
    primary_url: str | None = None,
    doi: str | None = None,
) -> ParsedCandidate | None:
    if not isinstance(link, str) or not link.strip():
        return None
    clean_title = _plain_text(title, maximum=MAX_TITLE_CHARS)
    if not clean_title:
        return None
    clean_summary = _plain_text(summary, maximum=MAX_SUMMARY_CHARS)
    clean_content = _plain_text(content or summary or title, maximum=MAX_CONTENT_CHARS)
    if not clean_content:
        return None
    absolute_link = urljoin(base_url, link.strip())
    identifier = _clean_text(external_id or absolute_link, maximum=512) or absolute_link
    return ParsedCandidate(
        external_id=identifier,
        canonical_url=absolute_link,
        title=clean_title,
        summary=clean_summary,
        content=clean_content,
        primary_url=primary_url,
        author=_plain_text(author, maximum=256) or None,
        publisher=_plain_text(publisher, maximum=160) or None,
        published_at=_parse_datetime(published_at),
        updated_at=_parse_datetime(updated_at),
        doi=doi,
    )


def _parse_rss(body: bytes, base_url: str, publisher: str) -> tuple[ParsedCandidate, ...]:
    lowered = body.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered or b"<![doctype" in lowered:
        raise DiscoveryError("source_unsafe_xml")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise DiscoveryError("source_malformed_feed") from exc
    entries = [
        element
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1].casefold() in {"item", "entry"}
    ][:MAX_ITEMS_PER_SOURCE]
    candidates: list[ParsedCandidate] = []
    for entry in entries:
        title = _first_text(entry, frozenset({"title"}))
        link = _first_link(entry)
        summary = _first_text(entry, frozenset({"summary", "description", "content", "encoded"}))
        candidate = _candidate_from_values(
            external_id=_first_text(entry, frozenset({"guid", "id"})) or link,
            link=link,
            title=title,
            summary=summary,
            content=summary,
            base_url=base_url,
            publisher=publisher,
            author=_first_text(entry, frozenset({"author", "creator"})),
            published_at=_first_text(entry, frozenset({"published", "pubdate", "date"})),
            updated_at=_first_text(entry, frozenset({"updated", "modified"})),
            doi=_doi(_first_text(entry, frozenset({"doi", "identifier"})), link, summary),
        )
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates)


def _parse_json_feed(body: bytes, base_url: str, publisher: str) -> tuple[ParsedCandidate, ...]:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiscoveryError("source_malformed_feed") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise DiscoveryError("source_malformed_feed")
    feed_publisher = _plain_text(payload.get("title") or publisher, maximum=160) or publisher
    candidates: list[ParsedCandidate] = []
    for raw in payload["items"][:MAX_ITEMS_PER_SOURCE]:
        if not isinstance(raw, dict):
            continue
        summary = raw.get("summary") or raw.get("content_text") or raw.get("content_html")
        authors = raw.get("authors")
        author = None
        if isinstance(authors, list) and authors and isinstance(authors[0], dict):
            author = authors[0].get("name")
        candidate = _candidate_from_values(
            external_id=raw.get("id") or raw.get("url") or raw.get("external_url"),
            link=raw.get("url") or raw.get("external_url"),
            title=raw.get("title"),
            summary=summary,
            content=raw.get("content_text") or raw.get("content_html") or summary,
            base_url=base_url,
            publisher=feed_publisher,
            author=author,
            published_at=raw.get("date_published"),
            updated_at=raw.get("date_modified"),
            doi=_doi(str(raw.get("id", "")), str(raw.get("url", "")), str(summary or "")),
        )
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates)


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.metadata: dict[str, str] = {}
        self.canonical: str | None = None
        self.in_title = False
        self.title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value for key, value in attrs if value is not None}
        if tag.casefold() == "meta":
            key = (values.get("property") or values.get("name") or "").casefold()
            content = values.get("content")
            if key and content and len(content) <= MAX_SUMMARY_CHARS:
                self.metadata[key] = content
        if tag.casefold() == "link" and values.get("rel", "").casefold() == "canonical":
            self.canonical = values.get("href")
        if tag.casefold() == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)


def _parse_html_metadata(body: bytes, base_url: str, publisher: str) -> tuple[ParsedCandidate, ...]:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DiscoveryError("source_malformed_content") from exc
    parser = _MetadataParser()
    try:
        parser.feed(text)
        parser.close()
    except (RecursionError, ValueError) as exc:
        raise DiscoveryError("source_markup_invalid") from exc
    title = parser.metadata.get("og:title") or " ".join(parser.title_parts)
    link = urljoin(base_url, parser.canonical or parser.metadata.get("og:url") or base_url)
    summary = parser.metadata.get("og:description") or parser.metadata.get("description") or ""
    doi = _doi(parser.metadata.get("citation_doi"), link, summary)
    candidate = _candidate_from_values(
        external_id=link,
        link=link,
        title=title,
        summary=summary,
        content=summary or title,
        base_url=base_url,
        publisher=parser.metadata.get("og:site_name") or publisher,
        author=parser.metadata.get("author") or parser.metadata.get("article:author"),
        published_at=parser.metadata.get("article:published_time"),
        updated_at=parser.metadata.get("article:modified_time"),
        primary_url=f"https://doi.org/{doi}" if doi else None,
        doi=doi,
    )
    return (candidate,) if candidate is not None else ()


def _parse_body(
    fetch_kind: str, body: bytes, base_url: str, publisher: str
) -> tuple[ParsedCandidate, ...]:
    if fetch_kind == "rss":
        return _parse_rss(body, base_url, publisher)
    if fetch_kind == "json_feed":
        return _parse_json_feed(body, base_url, publisher)
    if fetch_kind == "html_metadata":
        return _parse_html_metadata(body, base_url, publisher)
    raise DiscoveryError("source_fetch_kind_invalid")


def _default_resolver(host: str, port: int) -> tuple[str, ...]:
    try:
        rows = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise DiscoveryError("source_dns_error") from exc
    addresses = tuple(sorted({str(row[4][0]) for row in rows}))
    if not addresses:
        raise DiscoveryError("source_dns_error")
    return addresses


def _resolve_public(host: str, port: int) -> tuple[str, ...]:
    addresses = _default_resolver(host, port)
    try:
        parsed = tuple(ipaddress.ip_address(address) for address in addresses)
    except ValueError as exc:
        raise DiscoveryError("source_dns_error") from exc
    if any(not address.is_global for address in parsed):
        raise DiscoveryError("source_private_network_blocked")
    return addresses


def _media_type(value: str | None) -> str:
    return (value or "").split(";", 1)[0].strip().casefold()


def _allowed_content_types(fetch_kind: str) -> frozenset[str]:
    return {
        "rss": frozenset(
            {"application/rss+xml", "application/atom+xml", "application/xml", "text/xml"}
        ),
        "json_feed": frozenset({"application/feed+json", "application/json"}),
        "html_metadata": frozenset({"text/html", "application/xhtml+xml"}),
    }.get(fetch_kind, frozenset())


def _http_get(
    url: str,
    *,
    mode: str,
    allowed_hosts: frozenset[str],
    accept: str,
    timeout_seconds: float,
    max_bytes: int,
    headers: Mapping[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    normalized = _validate_fetch_url(url, mode=mode, allowed_hosts=allowed_hosts)
    parsed = urlsplit(normalized)
    hostname = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = (
        _resolve_public(hostname, port)
        if mode == EXTERNAL_MODE
        else _default_resolver(hostname, port)
    )
    target = parsed.path or "/"
    if parsed.query:
        target += f"?{parsed.query}"
    request_headers = {
        "Accept": accept,
        "Accept-Encoding": "identity",
        "Connection": "close",
        "Host": hostname if port in {80, 443} else f"{hostname}:{port}",
        "User-Agent": USER_AGENT,
    }
    if headers:
        request_headers.update(headers)
    last_error: DiscoveryError | None = None
    timed_out = False
    for address in addresses:
        started = time.monotonic()
        transport: socket.socket | ssl.SSLSocket | None = None
        response: http.client.HTTPResponse | None = None
        try:
            transport = socket.create_connection((address, port), timeout=timeout_seconds)
            transport.settimeout(timeout_seconds)
            if parsed.scheme == "https":
                context = ssl.create_default_context()
                transport = context.wrap_socket(transport, server_hostname=hostname)
                transport.settimeout(timeout_seconds)
            request = (
                "GET "
                + target
                + " HTTP/1.1\r\n"
                + "".join(f"{key}: {value}\r\n" for key, value in request_headers.items())
                + "\r\n"
            )
            transport.sendall(request.encode("ascii"))
            response = http.client.HTTPResponse(transport, method="GET")
            response.begin()
            response_headers = {
                key.casefold(): value.strip() for key, value in response.getheaders()
            }
            content_length = response_headers.get("content-length")
            if content_length is not None and (
                not content_length.isdigit() or int(content_length) > max_bytes
            ):
                raise DiscoveryError("source_content_too_large")
            if _media_type(response_headers.get("content-encoding")) not in {"", "identity"}:
                raise DiscoveryError("source_content_encoding_unsupported")
            if 300 <= response.status < 400:
                return response.status, response_headers, b""
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise DiscoveryError("source_content_too_large")
            return response.status, response_headers, body
        except DiscoveryError:
            raise
        except TimeoutError:
            last_error = DiscoveryError("source_timeout")
            timed_out = True
        except http.client.RemoteDisconnected:
            if time.monotonic() - started >= timeout_seconds * 0.75:
                last_error = DiscoveryError("source_timeout")
                timed_out = True
            else:
                last_error = DiscoveryError("source_network_error")
        except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
            if (
                isinstance(exc, TimeoutError)
                or getattr(exc, "errno", None) in {11, 60, 104, 110, 10054, 10060}
                or (
                    isinstance(exc, ConnectionResetError)
                    and time.monotonic() - started >= timeout_seconds * 0.75
                )
            ):
                last_error = DiscoveryError("source_timeout")
                timed_out = True
            else:
                last_error = DiscoveryError("source_network_error")
        finally:
            if response is not None:
                response.close()
            if transport is not None:
                transport.close()
    if timed_out:
        raise DiscoveryError("source_timeout")
    raise last_error or DiscoveryError("source_network_error")


def fetch_source(
    source: SourceDefinition,
    *,
    mode: str,
    timeout_seconds: float,
    max_bytes: int,
    max_items: int,
    state_entry: Mapping[str, Any] | None,
) -> FetchResult:
    source_url = _canonical_url(source.url)
    source_host = (urlsplit(source_url).hostname or "").casefold().rstrip(".")
    allowed_hosts = frozenset(
        {source_host, *source.allowed_redirect_hosts}
        if mode == EXTERNAL_MODE
        else {source_host, *source.allowed_redirect_hosts, *LOCAL_HOSTS}
    )
    request_headers: dict[str, str] = {}
    if state_entry:
        etag = state_entry.get("etag")
        last_modified = state_entry.get("last_modified")
        if isinstance(etag, str) and etag:
            request_headers["If-None-Match"] = etag
        if isinstance(last_modified, str) and last_modified:
            request_headers["If-Modified-Since"] = last_modified
    current_url = source_url
    for redirect_count in range(MAX_REDIRECTS + 1):
        current_url = _validate_fetch_url(current_url, mode=mode, allowed_hosts=allowed_hosts)
        status, headers, body = _http_get(
            current_url,
            mode=mode,
            allowed_hosts=allowed_hosts,
            accept=", ".join(sorted(_allowed_content_types(source.fetch_kind))),
            timeout_seconds=timeout_seconds,
            max_bytes=max_bytes,
            headers=request_headers,
        )
        if status == 304:
            return FetchResult(status="not_modified")
        if 300 <= status < 400:
            if redirect_count >= MAX_REDIRECTS:
                raise DiscoveryError("source_too_many_redirects")
            location = headers.get("location")
            if not location:
                raise DiscoveryError("source_redirect_invalid")
            current_url = urljoin(current_url, location)
            request_headers.pop("If-None-Match", None)
            request_headers.pop("If-Modified-Since", None)
            continue
        if status == 429:
            raise DiscoveryError("source_rate_limited")
        if status >= 500:
            raise DiscoveryError("source_upstream_error")
        if status >= 400:
            raise DiscoveryError(f"source_http_{status}")
        if status < 200:
            raise DiscoveryError("source_http_invalid")
        content_type = _media_type(headers.get("content-type"))
        if content_type not in _allowed_content_types(source.fetch_kind):
            raise DiscoveryError("source_invalid_mime")
        parsed_items = _parse_body(source.fetch_kind, body, current_url, source.name)
        return FetchResult(
            status="fetched",
            items=tuple(parsed_items[:max_items]),
            etag=headers.get("etag"),
            last_modified=headers.get("last-modified"),
            body_hash=hashlib.sha256(body).hexdigest(),
        )
    raise DiscoveryError("source_too_many_redirects")


def _validate_source_definition(raw: object) -> SourceDefinition:
    if not isinstance(raw, dict):
        raise DiscoveryError("source_definition_invalid")
    source_id = raw.get("id")
    if not isinstance(source_id, str) or SOURCE_ID_PATTERN.fullmatch(source_id) is None:
        raise DiscoveryError("source_id_invalid")
    name = raw.get("name")
    source_type = raw.get("type")
    fetch_kind = raw.get("fetch_kind")
    language = raw.get("language")
    topics = raw.get("topics")
    if (
        not isinstance(name, str)
        or not 1 <= len(name.strip()) <= 160
        or not isinstance(source_type, str)
        or not 1 <= len(source_type) <= 64
        or fetch_kind not in FETCH_KINDS
        or not isinstance(language, str)
        or not re.fullmatch(r"[a-z]{2,8}(?:-[A-Z]{2})?", language)
        or not isinstance(raw.get("enabled"), bool)
        or not isinstance(raw.get("authoritative"), bool)
        or not isinstance(topics, list)
        or not 1 <= len(topics) <= 20
        or len(set(topics)) != len(topics)
        or any(not isinstance(topic, str) or topic not in SUPPORTED_TOPICS for topic in topics)
    ):
        raise DiscoveryError("source_definition_invalid")
    try:
        url = _canonical_url(str(raw.get("url", "")))
    except (DiscoveryError, TypeError) as exc:
        raise DiscoveryError("source_definition_invalid") from exc
    allowed_redirect_hosts = _host_tuple(raw.get("allowed_redirect_hosts"))
    allowed_item_hosts = _host_tuple(raw.get("allowed_item_hosts"))
    return SourceDefinition(
        source_id=source_id,
        name=name.strip(),
        source_type=source_type,
        fetch_kind=fetch_kind,
        url=url,
        language=language,
        enabled=bool(raw["enabled"]),
        topics=tuple(topics),
        authoritative=bool(raw["authoritative"]),
        allowed_redirect_hosts=allowed_redirect_hosts,
        allowed_item_hosts=allowed_item_hosts,
    )


def _host_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > 12:
        raise DiscoveryError("source_host_list_invalid")
    hosts = tuple(_normalise_host(item) for item in value)
    if len(set(hosts)) != len(hosts):
        raise DiscoveryError("source_host_list_duplicate")
    return tuple(sorted(hosts))


def load_source_definitions(
    path: Path, *, mode: str
) -> tuple[dict[str, Any], tuple[SourceDefinition, ...]]:
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise DiscoveryError("source_definitions_unavailable") from exc
    if len(raw_bytes) > MAX_DEFINITIONS_BYTES:
        raise DiscoveryError("source_definitions_too_large")
    expected_digest = os.environ.get("HERMES_DISCOVERY_DEFINITIONS_SHA256", "").strip().casefold()
    if mode == EXTERNAL_MODE:
        if HEX_64_PATTERN.fullmatch(expected_digest) is None:
            raise DiscoveryError("source_definitions_integrity_invalid")
        if hashlib.sha256(raw_bytes).hexdigest() != expected_digest:
            raise DiscoveryError("source_definitions_integrity_invalid")
    try:
        document = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiscoveryError("source_definitions_invalid") from exc
    if not isinstance(document, dict):
        raise DiscoveryError("source_definitions_invalid")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise DiscoveryError("source_definitions_version_invalid")
    if (
        document.get("generator") != GENERATOR_VERSION
        or document.get("source_registry") != SOURCE_REGISTRY_PATH
    ):
        raise DiscoveryError("source_definitions_provenance_invalid")
    registry_hash = document.get("source_registry_sha256")
    if not isinstance(registry_hash, str) or HEX_64_PATTERN.fullmatch(registry_hash) is None:
        raise DiscoveryError("source_definitions_provenance_invalid")
    if document.get("definitions_version") != f"yfc-news-sources:{registry_hash}":
        raise DiscoveryError("source_definitions_provenance_invalid")
    supported_topics = document.get("supported_topics")
    if not isinstance(supported_topics, list) or set(supported_topics) != SUPPORTED_TOPICS:
        raise DiscoveryError("source_definitions_topics_invalid")
    raw_sources = document.get("sources")
    if not isinstance(raw_sources, list) or not 1 <= len(raw_sources) <= MAX_SOURCES:
        raise DiscoveryError("source_definitions_sources_invalid")
    sources = tuple(_validate_source_definition(item) for item in raw_sources)
    source_ids = [source.source_id for source in sources]
    if len(set(source_ids)) != len(source_ids):
        raise DiscoveryError("source_id_duplicate")
    for source in sources:
        if not source.enabled:
            continue
        _validate_fetch_url(
            source.url,
            mode=mode,
            allowed_hosts=frozenset(
                {urlsplit(source.url).hostname or "", *source.allowed_redirect_hosts, *LOCAL_HOSTS}
            ),
        )
    return document, sources


def _default_state() -> dict[str, Any]:
    return {"schema_version": STATE_SCHEMA_VERSION, "sources": {}, "candidates": {}}


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _default_state()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiscoveryError("discovery_state_invalid") from exc
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != STATE_SCHEMA_VERSION
        or not isinstance(document.get("sources"), dict)
        or not isinstance(document.get("candidates"), dict)
    ):
        raise DiscoveryError("discovery_state_invalid")
    if (
        len(document["sources"]) > MAX_SOURCE_STATE_ENTRIES
        or len(document["candidates"]) > MAX_CANDIDATES_IN_STATE
    ):
        raise DiscoveryError("discovery_state_bounds_exceeded")
    return document


def _file_owner(path: Path) -> tuple[int, int] | None:
    try:
        metadata = path.stat()
    except FileNotFoundError:
        return None
    uid = getattr(metadata, "st_uid", None)
    gid = getattr(metadata, "st_gid", None)
    if isinstance(uid, int) and isinstance(gid, int):
        return uid, gid
    return None


def _restore_file_owner(path: Path, owner: tuple[int, int] | None) -> None:
    if owner is None or _file_owner(path) == owner:
        return
    chown = getattr(os, "chown", None)
    if chown is None:
        raise DiscoveryError("state_owner_preservation_unsupported")
    try:
        chown(path, *owner)
    except OSError as exc:
        raise DiscoveryError("state_owner_preservation_failed") from exc
    if _file_owner(path) != owner:
        raise DiscoveryError("state_owner_preservation_failed")


def _atomic_write_json(path: Path, document: Mapping[str, Any]) -> None:
    owner = _file_owner(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        _restore_file_owner(temporary, owner)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


@contextlib.contextmanager
def _exclusive_lock(path: Path, *, stale_seconds: float) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fcntl is not None:
        handle = path.open("a+", encoding="ascii")
        try:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise DiscoveryError("scheduler_overlap") from exc
            yield
        finally:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()
        return
    acquired = False
    for attempt in range(2):
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            try:
                is_stale = time.time() - path.stat().st_mtime > stale_seconds
            except OSError:
                is_stale = False
            if attempt == 0 and is_stale:
                with contextlib.suppress(OSError):
                    path.unlink()
                continue
            raise DiscoveryError("scheduler_overlap") from exc
        else:
            try:
                os.write(
                    descriptor, f"pid={os.getpid()}\nstarted={time.time():.3f}\n".encode("ascii")
                )
            finally:
                os.close(descriptor)
            acquired = True
            break
    if not acquired:
        raise DiscoveryError("scheduler_overlap")
    try:
        yield
    finally:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()


def _bounded_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise DiscoveryError(f"{name.casefold()}_invalid") from exc
    if not minimum <= value <= maximum:
        raise DiscoveryError(f"{name.casefold()}_invalid")
    return value


def _bounded_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise DiscoveryError(f"{name.casefold()}_invalid") from exc
    if not minimum <= value <= maximum:
        raise DiscoveryError(f"{name.casefold()}_invalid")
    return value


def _mode() -> str:
    value = os.environ.get("HERMES_DISCOVERY_MODE", EXTERNAL_MODE).strip().casefold()
    if value not in DISCOVERY_MODES:
        raise DiscoveryError("hermes_discovery_mode_invalid")
    return value


def _candidate_content_hash(candidate: ParsedCandidate) -> str:
    return hashlib.sha256(candidate.content.encode("utf-8")).hexdigest()


def _event_date(candidate: ParsedCandidate) -> str:
    value = candidate.published_at or candidate.updated_at
    return value.date().isoformat() if value else ""


def _candidate_key(source_id: str, candidate: ParsedCandidate) -> str:
    values = (
        source_id,
        candidate.canonical_url,
        _candidate_content_hash(candidate),
        _event_date(candidate),
    )
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def _job_document(source_id: str, candidate: ParsedCandidate, key: str) -> dict[str, Any]:
    return {
        "schema_version": JOB_SCHEMA_VERSION,
        "job_id": f"job-{key}",
        "idempotency_key": f"discovery-{key}",
        "request_nonce": f"nonce-{key}",
        "source": {
            "source_id": source_id,
            "external_id": candidate.external_id,
            "canonical_url": candidate.canonical_url,
            "primary_url": candidate.primary_url,
            "title": candidate.title,
            "summary": candidate.summary,
            "content": candidate.content,
            "author": candidate.author,
            "publisher": candidate.publisher,
            "published_at": _iso_datetime(candidate.published_at),
            "updated_at": _iso_datetime(candidate.updated_at),
            "doi": candidate.doi,
        },
    }


def _write_job(outbox: Path, key: str, document: Mapping[str, Any]) -> bool:
    outbox.mkdir(parents=True, exist_ok=True)
    target = outbox / f"{key}.json"
    if target.exists():
        return False
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=outbox, prefix=f".{key}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            raw = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            if len(raw.encode("utf-8")) > MAX_JOB_BYTES:
                raise DiscoveryError("candidate_job_too_large")
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        try:
            os.link(temporary, target)
        except FileExistsError:
            return False
        finally:
            temporary.unlink(missing_ok=True)
        return True
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _trim_state(state: dict[str, Any]) -> None:
    candidates = state["candidates"]
    if len(candidates) > MAX_CANDIDATES_IN_STATE:
        ordered = sorted(
            candidates.items(), key=lambda pair: str(pair[1].get("created_at", "")), reverse=True
        )[:MAX_CANDIDATES_IN_STATE]
        state["candidates"] = dict(ordered)
    sources = state["sources"]
    if len(sources) > MAX_SOURCE_STATE_ENTRIES:
        state["sources"] = dict(sorted(sources.items())[:MAX_SOURCE_STATE_ENTRIES])


def _source_outcome(
    source: SourceDefinition,
    *,
    mode: str,
    timeout_seconds: float,
    max_bytes: int,
    max_items: int,
    state_entry: Mapping[str, Any] | None,
) -> SourceFetchOutcome:
    try:
        result = fetch_source(
            source,
            mode=mode,
            timeout_seconds=timeout_seconds,
            max_bytes=max_bytes,
            max_items=max_items,
            state_entry=state_entry,
        )
    except DiscoveryError as exc:
        return SourceFetchOutcome(source=source, error_code=exc.code)
    except (AttributeError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError):  # fmt: skip
        return SourceFetchOutcome(source=source, error_code="source_internal_error")
    return SourceFetchOutcome(source=source, result=result)


def run_once(
    *,
    definitions_path: Path,
    state_dir: Path,
    outbox_dir: Path,
    mode: str,
) -> dict[str, Any]:
    definitions, all_sources = load_source_definitions(definitions_path, mode=mode)
    sources = tuple(source for source in all_sources if source.enabled)
    max_sources = _bounded_int(
        "HERMES_DISCOVERY_MAX_SOURCES", len(sources) or 1, minimum=1, maximum=MAX_SOURCES
    )
    if len(sources) > max_sources:
        sources = sources[:max_sources]
    timeout_seconds = _bounded_float(
        "HERMES_DISCOVERY_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, minimum=0.2, maximum=30
    )
    max_bytes = _bounded_int(
        "HERMES_DISCOVERY_MAX_RESPONSE_BYTES",
        MAX_SOURCE_RESPONSE_BYTES,
        minimum=16 * 1024,
        maximum=MAX_SOURCE_RESPONSE_BYTES,
    )
    max_items = _bounded_int(
        "HERMES_DISCOVERY_MAX_ITEMS_PER_SOURCE",
        DEFAULT_MAX_ITEMS_PER_SOURCE,
        minimum=1,
        maximum=MAX_ITEMS_PER_SOURCE,
    )
    max_concurrency = _bounded_int(
        "HERMES_DISCOVERY_MAX_CONCURRENCY",
        DEFAULT_MAX_CONCURRENCY,
        minimum=1,
        maximum=8,
    )
    stale_seconds = _bounded_float(
        "HERMES_DISCOVERY_LOCK_STALE_SECONDS",
        DEFAULT_LOCK_STALE_SECONDS,
        minimum=30,
        maximum=86_400,
    )
    state_dir.mkdir(parents=True, exist_ok=True)
    outbox_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "state.json"
    run_lock = state_dir / ".discovery-run.lock"
    state_lock = state_dir / ".state.lock"
    with (
        _exclusive_lock(run_lock, stale_seconds=stale_seconds),
        _exclusive_lock(state_lock, stale_seconds=stale_seconds),
    ):
        state = _load_state(state_path)
        state["source_definitions_version"] = definitions["definitions_version"]
        state["source_registry_sha256"] = definitions["source_registry_sha256"]
        state["last_run_at"] = datetime.now(UTC).replace(microsecond=0).isoformat()
        outcomes: list[SourceFetchOutcome] = []
        with ThreadPoolExecutor(
            max_workers=max_concurrency, thread_name_prefix="hermes-discovery"
        ) as pool:
            futures = {
                pool.submit(
                    _source_outcome,
                    source,
                    mode=mode,
                    timeout_seconds=timeout_seconds,
                    max_bytes=max_bytes,
                    max_items=max_items,
                    state_entry=state["sources"].get(source.source_id),
                ): source
                for source in sources
            }
            for future in as_completed(futures):
                outcomes.append(future.result())
        outcomes.sort(key=lambda outcome: outcome.source.source_id)
        created = 0
        duplicates = 0
        source_errors: list[dict[str, str]] = []
        fetched_sources = 0
        for outcome in outcomes:
            source = outcome.source
            source_state = state["sources"].setdefault(source.source_id, {})
            source_state["last_attempt_at"] = state["last_run_at"]
            if outcome.error_code:
                source_state.update({"status": "error", "error_code": outcome.error_code})
                source_errors.append({"source_id": source.source_id, "code": outcome.error_code})
                continue
            result = outcome.result
            if result is None:
                source_state.update({"status": "error", "error_code": "source_internal_error"})
                source_errors.append(
                    {"source_id": source.source_id, "code": "source_internal_error"}
                )
                continue
            source_state.update(
                {
                    "status": result.status,
                    "error_code": None,
                    "etag": result.etag,
                    "last_modified": result.last_modified,
                    "last_success_at": state["last_run_at"],
                    "body_hash": result.body_hash,
                }
            )
            if result.status == "fetched":
                fetched_sources += 1
            allowed_item_hosts = frozenset(
                {
                    (urlsplit(source.url).hostname or "").casefold().rstrip("."),
                    *source.allowed_item_hosts,
                    *source.allowed_redirect_hosts,
                    *(LOCAL_HOSTS if mode == LOCAL_MOCK_MODE else ()),
                }
            )
            for candidate in result.items:
                try:
                    normalized_url = _validate_item_url(
                        candidate.canonical_url,
                        base_url=source.url,
                        mode=mode,
                        allowed_hosts=allowed_item_hosts,
                    )
                except DiscoveryError:
                    continue
                normalized_candidate = ParsedCandidate(
                    external_id=candidate.external_id,
                    canonical_url=normalized_url,
                    title=candidate.title,
                    summary=candidate.summary,
                    content=candidate.content,
                    primary_url=candidate.primary_url,
                    author=candidate.author,
                    publisher=candidate.publisher or source.name,
                    published_at=candidate.published_at,
                    updated_at=candidate.updated_at,
                    doi=candidate.doi,
                )
                key = _candidate_key(source.source_id, normalized_candidate)
                existing = state["candidates"].get(key)
                if existing is not None or key + ".json" in {
                    path.name for path in outbox_dir.glob("*.json")
                }:
                    duplicates += 1
                    continue
                document = _job_document(source.source_id, normalized_candidate, key)
                if _write_job(outbox_dir, key, document):
                    created += 1
                    state["candidates"][key] = {
                        "status": "pending",
                        "job_id": document["job_id"],
                        "idempotency_key": document["idempotency_key"],
                        "source_id": source.source_id,
                        "canonical_url": normalized_url,
                        "content_hash": _candidate_content_hash(normalized_candidate),
                        "event_date": _event_date(normalized_candidate),
                        "created_at": state["last_run_at"],
                    }
                else:
                    duplicates += 1
        _trim_state(state)
        _atomic_write_json(state_path, state)
    status = "completed" if not source_errors else ("partial" if fetched_sources else "failed")
    return {
        "status": status,
        "mode": mode,
        "definitions_version": definitions["definitions_version"],
        "enabled_source_count": len(sources),
        "fetched_source_count": fetched_sources,
        "source_error_count": len(source_errors),
        "source_errors": source_errors,
        "candidates_created": created,
        "duplicates": duplicates,
        "outbox_pending": len(list(outbox_dir.glob("*.json"))),
        "publication": "not evaluated by discovery; YFC intake owns taxonomy/risk/publication",
    }


def mark_candidate_status(
    state_dir: Path,
    key: str,
    status: str,
    *,
    stale_seconds: float,
    error_code: str | None = None,
) -> None:
    if not HEX_64_PATTERN.fullmatch(key) or status not in {
        "accepted",
        "duplicate",
        "failed",
        "pending",
    }:
        raise DiscoveryError("candidate_status_invalid")
    state_path = state_dir / "state.json"
    with _exclusive_lock(state_dir / ".state.lock", stale_seconds=stale_seconds):
        state = _load_state(state_path)
        candidate = state["candidates"].get(key)
        if candidate is None:
            raise DiscoveryError("candidate_not_found")
        candidate["status"] = status
        if error_code is not None:
            if not re.fullmatch(r"[a-z0-9_.:-]{1,64}", error_code):
                raise DiscoveryError("candidate_status_invalid")
            candidate["error_code"] = error_code
        candidate["updated_at"] = datetime.now(UTC).replace(microsecond=0).isoformat()
        _atomic_write_json(state_path, state)


def _self_check() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "job_schema_version": JOB_SCHEMA_VERSION,
        "modes": sorted(DISCOVERY_MODES),
        "fetch_kinds": sorted(FETCH_KINDS),
        "source_fetch": "explicit versioned YFC definitions only",
        "source_content": "untrusted data; no instructions executed",
        "redirects": f"manual revalidation; maximum {MAX_REDIRECTS}",
        "ssrf": "exact host allowlist, DNS resolution, public-IP-only external targets",
        "provider_credentials": False,
        "yfc_credentials": False,
        "telegram_capability": False,
        "publication_capability": False,
        "shell_browser_plugins": False,
        "dedupe": "source_id + canonical URL + content hash + event date",
        "publication_quota": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument(
        "--definitions", type=Path, default=Path("/opt/hermes/config/source-definitions.json")
    )
    parser.add_argument("--state-dir", type=Path, default=Path("/opt/data"))
    parser.add_argument("--outbox-dir", type=Path, default=Path("/opt/data/outbox"))
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.self_check and not args.once:
            print(json.dumps(_self_check(), ensure_ascii=False, sort_keys=True))
            return 0
        if not args.once:
            print("bounded discovery supports only --once or --self-check", file=sys.stderr)
            return 2
        result = run_once(
            definitions_path=args.definitions,
            state_dir=args.state_dir,
            outbox_dir=args.outbox_dir,
            mode=_mode(),
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["status"] != "failed" else 1
    except DiscoveryError as exc:
        print(json.dumps({"error": exc.code}, ensure_ascii=False, sort_keys=True))
        return 75 if exc.code == "scheduler_overlap" else 1
    except (
        AttributeError,
        KeyError,
        LookupError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        print(
            json.dumps(
                {"error": f"discovery_internal_{type(exc).__name__.casefold()}"}, sort_keys=True
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
