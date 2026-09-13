"""Регрессии отключённого Codex Code Review и resource-efficient delivery policy."""

import json
from pathlib import Path

import pytest
from scripts import task_session

ROOT = Path(__file__).parents[1]


def test_agent_manifest_has_no_standalone_code_reviewer() -> None:
    manifest = json.loads((ROOT / ".agents/MANIFEST.json").read_text(encoding="utf-8"))
    assert "independent-reviewer" not in manifest["roles"]
    assert "code-reviewer" not in manifest["skills"]
    assert manifest["role_count"] == len(manifest["roles"])
    assert manifest["skill_count"] == len(manifest["skills"])
    assert not (ROOT / ".agents/roles/independent-reviewer.md").exists()


def test_delivery_scripts_have_no_codex_review_runtime_mechanics() -> None:
    controller = (ROOT / "scripts" / "task_session.py").read_text(encoding="utf-8")
    launcher = (ROOT / "scripts" / "run_task_delivery.py").read_text(encoding="utf-8")

    forbidden_runtime_markers = (
        "request-codex-review",
        "validate-codex-review",
        "yfc-codex-review",
        "codex_review",
        "pull_request_reviews",
        "issue_comments",
        "create_issue_comment",
        "review_threads",
        "chatgpt-codex-connector",
    )
    for name, source in (("task_session.py", controller), ("run_task_delivery.py", launcher)):
        lowered = source.lower()
        for marker in forbidden_runtime_markers:
            assert marker not in lowered, (name, marker)
        assert "--review-verdict" not in lowered, name
        assert "fresh connector review" not in lowered, name
        assert "review_rate_limit" not in lowered, name

    for argv in (
        ["request-codex-review", "--pr", "1", "--head-sha", "a" * 40, "--round", "1"],
        ["validate-codex-review", "--pr", "1", "--head-sha", "a" * 40],
    ):
        with pytest.raises(SystemExit):
            task_session._parser().parse_args(argv)


def test_canonical_policy_preserves_deterministic_and_explicit_gates() -> None:
    for name in (
        "AGENTS.md",
        "codex-backlog/GLOBAL_RULES.md",
        "codex-backlog/TASK_EXECUTION_LIFECYCLE.md",
    ):
        source = (ROOT / name).read_text(encoding="utf-8")
        for requirement in (
            "Codex Code Review",
            "exact-head",
            "`checks`",
            "human",
            "external",
            "non-fast-forward protection",
            "thread resolution",
        ):
            assert requirement in source, (name, requirement)
        assert "Codex Code Review полностью отключён" in source, name
        assert "request-codex-review" not in source
        assert "validate-codex-review" not in source
        assert "Codex review round" not in source


def test_parallel_worktrees_and_serial_delivery_lane_remain_documented() -> None:
    sources = {
        name: (ROOT / name).read_text(encoding="utf-8")
        for name in (
            "scripts/task_session.py",
            "scripts/run_task_delivery.py",
            "docs/task-branch-integration.md",
        )
    }
    for name, source in sources.items():
        assert "independent-write" in source, name
        assert "delivery lane" in source.lower(), name
    assert "параллельно" in sources["docs/task-branch-integration.md"]
    assert "serial" in sources["scripts/run_task_delivery.py"].lower()


def test_security_review_is_separate_conditional_gate() -> None:
    for name in (
        "AGENTS.md",
        "codex-backlog/GLOBAL_RULES.md",
        "codex-backlog/TASK_EXECUTION_LIFECYCLE.md",
        "codex-backlog/CODEX_PROMPT_TEMPLATE.md",
        "codex-backlog/CODEX_SHORT_PROMPT.md",
        "docs/codex-code-review-retirement.md",
        "docs/issue-driven-continuous-workflow.md",
        "docs/task-branch-integration.md",
    ):
        source = " ".join((ROOT / name).read_text(encoding="utf-8").lower().split())
        assert "security review" in source, name
        assert "manual/conditional" in source, name
        assert "deterministic security" in source, name


def test_quality_gate_cli_does_not_make_qa_a_universal_stage() -> None:
    args = task_session._parser().parse_args(
        ["mark-ready", "229", "--head-sha", "exact-sha", "--quality-verdict", "PASS"]
    )
    assert args.quality_verdict == "PASS"
    assert args.qa_verdict == "NOT_REQUIRED"
