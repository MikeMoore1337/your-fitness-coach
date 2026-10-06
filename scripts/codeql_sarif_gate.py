from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SECURITY_BLOCK_SCORE = 7.0
BLOCKING_NON_SECURITY_LEVELS = {"error"}

ValidatedFindingKey = tuple[str, str, int]
VALIDATED_NON_EXPLOITABLE_FINDINGS: dict[ValidatedFindingKey, str] = {
    ("js/user-controlled-bypass", "frontend/src/pages/auth/LoginPage.tsx", 195): (
        "The URL-controlled branch only clears the product-analytics login-attempt marker from "
        "memory/sessionStorage. Authentication state, tokens, cookies, roles and authorization "
        "checks are not changed by this function."
    ),
    **{
        ("py/overly-permissive-file", "scripts/allure_report_origin.py", line): (
            "Allure report storage deliberately uses group-only 0640/0750 permissions so the "
            "dedicated publisher and read-only origin can share reports; world access is absent."
        )
        for line in (550, 559, 579, 606, 624, 625, 638, 650, 675, 728, 738, 799, 803, 850)
    },
    ("py/overly-permissive-file", "scripts/hermes_colocation.py", 89): (
        "Hermes installer writes immutable runtime artifacts with explicit caller-selected modes; "
        "the only secret worker.env is installed as 0600."
    ),
    ("py/overly-permissive-file", "scripts/hermes_colocation.py", 101): (
        "Hermes release directories are root-owned and intentionally traversable for the isolated "
        "runtime identity; secrets remain owner-only."
    ),
    ("py/overly-permissive-file", "scripts/hermes_colocation.py", 389): (
        "Root-owned systemd/runtime text artifacts are intentionally readable by their runtime "
        "consumer and contain no credentials."
    ),
    ("py/overly-permissive-file", "tests/test_zero_downtime_deploy.py", 110): (
        "Test fixture preserves and verifies the production 0640 environment-file contract; it "
        "does not create a production credential file."
    ),
}


def _sarif_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    if path.is_dir():
        yield from sorted(path.rglob("*.sarif"))
        return
    raise FileNotFoundError(path)


def _rules_by_id(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tool = run.get("tool", {})
    components = [tool.get("driver", {}), *tool.get("extensions", [])]
    rules: dict[str, dict[str, Any]] = {}
    for component in components:
        for rule in component.get("rules", []) or []:
            rule_id = rule.get("id")
            if isinstance(rule_id, str) and rule_id:
                rules[rule_id] = rule
    return rules


def _security_score(rule: dict[str, Any]) -> float | None:
    raw = rule.get("properties", {}).get("security-severity")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):  # fmt: skip
        return None


def _result_level(result: dict[str, Any], rule: dict[str, Any]) -> str:
    level = result.get("level")
    if isinstance(level, str) and level:
        return level.lower()
    default_level = rule.get("defaultConfiguration", {}).get("level")
    if isinstance(default_level, str) and default_level:
        return default_level.lower()
    return ""


def _location(result: dict[str, Any]) -> tuple[str, int | None]:
    locations = result.get("locations", []) or []
    if not locations:
        return "<unknown>", None
    physical = locations[0].get("physicalLocation", {})
    path = physical.get("artifactLocation", {}).get("uri") or "<unknown>"
    line = physical.get("region", {}).get("startLine")
    return str(path), line if isinstance(line, int) else None


def findings(document: dict[str, Any]) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for run in document.get("runs", []) or []:
        rules = _rules_by_id(run)
        for result in run.get("results", []) or []:
            if result.get("suppressions"):
                continue
            rule_id = result.get("ruleId")
            if not isinstance(rule_id, str) or not rule_id:
                rule_id = result.get("rule", {}).get("id")
            if not isinstance(rule_id, str) or not rule_id:
                rule_id = "<unknown>"
            rule = rules.get(rule_id, {})
            score = _security_score(rule)
            level = _result_level(result, rule)
            path, line = _location(result)
            validated_reason = (
                VALIDATED_NON_EXPLOITABLE_FINDINGS.get((rule_id, path, line))
                if line is not None
                else None
            )
            severity_blocks = (score is not None and score >= SECURITY_BLOCK_SCORE) or (
                score is None and level in BLOCKING_NON_SECURITY_LEVELS
            )
            collected.append(
                {
                    "rule_id": rule_id,
                    "security_score": score,
                    "level": level or "<none>",
                    "path": path,
                    "line": line,
                    "blocking": severity_blocks and validated_reason is None,
                    "validated_reason": validated_reason,
                }
            )
    return collected


def evaluate(path: Path) -> list[dict[str, Any]]:
    files = list(_sarif_files(path))
    if not files:
        raise ValueError(f"No SARIF files found under {path}")
    collected: list[dict[str, Any]] = []
    for sarif_file in files:
        document = json.loads(sarif_file.read_text(encoding="utf-8"))
        collected.extend(findings(document))
    return collected


def _format_finding(finding: dict[str, Any]) -> str:
    line = finding["line"] if finding["line"] is not None else "?"
    score = finding["security_score"]
    score_text = f"{score:.1f}" if isinstance(score, float) else "-"
    return (
        f"rule={finding['rule_id']} "
        f"security_severity={score_text} "
        f"level={finding['level']} "
        f"path={finding['path']}:{line}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Report CodeQL SARIF findings and fail on security severity >= 7.0 "
            "or a non-security error."
        )
    )
    parser.add_argument("sarif_path", type=Path)
    args = parser.parse_args()

    try:
        collected = evaluate(args.sarif_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"CODEQL_SARIF_GATE=ERROR: {exc}")
        return 2

    print(f"CODEQL_SARIF_FINDINGS={len(collected)}")
    for finding in collected:
        if finding["validated_reason"]:
            disposition = "VALIDATED_NON_BLOCKING"
        else:
            disposition = "BLOCKING" if finding["blocking"] else "NON_BLOCKING"
        print(f"{disposition} {_format_finding(finding)}")
        if finding["validated_reason"]:
            print(f"VALIDATION_REASON {finding['validated_reason']}")

    blocking = [finding for finding in collected if finding["blocking"]]
    if not blocking:
        print("CODEQL_SARIF_GATE=PASS")
        return 0

    print(f"CODEQL_SARIF_GATE=BLOCKED count={len(blocking)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
