"""Fail-closed task worktree, provenance and trunk-based release controller.

The normal lifecycle is deliberately small: a task branch is based on master,
runs relevant local checks, enters a PR into master, and is closed only after
the merged master revision is deployed successfully. GitHub CI is the release
quality source of truth; local checks provide fast feedback and do not create
release evidence. Coordination state lives in the shared Git common directory
and is never committed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

try:
    from scripts.artifact_manager import ArtifactError, ArtifactManager
    from scripts.issue_workflow import (
        CONTROL_STATES,
        DEFAULT_QUEUE_BUDGET,
        TASK_CONTRACT_MARKER,
        IssueWorkflowError,
        latest_control_state,
        normalize_github_login,
        parse_task_contract,
        task_risk_lane,
    )
    from scripts.worker_guard import GuardLimits, WorkerEventGuard, WorkerGuardConfigError
except ModuleNotFoundError:
    from artifact_manager import ArtifactError, ArtifactManager
    from issue_workflow import (
        CONTROL_STATES,
        DEFAULT_QUEUE_BUDGET,
        TASK_CONTRACT_MARKER,
        IssueWorkflowError,
        latest_control_state,
        normalize_github_login,
        parse_task_contract,
        task_risk_lane,
    )
    from worker_guard import GuardLimits, WorkerEventGuard, WorkerGuardConfigError

TASK_ID_PATTERN = r"[0-9]+[A-Z]?"
TASK_ID_RE = re.compile(rf"^{TASK_ID_PATTERN}$", re.IGNORECASE)
TASK_BRANCH_RE = re.compile(
    rf"^task/(?P<task_id>{TASK_ID_PATTERN})-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)$",
    re.IGNORECASE,
)
CONTROLLER_BRANCH_RE = re.compile(r"^codex/controller-[a-z0-9]+(?:-[a-z0-9]+)*$")
TASK_COMMIT_RE = re.compile(rf"\[Task (?P<task_id>{TASK_ID_PATTERN})\]", re.IGNORECASE)
CONTROLLER_COMMIT_RE = re.compile(r"^\[Controller\]\s+\S")
CONTROLLER_ALLOWED_PATHS = frozenset(
    {
        ".github/workflows/deploy.yml",
        "AGENTS.md",
        "codex-backlog/CODEX_PROMPT_TEMPLATE.md",
        "codex-backlog/CODEX_SHORT_PROMPT.md",
        "codex-backlog/COMPLETION_CHECKLIST.md",
        "codex-backlog/EXECUTION_STATUS.md",
        "codex-backlog/GLOBAL_RULES.md",
        "codex-backlog/POST_RELEASE_DEPENDENCY_GRAPH.md",
        "codex-backlog/POST_RELEASE_PRIORITY_ORDER.md",
        "codex-backlog/TASK_EXECUTION_LIFECYCLE.md",
        "docs/codex-code-review-retirement.md",
        "docs/issue-driven-continuous-workflow.md",
        "docs/task-branch-integration.md",
        "scripts/archive_backlog_task.py",
        "scripts/artifact_manager.py",
        "scripts/issue_workflow.py",
        "scripts/run_task_delivery.py",
        "scripts/task_session.py",
        "tests/test_archive_backlog_task.py",
        "tests/test_artifact_manager.py",
        "tests/test_deployment_contract.py",
        "tests/test_issue_workflow.py",
        "tests/test_quality_gate_policy.py",
        "tests/test_release_safeguards.py",
        "tests/test_run_task_delivery.py",
        "tests/test_task_session.py",
    }
)
TASK_DEPENDENCY_RE = re.compile(r"(?im)^Depends-on:\s*(?P<value>.+)$")
TASK_FILE_RE = re.compile(rf"^(?P<task_id>{TASK_ID_PATTERN})-(?P<slug>.+)\.md$", re.IGNORECASE)
TASK_STATE_VERSION = 2
STATE_DIRECTORY_NAME = "codex-task-sessions-v1"
ACTIVE_DELIVERY_ARTIFACTS_ENV = "YFC_ACTIVE_DELIVERY_ARTIFACTS"
TARGET_BASE_BRANCH = "master"
MAX_GUARD_BUDGET_RECOVERIES = 1
MAX_POST_START_TRANSPORT_RECOVERIES = 1
POST_START_TRANSPORT_FAILURE_KIND = "post_start_external_transport_interruption"
POST_START_TRANSPORT_HANDOFF_BLOCKER = (
    "Owner-authorized bounded post-start transport recovery is launching the preserved task WIP."
)
POST_START_TRANSPORT_SIGNATURES = (
    "os error 11001",
    "connection failed",
    "error sending request",
    "stream disconnected before completion",
    "falling back from websockets to https transport",
    "error running remote compact task",
)
GUARD_RECOVERY_HANDOFF_BLOCKER = (
    "Owner-authorized bounded guard recovery is launching the preserved task WIP."
)
MAX_GUARD_EVIDENCE_BYTES = 16 * 1024 * 1024
TASK_INTEGRATION_BRANCHES = {"feature/app-experience-v3": "393"}
DEPENDABOT_LOGIN = "dependabot[bot]"
RENOVATE_LOGIN = "renovate[bot]"
TRUSTED_DEPENDENCY_BOT_BRANCH_PREFIXES = {
    DEPENDABOT_LOGIN: "dependabot/",
    RENOVATE_LOGIN: "renovate/",
}
VALID_CHECK_CONCLUSIONS = {"SUCCESS"}
UMBRELLA_TASK_IDS = {"90", "92", "93", "94", "95", "99", "100", "126"}
STATE_LOCK_STALE_SECONDS = 300

# A task lease and delivery ownership are separate controller concerns.  Every task owns only its
# own worktree/branch and task-state record.  ``exclusive-write`` remains a legacy metadata value
# for compatibility, but never creates a repository-wide implementation barrier; genuinely shared
# mutations are serialized by the narrower state/delivery mutexes below.  A superseded lease is a
# non-release terminal record whose clean Git anchor is retained for audit/recovery.
IMPLEMENTATION_STATES = frozenset({"starting", "implementation", "review", "qa"})
READY_STATES = frozenset({"ready-for-delivery", "ready-for-pr"})
WAITING_STATES = frozenset({"waiting-for-delivery"})
DELIVERY_STATES = frozenset({"delivering", "delivery-refreshing", "delivery-gate"})
TERMINAL_LEASE_STATES = frozenset({"production-success"})
SUPERSEDED_LEASE_STATES = frozenset({"superseded"})
CLOSED_LEASE_STATES = TERMINAL_LEASE_STATES | SUPERSEDED_LEASE_STATES
RECOVERY_STATES = frozenset({"recovery-required", "start-failed-recovery-required"})
KNOWN_LEASE_STATES = (
    IMPLEMENTATION_STATES
    | READY_STATES
    | WAITING_STATES
    | DELIVERY_STATES
    | CLOSED_LEASE_STATES
    | RECOVERY_STATES
)
DELIVERY_OWNER_STATES = DELIVERY_STATES | TERMINAL_LEASE_STATES
DELIVERY_STATE_VERSION = 1
DELIVERY_PRIORITY_REASON_MAX_LENGTH = 1024
CANONICAL_REFRESH_RESULTS = frozenset({"ALIGNED", "REFRESHED", "WAITING", "BLOCKED"})

# These paths are intentionally ignored by the repository and are managed by the controller,
# local tooling, or the owner-only backlog.  They must not make the canonical worktree look
# dirty for a ref-only fast-forward.  An ignored path outside this list remains a blocker.
CANONICAL_MANAGED_IGNORED_PATHS = (
    ".artifacts",
    ".env",
    ".idea",
    ".vscode",
    "backend/.artifacts",
    ".venv",
    "venv",
    "env",
    "frontend/node_modules",
    "frontend/dist",
    "frontend/coverage",
    "frontend/playwright-report",
    "frontend/test-results",
    "frontend/openapi.json",
    "codex-backlog",
    "docs/private",
)
CANONICAL_MANAGED_IGNORED_BASENAMES = frozenset(
    {".pytest_cache", ".ruff_cache", ".mypy_cache", "__pycache__"}
)


def _is_canonical_managed_ignored_path(path: str, *, root: Path) -> bool:
    """Return whether an ignored repository-relative path is controller-managed."""
    normalized = path.replace("\\", "/").casefold().rstrip("/")
    if not normalized or normalized.startswith("/") or re.fullmatch(r"[a-z]:.*", normalized):
        return False
    parts = normalized.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        return False

    if any(part in CANONICAL_MANAGED_IGNORED_BASENAMES for part in parts):
        return True

    for managed_path in CANONICAL_MANAGED_IGNORED_PATHS:
        managed = managed_path.casefold().rstrip("/")
        if normalized == managed:
            return True
        if not normalized.startswith(f"{managed}/"):
            continue
        try:
            managed_root = root.joinpath(*managed.split("/"))
        except OSError, ValueError:
            return False
        return managed_root.is_dir()
    return False


class TaskSessionError(RuntimeError):
    """A fail-closed controller refusal with an actionable message."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_task_id(value: str) -> str:
    task_id = value.strip().upper()
    if not TASK_ID_RE.fullmatch(task_id):
        raise TaskSessionError(f"Invalid task ID: {value!r}")
    return task_id


def normalize_delivery_priority_reason(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise TaskSessionError("owner-priority requires a non-empty reason")
    if len(normalized) > DELIVERY_PRIORITY_REASON_MAX_LENGTH:
        raise TaskSessionError("owner-priority reason exceeds the bounded length")
    return normalized


def _active_delivery_exclude_prefixes(root: Path, task_id: str) -> tuple[str, ...]:
    raw_path = os.environ.get(ACTIVE_DELIVERY_ARTIFACTS_ENV, "").strip()
    if not raw_path:
        return ()
    expected = normalize_task_id(task_id)
    active_path = Path(raw_path)
    if not active_path.is_absolute():
        raise TaskSessionError(f"{ACTIVE_DELIVERY_ARTIFACTS_ENV} must be an absolute path")
    try:
        active_path = active_path.resolve()
        temporary_root = (root / ".artifacts" / "tasks" / expected / "temporary").resolve()
    except (OSError, RuntimeError) as error:
        raise TaskSessionError(
            f"{ACTIVE_DELIVERY_ARTIFACTS_ENV} path could not be resolved"
        ) from error
    try:
        relative = active_path.relative_to(temporary_root)
    except ValueError as error:
        raise TaskSessionError(
            f"{ACTIVE_DELIVERY_ARTIFACTS_ENV} must stay under the exact task temporary root"
        ) from error
    if len(relative.parts) < 2 or relative.parts[0] != "delivery":
        raise TaskSessionError(
            f"{ACTIVE_DELIVERY_ARTIFACTS_ENV} must point to temporary/delivery/<run>"
        )
    if not active_path.is_dir():
        raise TaskSessionError(
            f"{ACTIVE_DELIVERY_ARTIFACTS_ENV} must point to an existing directory"
        )
    return (relative.as_posix(),)


def task_id_from_branch(branch: str) -> str:
    match = TASK_BRANCH_RE.fullmatch(branch)
    if match is None:
        raise TaskSessionError(f"Branch {branch!r} must match task/<ID>-<lowercase-kebab-slug>")
    if match.group("slug") != match.group("slug").lower():
        raise TaskSessionError(f"Branch {branch!r} must match task/<ID>-<lowercase-kebab-slug>")
    return match.group("task_id").upper()


def task_pr_task_id_from_branch(branch: str) -> str:
    try:
        return task_id_from_branch(branch)
    except TaskSessionError:
        task_id = TASK_INTEGRATION_BRANCHES.get(branch)
        if task_id is None:
            raise
        return task_id


def trusted_dependency_bot_login(pull_request: Mapping[str, Any]) -> str | None:
    user = pull_request.get("user")
    if not isinstance(user, Mapping):
        return None
    login = user.get("login")
    if not isinstance(login, str):
        return None
    branch_prefix = TRUSTED_DEPENDENCY_BOT_BRANCH_PREFIXES.get(login)
    if branch_prefix is None:
        return None
    head = pull_request.get("head")
    if not isinstance(head, Mapping):
        return None
    branch = head.get("ref")
    if not isinstance(branch, str) or not branch.startswith(branch_prefix):
        return None
    return login


def is_dependabot_pull_request(pull_request: Mapping[str, Any]) -> bool:
    return trusted_dependency_bot_login(pull_request) == DEPENDABOT_LOGIN


def is_renovate_pull_request(pull_request: Mapping[str, Any]) -> bool:
    return trusted_dependency_bot_login(pull_request) == RENOVATE_LOGIN


def normalize_concurrency_class(value: str) -> str:
    concurrency_class = value.strip().lower()
    if concurrency_class in {"exclusive-write", "independent-write"}:
        return concurrency_class
    raise TaskSessionError("Concurrency must be exclusive-write or independent-write")


def write_lanes_compatible(first: str, second: str) -> bool:
    # The old implementation treated ``exclusive-write`` as a repository-wide writer lock.  That
    # made an otherwise unrelated implementation wait without a shared resource to justify it.
    # Keep validating the legacy labels, while making compatibility mean what the worktree model
    # actually guarantees: separate task worktrees can be written concurrently.
    normalize_concurrency_class(first)
    normalize_concurrency_class(second)
    return True


def _task_commit_ids(message: str) -> set[str]:
    without_dependency_trailers = TASK_DEPENDENCY_RE.sub("", message)
    return {
        match.group("task_id").upper()
        for match in TASK_COMMIT_RE.finditer(without_dependency_trailers)
    }


def _is_origin_master_integration_merge(message: str) -> bool:
    headline = message.splitlines()[0] if message else ""
    return headline.startswith("Merge remote-tracking branch 'origin/master' into task/")


def declared_task_dependency_ids(messages: Sequence[str]) -> set[str]:
    result: set[str] = set()
    for message in messages:
        for trailer in TASK_DEPENDENCY_RE.finditer(message):
            result.update(
                match.group("task_id").upper()
                for match in TASK_COMMIT_RE.finditer(trailer.group("value"))
            )
    return result


def validate_task_commit_messages(
    task_id: str,
    messages: Sequence[str],
    *,
    dependency_ids: Sequence[str] | None = (),
) -> None:
    expected = normalize_task_id(task_id)
    if not messages:
        raise TaskSessionError("Task branch contains no task commits")
    declared_dependencies = declared_task_dependency_ids(messages)
    allowed_dependencies = (
        declared_dependencies
        if dependency_ids is None
        else {normalize_task_id(item) for item in dependency_ids}
    )
    if dependency_ids is not None and declared_dependencies - allowed_dependencies:
        unexpected = ", ".join(sorted(declared_dependencies - allowed_dependencies))
        raise TaskSessionError(
            f"Commit dependency declaration contains undeclared task IDs: {unexpected}"
        )
    allowed = {expected, *allowed_dependencies}
    task_ids: set[str] = set()
    for message in messages:
        if _is_origin_master_integration_merge(message):
            continue
        ids = _task_commit_ids(message)
        task_ids.update(ids)
        if len(ids) != 1 or not ids <= allowed:
            headline = message.splitlines()[0] if message else "<empty>"
            if dependency_ids is None:
                requirement = f"[Task {expected}] or an explicitly declared dependency"
            else:
                requirement = f"[Task {expected}] or a declared hard dependency"
            raise TaskSessionError(f"Commit {headline!r} must contain exactly {requirement}")
    if expected not in task_ids:
        raise TaskSessionError(f"Task branch contains no [Task {expected}] commit")
    foreign_ids = task_ids - {expected}
    if foreign_ids - declared_dependencies:
        unexpected = ", ".join(sorted(foreign_ids - declared_dependencies))
        raise TaskSessionError(
            f"Dependency commit provenance is missing Depends-on declaration: {unexpected}"
        )
    if dependency_ids is not None and foreign_ids - allowed_dependencies:
        unexpected = ", ".join(sorted(foreign_ids - allowed_dependencies))
        raise TaskSessionError(f"Commit provenance contains undeclared task IDs: {unexpected}")


def _run(
    args: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = list(args)
    if command and command[0] == "git":
        command = [
            "git",
            "-c",
            f"safe.directory={cwd.resolve().as_posix()}",
            "-c",
            "core.longpaths=true",
            *command[1:],
        ]
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=dict(os.environ) | dict(env or {}),
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise TaskSessionError(f"Command failed ({' '.join(args)}): {detail}")
    return completed


@dataclass(frozen=True)
class Worktree:
    path: Path
    head: str
    branch: str | None
    detached: bool


@dataclass(frozen=True)
class TaskDocument:
    task_id: str
    path: Path
    slug: str
    status: str
    dependencies: tuple[str, ...]
    executable: bool
    concurrency_class: str
    owner_gate: str
    integration_policy: str


class GitRepository:
    def __init__(self, start: Path) -> None:
        self.start = start.resolve()
        top = _run(["git", "rev-parse", "--show-toplevel"], cwd=self.start).stdout.strip()
        self.current_worktree = Path(top).resolve()
        common = _run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=self.current_worktree,
        ).stdout.strip()
        self.common_dir = Path(common).resolve()

    @property
    def repository_root(self) -> Path:
        return self.common_dir.parent

    def git(self, *args: str, cwd: Path | None = None, check: bool = True) -> str:
        return _run(["git", *args], cwd=cwd or self.current_worktree, check=check).stdout.strip()

    def worktrees(self) -> list[Worktree]:
        output = self.git("worktree", "list", "--porcelain")
        records: list[Worktree] = []
        current: dict[str, str] = {}
        for line in [*output.splitlines(), ""]:
            if line:
                key, _, value = line.partition(" ")
                current[key] = value
                continue
            if not current:
                continue
            branch = current.get("branch")
            records.append(
                Worktree(
                    path=Path(current["worktree"]).resolve(),
                    head=current.get("HEAD", ""),
                    branch=branch.removeprefix("refs/heads/") if branch else None,
                    detached="detached" in current,
                )
            )
            current = {}
        return records

    def ref(self, name: str) -> str:
        return self.git("rev-parse", "--verify", name)

    def ref_exists(self, name: str) -> bool:
        return self.git("rev-parse", "--verify", "--quiet", name, check=False) != ""

    def remote_branch_exists(self, branch: str, *, cwd: Path | None = None) -> bool:
        result = _run(
            ["git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}"],
            cwd=cwd or self.current_worktree,
            check=False,
        )
        if result.returncode != 0:
            raise TaskSessionError("Cannot verify the task branch on origin")
        return bool(result.stdout.strip())

    def fetch_origin_master(self, *, cwd: Path | None = None, prune: bool = True) -> None:
        args = ["fetch"]
        if prune:
            args.append("--prune")
        args.extend(("origin", "master"))
        self.git(*args, cwd=cwd)

    def head(self, *, cwd: Path | None = None) -> str:
        return self.git("rev-parse", "HEAD", cwd=cwd)

    def current_branch(self, *, cwd: Path | None = None) -> str | None:
        result = _run(
            ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
            cwd=cwd or self.current_worktree,
            check=False,
        )
        branch = result.stdout.strip()
        return branch or None

    def fast_forward_current(self, target: str, *, cwd: Path | None = None) -> None:
        self.git("merge", "--ff-only", target, cwd=cwd or self.current_worktree)

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        result = _run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=self.current_worktree,
            check=False,
        )
        return result.returncode == 0

    def status(
        self,
        path: Path,
        *,
        include_ignored: bool = False,
    ) -> list[str]:
        args = ["status", "--porcelain=v1", "--untracked-files=all"]
        if include_ignored:
            args.append("--ignored=matching")
        output = self.git(*args, cwd=path)
        return output.splitlines() if output else []

    def ahead_behind(self, left: str, right: str) -> tuple[int, int]:
        output = self.git("rev-list", "--left-right", "--count", f"{left}...{right}")
        ahead, behind = output.split()
        return int(ahead), int(behind)

    def git_dir(self, path: Path) -> Path:
        output = self.git("rev-parse", "--path-format=absolute", "--git-dir", cwd=path)
        return Path(output).resolve()

    def operation_issues(self, path: Path) -> list[str]:
        git_dir = self.git_dir(path)
        markers = (
            "index.lock",
            "MERGE_HEAD",
            "CHERRY_PICK_HEAD",
            "REVERT_HEAD",
            "BISECT_START",
            "rebase-apply",
            "rebase-merge",
        )
        return [marker for marker in markers if (git_dir / marker).exists()]

    def commits(self, revision_range: str) -> list[str]:
        output = self.git("log", "--format=%B%x00", revision_range, check=False)
        return [message.strip() for message in output.split("\x00") if message.strip()]

    def unique_commits(self, branch: str, base: str = "origin/master") -> list[str]:
        output = self.git("log", "--oneline", f"{base}..{branch}", check=False)
        return output.splitlines() if output else []

    def detached_unique_commits(self, path: Path) -> list[str]:
        output = self.git("log", "--oneline", "HEAD", "--not", "--all", cwd=path, check=False)
        return output.splitlines() if output else []

    def remove_worktree(self, path: Path) -> None:
        self.git("worktree", "remove", "--", str(path), cwd=self.current_worktree)

    def delete_local_branch(self, branch: str, *, force: bool = False) -> None:
        self.git("branch", "-D" if force else "--delete", "--", branch, cwd=self.current_worktree)

    def upstream(self, branch: str) -> str | None:
        result = _run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", f"{branch}@{{upstream}}"],
            cwd=self.current_worktree,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    def local_branches(self) -> list[dict[str, str | None]]:
        output = self.git(
            "for-each-ref",
            "--format=%(refname:short)%00%(objectname)%00%(upstream:short)",
            "refs/heads",
        )
        result: list[dict[str, str | None]] = []
        for line in output.splitlines():
            name, sha, upstream = line.split("\x00")
            result.append({"branch": name, "sha": sha, "upstream": upstream or None})
        return result

    def create_task_worktree(self, branch: str, path: Path, base_sha: str) -> None:
        self.git("branch", branch, base_sha)
        try:
            self.git("worktree", "add", str(path), branch)
        except Exception:
            self.git("branch", "-D", branch, check=False)
            raise


def _extract_bold_field(text: str, name: str) -> str:
    pattern = re.compile(rf"^- \*\*{re.escape(name)}:\*\*\s*(.+)$", re.MULTILINE)
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _legacy_dependencies(text: str, current_task_id: str) -> tuple[str, ...]:
    value = _extract_bold_field(text, "Зависимости")
    if not value:
        return ()
    candidates = {
        match.group(0).upper()
        for match in re.finditer(TASK_ID_PATTERN, value.upper())
        if match.group(0).upper() != current_task_id.upper()
    }
    return tuple(sorted(candidates))


def _metadata_block(text: str) -> dict[str, str]:
    match = re.search(r"<!--\s*task-session\s*(.*?)-->", text, flags=re.DOTALL)
    if match is None:
        return {}
    result: dict[str, str] = {}
    for raw_line in match.group(1).splitlines():
        key, separator, value = raw_line.partition(":")
        if separator:
            result[key.strip()] = value.strip()
    return result


def find_task_document(canonical_root: Path, task_id: str) -> TaskDocument:
    expected = normalize_task_id(task_id)
    roots = (
        canonical_root / "codex-backlog" / "tasks",
        canonical_root / "codex-backlog" / "bugs" / "pending",
        canonical_root / "codex-backlog" / "telegram-core-release-backlog" / "tasks",
    )
    matches: list[Path] = []
    for root in roots:
        if root.is_dir():
            matches.extend(
                path
                for path in root.glob(f"{expected}-*.md")
                if "done" not in path.relative_to(root).parts
            )
    if len(matches) != 1:
        raise TaskSessionError(
            f"Expected one canonical pending task for {expected}, found {len(matches)}"
        )
    path = matches[0].resolve()
    filename_match = TASK_FILE_RE.fullmatch(path.name)
    if filename_match is None:
        raise TaskSessionError(f"Invalid task filename: {path.name}")
    text = path.read_text(encoding="utf-8")
    metadata = _metadata_block(text)
    status = _extract_bold_field(text, "Статус")
    task_type = _extract_bold_field(text, "Тип").lower()
    executable_default = expected not in UMBRELLA_TASK_IDS and "umbrella" not in task_type
    return TaskDocument(
        task_id=expected,
        path=path,
        slug=re.sub(r"[^a-z0-9]+", "-", filename_match.group("slug").lower()).strip("-"),
        status=status,
        dependencies=tuple(
            normalize_task_id(item)
            for item in metadata.get("dependencies", "").split(",")
            if item.strip()
        )
        or _legacy_dependencies(text, expected),
        executable=metadata.get("executable", str(executable_default)).lower() == "true",
        # Ordinary tasks are safe to start in separate worktrees.  Preserve the explicit class
        # only as task metadata; final shared mutations are serialized by delivery coordination.
        concurrency_class=normalize_concurrency_class(
            metadata.get("concurrency", "independent-write")
        ),
        owner_gate=metadata.get("owner_gate", "explicit-launch"),
        integration_policy=metadata.get("integration", "task-pr-to-master"),
    )


def _resolved_dependency_ids(
    raw_dependencies: Sequence[str] | None,
    fallback: Sequence[str],
) -> tuple[str, ...]:
    if raw_dependencies is None:
        return tuple(fallback)
    if isinstance(raw_dependencies, (str, bytes)):
        raise TaskSessionError("Issue dependency contract must be an array of task IDs")
    try:
        normalized = [normalize_task_id(item) for item in raw_dependencies]
    except (TypeError, TaskSessionError) as error:
        raise TaskSessionError("Issue dependency contract contains an invalid task ID") from error
    return tuple(dict.fromkeys(normalized))


class StateStore:
    def __init__(self, common_dir: Path) -> None:
        self.root = common_dir / STATE_DIRECTORY_NAME
        self.leases = self.root / "leases"
        self.history = self.root / "history"
        self.lock_path = self.root / "state.lock"

    def initialize(self) -> None:
        self.leases.mkdir(parents=True, exist_ok=True)
        self.history.mkdir(parents=True, exist_ok=True)
        contract = self.root / "contract.json"
        if not contract.exists():
            try:
                self.create_json(contract, {"version": TASK_STATE_VERSION, "created_at": utc_now()})
            except TaskSessionError:
                # Two first-time controller calls may initialize the shared state concurrently.
                # The O_EXCL winner owns creation; a loser may continue only after confirming
                # that the contract now exists.
                if not contract.exists():
                    raise

    @contextmanager
    def lock(self) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        owner = {
            "pid": os.getpid(),
            "created_at": utc_now(),
            "token": uuid4().hex,
        }
        owner_text = json.dumps(owner, ensure_ascii=True, sort_keys=True) + "\n"
        try:
            descriptor = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as error:
            self._reclaim_stale_lock_if_safe()
            try:
                descriptor = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                raise TaskSessionError(
                    f"Coordination state is locked: {self.lock_path}; wait for the active owner"
                ) from error
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                handle.write(owner_text)
                handle.flush()
            yield
        finally:
            try:
                current = self.lock_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                current = ""
            except OSError as error:
                raise TaskSessionError(
                    f"Cannot verify coordination lock ownership {self.lock_path}: {error}"
                ) from error
            if current == owner_text:
                self.lock_path.unlink(missing_ok=True)

    @staticmethod
    def _pid_is_alive(pid: int) -> bool:
        if pid < 1:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError as error:
            return not (os.name == "nt" and getattr(error, "winerror", None) == 87)
        return True

    def _reclaim_stale_lock_if_safe(self) -> None:
        try:
            raw = self.lock_path.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except FileNotFoundError:
            return
        except (OSError, json.JSONDecodeError) as error:
            raise TaskSessionError(
                f"Coordination state lock is malformed or unreadable: {self.lock_path}"
            ) from error
        if not isinstance(payload, Mapping):
            raise TaskSessionError(f"Coordination state lock is malformed: {self.lock_path}")
        pid = payload.get("pid")
        created_at = payload.get("created_at")
        token = payload.get("token")
        if (
            isinstance(pid, bool)
            or not isinstance(pid, int)
            or pid < 1
            or not isinstance(created_at, str)
            or not created_at.strip()
            or not isinstance(token, str)
            or not re.fullmatch(r"[0-9a-f]{32}", token)
        ):
            raise TaskSessionError(f"Coordination state lock is malformed: {self.lock_path}")
        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise TaskSessionError(
                f"Coordination state lock timestamp is malformed: {self.lock_path}"
            ) from error
        if created.tzinfo is None:
            raise TaskSessionError(
                f"Coordination state lock timestamp has no timezone: {self.lock_path}"
            )
        age = (datetime.now(UTC) - created.astimezone(UTC)).total_seconds()
        if age < STATE_LOCK_STALE_SECONDS or self._pid_is_alive(pid):
            return
        try:
            current = self.lock_path.read_text(encoding="utf-8")
            if current != raw:
                return
            self.lock_path.unlink()
        except FileNotFoundError:
            return
        except OSError as error:
            raise TaskSessionError(
                f"Cannot reclaim stale coordination lock safely: {self.lock_path}"
            ) from error

    @staticmethod
    def read_json(path: Path, default: Any = None) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise TaskSessionError(f"Corrupted coordination state {path}: {error}") from error

    def create_json(self, path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as error:
            raise TaskSessionError(f"State already exists: {path}") from error
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

    @staticmethod
    def replace_json(path: Path, payload: Mapping[str, Any] | Sequence[Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def task_lease_path(self, task_id: str) -> Path:
        return self.leases / f"task-{normalize_task_id(task_id)}.json"

    @property
    def delivery_path(self) -> Path:
        return self.root / "delivery.json"

    def delivery_state(self) -> dict[str, Any]:
        payload = self.read_json(
            self.delivery_path,
            {"version": DELIVERY_STATE_VERSION, "next_sequence": 0, "owner": None},
        )
        if not isinstance(payload, dict):
            raise TaskSessionError(f"Invalid delivery coordination state: {self.delivery_path}")
        if payload.get("version") != DELIVERY_STATE_VERSION:
            raise TaskSessionError(f"Unsupported delivery coordination state: {self.delivery_path}")
        owner = payload.get("owner")
        if owner is not None and not isinstance(owner, dict):
            raise TaskSessionError(
                f"Invalid delivery owner in coordination state: {self.delivery_path}"
            )
        if owner is not None:
            owner_task_id = owner.get("task_id")
            if not isinstance(owner_task_id, str) or not TASK_ID_RE.fullmatch(owner_task_id):
                raise TaskSessionError(f"Invalid delivery owner task ID: {self.delivery_path}")
        sequence = payload.get("next_sequence", 0)
        if not isinstance(sequence, int) or sequence < 0:
            raise TaskSessionError(
                f"Invalid delivery sequence in coordination state: {self.delivery_path}"
            )
        priority_override = payload.get("priority_override")
        if priority_override is not None:
            if not isinstance(priority_override, dict):
                raise TaskSessionError(
                    f"Invalid delivery priority override in coordination state: {self.delivery_path}"
                )
            override_task_id = priority_override.get("task_id")
            skipped_task_ids = priority_override.get("skipped_task_ids")
            reason = priority_override.get("reason")
            authorized_at = priority_override.get("authorized_at")
            if (
                not isinstance(override_task_id, str)
                or not TASK_ID_RE.fullmatch(override_task_id)
                or not isinstance(skipped_task_ids, list)
                or any(
                    not isinstance(task_id, str) or not TASK_ID_RE.fullmatch(task_id)
                    for task_id in skipped_task_ids
                )
                or not isinstance(reason, str)
                or not reason.strip()
                or len(reason.strip()) > DELIVERY_PRIORITY_REASON_MAX_LENGTH
                or not isinstance(authorized_at, str)
                or not authorized_at.strip()
            ):
                raise TaskSessionError(
                    f"Malformed delivery priority override in coordination state: {self.delivery_path}"
                )
        return payload

    def all_leases(self) -> list[dict[str, Any]]:
        if not self.leases.exists():
            return []
        leases: list[dict[str, Any]] = []
        for path in sorted(self.leases.glob("*.json")):
            payload = self.read_json(path)
            if not isinstance(payload, dict):
                raise TaskSessionError(f"Invalid task lease payload: {path}")
            leases.append(payload)
        return leases


class GitHubClient:
    def __init__(self, repository: GitRepository, repo_slug: str | None = None) -> None:
        self.repository = repository
        self.repo_slug = repo_slug or self._repo_slug()

    def _repo_slug(self) -> str:
        remote = self.repository.git("remote", "get-url", "origin")
        match = re.search(r"github\.com[/:](?P<slug>[^/]+/[^/.]+)(?:\.git)?$", remote)
        if match is None:
            raise TaskSessionError("Cannot derive GitHub repository from the configured origin")
        return match.group("slug")

    def api(self, endpoint: str) -> Any:
        result = _run(
            ["gh", "api", f"repos/{self.repo_slug}/{endpoint}"],
            cwd=self.repository.current_worktree,
        )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise TaskSessionError(f"GitHub returned invalid JSON for {endpoint}") from error

    def open_pull_requests(self) -> list[dict[str, Any]]:
        return list(self.api("pulls?state=open&per_page=100"))

    def issue_comments(self, number: int) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self.api(f"issues/{number}/comments?per_page=100&page={page}")
            if not isinstance(payload, list):
                raise TaskSessionError(f"GitHub Issue #{number} comments are not a list")
            batch = [dict(item) for item in payload if isinstance(item, Mapping)]
            comments.extend(batch)
            if len(payload) < 100:
                return comments
            page += 1

    def pull_request(self, number: int) -> dict[str, Any]:
        return dict(self.api(f"pulls/{number}"))

    def pull_request_commits(self, number: int) -> list[dict[str, Any]]:
        commits: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = list(self.api(f"pulls/{number}/commits?per_page=100&page={page}"))
            commits.extend(batch)
            if len(batch) < 100:
                return commits
            page += 1

    def pull_request_files(self, number: int) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = list(self.api(f"pulls/{number}/files?per_page=100&page={page}"))
            files.extend(batch)
            if len(batch) < 100:
                return files
            page += 1

    def check_runs(self, sha: str) -> list[dict[str, Any]]:
        payload = self.api(f"commits/{sha}/check-runs?per_page=100")
        return list(payload.get("check_runs", []))

    def workflow_runs(self, workflow: str, sha: str) -> list[dict[str, Any]]:
        payload = self.api(f"actions/workflows/{workflow}/runs?head_sha={sha}&per_page=100")
        return list(payload.get("workflow_runs", []))

    def workflow_jobs(self, run_id: int) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self.api(f"actions/runs/{run_id}/jobs?per_page=100&page={page}")
            batch = list(payload.get("jobs", []))
            jobs.extend(batch)
            if len(batch) < 100:
                return jobs
            page += 1

    def pull_requests_for_commit(self, sha: str) -> list[dict[str, Any]]:
        return list(self.api(f"commits/{sha}/pulls?per_page=100"))

    def latest_deployment_status(self, environment: str) -> dict[str, Any] | None:
        deployments = [
            item
            for item in self.api(f"deployments?environment={environment}&per_page=100")
            if item.get("environment") == environment
        ]
        if not deployments:
            return None
        deployment = max(
            deployments,
            key=lambda item: (str(item.get("created_at", "")), int(item.get("id", 0))),
        )
        deployment_id = deployment.get("id")
        if type(deployment_id) is not int or deployment_id <= 0:
            raise TaskSessionError("GitHub returned an invalid production deployment ID")
        statuses = self.api(f"deployments/{deployment_id}/statuses?per_page=1")
        if not statuses:
            raise TaskSessionError("Latest production deployment has no status")
        status = statuses[0]
        return {
            "deployment_id": deployment_id,
            "sha": deployment.get("sha"),
            "environment": deployment.get("environment"),
            "state": status.get("state"),
            "created_at": deployment.get("created_at"),
            "updated_at": status.get("updated_at") or status.get("created_at"),
            "log_url": status.get("log_url"),
        }

    def branch_head(self, branch: str) -> str:
        payload = self.api(f"git/ref/heads/{branch}")
        return str(payload["object"]["sha"])

    def active_workflow_runs(self) -> list[dict[str, Any]]:
        payload = self.api("actions/runs?per_page=100")
        active_statuses = {"queued", "in_progress", "pending", "requested", "waiting"}
        return [
            item
            for item in payload.get("workflow_runs", [])
            if item.get("status") in active_statuses
        ]

    def rulesets(self) -> list[dict[str, Any]]:
        summaries = self.api("rulesets?per_page=100")
        return [dict(self.api(f"rulesets/{item['id']}")) for item in summaries]

    def has_successful_deployment(self, sha: str, environment: str) -> bool:
        deployments = self.api(f"deployments?sha={sha}&environment={environment}&per_page=100")
        for deployment in deployments:
            if deployment.get("sha") != sha or deployment.get("environment") != environment:
                continue
            statuses = self.api(f"deployments/{deployment['id']}/statuses?per_page=1")
            if statuses and statuses[0].get("state") == "success":
                return True
        return False


def _successful_exact_check(checks: Sequence[Mapping[str, Any]], name: str, sha: str) -> bool:
    return any(
        item.get("name") == name
        and item.get("head_sha") == sha
        and item.get("status") == "completed"
        and str(item.get("conclusion", "")).upper() in VALID_CHECK_CONCLUSIONS
        for item in checks
    )


def _verified_required_check(checks: Sequence[Mapping[str, Any]], sha: str) -> dict[str, str]:
    exact = [
        item for item in checks if item.get("name") == "checks" and item.get("head_sha") == sha
    ]
    if not exact:
        raise TaskSessionError(f"Exact-head required check 'checks' is missing for {sha}")
    latest = max(
        exact,
        key=lambda item: (
            str(item.get("started_at", "")),
            int(item.get("id", 0)) if str(item.get("id", 0)).isdigit() else 0,
        ),
    )
    if (
        latest.get("status") != "completed"
        or str(latest.get("conclusion", "")).upper() not in VALID_CHECK_CONCLUSIONS
    ):
        raise TaskSessionError(f"Exact-head required check 'checks' is not successful for {sha}")
    return {
        "name": "checks",
        "head_sha": sha,
        "status": "completed",
        "conclusion": str(latest.get("conclusion", "")).upper(),
    }


def validate_task_pull_request(
    pull_request: Mapping[str, Any],
    commits: Sequence[Mapping[str, Any]],
    checks: Sequence[Mapping[str, Any]],
    *,
    expected_base_sha: str,
    expected_base_branch: str = TARGET_BASE_BRANCH,
    require_checks: bool = True,
    dependency_ids: Sequence[str] | None = (),
) -> str:
    base = pull_request.get("base", {})
    head = pull_request.get("head", {})
    if base.get("ref") != expected_base_branch:
        raise TaskSessionError(
            f"Task pull request base must be {expected_base_branch}, found {base.get('ref')}"
        )
    branch = str(head.get("ref", ""))
    task_id = task_pr_task_id_from_branch(branch)
    if base.get("sha") != expected_base_sha:
        raise TaskSessionError(
            f"Task PR is stale: base {base.get('sha')} != current {expected_base_sha}"
        )
    if head.get("repo", {}).get("full_name") != base.get("repo", {}).get("full_name"):
        raise TaskSessionError("Task PR must originate from the same repository")
    title = str(pull_request.get("title", ""))
    if not title.startswith(f"[Task {task_id}]"):
        raise TaskSessionError(f"PR title must start with [Task {task_id}]")
    messages = [str(item.get("commit", {}).get("message", "")) for item in commits]
    declared_commit_count = pull_request.get("commits")
    if declared_commit_count is not None and int(declared_commit_count) != len(commits):
        raise TaskSessionError(
            "Task PR commit inventory is incomplete; split/review the PR instead of truncating provenance"
        )
    validate_task_commit_messages(task_id, messages, dependency_ids=dependency_ids)
    head_sha = str(head.get("sha", ""))
    if require_checks and not _successful_exact_check(checks, "checks", head_sha):
        raise TaskSessionError(
            f"Exact-head required check 'checks' is not successful for {head_sha}"
        )
    return task_id


def validate_controller_pull_request(
    pull_request: Mapping[str, Any],
    commits: Sequence[Mapping[str, Any]],
    checks: Sequence[Mapping[str, Any]],
    *,
    expected_base_sha: str,
    expected_base_branch: str = TARGET_BASE_BRANCH,
    require_checks: bool = True,
) -> str:
    """Validate a controller-only maintenance PR without inventing a product task."""

    base = pull_request.get("base", {})
    head = pull_request.get("head", {})
    if base.get("ref") != expected_base_branch:
        raise TaskSessionError(
            f"Controller pull request base must be {expected_base_branch}, found {base.get('ref')}"
        )
    branch = str(head.get("ref", ""))
    if CONTROLLER_BRANCH_RE.fullmatch(branch) is None:
        raise TaskSessionError(
            f"Controller branch {branch!r} must match codex/controller-<lowercase-kebab-slug>"
        )
    if base.get("sha") != expected_base_sha:
        raise TaskSessionError(
            f"Controller PR is stale: base {base.get('sha')} != current {expected_base_sha}"
        )
    base_repo = base.get("repo", {})
    head_repo = head.get("repo", {})
    if (
        not isinstance(base_repo, Mapping)
        or not isinstance(head_repo, Mapping)
        or not base_repo.get("full_name")
        or head_repo.get("full_name") != base_repo.get("full_name")
    ):
        raise TaskSessionError("Controller PR must originate from the same repository")
    title = str(pull_request.get("title", ""))
    if not title.startswith("[Controller]"):
        raise TaskSessionError("Controller PR title must start with [Controller]")
    messages = [str(item.get("commit", {}).get("message", "")) for item in commits]
    declared_commit_count = pull_request.get("commits")
    if declared_commit_count is not None and int(declared_commit_count) != len(commits):
        raise TaskSessionError(
            "Controller PR commit inventory is incomplete; split/review the PR instead of truncating provenance"
        )
    if not messages:
        raise TaskSessionError("Controller branch contains no controller commits")
    invalid = [
        message.splitlines()[0] if message else "<empty>"
        for message in messages
        if not CONTROLLER_COMMIT_RE.match(message)
    ]
    if invalid:
        raise TaskSessionError(
            "Controller commit messages must start with [Controller]: " + ", ".join(invalid)
        )
    head_sha = str(head.get("sha", ""))
    if not head_sha:
        raise TaskSessionError("Controller PR head SHA is missing")
    if require_checks and not _successful_exact_check(checks, "checks", head_sha):
        raise TaskSessionError(
            f"Exact-head required check 'checks' is not successful for {head_sha}"
        )
    return branch


def validate_controller_pull_request_files(
    files: Sequence[Mapping[str, Any]], *, expected_count: int | None = None
) -> None:
    """Keep controller-only provenance from becoming a product-code bypass."""

    validate_task_pull_request_files(files, expected_count=expected_count)
    changed = {str(item.get("filename", "")).replace("\\", "/") for item in files}
    disallowed = sorted(changed - CONTROLLER_ALLOWED_PATHS)
    if disallowed:
        raise TaskSessionError(
            "Controller PR contains paths outside the governance allowlist: "
            + ", ".join(disallowed)
        )


def validate_task_pull_request_files(
    files: Sequence[Mapping[str, Any]], *, expected_count: int | None = None
) -> None:
    if expected_count is not None and len(files) != expected_count:
        raise TaskSessionError(
            f"Task PR file inventory is incomplete: received {len(files)} of {expected_count} files"
        )
    forbidden: list[str] = []
    for item in files:
        filename = str(item.get("filename", "")).replace("\\", "/")
        lowered = filename.lower()
        if (
            filename.startswith((".artifacts/", ".git/"))
            or (Path(filename).name.startswith(".env") and Path(filename).name != ".env.example")
            or lowered.endswith((".pem", ".key", ".p12", ".pfx"))
        ):
            forbidden.append(filename)
    if forbidden:
        raise TaskSessionError(
            "Task PR contains forbidden artifact/credential paths: " + ", ".join(sorted(forbidden))
        )


def validate_master_ruleset(rulesets: Sequence[Mapping[str, Any]]) -> list[str]:
    matching = [
        item
        for item in rulesets
        if item.get("target") == "branch"
        and item.get("enforcement") == "active"
        and "refs/heads/master" in item.get("conditions", {}).get("ref_name", {}).get("include", [])
    ]
    if len(matching) != 1:
        return [f"expected exactly one active master Ruleset, found {len(matching)}"]
    rules = list(matching[0].get("rules", []))
    types = {item.get("type") for item in rules}
    issues = [
        f"master Ruleset is missing {required}"
        for required in ("deletion", "non_fast_forward", "pull_request", "required_status_checks")
        if required not in types
    ]
    status_rules = [item for item in rules if item.get("type") == "required_status_checks"]
    if status_rules:
        parameters = status_rules[0].get("parameters", {})
        contexts = {item.get("context") for item in parameters.get("required_status_checks", [])}
        if parameters.get("strict_required_status_checks_policy") is not True:
            issues.append("master Ruleset required checks are not strict-current-base")
        if "checks" not in contexts:
            issues.append("master Ruleset does not require aggregate checks")
    return issues


def validate_pr_event(
    repository: GitRepository, github: GitHubClient, event_path: Path
) -> dict[str, Any]:
    del repository
    event = json.loads(event_path.read_text(encoding="utf-8"))
    pull_request = event.get("pull_request")
    if not isinstance(pull_request, dict):
        return {"kind": "not-pull-request"}
    if pull_request.get("base", {}).get("ref") != TARGET_BASE_BRANCH:
        raise TaskSessionError(
            f"Unsupported pull request base: {pull_request.get('base', {}).get('ref')}"
        )
    dependency_bot_login = trusted_dependency_bot_login(pull_request)
    if dependency_bot_login is not None:
        base = pull_request.get("base", {})
        head = pull_request.get("head", {})
        base_repo = base.get("repo", {}).get("full_name")
        head_repo = head.get("repo", {}).get("full_name")
        bot_name = "Dependabot" if dependency_bot_login == DEPENDABOT_LOGIN else "Renovate"
        if not base_repo or not head_repo or head_repo != base_repo:
            raise TaskSessionError(
                f"{bot_name} pull request must originate from the same repository"
            )
        head_sha = str(head.get("sha", ""))
        if not head_sha:
            raise TaskSessionError(f"{bot_name} pull request head SHA is missing")
        kind = "dependabot-pr" if dependency_bot_login == DEPENDABOT_LOGIN else "renovate-pr"
        return {"kind": kind, "head_sha": head_sha}
    event_base_sha = str(pull_request.get("base", {}).get("sha", ""))
    current_master_sha = github.branch_head(TARGET_BASE_BRANCH)
    if event_base_sha != current_master_sha:
        raise TaskSessionError(
            f"Task PR is stale: base {event_base_sha} != current {current_master_sha}"
        )
    number = int(pull_request["number"])
    commits = github.pull_request_commits(number)
    files = github.pull_request_files(number)
    branch = str(pull_request.get("head", {}).get("ref", ""))
    if CONTROLLER_BRANCH_RE.fullmatch(branch):
        validate_controller_pull_request(
            pull_request,
            commits,
            [],
            expected_base_sha=event_base_sha,
            require_checks=False,
        )
        validate_controller_pull_request_files(
            files, expected_count=int(pull_request.get("changed_files", len(files)))
        )
        return {
            "kind": "controller-pr",
            "branch": branch,
            "head_sha": pull_request["head"]["sha"],
        }
    task_id = validate_task_pull_request(
        pull_request,
        commits,
        [],
        expected_base_sha=event_base_sha,
        require_checks=False,
        dependency_ids=None,
    )
    validate_task_pull_request_files(
        files, expected_count=int(pull_request.get("changed_files", len(files)))
    )
    return {"kind": "task-pr", "task_id": task_id, "head_sha": pull_request["head"]["sha"]}


def verify_master_merge(
    repository: GitRepository, github: GitHubClient, *, sha: str
) -> dict[str, Any]:
    if github.branch_head(TARGET_BASE_BRANCH) != sha:
        raise TaskSessionError(f"Master head is not the requested merge SHA {sha}")
    associated = github.api(f"commits/{sha}/pulls")
    matches: list[dict[str, Any]] = []
    for pull_request in associated:
        base = pull_request.get("base", {})
        head = pull_request.get("head", {})
        if not (
            pull_request.get("merged_at")
            and pull_request.get("merge_commit_sha") == sha
            and base.get("ref") == TARGET_BASE_BRANCH
        ):
            continue
        branch = str(head.get("ref", ""))
        title = str(pull_request.get("title", ""))
        base_repo = base.get("repo", {})
        head_repo = head.get("repo", {})
        is_same_repository = (
            isinstance(base_repo, Mapping)
            and isinstance(head_repo, Mapping)
            and bool(base_repo.get("full_name"))
            and head_repo.get("full_name") == base_repo.get("full_name")
        )
        try:
            task_id = task_pr_task_id_from_branch(branch)
        except TaskSessionError:
            task_id = None
        is_task_merge = (
            task_id is not None and title.startswith(f"[Task {task_id}]") and is_same_repository
        )
        is_controller_merge = CONTROLLER_BRANCH_RE.fullmatch(
            branch
        ) is not None and title.startswith("[Controller]")
        dependency_bot_login = trusted_dependency_bot_login(pull_request)
        is_dependency_bot_merge = dependency_bot_login is not None and is_same_repository
        if is_task_merge:
            merge_kind = "task-pr-merge"
        elif is_controller_merge and is_same_repository:
            merge_kind = "controller-pr-merge"
        elif is_dependency_bot_merge:
            merge_kind = (
                "dependabot-pr-merge"
                if dependency_bot_login == DEPENDABOT_LOGIN
                else "renovate-pr-merge"
            )
        else:
            continue
        matches.append(
            {
                "kind": merge_kind,
                "number": pull_request.get("number"),
                "title": pull_request.get("title"),
            }
        )
    if len(matches) != 1:
        raise TaskSessionError(
            f"Master revision {sha} is not exactly one merged task or controller PR result: "
            f"found {len(matches)}"
        )
    match = matches[0]
    return {
        "kind": match["kind"],
        "sha": sha,
        "pull_request": {"number": match["number"], "title": match["title"]},
    }


class TaskController:
    def __init__(self, repository: GitRepository, *, github: GitHubClient | None = None) -> None:
        self.repository = repository
        self.store = StateStore(repository.common_dir)
        self.github = github

    def _github(self) -> GitHubClient:
        if self.github is None:
            self.github = GitHubClient(self.repository)
        return self.github

    def _canonical_root(self) -> Path:
        return self.repository.repository_root

    def _canonical_worktree_status(self, root: Path | None = None) -> list[str]:
        canonical_root = root or self._canonical_root()
        status = self.repository.status(canonical_root, include_ignored=True)
        unexpected: list[str] = []
        for item in status:
            if not item.startswith("!! "):
                unexpected.append(item)
                continue
            ignored_path = item[3:].strip().replace("\\", "/").rstrip("/")
            if not _is_canonical_managed_ignored_path(ignored_path, root=canonical_root):
                unexpected.append(item)
        return unexpected

    def _canonical_refresh_payload(
        self,
        result: str,
        *,
        old_sha: str | None = None,
        new_sha: str | None = None,
        origin_sha: str | None = None,
        live_sha: str | None = None,
        ahead_before: int | None = None,
        behind_before: int | None = None,
        ahead_after: int | None = None,
        behind_after: int | None = None,
        updated_commits: int = 0,
        mutation_performed: bool = False,
        reason: str = "",
        recovery_hint: str = "Retry canonical master refresh after the blocker is resolved.",
        delivery_task_id: str | None = None,
        reread_after_contention: bool = False,
    ) -> dict[str, Any]:
        if result not in CANONICAL_REFRESH_RESULTS:
            raise TaskSessionError(f"Unknown canonical refresh result: {result}")
        return {
            "operation": "canonical-master-refresh",
            "result": result,
            "canonical_worktree": str(self._canonical_root()),
            "old_sha": old_sha,
            "new_sha": new_sha,
            "local_master_before": old_sha,
            "local_master_after": new_sha,
            "origin_master_sha": origin_sha,
            "verified_remote_sha": origin_sha,
            "live_master_sha": live_sha,
            "ahead_before": ahead_before,
            "behind_before": behind_before,
            "ahead_after": ahead_after,
            "behind_after": behind_after,
            "updated_commits": updated_commits,
            "mutation_performed": mutation_performed,
            "mutated_ref": "refs/heads/master" if mutation_performed else None,
            "reread_after_contention": reread_after_contention,
            "delivery_task_id": delivery_task_id,
            "reason": reason,
            "recovery_hint": recovery_hint,
        }

    def _safe_ref(self, name: str) -> str | None:
        try:
            return self.repository.ref(name)
        except TaskSessionError:
            return None

    def _canonical_refresh_controller_blocker(
        self, *, delivery_task_id: str | None
    ) -> tuple[str, str] | None:
        expected_delivery_task = (
            normalize_task_id(delivery_task_id) if delivery_task_id is not None else None
        )
        leases = self.store.all_leases()
        delivery = self.store.delivery_state()
        owner = delivery.get("owner")
        owner_id = str(owner.get("task_id", "")).upper() if isinstance(owner, dict) else ""
        delivery_waiting_reason: str | None = None
        owner_lease = None
        if owner_id:
            owner_lease = next(
                (item for item in leases if str(item.get("task_id", "")).upper() == owner_id),
                None,
            )
            if owner_lease is None:
                return (
                    "BLOCKED",
                    f"delivery lane owner Task {owner_id} has no matching lease",
                )
            try:
                self._validated_lease_concurrency_class(owner_lease)
            except TaskSessionError as error:
                return ("BLOCKED", str(error))
            owner_state = self._lease_state(owner_lease)
            if owner_state == "production-success":
                delivery_waiting_reason = f"Task {owner_id} is in terminal production closeout"
            elif owner_state not in DELIVERY_STATES:
                return (
                    "BLOCKED",
                    f"delivery lane owner Task {owner_id} has ambiguous state {owner_state}",
                )
            elif owner_id != expected_delivery_task:
                delivery_waiting_reason = f"delivery lane is occupied by Task {owner_id}"

        task_ids: set[str] = set()
        lease_branches: dict[str, str] = {}
        lease_worktrees: dict[str, str] = {}
        try:
            repository_worktrees = {
                str(item.path.resolve()).casefold(): item for item in self.repository.worktrees()
            }
        except TaskSessionError as error:
            return ("BLOCKED", f"cannot inspect controller worktrees: {error}")
        waiting_reason = delivery_waiting_reason
        known_states = IMPLEMENTATION_STATES | READY_STATES | WAITING_STATES | DELIVERY_STATES
        for lease in leases:
            raw_task_id = str(lease.get("task_id", "")).upper()
            if not TASK_ID_RE.fullmatch(raw_task_id):
                return ("BLOCKED", "controller contains a lease with an invalid task ID")
            if raw_task_id in task_ids:
                return ("BLOCKED", f"controller contains duplicate Task {raw_task_id} leases")
            task_ids.add(raw_task_id)
            if lease.get("mode") != "write":
                return ("BLOCKED", f"Task {raw_task_id} has an unsupported controller mode")
            try:
                self._validated_lease_concurrency_class(lease)
            except TaskSessionError as error:
                return ("BLOCKED", str(error))
            branch = lease.get("branch")
            if not isinstance(branch, str):
                return ("BLOCKED", f"Task {raw_task_id} lease has no valid task branch")
            try:
                if task_id_from_branch(branch) != raw_task_id:
                    return (
                        "BLOCKED",
                        f"Task {raw_task_id} lease branch does not match its task ID",
                    )
            except TaskSessionError:
                return ("BLOCKED", f"Task {raw_task_id} lease has an invalid task branch")
            branch_key = branch.casefold()
            if branch_key in lease_branches:
                return (
                    "BLOCKED",
                    f"controller leases share task branch {branch} "
                    f"(Tasks {lease_branches[branch_key]} and {raw_task_id})",
                )
            lease_branches[branch_key] = raw_task_id
            worktree_value = lease.get("worktree")
            if not isinstance(worktree_value, str) or not worktree_value.strip():
                return ("BLOCKED", f"Task {raw_task_id} lease has no valid worktree")
            try:
                worktree_key = str(Path(worktree_value).resolve()).casefold()
            except (OSError, RuntimeError) as _error:
                return ("BLOCKED", f"Task {raw_task_id} lease worktree cannot be resolved")
            if worktree_key == str(self._canonical_root().resolve()).casefold():
                return (
                    "BLOCKED",
                    f"Task {raw_task_id} lease points to the canonical controller worktree",
                )
            if worktree_key in lease_worktrees:
                return (
                    "BLOCKED",
                    f"controller leases share worktree {worktree_value} "
                    f"(Tasks {lease_worktrees[worktree_key]} and {raw_task_id})",
                )
            lease_worktrees[worktree_key] = raw_task_id
            repository_worktree = repository_worktrees.get(worktree_key)
            if repository_worktree is None:
                return (
                    "BLOCKED",
                    f"Task {raw_task_id} lease worktree is missing from Git worktrees",
                )
            if repository_worktree.branch != branch:
                return (
                    "BLOCKED",
                    f"Task {raw_task_id} lease worktree branch does not match {branch}",
                )
            state = self._lease_state(lease)
            if state in SUPERSEDED_LEASE_STATES:
                continue
            if state in RECOVERY_STATES:
                return ("BLOCKED", f"Task {raw_task_id} requires controller recovery")
            if state in DELIVERY_STATES:
                if raw_task_id == owner_id:
                    continue
                return (
                    "BLOCKED",
                    f"Task {raw_task_id} is in delivery state without matching delivery ownership",
                )
            if state == "production-success":
                if raw_task_id == owner_id:
                    continue
                return (
                    "BLOCKED",
                    f"Task {raw_task_id} has terminal success without delivery ownership",
                )
            if state == "starting":
                waiting_reason = waiting_reason or (
                    f"Task {raw_task_id} is in an active controller start transition"
                )
                continue
            if state not in known_states:
                return (
                    "BLOCKED",
                    f"Task {raw_task_id} has an ambiguous controller state {state or '<missing>'}",
                )

        if owner_id and owner_id not in task_ids:
            return ("BLOCKED", f"delivery lane owner Task {owner_id} is not represented by a lease")
        if not owner_id and any(
            self._lease_state(lease) in DELIVERY_STATES | TERMINAL_LEASE_STATES for lease in leases
        ):
            return (
                "BLOCKED",
                "controller has a delivery/closeout state without delivery ownership",
            )
        if waiting_reason:
            return ("WAITING", waiting_reason)
        return None

    def _canonical_refresh_after_contention(
        self, *, offline: bool, delivery_task_id: str | None
    ) -> dict[str, Any]:
        old_sha = self._safe_ref("master")
        origin_sha = self._safe_ref("origin/master")
        if not offline:
            try:
                live_sha = self._github().branch_head(TARGET_BASE_BRANCH)
            except (TaskSessionError, OSError) as _error:
                live_sha = None
            if old_sha and origin_sha and live_sha and old_sha == origin_sha == live_sha:
                return self._canonical_refresh_payload(
                    "ALIGNED",
                    old_sha=old_sha,
                    new_sha=old_sha,
                    origin_sha=origin_sha,
                    live_sha=live_sha,
                    ahead_before=0,
                    behind_before=0,
                    ahead_after=0,
                    behind_after=0,
                    reason="concurrent controller operation completed; verified refs were reread",
                    recovery_hint="No recovery is required.",
                    delivery_task_id=delivery_task_id,
                    reread_after_contention=True,
                )
        return self._canonical_refresh_payload(
            "WAITING",
            old_sha=old_sha,
            new_sha=old_sha,
            origin_sha=origin_sha,
            reason="another controller operation owns the coordination lock",
            recovery_hint="Wait for the active controller operation to finish, then retry.",
            delivery_task_id=delivery_task_id,
            reread_after_contention=True,
        )

    def refresh_canonical_master(
        self, *, offline: bool = False, delivery_task_id: str | None = None
    ) -> dict[str, Any]:
        """Safely align the canonical local master with the verified protected master."""

        expected_delivery_task = (
            normalize_task_id(delivery_task_id) if delivery_task_id is not None else None
        )
        root = self._canonical_root()
        try:
            self.store.initialize()
        except (TaskSessionError, OSError) as _error:
            return self._canonical_refresh_payload(
                "BLOCKED",
                reason="canonical refresh shared controller state could not be initialized",
                recovery_hint="Resolve the controller state filesystem issue owner-safely, then retry.",
                delivery_task_id=expected_delivery_task,
            )
        if self.store.lock_path.exists():
            return self._canonical_refresh_after_contention(
                offline=offline, delivery_task_id=expected_delivery_task
            )

        try:
            with self.store.lock():
                controller_blocker = self._canonical_refresh_controller_blocker(
                    delivery_task_id=expected_delivery_task
                )
                if controller_blocker is not None:
                    result, reason = controller_blocker
                    old_sha = self._safe_ref("master")
                    return self._canonical_refresh_payload(
                        result,
                        old_sha=old_sha,
                        new_sha=old_sha,
                        reason=reason,
                        recovery_hint=(
                            "Retry after the delivery or controller transition completes."
                            if result == "WAITING"
                            else "Use the named controller recovery path; do not reset or stash master."
                        ),
                        delivery_task_id=expected_delivery_task,
                    )

                try:
                    canonical_branch = self.repository.git("branch", "--show-current", cwd=root)
                except (TaskSessionError, OSError) as _error:
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        reason="canonical controller worktree branch could not be inspected",
                        recovery_hint="Restore a readable canonical worktree on branch master, then retry.",
                        delivery_task_id=expected_delivery_task,
                    )
                if canonical_branch != TARGET_BASE_BRANCH:
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        reason=f"canonical controller worktree is not on {TARGET_BASE_BRANCH}",
                        recovery_hint="Resolve the canonical checkout state manually; no ref was changed.",
                        delivery_task_id=expected_delivery_task,
                    )
                try:
                    dirty = self._canonical_worktree_status(root)
                except (TaskSessionError, OSError) as _error:
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        reason="canonical worktree status could not be inspected",
                        recovery_hint="Resolve the status/permission issue without stash or reset, then retry.",
                        delivery_task_id=expected_delivery_task,
                    )
                if dirty:
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        old_sha=self._safe_ref("master"),
                        reason="canonical worktree is dirty, including significant ignored state",
                        recovery_hint="Preserve the changes, make the canonical worktree clean, then retry.",
                        delivery_task_id=expected_delivery_task,
                    )
                operations = self.repository.operation_issues(root)
                if operations:
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        old_sha=self._safe_ref("master"),
                        reason="canonical worktree has an active Git operation or lock",
                        recovery_hint="Finish or owner-safely recover the Git operation; do not delete the lock.",
                        delivery_task_id=expected_delivery_task,
                    )
                if offline:
                    old_sha = self._safe_ref("master")
                    origin_sha = self._safe_ref("origin/master")
                    return self._canonical_refresh_payload(
                        "WAITING",
                        old_sha=old_sha,
                        new_sha=old_sha,
                        origin_sha=origin_sha,
                        reason="offline mode cannot verify live protected master freshness",
                        recovery_hint="Retry online after the remote and live protected branch are reachable.",
                        delivery_task_id=expected_delivery_task,
                    )
                try:
                    if self._active_production_deployment():
                        old_sha = self._safe_ref("master")
                        return self._canonical_refresh_payload(
                            "WAITING",
                            old_sha=old_sha,
                            new_sha=old_sha,
                            reason="production deployment is active",
                            recovery_hint="Wait for production deployment to reach a terminal state, then retry.",
                            delivery_task_id=expected_delivery_task,
                        )
                except (TaskSessionError, OSError) as _error:
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        reason="production delivery state could not be verified",
                        recovery_hint="Restore the online controller/GitHub verification path, then retry.",
                        delivery_task_id=expected_delivery_task,
                    )

                old_sha = self._safe_ref("master")
                try:
                    self.repository.fetch_origin_master(cwd=root, prune=False)
                except (TaskSessionError, OSError) as _error:
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        old_sha=old_sha,
                        new_sha=old_sha,
                        reason="fetch of current origin/master failed",
                        recovery_hint="Verify the configured remote and network, then retry; canonical master was not changed.",
                        delivery_task_id=expected_delivery_task,
                    )
                origin_sha = self._safe_ref("origin/master")
                try:
                    live_sha = self._github().branch_head(TARGET_BASE_BRANCH)
                except (TaskSessionError, OSError) as _error:
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        old_sha=old_sha,
                        new_sha=old_sha,
                        origin_sha=origin_sha,
                        reason="live protected master verification failed",
                        recovery_hint="Restore live branch verification and retry; canonical master was not changed.",
                        delivery_task_id=expected_delivery_task,
                    )
                if not old_sha or not origin_sha or not live_sha:
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        old_sha=old_sha,
                        new_sha=old_sha,
                        origin_sha=origin_sha,
                        live_sha=live_sha,
                        reason="canonical, tracking, or live master SHA is unavailable",
                        recovery_hint="Repair the missing ref/verification input without resetting master, then retry.",
                        delivery_task_id=expected_delivery_task,
                    )
                if origin_sha != live_sha:
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        old_sha=old_sha,
                        new_sha=old_sha,
                        origin_sha=origin_sha,
                        live_sha=live_sha,
                        reason="fetched origin/master does not match live protected master",
                        recovery_hint="Do not mutate master; investigate remote/live divergence and retry after it is resolved.",
                        delivery_task_id=expected_delivery_task,
                    )
                try:
                    ahead_before, behind_before = self.repository.ahead_behind("master", live_sha)
                except (TaskSessionError, OSError) as _error:
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        old_sha=old_sha,
                        new_sha=old_sha,
                        origin_sha=origin_sha,
                        live_sha=live_sha,
                        reason="canonical master ancestry could not be verified",
                        recovery_hint="Inspect the canonical refs without reset, then retry.",
                        delivery_task_id=expected_delivery_task,
                    )
                if ahead_before > 0:
                    reason = (
                        "canonical master diverges from verified protected master"
                        if behind_before > 0
                        else "canonical master contains unpublished commits"
                    )
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        old_sha=old_sha,
                        new_sha=old_sha,
                        origin_sha=origin_sha,
                        live_sha=live_sha,
                        ahead_before=ahead_before,
                        behind_before=behind_before,
                        reason=f"{reason}: ahead={ahead_before} behind={behind_before}",
                        recovery_hint="Preserve the canonical commits and resolve the divergence owner-safely; no reset or merge was attempted.",
                        delivery_task_id=expected_delivery_task,
                    )
                if behind_before == 0:
                    return self._canonical_refresh_payload(
                        "ALIGNED",
                        old_sha=old_sha,
                        new_sha=old_sha,
                        origin_sha=origin_sha,
                        live_sha=live_sha,
                        ahead_before=0,
                        behind_before=0,
                        ahead_after=0,
                        behind_after=0,
                        reason="canonical master already matches verified protected master",
                        recovery_hint="No recovery is required.",
                        delivery_task_id=expected_delivery_task,
                    )

                # Recheck the safety boundary immediately before the sole canonical mutation.
                if self._canonical_worktree_status(root):
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        old_sha=old_sha,
                        new_sha=old_sha,
                        origin_sha=origin_sha,
                        live_sha=live_sha,
                        ahead_before=ahead_before,
                        behind_before=behind_before,
                        reason="canonical worktree changed during refresh validation",
                        recovery_hint="Preserve the change, make the canonical worktree clean, then retry.",
                        delivery_task_id=expected_delivery_task,
                    )
                if self.repository.operation_issues(root):
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        old_sha=old_sha,
                        new_sha=old_sha,
                        origin_sha=origin_sha,
                        live_sha=live_sha,
                        ahead_before=ahead_before,
                        behind_before=behind_before,
                        reason="canonical Git operation appeared during refresh validation",
                        recovery_hint="Resolve the active Git operation owner-safely, then retry.",
                        delivery_task_id=expected_delivery_task,
                    )
                if (
                    self._safe_ref("master") != old_sha
                    or self._safe_ref("origin/master") != origin_sha
                ):
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        old_sha=old_sha,
                        new_sha=self._safe_ref("master"),
                        origin_sha=self._safe_ref("origin/master"),
                        live_sha=live_sha,
                        ahead_before=ahead_before,
                        behind_before=behind_before,
                        reason="canonical or tracking ref changed during refresh validation",
                        recovery_hint="Re-read the refs and retry without resetting master.",
                        delivery_task_id=expected_delivery_task,
                    )
                try:
                    live_before_merge = self._github().branch_head(TARGET_BASE_BRANCH)
                except (TaskSessionError, OSError) as _error:
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        old_sha=old_sha,
                        new_sha=old_sha,
                        origin_sha=origin_sha,
                        live_sha=live_sha,
                        ahead_before=ahead_before,
                        behind_before=behind_before,
                        reason="live protected master verification failed before mutation",
                        recovery_hint="Restore live branch verification and retry; canonical master was not changed.",
                        delivery_task_id=expected_delivery_task,
                    )
                if live_before_merge != live_sha:
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        old_sha=old_sha,
                        new_sha=old_sha,
                        origin_sha=origin_sha,
                        live_sha=live_before_merge,
                        ahead_before=ahead_before,
                        behind_before=behind_before,
                        reason="live protected master changed during refresh validation",
                        recovery_hint="Re-fetch and re-verify the live branch before retrying; no mutation was attempted.",
                        delivery_task_id=expected_delivery_task,
                    )
                try:
                    final_canonical_branch = self.repository.git(
                        "branch", "--show-current", cwd=root
                    )
                    final_symbolic_head = self.repository.git(
                        "symbolic-ref", "--quiet", "--short", "HEAD", cwd=root, check=False
                    )
                    final_canonical_head = self.repository.head(cwd=root)
                except (TaskSessionError, OSError) as _error:
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        old_sha=old_sha,
                        new_sha=old_sha,
                        origin_sha=origin_sha,
                        live_sha=live_before_merge,
                        ahead_before=ahead_before,
                        behind_before=behind_before,
                        reason="canonical HEAD could not be verified immediately before mutation",
                        recovery_hint="Restore the canonical master checkout and retry; no mutation was attempted.",
                        delivery_task_id=expected_delivery_task,
                    )
                if (
                    final_canonical_branch != TARGET_BASE_BRANCH
                    or final_symbolic_head != TARGET_BASE_BRANCH
                    or final_canonical_head != old_sha
                ):
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        old_sha=old_sha,
                        new_sha=final_canonical_head,
                        origin_sha=origin_sha,
                        live_sha=live_before_merge,
                        ahead_before=ahead_before,
                        behind_before=behind_before,
                        reason=(
                            "canonical checkout changed during final refresh validation: "
                            f"branch={final_canonical_branch or '<detached>'}; "
                            f"symbolic_head={final_symbolic_head or '<detached>'}; "
                            f"HEAD={final_canonical_head}; expected_branch={TARGET_BASE_BRANCH}; "
                            f"expected_HEAD={old_sha}"
                        ),
                        recovery_hint="Restore the canonical master checkout and retry; no mutation was attempted.",
                        delivery_task_id=expected_delivery_task,
                    )
                try:
                    self.repository.git("merge", "--ff-only", origin_sha, cwd=root)
                except TaskSessionError:
                    new_sha = self._safe_ref("master")
                    changed = new_sha is not None and new_sha != old_sha
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        old_sha=old_sha,
                        new_sha=new_sha,
                        origin_sha=origin_sha,
                        live_sha=live_sha,
                        ahead_before=ahead_before,
                        behind_before=behind_before,
                        mutation_performed=changed,
                        reason="fast-forward-only canonical master update failed",
                        recovery_hint="Inspect the canonical Git operation without reset; retry only after the ref state is clear.",
                        delivery_task_id=expected_delivery_task,
                    )

                new_sha = self._safe_ref("master")
                origin_after = self._safe_ref("origin/master")
                try:
                    live_after = self._github().branch_head(TARGET_BASE_BRANCH)
                except (TaskSessionError, OSError) as _error:
                    live_after = None
                changed = new_sha is not None and new_sha != old_sha
                if not new_sha or not origin_after or not live_after:
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        old_sha=old_sha,
                        new_sha=new_sha,
                        origin_sha=origin_after,
                        live_sha=live_after,
                        ahead_before=ahead_before,
                        behind_before=behind_before,
                        updated_commits=behind_before,
                        mutation_performed=changed,
                        reason="post-refresh master verification could not read all refs",
                        recovery_hint="Preserve the resulting refs and complete owner-safe verification before retrying.",
                        delivery_task_id=expected_delivery_task,
                    )
                if new_sha != origin_after or origin_after != live_after:
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        old_sha=old_sha,
                        new_sha=new_sha,
                        origin_sha=origin_after,
                        live_sha=live_after,
                        ahead_before=ahead_before,
                        behind_before=behind_before,
                        mutation_performed=changed,
                        reason="post-refresh canonical, tracking, and live master SHAs do not match",
                        recovery_hint="Do not reset or repeat blindly; investigate the exact refs and retry after verification is restored.",
                        delivery_task_id=expected_delivery_task,
                    )
                try:
                    dirty_after = self._canonical_worktree_status(root)
                    operations_after = self.repository.operation_issues(root)
                except (TaskSessionError, OSError) as _error:
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        old_sha=old_sha,
                        new_sha=new_sha,
                        origin_sha=origin_after,
                        live_sha=live_after,
                        ahead_before=ahead_before,
                        behind_before=behind_before,
                        ahead_after=0,
                        behind_after=0,
                        updated_commits=behind_before,
                        mutation_performed=changed,
                        reason="post-refresh canonical worktree verification failed",
                        recovery_hint="Preserve the resulting refs and resolve the worktree state owner-safely before retrying.",
                        delivery_task_id=expected_delivery_task,
                    )
                if dirty_after or operations_after:
                    return self._canonical_refresh_payload(
                        "BLOCKED",
                        old_sha=old_sha,
                        new_sha=new_sha,
                        origin_sha=origin_after,
                        live_sha=live_after,
                        ahead_before=ahead_before,
                        behind_before=behind_before,
                        ahead_after=0,
                        behind_after=0,
                        updated_commits=behind_before,
                        mutation_performed=changed,
                        reason="canonical worktree changed during canonical master update",
                        recovery_hint="Preserve the change, resolve the worktree or Git operation owner-safely, then retry.",
                        delivery_task_id=expected_delivery_task,
                    )
                return self._canonical_refresh_payload(
                    "REFRESHED",
                    old_sha=old_sha,
                    new_sha=new_sha,
                    origin_sha=origin_after,
                    live_sha=live_after,
                    ahead_before=ahead_before,
                    behind_before=behind_before,
                    ahead_after=0,
                    behind_after=0,
                    updated_commits=behind_before,
                    mutation_performed=changed,
                    reason="canonical master was fast-forwarded to the verified protected master",
                    recovery_hint="No recovery is required.",
                    delivery_task_id=expected_delivery_task,
                )
        except TaskSessionError as error:
            if str(error).startswith("Coordination state is locked:"):
                return self._canonical_refresh_after_contention(
                    offline=offline, delivery_task_id=expected_delivery_task
                )
            return self._canonical_refresh_payload(
                "BLOCKED",
                reason="canonical refresh controller state could not be validated safely",
                recovery_hint="Inspect the controller state and active Git operation without deleting or resetting it, then retry.",
                delivery_task_id=expected_delivery_task,
            )
        except OSError:
            return self._canonical_refresh_payload(
                "BLOCKED",
                reason="canonical refresh filesystem operation failed safely",
                recovery_hint="Resolve the filesystem/permission issue without changing refs, then retry.",
                delivery_task_id=expected_delivery_task,
            )

    def _completed_dependency_ids(self) -> set[str]:
        roots = (
            self._canonical_root() / "codex-backlog" / "tasks" / "done",
            self._canonical_root() / "codex-backlog" / "bugs" / "done",
            self._canonical_root()
            / "codex-backlog"
            / "telegram-core-release-backlog"
            / "tasks"
            / "done",
        )
        result: set[str] = set()
        for root in roots:
            if root.is_dir():
                for path in root.glob("*.md"):
                    match = TASK_FILE_RE.fullmatch(path.name)
                    if match:
                        task_id = match.group("task_id").upper()
                        lease = self.store.read_json(self.store.task_lease_path(task_id))
                        if (
                            isinstance(lease, dict)
                            and self._lease_state(lease) in SUPERSEDED_LEASE_STATES
                        ):
                            continue
                        result.add(task_id)
        return result

    @staticmethod
    def _lease_state(lease: Mapping[str, Any]) -> str:
        return str(lease.get("lifecycle_state", "")).strip().lower()

    @classmethod
    def _is_active_write_lease(cls, lease: Mapping[str, Any]) -> bool:
        return lease.get("mode") == "write" and cls._lease_state(lease) not in CLOSED_LEASE_STATES

    @classmethod
    def _validated_lease_concurrency_class(cls, lease: Mapping[str, Any]) -> str:
        task_id = str(lease.get("task_id", "")).upper() or "<unknown>"
        raw_class = lease.get("concurrency_class")
        if not isinstance(raw_class, str) or not raw_class.strip():
            raise TaskSessionError(
                f"Task {task_id} lease has missing concurrency class; recovery is required"
            )
        try:
            return normalize_concurrency_class(raw_class)
        except TaskSessionError as error:
            raise TaskSessionError(
                f"Task {task_id} lease has invalid concurrency class {raw_class!r}; "
                "recovery is required"
            ) from error

    @classmethod
    def _lease_holds_implementation_exclusion(cls, lease: Mapping[str, Any]) -> bool:
        # ``exclusive-write`` is retained in old leases as metadata only.  A task lease owns its
        # worktree, not the repository's implementation lane; serial delivery is the only global
        # write boundary.  Keep this helper for status/backward compatibility with older state.
        if lease.get("mode") == "write":
            cls._validated_lease_concurrency_class(lease)
        return False

    @classmethod
    def _validate_lease_concurrency_classes(cls, leases: Sequence[Mapping[str, Any]]) -> None:
        for lease in leases:
            if lease.get("mode") == "write":
                cls._validated_lease_concurrency_class(lease)

    @classmethod
    def _lease_ownership_snapshot(
        cls, lease: Mapping[str, Any], *, delivery_owner_id: str
    ) -> dict[str, bool]:
        task_session_active = lease.get("mode") == "write" and (
            cls._lease_state(lease) not in SUPERSEDED_LEASE_STATES
        )
        try:
            implementation_exclusion_active = cls._lease_holds_implementation_exclusion(lease)
        except TaskSessionError:
            # Status/doctor output must remain useful for recovery, while malformed state is
            # conservatively represented as holding the implementation boundary.
            implementation_exclusion_active = task_session_active
        task_id = str(lease.get("task_id", "")).upper()
        return {
            "task_session_active": task_session_active,
            "implementation_exclusion_active": implementation_exclusion_active,
            "delivery_critical_section_active": bool(task_id and task_id == delivery_owner_id),
        }

    @classmethod
    def _lease_snapshots(
        cls, leases: Sequence[Mapping[str, Any]], delivery: Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        owner = delivery.get("owner")
        delivery_owner_id = (
            str(owner.get("task_id", "")).upper() if isinstance(owner, Mapping) else ""
        )
        return [
            {
                **dict(lease),
                "ownership": cls._lease_ownership_snapshot(
                    lease, delivery_owner_id=delivery_owner_id
                ),
            }
            for lease in leases
        ]

    @classmethod
    def _implementation_lease_conflicts(
        cls,
        leases: Sequence[Mapping[str, Any]],
        *,
        task_id: str,
        concurrency_class: str,
    ) -> list[dict[str, Any]]:
        normalize_concurrency_class(concurrency_class)
        conflicts: list[dict[str, Any]] = []
        for lease in leases:
            if lease.get("mode") != "write":
                continue
            if str(lease.get("task_id", "")).upper() == task_id.upper():
                continue
            cls._validated_lease_concurrency_class(lease)
            state = cls._lease_state(lease)
            if state not in KNOWN_LEASE_STATES:
                raise TaskSessionError(
                    f"Task {str(lease.get('task_id', '')).upper() or '<unknown>'} lease has "
                    f"ambiguous lifecycle state {state or '<missing>'}; recovery is required"
                )
            if state in RECOVERY_STATES:
                raise TaskSessionError(
                    f"Task {str(lease.get('task_id', '')).upper() or '<unknown>'} lease "
                    "requires controller recovery"
                )
            # The class is deliberately not used as a repository-wide lock.  Distinct task
            # worktrees have distinct mutable ownership; real file conflicts are discovered by
            # the serialized refresh/rebase/finalization path.  The state validation above still
            # fails closed for malformed or recovery-required leases.
        return conflicts

    @classmethod
    def _delivery_candidates(cls, leases: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        cls._validate_lease_concurrency_classes(leases)
        candidates = [
            dict(lease)
            for lease in leases
            if lease.get("mode") == "write"
            and cls._lease_state(lease) in READY_STATES | WAITING_STATES
        ]

        def queue_key(lease: Mapping[str, Any]) -> tuple[int, str, str]:
            sequence = lease.get("ready_sequence")
            if isinstance(sequence, int) and sequence >= 0:
                return (0, f"{sequence:020d}", str(lease.get("task_id", "")))
            return (
                1,
                str(
                    lease.get("ready_for_delivery_at")
                    or lease.get("updated_at")
                    or lease.get("created_at")
                    or ""
                ),
                str(lease.get("task_id", "")),
            )

        return sorted(candidates, key=queue_key)

    def _promote_next_delivery_locked(
        self,
        delivery: dict[str, Any],
        *,
        requested_task_id: str | None = None,
        priority_override: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if delivery.get("owner") is not None:
            return dict(delivery["owner"])
        delivery.pop("priority_override", None)
        candidates = self._delivery_candidates(self.store.all_leases())
        if not candidates:
            return None
        if requested_task_id is None:
            candidate = candidates[0]
        else:
            expected = normalize_task_id(requested_task_id)
            candidate = next(
                (
                    item
                    for item in candidates
                    if normalize_task_id(str(item["task_id"])) == expected
                ),
                None,
            )
            if candidate is None:
                raise TaskSessionError(
                    f"Requested delivery priority task {expected} is not a queue candidate"
                )
        task_id = normalize_task_id(str(candidate["task_id"]))
        lease_path = self.store.task_lease_path(task_id)
        lease = self.store.read_json(lease_path)
        if not isinstance(lease, dict):
            raise TaskSessionError(f"Delivery queue lease is missing or invalid for Task {task_id}")
        now = utc_now()
        owner = {
            "task_id": task_id,
            "acquired_at": now,
            "lease_updated_at": now,
        }
        lease.update(
            {
                "lifecycle_state": "delivering",
                "delivery_acquired_at": now,
                "delivery_owner": task_id,
                "updated_at": now,
            }
        )
        delivery["owner"] = owner
        if priority_override is not None:
            delivery["priority_override"] = dict(priority_override)
        delivery["updated_at"] = now
        StateStore.replace_json(lease_path, lease)
        StateStore.replace_json(self.store.delivery_path, delivery)
        return owner

    def _require_delivery_owner(self, task_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        expected = normalize_task_id(task_id)
        lease = self.store.read_json(self.store.task_lease_path(expected))
        if not isinstance(lease, dict):
            raise TaskSessionError(f"Task {expected} has no active lease")
        delivery = self.store.delivery_state()
        owner = delivery.get("owner")
        if not isinstance(owner, dict) or str(owner.get("task_id", "")).upper() != expected:
            owner_id = owner.get("task_id") if isinstance(owner, dict) else None
            raise TaskSessionError(
                f"Task {expected} does not own the delivery lane"
                + (f"; owner is Task {owner_id}" if owner_id else "")
            )
        return lease, delivery

    def _active_production_deployment(self) -> bool:
        try:
            runs = self._github().active_workflow_runs()
        except TaskSessionError as error:
            raise TaskSessionError(f"Cannot verify production delivery state: {error}") from error
        return any(item.get("name") in {"Release production", "Deploy production"} for item in runs)

    def _verify_live_master(self, expected_sha: str) -> None:
        live_master = self._github().branch_head(TARGET_BASE_BRANCH)
        if live_master != expected_sha:
            raise TaskSessionError(
                "origin/master is not the live protected master: "
                f"tracking={expected_sha}; live={live_master}; refresh again"
            )

    def doctor(self, *, offline: bool = False) -> dict[str, Any]:
        root = self._canonical_root()
        implementation_blockers: list[str] = []
        delivery_blockers: list[str] = []
        recovery_findings: list[str] = []
        informational_findings: list[str] = []
        dirty = self._canonical_worktree_status(root)
        if dirty:
            implementation_blockers.append("controller worktree is dirty")
        operations = self.repository.operation_issues(root)
        if operations:
            implementation_blockers.append(
                f"controller worktree has active Git operation/lock: {', '.join(operations)}"
            )
        try:
            local_master = self.repository.ref("master")
            origin_master = self.repository.ref("origin/master")
        except TaskSessionError as error:
            implementation_blockers.append(str(error))
            local_master = origin_master = "unknown"
        else:
            if local_master != origin_master:
                ahead, behind = self.repository.ahead_behind("master", "origin/master")
                if ahead > 0:
                    implementation_blockers.append(
                        "canonical master contains unpublished commits: "
                        f"ahead={ahead} behind={behind}; preserve them and resolve master divergence"
                    )
                elif behind > 0:
                    informational_findings.append(
                        "local master is behind origin/master: "
                        f"ahead={ahead} behind={behind}; task bases use origin/master"
                    )
                else:
                    recovery_findings.append(
                        f"local master differs from origin/master unexpectedly: ahead={ahead} behind={behind}"
                    )
        leases: list[dict[str, Any]] = []
        try:
            leases = self.store.all_leases()
        except TaskSessionError as error:
            implementation_blockers.append(str(error))
        try:
            delivery = self.store.delivery_state()
        except TaskSessionError as error:
            implementation_blockers.append(str(error))
            delivery = {"version": DELIVERY_STATE_VERSION, "next_sequence": 0, "owner": None}
        owner = delivery.get("owner")
        if isinstance(owner, dict):
            owner_id = str(owner.get("task_id", "")).upper()
            owner_lease = next(
                (item for item in leases if str(item.get("task_id", "")).upper() == owner_id),
                None,
            )
            if owner_lease is None:
                recovery_findings.append(
                    f"delivery lane owner Task {owner_id} has no lease; recovery is required"
                )
            elif self._lease_state(owner_lease) not in DELIVERY_OWNER_STATES:
                recovery_findings.append(
                    f"delivery lane owner Task {owner_id} has incompatible state "
                    f"{self._lease_state(owner_lease)}"
                )
            else:
                delivery_blockers.append(f"delivery lane is occupied by Task {owner_id}")
        delivery_owner_id = str(owner.get("task_id", "")).upper() if isinstance(owner, dict) else ""
        for item in leases:
            item_id = str(item.get("task_id", "")).upper()
            if self._lease_state(item) in DELIVERY_OWNER_STATES and item_id != delivery_owner_id:
                recovery_findings.append(
                    f"Task {item_id} is in delivery state without matching delivery ownership; "
                    "recovery is required"
                )
        try:
            coordination_blocker = self._canonical_refresh_controller_blocker(delivery_task_id=None)
        except TaskSessionError as error:
            implementation_blockers.append(f"coordination state validation failed: {error}")
        else:
            if coordination_blocker and coordination_blocker[0] == "BLOCKED":
                implementation_blockers.append(
                    f"coordination state is fail-closed: {coordination_blocker[1]}"
                )
        active_runs: list[dict[str, Any]] | str = "offline"
        open_task_prs: list[dict[str, Any]] | str = "offline"
        rulesets: list[dict[str, Any]] | str = "offline"
        live_master = "offline"
        if not offline:
            try:
                live_master = self._github().branch_head(TARGET_BASE_BRANCH)
                if live_master != origin_master:
                    delivery_blockers.append(
                        "local origin/master is stale: "
                        f"tracking={origin_master}; live={live_master}; fetch current master"
                    )
                open_task_prs = [
                    {
                        "number": item.get("number"),
                        "title": item.get("title"),
                        "head": item.get("head", {}).get("ref"),
                        "base": item.get("base", {}).get("ref"),
                    }
                    for item in self._github().open_pull_requests()
                    if str(item.get("head", {}).get("ref", "")).startswith("task/")
                ]
                active_runs = [
                    {
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "event": item.get("event"),
                        "head_branch": item.get("head_branch"),
                        "head_sha": item.get("head_sha"),
                        "status": item.get("status"),
                    }
                    for item in self._github().active_workflow_runs()
                ]
                if any(
                    item.get("name") in {"Release production", "Deploy production"}
                    for item in active_runs
                ):
                    delivery_blockers.append(
                        "active production deployment occupies the delivery lane; "
                        "compatible implementation remains allowed"
                    )
                rulesets = [
                    {
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "target": item.get("target"),
                        "enforcement": item.get("enforcement"),
                        "conditions": item.get("conditions"),
                        "rules": item.get("rules"),
                        "bypass_actors": item.get("bypass_actors"),
                    }
                    for item in self._github().rulesets()
                ]
                delivery_blockers.extend(validate_master_ruleset(rulesets))
            except TaskSessionError as error:
                delivery_blockers.append(f"GitHub state unavailable: {error}")
                active_runs = open_task_prs = rulesets = "unavailable"
        active_task_ids = {
            item.get("task_id")
            for item in leases
            if item.get("mode") == "write"
            and self._lease_state(item) not in SUPERSEDED_LEASE_STATES
        }
        if any(item.get("mode") in {"integration", "release"} for item in leases):
            recovery_findings.append(
                "obsolete integration/release lease requires explicit recovery"
            )
        inventory: list[dict[str, Any]] = []
        for worktree in self.repository.worktrees():
            status = self.repository.status(worktree.path)
            operation_issues = self.repository.operation_issues(worktree.path)
            task_id = None
            if worktree.branch and TASK_BRANCH_RE.fullmatch(worktree.branch):
                task_id = task_id_from_branch(worktree.branch)
            unique = (
                self.repository.unique_commits(worktree.branch)
                if worktree.branch and worktree.branch not in {"master", "dev"}
                else self.repository.detached_unique_commits(worktree.path)
                if worktree.detached
                else []
            )
            classification = "ACTIVE" if task_id in active_task_ids else "SAFE_TO_REMOVE"
            if status or operation_issues:
                classification = "DIRTY_NEEDS_OWNER"
                if task_id:
                    recovery_findings.append(
                        f"Task {task_id} worktree is dirty or interrupted; recovery is required"
                    )
            elif unique:
                classification = "RECOVERY_ANCHOR"
            elif worktree.branch == "dev":
                classification = "LEGACY_NOT_NORMAL"
            inventory.append(
                {
                    "path": str(worktree.path),
                    "branch": worktree.branch,
                    "head": worktree.head,
                    "detached": worktree.detached,
                    "dirty": status,
                    "unique_commits_count": len(unique),
                    "unique_commits_preview": unique[:5],
                    "classification": classification,
                }
            )
        if self.store.lock_path.exists():
            implementation_blockers.append("coordination state lock exists; recovery is required")
        issues = list(implementation_blockers)
        return {
            "ok": not implementation_blockers,
            "safe_for_implementation": not implementation_blockers,
            "canonical_worktree": str(root),
            "current_worktree": str(self.repository.current_worktree),
            "git_common_dir": str(self.repository.common_dir),
            "refs": {
                "master": local_master,
                "origin/master": origin_master,
                "live/master": live_master,
            },
            "leases": self._lease_snapshots(leases, delivery),
            "open_task_prs": open_task_prs,
            "active_workflow_runs": active_runs,
            "rulesets": rulesets,
            "inventory": inventory,
            "delivery": delivery,
            "issues": issues,
            "implementation_blockers": implementation_blockers,
            "delivery_blockers": delivery_blockers,
            "recovery_findings": recovery_findings,
            "informational_findings": informational_findings,
        }

    def status(self) -> dict[str, Any]:
        delivery = self.store.delivery_state()
        leases = self.store.all_leases()
        return {
            "state_root": str(self.store.root),
            "leases": self._lease_snapshots(leases, delivery),
            "delivery": delivery,
            "history": sorted(path.name for path in self.store.history.glob("*.json"))
            if self.store.history.exists()
            else [],
        }

    def validate_metadata(self) -> dict[str, Any]:
        roots = (
            self._canonical_root() / "codex-backlog" / "tasks",
            self._canonical_root() / "codex-backlog" / "bugs" / "pending",
            self._canonical_root() / "codex-backlog" / "telegram-core-release-backlog" / "tasks",
        )
        records: list[dict[str, Any]] = []
        errors: list[str] = []
        task_ids: list[str] = []
        for root in roots:
            if not root.is_dir():
                continue
            for path in sorted(root.glob("*.md")):
                match = TASK_FILE_RE.fullmatch(path.name)
                if match is None:
                    continue
                task_id = match.group("task_id").upper()
                task_ids.append(task_id)
                try:
                    document = find_task_document(self._canonical_root(), task_id)
                except TaskSessionError as error:
                    errors.append(str(error))
                    continue
                source_text = document.path.read_text(encoding="utf-8")
                records.append(
                    {
                        "task_id": document.task_id,
                        "canonical_task_path": str(document.path),
                        "dependencies": list(document.dependencies),
                        "executable": document.executable,
                        "concurrency_class": document.concurrency_class,
                        "owner_gate": document.owner_gate,
                        "integration_policy": document.integration_policy,
                        "metadata_source": "task-session-block"
                        if _metadata_block(source_text)
                        else "legacy-inferred",
                    }
                )
        errors.extend(
            f"Duplicate pending task ID: {task_id}"
            for task_id in sorted({item for item in task_ids if task_ids.count(item) > 1})
        )
        return {"ok": not errors, "tasks": records, "errors": errors}

    def start(
        self,
        task_id: str,
        *,
        owner_launch: bool,
        session_label: str,
        mode: str = "write",
        slug: str | None = None,
        dependency_ids: Sequence[str] | None = None,
        offline: bool = False,
        queue_mode: bool = False,
    ) -> dict[str, Any]:
        expected = normalize_task_id(task_id)
        if not owner_launch:
            raise TaskSessionError("start requires explicit --owner-launch evidence")
        if mode != "write":
            raise TaskSessionError("research-readonly sessions are not part of normal delivery")
        canonical_refresh = self.refresh_canonical_master(offline=offline)
        if canonical_refresh["result"] == "BLOCKED":
            raise TaskSessionError(
                f"Task {expected} blocked by canonical master refresh: "
                f"{canonical_refresh['reason']}; {canonical_refresh['recovery_hint']}"
            )
        if canonical_refresh["result"] == "WAITING" and canonical_refresh["reason"] == (
            "another controller operation owns the coordination lock"
        ):
            raise TaskSessionError(
                "Coordination state is locked during canonical master refresh; retry start"
            )
        if canonical_refresh["result"] == "WAITING" and not offline:
            # A busy delivery/production lane may still allow a compatible implementation
            # lease. Keep the historical current-base fetch for that non-mutating path; the
            # lease acquisition below rechecks the fetched tracking SHA against live master.
            self.repository.fetch_origin_master()
        report = self.doctor(offline=offline)
        if report["implementation_blockers"]:
            raise TaskSessionError(
                "implementation/start blockers: " + "; ".join(report["implementation_blockers"])
            )
        document = find_task_document(self._canonical_root(), expected)
        if not document.executable:
            raise TaskSessionError(f"Task {expected} is umbrella/non-executable")
        if "blocked" in document.status.lower() or "заблок" in document.status.lower():
            raise TaskSessionError(f"Task {expected} status is blocked: {document.status}")
        owner_gate = document.owner_gate.strip()
        if owner_gate.lower() not in {"", "explicit-launch", "owner-launch", "none"}:
            label, _, requirement = owner_gate.partition(":")
            gate_name = label.strip().upper().replace("-", "_")
            concrete_requirement = requirement.strip() or "the task-declared evidence"
            raise TaskSessionError(
                f"Task {expected} blocked: {gate_name} is missing: {concrete_requirement}"
            )
        resolved_dependencies = _resolved_dependency_ids(dependency_ids, document.dependencies)
        missing = sorted(set(resolved_dependencies) - self._completed_dependency_ids())
        if missing:
            raise TaskSessionError(
                f"Task {expected} has incomplete dependencies: {', '.join(missing)}"
            )
        branch = f"task/{expected}-{slug or document.slug}"
        task_id_from_branch(branch)
        target = self._canonical_root() / ".artifacts" / "worktrees" / branch.removeprefix("task/")
        if target.exists() or self.repository.ref_exists(f"refs/heads/{branch}"):
            raise TaskSessionError(f"Ambiguous existing branch/worktree for {branch}")
        self.store.initialize()
        lease_path = self.store.task_lease_path(expected)
        with self.store.lock():
            existing = self.store.all_leases()
            if any(item.get("task_id") == expected for item in existing):
                raise TaskSessionError(f"Task {expected} already has an active lease")
            if target.exists() or self.repository.ref_exists(f"refs/heads/{branch}"):
                raise TaskSessionError(f"Ambiguous existing branch/worktree for {branch}")
            conflicts = self._implementation_lease_conflicts(
                existing,
                task_id=expected,
                concurrency_class=document.concurrency_class,
            )
            if conflicts:
                occupied = ", ".join(
                    f"Task {item['task_id']} ({item['concurrency_class']}, {item['lifecycle_state']})"
                    for item in conflicts
                )
                raise TaskSessionError(
                    f"Task {expected} blocked by incompatible implementation write lease(s): {occupied}"
                )
            base_sha = self.repository.ref("origin/master")
            if not offline and self._github().branch_head(TARGET_BASE_BRANCH) != base_sha:
                raise TaskSessionError("origin/master changed while start was acquiring its lease")
            lease = {
                "version": TASK_STATE_VERSION,
                "task_id": expected,
                "canonical_task_path": str(document.path),
                "branch": branch,
                "worktree": str(target.resolve()),
                "base_origin_master_sha": base_sha,
                "original_base_origin_master_sha": base_sha,
                "target_base_branch": TARGET_BASE_BRANCH,
                "mode": "write",
                "created_at": utc_now(),
                "updated_at": utc_now(),
                "lifecycle_state": "starting",
                "session_label": session_label,
                "concurrency_class": document.concurrency_class,
                "integration_policy": "task-pr-to-master",
                "dependency_ids": list(resolved_dependencies),
                "dependency_source": "github-issue" if dependency_ids is not None else "task-spec",
                "owner_launch": True,
                "canonical_master_refresh": canonical_refresh,
            }
            if queue_mode:
                lease["queue_mode"] = True
                lease["queue_budget"] = {
                    "review_fix_cycles": 0,
                    "ci_fix_cycles": 0,
                    "scope_expansions": 0,
                    "events": [],
                }
            self.store.create_json(lease_path, lease)
        try:
            self.repository.create_task_worktree(branch, target, base_sha)
        except Exception:
            lease["lifecycle_state"] = "start-failed-recovery-required"
            lease["updated_at"] = utc_now()
            StateStore.replace_json(lease_path, lease)
            raise
        lease["lifecycle_state"] = "implementation"
        lease["updated_at"] = utc_now()
        StateStore.replace_json(lease_path, lease)
        return {
            "lease": lease,
            "canonical_master_refresh": canonical_refresh,
            "prompt": (
                f"Worktree: {target.resolve()}\nBranch: {branch}\n"
                f"Base origin/master: {base_sha}\nTask: {expected} ({document.path})\n"
                f"Dependencies ({'Issue' if dependency_ids is not None else 'task spec'} source): "
                f"{', '.join(resolved_dependencies) or 'none'}\n"
                f"Canonical master checkpoint: {canonical_refresh['result']}\n"
                "Concurrency: missing task concurrency metadata defaults to independent-write; "
                "legacy exclusive-write metadata does not block another task's separate worktree. "
                "Task/worktree ownership is scoped; final refresh, CI and merge use the "
                "serial delivery lane.\n"
                "Normal path: targeted checks/self-review/QA/commit -> push task branch -> PR master\n"
                "-> GitHub exact-head checks -> merge -> exact-SHA production deployment.\n"
                "Local checks are fast feedback only; they do not create release evidence or decide\n"
                "whether the PR may merge. Implementation may run in parallel with compatible tasks.\n"
                "Delivery ownership is coordination bookkeeping for the serialized PR/merge/deploy\n"
                "lane; before merge it only refreshes the branch anchor and never replaces GitHub CI.\n"
                "Do not merge or push master directly.\n"
                f"Recovery: python scripts/task_session.py recover {expected}\n"
            ),
        }

    def _preimplementation_issue_state(
        self,
        task_id: str,
        issue_number: int,
        branch: str,
        document: TaskDocument,
        lease: Mapping[str, Any],
        *,
        allow_cli_preflight_failure: bool = False,
        allow_guard_budget_failure: bool = False,
        allow_transport_failure: bool = False,
    ) -> dict[str, Any]:
        github = self._github()
        owner = normalize_github_login(github.repo_slug.split("/", maxsplit=1)[0])
        if not owner:
            raise TaskSessionError("Cannot establish the repository owner for resume authorization")
        issue = github.api(f"issues/{issue_number}")
        if not isinstance(issue, Mapping) or issue.get("number") != issue_number:
            raise TaskSessionError("Resume requires the matching task Issue")
        if "pull_request" in issue:
            raise TaskSessionError(
                "Resume control reference must be a task Issue, not a pull request"
            )
        author = issue.get("user")
        if (
            not isinstance(author, Mapping)
            or normalize_github_login(str(author.get("login", ""))) != owner
        ):
            raise TaskSessionError("Task Issue must be authored by the repository owner")
        if str(issue.get("state", "")).lower() != "open":
            raise TaskSessionError("Resume requires the matching open control Issue")
        issue_body = str(issue.get("body", ""))
        try:
            contract = parse_task_contract(issue_body)
        except IssueWorkflowError as error:
            if str(error) != "Task contract requires scope and source_spec":
                raise TaskSessionError(
                    f"Task {task_id} Issue contract is malformed: {error}"
                ) from error
            contract = self._legacy_preimplementation_issue_contract(
                issue_body, task_id=task_id, document=document
            )
        if contract is None or contract.get("task_id") != task_id:
            raise TaskSessionError("Task Issue has no matching machine-readable contract")
        expected_source = document.path.resolve().relative_to(self._canonical_root()).as_posix()
        if contract.get("source_spec") != expected_source:
            raise TaskSessionError("Task Issue source does not match the registered task document")
        try:
            issue_dependencies = _resolved_dependency_ids(
                contract.get("dependencies"), document.dependencies
            )
        except TaskSessionError as error:
            raise TaskSessionError(f"Task Issue dependency contract is invalid: {error}") from error
        document_dependencies = tuple(
            dict.fromkeys(normalize_task_id(item) for item in document.dependencies)
        )
        lease_dependencies = lease.get("dependency_ids")
        if (
            issue_dependencies != document_dependencies
            or not isinstance(lease_dependencies, list)
            or tuple(lease_dependencies) != document_dependencies
        ):
            raise TaskSessionError("Task dependency contract changed since the lease was created")
        owner_gate = str(contract.get("owner_gate", ""))
        if contract.get("risk_lane") == "RED" or task_risk_lane(owner_gate) == "RED":
            raise TaskSessionError(
                "Task Issue owner gate requires a separate human or external gate"
            )
        missing_dependencies = sorted(set(issue_dependencies) - self._completed_dependency_ids())
        if missing_dependencies:
            raise TaskSessionError(
                "Task has incomplete dependencies: " + ", ".join(missing_dependencies)
            )
        try:
            state = latest_control_state(
                github.issue_comments(issue_number),
                task_id=task_id,
                authorized_logins=(owner,),
            )
        except IssueWorkflowError as error:
            raise TaskSessionError(f"Task control state is malformed: {error}") from error
        if state is None or state.get("state") not in {"human_required", "blocked"}:
            raise TaskSessionError(
                "Resume requires the latest owner-authorized human_required or verified CLI failure state"
            )
        blocker = state.get("blocker")
        blocker_text = blocker.lower() if isinstance(blocker, str) else ""
        if state.get("issue_number") != issue_number:
            raise TaskSessionError(
                "Latest control state Issue identity does not match the task Issue"
            )
        if state.get("branch") != branch:
            raise TaskSessionError("Latest control state branch does not match the task lease")
        common_failure = state.get("pr_number") is None and state.get("head_sha") is None
        valid_human_required = (
            state.get("state") == "human_required"
            and "before implementation" in blocker_text
            and any(
                token in blocker_text for token in ("bootstrap", "worker-state", "worker state")
            )
        )
        valid_cli_failure = (
            allow_cli_preflight_failure
            and state.get("state") == "blocked"
            and blocker_text == "worker exited with code 2"
        )
        valid_guard_failure = (
            allow_guard_budget_failure
            and state.get("state") == "blocked"
            and isinstance(blocker, str)
            and re.fullmatch(
                r"worker guard blocked execution \(TOOL_ACTION_BUDGET_EXCEEDED\); inspect .+",
                blocker,
                flags=re.IGNORECASE,
            )
        )
        valid_guard_recovery_handoff = (
            allow_guard_budget_failure
            and state.get("state") == "human_required"
            and blocker == GUARD_RECOVERY_HANDOFF_BLOCKER
        )
        valid_transport_failure = (
            allow_transport_failure
            and state.get("state") in {"blocked", "human_required"}
            and isinstance(blocker, str)
            and (
                POST_START_TRANSPORT_FAILURE_KIND in blocker
                or (
                    "Codex worker turn failed while reconnecting to the API" in blocker
                    and "os error" in blocker
                )
            )
        )
        valid_transport_recovery_handoff = (
            allow_transport_failure
            and state.get("state") == "human_required"
            and blocker == POST_START_TRANSPORT_HANDOFF_BLOCKER
        )
        if not common_failure or not (
            valid_human_required
            or valid_cli_failure
            or valid_guard_failure
            or valid_guard_recovery_handoff
            or valid_transport_failure
            or valid_transport_recovery_handoff
        ):
            raise TaskSessionError(
                "Latest control state is not a matching pre-implementation failure"
            )
        return state

    def _legacy_preimplementation_issue_contract(
        self,
        body: str,
        *,
        task_id: str,
        document: TaskDocument,
    ) -> dict[str, Any]:
        parts = body.split(TASK_CONTRACT_MARKER)
        if len(parts) != 3:
            raise TaskSessionError("Legacy task Issue contract markers are malformed")
        try:
            payload = json.loads(parts[1].strip())
        except json.JSONDecodeError as error:
            raise TaskSessionError("Legacy task Issue contract JSON is malformed") from error
        if not isinstance(payload, Mapping) or set(payload) != {
            "version",
            "scope",
            "owner_gate",
            "risk_lane",
            "issue_state",
        }:
            raise TaskSessionError("Legacy task Issue contract fields are incomplete or unknown")
        scope = payload.get("scope")
        owner_gate = payload.get("owner_gate")
        risk_lane = payload.get("risk_lane")
        issue_state = payload.get("issue_state")
        if (
            payload.get("version") != 1
            or not isinstance(scope, str)
            or not scope.strip()
            or len(scope.strip()) > 8192
            or not isinstance(owner_gate, str)
            or not owner_gate.strip()
            or not isinstance(risk_lane, str)
            or risk_lane.strip().upper() not in {"GREEN", "YELLOW", "RED"}
            or not isinstance(issue_state, str)
            or issue_state.strip().lower() not in CONTROL_STATES
        ):
            raise TaskSessionError("Legacy task Issue contract values are invalid")
        normalized_owner_gate = owner_gate.strip()
        normalized_risk_lane = risk_lane.strip().upper()
        risk_rank = {"GREEN": 0, "YELLOW": 1, "RED": 2}
        if risk_rank[normalized_risk_lane] < risk_rank[task_risk_lane(normalized_owner_gate)]:
            raise TaskSessionError(
                "Legacy task Issue contract risk lane is weaker than its owner gate"
            )
        expected_source = document.path.resolve().relative_to(self._canonical_root()).as_posix()
        return {
            "version": 1,
            "task_id": task_id,
            "scope": scope.strip(),
            "acceptance": [],
            "dependencies": list(document.dependencies),
            "owner_gate": normalized_owner_gate,
            "risk_lane": normalized_risk_lane,
            "source_spec": expected_source,
            "issue_state": issue_state.strip().lower(),
        }

    def _preimplementation_worker_state_paths(self, task_id: str) -> list[Path]:
        delivery_root = (
            self._canonical_root() / ".artifacts" / "tasks" / task_id / "temporary" / "delivery"
        )
        return sorted(delivery_root.rglob("worker-state.json")) if delivery_root.is_dir() else []

    def _preimplementation_cli_failure_evidence(
        self, task_id: str, event: Mapping[str, Any]
    ) -> dict[str, Any]:
        failure_kind = "codex_cli_argument_conflict_before_implementation"
        error_text = (
            "the argument '--approve-for-me' cannot be used with '--sandbox <SANDBOX_MODE>'"
        )
        attempts = event.get("launch_attempts")
        if not isinstance(attempts, list) or not attempts:
            raise TaskSessionError("Codex CLI startup failure has no launch-attempt audit")
        reconciled = [
            item
            for item in attempts
            if isinstance(item, Mapping) and item.get("state") == "failed-before-implementation"
        ]
        if len(reconciled) > 1:
            raise TaskSessionError("Codex CLI startup retry budget was already used")

        if event.get("state") == "worker-started":
            if reconciled:
                raise TaskSessionError("Codex CLI startup retry budget was already used")
            attempt = attempts[-1]
            if not isinstance(attempt, Mapping) or attempt.get("state") != "worker-started":
                raise TaskSessionError("Codex CLI startup failure launch audit is inconsistent")
            if any(
                not isinstance(item, Mapping) or item.get("state") != "no-worker-started"
                for item in attempts[:-1]
            ):
                raise TaskSessionError("Codex CLI startup failure launch audit is ambiguous")
        elif event.get("state") == "prepared":
            failure = event.get("last_preimplementation_failure")
            launch_id = failure.get("launch_id") if isinstance(failure, Mapping) else None
            attempt = next(
                (
                    item
                    for item in attempts
                    if isinstance(item, Mapping) and item.get("launch_id") == launch_id
                ),
                None,
            )
            if (
                not isinstance(failure, Mapping)
                or failure.get("kind") != failure_kind
                or len(reconciled) != 1
                or not isinstance(attempt, Mapping)
                or attempt.get("state") != "failed-before-implementation"
                or attempt.get("failure_kind") != failure_kind
                or attempt.get("worker_exit_code") != 2
                or failure.get("worker_exit_code") != 2
            ):
                raise TaskSessionError("Codex CLI startup retry audit is invalid")
        else:
            raise TaskSessionError("Task has no reconcilable Codex CLI startup failure")

        worker_pid = attempt.get("worker_pid")
        worker_state_value = attempt.get("worker_state_path")
        if (
            isinstance(worker_pid, bool)
            or not isinstance(worker_pid, int)
            or worker_pid < 1
            or not isinstance(worker_state_value, str)
            or not Path(worker_state_value).is_absolute()
            or (event.get("state") == "worker-started" and event.get("worker_pid") != worker_pid)
        ):
            raise TaskSessionError("Codex CLI startup failure has malformed worker identity")
        if self.store._pid_is_alive(worker_pid):
            raise TaskSessionError("Codex worker process is still live")

        delivery_root = (
            self._canonical_root() / ".artifacts" / "tasks" / task_id / "temporary" / "delivery"
        ).resolve()
        worker_state_path = Path(worker_state_value).resolve()
        try:
            worker_state_path.relative_to(delivery_root)
        except ValueError as error:
            raise TaskSessionError(
                "Codex worker state path is outside task delivery artifacts"
            ) from error
        if worker_state_path.name != "worker-state.json" or worker_state_path.exists():
            raise TaskSessionError("Codex worker state has not been fully reconciled")
        if self._preimplementation_worker_state_paths(task_id):
            raise TaskSessionError("Task has unreconciled worker state")

        events_path = worker_state_path.with_name("events.jsonl")
        guard_path = worker_state_path.with_name("worker-guard.json")
        try:
            if events_path.stat().st_size > 1024 * 1024 or guard_path.stat().st_size > 64 * 1024:
                raise TaskSessionError("Codex CLI startup failure evidence exceeds its size limit")
            events = events_path.read_text(encoding="utf-8")
            guard = json.loads(guard_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise TaskSessionError(
                "Codex CLI startup failure evidence is missing or unreadable"
            ) from error
        counters = guard.get("counters") if isinstance(guard, Mapping) else None
        zero_counters = (
            "completed_tool_actions",
            "collab_tool_calls",
            "spawned_subagents",
            "max_observed_concurrent_subagents",
            "progress_events",
        )
        if (
            not isinstance(guard, Mapping)
            or guard.get("schema_version") != 1
            or guard.get("classification") != "yfc-worker-guard-report"
            or guard.get("blocked") is not False
            or guard.get("block_reason_code") is not None
            or not isinstance(counters, Mapping)
            or any(
                isinstance(counters.get(name), bool)
                or not isinstance(counters.get(name), int)
                or counters.get(name) != 0
                for name in zero_counters
            )
            or isinstance(counters.get("malformed_lines"), bool)
            or not isinstance(counters.get("malformed_lines"), int)
            or counters.get("malformed_lines", -1) < 0
            or error_text not in events
        ):
            raise TaskSessionError(
                "Codex CLI startup failure is not a verified zero-action failure"
            )
        evidence = {
            "kind": failure_kind,
            "worker_pid": worker_pid,
            "worker_state_path": str(worker_state_path),
            "events_path": str(events_path.resolve()),
            "guard_report_path": str(guard_path.resolve()),
            "completed_tool_actions": 0,
            "collab_tool_calls": 0,
            "spawned_subagents": 0,
            "progress_events": 0,
        }
        if event.get("state") == "prepared":
            failure = event.get("last_preimplementation_failure")
            attempt_evidence = attempt.get("failure_evidence")
            failure_evidence = (
                failure.get("failure_evidence") if isinstance(failure, Mapping) else None
            )
            if (
                not isinstance(failure, Mapping)
                or not isinstance(attempt_evidence, Mapping)
                or not isinstance(failure_evidence, Mapping)
                or dict(attempt_evidence) != evidence
                or dict(failure_evidence) != evidence
            ):
                raise TaskSessionError(
                    "Codex CLI startup retry evidence changed after reconciliation"
                )
        return evidence

    def _preimplementation_windows_command_line_failure_evidence(
        self, task_id: str, event: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Verify a Windows shim failure before any Codex work could run."""

        failure_kind = "windows_command_line_too_long_before_implementation"
        attempts = event.get("launch_attempts")
        if (
            event.get("state") != "worker-started"
            or not isinstance(attempts, list)
            or not attempts
            or not isinstance(attempts[-1], Mapping)
            or attempts[-1].get("state") != "worker-started"
        ):
            raise TaskSessionError("Windows worker startup failure launch audit is inconsistent")
        if any(
            not isinstance(item, Mapping)
            or item.get("state")
            not in {"no-worker-started", "failed-before-implementation", "failed-guard-budget"}
            for item in attempts[:-1]
        ):
            raise TaskSessionError("Windows worker startup failure launch audit is ambiguous")
        if any(
            isinstance(item, Mapping) and item.get("failure_kind") == failure_kind
            for item in attempts[:-1]
        ):
            raise TaskSessionError("Windows worker startup retry budget was already used")

        attempt = attempts[-1]
        worker_pid = attempt.get("worker_pid")
        worker_state_value = attempt.get("worker_state_path")
        if (
            isinstance(worker_pid, bool)
            or not isinstance(worker_pid, int)
            or worker_pid < 1
            or event.get("worker_pid") != worker_pid
            or not isinstance(worker_state_value, str)
            or not Path(worker_state_value).is_absolute()
        ):
            raise TaskSessionError("Windows worker startup failure has malformed worker identity")
        if self.store._pid_is_alive(worker_pid):
            raise TaskSessionError("Codex worker process is still live")

        delivery_root = (
            self._canonical_root() / ".artifacts" / "tasks" / task_id / "temporary" / "delivery"
        ).resolve()
        worker_state_path = Path(worker_state_value).resolve()
        try:
            worker_state_path.relative_to(delivery_root)
        except ValueError as error:
            raise TaskSessionError(
                "Windows worker state path is outside task delivery artifacts"
            ) from error
        if worker_state_path.name != "worker-state.json" or worker_state_path.exists():
            raise TaskSessionError("Windows worker state has not been fully reconciled")
        if self._preimplementation_worker_state_paths(task_id):
            raise TaskSessionError("Task has unreconciled worker state")

        events_path = worker_state_path.with_name("events.jsonl")
        guard_path = worker_state_path.with_name("worker-guard.json")
        try:
            if events_path.stat().st_size > 1024 * 1024 or guard_path.stat().st_size > 64 * 1024:
                raise TaskSessionError(
                    "Windows worker startup failure evidence exceeds its size limit"
                )
            events = events_path.read_text(encoding="utf-8")
            guard = json.loads(guard_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise TaskSessionError(
                "Windows worker startup failure evidence is missing or unreadable"
            ) from error
        counters = guard.get("counters") if isinstance(guard, Mapping) else None
        zero_counters = (
            "completed_tool_actions",
            "collab_tool_calls",
            "spawned_subagents",
            "max_observed_concurrent_subagents",
            "progress_events",
        )
        if (
            not isinstance(guard, Mapping)
            or guard.get("schema_version") != 1
            or guard.get("classification") != "yfc-worker-guard-report"
            or guard.get("blocked") is not False
            or guard.get("block_reason_code") is not None
            or not isinstance(counters, Mapping)
            or any(
                isinstance(counters.get(name), bool)
                or not isinstance(counters.get(name), int)
                or counters.get(name) != 0
                for name in zero_counters
            )
            or isinstance(counters.get("malformed_lines"), bool)
            or not isinstance(counters.get("malformed_lines"), int)
            or counters.get("malformed_lines", -1) < 0
            or "the command line is too long." not in events.casefold()
        ):
            raise TaskSessionError(
                "Windows worker startup failure is not a verified zero-action failure"
            )
        return {
            "kind": failure_kind,
            "worker_pid": worker_pid,
            "worker_state_path": str(worker_state_path),
            "events_path": str(events_path.resolve()),
            "guard_report_path": str(guard_path.resolve()),
            "completed_tool_actions": 0,
            "collab_tool_calls": 0,
            "spawned_subagents": 0,
            "progress_events": 0,
        }

    def _preimplementation_queue_claim(self, task_id: str) -> None:
        claim_path = self.store.root / "continuous-queue.lock"
        if not claim_path.exists():
            return
        try:
            claim = json.loads(claim_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise TaskSessionError("Continuous queue claim is unreadable or malformed") from error
        if not isinstance(claim, Mapping):
            raise TaskSessionError("Continuous queue claim is malformed")
        phase = claim.get("queue_phase")
        raw_task_id = claim.get("task_id")
        if phase not in {"idle", "task_running"}:
            raise TaskSessionError("Continuous queue claim has an unknown phase")
        if (phase == "idle") != (raw_task_id is None):
            raise TaskSessionError("Continuous queue claim task state is inconsistent")
        if raw_task_id is not None:
            try:
                claimed_task_id = normalize_task_id(str(raw_task_id))
            except TaskSessionError as error:
                raise TaskSessionError(
                    "Continuous queue claim has an invalid task identity"
                ) from error
            if phase != "idle" and claimed_task_id == task_id:
                raise TaskSessionError("Task has an active continuous queue claim")

    @staticmethod
    def _reject_shared_task_lease_identity(
        task_id: str, lease: Mapping[str, Any], leases: Sequence[Mapping[str, Any]]
    ) -> None:
        branch = lease.get("branch")
        worktree_value = lease.get("worktree")
        worktree_key = (
            str(Path(worktree_value).resolve()).casefold()
            if isinstance(worktree_value, str)
            else ""
        )
        for other in leases:
            if str(other.get("task_id", "")).upper() == task_id:
                continue
            other_worktree = other.get("worktree")
            if branch == other.get("branch") or (
                isinstance(other_worktree, str)
                and str(Path(other_worktree).resolve()).casefold() == worktree_key
            ):
                raise TaskSessionError("Another task lease shares this task branch or worktree")

    def _guard_worktree_snapshot(self, task_id: str, worktree: Path, head: str) -> dict[str, Any]:
        self.store.root.mkdir(parents=True, exist_ok=True)
        descriptor, raw_index_path = tempfile.mkstemp(
            prefix=f"task-{task_id.lower()}-", suffix=".index", dir=self.store.root
        )
        os.close(descriptor)
        index_path = Path(raw_index_path)
        index_path.unlink()
        env = {"GIT_INDEX_FILE": str(index_path)}
        try:
            _run(["git", "read-tree", head], cwd=worktree, env=env)
            filters = _run(
                [
                    "git",
                    "config",
                    "--name-only",
                    "--get-regexp",
                    r"^filter\..*\.(clean|process)$",
                ],
                cwd=worktree,
                check=False,
            )
            if filters.returncode not in {0, 1}:
                raise TaskSessionError("Cannot inspect Git clean-filter configuration")
            filter_overrides: list[str] = []
            for key in filters.stdout.splitlines():
                if re.fullmatch(r"filter\.[a-zA-Z0-9_.-]+\.(clean|process)", key) is None:
                    raise TaskSessionError("Git clean-filter configuration contains an invalid key")
                filter_overrides.extend(("-c", f"{key}="))
            _run(["git", *filter_overrides, "add", "--all", "--"], cwd=worktree, env=env)
            tree = _run(["git", "write-tree"], cwd=worktree, env=env).stdout.strip()
            tracked = _run(["git", "diff", "--name-only", "-z", head], cwd=worktree).stdout.split(
                "\0"
            )
            untracked = _run(
                ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=worktree
            ).stdout.split("\0")
            changed_paths = sorted({item for item in (*tracked, *untracked) if item})
            patch = _run(
                ["git", "diff", "--binary", "--no-ext-diff", "--no-textconv", head, tree],
                cwd=worktree,
            ).stdout
            return {
                "tree": tree,
                "changed_paths": changed_paths,
                "patch_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
            }
        finally:
            index_path.unlink(missing_ok=True)
            Path(f"{index_path}.lock").unlink(missing_ok=True)

    def _guard_ignored_paths(self, worktree: Path) -> list[str]:
        output = _run(
            [
                "git",
                "status",
                "--porcelain=v1",
                "--ignored=matching",
                "--untracked-files=all",
                "-z",
            ],
            cwd=worktree,
        ).stdout
        records = output.split("\0")
        ignored: list[str] = []
        index = 0
        while index < len(records):
            record = records[index]
            index += 1
            if not record:
                continue
            if len(record) < 4:
                raise TaskSessionError("Task worktree status is malformed")
            status, path = record[:2], record[3:]
            if status == "!!":
                if not _is_canonical_managed_ignored_path(path, root=worktree):
                    ignored.append(path)
            elif ("R" in status or "C" in status) and index < len(records):
                index += 1
        return ignored

    @staticmethod
    def _read_guard_file(path: Path) -> tuple[bytes, os.stat_result]:
        try:
            with path.open("rb") as handle:
                content = handle.read(MAX_GUARD_EVIDENCE_BYTES + 1)
                file_stat = os.fstat(handle.fileno())
        except OSError as error:
            raise TaskSessionError(
                "Guard interruption evidence is missing or unreadable"
            ) from error
        if not stat.S_ISREG(file_stat.st_mode):
            raise TaskSessionError("Guard interruption evidence must be a regular file")
        if len(content) > MAX_GUARD_EVIDENCE_BYTES:
            raise TaskSessionError("Guard interruption evidence exceeds its size limit")
        return content, file_stat

    def _guard_interruption_evidence(
        self,
        task_id: str,
        worktree: Path,
        event: Mapping[str, Any],
        control_state: Mapping[str, Any],
    ) -> dict[str, Any]:
        attempts = event.get("launch_attempts")
        launch_id = event.get("launch_id")
        if (
            event.get("state") != "worker-started"
            or not isinstance(attempts, list)
            or not attempts
            or not isinstance(launch_id, str)
            or not isinstance(attempts[-1], Mapping)
            or attempts[-1].get("state") != "worker-started"
            or attempts[-1].get("launch_id") != launch_id
        ):
            raise TaskSessionError("Guard interruption has no matching worker launch audit")
        attempt = attempts[-1]
        if any(
            not isinstance(item, Mapping)
            or item.get("state") not in {"no-worker-started", "failed-before-implementation"}
            for item in attempts[:-1]
        ):
            raise TaskSessionError("Guard interruption launch history is ambiguous")
        worker_pid = event.get("worker_pid")
        worker_state_value = event.get("worker_state_path")
        command_started_at = event.get("command_started_at")
        process_instance = event.get("worker_process_instance")
        if (
            isinstance(worker_pid, bool)
            or not isinstance(worker_pid, int)
            or worker_pid < 1
            or attempt.get("worker_pid") != worker_pid
            or attempt.get("worker_process_instance") != event.get("worker_process_instance")
            or not isinstance(worker_state_value, str)
            or not Path(worker_state_value).is_absolute()
            or not isinstance(command_started_at, str)
            or attempt.get("worker_state_path") != worker_state_value
            or not isinstance(process_instance, Mapping)
            or attempt.get("worker_process_instance") != dict(process_instance)
            or not isinstance(process_instance.get("kind"), str)
            or not process_instance.get("kind")
            or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in process_instance.items()
            )
        ):
            raise TaskSessionError("Guard interruption worker identity is malformed")
        try:
            started_at = datetime.fromisoformat(command_started_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise TaskSessionError("Guard interruption command start time is malformed") from error
        if started_at.tzinfo is None:
            raise TaskSessionError("Guard interruption command start time has no timezone")
        if self.store._pid_is_alive(worker_pid):
            raise TaskSessionError("Guard-interrupted worker is still live")

        delivery_root = (
            self._canonical_root() / ".artifacts" / "tasks" / task_id / "temporary" / "delivery"
        ).resolve()
        worker_state_path = Path(worker_state_value).resolve()
        try:
            worker_state_path.relative_to(delivery_root)
        except ValueError as error:
            raise TaskSessionError(
                "Guard worker state path is outside task delivery artifacts"
            ) from error
        if worker_state_path.name != "worker-state.json" or worker_state_path.exists():
            raise TaskSessionError("Guard worker state has not been fully reconciled")
        if self._preimplementation_worker_state_paths(task_id):
            raise TaskSessionError("Task has unreconciled worker state")

        blocker = control_state.get("blocker")
        match = (
            re.fullmatch(
                r"worker guard blocked execution \(TOOL_ACTION_BUDGET_EXCEEDED\); inspect (.+)",
                blocker,
            )
            if isinstance(blocker, str)
            else None
        )
        if match is None:
            raise TaskSessionError(
                "Latest task blocker is not the supported tool-budget guard stop"
            )
        guard_path = Path(match.group(1)).resolve()
        expected_guard_path = worker_state_path.with_name("worker-guard.json")
        if guard_path != expected_guard_path:
            raise TaskSessionError("Guard report path does not match the interrupted attempt")
        attempt_id = guard_path.parent.name
        if re.fullmatch(r"\d{8}T\d{12}Z-delivery", attempt_id) is None:
            raise TaskSessionError("Guard report is outside a timestamped task delivery attempt")
        events_path = guard_path.with_name("events.jsonl")
        if events_path != worker_state_path.with_name("events.jsonl") or events_path.is_symlink():
            raise TaskSessionError("Guard events path is outside the interrupted attempt")
        report_bytes, report_stat = self._read_guard_file(guard_path)
        events_bytes, _ = self._read_guard_file(events_path)
        if not report_bytes or not events_bytes:
            raise TaskSessionError("Guard interruption evidence is empty")
        try:
            report = json.loads(report_bytes.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise TaskSessionError("Guard interruption report is not valid UTF-8 JSON") from error
        counters = report.get("counters") if isinstance(report, Mapping) else None
        limits = report.get("limits") if isinstance(report, Mapping) else None
        privacy = report.get("privacy") if isinstance(report, Mapping) else None
        completed = (
            counters.get("completed_tool_actions") if isinstance(counters, Mapping) else None
        )
        maximum = limits.get("max_completed_tool_actions") if isinstance(limits, Mapping) else None
        signature = report.get("block_signature_hash") if isinstance(report, Mapping) else None
        if (
            not isinstance(report, Mapping)
            or report.get("schema_version") != 1
            or report.get("classification") != "yfc-worker-guard-report"
            or report.get("blocked") is not True
            or report.get("block_reason_code") != "TOOL_ACTION_BUDGET_EXCEEDED"
            or isinstance(completed, bool)
            or not isinstance(completed, int)
            or isinstance(maximum, bool)
            or not isinstance(maximum, int)
            or maximum < 1
            or completed <= maximum
            or not isinstance(signature, str)
            or re.fullmatch(r"[0-9a-f]{64}", signature) is None
            or not isinstance(privacy, Mapping)
            or set(privacy)
            != {
                "raw_prompts_stored",
                "raw_commands_stored",
                "raw_tool_arguments_stored",
                "raw_tool_results_stored",
            }
            or any(
                privacy.get(key) is not False
                for key in (
                    "raw_prompts_stored",
                    "raw_commands_stored",
                    "raw_tool_arguments_stored",
                    "raw_tool_results_stored",
                )
            )
        ):
            raise TaskSessionError("Guard report does not verify a privacy-safe tool-budget stop")
        try:
            replay = WorkerEventGuard(GuardLimits.from_mapping(limits))
        except WorkerGuardConfigError as error:
            raise TaskSessionError("Guard report has invalid budget limits") from error
        for line in events_bytes.splitlines(keepends=True):
            replay.observe_line(line)
        if replay.report() != report:
            raise TaskSessionError("Guard report does not match its captured events")
        start_ns = int(started_at.timestamp() * 1_000_000_000)
        if start_ns > report_stat.st_mtime_ns:
            raise TaskSessionError("Guard report predates the interrupted worker start")
        snapshot = self._guard_worktree_snapshot(
            task_id, worktree, self.repository.head(cwd=worktree)
        )
        if not snapshot["changed_paths"]:
            raise TaskSessionError(
                "Guard-interrupted task has no tracked or untracked WIP to preserve"
            )
        ignored_paths = self._guard_ignored_paths(worktree)
        if ignored_paths:
            raise TaskSessionError(
                "Guard recovery refuses ignored files outside task artifacts: "
                + ", ".join(ignored_paths[:5])
            )
        for relative_path in snapshot["changed_paths"]:
            parts = PurePosixPath(relative_path).parts
            if not parts or PurePosixPath(relative_path).is_absolute() or ".." in parts:
                raise TaskSessionError("Guard recovery found an unsafe changed path")
            candidate = worktree.joinpath(*parts)
            stat_path = candidate
            while not stat_path.exists() and not stat_path.is_symlink() and stat_path != worktree:
                stat_path = stat_path.parent
            try:
                changed_at_ns = stat_path.lstat().st_mtime_ns
            except OSError as error:
                raise TaskSessionError(
                    "Cannot verify WIP modification time for the guard attempt"
                ) from error
            if changed_at_ns < start_ns or changed_at_ns > report_stat.st_mtime_ns:
                raise TaskSessionError(
                    "Task WIP includes a file changed outside the guarded attempt"
                )
        return {
            "attempt_id": attempt_id,
            "launch_id": launch_id,
            "worker_pid": worker_pid,
            "worker_state_path": str(worker_state_path),
            "command_started_at": command_started_at,
            "guard_stopped_at": datetime.fromtimestamp(
                report_stat.st_mtime_ns / 1_000_000_000, UTC
            ).isoformat(),
            "guard_report_path": str(guard_path),
            "guard_report_sha256": hashlib.sha256(report_bytes).hexdigest(),
            "events_path": str(events_path.resolve()),
            "events_sha256": hashlib.sha256(events_bytes).hexdigest(),
            "completed_tool_actions": completed,
            **snapshot,
        }

    def _validate_guard_wip_checkpoint(
        self,
        task_id: str,
        worktree: Path,
        lease: Mapping[str, Any],
        checkpoint: Mapping[str, Any],
    ) -> None:
        head = self.repository.head(cwd=worktree)
        checkpoint_ref = checkpoint.get("checkpoint_ref")
        checkpoint_commit = checkpoint.get("checkpoint_commit")
        attempt_id = checkpoint.get("attempt_id")
        delivery_root = (
            self._canonical_root() / ".artifacts" / "tasks" / task_id / "temporary" / "delivery"
        ).resolve()
        attempt_root = delivery_root / attempt_id if isinstance(attempt_id, str) else delivery_root
        expected_guard_path = (attempt_root / "worker-guard.json").resolve()
        expected_events_path = (attempt_root / "events.jsonl").resolve()
        expected_worker_state_path = (attempt_root / "worker-state.json").resolve()
        if (
            checkpoint.get("task_id") != task_id
            or checkpoint.get("recovery_attempt_number") != MAX_GUARD_BUDGET_RECOVERIES
            or checkpoint.get("head_sha") != head
            or checkpoint.get("base_sha") != lease.get("base_origin_master_sha")
            or checkpoint.get("original_base_sha") != lease.get("original_base_origin_master_sha")
            or not isinstance(attempt_id, str)
            or re.fullmatch(r"\d{8}T\d{12}Z-delivery", attempt_id) is None
            or not isinstance(checkpoint_ref, str)
            or not isinstance(checkpoint_commit, str)
            or not re.fullmatch(r"[0-9a-f]{40}", checkpoint_commit)
            or checkpoint.get("guard_report_path") != str(expected_guard_path)
            or checkpoint.get("events_path") != str(expected_events_path)
            or checkpoint.get("worker_state_path") != str(expected_worker_state_path)
            or expected_guard_path.is_symlink()
            or expected_events_path.is_symlink()
            or expected_worker_state_path.exists()
            or not self.repository.ref_exists(checkpoint_ref)
            or self.repository.ref(checkpoint_ref) != checkpoint_commit
        ):
            raise TaskSessionError("Guard WIP checkpoint identity or ref has changed")
        parents = self.repository.git("rev-list", "--parents", "-n", "1", checkpoint_commit).split()
        tree = self.repository.git("rev-parse", f"{checkpoint_commit}^{{tree}}")
        if (
            parents != [checkpoint_commit, head]
            or tree != checkpoint.get("checkpoint_tree")
            or checkpoint_ref
            != f"refs/codex/task-wip-checkpoints/task-{task_id.lower()}/{checkpoint.get('attempt_id')}"
        ):
            raise TaskSessionError(
                "Guard WIP checkpoint commit does not match its original task head"
            )
        snapshot = self._guard_worktree_snapshot(task_id, worktree, head)
        if (
            snapshot.get("tree") != tree
            or snapshot.get("changed_paths") != checkpoint.get("changed_paths")
            or snapshot.get("patch_sha256") != checkpoint.get("patch_sha256")
        ):
            raise TaskSessionError(
                "Task worktree no longer matches its durable guard WIP checkpoint"
            )
        for path_key, hash_key in (
            ("guard_report_path", "guard_report_sha256"),
            ("events_path", "events_sha256"),
        ):
            path_value = checkpoint.get(path_key)
            expected_hash = checkpoint.get(hash_key)
            if not isinstance(path_value, str) or not isinstance(expected_hash, str):
                raise TaskSessionError("Guard WIP checkpoint evidence metadata is malformed")
            path = Path(path_value)
            content, _ = self._read_guard_file(path)
            actual_hash = hashlib.sha256(content).hexdigest()
            if actual_hash != expected_hash:
                raise TaskSessionError("Guard WIP checkpoint evidence has changed")

    def _post_start_transport_interruption_evidence(
        self,
        task_id: str,
        worktree: Path,
        event: Mapping[str, Any],
        control_state: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Verify a real worker attempt stopped after an external transport failure."""

        attempts = event.get("launch_attempts")
        launch_id = event.get("launch_id")
        if (
            event.get("state") != "worker-started"
            or not isinstance(attempts, list)
            or not attempts
            or not isinstance(launch_id, str)
            or not isinstance(attempts[-1], Mapping)
            or attempts[-1].get("state") != "worker-started"
            or attempts[-1].get("launch_id") != launch_id
        ):
            raise TaskSessionError(
                "Post-start transport interruption has no matching worker launch"
            )
        attempt = attempts[-1]
        allowed_previous_states = {
            "no-worker-started",
            "failed-before-implementation",
            "failed-guard-budget",
            "failed-post-start-transport",
        }
        if any(
            not isinstance(item, Mapping) or item.get("state") not in allowed_previous_states
            for item in attempts[:-1]
        ):
            raise TaskSessionError("Post-start transport launch history is ambiguous")
        worker_pid = event.get("worker_pid")
        worker_state_value = event.get("worker_state_path")
        command_started_at = event.get("command_started_at")
        process_instance = event.get("worker_process_instance")
        if (
            isinstance(worker_pid, bool)
            or not isinstance(worker_pid, int)
            or worker_pid < 1
            or attempt.get("worker_pid") != worker_pid
            or attempt.get("worker_process_instance") != event.get("worker_process_instance")
            or not isinstance(worker_state_value, str)
            or not Path(worker_state_value).is_absolute()
            or not isinstance(command_started_at, str)
            or attempt.get("worker_state_path") != worker_state_value
            or not isinstance(process_instance, Mapping)
            or attempt.get("worker_process_instance") != dict(process_instance)
            or not isinstance(process_instance.get("kind"), str)
            or not process_instance.get("kind")
            or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in process_instance.items()
            )
        ):
            raise TaskSessionError("Post-start transport worker identity is malformed")
        try:
            started_at = datetime.fromisoformat(command_started_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise TaskSessionError(
                "Post-start transport command start time is malformed"
            ) from error
        if started_at.tzinfo is None:
            raise TaskSessionError("Post-start transport command start time has no timezone")
        if self.store._pid_is_alive(worker_pid):
            raise TaskSessionError("Post-start transport worker is still live")

        delivery_root = (
            self._canonical_root() / ".artifacts" / "tasks" / task_id / "temporary" / "delivery"
        ).resolve()
        worker_state_path = Path(worker_state_value).resolve()
        try:
            worker_state_path.relative_to(delivery_root)
        except ValueError as error:
            raise TaskSessionError(
                "Post-start transport worker state is outside task delivery artifacts"
            ) from error
        if worker_state_path.name != "worker-state.json" or worker_state_path.exists():
            raise TaskSessionError("Post-start transport worker state has not been reconciled")
        if self._preimplementation_worker_state_paths(task_id):
            raise TaskSessionError("Task has unreconciled worker state")

        events_path = worker_state_path.with_name("events.jsonl")
        guard_path = worker_state_path.with_name("worker-guard.json")
        blocker = control_state.get("blocker")
        if (
            not isinstance(blocker, str)
            or str(events_path) not in blocker
            or not events_path.is_file()
            or events_path.is_symlink()
            or not guard_path.is_file()
            or guard_path.is_symlink()
        ):
            raise TaskSessionError(
                "Post-start transport blocker does not identify the attempt evidence"
            )
        report_bytes, report_stat = self._read_guard_file(guard_path)
        events_bytes, _ = self._read_guard_file(events_path)
        if not report_bytes or not events_bytes:
            raise TaskSessionError("Post-start transport evidence is empty")
        try:
            report = json.loads(report_bytes.decode("utf-8"))
            events_text = events_bytes.decode("utf-8")
        except (UnicodeError, json.JSONDecodeError) as error:
            raise TaskSessionError(
                "Post-start transport evidence is not valid UTF-8 JSON"
            ) from error
        counters = report.get("counters") if isinstance(report, Mapping) else None
        limits = report.get("limits") if isinstance(report, Mapping) else None
        privacy = report.get("privacy") if isinstance(report, Mapping) else None
        completed = (
            counters.get("completed_tool_actions") if isinstance(counters, Mapping) else None
        )
        progress = counters.get("progress_events") if isinstance(counters, Mapping) else None
        if (
            not isinstance(report, Mapping)
            or report.get("schema_version") != 1
            or report.get("classification") != "yfc-worker-guard-report"
            or report.get("blocked") is not False
            or report.get("block_reason_code") is not None
            or isinstance(completed, bool)
            or not isinstance(completed, int)
            or completed < 1
            or isinstance(progress, bool)
            or not isinstance(progress, int)
            or progress < 1
            or not isinstance(privacy, Mapping)
            or set(privacy)
            != {
                "raw_prompts_stored",
                "raw_commands_stored",
                "raw_tool_arguments_stored",
                "raw_tool_results_stored",
            }
            or any(privacy.get(key) is not False for key in privacy)
        ):
            raise TaskSessionError("Post-start transport evidence is ambiguous")
        matched_signatures = tuple(
            signature
            for signature in POST_START_TRANSPORT_SIGNATURES
            if signature in events_text.casefold()
        )
        if not matched_signatures:
            raise TaskSessionError("Post-start transport evidence is ambiguous")
        try:
            replay = WorkerEventGuard(GuardLimits.from_mapping(limits))
        except WorkerGuardConfigError as error:
            raise TaskSessionError(
                "Post-start transport guard report has invalid limits"
            ) from error
        for line in events_bytes.splitlines(keepends=True):
            replay.observe_line(line)
        if replay.report() != report:
            raise TaskSessionError("Post-start transport guard report does not match its events")
        start_ns = int(started_at.timestamp() * 1_000_000_000)
        if start_ns > report_stat.st_mtime_ns:
            raise TaskSessionError("Post-start transport evidence predates the worker start")
        snapshot = self._guard_worktree_snapshot(
            task_id, worktree, self.repository.head(cwd=worktree)
        )
        if not snapshot["changed_paths"]:
            raise TaskSessionError("Post-start transport attempt has no task WIP")
        ignored_paths = self._guard_ignored_paths(worktree)
        if ignored_paths:
            raise TaskSessionError(
                "Post-start transport recovery refuses ignored files outside task artifacts: "
                + ", ".join(ignored_paths[:5])
            )
        baseline_snapshot = attempt.get("prelaunch_snapshot")
        baseline_tree = (
            baseline_snapshot.get("tree") if isinstance(baseline_snapshot, Mapping) else None
        )
        if (
            not isinstance(baseline_tree, str)
            or re.fullmatch(r"[0-9a-f]{40}", baseline_tree) is None
        ):
            previous_recovery = event.get("guard_budget_recovery")
            baseline_tree = (
                previous_recovery.get("checkpoint_tree")
                if isinstance(previous_recovery, Mapping)
                else None
            )
        if (
            not isinstance(baseline_tree, str)
            or re.fullmatch(r"[0-9a-f]{40}", baseline_tree) is None
        ):
            baseline_tree = self.repository.git("rev-parse", f"{event.get('head_sha')}^{{tree}}")

        def tree_entry(tree: str, relative_path: str) -> str:
            return self.repository.git("ls-tree", "-z", tree, "--", relative_path)

        for relative_path in snapshot["changed_paths"]:
            parts = PurePosixPath(relative_path).parts
            if not parts or PurePosixPath(relative_path).is_absolute() or ".." in parts:
                raise TaskSessionError("Post-start transport recovery found an unsafe changed path")
            candidate = worktree.joinpath(*parts)
            stat_path = candidate
            while not stat_path.exists() and not stat_path.is_symlink() and stat_path != worktree:
                stat_path = stat_path.parent
            try:
                changed_at_ns = stat_path.lstat().st_mtime_ns
            except OSError as error:
                raise TaskSessionError(
                    "Cannot verify WIP modification time for post-start transport recovery"
                ) from error
            if changed_at_ns > report_stat.st_mtime_ns:
                raise TaskSessionError(
                    "Task WIP includes a file changed outside the transport attempt"
                )
            if changed_at_ns < start_ns and tree_entry(baseline_tree, relative_path) != tree_entry(
                snapshot["tree"], relative_path
            ):
                raise TaskSessionError(
                    "Task WIP includes a file changed outside the transport attempt"
                )
        attempt_id = guard_path.parent.name
        if re.fullmatch(r"\d{8}T\d{12}Z-delivery", attempt_id) is None:
            raise TaskSessionError("Post-start transport evidence is outside a timestamped attempt")
        return {
            "kind": POST_START_TRANSPORT_FAILURE_KIND,
            "attempt_id": attempt_id,
            "launch_id": launch_id,
            "worker_pid": worker_pid,
            "worker_state_path": str(worker_state_path),
            "command_started_at": command_started_at,
            "transport_stopped_at": datetime.fromtimestamp(
                report_stat.st_mtime_ns / 1_000_000_000, UTC
            ).isoformat(),
            "transport_signatures": list(matched_signatures),
            "guard_report_path": str(guard_path),
            "guard_report_sha256": hashlib.sha256(report_bytes).hexdigest(),
            "events_path": str(events_path.resolve()),
            "events_sha256": hashlib.sha256(events_bytes).hexdigest(),
            "completed_tool_actions": completed,
            "progress_events": progress,
            **snapshot,
        }

    @staticmethod
    def _transport_control_state_matches_checkpoint(
        control_state: Mapping[str, Any], checkpoint: Mapping[str, Any]
    ) -> bool:
        blocker = control_state.get("blocker")
        expected = checkpoint.get("events_path")
        return bool(
            blocker == POST_START_TRANSPORT_HANDOFF_BLOCKER
            or (isinstance(blocker, str) and isinstance(expected, str) and expected in blocker)
        )

    @staticmethod
    def _guard_control_state_matches_checkpoint(
        control_state: Mapping[str, Any], checkpoint: Mapping[str, Any]
    ) -> bool:
        blocker = control_state.get("blocker")
        expected = checkpoint.get("guard_report_path")
        match = (
            re.fullmatch(
                r"worker guard blocked execution \(TOOL_ACTION_BUDGET_EXCEEDED\); inspect (.+)",
                blocker,
                flags=re.IGNORECASE,
            )
            if isinstance(blocker, str)
            else None
        )
        return bool(
            isinstance(expected, str)
            and (
                (match is not None and Path(match.group(1)).resolve() == Path(expected).resolve())
                or blocker == GUARD_RECOVERY_HANDOFF_BLOCKER
            )
        )

    def _validate_preimplementation_worktree(
        self,
        task_id: str,
        lease: Mapping[str, Any],
        *,
        prepared_event: Mapping[str, Any] | None = None,
        allow_guard_dirty: bool = False,
        validate_recovery_checkpoint: bool = True,
    ) -> tuple[Path, str, str]:
        branch = lease.get("branch")
        if not isinstance(branch, str):
            raise TaskSessionError("Task lease has no registered branch")
        try:
            if task_id_from_branch(branch) != task_id:
                raise TaskSessionError("Task branch does not match the registered task identity")
        except TaskSessionError as error:
            raise TaskSessionError(
                "Task branch does not match the registered task identity"
            ) from error
        worktree_value = lease.get("worktree")
        if not isinstance(worktree_value, str) or not worktree_value:
            raise TaskSessionError("Task lease has no registered worktree")
        worktree = Path(worktree_value).resolve()
        try:
            worktree.relative_to((self._canonical_root() / ".artifacts" / "worktrees").resolve())
        except ValueError as error:
            raise TaskSessionError(
                "Registered task worktree is outside the managed worktree root"
            ) from error
        worktrees = self.repository.worktrees()
        matches = [item for item in worktrees if item.path == worktree]
        branch_matches = [item for item in worktrees if item.branch == branch]
        if len(matches) != 1 or len(branch_matches) != 1 or matches[0].branch != branch:
            raise TaskSessionError("Registered worktree does not uniquely match the task branch")
        local_branches = [
            str(item["branch"])
            for item in self.repository.local_branches()
            if isinstance(item.get("branch"), str)
            and str(item["branch"]).startswith(f"task/{task_id}-")
        ]
        if local_branches != [branch]:
            raise TaskSessionError("Task has duplicate or ambiguous local task branches")
        if self.repository.current_branch(cwd=worktree) != branch:
            raise TaskSessionError("Registered task worktree is on a different branch")
        issues = self.repository.operation_issues(worktree)
        if issues:
            raise TaskSessionError(
                "Task worktree has an active Git operation: " + ", ".join(issues)
            )
        head = self.repository.head(cwd=worktree)
        branch_head = self.repository.ref(f"refs/heads/{branch}")
        base = str(lease.get("base_origin_master_sha", ""))
        original_base = str(lease.get("original_base_origin_master_sha", ""))
        valid_original_anchor = base == original_base or bool(
            isinstance(prepared_event, Mapping)
            and prepared_event.get("state") == "prepared"
            and prepared_event.get("original_base_sha") == original_base
            and prepared_event.get("head_sha") == base
        )
        if (
            re.fullmatch(r"[0-9a-f]{40}", base) is None
            or re.fullmatch(r"[0-9a-f]{40}", original_base) is None
            or head != branch_head
            or head != base
            or not valid_original_anchor
            or self.repository.unique_commits(branch, base=base)
        ):
            raise TaskSessionError(
                "Task branch has unique commits or no longer matches its original base"
            )
        dirty = self.repository.status(worktree, include_ignored=True)
        recoveries = (
            [
                prepared_event.get("guard_budget_recovery"),
                prepared_event.get("transport_interruption_recovery"),
            ]
            if isinstance(prepared_event, Mapping)
            else []
        )
        recoveries = [item for item in recoveries if isinstance(item, Mapping)]
        if recoveries and validate_recovery_checkpoint:
            ignored = self._guard_ignored_paths(worktree)
            if ignored:
                raise TaskSessionError(
                    "Guard recovery refuses ignored files outside task artifacts: "
                    + ", ".join(ignored[:5])
                )
            recovery = (
                prepared_event.get("transport_interruption_recovery")
                if isinstance(prepared_event, Mapping)
                else None
            )
            if not isinstance(recovery, Mapping):
                recovery = recoveries[0]
            self._validate_guard_wip_checkpoint(task_id, worktree, lease, recovery)
        elif dirty and allow_guard_dirty:
            ignored = self._guard_ignored_paths(worktree)
            if ignored:
                raise TaskSessionError(
                    "Guard recovery refuses ignored files outside task artifacts: "
                    + ", ".join(ignored[:5])
                )
        elif dirty:
            raise TaskSessionError("Task worktree is dirty: " + ", ".join(dirty[:5]))
        remote_branch = f"refs/remotes/origin/{branch}"
        if self.repository.ref_exists(remote_branch) or self.repository.remote_branch_exists(
            branch, cwd=self._canonical_root()
        ):
            raise TaskSessionError(
                "Task branch already has a remote ref that requires reconciliation"
            )
        return worktree, branch, head

    def resume_preimplementation(
        self,
        task_id: str,
        *,
        control_issue_number: int,
        reason: str,
        owner_authorize: bool,
    ) -> dict[str, Any]:
        expected = normalize_task_id(task_id)
        if not owner_authorize:
            raise TaskSessionError("Resume requires explicit owner authorization")
        if (
            isinstance(control_issue_number, bool)
            or not isinstance(control_issue_number, int)
            or control_issue_number < 1
        ):
            raise TaskSessionError("Resume requires a valid control Issue number")
        if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 1024:
            raise TaskSessionError("Resume reason must be a bounded non-empty string")
        if self.github is None:
            raise TaskSessionError("Pre-implementation resume requires online GitHub state")
        self.store.initialize()
        lease_path = self.store.task_lease_path(expected)
        with self.store.lock():
            leases = self.store.all_leases()
            matching_leases = []
            for item in leases:
                raw_task_id = item.get("task_id")
                if not isinstance(raw_task_id, str) or not TASK_ID_RE.fullmatch(raw_task_id):
                    raise TaskSessionError(
                        "Controller contains a lease with an invalid task identity"
                    )
                if raw_task_id.upper() == expected:
                    matching_leases.append(item)
            lease = self.store.read_json(lease_path)
            if len(matching_leases) != 1 or matching_leases[0] != lease:
                raise TaskSessionError(f"Task {expected} has an ambiguous task lease")
            if not isinstance(lease, dict):
                raise TaskSessionError(f"Task {expected} has no valid active lease")
            if (
                lease.get("mode") != "write"
                or lease.get("owner_launch") is not True
                or lease.get("queue_mode") is True
                or self._lease_state(lease) != "implementation"
            ):
                raise TaskSessionError(
                    f"Task {expected} is not in a compatible active implementation state"
                )
            document = find_task_document(self._canonical_root(), expected)
            if (
                not document.executable
                or "blocked" in document.status.lower()
                or "заблок" in document.status.lower()
                or Path(str(lease.get("canonical_task_path", ""))).resolve()
                != document.path.resolve()
            ):
                raise TaskSessionError("Registered task document does not match the active lease")
            if (
                self._validated_lease_concurrency_class(lease) != document.concurrency_class
                or lease.get("integration_policy") != document.integration_policy
                or lease.get("target_base_branch") != TARGET_BASE_BRANCH
            ):
                raise TaskSessionError("Task metadata is incompatible with the active lease")
            branch = str(lease.get("branch", ""))
            self._reject_shared_task_lease_identity(expected, lease, leases)
            event = lease.get("preimplementation_resume")
            cli_failure_evidence: dict[str, Any] | None = None
            if event is not None:
                if (
                    not isinstance(event, Mapping)
                    or event.get("control_issue_number") != control_issue_number
                    or event.get("reason") != reason.strip()
                ):
                    raise TaskSessionError(
                        "Task has an unreconciled or already-used pre-implementation resume"
                    )
                if event.get("state") == "worker-started" or (
                    event.get("state") == "prepared"
                    and event.get("last_preimplementation_failure") is not None
                ):
                    cli_failure_evidence = self._preimplementation_cli_failure_evidence(
                        expected, event
                    )
                elif event.get("state") != "prepared":
                    raise TaskSessionError(
                        "Task has an unreconciled or already-used pre-implementation resume"
                    )
            prepared_event = event if isinstance(event, Mapping) else None
            if isinstance(event, Mapping) and event.get("state") == "worker-started":
                prepared_event = {**event, "state": "prepared"}
            _, branch, old_head = self._validate_preimplementation_worktree(
                expected, lease, prepared_event=prepared_event
            )
            control_state = self._preimplementation_issue_state(
                expected,
                control_issue_number,
                branch,
                document,
                lease,
                allow_cli_preflight_failure=cli_failure_evidence is not None,
            )
            self._preimplementation_queue_claim(expected)
            worker_states = self._preimplementation_worker_state_paths(expected)
            if worker_states:
                raise TaskSessionError(
                    "Task has unreconciled worker state: "
                    + ", ".join(str(item) for item in worker_states)
                )
            open_prs = [
                item
                for item in self._github().open_pull_requests()
                if isinstance(item.get("head"), Mapping)
                if str(item["head"].get("ref", "")) == branch
            ]
            if open_prs:
                raise TaskSessionError("Task branch already has an open pull request")
            current_origin = self.repository.ref("origin/master")
            if event is not None and cli_failure_evidence is not None:
                self.repository.fetch_origin_master(cwd=self._canonical_root(), prune=False)
                current_origin = self.repository.ref("origin/master")
            if (
                event is not None
                and current_origin != lease.get("base_origin_master_sha")
                and cli_failure_evidence is None
            ):
                raise TaskSessionError("origin/master moved after the resume was prepared")
            if event is None:
                self.repository.fetch_origin_master(cwd=self._canonical_root(), prune=False)
                current_origin = self.repository.ref("origin/master")
            live_master = self._github().branch_head(TARGET_BASE_BRANCH)
            if current_origin != live_master:
                raise TaskSessionError(
                    "origin/master is not synchronized with live protected master"
                )
            canonical_head = self.repository.head(cwd=self._canonical_root())
            canonical_changes = self._canonical_worktree_status()
            if (
                self.repository.current_branch(cwd=self._canonical_root()) != TARGET_BASE_BRANCH
                or self.repository.operation_issues(self._canonical_root())
                or canonical_changes
                or not self.repository.is_ancestor(canonical_head, current_origin)
            ):
                detail = ", ".join(canonical_changes[:5])
                raise TaskSessionError(
                    "Canonical master is not clean and in a safe fast-forward relationship"
                    + (f": {detail}" if detail else "")
                )
            if not self.repository.is_ancestor(old_head, current_origin):
                raise TaskSessionError("Task branch cannot be refreshed by fast-forward")
            if event is not None:
                if cli_failure_evidence is not None and old_head != current_origin:
                    refreshes = event.get("base_refreshes", [])
                    if not isinstance(refreshes, list):
                        raise TaskSessionError("Task resume base-refresh audit is malformed")
                    timestamp = utc_now()
                    pending_refresh = {
                        "from_base_sha": lease.get("base_origin_master_sha"),
                        "from_head_sha": old_head,
                        "to_base_sha": current_origin,
                        "started_at": timestamp,
                    }
                    event["state"] = "refreshing"
                    event["pending_base_refresh"] = pending_refresh
                    lease["updated_at"] = timestamp
                    StateStore.replace_json(lease_path, lease)
                    try:
                        self.repository.fast_forward_current(
                            current_origin, cwd=Path(lease["worktree"])
                        )
                    except TaskSessionError as error:
                        event["state"] = "refresh-failed"
                        event["failure"] = str(error)[:1024]
                        lease["updated_at"] = utc_now()
                        StateStore.replace_json(lease_path, lease)
                        raise TaskSessionError(
                            "Task branch refresh failed; the recorded attempt requires reconciliation"
                        ) from error
                    if (
                        self.repository.head(cwd=Path(lease["worktree"])) != current_origin
                        or self.repository.ref(f"refs/heads/{branch}") != current_origin
                        or self.repository.ref("origin/master") != current_origin
                        or self._github().branch_head(TARGET_BASE_BRANCH) != current_origin
                    ):
                        event["state"] = "refresh-failed"
                        event["failure"] = "protected master changed during branch refresh"
                        lease["updated_at"] = utc_now()
                        StateStore.replace_json(lease_path, lease)
                        raise TaskSessionError("Protected master changed during branch refresh")
                    refreshes.append(
                        {
                            **pending_refresh,
                            "fast_forwarded_at": utc_now(),
                        }
                    )
                    event["base_refreshes"] = refreshes
                    event.pop("pending_base_refresh", None)
                    event["base_sha"] = current_origin
                    event["head_sha"] = current_origin
                    event["state"] = "worker-started"
                    lease["base_origin_master_sha"] = current_origin
                    lease["updated_at"] = utc_now()
                    StateStore.replace_json(lease_path, lease)
                if cli_failure_evidence is not None and event.get("state") == "worker-started":
                    attempts = event["launch_attempts"]
                    attempt = attempts[-1]
                    timestamp = utc_now()
                    failure_kind = "codex_cli_argument_conflict_before_implementation"
                    attempt.update(
                        {
                            "state": "failed-before-implementation",
                            "finished_at": timestamp,
                            "worker_exit_code": 2,
                            "failure_kind": failure_kind,
                            "failure_evidence": cli_failure_evidence,
                        }
                    )
                    event["last_preimplementation_failure"] = {
                        "kind": failure_kind,
                        "recorded_at": timestamp,
                        "launch_id": attempt["launch_id"],
                        "worker_exit_code": 2,
                        "failure_evidence": cli_failure_evidence,
                    }
                    event.pop("launch_id", None)
                    event.pop("launch_claimed_at", None)
                    event["state"] = "prepared"
                    lease["updated_at"] = timestamp
                    StateStore.replace_json(lease_path, lease)
                    return {
                        "task_id": expected,
                        "lease": dict(lease),
                        "preimplementation_resume": dict(event),
                        "control_state": control_state,
                        "mutation_performed": True,
                    }
                return {
                    "task_id": expected,
                    "lease": dict(lease),
                    "preimplementation_resume": dict(event),
                    "control_state": control_state,
                    "mutation_performed": False,
                }
            timestamp = utc_now()
            resume_event = {
                "version": 1,
                "state": "refreshing",
                "owner_authorized": True,
                "control_issue_number": control_issue_number,
                "previous_control_state": control_state,
                "registered_at": lease.get("created_at"),
                "original_base_sha": lease.get("original_base_origin_master_sha"),
                "previous_base_sha": lease.get("base_origin_master_sha"),
                "previous_head_sha": old_head,
                "base_sha": current_origin,
                "reason": reason.strip(),
                "prepared_at": timestamp,
            }
            lease["preimplementation_resume"] = resume_event
            lease["updated_at"] = timestamp
            StateStore.replace_json(lease_path, lease)
            try:
                self.repository.fast_forward_current(current_origin, cwd=Path(lease["worktree"]))
            except TaskSessionError as error:
                resume_event["state"] = "refresh-failed"
                resume_event["failure"] = str(error)[:1024]
                lease["updated_at"] = utc_now()
                StateStore.replace_json(lease_path, lease)
                raise TaskSessionError(
                    "Task branch refresh failed; the recorded attempt requires reconciliation"
                ) from error
            if (
                self.repository.head(cwd=Path(lease["worktree"])) != current_origin
                or self.repository.ref(f"refs/heads/{branch}") != current_origin
                or self.repository.ref("origin/master") != current_origin
                or self._github().branch_head(TARGET_BASE_BRANCH) != current_origin
            ):
                resume_event["state"] = "refresh-failed"
                resume_event["failure"] = "protected master changed during branch refresh"
                lease["updated_at"] = utc_now()
                StateStore.replace_json(lease_path, lease)
                raise TaskSessionError("Protected master changed during branch refresh")
            resume_event["state"] = "prepared"
            resume_event["head_sha"] = current_origin
            lease["base_origin_master_sha"] = current_origin
            lease["updated_at"] = utc_now()
            StateStore.replace_json(lease_path, lease)
            return {
                "task_id": expected,
                "lease": lease,
                "preimplementation_resume": resume_event,
                "control_state": control_state,
                "mutation_performed": True,
            }

    def resume_guard_interrupted(
        self,
        task_id: str,
        *,
        control_issue_number: int,
        reason: str,
        owner_authorize: bool,
    ) -> dict[str, Any]:
        expected = normalize_task_id(task_id)
        if not owner_authorize:
            raise TaskSessionError("Guard recovery requires explicit owner authorization")
        if (
            isinstance(control_issue_number, bool)
            or not isinstance(control_issue_number, int)
            or control_issue_number < 1
        ):
            raise TaskSessionError("Guard recovery requires a valid control Issue number")
        if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 1024:
            raise TaskSessionError("Guard recovery reason must be a bounded non-empty string")
        if self.github is None:
            raise TaskSessionError("Guard recovery requires online GitHub state")

        self.store.initialize()
        lease_path = self.store.task_lease_path(expected)
        with self.store.lock():
            leases = self.store.all_leases()
            matching = [
                item
                for item in leases
                if isinstance(item.get("task_id"), str) and str(item["task_id"]).upper() == expected
            ]
            lease = self.store.read_json(lease_path)
            if len(matching) != 1 or matching[0] != lease:
                raise TaskSessionError(f"Task {expected} has an ambiguous task lease")
            if (
                not isinstance(lease, dict)
                or lease.get("mode") != "write"
                or lease.get("owner_launch") is not True
                or lease.get("queue_mode") is True
                or self._lease_state(lease) != "implementation"
            ):
                raise TaskSessionError(f"Task {expected} has no active implementation lease")
            self._reject_shared_task_lease_identity(expected, lease, leases)
            document = find_task_document(self._canonical_root(), expected)
            if (
                not document.executable
                or "blocked" in document.status.lower()
                or "заблок" in document.status.lower()
                or Path(str(lease.get("canonical_task_path", ""))).resolve()
                != document.path.resolve()
                or self._validated_lease_concurrency_class(lease) != document.concurrency_class
                or lease.get("integration_policy") != document.integration_policy
                or lease.get("target_base_branch") != TARGET_BASE_BRANCH
            ):
                raise TaskSessionError("Task document or metadata no longer matches its lease")
            branch = str(lease.get("branch", ""))
            event = lease.get("preimplementation_resume")
            if (
                not isinstance(event, dict)
                or event.get("control_issue_number") != control_issue_number
            ):
                raise TaskSessionError("Task has no matching resumable pre-implementation launch")
            existing = event.get("guard_budget_recovery")
            if isinstance(existing, Mapping):
                if event.get("guard_budget_recovery_reason") != reason.strip():
                    raise TaskSessionError(
                        "The one-time guard recovery was already launched or reconciled"
                    )
                startup_failure_evidence: dict[str, Any] | None = None
                prepared_event: Mapping[str, Any] = event
                if event.get("state") == "worker-started":
                    classification_state = self._preimplementation_issue_state(
                        expected,
                        control_issue_number,
                        branch,
                        document,
                        lease,
                        allow_guard_budget_failure=True,
                        allow_transport_failure=True,
                    )
                    try:
                        self._post_start_transport_interruption_evidence(
                            expected,
                            Path(str(lease["worktree"])),
                            event,
                            classification_state,
                        )
                    except TaskSessionError:
                        pass
                    else:
                        raise TaskSessionError(
                            "Task has a post-start external transport interruption; use transport recovery"
                        )
                    startup_failure_evidence = (
                        self._preimplementation_windows_command_line_failure_evidence(
                            expected, event
                        )
                    )
                    prepared_event = {**event, "state": "prepared"}
                elif event.get("state") != "prepared" or "launch_id" in event:
                    raise TaskSessionError(
                        "The one-time guard recovery was already launched or reconciled"
                    )
                if isinstance(event.get("transport_interruption_recovery"), Mapping):
                    raise TaskSessionError(
                        "Task has a post-start external transport interruption; use transport recovery"
                    )
                control_state = self._preimplementation_issue_state(
                    expected,
                    control_issue_number,
                    branch,
                    document,
                    lease,
                    allow_guard_budget_failure=True,
                )
                if not self._guard_control_state_matches_checkpoint(control_state, existing):
                    raise TaskSessionError(
                        "Latest task guard blocker no longer matches its checkpoint"
                    )
                self._validate_preimplementation_worktree(
                    expected, lease, prepared_event=prepared_event
                )
                if startup_failure_evidence is not None:
                    attempts = event.get("launch_attempts")
                    if not isinstance(attempts, list) or not attempts:
                        raise TaskSessionError(
                            "Windows worker startup failure has no launch-attempt audit"
                        )
                    attempt = attempts[-1]
                    if not isinstance(attempt, dict):
                        raise TaskSessionError(
                            "Windows worker startup failure launch audit is malformed"
                        )
                    timestamp = utc_now()
                    failure_kind = str(startup_failure_evidence["kind"])
                    launch_id = str(attempt["launch_id"])
                    attempt.update(
                        {
                            "state": "failed-before-implementation",
                            "finished_at": timestamp,
                            "failure_kind": failure_kind,
                            "failure_evidence": startup_failure_evidence,
                        }
                    )
                    event["last_preimplementation_failure"] = {
                        "kind": failure_kind,
                        "recorded_at": timestamp,
                        "launch_id": launch_id,
                        "failure_evidence": startup_failure_evidence,
                    }
                    for key in (
                        "launch_id",
                        "launch_claimed_at",
                        "worker_started_at",
                        "command_started_at",
                        "worker_pid",
                        "worker_process_instance",
                        "worker_state_path",
                    ):
                        event.pop(key, None)
                    event["state"] = "prepared"
                    lease["updated_at"] = timestamp
                    StateStore.replace_json(lease_path, lease)
                return {
                    "task_id": expected,
                    "lease": dict(lease),
                    "preimplementation_resume": dict(event),
                    "control_state": control_state,
                    "mutation_performed": startup_failure_evidence is not None,
                }
            if event.get("state") != "worker-started":
                raise TaskSessionError("Task has no guard-interrupted worker to recover")

            control_state = self._preimplementation_issue_state(
                expected,
                control_issue_number,
                branch,
                document,
                lease,
                allow_guard_budget_failure=True,
                allow_transport_failure=True,
            )
            try:
                self._post_start_transport_interruption_evidence(
                    expected, Path(str(lease["worktree"])), event, control_state
                )
            except TaskSessionError:
                pass
            else:
                raise TaskSessionError(
                    "Task has a post-start external transport interruption; use transport recovery"
                )
            self._preimplementation_queue_claim(expected)
            if self._preimplementation_worker_state_paths(expected):
                raise TaskSessionError("Task has unreconciled worker state")
            if any(
                isinstance(item.get("head"), Mapping) and str(item["head"].get("ref", "")) == branch
                for item in self._github().open_pull_requests()
            ):
                raise TaskSessionError("Task branch already has an open pull request")

            canonical = self._canonical_root()
            self.repository.fetch_origin_master(cwd=canonical, prune=False)
            current_origin = self.repository.ref("origin/master")
            live_master = self._github().branch_head(TARGET_BASE_BRANCH)
            canonical_head = self.repository.head(cwd=canonical)
            canonical_changes = self._canonical_worktree_status()
            if current_origin != live_master:
                raise TaskSessionError(
                    "origin/master is not synchronized with live protected master"
                )
            if (
                self.repository.current_branch(cwd=canonical) != TARGET_BASE_BRANCH
                or self.repository.operation_issues(canonical)
                or canonical_changes
                or not self.repository.is_ancestor(canonical_head, current_origin)
            ):
                raise TaskSessionError(
                    "Canonical master is not clean and safely behind origin/master"
                )
            if not self.repository.is_ancestor(
                str(lease.get("base_origin_master_sha", "")), current_origin
            ):
                raise TaskSessionError("Task base is not an ancestor of synchronized origin/master")
            prepared_event = {**event, "state": "prepared"}
            worktree, branch, head = self._validate_preimplementation_worktree(
                expected, lease, prepared_event=prepared_event, allow_guard_dirty=True
            )
            if (
                head != event.get("head_sha")
                or self.repository.unique_commits(branch, base=current_origin)
                or self.repository.ref_exists(f"refs/remotes/origin/{branch}")
                or self.repository.remote_branch_exists(branch, cwd=canonical)
            ):
                raise TaskSessionError("Task branch is not a clean ancestor of protected master")
            evidence = self._guard_interruption_evidence(expected, worktree, event, control_state)
            if self._preimplementation_worker_state_paths(expected):
                raise TaskSessionError("Task worker state appeared during guard recovery")

            checkpoint_ref = (
                f"refs/codex/task-wip-checkpoints/task-{expected.lower()}/{evidence['attempt_id']}"
            )
            snapshot = self._guard_worktree_snapshot(expected, worktree, head)
            if (
                snapshot["tree"] != evidence["tree"]
                or snapshot["changed_paths"] != evidence["changed_paths"]
                or snapshot["patch_sha256"] != evidence["patch_sha256"]
            ):
                raise TaskSessionError("Task WIP changed while its guard checkpoint was prepared")
            latest_evidence = self._guard_interruption_evidence(
                expected, worktree, event, control_state
            )
            if any(latest_evidence[key] != evidence[key] for key in evidence):
                raise TaskSessionError(
                    "Guard evidence or task WIP changed during checkpoint creation"
                )
            if self.repository.ref_exists(checkpoint_ref):
                checkpoint_commit = self.repository.ref(checkpoint_ref)
                existing_parents = self.repository.git(
                    "rev-list", "--parents", "-n", "1", checkpoint_commit
                ).split()
                existing_tree = self.repository.git("rev-parse", f"{checkpoint_commit}^{{tree}}")
                if (
                    existing_parents != [checkpoint_commit, head]
                    or existing_tree != snapshot["tree"]
                ):
                    raise TaskSessionError("A conflicting guard WIP checkpoint ref already exists")
            else:
                checkpoint_commit = self.repository.git(
                    "-c",
                    "user.name=Codex Controller",
                    "-c",
                    "user.email=codex-controller@users.noreply.github.com",
                    "commit-tree",
                    snapshot["tree"],
                    "-p",
                    head,
                    "-m",
                    f"Checkpoint interrupted Task {expected} WIP",
                )
                self.repository.git(
                    "update-ref",
                    checkpoint_ref,
                    checkpoint_commit,
                    "0" * len(head),
                )
            checkpoint = {
                "version": 1,
                "task_id": expected,
                "attempt_id": evidence["attempt_id"],
                "launch_id": evidence["launch_id"],
                "recovery_attempt_number": MAX_GUARD_BUDGET_RECOVERIES,
                "original_base_sha": lease.get("original_base_origin_master_sha"),
                "base_sha": lease.get("base_origin_master_sha"),
                "head_sha": head,
                "checkpoint_ref": checkpoint_ref,
                "checkpoint_commit": checkpoint_commit,
                "checkpoint_tree": snapshot["tree"],
                "changed_paths": snapshot["changed_paths"],
                "patch_sha256": snapshot["patch_sha256"],
                "guard_stop_reason": "TOOL_ACTION_BUDGET_EXCEEDED",
                "command_started_at": evidence["command_started_at"],
                "guard_stopped_at": evidence["guard_stopped_at"],
                "guard_report_path": evidence["guard_report_path"],
                "guard_report_sha256": evidence["guard_report_sha256"],
                "events_path": evidence["events_path"],
                "events_sha256": evidence["events_sha256"],
                "worker_state_path": evidence["worker_state_path"],
                "worker_pid": evidence["worker_pid"],
                "created_at": utc_now(),
                "reason": reason.strip(),
            }
            self._validate_guard_wip_checkpoint(expected, worktree, lease, checkpoint)
            attempts = event.get("launch_attempts")
            if not isinstance(attempts, list) or not attempts or not isinstance(attempts[-1], dict):
                raise TaskSessionError("Guard interruption launch audit changed during recovery")
            timestamp = utc_now()
            attempts[-1].update(
                {
                    "state": "failed-guard-budget",
                    "finished_at": timestamp,
                    "worker_exit_code": 124,
                    "failure_kind": "TOOL_ACTION_BUDGET_EXCEEDED",
                    "failure_evidence": {
                        "guard_report_path": evidence["guard_report_path"],
                        "guard_report_sha256": evidence["guard_report_sha256"],
                        "events_path": evidence["events_path"],
                        "events_sha256": evidence["events_sha256"],
                        "completed_tool_actions": evidence["completed_tool_actions"],
                    },
                }
            )
            event["guard_budget_recovery"] = checkpoint
            event["guard_budget_recovery_reason"] = reason.strip()
            event["state"] = "prepared"
            event["head_sha"] = head
            for key in (
                "launch_id",
                "launch_claimed_at",
                "worker_started_at",
                "command_started_at",
                "worker_pid",
                "worker_process_instance",
                "worker_state_path",
            ):
                event.pop(key, None)
            lease["updated_at"] = timestamp
            StateStore.replace_json(lease_path, lease)
            return {
                "task_id": expected,
                "lease": dict(lease),
                "preimplementation_resume": dict(event),
                "control_state": control_state,
                "mutation_performed": True,
            }

    def resume_transport_interrupted(
        self,
        task_id: str,
        *,
        control_issue_number: int,
        reason: str,
        owner_authorize: bool,
    ) -> dict[str, Any]:
        expected = normalize_task_id(task_id)
        if not owner_authorize:
            raise TaskSessionError(
                "Post-start transport recovery requires explicit owner authorization"
            )
        if (
            isinstance(control_issue_number, bool)
            or not isinstance(control_issue_number, int)
            or control_issue_number < 1
        ):
            raise TaskSessionError(
                "Post-start transport recovery requires a valid control Issue number"
            )
        if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 1024:
            raise TaskSessionError(
                "Post-start transport recovery reason must be a bounded non-empty string"
            )
        if self.github is None:
            raise TaskSessionError("Post-start transport recovery requires online GitHub state")

        self.store.initialize()
        lease_path = self.store.task_lease_path(expected)
        with self.store.lock():
            leases = self.store.all_leases()
            matching = [
                item
                for item in leases
                if isinstance(item.get("task_id"), str) and str(item["task_id"]).upper() == expected
            ]
            lease = self.store.read_json(lease_path)
            if len(matching) != 1 or matching[0] != lease:
                raise TaskSessionError(f"Task {expected} has an ambiguous task lease")
            if (
                not isinstance(lease, dict)
                or lease.get("mode") != "write"
                or lease.get("owner_launch") is not True
                or lease.get("queue_mode") is True
                or self._lease_state(lease) != "implementation"
            ):
                raise TaskSessionError(f"Task {expected} has no active implementation lease")
            self._reject_shared_task_lease_identity(expected, lease, leases)
            document = find_task_document(self._canonical_root(), expected)
            if (
                not document.executable
                or "blocked" in document.status.lower()
                or "заблок" in document.status.lower()
                or Path(str(lease.get("canonical_task_path", ""))).resolve()
                != document.path.resolve()
                or self._validated_lease_concurrency_class(lease) != document.concurrency_class
                or lease.get("integration_policy") != document.integration_policy
                or lease.get("target_base_branch") != TARGET_BASE_BRANCH
            ):
                raise TaskSessionError("Task document or metadata no longer matches its lease")
            branch = str(lease.get("branch", ""))
            event = lease.get("preimplementation_resume")
            if (
                not isinstance(event, dict)
                or event.get("control_issue_number") != control_issue_number
            ):
                raise TaskSessionError("Task has no matching resumable pre-implementation launch")
            existing = event.get("transport_interruption_recovery")
            worktree = Path(str(lease["worktree"])).resolve()
            if isinstance(existing, Mapping):
                if event.get("transport_interruption_recovery_reason") != reason.strip():
                    raise TaskSessionError(
                        "The one-time post-start transport recovery was already launched or reconciled"
                    )
                control_state = self._preimplementation_issue_state(
                    expected,
                    control_issue_number,
                    branch,
                    document,
                    lease,
                    allow_guard_budget_failure=isinstance(
                        event.get("guard_budget_recovery"), Mapping
                    ),
                    allow_transport_failure=True,
                )
                if event.get("state") == "prepared" and "launch_id" not in event:
                    self._validate_preimplementation_worktree(expected, lease, prepared_event=event)
                    if not self._transport_control_state_matches_checkpoint(
                        control_state, existing
                    ):
                        raise TaskSessionError(
                            "Latest task transport blocker no longer matches its checkpoint"
                        )
                    return {
                        "task_id": expected,
                        "lease": dict(lease),
                        "preimplementation_resume": dict(event),
                        "control_state": control_state,
                        "mutation_performed": False,
                    }
                if event.get("state") != "worker-started":
                    raise TaskSessionError(
                        "The one-time post-start transport recovery was already launched or reconciled"
                    )
                self._post_start_transport_interruption_evidence(
                    expected, worktree, event, control_state
                )
                raise TaskSessionError("Post-start transport retry budget was already used")
            if event.get("state") != "worker-started":
                raise TaskSessionError("Task has no post-start transport interruption to recover")

            control_state = self._preimplementation_issue_state(
                expected,
                control_issue_number,
                branch,
                document,
                lease,
                allow_guard_budget_failure=isinstance(event.get("guard_budget_recovery"), Mapping),
                allow_transport_failure=True,
            )
            self._preimplementation_queue_claim(expected)
            if self._preimplementation_worker_state_paths(expected):
                raise TaskSessionError("Task has unreconciled worker state")
            if any(
                isinstance(item.get("head"), Mapping) and str(item["head"].get("ref", "")) == branch
                for item in self._github().open_pull_requests()
            ):
                raise TaskSessionError("Task branch already has an open pull request")

            canonical = self._canonical_root()
            self.repository.fetch_origin_master(cwd=canonical, prune=False)
            current_origin = self.repository.ref("origin/master")
            live_master = self._github().branch_head(TARGET_BASE_BRANCH)
            canonical_head = self.repository.head(cwd=canonical)
            canonical_changes = self._canonical_worktree_status()
            if current_origin != live_master:
                raise TaskSessionError(
                    "origin/master is not synchronized with live protected master"
                )
            if (
                self.repository.current_branch(cwd=canonical) != TARGET_BASE_BRANCH
                or self.repository.operation_issues(canonical)
                or canonical_changes
                or not self.repository.is_ancestor(canonical_head, current_origin)
            ):
                raise TaskSessionError(
                    "Canonical master is not clean and safely behind origin/master"
                )
            if not self.repository.is_ancestor(
                str(lease.get("base_origin_master_sha", "")), current_origin
            ):
                raise TaskSessionError("Task base is not an ancestor of synchronized origin/master")
            prepared_event = {**event, "state": "prepared"}
            worktree, branch, head = self._validate_preimplementation_worktree(
                expected,
                lease,
                prepared_event=prepared_event,
                allow_guard_dirty=True,
                validate_recovery_checkpoint=False,
            )
            if (
                head != event.get("head_sha")
                or self.repository.unique_commits(branch, base=current_origin)
                or self.repository.ref_exists(f"refs/remotes/origin/{branch}")
                or self.repository.remote_branch_exists(branch, cwd=canonical)
            ):
                raise TaskSessionError("Task branch is not a clean ancestor of protected master")
            evidence = self._post_start_transport_interruption_evidence(
                expected, worktree, event, control_state
            )
            if self._preimplementation_worker_state_paths(expected):
                raise TaskSessionError("Task worker state appeared during transport recovery")

            checkpoint_ref = (
                f"refs/codex/task-wip-checkpoints/task-{expected.lower()}/{evidence['attempt_id']}"
            )
            snapshot = self._guard_worktree_snapshot(expected, worktree, head)
            if (
                snapshot["tree"] != evidence["tree"]
                or snapshot["changed_paths"] != evidence["changed_paths"]
                or snapshot["patch_sha256"] != evidence["patch_sha256"]
            ):
                raise TaskSessionError(
                    "Task WIP changed while its transport checkpoint was prepared"
                )
            latest_evidence = self._post_start_transport_interruption_evidence(
                expected, worktree, event, control_state
            )
            if any(latest_evidence[key] != evidence[key] for key in evidence):
                raise TaskSessionError(
                    "Transport evidence or task WIP changed during checkpoint creation"
                )
            if self.repository.ref_exists(checkpoint_ref):
                checkpoint_commit = self.repository.ref(checkpoint_ref)
                existing_parents = self.repository.git(
                    "rev-list", "--parents", "-n", "1", checkpoint_commit
                ).split()
                existing_tree = self.repository.git("rev-parse", f"{checkpoint_commit}^{{tree}}")
                if (
                    existing_parents != [checkpoint_commit, head]
                    or existing_tree != snapshot["tree"]
                ):
                    raise TaskSessionError(
                        "A conflicting transport WIP checkpoint ref already exists"
                    )
            else:
                checkpoint_commit = self.repository.git(
                    "-c",
                    "user.name=Codex Controller",
                    "-c",
                    "user.email=codex-controller@users.noreply.github.com",
                    "commit-tree",
                    snapshot["tree"],
                    "-p",
                    head,
                    "-m",
                    f"Checkpoint interrupted Task {expected} transport WIP",
                )
                self.repository.git(
                    "update-ref",
                    checkpoint_ref,
                    checkpoint_commit,
                    "0" * len(head),
                )
            checkpoint = {
                "version": 1,
                "task_id": expected,
                "attempt_id": evidence["attempt_id"],
                "launch_id": evidence["launch_id"],
                "recovery_attempt_number": MAX_POST_START_TRANSPORT_RECOVERIES,
                "original_base_sha": lease.get("original_base_origin_master_sha"),
                "base_sha": lease.get("base_origin_master_sha"),
                "head_sha": head,
                "checkpoint_ref": checkpoint_ref,
                "checkpoint_commit": checkpoint_commit,
                "checkpoint_tree": snapshot["tree"],
                "changed_paths": snapshot["changed_paths"],
                "patch_sha256": snapshot["patch_sha256"],
                "transport_failure_kind": POST_START_TRANSPORT_FAILURE_KIND,
                "transport_signatures": evidence["transport_signatures"],
                "command_started_at": evidence["command_started_at"],
                "transport_stopped_at": evidence["transport_stopped_at"],
                "guard_report_path": evidence["guard_report_path"],
                "guard_report_sha256": evidence["guard_report_sha256"],
                "events_path": evidence["events_path"],
                "events_sha256": evidence["events_sha256"],
                "worker_state_path": evidence["worker_state_path"],
                "worker_pid": evidence["worker_pid"],
                "completed_tool_actions": evidence["completed_tool_actions"],
                "progress_events": evidence["progress_events"],
                "created_at": utc_now(),
                "reason": reason.strip(),
            }
            self._validate_guard_wip_checkpoint(expected, worktree, lease, checkpoint)
            attempts = event.get("launch_attempts")
            if not isinstance(attempts, list) or not attempts or not isinstance(attempts[-1], dict):
                raise TaskSessionError("Post-start transport launch audit changed during recovery")
            timestamp = utc_now()
            attempts[-1].update(
                {
                    "state": "failed-post-start-transport",
                    "finished_at": timestamp,
                    "failure_kind": POST_START_TRANSPORT_FAILURE_KIND,
                    "failure_evidence": {
                        "events_path": evidence["events_path"],
                        "events_sha256": evidence["events_sha256"],
                        "guard_report_path": evidence["guard_report_path"],
                        "guard_report_sha256": evidence["guard_report_sha256"],
                        "completed_tool_actions": evidence["completed_tool_actions"],
                        "progress_events": evidence["progress_events"],
                        "transport_signatures": evidence["transport_signatures"],
                    },
                }
            )
            event["transport_interruption_recovery"] = checkpoint
            event["transport_interruption_recovery_reason"] = reason.strip()
            event["state"] = "prepared"
            event["head_sha"] = head
            for key in (
                "launch_id",
                "launch_claimed_at",
                "worker_started_at",
                "command_started_at",
                "worker_pid",
                "worker_process_instance",
                "worker_state_path",
            ):
                event.pop(key, None)
            lease["updated_at"] = timestamp
            StateStore.replace_json(lease_path, lease)
            return {
                "task_id": expected,
                "lease": dict(lease),
                "preimplementation_resume": dict(event),
                "control_state": control_state,
                "mutation_performed": True,
            }

    def claim_preimplementation_worker_launch(self, task_id: str) -> dict[str, Any]:
        expected = normalize_task_id(task_id)
        lease_path = self.store.task_lease_path(expected)
        with self.store.lock():
            lease = self.store.read_json(lease_path)
            if not isinstance(lease, dict) or lease.get("task_id") != expected:
                raise TaskSessionError(f"No active task lease exists for Task {expected}")
            resume_event = lease.get("preimplementation_resume")
            if (
                self._lease_state(lease) != "implementation"
                or not isinstance(resume_event, dict)
                or resume_event.get("state") != "prepared"
            ):
                raise TaskSessionError("Task has no unclaimed prepared resume")
            worktree, branch, head = self._validate_preimplementation_worktree(
                expected, lease, prepared_event=resume_event
            )
            if head != resume_event.get("head_sha"):
                raise TaskSessionError("Prepared task branch changed before worker launch")
            control_issue = resume_event.get("control_issue_number")
            if isinstance(control_issue, bool) or not isinstance(control_issue, int):
                raise TaskSessionError("Prepared resume has an invalid control Issue identity")
            document = find_task_document(self._canonical_root(), expected)
            control_state = self._preimplementation_issue_state(
                expected,
                control_issue,
                branch,
                document,
                lease,
                allow_guard_budget_failure=isinstance(
                    resume_event.get("guard_budget_recovery"), Mapping
                ),
                allow_transport_failure=isinstance(
                    resume_event.get("transport_interruption_recovery"), Mapping
                ),
            )
            recovery = resume_event.get("guard_budget_recovery")
            transport_recovery = resume_event.get("transport_interruption_recovery")
            if (
                isinstance(recovery, Mapping)
                and not isinstance(transport_recovery, Mapping)
                and not self._guard_control_state_matches_checkpoint(control_state, recovery)
            ):
                raise TaskSessionError("Latest task guard blocker no longer matches its checkpoint")
            if isinstance(
                transport_recovery, Mapping
            ) and not self._transport_control_state_matches_checkpoint(
                control_state, transport_recovery
            ):
                raise TaskSessionError(
                    "Latest task transport blocker no longer matches its checkpoint"
                )
            self._preimplementation_queue_claim(expected)
            worker_states = self._preimplementation_worker_state_paths(expected)
            if worker_states:
                raise TaskSessionError("Task has unreconciled worker state")
            if any(
                isinstance(item.get("head"), Mapping) and str(item["head"].get("ref", "")) == branch
                for item in self._github().open_pull_requests()
            ):
                raise TaskSessionError("Task branch already has an open pull request")
            attempts = resume_event.get("launch_attempts", [])
            if not isinstance(attempts, list) or "launch_id" in resume_event:
                raise TaskSessionError("Prepared resume has unreconciled launch-attempt state")
            launch_id = uuid4().hex
            claimed_at = utc_now()
            attempts.append(
                {
                    "launch_id": launch_id,
                    "state": "launching",
                    "claimed_at": claimed_at,
                    "prelaunch_snapshot": self._guard_worktree_snapshot(expected, worktree, head),
                }
            )
            resume_event["launch_attempts"] = attempts
            resume_event.update(
                {
                    "state": "launching",
                    "launch_id": launch_id,
                    "launch_claimed_at": claimed_at,
                    "worktree": str(worktree),
                }
            )
            lease["updated_at"] = utc_now()
            StateStore.replace_json(lease_path, lease)
            return {"task_id": expected, "preimplementation_resume": resume_event}

    def release_preimplementation_worker_launch(
        self,
        task_id: str,
        *,
        launch_id: str,
        worker_state_path: Path,
        reason: str,
    ) -> dict[str, Any]:
        expected = normalize_task_id(task_id)
        path = worker_state_path.resolve()
        delivery_root = (
            self._canonical_root() / ".artifacts" / "tasks" / expected / "temporary" / "delivery"
        ).resolve()
        try:
            path.relative_to(delivery_root)
        except ValueError as error:
            raise TaskSessionError(
                "Worker state path is outside the task delivery artifacts"
            ) from error
        if path.exists():
            raise TaskSessionError("Worker state exists; launch requires reconciliation")
        if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 1024:
            raise TaskSessionError("Pre-worker failure reason must be a bounded non-empty string")
        lease_path = self.store.task_lease_path(expected)
        with self.store.lock():
            lease = self.store.read_json(lease_path)
            resume_event = (
                lease.get("preimplementation_resume") if isinstance(lease, Mapping) else None
            )
            if (
                not isinstance(lease, dict)
                or lease.get("task_id") != expected
                or not isinstance(resume_event, dict)
                or resume_event.get("state") != "launching"
                or resume_event.get("launch_id") != launch_id
            ):
                raise TaskSessionError("Task has no matching pre-implementation launch claim")
            attempts = resume_event.get("launch_attempts")
            if (
                not isinstance(attempts, list)
                or not attempts
                or not isinstance(attempts[-1], dict)
                or attempts[-1].get("launch_id") != launch_id
                or attempts[-1].get("state") != "launching"
            ):
                raise TaskSessionError("Task launch-attempt audit is malformed")
            released_at = utc_now()
            attempts[-1].update(
                {
                    "state": "no-worker-started",
                    "finished_at": released_at,
                    "reason": reason.strip(),
                    "worker_state_path": str(path),
                }
            )
            resume_event.pop("launch_id")
            resume_event.pop("launch_claimed_at", None)
            resume_event["state"] = "prepared"
            resume_event["last_prestart_failure"] = {
                "recorded_at": released_at,
                "reason": reason.strip(),
            }
            lease["updated_at"] = released_at
            StateStore.replace_json(lease_path, lease)
            return {"task_id": expected, "preimplementation_resume": resume_event}

    def record_preimplementation_worker_started(
        self, task_id: str, *, worker_state_path: Path
    ) -> dict[str, Any]:
        expected = normalize_task_id(task_id)
        path = worker_state_path.resolve()
        delivery_root = (
            self._canonical_root() / ".artifacts" / "tasks" / expected / "temporary" / "delivery"
        ).resolve()
        try:
            path.relative_to(delivery_root)
        except ValueError as error:
            raise TaskSessionError(
                "Worker state path is outside the task delivery artifacts"
            ) from error
        raw = self.store.read_json(path)
        command_process = raw.get("command_process") if isinstance(raw, Mapping) else None
        if (
            not isinstance(raw, Mapping)
            or raw.get("version") != 1
            or not isinstance(command_process, Mapping)
        ):
            raise TaskSessionError("Durable worker state has no actual command-start marker")
        worker_pid = command_process.get("pid")
        process_instance = command_process.get("process_instance")
        command_started_at = raw.get("command_started_at")
        if (
            isinstance(worker_pid, bool)
            or not isinstance(worker_pid, int)
            or worker_pid < 1
            or not isinstance(process_instance, Mapping)
            or not isinstance(process_instance.get("kind"), str)
            or not process_instance.get("kind")
            or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in process_instance.items()
            )
            or not isinstance(command_started_at, str)
            or not command_started_at
        ):
            raise TaskSessionError("Durable worker command-start marker is malformed")
        lease_path = self.store.task_lease_path(expected)
        with self.store.lock():
            lease = self.store.read_json(lease_path)
            resume_event = (
                lease.get("preimplementation_resume") if isinstance(lease, Mapping) else None
            )
            if (
                not isinstance(lease, dict)
                or lease.get("task_id") != expected
                or self._lease_state(lease) != "implementation"
                or not isinstance(resume_event, dict)
                or resume_event.get("state") != "launching"
            ):
                raise TaskSessionError("Task has no claimed pre-implementation worker launch")
            launch_id = resume_event.get("launch_id")
            attempts = resume_event.get("launch_attempts")
            if (
                not isinstance(launch_id, str)
                or not isinstance(attempts, list)
                or not attempts
                or not isinstance(attempts[-1], dict)
                or attempts[-1].get("launch_id") != launch_id
                or attempts[-1].get("state") != "launching"
            ):
                raise TaskSessionError("Task launch-attempt audit is malformed")
            started_at = utc_now()
            attempts[-1].update(
                {
                    "state": "worker-started",
                    "worker_started_at": started_at,
                    "worker_pid": worker_pid,
                    "worker_process_instance": dict(process_instance),
                    "worker_state_path": str(path),
                }
            )
            resume_event.update(
                {
                    "state": "worker-started",
                    "worker_started_at": started_at,
                    "command_started_at": command_started_at,
                    "worker_pid": worker_pid,
                    "worker_process_instance": dict(process_instance),
                    "worker_state_path": str(path),
                }
            )
            lease["updated_at"] = utc_now()
            StateStore.replace_json(lease_path, lease)
            return {"task_id": expected, "preimplementation_resume": resume_event}

    def record_queue_cycle(
        self,
        task_id: str,
        *,
        kind: str,
        reason: str,
    ) -> dict[str, Any]:
        """Record one bounded continuous-queue fix cycle in durable controller state."""

        expected = normalize_task_id(task_id)
        normalized_kind = kind.strip().lower()
        if normalized_kind not in {"review", "ci"}:
            raise TaskSessionError("queue cycle kind must be review or ci")
        if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 4096:
            raise TaskSessionError("queue cycle reason must be a bounded non-empty string")
        lease_path = self.store.task_lease_path(expected)
        with self.store.lock():
            lease = self.store.read_json(lease_path)
            if not isinstance(lease, dict) or lease.get("task_id") != expected:
                raise TaskSessionError(f"No active queue lease exists for Task {expected}")
            if lease.get("queue_mode") is not True:
                raise TaskSessionError(f"Task {expected} is not running in continuous queue mode")
            if self._lease_state(lease) in CLOSED_LEASE_STATES:
                raise TaskSessionError(f"Task {expected} is already terminal")
            raw_budget = lease.get("queue_budget")
            if not isinstance(raw_budget, dict):
                raise TaskSessionError(f"Task {expected} queue budget state is missing")
            review_cycles = raw_budget.get("review_fix_cycles", 0)
            ci_cycles = raw_budget.get("ci_fix_cycles", 0)
            scope_expansions = raw_budget.get("scope_expansions", 0)
            if any(
                isinstance(value, bool) or not isinstance(value, int)
                for value in (review_cycles, ci_cycles, scope_expansions)
            ):
                raise TaskSessionError(f"Task {expected} queue budget state is malformed")
            if normalized_kind == "review":
                review_cycles += 1
            else:
                ci_cycles += 1
            try:
                DEFAULT_QUEUE_BUDGET.check_counters(
                    tasks_started=1,
                    review_fix_cycles=review_cycles,
                    ci_fix_cycles=ci_cycles,
                    scope_expansions=scope_expansions,
                )
            except IssueWorkflowError as error:
                raise TaskSessionError(str(error)) from error
            raw_events = raw_budget.get("events", [])
            if not isinstance(raw_events, list) or len(raw_events) >= 6:
                raise TaskSessionError(f"Task {expected} queue cycle ledger is malformed or full")
            event = {
                "kind": normalized_kind,
                "reason": reason.strip(),
                "recorded_at": utc_now(),
                "sequence": len(raw_events) + 1,
            }
            budget = {
                "review_fix_cycles": review_cycles,
                "ci_fix_cycles": ci_cycles,
                "scope_expansions": scope_expansions,
                "events": [*raw_events, event],
            }
            lease["queue_budget"] = budget
            lease["updated_at"] = utc_now()
            StateStore.replace_json(lease_path, lease)
        return {"task_id": expected, "queue_budget": budget}

    def adopt_current(
        self,
        task_id: str,
        *,
        owner_launch: bool,
        session_label: str,
        offline: bool = False,
    ) -> dict[str, Any]:
        expected = normalize_task_id(task_id)
        if not owner_launch:
            raise TaskSessionError("adopt-current requires explicit --owner-launch evidence")
        branch = self.repository.git("branch", "--show-current")
        if not branch or task_id_from_branch(branch) != expected:
            raise TaskSessionError(f"Current branch {branch!r} does not match Task {expected}")
        canonical_refresh = self.refresh_canonical_master(offline=offline)
        if canonical_refresh["result"] == "BLOCKED":
            raise TaskSessionError(
                f"Task {expected} blocked by canonical master refresh: "
                f"{canonical_refresh['reason']}; {canonical_refresh['recovery_hint']}"
            )
        if canonical_refresh["result"] == "WAITING" and canonical_refresh["reason"] == (
            "another controller operation owns the coordination lock"
        ):
            raise TaskSessionError(
                "Coordination state is locked during canonical master refresh; retry adopt-current"
            )
        matches = [
            item
            for item in self.repository.worktrees()
            if item.path == self.repository.current_worktree
        ]
        if len(matches) != 1 or self.repository.current_worktree == self._canonical_root():
            raise TaskSessionError("Cannot adopt the controller worktree")
        if self.repository.status(self.repository.current_worktree):
            raise TaskSessionError(f"Task {expected} adoption refuses dirty worktree")
        if self.repository.operation_issues(self.repository.current_worktree):
            raise TaskSessionError("Cannot adopt a worktree with an active Git operation")
        base_sha = self.repository.ref("origin/master")
        head_sha = self.repository.ref("HEAD")
        if not self.repository.is_ancestor(base_sha, head_sha):
            raise TaskSessionError("Existing task branch is not based on current origin/master")
        document = find_task_document(self._canonical_root(), expected)
        if not document.executable:
            raise TaskSessionError(f"Task {expected} is umbrella/non-executable")
        if "blocked" in document.status.lower() or "заблок" in document.status.lower():
            raise TaskSessionError(f"Task {expected} status is blocked: {document.status}")
        owner_gate = document.owner_gate.strip()
        if owner_gate.lower() not in {"", "explicit-launch", "owner-launch", "none"}:
            label, _, requirement = owner_gate.partition(":")
            gate_name = label.strip().upper().replace("-", "_")
            concrete_requirement = requirement.strip() or "the task-declared evidence"
            raise TaskSessionError(
                f"Task {expected} blocked: {gate_name} is missing: {concrete_requirement}"
            )
        missing = sorted(set(document.dependencies) - self._completed_dependency_ids())
        if missing:
            raise TaskSessionError(
                f"Task {expected} has incomplete dependencies: {', '.join(missing)}"
            )
        self.store.initialize()
        lease = {
            "version": TASK_STATE_VERSION,
            "task_id": expected,
            "canonical_task_path": str(document.path),
            "branch": branch,
            "worktree": str(self.repository.current_worktree),
            "base_origin_master_sha": base_sha,
            "original_base_origin_master_sha": base_sha,
            "target_base_branch": TARGET_BASE_BRANCH,
            "mode": "write",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "lifecycle_state": "implementation",
            "session_label": session_label,
            "concurrency_class": document.concurrency_class,
            "integration_policy": "task-pr-to-master",
            "owner_launch": True,
            "adopted_existing_session": True,
            "canonical_master_refresh": canonical_refresh,
        }
        with self.store.lock():
            existing = self.store.all_leases()
            if any(item.get("task_id") == expected for item in existing):
                raise TaskSessionError(f"Task {expected} already has an active lease")
            duplicate = [
                item
                for item in existing
                if item.get("branch") == branch
                or str(item.get("worktree", "")).lower()
                == str(self.repository.current_worktree).lower()
            ]
            if duplicate:
                raise TaskSessionError(
                    f"Task {expected} adoption is ambiguous with an existing lease: "
                    + ", ".join(str(item.get("task_id")) for item in duplicate)
                )
            conflicts = self._implementation_lease_conflicts(
                existing,
                task_id=expected,
                concurrency_class=document.concurrency_class,
            )
            if conflicts:
                occupied = ", ".join(
                    f"Task {item['task_id']} ({item['concurrency_class']}, {item['lifecycle_state']})"
                    for item in conflicts
                )
                raise TaskSessionError(
                    f"Task {expected} blocked by incompatible implementation write lease(s): {occupied}"
                )
            self.store.create_json(self.store.task_lease_path(expected), lease)
        return lease

    def mark_ready(
        self,
        task_id: str,
        *,
        head_sha: str,
        quality_verdict: str,
        qa_verdict: str = "NOT_REQUIRED",
    ) -> dict[str, Any]:
        expected = normalize_task_id(task_id)
        if quality_verdict != "PASS":
            raise TaskSessionError("mark-ready requires deterministic quality checks PASS")
        if qa_verdict not in {"PASS", "NOT_REQUIRED"}:
            raise TaskSessionError("mark-ready QA verdict must be PASS or NOT_REQUIRED")
        lease_path = self.store.task_lease_path(expected)
        lease = self.store.read_json(lease_path)
        if lease is None or lease.get("mode") != "write":
            raise TaskSessionError("Only an active write lease can become PR-ready")
        if self._lease_state(lease) not in IMPLEMENTATION_STATES | READY_STATES | WAITING_STATES:
            raise TaskSessionError(
                f"Task {expected} cannot become PR-ready from {lease.get('lifecycle_state')}"
            )
        worktree = Path(str(lease["worktree"]))
        if self.repository.status(worktree):
            raise TaskSessionError("Task worktree must be clean before PR readiness")
        actual_branch = self.repository.git("branch", "--show-current", cwd=worktree)
        if actual_branch != lease.get("branch"):
            raise TaskSessionError("Task worktree branch does not match its lease")
        actual_head = self.repository.git("rev-parse", "HEAD", cwd=worktree)
        if actual_head != head_sha:
            raise TaskSessionError(f"Task HEAD {actual_head} != declared ready SHA {head_sha}")
        base_sha = str(lease["base_origin_master_sha"])
        if not self.repository.is_ancestor(base_sha, head_sha):
            raise TaskSessionError("Task HEAD does not descend from leased origin/master base")
        document = find_task_document(self._canonical_root(), expected)
        dependency_ids = _resolved_dependency_ids(
            lease.get("dependency_ids"), document.dependencies
        )
        validation_base_sha = base_sha
        current_origin_master = self.repository.ref("origin/master")
        if self.repository.is_ancestor(current_origin_master, head_sha):
            # A delivery refresh may have completed a rebase before recovery was
            # acknowledged. Validate only commits unique to the task when the
            # current protected-base ref is already an ancestor of its HEAD.
            validation_base_sha = current_origin_master
        validate_task_commit_messages(
            expected,
            self.repository.commits(f"{validation_base_sha}..{head_sha}"),
            dependency_ids=dependency_ids,
        )
        with self.store.lock():
            current = self.store.read_json(lease_path)
            if not isinstance(current, dict):
                raise TaskSessionError(
                    f"Task {expected} lease disappeared while readiness was validated"
                )
            if current.get("updated_at") != lease.get("updated_at"):
                raise TaskSessionError("Task lease changed while readiness was validated")
            delivery = self.store.delivery_state()
            reusable_sequence = (
                current.get("ready_sequence")
                if self._lease_state(current) in READY_STATES | WAITING_STATES
                and current.get("ready_head_sha") == head_sha
                and isinstance(current.get("ready_sequence"), int)
                else None
            )
            sequence = (
                int(reusable_sequence)
                if reusable_sequence is not None
                else int(delivery.get("next_sequence", 0)) + 1
            )
            delivery["next_sequence"] = max(int(delivery.get("next_sequence", 0)), sequence)
            delivery["updated_at"] = utc_now()
            StateStore.replace_json(self.store.delivery_path, delivery)
            now = utc_now()
            current.pop("review_verdict", None)
            current.update(
                {
                    "lifecycle_state": "ready-for-delivery",
                    "ready_head_sha": head_sha,
                    "ready_base_origin_master_sha": base_sha,
                    "ready_for_delivery_at": now,
                    "ready_sequence": sequence,
                    "quality_verdict": quality_verdict,
                    "qa_verdict": qa_verdict,
                    "clean_worktree": True,
                    "task_provenance": {
                        "task_id": expected,
                        "branch": current.get("branch"),
                        "base_sha": base_sha,
                        "head_sha": head_sha,
                    },
                    "updated_at": now,
                }
            )
            StateStore.replace_json(lease_path, current)
        return current

    def acquire_delivery(
        self,
        task_id: str,
        *,
        offline: bool = False,
        owner_priority_reason: str | None = None,
    ) -> dict[str, Any]:
        expected = normalize_task_id(task_id)
        priority_reason = normalize_delivery_priority_reason(owner_priority_reason)
        lease_path = self.store.task_lease_path(expected)
        with self.store.lock():
            lease = self.store.read_json(lease_path)
            if not isinstance(lease, dict) or lease.get("mode") != "write":
                raise TaskSessionError(f"Task {expected} has no active write lease")
            state = self._lease_state(lease)
            delivery = self.store.delivery_state()
            self._validate_lease_concurrency_classes(self.store.all_leases())
            owner = delivery.get("owner")
            owner_id = str(owner.get("task_id", "")).upper() if isinstance(owner, dict) else ""
            if owner_id == expected:
                if state not in DELIVERY_STATES:
                    raise TaskSessionError(
                        f"Task {expected} owns delivery lane with incompatible state {state}"
                    )
                return {
                    "acquired": True,
                    "task_id": expected,
                    "lifecycle_state": state,
                    "delivery": delivery,
                }
            if state not in READY_STATES | WAITING_STATES:
                raise TaskSessionError(
                    f"Task {expected} cannot acquire delivery lane from {lease.get('lifecycle_state')}"
                )
            production_active = False if offline else self._active_production_deployment()

            candidates = self._delivery_candidates(self.store.all_leases())
            candidate_ids = [normalize_task_id(str(item["task_id"])) for item in candidates]
            if owner_id or production_active:
                lease["lifecycle_state"] = "waiting-for-delivery"
                lease["delivery_waiting_since"] = lease.get("delivery_waiting_since") or utc_now()
                lease["updated_at"] = utc_now()
                StateStore.replace_json(lease_path, lease)
                return {
                    "acquired": False,
                    "task_id": expected,
                    "lifecycle_state": "waiting-for-delivery",
                    "delivery_owner": owner_id,
                    "delivery_blocker": (
                        "active production deployment" if production_active else None
                    ),
                    "queue_position": (
                        candidate_ids.index(expected) + 1 if expected in candidate_ids else None
                    ),
                }
            if not candidate_ids:
                raise TaskSessionError("Delivery queue is empty while acquiring a task")
            if candidate_ids[0] != expected and priority_reason is None:
                lease["lifecycle_state"] = "waiting-for-delivery"
                lease["delivery_waiting_since"] = lease.get("delivery_waiting_since") or utc_now()
                lease["updated_at"] = utc_now()
                StateStore.replace_json(lease_path, lease)
                return {
                    "acquired": False,
                    "task_id": expected,
                    "lifecycle_state": "waiting-for-delivery",
                    "delivery_owner": None,
                    "queue_position": candidate_ids.index(expected) + 1,
                    "queue_head": candidate_ids[0],
                }
            priority_override: dict[str, Any] | None = None
            if candidate_ids[0] != expected:
                priority_override = {
                    "task_id": expected,
                    "skipped_task_ids": candidate_ids[: candidate_ids.index(expected)],
                    "reason": priority_reason,
                    "authorized_at": utc_now(),
                }
            promoted = self._promote_next_delivery_locked(
                delivery,
                requested_task_id=expected if priority_override is not None else None,
                priority_override=priority_override,
            )
            if promoted is None or str(promoted.get("task_id", "")).upper() != expected:
                raise TaskSessionError("Delivery lane promotion did not select the requested task")
            current = self.store.read_json(lease_path)
            if not isinstance(current, dict):
                raise TaskSessionError(
                    f"Task {expected} lease disappeared after delivery acquisition"
                )
            if priority_override is not None:
                current["delivery_priority_override"] = priority_override
                StateStore.replace_json(lease_path, current)
            return {
                "acquired": True,
                "task_id": expected,
                "lifecycle_state": self._lease_state(current),
                "delivery": delivery,
                "priority_override": priority_override,
            }

    def _mark_delivery_refresh_failure(self, task_id: str, reason: str) -> None:
        expected = normalize_task_id(task_id)
        with self.store.lock():
            lease_path = self.store.task_lease_path(expected)
            lease = self.store.read_json(lease_path)
            delivery = self.store.delivery_state()
            owner = delivery.get("owner")
            if (
                isinstance(lease, dict)
                and isinstance(owner, dict)
                and str(owner.get("task_id", "")).upper() == expected
            ):
                now = utc_now()
                lease.update(
                    {
                        "lifecycle_state": "recovery-required",
                        "recovery_reason": reason,
                        "delivery_failed_at": now,
                        "updated_at": now,
                    }
                )
                lease.pop("delivery_owner", None)
                delivery["owner"] = None
                delivery["updated_at"] = now
                StateStore.replace_json(lease_path, lease)
                StateStore.replace_json(self.store.delivery_path, delivery)
                self._promote_next_delivery_locked(delivery)

    def refresh_for_delivery(self, task_id: str, *, offline: bool = False) -> dict[str, Any]:
        expected = normalize_task_id(task_id)
        lease, _ = self._require_delivery_owner(expected)
        if self._lease_state(lease) not in DELIVERY_STATES:
            raise TaskSessionError(
                f"Task {expected} cannot refresh for delivery from {lease.get('lifecycle_state')}"
            )
        canonical_refresh = self.refresh_canonical_master(
            offline=offline, delivery_task_id=expected
        )
        if canonical_refresh["result"] == "BLOCKED":
            reason = (
                f"Task {expected} canonical master refresh blocked: {canonical_refresh['reason']}"
            )
            raise TaskSessionError(f"{reason}; {canonical_refresh['recovery_hint']}")
        if canonical_refresh["result"] == "WAITING" and not (
            offline and canonical_refresh["reason"].startswith("offline mode")
        ):
            raise TaskSessionError(
                f"Task {expected} canonical master refresh is waiting: "
                f"{canonical_refresh['reason']}; {canonical_refresh['recovery_hint']}"
            )
        worktree = Path(str(lease.get("worktree", ""))).resolve()
        if self.repository.status(worktree):
            raise TaskSessionError(f"Task {expected} delivery refresh refuses dirty worktree")
        operations = self.repository.operation_issues(worktree)
        if operations:
            raise TaskSessionError(
                f"Task {expected} delivery refresh refuses interrupted Git operation: {operations}"
            )
        head_before = self.repository.head(cwd=worktree)
        old_base = str(lease.get("base_origin_master_sha", ""))
        if not old_base:
            raise TaskSessionError(f"Task {expected} lease has no base SHA")
        try:
            with self.store.lock():
                lease_path = self.store.task_lease_path(expected)
                current = self.store.read_json(lease_path)
                delivery = self.store.delivery_state()
                owner = delivery.get("owner")
                if (
                    not isinstance(current, dict)
                    or not isinstance(owner, dict)
                    or str(owner.get("task_id", "")).upper() != expected
                ):
                    raise TaskSessionError("Task delivery ownership changed before master refresh")
                ready_head = str(current.get("ready_head_sha", ""))
                if not ready_head or head_before != ready_head:
                    raise TaskSessionError(
                        "Task branch HEAD changed after PR readiness; rerun targeted checks and applicable QA "
                        "before delivery refresh"
                    )
                current.update({"lifecycle_state": "delivery-refreshing", "updated_at": utc_now()})
                StateStore.replace_json(lease_path, current)
            self.repository.fetch_origin_master(cwd=worktree)
            current_base = self.repository.ref("origin/master")
            if not offline:
                self._verify_live_master(current_base)
            if current_base != old_base:
                if not self.repository.is_ancestor(old_base, head_before):
                    raise TaskSessionError(
                        f"Task {expected} branch no longer descends from its leased base {old_base}"
                    )
                if not self.repository.is_ancestor(current_base, head_before):
                    self.repository.git("rebase", current_base, cwd=worktree)
            head_after = self.repository.head(cwd=worktree)
        except TaskSessionError as error:
            self._mark_delivery_refresh_failure(expected, str(error))
            raise TaskSessionError(
                f"Task {expected} delivery refresh failed and was preserved for recovery: {error}"
            ) from error

        with self.store.lock():
            lease_path = self.store.task_lease_path(expected)
            current = self.store.read_json(lease_path)
            delivery = self.store.delivery_state()
            owner = delivery.get("owner")
            if (
                not isinstance(current, dict)
                or not isinstance(owner, dict)
                or str(owner.get("task_id", "")).upper() != expected
            ):
                raise TaskSessionError("Task delivery ownership changed during master refresh")
            if self._lease_state(current) not in DELIVERY_STATES:
                raise TaskSessionError("Task delivery state changed during master refresh")
            now = utc_now()
            current.update(
                {
                    "base_origin_master_sha": current_base,
                    "delivery_base_origin_master_sha": current_base,
                    "delivery_head_sha": head_after,
                    "ready_head_sha": head_after,
                    "ready_base_origin_master_sha": current_base,
                    "task_provenance": {
                        "task_id": expected,
                        "branch": current.get("branch"),
                        "base_sha": current_base,
                        "head_sha": head_after,
                        "original_base_sha": current.get("original_base_origin_master_sha"),
                    },
                    "delivery_anchor": {
                        "task_id": expected,
                        "branch": current.get("branch"),
                        "base_sha": current_base,
                        "head_sha": head_after,
                    },
                    "canonical_master_refresh": canonical_refresh,
                    "lifecycle_state": "delivering",
                    "updated_at": now,
                }
            )
            StateStore.replace_json(lease_path, current)
        return current

    def validate_delivery(self, task_id: str, *, offline: bool = False) -> dict[str, Any]:
        expected = normalize_task_id(task_id)
        lease, _ = self._require_delivery_owner(expected)
        worktree = Path(str(lease.get("worktree", ""))).resolve()
        if self._lease_state(lease) not in {"delivering", "delivery-gate"}:
            raise TaskSessionError(f"Task {expected} is not ready for final delivery validation")
        if self.repository.status(worktree):
            raise TaskSessionError(f"Task {expected} delivery worktree is dirty")
        operations = self.repository.operation_issues(worktree)
        if operations:
            raise TaskSessionError(
                f"Task {expected} delivery worktree is interrupted: {operations}"
            )
        base_sha = str(lease.get("base_origin_master_sha", ""))
        head_sha = self.repository.head(cwd=worktree)
        if self.repository.ref("origin/master") != base_sha:
            raise TaskSessionError(
                f"Task {expected} origin/master changed after refresh; acquire a new delivery refresh"
            )
        if not offline:
            self._verify_live_master(base_sha)
        if lease.get("delivery_head_sha") != head_sha:
            raise TaskSessionError(
                f"Task {expected} delivery HEAD changed after refresh: {head_sha}"
            )
        document = find_task_document(self._canonical_root(), expected)
        dependency_ids = _resolved_dependency_ids(
            lease.get("dependency_ids"), document.dependencies
        )
        validate_task_commit_messages(
            expected,
            self.repository.commits(f"{base_sha}..{head_sha}"),
            dependency_ids=dependency_ids,
        )
        with self.store.lock():
            lease_path = self.store.task_lease_path(expected)
            current = self.store.read_json(lease_path)
            delivery = self.store.delivery_state()
            owner = delivery.get("owner")
            if (
                not isinstance(current, dict)
                or not isinstance(owner, dict)
                or str(owner.get("task_id", "")).upper() != expected
            ):
                raise TaskSessionError(
                    "Task delivery ownership changed during delivery anchor validation"
                )
            current_head = self.repository.head(cwd=worktree)
            if current.get("base_origin_master_sha") != base_sha:
                raise TaskSessionError(
                    "Task delivery base changed during delivery anchor validation"
                )
            if current.get("delivery_head_sha") != current_head or current_head != head_sha:
                raise TaskSessionError(
                    "Task delivery HEAD changed during delivery anchor validation"
                )
            current.update(
                {
                    "lifecycle_state": "delivery-gate",
                    "delivery_anchor": {
                        "task_id": expected,
                        "branch": current.get("branch"),
                        "base_sha": base_sha,
                        "head_sha": current_head,
                    },
                    "updated_at": utc_now(),
                }
            )
            StateStore.replace_json(lease_path, current)
        return current

    def release_delivery(
        self, task_id: str, *, reason: str, offline: bool = False
    ) -> dict[str, Any]:
        expected = normalize_task_id(task_id)
        _, _ = self._require_delivery_owner(expected)
        with self.store.lock():
            lease_path = self.store.task_lease_path(expected)
            current = self.store.read_json(lease_path)
            latest_delivery = self.store.delivery_state()
            owner = latest_delivery.get("owner")
            if (
                not isinstance(current, dict)
                or not isinstance(owner, dict)
                or str(owner.get("task_id", "")).upper() != expected
            ):
                raise TaskSessionError("Task delivery ownership changed before release")
            production_active = False if offline else self._active_production_deployment()
            now = utc_now()
            current.update(
                {
                    "lifecycle_state": "recovery-required",
                    "recovery_reason": reason,
                    "delivery_released_at": now,
                    "updated_at": now,
                }
            )
            current.pop("delivery_owner", None)
            latest_delivery["owner"] = None
            latest_delivery["updated_at"] = now
            StateStore.replace_json(lease_path, current)
            StateStore.replace_json(self.store.delivery_path, latest_delivery)
            next_owner = None
            if not production_active:
                next_owner = self._promote_next_delivery_locked(latest_delivery)
            else:
                current["delivery_handoff_blocker"] = "active production deployment"
            current["delivery_next_owner"] = next_owner
            StateStore.replace_json(lease_path, current)
        return current

    def reopen_for_review(self, task_id: str, *, reason: str) -> dict[str, Any]:
        expected = normalize_task_id(task_id)
        lease, _ = self._require_delivery_owner(expected)
        if self._lease_state(lease) not in DELIVERY_STATES:
            raise TaskSessionError(
                f"Task {expected} cannot reopen for review from {lease.get('lifecycle_state')}"
            )
        worktree = Path(str(lease.get("worktree", ""))).resolve()
        if self.repository.status(worktree):
            raise TaskSessionError(f"Task {expected} review reopen refuses dirty worktree")
        operations = self.repository.operation_issues(worktree)
        if operations:
            raise TaskSessionError(
                f"Task {expected} review reopen refuses interrupted Git operation: {operations}"
            )
        with self.store.lock():
            lease_path = self.store.task_lease_path(expected)
            current = self.store.read_json(lease_path)
            delivery = self.store.delivery_state()
            owner = delivery.get("owner")
            if (
                not isinstance(current, dict)
                or not isinstance(owner, dict)
                or str(owner.get("task_id", "")).upper() != expected
            ):
                raise TaskSessionError("Task delivery ownership changed before review reopen")
            if self._lease_state(current) not in DELIVERY_STATES:
                raise TaskSessionError("Task delivery state changed before review reopen")
            now = utc_now()
            for key in (
                "delivery_owner",
                "delivery_acquired_at",
                "delivery_base_origin_master_sha",
                "delivery_head_sha",
                "delivery_anchor",
                "ready_head_sha",
                "ready_base_origin_master_sha",
                "ready_for_delivery_at",
                "ready_sequence",
                "quality_verdict",
                "qa_verdict",
                "task_provenance",
                "canonical_master_refresh",
                "delivery_priority_override",
            ):
                current.pop(key, None)
            current.update(
                {
                    "lifecycle_state": "review",
                    "review_reopened_at": now,
                    "review_reopen_reason": reason,
                    "updated_at": now,
                }
            )
            delivery["owner"] = None
            delivery.pop("priority_override", None)
            delivery["updated_at"] = now
            StateStore.replace_json(lease_path, current)
            StateStore.replace_json(self.store.delivery_path, delivery)
        return current

    def reopen_after_production(
        self,
        task_id: str,
        *,
        reason: str,
        owner_authorize: bool,
    ) -> dict[str, Any]:
        """Safely continue a terminal task while preserving its prior production evidence."""

        expected = normalize_task_id(task_id)
        if not owner_authorize:
            raise TaskSessionError("reopen-after-production requires explicit owner authorization")
        if not reason.strip():
            raise TaskSessionError("reopen-after-production requires a non-empty reason")
        lease, _delivery = self._require_delivery_owner(expected)
        if self._lease_state(lease) != "production-success":
            raise TaskSessionError(
                f"Task {expected} cannot continue from {lease.get('lifecycle_state')}"
            )
        history_path = self.store.history / f"task-{expected}.json"
        history = self.store.read_json(history_path)
        if not isinstance(history, dict) or history.get("state") != "production-success":
            raise TaskSessionError(
                f"Task {expected} continuation requires production-success history"
            )
        worktree = Path(str(lease.get("worktree", ""))).resolve()
        if self.repository.status(worktree):
            raise TaskSessionError(f"Task {expected} continuation refuses dirty worktree")
        operations = self.repository.operation_issues(worktree)
        if operations:
            raise TaskSessionError(
                f"Task {expected} continuation refuses interrupted Git operation: {operations}"
            )
        previous = dict(history)
        now = utc_now()
        with self.store.lock():
            lease_path = self.store.task_lease_path(expected)
            current = self.store.read_json(lease_path)
            current_delivery = self.store.delivery_state()
            current_history = self.store.read_json(history_path)
            owner = current_delivery.get("owner")
            if (
                not isinstance(current, dict)
                or self._lease_state(current) != "production-success"
                or not isinstance(owner, dict)
                or str(owner.get("task_id", "")).upper() != expected
            ):
                raise TaskSessionError(
                    f"Task {expected} production continuation ownership changed before reopen"
                )
            if current_history != history:
                raise TaskSessionError("Task production history changed before continuation reopen")
            for key in (
                "delivery_owner",
                "delivery_acquired_at",
                "delivery_base_origin_master_sha",
                "delivery_head_sha",
                "delivery_anchor",
                "ready_head_sha",
                "ready_base_origin_master_sha",
                "ready_for_delivery_at",
                "ready_sequence",
                "quality_verdict",
                "qa_verdict",
                "task_provenance",
                "canonical_master_refresh",
                "delivery_priority_override",
                "merge_sha",
                "deployed_sha",
            ):
                current.pop(key, None)
            current.update(
                {
                    "lifecycle_state": "review",
                    "review_reopened_at": now,
                    "review_reopen_reason": reason,
                    "continuation_of_production_success": {
                        "merge_sha": previous.get("merge_sha"),
                        "deployed_sha": previous.get("deployed_sha"),
                        "pr_number": previous.get("pr_number"),
                    },
                    "updated_at": now,
                }
            )
            continuation_history = {
                "version": TASK_STATE_VERSION,
                "task_id": expected,
                "state": "continuation-in-progress",
                "continuation_started_at": now,
                "continuation_reason": reason,
                "previous_production_success": previous,
            }
            current_delivery["owner"] = None
            current_delivery.pop("priority_override", None)
            current_delivery["updated_at"] = now
            StateStore.replace_json(lease_path, current)
            StateStore.replace_json(history_path, continuation_history)
            StateStore.replace_json(self.store.delivery_path, current_delivery)
        return current

    def resolve_recovery(
        self, task_id: str, *, reason: str, owner_authorize: bool
    ) -> dict[str, Any]:
        """Return a clean, uniquely anchored recovery lease to review safely."""

        expected = normalize_task_id(task_id)
        if not owner_authorize:
            raise TaskSessionError("resolve-recovery requires explicit owner authorization")
        if not reason.strip():
            raise TaskSessionError("resolve-recovery requires a non-empty reason")

        lease_path = self.store.task_lease_path(expected)
        lease = self.store.read_json(lease_path)
        if not isinstance(lease, dict):
            raise TaskSessionError(f"Task {expected} has no active recovery lease")
        if self._lease_state(lease) not in RECOVERY_STATES:
            raise TaskSessionError(
                f"Task {expected} cannot resolve recovery from {lease.get('lifecycle_state')}"
            )
        delivery = self.store.delivery_state()
        if delivery.get("owner") is not None:
            raise TaskSessionError(
                "resolve-recovery refuses to change a task while the delivery lane has an owner"
            )

        def verify_anchor(current: Mapping[str, Any]) -> tuple[Path, str]:
            if current.get("mode") != "write":
                raise TaskSessionError(f"Task {expected} recovery lease is not writable")
            if str(current.get("task_id", "")).upper() != expected:
                raise TaskSessionError(f"Task {expected} recovery lease has mismatched task ID")
            branch = current.get("branch")
            worktree_value = current.get("worktree")
            if not isinstance(branch, str) or not isinstance(worktree_value, str):
                raise TaskSessionError(
                    f"Task {expected} recovery lease has no valid branch/worktree anchor"
                )
            if task_id_from_branch(branch) != expected:
                raise TaskSessionError(f"Task {expected} recovery lease has an invalid branch")
            worktree = Path(worktree_value).resolve()
            matches = [
                item
                for item in self.repository.worktrees()
                if str(item.path.resolve()).casefold() == str(worktree).casefold()
                or item.branch == branch
            ]
            if len(matches) != 1 or matches[0].branch != branch:
                raise TaskSessionError(
                    f"Task {expected} recovery requires exactly one matching branch/worktree"
                )
            branch_refs = [
                line.removeprefix("refs/heads/")
                for line in self.repository.git(
                    "for-each-ref", "--format=%(refname)", f"refs/heads/{branch}"
                ).splitlines()
                if line
            ]
            if branch_refs != [branch]:
                raise TaskSessionError(
                    f"Task {expected} recovery requires exactly one local task branch"
                )
            if self.repository.status(worktree):
                raise TaskSessionError(
                    f"Task {expected} recovery resolution refuses a dirty worktree"
                )
            operations = self.repository.operation_issues(worktree)
            if operations:
                raise TaskSessionError(
                    f"Task {expected} recovery resolution refuses interrupted Git operation: "
                    f"{operations}"
                )
            head = self.repository.head(cwd=worktree)
            base_sha = str(current.get("base_origin_master_sha", ""))
            if not base_sha or not self.repository.is_ancestor(base_sha, head):
                raise TaskSessionError(
                    f"Task {expected} recovery worktree does not descend from its leased base"
                )
            return worktree, head

        verify_anchor(lease)
        with self.store.lock():
            current = self.store.read_json(lease_path)
            current_delivery = self.store.delivery_state()
            if not isinstance(current, dict):
                raise TaskSessionError(f"Task {expected} recovery lease disappeared")
            if current.get("updated_at") != lease.get("updated_at"):
                raise TaskSessionError("Task recovery lease changed during resolution")
            if current_delivery.get("owner") is not None:
                raise TaskSessionError(
                    "resolve-recovery refuses to change a task while the delivery lane has an owner"
                )
            if self._lease_state(current) not in RECOVERY_STATES:
                raise TaskSessionError("Task recovery state changed during resolution")
            verify_anchor(current)
            self._validated_lease_concurrency_class(current)
            now = utc_now()
            for key in (
                "delivery_owner",
                "delivery_acquired_at",
                "delivery_base_origin_master_sha",
                "delivery_head_sha",
                "delivery_anchor",
                "delivery_released_at",
                "delivery_failed_at",
                "delivery_handoff_blocker",
                "delivery_next_owner",
                "ready_head_sha",
                "ready_base_origin_master_sha",
                "ready_for_delivery_at",
                "ready_sequence",
                "quality_verdict",
                "qa_verdict",
                "task_provenance",
                "canonical_master_refresh",
            ):
                current.pop(key, None)
            current.update(
                {
                    "lifecycle_state": "review",
                    "recovery_resolved_at": now,
                    "recovery_resolution_reason": reason,
                    "updated_at": now,
                }
            )
            current_delivery["owner"] = None
            current_delivery["updated_at"] = now
            StateStore.replace_json(lease_path, current)
            StateStore.replace_json(self.store.delivery_path, current_delivery)
        return current

    def supersede(self, task_id: str, *, reason: str, owner_authorize: bool) -> dict[str, Any]:
        """Close a task as superseded while retaining its clean Git anchor."""

        expected = normalize_task_id(task_id)
        if not owner_authorize:
            raise TaskSessionError("supersede requires explicit owner authorization")
        normalized_reason = reason.strip()
        if not normalized_reason or len(normalized_reason) > 4096:
            raise TaskSessionError("supersede reason must be a bounded non-empty string")

        lease_path = self.store.task_lease_path(expected)
        lease = self.store.read_json(lease_path)
        if not isinstance(lease, dict):
            raise TaskSessionError(f"Task {expected} has no active lease")

        initial_state = self._lease_state(lease)
        if initial_state in TERMINAL_LEASE_STATES:
            raise TaskSessionError(
                f"Task {expected} cannot be superseded from terminal state {initial_state}"
            )
        if initial_state not in (
            IMPLEMENTATION_STATES
            | READY_STATES
            | WAITING_STATES
            | RECOVERY_STATES
            | SUPERSEDED_LEASE_STATES
        ):
            raise TaskSessionError(
                f"Task {expected} cannot be superseded from {lease.get('lifecycle_state')}"
            )

        def verify_anchor(current: Mapping[str, Any]) -> tuple[Path, str]:
            if current.get("mode") != "write":
                raise TaskSessionError(f"Task {expected} supersede lease is not writable")
            if str(current.get("task_id", "")).upper() != expected:
                raise TaskSessionError(f"Task {expected} supersede lease has mismatched task ID")
            branch = current.get("branch")
            worktree_value = current.get("worktree")
            if not isinstance(branch, str) or not isinstance(worktree_value, str):
                raise TaskSessionError(
                    f"Task {expected} supersede lease has no valid branch/worktree anchor"
                )
            if task_id_from_branch(branch) != expected:
                raise TaskSessionError(f"Task {expected} supersede lease has an invalid branch")
            worktree = Path(worktree_value).resolve()
            matches = [
                item
                for item in self.repository.worktrees()
                if str(item.path.resolve()).casefold() == str(worktree).casefold()
                or item.branch == branch
            ]
            if len(matches) != 1 or matches[0].branch != branch:
                raise TaskSessionError(
                    f"Task {expected} supersede requires exactly one matching branch/worktree"
                )
            branch_refs = [
                line.removeprefix("refs/heads/")
                for line in self.repository.git(
                    "for-each-ref", "--format=%(refname)", f"refs/heads/{branch}"
                ).splitlines()
                if line
            ]
            if branch_refs != [branch]:
                raise TaskSessionError(
                    f"Task {expected} supersede requires exactly one local task branch"
                )
            if self.repository.status(worktree):
                raise TaskSessionError(f"Task {expected} supersede refuses a dirty worktree")
            operations = self.repository.operation_issues(worktree)
            if operations:
                raise TaskSessionError(
                    f"Task {expected} supersede refuses interrupted Git operation: {operations}"
                )
            head = self.repository.head(cwd=worktree)
            base_sha = str(current.get("base_origin_master_sha", ""))
            if not base_sha or not self.repository.is_ancestor(base_sha, head):
                raise TaskSessionError(
                    f"Task {expected} supersede worktree does not descend from its leased base"
                )
            return worktree, head

        def verified_open_pr_numbers(branch: object) -> list[str]:
            if not isinstance(branch, str) or not branch:
                raise TaskSessionError(
                    f"Task {expected} supersede lease has no valid branch anchor"
                )
            try:
                open_prs = self._github().open_pull_requests()
            except (TaskSessionError, OSError) as error:
                raise TaskSessionError(
                    f"Task {expected} supersede requires a verified open-PR inventory"
                ) from error
            matching: list[str] = []
            for pull_request in open_prs:
                if not isinstance(pull_request, Mapping):
                    raise TaskSessionError("GitHub returned an invalid open-PR inventory")
                head = pull_request.get("head", {})
                if not isinstance(head, Mapping):
                    raise TaskSessionError("GitHub returned an open PR without a valid head")
                if head.get("ref") == branch:
                    matching.append(str(pull_request.get("number", "<unknown>")))
            return matching

        delivery = self.store.delivery_state()
        owner = delivery.get("owner")
        owner_id = str(owner.get("task_id", "")).upper() if isinstance(owner, dict) else ""
        if owner_id == expected:
            raise TaskSessionError(
                f"Task {expected} cannot be superseded while owning the delivery lane"
            )
        matching_pr_numbers = verified_open_pr_numbers(lease.get("branch"))
        if matching_pr_numbers:
            raise TaskSessionError(
                f"Task {expected} supersede refuses open task PR(s): "
                + ", ".join(sorted(matching_pr_numbers))
            )
        verify_anchor(lease)

        with self.store.lock():
            current = self.store.read_json(lease_path)
            current_delivery = self.store.delivery_state()
            if not isinstance(current, dict):
                raise TaskSessionError(f"Task {expected} lease disappeared during supersede")
            if current.get("updated_at") != lease.get("updated_at"):
                raise TaskSessionError("Task supersede lease changed during transition")
            if current_delivery.get("owner") != delivery.get("owner"):
                raise TaskSessionError("Delivery ownership changed during task supersede")
            current_owner = current_delivery.get("owner")
            current_owner_id = (
                str(current_owner.get("task_id", "")).upper()
                if isinstance(current_owner, dict)
                else ""
            )
            if current_owner_id == expected:
                raise TaskSessionError(
                    f"Task {expected} cannot be superseded while owning the delivery lane"
                )
            current_state = self._lease_state(current)
            if current_state in TERMINAL_LEASE_STATES:
                raise TaskSessionError(
                    f"Task {expected} cannot be superseded from terminal state {current_state}"
                )
            if current_state in SUPERSEDED_LEASE_STATES:
                verify_anchor(current)
                return current
            if current_state not in (
                IMPLEMENTATION_STATES | READY_STATES | WAITING_STATES | RECOVERY_STATES
            ):
                raise TaskSessionError(
                    f"Task {expected} cannot be superseded from {current.get('lifecycle_state')}"
                )
            verify_anchor(current)
            matching_pr_numbers = verified_open_pr_numbers(current.get("branch"))
            if matching_pr_numbers:
                raise TaskSessionError(
                    f"Task {expected} supersede refuses open task PR(s): "
                    + ", ".join(sorted(matching_pr_numbers))
                )
            self._validated_lease_concurrency_class(current)
            previous_state = current_state
            now = utc_now()
            for key in (
                "delivery_owner",
                "delivery_acquired_at",
                "delivery_base_origin_master_sha",
                "delivery_head_sha",
                "delivery_anchor",
                "delivery_released_at",
                "delivery_failed_at",
                "delivery_handoff_blocker",
                "delivery_next_owner",
                "delivery_waiting_since",
                "ready_head_sha",
                "ready_base_origin_master_sha",
                "ready_for_delivery_at",
                "ready_sequence",
                "quality_verdict",
                "qa_verdict",
                "task_provenance",
                "canonical_master_refresh",
                "delivery_priority_override",
            ):
                current.pop(key, None)
            current.update(
                {
                    "lifecycle_state": "superseded",
                    "superseded_from_state": previous_state,
                    "superseded_at": now,
                    "superseded_reason": normalized_reason,
                    "owner_authorized": True,
                    "updated_at": now,
                }
            )
            StateStore.replace_json(lease_path, current)
        return current

    def record_production_success(
        self,
        task_id: str,
        *,
        pr_number: int,
        merge_sha: str,
        deployed_sha: str,
    ) -> dict[str, Any]:
        expected = normalize_task_id(task_id)
        lease, _ = self._require_delivery_owner(expected)
        lease_path = self.store.task_lease_path(expected)
        if self._lease_state(lease) != "delivery-gate":
            raise TaskSessionError(
                "Production completion requires a validated final delivery gate, found "
                f"{lease.get('lifecycle_state')}"
            )
        if merge_sha != deployed_sha:
            raise TaskSessionError("Deployed revision must equal the exact merged master SHA")
        if self.repository.ref("origin/master") != deployed_sha:
            raise TaskSessionError(
                "Production completion requires current origin/master at deployed SHA"
            )
        self._verify_live_master(deployed_sha)
        pull_request = self._github().pull_request(pr_number)
        commits = self._github().pull_request_commits(pr_number)
        checks = self._github().check_runs(str(pull_request["head"]["sha"]))
        files = self._github().pull_request_files(pr_number)
        worktree = Path(str(lease.get("worktree", ""))).resolve()
        head_sha = self.repository.head(cwd=worktree)
        if pull_request.get("head", {}).get("sha") != head_sha:
            raise TaskSessionError("Merged PR head does not match the delivery worktree HEAD")
        if lease.get("delivery_head_sha") != head_sha:
            raise TaskSessionError("Delivery worktree HEAD changed after the final refresh")
        if pull_request.get("base", {}).get("sha") != lease.get("base_origin_master_sha"):
            raise TaskSessionError("Merged PR base does not match the refreshed delivery base")
        delivery_anchor = {
            "task_id": expected,
            "branch": lease.get("branch"),
            "base_sha": lease.get("base_origin_master_sha"),
            "head_sha": head_sha,
        }
        if lease.get("delivery_anchor") != delivery_anchor:
            raise TaskSessionError("Delivery anchor changed before production completion")
        actual = validate_task_pull_request(
            pull_request,
            commits,
            checks,
            expected_base_sha=str(lease["base_origin_master_sha"]),
            require_checks=True,
            dependency_ids=None,
        )
        if actual != expected or pull_request.get("merge_commit_sha") != merge_sha:
            raise TaskSessionError("Merged PR does not match the task lease and deployed SHA")
        validate_task_pull_request_files(
            files, expected_count=int(pull_request.get("changed_files", len(files)))
        )
        if not self._github().has_successful_deployment(deployed_sha, "production"):
            raise TaskSessionError(
                "Production deployment is not terminal-success for the exact SHA"
            )
        history_path = self.store.history / f"task-{expected}.json"
        prior_history = self.store.read_json(history_path)
        continuation_history = (
            prior_history
            if isinstance(prior_history, dict)
            and prior_history.get("state") == "continuation-in-progress"
            else None
        )
        if prior_history is not None and continuation_history is None:
            raise TaskSessionError(f"Production success history already exists for Task {expected}")
        history = {
            "version": TASK_STATE_VERSION,
            "task_id": expected,
            "state": "production-success",
            "head_sha": head_sha,
            "base_sha": lease.get("base_origin_master_sha"),
            "merge_sha": merge_sha,
            "deployed_sha": deployed_sha,
            "pr_number": pr_number,
            "completed_at": utc_now(),
        }
        if continuation_history is not None:
            previous = continuation_history.get("previous_production_success")
            if not isinstance(previous, dict):
                raise TaskSessionError("Task continuation history has no prior production evidence")
            history.update(
                {
                    "continuation_started_at": continuation_history.get("continuation_started_at"),
                    "continuation_reason": continuation_history.get("continuation_reason"),
                    "previous_production_success": previous,
                }
            )
        with self.store.lock():
            current = self.store.read_json(lease_path)
            latest_delivery = self.store.delivery_state()
            owner = latest_delivery.get("owner")
            if (
                not isinstance(current, dict)
                or not isinstance(owner, dict)
                or str(owner.get("task_id", "")).upper() != expected
            ):
                raise TaskSessionError("Delivery ownership changed before production completion")
            if self._lease_state(current) != "delivery-gate":
                raise TaskSessionError(
                    "Task is no longer in the validated final delivery-gate state"
                )
            if current.get("delivery_head_sha") != head_sha or current.get(
                "base_origin_master_sha"
            ) != lease.get("base_origin_master_sha"):
                raise TaskSessionError("Delivery lease changed before production completion")
            if current.get("delivery_anchor") != delivery_anchor:
                raise TaskSessionError("Delivery anchor changed before production completion")
            if "queue_budget" in current:
                history["queue_budget"] = current["queue_budget"]
            if "delivery_priority_override" in current:
                history["delivery_priority_override"] = current["delivery_priority_override"]
            if isinstance(current.get("preimplementation_resume"), Mapping):
                history["preimplementation_resume"] = current["preimplementation_resume"]
            latest_history = self.store.read_json(history_path)
            if latest_history != prior_history:
                raise TaskSessionError(
                    "Task production history changed before production completion"
                )
            now = utc_now()
            current["lifecycle_state"] = "production-success"
            current["merge_sha"] = merge_sha
            current["deployed_sha"] = deployed_sha
            current["updated_at"] = now
            StateStore.replace_json(lease_path, current)
            history["closeout_required"] = True
            StateStore.replace_json(history_path, history)
        return history

    def _verified_reconciliation_pr(
        self, pr_number: int, task_id: str, master_sha: str
    ) -> dict[str, Any]:
        github = self._github()
        pull_request = github.pull_request(pr_number)
        if pull_request.get("number") != pr_number or pull_request.get("state") != "closed":
            raise TaskSessionError(f"PR #{pr_number} is not a closed pull request")
        merged_at = pull_request.get("merged_at")
        if not isinstance(merged_at, str) or not merged_at:
            raise TaskSessionError(f"PR #{pr_number} was not merged")
        try:
            merged_time = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise TaskSessionError(f"PR #{pr_number} has an invalid merged_at timestamp") from error
        if merged_time.tzinfo is None:
            raise TaskSessionError(f"PR #{pr_number} merged_at timestamp has no timezone")

        base = pull_request.get("base")
        head = pull_request.get("head")
        if not isinstance(base, Mapping) or not isinstance(head, Mapping):
            raise TaskSessionError(f"PR #{pr_number} has incomplete base/head provenance")
        base_repo = base.get("repo")
        head_repo = head.get("repo")
        if not isinstance(base_repo, Mapping) or not isinstance(head_repo, Mapping):
            raise TaskSessionError(f"PR #{pr_number} has incomplete repository provenance")
        base_sha = str(base.get("sha", ""))
        head_sha = str(head.get("sha", ""))
        merge_sha = str(pull_request.get("merge_commit_sha", ""))
        if any(
            re.fullmatch(r"[0-9a-f]{40}", sha) is None for sha in (base_sha, head_sha, merge_sha)
        ):
            raise TaskSessionError(f"PR #{pr_number} has an invalid or missing Git SHA")
        if base_sha == merge_sha or not self.repository.is_ancestor(base_sha, merge_sha):
            raise TaskSessionError(
                f"PR #{pr_number} merge is not based on its recorded master base"
            )
        if not self.repository.is_ancestor(merge_sha, master_sha):
            raise TaskSessionError(f"PR #{pr_number} merge is not an ancestor of current master")

        actual_task_id = validate_task_pull_request(
            pull_request,
            github.pull_request_commits(pr_number),
            github.check_runs(head_sha),
            expected_base_sha=base_sha,
            require_checks=True,
            dependency_ids=None,
        )
        if actual_task_id != task_id:
            raise TaskSessionError(f"PR #{pr_number} does not belong to Task {task_id}")
        repo_slug = getattr(github, "repo_slug", None)
        if (
            not repo_slug
            or base_repo.get("full_name") != repo_slug
            or head_repo.get("full_name") != repo_slug
        ):
            raise TaskSessionError(f"PR #{pr_number} does not target this repository")
        files = github.pull_request_files(pr_number)
        changed_files = pull_request.get("changed_files")
        if type(changed_files) is not int or changed_files < 0:
            raise TaskSessionError(f"PR #{pr_number} has an invalid changed_files count")
        validate_task_pull_request_files(files, expected_count=changed_files)
        return {
            "pr_number": pr_number,
            "branch": str(head.get("ref", "")),
            "base_sha": base_sha,
            "head_sha": head_sha,
            "merge_sha": merge_sha,
            "merged_at": merged_time.astimezone(UTC).isoformat(),
            "required_check": {
                "name": "checks",
                "head_sha": head_sha,
                "status": "completed",
                "conclusion": "SUCCESS",
            },
        }

    def _verified_post_merge_anchor(
        self,
        task_id: str,
        lease: Mapping[str, Any],
        anchor: Mapping[str, Any],
        original: Mapping[str, Any],
        final_pr: Mapping[str, Any],
        deployed_sha: str,
    ) -> dict[str, Any] | None:
        branch = str(lease.get("branch", ""))
        canonical_refresh = lease.get("canonical_master_refresh")
        original_base_sha = str(lease.get("original_base_origin_master_sha", ""))
        provenance = {
            "task_id": task_id,
            "branch": branch,
            "base_sha": deployed_sha,
            "head_sha": deployed_sha,
            "original_base_sha": original_base_sha,
        }
        expected_anchor = {
            "task_id": task_id,
            "branch": branch,
            "base_sha": deployed_sha,
            "head_sha": deployed_sha,
        }
        if (
            not isinstance(canonical_refresh, Mapping)
            or not original_base_sha
            or original.get("branch") != branch
            or original.get("base_sha") != original_base_sha
            or final_pr.get("branch") != branch
            or final_pr.get("merge_sha") != deployed_sha
            or any(
                lease.get(key) != deployed_sha
                for key in (
                    "base_origin_master_sha",
                    "ready_base_origin_master_sha",
                    "ready_head_sha",
                    "delivery_base_origin_master_sha",
                    "delivery_head_sha",
                )
            )
            or lease.get("task_provenance") != provenance
            or dict(anchor) != expected_anchor
            or lease.get("delivery_anchor") != expected_anchor
            or any(
                canonical_refresh.get(key) != value
                for key, value in (
                    ("operation", "canonical-master-refresh"),
                    ("result", "REFRESHED"),
                    ("canonical_worktree", str(self._canonical_root())),
                    ("old_sha", final_pr.get("base_sha")),
                    ("new_sha", deployed_sha),
                    ("local_master_before", final_pr.get("base_sha")),
                    ("local_master_after", deployed_sha),
                    ("origin_master_sha", deployed_sha),
                    ("verified_remote_sha", deployed_sha),
                    ("live_master_sha", deployed_sha),
                    ("ahead_before", 0),
                    ("ahead_after", 0),
                    ("behind_after", 0),
                    ("mutation_performed", True),
                    ("mutated_ref", "refs/heads/master"),
                    ("reread_after_contention", False),
                    ("delivery_task_id", task_id),
                )
            )
        ):
            return None

        transition_ref = f"refs/heads/{branch}"
        transition_message = f"rebase (finish): {transition_ref} onto {deployed_sha}"
        try:
            reflog = self.repository.git(
                "reflog", "show", "--format=%H%x09%gs", branch
            ).splitlines()
        except TaskSessionError, OSError:
            return None
        if len(reflog) < 2:
            return None
        try:
            current_ref, current_message = reflog[0].split("\t", maxsplit=1)
            prior_ref = reflog[1].split("\t", maxsplit=1)[0]
        except ValueError:
            return None
        if (
            current_ref != deployed_sha
            or prior_ref != final_pr.get("head_sha")
            or current_message != transition_message
        ):
            return None

        behind_before = canonical_refresh.get("behind_before")
        updated_commits = canonical_refresh.get("updated_commits")
        refresh_counts = (
            canonical_refresh.get("ahead_before"),
            behind_before,
            canonical_refresh.get("ahead_after"),
            canonical_refresh.get("behind_after"),
            updated_commits,
        )
        try:
            refresh_ahead, refresh_behind = self.repository.ahead_behind(
                str(final_pr.get("base_sha", "")), deployed_sha
            )
        except TaskSessionError:
            return None
        if (
            type(behind_before) is not int
            or behind_before <= 0
            or any(type(value) is not int for value in refresh_counts)
            or updated_commits != behind_before
            or refresh_ahead != 0
            or refresh_behind != behind_before
            or not self.repository.is_ancestor(str(final_pr.get("base_sha", "")), deployed_sha)
        ):
            return None

        return {
            "classification": "post_merge_collapsed_anchor",
            "observed_recovery_anchor": dict(anchor),
            "collapsed_from_delivery_anchor": {
                "task_id": task_id,
                "branch": branch,
                "base_sha": final_pr["base_sha"],
                "head_sha": final_pr["head_sha"],
            },
            "task_branch_transition": {
                "ref": transition_ref,
                "operation": "rebase (finish)",
                "from_sha": final_pr["head_sha"],
                "to_sha": deployed_sha,
                "reflog_message": transition_message,
            },
            "controller_master_refresh": {
                "operation": canonical_refresh["operation"],
                "result": canonical_refresh["result"],
                "old_sha": canonical_refresh["old_sha"],
                "new_sha": canonical_refresh["new_sha"],
                "delivery_task_id": canonical_refresh["delivery_task_id"],
                "mutation_performed": canonical_refresh["mutation_performed"],
                "mutated_ref": canonical_refresh["mutated_ref"],
                "behind_before": behind_before,
                "updated_commits": updated_commits,
            },
        }

    def reconcile_ready_production_success(
        self,
        task_id: str,
        *,
        pr_number: int,
        deployed_sha: str,
        production_run_id: int,
        owner_authorize: bool,
    ) -> dict[str, Any]:
        """Reconcile a ready task whose exact merged revision is already deployed."""

        expected = normalize_task_id(task_id)
        if not owner_authorize:
            raise TaskSessionError(
                "Ready production reconciliation requires explicit owner authorization"
            )
        if type(pr_number) is not int or pr_number <= 0:
            raise TaskSessionError("Ready production reconciliation requires a positive PR number")
        if type(production_run_id) is not int or production_run_id <= 0:
            raise TaskSessionError(
                "Ready production reconciliation requires a positive production run ID"
            )
        if re.fullmatch(r"[0-9a-f]{40}", deployed_sha) is None:
            raise TaskSessionError("Ready production reconciliation deployed SHA is invalid")

        lease_path = self.store.task_lease_path(expected)
        history_path = self.store.history / f"task-{expected}.json"
        lease = self.store.read_json(lease_path)
        if not isinstance(lease, dict) or lease.get("task_id") != expected:
            raise TaskSessionError(f"Task {expected} has no valid ready-for-delivery lease")
        if lease.get("mode") != "write" or self._lease_state(lease) != "ready-for-delivery":
            raise TaskSessionError(
                f"Task {expected} ready production reconciliation requires a ready-for-delivery lease"
            )
        self._validated_lease_concurrency_class(lease)
        if lease.get("delivery_owner") not in {None, ""}:
            raise TaskSessionError(
                f"Task {expected} ready production reconciliation refuses an active delivery owner"
            )
        if self.store.read_json(history_path) is not None:
            raise TaskSessionError(f"Production history already exists for Task {expected}")
        delivery = self.store.delivery_state()
        if delivery.get("owner") is not None:
            raise TaskSessionError(
                f"Task {expected} ready production reconciliation refuses an active delivery owner"
            )
        if self.repository.status(
            self.repository.current_worktree
        ) or self.repository.operation_issues(self.repository.current_worktree):
            raise TaskSessionError(
                "Ready production reconciliation requires a clean controller worktree"
            )
        worker_states = self._preimplementation_worker_state_paths(expected)
        if worker_states:
            raise TaskSessionError(
                "Ready production reconciliation refuses unreconciled worker state"
            )

        branch = str(lease.get("branch", ""))
        ready_base_sha = str(lease.get("ready_base_origin_master_sha", ""))
        ready_head_sha = str(lease.get("ready_head_sha", ""))
        expected_provenance = {
            "task_id": expected,
            "branch": branch,
            "base_sha": ready_base_sha,
            "head_sha": ready_head_sha,
        }
        if (
            task_id_from_branch(branch) != expected
            or re.fullmatch(r"[0-9a-f]{40}", ready_base_sha) is None
            or re.fullmatch(r"[0-9a-f]{40}", ready_head_sha) is None
            or lease.get("base_origin_master_sha") != ready_base_sha
            or lease.get("task_provenance") != expected_provenance
        ):
            raise TaskSessionError(
                "ready production reconciliation requires exact ready base and head provenance"
            )
        try:
            if not self.repository.is_ancestor(ready_base_sha, ready_head_sha):
                raise TaskSessionError(
                    "ready production reconciliation ready head is not based on ready base"
                )
        except TaskSessionError as error:
            raise TaskSessionError(
                "ready production reconciliation could not verify ready base and head"
            ) from error

        leases = self.store.all_leases()
        task_leases = [item for item in leases if str(item.get("task_id", "")).upper() == expected]
        if len(task_leases) != 1:
            raise TaskSessionError(
                "Ready production reconciliation requires exactly one task lease"
            )
        worktree_path = Path(str(lease.get("worktree", ""))).resolve()
        root = self._canonical_root()
        expected_parent = (root / ".artifacts" / "worktrees").resolve()
        if worktree_path.parent != expected_parent:
            raise TaskSessionError(
                "Ready production reconciliation task worktree is outside the canonical worktree directory"
            )
        branches = [
            line.removeprefix("refs/heads/")
            for line in self.repository.git(
                "for-each-ref", "--format=%(refname)", f"refs/heads/task/{expected}-*"
            ).splitlines()
            if line
        ]
        matches = [
            item
            for item in self.repository.worktrees()
            if item.path == worktree_path
            or (item.branch and item.branch.startswith(f"task/{expected}-"))
        ]
        if branches != [branch] or len(matches) != 1 or matches[0].path != worktree_path:
            raise TaskSessionError(
                "Ready production reconciliation requires one unambiguous task branch/worktree"
            )
        if (
            not worktree_path.is_dir()
            or matches[0].branch != branch
            or matches[0].head != ready_head_sha
            or self.repository.ref(branch) != ready_head_sha
        ):
            raise TaskSessionError(
                "Ready production reconciliation requires the leased task branch and worktree at the ready head"
            )
        if self.repository.status(worktree_path) or self.repository.operation_issues(worktree_path):
            raise TaskSessionError(
                "Ready production reconciliation refuses a dirty or interrupted task worktree"
            )

        previous_master_sha = self.repository.ref("origin/master")
        try:
            self.repository.fetch_origin_master(cwd=self.repository.current_worktree, prune=False)
        except (TaskSessionError, OSError) as error:
            raise TaskSessionError(
                f"Cannot refresh origin/master for ready production reconciliation: {error}"
            ) from error
        master_sha = self.repository.ref("origin/master")
        if not self.repository.is_ancestor(previous_master_sha, master_sha):
            raise TaskSessionError(
                "origin/master changed non-fast-forward during ready production reconciliation"
            )
        if deployed_sha != master_sha:
            raise TaskSessionError(
                "Ready production reconciliation deployed SHA must equal current protected origin/master"
            )
        self._verify_live_master(master_sha)

        github = self._github()

        def successful_production_run() -> Mapping[str, Any]:
            try:
                run = github.api(f"actions/runs/{production_run_id}")
            except (KeyError, OSError, TaskSessionError) as error:
                raise TaskSessionError(
                    f"Production run {production_run_id} is unavailable for reconciliation"
                ) from error
            if (
                not isinstance(run, Mapping)
                or run.get("id") != production_run_id
                or run.get("name") != "Release production"
                or run.get("head_sha") != deployed_sha
                or run.get("status") != "completed"
                or str(run.get("conclusion", "")).lower() != "success"
            ):
                raise TaskSessionError(
                    "Production run is not successful for the exact deployed SHA"
                )
            return run

        def verified_pr() -> dict[str, Any]:
            try:
                pull_request = github.pull_request(pr_number)
            except (KeyError, OSError, TaskSessionError) as error:
                raise TaskSessionError(
                    f"PR #{pr_number} is unavailable for reconciliation"
                ) from error
            if not isinstance(pull_request, Mapping):
                raise TaskSessionError(f"PR #{pr_number} has invalid reconciliation data")
            base = pull_request.get("base")
            head = pull_request.get("head")
            if not isinstance(base, Mapping) or not isinstance(head, Mapping):
                raise TaskSessionError(f"PR #{pr_number} has incomplete base/head provenance")
            if base.get("sha") != ready_base_sha:
                raise TaskSessionError("PR base does not match ready base")
            if head.get("sha") != ready_head_sha:
                raise TaskSessionError("PR head does not match ready head")
            if head.get("ref") != branch:
                raise TaskSessionError("PR branch does not match leased task branch")
            evidence = self._verified_reconciliation_pr(pr_number, expected, master_sha)
            if evidence["branch"] != branch:
                raise TaskSessionError("PR branch does not match leased task branch")
            if evidence["base_sha"] != ready_base_sha or evidence["head_sha"] != ready_head_sha:
                raise TaskSessionError("PR provenance does not match ready base and head")
            if evidence["merge_sha"] != deployed_sha:
                raise TaskSessionError("PR merge SHA does not match deployed SHA")
            return evidence

        pull_request_evidence = verified_pr()
        if self._active_production_deployment():
            raise TaskSessionError(
                "Ready production reconciliation refuses while a production deployment is active"
            )
        run = successful_production_run()
        if not github.has_successful_deployment(deployed_sha, "production"):
            raise TaskSessionError(
                "No successful production deployment exists for the exact deployed SHA"
            )

        now = utc_now()
        reconciliation = {
            "version": 1,
            "owner_authorized": True,
            "authorization": "explicit --owner-authorize",
            "authorized_at": now,
            "reconciled_at": now,
            "original_state": "ready-for-delivery",
            "branch": branch,
            "ready_base_origin_master_sha": ready_base_sha,
            "ready_head_sha": ready_head_sha,
            "reconciled_against_master_sha": master_sha,
            "pull_request": pull_request_evidence,
            "production": {
                "run_id": production_run_id,
                "run_url": run.get("html_url"),
                "run_conclusion": "success",
                "environment": "production",
                "deployed_sha": deployed_sha,
                "deployment_success_verified": True,
            },
        }
        history = {
            "version": TASK_STATE_VERSION,
            "task_id": expected,
            "state": "production-success",
            "head_sha": ready_head_sha,
            "base_sha": ready_base_sha,
            "merge_sha": deployed_sha,
            "deployed_sha": deployed_sha,
            "pr_number": pr_number,
            "completed_at": now,
            "closeout_required": True,
            "ready_production_reconciliation": reconciliation,
        }
        if "queue_budget" in lease:
            history["queue_budget"] = lease["queue_budget"]
        if "delivery_priority_override" in lease:
            history["delivery_priority_override"] = lease["delivery_priority_override"]
        if isinstance(lease.get("preimplementation_resume"), Mapping):
            history["preimplementation_resume"] = lease["preimplementation_resume"]

        with self.store.lock():
            current = self.store.read_json(lease_path)
            latest_delivery = self.store.delivery_state()
            if current != lease:
                raise TaskSessionError(
                    "Task ready-for-delivery lease changed during production reconciliation"
                )
            if latest_delivery.get("owner") is not None:
                raise TaskSessionError(
                    "Delivery ownership changed during ready production reconciliation"
                )
            if self.store.read_json(history_path) is not None:
                raise TaskSessionError(
                    f"Production history appeared for Task {expected} during reconciliation"
                )
            if self.repository.ref("origin/master") != master_sha:
                raise TaskSessionError(
                    "origin/master changed during ready production reconciliation"
                )
            if (
                self.repository.ref(branch) != ready_head_sha
                or self.repository.head(cwd=worktree_path) != ready_head_sha
                or self.repository.status(worktree_path)
                or self.repository.operation_issues(worktree_path)
            ):
                raise TaskSessionError("Task branch or worktree changed during reconciliation")
            if self._preimplementation_worker_state_paths(expected):
                raise TaskSessionError(
                    "Worker state appeared during ready production reconciliation"
                )
            self._verify_live_master(master_sha)
            if self._active_production_deployment():
                raise TaskSessionError("A production deployment started during reconciliation")
            if verified_pr() != pull_request_evidence:
                raise TaskSessionError("PR evidence changed during ready production reconciliation")
            latest_run = successful_production_run()
            if latest_run != run or not github.has_successful_deployment(
                deployed_sha, "production"
            ):
                raise TaskSessionError(
                    "Production deployment evidence changed during reconciliation"
                )
            current["lifecycle_state"] = "production-success"
            current["merge_sha"] = deployed_sha
            current["deployed_sha"] = deployed_sha
            current["ready_production_reconciliation"] = reconciliation
            current["updated_at"] = utc_now()
            StateStore.replace_json(lease_path, current)
            StateStore.replace_json(history_path, history)
        return history

    def reconcile_production_success(
        self,
        task_id: str,
        *,
        original_pr_number: int,
        superseding_pr_numbers: Sequence[int],
        deployed_sha: str,
        production_run_id: int,
        owner_authorize: bool,
    ) -> dict[str, Any]:
        expected = normalize_task_id(task_id)
        if not owner_authorize:
            raise TaskSessionError(
                "Production reconciliation requires explicit owner authorization"
            )
        if not superseding_pr_numbers or any(number <= 0 for number in superseding_pr_numbers):
            raise TaskSessionError("Production reconciliation requires one or more superseding PRs")
        pr_numbers = [original_pr_number, *superseding_pr_numbers]
        if original_pr_number <= 0 or len(set(pr_numbers)) != len(pr_numbers):
            raise TaskSessionError(
                "Production reconciliation PR numbers must be positive and unique"
            )
        if production_run_id <= 0:
            raise TaskSessionError(
                "Production reconciliation requires a positive production run ID"
            )
        if re.fullmatch(r"[0-9a-f]{40}", deployed_sha) is None:
            raise TaskSessionError("Production reconciliation deployed SHA is invalid")

        lease_path = self.store.task_lease_path(expected)
        lease = self.store.read_json(lease_path)
        if not isinstance(lease, dict) or lease.get("task_id") != expected:
            raise TaskSessionError(f"Task {expected} has no valid recovery lease")
        if self._lease_state(lease) != "recovery-required":
            raise TaskSessionError(
                "Production reconciliation only accepts a recovery-required lease"
            )
        if self.store.read_json(self.store.history / f"task-{expected}.json") is not None:
            raise TaskSessionError(f"Production history already exists for Task {expected}")
        delivery = self.store.delivery_state()
        if delivery.get("owner") is not None:
            raise TaskSessionError("Production reconciliation refuses an active delivery owner")
        if self.repository.status(
            self.repository.current_worktree
        ) or self.repository.operation_issues(self.repository.current_worktree):
            raise TaskSessionError("Production reconciliation requires a clean controller worktree")

        branch = str(lease.get("branch", ""))
        base_sha = str(lease.get("base_origin_master_sha", ""))
        head_sha = str(lease.get("ready_head_sha", ""))
        anchor = {
            "task_id": expected,
            "branch": branch,
            "base_sha": base_sha,
            "head_sha": head_sha,
        }
        if (
            task_id_from_branch(branch) != expected
            or not head_sha
            or any(
                lease.get(key) != value
                for key, value in (
                    ("delivery_head_sha", head_sha),
                    ("delivery_base_origin_master_sha", base_sha),
                    ("ready_base_origin_master_sha", base_sha),
                    ("delivery_anchor", anchor),
                    (
                        "task_provenance",
                        {
                            "task_id": expected,
                            "branch": branch,
                            "base_sha": base_sha,
                            "head_sha": head_sha,
                            "original_base_sha": lease.get("original_base_origin_master_sha"),
                        },
                    ),
                )
            )
        ):
            raise TaskSessionError("Recovery lease does not preserve one exact delivery anchor")

        root = self._canonical_root()
        worktree_path = Path(str(lease.get("worktree", ""))).resolve()
        if worktree_path.parent != (root / ".artifacts" / "worktrees").resolve():
            raise TaskSessionError(
                "Production reconciliation task worktree is outside the canonical worktree directory"
            )
        branches = [
            line.removeprefix("refs/heads/")
            for line in self.repository.git(
                "for-each-ref", "--format=%(refname)", f"refs/heads/task/{expected}-*"
            ).splitlines()
            if line
        ]
        matches = [
            item
            for item in self.repository.worktrees()
            if item.path == worktree_path
            or (item.branch and item.branch.startswith(f"task/{expected}-"))
        ]
        if branches != [branch] or len(matches) != 1 or matches[0].path != worktree_path:
            raise TaskSessionError(
                "Production reconciliation requires one unambiguous task branch/worktree"
            )
        if (
            not worktree_path.is_dir()
            or matches[0].branch != branch
            or matches[0].head != head_sha
            or self.repository.ref(branch) != head_sha
        ):
            raise TaskSessionError(
                "Production reconciliation task worktree no longer matches its delivery anchor"
            )
        if self.repository.status(worktree_path) or self.repository.operation_issues(worktree_path):
            raise TaskSessionError(
                "Production reconciliation refuses a dirty or interrupted task worktree"
            )
        if self.repository.unique_commits(branch):
            raise TaskSessionError("Production reconciliation refuses unmerged unique task commits")

        previous_master_sha = self.repository.ref("origin/master")
        try:
            self.repository.fetch_origin_master(cwd=self.repository.current_worktree, prune=False)
        except (TaskSessionError, OSError) as error:
            raise TaskSessionError(
                f"Cannot refresh origin/master for reconciliation: {error}"
            ) from error
        master_sha = self.repository.ref("origin/master")
        if not self.repository.is_ancestor(previous_master_sha, master_sha):
            raise TaskSessionError("origin/master changed non-fast-forward during reconciliation")
        self._verify_live_master(master_sha)
        original = self._verified_reconciliation_pr(original_pr_number, expected, master_sha)
        evidence = [original]
        previous = original
        for number in superseding_pr_numbers:
            current = self._verified_reconciliation_pr(number, expected, master_sha)
            if not self.repository.is_ancestor(previous["merge_sha"], current["base_sha"]):
                raise TaskSessionError(
                    f"PR #{number} breaks the chronological master ancestry chain"
                )
            if current["merged_at"] <= previous["merged_at"]:
                raise TaskSessionError(f"PR #{number} is not later than its predecessor")
            evidence.append(current)
            previous = current
        if deployed_sha != previous["merge_sha"]:
            raise TaskSessionError("Deployed SHA must equal the final superseding PR merge SHA")
        if not self.repository.is_ancestor(deployed_sha, master_sha):
            raise TaskSessionError("Deployed SHA is not an ancestor of current protected master")

        exact_anchor = (
            (
                original["branch"] == branch
                or TASK_INTEGRATION_BRANCHES.get(original["branch"]) == expected
            )
            and original["base_sha"] == base_sha
            and original["head_sha"] == head_sha
        )
        collapsed_anchor = None
        if not exact_anchor:
            collapsed_anchor = self._verified_post_merge_anchor(
                expected, lease, anchor, original, evidence[-1], deployed_sha
            )
            if collapsed_anchor is None:
                raise TaskSessionError(
                    "Original PR does not match the preserved delivery anchor and no verified post-merge anchor exists"
                )
        if self._active_production_deployment():
            raise TaskSessionError(
                "Production reconciliation refuses while a production deployment is active"
            )

        github = self._github()
        run = github.api(f"actions/runs/{production_run_id}")
        if (
            not isinstance(run, Mapping)
            or run.get("id") != production_run_id
            or run.get("name") != "Release production"
            or run.get("head_sha") != deployed_sha
            or run.get("status") != "completed"
            or str(run.get("conclusion", "")).lower() != "success"
        ):
            raise TaskSessionError("Production run is not successful for the exact deployed SHA")
        if not github.has_successful_deployment(deployed_sha, "production"):
            raise TaskSessionError(
                "No successful production deployment exists for the exact deployed SHA"
            )

        now = utc_now()
        reconciliation = {
            "version": 1,
            "anchor_classification": (
                "post_merge_collapsed_anchor"
                if collapsed_anchor is not None
                else "exact_delivery_anchor"
            ),
            "owner_authorized": True,
            "authorized_at": now,
            "reconciled_at": now,
            "reconciled_against_master_sha": master_sha,
            "original_delivery": {
                "pr_number": original_pr_number,
                "branch": original["branch"],
                "base_sha": original["base_sha"],
                "head_sha": original["head_sha"],
                "merge_sha": original["merge_sha"],
                "merged_at": original["merged_at"],
                "required_check": original["required_check"],
            },
            "superseding_prs": evidence[1:],
            "production": {
                "run_id": production_run_id,
                "run_url": run.get("html_url"),
                "run_conclusion": "success",
                "environment": "production",
                "deployed_sha": deployed_sha,
                "deployment_success_verified": True,
            },
        }
        if collapsed_anchor is not None:
            reconciliation["post_merge_collapsed_anchor"] = collapsed_anchor
        history = {
            "version": TASK_STATE_VERSION,
            "task_id": expected,
            "state": "production-success",
            "head_sha": original["head_sha"],
            "base_sha": original["base_sha"],
            "merge_sha": deployed_sha,
            "deployed_sha": deployed_sha,
            "pr_number": original_pr_number,
            "completed_at": now,
            "closeout_required": True,
            "superseding_production_reconciliation": reconciliation,
        }
        if "queue_budget" in lease:
            history["queue_budget"] = lease["queue_budget"]
        if "delivery_priority_override" in lease:
            history["delivery_priority_override"] = lease["delivery_priority_override"]

        with self.store.lock():
            current = self.store.read_json(lease_path)
            latest_delivery = self.store.delivery_state()
            if current != lease:
                raise TaskSessionError(
                    "Task recovery lease changed during production reconciliation"
                )
            if latest_delivery.get("owner") is not None:
                raise TaskSessionError(
                    "Delivery ownership changed during production reconciliation"
                )
            if self.store.read_json(self.store.history / f"task-{expected}.json") is not None:
                raise TaskSessionError(
                    f"Production history appeared for Task {expected} during reconciliation"
                )
            if self.repository.ref("origin/master") != master_sha:
                raise TaskSessionError("origin/master changed during production reconciliation")
            if (
                self.repository.ref(branch) != head_sha
                or self.repository.head(cwd=worktree_path) != head_sha
                or self.repository.status(worktree_path)
                or self.repository.operation_issues(worktree_path)
            ):
                raise TaskSessionError("Task worktree changed during production reconciliation")
            self._verify_live_master(master_sha)
            if self._active_production_deployment():
                raise TaskSessionError("A production deployment started during reconciliation")
            for item in evidence:
                if not _successful_exact_check(
                    github.check_runs(item["head_sha"]), "checks", item["head_sha"]
                ):
                    raise TaskSessionError(
                        f"Exact-head required check changed during reconciliation for PR #{item['pr_number']}"
                    )
            latest_run = github.api(f"actions/runs/{production_run_id}")
            if (
                not isinstance(latest_run, Mapping)
                or latest_run.get("id") != production_run_id
                or latest_run.get("name") != "Release production"
                or latest_run.get("head_sha") != deployed_sha
                or latest_run.get("status") != "completed"
                or str(latest_run.get("conclusion", "")).lower() != "success"
                or not github.has_successful_deployment(deployed_sha, "production")
            ):
                raise TaskSessionError(
                    "Production deployment evidence changed during reconciliation"
                )
            current["lifecycle_state"] = "production-success"
            current["merge_sha"] = deployed_sha
            current["deployed_sha"] = deployed_sha
            current["superseding_production_reconciliation"] = reconciliation
            current["updated_at"] = utc_now()
            StateStore.replace_json(lease_path, current)
            StateStore.replace_json(self.store.history / f"task-{expected}.json", history)
        return history

    def _successful_release_evidence(self, sha: str) -> dict[str, Any] | None:
        github = self._github()
        runs = github.workflow_runs("deploy.yml", sha)
        successful = [
            item
            for item in runs
            if item.get("name") == "Release production"
            and item.get("head_sha") == sha
            and item.get("status") == "completed"
            and str(item.get("conclusion", "")).lower() == "success"
            and type(item.get("id")) is int
            and item.get("id", 0) > 0
        ]
        if not successful or not github.has_successful_deployment(sha, "production"):
            return None
        run = min(successful, key=lambda item: item["id"])
        return {
            "run_id": run["id"],
            "run_url": run.get("html_url"),
            "head_sha": sha,
            "run_conclusion": "success",
            "environment": "production",
            "deployment_success_verified": True,
        }

    def _verified_subsequent_production_chain(
        self, original_sha: str, master_sha: str
    ) -> dict[str, Any]:
        github = self._github()
        if not self.repository.is_ancestor(original_sha, master_sha):
            raise TaskSessionError("Current master does not descend from the original deployed SHA")
        if self._active_production_deployment():
            raise TaskSessionError(
                "Subsequent production reconciliation refuses an active deployment"
            )

        master_commits = self.repository.git(
            "rev-list", "--first-parent", "--reverse", f"{original_sha}..{master_sha}"
        ).splitlines()
        if not master_commits:
            raise TaskSessionError("Subsequent production reconciliation requires later commits")

        chain: list[dict[str, Any]] = []
        classified_nested_commits: set[str] = set()
        previous_sha = original_sha
        previous_merged_at: datetime | None = None
        for commit_sha in master_commits:
            details = self.repository.git("show", "-s", "--format=%P%n%s", commit_sha)
            lines = details.splitlines()
            parents = lines[0].split() if lines else []
            subject = lines[1] if len(lines) > 1 else ""
            if not parents or parents[0] != previous_sha:
                raise TaskSessionError(
                    f"Intervening commit {commit_sha} breaks first-parent master ancestry"
                )
            associated = github.pull_requests_for_commit(commit_sha)
            matching = [
                item
                for item in associated
                if item.get("merge_commit_sha") == commit_sha
                and type(item.get("number")) is int
                and item.get("number", 0) > 0
            ]
            if len(matching) != 1:
                raise TaskSessionError(
                    f"Intervening commit {commit_sha} has no unique merged pull request"
                )
            pr_number = matching[0]["number"]
            pull_request = github.pull_request(pr_number)
            merged_at = pull_request.get("merged_at")
            try:
                merged_time = datetime.fromisoformat(str(merged_at).replace("Z", "+00:00"))
            except ValueError as error:
                raise TaskSessionError(
                    f"PR #{pr_number} has an invalid merged_at timestamp"
                ) from error
            if merged_time.tzinfo is None or (
                previous_merged_at is not None and merged_time <= previous_merged_at
            ):
                raise TaskSessionError(f"PR #{pr_number} is not chronologically ordered")

            base = pull_request.get("base")
            head = pull_request.get("head")
            repo_slug = getattr(github, "repo_slug", None)
            if not isinstance(base, Mapping) or not isinstance(head, Mapping):
                raise TaskSessionError(f"PR #{pr_number} has incomplete base/head provenance")
            base_repo = base.get("repo")
            head_repo = head.get("repo")
            if (
                pull_request.get("number") != pr_number
                or pull_request.get("state") != "closed"
                or not isinstance(merged_at, str)
                or not merged_at
                or pull_request.get("merge_commit_sha") != commit_sha
                or base.get("ref") != TARGET_BASE_BRANCH
                or not isinstance(base_repo, Mapping)
                or not isinstance(head_repo, Mapping)
                or not repo_slug
                or base_repo.get("full_name") != repo_slug
                or head_repo.get("full_name") != repo_slug
            ):
                raise TaskSessionError(f"PR #{pr_number} is not a merged same-repository master PR")
            branch = str(head.get("ref", ""))
            head_sha = str(head.get("sha", ""))
            if re.fullmatch(r"[0-9a-f]{40}", head_sha) is None:
                raise TaskSessionError(f"PR #{pr_number} has an invalid head SHA")

            pr_commits = github.pull_request_commits(pr_number)
            declared_commit_count = pull_request.get("commits")
            if (
                type(declared_commit_count) is not int
                or declared_commit_count != len(pr_commits)
                or not pr_commits
            ):
                raise TaskSessionError(f"PR #{pr_number} commit inventory is incomplete")
            pr_commit_shas = {
                str(item.get("sha", ""))
                for item in pr_commits
                if re.fullmatch(r"[0-9a-f]{40}", str(item.get("sha", "")))
            }
            if len(pr_commit_shas) != len(pr_commits):
                raise TaskSessionError(f"PR #{pr_number} has invalid commit provenance")
            if head_sha not in pr_commit_shas:
                raise TaskSessionError(f"PR #{pr_number} head is absent from its commit inventory")
            introduced = set(
                self.repository.git("rev-list", f"{previous_sha}..{commit_sha}").splitlines()
            ) - {commit_sha}
            if not introduced.issubset(pr_commit_shas) or introduced & classified_nested_commits:
                raise TaskSessionError(
                    f"PR #{pr_number} does not account for every commit introduced by its merge"
                )
            classified_nested_commits.update(introduced)

            title = str(pull_request.get("title", ""))
            messages = [str(item.get("commit", {}).get("message", "")) for item in pr_commits]
            files = github.pull_request_files(pr_number)
            changed_files = pull_request.get("changed_files")
            if type(changed_files) is not int or changed_files < 0:
                raise TaskSessionError(f"PR #{pr_number} has an invalid changed_files count")
            changed_paths = sorted(
                path
                for path in self.repository.git(
                    "diff", "--name-only", f"{previous_sha}..{commit_sha}"
                ).splitlines()
                if path
            )
            check = _verified_required_check(github.check_runs(head_sha), head_sha)
            merge_subject = re.match(
                r"^Merge pull request #(?P<pr_number>\d+) from \S+$",
                subject,
            )
            standard_merge_pr = (
                merge_subject is not None
                and int(merge_subject.group("pr_number")) == pr_number
                and len(parents) >= 2
            )
            controller_match = CONTROLLER_COMMIT_RE.match(subject)
            controller_from_merge = standard_merge_pr and title.startswith("[Controller]")
            if controller_match or controller_from_merge:
                if (
                    CONTROLLER_BRANCH_RE.fullmatch(branch) is None
                    or not title.startswith("[Controller]")
                    or any(CONTROLLER_COMMIT_RE.match(message) is None for message in messages)
                ):
                    raise TaskSessionError(
                        f"Controller commit {commit_sha} has invalid controller PR provenance"
                    )
                validate_controller_pull_request_files(files, expected_count=changed_files)
                disallowed = sorted(set(changed_paths) - CONTROLLER_ALLOWED_PATHS)
                if disallowed:
                    raise TaskSessionError(
                        f"Controller commit {commit_sha} changes disallowed paths: "
                        + ", ".join(disallowed)
                    )
                release_runs = [
                    item
                    for item in github.workflow_runs("deploy.yml", commit_sha)
                    if item.get("name") == "Release production"
                    and item.get("head_sha") == commit_sha
                    and item.get("status") == "completed"
                    and str(item.get("conclusion", "")).lower() == "success"
                    and type(item.get("id")) is int
                ]
                controller_release: dict[str, Any] | None = None
                for run in sorted(release_runs, key=lambda item: item["id"]):
                    jobs = github.workflow_jobs(run["id"])
                    authorize = [
                        job
                        for job in jobs
                        if job.get("name") == "Authorize exact merged master revision"
                    ]
                    deploy = [
                        job for job in jobs if job.get("name") == "Deploy immutable tested bundle"
                    ]
                    if (
                        len(authorize) == 1
                        and authorize[0].get("conclusion") == "success"
                        and len(deploy) == 1
                        and deploy[0].get("conclusion") == "skipped"
                    ):
                        controller_release = {
                            "run_id": run["id"],
                            "run_url": run.get("html_url"),
                            "run_conclusion": "success",
                            "authorization_job": "success",
                            "application_deploy_job": "skipped",
                            "application_deployment_verified": False,
                        }
                        break
                if controller_release is None:
                    raise TaskSessionError(
                        f"Controller PR #{pr_number} lacks proof that application deployment was skipped"
                    )
                if github.has_successful_deployment(commit_sha, "production"):
                    raise TaskSessionError(
                        f"Controller commit {commit_sha} unexpectedly has a production deployment"
                    )
                record = {
                    "commit_sha": commit_sha,
                    "parent_sha": previous_sha,
                    "subject": subject,
                    "classification": "controller",
                    "pr_number": pr_number,
                    "pr_title": title,
                    "branch": branch,
                    "head_sha": head_sha,
                    "merged_at": merged_time.astimezone(UTC).isoformat(),
                    "required_check": check,
                    "changed_paths": changed_paths,
                    "release": controller_release,
                }
            else:
                task_match = re.match(
                    rf"^\[Task (?P<task_id>{TASK_ID_PATTERN})\]", subject, re.IGNORECASE
                )
                if task_match is not None:
                    task_id = normalize_task_id(task_match.group("task_id"))
                else:
                    title_task_match = re.match(
                        rf"^\[Task (?P<task_id>{TASK_ID_PATTERN})\]",
                        title,
                        re.IGNORECASE,
                    )
                    if not standard_merge_pr or title_task_match is None:
                        raise TaskSessionError(f"Intervening commit {commit_sha} is unclassified")
                    task_id = normalize_task_id(title_task_match.group("task_id"))
                try:
                    branch_task_id = task_pr_task_id_from_branch(branch)
                except TaskSessionError as error:
                    raise TaskSessionError(
                        f"Product PR #{pr_number} has an invalid task branch"
                    ) from error
                if branch_task_id != task_id or not title.startswith(f"[Task {task_id}]"):
                    raise TaskSessionError(
                        f"Product commit {commit_sha} does not map to its PR task ID"
                    )
                validate_task_commit_messages(task_id, messages, dependency_ids=None)
                validate_task_pull_request_files(files, expected_count=changed_files)
                record = {
                    "commit_sha": commit_sha,
                    "parent_sha": previous_sha,
                    "subject": subject,
                    "classification": "product",
                    "task_id": task_id,
                    "pr_number": pr_number,
                    "pr_title": title,
                    "branch": branch,
                    "head_sha": head_sha,
                    "merged_at": merged_time.astimezone(UTC).isoformat(),
                    "required_check": check,
                    "changed_paths": changed_paths,
                    "release": None,
                }
            chain.append(record)
            previous_sha = commit_sha
            previous_merged_at = merged_time

        every_commit = set(
            self.repository.git("rev-list", f"{original_sha}..{master_sha}").splitlines()
        )
        if every_commit - set(master_commits) - classified_nested_commits:
            raise TaskSessionError("Intervening master history contains an unclassified commit")

        deployment = github.latest_deployment_status("production")
        if (
            not isinstance(deployment, Mapping)
            or deployment.get("environment") != "production"
            or deployment.get("state") in {"queued", "pending", "in_progress"}
            or deployment.get("state") != "success"
        ):
            raise TaskSessionError("Current production deployment is not verified successful")
        production_sha = str(deployment.get("sha", ""))
        if (
            re.fullmatch(r"[0-9a-f]{40}", production_sha) is None
            or not self.repository.is_ancestor(original_sha, production_sha)
            or not self.repository.is_ancestor(production_sha, master_sha)
            or production_sha not in {original_sha, *master_commits}
        ):
            raise TaskSessionError(
                "Current production SHA is not on the verified protected-master chain"
            )
        production_index = (
            master_commits.index(production_sha) if production_sha in master_commits else -1
        )
        if any(item["classification"] != "controller" for item in chain[production_index + 1 :]):
            raise TaskSessionError(
                "Current master contains product commits after the latest production deployment"
            )

        release_cache: dict[str, dict[str, Any] | None] = {}

        def release_for(sha: str) -> dict[str, Any] | None:
            if sha not in release_cache:
                release_cache[sha] = self._successful_release_evidence(sha)
            return release_cache[sha]

        original_production = release_for(original_sha)
        current_production_run = release_for(production_sha)
        if original_production is None:
            raise TaskSessionError("Original deployed SHA has no successful production evidence")
        if current_production_run is None:
            raise TaskSessionError(
                "Current production SHA has no successful exact-SHA release and deployment evidence"
            )
        for index, item in enumerate(chain):
            if item["classification"] != "product":
                continue
            deployed = release_for(item["commit_sha"])
            if deployed is not None:
                item["release"] = {
                    "result": "deployed",
                    "deployed_sha": item["commit_sha"],
                    **deployed,
                }
                continue
            later = next(
                (
                    candidate
                    for candidate in chain[index + 1 : production_index + 1]
                    if self.repository.is_ancestor(item["commit_sha"], candidate["commit_sha"])
                    and release_for(candidate["commit_sha"]) is not None
                ),
                None,
            )
            if later is None and self.repository.is_ancestor(item["commit_sha"], production_sha):
                later_sha = production_sha
                later_evidence = current_production_run
            elif later is not None:
                later_sha = later["commit_sha"]
                later_evidence = release_for(later_sha)
            else:
                raise TaskSessionError(
                    f"Product PR #{item['pr_number']} lacks successful or superseding production evidence"
                )
            item["release"] = {
                "result": "superseded",
                "superseded_by_sha": later_sha,
                **(later_evidence or {}),
            }

        return {
            "intervening_commits": chain,
            "original_production": {
                "deployed_sha": original_sha,
                **original_production,
            },
            "current_production": {
                "deployed_sha": production_sha,
                "deployment_id": deployment.get("deployment_id"),
                "deployment_state": "success",
                "deployment_updated_at": deployment.get("updated_at"),
                "deployment_log_url": deployment.get("log_url"),
                **(current_production_run or {}),
            },
            "current_master_sha": master_sha,
        }

    def reconcile_subsequent_production(
        self, task_id: str, *, owner_authorize: bool
    ) -> dict[str, Any]:
        expected = normalize_task_id(task_id)
        if not owner_authorize:
            raise TaskSessionError(
                "Subsequent production reconciliation requires explicit owner authorization"
            )
        lease_path = self.store.task_lease_path(expected)
        history_path = self.store.history / f"task-{expected}.json"
        lease = self.store.read_json(lease_path)
        history = self.store.read_json(history_path)
        if not isinstance(lease, dict) or not isinstance(history, dict):
            raise TaskSessionError(
                "Subsequent production reconciliation requires task lease and production history"
            )
        original_sha = str(history.get("deployed_sha", ""))
        if (
            lease.get("task_id") != expected
            or history.get("task_id") != expected
            or lease.get("lifecycle_state") != "production-success"
            or history.get("state") != "production-success"
            or lease.get("deployed_sha") != original_sha
            or lease.get("merge_sha") != history.get("merge_sha")
            or history.get("merge_sha") != original_sha
            or lease.get("ready_head_sha") != history.get("head_sha")
            or re.fullmatch(r"[0-9a-f]{40}", original_sha) is None
            or re.fullmatch(r"[0-9a-f]{40}", str(history.get("head_sha", ""))) is None
            or history.get("subsequent_production_reconciliation") is not None
            or lease.get("subsequent_production_reconciliation") is not None
        ):
            raise TaskSessionError(
                "Subsequent production reconciliation requires an unchanged production-success anchor"
            )
        if history.get("deployed_sha") != lease.get("deployed_sha"):
            raise TaskSessionError("Original production SHA differs between task lease and history")

        def verify_task_anchor(current_lease: Mapping[str, Any]) -> Path:
            branch = str(current_lease.get("branch", ""))
            worktree_path = Path(str(current_lease.get("worktree", ""))).resolve()
            root = self._canonical_root()
            if task_id_from_branch(branch) != expected:
                raise TaskSessionError("Task lease branch does not match its task ID")
            if worktree_path.parent != (root / ".artifacts" / "worktrees").resolve():
                raise TaskSessionError(
                    "Task worktree is outside the canonical task worktree directory"
                )
            branches = [
                line.removeprefix("refs/heads/")
                for line in self.repository.git(
                    "for-each-ref", "--format=%(refname)", f"refs/heads/task/{expected}-*"
                ).splitlines()
                if line
            ]
            matches = [
                item
                for item in self.repository.worktrees()
                if item.path == worktree_path
                or (item.branch and item.branch.startswith(f"task/{expected}-"))
            ]
            head_sha = str(current_lease.get("ready_head_sha", ""))
            if (
                branches != [branch]
                or len(matches) != 1
                or matches[0].branch != branch
                or matches[0].path != worktree_path
                or matches[0].head != head_sha
                or not worktree_path.is_dir()
                or self.repository.ref(branch) != head_sha
                or current_lease.get("head_sha", head_sha) != head_sha
                or self.repository.status(worktree_path)
                or self.repository.operation_issues(worktree_path)
            ):
                raise TaskSessionError(
                    "Subsequent production reconciliation requires an unchanged clean task worktree"
                )
            if self.repository.unique_commits(branch):
                raise TaskSessionError(
                    "Subsequent production reconciliation refuses unique task commits"
                )
            if self.repository.operation_issues(root):
                raise TaskSessionError(
                    "Subsequent production reconciliation found an interrupted Git operation"
                )
            return worktree_path

        if self.repository.current_worktree != self._canonical_root():
            raise TaskSessionError(
                "Subsequent production reconciliation must run from the canonical repository worktree"
            )
        if self.repository.current_branch() != TARGET_BASE_BRANCH:
            raise TaskSessionError(
                "Subsequent production reconciliation requires canonical local master"
            )
        if self.repository.status(
            self.repository.current_worktree
        ) or self.repository.operation_issues(self.repository.current_worktree):
            raise TaskSessionError(
                "Subsequent production reconciliation requires a clean canonical worktree"
            )
        verify_task_anchor(lease)
        if self.store.delivery_state().get("owner") is not None:
            raise TaskSessionError(
                "Subsequent production reconciliation refuses an active delivery owner"
            )

        try:
            self.repository.fetch_origin_master(cwd=self.repository.current_worktree, prune=False)
        except (TaskSessionError, OSError) as error:
            raise TaskSessionError(
                f"Cannot refresh origin/master for subsequent production reconciliation: {error}"
            ) from error
        master_sha = self.repository.ref("origin/master")
        self._verify_live_master(master_sha)
        evidence = self._verified_subsequent_production_chain(original_sha, master_sha)
        now = utc_now()
        reconciliation = {
            "version": 1,
            "owner_authorized": True,
            "authorization": "explicit --owner-authorize",
            "authorized_at": now,
            "reconciled_at": now,
            "original_deployed_sha": original_sha,
            **evidence,
        }

        with self.store.lock():
            current_lease = self.store.read_json(lease_path)
            current_history = self.store.read_json(history_path)
            if current_lease != lease or current_history != history:
                raise TaskSessionError(
                    "Task lease or production history changed during reconciliation"
                )
            if self.store.delivery_state().get("owner") is not None:
                raise TaskSessionError("Delivery ownership changed during reconciliation")
            if self.repository.status(
                self.repository.current_worktree
            ) or self.repository.operation_issues(self.repository.current_worktree):
                raise TaskSessionError("Canonical worktree changed during reconciliation")
            verify_task_anchor(current_lease)
            self.repository.fetch_origin_master(cwd=self.repository.current_worktree, prune=False)
            if self.repository.ref("origin/master") != master_sha:
                raise TaskSessionError("Protected master changed during reconciliation")
            self._verify_live_master(master_sha)
            refreshed_evidence = self._verified_subsequent_production_chain(
                original_sha, master_sha
            )
            if refreshed_evidence != evidence:
                raise TaskSessionError("Production or PR evidence changed during reconciliation")

            current_lease["subsequent_production_reconciliation"] = reconciliation
            current_lease["updated_at"] = utc_now()
            current_history["subsequent_production_reconciliation"] = reconciliation
            StateStore.replace_json(lease_path, current_lease)
            StateStore.replace_json(history_path, current_history)
        return reconciliation

    def recover(self, task_id: str) -> dict[str, Any]:
        expected = normalize_task_id(task_id)
        lease = self.store.read_json(self.store.task_lease_path(expected))
        if lease is not None and not isinstance(lease, dict):
            raise TaskSessionError(f"Invalid task lease payload for Task {expected}")
        delivery = self.store.delivery_state()
        worktrees = self.repository.worktrees()
        matches = [
            item
            for item in worktrees
            if (lease and str(item.path) == lease.get("worktree"))
            or (item.branch and item.branch.startswith(f"task/{expected}-"))
        ]
        branches = [
            line.removeprefix("refs/heads/")
            for line in self.repository.git(
                "for-each-ref", "--format=%(refname)", f"refs/heads/task/{expected}-*"
            ).splitlines()
            if line
        ]
        details = [
            {
                **asdict(worktree),
                "path": str(worktree.path),
                "dirty": self.repository.status(worktree.path),
                "operation_issues": self.repository.operation_issues(worktree.path),
                "unique_commits": self.repository.unique_commits(worktree.branch)
                if worktree.branch
                else [],
            }
            for worktree in matches
        ]
        issues: list[str] = []
        state = self._lease_state(lease) if isinstance(lease, dict) else ""
        if lease is None:
            issues.append("missing task lease")
        if len(branches) > 1 or len(matches) > 1:
            issues.append("duplicate task branch/worktree")
        if lease and not matches:
            issues.append("lease exists but worktree is missing")
        stale_or_interrupted = any(item["dirty"] or item["operation_issues"] for item in details)
        if stale_or_interrupted:
            issues.append("dirty or interrupted worktree requires owner-safe recovery")
        # Unique commits are expected for a leased implementation/ready candidate.  They
        # remain visible in the report, but only an orphan/recovery worktree turns them into
        # an automatic-cleanup blocker.
        if (
            lease is None or state in {"recovery-required", "start-failed-recovery-required"}
        ) and any(item["unique_commits"] for item in details):
            issues.append("unique commits make automatic cleanup unsafe")
        owner = delivery.get("owner")
        owner_id = str(owner.get("task_id", "")).upper() if isinstance(owner, dict) else ""
        if owner_id == expected and state not in DELIVERY_OWNER_STATES:
            issues.append("delivery owner does not match task lifecycle state")
        if owner_id and owner_id != expected and state in DELIVERY_OWNER_STATES:
            issues.append(f"task is delivering while delivery owner is Task {owner_id}")
        if issues:
            classification = (
                "STALE_OR_INTERRUPTED"
                if stale_or_interrupted
                and len(issues) == 1
                and state not in {"recovery-required", "start-failed-recovery-required"}
                else "RECOVERY_REQUIRED"
            )
        elif state in READY_STATES:
            classification = "READY_FOR_DELIVERY"
        elif state in WAITING_STATES:
            classification = "WAITING_FOR_DELIVERY"
        elif state in SUPERSEDED_LEASE_STATES:
            classification = "SUPERSEDED"
        elif state in TERMINAL_LEASE_STATES:
            classification = "TERMINAL_SUCCESS"
        elif state in DELIVERY_STATES:
            classification = "DELIVERING"
        elif state in IMPLEMENTATION_STATES:
            classification = "ACTIVE"
        else:
            classification = "RECOVERY_REQUIRED"
        return {
            "task_id": expected,
            "lease": lease,
            "delivery": delivery,
            "branches": branches,
            "worktrees": details,
            "lifecycle_state": state or None,
            "classification": classification,
            "issues": issues,
            "mutation_performed": False,
        }

    def _superseding_reconciliation_master_snapshot(
        self, expected: str, lease: Mapping[str, Any], history: Mapping[str, Any]
    ) -> str | None:
        key = "superseding_production_reconciliation"
        if key not in history:
            return None
        audit = history.get(key)
        invalid = "finish refuses malformed superseding production reconciliation history"
        if not isinstance(audit, Mapping):
            raise TaskSessionError(invalid)
        original = audit.get("original_delivery")
        superseding = audit.get("superseding_prs")
        production = audit.get("production")
        anchor_classification = audit.get("anchor_classification", "exact_delivery_anchor")
        collapsed = audit.get("post_merge_collapsed_anchor")
        master_sha = str(audit.get("reconciled_against_master_sha", ""))
        deployed_sha = str(history.get("deployed_sha", ""))
        head_sha = str(history.get("head_sha", ""))
        base_sha = str(history.get("base_sha", ""))
        anchor = {
            "task_id": expected,
            "branch": lease.get("branch"),
            "base_sha": base_sha,
            "head_sha": head_sha,
        }
        if (
            audit.get("version") != 1
            or audit.get("owner_authorized") is not True
            or anchor_classification not in {"exact_delivery_anchor", "post_merge_collapsed_anchor"}
            or not isinstance(original, Mapping)
            or not isinstance(superseding, list)
            or not superseding
            or not isinstance(production, Mapping)
            or (
                anchor_classification == "post_merge_collapsed_anchor"
                and not isinstance(collapsed, Mapping)
            )
            or (anchor_classification == "exact_delivery_anchor" and collapsed is not None)
            or any(
                re.fullmatch(r"[0-9a-f]{40}", sha) is None
                for sha in (master_sha, deployed_sha, head_sha, base_sha)
            )
            or lease.get(key) != audit
            or history.get("closeout_required") is not True
            or history.get("merge_sha") != deployed_sha
            or lease.get("merge_sha") != deployed_sha
            or lease.get("deployed_sha") != deployed_sha
            or history.get("pr_number") != original.get("pr_number")
            or not (
                original.get("branch") == lease.get("branch")
                or TASK_INTEGRATION_BRANCHES.get(str(original.get("branch", ""))) == expected
            )
            or original.get("base_sha") != base_sha
            or original.get("head_sha") != head_sha
            or not self.repository.is_ancestor(deployed_sha, master_sha)
        ):
            raise TaskSessionError(invalid)

        entries = [original, *superseding]
        prior_merge_sha = ""
        numbers: set[int] = set()
        for item in entries:
            if not isinstance(item, Mapping):
                raise TaskSessionError(invalid)
            number = item.get("pr_number")
            branch = str(item.get("branch", ""))
            item_base = str(item.get("base_sha", ""))
            item_head = str(item.get("head_sha", ""))
            item_merge = str(item.get("merge_sha", ""))
            check = item.get("required_check")
            if (
                type(number) is not int
                or number <= 0
                or number in numbers
                or task_pr_task_id_from_branch(branch) != expected
                or any(
                    re.fullmatch(r"[0-9a-f]{40}", sha) is None
                    for sha in (item_base, item_head, item_merge)
                )
                or not isinstance(check, Mapping)
                or check.get("name") != "checks"
                or check.get("head_sha") != item_head
                or check.get("status") != "completed"
                or check.get("conclusion") != "SUCCESS"
                or item_base == item_merge
                or not self.repository.is_ancestor(item_base, item_merge)
                or (prior_merge_sha and not self.repository.is_ancestor(prior_merge_sha, item_base))
                or not self.repository.is_ancestor(item_merge, master_sha)
            ):
                raise TaskSessionError(invalid)
            numbers.add(number)
            prior_merge_sha = item_merge

        if anchor_classification == "exact_delivery_anchor":
            if lease.get("delivery_anchor") != anchor:
                raise TaskSessionError(invalid)
        else:
            if not isinstance(collapsed, Mapping):
                raise TaskSessionError(invalid)
            observed_anchor = collapsed.get("observed_recovery_anchor")
            final_pr = entries[-1]
            verified = (
                self._verified_post_merge_anchor(
                    expected, lease, observed_anchor, original, final_pr, deployed_sha
                )
                if isinstance(observed_anchor, Mapping)
                else None
            )
            if verified != collapsed:
                raise TaskSessionError(invalid)

        if (
            prior_merge_sha != deployed_sha
            or production.get("deployed_sha") != deployed_sha
            or production.get("run_conclusion") != "success"
            or production.get("environment") != "production"
            or production.get("deployment_success_verified") is not True
            or type(production.get("run_id")) is not int
            or production.get("run_id", 0) <= 0
        ):
            raise TaskSessionError(invalid)
        return master_sha

    def _reconciliation_master_snapshot(
        self, expected: str, lease: Mapping[str, Any], history: Mapping[str, Any]
    ) -> str | None:
        superseding_sha = self._superseding_reconciliation_master_snapshot(expected, lease, history)
        key = "subsequent_production_reconciliation"
        if key not in history:
            if key in lease:
                raise TaskSessionError(
                    "finish refuses unmatched subsequent production reconciliation"
                )
            return superseding_sha
        audit = history.get(key)
        deployed_sha = str(history.get("deployed_sha", ""))
        master_sha = str(audit.get("current_master_sha", "")) if isinstance(audit, Mapping) else ""
        production = audit.get("current_production") if isinstance(audit, Mapping) else None
        invalid = "finish refuses malformed subsequent production reconciliation history"
        if (
            not isinstance(audit, Mapping)
            or audit.get("version") != 1
            or audit.get("owner_authorized") is not True
            or audit.get("authorization") != "explicit --owner-authorize"
            or not isinstance(audit.get("authorized_at"), str)
            or not isinstance(audit.get("reconciled_at"), str)
            or audit.get("original_deployed_sha") != deployed_sha
            or lease.get("deployed_sha") != deployed_sha
            or history.get("merge_sha") != deployed_sha
            or lease.get("merge_sha") != deployed_sha
            or lease.get(key) != audit
            or history.get("closeout_required") is not True
            or re.fullmatch(r"[0-9a-f]{40}", deployed_sha) is None
            or re.fullmatch(r"[0-9a-f]{40}", master_sha) is None
            or not isinstance(production, Mapping)
            or production.get("deployment_state") != "success"
            or re.fullmatch(r"[0-9a-f]{40}", str(production.get("deployed_sha", ""))) is None
            or not self.repository.is_ancestor(deployed_sha, master_sha)
            or not self.repository.is_ancestor(str(production.get("deployed_sha")), master_sha)
        ):
            raise TaskSessionError(invalid)

        chain = audit.get("intervening_commits")
        if not isinstance(chain, list) or not chain:
            raise TaskSessionError(invalid)
        origin_master_sha = self.repository.ref("origin/master")
        if origin_master_sha != master_sha:
            raise TaskSessionError(
                "finish requires master to remain at the reconciled protected-master SHA"
            )
        self._verify_live_master(master_sha)
        evidence = self._verified_subsequent_production_chain(deployed_sha, master_sha)
        if any(audit.get(field) != evidence.get(field) for field in evidence):
            raise TaskSessionError("finish refuses stale subsequent production evidence")
        if superseding_sha is not None and not self.repository.is_ancestor(
            superseding_sha, master_sha
        ):
            raise TaskSessionError(invalid)
        return master_sha

    def finish(self, task_id: str) -> dict[str, Any]:
        expected = normalize_task_id(task_id)
        lease_path = self.store.task_lease_path(expected)
        lease = self.store.read_json(lease_path)
        history_path = self.store.history / f"task-{expected}.json"
        history = self.store.read_json(history_path)
        if lease is None or history is None:
            raise TaskSessionError("finish requires task lease and production success history")
        if lease.get("task_id") != expected or history.get("task_id") != expected:
            raise TaskSessionError("finish task lease/history does not match requested task ID")
        if (
            lease.get("lifecycle_state") != "production-success"
            or history.get("state") != "production-success"
        ):
            raise TaskSessionError("finish requires terminal production-success state")
        delivery = self.store.delivery_state()
        owner = delivery.get("owner")
        owner_id = str(owner.get("task_id", "")).upper() if isinstance(owner, dict) else ""
        if owner_id == expected and lease.get("lifecycle_state") != "production-success":
            raise TaskSessionError(
                "finish requires terminal production success before releasing delivery"
            )
        if (
            owner_id
            and owner_id != expected
            and lease.get("lifecycle_state") == "production-success"
        ):
            raise TaskSessionError(
                "finish refuses cleanup while another task owns the delivery lane"
            )
        branch = str(lease.get("branch", ""))
        worktree_path = Path(str(lease.get("worktree", ""))).resolve()
        expected_head = str(lease.get("ready_head_sha", ""))
        deployed_sha = str(history.get("deployed_sha", ""))
        root = self._canonical_root()
        expected_parent = (root / ".artifacts" / "worktrees").resolve()
        if worktree_path.parent != expected_parent:
            raise TaskSessionError(
                "finish cleanup worktree is outside canonical task worktree directory"
            )
        if task_id_from_branch(branch) != expected:
            raise TaskSessionError("finish cleanup branch does not match task lease")
        if not expected_head or not deployed_sha:
            raise TaskSessionError("finish requires exact ready and deployed SHAs")
        reconciliation_master_sha = self._reconciliation_master_snapshot(expected, lease, history)
        if self.repository.current_worktree != root:
            raise TaskSessionError("finish cleanup must run from the canonical repository worktree")
        origin_master_sha = self.repository.ref("origin/master")
        if reconciliation_master_sha is not None:
            self._verify_live_master(origin_master_sha)
            if not self.repository.is_ancestor(reconciliation_master_sha, origin_master_sha):
                raise TaskSessionError(
                    "finish requires current master to descend from the reconciled master snapshot"
                )
            if self._active_production_deployment():
                raise TaskSessionError("finish refuses while a production deployment is active")
        if origin_master_sha != deployed_sha:
            if not origin_master_sha or not self.repository.is_ancestor(
                deployed_sha, origin_master_sha
            ):
                raise TaskSessionError(
                    "finish requires deployed SHA to be an ancestor of origin/master"
                )
            drift_base_sha = reconciliation_master_sha or deployed_sha
            drift_subjects = self.repository.git(
                "log", "--format=%s", f"{drift_base_sha}..{origin_master_sha}", check=False
            ).splitlines()
            drift_paths = {
                path
                for path in self.repository.git(
                    "diff", "--name-only", f"{drift_base_sha}..{origin_master_sha}", check=False
                ).splitlines()
                if path
            }
            if reconciliation_master_sha is None and not drift_subjects:
                raise TaskSessionError("finish refuses non-controller drift after deployed master")
            if drift_subjects and (
                any(
                    not (
                        CONTROLLER_COMMIT_RE.match(subject)
                        or subject.startswith("Merge pull request #")
                    )
                    for subject in drift_subjects
                )
                or not any(CONTROLLER_COMMIT_RE.match(subject) for subject in drift_subjects)
                or not drift_paths
                or not drift_paths.issubset(CONTROLLER_ALLOWED_PATHS)
            ):
                raise TaskSessionError(
                    "finish refuses non-controller drift after reconciled master"
                    if reconciliation_master_sha is not None
                    else "finish refuses non-controller drift after deployed master"
                )
        if self.repository.current_branch(cwd=root) != "master":
            raise TaskSessionError("finish cleanup requires canonical worktree on local master")
        local_master_was_stale = self.repository.ref("master") != origin_master_sha
        if local_master_was_stale:
            if not self.repository.is_ancestor(self.repository.ref("master"), origin_master_sha):
                raise TaskSessionError(
                    "finish refuses to fast-forward local master because it diverged from origin/master"
                )
            try:
                self.repository.fast_forward_current("origin/master", cwd=root)
            except Exception as error:
                raise TaskSessionError(
                    f"finish could not fast-forward local master to origin/master: {error}"
                ) from error
            if self.repository.ref("master") != origin_master_sha:
                raise TaskSessionError("finish local master did not reach origin/master")
        branches = [
            line.removeprefix("refs/heads/")
            for line in self.repository.git(
                "for-each-ref", "--format=%(refname)", f"refs/heads/task/{expected}-*"
            ).splitlines()
            if line
        ]
        matches = [
            item
            for item in self.repository.worktrees()
            if item.path == worktree_path
            or (item.branch and item.branch.startswith(f"task/{expected}-"))
        ]
        if branches != [branch] or len(matches) > 1:
            raise TaskSessionError(
                "finish cleanup requires exactly one matching task branch/worktree"
            )
        worktree_registered = len(matches) == 1
        if worktree_registered and (
            matches[0].branch != branch or matches[0].path != worktree_path
        ):
            raise TaskSessionError(
                "finish cleanup requires exactly one matching task branch/worktree"
            )
        if not worktree_registered and worktree_path.exists():
            raise TaskSessionError(
                "finish cleanup found an unregistered task worktree at the expected path"
            )
        if self.repository.ref(branch) != expected_head or (
            worktree_registered and matches[0].head != expected_head
        ):
            raise TaskSessionError("finish cleanup branch/worktree head changed after readiness")
        if worktree_registered and self.repository.status(worktree_path):
            raise TaskSessionError(f"finish cleanup refuses dirty task worktree {worktree_path}")
        operations = self.repository.operation_issues(worktree_path) if worktree_registered else []
        if operations:
            raise TaskSessionError(
                f"finish cleanup refuses interrupted Git operation: {operations}"
            )
        task_head_is_merged = self.repository.is_ancestor(expected_head, deployed_sha)
        squash_merge_is_verified = (
            not task_head_is_merged
            and history.get("head_sha") == expected_head
            and history.get("merge_sha") == deployed_sha
            and history.get("deployed_sha") == deployed_sha
        )
        if not task_head_is_merged and not squash_merge_is_verified:
            raise TaskSessionError("finish cleanup refuses task head absent from deployed master")
        if self.repository.unique_commits(branch) and not squash_merge_is_verified:
            raise TaskSessionError("finish cleanup refuses task branch with unique commits")
        artifact_cleanup: dict[str, Any] = {"status": "noop", "removed_count": 0}
        try:
            preserved_prefixes = _active_delivery_exclude_prefixes(root, expected)
            artifact_cleanup = ArtifactManager(
                root / ".artifacts", repo_root=root, controller_state_dir=self.store.root
            ).cleanup_task(
                expected,
                terminal_state="finished",
                exclude_prefixes=preserved_prefixes,
            )
        except ArtifactError as error:
            raise TaskSessionError(f"finish artifact cleanup failed closed: {error}") from error
        if artifact_cleanup.get("status") not in {"completed", "noop"} or artifact_cleanup.get(
            "cleanup_errors"
        ):
            raise TaskSessionError("finish artifact cleanup stopped fail-closed")
        if worktree_registered:
            self.repository.remove_worktree(worktree_path)
        if self.repository.ref(branch) != expected_head:
            raise TaskSessionError("finish cleanup branch changed after worktree removal")
        if squash_merge_is_verified:
            self.repository.delete_local_branch(branch, force=True)
        else:
            self.repository.delete_local_branch(branch)
        with self.store.lock():
            current = self.store.read_json(lease_path)
            latest_delivery = self.store.delivery_state()
            current_owner = latest_delivery.get("owner")
            current_owner_id = (
                str(current_owner.get("task_id", "")).upper()
                if isinstance(current_owner, dict)
                else ""
            )
            if (
                not isinstance(current, dict)
                or current.get("lifecycle_state") != "production-success"
            ):
                raise TaskSessionError("finish task lease changed before terminal closeout")
            if current_owner_id not in {"", expected}:
                raise TaskSessionError(
                    "finish refuses cleanup while another task owns the delivery lane"
                )
            history["state"] = "finished"
            history["finished_at"] = utc_now()
            history["cleanup"] = {
                "worktree": str(worktree_path),
                "branch": branch,
                "worktree_already_removed": not worktree_registered,
                "local_master_fast_forwarded": local_master_was_stale,
            }
            history["artifact_cleanup"] = artifact_cleanup
            StateStore.replace_json(history_path, history)
            lease_path.unlink()
            latest_delivery["owner"] = None
            latest_delivery.pop("priority_override", None)
            latest_delivery["updated_at"] = utc_now()
            StateStore.replace_json(self.store.delivery_path, latest_delivery)
            next_owner = self._promote_next_delivery_locked(latest_delivery)
            history["next_delivery_owner"] = next_owner
            StateStore.replace_json(history_path, history)
        return {
            "history": history,
            "cleanup_performed": True,
            "removed_worktree": str(worktree_path),
            "deleted_local_branch": branch,
            "worktree_already_removed": not worktree_registered,
            "local_master_fast_forwarded": local_master_was_stale,
        }


def archive_guard(backlog_root: Path, task_id: str) -> None:
    repository_root = next(
        (
            candidate
            for candidate in (backlog_root.resolve(), *backlog_root.resolve().parents)
            if (candidate / ".git").exists()
        ),
        None,
    )
    if repository_root is None:
        return
    common_dir = Path(
        _run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=repository_root,
        ).stdout.strip()
    ).resolve()
    store = StateStore(common_dir)
    if not (store.root / "contract.json").exists():
        return
    expected = normalize_task_id(task_id)
    history = store.read_json(store.history / f"task-{expected}.json")
    if isinstance(history, dict) and history.get("state") == "finished":
        return
    lease = store.read_json(store.task_lease_path(expected))
    if (
        isinstance(lease, dict)
        and lease.get("task_id") == expected
        and lease.get("mode") == "write"
        and lease.get("owner_authorized") is True
        and lease.get("lifecycle_state") in SUPERSEDED_LEASE_STATES
    ):
        reason = lease.get("superseded_reason")
        timestamp = lease.get("superseded_at")
        if isinstance(reason, str) and reason.strip() and isinstance(timestamp, str) and timestamp:
            return
    raise TaskSessionError(
        f"Task {task_id} cannot be archived before controller finish/terminal production success "
        "or owner-authorized supersede"
    )


def _print(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--github-repository")
    subparsers = parser.add_subparsers(dest="command", required=True)
    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--offline", action="store_true")
    subparsers.add_parser("status")
    subparsers.add_parser("validate-metadata")
    start = subparsers.add_parser("start")
    start.add_argument("task_id")
    start.add_argument("--owner-launch", action="store_true")
    start.add_argument("--session-label", required=True)
    start.add_argument("--mode", choices=("write",), default="write")
    start.add_argument("--slug")
    start.add_argument("--dependency-id", action="append")
    start.add_argument("--offline", action="store_true")
    start.add_argument("--queue-mode", action="store_true")
    resume = subparsers.add_parser("resume-preimplementation")
    resume.add_argument("task_id")
    resume.add_argument("--control-issue", type=int, required=True)
    resume.add_argument("--reason", required=True)
    resume.add_argument("--owner-authorize", action="store_true")
    guard_resume = subparsers.add_parser("resume-guard-interrupted")
    guard_resume.add_argument("task_id")
    guard_resume.add_argument("--control-issue", type=int, required=True)
    guard_resume.add_argument("--reason", required=True)
    guard_resume.add_argument("--owner-authorize", action="store_true")
    transport_resume = subparsers.add_parser("resume-transport-interrupted")
    transport_resume.add_argument("task_id")
    transport_resume.add_argument("--control-issue", type=int, required=True)
    transport_resume.add_argument("--reason", required=True)
    transport_resume.add_argument("--owner-authorize", action="store_true")
    claim_worker = subparsers.add_parser("claim-preimplementation-worker-launch")
    claim_worker.add_argument("task_id")
    release_worker = subparsers.add_parser("release-preimplementation-worker-launch")
    release_worker.add_argument("task_id")
    release_worker.add_argument("--launch-id", required=True)
    release_worker.add_argument("--worker-state-path", type=Path, required=True)
    release_worker.add_argument("--reason", required=True)
    record_worker = subparsers.add_parser("record-preimplementation-worker-started")
    record_worker.add_argument("task_id")
    record_worker.add_argument("--worker-state-path", type=Path, required=True)
    adopt = subparsers.add_parser("adopt-current")
    adopt.add_argument("task_id")
    adopt.add_argument("--owner-launch", action="store_true")
    adopt.add_argument("--session-label", required=True)
    adopt.add_argument("--offline", action="store_true")
    canonical_refresh = subparsers.add_parser(
        "refresh-canonical-master", aliases=("refresh-canonical",)
    )
    canonical_refresh.add_argument("--offline", action="store_true")
    ready = subparsers.add_parser("mark-ready")
    ready.add_argument("task_id")
    ready.add_argument("--head-sha", required=True)
    ready.add_argument(
        "--quality-verdict",
        choices=("PASS",),
        required=True,
    )
    ready.add_argument("--qa-verdict", choices=("PASS", "NOT_REQUIRED"), default="NOT_REQUIRED")
    acquire_delivery = subparsers.add_parser("acquire-delivery")
    acquire_delivery.add_argument("task_id")
    acquire_delivery.add_argument("--offline", action="store_true")
    acquire_delivery.add_argument("--owner-priority-reason")
    refresh_delivery = subparsers.add_parser("refresh-delivery")
    refresh_delivery.add_argument("task_id")
    refresh_delivery.add_argument("--offline", action="store_true")
    validate_delivery = subparsers.add_parser("validate-delivery")
    validate_delivery.add_argument("task_id")
    validate_delivery.add_argument("--offline", action="store_true")
    release_delivery = subparsers.add_parser("release-delivery")
    release_delivery.add_argument("task_id")
    release_delivery.add_argument("--reason", required=True)
    release_delivery.add_argument("--offline", action="store_true")
    reopen_review = subparsers.add_parser("reopen-for-review")
    reopen_review.add_argument("task_id")
    reopen_review.add_argument("--reason", required=True)
    reopen_production = subparsers.add_parser("reopen-after-production")
    reopen_production.add_argument("task_id")
    reopen_production.add_argument("--reason", required=True)
    reopen_production.add_argument("--owner-authorize", action="store_true")
    resolve_recovery = subparsers.add_parser("resolve-recovery")
    resolve_recovery.add_argument("task_id")
    resolve_recovery.add_argument("--reason", required=True)
    resolve_recovery.add_argument("--owner-authorize", action="store_true")
    supersede = subparsers.add_parser("supersede")
    supersede.add_argument("task_id")
    supersede.add_argument("--reason", required=True)
    supersede.add_argument("--owner-authorize", action="store_true")
    queue_cycle = subparsers.add_parser("record-queue-cycle")
    queue_cycle.add_argument("task_id")
    queue_cycle.add_argument("--kind", choices=("review", "ci"), required=True)
    queue_cycle.add_argument("--reason", required=True)
    production = subparsers.add_parser("complete-production")
    production.add_argument("task_id")
    production.add_argument("--pr", type=int, required=True)
    production.add_argument("--merge-sha", required=True)
    production.add_argument("--deployed-sha", required=True)
    reconcile_production = subparsers.add_parser("reconcile-production-success")
    reconcile_production.add_argument("task_id")
    reconcile_production.add_argument("--original-pr", type=int, required=True)
    reconcile_production.add_argument("--superseding-pr", type=int, action="append", required=True)
    reconcile_production.add_argument("--deployed-sha", required=True)
    reconcile_production.add_argument("--production-run", type=int, required=True)
    reconcile_production.add_argument("--owner-authorize", action="store_true")
    reconcile_ready_production = subparsers.add_parser("reconcile-ready-production-success")
    reconcile_ready_production.add_argument("task_id")
    reconcile_ready_production.add_argument("--pr", type=int, required=True)
    reconcile_ready_production.add_argument("--deployed-sha", required=True)
    reconcile_ready_production.add_argument("--production-run", type=int, required=True)
    reconcile_ready_production.add_argument("--owner-authorize", action="store_true")
    reconcile_subsequent = subparsers.add_parser("reconcile-subsequent-production")
    reconcile_subsequent.add_argument("task_id")
    reconcile_subsequent.add_argument("--owner-authorize", action="store_true")
    recover = subparsers.add_parser("recover")
    recover.add_argument("task_id")
    finish = subparsers.add_parser("finish")
    finish.add_argument("task_id")
    validate_pr = subparsers.add_parser("validate-pr")
    validate_pr.add_argument("--event", type=Path, required=True)
    merge = subparsers.add_parser("verify-master-merge")
    merge.add_argument("--sha", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        repository = GitRepository(args.repo)
        github = (
            None
            if bool(getattr(args, "offline", False))
            else GitHubClient(repository, args.github_repository)
        )
        controller = TaskController(repository, github=github)
        if args.command == "doctor":
            payload = controller.doctor(offline=args.offline)
            _print(payload)
            return 0 if payload["ok"] else 1
        if args.command == "status":
            _print(controller.status())
            return 0
        if args.command == "validate-metadata":
            payload = controller.validate_metadata()
            _print(payload)
            return 0 if payload["ok"] else 1
        if args.command == "start":
            _print(
                controller.start(
                    args.task_id,
                    owner_launch=args.owner_launch,
                    session_label=args.session_label,
                    mode=args.mode,
                    slug=args.slug,
                    dependency_ids=args.dependency_id,
                    offline=args.offline,
                    queue_mode=args.queue_mode,
                )
            )
            return 0
        if args.command == "resume-preimplementation":
            _print(
                controller.resume_preimplementation(
                    args.task_id,
                    control_issue_number=args.control_issue,
                    reason=args.reason,
                    owner_authorize=args.owner_authorize,
                )
            )
            return 0
        if args.command == "resume-guard-interrupted":
            try:
                payload = controller.resume_guard_interrupted(
                    args.task_id,
                    control_issue_number=args.control_issue,
                    reason=args.reason,
                    owner_authorize=args.owner_authorize,
                )
            except TaskSessionError as error:
                raise TaskSessionError(f"HUMAN_REQUIRED: {error}") from error
            _print(payload)
            return 0
        if args.command == "resume-transport-interrupted":
            try:
                payload = controller.resume_transport_interrupted(
                    args.task_id,
                    control_issue_number=args.control_issue,
                    reason=args.reason,
                    owner_authorize=args.owner_authorize,
                )
            except TaskSessionError as error:
                raise TaskSessionError(f"HUMAN_REQUIRED: {error}") from error
            _print(payload)
            return 0
        if args.command == "claim-preimplementation-worker-launch":
            _print(controller.claim_preimplementation_worker_launch(args.task_id))
            return 0
        if args.command == "release-preimplementation-worker-launch":
            _print(
                controller.release_preimplementation_worker_launch(
                    args.task_id,
                    launch_id=args.launch_id,
                    worker_state_path=args.worker_state_path,
                    reason=args.reason,
                )
            )
            return 0
        if args.command == "record-preimplementation-worker-started":
            _print(
                controller.record_preimplementation_worker_started(
                    args.task_id,
                    worker_state_path=args.worker_state_path,
                )
            )
            return 0
        if args.command == "adopt-current":
            _print(
                controller.adopt_current(
                    args.task_id,
                    owner_launch=args.owner_launch,
                    session_label=args.session_label,
                    offline=args.offline,
                )
            )
            return 0
        if args.command in {"refresh-canonical-master", "refresh-canonical"}:
            payload = controller.refresh_canonical_master(offline=args.offline)
            _print(payload)
            return 0 if payload["result"] in {"ALIGNED", "REFRESHED", "WAITING"} else 1
        if args.command == "mark-ready":
            _print(
                controller.mark_ready(
                    args.task_id,
                    head_sha=args.head_sha,
                    quality_verdict=args.quality_verdict,
                    qa_verdict=args.qa_verdict,
                )
            )
            return 0
        if args.command == "acquire-delivery":
            _print(
                controller.acquire_delivery(
                    args.task_id,
                    offline=args.offline,
                    owner_priority_reason=args.owner_priority_reason,
                )
            )
            return 0
        if args.command == "refresh-delivery":
            _print(controller.refresh_for_delivery(args.task_id, offline=args.offline))
            return 0
        if args.command == "validate-delivery":
            _print(controller.validate_delivery(args.task_id, offline=args.offline))
            return 0
        if args.command == "release-delivery":
            _print(
                controller.release_delivery(args.task_id, reason=args.reason, offline=args.offline)
            )
            return 0
        if args.command == "reopen-for-review":
            _print(controller.reopen_for_review(args.task_id, reason=args.reason))
            return 0
        if args.command == "reopen-after-production":
            _print(
                controller.reopen_after_production(
                    args.task_id,
                    reason=args.reason,
                    owner_authorize=args.owner_authorize,
                )
            )
            return 0
        if args.command == "resolve-recovery":
            _print(
                controller.resolve_recovery(
                    args.task_id,
                    reason=args.reason,
                    owner_authorize=args.owner_authorize,
                )
            )
            return 0
        if args.command == "supersede":
            _print(
                controller.supersede(
                    args.task_id,
                    reason=args.reason,
                    owner_authorize=args.owner_authorize,
                )
            )
            return 0
        if args.command == "record-queue-cycle":
            _print(
                controller.record_queue_cycle(
                    args.task_id,
                    kind=args.kind,
                    reason=args.reason,
                )
            )
            return 0
        if args.command == "complete-production":
            _print(
                controller.record_production_success(
                    args.task_id,
                    pr_number=args.pr,
                    merge_sha=args.merge_sha,
                    deployed_sha=args.deployed_sha,
                )
            )
            return 0
        if args.command == "reconcile-production-success":
            _print(
                controller.reconcile_production_success(
                    args.task_id,
                    original_pr_number=args.original_pr,
                    superseding_pr_numbers=args.superseding_pr,
                    deployed_sha=args.deployed_sha,
                    production_run_id=args.production_run,
                    owner_authorize=args.owner_authorize,
                )
            )
            return 0
        if args.command == "reconcile-ready-production-success":
            _print(
                controller.reconcile_ready_production_success(
                    args.task_id,
                    pr_number=args.pr,
                    deployed_sha=args.deployed_sha,
                    production_run_id=args.production_run,
                    owner_authorize=args.owner_authorize,
                )
            )
            return 0
        if args.command == "reconcile-subsequent-production":
            _print(
                controller.reconcile_subsequent_production(
                    args.task_id,
                    owner_authorize=args.owner_authorize,
                )
            )
            return 0
        if args.command == "recover":
            _print(controller.recover(args.task_id))
            return 0
        if args.command == "finish":
            _print(controller.finish(args.task_id))
            return 0
        if args.command == "validate-pr":
            _print(validate_pr_event(repository, github, args.event))
            return 0
        if args.command == "verify-master-merge":
            _print(verify_master_merge(repository, github, sha=args.sha))
            return 0
        raise AssertionError(f"Unhandled command: {args.command}")
    except (TaskSessionError, OSError, json.JSONDecodeError) as error:
        print(f"task session error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
