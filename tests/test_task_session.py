from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

import pytest


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
        self.pulls: dict[int, dict[str, Any]] = {}
        self.commits: dict[int, list[dict[str, Any]]] = {}
        self.files: dict[int, list[dict[str, Any]]] = {}
        self.reviews: dict[int, list[dict[str, Any]]] = {}
        self.comments: dict[int, list[dict[str, Any]]] = {}
        self.threads: dict[int, list[dict[str, Any]]] = {}
        self.checks: dict[str, list[dict[str, Any]]] = {}
        self.open_prs: list[dict[str, Any]] = []
        self.active_runs: list[dict[str, Any]] = []
        self.ruleset_payload: list[dict[str, Any]] = []
        self.successful_deployments: set[tuple[str, str]] = set()
        self.associated_pulls: list[dict[str, Any]] = []
        self.created_comments: list[tuple[int, str]] = []
        self.next_comment_id = 1000

    def api(self, endpoint: str) -> Any:
        if endpoint.startswith("commits/") and endpoint.endswith("/pulls"):
            return self.associated_pulls
        raise AssertionError(f"Unexpected fake GitHub API endpoint: {endpoint}")

    def open_pull_requests(self) -> list[dict[str, Any]]:
        return self.open_prs

    def pull_request(self, number: int) -> dict[str, Any]:
        return self.pulls[number]

    def pull_request_commits(self, number: int) -> list[dict[str, Any]]:
        return self.commits[number]

    def pull_request_files(self, number: int) -> list[dict[str, Any]]:
        return self.files.get(number, [{"filename": "README.md"}])

    def pull_request_reviews(self, number: int) -> list[dict[str, Any]]:
        if number in self.reviews:
            return self.reviews[number]
        head_sha = str(self.pulls[number].get("head", {}).get("sha", ""))
        return [{"state": "APPROVED", "commit_id": head_sha, "user": {"login": "pytest"}}]

    def issue_comments(self, number: int) -> list[dict[str, Any]]:
        return self.comments.get(number, [])

    def create_issue_comment(self, number: int, body: str) -> dict[str, Any]:
        self.next_comment_id += 1
        comment = {
            "id": self.next_comment_id,
            "user": {"login": "pytest"},
            "body": body,
            "created_at": "2026-09-12T10:00:00Z",
        }
        self.created_comments.append((number, body))
        self.comments.setdefault(number, []).append(comment)
        return comment

    def review_threads(self, number: int) -> list[dict[str, Any]]:
        return self.threads.get(number, [])

    def check_runs(self, sha: str) -> list[dict[str, Any]]:
        return self.checks.get(sha, [])

    def branch_head(self, branch: str) -> str:
        if branch != "master":
            raise AssertionError(f"Unexpected branch lookup: {branch}")
        return self.master_sha

    def has_successful_deployment(self, sha: str, environment: str) -> bool:
        return (sha, environment) in self.successful_deployments

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


def _prepare_delivery(controller: Any, task_id: str, *, branch: str) -> dict[str, Any]:
    del branch
    acquired = controller.acquire_delivery(task_id)
    assert acquired["acquired"] is True
    controller.refresh_for_delivery(task_id)
    return controller.validate_delivery(task_id)


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


def _review_pr(head_sha: str) -> dict[str, Any]:
    pull_request = _task_pr(219, "219", "a" * 40, head_sha)
    pull_request.update({"state": "open", "mergeable": True, "mergeable_state": "clean"})
    return pull_request


def test_review_contract_rejects_pending_review_for_current_head() -> None:
    with pytest.raises(task_session.TaskSessionError, match="no completed approval"):
        task_session.validate_pull_request_review_contract(_review_pr("b" * 40), [], [], [])


def test_review_contract_rejects_old_codex_review_marker() -> None:
    pull_request = _review_pr("b" * 40)
    comments = [
        {
            "user": {"login": "chatgpt-codex-connector"},
            "body": "Codex Review: **Reviewed commit:** `aaaaaaa`",
        }
    ]
    with pytest.raises(task_session.TaskSessionError, match="stale review markers"):
        task_session.validate_pull_request_review_contract(pull_request, [], comments, [])


def test_review_contract_rejects_current_blocking_finding() -> None:
    head_sha = "b" * 40
    reviews = [
        {
            "id": 1,
            "state": "CHANGES_REQUESTED",
            "commit_id": head_sha,
            "body": "P1 functional defect",
        }
    ]
    with pytest.raises(task_session.TaskSessionError, match="blocking current-head"):
        task_session.validate_pull_request_review_contract(_review_pr(head_sha), reviews, [], [])


