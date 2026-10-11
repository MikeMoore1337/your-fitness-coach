"""Аудит USDA: без записи в БД, с явной очередью согласования."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from scripts.audit_usda_catalog import audit


@pytest.mark.parametrize(
    ("changes", "code", "expected"),
    [
        ({"added_count": 0, "removed_count": 0, "changed_count": 0}, 0, "unchanged"),
        ({"added_count": 1, "removed_count": 0, "changed_count": 0}, 0, "needs_review"),
        ({"added_count": 0, "removed_count": 0, "changed_count": 1}, 2, "needs_review"),
        ({"added_count": 0, "removed_count": 1, "changed_count": 0}, 2, "needs_review"),
    ],
)
def test_quarterly_audit_is_read_only_and_flags_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changes: dict,
    code: int,
    expected: str,
) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text('{"valid":true}', encoding="utf-8")
    candidate = tmp_path / "candidate.json"
    report = tmp_path / "report.json"

    def fake_run(args, **kwargs):
        assert "import_food_catalog" not in " ".join(map(str, args))
        assert kwargs["capture_output"] and kwargs["timeout"] <= 300
        if "export_usda_reviewed_catalog.py" in str(args[1]):
            candidate.write_text('{"valid":true}', encoding="utf-8")
            return subprocess.CompletedProcess(args, 0, stdout="Validated snapshot", stderr="")
        return subprocess.CompletedProcess(args, code, stdout=json.dumps(changes), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = audit(baseline=baseline, candidate=candidate, report=report)
    output = json.loads(report.read_text(encoding="utf-8"))
    assert result == (2 if expected == "needs_review" else 0)
    assert output["status"] == expected
    assert output["db_mutations"] is False
    assert "USDA_FDC_API_KEY" not in report.read_text(encoding="utf-8")
    assert candidate.exists()


def test_quarterly_audit_fail_closed_on_export_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text('{"valid":true}', encoding="utf-8")
    candidate = tmp_path / "candidate.json"
    report = tmp_path / "report.json"

    def fail_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="SECRET=should_not_log")

    monkeypatch.setattr(subprocess, "run", fail_run)
    assert audit(baseline=baseline, candidate=candidate, report=report) == 1
    output = json.loads(report.read_text(encoding="utf-8"))
    assert output["status"] == "error"
    assert "SECRET=" not in report.read_text(encoding="utf-8")
    assert output["db_mutations"] is False


def test_quarterly_audit_never_overwrites_existing_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text("base", encoding="utf-8")
    candidate = tmp_path / "candidate.json"
    candidate.write_text("preserve", encoding="utf-8")
    report = tmp_path / "report.json"

    def should_not_run(*args, **kwargs):
        pytest.fail("Auditor must reject existing artifacts without launching subprocesses")

    monkeypatch.setattr(subprocess, "run", should_not_run)
    assert audit(baseline=baseline, candidate=candidate, report=report) == 1
    assert candidate.read_text(encoding="utf-8") == "preserve"
