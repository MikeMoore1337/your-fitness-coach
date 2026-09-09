from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.check_deployment import HttpResponse, check_deployment

BASE_URL = "https://app.example.test"
HTML = b'<html><body><div id="root"></div><script src="/assets/app-abc.js"></script></body></html>'


def _response(
    path: str,
    *,
    body: bytes,
    content_type: str,
    cache_control: str = "no-store",
    final_url: str | None = None,
) -> HttpResponse:
    return HttpResponse(
        status=200,
        body=body,
        content_type=content_type,
        final_url=final_url or f"{BASE_URL}{path}",
        headers={"cache-control": cache_control},
    )


def test_deployment_smoke_separates_compatible_preflight_from_release_contract() -> None:
    responses = {
        "/health/ready": _response(
            "/health/ready", body=b'{"status":"ok"}', content_type="application/json"
        ),
        "/health/live": _response(
            "/health/live", body=b'{"status":"ok"}', content_type="application/json"
        ),
        "/api/v1/public/config": _response(
            "/api/v1/public/config",
            body=(
                b'{"app_env":"prod","enable_dev_auth":false,'
                b'"enable_web_auth":true,"enable_email_auth":false}'
            ),
            content_type="application/json",
        ),
        "/api/v1/me": HttpResponse(
            status=401,
            body=b'{"detail":"Not authenticated"}',
            content_type="application/json",
            final_url=f"{BASE_URL}/api/v1/me",
            headers={"cache-control": "no-store"},
        ),
        "/api/v1/auth/refresh": HttpResponse(
            status=401,
            body=b'{"detail":"Not authenticated"}',
            content_type="application/json",
            final_url=f"{BASE_URL}/api/v1/auth/refresh",
            headers={"cache-control": "no-store"},
        ),
        "/app": _response("/app", body=HTML, content_type="text/html"),
        "/app/report?period=days_30": _response(
            "/app/report?period=days_30", body=HTML, content_type="text/html"
        ),
        "/login": _response("/login", body=HTML, content_type="text/html"),
        "/app?tgWebAppPlatform=android": _response(
            "/app?tgWebAppPlatform=android", body=HTML, content_type="text/html"
        ),
        "/assets/app-abc.js": _response(
            "/assets/app-abc.js",
            body=b"export {};",
            content_type="text/javascript",
            cache_control="public, max-age=31536000, immutable",
        ),
    }

    requested_paths: list[str] = []

    def read(
        _base_url: str,
        path: str,
        *,
        timeout: float,
        method: str = "GET",
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        assert timeout == 3
        requested_paths.append(path)
        if path == "/api/v1/auth/refresh":
            assert method == "POST"
            assert body == b"{}"
            assert headers == {"Accept": "application/json", "Content-Type": "application/json"}
        else:
            assert method == "GET"
            assert body is None
            assert headers is None
        return responses[path]

    assert (
        check_deployment(
            BASE_URL,
            timeout=3,
            expected_environment="prod",
            require_progress_report_shell=True,
            read=read,
        )
        == "prod"
    )
    assert "/app/report?period=days_30" in requested_paths

    requested_paths.clear()
    assert check_deployment(BASE_URL, timeout=3, expected_environment="prod", read=read) == "prod"
    assert "/app/report?period=days_30" not in requested_paths


def test_rollout_smoke_requires_new_contract_only_for_candidate_and_post_switch(
    monkeypatch,
) -> None:
    from scripts import zero_downtime_deploy

    commands: list[list[str]] = []
    monkeypatch.setattr(
        zero_downtime_deploy,
        "_run",
        lambda args, **_kwargs: commands.append(list(args)),
    )
    config = SimpleNamespace(
        base_url=BASE_URL,
        public_base_url="https://public.example.test",
        seo_timeout_seconds=4,
    )

    zero_downtime_deploy._public_smoke(config)
    assert "--expect-progress-report-shell" not in commands[0]

    commands.clear()
    zero_downtime_deploy._public_smoke(config, require_progress_report_shell=True)
    assert "--expect-progress-report-shell" in commands[0]

    commands.clear()
    zero_downtime_deploy._candidate_smoke("legacy")
    assert "--expect-progress-report-shell" not in commands[0]

    commands.clear()
    zero_downtime_deploy._candidate_smoke("legacy", require_progress_report_shell=True)
    assert "--expect-progress-report-shell" in commands[0]

    source = (
        Path(__file__).resolve().parents[2] / "scripts" / "zero_downtime_deploy.py"
    ).read_text(encoding="utf-8")
    single_preflight_start = source.index('with _stage(evidence, "single_slot_preflight")')
    single_preflight_end = source.index(
        'with _stage(evidence, "pull_and_verify")', single_preflight_start
    )
    single_preflight = source[single_preflight_start:single_preflight_end]
    assert "_public_smoke(config)" in single_preflight
    assert "require_progress_report_shell=True" not in single_preflight

    application_start = source.index('with _stage(evidence, "application_start")')
    application_end = source.index('with _stage(evidence, "verification")', application_start)
    assert "require_progress_report_shell=True" in source[application_start:application_end]


def test_deployment_smoke_rejects_origin_escape() -> None:
    def read(_base_url: str, path: str, *, timeout: float) -> HttpResponse:
        del timeout
        return _response(
            path,
            body=b'{"status":"ok"}',
            content_type="application/json",
            final_url="http://internal.example.test/health/ready",
        )

    with pytest.raises(RuntimeError, match="escaped the deployment origin"):
        check_deployment(BASE_URL, timeout=3, read=read)


def test_production_deploy_is_fail_closed_before_backup_and_runs_public_smoke() -> None:
    script = (Path(__file__).resolve().parents[2] / "scripts" / "deploy_production.sh").read_text(
        encoding="utf-8"
    )

    digest_gate = script.index("require_digest_ref POSTGRES_IMAGE")
    compose_gate = script.index("docker compose config --quiet")
    rollout = script.index("scripts/zero_downtime_deploy.py")

    assert digest_gate < compose_gate < rollout
    assert "--remove-orphans" not in script
    assert "docker compose up" not in script
