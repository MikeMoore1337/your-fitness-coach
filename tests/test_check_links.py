from __future__ import annotations

import json
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request

from scripts.check_links import (
    HttpResponse,
    _classify_http_response,
    _RedirectCounter,
    _render_report,
    check_repository,
)


def _write_markdown(root: Path, content: str) -> Path:
    source = root / "docs" / "source.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(content, encoding="utf-8")
    return source


def test_local_file_anchor_and_query_fragment_are_valid(tmp_path: Path) -> None:
    source = _write_markdown(tmp_path, "[guide](target.md?view=compact#correct-anchor)\n")
    (source.parent / "target.md").write_text("# Correct Anchor\n", encoding="utf-8")

    report = check_repository(tmp_path, paths=[source])

    assert not report.errors
    assert any(
        finding.category == "local-file" and finding.status == "pass" for finding in report.findings
    )


def test_missing_file_and_anchor_are_reported(tmp_path: Path) -> None:
    source = _write_markdown(
        tmp_path,
        "[missing file](missing.md)\n[missing anchor](target.md#no-such-anchor)\n",
    )
    (source.parent / "target.md").write_text("# Existing\n", encoding="utf-8")

    report = check_repository(tmp_path, paths=[source])

    assert {finding.category for finding in report.errors} == {"missing-file", "missing-anchor"}


def test_duplicate_github_heading_slug_is_supported(tmp_path: Path) -> None:
    source = _write_markdown(tmp_path, "[second](target.md#section-1)\n")
    (source.parent / "target.md").write_text("# Section\n# Section\n", encoding="utf-8")

    report = check_repository(tmp_path, paths=[source])

    assert not report.errors


def test_public_content_paths_must_be_declared_public_routes(tmp_path: Path) -> None:
    manifest = tmp_path / "frontend" / "src" / "content" / "publicContent.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "pages": [
                    {"path": "/known", "status": "published"},
                    {
                        "path": "/known",
                        "status": "published",
                        "related": [{"path": "/missing"}],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = check_repository(tmp_path, paths=[manifest])

    assert any(finding.category == "unknown-public-route" for finding in report.errors)
    assert any(
        finding.target == "/known" and finding.status == "pass" for finding in report.findings
    )


def test_static_source_anchor_is_checked(tmp_path: Path) -> None:
    source = tmp_path / "frontend" / "src" / "pages" / "landing" / "Page.tsx"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('<a href="#faq">FAQ</a><section id="faq" />', encoding="utf-8")

    report = check_repository(tmp_path, paths=[source])

    assert not report.errors


def test_frontend_root_relative_assets_are_checked_as_local_files(tmp_path: Path) -> None:
    source = tmp_path / "frontend" / "index.html"
    manifest = tmp_path / "frontend" / "public" / "manifest.webmanifest"
    asset = tmp_path / "frontend" / "public" / "assets" / "brand.svg"
    source.parent.mkdir(parents=True, exist_ok=True)
    asset.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('<link rel="icon" href="/assets/brand.svg" />', encoding="utf-8")
    manifest.write_text('{"icons": [{"src": "/assets/brand.svg"}]}', encoding="utf-8")
    asset.write_text("<svg />", encoding="utf-8")

    report = check_repository(tmp_path, paths=[source, manifest])

    assert not report.errors
    assert sum(finding.category == "public-asset" for finding in report.findings) == 2


def test_redirect_is_a_successful_external_result() -> None:
    status, category, detail = _classify_http_response(
        HttpResponse(status=301, final_url="https://public.example/final", redirects=1)
    )

    assert (status, category) == ("pass", "redirect")
    assert detail == "HTTP 301"


def test_redirect_to_private_host_is_blocked_before_network() -> None:
    handler = _RedirectCounter()

    try:
        handler.redirect_request(
            Request("https://public.example/start"),
            None,
            302,
            "Found",
            {},
            "http://127.0.0.1/private",
        )
    except URLError as error:
        assert "excluded" in str(error)
    else:
        raise AssertionError("redirect to a private host must not be followed")


def test_external_404_is_confirmed_but_429_is_deferred(tmp_path: Path) -> None:
    source = _write_markdown(
        tmp_path,
        "[missing](https://public.example/missing)\n[limited](https://public.example/limited)\n",
    )

    def fetch(url: str, timeout: float) -> HttpResponse:
        del timeout
        return HttpResponse(404 if url.endswith("missing") else 429)

    report = check_repository(tmp_path, paths=[source], external=True, fetch=fetch)

    assert [
        finding.status for finding in report.findings if finding.category == "confirmed-http-error"
    ] == ["error"]
    assert any(
        finding.status == "deferred" and finding.category == "temporary-http-condition"
        for finding in report.findings
    )
    assert len(report.errors) == 1


def test_timeout_is_deferred_and_does_not_fail_report(tmp_path: Path) -> None:
    source = _write_markdown(tmp_path, "[slow](https://public.example/slow)\n")

    def fetch(url: str, timeout: float) -> HttpResponse:
        del url, timeout
        raise TimeoutError

    report = check_repository(tmp_path, paths=[source], external=True, fetch=fetch)

    assert not report.errors
    assert any(finding.category == "network-timeout" for finding in report.findings)


def test_unsupported_and_private_urls_never_reach_fetch_and_are_redacted(tmp_path: Path) -> None:
    source = _write_markdown(
        tmp_path,
        "[file](file:///secret.txt)\n"
        "[private](http://127.0.0.1/export?token=secret-token)\n"
        "[provider](https://www.fatsecret.com/users/private-export/secret-id?token=personal-token)\n",
    )

    def fetch(url: str, timeout: float) -> HttpResponse:
        raise AssertionError(f"forbidden network call: {url} timeout={timeout}")

    report = check_repository(tmp_path, paths=[source], external=True, fetch=fetch)
    output = _render_report(report, json_output=True)

    assert not report.errors
    assert {finding.category for finding in report.findings} >= {"unsupported-url", "forbidden-url"}
    assert "secret-token" not in output
    assert "personal-token" not in output
    assert "private-export" not in output
    assert "secret-id" not in output


def test_live_public_route_404_is_checked_without_auth(tmp_path: Path) -> None:
    source = _write_markdown(tmp_path, "[public](/public-page)\n")
    manifest = tmp_path / "frontend" / "src" / "content" / "publicContent.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"pages": [{"path": "/public-page"}]}), encoding="utf-8")

    def fetch(url: str, timeout: float) -> HttpResponse:
        del timeout
        assert url == "https://public.example/public-page"
        return HttpResponse(404)

    report = check_repository(
        tmp_path,
        paths=[source, manifest],
        public_base_url="https://public.example",
        fetch=fetch,
    )

    assert any(finding.category == "confirmed-http-error" for finding in report.errors)
