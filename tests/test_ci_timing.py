import json
from types import SimpleNamespace

from scripts import ci_timing


def test_main_runs_argv_without_shell_and_records_success(monkeypatch, tmp_path) -> None:
    timing_file = tmp_path / "timing.jsonl"
    observed: dict[str, object] = {}

    def fake_run(command, *, check):
        observed["command"] = command
        observed["check"] = check
        return SimpleNamespace(returncode=0)

    monkeypatch.setenv("CI_TIMING_FILE", str(timing_file))
    monkeypatch.setattr(ci_timing.subprocess, "run", fake_run)

    result = ci_timing.main(
        ["--group", "mobile", "--command", "install", "--", "npm", "ci", "--ignore-scripts"]
    )

    assert result == 0
    assert observed == {"command": ["npm", "ci", "--ignore-scripts"], "check": False}
    record = json.loads(timing_file.read_text(encoding="utf-8"))
    assert record["group"] == "mobile"
    assert record["command"] == "install"
    assert record["status"] == "success"
    assert record["attempts"] == 1
    assert record["duration_seconds"] >= 0


def test_main_propagates_child_failure_and_records_failed_status(monkeypatch, tmp_path) -> None:
    timing_file = tmp_path / "timing.jsonl"
    monkeypatch.setenv("CI_TIMING_FILE", str(timing_file))
    monkeypatch.setattr(
        ci_timing.subprocess,
        "run",
        lambda command, *, check: SimpleNamespace(returncode=17),
    )

    result = ci_timing.main(["--group", "mobile", "--command", "test", "--", "false"])

    assert result == 17
    record = json.loads(timing_file.read_text(encoding="utf-8"))
    assert record["status"] == "failed"
