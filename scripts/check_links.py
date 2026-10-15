"""Check repository-local links deterministically and external links opt-in."""

from __future__ import annotations

import argparse
import html
import ipaddress
import json
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

DEFAULT_EXTERNAL_LIMIT = 50
DEFAULT_HOST_LIMIT = 5
DEFAULT_TIMEOUT = 5.0
SUPPORTED_EXTERNAL_SCHEMES = frozenset({"http", "https"})
UNSUPPORTED_SCHEMES = frozenset({"data", "file", "ftp", "javascript", "mailto", "tel", "tg"})
PRIVATE_ROUTE_PREFIXES = (
    "/admin",
    "/api",
    "/app",
    "/coach",
    "/join",
    "/login",
    "/reset-password",
    "/share",
    "/verify-email",
)
PUBLIC_STATIC_ROUTES = frozenset(
    {
        "/",
        "/articles",
        "/demo",
        "/for-athletes",
        "/manifest.webmanifest",
        "/robots.txt",
        "/sitemap.xml",
        "/sw.js",
    }
)
SENSITIVE_QUERY_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "auth",
        "authorization",
        "code",
        "jwt",
        "key",
        "password",
        "secret",
        "signature",
        "sig",
        "token",
    }
)
SKIPPED_PARTS = frozenset(
    {
        ".agents",
        ".artifacts",
        ".git",
        ".make-feature",
        "__pycache__",
        "coverage",
        "dist",
        "node_modules",
        "playwright-report",
        "test-results",
    }
)


@dataclass(frozen=True)
class LinkRef:
    source: Path
    line: int
    target: str
    kind: str


@dataclass(frozen=True)
class HttpResponse:
    status: int
    final_url: str | None = None
    redirects: int = 0


@dataclass(frozen=True)
class Finding:
    status: str
    category: str
    source: str
    line: int
    target: str
    detail: str


@dataclass
class LinkReport:
    scanned_sources: int = 0
    checked_references: int = 0
    external_requests: int = 0
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.status == "error"]

    def counts(self) -> dict[str, int]:
        return dict(Counter(finding.status for finding in self.findings))