def test_review_contract_uses_latest_state_changing_review_for_each_reviewer() -> None:
    head_sha = "b" * 40
    reviews = [
        {
            "id": 1,
            "state": "CHANGES_REQUESTED",
            "commit_id": head_sha,
            "submitted_at": "2026-09-09T01:00:00Z",
            "user": {"login": "reviewer"},
            "body": "P1 old finding",
        },
        {
            "id": 2,
            "state": "APPROVED",
            "commit_id": head_sha,
            "submitted_at": "2026-09-09T02:00:00Z",
            "user": {"login": "reviewer"},
        },
    ]

    result = task_session.validate_pull_request_review_contract(
        _review_pr(head_sha), reviews, [], []
    )

    assert result["status"] == "PASS"
    assert result["formal_approval_count"] == 1


def test_review_contract_rejects_unresolved_thread_even_with_exact_approval() -> None:
    head_sha = "b" * 40
    reviews = [{"state": "APPROVED", "commit_id": head_sha, "user": {"login": "owner"}}]
    with pytest.raises(task_session.TaskSessionError, match="unresolved review threads"):
        task_session.validate_pull_request_review_contract(
            _review_pr(head_sha), reviews, [], [{"isResolved": False}]
        )


def test_review_contract_accepts_exact_codex_comment_and_resolved_threads() -> None:
    head_sha = "b" * 40
    comments = [
        {
            "id": 12,
            "user": {"login": "chatgpt-codex-connector[bot]"},
            "body": (
                "Codex Review: Didn't find any major issues. "
                f"**Reviewed commit:** `{head_sha[:10]}`"
            ),
        },
        {
            "id": 13,
            "user": {"login": "codereviewbot-ai"},
            "body": "Review skipped: Repository Owner rate limit exceeded",
        },
    ]
    result = task_session.validate_pull_request_review_contract(
        _review_pr(head_sha),
        [],
        comments,
        [{"isResolved": True}],
        known_commit_shas=(head_sha,),
    )
    assert result["status"] == "PASS"
    assert result["sources"] == ["codex-completed-review-comment"]
    assert result["head_sha"] == head_sha


def test_review_contract_rejects_ambiguous_abbreviated_codex_marker() -> None:
    head_sha = "abcdef0" + "1" * 33
    other_sha = "abcdef0" + "2" * 33
    comments = [
        {
            "id": 14,
            "user": {"login": "chatgpt-codex-connector[bot]"},
            "body": (
                f"Codex Review: Didn't find any major issues. **Reviewed commit:** `{head_sha[:7]}`"
            ),
        }
    ]

    with pytest.raises(task_session.TaskSessionError, match="stale review markers"):
        task_session.validate_pull_request_review_contract(
            _review_pr(head_sha),
            [],
            comments,
            [],
            known_commit_shas=(head_sha, other_sha),
        )


def test_review_contract_rejects_exact_codex_summary_without_approval() -> None:
    head_sha = "b" * 40
    comments = [
        {
            "id": 15,
            "user": {"login": "chatgpt-codex-connector[bot]"},
            "body": (
                "Codex Review Summary: Completed. **Reviewed commit:** "
                f"`{head_sha[:10]}`\n\nP1 blocking finding"
            ),
        }
    ]

    with pytest.raises(task_session.TaskSessionError, match="explicit approving verdict"):
        task_session.validate_pull_request_review_contract(
            _review_pr(head_sha), [], comments, [], known_commit_shas=(head_sha,)
        )


def test_review_contract_uses_latest_exact_head_codex_verdict() -> None:
    head_sha = "b" * 40
    comments = [
        {
            "id": 16,
            "user": {"login": "chatgpt-codex-connector[bot]"},
            "created_at": "2026-09-09T05:00:00Z",
            "updated_at": "2026-09-09T05:00:00Z",
            "body": (
                "Codex Review: Didn't find any major issues. "
                f"**Reviewed commit:** `{head_sha[:10]}`"
            ),
        },
        {
            "id": 17,
            "user": {"login": "chatgpt-codex-connector[bot]"},
            "created_at": "2026-09-09T06:00:00Z",
            "updated_at": "2026-09-09T06:00:00Z",
            "body": (
                "Codex Review Summary: Completed. **Reviewed commit:** "
                f"`{head_sha[:10]}`\n\nP1 blocking finding"
            ),
        },
    ]

    with pytest.raises(task_session.TaskSessionError, match="explicit approving verdict"):
        task_session.validate_pull_request_review_contract(
            _review_pr(head_sha), [], comments, [], known_commit_shas=(head_sha,)
        )


