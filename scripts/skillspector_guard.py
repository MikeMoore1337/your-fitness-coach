"""Second-stage NVIDIA SkillSpector gate for external YFC agent skills."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SKILLSPECTOR_VERSION = "2.11.2-postrelease"
SKILLSPECTOR_COMMIT = "d162d9b343e559be13df8ebba093df3bc9d58c90"
SKILLSPECTOR_SOURCE = (
    f"git+https://github.com/NVIDIA/SkillSpector.git@{SKILLSPECTOR_COMMIT}"
)
EXTERNAL_SOURCE_NAME = "SOURCE.json"
SECRET_ENV_RE = re.compile(
    r"(TOKEN|KEY|SECRET|PASSWORD|CREDENTIAL|AUTH|PRIVATE|SESSION)", re.IGNORECASE
)


class SkillSpectorGuardError(RuntimeError):
    """SkillSpector could not prove that the candidate skill is acceptable."""


@dataclass(frozen=True)
class ScanVerdict:
    skill: str
    recommendation: str
    severity: str
    score: int | float
    report_path: Path
    warning: bool


def _safe_env(source: Mapping[str, str] | None = None) -> dict[str, str]:
    raw = dict(os.environ if source is None else source)
    return {key: value for key, value in raw.items() if SECRET_ENV_RE.search(key) is None}


def discover_external_skills(skills_root: Path) -> list[Path]:
    root = skills_root.resolve()
    if not root.is_dir():
        raise SkillSpectorGuardError(f"Skills root not found: {root}")
    return sorted(
        path.parent
        for path in root.glob(f"*/{EXTERNAL_SOURCE_NAME}")
        if (path.parent / "SKILL.md").is_file()
    )


def build_command(skill_dir: Path, report_path: Path, *, uvx: str = "uvx") -> list[str]:
    return [
        uvx,
        "--from",
        SKILLSPECTOR_SOURCE,
        "skillspector",
        "scan",
        str(skill_dir.resolve()),
        "--no-llm",
        "--format",
        "json",
        "--output",
        str(report_path.resolve()),
        "--fail-on-incomplete",
    ]


def _parse_report(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SkillSpectorGuardError(f"SkillSpector report is unreadable: {path}") from error
    if not isinstance(raw, dict):
        raise SkillSpectorGuardError(f"SkillSpector report is not an object: {path}")
    return raw


def _completeness_diagnostic(completeness: Mapping[str, Any]) -> str:
    reason_codes: set[str] = set()
    exceptions = completeness.get("ledger_exceptions")
    if isinstance(exceptions, list):
        for item in exceptions:
            if isinstance(item, Mapping) and isinstance(item.get("reason_code"), str):
                reason_codes.add(str(item["reason_code"]))
    status = str(completeness.get("status") or "unknown")
    coverage = completeness.get("coverage_percent")
    coverage_text = str(coverage) if isinstance(coverage, (int, float)) else "unknown"
    reasons = ",".join(sorted(reason_codes)) or "none"
    return f"status={status} coverage={coverage_text} reason_codes={reasons}"


def _validate_static_report(report: Mapping[str, Any], report_path: Path) -> ScanVerdict:
    if report.get("execution_successful") is False:
        raise SkillSpectorGuardError(
            f"SkillSpector execution was not successful; inspect {report_path}"
        )

    completeness = report.get("analysis_completeness")
    if not isinstance(completeness, Mapping):
        raise SkillSpectorGuardError(
            f"SkillSpector report has no analysis_completeness; inspect {report_path}"
        )
    exceptions = completeness.get("ledger_exceptions")
    reference_missing_only = (
        isinstance(exceptions, list)
        and bool(exceptions)
        and not completeness.get("limitations")
        and int(completeness.get("entirely_uninspected_files", 0) or 0) == 0
        and int(completeness.get("partially_inspected_files", 0) or 0) == 0
        and all(
            isinstance(item, Mapping) and item.get("reason_code") == "reference_missing"
            for item in exceptions
        )
    )
    if (
        completeness.get("is_complete") is not True
        or completeness.get("status") != "complete"
    ) and not reference_missing_only:
        raise SkillSpectorGuardError(
            "SkillSpector analysis is incomplete "
            f"({_completeness_diagnostic(completeness)}); inspect {report_path}"
        )
    if completeness.get("execution_successful") is False:
        raise SkillSpectorGuardError(
            f"SkillSpector completeness reports execution failure; inspect {report_path}"
        )

    metadata = report.get("metadata")
    if not isinstance(metadata, Mapping):
        raise SkillSpectorGuardError(f"SkillSpector report has no metadata; inspect {report_path}")
    if metadata.get("llm_requested") not in {False, None}:
        raise SkillSpectorGuardError(
            f"SkillSpector unexpectedly requested LLM analysis; inspect {report_path}"
        )
    if int(metadata.get("llm_calls_attempted", 0) or 0) != 0:
        raise SkillSpectorGuardError(
            f"SkillSpector unexpectedly attempted LLM analysis; inspect {report_path}"
        )

    risk = report.get("risk_assessment")
    if not isinstance(risk, Mapping):
        raise SkillSpectorGuardError(
            f"SkillSpector report has no risk_assessment; inspect {report_path}"
        )
    recommendation = str(risk.get("recommendation") or "").upper()
    severity = str(risk.get("severity") or "").upper()
    score = risk.get("score", 0)
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise SkillSpectorGuardError(f"SkillSpector risk score is invalid; inspect {report_path}")
    if recommendation not in {"SAFE", "CAUTION", "DO_NOT_INSTALL"}:
        raise SkillSpectorGuardError(
            f"SkillSpector recommendation is invalid; inspect {report_path}"
        )
    if severity not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
        raise SkillSpectorGuardError(f"SkillSpector severity is invalid; inspect {report_path}")

    skill = report.get("skill")
    skill_name = "unknown"
    if isinstance(skill, Mapping) and isinstance(skill.get("name"), str):
        skill_name = str(skill["name"])

    if recommendation == "DO_NOT_INSTALL" or severity in {"HIGH", "CRITICAL"}:
        raise SkillSpectorGuardError(
            f"SkillSpector blocked {skill_name}: {severity}/{recommendation}; inspect {report_path}"
        )
    return ScanVerdict(
        skill=skill_name,
        recommendation=recommendation,
        severity=severity,
        score=score,
        report_path=report_path,
        warning=(
            recommendation == "CAUTION"
            or severity == "MEDIUM"
            or reference_missing_only
        ),
    )


def scan_skill(
    skill_dir: Path,
    *,
    output_root: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    uvx: str | None = None,
    env: Mapping[str, str] | None = None,
) -> ScanVerdict:
    resolved_uvx = uvx or shutil.which("uvx")
    if not resolved_uvx:
        raise SkillSpectorGuardError("uvx is required for the SkillSpector gate")
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / f"{skill_dir.resolve().name}.json"
    command = build_command(skill_dir, report_path, uvx=resolved_uvx)
    completed = runner(
        command,
        check=False,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=_safe_env(env),
    )
    if completed.returncode not in {0, 1}:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise SkillSpectorGuardError(
            f"SkillSpector tool error ({completed.returncode}): {detail[:400]}"
        )
    report = _parse_report(report_path)
    verdict = _validate_static_report(report, report_path)
    if completed.returncode == 1:
        completeness = report.get("analysis_completeness")
        exceptions = (
            completeness.get("ledger_exceptions")
            if isinstance(completeness, Mapping)
            else None
        )
        reference_missing_only = (
            isinstance(exceptions, list)
            and bool(exceptions)
            and not completeness.get("limitations")
            and int(completeness.get("entirely_uninspected_files", 0) or 0) == 0
            and int(completeness.get("partially_inspected_files", 0) or 0) == 0
            and all(
                isinstance(item, Mapping) and item.get("reason_code") == "reference_missing"
                for item in exceptions
            )
        )
        if not reference_missing_only:
            raise SkillSpectorGuardError(
                f"SkillSpector strict gate failed for {verdict.skill}; inspect {report_path}"
            )
    return verdict


def scan_external_skills(
    skills_root: Path,
    *,
    output_root: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    uvx: str | None = None,
    env: Mapping[str, str] | None = None,
) -> list[ScanVerdict]:
    verdicts: list[ScanVerdict] = []
    for skill_dir in discover_external_skills(skills_root):
        verdicts.append(
            scan_skill(
                skill_dir,
                output_root=output_root,
                runner=runner,
                uvx=uvx,
                env=env,
            )
        )
    return verdicts


def _default_output_root(repo_root: Path) -> Path:
    return repo_root / ".artifacts" / "runtime" / "tests" / "skillspector"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_one = subparsers.add_parser("scan")
    scan_one.add_argument("path", type=Path)
    scan_one.add_argument("--output-root", type=Path)

    scan_all = subparsers.add_parser("scan-all-external")
    scan_all.add_argument("--skills-root", type=Path, default=Path(".agents/skills"))
    scan_all.add_argument("--output-root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    output_root = (args.output_root or _default_output_root(repo_root)).resolve()
    try:
        if args.command == "scan":
            verdicts = [scan_skill(args.path, output_root=output_root)]
        else:
            verdicts = scan_external_skills(
                args.skills_root,
                output_root=output_root,
            )
    except SkillSpectorGuardError as error:
        print(f"SkillSpector gate blocked: {error}", file=sys.stderr)
        return 1

    if not verdicts:
        print("SkillSpector gate: no external skills discovered")
        return 0
    for verdict in verdicts:
        prefix = "CAUTION" if verdict.warning else "PASS"
        print(
            f"SkillSpector {prefix}: {verdict.skill} "
            f"{verdict.severity}/{verdict.recommendation} score={verdict.score} "
            f"report={verdict.report_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