class _HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[tuple[int, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"a", "area", "link"}:
            attribute = "href"
        elif tag in {"audio", "embed", "iframe", "img", "script", "source", "track", "video"}:
            attribute = "src"
        else:
            return
        target = dict(attrs).get(attribute)
        if target:
            self.references.append((self.getpos()[0], target))


class _IdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        for key in ("id", "name"):
            value = attributes.get(key)
            if value:
                self.ids.add(value)


class _RedirectCounter(HTTPRedirectHandler):
    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        self.count += 1
        redirected_url = urljoin(request.full_url, newurl)
        if _external_skip_reason(redirected_url):
            raise URLError("redirect target is excluded by the safety policy")
        return super().redirect_request(request, fp, code, msg, headers, redirected_url)


def _line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _normalize_label(value: str) -> str:
    return " ".join(html.unescape(value).split()).casefold()


def _unescape_destination(value: str) -> str:
    return value.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\")


def _mask_markdown_code(text: str) -> str:
    masked: list[str] = []
    fence: str | None = None
    fence_length = 0
    for line in text.splitlines(keepends=True):
        match = re.match(r"^\s*(?P<marker>`{3,}|~{3,})", line)
        if fence is None and match:
            fence = match.group("marker")[0]
            fence_length = len(match.group("marker"))
            masked.append("".join("\n" if char == "\n" else " " for char in line))
            continue
        if fence is not None:
            if re.match(rf"^\s*{re.escape(fence)}{{{fence_length},}}", line):
                fence = None
                fence_length = 0
            masked.append("".join("\n" if char == "\n" else " " for char in line))
            continue

        pieces: list[str] = []
        cursor = 0
        for code in re.finditer(r"`+[^`\n]*`+", line):
            pieces.append(line[cursor : code.start()])
            pieces.append("".join("\n" if char == "\n" else " " for char in code.group(0)))
            cursor = code.end()
        pieces.append(line[cursor:])
        masked.append("".join(pieces))
    return "".join(masked)


def _read_inline_destination(text: str, start: int) -> tuple[str, int] | None:
    cursor = start
    while cursor < len(text) and text[cursor].isspace() and text[cursor] != "\n":
        cursor += 1
    if cursor >= len(text):
        return None

    if text[cursor] == "<":
        end = text.find(">", cursor + 1)
        if end < 0:
            return None
        target = text[cursor + 1 : end]
        cursor = end + 1
    else:
        chars: list[str] = []
        depth = 0
        while cursor < len(text):
            char = text[cursor]
            if char == "\\" and cursor + 1 < len(text):
                chars.append(text[cursor + 1])
                cursor += 2
                continue
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    break
                depth -= 1
            if char.isspace() and depth == 0:
                break
            chars.append(char)
            cursor += 1
        target = "".join(chars)
        while cursor < len(text) and text[cursor] != ")":
            cursor += 1

    if not target or cursor >= len(text) or text[cursor] != ")":
        return None
    return _unescape_destination(target), cursor + 1


def _markdown_references(path: Path, text: str) -> list[LinkRef]:
    clean = _mask_markdown_code(text)
    references: list[LinkRef] = []
    definitions: dict[str, str] = {}
    definition_pattern = re.compile(r"(?m)^\s{0,3}\[([^\]\n]+)\]:\s*(<[^>\n]+>|[^\s]+)")
    for match in definition_pattern.finditer(clean):
        target = match.group(2).strip("<>")
        definitions[_normalize_label(match.group(1))] = _unescape_destination(target)

    inline_pattern = re.compile(r"(?<!!)\[[^\]\n]*\]\(")
    for match in inline_pattern.finditer(clean):
        parsed = _read_inline_destination(clean, match.end())
        if parsed:
            target, _ = parsed
            references.append(LinkRef(path, _line_number(clean, match.start()), target, "markdown"))

    reference_pattern = re.compile(r"(?<!!)\[([^\]\n]+)\]\[([^\]\n]*)\]")
    for match in reference_pattern.finditer(clean):
        label = match.group(2) or match.group(1)
        target = definitions.get(_normalize_label(label))
        if target is not None:
            references.append(
                LinkRef(path, _line_number(clean, match.start()), target, "markdown-reference")
            )

    try:
        parser = _HrefParser()
        parser.feed(clean)
    except Exception:  # HTMLParser is best effort inside Markdown.
        parser = _HrefParser()
    references.extend(
        LinkRef(path, line, target, "markdown-html") for line, target in parser.references
    )

    for match in re.finditer(r"<((?:https?|mailto):[^>\s]+)>", clean):
        references.append(
            LinkRef(path, _line_number(clean, match.start()), match.group(1), "autolink")
        )
    for match in re.finditer(r"(?<![\w\"'=])(https?://[^\s<>\]\)]+)", clean):
        target = match.group(1).rstrip(".,;:!?}")
        references.append(LinkRef(path, _line_number(clean, match.start()), target, "bare-url"))
    return _unique_references(references)


def _source_references(path: Path, text: str) -> list[LinkRef]:
    references = [
        LinkRef(path, _line_number(text, match.start()), match.group(2), "source-route")
        for match in re.finditer(r"\b(?:href|to)\s*=\s*([\"'])(.*?)\1", text, re.DOTALL)
        if match.group(2).strip()
    ]
    return _unique_references(references)


def _json_references(path: Path, text: str) -> list[LinkRef]:
    payload = json.loads(text)
    references: list[LinkRef] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if isinstance(child, str) and (
                    key == "path" or key == "url" or key == "src" or key.endswith("_url")
                ):
                    index = text.find(json.dumps(child, ensure_ascii=False))
                    references.append(
                        LinkRef(path, _line_number(text, max(index, 0)), child, "public-route")
                    )
                else:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return _unique_references(references)


def _unique_references(references: Iterable[LinkRef]) -> list[LinkRef]:
    seen: set[tuple[Path, int, str]] = set()
    unique: list[LinkRef] = []
    for reference in references:
        key = (reference.source, reference.line, reference.target)
        if key not in seen:
            seen.add(key)
            unique.append(reference)
    return unique


def _github_slug(heading: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", "", heading))
    value = re.sub(r"`([^`]*)`", r"\1", value).strip().casefold()
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE)
    return re.sub(r"\s+", "-", value)


def _anchors_for(path: Path, text: str) -> set[str]:
    anchors: set[str] = set()
    if path.suffix.casefold() in {".md", ".markdown"}:
        used: Counter[str] = Counter()
        lines = text.splitlines()
        for index, line in enumerate(lines):
            match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
            if match:
                slug = _github_slug(match.group(1))
            elif index + 1 < len(lines) and re.match(r"^\s{0,3}(?:=+|-+)\s*$", lines[index + 1]):
                slug = _github_slug(line)
            else:
                slug = ""
            if slug:
                suffix = used[slug]
                anchors.add(slug if suffix == 0 else f"{slug}-{suffix}")
                used[slug] += 1
    try:
        parser = _IdParser()
        parser.feed(text)
        anchors.update(parser.ids)
    except Exception:  # HTMLParser is best effort for source documents.
        pass
    return anchors


def _relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _redact_query(query: str) -> str:
    if not query:
        return ""
    keys: list[str] = []
    for pair in query.split("&"):
        key = unquote(pair.split("=", 1)[0])
        key = re.sub(r"[^A-Za-z0-9_.~-]", "", key)[:40] or "param"
        keys.append(f"{key}=[redacted]")
    return "&".join(keys)


def _safe_target(target: str) -> str:
    try:
        parsed = urlsplit(target)
    except ValueError:
        return "[invalid-url]"
    if parsed.scheme in SUPPORTED_EXTERNAL_SCHEMES:
        host = parsed.hostname or "[invalid-host]"
        try:
            port = f":{parsed.port}" if parsed.port else ""
        except ValueError:
            port = ""
        return urlunsplit(
            (parsed.scheme, f"{host}{port}", parsed.path, _redact_query(parsed.query), "")
        )
    fragment = f"#{unquote(parsed.fragment)}" if parsed.fragment else ""
    query = f"?{_redact_query(parsed.query)}" if parsed.query else ""
    return f"{parsed.path}{query}{fragment}" or target


def _finding(root: Path, reference: LinkRef, status: str, category: str, detail: str) -> Finding:
    return Finding(
        status=status,
        category=category,
        source=_relative_path(root, reference.source),
        line=reference.line,
        target=_safe_target(reference.target),
        detail=detail,
    )


def _is_http_url(target: str) -> bool:
    try:
        return urlsplit(target).scheme.casefold() in SUPPORTED_EXTERNAL_SCHEMES
    except ValueError:
        return False


def _route_path(target: str) -> str | None:
    try:
        parsed = urlsplit(target)
    except ValueError:
        return None
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return None
    path = unquote(parsed.path) or "/"
    if "\\" in path or "\x00" in path:
        return None
    return path


def _is_private_route(path: str) -> bool:
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in PRIVATE_ROUTE_PREFIXES)


