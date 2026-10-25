"""Offline safety and command-contract checks for optional GEO audit (#1224)."""

from __future__ import annotations

import json
import subprocess

import pytest

from scripts.geo_readonly_audit import (
    CANONICAL_ORIGIN,
    MAX_OUTPUT_CHARS,
    audit,
    main,
    plan_audits,
    restricted_environment,
)


def test_preview_requires_no_cli_and_never_executes() -> None:
    def unexpected(_: str) -> str | None:
        raise AssertionError("dry-run must never resolve or execute external CLI")

    result = audit(["/", "/nutrition", "/"], execute=False, which=unexpected)
    assert result["status"] == "PREVIEW_ONLY"
    assert result["external_execution"] == "NOT_EXECUTED"
    assert result["real_ai_citations"] == "NOT_MEASURED"
    assert result["commands"] == [
        ["geo", "audit", "--url", f"{CANONICAL_ORIGIN}/"],
        ["geo", "audit", "--url", f"{CANONICAL_ORIGIN}/nutrition"],
    ]


@pytest.mark.parametrize(
    "route",
    [
        "/app",
        "/api/v1/public/exercises",
        "/admin",
        "https://attacker.example",
        "/nutrition?token=secret",
        "/knowledge/../app",
        "//attacker.example",
    ],
)
def test_arbitrary_or_private_routes_rejected(route: str) -> None:
    with pytest.raises(ValueError, match="allowlisted"):
        plan_audits([route])


def test_empty_routes_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        plan_audits([])


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), 120.01])
def test_invalid_timeout_fails_closed(value: float) -> None:
    with pytest.raises(ValueError, match="timeout"):
        audit(["/"], execute=False, timeout=value)


def test_executes_only_readonly_audit_with_sanitized_env() -> None:
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout="Score 70/100", stderr="")

    report = audit(
        ["/training"],
        execute=True,
        which=lambda _: "/opt/tools/geo",
        run=fake_run,
        environment={
            "PATH": "/opt/tools",
            "HOME": "/private/home",
            "OPENAI_API_KEY": "do-not-leak",
            "GITHUB_TOKEN": "secret",
        },
    )
    assert report["status"] == "OBSERVED_CLI_RESULTS"
    assert report["real_ai_citations"] == "NOT_MEASURED"
    assert report["results"][0]["score_is_tool_heuristic"] is True
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv == ["/opt/tools/geo", "audit", "--url", f"{CANONICAL_ORIGIN}/training"]
    assert kwargs["shell"] is False
    assert kwargs["check"] is False
    assert kwargs["capture_output"] is True
    assert kwargs["timeout"] == 30
    assert kwargs["env"]["PATH"] == "/opt/tools"
    assert "OPENAI_API_KEY" not in kwargs["env"]
    assert "GITHUB_TOKEN" not in kwargs["env"]
    assert "HOME" not in kwargs["env"]


def test_missing_executable_blocks_execution() -> None:
    with pytest.raises(RuntimeError, match="unavailable"):
        audit(["/"], execute=True, which=lambda _: None)


def test_relative_executable_rejected() -> None:
    with pytest.raises(RuntimeError, match="absolute"):
        audit(["/"], execute=True, which=lambda _: "./geo")


def test_timeout_and_cli_failure_are_not_reported_as_success() -> None:
    def timed_out(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], timeout=kwargs["timeout"])

    with pytest.raises(RuntimeError, match="timed out"):
        audit(["/"], execute=True, which=lambda _: "/bin/geo", run=timed_out)

    with pytest.raises(RuntimeError, match="exit code 7"):
        audit(
            ["/"],
            execute=True,
            which=lambda _: "/bin/geo",
            run=lambda argv, **kwargs: subprocess.CompletedProcess(argv, 7, "", "secret"),
        )


def test_output_is_bounded_and_does_not_promise_visibility() -> None:
    text = "x" * (MAX_OUTPUT_CHARS + 42)
    report = audit(
        ["/"],
        execute=True,
        which=lambda _: "/bin/geo",
        run=lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, text, ""),
    )
    result = report["results"][0]
    assert len(result["stdout_excerpt"]) == MAX_OUTPUT_CHARS
    assert result["stdout_truncated"] is True
    assert report["real_ai_citations"] == "NOT_MEASURED"


def test_environment_allowlist_strips_case_insensitive_secret_keys() -> None:
    actual = restricted_environment(
        {"PATH": "/bin", "path": "/hidden", "SECRET_KEY": "secret", "azure_client_secret": "secret"}
    )
    assert "SECRET_KEY" not in actual
    assert "azure_client_secret" not in actual
    assert actual["NO_COLOR"] == "1"


def test_main_preview_is_offline(capsys) -> None:
    assert main(["--route", "/nutrition"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "PREVIEW_ONLY"
    assert report["commands"][0][-1] == f"{CANONICAL_ORIGIN}/nutrition"


def test_main_bad_timeout_fails_without_subprocess(capsys) -> None:
    assert main(["--timeout", "-1", "--execute"]) == 2
    assert "GEO_READONLY_NOT_VERIFIED" in capsys.readouterr().err
