from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from scripts.issue_workflow import (
    control_state_payload,
    render_control_state_comment,
    render_task_contract,
)


def _load_module():
    script = Path(__file__).parents[1] / "scripts" / "task_session.py"
    spec = importlib.util.spec_from_file_location("task_session", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


task_session = _load_module()


def _git(path: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=path, check=True, text=True, capture_output=True)
    return completed.stdout.strip()


def _write_task(
    root: Path,
    task_id: str,
    slug: str,
    *,
    dependencies: str = "",
    concurrency: str | None = None,
    owner_gate: str = "explicit-launch",
) -> Path:
    tasks = root / "codex-backlog" / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    path = tasks / f"{task_id}-{slug}.md"
    concurrency_metadata = f"concurrency: {concurrency}\n" if concurrency is not None else ""
    path.write_text(
        "# Task fixture\n\n"
        "- **Статус:** owner-selected, not started\n"
        "- **Тип:** implementation\n"
        "<!-- task-session\n"
        f"dependencies: {dependencies}\n"
        "executable: true\n"
        f"{concurrency_metadata}"
        f"owner_gate: {owner_gate}\n"
        "integration: task-pr-to-master\n"
        "-->\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def repository():
    test_root = Path(tempfile.mkdtemp(prefix=f"yfc-task-session-{uuid.uuid4().hex[:8]}-"))
    root = test_root / "repository with spaces"
    remote = test_root / "remote.git"
    root.mkdir()
    _git(root, "init", "-b", "master")
    _git(root, "config", "user.name", "Task Session Tests")
    _git(root, "config", "user.email", "task-session@example.invalid")
    (root / ".gitignore").write_text("/codex-backlog/tasks/\n.artifacts/\n", encoding="utf-8")
    (root / "README.md").write_text("initial\n", encoding="utf-8")
    _git(root, "add", ".gitignore", "README.md")
    _git(root, "commit", "-m", "chore: initial")
    _git(test_root, "init", "--bare", str(remote))
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-u", "origin", "master")
    _git(root, "fetch", "origin")
    repository = task_session.GitRepository(root)
    try:
        yield root, repository
    finally:
        for worktree in repository.worktrees():
            if worktree.path != root:
                _git(root, "worktree", "remove", "--force", str(worktree.path))
        _git(root, "worktree", "prune")
        shutil.rmtree(test_root, ignore_errors=True)


class FakeGitHub:
    def __init__(self, master_sha: str) -> None:
        self.master_sha = master_sha
        self.repo_slug = "owner/repository"
        self.pulls: dict[int, dict[str, Any]] = {}
        self.commits: dict[int, list[dict[str, Any]]] = {}
        self.files: dict[int, list[dict[str, Any]]] = {}
        self.checks: dict[str, list[dict[str, Any]]] = {}
        self.open_prs: list[dict[str, Any]] = []
        self.active_runs: list[dict[str, Any]] = []
        self.ruleset_payload: list[dict[str, Any]] = []
        self.successful_deployments: set[tuple[str, str]] = set()
        self.associated_pulls: list[dict[str, Any]] = []
        self.associated_pulls_by_commit: dict[str, list[dict[str, Any]]] = {}
        self.runs: dict[int, dict[str, Any]] = {}
        self.workflow_runs_by_sha: dict[str, list[dict[str, Any]]] = {}
        self.workflow_jobs_by_run: dict[int, list[dict[str, Any]]] = {}
        self.current_production_deployment: dict[str, Any] | None = None
        self.issues: dict[int, dict[str, Any]] = {}
        self.issue_comment_map: dict[int, list[dict[str, Any]]] = {}

    def api(self, endpoint: str) -> Any:
        if endpoint.startswith("commits/") and endpoint.endswith("/pulls"):
            return self.associated_pulls
        if endpoint.startswith("issues/") and endpoint.count("/") == 1:
            return self.issues[int(endpoint.rsplit("/", maxsplit=1)[1])]
        if endpoint.startswith("actions/runs/"):
            return self.runs[int(endpoint.rsplit("/", maxsplit=1)[1])]
        raise AssertionError(f"Unexpected fake GitHub API endpoint: {endpoint}")

    def open_pull_requests(self) -> list[dict[str, Any]]:
        return self.open_prs

    def pull_request(self, number: int) -> dict[str, Any]:
        return self.pulls[number]

    def pull_request_commits(self, number: int) -> list[dict[str, Any]]:
        return self.commits[number]

    def pull_request_files(self, number: int) -> list[dict[str, Any]]:
        return self.files.get(number, [{"filename": "README.md"}])

    def pull_requests_for_commit(self, sha: str) -> list[dict[str, Any]]:
        return self.associated_pulls_by_commit.get(sha, [])

    def check_runs(self, sha: str) -> list[dict[str, Any]]:
        return self.checks.get(sha, [])

    def branch_head(self, branch: str) -> str:
        if branch != "master":
            raise AssertionError(f"Unexpected branch lookup: {branch}")
        return self.master_sha

    def issue_comments(self, number: int) -> list[dict[str, Any]]:
        return self.issue_comment_map[number]

    def has_successful_deployment(self, sha: str, environment: str) -> bool:
        return (sha, environment) in self.successful_deployments

    def workflow_runs(self, workflow: str, sha: str) -> list[dict[str, Any]]:
        assert workflow == "deploy.yml"
        return self.workflow_runs_by_sha.get(sha, [])

    def workflow_jobs(self, run_id: int) -> list[dict[str, Any]]:
        return self.workflow_jobs_by_run.get(run_id, [])

    def latest_deployment_status(self, environment: str) -> dict[str, Any] | None:
        assert environment == "production"
        return self.current_production_deployment

    def active_workflow_runs(self) -> list[dict[str, Any]]:
        return self.active_runs

    def rulesets(self) -> list[dict[str, Any]]:
        return self.ruleset_payload


def _task_pr(
    number: int,
    task_id: str,
    base_sha: str,
    head_sha: str,
    *,
    base_branch: str = "master",
    merge_sha: str | None = None,
) -> dict[str, Any]:
    return {
        "number": number,
        "title": f"[Task {task_id}] Synthetic task",
        "merged_at": "2026-09-03T10:00:00Z" if merge_sha else None,
        "merge_commit_sha": merge_sha,
        "commits": 1,
        "changed_files": 1,
        "base": {
            "ref": base_branch,
            "sha": base_sha,
            "repo": {"full_name": "owner/repository"},
        },
        "head": {
            "ref": f"task/{task_id}-synthetic-task",
            "sha": head_sha,
            "repo": {"full_name": "owner/repository"},
        },
    }


def _task_commit(task_id: str) -> dict[str, Any]:
    return {"commit": {"message": f"feat: [Task {task_id}] synthetic change"}}


def _controller_pr(base_sha: str, head_sha: str) -> dict[str, Any]:
    pull_request = _task_pr(234, "234", base_sha, head_sha)
    pull_request["title"] = "[Controller] Synthetic maintenance"
    pull_request["head"]["ref"] = "codex/controller-synthetic-maintenance"
    return pull_request


def _controller_commit() -> dict[str, Any]:
    return {"commit": {"message": "[Controller] synthetic maintenance"}}


def _merged_release_pr(
    number: int,
    merge_sha: str,
    *,
    branch: str,
    title: str,
    paths: list[str],
    declared_count: int | None = None,
) -> dict[str, Any]:
    pull_request = _task_pr(number, str(number), "a" * 40, "b" * 40, merge_sha=merge_sha)
    pull_request["title"] = title
    pull_request["head"]["ref"] = branch
    pull_request["changed_files"] = len(paths) if declared_count is None else declared_count
    return pull_request


def _release_github(
    pull_requests: list[dict[str, Any]], files_by_pr: dict[int, list[str]]
) -> FakeGitHub:
    github = FakeGitHub("a" * 40)
    github.associated_pulls = pull_requests
    if pull_requests:
        merge_sha = str(pull_requests[0]["merge_commit_sha"])
        github.associated_pulls_by_commit[merge_sha] = pull_requests
    for pull_request in pull_requests:
        number = int(pull_request["number"])
        github.pulls[number] = pull_request
        github.files[number] = [{"filename": path} for path in files_by_pr[number]]
    return github


def _success_check(sha: str) -> dict[str, Any]:
    return {"name": "checks", "head_sha": sha, "status": "completed", "conclusion": "SUCCESS"}


def _prepare_started(
    repository: tuple[Path, Any],
    task_id: str = "301",
    *,
    concurrency: str = "independent-write",
    queue_mode: bool = False,
) -> tuple[Path, Any, Any, Path, str, str]:
    root, git_repository = repository
    _write_task(root, task_id, "synthetic-task", concurrency=concurrency)
    controller = task_session.TaskController(
        git_repository, github=FakeGitHub(git_repository.ref("origin/master"))
    )
    started = controller.start(
        task_id,
        owner_launch=True,
        session_label="pytest",
        offline=True,
        queue_mode=queue_mode,
    )
    worktree = Path(started["lease"]["worktree"])
    branch = str(started["lease"]["branch"])
    base_sha = str(started["lease"]["base_origin_master_sha"])
    (worktree / "change.txt").write_text("change\n", encoding="utf-8")
    _git(worktree, "add", "change.txt")
    _git(worktree, "commit", "-m", f"feat: [Task {task_id}] synthetic change")
    head_sha = _git(worktree, "rev-parse", "HEAD")
    return root, git_repository, controller, worktree, branch, base_sha + ":" + head_sha


def _prepare_merged_no_deploy_reconciliation(
    repository: tuple[Path, Any],
    task_id: str = "729",
    *,
    stale_done: bool = True,
    keep_anchor: bool = False,
) -> tuple[Path, Any, Any, Path, str, str, str, str, FakeGitHub, dict[str, Any]]:
    root, git_repository, controller, worktree, branch, sha_pair = _prepare_started(
        repository, task_id
    )
    base_sha, head_sha = sha_pair.split(":")
    merge_sha = _publish_task_squash_without_advancing_local_master(root, branch)
    github = controller.github
    assert isinstance(github, FakeGitHub)
    github.master_sha = merge_sha
    pull_request = _task_pr(730, task_id, base_sha, head_sha, merge_sha=merge_sha)
    pull_request.update(
        {
            "state": "closed",
            "body": task_session.NO_DEPLOY_CONTRACT_STATEMENT,
        }
    )
    pull_request["head"]["ref"] = branch
    github.pulls[730] = pull_request
    github.commits[730] = [_task_commit(task_id)]
    github.files[730] = [{"filename": "change.txt"}]
    github.checks[head_sha] = [_success_check(head_sha)]
    github.associated_pulls_by_commit[merge_sha] = [pull_request]
    if stale_done:
        lease = controller.store.read_json(controller.store.task_lease_path(task_id))
        assert isinstance(lease, dict)
        lease.update(
            {
                "lifecycle_state": task_session.DONE_STATE,
                "terminal_result": "superseded",
                "owner_authorized": True,
                "superseded_reason": "legacy stale closeout fixture",
                "superseded_at": "2026-10-05T12:00:00Z",
            }
        )
        task_session.StateStore.replace_json(controller.store.task_lease_path(task_id), lease)
    if not keep_anchor:
        _git(root, "worktree", "remove", "--force", str(worktree))
        _git(root, "branch", "-D", branch)
    return (
        root,
        git_repository,
        controller,
        worktree,
        branch,
        base_sha,
        head_sha,
        merge_sha,
        github,
        pull_request,
    )


def _prepare_historical_production_reconciliation(
    repository: tuple[Path, Any],
    *,
    revert_feature: bool = False,
    controller_disallowed_path: bool = False,
    omit_latest_release: bool = False,
) -> tuple[Path, Any, Any, Path, str, str, str, str, FakeGitHub, list[dict[str, Any]]]:
    root, git_repository, controller, worktree, branch, sha_pair = _prepare_started(
        repository, "746"
    )
    base_sha, anchor_head_sha = sha_pair.split(":")
    controller.mark_ready(
        "746",
        head_sha=anchor_head_sha,
        quality_verdict="PASS",
        qa_verdict="PASS",
    )

    migration_path = worktree / "backend" / "alembic" / "versions" / "0120_synthetic.py"
    migration_path.parent.mkdir(parents=True, exist_ok=True)
    migration_path.write_text("revision = '0120_synthetic'\n", encoding="utf-8")
    _git(worktree, "add", str(migration_path.relative_to(worktree)))
    _git(worktree, "commit", "-m", "[Task 746] Add synthetic migration")
    (worktree / "change.txt").write_text("change\nfinal\n", encoding="utf-8")
    _git(worktree, "add", "change.txt")
    _git(worktree, "commit", "-m", "[Task 746] Complete bounded delivery repair")
    final_head_sha = _git(worktree, "rev-parse", "HEAD")

    task_commit_shas = _git(
        worktree, "rev-list", "--reverse", f"{base_sha}..{final_head_sha}"
    ).splitlines()
    task_commits = [
        {
            "sha": sha,
            "commit": {"message": _git(worktree, "show", "-s", "--format=%B", sha).strip()},
        }
        for sha in task_commit_shas
    ]

    _git(
        root,
        "merge",
        "--no-ff",
        branch,
        "-m",
        "Merge pull request #764 from owner/task/746-synthetic-task",
    )
    deployed_sha = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "origin", "master")
    _git(root, "fetch", "origin", "master")

    github = controller.github
    assert isinstance(github, FakeGitHub)
    task_pr = _task_pr(764, "746", base_sha, final_head_sha, merge_sha=deployed_sha)
    task_pr.update(
        {
            "state": "closed",
            "title": "[Task 746] V10-A1 synthetic meal planner",
            "commits": len(task_commits),
            "changed_files": 2,
        }
    )
    task_pr["head"]["ref"] = branch
    github.pulls[764] = task_pr
    github.commits[764] = task_commits
    github.files[764] = [
        {"filename": "change.txt"},
        {"filename": "backend/alembic/versions/0120_synthetic.py"},
    ]
    github.checks[final_head_sha] = [_success_check(final_head_sha)]
    github.associated_pulls_by_commit[deployed_sha] = [task_pr]

    production_run_id = 37419987998
    production_run = {
        "id": production_run_id,
        "name": "Release production",
        "head_sha": deployed_sha,
        "status": "completed",
        "conclusion": "success",
        "html_url": f"https://example.invalid/actions/runs/{production_run_id}",
    }
    github.runs[production_run_id] = production_run
    github.workflow_runs_by_sha[deployed_sha] = [production_run]
    github.successful_deployments.add((deployed_sha, "production"))
    github.current_production_deployment = {
        "deployment_id": 8100,
        "sha": deployed_sha,
        "environment": "production",
        "state": "success",
        "updated_at": "2026-10-06T05:45:00Z",
        "log_url": "https://example.invalid/deployments/8100",
    }

    records: list[dict[str, Any]] = []
    previous_sha = deployed_sha

    controller_branch = "codex/controller-synthetic-after-746"
    _git(root, "switch", "-c", controller_branch)
    controller_path = (
        "backend/forbidden-controller.py"
        if controller_disallowed_path
        else "scripts/task_session.py"
    )
    controller_file = root / controller_path
    controller_file.parent.mkdir(parents=True, exist_ok=True)
    controller_file.write_text(
        controller_file.read_text(encoding="utf-8") + "\n# synthetic controller drift\n"
        if controller_file.exists()
        else "# synthetic controller drift\n",
        encoding="utf-8",
    )
    _git(root, "add", controller_path)
    _git(root, "commit", "-m", "[Controller] Synthetic post-746 maintenance")
    controller_head = _git(root, "rev-parse", "HEAD")
    _git(root, "switch", "master")
    _git(
        root,
        "merge",
        "--no-ff",
        controller_branch,
        "-m",
        "Merge pull request #761 from owner/codex/controller-synthetic-after-746",
    )
    controller_merge = _git(root, "rev-parse", "HEAD")
    controller_pr = {
        "number": 761,
        "title": "[Controller] Synthetic post-746 maintenance",
        "state": "closed",
        "merged_at": "2026-10-06T05:49:08Z",
        "merge_commit_sha": controller_merge,
        "commits": 1,
        "changed_files": 1,
        "base": {
            "ref": "master",
            "sha": previous_sha,
            "repo": {"full_name": "owner/repository"},
        },
        "head": {
            "ref": controller_branch,
            "sha": controller_head,
            "repo": {"full_name": "owner/repository"},
        },
    }
    github.pulls[761] = controller_pr
    github.associated_pulls_by_commit[controller_merge] = [controller_pr]
    github.commits[761] = [
        {
            "sha": controller_head,
            "commit": {"message": "[Controller] Synthetic post-746 maintenance"},
        }
    ]
    github.files[761] = [{"filename": controller_path}]
    github.checks[controller_head] = [_success_check(controller_head)]
    controller_run_id = 37420010001
    github.workflow_runs_by_sha[controller_merge] = [
        {
            "id": controller_run_id,
            "name": "Release production",
            "head_sha": controller_merge,
            "status": "completed",
            "conclusion": "success",
            "html_url": f"https://example.invalid/runs/{controller_run_id}",
        }
    ]
    github.workflow_jobs_by_run[controller_run_id] = [
        {"name": "Authorize exact merged master revision", "conclusion": "success"},
        {"name": "Deploy immutable tested bundle", "conclusion": "skipped"},
    ]
    records.append(
        {
            "classification": "controller",
            "commit_sha": controller_merge,
            "head_sha": controller_head,
            "pr_number": 761,
        }
    )
    previous_sha = controller_merge

    product_branch = "task/760-synthetic-after-746"
    _git(root, "switch", "-c", product_branch)
    product_paths: list[str]
    if revert_feature:
        _git(root, "rm", "change.txt", "backend/alembic/versions/0120_synthetic.py")
        product_paths = ["change.txt", "backend/alembic/versions/0120_synthetic.py"]
    else:
        runtime_path = root / "backend" / "synthetic_after_746.py"
        runtime_path.write_text("VALUE = 1\n", encoding="utf-8")
        _git(root, "add", str(runtime_path.relative_to(root)))
        product_paths = ["backend/synthetic_after_746.py"]
    _git(root, "commit", "-m", "[Task 760] Synthetic independent runtime change")
    product_head = _git(root, "rev-parse", "HEAD")
    _git(root, "switch", "master")
    _git(
        root,
        "merge",
        "--no-ff",
        product_branch,
        "-m",
        "Merge pull request #767 from owner/task/760-synthetic-after-746",
    )
    product_merge = _git(root, "rev-parse", "HEAD")
    product_pr = {
        "number": 767,
        "title": "[Task 760] Synthetic independent runtime change",
        "state": "closed",
        "merged_at": "2026-10-06T06:00:00Z",
        "merge_commit_sha": product_merge,
        "commits": 1,
        "changed_files": len(product_paths),
        "base": {
            "ref": "master",
            "sha": previous_sha,
            "repo": {"full_name": "owner/repository"},
        },
        "head": {
            "ref": product_branch,
            "sha": product_head,
            "repo": {"full_name": "owner/repository"},
        },
    }
    github.pulls[767] = product_pr
    github.associated_pulls_by_commit[product_merge] = [product_pr]
    github.commits[767] = [
        {
            "sha": product_head,
            "commit": {"message": "[Task 760] Synthetic independent runtime change"},
        }
    ]
    github.files[767] = [{"filename": item} for item in product_paths]
    github.checks[product_head] = [_success_check(product_head)]
    product_run_id = 37420010002
    if not omit_latest_release:
        github.workflow_runs_by_sha[product_merge] = [
            {
                "id": product_run_id,
                "name": "Release production",
                "head_sha": product_merge,
                "status": "completed",
                "conclusion": "success",
                "html_url": f"https://example.invalid/runs/{product_run_id}",
            }
        ]
        github.successful_deployments.add((product_merge, "production"))
        github.current_production_deployment = {
            "deployment_id": 8102,
            "sha": product_merge,
            "environment": "production",
            "state": "success",
            "updated_at": "2026-10-06T06:05:00Z",
            "log_url": "https://example.invalid/deployments/8102",
        }
    records.append(
        {
            "classification": "product",
            "commit_sha": product_merge,
            "head_sha": product_head,
            "pr_number": 767,
            "release_run_id": product_run_id,
        }
    )

    _git(root, "push", "origin", "master")
    _git(root, "fetch", "origin", "master")
    github.master_sha = product_merge

    lease_path = controller.store.task_lease_path("746")
    lease = controller.store.read_json(lease_path)
    assert isinstance(lease, dict)
    lease.update(
        {
            "lifecycle_state": task_session.HUMAN_REQUIRED_STATE,
            "delivery_base_origin_master_sha": base_sha,
            "delivery_head_sha": anchor_head_sha,
            "delivery_anchor": {
                "task_id": "746",
                "branch": branch,
                "base_sha": base_sha,
                "head_sha": anchor_head_sha,
            },
            "recovery_reason": "missed production closeout after independent master drift",
        }
    )
    lease.pop("delivery_owner", None)
    task_session.StateStore.replace_json(lease_path, lease)

    return (
        root,
        git_repository,
        controller,
        worktree,
        branch,
        base_sha,
        anchor_head_sha,
        deployed_sha,
        github,
        records,
    )


def _prepare_ready_production_reconciliation(
    repository: tuple[Path, Any], task_id: str = "506"
) -> tuple[Path, Any, Any, Path, str, str, str, FakeGitHub]:
    root, git_repository, controller, worktree, branch, sha_pair = _prepare_started(
        repository, task_id
    )
    base_sha, head_sha = sha_pair.split(":")
    controller.mark_ready(task_id, head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")
    merge_sha = _publish_task_squash_without_advancing_local_master(root, branch)
    github = controller.github
    assert isinstance(github, FakeGitHub)
    github.master_sha = merge_sha
    pull_request = _task_pr(570, task_id, base_sha, head_sha, merge_sha=merge_sha)
    pull_request["state"] = "closed"
    pull_request["head"]["ref"] = branch
    github.pulls[570] = pull_request
    github.commits[570] = [_task_commit(task_id)]
    github.files[570] = [{"filename": "change.txt"}]
    github.checks[head_sha] = [_success_check(head_sha)]
    github.runs[36522345602] = {
        "id": 36522345602,
        "name": "Release production",
        "head_sha": merge_sha,
        "status": "completed",
        "conclusion": "success",
        "html_url": "https://example.invalid/actions/runs/36522345602",
    }
    github.successful_deployments.add((merge_sha, "production"))
    return root, git_repository, controller, worktree, branch, base_sha, head_sha, github


def _prepare_preimplementation_resume(
    repository: tuple[Path, Any],
    task_id: str = "241",
    *,
    dependencies: tuple[str, ...] = (),
) -> tuple[Path, Any, Any, Path, str, str, FakeGitHub]:
    root, git_repository = repository
    slug = "resume-me"
    _write_task(root, task_id, slug, dependencies=", ".join(dependencies))
    github = FakeGitHub(git_repository.ref("origin/master"))
    controller = task_session.TaskController(git_repository, github=github)
    started = controller.start(
        task_id, owner_launch=True, session_label="resume-test", offline=True
    )
    lease = started["lease"]
    branch = str(lease["branch"])
    issue_number = int(task_id.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
    github.issues[issue_number] = {
        "number": issue_number,
        "title": f"[Product v4 / Stage 0] Synthetic task {task_id} resume fixture",
        "state": "open",
        "user": {"login": "owner"},
        "body": render_task_contract(
            {
                "version": 1,
                "task_id": task_id,
                "scope": "Synthetic pre-implementation recovery",
                "acceptance": ["resume safely"],
                "dependencies": list(dependencies),
                "owner_gate": "explicit-launch",
                "risk_lane": "GREEN",
                "source_spec": f"codex-backlog/tasks/{task_id}-{slug}.md",
                "issue_state": "in_progress",
            }
        ),
    }
    blocker = (
        "Task worker stopped before implementation: guarded bootstrap exited before "
        "creating worker-state.json."
    )
    github.issue_comment_map[issue_number] = [
        {
            "id": 1,
            "created_at": "2026-09-26T12:00:00Z",
            "user": {"login": "owner"},
            "body": render_control_state_comment(
                control_state_payload(
                    task_id=task_id,
                    state="human_required",
                    issue_number=issue_number,
                    branch=branch,
                    blocker=blocker,
                )
            ),
        }
    ]
    return (
        root,
        git_repository,
        controller,
        Path(lease["worktree"]),
        branch,
        str(lease["base_origin_master_sha"]),
        github,
    )


def test_verified_noop_retry_reconciles_omitted_dependency_and_preserves_lease(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, _, _, _, _ = _prepare_verified_noop_retry_fixture(repository)
    lease_path = controller.store.task_lease_path("508")
    lease = controller.store.read_json(lease_path)
    assert isinstance(lease, dict)
    assert lease["dependency_ids"] == []
    result = controller.retry_noop_worker(
        "508",
        control_issue_number=508,
        reason="retry after corrected Agent Flow routing; previous worker completed read-only with zero product mutation",
        owner_authorize=True,
    )
    assert result["dependency_reconciliation"]["previous"] == []
    assert result["dependency_reconciliation"]["authoritative"] == ["507"]
    assert [item["name"] for item in result["agent_flow"]["worker_role_passes"]] == [
        "implementer",
        "qa-verifier",
    ]
    preserved = controller.store.read_json(lease_path)
    assert preserved["dependency_ids"] == ["507"]
    assert (
        preserved["worker_retry"]["classification"] == task_session.NOOP_WORKER_RETRY_CLASSIFICATION
    )
    claimed = controller.claim_preimplementation_worker_launch("508")
    assert claimed["preimplementation_resume"]["state"] == "launching"
    with pytest.raises(task_session.TaskSessionError, match="retry budget"):
        controller.retry_noop_worker(
            "508",
            control_issue_number=508,
            reason="second retry",
            owner_authorize=True,
        )


def _prepare_verified_noop_retry_fixture(
    repository: tuple[Path, Any],
    *,
    advance_master: bool = False,
    already_fast_forwarded: bool = False,
) -> tuple[Path, Any, Any, Path, str, str, FakeGitHub]:
    root, git_repository = repository
    task_path = _write_task(root, "508", "synthetic-task")
    task_path.write_text(
        task_path.read_text(encoding="utf-8")
        + "\n- **Основная роль:** `implementer`\n"
        + "- **Дополнительные роли lifecycle:** `qa-verifier`\n"
        + "Depends on: #507\n",
        encoding="utf-8",
    )
    done = root / "codex-backlog" / "tasks" / "done"
    done.mkdir(parents=True, exist_ok=True)
    (done / "507-terminal.md").write_text("terminal\n", encoding="utf-8")
    github = FakeGitHub(git_repository.ref("origin/master"))
    controller = task_session.TaskController(git_repository, github=github)
    controller.start("508", owner_launch=True, session_label="retry-test", offline=True)
    lease_path = controller.store.task_lease_path("508")
    lease = controller.store.read_json(lease_path)
    assert isinstance(lease, dict)
    assert lease["dependency_ids"] == ["507"]
    base_sha = str(lease["base_origin_master_sha"])
    branch = str(lease["branch"])
    worktree = Path(str(lease["worktree"]))
    lease["dependency_ids"] = []
    controller.store.replace_json(lease_path, lease)
    attempt = (
        root
        / ".artifacts"
        / "tasks"
        / "508"
        / "temporary"
        / "delivery"
        / "20260930T000000000000Z-delivery"
    )
    attempt.mkdir(parents=True)
    (attempt / "final.md").write_text("read-only worker\n", encoding="utf-8")
    (attempt / "events.jsonl").write_text('{"type":"turn.completed"}\n', encoding="utf-8")
    (attempt / "worker-guard.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "classification": "yfc-worker-guard-report",
                "blocked": False,
                "privacy": {
                    "raw_prompts_stored": False,
                    "raw_commands_stored": False,
                    "raw_tool_arguments_stored": False,
                    "raw_tool_results_stored": False,
                },
            }
        ),
        encoding="utf-8",
    )
    flow = root / ".artifacts" / "tasks" / "508" / "evidence" / "agent-flow"
    flow.mkdir(parents=True, exist_ok=True)
    (flow / "old.json").write_text(
        json.dumps(
            {
                "classification": "yfc-agent-flow-plan",
                "task_id": "508",
                "routing": {"explicit_role_contract": False},
                "execution": {"production_writer": None},
                "worker_role_passes": [{"name": "researcher"}],
            }
        ),
        encoding="utf-8",
    )
    issue_number = 508
    github.issues[issue_number] = {
        "number": issue_number,
        "state": "open",
        "user": {"login": "owner"},
        "body": render_task_contract(
            {
                "version": 1,
                "task_id": "508",
                "scope": "synthetic implementation",
                "acceptance": ["works"],
                "dependencies": ["507"],
                "owner_gate": "owner_launch",
                "risk_lane": "GREEN",
                "source_spec": "codex-backlog/tasks/508-synthetic-task.md",
                "issue_state": "queued",
            }
        ),
    }
    github.issue_comment_map[issue_number] = []
    if advance_master:
        (root / "README.md").write_text("controller refresh\n", encoding="utf-8")
        _git(root, "add", "README.md")
        _git(root, "commit", "-m", "[Controller] advance protected master")
        _git(root, "push", "origin", "master")
        git_repository.fetch_origin_master(cwd=root, prune=False)
        github.master_sha = git_repository.ref("origin/master")
        if already_fast_forwarded:
            git_repository.fast_forward_current(github.master_sha, cwd=worktree)
    return root, git_repository, controller, worktree, branch, base_sha, github


def test_verified_noop_retry_proves_evidence_before_fast_forward(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository, controller, worktree, _, base_sha, _ = (
        _prepare_verified_noop_retry_fixture(repository, advance_master=True)
    )
    flow_root = root / ".artifacts" / "tasks" / "508" / "evidence" / "agent-flow"
    (flow_root / "old.json").unlink()
    before_head = git_repository.head(cwd=worktree)
    with pytest.raises(task_session.TaskSessionError, match="researcher-only Agent Flow"):
        controller.retry_noop_worker(
            "508",
            control_issue_number=508,
            reason="retry after corrected Agent Flow routing; previous worker completed read-only with zero product mutation",
            owner_authorize=True,
        )
    assert before_head == base_sha
    assert git_repository.head(cwd=worktree) == base_sha


def test_verified_noop_retry_reconciles_already_fast_forwarded_controller_state(
    repository: tuple[Path, Any],
) -> None:
    _, git_repository, controller, worktree, branch, base_sha, github = (
        _prepare_verified_noop_retry_fixture(
            repository, advance_master=True, already_fast_forwarded=True
        )
    )
    current_origin = github.master_sha
    assert git_repository.head(cwd=worktree) == current_origin
    result = controller.retry_noop_worker(
        "508",
        control_issue_number=508,
        reason="retry after corrected Agent Flow routing; previous worker completed read-only with zero product mutation",
        owner_authorize=True,
    )
    assert result["base_refresh"]["classification"] == ("controller_induced_pre_retry_fast_forward")
    assert result["base_refresh"]["previous_task_head"] == base_sha
    assert result["lease"]["dependency_ids"] == ["507"]
    assert git_repository.head(cwd=worktree) == current_origin
    assert git_repository.unique_commits(branch, base=current_origin) == []
    assert result["lease"]["original_base_origin_master_sha"] == base_sha


def test_verified_noop_retry_records_post_refresh_preimplementation_head(
    repository: tuple[Path, Any],
) -> None:
    _, git_repository, controller, worktree, _, base_sha, github = (
        _prepare_verified_noop_retry_fixture(repository, advance_master=True)
    )

    result = controller.retry_noop_worker(
        "508",
        control_issue_number=508,
        reason="retry after corrected Agent Flow routing; previous worker completed read-only with zero product mutation",
        owner_authorize=True,
    )

    current_origin = github.master_sha
    event = result["preimplementation_resume"]
    assert base_sha != current_origin
    assert git_repository.head(cwd=worktree) == current_origin
    assert event["base_sha"] == current_origin
    assert event["head_sha"] == current_origin
    assert event["original_base_sha"] == base_sha


def _prepare_stale_verified_noop_resume(
    repository: tuple[Path, Any],
) -> tuple[Path, Any, Any, Path, str, str, str]:
    root, git_repository, controller, worktree, branch, base_sha, github = (
        _prepare_verified_noop_retry_fixture(repository, advance_master=True)
    )
    result = controller.retry_noop_worker(
        "508",
        control_issue_number=508,
        reason="retry after corrected Agent Flow routing; previous worker completed read-only with zero product mutation",
        owner_authorize=True,
    )
    lease_path = controller.store.task_lease_path("508")
    lease = controller.store.read_json(lease_path)
    assert isinstance(lease, dict)
    stale_head = base_sha
    event = lease["preimplementation_resume"]
    event["head_sha"] = stale_head
    lease["worker_retry"]["prior_attempt"]["pre_refresh_head"] = stale_head
    lease["worker_retry"]["base_refresh"]["observed_head_before_operation"] = stale_head
    task_session.StateStore.replace_json(lease_path, lease)
    assert result["base_refresh"]["refreshed_head"] == github.master_sha
    return root, git_repository, controller, worktree, branch, stale_head, github.master_sha


def test_claim_reconciles_exact_stale_verified_noop_prepared_head(
    repository: tuple[Path, Any],
) -> None:
    _, git_repository, controller, worktree, branch, stale_head, current_origin = (
        _prepare_stale_verified_noop_resume(repository)
    )

    claimed = controller.claim_preimplementation_worker_launch("508")
    event = claimed["preimplementation_resume"]
    lease = controller.store.read_json(controller.store.task_lease_path("508"))
    assert event["state"] == "launching"
    assert event["head_sha"] == current_origin
    assert event["prepared_head_reconciliation"]["previous_head_sha"] == stale_head
    assert event["prepared_head_reconciliation"]["reconciled_head_sha"] == current_origin
    assert git_repository.head(cwd=worktree) == current_origin
    assert git_repository.ref(f"refs/heads/{branch}") == current_origin
    assert lease["preimplementation_resume"]["head_sha"] == current_origin


def test_claim_refuses_stale_prepared_head_without_matching_base_refresh(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, _, _, stale_head, _ = _prepare_stale_verified_noop_resume(repository)
    lease_path = controller.store.task_lease_path("508")
    lease = controller.store.read_json(lease_path)
    assert isinstance(lease, dict)
    lease["worker_retry"].pop("base_refresh")
    task_session.StateStore.replace_json(lease_path, lease)

    with pytest.raises(task_session.TaskSessionError, match="HUMAN_REQUIRED"):
        controller.claim_preimplementation_worker_launch("508")

    unchanged = controller.store.read_json(lease_path)
    assert unchanged["preimplementation_resume"]["head_sha"] == stale_head
    assert "prepared_head_reconciliation" not in unchanged["preimplementation_resume"]


def test_claim_refuses_stale_prepared_head_with_existing_launch_attempt(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, _, _, stale_head, _ = _prepare_stale_verified_noop_resume(repository)
    lease_path = controller.store.task_lease_path("508")
    lease = controller.store.read_json(lease_path)
    assert isinstance(lease, dict)
    lease["preimplementation_resume"]["launch_attempts"] = [
        {"launch_id": "already-claimed", "state": "launching"}
    ]
    task_session.StateStore.replace_json(lease_path, lease)

    with pytest.raises(task_session.TaskSessionError, match="HUMAN_REQUIRED"):
        controller.claim_preimplementation_worker_launch("508")

    unchanged = controller.store.read_json(lease_path)
    assert unchanged["preimplementation_resume"]["head_sha"] == stale_head
    assert "prepared_head_reconciliation" not in unchanged["preimplementation_resume"]


def test_claim_refuses_stale_prepared_head_when_branch_ref_differs(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository, controller, _, branch, stale_head, current_origin = (
        _prepare_stale_verified_noop_resume(repository)
    )
    _git(root, "update-ref", f"refs/heads/{branch}", stale_head, current_origin)

    with pytest.raises(task_session.TaskSessionError, match="HUMAN_REQUIRED"):
        controller.claim_preimplementation_worker_launch("508")

    lease = controller.store.read_json(controller.store.task_lease_path("508"))
    assert lease["preimplementation_resume"]["head_sha"] == stale_head
    assert git_repository.ref(f"refs/heads/{branch}") == stale_head


def test_claim_refuses_stale_prepared_head_with_genuine_unique_task_commit(
    repository: tuple[Path, Any],
) -> None:
    _, git_repository, controller, worktree, _, stale_head, current_origin = (
        _prepare_stale_verified_noop_resume(repository)
    )
    (worktree / "task-only.txt").write_text("product WIP\n", encoding="utf-8")
    _git(worktree, "add", "task-only.txt")
    _git(worktree, "commit", "-m", "feat: [Task 508] genuine product change")
    unique_head = git_repository.head(cwd=worktree)
    assert unique_head not in {stale_head, current_origin}

    with pytest.raises(task_session.TaskSessionError, match="HUMAN_REQUIRED"):
        controller.claim_preimplementation_worker_launch("508")

    lease = controller.store.read_json(controller.store.task_lease_path("508"))
    assert lease["preimplementation_resume"]["head_sha"] == stale_head
    assert "prepared_head_reconciliation" not in lease["preimplementation_resume"]


def test_verified_noop_retry_refuses_genuine_unique_task_commit_before_refresh(
    repository: tuple[Path, Any],
) -> None:
    _, git_repository, controller, worktree, _, base_sha, _ = _prepare_verified_noop_retry_fixture(
        repository, advance_master=True
    )
    (worktree / "task-only.txt").write_text("product WIP\n", encoding="utf-8")
    _git(worktree, "add", "task-only.txt")
    _git(worktree, "commit", "-m", "feat: [Task 508] genuine product change")
    before_head = git_repository.head(cwd=worktree)
    with pytest.raises(
        task_session.TaskSessionError, match="ancestor of synchronized origin/master"
    ):
        controller.retry_noop_worker(
            "508",
            control_issue_number=508,
            reason="retry after corrected Agent Flow routing; previous worker completed read-only with zero product mutation",
            owner_authorize=True,
        )
    assert before_head != base_sha
    assert git_repository.head(cwd=worktree) == before_head


def _record_codex_cli_argument_failure(
    controller: Any,
    root: Path,
    github: Any,
    branch: str,
    *,
    reason: str,
    completed_tool_actions: int = 0,
    attempt_name: str = "codex-cli-attempt",
    advance_master: bool = False,
) -> Path:
    controller.resume_preimplementation(
        "241",
        control_issue_number=241,
        reason=reason,
        owner_authorize=True,
    )
    controller.claim_preimplementation_worker_launch("241")
    attempt_root = root / ".artifacts" / "tasks" / "241" / "temporary" / "delivery" / attempt_name
    attempt_root.mkdir(parents=True)
    worker_state_path = attempt_root / "worker-state.json"
    worker_state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "pid": 701,
                "process_group_id": None,
                "process_instance": {"kind": "test", "instance": "supervisor"},
                "started_at": "2026-09-27T00:00:00Z",
                "command_process": {
                    "pid": 702,
                    "process_instance": {"kind": "test", "instance": "codex"},
                },
                "command_started_at": "2026-09-27T00:00:01Z",
            }
        ),
        encoding="utf-8",
    )
    controller.record_preimplementation_worker_started("241", worker_state_path=worker_state_path)
    worker_state_path.unlink()
    (attempt_root / "events.jsonl").write_text(
        "error: the argument '--approve-for-me' cannot be used with '--sandbox <SANDBOX_MODE>'\n",
        encoding="utf-8",
    )
    (attempt_root / "worker-guard.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "classification": "yfc-worker-guard-report",
                "blocked": False,
                "block_reason_code": None,
                "counters": {
                    "completed_tool_actions": completed_tool_actions,
                    "collab_tool_calls": 0,
                    "spawned_subagents": 0,
                    "max_observed_concurrent_subagents": 0,
                    "progress_events": 0,
                    "malformed_lines": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    github.issue_comment_map[241] = [
        {
            "id": 2,
            "created_at": "2026-09-27T00:01:00Z",
            "user": {"login": "owner"},
            "body": render_control_state_comment(
                control_state_payload(
                    task_id="241",
                    state="blocked",
                    issue_number=241,
                    branch=branch,
                    blocker="worker exited with code 2",
                )
            ),
        }
    ]
    if advance_master:
        (root / "controller-fix.txt").write_text(
            "merged controller remediation\n", encoding="utf-8"
        )
        _git(root, "add", "controller-fix.txt")
        _git(root, "commit", "-m", "[Controller] Merge startup fix")
        _git(root, "push", "origin", "master")
        controller.repository.fetch_origin_master(cwd=root, prune=False)
        github.master_sha = controller.repository.ref("origin/master")
    return worker_state_path


def _record_guard_budget_failure(
    controller: Any,
    root: Path,
    github: FakeGitHub,
    branch: str,
    worktree: Path,
    *,
    worker_state_present: bool = False,
    filter_attempt: bool = False,
    reason: str = "owner-authorized resume after tool-budget interruption",
) -> tuple[Path, Path, Path, str]:
    controller.store._pid_is_alive = lambda _pid: False
    controller.resume_preimplementation(
        "241",
        control_issue_number=241,
        reason=reason,
        owner_authorize=True,
    )
    first_claim = controller.claim_preimplementation_worker_launch("241")[
        "preimplementation_resume"
    ]
    first_worker_state = (
        root
        / ".artifacts"
        / "tasks"
        / "241"
        / "temporary"
        / "delivery"
        / "prestart-attempt"
        / "worker-state.json"
    )
    controller.release_preimplementation_worker_launch(
        "241",
        launch_id=first_claim["launch_id"],
        worker_state_path=first_worker_state,
        reason="guarded supervisor failed before worker start",
    )
    controller.claim_preimplementation_worker_launch("241")
    attempt_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-delivery"
    attempt_root = root / ".artifacts" / "tasks" / "241" / "temporary" / "delivery" / attempt_id
    attempt_root.mkdir(parents=True)
    worker_state_path = attempt_root / "worker-state.json"
    worker_state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "pid": 701,
                "process_group_id": None,
                "process_instance": {"kind": "test", "instance": "supervisor"},
                "started_at": task_session.utc_now(),
                "command_process": {
                    "pid": 702,
                    "process_instance": {"kind": "test", "instance": "codex"},
                },
                "command_started_at": task_session.utc_now(),
            }
        ),
        encoding="utf-8",
    )
    controller.record_preimplementation_worker_started("241", worker_state_path=worker_state_path)
    if not worker_state_present:
        worker_state_path.unlink()

    (worktree / "README.md").write_text("guarded implementation\n", encoding="utf-8")
    (worktree / "new-module.py").write_text("value = 1\n", encoding="utf-8")
    _git(worktree, "add", "README.md")
    if filter_attempt:
        (worktree / ".gitattributes").write_text("*.filtered filter=guard-test\n", encoding="utf-8")
        (worktree / "new.filtered").write_text(
            "checkpoint without running filters\n", encoding="utf-8"
        )
        _git(worktree, "config", "filter.guard-test.clean", "exit 1")
    events_path = attempt_root / "events.jsonl"
    limits = {
        "max_completed_tool_actions": 240,
        "max_collab_tool_calls": 10,
        "max_spawned_subagents": 2,
        "max_concurrent_subagents": 2,
        "max_identical_failed_actions": 4,
        "max_identical_actions_without_progress": 8,
        "short_cycle_period_max": 3,
        "short_cycle_repetitions": 4,
    }
    events = "".join(
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": f"guard-test-action-{action_number}",
                    "status": "completed",
                },
            }
        )
        + "\n"
        for action_number in range(1, 242)
    )
    events_path.write_text(events, encoding="utf-8")
    guard = task_session.WorkerEventGuard(task_session.GuardLimits.from_mapping(limits))
    for line in events.splitlines(keepends=True):
        guard.observe_line(line)
    guard_path = attempt_root / "worker-guard.json"
    guard_path.write_text(json.dumps(guard.report()), encoding="utf-8")
    github.issue_comment_map[241] = [
        {
            "id": 3,
            "created_at": task_session.utc_now(),
            "user": {"login": "owner"},
            "body": render_control_state_comment(
                control_state_payload(
                    task_id="241",
                    state="blocked",
                    issue_number=241,
                    branch=branch,
                    blocker=(
                        "worker guard blocked execution (TOOL_ACTION_BUDGET_EXCEEDED); "
                        f"inspect {guard_path}"
                    ),
                )
            ),
        }
    ]
    return worker_state_path, guard_path, events_path, attempt_id