def _is_private_host(host: str) -> bool:
    lowered = host.casefold().rstrip(".")
    if lowered in {"localhost", "localhost.localdomain", "metadata.google.internal"}:
        return True
    if lowered.endswith((".local", ".internal", ".localhost")):
        return True
    try:
        address = ipaddress.ip_address(lowered)
    except ValueError:
        return False
    return bool(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    )


def _external_skip_reason(target: str) -> tuple[str, str] | None:
    try:
        parsed = urlsplit(target)
        host = parsed.hostname or ""
    except ValueError:
        return "forbidden-url", "invalid URL"
    scheme = parsed.scheme.casefold()
    if scheme not in SUPPORTED_EXTERNAL_SCHEMES:
        if scheme in UNSUPPORTED_SCHEMES or scheme:
            return "unsupported-url", f"scheme {scheme or '[missing]'} is not checked"
        return "unsupported-url", "relative URL is not an external target"
    if not host:
        return "forbidden-url", "URL has no public host"
    if parsed.username or parsed.password:
        return "forbidden-url", "URL credentials are never sent"
    if _is_private_host(host):
        return "forbidden-url", "private or local host is never contacted"
    if host.casefold().endswith("fatsecret.com"):
        return "forbidden-url", "personal FatSecret resources are excluded"
    query_keys = {
        unquote(pair.split("=", 1)[0]).casefold() for pair in parsed.query.split("&") if pair
    }
    if query_keys & SENSITIVE_QUERY_KEYS:
        return "forbidden-url", "URL contains a sensitive query parameter"
    path_parts = {part.casefold() for part in parsed.path.split("/") if part}
    if "api" in path_parts:
        return "forbidden-url", "authenticated/API resources are excluded"
    return None


def _fetch_http(url: str, timeout: float) -> HttpResponse:
    redirects = _RedirectCounter()
    opener = build_opener(redirects)
    request = Request(url, headers={"User-Agent": "yfc-link-checker/1"})
    try:
        with opener.open(request, timeout=timeout) as response:
            return HttpResponse(response.status, response.geturl(), redirects.count)
    except HTTPError as error:
        return HttpResponse(error.code, error.geturl(), redirects.count)


