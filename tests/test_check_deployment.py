from __future__ import annotations

import json
import sys

import pytest
from scripts import check_deployment


def _fake_read(config: dict[str, object]):
    base_url = "https://app.example.test"
    html = b'<div id="root"></div><script src="/assets/app-abc.js"></script>'

    def response(
        path: str,
        body: bytes,
        content_type: str,
        *,
        cache_control: str = "no-store",
    ) -> check_deployment.HttpResponse:
        return check_deployment.HttpResponse(
            status=200,
            body=body,
            content_type=content_type,
            final_url=f"{base_url}{path}",
            headers={"cache-control": cache_control},
        )

    responses = {
        "/health/ready": response("/health/ready", b'{"status":"ok"}', "application/json"),
        "/health/live": response("/health/live", b'{"status":"ok"}', "application/json"),
        "/api/v1/public/config": response(
            "/api/v1/public/config",
            json.dumps(config).encode(),
            "application/json",
        ),
        "/api/v1/me": check_deployment.HttpResponse(
            status=401,
            body=b'{"detail":"Not authenticated"}',
            content_type="application/json",
            final_url=f"{base_url}/api/v1/me",
            headers={"cache-control": "no-store"},
        ),
        "/api/v1/auth/refresh": check_deployment.HttpResponse(
            status=401,
            body=b'{"detail":"Not authenticated"}',
            content_type="application/json",
            final_url=f"{base_url}/api/v1/auth/refresh",
            headers={"cache-control": "no-store"},
        ),
        "/app": response("/app", html, "text/html; charset=utf-8"),
        "/login": response("/login", html, "text/html; charset=utf-8"),
        "/app?tgWebAppPlatform=android": response(
            "/app?tgWebAppPlatform=android", html, "text/html; charset=utf-8"
        ),
        "/assets/app-abc.js": response(
            "/assets/app-abc.js",
            b"export {};",
            "text/javascript",
            cache_control="public, max-age=31536000, immutable",
        ),
    }

    def read(
        _base_url: str,
        path: str,
        *,
        timeout: float,
        method: str = "GET",
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> check_deployment.HttpResponse:
        assert timeout == 10.0
        if path == "/api/v1/auth/refresh":
            assert method == "POST"
            assert body == b"{}"
            assert headers == {"Accept": "application/json", "Content-Type": "application/json"}
        else:
            assert method == "GET"
            assert body is None
            assert headers is None
        return responses[path]

    return read


def test_production_smoke_requires_safe_environment_and_auth_flags(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        check_deployment,
        "_read",
        _fake_read(
            {
                "app_env": "prod",
                "enable_dev_auth": False,
                "enable_web_auth": True,
                "enable_email_auth": False,
            }
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["check_deployment.py", "https://app.example.test", "--expect-app-env", "prod"],
    )

    assert check_deployment.main() == 0
    assert "Environment reported by API: prod" in capsys.readouterr().out


def test_deployment_check_can_skip_rate_limited_refresh_boundary() -> None:
    read = _fake_read(
        {
            "app_env": "prod",
            "enable_dev_auth": False,
            "enable_web_auth": True,
            "enable_email_auth": False,
        }
    )

    def no_refresh(
        base_url: str,
        path: str,
        *,
        timeout: float,
        method: str = "GET",
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> check_deployment.HttpResponse:
        if path == "/api/v1/auth/refresh":
            pytest.fail("rate-limited refresh boundary should be skipped")
        return read(
            base_url,
            path,
            timeout=timeout,
            method=method,
            body=body,
            headers=headers,
        )

    assert (
        check_deployment.check_deployment(
            "https://app.example.test",
            timeout=10.0,
            expected_environment="prod",
            check_refresh_boundary=False,
            read=no_refresh,
        )
        == "prod"
    )


@pytest.mark.parametrize(
    "config, expected_error",
    [
        (
            {
                "app_env": "test",
                "enable_dev_auth": False,
                "enable_web_auth": True,
                "enable_email_auth": False,
            },
            "expected 'prod'",
        ),
        (
            {
                "app_env": "prod",
                "enable_dev_auth": True,
                "enable_web_auth": True,
                "enable_email_auth": False,
            },
            "production auth flags are unsafe",
        ),
    ],
)
def test_production_smoke_rejects_unsafe_public_config(
    config: dict[str, object],
    expected_error: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(check_deployment, "_read", _fake_read(config))
    monkeypatch.setattr(
        sys,
        "argv",
        ["check_deployment.py", "https://app.example.test", "--expect-app-env", "prod"],
    )

    assert check_deployment.main() == 1
    assert expected_error in capsys.readouterr().err
