import io
import logging
import socket
import ssl
import subprocess
import sys
import traceback
from email.message import Message
from pathlib import Path

import pytest

from fitminiapp_api.services import nutrition_import_fatsecret_url as transport

URL = (
    "https://foods.fatsecret.com/export/fake_account/fake_token/fake_report/"
    "month/food/FoodDiary_Test_24_foods.csv?lang=ru&mkt=RU"
)
CSV = b"# Period Summary\nsynthetic,1\n"
PUBLIC = "93.184.216.34"


@pytest.mark.parametrize(
    "url",
    [
        URL.replace("https:", "http:"),
        URL.replace("foods.fatsecret.com", "example.com"),
        URL.replace("foods.fatsecret.com", "sub.foods.fatsecret.com"),
        URL.replace("foods.fatsecret.com", "foods.fatsecret.com.evil.example"),
        URL.replace("foods.fatsecret.com", "localhost"),
        URL.replace("foods.fatsecret.com", "127.0.0.1"),
        URL.replace("foods.fatsecret.com", "169.254.169.254"),
        URL.replace("foods.fatsecret.com", "[::1]"),
        URL.replace("foods.fatsecret.com", "user:pass@foods.fatsecret.com"),
        URL.replace("foods.fatsecret.com", "foods.fatsecret.com:8443"),
        URL.replace("/export/", "/%65xport/"),
        URL.replace("fake_token", "fake%2ftoken"),
        URL.replace("fake_token", ".."),
        URL + "#fragment",
        URL + "&lang=en",
        URL + "\r\nX-Injected: x",
        URL.replace("FoodDiary", "fooddiary"),
    ],
)
def test_url_allowlist_rejects_ambiguous_or_untrusted_urls(url):
    with pytest.raises(transport.FatSecretUrlError, match=r"^invalid_url$"):
        transport._target(url)


def test_url_allows_only_documented_synthetic_shape():
    target, kind = transport._target(URL)
    assert target.startswith("/export/")
    assert kind == "csv"
    assert transport._target(URL.replace(".csv", ".pdf"))[1] == "pdf"
    assert str(transport.FatSecretUrlError(URL)) == "network_error"


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "192.0.0.9",
        "192.0.2.1",
        "224.0.0.1",
        "::1",
        "fc00::1",
        "fe80::1",
        "::ffff:93.184.216.34",
        "64:ff9b::5db8:d822",
        "2001:db8::1",
        "2001:1::1",
        "2002:5db8:d822::1",
        "2620:4f:8000::1",
        "ff02::1",
    ],
)
def test_special_addresses_are_never_public(address):
    assert not transport._public_ip(address)


def test_public_ipv4_and_ipv6_are_allowed():
    assert transport._public_ip(PUBLIC)
    assert transport._public_ip("2606:4700:4700::1111")


def test_default_tls_context_verifies_certificates_and_hostnames():
    context = ssl.create_default_context()
    assert context.check_hostname
    assert context.verify_mode == ssl.CERT_REQUIRED