def _classify_http_response(response: HttpResponse) -> tuple[str, str, str]:
    status = response.status
    if 200 <= status < 400:
        category = "redirect" if response.redirects or 300 <= status < 400 else "external-url"
        return "pass", category, f"HTTP {status}"
    if status in {404, 410}:
        return "error", "confirmed-http-error", f"HTTP {status}"
    if status in {401, 403, 408, 425, 429} or 500 <= status <= 599:
        return "deferred", "temporary-http-condition", f"HTTP {status}; manual retry required"
    if 400 <= status <= 499:
        return "error", "confirmed-http-error", f"HTTP {status}"
    return "deferred", "unknown-http-condition", f"HTTP {status}; manual retry required"


def _external_finding(
    root: Path,
    reference: LinkRef,
    *,
    enabled: bool,
    timeout: float,
    host_counts: dict[str, int],
    max_per_host: int,
    fetch: Callable[[str, float], HttpResponse],
) -> tuple[Finding, bool]:
    skip = _external_skip_reason(reference.target)
    if skip:
        return _finding(root, reference, "skipped", *skip), False
    if not enabled:
        return _finding(
            root, reference, "skipped", "external-opt-in", "external checks are opt-in"
        ), False

    parsed = urlsplit(reference.target)
    host = (parsed.hostname or "").casefold()
    if host_counts.get(host, 0) >= max_per_host:
        return _finding(
            root,
            reference,
            "skipped",
            "host-limit",
            f"per-host limit {max_per_host} reached",
        ), False
    host_counts[host] = host_counts.get(host, 0) + 1
    try:
        response = fetch(reference.target, timeout)
    except TimeoutError:
        return _finding(root, reference, "deferred", "network-timeout", "request timed out"), True
    except URLError, OSError:
        return _finding(
            root,
            reference,
            "deferred",
            "network-unavailable",
            "network failure; manual retry required",
        ), True
    status, category, detail = _classify_http_response(response)
    return _finding(root, reference, status, category, detail), True


def _public_routes(root: Path) -> set[str]:
    routes = set(PUBLIC_STATIC_ROUTES)
    manifest = root / "frontend" / "src" / "content" / "publicContent.json"
    if not manifest.is_file():
        return routes
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    pages = payload.get("pages") if isinstance(payload, dict) else None
    if not isinstance(pages, list):
        raise ValueError("publicContent.json must contain a pages array")
    for page in pages:
        if isinstance(page, dict) and page.get("status", "published") == "published":
            path = page.get("path")
            route_path = _route_path(path) if isinstance(path, str) else None
            if route_path:
                routes.add(route_path)
    return routes


def _default_sources(root: Path) -> list[Path]:
    sources: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        parts = set(path.relative_to(root).parts)
        if parts & SKIPPED_PARTS or relative.startswith("docs/ux-proposals/"):
            continue
        if (
            (
                path.suffix.casefold() in {".md", ".markdown"}
                and (
                    len(path.relative_to(root).parts) == 1
                    or relative.startswith(("docs/", "codex-backlog/"))
                )
            )
            or (
                path.suffix.casefold() in {".html", ".htm"}
                and (relative.startswith("docs/") or relative == "frontend/index.html")
            )
            or (
                path.suffix.casefold() == ".tsx"
                and relative.startswith(
                    (
                        "frontend/src/pages/landing/",
                        "frontend/src/pages/public/",
                        "frontend/src/shared/navigation/",
                    )
                )
            )
            or relative == "frontend/src/content/publicContent.json"
            or relative == "frontend/public/manifest.webmanifest"
        ):
            sources.append(path)
    return sorted(sources)


def _requested_sources(root: Path, requested: Sequence[Path]) -> list[Path]:
    sources: list[Path] = []
    for raw_path in requested:
        path = (root / raw_path).resolve() if not raw_path.is_absolute() else raw_path.resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError(f"source path escapes repository: {raw_path}")
        if path.is_dir():
            sources.extend(item for item in path.rglob("*") if item.is_file())
        elif path.is_file():
            sources.append(path)
        else:
            raise ValueError(f"source path does not exist: {raw_path}")
    return sorted(set(sources))


