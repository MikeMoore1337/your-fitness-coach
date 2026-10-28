"""External unmodified upstream Harness2 must never execute model benchmarks in YFC."""

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "harness2_dev.ps1"
PIN = "1cfe254e8d25b15f37048c3730134686abe60335"


def test_harness2_dev_is_read_only_upstream_bridge():
    text = SCRIPT.read_text(encoding="utf-8")
    assert PIN in text
    assert "https://github.com/google-research/harness2.git" in text
    assert "wsl.exe" in text
    assert '"$bin/harness2-check"' in text
    assert '"$bin/harness2-report"' in text
    assert '"$bin/harness2" ' not in text or "--dry-run" in text
    assert "SetupPreview" in text
    assert "RunPreview" in text
    assert '"$bin/harness2-setup" "$2" --dry-run' in text
    assert '"$bin/harness2" --bench "$2" --k 1 --mode parallel --max-tasks 1 --dry-run' in text
    assert '"$bin/harness2-judge"' not in text
    assert "codex exec" not in text
    assert "harness2-demo" not in text
