import json
from pathlib import Path

from scripts.security_review_gate import evaluate_result


def _payload(*, severity: str | None = None) -> dict[str, object]:
    findings: list[dict[str, str]] = []
    if severity is not None:
        findings.append(
            {
                "severity": severity,
                "title": "Cross-user write",
                "affected_boundary": "FastAPI -> PostgreSQL",
                "attack_path": "Authenticated user changes another user's object.",
                "evidence": "Ownership filter is absent in the validated update path.",
                "impact": "Cross-user data modification.",
                "remediation": "Enforce owner scope server-side.",
                "regression_verification": "Add negative API authorization coverage.",
            }
        )
    return {
        "status": "CONFIRMED_FINDINGS" if findings else "NO_CONFIRMED_FINDINGS",
        "security_relevance": "RELEVANT" if findings else "NONE",
        "summary": "Review completed.",
        "threat_model_delta": "",
        "inspected_surfaces": ["backend API"],
        "limitations": [],
        "confirmed_findings": findings,
        "unvalidated_concerns": [],
        "residual_risk": "",
    }


def _write(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "result.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_no_findings_passes_gate(tmp_path: Path) -> None:
    decision = evaluate_result(
        _write(tmp_path, _payload()),
        base_sha="a" * 40,
        head_sha="b" * 40,
        codex_outcome="success",
        credential_available=True,
    )

    assert decision.status == "NO_CONFIRMED_FINDINGS"
    assert decision.blocking is False
    assert decision.confirmed_count == 0


def test_medium_finding_is_advisory(tmp_path: Path) -> None:
    decision = evaluate_result(
        _write(tmp_path, _payload(severity="MEDIUM")),
        base_sha="a" * 40,
        head_sha="b" * 40,
        codex_outcome="success",
        credential_available=True,
    )

    assert decision.status == "CONFIRMED_FINDINGS"
    assert decision.blocking is False
    assert "MEDIUM" in decision.comment


def test_high_finding_blocks_gate(tmp_path: Path) -> None:
    decision = evaluate_result(
        _write(tmp_path, _payload(severity="HIGH")),
        base_sha="a" * 40,
        head_sha="b" * 40,
        codex_outcome="success",
        credential_available=True,
    )

    assert decision.blocking is True
    assert decision.confirmed_count == 1
    assert "**Gate:** BLOCK" in decision.comment


def test_missing_credential_fails_closed(tmp_path: Path) -> None:
    decision = evaluate_result(
        tmp_path / "missing.json",
        base_sha="a" * 40,
        head_sha="b" * 40,
        codex_outcome="skipped",
        credential_available=False,
    )

    assert decision.status == "REVIEW_FAILED"
    assert decision.blocking is True
    assert "OPENAI_API_KEY" in decision.comment


def test_malformed_result_fails_closed(tmp_path: Path) -> None:
    path = _write(tmp_path, {"status": "NO_CONFIRMED_FINDINGS"})
    decision = evaluate_result(
        path,
        base_sha="a" * 40,
        head_sha="b" * 40,
        codex_outcome="success",
        credential_available=True,
    )

    assert decision.status == "REVIEW_FAILED"
    assert decision.blocking is True
    assert "invalid" in decision.comment.lower()
