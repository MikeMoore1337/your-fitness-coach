"""Регрессии bounded final-review и resource-efficient delivery policy."""

import json
from pathlib import Path

from scripts import task_session

ROOT = Path(__file__).parents[1]


def test_agent_manifest_has_no_standalone_code_reviewer() -> None:
    manifest = json.loads((ROOT / ".agents/MANIFEST.json").read_text(encoding="utf-8"))
    assert "independent-reviewer" not in manifest["roles"]
    assert "code-reviewer" not in manifest["skills"]
    assert manifest["role_count"] == len(manifest["roles"])
    assert manifest["skill_count"] == len(manifest["skills"])
    assert not (ROOT / ".agents/roles/independent-reviewer.md").exists()


def test_delivery_scripts_expose_only_bounded_codex_review_contract() -> None:
    controller = (ROOT / "scripts" / "task_session.py").read_text(encoding="utf-8")
    launcher = (ROOT / "scripts" / "run_task_delivery.py").read_text(encoding="utf-8")

    assert "request-codex-review" in controller
    assert "validate-codex-review" in controller
    assert "CODEX_REVIEW_MAX_ROUNDS = 2" in controller
    assert "CODEX_REVIEW_REQUEST_MARKER" in controller
    assert "HUMAN_REQUIRED" in controller
    assert "@codex review" in controller
    assert "request-codex-review --pr <N>" in launcher
    assert "--round 2" in launcher
    assert "третья проверка запрещена" in launcher
    for name in ("task_session.py", "run_task_delivery.py"):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8").lower()
        assert "--review-verdict" not in source, name
        assert "fresh connector review" not in source, name
        assert "review_rate_limit" not in source, name
        assert "reviewer-agent" not in source, name


def test_canonical_policy_preserves_deterministic_and_explicit_gates() -> None:
    for name in (
        "AGENTS.md",
        "codex-backlog/GLOBAL_RULES.md",
        "codex-backlog/TASK_EXECUTION_LIFECYCLE.md",
    ):
        source = (ROOT / name).read_text(encoding="utf-8")
        for requirement in (
            "bounded",
            "exact-head",
            "`checks`",
            "P0/P1",
            "human",
            "external",
            "non-fast-forward protection",
            "thread resolution",
        ):
            assert requirement in source, (name, requirement)
        assert "Codex Code Review отключён" not in source, name


def test_quality_gate_cli_does_not_make_qa_a_universal_stage() -> None:
    args = task_session._parser().parse_args(
        ["mark-ready", "229", "--head-sha", "exact-sha", "--quality-verdict", "PASS"]
    )
    assert args.quality_verdict == "PASS"
    assert args.qa_verdict == "NOT_REQUIRED"