@pytest.fixture
def network(monkeypatch):
    state = {
        "answers": [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (PUBLIC, 443))],
        "peer": PUBLIC,
        "status": 200,
        "body": CSV,
        "headers": {"Content-Type": "text/csv", "Content-Length": str(len(CSV))},
        "sent": [],
        "connected": [],
        "sni": [],
        "closed": 0,
        "failure": None,
        "dns_calls": [],
        "read_failure": None,
    }

    class FakeSocket:
        def __init__(self, *args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            state["closed"] += 1

        def settimeout(self, seconds):
            assert seconds in {transport.CONNECT_SECONDS, transport.READ_SECONDS}

        def connect(self, address):
            state["connected"].append(address)

        def getpeername(self):
            return state["peer"], 443

        def sendall(self, data):
            state["sent"].append(data)

    class FakeContext:
        def wrap_socket(self, raw, *, server_hostname):
            state["sni"].append(server_hostname)
            assert self.minimum_version == ssl.TLSVersion.TLSv1_2
            return raw

    class FakeResponse:
        def __init__(self, connection):
            self.status = state["status"]
            self.headers = Message()
            for key, value in state["headers"].items():
                self.headers[key] = value
            self.chunked = self.headers.get("Transfer-Encoding", "").lower() == "chunked"
            self.body = io.BytesIO(state["body"])

        def begin(self):
            if state["failure"]:
                raise state["failure"]

        def read(self, size):
            if state["read_failure"]:
                raise state["read_failure"]
            return self.body.read(size)

        def close(self):
            state["closed"] += 1

    def resolve(*args):
        state["dns_calls"].append(args)
        return state["answers"]

    monkeypatch.setattr(transport.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(transport.socket, "socket", FakeSocket)
    monkeypatch.setattr(transport.ssl, "create_default_context", FakeContext)
    monkeypatch.setattr(transport.http.client, "HTTPResponse", FakeResponse)
    return state


def test_download_pins_validated_peer_and_tls_hostname(network):
    source, mime = transport._download(URL, 512 * 1024)
    assert (source, mime) == (CSV, "text/csv")
    assert network["connected"] == [(PUBLIC, 443)]
    assert len(network["dns_calls"]) == 1
    assert network["sni"] == [transport.HOST]
    assert len(network["sent"]) == 1
    assert b"Cookie:" not in network["sent"][0]
    assert b"Authorization:" not in network["sent"][0]
    assert network["closed"] >= 2


def test_mixed_dns_answers_are_rejected_before_connect(network):
    network["answers"].append(
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.0.0.1", 443))
    )
    with pytest.raises(transport.FatSecretUrlError, match=r"^unsafe_address$"):
        transport._download(URL, 1024)
    assert network["connected"] == []


def test_dns_failure_is_sanitized(monkeypatch):
    def fail(*args):
        raise socket.gaierror("synthetic resolver error")

    monkeypatch.setattr(transport.socket, "getaddrinfo", fail)
    with pytest.raises(transport.FatSecretUrlError, match=r"^dns_error$"):
        transport._download(URL, 1024)


def test_rebinding_peer_is_rejected_before_tls_or_request(network):
    network["peer"] = "127.0.0.1"
    with pytest.raises(transport.FatSecretUrlError, match=r"^unsafe_address$"):
        transport._download(URL, 1024)
    assert network["sni"] == []
    assert network["sent"] == []


@pytest.mark.parametrize("status", [301, 302, 307, 308, 403, 404, 410, 429])
def test_redirects_and_upstream_refusals_fail_closed(network, status):
    network["status"] = status
    expected = "redirect" if status < 400 else f"upstream_{status}"
    with pytest.raises(transport.FatSecretUrlError, match=f"^{expected}$"):
        transport._download(URL, 1024)
    assert len(network["sent"]) == 1


@pytest.mark.parametrize(
    ("url", "body", "mime", "error"),
    [
        (URL, b"<html>login</html>", "text/html", "incompatible_content"),
        (URL, b"%PDF-1.7\n", "text/csv", "incompatible_content"),
        (URL, CSV, "application/pdf", "incompatible_content"),
        (URL.replace(".csv", ".pdf"), CSV, "application/pdf", "incompatible_content"),
    ],
)
def test_format_conflicts_and_pdf_fail_closed(network, url, body, mime, error):
    network["body"] = body
    network["headers"] = {"Content-Type": mime, "Content-Length": str(len(body))}
    with pytest.raises(transport.FatSecretUrlError, match=f"^{error}$"):
        transport._download(url, 1024)


def test_pdf_candidate_is_returned_for_adapter_routing(network):
    network["body"] = b"%PDF-1.7\nsynthetic"
    network["headers"] = {"Content-Type": "application/pdf", "Content-Length": "18"}
    assert transport._download(URL.replace(".csv", ".pdf"), 1024) == (
        b"%PDF-1.7\nsynthetic",
        "application/pdf",
    )


@pytest.mark.parametrize("truncated", [False, True])
def test_real_http_parser_handles_chunked_framing_without_network(monkeypatch, truncated):
    header = b"HTTP/1.1 200 OK\r\nContent-Type: text/csv\r\nTransfer-Encoding: chunked\r\n\r\n"
    wire = header + (
        b"5\r\nabc" if truncated else f"{len(CSV):x}\r\n".encode() + CSV + b"\r\n0\r\n\r\n"
    )

    class LocalSocket:
        def __init__(self, *args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def settimeout(self, seconds):
            pass

        def connect(self, address):
            assert address == (PUBLIC, 443)

        def getpeername(self):
            return PUBLIC, 443

        def sendall(self, data):
            pass

        def makefile(self, mode):
            return io.BytesIO(wire)

    class Context:
        def wrap_socket(self, raw, *, server_hostname):
            assert server_hostname == transport.HOST
            assert self.minimum_version == ssl.TLSVersion.TLSv1_2
            return raw

    monkeypatch.setattr(
        transport.socket,
        "getaddrinfo",
        lambda *args: [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (PUBLIC, 443))],
    )
    monkeypatch.setattr(transport.socket, "socket", LocalSocket)
    monkeypatch.setattr(transport.ssl, "create_default_context", Context)
    if truncated:
        with pytest.raises(transport.FatSecretUrlError, match=r"^incomplete_response$"):
            transport._download(URL, 1024)
    else:
        assert transport._download(URL, 1024) == (CSV, "text/csv")


@pytest.mark.parametrize(
    ("headers", "body", "limit", "error"),
    [
        ({"Content-Type": "text/csv", "Content-Length": "5000"}, CSV, 1024, "too_large"),
        ({"Content-Type": "text/csv", "Transfer-Encoding": "chunked"}, CSV, 4, "too_large"),
        ({"Content-Type": "text/csv", "Content-Length": "100"}, CSV, 1024, "incomplete_response"),
        ({"Content-Type": "text/csv"}, CSV, 1024, "incomplete_response"),
        (
            {
                "Content-Type": "text/csv",
                "Content-Length": str(len(CSV)),
                "Content-Range": "bytes 0-2/9",
            },
            CSV,
            1024,
            "incomplete_response",
        ),
        (
            {"Content-Type": "text/csv", "Content-Length": "1", "Transfer-Encoding": "chunked"},
            CSV,
            1024,
            "incompatible_content",
        ),
        (
            {"Content-Type": "text/csv", "Content-Length": "1", "Content-Encoding": "gzip"},
            CSV,
            1024,
            "incompatible_content",
        ),
        (
            {
                "Content-Type": "text/csv",
                "Content-Length": str(len(CSV)),
                "Content-Disposition": 'attachment; filename="report.pdf"',
            },
            CSV,
            1024,
            "incompatible_content",
        ),
    ],
)
def test_response_limits_and_framing(network, headers, body, limit, error):
    network["headers"] = headers
    network["body"] = body
    with pytest.raises(transport.FatSecretUrlError, match=f"^{error}$"):
        transport._download(URL, limit)


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (TimeoutError(), "timeout"),
        (ssl.SSLError("synthetic"), "tls_error"),
        (OSError("synthetic"), "network_error"),
    ],
)
def test_network_failures_are_safe(network, failure, code):
    network["failure"] = failure
    with pytest.raises(transport.FatSecretUrlError, match=f"^{code}$"):
        transport._download(URL, 1024)