def _record_post_start_transport_failure(
    controller: Any,
    root: Path,
    github: FakeGitHub,
    branch: str,
    worktree: Path,
    *,
    reason: str = "owner-authorized resume after tool-budget interruption",
) -> tuple[Path, Path, Path, str]:
    _record_guard_budget_failure(controller, root, github, branch, worktree, reason=reason)
    controller.resume_guard_interrupted(
        "241",
        control_issue_number=241,
        reason=reason,
        owner_authorize=True,
    )
    github.issue_comment_map[241] = [
        {
            "id": 4,
            "created_at": task_session.utc_now(),
            "user": {"login": "owner"},
            "body": render_control_state_comment(
                control_state_payload(
                    task_id="241",
                    state="human_required",
                    issue_number=241,
                    branch=branch,
                    blocker=task_session.GUARD_RECOVERY_HANDOFF_BLOCKER,
                )
            ),
        }
    ]
    claimed = controller.claim_preimplementation_worker_launch("241")["preimplementation_resume"]
    attempt_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-delivery"
    attempt_root = root / ".artifacts" / "tasks" / "241" / "temporary" / "delivery" / attempt_id
    attempt_root.mkdir(parents=True)
    worker_state_path = attempt_root / "worker-state.json"
    worker_state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "pid": 901,
                "process_group_id": None,
                "process_instance": {"kind": "test", "instance": "supervisor"},
                "started_at": task_session.utc_now(),
                "command_process": {
                    "pid": 902,
                    "process_instance": {"kind": "test", "instance": "codex"},
                },
                "command_started_at": task_session.utc_now(),
            }
        ),
        encoding="utf-8",
    )
    controller.record_preimplementation_worker_started("241", worker_state_path=worker_state_path)
    worker_state_path.unlink()

    (worktree / "README.md").write_text("transport implementation\n", encoding="utf-8")
    (worktree / "transport-new.py").write_text("value = 2\n", encoding="utf-8")
    _git(worktree, "add", "README.md")

    limits = {
        "max_completed_tool_actions": 240,
        "max_collab_tool_calls": 10,
        "max_spawned_subagents": 2,
        "max_concurrent_subagents": 2,
        "max_identical_failed_actions": 4,
        "max_identical_actions_without_progress": 8,
        "short_cycle_period_max": 3,
        "short_cycle_repetitions": 4,
    }
    events = [
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": "transport-test-action-1",
                    "status": "completed",
                },
            }
        ),
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "type": "file_change",
                    "status": "completed",
                    "changes": ["README.md"],
                },
            }
        ),
        json.dumps(
            {
                "type": "error",
                "message": "Connection failed: error sending request (os error 11001)",
            }
        ),
        json.dumps(
            {
                "type": "turn.failed",
                "error": {"message": "Error running remote compact task: Connection failed"},
            }
        ),
    ]
    events_path = attempt_root / "events.jsonl"
    events_path.write_text("\n".join(events) + "\n", encoding="utf-8")
    guard = task_session.WorkerEventGuard(task_session.GuardLimits.from_mapping(limits))
    for line in events_path.read_text(encoding="utf-8").splitlines(keepends=True):
        guard.observe_line(line)
    guard_path = attempt_root / "worker-guard.json"
    guard_path.write_text(json.dumps(guard.report()), encoding="utf-8")
    assert guard.report()["blocked"] is False
    assert guard.report()["counters"]["completed_tool_actions"] > 0
    assert guard.report()["counters"]["progress_events"] > 0

    github.issue_comment_map[241] = [
        {
            "id": 5,
            "created_at": task_session.utc_now(),
            "user": {"login": "owner"},
            "body": render_control_state_comment(
                control_state_payload(
                    task_id="241",
                    state="human_required",
                    issue_number=241,
                    branch=branch,
                    blocker=(
                        f"worker stopped after {task_session.POST_START_TRANSPORT_FAILURE_KIND}; "
                        f"inspect {events_path}"
                    ),
                )
            ),
        }
    ]
    assert claimed["state"] == "launching"
    return worker_state_path, guard_path, events_path, attempt_id


def test_task_session_exposes_generic_worker_resume_alias() -> None:
    args = task_session._parser().parse_args(
        [
            "retry-worker",
            "241",
            "--control-issue",
            "241",
            "--reason",
            "owner-authorized generic worker retry",
            "--owner-authorize",
        ]
    )

    assert args.command == "retry-worker"
    assert args.control_issue == 241
    assert args.owner_authorize is True


def test_task_session_exposes_guard_interrupted_resume_command() -> None:
    args = task_session._parser().parse_args(
        [
            "resume-guard-interrupted",
            "241",
            "--control-issue",
            "241",
            "--reason",
            "owner-authorized resume after guard stop",
            "--owner-authorize",
        ]
    )

    assert args.command == "resume-guard-interrupted"
    assert args.control_issue == 241
    assert args.owner_authorize is True


def test_task_session_exposes_transport_interrupted_resume_command() -> None:
    args = task_session._parser().parse_args(
        [
            "resume-transport-interrupted",
            "241",
            "--control-issue",
            "241",
            "--reason",
            "owner-authorized one-time post-start transport recovery",
            "--owner-authorize",
        ]
    )

    assert args.command == "resume-transport-interrupted"
    assert args.control_issue == 241
    assert args.owner_authorize is True


def test_guard_interrupted_resume_checkpoints_and_preserves_wip(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository, controller, worktree, branch, _, github = (
        _prepare_preimplementation_resume(repository)
    )
    worker_state_path, guard_path, events_path, attempt_id = _record_guard_budget_failure(
        controller, root, github, branch, worktree
    )
    before_head = git_repository.head(cwd=worktree)
    before_status = git_repository.status(worktree)
    lease_path = controller.store.task_lease_path("241")
    before_lease = controller.store.read_json(lease_path)

    resumed = controller.resume_guard_interrupted(
        "241",
        control_issue_number=241,
        reason="owner-authorized resume after tool-budget interruption",
        owner_authorize=True,
    )

    event = resumed["preimplementation_resume"]
    checkpoint = event["guard_budget_recovery"]
    checkpoint_ref = checkpoint["checkpoint_ref"]
    checkpoint_commit = checkpoint["checkpoint_commit"]
    assert resumed["mutation_performed"] is True
    assert resumed["control_state"]["state"] == "blocked"
    assert event["state"] == "prepared"
    assert (
        event["launch_attempts"][0]
        == before_lease["preimplementation_resume"]["launch_attempts"][0]
    )
    assert event["launch_attempts"][1]["state"] == "failed-guard-budget"
    assert event["launch_attempts"][1]["failure_evidence"]["guard_report_path"] == str(guard_path)
    assert checkpoint["task_id"] == "241"
    assert checkpoint["attempt_id"] == attempt_id
    assert checkpoint["recovery_attempt_number"] == 1
    assert checkpoint["base_sha"] == before_head
    assert checkpoint["head_sha"] == before_head
    assert checkpoint["guard_stop_reason"] == "TOOL_ACTION_BUDGET_EXCEEDED"
    assert checkpoint["guard_report_path"] == str(guard_path.resolve())
    assert checkpoint["events_path"] == str(events_path.resolve())
    assert set(checkpoint["changed_paths"]) == {"README.md", "new-module.py"}
    assert git_repository.ref(checkpoint_ref) == checkpoint_commit
    assert _git(worktree, "show", f"{checkpoint_ref}:README.md") == "guarded implementation"
    assert _git(worktree, "show", f"{checkpoint_ref}:new-module.py") == "value = 1"
    patch = subprocess.run(
        ["git", "diff", "--binary", "--no-ext-diff", before_head, checkpoint_commit],
        cwd=worktree,
        check=True,
        capture_output=True,
    ).stdout
    assert hashlib.sha256(patch).hexdigest() == checkpoint["patch_sha256"]
    assert git_repository.head(cwd=worktree) == before_head
    assert git_repository.status(worktree) == before_status
    assert (
        controller.store.read_json(lease_path)["preimplementation_resume"]["launch_attempts"][:1]
        == before_lease["preimplementation_resume"]["launch_attempts"][:1]
    )
    assert not worker_state_path.exists()


def test_guard_checkpoint_does_not_execute_git_clean_filters(
    repository: tuple[Path, Any],
) -> None:
    root, _, controller, worktree, branch, _, github = _prepare_preimplementation_resume(repository)
    _record_guard_budget_failure(controller, root, github, branch, worktree, filter_attempt=True)

    resumed = controller.resume_guard_interrupted(
        "241",
        control_issue_number=241,
        reason="owner-authorized resume after tool-budget interruption",
        owner_authorize=True,
    )

    checkpoint = resumed["preimplementation_resume"]["guard_budget_recovery"]
    assert _git(worktree, "show", f"{checkpoint['checkpoint_ref']}:new.filtered") == (
        "checkpoint without running filters"
    )


def test_guard_interrupted_resume_allows_known_generated_cache(
    repository: tuple[Path, Any],
) -> None:
    root, _, controller, worktree, branch, _, github = _prepare_preimplementation_resume(repository)
    _record_guard_budget_failure(controller, root, github, branch, worktree)
    cache_path = worktree / "__pycache__" / "generated.cpython-314.pyc"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_bytes(b"generated cache")
    excludes = root.parent / "cache-excludes"
    excludes.write_text("__pycache__/\n", encoding="utf-8")
    _git(worktree, "config", "core.excludesfile", str(excludes))

    resumed = controller.resume_guard_interrupted(
        "241",
        control_issue_number=241,
        reason="owner-authorized resume after tool-budget interruption",
        owner_authorize=True,
    )

    assert resumed["mutation_performed"] is True


def test_guard_ignored_paths_accepts_canonical_managed_paths(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    controller = task_session.TaskController(
        git_repository,
        github=FakeGitHub(git_repository.ref("origin/master")),
    )
    frontend = root / "frontend"
    (frontend / "node_modules" / "some-package").mkdir(parents=True)
    (frontend / "node_modules" / "some-package" / "file.js").write_text(
        "generated\n", encoding="utf-8"
    )
    (frontend / "openapi.json").write_text("{}\n", encoding="utf-8")
    (frontend / "dist" / "assets").mkdir(parents=True)
    (frontend / ".pytest_cache" / "v" / "cache").mkdir(parents=True)
    excludes = root.parent / "canonical-managed-excludes"
    excludes.write_text(
        "frontend/node_modules/\n/frontend/openapi.json\nfrontend/dist/\nfrontend/.pytest_cache/\n",
        encoding="utf-8",
    )
    _git(root, "config", "core.excludesfile", str(excludes))

    assert controller._guard_ignored_paths(root) == []


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("frontend/node_modules/", True),
        ("FRONTEND\\NODE_MODULES\\some-package\\file.js", True),
        ("frontend/dist/assets/manifest.js", True),
        ("frontend/.pytest_cache/v/cache/nodeids", True),
        ("frontend/openapi.json", True),
        ("frontend/node_modules-evil/", False),
        ("frontend/node_modules_backup/", False),
        ("frontend/openapi.json.bak", False),
        ("frontend/openapi.json/anything", False),
        ("frontend/random-secret.txt", False),
        ("tmp/private-data/", False),
        ("../frontend/node_modules/file.js", False),
        ("C:\\repo\\frontend\\node_modules\\file.js", False),
    ],
)
def test_canonical_managed_ignored_path_boundaries(
    tmp_path: Path,
    path: str,
    expected: bool,
) -> None:
    (tmp_path / "frontend" / "node_modules" / "some-package").mkdir(parents=True)
    (tmp_path / "frontend" / "dist").mkdir(parents=True)
    (tmp_path / "frontend" / ".pytest_cache" / "v" / "cache").mkdir(parents=True)
    (tmp_path / "frontend" / "openapi.json").write_text("{}\n", encoding="utf-8")

    assert task_session._is_canonical_managed_ignored_path(path, root=tmp_path) is expected


def test_canonical_refresh_reuses_managed_ignored_path_semantics(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    controller = task_session.TaskController(
        git_repository,
        github=FakeGitHub(git_repository.ref("origin/master")),
    )
    frontend = root / "frontend"
    (frontend / "node_modules" / "some-package").mkdir(parents=True)
    (frontend / "node_modules" / "some-package" / "file.js").write_text(
        "generated\n", encoding="utf-8"
    )
    (frontend / "openapi.json").write_text("{}\n", encoding="utf-8")
    excludes = root.parent / "canonical-refresh-excludes"
    excludes.write_text(
        "frontend/node_modules/\n/frontend/openapi.json\n",
        encoding="utf-8",
    )
    _git(root, "config", "core.excludesfile", str(excludes))

    assert controller._canonical_worktree_status(root) == []


def test_post_start_transport_resume_accepts_canonical_managed_paths(
    repository: tuple[Path, Any],
) -> None:
    root, _, controller, worktree, branch, _, github = _prepare_preimplementation_resume(repository)
    _record_post_start_transport_failure(controller, root, github, branch, worktree)
    frontend = worktree / "frontend"
    (frontend / "node_modules" / "some-package").mkdir(parents=True)
    (frontend / "node_modules" / "some-package" / "file.js").write_text(
        "generated\n", encoding="utf-8"
    )
    (frontend / "openapi.json").write_text("{}\n", encoding="utf-8")
    excludes = root.parent / "canonical-transport-excludes"
    excludes.write_text(
        "frontend/node_modules/\n/frontend/openapi.json\n",
        encoding="utf-8",
    )
    _git(worktree, "config", "core.excludesfile", str(excludes))

    resumed = controller.resume_transport_interrupted(
        "241",
        control_issue_number=241,
        reason="owner-authorized one-time post-start transport recovery",
        owner_authorize=True,
    )

    assert resumed["mutation_performed"] is True


def test_guard_interrupted_resume_accepts_prior_base_refresh_anchor(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository, controller, worktree, branch, _, github = (
        _prepare_preimplementation_resume(repository)
    )
    _record_guard_budget_failure(controller, root, github, branch, worktree)
    lease_path = controller.store.task_lease_path("241")
    lease = controller.store.read_json(lease_path)
    current_base = str(lease["base_origin_master_sha"])
    original_base = "a" * 40
    event = lease["preimplementation_resume"]
    lease["original_base_origin_master_sha"] = original_base
    event["original_base_sha"] = original_base
    event["base_sha"] = current_base
    event["head_sha"] = current_base
    event["base_refreshes"] = [
        {
            "from_base_sha": original_base,
            "from_head_sha": original_base,
            "to_base_sha": current_base,
        }
    ]
    task_session.StateStore.replace_json(lease_path, lease)

    resumed = controller.resume_guard_interrupted(
        "241",
        control_issue_number=241,
        reason="owner-authorized resume after tool-budget interruption",
        owner_authorize=True,
    )

    assert resumed["mutation_performed"] is True
    assert resumed["preimplementation_resume"]["guard_budget_recovery"]["base_sha"] == current_base
    assert git_repository.head(cwd=worktree) == current_base


def test_guard_interrupted_resume_reconciles_windows_command_line_failure(
    repository: tuple[Path, Any],
) -> None:
    root, _, controller, worktree, branch, _, github = _prepare_preimplementation_resume(repository)
    _record_guard_budget_failure(controller, root, github, branch, worktree)
    kwargs = {
        "control_issue_number": 241,
        "reason": "owner-authorized resume after tool-budget interruption",
        "owner_authorize": True,
    }
    controller.resume_guard_interrupted("241", **kwargs)
    claimed = controller.claim_preimplementation_worker_launch("241")["preimplementation_resume"]
    attempt_root = (
        root
        / ".artifacts"
        / "tasks"
        / "241"
        / "temporary"
        / "delivery"
        / "windows-command-line-attempt"
    )
    attempt_root.mkdir(parents=True)
    worker_state_path = attempt_root / "worker-state.json"
    worker_state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "pid": 801,
                "process_group_id": None,
                "process_instance": {"kind": "test", "instance": "supervisor"},
                "started_at": "2026-09-27T00:00:00Z",
                "command_process": {
                    "pid": 802,
                    "process_instance": {"kind": "test", "instance": "codex"},
                },
                "command_started_at": "2026-09-27T00:00:01Z",
            }
        ),
        encoding="utf-8",
    )
    controller.record_preimplementation_worker_started("241", worker_state_path=worker_state_path)
    worker_state_path.unlink()
    (attempt_root / "events.jsonl").write_text("The command line is too long.\n", encoding="utf-8")
    (attempt_root / "worker-guard.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "classification": "yfc-worker-guard-report",
                "blocked": False,
                "block_reason_code": None,
                "counters": {
                    "completed_tool_actions": 0,
                    "collab_tool_calls": 0,
                    "spawned_subagents": 0,
                    "max_observed_concurrent_subagents": 0,
                    "progress_events": 0,
                    "malformed_lines": 1,
                },
            }
        ),
        encoding="utf-8",
    )

    resumed = controller.resume_guard_interrupted("241", **kwargs)

    event = resumed["preimplementation_resume"]
    assert resumed["mutation_performed"] is True
    assert event["state"] == "prepared"
    assert event["last_preimplementation_failure"]["kind"] == (
        "windows_command_line_too_long_before_implementation"
    )
    assert event["launch_attempts"][-1]["state"] == "failed-before-implementation"
    assert event["launch_attempts"][-1]["launch_id"] == claimed["launch_id"]
    repeated = controller.resume_guard_interrupted("241", **kwargs)
    assert repeated["mutation_performed"] is False


def test_post_start_transport_resume_does_not_use_windows_startup_recovery(
    repository: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _, controller, worktree, branch, _, github = _prepare_preimplementation_resume(repository)
    reason = "owner-authorized one-time post-start transport recovery"
    _record_post_start_transport_failure(
        controller,
        root,
        github,
        branch,
        worktree,
        reason="owner-authorized resume after tool-budget interruption",
    )

    monkeypatch.setattr(
        controller,
        "_preimplementation_windows_command_line_failure_evidence",
        lambda *_args: pytest.fail(
            "post-start transport recovery must not use Windows startup evidence"
        ),
    )

    resumed = controller.resume_transport_interrupted(
        "241",
        control_issue_number=241,
        reason=reason,
        owner_authorize=True,
    )

    event = resumed["preimplementation_resume"]
    attempt = event["launch_attempts"][-1]
    recovery = event["transport_interruption_recovery"]
    assert resumed["mutation_performed"] is True
    assert event["state"] == "prepared"
    assert attempt["state"] == "failed-post-start-transport"
    assert attempt["failure_kind"] == task_session.POST_START_TRANSPORT_FAILURE_KIND
    assert recovery["recovery_attempt_number"] == 1
    assert recovery["transport_failure_kind"] == task_session.POST_START_TRANSPORT_FAILURE_KIND
    assert recovery["completed_tool_actions"] > 0
    assert recovery["checkpoint_ref"].startswith("refs/codex/task-wip-checkpoints/task-241/")

    with pytest.raises(task_session.TaskSessionError, match="post-start external transport"):
        controller.resume_guard_interrupted(
            "241",
            control_issue_number=241,
            reason="owner-authorized resume after tool-budget interruption",
            owner_authorize=True,
        )


def test_post_start_transport_resume_refuses_ambiguous_evidence_without_mutation(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository, controller, worktree, branch, _, github = (
        _prepare_preimplementation_resume(repository)
    )
    _, guard_path, events_path, _ = _record_post_start_transport_failure(
        controller,
        root,
        github,
        branch,
        worktree,
    )
    events_path.write_text(
        '{"type":"turn.failed","error":{"message":"unknown"}}\n', encoding="utf-8"
    )
    guard = json.loads(guard_path.read_text(encoding="utf-8"))
    guard["counters"]["completed_tool_actions"] = 0
    guard["counters"]["progress_events"] = 0
    guard_path.write_text(json.dumps(guard), encoding="utf-8")
    lease_path = controller.store.task_lease_path("241")
    before = controller.store.read_json(lease_path)
    before_head = git_repository.head(cwd=worktree)

    with pytest.raises(task_session.TaskSessionError, match="ambiguous"):
        controller.resume_transport_interrupted(
            "241",
            control_issue_number=241,
            reason="owner-authorized one-time post-start transport recovery",
            owner_authorize=True,
        )

    assert controller.store.read_json(lease_path) == before
    assert git_repository.head(cwd=worktree) == before_head


def test_post_start_transport_resume_budget_is_independent_and_bounded(
    repository: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _, controller, worktree, branch, _, github = _prepare_preimplementation_resume(repository)
    _record_post_start_transport_failure(controller, root, github, branch, worktree)
    reason = "owner-authorized one-time post-start transport recovery"
    first = controller.resume_transport_interrupted(
        "241",
        control_issue_number=241,
        reason=reason,
        owner_authorize=True,
    )
    assert (
        first["preimplementation_resume"]["guard_budget_recovery"]["recovery_attempt_number"] == 1
    )

    github.issue_comment_map[241] = [
        {
            "id": 6,
            "created_at": task_session.utc_now(),
            "user": {"login": "owner"},
            "body": render_control_state_comment(
                control_state_payload(
                    task_id="241",
                    state="human_required",
                    issue_number=241,
                    branch=branch,
                    blocker=task_session.POST_START_TRANSPORT_HANDOFF_BLOCKER,
                )
            ),
        }
    ]
    claimed = controller.claim_preimplementation_worker_launch("241")["preimplementation_resume"]
    assert claimed["state"] == "launching"
    lease = controller.store.read_json(controller.store.task_lease_path("241"))
    attempt_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-delivery"
    attempt_root = root / ".artifacts" / "tasks" / "241" / "temporary" / "delivery" / attempt_id
    attempt_root.mkdir(parents=True)
    worker_state_path = attempt_root / "worker-state.json"
    worker_state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "pid": 903,
                "process_group_id": None,
                "process_instance": {"kind": "test", "instance": "supervisor"},
                "started_at": task_session.utc_now(),
                "command_process": {
                    "pid": 904,
                    "process_instance": {"kind": "test", "instance": "codex"},
                },
                "command_started_at": task_session.utc_now(),
            }
        ),
        encoding="utf-8",
    )
    controller.record_preimplementation_worker_started("241", worker_state_path=worker_state_path)
    worker_state_path.unlink()
    (worktree / "transport-second.py").write_text("value = 3\n", encoding="utf-8")
    _git(worktree, "add", "transport-second.py")
    events_path = attempt_root / "events.jsonl"
    events_path.write_text(
        '{"type":"item.completed","item":{"type":"command_execution","command":"second","status":"completed"}}\n'
        '{"type":"item.completed","item":{"type":"file_change","status":"completed","changes":["transport-second.py"]}}\n'
        '{"type":"error","message":"Connection failed: error sending request (os error 11001)"}\n',
        encoding="utf-8",
    )
    limits = {
        "max_completed_tool_actions": 240,
        "max_collab_tool_calls": 10,
        "max_spawned_subagents": 2,
        "max_concurrent_subagents": 2,
        "max_identical_failed_actions": 4,
        "max_identical_actions_without_progress": 8,
        "short_cycle_period_max": 3,
        "short_cycle_repetitions": 4,
    }
    guard = task_session.WorkerEventGuard(task_session.GuardLimits.from_mapping(limits))
    for line in events_path.read_text(encoding="utf-8").splitlines(keepends=True):
        guard.observe_line(line)
    (attempt_root / "worker-guard.json").write_text(json.dumps(guard.report()), encoding="utf-8")
    github.issue_comment_map[241] = [
        {
            "id": 7,
            "created_at": task_session.utc_now(),
            "user": {"login": "owner"},
            "body": render_control_state_comment(
                control_state_payload(
                    task_id="241",
                    state="human_required",
                    issue_number=241,
                    branch=branch,
                    blocker=(
                        f"worker stopped after {task_session.POST_START_TRANSPORT_FAILURE_KIND}; "
                        f"inspect {events_path}"
                    ),
                )
            ),
        }
    ]
    monkeypatch.setattr(controller.store, "_pid_is_alive", lambda _pid: False)
    before = controller.store.read_json(controller.store.task_lease_path("241"))

    with pytest.raises(
        task_session.TaskSessionError, match="transport retry budget was already used"
    ):
        controller.resume_transport_interrupted(
            "241",
            control_issue_number=241,
            reason=reason,
            owner_authorize=True,
        )

    assert controller.store.read_json(controller.store.task_lease_path("241")) == before
    assert (
        lease["preimplementation_resume"]["transport_interruption_recovery"][
            "recovery_attempt_number"
        ]
        == 1
    )


def test_post_start_transport_resume_refuses_live_worker_without_mutation(
    repository: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _, controller, worktree, branch, _, github = _prepare_preimplementation_resume(repository)
    _record_post_start_transport_failure(controller, root, github, branch, worktree)
    lease_path = controller.store.task_lease_path("241")
    before = controller.store.read_json(lease_path)
    monkeypatch.setattr(controller.store, "_pid_is_alive", lambda _pid: True)

    with pytest.raises(task_session.TaskSessionError, match="worker is still live"):
        controller.resume_transport_interrupted(
            "241",
            control_issue_number=241,
            reason="owner-authorized one-time post-start transport recovery",
            owner_authorize=True,
        )

    assert controller.store.read_json(lease_path) == before


def test_post_start_transport_resume_refuses_external_wip_mutation(
    repository: tuple[Path, Any],
) -> None:
    root, _, controller, worktree, branch, _, github = _prepare_preimplementation_resume(repository)
    _, guard_path, _, _ = _record_post_start_transport_failure(
        controller, root, github, branch, worktree
    )
    (worktree / "transport-new.py").write_text("mutated after worker stop\n", encoding="utf-8")
    report_mtime_ns = guard_path.stat().st_mtime_ns
    os.utime(worktree / "transport-new.py", ns=(report_mtime_ns + 1_000_000_000,) * 2)

    with pytest.raises(
        task_session.TaskSessionError, match="changed outside the transport attempt"
    ):
        controller.resume_transport_interrupted(
            "241",
            control_issue_number=241,
            reason="owner-authorized one-time post-start transport recovery",
            owner_authorize=True,
        )


def test_post_start_transport_resume_refuses_checkpoint_mismatch(
    repository: tuple[Path, Any],
) -> None:
    root, _, controller, worktree, branch, _, github = _prepare_preimplementation_resume(repository)
    _record_post_start_transport_failure(controller, root, github, branch, worktree)
    controller.resume_transport_interrupted(
        "241",
        control_issue_number=241,
        reason="owner-authorized one-time post-start transport recovery",
        owner_authorize=True,
    )
    lease_path = controller.store.task_lease_path("241")
    lease = controller.store.read_json(lease_path)
    lease["preimplementation_resume"]["transport_interruption_recovery"]["patch_sha256"] = "0" * 64
    task_session.StateStore.replace_json(lease_path, lease)

    with pytest.raises(task_session.TaskSessionError, match="checkpoint"):
        controller.claim_preimplementation_worker_launch("241")

    assert (
        controller.store.read_json(lease_path)["preimplementation_resume"][
            "transport_interruption_recovery"
        ]["patch_sha256"]
        == "0" * 64
    )


def test_guard_interrupted_resume_is_idempotent_and_claim_requires_checkpoint(
    repository: tuple[Path, Any],
) -> None:
    root, _, controller, worktree, branch, _, github = _prepare_preimplementation_resume(repository)
    _record_guard_budget_failure(controller, root, github, branch, worktree)
    kwargs = {
        "control_issue_number": 241,
        "reason": "owner-authorized resume after tool-budget interruption",
        "owner_authorize": True,
    }

    first = controller.resume_guard_interrupted("241", **kwargs)
    repeated = controller.resume_guard_interrupted("241", **kwargs)

    assert first["mutation_performed"] is True
    assert repeated["mutation_performed"] is False
    assert (
        repeated["preimplementation_resume"]["guard_budget_recovery"]
        == (first["preimplementation_resume"]["guard_budget_recovery"])
    )
    github.issue_comment_map[241].append(
        {
            "id": 4,
            "created_at": task_session.utc_now(),
            "user": {"login": "owner"},
            "body": render_control_state_comment(
                control_state_payload(
                    task_id="241",
                    state="human_required",
                    issue_number=241,
                    branch=branch,
                    blocker=task_session.GUARD_RECOVERY_HANDOFF_BLOCKER,
                )
            ),
        }
    )
    repeated_after_handoff = controller.resume_guard_interrupted("241", **kwargs)
    assert repeated_after_handoff["mutation_performed"] is False
    claimed = controller.claim_preimplementation_worker_launch("241")
    assert claimed["preimplementation_resume"]["state"] == "launching"
    with pytest.raises(task_session.TaskSessionError, match="unclaimed prepared resume"):
        controller.claim_preimplementation_worker_launch("241")


@pytest.mark.parametrize(
    "failure",
    ["live-worker", "missing-report", "mismatched-report", "post-stop-file", "conflicting-pr"],
)
def test_guard_interrupted_resume_fails_closed_without_mutating_task(
    repository: tuple[Path, Any],
    failure: str,
) -> None:
    root, _, controller, worktree, branch, _, github = _prepare_preimplementation_resume(repository)
    worker_state_path, guard_path, _, _ = _record_guard_budget_failure(
        controller,
        root,
        github,
        branch,
        worktree,
        worker_state_present=failure == "live-worker",
    )
    if failure == "missing-report":
        guard_path.unlink()
        message = "evidence"
    elif failure == "mismatched-report":
        guard = json.loads(guard_path.read_text(encoding="utf-8"))
        guard["block_reason_code"] = "SHORT_CYCLE"
        guard_path.write_text(json.dumps(guard), encoding="utf-8")
        message = "Guard report"
    elif failure == "live-worker":
        controller.store._pid_is_alive = lambda _pid: True
        message = "worker"
    elif failure == "conflicting-pr":
        github.open_prs = [{"head": {"ref": branch}}]
        message = "pull request"
    else:
        external_path = worktree / "external-after-stop.txt"
        external_path.write_text("not from the guarded attempt\n", encoding="utf-8")
        stopped_ns = guard_path.stat().st_mtime_ns
        os.utime(external_path, ns=(stopped_ns + 5_000_000_000,) * 2)
        message = "attempt"
    lease_path = controller.store.task_lease_path("241")
    before_lease = controller.store.read_json(lease_path)
    before_head = controller.repository.head(cwd=worktree)
    with pytest.raises(task_session.TaskSessionError, match=message):
        controller.resume_guard_interrupted(
            "241",
            control_issue_number=241,
            reason="owner-authorized resume after tool-budget interruption",
            owner_authorize=True,
        )
    assert controller.store.read_json(lease_path) == before_lease
    assert controller.repository.head(cwd=worktree) == before_head
    assert worker_state_path.exists() is (failure == "live-worker")


@pytest.mark.parametrize("invalid_identity", ["branch", "worktree", "dependencies", "shared-lease"])
def test_guard_interrupted_resume_refuses_invalid_task_identity_without_mutation(
    repository: tuple[Path, Any],
    invalid_identity: str,
) -> None:
    root, _, controller, worktree, branch, _, github = _prepare_preimplementation_resume(repository)
    _record_guard_budget_failure(controller, root, github, branch, worktree)
    lease_path = controller.store.task_lease_path("241")
    lease = controller.store.read_json(lease_path)
    if invalid_identity == "branch":
        lease["branch"] = "task/242-different-task"
        task_session.StateStore.replace_json(lease_path, lease)
        message = "branch"
    elif invalid_identity == "worktree":
        lease["worktree"] = str(root / "unregistered-worktree")
        task_session.StateStore.replace_json(lease_path, lease)
        message = "branch|worktree"
    elif invalid_identity == "shared-lease":
        duplicate = {**lease, "task_id": "242"}
        task_session.StateStore.replace_json(controller.store.task_lease_path("242"), duplicate)
        message = "shares this task branch"
    else:
        github.issues[241]["body"] = render_task_contract(
            {
                "version": 1,
                "task_id": "241",
                "scope": "Synthetic pre-implementation recovery",
                "acceptance": ["resume safely"],
                "dependencies": ["242"],
                "owner_gate": "explicit-launch",
                "risk_lane": "GREEN",
                "source_spec": "codex-backlog/tasks/241-resume-me.md",
                "issue_state": "in_progress",
            }
        )
        message = "dependency"
    before_lease = controller.store.read_json(lease_path)

    with pytest.raises(task_session.TaskSessionError, match=message):
        controller.resume_guard_interrupted(
            "241",
            control_issue_number=241,
            reason="owner-authorized resume after tool-budget interruption",
            owner_authorize=True,
        )

    assert controller.store.read_json(lease_path) == before_lease


def test_guard_interrupted_resume_refuses_active_queue_claim_without_mutation(
    repository: tuple[Path, Any],
) -> None:
    root, _, controller, worktree, branch, _, github = _prepare_preimplementation_resume(repository)
    _record_guard_budget_failure(controller, root, github, branch, worktree)
    claim_path = controller.store.root / "continuous-queue.lock"
    claim_path.write_text(
        json.dumps({"queue_phase": "task_running", "task_id": "241"}), encoding="utf-8"
    )
    lease_path = controller.store.task_lease_path("241")
    before_lease = controller.store.read_json(lease_path)

    with pytest.raises(task_session.TaskSessionError, match="queue claim"):
        controller.resume_guard_interrupted(
            "241",
            control_issue_number=241,
            reason="owner-authorized resume after tool-budget interruption",
            owner_authorize=True,
        )

    assert controller.store.read_json(lease_path) == before_lease


def test_guard_interrupted_resume_claim_refuses_changed_checkpoint(
    repository: tuple[Path, Any],
) -> None:
    root, _, controller, worktree, branch, _, github = _prepare_preimplementation_resume(repository)
    _record_guard_budget_failure(controller, root, github, branch, worktree)
    controller.resume_guard_interrupted(
        "241",
        control_issue_number=241,
        reason="owner-authorized resume after tool-budget interruption",
        owner_authorize=True,
    )
    lease_path = controller.store.task_lease_path("241")
    before = controller.store.read_json(lease_path)
    (worktree / "README.md").write_text("changed after checkpoint\n", encoding="utf-8")

    with pytest.raises(task_session.TaskSessionError, match="checkpoint"):
        controller.claim_preimplementation_worker_launch("241")

    assert controller.store.read_json(lease_path) == before


def test_guard_interrupted_resume_claim_refuses_changed_evidence(
    repository: tuple[Path, Any],
) -> None:
    root, _, controller, worktree, branch, _, github = _prepare_preimplementation_resume(repository)
    _, guard_path, _, _ = _record_guard_budget_failure(controller, root, github, branch, worktree)
    controller.resume_guard_interrupted(
        "241",
        control_issue_number=241,
        reason="owner-authorized resume after tool-budget interruption",
        owner_authorize=True,
    )
    lease_path = controller.store.task_lease_path("241")
    before = controller.store.read_json(lease_path)
    guard = json.loads(guard_path.read_text(encoding="utf-8"))
    guard["counters"]["completed_tool_actions"] += 1
    guard_path.write_text(json.dumps(guard), encoding="utf-8")

    with pytest.raises(task_session.TaskSessionError, match="evidence has changed"):
        controller.claim_preimplementation_worker_launch("241")

    assert controller.store.read_json(lease_path) == before


def test_guard_interrupted_resume_recovery_budget_is_exhausted_after_claim(
    repository: tuple[Path, Any],
) -> None:
    root, _, controller, worktree, branch, _, github = _prepare_preimplementation_resume(repository)
    _record_guard_budget_failure(controller, root, github, branch, worktree)
    kwargs = {
        "control_issue_number": 241,
        "reason": "owner-authorized resume after tool-budget interruption",
        "owner_authorize": True,
    }
    controller.resume_guard_interrupted("241", **kwargs)
    controller.claim_preimplementation_worker_launch("241")
    lease_path = controller.store.task_lease_path("241")
    before = controller.store.read_json(lease_path)

    with pytest.raises(task_session.TaskSessionError, match="already launched"):
        controller.resume_guard_interrupted("241", **kwargs)

    assert controller.store.read_json(lease_path) == before


def test_task_session_exposes_supported_preimplementation_resume_command() -> None:
    args = task_session._parser().parse_args(
        [
            "resume-preimplementation",
            "241",
            "--control-issue",
            "241",
            "--reason",
            "owner-authorized retry after resolved bootstrap failure",
            "--owner-authorize",
        ]
    )

    assert args.command == "resume-preimplementation"
    assert args.control_issue == 241
    assert args.owner_authorize is True


def test_resume_preimplementation_fast_forwards_and_preserves_attempt_audit(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository, controller, worktree, branch, original_base, github = (
        _prepare_preimplementation_resume(repository)
    )
    (root / "controller-fix.txt").write_text("resolved controller blocker\n", encoding="utf-8")
    _git(root, "add", "controller-fix.txt")
    _git(root, "commit", "-m", "[Controller] Resolve the worker bootstrap blocker")
    _git(root, "push", "origin", "master")
    git_repository.fetch_origin_master(cwd=root)
    current_master = git_repository.ref("origin/master")
    github.master_sha = current_master

    resumed = controller.resume_preimplementation(
        "241",
        control_issue_number=241,
        reason="owner-authorized retry after merged bootstrap fix",
        owner_authorize=True,
    )

    event = resumed["preimplementation_resume"]
    assert resumed["lease"]["original_base_origin_master_sha"] == original_base
    assert resumed["lease"]["base_origin_master_sha"] == current_master
    assert resumed["lease"]["lifecycle_state"] == "working"
    assert git_repository.head(cwd=worktree) == current_master
    assert git_repository.ref(branch) == current_master
    assert event["state"] == "prepared"
    assert event["original_base_sha"] == original_base
    assert event["previous_head_sha"] == original_base
    assert event["base_sha"] == current_master
    assert event["head_sha"] == current_master
    assert event["reason"] == "owner-authorized retry after merged bootstrap fix"
    assert "worker-state.json" in event["previous_control_state"]["blocker"]
    assert event["registered_at"] == resumed["lease"]["created_at"]
    repeated = controller.resume_preimplementation(
        "241",
        control_issue_number=241,
        reason="owner-authorized retry after merged bootstrap fix",
        owner_authorize=True,
    )
    assert repeated["mutation_performed"] is False
    assert repeated["preimplementation_resume"] == event
    claimed = controller.claim_preimplementation_worker_launch("241")
    assert claimed["preimplementation_resume"]["state"] == "launching"
    first_launch_id = claimed["preimplementation_resume"]["launch_id"]
    prestart_path = (
        root
        / ".artifacts"
        / "tasks"
        / "241"
        / "temporary"
        / "delivery"
        / "first-attempt"
        / "worker-state.json"
    )
    released = controller.release_preimplementation_worker_launch(
        "241",
        launch_id=first_launch_id,
        worker_state_path=prestart_path,
        reason="guarded worker supervisor exited before durable state",
    )
    assert released["preimplementation_resume"]["state"] == "prepared"
    assert released["preimplementation_resume"]["launch_attempts"][0]["state"] == (
        "no-worker-started"
    )
    claimed = controller.claim_preimplementation_worker_launch("241")
    assert claimed["preimplementation_resume"]["launch_attempts"][1]["state"] == "launching"

    worker_state_path = (
        root
        / ".artifacts"
        / "tasks"
        / "241"
        / "temporary"
        / "delivery"
        / "test-delivery"
        / "worker-state.json"
    )
    worker_state_path.parent.mkdir(parents=True)
    worker_state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "pid": 101,
                "process_group_id": None,
                "process_instance": {"kind": "test", "instance": "supervisor"},
                "started_at": "2026-09-27T00:00:00Z",
                "command_process": {
                    "pid": 102,
                    "process_instance": {"kind": "test", "instance": "codex"},
                },
                "command_started_at": "2026-09-27T00:00:01Z",
            }
        ),
        encoding="utf-8",
    )
    recorded = controller.record_preimplementation_worker_started(
        "241", worker_state_path=worker_state_path
    )
    assert recorded["preimplementation_resume"]["state"] == "worker-started"
    assert recorded["preimplementation_resume"]["worker_pid"] == 102
    assert recorded["preimplementation_resume"]["launch_attempts"][1]["state"] == ("worker-started")
    worker_state_path.unlink()
    with pytest.raises(task_session.TaskSessionError, match="unreconciled or already-used"):
        controller.resume_preimplementation(
            "241",
            control_issue_number=241,
            reason="repeat request",
            owner_authorize=True,
        )


