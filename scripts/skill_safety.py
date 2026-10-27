"""Deterministic offline safety scan for repository agent skills."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
SOURCE_SCHEMA_VERSION = 1
CRITICAL = "CRITICAL"
WARNING = "WARNING"

_NEGATION_PREFIXES = (
    "do not ",
    "don't ",
    "never ",
    "avoid ",
    "must not ",
    "не ",
    "никогда ",
    "запрещ",
)

_INSTRUCTION_BYPASS = re.compile(
    r"(?is)\b(?:ignore|disregard|override|bypass)\b.{0,100}"
    r"\b(?:previous|system|developer|repository|higher[- ]priority|project)\b.{0,80}"
    r"\b(?:instructions?|rules?|prompts?|polic(?:y|ies))\b"
)
_SECRET_READ = re.compile(
    r"(?i)(?:cat|type|get-content|read_file|open)\s+[^\n]{0,100}"
    r"(?:\.env\b|\.ssh[/\\]|\.aws[/\\]credentials|auth\.json\b|credentials\.json\b)"
)
_SECRET_EXFIL = re.compile(
    r"(?i)(?:curl|wget|invoke-webrequest|irm|httpx\.(?:post|put)|requests\.(?:post|put))"
    r"[^\n]{0,220}(?:\$[A-Z0-9_]*(?:TOKEN|KEY|SECRET|PASSWORD)|"
    r"%[A-Z0-9_]*(?:TOKEN|KEY|SECRET|PASSWORD)%|\.env\b|auth\.json\b)"
)
_DANGEROUS_PIPE = re.compile(
    r"(?i)(?:curl|wget|irm|invoke-restmethod|invoke-webrequest)[^\n|]{0,300}\|\s*"
    r"(?:sh|bash|zsh|iex|invoke-expression)\b"
)
_DESTRUCTIVE = re.compile(
    r"(?i)(?:\brm\s+-[^\n]*r[^\n]*f[^\n]*\s+(?:/|~|\$HOME)\b|"
    r"\bgit\s+reset\s+--hard\b|\bgit\s+clean\s+-[^\n]*f[^\n]*d|"
    r"\bremove-item\b[^\n]*-(?:recurse|r)\b[^\n]*-(?:force|f)\b|"
    r"\bformat\s+[a-z]:|\bmkfs(?:\.|\s)|\bdd\s+if=.*\sof=/dev/)"
)
_PERSISTENCE = re.compile(
    r"(?i)(?:\.git[/\\]hooks[/\\]|crontab\s+-|systemctl\s+enable|"
    r"/etc/(?:cron|systemd)|(?:appdata|programdata)[^\n]{0,120}startup[/\\]|schtasks\s+/create|"
    r"(?:>>|tee\s+-?a?)\s*(?:~[/\\])?\.(?:bashrc|zshrc|profile))"
)
_NETWORK_OR_INSTALL = re.compile(
    r"(?i)\b(?:curl|wget|irm|invoke-webrequest|pip\s+install|uv\s+(?:add|tool\s+install)|"
    r"npm\s+(?:install|i)\b|npx\s+|pnpm\s+(?:add|dlx)\b|yarn\s+add\b)"
)
_PRIVILEGED = re.compile(r"(?i)(?:^|\s)(?:sudo\s+|runas\s+|set-executionpolicy\b)")
_HOST_CONFIG = re.compile(
    r"(?i)(?:~[/\\]\.(?:config|codex|claude|ssh|aws)|%APPDATA%|"
    r"\$HOME[/\\]\.(?:config|codex|claude|ssh|aws)|/etc/)"
)
_SHELL_FENCE = re.compile(r"(?im)^\s*```(?:bash|sh|shell|powershell|pwsh|cmd)\s*$")


class SkillSafetyError(RuntimeError):
    """The skill safety scan cannot be evaluated safely."""


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def _hash_excerpt(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _finding(
    *,
    severity: str,
    code: str,
    path: Path,
    text: str,
    match: re.Match[str],
) -> dict[str, Any]:
    excerpt = match.group(0)
    return {
        "severity": severity,
        "code": code,
        "path": path.as_posix(),
        "line": _line_number(text, match.start()),
        "evidence_hash": _hash_excerpt(excerpt),
    }


def _line_is_negated(text: str, offset: int) -> bool:
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    if end < 0:
        end = len(text)
    line = text[start:end].strip().lower().lstrip("-*").strip()
    return any(line.startswith(prefix) for prefix in _NEGATION_PREFIXES)


def _scan_pattern(
    findings: list[dict[str, Any]],
    *,
    severity: str,
    code: str,
    path: Path,
    text: str,
    pattern: re.Pattern[str],
    allow_negated: bool = True,
) -> None:
    for match in pattern.finditer(text):
        if allow_negated and _line_is_negated(text, match.start()):
            continue
        findings.append(
            _finding(
                severity=severity,
                code=code,
                path=path,
                text=text,
                match=match,
            )
        )


def _load_source_manifest(skill_dir: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    source_path = skill_dir / "SOURCE.json"
    if not source_path.exists():
        return None, []
    try:
        raw = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, [
            {
                "severity": CRITICAL,
                "code": "INVALID_EXTERNAL_SKILL_SOURCE_MANIFEST",
                "path": source_path.as_posix(),
                "line": 1,
                "evidence_hash": _hash_excerpt(str(error)),
            }
        ]
    if not isinstance(raw, dict):
        return None, [
            {
                "severity": CRITICAL,
                "code": "INVALID_EXTERNAL_SKILL_SOURCE_MANIFEST",
                "path": source_path.as_posix(),
                "line": 1,
                "evidence_hash": _hash_excerpt("not-an-object"),
            }
        ]

    required = {
        "schema_version": int,
        "classification": str,
        "source_url": str,
        "source_repository": str,
        "source_commit": str,
        "license": str,
        "license_file": str,
    }
    problems: list[str] = []
    for key, expected in required.items():
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, expected):
            problems.append(key)
    if raw.get("schema_version") != SOURCE_SCHEMA_VERSION:
        problems.append("schema_version")
    if raw.get("classification") != "external-skill-source":
        problems.append("classification")
    source_url = raw.get("source_url")
    source_repo = raw.get("source_repository")
    source_commit = raw.get("source_commit")
    if isinstance(source_url, str) and not source_url.startswith("https://"):
        problems.append("source_url")
    if isinstance(source_repo, str) and not source_repo.startswith("https://"):
        problems.append("source_repository")
    if isinstance(source_commit, str) and re.fullmatch(r"[0-9a-fA-F]{40}", source_commit) is None:
        problems.append("source_commit")
    license_file = raw.get("license_file")
    if isinstance(license_file, str):
        candidate = skill_dir / license_file
        if not candidate.is_file():
            problems.append("license_file")

    if problems:
        detail = ",".join(sorted(set(problems)))
        return raw, [
            {
                "severity": CRITICAL,
                "code": "INVALID_EXTERNAL_SKILL_PROVENANCE",
                "path": source_path.as_posix(),
                "line": 1,
                "evidence_hash": _hash_excerpt(detail),
            }
        ]
    return raw, []


def scan_skill(skill_path: Path) -> dict[str, Any]:
    skill_path = skill_path.resolve()
    if skill_path.is_dir():
        skill_file = skill_path / "SKILL.md"
        skill_dir = skill_path
    else:
        skill_file = skill_path
        skill_dir = skill_path.parent
    if not skill_file.is_file():
        raise SkillSafetyError(f"Skill file not found: {skill_file}")

    try:
        text = skill_file.read_text(encoding="utf-8")
    except OSError as error:
        raise SkillSafetyError(f"Cannot read skill file {skill_file}: {error}") from error

    findings: list[dict[str, Any]] = []
    source_manifest, source_findings = _load_source_manifest(skill_dir)
    findings.extend(source_findings)

    _scan_pattern(
        findings,
        severity=CRITICAL,
        code="INSTRUCTION_PRECEDENCE_BYPASS",
        path=skill_file,
        text=text,
        pattern=_INSTRUCTION_BYPASS,
        allow_negated=False,
    )
    _scan_pattern(
        findings,
        severity=CRITICAL,
        code="SENSITIVE_CREDENTIAL_READ",
        path=skill_file,
        text=text,
        pattern=_SECRET_READ,
    )
    _scan_pattern(
        findings,
        severity=CRITICAL,
        code="CREDENTIAL_NETWORK_EXFILTRATION",
        path=skill_file,
        text=text,
        pattern=_SECRET_EXFIL,
    )
    _scan_pattern(
        findings,
        severity=CRITICAL,
        code="NETWORK_TO_SHELL_PIPE",
        path=skill_file,
        text=text,
        pattern=_DANGEROUS_PIPE,
    )
    _scan_pattern(
        findings,
        severity=CRITICAL,
        code="DESTRUCTIVE_HOST_COMMAND",
        path=skill_file,
        text=text,
        pattern=_DESTRUCTIVE,
    )
    _scan_pattern(
        findings,
        severity=CRITICAL,
        code="UNSAFE_PERSISTENCE_OR_HOOK",
        path=skill_file,
        text=text,
        pattern=_PERSISTENCE,
    )

    _scan_pattern(
        findings,
        severity=WARNING,
        code="NETWORK_OR_PACKAGE_INSTALL",
        path=skill_file,
        text=text,
        pattern=_NETWORK_OR_INSTALL,
    )
    _scan_pattern(
        findings,
        severity=WARNING,
        code="PRIVILEGED_COMMAND",
        path=skill_file,
        text=text,
        pattern=_PRIVILEGED,
    )
    _scan_pattern(
        findings,
        severity=WARNING,
        code="HOST_CONFIG_PATH",
        path=skill_file,
        text=text,
        pattern=_HOST_CONFIG,
    )
    _scan_pattern(
        findings,
        severity=WARNING,
        code="SHELL_INSTRUCTIONS",
        path=skill_file,
        text=text,
        pattern=_SHELL_FENCE,
        allow_negated=False,
    )

    relative_name = skill_dir.name
    return {
        "schema_version": SCHEMA_VERSION,
        "classification": "yfc-skill-safety-result",
        "skill": relative_name,
        "path": skill_file.as_posix(),
        "external": source_manifest is not None,
        "provenance": (
            {
                "source_url": source_manifest["source_url"],
                "source_repository": source_manifest["source_repository"],
                "source_commit": source_manifest["source_commit"],
                "license": source_manifest["license"],
                "license_file": source_manifest["license_file"],
            }
            if source_manifest is not None and not source_findings
            else None
        ),
        "findings": sorted(
            findings,
            key=lambda item: (
                0 if item["severity"] == CRITICAL else 1,
                str(item["path"]),
                int(item["line"]),
                str(item["code"]),
            ),
        ),
    }


def scan_repository_skills(skills_root: Path) -> dict[str, Any]:
    root = skills_root.resolve()
    if not root.is_dir():
        raise SkillSafetyError(f"Skills root not found: {root}")
    results = [scan_skill(path) for path in sorted(root.glob("*/SKILL.md"))]
    critical = sum(
        1 for result in results for finding in result["findings"] if finding["severity"] == CRITICAL
    )
    warnings = sum(
        1 for result in results for finding in result["findings"] if finding["severity"] == WARNING
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "classification": "yfc-skill-safety-report",
        "skills_root": root.as_posix(),
        "skills_scanned": len(results),
        "external_skills": sum(1 for result in results if result["external"]),
        "critical_findings": critical,
        "warning_findings": warnings,
        "blocked": critical > 0,
        "results": results,
        "policy": {
            "network_calls_performed": False,
            "llm_calls_performed": False,
            "critical_blocks_delivery": True,
            "warnings_block_delivery": False,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan_all = subparsers.add_parser("scan-all")
    scan_all.add_argument("--root", type=Path, default=Path(".agents/skills"))
    scan_one = subparsers.add_parser("scan")
    scan_one.add_argument("path", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "scan-all":
            report = scan_repository_skills(args.root)
        else:
            result = scan_skill(args.path)
            critical = sum(1 for finding in result["findings"] if finding["severity"] == CRITICAL)
            warnings = sum(1 for finding in result["findings"] if finding["severity"] == WARNING)
            report = {
                "schema_version": SCHEMA_VERSION,
                "classification": "yfc-skill-safety-report",
                "skills_scanned": 1,
                "external_skills": int(result["external"]),
                "critical_findings": critical,
                "warning_findings": warnings,
                "blocked": critical > 0,
                "results": [result],
                "policy": {
                    "network_calls_performed": False,
                    "llm_calls_performed": False,
                    "critical_blocks_delivery": True,
                    "warnings_block_delivery": False,
                },
            }
    except SkillSafetyError as error:
        print(str(error), file=sys.stderr)
        return 2

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if report["blocked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