def test_review_contract_negative_codex_verdict_vetoes_formal_approval() -> None:
    head_sha = "b" * 40
    reviews = [
        {
            "id": 18,
            "state": "APPROVED",
            "commit_id": head_sha,
            "user": {"login": "owner"},
        }
    ]
    comments = [
        {
            "id": 19,
            "user": {"login": "chatgpt-codex-connector[bot]"},
            "created_at": "2026-09-09T07:00:00Z",
            "body": (
                "Codex Review Summary: Completed. P1 blocking finding. "
                f"**Reviewed commit:** `{head_sha[:10]}`"
            ),
        }
    ]

    with pytest.raises(task_session.TaskSessionError, match="blocking exact-head Codex verdict"):
        task_session.validate_pull_request_review_contract(
            _review_pr(head_sha), reviews, comments, [], known_commit_shas=(head_sha,)
        )


@pytest.mark.parametrize("mergeable_state", ["blocked", "unstable"])
def test_review_event_accepts_exact_review_before_aggregate_check_is_green(
    mergeable_state: str,
) -> None:
    head_sha = "b" * 40
    pull_request = _review_pr(head_sha)
    pull_request["mergeable_state"] = mergeable_state
    comments = [
        {
            "id": 14,
            "user": {"login": "chatgpt-codex-connector[bot]"},
            "body": (
                "Codex Review: Didn't find any major issues. review status completed; "
                f"**Reviewed commit:** `{head_sha[:10]}`"
            ),
        }
    ]

    with pytest.raises(task_session.TaskSessionError, match="clean mergeable"):
        task_session.validate_pull_request_review_contract(pull_request, [], comments, [])

    result = task_session.validate_pull_request_review_contract(
        pull_request,
        [],
        comments,
        [],
        known_commit_shas=(head_sha,),
        allow_blocked_mergeable_state=True,
    )
    assert result["status"] == "PASS"
    assert result["head_sha"] == head_sha


def test_review_event_polls_transient_mergeability_before_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_sha = "a" * 40
    head_sha = "b" * 40
    pull_request = _review_pr(head_sha)
    github = FakeGitHub(base_sha)
    github.pulls[219] = pull_request
    github.commits[219] = []
    responses = [
        {**pull_request, "mergeable": None, "mergeable_state": None},
        {**pull_request, "mergeable": None, "mergeable_state": None},
        pull_request,
    ]
    fetches: list[int] = []

    def fetch(number: int) -> dict[str, Any]:
        fetches.append(number)
        return responses.pop(0)

    monkeypatch.setattr(github, "pull_request", fetch)
    current_time = [0.0]
    waits: list[float] = []

    def monotonic() -> float:
        return current_time[0]

    def sleep(seconds: float) -> None:
        waits.append(seconds)
        current_time[0] += seconds

    monkeypatch.setattr(task_session.time, "monotonic", monotonic)
    monkeypatch.setattr(task_session.time, "sleep", sleep)
    event_path = tmp_path / "review-event.json"
    event_path.write_text(json.dumps({"pull_request": pull_request}), encoding="utf-8")

    result = task_session.validate_pr_review_event(github, event_path)  # type: ignore[arg-type]

    assert result["status"] == "PASS"
    assert fetches == [219, 219, 219]
    assert waits == [1.0, 1.0]


def _codex_review_fixture(repository: tuple[Path, Any]) -> tuple[Any, Any, str, str]:
    _, git_repository = repository
    base_sha = git_repository.ref("origin/master")
    head_sha = "b" * 40
    github = FakeGitHub(base_sha)
    pull_request = _review_pr(head_sha)
    pull_request["base"]["sha"] = base_sha
    github.pulls[219] = pull_request
    github.commits[219] = [{"sha": head_sha}]
    github.checks[head_sha] = [_success_check(head_sha)]
    controller = task_session.TaskController(git_repository, github=github)
    return controller, github, base_sha, head_sha


def _append_codex_result(
    github: FakeGitHub,
    *,
    head_sha: str,
    body: str,
    comment_id: int = 50,
) -> None:
    github.comments.setdefault(219, []).append(
        {
            "id": comment_id,
            "user": {"login": "chatgpt-codex-connector[bot]"},
            "created_at": f"2026-09-12T10:00:{comment_id:02d}Z",
            "body": f"Codex Review Summary\nReviewed commit: `{head_sha}`\n{body}",
        }
    )


def test_codex_review_refuses_non_green_exact_head_ci(
    repository: tuple[Path, Any],
) -> None:
    controller, github, _, head_sha = _codex_review_fixture(repository)
    github.checks[head_sha] = [{**_success_check("c" * 40)}]

    with pytest.raises(task_session.TaskSessionError, match="exact-head required check"):
        controller.request_codex_review(pr_number=219, head_sha=head_sha, round_number=1)

    assert github.created_comments == []