def test_resume_preimplementation_reconciles_verified_zero_action_cli_failure(
    repository: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, git_repository, controller, worktree, branch, original_base, github = (
        _prepare_preimplementation_resume(repository)
    )
    reason = "owner-authorized retry after merged controller CLI fix"
    worker_state_path = _record_codex_cli_argument_failure(
        controller, root, github, branch, reason=reason, advance_master=True
    )
    monkeypatch.setattr(controller.store, "_pid_is_alive", lambda _pid: False)
    lease_path = controller.store.task_lease_path("241")
    before = controller.store.read_json(lease_path)

    resumed = controller.resume_preimplementation(
        "241",
        control_issue_number=241,
        reason=reason,
        owner_authorize=True,
    )

    event = resumed["preimplementation_resume"]
    failed_attempt = event["launch_attempts"][0]
    current_master = git_repository.ref("origin/master")
    assert resumed["mutation_performed"] is True
    assert resumed["control_state"]["state"] == "blocked"
    assert resumed["lease"]["original_base_origin_master_sha"] == original_base
    assert before["base_origin_master_sha"] == original_base
    assert resumed["lease"]["base_origin_master_sha"] == current_master
    assert git_repository.head(cwd=worktree) == current_master
    assert event["state"] == "prepared"
    assert event["base_refreshes"][0]["from_base_sha"] == original_base
    assert event["base_refreshes"][0]["to_base_sha"] == current_master
    assert event["registered_at"] == resumed["lease"]["created_at"]
    assert event["previous_control_state"]["state"] == "human_required"
    assert "worker-state.json" in event["previous_control_state"]["blocker"]
    assert failed_attempt["state"] == "failed-before-implementation"
    assert failed_attempt["worker_exit_code"] == 2
    assert event["last_preimplementation_failure"]["worker_exit_code"] == 2
    assert event["last_preimplementation_failure"]["recorded_at"] == failed_attempt["finished_at"]
    assert failed_attempt["failure_kind"] == "codex_cli_argument_conflict_before_implementation"
    assert failed_attempt["failure_evidence"]["completed_tool_actions"] == 0
    assert failed_attempt["failure_evidence"]["worker_state_path"] == str(worker_state_path)
    assert not worker_state_path.exists()

    repeated = controller.resume_preimplementation(
        "241",
        control_issue_number=241,
        reason=reason,
        owner_authorize=True,
    )
    assert repeated["mutation_performed"] is False
    assert repeated["preimplementation_resume"] == event


@pytest.mark.parametrize(
    ("completed_tool_actions", "process_alive", "message"),
    [
        (1, False, "zero-action"),
        (0, True, "still live"),
    ],
)
def test_resume_preimplementation_refuses_unproven_cli_failure(
    repository: tuple[Path, Any],
    monkeypatch: pytest.MonkeyPatch,
    completed_tool_actions: int,
    process_alive: bool,
    message: str,
) -> None:
    root, git_repository, controller, worktree, branch, _, github = (
        _prepare_preimplementation_resume(repository)
    )
    reason = "owner-authorized retry after merged controller CLI fix"
    _record_codex_cli_argument_failure(
        controller,
        root,
        github,
        branch,
        reason=reason,
        completed_tool_actions=completed_tool_actions,
    )
    monkeypatch.setattr(controller.store, "_pid_is_alive", lambda _pid: process_alive)
    lease_path = controller.store.task_lease_path("241")
    lease_before = controller.store.read_json(lease_path)
    head_before = git_repository.head(cwd=worktree)

    with pytest.raises(task_session.TaskSessionError, match=message):
        controller.resume_preimplementation(
            "241",
            control_issue_number=241,
            reason=reason,
            owner_authorize=True,
        )

    assert controller.store.read_json(lease_path) == lease_before
    assert git_repository.head(cwd=worktree) == head_before


def test_resume_preimplementation_allows_only_one_cli_failure_rearm(
    repository: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _, controller, _, branch, _, github = _prepare_preimplementation_resume(repository)
    reason = "owner-authorized retry after merged controller CLI fix"
    _record_codex_cli_argument_failure(controller, root, github, branch, reason=reason)
    monkeypatch.setattr(controller.store, "_pid_is_alive", lambda _pid: False)
    first_resume = controller.resume_preimplementation(
        "241",
        control_issue_number=241,
        reason=reason,
        owner_authorize=True,
    )
    assert first_resume["preimplementation_resume"]["state"] == "prepared"

    github.issue_comment_map[241] = [
        {
            "id": 3,
            "created_at": "2026-09-27T00:02:00Z",
            "user": {"login": "owner"},
            "body": render_control_state_comment(
                control_state_payload(
                    task_id="241",
                    state="human_required",
                    issue_number=241,
                    branch=branch,
                    blocker="Task worker stopped before implementation; inspect worker-state.json.",
                )
            ),
        }
    ]
    _record_codex_cli_argument_failure(
        controller,
        root,
        github,
        branch,
        reason=reason,
        attempt_name="second-codex-cli-attempt",
    )
    lease_path = controller.store.task_lease_path("241")
    lease_before = controller.store.read_json(lease_path)

    with pytest.raises(task_session.TaskSessionError, match="retry budget was already used"):
        controller.resume_preimplementation(
            "241",
            control_issue_number=241,
            reason=reason,
            owner_authorize=True,
        )

    assert controller.store.read_json(lease_path) == lease_before


def test_resume_preimplementation_refuses_non_fast_forward_cli_failure_refresh(
    repository: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, git_repository, controller, worktree, branch, _, github = (
        _prepare_preimplementation_resume(repository)
    )
    reason = "owner-authorized retry after merged controller CLI fix"
    _record_codex_cli_argument_failure(
        controller, root, github, branch, reason=reason, advance_master=True
    )
    monkeypatch.setattr(controller.store, "_pid_is_alive", lambda _pid: False)
    is_ancestor = git_repository.is_ancestor
    calls = 0

    def reject_task_branch_refresh(ancestor: str, descendant: str) -> bool:
        nonlocal calls
        calls += 1
        return False if calls == 2 else is_ancestor(ancestor, descendant)

    monkeypatch.setattr(git_repository, "is_ancestor", reject_task_branch_refresh)
    lease_path = controller.store.task_lease_path("241")
    lease_before = controller.store.read_json(lease_path)
    head_before = git_repository.head(cwd=worktree)

    with pytest.raises(task_session.TaskSessionError, match="cannot be refreshed by fast-forward"):
        controller.resume_preimplementation(
            "241",
            control_issue_number=241,
            reason=reason,
            owner_authorize=True,
        )

    assert controller.store.read_json(lease_path) == lease_before
    assert git_repository.head(cwd=worktree) == head_before


@pytest.mark.parametrize(
    ("risk_lane", "error"),
    [("YELLOW", None), ("GREEN", "weaker than its owner gate")],
)
def test_resume_preimplementation_validates_legacy_owner_task_issue_contract(
    repository: tuple[Path, Any], risk_lane: str, error: str | None
) -> None:
    _, _, controller, _, _, _, github = _prepare_preimplementation_resume(repository)
    github.issues[241]["body"] = (
        f"{task_session.TASK_CONTRACT_MARKER}\n"
        + json.dumps(
            {
                "version": 1,
                "scope": "Product v4 stage 0 synthetic scope",
                "owner_gate": "domain_contract",
                "risk_lane": risk_lane,
                "issue_state": "in_progress",
            }
        )
        + f"\n{task_session.TASK_CONTRACT_MARKER}"
    )

    if error is not None:
        with pytest.raises(task_session.TaskSessionError, match=error):
            controller.resume_preimplementation(
                "241",
                control_issue_number=241,
                reason="owner-authorized retry of the legacy Issue contract",
                owner_authorize=True,
            )
        return

    resumed = controller.resume_preimplementation(
        "241",
        control_issue_number=241,
        reason="owner-authorized retry of the legacy Issue contract",
        owner_authorize=True,
    )

    assert resumed["preimplementation_resume"]["state"] == "prepared"
    assert resumed["preimplementation_resume"]["previous_control_state"]["state"] == (
        "human_required"
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("dirty", "worktree is dirty"),
        ("unique_commit", "unique commits"),
        ("worker_state", "unreconciled worker state"),
        ("git_operation", "active Git operation"),
        ("open_pr", "open pull request"),
        ("remote_branch", "remote ref"),
        ("queue_claim", "continuous queue claim"),
        ("branch_mismatch", "does not uniquely match"),
        ("superseded", "implementation state"),
        ("missing_worktree", "does not uniquely match"),
        ("divergent", "fast-forward"),
        ("duplicate_lease", "ambiguous task lease"),
        ("dependency_changed", "dependency contract changed"),
        ("unresolved_dependency", "incomplete dependencies"),
    ],
)
def test_resume_preimplementation_refuses_unsafe_state_without_mutation(
    repository: tuple[Path, Any], mutation: str, message: str
) -> None:
    root, git_repository, controller, worktree, branch, base_sha, github = (
        _prepare_preimplementation_resume(repository)
    )
    lease_path = controller.store.task_lease_path("241")
    lease_before = controller.store.read_json(lease_path)
    head_before = git_repository.head(cwd=worktree)
    if mutation == "dirty":
        (worktree / "untracked.txt").write_text("keep\n", encoding="utf-8")
    elif mutation == "unique_commit":
        (worktree / "unique.txt").write_text("keep\n", encoding="utf-8")
        _git(worktree, "add", "unique.txt")
        _git(worktree, "commit", "-m", "feat: [Task 241] unique commit")
    elif mutation == "worker_state":
        path = (
            root / ".artifacts" / "tasks" / "241" / "temporary" / "delivery" / "worker-state.json"
        )
        path.parent.mkdir(parents=True)
        path.write_text("{}\n", encoding="utf-8")
    elif mutation == "git_operation":
        marker = git_repository.git_dir(worktree) / "MERGE_HEAD"
        marker.write_text("a" * 40, encoding="utf-8")
    elif mutation == "open_pr":
        github.open_prs = [{"head": {"ref": branch}}]
    elif mutation == "remote_branch":
        _git(root, "push", "origin", branch)
    elif mutation == "queue_claim":
        claim_path = controller.store.root / "continuous-queue.lock"
        claim_path.write_text(
            json.dumps({"queue_phase": "task_running", "task_id": "241"}),
            encoding="utf-8",
        )
    elif mutation == "branch_mismatch":
        lease = dict(lease_before)
        lease["branch"] = "task/241-other"
        task_session.StateStore.replace_json(lease_path, lease)
    elif mutation == "superseded":
        lease = dict(lease_before)
        lease["lifecycle_state"] = "superseded"
        task_session.StateStore.replace_json(lease_path, lease)
    elif mutation == "missing_worktree":
        lease = dict(lease_before)
        lease["worktree"] = str(root / ".artifacts" / "worktrees" / "missing")
        task_session.StateStore.replace_json(lease_path, lease)
    elif mutation == "divergent":
        git_repository.is_ancestor = lambda _ancestor, _descendant: False
    elif mutation == "duplicate_lease":
        task_session.StateStore.replace_json(
            controller.store.leases / "duplicate.json", dict(lease_before)
        )
    elif mutation == "unresolved_dependency":
        task_path = Path(lease_before["canonical_task_path"])
        task_path.write_text(
            task_path.read_text(encoding="utf-8").replace(
                "dependencies: \n", "dependencies: 999\n"
            ),
            encoding="utf-8",
        )
        lease_before["dependency_ids"] = ["999"]
        task_session.StateStore.replace_json(lease_path, lease_before)
        issue_number = 241
        github.issues[issue_number]["body"] = render_task_contract(
            {
                "version": 1,
                "task_id": "241",
                "scope": "Synthetic pre-implementation recovery",
                "acceptance": ["resume safely"],
                "dependencies": ["999"],
                "owner_gate": "explicit-launch",
                "risk_lane": "GREEN",
                "source_spec": "codex-backlog/tasks/241-resume-me.md",
                "issue_state": "in_progress",
            }
        )
    elif mutation == "dependency_changed":
        task_path = Path(lease_before["canonical_task_path"])
        task_path.write_text(
            task_path.read_text(encoding="utf-8").replace(
                "dependencies: \n", "dependencies: 999\n"
            ),
            encoding="utf-8",
        )
        github.issues[241]["body"] = render_task_contract(
            {
                "version": 1,
                "task_id": "241",
                "scope": "Synthetic pre-implementation recovery",
                "acceptance": ["resume safely"],
                "dependencies": ["999"],
                "owner_gate": "explicit-launch",
                "risk_lane": "GREEN",
                "source_spec": "codex-backlog/tasks/241-resume-me.md",
                "issue_state": "in_progress",
            }
        )

    head_before = git_repository.head(cwd=worktree)
    with pytest.raises(task_session.TaskSessionError, match=message):
        controller.resume_preimplementation(
            "241",
            control_issue_number=241,
            reason="owner-authorized retry",
            owner_authorize=True,
        )

    if mutation not in {"branch_mismatch", "superseded", "missing_worktree", "duplicate_lease"}:
        assert git_repository.head(cwd=worktree) == head_before
        assert controller.store.read_json(lease_path) == lease_before
    assert base_sha == lease_before["base_origin_master_sha"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("not_authorized", "owner authorization"),
        ("wrong_state", "human_required"),
        ("wrong_branch", "control state branch"),
        ("wrong_blocker", "pre-implementation failure"),
        ("closed_issue", "open control Issue"),
        ("pull_request", "not a pull request"),
        ("wrong_author", "repository owner"),
        ("wrong_task_contract", "machine-readable contract"),
        ("external_gate", "separate human or external gate"),
    ],
)
def test_resume_preimplementation_requires_matching_owner_control_state(
    repository: tuple[Path, Any], mutation: str, message: str
) -> None:
    _, _, controller, _, branch, _, github = _prepare_preimplementation_resume(repository)
    if mutation == "wrong_state":
        github.issue_comment_map[241] = [
            {
                "id": 2,
                "created_at": "2026-09-26T13:00:00Z",
                "user": {"login": "owner"},
                "body": render_control_state_comment(
                    control_state_payload(
                        task_id="241",
                        state="queued",
                        issue_number=241,
                        branch=branch,
                    )
                ),
            }
        ]
    elif mutation == "wrong_branch":
        payload = control_state_payload(
            task_id="241",
            state="human_required",
            issue_number=241,
            branch="task/241-wrong",
            blocker="worker stopped before implementation",
        )
        github.issue_comment_map[241] = [
            {
                "id": 2,
                "created_at": "2026-09-26T13:00:00Z",
                "user": {"login": "owner"},
                "body": render_control_state_comment(payload),
            }
        ]
    elif mutation == "wrong_blocker":
        payload = control_state_payload(
            task_id="241",
            state="human_required",
            issue_number=241,
            branch=branch,
            blocker="domain owner decision required",
        )
        github.issue_comment_map[241] = [
            {
                "id": 2,
                "created_at": "2026-09-26T13:00:00Z",
                "user": {"login": "owner"},
                "body": render_control_state_comment(payload),
            }
        ]
    elif mutation == "closed_issue":
        github.issues[241]["state"] = "closed"
    elif mutation == "pull_request":
        github.issues[241]["pull_request"] = {}
    elif mutation == "wrong_author":
        github.issues[241]["user"]["login"] = "intruder"
    elif mutation in {"wrong_task_contract", "external_gate"}:
        github.issues[241]["body"] = render_task_contract(
            {
                "version": 1,
                "task_id": "242" if mutation == "wrong_task_contract" else "241",
                "scope": "Synthetic pre-implementation recovery",
                "acceptance": ["resume safely"],
                "dependencies": [],
                "owner_gate": (
                    "external_authorization" if mutation == "external_gate" else "explicit-launch"
                ),
                "risk_lane": "RED" if mutation == "external_gate" else "GREEN",
                "source_spec": "codex-backlog/tasks/241-resume-me.md",
                "issue_state": "in_progress",
            }
        )

    with pytest.raises(task_session.TaskSessionError, match=message):
        controller.resume_preimplementation(
            "241",
            control_issue_number=241,
            reason="owner-authorized retry",
            owner_authorize=mutation != "not_authorized",
        )


def _prepare_subsequent_production_reconciliation(
    repository: tuple[Path, Any],
    later_changes: list[tuple[str, str, str, bool]],
) -> tuple[Path, Any, Any, Path, str, str, list[dict[str, Any]]]:
    root, git_repository, controller, worktree, branch, sha_pair = _prepare_started(
        repository, "415"
    )
    base_sha, head_sha = sha_pair.split(":")
    controller.mark_ready("415", head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")
    _git(root, "merge", "--no-ff", branch, "-m", "Merge task 415")
    original_sha = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "origin", "master")
    _git(root, "fetch", "origin", "master")
    github = controller.github
    assert isinstance(github, FakeGitHub)
    github.master_sha = original_sha
    original_run_id = 9000
    github.workflow_runs_by_sha[original_sha] = [
        {
            "id": original_run_id,
            "name": "Release production",
            "head_sha": original_sha,
            "status": "completed",
            "conclusion": "success",
            "html_url": f"https://example.invalid/runs/{original_run_id}",
        }
    ]
    github.successful_deployments.add((original_sha, "production"))
    github.current_production_deployment = {
        "deployment_id": 8000,
        "sha": original_sha,
        "environment": "production",
        "state": "success",
        "updated_at": "2026-09-24T00:00:00Z",
        "log_url": "https://example.invalid/deployments/8000",
    }

    lease_path = controller.store.task_lease_path("415")
    lease = controller.store.read_json(lease_path)
    assert isinstance(lease, dict)
    lease.update(
        {
            "lifecycle_state": "production-success",
            "merge_sha": original_sha,
            "deployed_sha": original_sha,
        }
    )
    history = {
        "version": task_session.TASK_STATE_VERSION,
        "task_id": "415",
        "state": "production-success",
        "head_sha": head_sha,
        "base_sha": base_sha,
        "merge_sha": original_sha,
        "deployed_sha": original_sha,
        "pr_number": 415,
        "completed_at": "2026-09-24T00:00:00Z",
        "closeout_required": True,
    }
    task_session.StateStore.replace_json(lease_path, lease)
    history_path = controller.store.history / "task-415.json"
    task_session.StateStore.replace_json(history_path, history)

    records: list[dict[str, Any]] = []
    previous_sha = original_sha
    for index, (classification, task_id, filename, deploy) in enumerate(later_changes, start=1):
        number = 600 + index
        if classification in {"controller", "controller_merge"}:
            subject = f"[Controller] Synthetic controller change {index}"
            branch_name = f"codex/controller-synthetic-{index}"
            title = f"[Controller] Synthetic controller change {index}"
        else:
            subject = f"[Task {task_id}] Synthetic product change {index}"
            branch_name = f"task/{task_id}-synthetic-{index}"
            title = f"[Task {task_id}] Synthetic product change {index}"
        if classification in {"product_merge", "controller_merge"}:
            _git(root, "switch", "-c", branch_name)
        path = root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"change {index}\n", encoding="utf-8")
        _git(root, "add", filename)
        _git(root, "commit", "-m", subject)
        head_sha_for_pr = _git(root, "rev-parse", "HEAD")
        if classification in {"product_merge", "controller_merge"}:
            _git(root, "switch", "master")
            _git(
                root,
                "merge",
                "--no-ff",
                branch_name,
                "-m",
                f"Merge pull request #{number} from owner/{branch_name}",
            )
            commit_sha = _git(root, "rev-parse", "HEAD")
        else:
            commit_sha = head_sha_for_pr
        pr = {
            "number": number,
            "title": title,
            "state": "closed",
            "merged_at": f"2026-09-24T0{index}:00:00Z",
            "merge_commit_sha": commit_sha,
            "commits": 1,
            "changed_files": 1,
            "base": {
                "ref": "master",
                "sha": previous_sha,
                "repo": {"full_name": "owner/repository"},
            },
            "head": {
                "ref": branch_name,
                "sha": head_sha_for_pr,
                "repo": {"full_name": "owner/repository"},
            },
        }
        github.pulls[number] = pr
        github.associated_pulls_by_commit[commit_sha] = [pr]
        github.commits[number] = [{"sha": head_sha_for_pr, "commit": {"message": subject}}]
        github.files[number] = [{"filename": filename}]
        github.checks[head_sha_for_pr] = [_success_check(head_sha_for_pr)]
        release_run_id = 9100 + index
        if classification in {"controller", "controller_merge"}:
            github.workflow_runs_by_sha[commit_sha] = [
                {
                    "id": release_run_id,
                    "name": "Release production",
                    "head_sha": commit_sha,
                    "status": "completed",
                    "conclusion": "success",
                    "html_url": f"https://example.invalid/runs/{release_run_id}",
                }
            ]
            github.workflow_jobs_by_run[release_run_id] = [
                {"name": "Authorize exact merged master revision", "conclusion": "success"},
                {"name": "Deploy immutable tested bundle", "conclusion": "skipped"},
            ]
        elif deploy:
            github.workflow_runs_by_sha[commit_sha] = [
                {
                    "id": release_run_id,
                    "name": "Release production",
                    "head_sha": commit_sha,
                    "status": "completed",
                    "conclusion": "success",
                    "html_url": f"https://example.invalid/runs/{release_run_id}",
                }
            ]
            github.successful_deployments.add((commit_sha, "production"))
            github.current_production_deployment = {
                "deployment_id": 8000 + index,
                "sha": commit_sha,
                "environment": "production",
                "state": "success",
                "updated_at": f"2026-09-24T0{index}:30:00Z",
                "log_url": f"https://example.invalid/deployments/{8000 + index}",
            }
        records.append(
            {
                "classification": (
                    "product"
                    if classification == "product_merge"
                    else "controller"
                    if classification == "controller_merge"
                    else classification
                ),
                "task_id": task_id,
                "commit_sha": commit_sha,
                "pr_number": number,
                "head_sha": head_sha_for_pr,
                "release_run_id": release_run_id,
            }
        )
        previous_sha = commit_sha
    _git(root, "push", "origin", "master")
    _git(root, "fetch", "origin", "master")
    github.master_sha = previous_sha
    return root, git_repository, controller, worktree, branch, original_sha, records