def _source_references_for(path: Path, text: str) -> list[LinkRef]:
    suffix = path.suffix.casefold()
    if suffix in {".md", ".markdown"}:
        return _markdown_references(path, text)
    if suffix in {".html", ".htm"}:
        parser = _HrefParser()
        parser.feed(text)
        return [LinkRef(path, line, target, "html") for line, target in parser.references]
    if suffix == ".tsx":
        return _source_references(path, text)
    if path.name in {"publicContent.json", "manifest.webmanifest"}:
        return _json_references(path, text)
    return []


def _frontend_static_path(root: Path, route_path: str) -> Path | None:
    if route_path in {"/manifest.webmanifest", "/sw.js"} or route_path.startswith("/assets/"):
        return root / "frontend" / "public" / route_path.lstrip("/")
    if route_path.startswith("/src/"):
        return root / "frontend" / route_path.lstrip("/")
    return None


def _evaluate_local(
    root: Path,
    reference: LinkRef,
    *,
    public_routes: set[str],
    anchors: dict[Path, set[str]],
    source_anchors: set[str],
) -> Finding | None:
    try:
        parsed = urlsplit(reference.target)
    except ValueError:
        return _finding(root, reference, "error", "invalid-url", "URL cannot be parsed")
    if parsed.scheme.casefold() in SUPPORTED_EXTERNAL_SCHEMES:
        return None
    if parsed.scheme or parsed.netloc:
        skip = _external_skip_reason(reference.target)
        if skip is None:
            return None
        category, detail = skip
        return _finding(root, reference, "skipped", category, detail)

    route_path = _route_path(reference.target)
    if route_path is not None:
        static_path = _frontend_static_path(root, route_path)
        if static_path is not None:
            if not static_path.is_file():
                return _finding(
                    root,
                    reference,
                    "error",
                    "missing-file",
                    "frontend public asset does not exist",
                )
            return _finding(root, reference, "pass", "public-asset", "frontend public asset exists")
        if _is_private_route(route_path):
            return _finding(
                root,
                reference,
                "skipped",
                "private-route",
                "private route is not probed anonymously",
            )
        if route_path not in public_routes:
            return _finding(
                root,
                reference,
                "error",
                "unknown-public-route",
                "route is not in the public route manifest",
            )
        target_anchors = (
            source_anchors
            if reference.kind == "source-route"
            else anchors.get(reference.source, set())
        )
        if parsed.fragment and unquote(parsed.fragment) not in target_anchors:
            return _finding(
                root,
                reference,
                "error",
                "missing-anchor",
                "public route anchor does not exist in source",
            )
        return _finding(root, reference, "pass", "public-route", "public route is declared")

    path_part = unquote(parsed.path)
    target_path = (
        reference.source if not path_part else (reference.source.parent / path_part).resolve()
    )
    if not target_path.is_relative_to(root.resolve()):
        return _finding(
            root, reference, "error", "path-outside-root", "local link escapes the repository"
        )
    if not target_path.exists():
        return _finding(root, reference, "error", "missing-file", "local target does not exist")
    if parsed.fragment:
        if target_path not in anchors and target_path.suffix.casefold() in {
            ".md",
            ".markdown",
            ".html",
            ".htm",
        }:
            anchors[target_path] = _anchors_for(
                target_path, target_path.read_text(encoding="utf-8")
            )
        target_anchors = (
            source_anchors
            if target_path == reference.source and reference.kind == "source-route"
            else anchors.get(target_path, set())
        )
        if unquote(parsed.fragment) not in target_anchors:
            return _finding(
                root, reference, "error", "missing-anchor", "anchor does not exist in target"
            )
    return _finding(root, reference, "pass", "local-file", "local target exists")


def _route_reference_url(base_url: str, reference: LinkRef) -> str | None:
    route_path = _route_path(reference.target)
    if route_path is None or _is_private_route(route_path):
        return None
    parsed = urlsplit(reference.target)
    return urljoin(base_url.rstrip("/") + "/", route_path.lstrip("/")) + (
        f"?{parsed.query}" if parsed.query else ""
    )


