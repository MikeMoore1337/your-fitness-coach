"""Evaluate structured repository-native Codex Security Review output."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

MARKER = "<!-- yfc-repository-security-review -->"
ALLOWED_STATUSES = {
    "NO_CONFIRMED_FINDINGS",
    "CONFIRMED_FINDINGS",
    "NEEDS_MANUAL_VALIDATION",
}
ALLOWED_RELEVANCE = {"NONE", "LOW", "RELEVANT"}
ALLOWED_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
BLOCKING_SEVERITIES = {"CRITICAL", "HIGH"}


@dataclass(frozen=True)
class GateDecision:
    status: str
    blocking: bool
    confirmed_count: int
    comment: str


def _require_string(mapping: dict[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _require_list(mapping: dict[str, object], key: str) -> list[object]:
    value = mapping.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _validated_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("review result must be a JSON object")

    status = _require_string(payload, "status")
    relevance = _require_string(payload, "security_relevance")
    _require_string(payload, "summary")
    _require_string(payload, "threat_model_delta")
    _require_string(payload, "residual_risk")
    surfaces = _require_list(payload, "inspected_surfaces")
    limitations = _require_list(payload, "limitations")
    findings = _require_list(payload, "confirmed_findings")
    concerns = _require_list(payload, "unvalidated_concerns")

    if status not in ALLOWED_STATUSES:
        raise ValueError(f"unsupported status: {status}")
    if relevance not in ALLOWED_RELEVANCE:
        raise ValueError(f"unsupported security_relevance: {relevance}")
    if not all(isinstance(item, str) and item for item in (*surfaces, *limitations)):
        raise ValueError("inspected_surfaces and limitations must contain strings")

    for finding in findings:
        if not isinstance(finding, dict):
            raise ValueError("confirmed_findings entries must be objects")
        severity = _require_string(finding, "severity")
        if severity not in ALLOWED_SEVERITIES:
            raise ValueError(f"unsupported finding severity: {severity}")
        for key in (
            "title",
            "affected_boundary",
            "attack_path",
            "evidence",
            "impact",
            "remediation",
            "regression_verification",
        ):
            if not _require_string(finding, key):
                raise ValueError(f"{key} must not be empty")

    for concern in concerns:
        if not isinstance(concern, dict):
            raise ValueError("unvalidated_concerns entries must be objects")
        if not _require_string(concern, "title") or not _require_string(concern, "reason"):
            raise ValueError("concern title/reason must not be empty")

    if status == "NO_CONFIRMED_FINDINGS" and findings:
        raise ValueError("NO_CONFIRMED_FINDINGS cannot contain confirmed findings")
    if status == "CONFIRMED_FINDINGS" and not findings:
        raise ValueError("CONFIRMED_FINDINGS requires at least one finding")

    return payload


def _short(value: str, limit: int = 1200) -> str:
    compact = value.strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _render_success(
    payload: dict[str, object],
    *,
    base_sha: str,
    head_sha: str,
) -> GateDecision:
    findings = _require_list(payload, "confirmed_findings")
    blocking = any(
        isinstance(item, dict) and item.get("severity") in BLOCKING_SEVERITIES
        for item in findings
    )
    status = _require_string(payload, "status")
    relevance = _require_string(payload, "security_relevance")
    summary = _require_string(payload, "summary")
    surfaces = _require_list(payload, "inspected_surfaces")
    limitations = _require_list(payload, "limitations")
    concerns = _require_list(payload, "unvalidated_concerns")
    residual = _require_string(payload, "residual_risk")

    lines = [
        MARKER,
        "## Repository Security Review",
        "",
        f"**Status:** `{status}`",
        f"**Security relevance:** `{relevance}`",
        f"**Gate:** {'BLOCK' if blocking else 'PASS'}",
        f"**Range:** `{base_sha[:12]}` -> `{head_sha[:12]}`",
        "",
        _short(summary),
    ]

    if findings:
        lines.extend(["", "### Confirmed findings"])
        for raw in findings:
            assert isinstance(raw, dict)
            severity = _require_string(raw, "severity")
            title = _require_string(raw, "title")
            boundary = _require_string(raw, "affected_boundary")
            evidence = _require_string(raw, "evidence")
            lines.extend(
                [
                    "",
                    f"- **{severity} - {_short(title, 300)}**",
                    f"  - Boundary: {_short(boundary, 500)}",
                    f"  - Evidence: {_short(evidence)}",
                ]
            )
    else:
        lines.extend(["", "### Confirmed findings", "", "None."])

    if concerns:
        lines.extend(["", "### Unvalidated concerns"])
        for raw in concerns:
            assert isinstance(raw, dict)
            lines.append(
                f"- **{_short(_require_string(raw, 'title'), 300)}:** "
                f"{_short(_require_string(raw, 'reason'))}"
            )

    if surfaces:
        lines.extend(
            [
                "",
                "### Inspected surfaces",
                *[f"- {_short(str(item), 500)}" for item in surfaces],
            ]
        )

    if limitations:
        lines.extend(
            [
                "",
                "### Limitations",
                *[f"- {_short(str(item), 800)}" for item in limitations],
            ]
        )

    if residual.strip():
        lines.extend(["", "### Residual risk", "", _short(residual)])

    lines.extend(
        [
            "",
            "_Automatic YFC diff review. Only validated CRITICAL/HIGH findings block merge._",
        ]
    )
    return GateDecision(
        status=status,
        blocking=blocking,
        confirmed_count=len(findings),
        comment="\n".join(lines).rstrip() + "\n",
    )


def _render_failure(reason: str, *, base_sha: str, head_sha: str) -> GateDecision:
    comment = "\n".join(
        [
            MARKER,
            "## Repository Security Review",
            "",
            "**Status:** `REVIEW_FAILED`",
            "**Gate:** BLOCK",
            f"**Range:** `{base_sha[:12]}` -> `{head_sha[:12]}`",
            "",
            _short(reason, 1800),
            "",
            "The semantic security gate is fail-closed. Fix the review execution/configuration "
            "and rerun the exact PR head.",
        ]
    ) + "\n"
    return GateDecision(
        status="REVIEW_FAILED",
        blocking=True,
        confirmed_count=0,
        comment=comment,
    )


def evaluate_result(
    result_path: Path,
    *,
    base_sha: str,
    head_sha: str,
    codex_outcome: str,
    credential_available: bool,
) -> GateDecision:
    if not credential_available:
        return _render_failure(
            "GitHub secret OPENAI_API_KEY is unavailable for this PR actor/scope.",
            base_sha=base_sha,
            head_sha=head_sha,
        )
    if codex_outcome != "success":
        return _render_failure(
            f"Codex action did not complete successfully (outcome={codex_outcome or 'unknown'}).",
            base_sha=base_sha,
            head_sha=head_sha,
        )
    if not result_path.is_file():
        return _render_failure(
            "Codex completed without the expected structured result file.",
            base_sha=base_sha,
            head_sha=head_sha,
        )

    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        validated = _validated_payload(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return _render_failure(
            f"Structured Security Review result is invalid: {error}",
            base_sha=base_sha,
            head_sha=head_sha,
        )
    return _render_success(validated, base_sha=base_sha, head_sha=head_sha)


def _write_outputs(path: Path, decision: GateDecision) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(f"blocking={'true' if decision.blocking else 'false'}\n")
        stream.write(f"status={decision.status}\n")
        stream.write(f"confirmed_count={decision.confirmed_count}\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--result", type=Path, required=True)
    evaluate.add_argument("--comment", type=Path, required=True)
    evaluate.add_argument("--github-output", type=Path, required=True)
    evaluate.add_argument("--base-sha", required=True)
    evaluate.add_argument("--head-sha", required=True)
    evaluate.add_argument("--codex-outcome", required=True)
    evaluate.add_argument(
        "--credential-available",
        choices=("true", "false"),
        required=True,
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.command != "evaluate":
        raise AssertionError("unreachable")

    decision = evaluate_result(
        args.result,
        base_sha=args.base_sha,
        head_sha=args.head_sha,
        codex_outcome=args.codex_outcome,
        credential_available=args.credential_available == "true",
    )
    args.comment.parent.mkdir(parents=True, exist_ok=True)
    args.comment.write_text(decision.comment, encoding="utf-8")
    _write_outputs(args.github_output, decision)
    print(
        "SECURITY_REVIEW_GATE "
        f"status={decision.status} blocking={str(decision.blocking).lower()} "
        f"confirmed_count={decision.confirmed_count}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
