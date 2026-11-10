"""Bounded, direct HTTPS transport for the documented FatSecret export URLs."""

from __future__ import annotations

import base64
import http.client
import importlib
import ipaddress
import json
import re
import signal
import socket
import ssl
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from typing import cast

HOST = "foods.fatsecret.com"
MAX_URL_CHARS = 2048
CONNECT_SECONDS = 4
READ_SECONDS = 5
TOTAL_SECONDS = 20
_URL = re.compile(
    r"https://foods\.fatsecret\.com(?P<path>/export/"
    r"(?:[A-Za-z0-9_-]{1,128}/){3}month/food/"
    r"FoodDiary_[A-Za-z0-9_-]{1,80}_foods\.(?P<format>csv|pdf))"
    r"(?P<query>\?(?:lang|mkt)=[A-Za-z]{2,3}(?:&(?:lang|mkt)=[A-Za-z]{2,3})?)?\Z",
    re.ASCII,
)
_ERROR_CODES = frozenset(
    {
        "invalid_url",
        "unsafe_address",
        "redirect",
        "upstream_403",
        "upstream_404",
        "upstream_410",
        "upstream_429",
        "upstream_error",
        "dns_error",
        "tls_error",
        "timeout",
        "too_large",
        "incomplete_response",
        "incompatible_content",
        "pdf_unavailable",
        "network_error",
    }
)


class FatSecretUrlError(ValueError):
    def __init__(self, code: str) -> None:
        if not isinstance(code, str) or code not in _ERROR_CODES:
            code = "network_error"
        super().__init__(code)
        self.code = code


def _target(url: str) -> tuple[str, str]:
    match = _URL.fullmatch(url) if len(url) <= MAX_URL_CHARS else None
    if match is None:
        raise FatSecretUrlError("invalid_url")
    query = match.group("query") or ""
    if query:
        pairs = [part.split("=", 1) for part in query[1:].split("&")]
        if len({key for key, _ in pairs}) != len(pairs) or any(
            key == "mkt" and len(value) != 2 for key, value in pairs
        ):
            raise FatSecretUrlError("invalid_url")
    return match.group("path") + query, match.group("format")


def _public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if not address.is_global or address.is_reserved or address.is_multicast:
        return False
    # shortcut: extra special-use ranges reflect IANA's 2025-10-09 registries; update on changes.
    if isinstance(address, ipaddress.IPv4Address) and any(
        address in ipaddress.ip_network(network)
        for network in (
            "192.0.0.0/24",
            "192.31.196.0/24",
            "192.52.193.0/24",
            "192.88.99.0/24",
            "192.175.48.0/24",
        )
    ):
        return False
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped or address.sixtofour or address.teredo:
            return False
        if any(
            address in ipaddress.ip_network(network)
            for network in (
                "64:ff9b::/96",
                "64:ff9b:1::/48",
                "2001::/23",
                "2002::/16",
                "2620:4f:8000::/48",
            )
        ):
            return False
    return True


def _single_header(response: http.client.HTTPResponse, name: str) -> str | None:
    values = response.headers.get_all(name, [])
    if len(values) > 1:
        raise FatSecretUrlError("incompatible_content")
    return values[0] if values else None