def check_repository(
    root: Path,
    *,
    paths: Sequence[Path] | None = None,
    external: bool = False,
    public_base_url: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_external_urls: int = DEFAULT_EXTERNAL_LIMIT,
    max_per_host: int = DEFAULT_HOST_LIMIT,
    fetch: Callable[[str, float], HttpResponse] | None = None,
) -> LinkReport:
    root = root.resolve()
    if timeout <= 0 or max_external_urls <= 0 or max_per_host <= 0:
        raise ValueError("timeout and request limits must be positive")
    source_paths = _requested_sources(root, paths) if paths is not None else _default_sources(root)
    report = LinkReport(scanned_sources=len(source_paths))
    public_routes = _public_routes(root)
    text_by_path: dict[Path, str] = {}
    anchors: dict[Path, set[str]] = {}
    source_anchors: set[str] = set()
    references: list[LinkRef] = []
    for path in source_paths:
        text = path.read_text(encoding="utf-8")
        text_by_path[path] = text
        anchors[path] = _anchors_for(path, text)
        if path.suffix.casefold() == ".tsx":
            source_anchors.update(
                match.group(2) for match in re.finditer(r"\bid\s*=\s*([\"'])(.*?)\1", text)
            )
        references.extend(_source_references_for(path, text))

    external_references: list[LinkRef] = []
    public_references: list[tuple[LinkRef, str]] = []
    for reference in _unique_references(references):
        report.checked_references += 1
        if _is_http_url(reference.target):
            external_references.append(reference)
            continue
        finding = _evaluate_local(
            root,
            reference,
            public_routes=public_routes,
            anchors=anchors,
            source_anchors=source_anchors,
        )
        if finding is not None:
            report.findings.append(finding)
            if public_base_url and finding.status == "pass":
                route_url = _route_reference_url(public_base_url, reference)
                if route_url:
                    public_references.append((reference, route_url))

    fetcher = fetch or _fetch_http
    host_counts: dict[str, int] = {}
    seen_external: set[str] = set()
    for reference in [
        *external_references,
        *[
            LinkRef(ref.source, ref.line, url, "public-route-live")
            for ref, url in public_references
        ],
    ]:
        key = reference.target.split("#", 1)[0]
        if key in seen_external:
            continue
        seen_external.add(key)
        if report.external_requests >= max_external_urls:
            report.findings.append(
                _finding(
                    root,
                    reference,
                    "skipped",
                    "external-limit",
                    f"limit {max_external_urls} reached",
                )
            )
            continue
        finding, requested = _external_finding(
            root,
            reference,
            enabled=external or reference.kind == "public-route-live",
            timeout=timeout,
            host_counts=host_counts,
            max_per_host=max_per_host,
            fetch=fetcher,
        )
        report.findings.append(finding)
        report.external_requests += int(requested)
    return report


def _reproduce(finding: Finding) -> str:
    return f"python scripts/check_links.py --path {finding.source}"


def _render_report(report: LinkReport, *, json_output: bool) -> str:
    payload = {
        "scanned_sources": report.scanned_sources,
        "checked_references": report.checked_references,
        "external_requests": report.external_requests,
        "counts": report.counts(),
        "errors": [asdict(finding) for finding in report.errors],
        "deferred": [
            asdict(finding) for finding in report.findings if finding.status == "deferred"
        ],
        "skipped": [
            asdict(finding)
            for finding in report.findings
            if finding.status == "skipped" and finding.category != "external-opt-in"
        ],
    }
    if json_output:
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    lines = [
        "LINK_CHECK_RESULT "
        f"status={'FAIL' if report.errors else 'PASS'} "
        f"sources={report.scanned_sources} references={report.checked_references} "
        f"external_requests={report.external_requests} counts={json.dumps(report.counts(), sort_keys=True)}"
    ]
    for finding in report.findings:
        if finding.status == "pass" or finding.category == "external-opt-in":
            continue
        lines.append(
            f"{finding.status.upper()} {finding.category} {finding.source}:{finding.line} "
            f"-> {finding.target} | {finding.detail} | reproduce: {_reproduce(finding)}"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--path", action="append", type=Path, help="limit the scan; repeatable")
    parser.add_argument("--external", action="store_true", help="opt-in bounded public HTTP checks")
    parser.add_argument("--public-base-url", help="opt-in unauthenticated public-route checks")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--max-external-urls", type=int, default=DEFAULT_EXTERNAL_LIMIT)
    parser.add_argument("--max-per-host", type=int, default=DEFAULT_HOST_LIMIT)
    parser.add_argument("--json", action="store_true", help="emit a sanitized JSON report")
    args = parser.parse_args(argv)
    try:
        report = check_repository(
            args.root,
            paths=args.path,
            external=args.external,
            public_base_url=args.public_base_url,
            timeout=args.timeout,
            max_external_urls=args.max_external_urls,
            max_per_host=args.max_per_host,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"link check failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print(_render_report(report, json_output=args.json))
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
