"""Регрессии постоянной политики без отдельного LLM code review."""

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


def test_delivery_scripts_cannot_request_or_wait_for_codex_review() -> None:
    for name in ("task_session.py", "run_task_delivery.py"):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8").lower()
        for forbidden in (
            "@codex review",
            "chatgpt-codex-connector",
            "--review-verdict",
            "fresh connector review",
            "review_rate_limit",
        ):
            assert forbidden not in source, (name, forbidden)


def test_canonical_policy_preserves_deterministic_and_explicit_gates() -> None:
    for name in (
        "AGENTS.md",
        "codex-backlog/GLOBAL_RULES.md",
        "codex-backlog/TASK_EXECUTION_LIFECYCLE.md",
    ):
        source = (ROOT / name).read_text(encoding="utf-8")
        for requirement in (
            "Codex Code Review отключён",
            "exact-head CI GREEN",
            "`checks` GREEN",
            "BLOCKER/HIGH",
            "human/external gates",
            "non-fast-forward protection",
            "thread resolution",
        ):
            assert requirement in source, (name, requirement)


def test_quality_gate_cli_does_not_make_qa_a_universal_stage() -> None:
    args = task_session._parser().parse_args(
        ["mark-ready", "229", "--head-sha", "exact-sha", "--quality-verdict", "PASS"]
    )
    assert args.quality_verdict == "PASS"
    assert args.qa_verdict == "NOT_REQUIRED"