def test_truncated_chunked_body_is_rejected(network):
    network["headers"] = {"Content-Type": "text/csv", "Transfer-Encoding": "chunked"}
    network["read_failure"] = transport.http.client.IncompleteRead(b"partial")
    with pytest.raises(transport.FatSecretUrlError, match=r"^incomplete_response$"):
        transport._download(URL, 1024)


def test_partial_http_status_is_rejected(network):
    network["status"] = 206
    with pytest.raises(transport.FatSecretUrlError, match=r"^incomplete_response$"):
        transport._download(URL, 1024)


def test_total_timeout_kills_worker_and_exception_has_no_url(monkeypatch, caplog):
    state = {"killed": False, "input": None, "args": None, "env": None}

    class TimedOutProcess:
        returncode = None

        def __init__(self, args, **kwargs):
            state["args"] = args
            state["env"] = kwargs["env"]

        def communicate(self, input=None, timeout=None):
            if not state["killed"]:
                state["input"] = input
                raise subprocess.TimeoutExpired(state["args"], timeout)
            return b"", b""

        def poll(self):
            return -9 if state["killed"] else None

        def kill(self):
            state["killed"] = True

    monkeypatch.setattr(transport.subprocess, "Popen", TimedOutProcess)
    caplog.set_level(logging.DEBUG)
    with pytest.raises(transport.FatSecretUrlError, match=r"^timeout$") as caught:
        transport.FatSecretShareUrlTransport().fetch(URL, limit=1024)
    rendered = "".join(traceback.format_exception(caught.value))
    assert "fake_token" not in rendered and "fake_report" not in rendered
    assert "fake_token" not in caplog.text and "fake_report" not in caplog.text
    assert state["killed"] and state["input"] == URL.encode("ascii")
    assert URL not in str(state["args"]) and state["env"] == {}
    frame = caught.value.__traceback__
    while frame:
        if Path(frame.tb_frame.f_code.co_filename).name == "nutrition_import_fatsecret_url.py":
            local_values = repr(frame.tb_frame.f_locals)
            assert "fake_token" not in local_values and "fake_report" not in local_values
        frame = frame.tb_next


def test_interrupted_fetch_closes_worker(monkeypatch):
    state = {"killed": False}

    class InterruptedProcess:
        def __init__(self, *args, **kwargs):
            pass

        def communicate(self, input=None, timeout=None):
            if not state["killed"]:
                raise KeyboardInterrupt("fake_token_fake_report")
            return b"", b""

        def poll(self):
            return -9 if state["killed"] else None

        def kill(self):
            state["killed"] = True

    monkeypatch.setattr(transport.subprocess, "Popen", InterruptedProcess)
    with pytest.raises(KeyboardInterrupt) as caught:
        transport.FatSecretShareUrlTransport().fetch(URL, limit=1024)
    assert state["killed"]
    assert "fake_token" not in repr(caught.value)
    frame = caught.value.__traceback__
    while frame:
        if Path(frame.tb_frame.f_code.co_filename).name == "nutrition_import_fatsecret_url.py":
            local_values = repr(frame.tb_frame.f_locals)
            assert "fake_token" not in local_values and "fake_report" not in local_values
        frame = frame.tb_next


@pytest.mark.skipif(sys.platform != "linux", reason="worker resource limits require Linux")
def test_worker_process_returns_only_safe_error():
    result = subprocess.run(
        [sys.executable, "-I", transport.__file__, "1024"],
        input=b"fake_token_fake_report",
        capture_output=True,
        env={},
        timeout=5,
        check=True,
    )
    assert result.stdout == b'{"error":"invalid_url"}'
    assert result.stderr == b""
