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


def test_inspect_redacts_environment_values(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(recovery, "APP_ROOT", tmp_path)
    monkeypatch.setattr(recovery, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(recovery, "MARKER", tmp_path / "marker")
    monkeypatch.setattr(recovery, "container_summary", lambda: {})
    recovery.ENV_FILE.write_bytes(broken_env("password(secret)"))
    recovery.ENV_FILE.chmod(0o600)
    report = recovery.inspect()
    assert report["env_bash_syntax_valid"] is False
    assert report["line_30_key"] == "EXPECTED_KEY"
    assert "password" not in str(report)
    assert "secret" not in str(report)
