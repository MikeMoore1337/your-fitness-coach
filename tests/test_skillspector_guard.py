from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import skillspector_guard as guard


def _report(
    *,
    recommendation: str = "SAFE",
    severity: str = "LOW",
    score: int = 0,
    complete: bool = True,
    llm_requested: bool = False,
    llm_calls_attempted: int = 0,
    reason_codes: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "execution_successful": True,
        "skill": {"name": "sample"},
        "risk_assessment": {
            "score": score,
            "severity": severity,
            "recommendation": recommendation,
        },
        "metadata": {
            "llm_requested": llm_requested,
            "llm_calls_attempted": llm_calls_attempted,
        },
        "analysis_completeness": {
            "execution_successful": True,
            "is_complete": complete,
            "status": "complete" if complete else "partial",
            "coverage_percent": 100.0,
            "entirely_uninspected_files": 0,
            "partially_inspected_files": 0,
            "limitations": [],
            "ledger_exceptions": [
                {"reason_code": reason_code}
                for reason_code in reason_codes
            ],
        },
        "issues": [],
    }


def _runner_with_report(report: dict[str, object], *, returncode: int = 0):
    def runner(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        output_index = command.index("--output") + 1
        Path(command[output_index]).write_text(json.dumps(report), encoding="utf-8")
        return subprocess.CompletedProcess(command, returncode, stdout="", stderr="")

    return runner


def test_command_is_pinned_static_and_fail_closed(tmp_path: Path) -> None:
    command = guard.build_command(tmp_path / "skill", tmp_path / "report.json", uvx="uvx")

    assert command[:4] == [
        "uvx",
        "--from",
        f"git+https://github.com/NVIDIA/SkillSpector.git@{guard.SKILLSPECTOR_COMMIT}",
        "skillspector",
    ]
    assert command[4:6] == ["scan", str((tmp_path / "skill").resolve())]
    assert "--no-llm" in command
    assert command[command.index("--format") + 1] == "json"
    assert "--fail-on-incomplete" in command
    assert "--output" in command


def test_safe_scan_passes_and_strips_secret_env(tmp_path: Path) -> None:
    skill = tmp_path / "safe"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# Safe\n", encoding="utf-8")
    observed: dict[str, object] = {}

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed["env"] = kwargs["env"]
        Path(command[command.index("--output") + 1]).write_text(
            json.dumps(_report()), encoding="utf-8"
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    verdict = guard.scan_skill(
        skill,
        output_root=tmp_path / "out",
        runner=runner,
        uvx="uvx",
        env={"PATH": "/bin", "OPENAI_API_KEY": "secret", "GITHUB_TOKEN": "secret"},
    )

    assert verdict.recommendation == "SAFE"
    assert observed["env"] == {"PATH": "/bin"}


def test_caution_is_warning_not_blocker(tmp_path: Path) -> None:
    skill = tmp_path / "caution"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# Caution\n", encoding="utf-8")

    verdict = guard.scan_skill(
        skill,
        output_root=tmp_path / "out",
        runner=_runner_with_report(
            _report(recommendation="CAUTION", severity="MEDIUM", score=35)
        ),
        uvx="uvx",
        env={"PATH": "/bin"},
    )

    assert verdict.warning is True
    assert verdict.severity == "MEDIUM"


def test_do_not_install_blocks(tmp_path: Path) -> None:
    skill = tmp_path / "bad"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# Bad\n", encoding="utf-8")

    with pytest.raises(guard.SkillSpectorGuardError, match="blocked"):
        guard.scan_skill(
            skill,
            output_root=tmp_path / "out",
            runner=_runner_with_report(
                _report(recommendation="DO_NOT_INSTALL", severity="HIGH", score=70),
                returncode=1,
            ),
            uvx="uvx",
            env={"PATH": "/bin"},
        )


def test_reference_missing_only_is_nonblocking_caution(tmp_path: Path) -> None:
    skill = tmp_path / "missing-reference"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# Missing reference\n", encoding="utf-8")

    verdict = guard.scan_skill(
        skill,
        output_root=tmp_path / "out",
        runner=_runner_with_report(
            _report(
                recommendation="CAUTION",
                severity="MEDIUM",
                score=10,
                complete=False,
                reason_codes=("reference_missing",),
            ),
            returncode=1,
        ),
        uvx="uvx",
        env={"PATH": "/bin"},
    )

    assert verdict.warning is True


def test_ambiguous_reference_still_blocks(tmp_path: Path) -> None:
    skill = tmp_path / "ambiguous-reference"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# Ambiguous reference\n", encoding="utf-8")

    with pytest.raises(guard.SkillSpectorGuardError, match="incomplete"):
        guard.scan_skill(
            skill,
            output_root=tmp_path / "out",
            runner=_runner_with_report(
                _report(
                    recommendation="CAUTION",
                    severity="MEDIUM",
                    score=10,
                    complete=False,
                    reason_codes=("reference_unresolved",),
                ),
                returncode=1,
            ),
            uvx="uvx",
            env={"PATH": "/bin"},
        )


def test_incomplete_scan_blocks(tmp_path: Path) -> None:
    skill = tmp_path / "partial"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# Partial\n", encoding="utf-8")

    with pytest.raises(guard.SkillSpectorGuardError, match="incomplete"):
        guard.scan_skill(
            skill,
            output_root=tmp_path / "out",
            runner=_runner_with_report(_report(complete=False), returncode=1),
            uvx="uvx",
            env={"PATH": "/bin"},
        )


def test_malformed_report_blocks(tmp_path: Path) -> None:
    skill = tmp_path / "broken"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# Broken\n", encoding="utf-8")

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        Path(command[command.index("--output") + 1]).write_text("{bad", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    with pytest.raises(guard.SkillSpectorGuardError, match="unreadable"):
        guard.scan_skill(
            skill,
            output_root=tmp_path / "out",
            runner=runner,
            uvx="uvx",
            env={"PATH": "/bin"},
        )


def test_tool_error_blocks(tmp_path: Path) -> None:
    skill = tmp_path / "tool-error"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# Tool\n", encoding="utf-8")

    def runner(command: list[str], **kwargs: object) -> SimpleNamespace:
        del command, kwargs
        return SimpleNamespace(returncode=2, stdout="", stderr="internal failure")

    with pytest.raises(guard.SkillSpectorGuardError, match="tool error"):
        guard.scan_skill(
            skill,
            output_root=tmp_path / "out",
            runner=runner,
            uvx="uvx",
            env={"PATH": "/bin"},
        )


def test_unexpected_llm_usage_blocks(tmp_path: Path) -> None:
    skill = tmp_path / "llm"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# LLM\n", encoding="utf-8")

    with pytest.raises(guard.SkillSpectorGuardError, match="LLM"):
        guard.scan_skill(
            skill,
            output_root=tmp_path / "out",
            runner=_runner_with_report(
                _report(llm_requested=True, llm_calls_attempted=1)
            ),
            uvx="uvx",
            env={"PATH": "/bin"},
        )


def test_discover_external_skills_uses_source_json(tmp_path: Path) -> None:
    external = tmp_path / "external"
    external.mkdir()
    (external / "SKILL.md").write_text("# External\n", encoding="utf-8")
    (external / "SOURCE.json").write_text("{}", encoding="utf-8")
    internal = tmp_path / "internal"
    internal.mkdir()
    (internal / "SKILL.md").write_text("# Internal\n", encoding="utf-8")

    assert guard.discover_external_skills(tmp_path) == [external.resolve()]


def test_no_external_skills_is_clean_noop(tmp_path: Path) -> None:
    internal = tmp_path / "internal"
    internal.mkdir()
    (internal / "SKILL.md").write_text("# Internal\n", encoding="utf-8")

    assert guard.scan_external_skills(
        tmp_path,
        output_root=tmp_path / "out",
        runner=lambda *args, **kwargs: pytest.fail("runner must not execute"),
        uvx="uvx",
        env={"PATH": "/bin"},
    ) == []
