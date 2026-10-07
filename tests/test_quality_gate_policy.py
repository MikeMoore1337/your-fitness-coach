"""Small regressions for the standard Git/GitHub lifecycle boundary."""

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_agent_manifest_has_no_release_owner_role() -> None:
    manifest = json.loads((ROOT / ".agents/MANIFEST.json").read_text(encoding="utf-8"))

    assert "integration-release" not in manifest["roles"]
    assert manifest["role_count"] == len(manifest["roles"])
    assert manifest["skill_count"] == len(manifest["skills"])


def test_normal_ci_and_deploy_do_not_call_removed_controller_entrypoints() -> None:
    for relative in (".github/workflows/ci.yml", ".github/workflows/deploy.yml"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "scripts/task_session.py" not in source
        assert "scripts/run_task_delivery.py" not in source
        assert "classify-controller-release" not in source


def test_active_policy_names_github_as_operational_source_of_truth() -> None:
    for relative in (
        "AGENTS.md",
        "codex-backlog/GLOBAL_RULES.md",
        "codex-backlog/TASK_EXECUTION_LIFECYCLE.md",
        "docs/development.md",
        "docs/deployment.md",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "GitHub" in source
        assert "source of truth" in source.lower() or "operational source" in source.lower()


def test_artifact_cleanup_has_no_lifecycle_state_dependency() -> None:
    source = (ROOT / "scripts/artifact_manager.py").read_text(encoding="utf-8")

    assert "codex-task-sessions-v1" not in source
    assert "controller_state_dir" not in source
    assert "terminal_state" not in source
    assert "_controller_guard" not in source