def _download(url: str, limit: int) -> tuple[bytes, str]:
    target, expected = _target(url)
    try:
        answers = socket.getaddrinfo(HOST, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except OSError:
        raise FatSecretUrlError("dns_error") from None
    if not answers:
        raise FatSecretUrlError("dns_error")
    for family, socktype, protocol, _, sockaddr in answers:
        if (
            family not in (socket.AF_INET, socket.AF_INET6)
            or socktype != socket.SOCK_STREAM
            or protocol != socket.IPPROTO_TCP
            or not _public_ip(cast(str, sockaddr[0]))
            or sockaddr[1] != 443
            or (family == socket.AF_INET6 and (len(sockaddr) != 4 or sockaddr[-1] != 0))
        ):
            raise FatSecretUrlError("unsafe_address")
    family, socktype, protocol, _, sockaddr = answers[0]
    try:
        with socket.socket(family, socktype, protocol) as raw:
            raw.settimeout(CONNECT_SECONDS)
            raw.connect(sockaddr)
            peer = raw.getpeername()[0]
            if not _public_ip(peer) or ipaddress.ip_address(peer) != ipaddress.ip_address(
                cast(str, sockaddr[0])
            ):
                raise FatSecretUrlError("unsafe_address")
            with ssl.create_default_context().wrap_socket(raw, server_hostname=HOST) as connection:
                connection.settimeout(READ_SECONDS)
                request = (
                    f"GET {target} HTTP/1.1\r\nHost: {HOST}\r\n"
                    "Accept: text/csv, application/csv, text/plain, application/pdf\r\n"
                    "Accept-Encoding: identity\r\nConnection: close\r\n\r\n"
                )
                connection.sendall(request.encode("ascii"))
                response = http.client.HTTPResponse(connection)
                try:
                    response.begin()
                    if 300 <= response.status < 400:
                        raise FatSecretUrlError("redirect")
                    if response.status in {403, 404, 410, 429}:
                        raise FatSecretUrlError(f"upstream_{response.status}")
                    if response.status == 206:
                        raise FatSecretUrlError("incomplete_response")
                    if response.status != 200:
                        raise FatSecretUrlError("upstream_error")
                    if _single_header(response, "Content-Range") is not None:
                        raise FatSecretUrlError("incomplete_response")
                    content_type = _single_header(response, "Content-Type")
                    mime = (content_type or "").split(";", 1)[0].strip().lower()
                    allowed = {"text/csv", "application/csv", "text/plain"}
                    if mime not in (allowed if expected == "csv" else {"application/pdf"}):
                        raise FatSecretUrlError("incompatible_content")
                    encoding = _single_header(response, "Content-Encoding")
                    if encoding and encoding.strip().lower() != "identity":
                        raise FatSecretUrlError("incompatible_content")
                    length = _single_header(response, "Content-Length")
                    transfer = _single_header(response, "Transfer-Encoding")
                    if length is not None:
                        if not length.isascii() or not length.isdecimal() or transfer:
                            raise FatSecretUrlError("incompatible_content")
                        size = int(length)
                        if size > limit:
                            raise FatSecretUrlError("too_large")
                    elif transfer and transfer.strip().lower() == "chunked" and response.chunked:
                        size = None
                    else:
                        raise FatSecretUrlError("incomplete_response")
                    _single_header(response, "Content-Disposition")
                    filename = response.headers.get_filename()
                    if filename and (
                        not filename.lower().endswith(f".{expected}")
                        or any(char in filename for char in "/\\\r\n")
                    ):
                        raise FatSecretUrlError("incompatible_content")
                    data = bytearray()
                    while len(data) <= limit:
                        chunk = response.read(min(65536, limit + 1 - len(data)))
                        if not chunk:
                            break
                        data.extend(chunk)
                    if len(data) > limit:
                        raise FatSecretUrlError("too_large")
                    if not data or (size is not None and len(data) != size):
                        raise FatSecretUrlError("incomplete_response")
                    pdf = re.match(rb"%PDF-(?:1\.[0-7]|2\.0)(?:\r|\n)", data) is not None
                    if (expected == "pdf") != pdf:
                        raise FatSecretUrlError("incompatible_content")
                    return bytes(data), mime
                finally:
                    response.close()
    except FatSecretUrlError:
        raise
    except ssl.SSLError:
        raise FatSecretUrlError("tls_error") from None
    except TimeoutError:
        raise FatSecretUrlError("timeout") from None
    except http.client.IncompleteRead:
        raise FatSecretUrlError("incomplete_response") from None
    except OSError, http.client.HTTPException, ValueError:
        raise FatSecretUrlError("network_error") from None


class FatSecretShareUrlTransport:
    """Run DNS and the connection in a disposable process with a total deadline."""

    def fetch(self, url: str, *, limit: int) -> tuple[bytes, str]:
        code = "network_error"
        interrupted: BaseException | None = None
        try:
            return self._fetch(url, limit=limit)
        except FatSecretUrlError as exc:
            code = exc.code
        except Exception:
            pass
        except BaseException as exc:
            # Cancellation must not retain the private URL in traceback frames.
            exc.__traceback__ = None
            exc.__context__ = None
            exc.__cause__ = None
            exc.args = ()
            interrupted = exc
        finally:
            del url
        if interrupted is not None:
            raise interrupted from None
        raise FatSecretUrlError(code) from None

    def _fetch(self, url: str, *, limit: int) -> tuple[bytes, str]:
        _target(url)
        try:
            process = subprocess.Popen(
                [sys.executable, "-I", str(Path(__file__)), str(limit)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env={},
            )
        except OSError:
            raise FatSecretUrlError("network_error") from None
        try:
            try:
                output, _ = process.communicate(url.encode("ascii"), timeout=TOTAL_SECONDS)
            except subprocess.TimeoutExpired:
                raise FatSecretUrlError("timeout") from None
            if process.returncode != 0 or len(output) > (limit * 2 + 1024):
                raise FatSecretUrlError("network_error")
            try:
                result = json.loads(output)
                if "error" in result:
                    raise FatSecretUrlError(result["error"])
                source = base64.b64decode(result["content"], validate=True)
                mime = result["mime"]
                if (
                    not source
                    or len(source) > limit
                    or mime not in {"text/csv", "application/csv", "text/plain", "application/pdf"}
                ):
                    raise ValueError
                return source, mime
            except FatSecretUrlError:
                raise
            except ValueError, TypeError, KeyError:
                raise FatSecretUrlError("network_error") from None
        finally:
            if process.poll() is None:
                with suppress(ProcessLookupError):
                    process.kill()
                process.communicate()


def _worker() -> None:
    try:
        if hasattr(signal, "alarm"):
            signal.signal(signal.SIGALRM, signal.SIG_DFL)  # type: ignore[attr-defined]
            signal.alarm(TOTAL_SECONDS)
        if sys.platform == "linux":
            resource = importlib.import_module("resource")
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024, 384 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
            resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))
        url = sys.stdin.buffer.read(MAX_URL_CHARS + 1).decode("ascii")
        source, mime = _download(url, int(sys.argv[1]))
        result = {"content": base64.b64encode(source).decode("ascii"), "mime": mime}
    except FatSecretUrlError as exc:
        result = {"error": exc.code}
    except Exception:
        result = {"error": "network_error"}
    sys.stdout.write(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    _worker()
