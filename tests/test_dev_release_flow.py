"""Two-stage YFC release governance contracts."""

import json
from pathlib import Path

from scripts import ci_contract

ROOT = Path(__file__).resolve().parents[1]


def test_dev_push_runs_ci_but_cannot_start_production_deploy() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    deploy = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")

    assert "branches: [master, dev]" in ci
    assert "Require accepted dev promotion for master PR" in ci
    assert "PR_HEAD_REF: ${{ github.event.pull_request.head.ref }}" in ci
    assert "PR_HEAD_REPO: ${{ github.event.pull_request.head.repo.full_name }}" in ci
    assert '[ "$PR_HEAD_REF" != dev ] || [ "$PR_HEAD_REPO" != "$REPOSITORY" ]' in ci

    # The preexisting release trigger must remain master-only.
    assert "branches: [master]" in deploy
    assert "github.event.workflow_run.head_branch == 'master'" in deploy
    assert "environment: production" in deploy


def test_initial_master_to_dev_large_diff_does_not_overflow_ci_outputs(tmp_path: Path) -> None:
    paths = [f"backend/tests/fixture_{index:07d}.py" for index in range(15_000)]
    decision = ci_contract.classify_scope(paths)
    assert len(decision["paths"]) == len(paths)
    assert "python-tests" in decision["required_groups"]

    path = tmp_path / "gh-output"
    ci_contract.write_router_outputs(decision, path)
    content = path.read_text(encoding="utf-8")
    assert len(content.encode("utf-16-le")) < 20_000
    serialized = next(
        line.split("=", 1)[1] for line in content.splitlines() if line.startswith("changed_paths=")
    )
    assert json.loads(serialized) == [f"__paths_truncated__:{len(paths)}"]


def test_normal_pull_request_outputs_preserve_exact_paths(tmp_path: Path) -> None:
    decision = ci_contract.classify_scope(["frontend/package.json"])
    path = tmp_path / "gh-output"
    ci_contract.write_router_outputs(decision, path)
    assert 'changed_paths=["frontend/package.json"]' in path.read_text(encoding="utf-8")
