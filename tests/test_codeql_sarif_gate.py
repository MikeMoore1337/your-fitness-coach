import json
from pathlib import Path

from scripts import codeql_sarif_gate


def _sarif(
    *,
    security_severity: str | None,
    level: str,
    suppressed: bool = False,
    rule_id: str = "test/rule",
    path: str = "src/example.py",
    line: int = 17,
) -> dict:
    properties = {}
    if security_severity is not None:
        properties["security-severity"] = security_severity
    result = {
        "ruleId": rule_id,
        "level": level,
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": path},
                    "region": {"startLine": line},
                }
            }
        ],
    }
    if suppressed:
        result["suppressions"] = [{"kind": "inSource"}]
    return {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "CodeQL",
                        "rules": [
                            {
                                "id": rule_id,
                                "properties": properties,
                            }
                        ],
                    }
                },
                "results": [result],
            }
        ],
    }


def _write(tmp_path: Path, document: dict) -> Path:
    path = tmp_path / "result.sarif"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_high_security_finding_blocks(tmp_path: Path) -> None:
    path = _write(tmp_path, _sarif(security_severity="7.8", level="error"))

    assert codeql_sarif_gate.evaluate(path) == [
        {
            "rule_id": "test/rule",
            "security_score": 7.8,
            "level": "error",
            "path": "src/example.py",
            "line": 17,
            "blocking": True,
            "validated_reason": None,
        }
    ]


def test_medium_security_finding_is_reported_but_does_not_block(tmp_path: Path) -> None:
    path = _write(tmp_path, _sarif(security_severity="6.1", level="error"))

    result = codeql_sarif_gate.evaluate(path)

    assert len(result) == 1
    assert result[0]["blocking"] is False


def test_non_security_error_blocks(tmp_path: Path) -> None:
    path = _write(tmp_path, _sarif(security_severity=None, level="error"))

    assert codeql_sarif_gate.evaluate(path)[0]["blocking"] is True


def test_non_security_warning_does_not_block(tmp_path: Path) -> None:
    path = _write(tmp_path, _sarif(security_severity=None, level="warning"))

    assert codeql_sarif_gate.evaluate(path)[0]["blocking"] is False


def test_suppressed_high_security_finding_is_not_reported(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        _sarif(security_severity="9.8", level="error", suppressed=True),
    )

    assert codeql_sarif_gate.evaluate(path) == []


def test_exact_validated_baseline_finding_is_reported_but_does_not_block(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        _sarif(
            security_severity="7.8",
            level="warning",
            rule_id="py/overly-permissive-file",
            path="scripts/allure_report_origin.py",
            line=550,
        ),
    )

    result = codeql_sarif_gate.evaluate(path)

    assert len(result) == 1
    assert result[0]["blocking"] is False
    assert result[0]["validated_reason"]


def test_analytics_only_login_error_baseline_is_exact(tmp_path: Path) -> None:
    exact = _write(
        tmp_path,
        _sarif(
            security_severity="7.8",
            level="error",
            rule_id="js/user-controlled-bypass",
            path="frontend/src/pages/auth/LoginPage.tsx",
            line=195,
        ),
    )
    exact_result = codeql_sarif_gate.evaluate(exact)

    assert len(exact_result) == 1
    assert exact_result[0]["blocking"] is False
    assert exact_result[0]["validated_reason"]

    shifted = _write(
        tmp_path,
        _sarif(
            security_severity="7.8",
            level="error",
            rule_id="js/user-controlled-bypass",
            path="frontend/src/pages/auth/LoginPage.tsx",
            line=196,
        ),
    )
    shifted_result = codeql_sarif_gate.evaluate(shifted)

    assert len(shifted_result) == 1
    assert shifted_result[0]["blocking"] is True
    assert shifted_result[0]["validated_reason"] is None


def test_validated_baseline_does_not_hide_same_rule_on_a_new_line(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        _sarif(
            security_severity="7.8",
            level="warning",
            rule_id="py/overly-permissive-file",
            path="scripts/allure_report_origin.py",
            line=551,
        ),
    )

    result = codeql_sarif_gate.evaluate(path)

    assert len(result) == 1
    assert result[0]["blocking"] is True
    assert result[0]["validated_reason"] is None


def test_backup_group_read_triage_is_exact_and_keeps_other_findings_blocking(
    tmp_path: Path,
) -> None:
    for rule, path, line, blocked in (
        ("py/overly-permissive-file", "scripts/backup_manifest.py", 187, False),
        ("py/overly-permissive-file", "scripts/backup_manifest.py", 188, True),
        ("py/overly-permissive-file", "scripts/unrelated.py", 187, True),
        ("test/other-security-rule", "scripts/backup_manifest.py", 187, True),
    ):
        document = _sarif(
            security_severity="7.8", level="warning", rule_id=rule, path=path, line=line
        )
        result = codeql_sarif_gate.evaluate(_write(tmp_path, document))
        assert len(result) == 1
        assert result[0]["blocking"] is blocked
        assert bool(result[0]["validated_reason"]) is not blocked


def test_polling_heartbeat_group_only_read_exception_is_exact(tmp_path: Path) -> None:
    """A single explicitly approved 0640 line; no new general bypass."""
    status_path = "bot/fitminiapp_bot/polling_health.py"
    for path, line, rule, blocked in (
        (status_path, 71, "py/overly-permissive-file", False),
        (status_path, 72, "py/overly-permissive-file", True),
        ("bot/fitminiapp_bot/other.py", 71, "py/overly-permissive-file", True),
        (status_path, 71, "py/path-injection", True),
    ):
        evidence = _sarif(
            security_severity="7.8", level="warning",
            rule_id=rule, path=path, line=line,
        )
        found = codeql_sarif_gate.evaluate(_write(tmp_path, evidence))
        assert len(found) == 1
        assert found[0]["blocking"] is blocked
        assert bool(found[0]["validated_reason"]) is not blocked