def test_codex_review_reuses_one_request_for_the_same_sha(
    repository: tuple[Path, Any],
) -> None:
    controller, github, _, head_sha = _codex_review_fixture(repository)

    first = controller.request_codex_review(pr_number=219, head_sha=head_sha, round_number=1)
    second = controller.request_codex_review(pr_number=219, head_sha=head_sha, round_number=1)

    assert first["status"] == "REQUESTED"
    assert second["status"] == "PENDING"
    assert second["reused"] is True
    assert len(github.created_comments) == 1
    assert f"head={head_sha}" in github.created_comments[0][1]


def test_codex_clean_round_one_allows_merge_without_rereview(
    repository: tuple[Path, Any],
) -> None:
    controller, github, _, head_sha = _codex_review_fixture(repository)
    controller.request_codex_review(pr_number=219, head_sha=head_sha, round_number=1)
    _append_codex_result(
        github, head_sha=head_sha, body="review status completed; no blocking findings"
    )

    result = controller.validate_codex_review(pr_number=219, head_sha=head_sha)
    reused = controller.request_codex_review(pr_number=219, head_sha=head_sha, round_number=1)

    assert result["status"] == "CLEAN"
    assert result["merge_allowed"] is True
    assert reused["status"] == "CLEAN"
    assert len(github.created_comments) == 1
    with pytest.raises(task_session.TaskSessionError, match="requires a blocking P0/P1"):
        controller.request_codex_review(pr_number=219, head_sha=head_sha, round_number=2)


def test_codex_medium_finding_does_not_open_a_second_round(
    repository: tuple[Path, Any],
) -> None:
    controller, github, _, head_sha = _codex_review_fixture(repository)
    controller.request_codex_review(pr_number=219, head_sha=head_sha, round_number=1)
    _append_codex_result(github, head_sha=head_sha, body="review completed; P2 medium finding")

    result = controller.validate_codex_review(pr_number=219, head_sha=head_sha)

    assert result["status"] == "CLEAN"
    assert result["review_budget"] == {"used": 1, "max": 2, "remaining": 1}
    with pytest.raises(task_session.TaskSessionError, match="requires a blocking P0/P1"):
        controller.request_codex_review(pr_number=219, head_sha=head_sha, round_number=2)


def test_codex_round_two_requires_changed_head_and_ends_human_required(
    repository: tuple[Path, Any],
) -> None:
    controller, github, _, first_head = _codex_review_fixture(repository)
    controller.request_codex_review(pr_number=219, head_sha=first_head, round_number=1)
    _append_codex_result(github, head_sha=first_head, body="review completed; P1 blocking defect")
    first_result = controller.validate_codex_review(pr_number=219, head_sha=first_head)
    assert first_result["status"] == "BLOCKING_P0_P1"

    second_head = "c" * 40
    github.pulls[219]["head"]["sha"] = second_head
    github.commits[219] = [{"sha": second_head}]
    github.checks[second_head] = [_success_check(second_head)]
    second_request = controller.request_codex_review(
        pr_number=219, head_sha=second_head, round_number=2
    )
    _append_codex_result(
        github, head_sha=second_head, body="review completed; P1 blocking regression", comment_id=51
    )
    second_result = controller.validate_codex_review(pr_number=219, head_sha=second_head)
    repeated = controller.request_codex_review(pr_number=219, head_sha=second_head, round_number=2)

    assert second_request["status"] == "REQUESTED"
    assert second_result["status"] == "HUMAN_REQUIRED"
    assert "P1" in second_result["blocker_report"]
    assert repeated["status"] == "HUMAN_REQUIRED"
    assert len(github.created_comments) == 2
    with pytest.raises(task_session.TaskSessionError, match="must be 1 or 2"):
        controller.request_codex_review(pr_number=219, head_sha=second_head, round_number=3)


def test_codex_review_rejects_unresolved_thread_before_request(
    repository: tuple[Path, Any],
) -> None:
    controller, github, _, head_sha = _codex_review_fixture(repository)
    github.threads[219] = [{"isResolved": False}]

    with pytest.raises(task_session.TaskSessionError, match="unresolved review threads"):
        controller.request_codex_review(pr_number=219, head_sha=head_sha, round_number=1)

    assert github.created_comments == []


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
    assert all(item["lease"]["lifecycle_state"] == "implementation" for item in started)


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
    assert started["lease"]["lifecycle_state"] == "implementation"


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
    assert candidate["lease"]["lifecycle_state"] == "implementation"
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


