"""Security and regression tests for the one-use #1249 production helper."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts import incident_1249_recovery as recovery


def broken_env(value: str = "something(else)") -> bytes:
    return ("SAFE=value\n" * 29 + "EXPECTED_KEY=" + value + "\n").encode()


def test_candidate_only_quotes_plain_line_30_value() -> None:
    original = broken_env()
    assert not recovery.bash_valid(original)
    candidate = recovery.candidate_fix(original, "EXPECTED_KEY")
    assert recovery.bash_valid(candidate)
    assert candidate.splitlines()[:29] == original.splitlines()[:29]
    assert candidate.splitlines()[29] == b"EXPECTED_KEY='something(else)'"


@pytest.mark.parametrize("value", ["$(echo forbidden)", "hello;touch", "a|b(c)", "safe"])
def test_candidate_rejects_complex_or_irrelevant_values(value: str) -> None:
    with pytest.raises(recovery.RecoveryError):
        recovery.candidate_fix(broken_env(value), "EXPECTED_KEY")


def test_repair_requires_prior_checksum_and_preserves_private_backup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(recovery, "ENV_FILE", tmp_path / ".env")
    original = broken_env()
    recovery.ENV_FILE.write_bytes(original)
    recovery.ENV_FILE.chmod(0o600)

    with pytest.raises(recovery.RecoveryError):
        recovery.fix_env("0" * 64, "EXPECTED_KEY")
    assert recovery.ENV_FILE.read_bytes() == original

    outcome = recovery.fix_env(recovery.checksum(original), "EXPECTED_KEY")
    assert outcome["env_bash_syntax_valid"] is True
    assert recovery.bash_valid(recovery.ENV_FILE.read_bytes())
    backups = list(tmp_path.glob(".env.incident-1249.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert backups[0].stat().st_mode & 0o077 == 0

    with pytest.raises(recovery.RecoveryError):
        recovery.fix_env(recovery.checksum(original), "EXPECTED_KEY")


def test_inspect_redacts_environment_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(recovery, "APP_ROOT", tmp_path)
    monkeypatch.setattr(recovery, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(recovery, "MARKER", tmp_path / "marker")
    monkeypatch.setattr(recovery, "container_summary", lambda: {})
    monkeypatch.setattr(recovery, "stopped_runtime_candidate_summary", lambda _rev: {})
    recovery.ENV_FILE.write_bytes(broken_env("password(secret)"))
    recovery.ENV_FILE.chmod(0o600)
    report = recovery.inspect()
    assert report["env_bash_syntax_valid"] is False
    assert report["line_30_key"] == "EXPECTED_KEY"
    assert "password" not in str(report)
    assert "secret" not in str(report)


def test_candidate_can_repair_two_simple_parenthesized_assignments() -> None:
    original = broken_env() + b"SECOND_AGENT=another(contact@example.org)\n"
    corrected = recovery.candidate_fix(original, "EXPECTED_KEY")
    assert recovery.bash_valid(corrected)
    assert corrected.splitlines()[29] == b"EXPECTED_KEY='something(else)'"
    assert corrected.splitlines()[30] == b"SECOND_AGENT='another(contact@example.org)'"


def test_candidate_rejects_more_than_three_additional_lines() -> None:
    original = broken_env() + b"OTHER_AGENT=another(contact@example.org)\n" * 4
    with pytest.raises(recovery.RecoveryError, match="too many additional"):
        recovery.candidate_fix(original, "EXPECTED_KEY")


def test_readonly_diagnostic_reports_sanitized_next_parse_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(recovery, "APP_ROOT", tmp_path)
    monkeypatch.setattr(recovery, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(recovery, "MARKER", tmp_path / "marker")
    monkeypatch.setattr(recovery, "container_summary", lambda: {})
    monkeypatch.setattr(recovery, "stopped_runtime_candidate_summary", lambda _rev: {})
    original = ("SAFE=value\n" * 29 + "FIRST_KEY=hello(first)\nSECOND_KEY=hello(second)\n").encode()
    recovery.ENV_FILE.write_bytes(original)
    recovery.ENV_FILE.chmod(0o600)

    report = recovery.inspect()
    assert report["env_bash_syntax_valid"] is False
    assert report["bash_parse_error_line"] == 30
    assert report["bash_parse_error_key"] == "FIRST_KEY"
    assert report["line_30_preview_error_line"] == 31
    assert report["line_30_preview_error_key"] == "SECOND_KEY"
    assert report["bounded_preview_bash_valid"] is True
    assert report["bounded_preview_error_line"] is None
    assert "hello(first)" not in str(report)
    assert "hello(second)" not in str(report)
    assert recovery.ENV_FILE.read_bytes() == original


def test_line_98_diagnostic_previews_only_literal_without_exposing_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(recovery, "APP_ROOT", tmp_path)
    monkeypatch.setattr(recovery, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(recovery, "MARKER", tmp_path / "marker")
    monkeypatch.setattr(recovery, "container_summary", lambda: {})
    monkeypatch.setattr(recovery, "stopped_runtime_candidate_summary", lambda _rev: {})
    original = (
        "SAFE=value\n" * 29
        + "OPEN_FOOD_FACTS_USER_AGENT=fitness(client)\n"
        + "SAFE=value\n" * 67
        + "CLOUDFLARED_TOKEN=token(other)\n"
    ).encode()
    recovery.ENV_FILE.write_bytes(original)
    recovery.ENV_FILE.chmod(0o600)

    report = recovery.inspect()
    assert report["line_98_key"] == "CLOUDFLARED_TOKEN"
    assert report["line_30_and_98_literal_preview_safe"] is True
    assert report["line_30_and_98_literal_preview_bash_valid"] is True
    assert report["line_30_and_98_literal_preview_error_line"] is None
    assert "token(other)" not in str(report)
    assert recovery.ENV_FILE.read_bytes() == original


def test_stopped_runtime_probe_rejects_wrong_image_revision(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from subprocess import CompletedProcess

    baseline = "a" * 40
    (tmp_path / "releases" / baseline).mkdir(parents=True)
    monkeypatch.setattr(recovery, "APP_ROOT", tmp_path)

    def fake_docker(args: list[str], **_kwargs: object) -> CompletedProcess[str]:
        if args[:3] == ["docker", "ps", "-a"]:
            service = args[args.index("--filter") + 1].rsplit("=", 1)[-1]
            return CompletedProcess(args, 0, f"{service}-id\n", "")
        if args[:3] == ["docker", "inspect", "--format"]:
            service = args[-1].removesuffix("-id")
            status = "running" if service in {"db", "edge"} else "exited"
            image_id = "sha256:backend" if service in {"backend", "worker"} else "sha256:bot"
            revision = ("b" * 40) if service == "bot" else baseline
            return CompletedProcess(
                args, 0, f"{status}|{image_id}|{revision}|healthy\n", ""
            )
        if args[:3] == ["docker", "compose", "config"]:
            return CompletedProcess(args, 0, "", "")
        raise AssertionError("Unexpected read-only Docker call")

    monkeypatch.setattr(recovery.subprocess, "run", fake_docker)
    report = recovery.stopped_runtime_candidate_summary(baseline)
    assert report["compose_config_valid"] is True
    assert report["backend_worker_same_image"] is True
    assert report["baseline_revision_verified"] is False
    states = report["service_states"]
    assert states["bot"]["oci_revision"] == "b" * 40
    assert states["backend"]["oci_revision"] == baseline