def test_reconcile_subsequent_production_accepts_controller_only_master_advance(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, _, _, original_sha, records = _prepare_subsequent_production_reconciliation(
        repository,
        [("controller", "", "scripts/task_session.py", False)],
    )

    reconciliation = controller.reconcile_subsequent_production("415", owner_authorize=True)

    assert reconciliation["current_master_sha"] == records[-1]["commit_sha"]
    assert reconciliation["current_production"]["deployed_sha"] == original_sha
    assert reconciliation["intervening_commits"][0]["classification"] == "controller"
    assert (
        reconciliation["intervening_commits"][0]["release"]["application_deploy_job"] == "skipped"
    )


def test_reconcile_subsequent_production_preserves_original_and_records_product_deployment(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, _, _, original_sha, records = _prepare_subsequent_production_reconciliation(
        repository,
        [("product", "475", "backend/fitminiapp_api/services/news_editorial.py", True)],
    )

    reconciliation = controller.reconcile_subsequent_production("415", owner_authorize=True)
    history = controller.store.read_json(controller.store.history / "task-415.json")
    lease = controller.store.read_json(controller.store.task_lease_path("415"))

    assert history["deployed_sha"] == original_sha
    assert history["merge_sha"] == original_sha
    assert lease["deployed_sha"] == original_sha
    assert reconciliation["original_deployed_sha"] == original_sha
    assert reconciliation["current_production"]["deployed_sha"] == records[0]["commit_sha"]
    assert (
        history["subsequent_production_reconciliation"]
        == lease["subsequent_production_reconciliation"]
    )


def test_reconcile_subsequent_production_accepts_standard_github_merge_commit(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, _, _, _, records = _prepare_subsequent_production_reconciliation(
        repository,
        [
            (
                "product_merge",
                "480",
                "backend/tests/test_news_publishing.py",
                True,
            )
        ],
    )

    reconciliation = controller.reconcile_subsequent_production("415", owner_authorize=True)
    record = reconciliation["intervening_commits"][0]

    assert record["classification"] == "product"
    assert record["task_id"] == "480"
    assert record["pr_number"] == 601
    assert record["subject"].startswith("Merge pull request #601 from ")
    assert reconciliation["current_production"]["deployed_sha"] == records[0]["commit_sha"]


def test_reconcile_subsequent_production_accepts_standard_github_controller_merge_commit(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, _, _, original_sha, _ = _prepare_subsequent_production_reconciliation(
        repository,
        [("controller_merge", "", "scripts/task_session.py", False)],
    )

    reconciliation = controller.reconcile_subsequent_production("415", owner_authorize=True)
    record = reconciliation["intervening_commits"][0]

    assert record["classification"] == "controller"
    assert record["pr_number"] == 601
    assert record["subject"].startswith("Merge pull request #601 from ")
    assert record["release"]["application_deploy_job"] == "skipped"
    assert reconciliation["current_production"]["deployed_sha"] == original_sha


def test_reconcile_subsequent_production_preserves_ordered_product_deployments(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, _, _, _, records = _prepare_subsequent_production_reconciliation(
        repository,
        [
            ("controller", "", "scripts/task_session.py", False),
            ("product", "475", "backend/news_one.py", True),
            ("product", "477", "backend/news_two.py", True),
        ],
    )

    reconciliation = controller.reconcile_subsequent_production("415", owner_authorize=True)
    chain = reconciliation["intervening_commits"]

    assert [item["classification"] for item in chain] == ["controller", "product", "product"]
    assert [item["pr_number"] for item in chain] == [601, 602, 603]
    assert [item["task_id"] for item in chain if item["classification"] == "product"] == [
        "475",
        "477",
    ]
    assert [
        item["release"]["deployed_sha"] for item in chain if item["classification"] == "product"
    ] == [
        records[1]["commit_sha"],
        records[2]["commit_sha"],
    ]


def test_reconcile_subsequent_production_records_a_later_deployment_that_supersedes_a_product_sha(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, _, _, _, records = _prepare_subsequent_production_reconciliation(
        repository,
        [
            ("product", "475", "backend/news_one.py", False),
            ("product", "477", "backend/news_two.py", True),
        ],
    )

    reconciliation = controller.reconcile_subsequent_production("415", owner_authorize=True)
    first, second = reconciliation["intervening_commits"]

    assert first["release"]["result"] == "superseded"
    assert first["release"]["superseded_by_sha"] == records[1]["commit_sha"]
    assert second["release"]["result"] == "deployed"
    assert reconciliation["current_production"]["deployed_sha"] == records[1]["commit_sha"]


def test_reconcile_subsequent_production_allows_only_controller_tail_and_finish_revalidates(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, worktree, branch, original_sha, records = (
        _prepare_subsequent_production_reconciliation(
            repository,
            [
                ("controller", "", "scripts/task_session.py", False),
                ("product", "475", "backend/news_one.py", True),
                ("product", "477", "backend/news_two.py", True),
                ("controller", "", "docs/task-branch-integration.md", False),
            ],
        )
    )

    reconciliation = controller.reconcile_subsequent_production("415", owner_authorize=True)
    assert reconciliation["original_deployed_sha"] == original_sha
    assert reconciliation["current_production"]["deployed_sha"] == records[2]["commit_sha"]
    assert reconciliation["current_master_sha"] == records[3]["commit_sha"]
    assert (
        reconciliation["current_production"]["deployed_sha"] != reconciliation["current_master_sha"]
    )

    result = controller.finish("415")

    assert result["cleanup_performed"] is True
    assert not worktree.exists()
    assert branch not in controller.repository.git("branch", "--list", branch).splitlines()
    history = controller.store.read_json(controller.store.history / "task-415.json")
    assert history["state"] == "finished"
    assert history["deployed_sha"] == original_sha


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("unverified_product", "after the latest production deployment"),
        ("failed_checks", "required check 'checks' is not successful"),
        ("unknown_commit", "unique merged pull request"),
        ("active_deployment", "active deployment"),
        ("dirty_worktree", "unchanged clean task worktree"),
        ("unique_task_commit", "unique task commits"),
    ],
)
def test_reconcile_subsequent_production_fails_closed(
    repository: tuple[Path, Any], mutation: str, message: str, monkeypatch: Any
) -> None:
    root, git_repository, controller, worktree, _branch, _, records = (
        _prepare_subsequent_production_reconciliation(
            repository,
            [("product", "475", "backend/news_one.py", True)],
        )
    )
    github = controller.github
    assert isinstance(github, FakeGitHub)
    if mutation == "unverified_product":
        extra = root / "backend" / "news_unreleased.py"
        extra.write_text("unreleased\n", encoding="utf-8")
        _git(root, "add", "backend/news_unreleased.py")
        _git(root, "commit", "-m", "[Task 477] Unreleased product change")
        _git(root, "push", "origin", "master")
        _git(root, "fetch", "origin", "master")
        github.master_sha = _git(root, "rev-parse", "HEAD")
        new_sha = github.master_sha
        pr_number = 699
        pr = {
            "number": pr_number,
            "title": "[Task 477] Unreleased product change",
            "state": "closed",
            "merged_at": "2026-09-24T08:00:00Z",
            "merge_commit_sha": new_sha,
            "commits": 1,
            "changed_files": 1,
            "base": {
                "ref": "master",
                "sha": records[-1]["commit_sha"],
                "repo": {"full_name": "owner/repository"},
            },
            "head": {
                "ref": "task/477-unreleased",
                "sha": new_sha,
                "repo": {"full_name": "owner/repository"},
            },
        }
        github.pulls[pr_number] = pr
        github.associated_pulls_by_commit[new_sha] = [pr]
        github.commits[pr_number] = [
            {"sha": new_sha, "commit": {"message": "[Task 477] Unreleased product change"}}
        ]
        github.files[pr_number] = [{"filename": "backend/news_unreleased.py"}]
        github.checks[new_sha] = [_success_check(new_sha)]
    elif mutation == "failed_checks":
        github.checks[records[0]["head_sha"]] = [
            {
                "name": "checks",
                "head_sha": records[0]["head_sha"],
                "status": "completed",
                "conclusion": "FAILURE",
            }
        ]
    elif mutation == "unknown_commit":
        path = root / "misc.py"
        path.write_text("unknown\n", encoding="utf-8")
        _git(root, "add", "misc.py")
        _git(root, "commit", "-m", "Refactor without task provenance")
        _git(root, "push", "origin", "master")
        _git(root, "fetch", "origin", "master")
        github.master_sha = _git(root, "rev-parse", "HEAD")
    elif mutation == "active_deployment":
        github.active_runs = [{"name": "Release production", "status": "in_progress"}]
    elif mutation == "dirty_worktree":
        (worktree / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    elif mutation == "unique_task_commit":
        monkeypatch.setattr(git_repository, "unique_commits", lambda _branch: ["a" * 40])

    with pytest.raises(task_session.TaskSessionError, match=message):
        controller.reconcile_subsequent_production("415", owner_authorize=True)


def test_reconcile_subsequent_production_requires_explicit_owner_authorization(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, _, _, _, _ = _prepare_subsequent_production_reconciliation(
        repository,
        [("product", "475", "backend/news_one.py", True)],
    )

    with pytest.raises(task_session.TaskSessionError, match="explicit owner authorization"):
        controller.reconcile_subsequent_production("415", owner_authorize=False)

    history = controller.store.read_json(controller.store.history / "task-415.json")
    lease = controller.store.read_json(controller.store.task_lease_path("415"))
    assert "subsequent_production_reconciliation" not in history
    assert "subsequent_production_reconciliation" not in lease


def test_superseded_archived_task_is_not_a_completed_dependency(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    done = root / "codex-backlog" / "tasks" / "done"
    done.mkdir(parents=True)
    (done / "152-superseded.md").write_text("superseded\n", encoding="utf-8")
    (done / "153-delivered.md").write_text("delivered\n", encoding="utf-8")
    controller = task_session.TaskController(
        git_repository,
        github=FakeGitHub(git_repository.ref("origin/master")),
    )
    controller.store.initialize()
    task_session.StateStore.replace_json(
        controller.store.task_lease_path("152"),
        {
            "task_id": "152",
            "mode": "write",
            "lifecycle_state": "superseded",
        },
    )

    completed = controller._completed_dependency_ids()

    assert "152" not in completed
    assert "153" in completed


def test_finished_history_is_a_completed_dependency_for_local_task_shims(
    repository: tuple[Path, Any],
) -> None:
    _, git_repository = repository
    controller = task_session.TaskController(
        git_repository,
        github=FakeGitHub(git_repository.ref("origin/master")),
    )
    controller.store.initialize()
    task_session.StateStore.replace_json(
        controller.store.history / "task-519.json",
        {
            "version": task_session.TASK_STATE_VERSION,
            "task_id": "519",
            "state": "finished",
            "merge_sha": "a" * 40,
            "deployed_sha": "a" * 40,
        },
    )
    task_session.StateStore.replace_json(
        controller.store.history / "task-520.json",
        {
            "version": task_session.TASK_STATE_VERSION,
            "task_id": "520",
            "state": "production-success",
        },
    )
    task_session.StateStore.replace_json(
        controller.store.history / "task-521.json",
        {
            "version": task_session.TASK_STATE_VERSION,
            "task_id": "not-521",
            "state": "finished",
        },
    )

    completed = controller._completed_dependency_ids()

    assert "519" in completed
    assert "520" not in completed
    assert "521" not in completed


def test_finished_history_respects_superseded_lease_dependency_safety(
    repository: tuple[Path, Any],
) -> None:
    _, git_repository = repository
    controller = task_session.TaskController(
        git_repository,
        github=FakeGitHub(git_repository.ref("origin/master")),
    )
    controller.store.initialize()
    task_session.StateStore.replace_json(
        controller.store.history / "task-519.json",
        {
            "version": task_session.TASK_STATE_VERSION,
            "task_id": "519",
            "state": "finished",
        },
    )
    task_session.StateStore.replace_json(
        controller.store.task_lease_path("519"),
        {
            "task_id": "519",
            "mode": "write",
            "lifecycle_state": "superseded",
        },
    )

    assert "519" not in controller._completed_dependency_ids()


def test_reconcile_merged_no_deploy_corrects_stale_lease_and_unblocks_controller(
    repository: tuple[Path, Any],
) -> None:
    root, _, controller, _, _, _, _, merge_sha, _, _ = _prepare_merged_no_deploy_reconciliation(
        repository
    )

    blocker = controller._canonical_refresh_controller_blocker(delivery_task_id=None)
    assert blocker is not None and blocker[0] == "BLOCKED"
    assert "worktree is missing" in blocker[1]

    result = controller.reconcile_merged_no_deploy(
        "729",
        pr_number=730,
        merge_sha=merge_sha,
        reason="Task 729 is merged CI-only dependency remediation; production deploy is not required.",
        owner_authorize=True,
    )

    assert result["mutation_performed"] is True
    assert result["recovery_classification"] == "corrected_stale_superseded_lease"
    assert result["lease"]["lifecycle_state"] == task_session.MERGED_NO_DEPLOY_STATE
    assert result["history"]["state"] == task_session.MERGED_NO_DEPLOY_STATE
    assert result["history"]["merge_sha"] == merge_sha
    assert controller._canonical_refresh_controller_blocker(delivery_task_id=None) is None
    assert "729" in controller._completed_dependency_ids()
    assert controller._is_active_write_lease(result["lease"]) is False
    recovery = controller.recover("729")
    assert recovery["classification"] == "MERGED_NO_DEPLOY"
    assert recovery["issues"] == []
    task_session.archive_guard(root / "codex-backlog" / "tasks", "729")


def test_reconcile_merged_no_deploy_requires_owner_authorization(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, _, _, _, _, merge_sha, _, _ = _prepare_merged_no_deploy_reconciliation(
        repository
    )
    lease_before = controller.store.read_json(controller.store.task_lease_path("729"))

    with pytest.raises(task_session.TaskSessionError, match="explicit owner authorization"):
        controller.reconcile_merged_no_deploy(
            "729",
            pr_number=730,
            merge_sha=merge_sha,
            reason="owner did not authorize",
            owner_authorize=False,
        )

    assert controller.store.read_json(controller.store.task_lease_path("729")) == lease_before
    assert controller.store.read_json(controller.store.history / "task-729.json") is None


@pytest.mark.parametrize(
    ("mutation", "expected_message"),
    [
        ("open", "not a closed pull request"),
        ("wrong_task", "PR title"),
        ("sha", "exactly one matching merged PR provenance"),
        ("checks", "checks"),
        ("contract", "exact no-deploy contract"),
        ("ambiguous", "exactly one matching merged PR provenance"),
        ("non_ancestor", "not based on its recorded master base"),
    ],
)
def test_reconcile_merged_no_deploy_fails_closed_for_invalid_evidence(
    repository: tuple[Path, Any], mutation: str, expected_message: str
) -> None:
    (
        _,
        _,
        controller,
        _,
        _,
        base_sha,
        head_sha,
        merge_sha,
        github,
        pull_request,
    ) = _prepare_merged_no_deploy_reconciliation(repository)
    call_merge_sha = merge_sha
    if mutation == "open":
        pull_request["state"] = "open"
    elif mutation == "wrong_task":
        pull_request["title"] = "[Task 730] Wrong task provenance"
    elif mutation == "sha":
        call_merge_sha = base_sha
    elif mutation == "checks":
        github.checks[head_sha] = [{**_success_check(head_sha), "conclusion": "FAILURE"}]
    elif mutation == "contract":
        pull_request["body"] = "runtime change requires production"
    elif mutation == "ambiguous":
        github.associated_pulls_by_commit[merge_sha] = [
            pull_request,
            {**pull_request, "number": 731},
        ]
    elif mutation == "non_ancestor":
        pull_request["merge_commit_sha"] = base_sha
        github.associated_pulls_by_commit[base_sha] = [pull_request]
        call_merge_sha = base_sha
    else:
        raise AssertionError(mutation)
    lease_before = controller.store.read_json(controller.store.task_lease_path("729"))

    with pytest.raises(task_session.TaskSessionError, match=expected_message):
        controller.reconcile_merged_no_deploy(
            "729",
            pr_number=730,
            merge_sha=call_merge_sha,
            reason="invalid evidence fixture",
            owner_authorize=True,
        )

    assert controller.store.read_json(controller.store.task_lease_path("729")) == lease_before
    assert controller.store.read_json(controller.store.history / "task-729.json") is None


def test_reconcile_merged_no_deploy_records_observed_automatic_deployment(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, _, _, _, _, merge_sha, github, _ = _prepare_merged_no_deploy_reconciliation(
        repository
    )
    github.successful_deployments.add((merge_sha, "production"))

    result = controller.reconcile_merged_no_deploy(
        "729",
        pr_number=730,
        merge_sha=merge_sha,
        reason="The merged CI-only task did not require another production deployment.",
        owner_authorize=True,
    )

    assert result["history"]["state"] == task_session.MERGED_NO_DEPLOY_STATE
    assert result["history"]["deployment_required"] is False
    assert result["history"]["production_deployment_observed"] is True


def test_reconcile_merged_no_deploy_rejects_dirty_or_changed_anchor(
    repository: tuple[Path, Any],
) -> None:
    (
        _,
        _,
        controller,
        worktree,
        _,
        _,
        _,
        merge_sha,
        _,
        _,
    ) = _prepare_merged_no_deploy_reconciliation(repository, keep_anchor=True)
    (worktree / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(task_session.TaskSessionError, match="dirty task worktree"):
        controller.reconcile_merged_no_deploy(
            "729",
            pr_number=730,
            merge_sha=merge_sha,
            reason="dirty anchor fixture",
            owner_authorize=True,
        )

    _git(worktree, "add", "dirty.txt")
    _git(worktree, "commit", "-m", "feat: [Task 729] unmerged follow-up")
    with pytest.raises(task_session.TaskSessionError, match="changed task worktree head"):
        controller.reconcile_merged_no_deploy(
            "729",
            pr_number=730,
            merge_sha=merge_sha,
            reason="changed anchor fixture",
            owner_authorize=True,
        )


def test_missing_worktree_still_blocks_unfinished_task(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, _, _, _, _, _, _, _ = _prepare_merged_no_deploy_reconciliation(
        repository, stale_done=False
    )
    lease = controller.store.read_json(controller.store.task_lease_path("729"))
    assert isinstance(lease, dict)
    assert controller._is_active_write_lease(lease) is True
    blocker = controller._canonical_refresh_controller_blocker(delivery_task_id=None)
    assert blocker is not None and blocker[0] == "BLOCKED"
    assert "worktree is missing" in blocker[1]


def test_record_queue_cycle_is_durable_and_bounded(repository: tuple[Path, Any]) -> None:
    _, _, controller, _, _, _ = _prepare_started(repository, "250", queue_mode=True)

    for index in range(3):
        budget = controller.record_queue_cycle(
            "250", kind="review", reason=f"bounded review fix {index + 1}"
        )

    assert budget["task_id"] == "250"
    assert budget["queue_budget"]["review_fix_cycles"] == 3
    assert budget["queue_budget"]["ci_fix_cycles"] == 0
    assert budget["queue_budget"]["scope_expansions"] == 0
    with pytest.raises(task_session.TaskSessionError, match="HUMAN_REQUIRED"):
        controller.record_queue_cycle("250", kind="review", reason="fourth review fix")

    lease = next(item for item in controller.status()["leases"] if item["task_id"] == "250")
    assert lease["queue_budget"]["review_fix_cycles"] == 3
    assert len(lease["queue_budget"]["events"]) == 3


def _commit_task(worktree: Path, task_id: str, filename: str = "change.txt") -> str:
    (worktree / filename).write_text(f"{task_id}\n", encoding="utf-8")
    _git(worktree, "add", filename)
    _git(worktree, "commit", "-m", f"feat: [Task {task_id}] synthetic change")
    return _git(worktree, "rev-parse", "HEAD")


def _advance_remote_master(root: Path, count: int, *, fetch: bool = True) -> tuple[str, str]:
    old_sha = _git(root, "rev-parse", "master")
    remote_worktree = root.parent / f"remote-master-{uuid.uuid4().hex[:8]}"
    _git(root, "worktree", "add", "--detach", str(remote_worktree), old_sha)
    try:
        for index in range(count):
            filename = f"remote-change-{index}.txt"
            (remote_worktree / filename).write_text(f"remote {index}\n", encoding="utf-8")
            _git(remote_worktree, "add", filename)
            _git(remote_worktree, "commit", "-m", f"chore: advance remote master {index + 1}")
        new_sha = _git(remote_worktree, "rev-parse", "HEAD")
        _git(remote_worktree, "push", "origin", "HEAD:master")
    finally:
        _git(root, "worktree", "remove", "--force", str(remote_worktree))
    if fetch:
        _git(root, "fetch", "origin", "master")
    return old_sha, new_sha


def _publish_task_merge_without_advancing_local_master(root: Path, branch: str) -> str:
    base_sha = _git(root, "rev-parse", "master")
    remote_worktree = root.parent / f"remote-task-merge-{uuid.uuid4().hex[:8]}"
    _git(root, "worktree", "add", "--detach", str(remote_worktree), base_sha)
    try:
        _git(remote_worktree, "merge", "--no-ff", branch, "-m", f"Merge {branch}")
        merge_sha = _git(remote_worktree, "rev-parse", "HEAD")
        _git(remote_worktree, "push", "origin", "HEAD:master")
    finally:
        _git(root, "worktree", "remove", "--force", str(remote_worktree))
    _git(root, "fetch", "origin", "master")
    return merge_sha


def _publish_task_squash_without_advancing_local_master(root: Path, branch: str) -> str:
    base_sha = _git(root, "rev-parse", "master")
    remote_worktree = root.parent / f"remote-task-squash-{uuid.uuid4().hex[:8]}"
    _git(root, "worktree", "add", "--detach", str(remote_worktree), base_sha)
    try:
        _git(remote_worktree, "merge", "--squash", branch)
        _git(remote_worktree, "commit", "-m", f"[Task 207C] Squash task {branch}")
        merge_sha = _git(remote_worktree, "rev-parse", "HEAD")
        _git(remote_worktree, "push", "origin", "HEAD:master")
    finally:
        _git(root, "worktree", "remove", "--force", str(remote_worktree))
    _git(root, "fetch", "origin", "master")
    return merge_sha


def _publish_task_squash_from_origin_master(root: Path, branch: str, task_id: str) -> str:
    base_sha = _git(root, "rev-parse", "origin/master")
    remote_worktree = root.parent / f"remote-task-squash-origin-{uuid.uuid4().hex[:8]}"
    _git(root, "worktree", "add", "--detach", str(remote_worktree), base_sha)
    try:
        _git(remote_worktree, "merge", "--squash", branch)
        _git(remote_worktree, "commit", "-m", f"[Task {task_id}] Squash task {branch}")
        merge_sha = _git(remote_worktree, "rev-parse", "HEAD")
        _git(remote_worktree, "push", "origin", "HEAD:master")
    finally:
        _git(root, "worktree", "remove", "--force", str(remote_worktree))
    _git(root, "fetch", "origin", "master")
    return merge_sha


def _prepare_delivery(controller: Any, task_id: str, *, branch: str) -> dict[str, Any]:
    del branch
    acquired = controller.acquire_delivery(task_id)
    assert acquired["acquired"] is True
    controller.refresh_for_delivery(task_id)
    return controller.validate_delivery(task_id)


def _prepare_superseding_production_reconciliation(
    repository: tuple[Path, Any],
    *,
    task_id: str = "415",
    superseding_count: int = 2,
    post_deploy_drift: bool = True,
    original_pr_branch: str | None = None,
    superseding_pr_branch: str | None = None,
) -> tuple[Path, Any, Any, Path, str, list[int], str]:
    root, git_repository, controller, worktree, branch, sha_pair = _prepare_started(
        repository, task_id
    )
    base_sha, head_sha = sha_pair.split(":")
    controller.mark_ready(task_id, head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")
    _prepare_delivery(controller, task_id, branch=branch)
    _git(root, "merge", "--no-ff", branch, "-m", f"Merge task {task_id}")
    original_merge_sha = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "origin", "master")

    github = controller.github
    assert isinstance(github, FakeGitHub)
    original_pr = 423
    original = _task_pr(original_pr, task_id, base_sha, head_sha, merge_sha=original_merge_sha)
    if original_pr_branch is not None:
        original["head"]["ref"] = original_pr_branch
    original["state"] = "closed"
    original["merged_at"] = "2026-09-22T13:34:24Z"
    github.pulls[original_pr] = original
    github.commits[original_pr] = [_task_commit(task_id)]
    github.files[original_pr] = [{"filename": "change.txt"}]
    github.checks[head_sha] = [_success_check(head_sha)]

    superseding_numbers: list[int] = []
    prior_merge_sha = original_merge_sha
    for index in range(superseding_count):
        number = (432, 435, 438, 441)[index]
        tree_sha = _git(root, "rev-parse", f"{prior_merge_sha}^{{tree}}")
        superseding_head = _git(
            root,
            "commit-tree",
            tree_sha,
            "-p",
            prior_merge_sha,
            "-m",
            f"feat: [Task {task_id}] superseding change {index + 1}",
        )
        superseding_merge = _git(
            root,
            "commit-tree",
            tree_sha,
            "-p",
            prior_merge_sha,
            "-m",
            f"Merge pull request #{number}",
        )
        pull_request = _task_pr(
            number,
            task_id,
            prior_merge_sha,
            superseding_head,
            merge_sha=superseding_merge,
        )
        pull_request["state"] = "closed"
        pull_request["head"]["ref"] = superseding_pr_branch or (
            f"task/{task_id}-superseding-{index + 1}"
        )
        pull_request["merged_at"] = f"2026-09-22T20:{20 + index * 33:02}:29Z"
        github.pulls[number] = pull_request
        github.commits[number] = [_task_commit(task_id)]
        github.files[number] = [{"filename": "change.txt"}]
        github.checks[superseding_head] = [_success_check(superseding_head)]
        superseding_numbers.append(number)
        prior_merge_sha = superseding_merge

    master_sha = prior_merge_sha
    if post_deploy_drift:
        tree_sha = _git(root, "rev-parse", f"{prior_merge_sha}^{{tree}}")
        master_sha = _git(
            root,
            "commit-tree",
            tree_sha,
            "-p",
            prior_merge_sha,
            "-m",
            "feat: [Task 416] subsequent master change",
        )
    _git(root, "reset", "--hard", master_sha)
    _git(root, "push", "origin", "master")
    _git(root, "fetch", "origin", "master")
    github.master_sha = master_sha
    github.successful_deployments.add((prior_merge_sha, "production"))
    github.runs[35783412553] = {
        "id": 35783412553,
        "name": "Release production",
        "head_sha": prior_merge_sha,
        "status": "completed",
        "conclusion": "success",
        "html_url": "https://example.invalid/actions/runs/35783412553",
    }
    controller.release_delivery(
        task_id,
        reason="Synthetic recovery lease for superseding production reconciliation",
    )
    return root, git_repository, controller, worktree, branch, superseding_numbers, prior_merge_sha


def _collapse_reconciliation_anchor_after_refresh(
    root: Path,
    git_repository: Any,
    controller: Any,
    worktree: Path,
    branch: str,
    superseding_prs: list[int],
    deployed_sha: str,
) -> None:
    lease_path = controller.store.task_lease_path("415")
    lease = controller.store.read_json(lease_path)
    assert isinstance(lease, dict)
    final_pr = controller.github.pulls[superseding_prs[-1]]
    final_pr["head"]["ref"] = branch
    ref = f"refs/heads/{branch}"
    previous_sha = git_repository.ref(branch)
    _git(
        root,
        "update-ref",
        "-m",
        "commit: [Task 415] superseding PR head",
        ref,
        final_pr["head"]["sha"],
        previous_sha,
    )
    _git(
        root,
        "update-ref",
        "-m",
        f"rebase (finish): {ref} onto {deployed_sha}",
        ref,
        deployed_sha,
        final_pr["head"]["sha"],
    )

    original_base_sha = lease["original_base_origin_master_sha"]
    lease.update(
        {
            "base_origin_master_sha": deployed_sha,
            "ready_head_sha": deployed_sha,
            "ready_base_origin_master_sha": deployed_sha,
            "delivery_base_origin_master_sha": deployed_sha,
            "delivery_head_sha": deployed_sha,
            "task_provenance": {
                "task_id": "415",
                "branch": branch,
                "base_sha": deployed_sha,
                "head_sha": deployed_sha,
                "original_base_sha": original_base_sha,
            },
            "delivery_anchor": {
                "task_id": "415",
                "branch": branch,
                "base_sha": deployed_sha,
                "head_sha": deployed_sha,
            },
            "canonical_master_refresh": {
                "operation": "canonical-master-refresh",
                "result": "REFRESHED",
                "canonical_worktree": str(root),
                "old_sha": final_pr["base"]["sha"],
                "new_sha": deployed_sha,
                "local_master_before": final_pr["base"]["sha"],
                "local_master_after": deployed_sha,
                "origin_master_sha": deployed_sha,
                "verified_remote_sha": deployed_sha,
                "live_master_sha": deployed_sha,
                "ahead_before": 0,
                "behind_before": int(
                    _git(root, "rev-list", "--count", f"{final_pr['base']['sha']}..{deployed_sha}")
                ),
                "ahead_after": 0,
                "behind_after": 0,
                "updated_commits": int(
                    _git(root, "rev-list", "--count", f"{final_pr['base']['sha']}..{deployed_sha}")
                ),
                "mutation_performed": True,
                "mutated_ref": "refs/heads/master",
                "reread_after_contention": False,
                "delivery_task_id": "415",
            },
        }
    )
    task_session.StateStore.replace_json(lease_path, lease)
    assert git_repository.head(cwd=worktree) == deployed_sha


def _prepare_single_collapsed_production_reconciliation(
    repository: tuple[Path, Any],
) -> tuple[Path, Any, Any, Path, str, str, str, str, FakeGitHub]:
    root, git_repository, controller, worktree, branch, sha_pair = _prepare_started(
        repository, "507"
    )
    base_sha, head_sha = sha_pair.split(":")
    controller.mark_ready("507", head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")
    _prepare_delivery(controller, "507", branch=branch)
    _git(root, "merge", "--no-ff", branch, "-m", "Merge task 507")
    deployed_sha = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "origin", "master")

    github = controller.github
    assert isinstance(github, FakeGitHub)
    pull_request = _task_pr(578, "507", base_sha, head_sha, merge_sha=deployed_sha)
    pull_request["state"] = "closed"
    pull_request["head"]["ref"] = branch
    pull_request["merged_at"] = "2026-09-29T15:23:46Z"
    github.pulls[578] = pull_request
    github.commits[578] = [_task_commit("507")]
    github.files[578] = [{"filename": "change.txt"}]
    github.checks[head_sha] = [_success_check(head_sha)]
    github.master_sha = deployed_sha
    github.runs[36590222806] = {
        "id": 36590222806,
        "name": "Release production",
        "head_sha": deployed_sha,
        "status": "completed",
        "conclusion": "success",
        "html_url": "https://example.invalid/actions/runs/36590222806",
    }
    github.successful_deployments.add((deployed_sha, "production"))

    lease_path = controller.store.task_lease_path("507")
    lease = controller.store.read_json(lease_path)
    assert isinstance(lease, dict)
    ref = f"refs/heads/{branch}"
    previous_sha = git_repository.ref(branch)
    _git(
        root,
        "update-ref",
        "-m",
        "commit: [Task 507] PR head",
        ref,
        head_sha,
        previous_sha,
    )
    _git(
        root,
        "update-ref",
        "-m",
        f"rebase (finish): {ref} onto {deployed_sha}",
        ref,
        deployed_sha,
        head_sha,
    )
    behind_before = int(_git(root, "rev-list", "--count", f"{base_sha}..{deployed_sha}"))
    lease.update(
        {
            "base_origin_master_sha": deployed_sha,
            "ready_head_sha": deployed_sha,
            "ready_base_origin_master_sha": deployed_sha,
            "delivery_base_origin_master_sha": deployed_sha,
            "delivery_head_sha": deployed_sha,
            "task_provenance": {
                "task_id": "507",
                "branch": branch,
                "base_sha": deployed_sha,
                "head_sha": deployed_sha,
                "original_base_sha": base_sha,
            },
            "delivery_anchor": {
                "task_id": "507",
                "branch": branch,
                "base_sha": deployed_sha,
                "head_sha": deployed_sha,
            },
            "canonical_master_refresh": {
                "operation": "canonical-master-refresh",
                "result": "REFRESHED",
                "canonical_worktree": str(root),
                "old_sha": base_sha,
                "new_sha": deployed_sha,
                "local_master_before": base_sha,
                "local_master_after": deployed_sha,
                "origin_master_sha": deployed_sha,
                "verified_remote_sha": deployed_sha,
                "live_master_sha": deployed_sha,
                "ahead_before": 0,
                "behind_before": behind_before,
                "ahead_after": 0,
                "behind_after": 0,
                "updated_commits": behind_before,
                "mutation_performed": True,
                "mutated_ref": "refs/heads/master",
                "reread_after_contention": False,
                "delivery_task_id": "507",
            },
        }
    )
    task_session.StateStore.replace_json(lease_path, lease)
    assert git_repository.head(cwd=worktree) == deployed_sha
    controller.release_delivery(
        "507",
        reason="post-merge refresh collapsed the Task #507 delivery anchor",
    )
    return (
        root,
        git_repository,
        controller,
        worktree,
        branch,
        base_sha,
        head_sha,
        deployed_sha,
        github,
    )


def test_reconcile_verified_post_merge_anchor_preserves_pr_chain_and_finishes(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository, controller, worktree, branch, superseding_prs, deployed_sha = (
        _prepare_superseding_production_reconciliation(
            repository, superseding_count=1, post_deploy_drift=False
        )
    )
    _collapse_reconciliation_anchor_after_refresh(
        root, git_repository, controller, worktree, branch, superseding_prs, deployed_sha
    )

    history = controller.reconcile_production_success(
        "415",
        original_pr_number=423,
        superseding_pr_numbers=superseding_prs,
        deployed_sha=deployed_sha,
        production_run_id=35783412553,
        owner_authorize=True,
    )

    reconciliation = history["superseding_production_reconciliation"]
    collapsed = reconciliation["post_merge_collapsed_anchor"]
    assert reconciliation["anchor_classification"] == "post_merge_collapsed_anchor"
    assert history["base_sha"] == controller.github.pulls[423]["base"]["sha"]
    assert history["head_sha"] == controller.github.pulls[423]["head"]["sha"]
    assert [reconciliation["original_delivery"], *reconciliation["superseding_prs"]] == [
        {
            "pr_number": 423,
            "branch": branch,
            "base_sha": controller.github.pulls[423]["base"]["sha"],
            "head_sha": controller.github.pulls[423]["head"]["sha"],
            "merge_sha": controller.github.pulls[423]["merge_commit_sha"],
            "merged_at": "2026-09-22T13:34:24+00:00",
            "required_check": _success_check(controller.github.pulls[423]["head"]["sha"]),
        },
        {
            "pr_number": superseding_prs[0],
            "branch": branch,
            "base_sha": controller.github.pulls[superseding_prs[0]]["base"]["sha"],
            "head_sha": controller.github.pulls[superseding_prs[0]]["head"]["sha"],
            "merge_sha": controller.github.pulls[superseding_prs[0]]["merge_commit_sha"],
            "merged_at": "2026-09-22T20:20:29+00:00",
            "required_check": _success_check(
                controller.github.pulls[superseding_prs[0]]["head"]["sha"]
            ),
        },
    ]
    assert collapsed["classification"] == "post_merge_collapsed_anchor"
    assert collapsed["observed_recovery_anchor"]["head_sha"] == deployed_sha
    assert (
        collapsed["collapsed_from_delivery_anchor"]["head_sha"]
        == controller.github.pulls[superseding_prs[0]]["head"]["sha"]
    )
    assert (
        collapsed["task_branch_transition"]["from_sha"]
        == controller.github.pulls[superseding_prs[0]]["head"]["sha"]
    )
    assert collapsed["task_branch_transition"]["to_sha"] == deployed_sha
    assert collapsed["controller_master_refresh"]["new_sha"] == deployed_sha

    result = controller.finish("415")

    assert result["cleanup_performed"] is True
    assert not worktree.exists()
    finished = controller.store.read_json(controller.store.history / "task-415.json")
    assert finished["state"] == "finished"
    assert finished["superseding_production_reconciliation"] == reconciliation


@pytest.mark.parametrize(
    ("invalid_case", "expected_error"),
    [
        ("intermediate_anchor", "no verified post-merge anchor"),
        ("dirty_worktree", "dirty or interrupted task worktree"),
        ("unique_commit", "unmerged unique task commits"),
        ("missing_deployment", "No successful production deployment"),
        ("wrong_task", "does not belong to Task 415"),
        ("broken_chain", "breaks the chronological master ancestry chain"),
        ("deployed_mismatch", "must equal the final superseding PR merge SHA"),
        ("ambiguous_branch", "one unambiguous task branch/worktree"),
        ("owner_authorization", "explicit owner authorization"),
        ("unverified_refresh", "no verified post-merge anchor"),
        ("arbitrary_branch_move", "no verified post-merge anchor"),
    ],
)
def test_reconcile_verified_post_merge_anchor_rejects_unsafe_recovery(
    repository: tuple[Path, Any], invalid_case: str, expected_error: str
) -> None:
    root, git_repository, controller, worktree, branch, superseding_prs, deployed_sha = (
        _prepare_superseding_production_reconciliation(
            repository, superseding_count=1, post_deploy_drift=False
        )
    )
    _collapse_reconciliation_anchor_after_refresh(
        root, git_repository, controller, worktree, branch, superseding_prs, deployed_sha
    )
    github = controller.github
    assert isinstance(github, FakeGitHub)
    final_pr = github.pulls[superseding_prs[0]]
    deployed_argument = deployed_sha
    owner_authorize = True
    lease_path = controller.store.task_lease_path("415")

    if invalid_case == "intermediate_anchor":
        intermediate_sha = final_pr["base"]["sha"]
        _git(worktree, "reset", "--hard", intermediate_sha)
        lease = controller.store.read_json(lease_path)
        assert isinstance(lease, dict)
        lease.update(
            {
                "base_origin_master_sha": intermediate_sha,
                "ready_head_sha": intermediate_sha,
                "ready_base_origin_master_sha": intermediate_sha,
                "delivery_base_origin_master_sha": intermediate_sha,
                "delivery_head_sha": intermediate_sha,
                "task_provenance": {
                    **lease["task_provenance"],
                    "base_sha": intermediate_sha,
                    "head_sha": intermediate_sha,
                },
                "delivery_anchor": {
                    "task_id": "415",
                    "branch": branch,
                    "base_sha": intermediate_sha,
                    "head_sha": intermediate_sha,
                },
            }
        )
        task_session.StateStore.replace_json(lease_path, lease)
    elif invalid_case == "dirty_worktree":
        (worktree / "untracked.txt").write_text("preserve\n", encoding="utf-8")
    elif invalid_case == "unique_commit":
        _git(worktree, "config", "user.name", "Task Session Tests")
        _git(worktree, "config", "user.email", "task-session@example.invalid")
        (worktree / "unique.txt").write_text("unmerged\n", encoding="utf-8")
        _git(worktree, "add", "unique.txt")
        _git(worktree, "commit", "-m", "chore: unmerged unique change")
        unique_sha = _git(worktree, "rev-parse", "HEAD")
        lease = controller.store.read_json(lease_path)
        assert isinstance(lease, dict)
        lease["ready_head_sha"] = unique_sha
        lease["delivery_head_sha"] = unique_sha
        lease["task_provenance"]["head_sha"] = unique_sha
        lease["delivery_anchor"]["head_sha"] = unique_sha
        task_session.StateStore.replace_json(lease_path, lease)
    elif invalid_case == "missing_deployment":
        github.successful_deployments.clear()
    elif invalid_case == "wrong_task":
        final_pr["title"] = "[Task 416] Synthetic task"
        final_pr["head"]["ref"] = "task/416-synthetic-task"
        github.commits[superseding_prs[0]] = [_task_commit("416")]
    elif invalid_case == "broken_chain":
        final_pr["base"]["sha"] = controller.store.read_json(lease_path)[
            "original_base_origin_master_sha"
        ]
    elif invalid_case == "deployed_mismatch":
        deployed_argument = final_pr["base"]["sha"]
    elif invalid_case == "ambiguous_branch":
        _git(root, "branch", "task/415-duplicate", "origin/master")
    elif invalid_case == "owner_authorization":
        owner_authorize = False
    elif invalid_case == "unverified_refresh":
        lease = controller.store.read_json(lease_path)
        assert isinstance(lease, dict)
        lease["canonical_master_refresh"]["delivery_task_id"] = "416"
        task_session.StateStore.replace_json(lease_path, lease)
    elif invalid_case == "arbitrary_branch_move":
        ref = f"refs/heads/{branch}"
        _git(
            root,
            "update-ref",
            "-m",
            "reset: moving to PR head",
            ref,
            final_pr["head"]["sha"],
            deployed_sha,
        )
        _git(
            root,
            "update-ref",
            "-m",
            "reset: moving back to merge",
            ref,
            deployed_sha,
            final_pr["head"]["sha"],
        )

    with pytest.raises(task_session.TaskSessionError, match=expected_error):
        controller.reconcile_production_success(
            "415",
            original_pr_number=423,
            superseding_pr_numbers=superseding_prs,
            deployed_sha=deployed_argument,
            production_run_id=35783412553,
            owner_authorize=owner_authorize,
        )

    assert controller.store.read_json(lease_path)["lifecycle_state"] == "human-required"
    assert not (controller.store.history / "task-415.json").exists()


@pytest.mark.parametrize("superseding_count", [1, 2])
def test_reconcile_superseding_production_preserves_anchor_and_all_evidence(
    repository: tuple[Path, Any], superseding_count: int
) -> None:
    _, git_repository, controller, worktree, branch, superseding_prs, deployed_sha = (
        _prepare_superseding_production_reconciliation(
            repository, superseding_count=superseding_count
        )
    )
    lease_path = controller.store.task_lease_path("415")
    original_lease = controller.store.read_json(lease_path)
    assert isinstance(original_lease, dict)
    original_anchor = original_lease["delivery_anchor"]

    history = controller.reconcile_production_success(
        "415",
        original_pr_number=423,
        superseding_pr_numbers=superseding_prs,
        deployed_sha=deployed_sha,
        production_run_id=35783412553,
        owner_authorize=True,
    )

    reconciliation = history["superseding_production_reconciliation"]
    assert history["state"] == "production-success"
    assert history["head_sha"] == original_anchor["head_sha"]
    assert history["base_sha"] == original_anchor["base_sha"]
    assert history["merge_sha"] == deployed_sha
    assert history["deployed_sha"] == deployed_sha
    assert reconciliation["reconciled_against_master_sha"] != deployed_sha
    assert git_repository.is_ancestor(deployed_sha, reconciliation["reconciled_against_master_sha"])
    assert reconciliation["original_delivery"]["pr_number"] == 423
    assert reconciliation["original_delivery"]["merge_sha"] != deployed_sha
    assert [item["pr_number"] for item in reconciliation["superseding_prs"]] == superseding_prs
    assert all(
        item["required_check"]["conclusion"] == "SUCCESS"
        for item in reconciliation["superseding_prs"]
    )
    assert reconciliation["production"]["run_id"] == 35783412553
    assert reconciliation["production"]["deployed_sha"] == deployed_sha
    reconciled_lease = controller.store.read_json(lease_path)
    assert isinstance(reconciled_lease, dict)
    assert reconciled_lease["lifecycle_state"] == "deployed"
    assert reconciled_lease["delivery_anchor"] == original_anchor
    assert controller.store.delivery_state()["owner"] is None

    result = controller.finish("415")

    assert result["cleanup_performed"] is True
    assert result["deleted_local_branch"] == branch
    assert not worktree.exists()
    assert not git_repository.ref_exists(branch)
    assert not lease_path.exists()
    finished_history = controller.store.read_json(controller.store.history / "task-415.json")
    assert finished_history["state"] == "finished"
    assert finished_history["superseding_production_reconciliation"] == reconciliation


def test_reconcile_single_pr_collapsed_anchor_for_task_507_and_finishes(
    repository: tuple[Path, Any],
) -> None:
    (
        _root,
        git_repository,
        controller,
        worktree,
        branch,
        base_sha,
        head_sha,
        deployed_sha,
        _github,
    ) = _prepare_single_collapsed_production_reconciliation(repository)

    history = controller.reconcile_production_success(
        "507",
        original_pr_number=578,
        superseding_pr_numbers=[],
        deployed_sha=deployed_sha,
        production_run_id=36590222806,
        owner_authorize=True,
    )

    reconciliation = history["superseding_production_reconciliation"]
    assert history["state"] == "production-success"
    assert history["base_sha"] == base_sha
    assert history["head_sha"] == head_sha
    assert history["merge_sha"] == deployed_sha
    assert reconciliation["anchor_classification"] == "post_merge_collapsed_anchor"
    assert reconciliation["original_delivery"]["pr_number"] == 578
    assert reconciliation["original_delivery"]["head_sha"] == head_sha
    assert reconciliation["original_delivery"]["merge_sha"] == deployed_sha
    assert reconciliation["superseding_prs"] == []
    assert reconciliation["production"]["run_id"] == 36590222806
    assert reconciliation["post_merge_collapsed_anchor"]["classification"] == (
        "post_merge_collapsed_anchor"
    )

    result = controller.finish("507")

    assert result["cleanup_performed"] is True
    assert result["deleted_local_branch"] == branch
    assert not worktree.exists()
    assert not git_repository.ref_exists(branch)
    assert controller.store.read_json(controller.store.history / "task-507.json")["state"] == (
        "finished"
    )


@pytest.mark.parametrize(
    ("invalid_case", "expected_error"),
    [
        ("wrong_reflog_prior", "no verified post-merge anchor"),
        ("wrong_rebase_message", "no verified post-merge anchor"),
        ("current_branch_not_deployed", "no longer matches its delivery anchor"),
        ("deployed_sha_mismatch", "final superseding PR merge SHA"),
        ("failed_run", "not successful for the exact deployed SHA"),
        ("wrong_run", "not successful for the exact deployed SHA"),
        ("missing_deployment", "No successful production deployment"),
        ("failed_check", "Exact-head required check"),
        ("unique_commit", "unmerged unique task commits"),
    ],
)
def test_reconcile_single_pr_collapsed_anchor_rejects_unsafe_evidence(
    repository: tuple[Path, Any], invalid_case: str, expected_error: str
) -> None:
    (
        root,
        _git_repository,
        controller,
        worktree,
        branch,
        base_sha,
        head_sha,
        deployed_sha,
        github,
    ) = _prepare_single_collapsed_production_reconciliation(repository)
    lease_path = controller.store.task_lease_path("507")
    deployed_argument = deployed_sha
    production_run = 36590222806

    if invalid_case == "wrong_reflog_prior":
        ref = f"refs/heads/{branch}"
        _git(
            root,
            "update-ref",
            "-m",
            "controller transition noise",
            ref,
            base_sha,
            deployed_sha,
        )
        _git(
            root,
            "update-ref",
            "-m",
            f"rebase (finish): {ref} onto {deployed_sha}",
            ref,
            deployed_sha,
            base_sha,
        )
    elif invalid_case == "wrong_rebase_message":
        ref = f"refs/heads/{branch}"
        _git(root, "update-ref", "-m", "controller transition noise", ref, head_sha, deployed_sha)
        _git(root, "update-ref", "-m", "rebase (finish): wrong", ref, deployed_sha, head_sha)
    elif invalid_case == "current_branch_not_deployed":
        _git(worktree, "checkout", "--detach", base_sha)
    elif invalid_case == "deployed_sha_mismatch":
        deployed_argument = "f" * 40
    elif invalid_case == "failed_run":
        github.runs[36590222806]["conclusion"] = "failure"
    elif invalid_case == "wrong_run":
        github.runs[36590222807] = {
            **github.runs[36590222806],
            "id": 36590222807,
            "head_sha": head_sha,
        }
        production_run = 36590222807
    elif invalid_case == "missing_deployment":
        github.successful_deployments.clear()
    elif invalid_case == "failed_check":
        github.checks[head_sha] = [
            {
                "name": "checks",
                "head_sha": head_sha,
                "status": "completed",
                "conclusion": "FAILURE",
            }
        ]
    elif invalid_case == "unique_commit":
        _git(worktree, "config", "user.name", "Task Session Tests")
        _git(worktree, "config", "user.email", "task-session@example.invalid")
        (worktree / "unique.txt").write_text("unpublished\n", encoding="utf-8")
        _git(worktree, "add", "unique.txt")
        _git(worktree, "commit", "-m", "chore: unpublished unique task change")
        unique_sha = _git(worktree, "rev-parse", "HEAD")
        lease = controller.store.read_json(lease_path)
        assert isinstance(lease, dict)
        for key in ("ready_head_sha", "delivery_head_sha"):
            lease[key] = unique_sha
        lease["task_provenance"]["head_sha"] = unique_sha
        lease["delivery_anchor"]["head_sha"] = unique_sha
        task_session.StateStore.replace_json(lease_path, lease)

    with pytest.raises(task_session.TaskSessionError, match=expected_error):
        controller.reconcile_production_success(
            "507",
            original_pr_number=578,
            superseding_pr_numbers=[],
            deployed_sha=deployed_argument,
            production_run_id=production_run,
            owner_authorize=True,
        )

    assert controller.store.read_json(lease_path)["lifecycle_state"] == "human-required"
    assert not (controller.store.history / "task-507.json").exists()


def test_reconcile_empty_superseding_list_refuses_normal_exact_anchor(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, _, _, _, deployed_sha = _prepare_superseding_production_reconciliation(
        repository, superseding_count=0, post_deploy_drift=False
    )

    with pytest.raises(
        task_session.TaskSessionError,
        match="Single-PR production reconciliation requires a verified post-merge collapsed anchor",
    ):
        controller.reconcile_production_success(
            "415",
            original_pr_number=423,
            superseding_pr_numbers=[],
            deployed_sha=deployed_sha,
            production_run_id=35783412553,
            owner_authorize=True,
        )


def test_reconcile_refreshes_stale_tracking_master_before_verification(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository, controller, _, _, superseding_prs, deployed_sha = (
        _prepare_superseding_production_reconciliation(repository)
    )
    github = controller.github
    assert isinstance(github, FakeGitHub)
    tracked_before = git_repository.ref("origin/master")
    tree_sha = _git(root, "rev-parse", f"{tracked_before}^{{tree}}")
    live_master = _git(
        root,
        "commit-tree",
        tree_sha,
        "-p",
        tracked_before,
        "-m",
        "feat: [Task 416] master advanced before controller reconciliation",
    )
    _git(root, "reset", "--hard", live_master)
    _git(root, "push", "origin", "master")
    _git(root, "update-ref", "refs/remotes/origin/master", tracked_before)
    github.master_sha = live_master
    assert git_repository.ref("origin/master") == tracked_before

    history = controller.reconcile_production_success(
        "415",
        original_pr_number=423,
        superseding_pr_numbers=superseding_prs,
        deployed_sha=deployed_sha,
        production_run_id=35783412553,
        owner_authorize=True,
    )

    assert git_repository.ref("origin/master") == live_master
    assert (
        history["superseding_production_reconciliation"]["reconciled_against_master_sha"]
        == live_master
    )
    assert git_repository.ref("master") == live_master


def test_finish_rejects_non_controller_drift_after_reconciliation_snapshot(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository, controller, worktree, branch, superseding_prs, deployed_sha = (
        _prepare_superseding_production_reconciliation(repository, post_deploy_drift=False)
    )
    controller.reconcile_production_success(
        "415",
        original_pr_number=423,
        superseding_pr_numbers=superseding_prs,
        deployed_sha=deployed_sha,
        production_run_id=35783412553,
        owner_authorize=True,
    )
    tree_sha = _git(root, "rev-parse", f"{deployed_sha}^{{tree}}")
    product_drift = _git(
        root,
        "commit-tree",
        tree_sha,
        "-p",
        deployed_sha,
        "-m",
        "feat: [Task 416] later product change",
    )
    _git(root, "reset", "--hard", product_drift)
    _git(root, "push", "origin", "master")
    _git(root, "fetch", "origin", "master")
    github = controller.github
    assert isinstance(github, FakeGitHub)
    github.master_sha = product_drift

    with pytest.raises(
        task_session.TaskSessionError, match="non-controller drift after reconciled master"
    ):
        controller.finish("415")

    assert worktree.exists()
    assert git_repository.ref_exists(branch)
    assert (
        controller.store.read_json(controller.store.task_lease_path("415"))["lifecycle_state"]
        == "deployed"
    )


def test_reconcile_superseding_production_requires_owner_authorization(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, _, _, superseding_prs, deployed_sha = (
        _prepare_superseding_production_reconciliation(repository)
    )

    with pytest.raises(task_session.TaskSessionError, match="explicit owner authorization"):
        controller.reconcile_production_success(
            "415",
            original_pr_number=423,
            superseding_pr_numbers=superseding_prs,
            deployed_sha=deployed_sha,
            production_run_id=35783412553,
            owner_authorize=False,
        )

    assert (
        controller.store.read_json(controller.store.task_lease_path("415"))["lifecycle_state"]
        == task_session.HUMAN_REQUIRED_STATE
    )
    assert not (controller.store.history / "task-415.json").exists()


@pytest.mark.parametrize(
    "superseding_numbers,error",
    [
        ([], "final superseding PR merge SHA"),
        ([423], "positive and unique"),
        ([432, 432], "positive and unique"),
    ],
)
def test_reconcile_superseding_production_rejects_missing_or_duplicate_pr_numbers(
    repository: tuple[Path, Any], superseding_numbers: list[int], error: str
) -> None:
    _, _, controller, _, _, _, deployed_sha = _prepare_superseding_production_reconciliation(
        repository
    )

    with pytest.raises(task_session.TaskSessionError, match=error):
        controller.reconcile_production_success(
            "415",
            original_pr_number=423,
            superseding_pr_numbers=superseding_numbers,
            deployed_sha=deployed_sha,
            production_run_id=35783412553,
            owner_authorize=True,
        )

    assert (
        controller.store.read_json(controller.store.task_lease_path("415"))["lifecycle_state"]
        == task_session.HUMAN_REQUIRED_STATE
    )


@pytest.mark.parametrize(
    "invalid_case,expected_error",
    [
        ("wrong_task", "does not belong to Task 415"),
        ("wrong_repository", "same repository"),
        ("wrong_base_branch", "base must be master"),
        ("unmerged", "not a closed pull request"),
        ("failed_check", "Exact-head required check"),
        ("broken_chain", "breaks the chronological master ancestry chain"),
        ("wrong_order", "breaks the chronological master ancestry chain"),
        ("malformed_pr", "invalid changed_files count"),
        ("final_sha_mismatch", "must equal the final superseding PR merge SHA"),
        ("missing_deployment", "No successful production deployment"),
        ("failed_run", "not successful for the exact deployed SHA"),
        ("active_deployment", "while a production deployment is active"),
        ("active_delivery_owner", "active delivery owner"),
        ("duplicate_history", "Production history already exists"),
        ("malformed_anchor", "does not preserve one exact delivery anchor"),
        ("dirty_worktree", "dirty or interrupted task worktree"),
        ("dirty_controller", "clean controller worktree"),
        ("duplicate_branch", "one unambiguous task branch/worktree"),
        ("out_of_master", "not an ancestor of current master"),
    ],
)
def test_reconcile_superseding_production_rejects_ambiguous_or_invalid_evidence(
    repository: tuple[Path, Any], invalid_case: str, expected_error: str
) -> None:
    root, git_repository, controller, worktree, _, superseding_prs, deployed_sha = (
        _prepare_superseding_production_reconciliation(repository)
    )
    github = controller.github
    assert isinstance(github, FakeGitHub)
    final_pr = github.pulls[superseding_prs[-1]]
    final_head_sha = final_pr["head"]["sha"]

    if invalid_case == "wrong_task":
        final_pr["title"] = "[Task 416] Synthetic task"
        final_pr["head"]["ref"] = "task/416-synthetic-task"
        github.commits[superseding_prs[-1]] = [_task_commit("416")]
    elif invalid_case == "wrong_repository":
        final_pr["head"]["repo"]["full_name"] = "another/repository"
    elif invalid_case == "wrong_base_branch":
        final_pr["base"]["ref"] = "develop"
    elif invalid_case == "unmerged":
        final_pr["state"] = "open"
        final_pr["merged_at"] = None
    elif invalid_case == "failed_check":
        github.checks[final_head_sha] = [
            {
                "name": "checks",
                "head_sha": final_head_sha,
                "status": "completed",
                "conclusion": "FAILURE",
            }
        ]
    elif invalid_case == "broken_chain":
        final_pr["base"]["sha"] = controller.store.read_json(
            controller.store.task_lease_path("415")
        )["base_origin_master_sha"]
    elif invalid_case == "wrong_order":
        superseding_prs.reverse()
    elif invalid_case == "malformed_pr":
        final_pr["changed_files"] = "two"
    elif invalid_case == "final_sha_mismatch":
        deployed_sha = "f" * 40
    elif invalid_case == "missing_deployment":
        github.successful_deployments.clear()
    elif invalid_case == "failed_run":
        github.runs[35783412553]["conclusion"] = "failure"
    elif invalid_case == "active_deployment":
        github.active_runs = [{"name": "Release production", "status": "in_progress"}]
    elif invalid_case == "active_delivery_owner":
        delivery = controller.store.delivery_state()
        delivery["owner"] = {"task_id": "416"}
        task_session.StateStore.replace_json(controller.store.delivery_path, delivery)
    elif invalid_case == "duplicate_history":
        task_session.StateStore.replace_json(
            controller.store.history / "task-415.json", {"state": "stale"}
        )
    elif invalid_case == "malformed_anchor":
        lease_path = controller.store.task_lease_path("415")
        lease = controller.store.read_json(lease_path)
        lease["delivery_anchor"] = None
        task_session.StateStore.replace_json(lease_path, lease)
    elif invalid_case == "dirty_worktree":
        (worktree / "untracked.txt").write_text("preserve\n", encoding="utf-8")
    elif invalid_case == "dirty_controller":
        (root / "uncommitted-controller-file.txt").write_text("preserve\n", encoding="utf-8")
    elif invalid_case == "duplicate_branch":
        _git(root, "branch", "task/415-duplicate", "origin/master")
    elif invalid_case == "out_of_master":
        final_base = final_pr["base"]["sha"]
        tree_sha = _git(root, "rev-parse", f"{final_base}^{{tree}}")
        final_pr["merge_commit_sha"] = _git(
            root,
            "commit-tree",
            tree_sha,
            "-p",
            final_base,
            "-m",
            "Merge pull request with unmerged final SHA",
        )
        deployed_sha = final_pr["merge_commit_sha"]

    master_before = git_repository.ref("master")

    with pytest.raises(task_session.TaskSessionError, match=expected_error):
        controller.reconcile_production_success(
            "415",
            original_pr_number=423,
            superseding_pr_numbers=superseding_prs,
            deployed_sha=deployed_sha,
            production_run_id=35783412553,
            owner_authorize=True,
        )

    lease = controller.store.read_json(controller.store.task_lease_path("415"))
    assert lease["lifecycle_state"] == "human-required"
    if invalid_case != "duplicate_history":
        assert not (controller.store.history / "task-415.json").exists()
    if invalid_case != "active_delivery_owner":
        assert controller.store.delivery_state()["owner"] is None
    assert git_repository.ref("master") == master_before


def test_reconcile_superseding_production_rechecks_live_master_before_write(
    repository: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, controller, _, _, superseding_prs, deployed_sha = (
        _prepare_superseding_production_reconciliation(repository)
    )
    github = controller.github
    assert isinstance(github, FakeGitHub)
    original_branch_head = github.branch_head
    calls = 0

    def change_live_master(branch: str) -> str:
        nonlocal calls
        calls += 1
        return original_branch_head(branch) if calls == 1 else "f" * 40

    monkeypatch.setattr(github, "branch_head", change_live_master)

    with pytest.raises(task_session.TaskSessionError, match="not the live protected master"):
        controller.reconcile_production_success(
            "415",
            original_pr_number=423,
            superseding_pr_numbers=superseding_prs,
            deployed_sha=deployed_sha,
            production_run_id=35783412553,
            owner_authorize=True,
        )

    assert calls == 2
    assert (
        controller.store.read_json(controller.store.task_lease_path("415"))["lifecycle_state"]
        == task_session.HUMAN_REQUIRED_STATE
    )
    assert not (controller.store.history / "task-415.json").exists()


def test_run_scopes_git_safety_to_exact_worktree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    observed: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed["args"] = args[0]
        return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")

    monkeypatch.setattr(task_session.subprocess, "run", fake_run)
    task_session._run(["git", "status", "--short"], cwd=tmp_path)
    command = observed["args"]
    assert command[:3] == ["git", "-c", f"safe.directory={tmp_path.resolve().as_posix()}"]
    if task_session.os.name == "nt":
        assert command[3:5] == ["-c", "core.longpaths=true"]


@pytest.mark.parametrize("task_id", ["127", "90A", "124C"])
def test_task_ids_and_branch_traceability_accept_suffix_ids(task_id: str) -> None:
    task_session.validate_task_commit_messages(task_id, [f"fix: [Task {task_id}] preserve trace"])
    assert task_session.task_id_from_branch(f"task/{task_id}-valid-kebab") == task_id


def test_task_commit_messages_allow_only_declared_hard_dependencies() -> None:
    messages = [
        "feat: [Task 133] provide dependency",
        "feat: [Task 135] consume dependency\n\nDepends-on: [Task 133], [Task 134]",
    ]

    task_session.validate_task_commit_messages("135", messages, dependency_ids=("133", "134"))

    with pytest.raises(task_session.TaskSessionError, match="declared hard dependency"):
        task_session.validate_task_commit_messages(
            "135",
            [*messages, "fix: [Task 136] unrelated change"],
            dependency_ids=("133", "134"),
        )


def test_task_commit_messages_allow_origin_master_integration_merge() -> None:
    task_session.validate_task_commit_messages(
        "393",
        [
            "Merge remote-tracking branch 'origin/master' into task/393-app-experience-v3-final-hardening",
            "fix: [Task 393] preserve trace",
        ],
    )

    with pytest.raises(task_session.TaskSessionError, match="must contain exactly"):
        task_session.validate_task_commit_messages(
            "393",
            [
                "Merge branch 'other' into task/393-app-experience-v3-final-hardening",
                "fix: [Task 393] preserve trace",
            ],
        )


def test_task_pr_accepts_dependency_provenance_declared_in_task_commit() -> None:
    base_sha = "a" * 40
    head_sha = "b" * 40
    pull_request = _task_pr(135, "135", base_sha, head_sha)
    pull_request["commits"] = 2
    commits = [
        _task_commit("133"),
        {"commit": {"message": "feat: [Task 135] consume dependency\n\nDepends-on: [Task 133]"}},
    ]

    assert (
        task_session.validate_task_pull_request(
            pull_request,
            commits,
            [_success_check(head_sha)],
            expected_base_sha=base_sha,
            dependency_ids=None,
        )
        == "135"
    )


def test_task_pr_accepts_task_393_integration_branch_and_completed_stages() -> None:
    base_sha = "a" * 40
    head_sha = "b" * 40
    pull_request = _task_pr(393, "393", base_sha, head_sha)
    pull_request["head"]["ref"] = "feature/app-experience-v3"
    pull_request["commits"] = 2
    commits = [
        {"commit": {"message": "[Task 391] Make active workout media full width on mobile"}},
        {
            "commit": {
                "message": (
                    "[Task 393] Integrate approved stages\n\n"
                    "Depends-on: [Task 386], [Task 387], [Task 388], [Task 389], "
                    "[Task 390], [Task 391], [Task 392], [Task 395], [Task 396], "
                    "[Task 397], [Task 400]"
                )
            }
        },
    ]

    assert (
        task_session.validate_task_pull_request(
            pull_request,
            commits,
            [_success_check(head_sha)],
            expected_base_sha=base_sha,
            dependency_ids=None,
        )
        == "393"
    )


@pytest.mark.parametrize(
    "branch", ["feature/127-x", "task/127", "task/127-Bad-Slug", "task/127_bad", "task/A127-test"]
)
def test_invalid_task_branch_names_fail_closed(branch: str) -> None:
    with pytest.raises(task_session.TaskSessionError, match="must match"):
        task_session.task_id_from_branch(branch)


def test_task_pr_requires_master_and_exact_head_check() -> None:
    base_sha = "a" * 40
    head_sha = "b" * 40
    pull_request = _task_pr(135, "135", base_sha, head_sha)
    assert (
        task_session.validate_task_pull_request(
            pull_request,
            [_task_commit("135")],
            [_success_check(head_sha)],
            expected_base_sha=base_sha,
        )
        == "135"
    )

    pull_request["base"]["ref"] = "dev"
    with pytest.raises(task_session.TaskSessionError, match="base must be master"):
        task_session.validate_task_pull_request(
            pull_request,
            [_task_commit("135")],
            [_success_check(head_sha)],
            expected_base_sha=base_sha,
        )


def test_validate_pr_event_rejects_base_behind_live_master(
    tmp_path: Path,
) -> None:
    base_sha = "a" * 40
    live_master_sha = "c" * 40
    head_sha = "b" * 40
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps({"pull_request": _task_pr(135, "135", base_sha, head_sha)}),
        encoding="utf-8",
    )
    github = FakeGitHub(live_master_sha)
    github.commits[135] = [_task_commit("135")]
    with pytest.raises(task_session.TaskSessionError, match="Task PR is stale"):
        task_session.validate_pr_event(object(), github, event_path)  # type: ignore[arg-type]


def test_validate_pr_event_accepts_trusted_dependabot_without_task_branch(
    tmp_path: Path,
) -> None:
    base_sha = "a" * 40
    live_master_sha = "c" * 40
    head_sha = "b" * 40
    pull_request = _task_pr(178, "178", base_sha, head_sha)
    pull_request["head"]["ref"] = "dependabot/pip/wrapt-2.4.0"
    pull_request["user"] = {"login": "dependabot[bot]", "type": "Bot"}
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"pull_request": pull_request}), encoding="utf-8")

    result = task_session.validate_pr_event(
        object(),
        FakeGitHub(live_master_sha),
        event_path,  # type: ignore[arg-type]
    )

    assert result == {"kind": "dependabot-pr", "head_sha": head_sha}


def test_validate_pr_event_accepts_controller_maintenance_branch(
    tmp_path: Path,
) -> None:
    base_sha = "a" * 40
    head_sha = "b" * 40
    pull_request = _controller_pr(base_sha, head_sha)
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"pull_request": pull_request}), encoding="utf-8")
    github = FakeGitHub(base_sha)
    github.commits[234] = [_controller_commit()]
    github.files[234] = [{"filename": "scripts/task_session.py"}]

    result = task_session.validate_pr_event(
        object(),
        github,
        event_path,  # type: ignore[arg-type]
    )

    assert result == {
        "kind": "controller-pr",
        "branch": "codex/controller-synthetic-maintenance",
        "head_sha": head_sha,
    }


def test_controller_pr_rejects_product_paths(
    tmp_path: Path,
) -> None:
    base_sha = "a" * 40
    head_sha = "b" * 40
    pull_request = _controller_pr(base_sha, head_sha)
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"pull_request": pull_request}), encoding="utf-8")
    github = FakeGitHub(base_sha)
    github.commits[234] = [_controller_commit()]
    github.files[234] = [{"filename": "backend/app.py"}]

    with pytest.raises(task_session.TaskSessionError, match="outside the governance allowlist"):
        task_session.validate_pr_event(  # type: ignore[arg-type]
            object(),
            github,
            event_path,
        )


def test_controller_pr_accepts_only_the_new_artifact_cleanup_paths() -> None:
    task_session.validate_controller_pull_request_files(
        [
            {"filename": "scripts/artifact_manager.py"},
            {"filename": "tests/test_artifact_manager.py"},
        ]
    )
    with pytest.raises(task_session.TaskSessionError, match="outside the governance allowlist"):
        task_session.validate_controller_pull_request_files(
            [
                {"filename": "scripts/artifact_manager.py"},
                {"filename": "scripts/unrelated.py"},
            ]
        )


def test_controller_pr_accepts_issue_workflow_contract_paths() -> None:
    task_session.validate_controller_pull_request_files(
        [
            {"filename": "scripts/issue_workflow.py"},
            {"filename": "tests/test_issue_workflow.py"},
        ]
    )


@pytest.mark.parametrize("branch", ["codex/controller-foo", "task/999-controller-foo"])
def test_controller_release_skips_allowlisted_diff_for_controller_and_task_branches(
    branch: str,
) -> None:
    merge_sha = "c" * 40
    pull_request = _merged_release_pr(
        999,
        merge_sha,
        branch=branch,
        title="[Controller] Foo",
        paths=["scripts/task_session.py"],
    )
    result = task_session.classify_controller_release(
        _release_github([pull_request], {999: ["scripts/task_session.py"]}),
        deploy_sha=merge_sha,
        repository="owner/repository",
    )

    assert result["controller_only"] is True
    assert result["deploy"] is False


def test_controller_release_skips_task_735_security_only_diff() -> None:
    merge_sha = "c" * 40
    paths = [
        ".github/workflows/ci.yml",
        ".github/workflows/security-audit.yml",
        "scripts/codeql_sarif_gate.py",
        "scripts/task_session.py",
        "security/SECURITY_REVIEW.md",
        "tests/test_ci_contract.py",
        "tests/test_codeql_sarif_gate.py",
        "tests/test_release_safeguards.py",
        "tests/test_task_session.py",
    ]
    pull_request = _merged_release_pr(
        735,
        merge_sha,
        branch="task/735-codeql-gate-final-v2",
        title="[Task 735] Enforce CodeQL SARIF security gate",
        paths=paths,
    )
    result = task_session.classify_controller_release(
        _release_github([pull_request], {735: paths}),
        deploy_sha=merge_sha,
        repository="owner/repository",
    )

    assert result["controller_only"] is True
    assert result["deploy"] is False


def test_controller_release_skips_worker_guard_only_diff() -> None:
    merge_sha = "c" * 40
    pull_request = _merged_release_pr(
        999,
        merge_sha,
        branch="codex/controller-worker-guard-compatibility",
        title="[Controller] Worker guard compatibility",
        paths=["scripts/worker_guard.py"],
    )
    result = task_session.classify_controller_release(
        _release_github([pull_request], {999: ["scripts/worker_guard.py"]}),
        deploy_sha=merge_sha,
        repository="owner/repository",
    )

    assert result["controller_only"] is True
    assert result["deploy"] is False


def test_controller_release_skips_agent_harness_governance_diff() -> None:
    merge_sha = "c" * 40
    paths = [
        ".agents/MANIFEST.json",
        ".agents/evals/lifecycle.json",
        "AGENTS.md",
        "docs/agent-harness.md",
        "scripts/agent_harness.py",
        "tests/test_agent_harness.py",
    ]
    pull_request = _merged_release_pr(
        999,
        merge_sha,
        branch="task/999-agent-harness",
        title="[Task 999] Agent Harness",
        paths=paths,
    )
    result = task_session.classify_controller_release(
        _release_github([pull_request], {999: paths}),
        deploy_sha=merge_sha,
        repository="owner/repository",
    )

    assert result["controller_only"] is True
    assert result["deploy"] is False


@pytest.mark.parametrize(
    ("branch", "title", "paths"),
    [
        ("task/999-product-change", "[Task 999] Product", ["backend/app.py"]),
        (
            "task/735-codeql-gate-final-v2",
            "[Task 735] Mixed security/runtime",
            [".github/workflows/ci.yml", "backend/app.py"],
        ),
        ("task/999-product-change", "[Controller] Fake", ["backend/app.py"]),
        ("codex/controller-foo", "[Controller] Fake", ["backend/app.py"]),
        (
            "task/999-mixed-change",
            "[Controller] Mixed",
            ["scripts/task_session.py", "backend/app.py"],
        ),
        ("task/999-unknown-change", "[Controller] Unknown", ["new/unknown.txt"]),
    ],
)
def test_controller_release_defaults_to_application_deploy_for_non_controller_scope(
    branch: str, title: str, paths: list[str]
) -> None:
    merge_sha = "c" * 40
    pull_request = _merged_release_pr(
        999,
        merge_sha,
        branch=branch,
        title=title,
        paths=paths,
    )
    result = task_session.classify_controller_release(
        _release_github([pull_request], {999: paths}),
        deploy_sha=merge_sha,
        repository="owner/repository",
    )

    assert result["controller_only"] is False
    assert result["deploy"] is True


def test_controller_release_does_not_skip_mixed_pull_requests_sharing_merge_sha() -> None:
    merge_sha = "c" * 40
    controller_pr = _merged_release_pr(
        999,
        merge_sha,
        branch="codex/controller-foo",
        title="[Controller] Foo",
        paths=["scripts/task_session.py"],
    )
    product_pr = _merged_release_pr(
        1000,
        merge_sha,
        branch="task/1000-product-change",
        title="[Task 1000] Product",
        paths=["frontend/src/App.tsx"],
    )

    result = task_session.classify_controller_release(
        _release_github(
            [controller_pr, product_pr],
            {999: ["scripts/task_session.py"], 1000: ["frontend/src/App.tsx"]},
        ),
        deploy_sha=merge_sha,
        repository="owner/repository",
    )

    assert result["deploy"] is True


def test_controller_release_defaults_to_application_deploy_for_incomplete_file_inventory() -> None:
    merge_sha = "c" * 40
    pull_request = _merged_release_pr(
        999,
        merge_sha,
        branch="task/999-controller-foo",
        title="[Controller] Foo",
        paths=["scripts/task_session.py", "tests/test_task_session.py"],
        declared_count=2,
    )
    result = task_session.classify_controller_release(
        _release_github([pull_request], {999: ["scripts/task_session.py"]}),
        deploy_sha=merge_sha,
        repository="owner/repository",
    )

    assert result["deploy"] is True


def test_controller_release_defaults_to_application_deploy_when_file_lookup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    merge_sha = "c" * 40
    pull_request = _merged_release_pr(
        999,
        merge_sha,
        branch="task/999-controller-foo",
        title="[Controller] Foo",
        paths=["scripts/task_session.py"],
    )
    github = _release_github([pull_request], {999: ["scripts/task_session.py"]})

    def fail(_number: int) -> list[dict[str, Any]]:
        raise task_session.TaskSessionError("changed files unavailable")

    monkeypatch.setattr(github, "pull_request_files", fail)
    result = task_session.classify_controller_release(
        github,
        deploy_sha=merge_sha,
        repository="owner/repository",
    )

    assert result["deploy"] is True


def test_controller_release_preserves_exact_merge_provenance_refusal() -> None:
    pull_request = _merged_release_pr(
        999,
        "d" * 40,
        branch="task/999-controller-foo",
        title="[Controller] Foo",
        paths=["scripts/task_session.py"],
    )
    github = _release_github([pull_request], {999: ["scripts/task_session.py"]})
    github.associated_pulls_by_commit["c" * 40] = [{**pull_request, "merge_commit_sha": "c" * 40}]

    with pytest.raises(
        task_session.TaskSessionError, match="does not prove the exact merge provenance"
    ):
        task_session.classify_controller_release(
            github,
            deploy_sha="c" * 40,
            repository="owner/repository",
        )


def test_pull_request_changed_file_lookup_reads_every_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = object.__new__(task_session.GitHubClient)
    requests: list[str] = []

    def api(endpoint: str) -> list[dict[str, str]]:
        requests.append(endpoint)
        if endpoint.endswith("page=1"):
            return [{"filename": "scripts/task_session.py"}] * 100
        if endpoint.endswith("page=2"):
            return [{"filename": "tests/test_task_session.py"}]
        raise AssertionError(f"Unexpected endpoint: {endpoint}")

    monkeypatch.setattr(client, "api", api)

    assert len(client.pull_request_files(999)) == 101
    assert requests == [
        "pulls/999/files?per_page=100&page=1",
        "pulls/999/files?per_page=100&page=2",
    ]


def test_validate_pr_event_rejects_dependabot_branch_for_regular_user(
    tmp_path: Path,
) -> None:
    base_sha = "a" * 40
    head_sha = "b" * 40
    pull_request = _task_pr(178, "178", base_sha, head_sha)
    pull_request["head"]["ref"] = "dependabot/pip/wrapt-2.4.0"
    pull_request["user"] = {"login": "ordinary-user", "type": "User"}
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"pull_request": pull_request}), encoding="utf-8")
    github = FakeGitHub(base_sha)
    github.commits[178] = [_task_commit("178")]

    with pytest.raises(task_session.TaskSessionError, match="must match"):
        task_session.validate_pr_event(object(), github, event_path)  # type: ignore[arg-type]


def test_controller_pr_validation_requires_exact_checks_without_review_evidence() -> None:
    base_sha = "a" * 40
    head_sha = "b" * 40

    assert (
        task_session.validate_controller_pull_request(
            _controller_pr(base_sha, head_sha),
            [_controller_commit()],
            [_success_check(head_sha)],
            expected_base_sha=base_sha,
        )
        == "codex/controller-synthetic-maintenance"
    )

    controller_methods = dir(task_session.TaskController)
    assert "request_codex_review" not in controller_methods
    assert "validate_codex_review" not in controller_methods


def test_master_ruleset_requires_pr_current_base_and_aggregate_check() -> None:
    weak = [
        {
            "target": "branch",
            "enforcement": "active",
            "conditions": {"ref_name": {"include": ["refs/heads/master"]}},
            "rules": [{"type": "pull_request"}],
        }
    ]
    issues = task_session.validate_master_ruleset(weak)
    assert "master Ruleset is missing deletion" in issues
    assert "master Ruleset is missing required_status_checks" in issues

    strong = [
        {
            "target": "branch",
            "enforcement": "active",
            "conditions": {"ref_name": {"include": ["refs/heads/master"]}},
            "rules": [
                {"type": "deletion"},
                {"type": "non_fast_forward"},
                {"type": "pull_request"},
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "strict_required_status_checks_policy": True,
                        "required_status_checks": [{"context": "checks"}],
                    },
                },
            ],
        }
    ]
    assert task_session.validate_master_ruleset(strong) == []


def test_start_uses_exact_origin_master_and_records_no_dev_lane(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    _write_task(root, "201", "start-me")
    controller = task_session.TaskController(
        git_repository, github=FakeGitHub(git_repository.ref("origin/master"))
    )

    started = controller.start("201", owner_launch=True, session_label="pytest", offline=True)
    lease = started["lease"]
    assert lease["base_origin_master_sha"] == git_repository.ref("origin/master")
    assert lease["target_base_branch"] == "master"
    assert lease["integration_policy"] == "task-pr-to-master"
    assert lease["concurrency_class"] == "independent-write"
    assert "base_origin_dev_sha" not in lease
    assert "PR master" in started["prompt"]
    assert "GitHub exact-head checks" in started["prompt"]
    assert "Delivery ownership is coordination bookkeeping" in started["prompt"]


def test_issue_dependency_override_is_recorded_as_source_of_truth(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    _write_task(root, "202", "issue-dependencies", dependencies="999")
    controller = task_session.TaskController(
        git_repository, github=FakeGitHub(git_repository.ref("origin/master"))
    )

    started = controller.start(
        "202",
        owner_launch=True,
        session_label="issue-contract",
        dependency_ids=(),
        offline=True,
    )

    assert started["lease"]["dependency_ids"] == []
    assert started["lease"]["dependency_source"] == "github-issue"
    assert "Dependencies (Issue source): none" in started["prompt"]


def test_two_independent_write_tasks_get_distinct_leases_and_worktrees(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    for task_id in ("220", "221"):
        _write_task(root, task_id, f"parallel-{task_id}", concurrency="independent-write")
    controller = task_session.TaskController(
        git_repository, github=FakeGitHub(git_repository.ref("origin/master"))
    )

    first = controller.start("220", owner_launch=True, session_label="parallel-a", offline=True)
    second = controller.start("221", owner_launch=True, session_label="parallel-b", offline=True)

    assert first["lease"]["concurrency_class"] == "independent-write"
    assert second["lease"]["concurrency_class"] == "independent-write"
    assert first["lease"]["worktree"] != second["lease"]["worktree"]
    assert {item["task_id"] for item in controller.store.all_leases()} == {"220", "221"}


def test_three_independent_write_tasks_can_run_at_once(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    for task_id in ("222", "223", "224"):
        _write_task(root, task_id, f"parallel-{task_id}", concurrency="independent-write")
    controller = task_session.TaskController(git_repository)

    started = [
        controller.start(
            task_id, owner_launch=True, session_label=f"parallel-{task_id}", offline=True
        )
        for task_id in ("222", "223", "224")
    ]

    assert len({item["lease"]["worktree"] for item in started}) == 3
    assert all(item["lease"]["lifecycle_state"] == "working" for item in started)


@pytest.mark.parametrize(
    ("existing_class", "candidate_class"),
    [
        ("exclusive-write", "independent-write"),
        ("independent-write", "exclusive-write"),
        ("exclusive-write", "exclusive-write"),
    ],
)
def test_legacy_exclusive_metadata_does_not_block_distinct_worktrees(
    repository: tuple[Path, Any], existing_class: str, candidate_class: str
) -> None:
    root, git_repository = repository
    _write_task(root, "225", "existing", concurrency=existing_class)
    _write_task(root, "226", "candidate", concurrency=candidate_class)
    controller = task_session.TaskController(git_repository)
    controller.start("225", owner_launch=True, session_label="existing", offline=True)

    started = controller.start("226", owner_launch=True, session_label="candidate", offline=True)
    assert started["lease"]["lifecycle_state"] == "working"


def test_ready_or_delivery_exclusive_lease_releases_implementation_exclusion(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    _write_task(root, "226A", "existing", concurrency="exclusive-write")
    _write_task(root, "226B", "candidate", concurrency="independent-write")
    controller = task_session.TaskController(git_repository)
    existing = controller.start("226A", owner_launch=True, session_label="existing", offline=True)
    existing_head = _commit_task(Path(existing["lease"]["worktree"]), "226A")
    controller.mark_ready("226A", head_sha=existing_head, quality_verdict="PASS", qa_verdict="PASS")
    controller.acquire_delivery("226A", offline=True)

    candidate = controller.start("226B", owner_launch=True, session_label="candidate", offline=True)

    snapshots = {item["task_id"]: item for item in controller.status()["leases"]}
    assert candidate["lease"]["lifecycle_state"] == "working"
    assert snapshots["226A"]["ownership"] == {
        "task_session_active": True,
        "implementation_exclusion_active": False,
        "delivery_critical_section_active": True,
    }
    assert snapshots["226B"]["ownership"]["implementation_exclusion_active"] is False


@pytest.mark.parametrize(
    ("existing_state", "existing_class", "candidate_class", "expected_conflict"),
    [
        ("starting", "exclusive-write", "independent-write", False),
        ("implementation", "exclusive-write", "independent-write", False),
        ("review", "exclusive-write", "independent-write", False),
        ("qa", "exclusive-write", "independent-write", False),
        ("review", "independent-write", "independent-write", False),
        ("qa", "independent-write", "independent-write", False),
        ("implementation", "independent-write", "exclusive-write", False),
        ("ready-for-delivery", "independent-write", "independent-write", False),
        ("waiting-for-delivery", "independent-write", "independent-write", False),
        ("ready-for-delivery", "exclusive-write", "independent-write", False),
        ("ready-for-pr", "exclusive-write", "exclusive-write", False),
        ("waiting-for-delivery", "exclusive-write", "independent-write", False),
        ("delivering", "exclusive-write", "exclusive-write", False),
        ("delivery-refreshing", "exclusive-write", "independent-write", False),
        ("delivery-gate", "exclusive-write", "exclusive-write", False),
        ("production-success", "exclusive-write", "independent-write", False),
        ("superseded", "exclusive-write", "exclusive-write", False),
    ],
)
def test_implementation_metadata_never_creates_repository_wide_exclusion(
    existing_state: str,
    existing_class: str,
    candidate_class: str,
    expected_conflict: bool,
) -> None:
    existing = {
        "mode": "write",
        "task_id": "225",
        "concurrency_class": existing_class,
        "lifecycle_state": existing_state,
    }

    conflicts = task_session.TaskController._implementation_lease_conflicts(
        [existing], task_id="226", concurrency_class=candidate_class
    )

    assert bool(conflicts) is expected_conflict


def test_missing_concurrency_metadata_defaults_to_independent_write(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    task_path = _write_task(root, "226C", "legacy-without-concurrency")
    document = task_session.find_task_document(root, "226C")
    controller = task_session.TaskController(git_repository)

    started = controller.start("226C", owner_launch=True, session_label="legacy", offline=True)

    assert task_path.exists()
    assert document.concurrency_class == "independent-write"
    assert started["lease"]["concurrency_class"] == "independent-write"


def test_corrupt_lease_concurrency_class_fails_closed(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    _write_task(root, "226D", "existing", concurrency="independent-write")
    _write_task(root, "226E", "candidate", concurrency="independent-write")
    controller = task_session.TaskController(git_repository)
    controller.start("226D", owner_launch=True, session_label="existing", offline=True)
    lease_path = controller.store.task_lease_path("226D")
    lease = controller.store.read_json(lease_path)
    assert isinstance(lease, dict)
    lease["concurrency_class"] = "unknown-write"
    task_session.StateStore.replace_json(lease_path, lease)

    report = controller.doctor(offline=True)

    assert report["safe_for_implementation"] is False
    assert any("invalid concurrency class" in item for item in report["implementation_blockers"])
    with pytest.raises(task_session.TaskSessionError, match="invalid concurrency class"):
        controller.start("226E", owner_launch=True, session_label="candidate", offline=True)


def test_duplicate_task_lease_fails_closed_before_new_start(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    _write_task(root, "226F", "existing", concurrency="independent-write")
    _write_task(root, "226G", "candidate", concurrency="independent-write")
    controller = task_session.TaskController(git_repository)
    controller.start("226F", owner_launch=True, session_label="existing", offline=True)
    lease_path = controller.store.task_lease_path("226F")
    lease = controller.store.read_json(lease_path)
    assert isinstance(lease, dict)
    duplicate_path = controller.store.leases / "duplicate-lease.json"
    task_session.StateStore.replace_json(duplicate_path, lease)

    with pytest.raises(task_session.TaskSessionError, match="duplicate Task 226F leases"):
        controller.start("226G", owner_launch=True, session_label="candidate", offline=True)


def test_missing_lease_worktree_fails_closed_before_new_start(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    _write_task(root, "226J", "existing", concurrency="independent-write")
    _write_task(root, "226K", "candidate", concurrency="independent-write")
    controller = task_session.TaskController(git_repository)
    controller.start("226J", owner_launch=True, session_label="existing", offline=True)
    lease_path = controller.store.task_lease_path("226J")
    lease = controller.store.read_json(lease_path)
    assert isinstance(lease, dict)
    lease["worktree"] = str(root / ".artifacts" / "worktrees" / "missing-226J")
    task_session.StateStore.replace_json(lease_path, lease)

    with pytest.raises(task_session.TaskSessionError, match="lease worktree is missing"):
        controller.start("226K", owner_launch=True, session_label="candidate", offline=True)


def test_unrelated_dirty_task_worktree_does_not_block_new_writer(
    repository: tuple[Path, Any],
) -> None:
    root, _, controller, worktree, _, _ = _prepare_started(
        repository, "226H", concurrency="exclusive-write"
    )
    _write_task(root, "226I", "candidate")
    (worktree / "uncommitted.txt").write_text("preserve\n", encoding="utf-8")

    report = controller.doctor(offline=True)

    inventory = next(
        item for item in report["inventory"] if item["branch"] == "task/226H-synthetic-task"
    )
    assert report["safe_for_implementation"] is True
    assert report["ok"] is True
    assert inventory["classification"] == "DIRTY_NEEDS_OWNER"
    assert any("Task 226H worktree is dirty" in item for item in report["recovery_findings"])
    assert not any(
        "Task 226H worktree is dirty" in item for item in report["implementation_blockers"]
    )

    started = controller.start("226I", owner_launch=True, session_label="candidate", offline=True)

    assert started["lease"]["lifecycle_state"] == "working"
    assert (worktree / "uncommitted.txt").read_text(encoding="utf-8") == "preserve\n"


def test_unrelated_interrupted_task_worktree_does_not_block_new_writer(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository, controller, worktree, _, _ = _prepare_started(
        repository, "226L", concurrency="independent-write"
    )
    _write_task(root, "226M", "candidate")
    marker = git_repository.git_dir(worktree) / "MERGE_HEAD"
    marker.write_text("synthetic\n", encoding="utf-8")

    try:
        report = controller.doctor(offline=True)

        inventory = next(
            item for item in report["inventory"] if item["branch"] == "task/226L-synthetic-task"
        )
        assert report["safe_for_implementation"] is True
        assert inventory["classification"] == "DIRTY_NEEDS_OWNER"
        assert any(
            "Task 226L worktree is dirty or interrupted" in item
            for item in report["recovery_findings"]
        )

        started = controller.start(
            "226M", owner_launch=True, session_label="candidate", offline=True
        )

        assert started["lease"]["lifecycle_state"] == "working"
        assert marker.read_text(encoding="utf-8") == "synthetic\n"
    finally:
        marker.unlink(missing_ok=True)


def test_dirty_canonical_worktree_remains_global_implementation_blocker(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    _write_task(root, "226N", "candidate")
    (root / "canonical-uncommitted.txt").write_text("preserve\n", encoding="utf-8")
    controller = task_session.TaskController(git_repository)

    report = controller.doctor(offline=True)

    assert report["safe_for_implementation"] is False
    assert "controller worktree is dirty" in report["implementation_blockers"]
    with pytest.raises(task_session.TaskSessionError, match="canonical master refresh"):
        controller.start("226N", owner_launch=True, session_label="candidate", offline=True)
    assert (root / "canonical-uncommitted.txt").read_text(encoding="utf-8") == "preserve\n"


def test_adopt_current_uses_same_compatible_lease_contract(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    _write_task(root, "227", "existing", concurrency="independent-write")
    _write_task(root, "228", "adopted", concurrency="independent-write")
    controller = task_session.TaskController(git_repository)
    controller.start("227", owner_launch=True, session_label="existing", offline=True)
    adopted_path = root / ".artifacts" / "worktrees" / "adopted-228"
    _git(root, "worktree", "add", "-b", "task/228-adopted", str(adopted_path), "origin/master")

    adopted_controller = task_session.TaskController(task_session.GitRepository(adopted_path))
    lease = adopted_controller.adopt_current(
        "228", owner_launch=True, session_label="adopted", offline=True
    )

    assert lease["task_id"] == "228"
    assert lease["concurrency_class"] == "independent-write"


def test_adopt_current_refuses_dirty_task_worktree_without_mutation(
    repository: tuple[Path, Any],
) -> None:
    root, _ = repository
    _write_task(root, "228A", "adopted", concurrency="independent-write")
    adopted_path = root / ".artifacts" / "worktrees" / "adopted-228A"
    _git(root, "worktree", "add", "-b", "task/228A-adopted", str(adopted_path), "origin/master")
    (adopted_path / "uncommitted.txt").write_text("preserve\n", encoding="utf-8")
    adopted_controller = task_session.TaskController(task_session.GitRepository(adopted_path))

    with pytest.raises(task_session.TaskSessionError, match="adoption refuses dirty worktree"):
        adopted_controller.adopt_current(
            "228A", owner_launch=True, session_label="adopted", offline=True
        )

    assert not adopted_controller.store.task_lease_path("228A").exists()
    assert (adopted_path / "uncommitted.txt").read_text(encoding="utf-8") == "preserve\n"


def test_active_production_deploy_blocks_only_delivery_acquisition(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    for task_id in ("230", "231"):
        _write_task(root, task_id, f"deploy-{task_id}", concurrency="independent-write")
    github = FakeGitHub(git_repository.ref("origin/master"))
    github.active_runs = [{"name": "Deploy production", "status": "in_progress"}]
    controller = task_session.TaskController(git_repository, github=github)

    first = controller.start("230", owner_launch=True, session_label="deploy-a")
    second = controller.start("231", owner_launch=True, session_label="deploy-b")
    second_lease = second["lease"]
    second_head = _commit_task(Path(second_lease["worktree"]), "231")
    controller.mark_ready("231", head_sha=second_head, quality_verdict="PASS", qa_verdict="PASS")

    waiting = controller.acquire_delivery("231")

    assert first["lease"]["worktree"] != second_lease["worktree"]
    assert waiting["acquired"] is False
    assert waiting["delivery_blocker"] == "active production deployment"
    assert (
        controller.store.read_json(controller.store.task_lease_path("231"))["lifecycle_state"]
        == "working"
    )

    github.active_runs = []
    acquired = controller.acquire_delivery("231")
    assert acquired["acquired"] is True
    assert acquired["lifecycle_state"] == "working"


def test_delivery_lane_is_serial_and_handoff_is_deterministic(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    for task_id in ("232", "233"):
        _write_task(root, task_id, f"queue-{task_id}", concurrency="independent-write")
    controller = task_session.TaskController(git_repository)
    started = {
        task_id: controller.start(
            task_id, owner_launch=True, session_label=f"queue-{task_id}", offline=True
        )
        for task_id in ("232", "233")
    }
    for task_id in ("232", "233"):
        head_sha = _commit_task(Path(started[task_id]["lease"]["worktree"]), task_id)
        controller.mark_ready(task_id, head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")

    first = controller.acquire_delivery("232", offline=True)
    second = controller.acquire_delivery("233", offline=True)
    assert first["acquired"] is True
    assert second["acquired"] is False
    assert second["delivery_owner"] == "232"
    assert (
        controller.store.read_json(controller.store.task_lease_path("233"))["lifecycle_state"]
        == "working"
    )

    released = controller.release_delivery(
        "232", reason="synthetic delivery interruption", offline=True
    )

    assert released["lifecycle_state"] == "human-required"
    assert controller.store.delivery_state()["owner"]["task_id"] == "233"
    assert (
        controller.store.read_json(controller.store.task_lease_path("233"))["lifecycle_state"]
        == "working"
    )


def test_owner_priority_promotes_current_task_and_preserves_fifo_handoff(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    for task_id in ("246", "247", "248"):
        _write_task(root, task_id, f"priority-{task_id}", concurrency="independent-write")
    controller = task_session.TaskController(git_repository)
    started = {
        task_id: controller.start(
            task_id, owner_launch=True, session_label=f"priority-{task_id}", offline=True
        )
        for task_id in ("246", "247", "248")
    }
    for task_id in ("246", "247", "248"):
        head_sha = _commit_task(Path(started[task_id]["lease"]["worktree"]), task_id)
        controller.mark_ready(task_id, head_sha=head_sha, quality_verdict="PASS")

    acquired = controller.acquire_delivery(
        "247", offline=True, owner_priority_reason="Owner requested current task first"
    )

    assert acquired["acquired"] is True
    priority_override = acquired["priority_override"]
    assert priority_override["task_id"] == "247"
    assert priority_override["skipped_task_ids"] == ["246"]
    assert priority_override["reason"] == "Owner requested current task first"
    assert priority_override["authorized_at"]
    assert controller.store.delivery_state()["owner"]["task_id"] == "247"
    assert controller.store.delivery_state()["priority_override"]["skipped_task_ids"] == ["246"]
    assert (
        controller.store.read_json(controller.store.task_lease_path("246"))["lifecycle_state"]
        == "working"
    )

    released = controller.release_delivery(
        "247", reason="synthetic priority delivery interruption", offline=True
    )

    assert released["lifecycle_state"] == "human-required"
    assert controller.store.delivery_state()["owner"]["task_id"] == "246"
    assert "priority_override" not in controller.store.delivery_state()


def test_owner_priority_requires_a_bounded_reason(repository: tuple[Path, Any]) -> None:
    root, git_repository = repository
    _write_task(root, "249", "priority-reason", concurrency="independent-write")
    controller = task_session.TaskController(git_repository)
    started = controller.start(
        "249", owner_launch=True, session_label="priority-reason", offline=True
    )
    head_sha = _commit_task(Path(started["lease"]["worktree"]), "249")
    controller.mark_ready("249", head_sha=head_sha, quality_verdict="PASS")

    with pytest.raises(task_session.TaskSessionError, match="non-empty reason"):
        controller.acquire_delivery("249", offline=True, owner_priority_reason=" ")


def test_release_delivery_does_not_handoff_during_active_production(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    for task_id in ("233A", "233B"):
        _write_task(root, task_id, f"queue-{task_id}", concurrency="independent-write")
    github = FakeGitHub(git_repository.ref("origin/master"))
    controller = task_session.TaskController(git_repository, github=github)
    started = {
        task_id: controller.start(
            task_id, owner_launch=True, session_label=f"queue-{task_id}", offline=True
        )
        for task_id in ("233A", "233B")
    }
    for task_id in ("233A", "233B"):
        head_sha = _commit_task(Path(started[task_id]["lease"]["worktree"]), task_id)
        controller.mark_ready(task_id, head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")
    acquired = controller.acquire_delivery("233A", offline=True)
    assert acquired["acquired"] is True

    github.active_runs = [{"name": "Deploy production", "status": "in_progress"}]
    released = controller.release_delivery("233A", reason="synthetic interruption")

    assert released["delivery_next_owner"] is None
    assert released["delivery_handoff_blocker"] == "active production deployment"
    assert controller.store.delivery_state()["owner"] is None
    assert (
        controller.store.read_json(controller.store.task_lease_path("233B"))["lifecycle_state"]
        == "working"
    )

    github.active_runs = []
    reacquired = controller.acquire_delivery("233B", offline=True)
    assert reacquired["acquired"] is True


def test_reopen_for_review_clears_delivery_snapshot_and_requires_new_readiness(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, worktree, _, sha_pair = _prepare_started(
        repository, "234A", concurrency="independent-write"
    )
    _, head_sha = sha_pair.split(":")
    controller.mark_ready("234A", head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")
    controller.acquire_delivery("234A", offline=True)
    controller.refresh_for_delivery("234A", offline=True)
    controller.validate_delivery("234A", offline=True)

    reopened = controller.reopen_for_review("234A", reason="address review findings")

    assert reopened["lifecycle_state"] == "working"
    assert "delivery_anchor" not in reopened
    assert "delivery_head_sha" not in reopened
    assert "ready_head_sha" not in reopened
    assert controller.store.delivery_state()["owner"] is None

    new_head = _commit_task(worktree, "234A", filename="review-fix.txt")
    ready = controller.mark_ready(
        "234A", head_sha=new_head, quality_verdict="PASS", qa_verdict="PASS"
    )
    assert ready["lifecycle_state"] == "working"
    assert ready["ready_head_sha"] == new_head


def test_resolve_recovery_requires_owner_authorization_and_clean_unique_anchor(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, worktree, _, _ = _prepare_started(
        repository, "234B", concurrency="independent-write"
    )
    lease_path = controller.store.task_lease_path("234B")
    lease = controller.store.read_json(lease_path)
    assert isinstance(lease, dict)
    lease.update(
        {
            "lifecycle_state": "recovery-required",
            "recovery_reason": "synthetic interrupted delivery",
            "delivery_head_sha": "stale",
            "ready_head_sha": "stale",
            "updated_at": task_session.utc_now(),
        }
    )
    task_session.StateStore.replace_json(lease_path, lease)

    with pytest.raises(task_session.TaskSessionError, match="owner authorization"):
        controller.resolve_recovery("234B", reason="resume after inspection", owner_authorize=False)

    resolved = controller.resolve_recovery(
        "234B", reason="resume after inspection", owner_authorize=True
    )

    assert resolved["lifecycle_state"] == "working"
    assert resolved["recovery_resolution_reason"] == "resume after inspection"
    assert "delivery_anchor" not in resolved
    assert "delivery_head_sha" not in resolved
    assert "ready_head_sha" not in resolved
    assert worktree.exists()
    assert not controller.store.delivery_state()["owner"]


def test_resolve_recovery_refuses_dirty_anchor(repository: tuple[Path, Any]) -> None:
    _, _, controller, worktree, _, _ = _prepare_started(
        repository, "234C", concurrency="independent-write"
    )
    lease_path = controller.store.task_lease_path("234C")
    lease = controller.store.read_json(lease_path)
    assert isinstance(lease, dict)
    lease["lifecycle_state"] = "recovery-required"
    lease["updated_at"] = task_session.utc_now()
    task_session.StateStore.replace_json(lease_path, lease)
    (worktree / "uncommitted.txt").write_text("keep\n", encoding="utf-8")

    with pytest.raises(task_session.TaskSessionError, match="dirty worktree"):
        controller.resolve_recovery("234C", reason="inspect", owner_authorize=True)


def test_supersede_releases_exclusion_and_preserves_clean_anchor(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository, controller, worktree, branch, sha_pair = _prepare_started(
        repository, "234D", concurrency="exclusive-write"
    )
    _, head_sha = sha_pair.split(":")

    with pytest.raises(task_session.TaskSessionError, match="owner authorization"):
        controller.supersede("234D", reason="owner decision", owner_authorize=False)

    superseded = controller.supersede("234D", reason="Task 229 is canonical", owner_authorize=True)

    assert superseded["lifecycle_state"] == "done"
    assert superseded["superseded_from_state"] == "working"
    assert superseded["superseded_reason"] == "Task 229 is canonical"
    assert worktree.exists()
    assert not _git(worktree, "status", "--short")
    assert git_repository.ref(branch) == head_sha
    assert controller.store.delivery_state()["owner"] is None

    snapshot = next(item for item in controller.status()["leases"] if item["task_id"] == "234D")
    assert snapshot["ownership"] == {
        "task_session_active": False,
        "implementation_exclusion_active": False,
        "delivery_critical_section_active": False,
    }
    recovered = controller.recover("234D")
    assert recovered["classification"] == "SUPERSEDED"
    assert recovered["issues"] == []
    assert recovered["mutation_performed"] is False

    _write_task(root, "234E", "after-supersede", concurrency="exclusive-write")
    started = controller.start("234E", owner_launch=True, session_label="after", offline=True)
    assert started["lease"]["lifecycle_state"] == "working"


def test_supersede_refuses_dirty_anchor_without_mutation(repository: tuple[Path, Any]) -> None:
    _, _, controller, worktree, _, _ = _prepare_started(
        repository, "234F", concurrency="exclusive-write"
    )
    (worktree / "uncommitted.txt").write_text("preserve\n", encoding="utf-8")

    with pytest.raises(task_session.TaskSessionError, match="dirty worktree"):
        controller.supersede("234F", reason="owner decision", owner_authorize=True)

    lease = controller.store.read_json(controller.store.task_lease_path("234F"))
    assert isinstance(lease, dict)
    assert lease["lifecycle_state"] == "working"


def test_supersede_refuses_open_task_pr_without_mutation(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, _, branch, _ = _prepare_started(repository, "234G")
    assert isinstance(controller.github, FakeGitHub)
    controller.github.open_prs = [{"number": 999, "head": {"ref": branch}}]

    with pytest.raises(task_session.TaskSessionError, match="open task PR"):
        controller.supersede("234G", reason="owner decision", owner_authorize=True)

    lease = controller.store.read_json(controller.store.task_lease_path("234G"))
    assert isinstance(lease, dict)
    assert lease["lifecycle_state"] == "working"


def test_busy_delivery_lane_does_not_block_compatible_implementation(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    for task_id in ("240", "241", "242"):
        _write_task(root, task_id, f"busy-{task_id}", concurrency="independent-write")
    controller = task_session.TaskController(git_repository)
    first = controller.start("240", owner_launch=True, session_label="busy-a", offline=True)
    first_worktree = Path(first["lease"]["worktree"])
    first_head = _commit_task(first_worktree, "240")
    controller.mark_ready("240", head_sha=first_head, quality_verdict="PASS", qa_verdict="PASS")
    acquired = controller.acquire_delivery("240", offline=True)

    second = controller.start("241", owner_launch=True, session_label="busy-b", offline=True)
    third = controller.start("242", owner_launch=True, session_label="busy-c", offline=True)

    assert acquired["acquired"] is True
    assert second["lease"]["lifecycle_state"] == "working"
    assert third["lease"]["lifecycle_state"] == "working"


def test_refresh_refuses_merged_task_pr_before_mutating_worktree(
    repository: tuple[Path, Any],
) -> None:
    _, git_repository, controller, worktree, branch, sha_pair = _prepare_started(repository, "245")
    base_sha, head_sha = sha_pair.split(":")
    controller.mark_ready("245", head_sha=head_sha, quality_verdict="PASS")
    controller.acquire_delivery("245", offline=True)
    github = controller.github
    assert isinstance(github, FakeGitHub)
    merged_pr = _task_pr(
        579, "245", base_sha, head_sha, merge_sha=git_repository.ref("origin/master")
    )
    merged_pr["state"] = "closed"
    merged_pr["head"]["ref"] = branch
    merged_pr["merged_at"] = "2026-09-29T15:23:46Z"
    github.associated_pulls = [merged_pr]
    github.associated_pulls_by_commit[head_sha] = [merged_pr]
    before_head = git_repository.head(cwd=worktree)
    before_master = git_repository.ref("master")

    with pytest.raises(
        task_session.TaskSessionError,
        match="already merged; refresh-delivery is not valid after merge",
    ):
        controller.refresh_for_delivery("245", offline=True)

    assert git_repository.head(cwd=worktree) == before_head
    assert git_repository.ref("master") == before_master
    assert (
        controller.store.read_json(controller.store.task_lease_path("245"))["lifecycle_state"]
        == task_session.WORKING_STATE
    )
    assert controller.store.delivery_state()["owner"]["task_id"] == "245"


def test_refresh_allows_open_task_pr_and_ignores_unrelated_merged_pr(
    repository: tuple[Path, Any],
) -> None:
    _, git_repository, controller, worktree, branch, sha_pair = _prepare_started(repository, "245A")
    base_sha, head_sha = sha_pair.split(":")
    controller.mark_ready("245A", head_sha=head_sha, quality_verdict="PASS")
    controller.acquire_delivery("245A", offline=True)
    github = controller.github
    assert isinstance(github, FakeGitHub)
    open_pr = _task_pr(580, "245A", base_sha, head_sha)
    open_pr["head"]["ref"] = branch
    open_pr["state"] = "open"
    open_pr["merged_at"] = None
    unrelated = _task_pr(581, "245A", base_sha, "b" * 40, merge_sha="c" * 40)
    unrelated["state"] = "closed"
    unrelated["head"]["ref"] = "task/999-unrelated"
    unrelated["merged_at"] = "2026-09-29T15:23:46Z"
    github.associated_pulls = [open_pr, unrelated]
    github.associated_pulls_by_commit[head_sha] = [open_pr, unrelated]

    refreshed = controller.refresh_for_delivery("245A", offline=True)

    assert refreshed["delivery_head_sha"] == head_sha
    assert git_repository.head(cwd=worktree) == head_sha


def test_refresh_fails_closed_for_unavailable_or_ambiguous_pr_evidence(
    repository: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, git_repository, controller, worktree, branch, sha_pair = _prepare_started(repository, "245B")
    base_sha, head_sha = sha_pair.split(":")
    controller.mark_ready("245B", head_sha=head_sha, quality_verdict="PASS")
    controller.acquire_delivery("245B", offline=True)
    github = controller.github
    assert isinstance(github, FakeGitHub)
    first = _task_pr(582, "245B", base_sha, head_sha)
    first["head"]["ref"] = branch
    second = dict(first)
    github.associated_pulls = [first, second]
    github.associated_pulls_by_commit[head_sha] = [first, second]

    with pytest.raises(task_session.TaskSessionError, match="ambiguous merged PR evidence"):
        controller.refresh_for_delivery("245B", offline=True)

    def unavailable(_: str) -> list[dict[str, Any]]:
        raise OSError("GitHub unavailable")

    monkeypatch.setattr(github, "pull_requests_for_commit", unavailable)
    with pytest.raises(task_session.TaskSessionError, match="cannot verify GitHub PR state"):
        controller.refresh_for_delivery("245B", offline=True)

    assert git_repository.head(cwd=worktree) == head_sha
    assert (
        controller.store.read_json(controller.store.task_lease_path("245B"))["lifecycle_state"]
        == task_session.WORKING_STATE
    )


def test_refresh_fails_closed_for_incomplete_closed_pr_evidence(
    repository: tuple[Path, Any],
) -> None:
    _, git_repository, controller, worktree, branch, sha_pair = _prepare_started(repository, "245C")
    base_sha, head_sha = sha_pair.split(":")
    controller.mark_ready("245C", head_sha=head_sha, quality_verdict="PASS")
    controller.acquire_delivery("245C", offline=True)
    github = controller.github
    assert isinstance(github, FakeGitHub)
    closed_pr = _task_pr(583, "245C", base_sha, head_sha)
    closed_pr["head"]["ref"] = branch
    closed_pr["state"] = "closed"
    closed_pr["merged_at"] = None
    closed_pr["merge_commit_sha"] = None
    github.associated_pulls_by_commit[head_sha] = [closed_pr]

    with pytest.raises(
        task_session.TaskSessionError,
        match="incomplete GitHub merge evidence",
    ):
        controller.refresh_for_delivery("245C", offline=True)

    assert git_repository.head(cwd=worktree) == head_sha
    assert (
        controller.store.read_json(controller.store.task_lease_path("245C"))["lifecycle_state"]
        == task_session.WORKING_STATE
    )


def test_refresh_delivery_parser_accepts_optional_superseding_prs() -> None:
    args = task_session._parser().parse_args(
        [
            "reconcile-production-success",
            "507",
            "--original-pr",
            "578",
            "--deployed-sha",
            "a" * 40,
            "--production-run",
            "36590222806",
        ]
    )

    assert args.superseding_pr == []


def test_refresh_updates_stale_task_base_and_rebuilds_exact_delivery_anchor(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository, controller, _, _, sha_pair = _prepare_started(
        repository, "234", concurrency="independent-write"
    )
    old_base, old_head = sha_pair.split(":")
    controller.mark_ready("234", head_sha=old_head, quality_verdict="PASS", qa_verdict="PASS")

    (root / "master-refresh.txt").write_text("M1\n", encoding="utf-8")
    _git(root, "add", "master-refresh.txt")
    _git(root, "commit", "-m", "chore: advance master for delivery refresh")
    _git(root, "push", "origin", "master")
    github = controller.github
    assert isinstance(github, FakeGitHub)
    github.master_sha = git_repository.ref("origin/master")

    controller.acquire_delivery("234", offline=True)
    refreshed = controller.refresh_for_delivery("234")
    new_head = refreshed["delivery_head_sha"]

    assert refreshed["base_origin_master_sha"] != old_base
    assert new_head != old_head
    validated = controller.validate_delivery("234")
    assert validated["lifecycle_state"] == "working"
    assert validated["delivery_anchor"]["head_sha"] == new_head


def test_refresh_preserves_published_master_integration_merge(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository, controller, worktree, branch, _ = _prepare_started(
        repository, "244B", concurrency="independent-write"
    )
    task_head = _commit_task(worktree, "244B")

    (root / "master-refresh.txt").write_text("M1\n", encoding="utf-8")
    _git(root, "add", "master-refresh.txt")
    _git(root, "commit", "-m", "chore: advance master for delivery refresh")
    _git(root, "push", "origin", "master")
    _git(root, "fetch", "origin", "master")
    _git(worktree, "fetch", "origin", "master")
    _git(
        worktree,
        "merge",
        "--no-ff",
        "origin/master",
        "-m",
        f"Merge remote-tracking branch 'origin/master' into {branch}",
    )
    integrated_head = git_repository.head(cwd=worktree)
    github = controller.github
    assert isinstance(github, FakeGitHub)
    github.master_sha = git_repository.ref("origin/master")

    controller.mark_ready("244B", head_sha=integrated_head, quality_verdict="PASS")
    controller.acquire_delivery("244B", offline=True)
    refreshed = controller.refresh_for_delivery("244B", offline=True)

    assert task_head != integrated_head
    assert refreshed["delivery_head_sha"] == integrated_head
    assert git_repository.head(cwd=worktree) == integrated_head
    assert len(_git(worktree, "rev-list", "--parents", "-n", "1", "HEAD").split()) == 3
    assert controller.validate_delivery("244B", offline=True)["lifecycle_state"] == "working"


def test_refresh_delivery_waits_for_active_production_before_touching_task_branch(
    repository: tuple[Path, Any],
) -> None:
    _, git_repository, controller, worktree, _, sha_pair = _prepare_started(
        repository, "244", concurrency="independent-write"
    )
    _, head_sha = sha_pair.split(":")
    controller.mark_ready("244", head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")
    controller.acquire_delivery("244", offline=True)
    github = controller.github
    assert isinstance(github, FakeGitHub)
    github.active_runs = [{"name": "Deploy production", "status": "in_progress"}]
    before_head = git_repository.head(cwd=worktree)

    with pytest.raises(task_session.TaskSessionError, match="canonical master refresh is waiting"):
        controller.refresh_for_delivery("244")

    lease = controller.store.read_json(controller.store.task_lease_path("244"))
    assert isinstance(lease, dict)
    assert lease["lifecycle_state"] == "working"
    assert controller.store.delivery_state()["owner"]["task_id"] == "244"
    assert git_repository.head(cwd=worktree) == before_head


def test_refresh_is_idempotent_when_head_and_base_are_unchanged(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, _, _, sha_pair = _prepare_started(
        repository, "243", concurrency="independent-write"
    )
    base_sha, head_sha = sha_pair.split(":")
    controller.mark_ready("243", head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")

    controller.acquire_delivery("243", offline=True)
    refreshed = controller.refresh_for_delivery("243", offline=True)

    assert refreshed["delivery_head_sha"] == head_sha
    validated = controller.validate_delivery("243", offline=True)
    assert validated["delivery_anchor"] == {
        "task_id": "243",
        "branch": refreshed["branch"],
        "base_sha": base_sha,
        "head_sha": head_sha,
    }


def test_refresh_refuses_post_ready_commit_until_review_and_qa_repeat(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, worktree, _, sha_pair = _prepare_started(
        repository, "243A", concurrency="independent-write"
    )
    base_sha, head_sha = sha_pair.split(":")
    controller.mark_ready("243A", head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")
    controller.acquire_delivery("243A", offline=True)
    _commit_task(worktree, "243A", filename="post-ready-change.txt")

    with pytest.raises(task_session.TaskSessionError, match="changed after PR readiness"):
        controller.refresh_for_delivery("243A", offline=True)

    lease = controller.store.read_json(controller.store.task_lease_path("243A"))
    assert isinstance(lease, dict)
    assert lease["lifecycle_state"] == "human-required"
    assert controller.store.delivery_state()["owner"] is None
    assert lease["ready_head_sha"] == head_sha
    assert base_sha == lease["base_origin_master_sha"]


def test_local_master_behind_remote_is_refreshed_before_start(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    remote_worktree = root.parent / "remote-master"
    _git(root, "worktree", "add", "--detach", str(remote_worktree), "HEAD")
    try:
        (remote_worktree / "remote-change.txt").write_text("remote\n", encoding="utf-8")
        _git(remote_worktree, "add", "remote-change.txt")
        _git(remote_worktree, "commit", "-m", "chore: advance remote master")
        _git(remote_worktree, "push", "origin", "HEAD:master")
    finally:
        _git(root, "worktree", "remove", "--force", str(remote_worktree))
    _git(root, "fetch", "origin", "master")
    _write_task(root, "235", "behind-remote", concurrency="independent-write")
    remote_sha = git_repository.ref("origin/master")
    controller = task_session.TaskController(git_repository, github=FakeGitHub(remote_sha))

    report = controller.doctor(offline=True)
    started = controller.start("235", owner_launch=True, session_label="behind")
    refreshed_report = controller.doctor(offline=True)

    assert git_repository.ahead_behind("master", "origin/master") == (0, 0)
    assert any("behind" in item for item in report["informational_findings"])
    assert not any("behind" in item for item in refreshed_report["informational_findings"])
    assert report["implementation_blockers"] == []
    assert started["lease"]["base_origin_master_sha"] == git_repository.ref("origin/master")
    assert started["canonical_master_refresh"]["result"] == "REFRESHED"


def test_compatible_start_keeps_current_base_fetch_when_production_is_active(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    _, remote_sha = _advance_remote_master(root, 1, fetch=False)
    _write_task(root, "235A", "production-active", concurrency="independent-write")
    github = FakeGitHub(remote_sha)
    github.active_runs = [{"name": "Deploy production", "status": "in_progress"}]
    controller = task_session.TaskController(git_repository, github=github)

    started = controller.start("235A", owner_launch=True, session_label="production-active")

    assert started["canonical_master_refresh"]["result"] == "WAITING"
    assert started["lease"]["base_origin_master_sha"] == remote_sha
    assert git_repository.ref("origin/master") == remote_sha


@pytest.mark.parametrize(
    ("count", "expected_result"), [(0, "ALIGNED"), (1, "REFRESHED"), (3, "REFRESHED")]
)
def test_canonical_refresh_reports_exact_fast_forward_and_is_idempotent(
    repository: tuple[Path, Any], count: int, expected_result: str
) -> None:
    _, git_repository = repository
    old_sha, remote_sha = _advance_remote_master(repository[0], count)
    controller = task_session.TaskController(git_repository, github=FakeGitHub(remote_sha))

    result = controller.refresh_canonical_master()

    assert result["result"] == expected_result
    assert result["old_sha"] == old_sha
    assert result["new_sha"] == remote_sha
    assert result["origin_master_sha"] == remote_sha
    assert result["live_master_sha"] == remote_sha
    assert result["ahead_before"] == 0
    assert result["behind_before"] == count
    assert result["updated_commits"] == count
    assert result["mutation_performed"] is (count > 0)
    assert git_repository.ref("master") == remote_sha

    repeated = controller.refresh_canonical_master()

    assert repeated["result"] == "ALIGNED"
    assert repeated["old_sha"] == remote_sha
    assert repeated["new_sha"] == remote_sha
    assert repeated["behind_before"] == 0
    assert repeated["updated_commits"] == 0
    assert repeated["mutation_performed"] is False


def test_canonical_refresh_offline_waits_without_claiming_freshness(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    before_master = git_repository.ref("master")
    controller = task_session.TaskController(git_repository, github=FakeGitHub(before_master))

    result = controller.refresh_canonical_master(offline=True)

    assert result["result"] == "WAITING"
    assert "offline" in result["reason"]
    assert result["mutation_performed"] is False
    assert git_repository.ref("master") == before_master
    assert git_repository.status(root) == []


def test_first_controller_state_initialization_is_safe_under_concurrency(
    repository: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, git_repository = repository
    store = task_session.StateStore(git_repository.common_dir)
    original_create_json = task_session.StateStore.create_json
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def concurrent_create_json(current: Any, path: Path, payload: dict[str, Any]) -> None:
        barrier.wait(timeout=5)
        original_create_json(current, path, payload)

    monkeypatch.setattr(task_session.StateStore, "create_json", concurrent_create_json)

    def initialize() -> None:
        try:
            store.initialize()
        except BaseException as error:  # pragma: no cover - assertion context below reports it
            errors.append(error)

    workers = [threading.Thread(target=initialize) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=5)

    assert not any(worker.is_alive() for worker in workers)
    assert not errors
    assert (store.root / "contract.json").is_file()


def test_state_lock_reclaims_only_a_stale_dead_owner(
    repository: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, git_repository = repository
    store = task_session.StateStore(git_repository.common_dir)
    store.initialize()
    store.lock_path.write_text(
        json.dumps(
            {
                "pid": 424242,
                "created_at": "2020-01-01T00:00:00Z",
                "token": "a" * 32,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(store, "_pid_is_alive", lambda pid: False)

    with store.lock():
        assert store.lock_path.is_file()

    assert not store.lock_path.exists()


@pytest.mark.parametrize(("winerror", "expected"), [(87, False), (5, True)])
def test_state_pid_is_alive_handles_windows_probe_errors(
    repository: tuple[Path, Any],
    monkeypatch: pytest.MonkeyPatch,
    winerror: int,
    expected: bool,
) -> None:
    _, git_repository = repository
    store = task_session.StateStore(git_repository.common_dir)
    error = OSError(winerror, "Windows process probe failed")
    error.winerror = winerror

    def fail_probe(_pid: int, _signal: int) -> None:
        raise error

    monkeypatch.setattr(task_session.os, "name", "nt")
    monkeypatch.setattr(task_session.os, "kill", fail_probe)

    assert store._pid_is_alive(424242) is expected


def test_state_lock_refuses_active_owner_and_preserves_lock(
    repository: tuple[Path, Any],
) -> None:
    _, git_repository = repository
    store = task_session.StateStore(git_repository.common_dir)
    store.initialize()
    store.lock_path.write_text(
        json.dumps(
            {
                "pid": task_session.os.getpid(),
                "created_at": task_session.utc_now(),
                "token": "b" * 32,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with (
        pytest.raises(task_session.TaskSessionError, match="Coordination state is locked"),
        store.lock(),
    ):
        pass

    assert json.loads(store.lock_path.read_text(encoding="utf-8"))["token"] == "b" * 32


def test_state_lock_refuses_malformed_owner_metadata(
    repository: tuple[Path, Any],
) -> None:
    _, git_repository = repository
    store = task_session.StateStore(git_repository.common_dir)
    store.initialize()
    store.lock_path.write_text("partial owner metadata", encoding="utf-8")

    with pytest.raises(task_session.TaskSessionError, match="malformed"), store.lock():
        pass

    assert store.lock_path.read_text(encoding="utf-8") == "partial owner metadata"


def test_state_lock_release_does_not_delete_a_replaced_foreign_lock(
    repository: tuple[Path, Any],
) -> None:
    _, git_repository = repository
    store = task_session.StateStore(git_repository.common_dir)
    store.initialize()

    with store.lock():
        store.lock_path.write_text(
            json.dumps(
                {
                    "pid": task_session.os.getpid(),
                    "created_at": task_session.utc_now(),
                    "token": "c" * 32,
                }
            )
            + "\n",
            encoding="utf-8",
        )

    assert store.lock_path.exists()


def test_canonical_refresh_reports_post_update_worktree_change(
    repository: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, git_repository = repository
    _, remote_sha = _advance_remote_master(root, 1)
    controller = task_session.TaskController(git_repository, github=FakeGitHub(remote_sha))
    original_git = git_repository.git

    def mutate_after_merge(*args: str, **kwargs: Any) -> str:
        result = original_git(*args, **kwargs)
        if args[:2] == ("merge", "--ff-only"):
            (root / "external-change-after-merge.txt").write_text("keep\n", encoding="utf-8")
        return result

    monkeypatch.setattr(git_repository, "git", mutate_after_merge)

    result = controller.refresh_canonical_master()

    assert result["result"] == "BLOCKED"
    assert result["mutation_performed"] is True
    assert result["new_sha"] == remote_sha
    assert "worktree changed" in result["reason"]
    assert git_repository.ref("master") == remote_sha


def test_canonical_refresh_blocks_checkout_change_before_mutation(
    repository: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, git_repository = repository
    before_sha, remote_sha = _advance_remote_master(root, 1)
    github = FakeGitHub(remote_sha)
    controller = task_session.TaskController(git_repository, github=github)
    original_branch_head = github.branch_head
    calls = 0

    def checkout_other_branch(branch: str) -> str:
        nonlocal calls
        calls += 1
        result = original_branch_head(branch)
        if calls == 2:
            _git(root, "switch", "-c", "synthetic-checkout-race")
        return result

    monkeypatch.setattr(github, "branch_head", checkout_other_branch)

    result = controller.refresh_canonical_master()

    assert result["result"] == "BLOCKED"
    assert "checkout changed" in result["reason"]
    assert "expected_HEAD" in result["reason"]
    assert git_repository.ref("master") == before_sha
    assert git_repository.head(cwd=root) == before_sha
    assert git_repository.git("branch", "--show-current", cwd=root) == "synthetic-checkout-race"


def test_canonical_refresh_blocks_ambiguous_lease_worktree(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    _write_task(root, "246A", "first", concurrency="independent-write")
    _write_task(root, "246B", "second", concurrency="independent-write")
    controller = task_session.TaskController(git_repository)
    first = controller.start("246A", owner_launch=True, session_label="first", offline=True)
    controller.start("246B", owner_launch=True, session_label="second", offline=True)
    second_path = controller.store.task_lease_path("246B")
    second = controller.store.read_json(second_path)
    assert isinstance(second, dict)
    second["worktree"] = first["lease"]["worktree"]
    task_session.StateStore.replace_json(second_path, second)

    result = controller.refresh_canonical_master(offline=True)

    assert result["result"] == "BLOCKED"
    assert "share worktree" in result["reason"]


def test_start_exposes_coordination_waiting_to_launcher_retry(
    repository: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, git_repository = repository
    _write_task(root, "247", "start-lock", concurrency="independent-write")
    controller = task_session.TaskController(git_repository)
    waiting = {
        "result": "WAITING",
        "reason": "another controller operation owns the coordination lock",
        "recovery_hint": "Wait and retry.",
    }
    monkeypatch.setattr(controller, "refresh_canonical_master", lambda **_: waiting)

    with pytest.raises(task_session.TaskSessionError, match="Coordination state is locked"):
        controller.start("247", owner_launch=True, session_label="start-lock", offline=True)

    assert not controller.store.task_lease_path("247").exists()


def test_offline_canonical_refresh_cli_does_not_require_github_origin(
    repository: tuple[Path, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    root, _ = repository

    exit_code = task_session.main(["--repo", str(root), "refresh-canonical-master", "--offline"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"] == "WAITING"
    assert "offline" in payload["reason"]


def test_canonical_refresh_allows_managed_ignored_state_but_blocks_unexpected_ignored_state(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    managed = root / ".artifacts" / "controller-cache.bin"
    managed.parent.mkdir(parents=True, exist_ok=True)
    managed.write_text("managed\n", encoding="utf-8")
    controller = task_session.TaskController(
        git_repository, github=FakeGitHub(git_repository.ref("master"))
    )

    aligned = controller.refresh_canonical_master()

    assert aligned["result"] == "ALIGNED"

    (root / ".git" / "info" / "exclude").write_text("ignored-unexpected.txt\n", encoding="utf-8")
    unexpected = root / "ignored-unexpected.txt"
    unexpected.write_text("unexpected\n", encoding="utf-8")
    before_master = git_repository.ref("master")

    blocked = controller.refresh_canonical_master()

    assert blocked["result"] == "BLOCKED"
    assert "ignored" in blocked["reason"]
    assert blocked["mutation_performed"] is False
    assert git_repository.ref("master") == before_master


@pytest.mark.parametrize("blocker", ["untracked", "operation"])
def test_canonical_refresh_blocks_dirty_or_interrupted_controller_without_mutation(
    repository: tuple[Path, Any], blocker: str
) -> None:
    root, git_repository = repository
    controller = task_session.TaskController(
        git_repository, github=FakeGitHub(git_repository.ref("master"))
    )
    operation_lock = root / ".git" / "index.lock"
    if blocker == "untracked":
        (root / "untracked-controller-file.txt").write_text("keep\n", encoding="utf-8")
    else:
        operation_lock.write_text("synthetic lock\n", encoding="utf-8")

    try:
        result = controller.refresh_canonical_master()
    finally:
        operation_lock.unlink(missing_ok=True)

    assert result["result"] == "BLOCKED"
    assert result["mutation_performed"] is False
    assert git_repository.ref("master") == git_repository.ref("origin/master")


def test_canonical_refresh_blocks_local_ahead_without_reset_or_merge(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    remote_sha = git_repository.ref("origin/master")
    (root / "local-master.txt").write_text("local\n", encoding="utf-8")
    _git(root, "add", "local-master.txt")
    _git(root, "commit", "-m", "chore: synthetic unpublished master commit")
    before_master = git_repository.ref("master")
    controller = task_session.TaskController(git_repository, github=FakeGitHub(remote_sha))

    result = controller.refresh_canonical_master()

    assert result["result"] == "BLOCKED"
    assert "ahead=1" in result["reason"]
    assert result["mutation_performed"] is False
    assert git_repository.ref("master") == before_master
    assert git_repository.ref("origin/master") == remote_sha


def test_canonical_refresh_blocks_diverged_refs_without_mutation(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    _, remote_sha = _advance_remote_master(root, 1)
    (root / "local-master.txt").write_text("local\n", encoding="utf-8")
    _git(root, "add", "local-master.txt")
    _git(root, "commit", "-m", "chore: synthetic divergent master commit")
    before_master = git_repository.ref("master")
    controller = task_session.TaskController(git_repository, github=FakeGitHub(remote_sha))

    result = controller.refresh_canonical_master()

    assert result["result"] == "BLOCKED"
    assert "ahead=1 behind=1" in result["reason"]
    assert result["mutation_performed"] is False
    assert git_repository.ref("master") == before_master
    assert git_repository.ref("origin/master") == remote_sha


def test_canonical_refresh_blocks_stale_tracking_ref_against_live_master(
    repository: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, git_repository = repository
    old_sha, live_sha = _advance_remote_master(root, 1, fetch=False)
    _git(root, "update-ref", "refs/remotes/origin/master", old_sha)
    assert git_repository.ref("origin/master") == old_sha
    monkeypatch.setattr(git_repository, "fetch_origin_master", lambda **_: None)
    controller = task_session.TaskController(git_repository, github=FakeGitHub(live_sha))

    result = controller.refresh_canonical_master()

    assert result["result"] == "BLOCKED"
    assert "does not match live" in result["reason"]
    assert result["mutation_performed"] is False
    assert git_repository.ref("master") == old_sha
    assert git_repository.ref("origin/master") == old_sha


def test_canonical_refresh_fetch_failure_preserves_refs(
    repository: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, git_repository = repository
    before_master = git_repository.ref("master")
    before_origin = git_repository.ref("origin/master")

    def fail_fetch(**_: Any) -> None:
        raise task_session.TaskSessionError("synthetic fetch failure")

    monkeypatch.setattr(git_repository, "fetch_origin_master", fail_fetch)
    controller = task_session.TaskController(git_repository, github=FakeGitHub(before_origin))

    result = controller.refresh_canonical_master()

    assert result["result"] == "BLOCKED"
    assert "fetch" in result["reason"]
    assert result["mutation_performed"] is False
    assert git_repository.ref("master") == before_master
    assert git_repository.ref("origin/master") == before_origin


def test_canonical_refresh_waits_for_active_production_without_mutation(
    repository: tuple[Path, Any],
) -> None:
    _, git_repository = repository
    before_master = git_repository.ref("master")
    github = FakeGitHub(before_master)
    github.active_runs = [{"name": "Deploy production", "status": "in_progress"}]
    controller = task_session.TaskController(git_repository, github=github)

    result = controller.refresh_canonical_master()

    assert result["result"] == "WAITING"
    assert "production" in result["reason"]
    assert result["mutation_performed"] is False
    assert git_repository.ref("master") == before_master


def test_canonical_refresh_waits_for_delivery_owner_without_mutation(
    repository: tuple[Path, Any],
) -> None:
    _, git_repository, controller, worktree, _, sha_pair = _prepare_started(
        repository, "245", concurrency="independent-write"
    )
    _, head_sha = sha_pair.split(":")
    controller.mark_ready("245", head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")
    assert controller.acquire_delivery("245", offline=True)["acquired"] is True
    before_master = git_repository.ref("master")

    result = controller.refresh_canonical_master()

    assert result["result"] == "WAITING"
    assert "occupied" in result["reason"]
    assert result["mutation_performed"] is False
    assert git_repository.ref("master") == before_master
    assert worktree.exists()


def test_canonical_refresh_serializes_concurrent_invocations(
    repository: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, git_repository = repository
    _, remote_sha = _advance_remote_master(root, 1)
    github = FakeGitHub(remote_sha)
    controller = task_session.TaskController(git_repository, github=github)
    entered_fetch = threading.Event()
    release_fetch = threading.Event()
    original_fetch = git_repository.fetch_origin_master
    first_result: list[dict[str, Any]] = []
    first_errors: list[BaseException] = []

    def blocking_fetch(**kwargs: Any) -> None:
        entered_fetch.set()
        if not release_fetch.wait(timeout=5):
            raise AssertionError("timed out waiting to release synthetic fetch")
        original_fetch(**kwargs)

    monkeypatch.setattr(git_repository, "fetch_origin_master", blocking_fetch)

    def run_first() -> None:
        try:
            first_result.append(controller.refresh_canonical_master())
        except BaseException as error:  # pragma: no cover - assertion context below reports it
            first_errors.append(error)

    worker = threading.Thread(target=run_first)
    worker.start()
    assert entered_fetch.wait(timeout=5)

    second = controller.refresh_canonical_master()

    assert second["result"] == "WAITING"
    assert second["reread_after_contention"] is True
    assert second["mutation_performed"] is False
    release_fetch.set()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert not first_errors
    assert first_result[0]["result"] == "REFRESHED"
    assert git_repository.ref("master") == remote_sha


def test_local_master_unique_commit_is_a_fail_closed_start_blocker(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    (root / "unpublished.txt").write_text("local\n", encoding="utf-8")
    _git(root, "add", "unpublished.txt")
    _git(root, "commit", "-m", "chore: unpublished local master change")
    _write_task(root, "236", "diverged", concurrency="independent-write")
    controller = task_session.TaskController(git_repository)

    report = controller.doctor(offline=True)

    assert any("unpublished commits" in item for item in report["implementation_blockers"])
    with pytest.raises(task_session.TaskSessionError, match="implementation/start blockers"):
        controller.start("236", owner_launch=True, session_label="diverged", offline=True)


def test_doctor_does_not_turn_compatible_leases_into_global_error(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    for task_id in ("237", "238"):
        _write_task(root, task_id, f"doctor-{task_id}", concurrency="independent-write")
    controller = task_session.TaskController(git_repository)
    controller.start("237", owner_launch=True, session_label="doctor-a", offline=True)
    controller.start("238", owner_launch=True, session_label="doctor-b", offline=True)

    report = controller.doctor(offline=True)

    assert report["safe_for_implementation"] is True
    assert not any("active task write lease" in item for item in report["issues"])
    assert [item["task_id"] for item in report["leases"]] == ["237", "238"]


def test_owner_selected_launch_requires_only_explicit_launch_unless_concrete_gate_declared(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    _write_task(root, "239", "concrete-gate", owner_gate="HUMAN_EVIDENCE: Telegram screenshot")
    controller = task_session.TaskController(git_repository)

    with pytest.raises(
        task_session.TaskSessionError,
        match="Task 239 blocked: HUMAN_EVIDENCE is missing: Telegram screenshot",
    ):
        controller.start("239", owner_launch=True, session_label="gate", offline=True)


def test_owner_launch_gate_accepts_underscore_spelling(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    _write_task(root, "239A", "owner-launch", owner_gate="owner_launch")
    controller = task_session.TaskController(git_repository)

    started = controller.start(
        "239A", owner_launch=True, session_label="owner-launch", offline=True
    )

    assert started["lease"]["task_id"] == "239A"


def test_mark_ready_records_local_verdicts_without_evidence_file(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository, controller, worktree, _, sha_pair = _prepare_started(repository, "202")
    _, head_sha = sha_pair.split(":")
    ready = controller.mark_ready(
        "202", head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS"
    )
    assert ready["lifecycle_state"] == "working"
    assert ready["quality_verdict"] == "PASS"
    assert ready["qa_verdict"] == "PASS"
    assert "local_evidence" not in ready
    assert "pre_push_ci_pass" not in ready
    assert root == controller._canonical_root()
    assert git_repository.status(worktree) == []


def test_record_production_success_requires_exact_merged_master_deployment(
    repository: tuple[Path, Any],
) -> None:
    root, _, controller, _, branch, sha_pair = _prepare_started(repository, "203")
    base_sha, head_sha = sha_pair.split(":")
    controller.mark_ready("203", head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")

    _prepare_delivery(controller, "203", branch=branch)

    _git(root, "merge", "--no-ff", branch, "-m", "Merge task 203")
    merge_sha = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "origin", "master")
    github = controller.github
    assert isinstance(github, FakeGitHub)
    github.master_sha = merge_sha
    github.pulls[203] = _task_pr(203, "203", base_sha, head_sha, merge_sha=merge_sha)
    github.commits[203] = [_task_commit("203")]
    github.files[203] = [{"filename": "change.txt"}]
    github.checks[head_sha] = [_success_check(head_sha)]
    github.successful_deployments.add((merge_sha, "production"))
    github.associated_pulls = [github.pulls[203]]

    history = controller.record_production_success(
        "203", pr_number=203, merge_sha=merge_sha, deployed_sha=merge_sha
    )
    assert history["state"] == "production-success"
    assert history["deployed_sha"] == merge_sha
    assert (
        controller.store.read_json(controller.store.task_lease_path("203"))["lifecycle_state"]
        == "deployed"
    )


def test_reopen_after_production_preserves_prior_evidence_and_releases_lane(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, worktree, _, _ = _prepare_started(repository, "205")
    lease_path = controller.store.task_lease_path("205")
    lease = controller.store.read_json(lease_path)
    assert isinstance(lease, dict)
    previous_history = {
        "version": task_session.TASK_STATE_VERSION,
        "task_id": "205",
        "state": "production-success",
        "head_sha": "a" * 40,
        "base_sha": "b" * 40,
        "merge_sha": "c" * 40,
        "deployed_sha": "c" * 40,
        "pr_number": 205,
        "completed_at": task_session.utc_now(),
        "closeout_required": True,
    }
    lease.update(
        {
            "lifecycle_state": "production-success",
            "delivery_owner": "205",
            "merge_sha": "c" * 40,
            "deployed_sha": "c" * 40,
        }
    )
    task_session.StateStore.replace_json(lease_path, lease)
    task_session.StateStore.replace_json(
        controller.store.delivery_path,
        {
            "version": task_session.DELIVERY_STATE_VERSION,
            "next_sequence": 1,
            "owner": {"task_id": "205"},
            "updated_at": task_session.utc_now(),
        },
    )
    history_path = controller.store.history / "task-205.json"
    task_session.StateStore.replace_json(history_path, previous_history)

    with pytest.raises(task_session.TaskSessionError, match="explicit owner authorization"):
        controller.reopen_after_production("205", reason="continue", owner_authorize=False)

    reopened = controller.reopen_after_production(
        "205", reason="Task 403 post-production remediation", owner_authorize=True
    )

    assert reopened["lifecycle_state"] == "working"
    assert reopened["continuation_of_production_success"] == {
        "merge_sha": "c" * 40,
        "deployed_sha": "c" * 40,
        "pr_number": 205,
    }
    continuation = controller.store.read_json(history_path)
    assert isinstance(continuation, dict)
    assert continuation["state"] == "continuation-in-progress"
    assert continuation["previous_production_success"] == previous_history
    assert controller.store.delivery_state()["owner"] is None
    assert not controller.repository.status(worktree)


def test_record_production_success_rejects_sha_mismatch_without_mutation(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, _, _, sha_pair = _prepare_started(repository, "204")
    _, head_sha = sha_pair.split(":")
    lease = controller.store.read_json(controller.store.task_lease_path("204"))
    controller.mark_ready("204", head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")
    _prepare_delivery(controller, "204", branch=lease["branch"])
    with pytest.raises(task_session.TaskSessionError, match="equal the exact merged master SHA"):
        controller.record_production_success(
            "204", pr_number=204, merge_sha="a" * 40, deployed_sha=head_sha
        )
    assert (
        controller.store.read_json(controller.store.task_lease_path("204"))["lifecycle_state"]
        == "working"
    )


def test_record_production_success_rejects_anchor_changed_during_finalization(
    repository: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _, controller, _, branch, sha_pair = _prepare_started(repository, "204A")
    base_sha, head_sha = sha_pair.split(":")
    controller.mark_ready("204A", head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")
    _prepare_delivery(controller, "204A", branch=branch)

    _git(root, "merge", "--no-ff", branch, "-m", "Merge task 204A")
    merge_sha = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "origin", "master")
    github = controller.github
    assert isinstance(github, FakeGitHub)
    github.master_sha = merge_sha
    github.pulls[214] = _task_pr(214, "204A", base_sha, head_sha, merge_sha=merge_sha)
    github.commits[214] = [_task_commit("204A")]
    github.files[214] = [{"filename": "change.txt"}]
    github.checks[head_sha] = [_success_check(head_sha)]
    github.successful_deployments.add((merge_sha, "production"))

    original_validation = task_session.validate_task_pull_request
    calls = 0

    def invalidate_after_pr_validation(*args: Any, **kwargs: Any) -> str:
        nonlocal calls
        result = original_validation(*args, **kwargs)
        calls += 1
        if calls == 1:
            lease_path = controller.store.task_lease_path("204A")
            lease = controller.store.read_json(lease_path)
            assert isinstance(lease, dict)
            lease["delivery_anchor"] = None
            task_session.StateStore.replace_json(lease_path, lease)
        return result

    monkeypatch.setattr(task_session, "validate_task_pull_request", invalidate_after_pr_validation)

    with pytest.raises(
        task_session.TaskSessionError,
        match="Delivery anchor changed before production completion",
    ):
        controller.record_production_success(
            "204A", pr_number=214, merge_sha=merge_sha, deployed_sha=merge_sha
        )

    assert calls == 1
    assert not (controller.store.history / "task-204A.json").exists()


def test_verify_master_merge_accepts_only_one_task_pr_for_current_master() -> None:
    base_sha = "a" * 40
    merge_sha = "c" * 40
    github = FakeGitHub(merge_sha)
    github.associated_pulls = [_task_pr(205, "205", base_sha, "b" * 40, merge_sha=merge_sha)]
    result = task_session.verify_master_merge(object(), github, sha=merge_sha)
    assert result["kind"] == "task-pr-merge"
    assert result["pull_request"]["number"] == 205


def test_verify_master_merge_accepts_task_393_integration_pr() -> None:
    base_sha = "a" * 40
    merge_sha = "c" * 40
    integration_pr = _task_pr(472, "393", base_sha, "b" * 40, merge_sha=merge_sha)
    integration_pr["head"]["ref"] = "feature/app-experience-v3"
    github = FakeGitHub(merge_sha)
    github.associated_pulls = [integration_pr]

    result = task_session.verify_master_merge(object(), github, sha=merge_sha)

    assert result["kind"] == "task-pr-merge"
    assert result["pull_request"]["number"] == 472


@pytest.mark.parametrize(
    ("title", "head_repository"),
    [
        ("[Task 392] Unrelated delivery", "owner/repository"),
        ("[Task 393] App Experience v3", "fork/repository"),
    ],
)
def test_verify_master_merge_rejects_misattributed_task_393_integration_pr(
    title: str, head_repository: str
) -> None:
    base_sha = "a" * 40
    merge_sha = "c" * 40
    integration_pr = _task_pr(472, "393", base_sha, "b" * 40, merge_sha=merge_sha)
    integration_pr["head"]["ref"] = "feature/app-experience-v3"
    integration_pr["title"] = title
    integration_pr["head"]["repo"]["full_name"] = head_repository
    github = FakeGitHub(merge_sha)
    github.associated_pulls = [integration_pr]

    with pytest.raises(
        task_session.TaskSessionError,
        match="not exactly one merged task or controller PR",
    ):
        task_session.verify_master_merge(object(), github, sha=merge_sha)


def test_reconcile_and_finish_accept_task_393_integration_branch_anchor(
    repository: tuple[Path, Any],
) -> None:
    _, git_repository, controller, worktree, branch, superseding_prs, deployed_sha = (
        _prepare_superseding_production_reconciliation(
            repository,
            task_id="393",
            superseding_count=1,
            post_deploy_drift=False,
            original_pr_branch="feature/app-experience-v3",
            superseding_pr_branch="feature/app-experience-v3",
        )
    )

    history = controller.reconcile_production_success(
        "393",
        original_pr_number=423,
        superseding_pr_numbers=superseding_prs,
        deployed_sha=deployed_sha,
        production_run_id=35783412553,
        owner_authorize=True,
    )

    assert history["superseding_production_reconciliation"]["anchor_classification"] == (
        "exact_delivery_anchor"
    )
    assert history["superseding_production_reconciliation"]["original_delivery"]["branch"] == (
        "feature/app-experience-v3"
    )
    assert controller.finish("393")["cleanup_performed"] is True
    assert not worktree.exists()
    assert not git_repository.ref_exists(branch)


def test_verify_master_merge_accepts_one_controller_maintenance_pr() -> None:
    base_sha = "a" * 40
    merge_sha = "c" * 40
    controller_pr = _controller_pr(base_sha, "b" * 40)
    controller_pr["merged_at"] = "2026-09-11T10:00:00Z"
    controller_pr["merge_commit_sha"] = merge_sha
    github = FakeGitHub(merge_sha)
    github.associated_pulls = [controller_pr]

    result = task_session.verify_master_merge(object(), github, sha=merge_sha)

    assert result["kind"] == "controller-pr-merge"
    assert result["pull_request"]["number"] == 234


def test_verify_master_merge_accepts_trusted_dependabot_pr() -> None:
    base_sha = "a" * 40
    merge_sha = "c" * 40
    dependabot_pr = _task_pr(178, "178", base_sha, "b" * 40, merge_sha=merge_sha)
    dependabot_pr["title"] = "build(deps): bump wrapt from 2.3.0 to 2.4.0"
    dependabot_pr["user"] = {"login": "dependabot[bot]", "type": "Bot"}
    dependabot_pr["head"]["ref"] = "dependabot/pip/wrapt-2.4.0"
    github = FakeGitHub(merge_sha)
    github.associated_pulls = [dependabot_pr]

    result = task_session.verify_master_merge(object(), github, sha=merge_sha)

    assert result["kind"] == "dependabot-pr-merge"
    assert result["pull_request"]["number"] == 178


def test_verify_master_merge_rejects_dependabot_fork_pr() -> None:
    base_sha = "a" * 40
    merge_sha = "c" * 40
    dependabot_pr = _task_pr(178, "178", base_sha, "b" * 40, merge_sha=merge_sha)
    dependabot_pr["title"] = "build(deps): bump wrapt from 2.3.0 to 2.4.0"
    dependabot_pr["user"] = {"login": "dependabot[bot]", "type": "Bot"}
    dependabot_pr["head"]["ref"] = "dependabot/pip/wrapt-2.4.0"
    dependabot_pr["head"]["repo"]["full_name"] = "dependabot/fork"
    github = FakeGitHub(merge_sha)
    github.associated_pulls = [dependabot_pr]

    with pytest.raises(
        task_session.TaskSessionError, match="not exactly one merged task or controller PR"
    ):
        task_session.verify_master_merge(object(), github, sha=merge_sha)


def test_recover_is_read_only_and_preserves_dirty_unique_task_state(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, worktree, _, _ = _prepare_started(repository, "206")
    (worktree / "unique.txt").write_text("unique\n", encoding="utf-8")
    _git(worktree, "add", "unique.txt")
    _git(worktree, "commit", "-m", "feat: [Task 206] unique recovery state")
    (worktree / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    result = controller.recover("206")

    assert result["classification"] == "STALE_OR_INTERRUPTED"
    assert result["mutation_performed"] is False
    assert any(item["dirty"] for item in result["worktrees"])
    assert any(item["unique_commits"] for item in result["worktrees"])
    assert (worktree / "dirty.txt").exists()


def test_finish_preserves_active_delivery_artifacts_until_worker_cleanup(
    repository: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, git_repository, controller, worktree, branch, sha_pair = _prepare_started(
        repository, "207"
    )
    base_sha, head_sha = sha_pair.split(":")
    controller.mark_ready("207", head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")
    _prepare_delivery(controller, "207", branch=branch)
    _git(root, "merge", "--no-ff", branch, "-m", "Merge task 207")
    merge_sha = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "origin", "master")
    github = controller.github
    assert isinstance(github, FakeGitHub)
    github.master_sha = merge_sha
    github.pulls[207] = _task_pr(207, "207", base_sha, head_sha, merge_sha=merge_sha)
    github.commits[207] = [_task_commit("207")]
    github.files[207] = [{"filename": "change.txt"}]
    github.checks[head_sha] = [_success_check(head_sha)]
    github.successful_deployments.add((merge_sha, "production"))
    controller.record_production_success(
        "207", pr_number=207, merge_sha=merge_sha, deployed_sha=merge_sha
    )
    from scripts.artifact_manager import ArtifactManager

    active_delivery = ArtifactManager(
        root / ".artifacts", repo_root=root, controller_state_dir=controller.store.root
    ).allocate_directory(
        "207",
        "temporary",
        Path("temporary") / "delivery" / "active-worker",
        purpose="active continuous delivery worker output",
        command="scripts/run_task_delivery.py",
        owner="run_task_delivery",
    )
    (active_delivery / "events.jsonl").write_text("worker output\n", encoding="utf-8")
    monkeypatch.setenv(task_session.ACTIVE_DELIVERY_ARTIFACTS_ENV, str(active_delivery))

    result = controller.finish("207")

    assert result["cleanup_performed"] is True
    assert active_delivery.is_dir()
    assert (active_delivery / "events.jsonl").is_file()
    assert result["deleted_local_branch"] == branch
    assert not worktree.exists()
    assert not git_repository.ref_exists(branch)
    assert not controller.store.task_lease_path("207").exists()
    assert (
        controller.store.read_json(controller.store.history / "task-207.json")["state"]
        == "finished"
    )


def test_finish_fast_forwards_stale_local_master_before_cleanup(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository, controller, worktree, branch, sha_pair = _prepare_started(
        repository, "207A"
    )
    base_sha, head_sha = sha_pair.split(":")
    controller.mark_ready("207A", head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")
    _prepare_delivery(controller, "207A", branch=branch)
    merge_sha = _publish_task_merge_without_advancing_local_master(root, branch)
    assert git_repository.ref("master") == base_sha
    assert git_repository.ref("origin/master") == merge_sha

    github = controller.github
    assert isinstance(github, FakeGitHub)
    github.master_sha = merge_sha
    github.pulls[207] = _task_pr(207, "207A", base_sha, head_sha, merge_sha=merge_sha)
    github.commits[207] = [_task_commit("207A")]
    github.files[207] = [{"filename": "change.txt"}]
    github.checks[head_sha] = [_success_check(head_sha)]
    github.successful_deployments.add((merge_sha, "production"))
    controller.record_production_success(
        "207A", pr_number=207, merge_sha=merge_sha, deployed_sha=merge_sha
    )

    result = controller.finish("207A")

    assert result["local_master_fast_forwarded"] is True
    assert result["worktree_already_removed"] is False
    assert git_repository.ref("master") == merge_sha
    assert not worktree.exists()
    assert not git_repository.ref_exists(branch)


def test_finish_accepts_verified_squash_merge(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository, controller, worktree, branch, sha_pair = _prepare_started(
        repository, "207C"
    )
    base_sha, head_sha = sha_pair.split(":")
    controller.mark_ready("207C", head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")
    _prepare_delivery(controller, "207C", branch=branch)
    merge_sha = _publish_task_squash_without_advancing_local_master(root, branch)

    github = controller.github
    assert isinstance(github, FakeGitHub)
    github.master_sha = merge_sha
    github.pulls[207] = _task_pr(207, "207C", base_sha, head_sha, merge_sha=merge_sha)
    github.commits[207] = [_task_commit("207C")]
    github.files[207] = [{"filename": "change.txt"}]
    github.checks[head_sha] = [_success_check(head_sha)]
    github.successful_deployments.add((merge_sha, "production"))
    controller.record_production_success(
        "207C", pr_number=207, merge_sha=merge_sha, deployed_sha=merge_sha
    )

    result = controller.finish("207C")

    assert result["cleanup_performed"] is True
    assert not worktree.exists()
    assert not git_repository.ref_exists(branch)


def test_task_session_exposes_ready_production_reconciliation_command() -> None:
    args = task_session._parser().parse_args(
        [
            "reconcile-ready-production-success",
            "506",
            "--pr",
            "570",
            "--production-run",
            "36522345602",
            "--deployed-sha",
            "a" * 40,
            "--owner-authorize",
        ]
    )

    assert args.command == "reconcile-ready-production-success"
    assert args.pr == 570
    assert args.production_run == 36522345602
    assert args.owner_authorize is True


def test_reconcile_historical_production_success_accepts_task_746_shape_and_finishes(
    repository: tuple[Path, Any],
) -> None:
    (
        _root,
        git_repository,
        controller,
        worktree,
        branch,
        base_sha,
        anchor_head_sha,
        deployed_sha,
        _github,
        records,
    ) = _prepare_historical_production_reconciliation(repository)
    final_head_sha = git_repository.ref(branch)

    history = controller.reconcile_historical_production_success(
        "746",
        pr_number=764,
        deployed_sha=deployed_sha,
        production_run_id=37419987998,
        owner_authorize=True,
    )

    assert history["state"] == "production-success"
    assert history["deployed_sha"] == deployed_sha
    assert history["head_sha"] == final_head_sha
    assert history["base_sha"] == base_sha
    audit = history["historical_production_reconciliation"]
    assert audit["preserved_anchor"]["head_sha"] == anchor_head_sha
    assert audit["final_task_pr"]["head_sha"] == final_head_sha
    assert audit["final_task_pr"]["bounded_delivery_commits"]
    assert audit["original_production"]["run_id"] == 37419987998
    assert [
        item["classification"]
        for item in audit["verified_master_evidence"]["intervening_commits"]
    ] == ["controller", "product"]
    assert audit["verified_master_evidence"]["current_master_sha"] == records[-1]["commit_sha"]
    assert audit["feature_preservation"]["migration_paths"] == [
        "backend/alembic/versions/0120_synthetic.py"
    ]

    lease = controller.store.read_json(controller.store.task_lease_path("746"))
    assert isinstance(lease, dict)
    assert lease["lifecycle_state"] == task_session.DEPLOYED_STATE
    assert lease["ready_head_sha"] == anchor_head_sha
    assert lease["delivery_head_sha"] == anchor_head_sha
    assert lease["historical_production_reconciliation"] == audit

    result = controller.finish("746")

    assert result["cleanup_performed"] is True
    assert result["deleted_local_branch"] == branch
    assert not worktree.exists()
    assert not git_repository.ref_exists(branch)
    finished = controller.store.read_json(controller.store.history / "task-746.json")
    assert finished["state"] == "finished"
    assert finished["historical_production_reconciliation"] == audit


def test_reconcile_historical_production_success_requires_owner_authorization(
    repository: tuple[Path, Any],
) -> None:
    (
        _root,
        _git_repository,
        controller,
        _worktree,
        _branch,
        _base_sha,
        _anchor_head_sha,
        deployed_sha,
        _github,
        _records,
    ) = _prepare_historical_production_reconciliation(repository)

    with pytest.raises(task_session.TaskSessionError, match="explicit owner authorization"):
        controller.reconcile_historical_production_success(
            "746",
            pr_number=764,
            deployed_sha=deployed_sha,
            production_run_id=37419987998,
            owner_authorize=False,
        )

    assert not (controller.store.history / "task-746.json").exists()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("anchor_ancestry", "not an ancestor of the final task PR head"),
        ("foreign_task_history", "does not belong exclusively to the same task"),
        ("pr_task_mismatch", "Task 746"),
        ("failed_check", "Exact-head required check"),
        ("missing_deployment", "lacks an exact successful deployment"),
        ("missing_subsequent_provenance", "no unique merged pull request"),
        ("controller_allowlist", "disallowed"),
        ("feature_revert", "appears fully reverted"),
        ("dirty_worktree", "dirty or interrupted task worktree"),
        ("unique_worktree", "unique local task commits"),
        ("active_delivery", "active delivery owner"),
        ("active_deployment", "production deployment is active"),
        ("missing_latest_release", "product commits after the latest production deployment"),
        ("non_ancestor_merge", "merge is not an ancestor of current master"),
    ],
)
def test_reconcile_historical_production_success_fails_closed(
    repository: tuple[Path, Any],
    mutation: str,
    message: str,
) -> None:
    (
        root,
        git_repository,
        controller,
        worktree,
        _branch,
        base_sha,
        _anchor_head_sha,
        deployed_sha,
        github,
        records,
    ) = _prepare_historical_production_reconciliation(
        repository,
        revert_feature=mutation == "feature_revert",
        controller_disallowed_path=mutation == "controller_allowlist",
        omit_latest_release=mutation == "missing_latest_release",
    )

    if mutation == "anchor_ancestry":
        lease_path = controller.store.task_lease_path("746")
        lease = controller.store.read_json(lease_path)
        assert isinstance(lease, dict)
        invalid_anchor = records[-1]["commit_sha"]
        lease["ready_head_sha"] = invalid_anchor
        lease["delivery_head_sha"] = invalid_anchor
        lease["delivery_anchor"]["head_sha"] = invalid_anchor
        lease["task_provenance"]["head_sha"] = invalid_anchor
        task_session.StateStore.replace_json(lease_path, lease)
    elif mutation == "foreign_task_history":
        github.commits[764][-1]["commit"]["message"] = "[Task 999] Foreign delivery mutation"
    elif mutation == "pr_task_mismatch":
        github.pulls[764]["title"] = "[Task 999] Wrong task"
    elif mutation == "failed_check":
        final_head = github.pulls[764]["head"]["sha"]
        github.checks[final_head] = [
            {
                "name": "checks",
                "head_sha": final_head,
                "status": "completed",
                "conclusion": "FAILURE",
            }
        ]
    elif mutation == "missing_deployment":
        github.successful_deployments.discard((deployed_sha, "production"))
    elif mutation == "missing_subsequent_provenance":
        github.associated_pulls_by_commit.pop(records[0]["commit_sha"], None)
    elif mutation == "dirty_worktree":
        (worktree / "untracked-recovery.txt").write_text("preserve\n", encoding="utf-8")
    elif mutation == "unique_worktree":
        unique_path = worktree / "unique.txt"
        unique_path.write_text("unique\n", encoding="utf-8")
        _git(worktree, "add", "unique.txt")
        _git(worktree, "commit", "-m", "[Task 746] Unmerged local recovery commit")
    elif mutation == "active_delivery":
        delivery = controller.store.delivery_state()
        delivery["owner"] = {"task_id": "999"}
        task_session.StateStore.replace_json(controller.store.delivery_path, delivery)
    elif mutation == "active_deployment":
        github.active_runs = [{"name": "Release production", "status": "in_progress"}]
    elif mutation == "non_ancestor_merge":
        _git(root, "switch", "-c", "task/999-side-history", base_sha)
        side_path = root / "side-history.txt"
        side_path.write_text("side\n", encoding="utf-8")
        _git(root, "add", "side-history.txt")
        _git(root, "commit", "-m", "[Task 999] Side history")
        side_sha = _git(root, "rev-parse", "HEAD")
        _git(root, "switch", "master")
        github.pulls[764]["merge_commit_sha"] = side_sha
        deployed_sha = side_sha
        github.runs[37419987998]["head_sha"] = side_sha
        github.successful_deployments.add((side_sha, "production"))

    with pytest.raises(task_session.TaskSessionError, match=message):
        controller.reconcile_historical_production_success(
            "746",
            pr_number=764,
            deployed_sha=deployed_sha,
            production_run_id=37419987998,
            owner_authorize=True,
        )

    assert not (controller.store.history / "task-746.json").exists()


def test_reconcile_historical_production_success_rejects_master_race(
    repository: tuple[Path, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _root,
        git_repository,
        controller,
        _worktree,
        _branch,
        _base_sha,
        _anchor_head_sha,
        deployed_sha,
        _github,
        _records,
    ) = _prepare_historical_production_reconciliation(repository)
    original_ref = git_repository.ref
    origin_master_reads = 0

    def racing_ref(name: str) -> str:
        nonlocal origin_master_reads
        value = original_ref(name)
        if name == "origin/master":
            origin_master_reads += 1
            if origin_master_reads >= 3:
                return "f" * 40
        return value

    monkeypatch.setattr(git_repository, "ref", racing_ref)

    with pytest.raises(task_session.TaskSessionError, match="origin/master changed during"):
        controller.reconcile_historical_production_success(
            "746",
            pr_number=764,
            deployed_sha=deployed_sha,
            production_run_id=37419987998,
            owner_authorize=True,
        )

    assert not (controller.store.history / "task-746.json").exists()


def test_historical_production_reconciliation_parser_contract() -> None:
    args = task_session._parser().parse_args(
        [
            "reconcile-historical-production-success",
            "746",
            "--pr",
            "764",
            "--deployed-sha",
            "a" * 40,
            "--production-run",
            "37419987998",
            "--owner-authorize",
        ]
    )

    assert args.task_id == "746"
    assert args.pr == 764
    assert args.deployed_sha == "a" * 40
    assert args.production_run == 37419987998
    assert args.owner_authorize is True


def test_reconcile_ready_production_success_accepts_exact_squash_and_finishes(
    repository: tuple[Path, Any],
) -> None:
    (
        _root,
        git_repository,
        controller,
        worktree,
        branch,
        base_sha,
        head_sha,
        _github,
    ) = _prepare_ready_production_reconciliation(repository)
    lease_path = controller.store.task_lease_path("506")
    lease_before = controller.store.read_json(lease_path)
    assert isinstance(lease_before, dict)
    worktree_head_before = git_repository.head(cwd=worktree)
    branch_head_before = git_repository.ref(branch)
    status_before = git_repository.status(worktree)

    history = controller.reconcile_ready_production_success(
        "506",
        pr_number=570,
        deployed_sha=git_repository.ref("origin/master"),
        production_run_id=36522345602,
        owner_authorize=True,
    )

    deployed_sha = git_repository.ref("origin/master")
    assert history["state"] == "production-success"
    assert history["head_sha"] == head_sha
    assert history["base_sha"] == base_sha
    assert history["merge_sha"] == deployed_sha
    assert history["deployed_sha"] == deployed_sha
    assert history["pr_number"] == 570
    assert history["closeout_required"] is True
    audit = history["ready_production_reconciliation"]
    assert audit["owner_authorized"] is True
    assert audit["authorization"] == "explicit --owner-authorize"
    assert audit["ready_head_sha"] == head_sha
    assert audit["ready_base_origin_master_sha"] == base_sha
    assert audit["production"]["run_id"] == 36522345602

    lease_after = controller.store.read_json(lease_path)
    assert isinstance(lease_after, dict)
    assert lease_after["lifecycle_state"] == "deployed"
    assert lease_after["ready_head_sha"] == lease_before["ready_head_sha"]
    assert (
        lease_after["ready_base_origin_master_sha"] == lease_before["ready_base_origin_master_sha"]
    )
    assert lease_after["task_provenance"] == lease_before["task_provenance"]
    assert controller.store.delivery_state()["owner"] is None
    assert git_repository.head(cwd=worktree) == worktree_head_before
    assert git_repository.ref(branch) == branch_head_before
    assert git_repository.status(worktree) == status_before

    result = controller.finish("506")

    assert result["cleanup_performed"] is True
    assert result["deleted_local_branch"] == branch
    assert not worktree.exists()
    assert not git_repository.ref_exists(branch)
    finished = controller.store.read_json(controller.store.history / "task-506.json")
    assert finished["state"] == "finished"
    assert finished["ready_production_reconciliation"] == audit


@pytest.mark.parametrize(
    ("invalid_case", "expected_error"),
    [
        ("owner_authorization", "explicit owner authorization"),
        ("missing_ready_provenance", "ready base and head provenance"),
        ("delivery_owner", "active delivery owner"),
        ("history", "Production history already exists"),
        ("dirty_worktree", "dirty or interrupted task worktree"),
        ("branch", "leased task branch"),
        ("base", "ready base"),
        ("head", "ready head"),
        ("deployed", "deployed SHA"),
        ("run", "successful for the exact deployed SHA"),
        ("deployment", "successful production deployment"),
        ("active_deployment", "production deployment is active"),
        ("worker_state", "unreconciled worker state"),
        ("missing_run", "unavailable for reconciliation"),
    ],
)
def test_reconcile_ready_production_success_rejects_unsafe_evidence(
    repository: tuple[Path, Any], invalid_case: str, expected_error: str
) -> None:
    (
        _root,
        git_repository,
        controller,
        worktree,
        _branch,
        base_sha,
        _head_sha,
        github,
    ) = _prepare_ready_production_reconciliation(repository)
    owner_authorize = True
    deployed_sha = git_repository.ref("origin/master")
    lease_path = controller.store.task_lease_path("506")

    if invalid_case == "owner_authorization":
        owner_authorize = False
    elif invalid_case == "missing_ready_provenance":
        lease = controller.store.read_json(lease_path)
        assert isinstance(lease, dict)
        lease["ready_head_sha"] = ""
        task_session.StateStore.replace_json(lease_path, lease)
    elif invalid_case == "delivery_owner":
        delivery = controller.store.delivery_state()
        delivery["owner"] = {"task_id": "999", "acquired_at": task_session.utc_now()}
        task_session.StateStore.replace_json(controller.store.delivery_path, delivery)
    elif invalid_case == "history":
        task_session.StateStore.replace_json(
            controller.store.history / "task-506.json",
            {"task_id": "506", "state": "production-success"},
        )
    elif invalid_case == "dirty_worktree":
        (worktree / "untracked.txt").write_text("preserve\n", encoding="utf-8")
    elif invalid_case == "branch":
        github.pulls[570]["head"]["ref"] = "task/506-other-slug"
    elif invalid_case == "base":
        github.pulls[570]["base"]["sha"] = "1" * 40
    elif invalid_case == "head":
        github.pulls[570]["head"]["sha"] = "2" * 40
    elif invalid_case == "deployed":
        deployed_sha = base_sha
    elif invalid_case == "run":
        github.runs[36522345602]["head_sha"] = base_sha
    elif invalid_case == "deployment":
        github.successful_deployments.clear()
    elif invalid_case == "active_deployment":
        github.active_runs = [{"name": "Release production", "status": "in_progress"}]
    elif invalid_case == "worker_state":
        worker_state = (
            _root
            / ".artifacts"
            / "tasks"
            / "506"
            / "temporary"
            / "delivery"
            / "run"
            / "worker-state.json"
        )
        worker_state.parent.mkdir(parents=True)
        worker_state.write_text("{}\n", encoding="utf-8")
    elif invalid_case == "missing_run":
        github.runs.pop(36522345602)

    with pytest.raises(task_session.TaskSessionError, match=expected_error):
        controller.reconcile_ready_production_success(
            "506",
            pr_number=570,
            deployed_sha=deployed_sha,
            production_run_id=36522345602,
            owner_authorize=owner_authorize,
        )

    lease = controller.store.read_json(lease_path)
    assert isinstance(lease, dict)
    assert lease["lifecycle_state"] == "working"
    if invalid_case != "history":
        assert not (controller.store.history / "task-506.json").exists()


def _prepare_ready_production_reconciliation_with_advanced_base(
    repository: tuple[Path, Any],
    *,
    integration_subject: str = "Merge remote-tracking branch 'origin/master' into task/506-synthetic-task",
) -> tuple[Path, Any, Any, Path, str, str, str, str, str, FakeGitHub]:
    root, git_repository, controller, worktree, branch, sha_pair = _prepare_started(
        repository, "506"
    )
    ready_base_sha, _initial_head_sha = sha_pair.split(":")
    _advance_remote_master(root, 1)
    effective_base_sha = _git(root, "rev-parse", "origin/master")
    _git(worktree, "merge", "--no-ff", "origin/master", "-m", integration_subject)
    ready_head_sha = _git(worktree, "rev-parse", "HEAD")
    controller.mark_ready("506", head_sha=ready_head_sha, quality_verdict="PASS", qa_verdict="PASS")
    merge_sha = _publish_task_squash_from_origin_master(root, branch, "506")
    github = controller.github
    assert isinstance(github, FakeGitHub)
    github.master_sha = merge_sha
    pull_request = _task_pr(570, "506", effective_base_sha, ready_head_sha, merge_sha=merge_sha)
    pull_request["state"] = "closed"
    pull_request["head"]["ref"] = branch
    github.pulls[570] = pull_request
    github.commits[570] = [_task_commit("506")]
    github.files[570] = [{"filename": "change.txt"}]
    github.checks[ready_head_sha] = [_success_check(ready_head_sha)]
    github.runs[36522345602] = {
        "id": 36522345602,
        "name": "Release production",
        "head_sha": merge_sha,
        "status": "completed",
        "conclusion": "success",
        "html_url": "https://example.invalid/actions/runs/36522345602",
    }
    github.successful_deployments.add((merge_sha, "production"))
    return (
        root,
        git_repository,
        controller,
        worktree,
        branch,
        ready_base_sha,
        effective_base_sha,
        ready_head_sha,
        merge_sha,
        github,
    )


def test_reconcile_ready_production_success_accepts_integrated_current_pr_base(
    repository: tuple[Path, Any],
) -> None:
    (
        _root,
        git_repository,
        controller,
        worktree,
        branch,
        ready_base_sha,
        effective_base_sha,
        ready_head_sha,
        merge_sha,
        _github,
    ) = _prepare_ready_production_reconciliation_with_advanced_base(repository)
    branch_before = git_repository.ref(branch)

    history = controller.reconcile_ready_production_success(
        "506",
        pr_number=570,
        deployed_sha=merge_sha,
        production_run_id=36522345602,
        owner_authorize=True,
    )

    audit = history["ready_production_reconciliation"]
    assert audit["anchor_classification"] == "integrated_current_base"
    assert audit["original_ready_base_sha"] == ready_base_sha
    assert audit["effective_pr_base_sha"] == effective_base_sha
    assert audit["ready_head_sha"] == ready_head_sha
    assert audit["integration_merge"]["second_parent_sha"] == effective_base_sha
    assert audit["verified_master_evidence"]["classification"] == "exact_deployed_master"
    assert git_repository.ref(branch) == branch_before
    assert worktree.exists()

    result = controller.finish("506")

    assert result["cleanup_performed"] is True
    assert not worktree.exists()
    assert not git_repository.ref_exists(branch)


def test_reconcile_ready_production_rejects_advanced_base_without_integration_merge(
    repository: tuple[Path, Any],
) -> None:
    (
        _root,
        _git_repository,
        controller,
        _worktree,
        _branch,
        _ready_base_sha,
        _effective_base_sha,
        _ready_head_sha,
        merge_sha,
        _github,
    ) = _prepare_ready_production_reconciliation_with_advanced_base(
        repository,
        integration_subject="Merge arbitrary branch into task/506-synthetic-task [Task 506]",
    )

    with pytest.raises(
        task_session.TaskSessionError,
        match="requires one valid origin/master integration merge",
    ):
        controller.reconcile_ready_production_success(
            "506",
            pr_number=570,
            deployed_sha=merge_sha,
            production_run_id=36522345602,
            owner_authorize=True,
        )

    assert not (controller.store.history / "task-506.json").exists()


def test_reconcile_ready_production_success_records_verified_controller_drift(
    repository: tuple[Path, Any],
) -> None:
    (
        root,
        git_repository,
        controller,
        worktree,
        branch,
        _base_sha,
        ready_head_sha,
        _github,
    ) = _prepare_ready_production_reconciliation(repository)
    deployed_sha = git_repository.ref("origin/master")
    github = controller.github
    assert isinstance(github, FakeGitHub)
    github.workflow_runs_by_sha[deployed_sha] = [
        {
            "id": 36522345602,
            "name": "Release production",
            "head_sha": deployed_sha,
            "status": "completed",
            "conclusion": "success",
            "html_url": "https://example.invalid/actions/runs/36522345602",
        }
    ]

    remote_worktree = root.parent / f"remote-controller-drift-{uuid.uuid4().hex[:8]}"
    _git(root, "worktree", "add", "--detach", str(remote_worktree), deployed_sha)
    try:
        (remote_worktree / "AGENTS.md").write_text("controller drift\\n", encoding="utf-8")
        _git(remote_worktree, "add", "AGENTS.md")
        _git(remote_worktree, "commit", "-m", "[Controller] Record governance drift")
        drift_sha = _git(remote_worktree, "rev-parse", "HEAD")
        _git(remote_worktree, "push", "origin", "HEAD:master")
    finally:
        _git(root, "worktree", "remove", "--force", str(remote_worktree))
    _git(root, "fetch", "origin", "master")

    controller_pr = _controller_pr(deployed_sha, drift_sha)
    controller_pr.update(
        {
            "number": 572,
            "state": "closed",
            "merged_at": "2026-09-03T11:00:00Z",
            "merge_commit_sha": drift_sha,
            "commits": 1,
            "changed_files": 1,
        }
    )
    github.master_sha = drift_sha
    github.pulls[572] = controller_pr
    github.commits[572] = [
        {"sha": drift_sha, "commit": {"message": "[Controller] Record governance drift"}}
    ]
    github.files[572] = [{"filename": "AGENTS.md"}]
    github.checks[drift_sha] = [_success_check(drift_sha)]
    github.associated_pulls_by_commit[drift_sha] = [{"number": 572, "merge_commit_sha": drift_sha}]
    controller_run = {
        "id": 36539698782,
        "name": "Release production",
        "head_sha": drift_sha,
        "status": "completed",
        "conclusion": "success",
        "html_url": "https://example.invalid/actions/runs/36539698782",
    }
    github.workflow_runs_by_sha[drift_sha] = [controller_run]
    github.workflow_jobs_by_run[36539698782] = [
        {"name": "Authorize exact merged master revision", "conclusion": "success"},
        {"name": "Deploy immutable tested bundle", "conclusion": "skipped"},
    ]
    github.current_production_deployment = {
        "environment": "production",
        "state": "success",
        "sha": deployed_sha,
        "deployment_id": 1,
    }

    history = controller.reconcile_ready_production_success(
        "506",
        pr_number=570,
        deployed_sha=deployed_sha,
        production_run_id=36522345602,
        owner_authorize=True,
    )

    evidence = history["ready_production_reconciliation"]["verified_master_evidence"]
    assert evidence["classification"] == "verified_controller_only_drift"
    assert evidence["current_master_sha"] == drift_sha
    assert evidence["current_production"]["deployed_sha"] == deployed_sha
    assert evidence["intervening_commits"][0]["classification"] == "controller"
    assert history["ready_production_reconciliation"]["production"]["run_id"] == 36522345602
    assert git_repository.ref(branch) == ready_head_sha
    assert worktree.exists()

    result = controller.finish("506")

    assert result["cleanup_performed"] is True
    assert not worktree.exists()
    assert not git_repository.ref_exists(branch)


@pytest.mark.parametrize(
    "drift_paths",
    [
        ("AGENTS.md",),
        ("scripts/artifact_manager.py", "tests/test_artifact_manager.py"),
    ],
)
def test_finish_accepts_controller_only_master_drift_after_deployment(
    repository: tuple[Path, Any],
    drift_paths: tuple[str, ...],
) -> None:
    root, git_repository, controller, worktree, branch, sha_pair = _prepare_started(
        repository, "207D"
    )
    base_sha, head_sha = sha_pair.split(":")
    controller.mark_ready("207D", head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")
    _prepare_delivery(controller, "207D", branch=branch)
    merge_sha = _publish_task_merge_without_advancing_local_master(root, branch)

    github = controller.github
    assert isinstance(github, FakeGitHub)
    github.master_sha = merge_sha
    github.pulls[207] = _task_pr(207, "207D", base_sha, head_sha, merge_sha=merge_sha)
    github.commits[207] = [_task_commit("207D")]
    github.files[207] = [{"filename": "change.txt"}]
    github.checks[head_sha] = [_success_check(head_sha)]
    github.successful_deployments.add((merge_sha, "production"))
    controller.record_production_success(
        "207D", pr_number=207, merge_sha=merge_sha, deployed_sha=merge_sha
    )

    _git(root, "merge", "--ff-only", "origin/master")
    remote_worktree = root.parent / f"remote-controller-drift-{uuid.uuid4().hex[:8]}"
    _git(root, "worktree", "add", "--detach", str(remote_worktree), merge_sha)
    try:
        for drift_path in drift_paths:
            changed_file = remote_worktree / Path(drift_path)
            changed_file.parent.mkdir(parents=True, exist_ok=True)
            changed_file.write_text("controller-only drift\n", encoding="utf-8")
        _git(remote_worktree, "add", *drift_paths)
        _git(remote_worktree, "commit", "-m", "[Controller] Advance governance after deployment")
        drift_sha = _git(remote_worktree, "rev-parse", "HEAD")
        _git(remote_worktree, "push", "origin", "HEAD:master")
    finally:
        _git(root, "worktree", "remove", "--force", str(remote_worktree))
    _git(root, "fetch", "origin", "master")

    result = controller.finish("207D")

    assert result["cleanup_performed"] is True
    assert result["local_master_fast_forwarded"] is True
    assert git_repository.ref("master") == drift_sha
    assert not worktree.exists()
    assert not git_repository.ref_exists(branch)


def test_finish_rejects_product_master_drift_after_deployment(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository, controller, worktree, branch, sha_pair = _prepare_started(
        repository, "207E"
    )
    base_sha, head_sha = sha_pair.split(":")
    controller.mark_ready("207E", head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")
    _prepare_delivery(controller, "207E", branch=branch)
    merge_sha = _publish_task_merge_without_advancing_local_master(root, branch)

    github = controller.github
    assert isinstance(github, FakeGitHub)
    github.master_sha = merge_sha
    github.pulls[207] = _task_pr(207, "207E", base_sha, head_sha, merge_sha=merge_sha)
    github.commits[207] = [_task_commit("207E")]
    github.files[207] = [{"filename": "change.txt"}]
    github.checks[head_sha] = [_success_check(head_sha)]
    github.successful_deployments.add((merge_sha, "production"))
    controller.record_production_success(
        "207E", pr_number=207, merge_sha=merge_sha, deployed_sha=merge_sha
    )

    _git(root, "merge", "--ff-only", "origin/master")
    remote_worktree = root.parent / f"remote-product-drift-{uuid.uuid4().hex[:8]}"
    _git(root, "worktree", "add", "--detach", str(remote_worktree), merge_sha)
    try:
        (remote_worktree / "frontend").mkdir()
        (remote_worktree / "frontend" / "product-drift.txt").write_text(
            "product drift\n", encoding="utf-8"
        )
        _git(remote_worktree, "add", "frontend/product-drift.txt")
        _git(remote_worktree, "commit", "-m", "[Task 999] Product drift after deployment")
        _git(remote_worktree, "push", "origin", "HEAD:master")
    finally:
        _git(root, "worktree", "remove", "--force", str(remote_worktree))
    _git(root, "fetch", "origin", "master")

    with pytest.raises(task_session.TaskSessionError, match="non-controller drift"):
        controller.finish("207E")

    assert worktree.exists()
    assert git_repository.ref_exists(branch)
    assert controller.store.task_lease_path("207E").exists()
    assert controller.store.delivery_state()["owner"]["task_id"] == "207E"


def test_finish_recovers_after_worktree_removed_before_branch_cleanup(
    repository: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, git_repository, controller, worktree, branch, sha_pair = _prepare_started(
        repository, "207B"
    )
    base_sha, head_sha = sha_pair.split(":")
    controller.mark_ready("207B", head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")
    _prepare_delivery(controller, "207B", branch=branch)
    merge_sha = _publish_task_merge_without_advancing_local_master(root, branch)
    github = controller.github
    assert isinstance(github, FakeGitHub)
    github.master_sha = merge_sha
    github.pulls[207] = _task_pr(207, "207B", base_sha, head_sha, merge_sha=merge_sha)
    github.commits[207] = [_task_commit("207B")]
    github.files[207] = [{"filename": "change.txt"}]
    github.checks[head_sha] = [_success_check(head_sha)]
    github.successful_deployments.add((merge_sha, "production"))
    controller.record_production_success(
        "207B", pr_number=207, merge_sha=merge_sha, deployed_sha=merge_sha
    )

    original_delete = git_repository.delete_local_branch
    calls = 0

    def fail_once(task_branch: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise task_session.TaskSessionError("simulated cleanup race")
        original_delete(task_branch)

    monkeypatch.setattr(git_repository, "delete_local_branch", fail_once)
    with pytest.raises(task_session.TaskSessionError, match="simulated cleanup race"):
        controller.finish("207B")

    assert not worktree.exists()
    assert git_repository.ref_exists(branch)
    assert controller.store.read_json(controller.store.history / "task-207B.json")["state"] == (
        "production-success"
    )

    result = controller.finish("207B")

    assert result["worktree_already_removed"] is True
    assert result["local_master_fast_forwarded"] is False
    assert not git_repository.ref_exists(branch)
    assert not controller.store.task_lease_path("207B").exists()
    assert controller.store.read_json(controller.store.history / "task-207B.json")["state"] == (
        "finished"
    )


def test_finish_records_windows_residue_without_blocking_terminal_closeout(
    repository: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, git_repository, controller, worktree, branch, sha_pair = _prepare_started(
        repository, "207F"
    )
    base_sha, head_sha = sha_pair.split(":")
    controller.mark_ready("207F", head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")
    _prepare_delivery(controller, "207F", branch=branch)
    _git(root, "merge", "--no-ff", branch, "-m", "Merge task 207F")
    merge_sha = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "origin", "master")
    github = controller.github
    assert isinstance(github, FakeGitHub)
    github.master_sha = merge_sha
    github.pulls[207] = _task_pr(207, "207F", base_sha, head_sha, merge_sha=merge_sha)
    github.commits[207] = [_task_commit("207F")]
    github.files[207] = [{"filename": "change.txt"}]
    github.checks[head_sha] = [_success_check(head_sha)]
    github.successful_deployments.add((merge_sha, "production"))
    controller.record_production_success(
        "207F", pr_number=207, merge_sha=merge_sha, deployed_sha=merge_sha
    )

    original_remove = git_repository.remove_worktree

    def remove_but_leave_residue(path: Path) -> dict[str, Any]:
        result = original_remove(path)
        path.mkdir(parents=True, exist_ok=True)
        (path / "locked.tmp").write_text("simulated Windows residue\n", encoding="utf-8")
        return result

    original_residue_cleanup = controller._delete_managed_worktree_residue

    def leave_pending(path: Path) -> dict[str, Any]:
        assert not any(item.path == path.resolve() for item in git_repository.worktrees())
        return {
            "status": "pending",
            "path": str(path.resolve()),
            "attempts": task_session.WORKTREE_CLEANUP_ATTEMPTS,
            "errors": ["PermissionError: simulated Windows lock"],
        }

    monkeypatch.setattr(git_repository, "remove_worktree", remove_but_leave_residue)
    monkeypatch.setattr(controller, "_delete_managed_worktree_residue", leave_pending)

    result = controller.finish("207F")

    assert result["cleanup_performed"] is True
    assert result["cleanup_pending"] is True
    assert worktree.exists()
    assert not git_repository.ref_exists(branch)
    assert not controller.store.task_lease_path("207F").exists()
    assert controller.store.delivery_state()["owner"] is None
    finished = controller.store.read_json(controller.store.history / "task-207F.json")
    assert finished["state"] == "finished"
    assert finished["cleanup"]["cleanup_pending"] is True
    assert finished["cleanup"]["physical_cleanup"]["status"] == "pending"

    monkeypatch.setattr(controller, "_delete_managed_worktree_residue", original_residue_cleanup)
    retries = controller._retry_pending_worktree_cleanups()

    assert {"task_id": "207F", "status": "completed", "path": str(worktree.resolve())} in retries
    assert not worktree.exists()
    finished = controller.store.read_json(controller.store.history / "task-207F.json")
    assert finished["cleanup"]["cleanup_pending"] is False
    assert finished["cleanup"]["physical_cleanup"]["status"] == "completed"


def test_finish_cleans_only_delivered_task_and_preserves_next_delivery_task(
    repository: tuple[Path, Any],
) -> None:
    root, _, controller, _, branch, sha_pair = _prepare_started(
        repository, "209", concurrency="independent-write"
    )
    base_sha, head_sha = sha_pair.split(":")
    controller.mark_ready("209", head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")

    _write_task(root, "210", "queue-b", concurrency="independent-write")
    second = controller.start("210", owner_launch=True, session_label="queue-b", offline=True)
    second_worktree = Path(second["lease"]["worktree"])
    second_branch = str(second["lease"]["branch"])
    second_head = _commit_task(second_worktree, "210")
    controller.mark_ready("210", head_sha=second_head, quality_verdict="PASS", qa_verdict="PASS")

    _prepare_delivery(controller, "209", branch=branch)
    _git(root, "merge", "--no-ff", branch, "-m", "Merge task 209")
    merge_sha = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "origin", "master")
    github = controller.github
    assert isinstance(github, FakeGitHub)
    github.master_sha = merge_sha
    github.pulls[209] = _task_pr(209, "209", base_sha, head_sha, merge_sha=merge_sha)
    github.commits[209] = [_task_commit("209")]
    github.files[209] = [{"filename": "change.txt"}]
    github.checks[head_sha] = [_success_check(head_sha)]
    github.successful_deployments.add((merge_sha, "production"))
    controller.record_production_success(
        "209", pr_number=209, merge_sha=merge_sha, deployed_sha=merge_sha
    )
    assert controller.store.delivery_state()["owner"]["task_id"] == "209"

    controller.finish("209")

    assert not (root / ".artifacts" / "worktrees" / branch.removeprefix("task/")).exists()
    assert second_worktree.exists()
    assert controller.store.task_lease_path("210").exists()
    assert controller.store.delivery_state()["owner"]["task_id"] == "210"
    assert controller.store.read_json(controller.store.task_lease_path("210"))["branch"] == (
        second_branch
    )


def test_finish_refuses_dirty_worktree_and_preserves_state(repository: tuple[Path, Any]) -> None:
    root, git_repository, controller, worktree, branch, sha_pair = _prepare_started(
        repository, "208"
    )
    base_sha, head_sha = sha_pair.split(":")
    controller.mark_ready("208", head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS")
    _prepare_delivery(controller, "208", branch=branch)
    _git(root, "merge", "--no-ff", branch, "-m", "Merge task 208")
    merge_sha = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "origin", "master")
    github = controller.github
    assert isinstance(github, FakeGitHub)
    github.master_sha = merge_sha
    github.successful_deployments.add((merge_sha, "production"))
    github.pulls[208] = _task_pr(208, "208", base_sha, head_sha, merge_sha=merge_sha)
    github.commits[208] = [_task_commit("208")]
    github.files[208] = [{"filename": "change.txt"}]
    github.checks[head_sha] = [_success_check(head_sha)]
    controller.record_production_success(
        "208", pr_number=208, merge_sha=merge_sha, deployed_sha=merge_sha
    )
    (worktree / "uncommitted.txt").write_text("preserve\n", encoding="utf-8")

    with pytest.raises(task_session.TaskSessionError, match="refuses dirty task worktree"):
        controller.finish("208")

    assert worktree.exists()
    assert git_repository.ref_exists(branch)
    assert controller.store.task_lease_path("208").exists()


@pytest.mark.parametrize("quality", ["FAIL", "APPROVED", "", "UNKNOWN"])
def test_readiness_rejects_nonpassing_deterministic_checks(quality: str) -> None:
    controller = task_session.TaskController(task_session.GitRepository(Path.cwd()))
    with pytest.raises(task_session.TaskSessionError, match="deterministic quality checks PASS"):
        controller.mark_ready("152", head_sha="unused", quality_verdict=quality, qa_verdict="PASS")


def test_readiness_cli_defaults_to_no_qa_when_task_does_not_declare_it() -> None:
    args = task_session._parser().parse_args(
        [
            "mark-ready",
            "152",
            "--head-sha",
            "exact-sha",
            "--quality-verdict",
            "PASS",
        ]
    )
    assert args.quality_verdict == "PASS"
    assert args.qa_verdict == "NOT_REQUIRED"
    assert not hasattr(args, "review_verdict")


def test_readiness_without_reviewer_records_only_local_verdicts(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    _write_task(root, "252", "quality-only")
    controller = task_session.TaskController(git_repository)
    started = controller.start("252", owner_launch=True, session_label="quality", offline=True)
    head = _commit_task(Path(started["lease"]["worktree"]), "252")
    with pytest.raises(task_session.TaskSessionError, match="declared ready SHA"):
        controller.mark_ready("252", head_sha="stale", quality_verdict="PASS", qa_verdict="PASS")
    ready = controller.mark_ready("252", head_sha=head, quality_verdict="PASS", qa_verdict="PASS")
    assert ready["quality_verdict"] == "PASS"
    assert "review_verdict" not in ready
    assert "local_evidence" not in ready


def test_readiness_after_rebase_validates_only_task_commits(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    _write_task(root, "254", "rebased-quality-only")
    controller = task_session.TaskController(git_repository)
    started = controller.start("254", owner_launch=True, session_label="rebased", offline=True)
    worktree = Path(started["lease"]["worktree"])
    _commit_task(worktree, "254")

    remote_worktree = root.parent / f"remote-master-{uuid.uuid4().hex[:8]}"
    old_master = _git(root, "rev-parse", "master")
    _git(root, "worktree", "add", "--detach", str(remote_worktree), old_master)
    try:
        (remote_worktree / "task-150-base.txt").write_text("inherited\n", encoding="utf-8")
        _git(remote_worktree, "add", "task-150-base.txt")
        _git(remote_worktree, "commit", "-m", "[Task 150] inherited base change")
        current_base = _git(remote_worktree, "rev-parse", "HEAD")
        _git(remote_worktree, "push", "origin", "HEAD:master")
    finally:
        _git(root, "worktree", "remove", "--force", str(remote_worktree))
    _git(root, "fetch", "origin", "master")
    assert current_base == _git(root, "rev-parse", "origin/master")
    _git(worktree, "rebase", "origin/master")
    head = _git(worktree, "rev-parse", "HEAD")

    ready = controller.mark_ready("254", head_sha=head, quality_verdict="PASS")

    assert ready["base_origin_master_sha"] != current_base
    assert ready["ready_head_sha"] == head


def test_readiness_allows_task_without_qa_role(repository: tuple[Path, Any]) -> None:
    root, git_repository = repository
    _write_task(root, "253", "quality-only-no-qa")
    controller = task_session.TaskController(git_repository)
    started = controller.start("253", owner_launch=True, session_label="quality-only", offline=True)
    worktree = Path(started["lease"]["worktree"])
    head = _commit_task(worktree, "253")

    ready = controller.mark_ready("253", head_sha=head, quality_verdict="PASS")

    assert ready["quality_verdict"] == "PASS"
    assert ready["qa_verdict"] == "NOT_REQUIRED"


def test_new_lease_preserves_exact_resolved_dependencies(repository: tuple[Path, Any]) -> None:
    root, git_repository = repository
    _write_task(root, "583A", "dependency-propagation", dependencies="507, 508")
    done = root / "codex-backlog" / "tasks" / "done"
    done.mkdir(parents=True, exist_ok=True)
    (done / "507-terminal.md").write_text("done\n", encoding="utf-8")
    (done / "508-terminal.md").write_text("done\n", encoding="utf-8")
    controller = task_session.TaskController(git_repository)

    started = controller.start(
        "583A",
        owner_launch=True,
        session_label="dependency-propagation",
        offline=True,
        dependency_ids=["507", "508"],
    )

    assert started["lease"]["dependency_ids"] == ["507", "508"]
    persisted = controller.store.read_json(controller.store.task_lease_path("583A"))
    assert persisted["dependency_ids"] == ["507", "508"]
    assert persisted["lifecycle_state"] == task_session.WORKING_STATE


def test_generic_worker_retry_records_bounded_attempt_and_uses_legacy_evidence(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, _, _, _, _ = _prepare_verified_noop_retry_fixture(repository)

    result = controller.retry_worker(
        "508",
        control_issue_number=508,
        reason="owner-authorized generic retry after a clean no-op worker attempt",
        owner_authorize=True,
    )

    assert result["retry_kind"] == "no_changes"
    lease = controller.store.read_json(controller.store.task_lease_path("508"))
    assert lease["lifecycle_state"] == task_session.WORKING_STATE
    assert lease["attempts"][0]["result"] == "no_changes"
    assert lease["attempts"][0]["evidence"]["mechanism"] == "generic-worker-retry"
    with pytest.raises(task_session.TaskSessionError, match="retry budget"):
        controller.retry_worker(
            "508",
            control_issue_number=508,
            reason="second generic retry",
            owner_authorize=True,
        )


def test_generic_worker_retry_resumes_preserved_wip(repository: tuple[Path, Any]) -> None:
    root, git_repository, controller, worktree, branch, _, github = (
        _prepare_preimplementation_resume(repository)
    )
    worker_state_path, _guard_path, _events_path, _attempt_id = _record_guard_budget_failure(
        controller, root, github, branch, worktree
    )

    result = controller.retry_worker(
        "241",
        control_issue_number=241,
        reason="owner-authorized generic retry after a bounded guard interruption",
        owner_authorize=True,
    )

    assert result["retry_kind"] == "interrupted"
    assert result["preimplementation_resume"]["state"] == "prepared"
    assert result["lease"]["lifecycle_state"] == task_session.WORKING_STATE
    assert result["lease"]["attempts"][0]["result"] == "interrupted"
    assert not worker_state_path.exists()
    assert (
        git_repository.head(cwd=worktree)
        == result["preimplementation_resume"]["guard_budget_recovery"]["base_sha"]
    )


def test_legacy_lifecycle_is_read_as_working_without_history_rewrite(
    repository: tuple[Path, Any],
) -> None:
    _, _, controller, _, _, _ = _prepare_started(repository, "583B")
    lease_path = controller.store.task_lease_path("583B")
    lease = controller.store.read_json(lease_path)
    lease["lifecycle_state"] = "implementation"
    task_session.StateStore.replace_json(lease_path, lease)

    snapshot = controller.status()["leases"][0]

    assert snapshot["lifecycle_state"] == task_session.WORKING_STATE
    assert snapshot["raw_lifecycle_state"] == "implementation"
    assert snapshot["derived_lifecycle_state"] == task_session.WORKING_STATE
    assert controller.store.read_json(lease_path)["lifecycle_state"] == "implementation"


def test_maintenance_cleanup_removes_only_clean_merged_unleased_worktrees(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    controller = task_session.TaskController(git_repository)

    managed = root / ".artifacts" / "worktrees"
    merged = managed / "900-merged-clean"
    stale = managed / "512-product-v5-exercise-history-pr-analytics-stale"
    dirty = managed / "901-dirty-merged"

    _git(root, "worktree", "add", "-b", "task/900-merged-clean", str(merged), "origin/master")
    _git(root, "worktree", "add", "-b", "task/512-stale", str(stale), "origin/master")
    _git(root, "worktree", "add", "-b", "task/901-dirty-merged", str(dirty), "origin/master")
    (dirty / "untracked.txt").write_text("keep\n", encoding="utf-8")

    result = controller.maintenance_cleanup()
    statuses = {Path(item["path"]).name: item["status"] for item in result["merged_worktrees"]}

    assert statuses["900-merged-clean"] == "removed"
    assert statuses["512-product-v5-exercise-history-pr-analytics-stale"] == "preserved"
    assert statuses["901-dirty-merged"] == "preserved-dirty"
    assert not merged.exists()
    assert stale.exists()
    assert dirty.exists()
    assert all(item.path != merged.resolve() for item in git_repository.worktrees())


@pytest.mark.parametrize(
    "owner_gate",
    ("owner_visual_acceptance", "behavior_contract", "privacy_and_sharing_contract"),
)
def test_yellow_owner_gates_allow_implementation_start(
    repository: tuple[Path, Any], owner_gate: str
) -> None:
    root, git_repository = repository
    _write_task(root, "239B", "yellow-gate", owner_gate=owner_gate)
    controller = task_session.TaskController(git_repository)

    started = controller.start("239B", owner_launch=True, session_label="yellow-gate", offline=True)

    assert started["lease"]["task_id"] == "239B"
    assert started["lease"]["lifecycle_state"] == task_session.WORKING_STATE


def test_yellow_owner_gate_allows_adopt_current(
    repository: tuple[Path, Any],
) -> None:
    root, _ = repository
    _write_task(root, "239C", "visual-adopt", owner_gate="owner_visual_acceptance")
    adopted_path = root / ".artifacts" / "worktrees" / "visual-adopt-239C"
    _git(
        root,
        "worktree",
        "add",
        "-b",
        "task/239C-visual-adopt",
        str(adopted_path),
        "origin/master",
    )
    controller = task_session.TaskController(task_session.GitRepository(adopted_path))

    lease = controller.adopt_current(
        "239C", owner_launch=True, session_label="visual-adopt", offline=True
    )

    assert lease["task_id"] == "239C"
    assert lease["lifecycle_state"] == task_session.WORKING_STATE


def test_start_reuses_exact_pristine_working_lease(repository: tuple[Path, Any]) -> None:
    root, git_repository = repository
    _write_task(root, "638A", "pristine-reuse", concurrency="independent-write")
    controller = task_session.TaskController(
        git_repository,
        github=FakeGitHub(git_repository.ref("origin/master")),
    )

    first = controller.start(
        "638A",
        owner_launch=True,
        session_label="pristine-reuse",
        offline=True,
    )
    second = controller.start(
        "638A",
        owner_launch=True,
        session_label="pristine-reuse",
        offline=True,
    )

    assert second["reused_existing_lease"] is True
    assert second["lease"] == first["lease"]
    matching_leases = [
        lease for lease in controller.store.all_leases() if lease.get("task_id") == "638A"
    ]
    assert len(matching_leases) == 1
    branch = first["lease"]["branch"]
    worktree = Path(first["lease"]["worktree"]).resolve()
    registrations = [
        item
        for item in git_repository.worktrees()
        if item.branch == branch or item.path == worktree
    ]
    assert len(registrations) == 1
    assert registrations[0].branch == branch
    assert registrations[0].path == worktree


def test_start_refuses_pristine_reuse_after_worker_attempt_evidence(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    _write_task(root, "638B", "attempt-evidence", concurrency="independent-write")
    controller = task_session.TaskController(
        git_repository,
        github=FakeGitHub(git_repository.ref("origin/master")),
    )
    controller.start(
        "638B",
        owner_launch=True,
        session_label="attempt-evidence",
        offline=True,
    )
    lease_path = controller.store.task_lease_path("638B")
    lease = controller.store.read_json(lease_path)
    assert isinstance(lease, dict)
    lease["attempts"] = [
        {
            "attempt": 1,
            "started_at": "2026-10-02T00:00:00Z",
            "ended_at": "2026-10-02T00:00:01Z",
            "result": "interrupted",
            "reason": "synthetic worker evidence",
        }
    ]
    task_session.StateStore.replace_json(lease_path, lease)

    with pytest.raises(task_session.TaskSessionError, match="worker/retry evidence"):
        controller.start(
            "638B",
            owner_launch=True,
            session_label="attempt-evidence",
            offline=True,
        )


def test_start_refuses_pristine_reuse_for_dirty_worktree(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    _write_task(root, "638C", "dirty-reuse", concurrency="independent-write")
    controller = task_session.TaskController(
        git_repository,
        github=FakeGitHub(git_repository.ref("origin/master")),
    )
    started = controller.start(
        "638C",
        owner_launch=True,
        session_label="dirty-reuse",
        offline=True,
    )
    worktree = Path(started["lease"]["worktree"])
    (worktree / "untracked.txt").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(task_session.TaskSessionError, match="Ambiguous existing branch/worktree"):
        controller.start(
            "638C",
            owner_launch=True,
            session_label="dirty-reuse",
            offline=True,
        )


def test_start_refuses_pristine_reuse_after_task_contract_drift(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository = repository
    _write_task(root, "638D", "contract-drift", concurrency="independent-write")
    controller = task_session.TaskController(
        git_repository,
        github=FakeGitHub(git_repository.ref("origin/master")),
    )
    controller.start(
        "638D",
        owner_launch=True,
        session_label="contract-drift",
        offline=True,
    )
    _write_task(root, "638D", "contract-drift", concurrency="exclusive-write")

    with pytest.raises(
        task_session.TaskSessionError, match="does not match the requested task contract"
    ):
        controller.start(
            "638D",
            owner_launch=True,
            session_label="contract-drift",
            offline=True,
        )


def _record_direct_guard_budget_failure(
    root: Path,
    worktree: Path,
    *,
    attempt_id: str | None = None,
) -> tuple[Path, Path, str]:
    attempt_id = attempt_id or (datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-delivery")
    attempt_root = root / ".artifacts" / "tasks" / "241" / "temporary" / "delivery" / attempt_id
    attempt_root.mkdir(parents=True)
    (worktree / "README.md").write_text("direct guarded implementation\n", encoding="utf-8")
    (worktree / "direct-module.py").write_text("value = 640\n", encoding="utf-8")
    events_path = attempt_root / "events.jsonl"
    limits = {
        "max_completed_tool_actions": 240,
        "max_collab_tool_calls": 10,
        "max_spawned_subagents": 2,
        "max_concurrent_subagents": 2,
        "max_identical_failed_actions": 4,
        "max_identical_actions_without_progress": 8,
        "short_cycle_period_max": 3,
        "short_cycle_repetitions": 4,
    }
    file_change_events = [
        {
            "type": "item.completed",
            "item": {
                "type": "file_change",
                "changes": [{"path": str(worktree / relative_path), "kind": "update"}],
                "status": "completed",
            },
        }
        for relative_path in ("README.md", "direct-module.py")
    ]
    command_events = [
        {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "command": f"direct-guard-action-{action_number}",
                "status": "completed",
            },
        }
        for action_number in range(1, 242)
    ]
    events = "".join(
        json.dumps(payload) + "\n" for payload in (*file_change_events, *command_events)
    )
    events_path.write_text(events, encoding="utf-8")
    guard = task_session.WorkerEventGuard(task_session.GuardLimits.from_mapping(limits))
    for line in events.splitlines(keepends=True):
        guard.observe_line(line)
    guard_path = attempt_root / "worker-guard.json"
    guard_path.write_text(json.dumps(guard.report()), encoding="utf-8")
    return guard_path, events_path, attempt_id


def test_direct_guard_interrupted_resume_recovers_without_legacy_launch_audit(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository, controller, worktree, _, _, github = _prepare_preimplementation_resume(
        repository
    )
    github.issue_comment_map[241] = []
    guard_path, events_path, attempt_id = _record_direct_guard_budget_failure(root, worktree)
    before_head = git_repository.head(cwd=worktree)
    before_status = git_repository.status(worktree)

    resumed = controller.resume_guard_interrupted(
        "241",
        control_issue_number=241,
        reason="owner-authorized direct guard recovery",
        owner_authorize=True,
    )

    event = resumed["preimplementation_resume"]
    checkpoint = event["guard_budget_recovery"]
    assert resumed["mutation_performed"] is True
    assert resumed["control_state"] == {}
    assert event["classification"] == task_session.DIRECT_GUARD_RECOVERY_CLASSIFICATION
    assert event["state"] == "prepared"
    assert event["launch_attempts"] == []
    assert checkpoint["attempt_id"] == attempt_id
    assert checkpoint["guard_report_path"] == str(guard_path.resolve())
    assert checkpoint["events_path"] == str(events_path.resolve())
    assert set(checkpoint["changed_paths"]) == {"README.md", "direct-module.py"}
    assert git_repository.head(cwd=worktree) == before_head
    assert git_repository.status(worktree) == before_status

    repeated = controller.resume_guard_interrupted(
        "241",
        control_issue_number=241,
        reason="owner-authorized direct guard recovery",
        owner_authorize=True,
    )
    assert repeated["mutation_performed"] is False
    assert repeated["control_state"] == {}
    assert repeated["preimplementation_resume"]["guard_budget_recovery"] == checkpoint
    assert git_repository.head(cwd=worktree) == before_head
    assert git_repository.status(worktree) == before_status

    github.issue_comment_map[241].append(
        {
            "id": 4,
            "created_at": task_session.utc_now(),
            "user": {"login": "owner"},
            "body": render_control_state_comment(
                control_state_payload(
                    task_id="241",
                    state="human_required",
                    issue_number=241,
                    branch=controller.store.read_json(controller.store.task_lease_path("241"))[
                        "branch"
                    ],
                    blocker=task_session.GUARD_RECOVERY_HANDOFF_BLOCKER,
                )
            ),
        }
    )
    claimed = controller.claim_preimplementation_worker_launch("241")
    assert claimed["preimplementation_resume"]["state"] == "launching"


def test_direct_guard_interrupted_resume_refuses_ambiguous_blocked_attempts(
    repository: tuple[Path, Any],
) -> None:
    root, _, controller, worktree, _, _, github = _prepare_preimplementation_resume(repository)
    github.issue_comment_map[241] = []
    _record_direct_guard_budget_failure(root, worktree)
    _record_direct_guard_budget_failure(root, worktree)

    with pytest.raises(task_session.TaskSessionError, match="ambiguous direct guard"):
        controller.resume_guard_interrupted(
            "241",
            control_issue_number=241,
            reason="owner-authorized direct guard recovery",
            owner_authorize=True,
        )
