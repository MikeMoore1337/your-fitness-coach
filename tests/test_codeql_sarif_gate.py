import json
from pathlib import Path

from scripts import codeql_sarif_gate


def _sarif(
    *,
    security_severity: str | None,
    level: str,
    suppressed: bool = False,
) -> dict:
    properties = {}
    if security_severity is not None:
        properties["security-severity"] = security_severity
    result = {
        "ruleId": "test/rule",
        "level": level,
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": "src/example.py"},
                    "region": {"startLine": 17},
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
                                "id": "test/rule",
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
        }
    ]


def test_medium_security_finding_is_reported_but_does_not_block(
    tmp_path: Path,
) -> None:
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