def test_dirty_exclusive_task_worktree_blocks_new_writer(
    repository: tuple[Path, Any],
) -> None:
    root, _, controller, worktree, _, _ = _prepare_started(
        repository, "226H", concurrency="exclusive-write"
    )
    _write_task(root, "226I", "candidate")
    (worktree / "uncommitted.txt").write_text("preserve\n", encoding="utf-8")

    report = controller.doctor(offline=True)

    assert report["safe_for_implementation"] is False
    assert any("Task 226H worktree is dirty" in item for item in report["implementation_blockers"])
    with pytest.raises(task_session.TaskSessionError, match="implementation/start blockers"):
        controller.start("226I", owner_launch=True, session_label="candidate", offline=True)


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
    assert controller.store.read_json(controller.store.task_lease_path("231"))[
        "lifecycle_state"
    ] == ("waiting-for-delivery")

    github.active_runs = []
    acquired = controller.acquire_delivery("231")
    assert acquired["acquired"] is True
    assert acquired["lifecycle_state"] == "delivering"


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
    assert controller.store.read_json(controller.store.task_lease_path("233"))[
        "lifecycle_state"
    ] == ("waiting-for-delivery")

    released = controller.release_delivery(
        "232", reason="synthetic delivery interruption", offline=True
    )

    assert released["lifecycle_state"] == "recovery-required"
    assert controller.store.delivery_state()["owner"]["task_id"] == "233"
    assert controller.store.read_json(controller.store.task_lease_path("233"))[
        "lifecycle_state"
    ] == ("delivering")


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
        == "ready-for-delivery"
    )

    released = controller.release_delivery(
        "247", reason="synthetic priority delivery interruption", offline=True
    )

    assert released["lifecycle_state"] == "recovery-required"
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
    assert controller.store.read_json(controller.store.task_lease_path("233B"))[
        "lifecycle_state"
    ] == ("ready-for-delivery")

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

    assert reopened["lifecycle_state"] == "review"
    assert "delivery_anchor" not in reopened
    assert "delivery_head_sha" not in reopened
    assert "ready_head_sha" not in reopened
    assert controller.store.delivery_state()["owner"] is None

    new_head = _commit_task(worktree, "234A", filename="review-fix.txt")
    ready = controller.mark_ready(
        "234A", head_sha=new_head, quality_verdict="PASS", qa_verdict="PASS"
    )
    assert ready["lifecycle_state"] == "ready-for-delivery"
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

    assert resolved["lifecycle_state"] == "review"
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

    assert superseded["lifecycle_state"] == "superseded"
    assert superseded["superseded_from_state"] == "implementation"
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
    assert started["lease"]["lifecycle_state"] == "implementation"


def test_supersede_refuses_dirty_anchor_without_mutation(repository: tuple[Path, Any]) -> None:
    _, _, controller, worktree, _, _ = _prepare_started(
        repository, "234F", concurrency="exclusive-write"
    )
    (worktree / "uncommitted.txt").write_text("preserve\n", encoding="utf-8")

    with pytest.raises(task_session.TaskSessionError, match="dirty worktree"):
        controller.supersede("234F", reason="owner decision", owner_authorize=True)

    lease = controller.store.read_json(controller.store.task_lease_path("234F"))
    assert isinstance(lease, dict)
    assert lease["lifecycle_state"] == "implementation"


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
    assert lease["lifecycle_state"] == "implementation"


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
    assert second["lease"]["lifecycle_state"] == "implementation"
    assert third["lease"]["lifecycle_state"] == "implementation"


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
    assert validated["lifecycle_state"] == "delivery-gate"
    assert validated["delivery_anchor"]["head_sha"] == new_head


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
    assert lease["lifecycle_state"] == "delivering"
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
    assert lease["lifecycle_state"] == "recovery-required"
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


def test_mark_ready_records_local_verdicts_without_evidence_file(
    repository: tuple[Path, Any],
) -> None:
    root, git_repository, controller, worktree, _, sha_pair = _prepare_started(repository, "202")
    _, head_sha = sha_pair.split(":")
    ready = controller.mark_ready(
        "202", head_sha=head_sha, quality_verdict="PASS", qa_verdict="PASS"
    )
    assert ready["lifecycle_state"] == "ready-for-delivery"
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
    assert controller.store.read_json(controller.store.task_lease_path("203"))[
        "lifecycle_state"
    ] == ("production-success")


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
    assert controller.store.read_json(controller.store.task_lease_path("204"))[
        "lifecycle_state"
    ] == ("delivery-gate")


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
