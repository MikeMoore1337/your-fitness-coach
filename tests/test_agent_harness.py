from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from scripts import agent_harness


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / ".agents" / "evals").mkdir(parents=True)
    (root / ".agents" / "roles").mkdir(parents=True)
    (root / ".agents" / "skills" / "qa-engineer").mkdir(parents=True)
    (root / "codex-backlog").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    (root / "AGENTS.md").write_text(
        "# Rules\n\nGitHub is the lifecycle source of truth.\n",
        encoding="utf-8",
    )
    (root / ".agents" / "README.md").write_text("# Agents\n", encoding="utf-8")
    (root / ".agents" / "roles" / "implementer.md").write_text(
        "# Implementer\n\nUse deterministic tests.\n", encoding="utf-8"
    )
    (root / ".agents" / "skills" / "qa-engineer" / "SKILL.md").write_text(
        "# QA\n\nPrefer regression tests.\n", encoding="utf-8"
    )
    (root / "codex-backlog" / "TASK_EXECUTION_LIFECYCLE.md").write_text(
        "# Lifecycle\n", encoding="utf-8"
    )
    (root / "codex-backlog" / "GLOBAL_RULES.md").write_text("# Global\n", encoding="utf-8")
    (root / "tests" / "test_git_flow.py").write_text(
        "def test_git_state():\n    assert True\n\ndef test_ci():\n    assert True\n",
        encoding="utf-8",
    )
    return root


def _manifest(root: Path) -> None:
    (root / ".agents" / "evals" / "github-flow.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "suite": "github-flow",
                "description": "Git and GitHub regression contract",
                "evals": [
                    {
                        "id": "git-state",
                        "kind": "regression",
                        "description": "Git state remains inspectable",
                        "pytest_nodeids": ["tests/test_git_flow.py::test_git_state"],
                    },
                    {
                        "id": "ci",
                        "kind": "capability",
                        "description": "CI remains deterministic",
                        "pytest_nodeids": ["tests/test_git_flow.py::test_ci"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def test_eval_manifest_validation_and_selection(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _manifest(root)

    manifests = agent_harness.load_eval_manifests(root)
    selected = agent_harness.select_evals(manifests, suite="github-flow", eval_id="git-state")

    assert len(manifests) == 1
    assert selected == [
        {
            "suite": "github-flow",
            "id": "git-state",
            "kind": "regression",
            "description": "Git state remains inspectable",
            "pytest_nodeids": ["tests/test_git_flow.py::test_git_state"],
        }
    ]


def test_eval_manifest_rejects_missing_test_function(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / ".agents" / "evals" / "broken.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "suite": "broken",
                "description": "Broken fixture",
                "evals": [
                    {
                        "id": "missing",
                        "kind": "regression",
                        "description": "Missing test",
                        "pytest_nodeids": ["tests/test_git_flow.py::test_missing"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(agent_harness.AgentHarnessError, match="does not exist"):
        agent_harness.load_eval_manifests(root)


def test_eval_runner_reports_each_eval(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _manifest(root)
    selected = agent_harness.select_evals(agent_harness.load_eval_manifests(root))
    calls: list[list[str]] = []

    def fake_runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        returncode = 1 if command[-1].endswith("test_ci") else 0
        return subprocess.CompletedProcess(
            command,
            returncode,
            stdout="synthetic output",
            stderr="" if returncode == 0 else "synthetic failure",
        )

    report = agent_harness.run_evals(root, selected, runner=fake_runner)

    assert report["overall"] == "FAIL"
    assert [item["status"] for item in report["evals"]] == ["PASS", "FAIL"]
    assert all(command[:3] == [agent_harness.sys.executable, "-m", "pytest"] for command in calls)


def test_eval_reports_use_canonical_artifact_class(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    report = {
        "schema_version": 1,
        "classification": "agent-eval-report",
        "generated_at": "2026-10-05T00:00:00Z",
        "overall": "PASS",
        "evals": [
            {
                "suite": "github-flow",
                "id": "git-state",
                "kind": "regression",
                "status": "PASS",
                "returncode": 0,
                "duration_seconds": 0.1,
                "pytest_nodeids": ["tests/test_git_flow.py::test_git_state"],
                "stdout": "",
                "stderr": "",
            }
        ],
    }
    eval_path = agent_harness.write_eval_report(
        root,
        "737",
        report,
        artifact_root=root / ".artifacts",
    )
    assert "/evidence/agent-evals/" in eval_path.as_posix()
    manifest = json.loads((root / ".artifacts/tasks/737/manifest.json").read_text(encoding="utf-8"))
    classifications = {item["path"]: item["classification"] for item in manifest["entries"]}
    assert any(
        path.startswith("evidence/agent-evals/") and classification == "evidence"
        for path, classification in classifications.items()
    )


def test_learning_candidate_deduplicates_without_touching_canonical_docs(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    agents_before = (root / "AGENTS.md").read_text(encoding="utf-8")
    kwargs = {
        "pattern": "GitHub is the lifecycle source of truth.",
        "evidence": ["Task 729", "Task 737"],
        "why_reusable": "The source-of-truth invariant applies across ordinary changes.",
        "destination": "AGENTS.md",
        "conflict_analysis": (
            "Compatible with the existing GitHub Flow rule; likely update existing text."
        ),
        "risk": "low",
        "action": "UPDATE_EXISTING",
        "artifact_root": root / ".artifacts",
    }

    first, first_path, first_duplicate = agent_harness.propose_learning_candidate(
        root, "737", **kwargs
    )
    second, second_path, second_duplicate = agent_harness.propose_learning_candidate(
        root, "737", **kwargs
    )

    assert first_duplicate is False
    assert second_duplicate is True
    assert first_path == second_path
    assert first["fingerprint"] == second["fingerprint"]
    assert first["promotion"]["auto_promotion_supported"] is False
    assert first["overlap"]
    assert (root / "AGENTS.md").read_text(encoding="utf-8") == agents_before


def test_learning_candidate_rejects_secret_before_persistence(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    with pytest.raises(agent_harness.AgentHarnessError, match="Secret-like"):
        agent_harness.propose_learning_candidate(
            root,
            "737",
            pattern="Reuse api_key=sk-proj-abcdefghijklmnop",
            evidence=["Task 737"],
            why_reusable="Synthetic test",
            destination="AGENTS.md",
            conflict_analysis="None",
            risk="high",
            action="REJECT",
            artifact_root=root / ".artifacts",
        )

    assert not (root / ".artifacts").exists()


def test_learning_destination_cannot_escape_repository(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    with pytest.raises(agent_harness.AgentHarnessError, match=r"invalid|escapes"):
        agent_harness.propose_learning_candidate(
            root,
            "737",
            pattern="Reusable deterministic pattern",
            evidence=["Task 737"],
            why_reusable="Synthetic test",
            destination="../outside.md",
            conflict_analysis="None",
            risk="low",
            action="DOC_ONLY",
            artifact_root=root / ".artifacts",
        )


def test_cli_has_no_learning_promotion_command() -> None:
    with pytest.raises(SystemExit):
        agent_harness._parser().parse_args(["learn", "promote"])


def test_repository_agent_eval_manifests_are_valid() -> None:
    repo_root = Path(__file__).parents[1]

    manifests = agent_harness.load_eval_manifests(repo_root)

    assert any(manifest["suite"] == "github-flow" for manifest in manifests)
