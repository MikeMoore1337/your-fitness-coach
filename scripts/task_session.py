"""Fail-closed task worktree, provenance and trunk-based release controller.

The normal lifecycle is deliberately small: a task branch is based on master,
passes the local exact-HEAD gate, enters a PR into master, and is closed only
after the merged master revision is deployed successfully.  Coordination state
lives in the shared Git common directory and is never committed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.artifact_manager import ArtifactError, ArtifactManager
    from scripts.issue_workflow import DEFAULT_QUEUE_BUDGET, IssueWorkflowError, normalize_severity
except ModuleNotFoundError:
    from artifact_manager import ArtifactError, ArtifactManager
    from issue_workflow import DEFAULT_QUEUE_BUDGET, IssueWorkflowError, normalize_severity

TASK_ID_PATTERN = r"[0-9]+[A-Z]?"
TASK_ID_RE = re.compile(rf"^{TASK_ID_PATTERN}$", re.IGNORECASE)
TASK_BRANCH_RE = re.compile(
    rf"^task/(?P<task_id>{TASK_ID_PATTERN})-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)$",
    re.IGNORECASE,
)
TASK_COMMIT_RE = re.compile(rf"\[Task (?P<task_id>{TASK_ID_PATTERN})\]", re.IGNORECASE)
TASK_DEPENDENCY_RE = re.compile(r"(?im)^Depends-on:\s*(?P<value>.+)$")
TASK_FILE_RE = re.compile(rf"^(?P<task_id>{TASK_ID_PATTERN})-(?P<slug>.+)\.md$", re.IGNORECASE)
TASK_STATE_VERSION = 2
STATE_DIRECTORY_NAME = "codex-task-sessions-v1"
ACTIVE_DELIVERY_ARTIFACTS_ENV = "YFC_ACTIVE_DELIVERY_ARTIFACTS"
TARGET_BASE_BRANCH = "master"
DEPENDABOT_LOGIN = "dependabot[bot]"
VALID_CHECK_CONCLUSIONS = {"SUCCESS"}
UMBRELLA_TASK_IDS = {"90", "92", "93", "94", "95", "99", "100", "126"}
TRUSTED_REVIEW_LOGINS = frozenset({"chatgpt-codex-connector"})
REVIEWED_COMMIT_RE = re.compile(
    r"(?im)\b(?:reviewed\s+commit|reviewed\s+head|commit)\b\s*\*{0,2}\s*[:=]\s*\*{0,2}\s*`?([0-9a-f]{7,40})`?"
)
REVIEW_COMPLETED_MARKERS = ("codex review", "review status completed")
REVIEW_MERGEABILITY_TIMEOUT_SECONDS = 30.0
REVIEW_MERGEABILITY_POLL_SECONDS = 1.0
REVIEW_APPROVAL_RE = re.compile(
    r"(?ix)"
    r"(?:didn['’]t|did\s+not)\s+find\s+any\s+(?:major\s+)?issues"
    r"|(?:^|[\n:])\s*no\s+blocking\s+(?:findings|issues)\b"
    r"|(?:^|[\n:])\s*(?:review\s+)?(?:verdict|status)\s*[:=-]\s*(?:pass|approved)\b"
    r"|(?:^|[\n:])\s*approved(?:\s+for\s+merge)?\b"
)
REVIEW_BLOCKING_MARKER_RE = re.compile(
    r"(?i)(?<![a-z0-9])(?:P[0-2]|BLOCKER|HIGH|MEDIUM)(?![a-z0-9])"
)

# A task lease, an implementation exclusion, and delivery ownership are separate controller
# concerns.  Only an exclusive-write lease in an implementation state owns the implementation
# exclusion.  A ready, waiting, delivery, or production-success lease remains a task session but
# does not hold that exclusion; delivery ownership is serialized independently below.
IMPLEMENTATION_STATES = frozenset({"starting", "implementation", "review", "qa"})
READY_STATES = frozenset({"ready-for-delivery", "ready-for-pr"})
WAITING_STATES = frozenset({"waiting-for-delivery"})
DELIVERY_STATES = frozenset({"delivering", "delivery-refreshing", "delivery-gate"})
TERMINAL_LEASE_STATES = frozenset({"production-success"})
RECOVERY_STATES = frozenset({"recovery-required", "start-failed-recovery-required"})
KNOWN_LEASE_STATES = (
    IMPLEMENTATION_STATES
    | READY_STATES
    | WAITING_STATES
    | DELIVERY_STATES
    | TERMINAL_LEASE_STATES
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


def is_dependabot_pull_request(pull_request: Mapping[str, Any]) -> bool:
    user = pull_request.get("user")
    return isinstance(user, Mapping) and user.get("login") == DEPENDABOT_LOGIN


def normalize_concurrency_class(value: str) -> str:
    concurrency_class = value.strip().lower()
    if concurrency_class in {"exclusive-write", "independent-write"}:
        return concurrency_class
    raise TaskSessionError("Concurrency must be exclusive-write or independent-write")


def write_lanes_compatible(first: str, second: str) -> bool:
    left = normalize_concurrency_class(first)
    right = normalize_concurrency_class(second)
    return left == right == "independent-write"


def _task_commit_ids(message: str) -> set[str]:
    without_dependency_trailers = TASK_DEPENDENCY_RE.sub("", message)
    return {
        match.group("task_id").upper()
        for match in TASK_COMMIT_RE.finditer(without_dependency_trailers)
    }


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

    def fetch_origin_master(self, *, cwd: Path | None = None, prune: bool = True) -> None:
        args = ["fetch"]
        if prune:
            args.append("--prune")
        args.extend(("origin", "master"))
        self.git(*args, cwd=cwd)

    def head(self, *, cwd: Path | None = None) -> str:
        return self.git("rev-parse", "HEAD", cwd=cwd)

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

    def delete_local_branch(self, branch: str) -> None:
        self.git("branch", "--delete", "--", branch, cwd=self.current_worktree)

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
        # Ordinary tasks are safe to start in separate worktrees.  A task must opt into the
        # stronger class explicitly because it changes the global implementation lane.
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
        try:
            descriptor = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as error:
            raise TaskSessionError(
                f"Coordination state is locked: {self.lock_path}; run recover, do not delete it"
            ) from error
        try:
            os.write(descriptor, f"pid={os.getpid()} created_at={utc_now()}\n".encode())
            os.close(descriptor)
            yield
        finally:
            self.lock_path.unlink(missing_ok=True)

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

    def pull_request(self, number: int) -> dict[str, Any]:
        return dict(self.api(f"pulls/{number}"))

    def pull_request_commits(self, number: int) -> list[dict[str, Any]]:
        return list(self.api(f"pulls/{number}/commits?per_page=100"))

    def pull_request_files(self, number: int) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = list(self.api(f"pulls/{number}/files?per_page=100&page={page}"))
            files.extend(batch)
            if len(batch) < 100:
                return files
            page += 1

    def pull_request_reviews(self, number: int) -> list[dict[str, Any]]:
        reviews: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = list(self.api(f"pulls/{number}/reviews?per_page=100&page={page}"))
            reviews.extend(batch)
            if len(batch) < 100:
                return reviews
            page += 1

    def issue_comments(self, number: int) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = list(self.api(f"issues/{number}/comments?per_page=100&page={page}"))
            comments.extend(batch)
            if len(batch) < 100:
                return comments
            page += 1

    def review_threads(self, number: int) -> list[dict[str, Any]]:
        owner, separator, name = self.repo_slug.partition("/")
        if not separator or not owner or not name:
            raise TaskSessionError("Cannot query review threads without an owner/repository slug")
        query = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        nodes { isResolved }
        pageInfo { hasNextPage }
      }
    }
  }
}
""".strip()
        result = _run(
            [
                "gh",
                "api",
                "graphql",
                "-f",
                f"query={query}",
                "-F",
                f"owner={owner}",
                "-F",
                f"name={name}",
                "-F",
                f"number={number}",
            ],
            cwd=self.repository.current_worktree,
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise TaskSessionError("GitHub returned invalid review-thread JSON") from error
        errors = payload.get("errors")
        if errors:
            raise TaskSessionError(f"GitHub review-thread query failed: {errors}")
        pull_request = payload.get("data", {}).get("repository", {}).get("pullRequest")
        if not isinstance(pull_request, Mapping):
            raise TaskSessionError("GitHub review-thread query returned no pull request")
        threads = pull_request.get("reviewThreads", {})
        if not isinstance(threads, Mapping):
            raise TaskSessionError("GitHub review-thread query returned an invalid connection")
        page_info = threads.get("pageInfo", {})
        if isinstance(page_info, Mapping) and page_info.get("hasNextPage"):
            raise TaskSessionError("GitHub review-thread inventory exceeds the bounded page size")
        nodes = threads.get("nodes", [])
        if not isinstance(nodes, list):
            raise TaskSessionError("GitHub review-thread query returned invalid nodes")
        return [dict(item) for item in nodes if isinstance(item, Mapping)]

    def check_runs(self, sha: str) -> list[dict[str, Any]]:
        payload = self.api(f"commits/{sha}/check-runs?per_page=100")
        return list(payload.get("check_runs", []))

    def workflow_runs(self, workflow: str, sha: str) -> list[dict[str, Any]]:
        payload = self.api(f"actions/workflows/{workflow}/runs?head_sha={sha}&per_page=100")
        return list(payload.get("workflow_runs", []))

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


def _pull_request_with_resolved_mergeability(
    github: GitHubClient,
    number: int,
    *,
    timeout_seconds: float = REVIEW_MERGEABILITY_TIMEOUT_SECONDS,
    poll_seconds: float = REVIEW_MERGEABILITY_POLL_SECONDS,
    clock: Callable[[], float] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Poll GitHub until the PR mergeability calculation is available or times out."""

    if timeout_seconds <= 0 or poll_seconds <= 0:
        raise TaskSessionError("PR mergeability polling requires positive timeout and interval")
    clock = time.monotonic if clock is None else clock
    sleeper = time.sleep if sleeper is None else sleeper
    deadline = clock() + timeout_seconds
    pull_request = github.pull_request(number)
    while pull_request.get("mergeable") is None:
        remaining = deadline - clock()
        if remaining <= 0:
            return pull_request
        sleeper(min(poll_seconds, remaining))
        pull_request = github.pull_request(number)
    return pull_request


def _successful_exact_check(checks: Sequence[Mapping[str, Any]], name: str, sha: str) -> bool:
    return any(
        item.get("name") == name
        and item.get("head_sha") == sha
        and item.get("status") == "completed"
        and str(item.get("conclusion", "")).upper() in VALID_CHECK_CONCLUSIONS
        for item in checks
    )


def reviewed_commit_markers(body: str) -> tuple[str, ...]:
    """Return bounded commit markers found in a review summary."""

    return tuple(match.group(1).lower() for match in REVIEWED_COMMIT_RE.finditer(body))


def _commit_shas(commits: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    return tuple(
        sha
        for item in commits
        if (sha := str(item.get("sha") or item.get("oid") or "").strip().lower())
        and re.fullmatch(r"[0-9a-f]{40}", sha)
    )


def _review_login(item: Mapping[str, Any]) -> str:
    for key in ("user", "author"):
        value = item.get(key)
        if isinstance(value, Mapping) and value.get("login"):
            # GitHub exposes App/bot accounts with a trailing ``[bot]`` suffix while
            # the trusted identity is configured by its canonical login.
            return re.sub(r"\[bot\]$", "", str(value["login"]).strip().casefold())
    return ""


def _marker_matches_head(
    marker: str,
    head_sha: str,
    *,
    known_commit_shas: Sequence[str] | None = None,
) -> bool:
    normalized = marker.strip().lower()
    normalized_head = head_sha.strip().lower()
    if len(normalized) == 40:
        return normalized == normalized_head
    if len(normalized) < 7 or not normalized_head.startswith(normalized):
        return False
    matching_shas = {
        candidate
        for raw_candidate in known_commit_shas or ()
        if (candidate := str(raw_candidate).strip().lower())
        and re.fullmatch(r"[0-9a-f]{40}", candidate)
        and candidate.startswith(normalized)
    }
    return matching_shas == {normalized_head}


def _review_body(item: Mapping[str, Any]) -> str:
    return str(item.get("body") or item.get("text") or "")


def _is_approving_codex_review(body: str) -> bool:
    """Accept only an explicit no-findings/approval verdict from the connector."""

    return bool(REVIEW_APPROVAL_RE.search(body)) and not bool(
        REVIEW_BLOCKING_MARKER_RE.search(body)
    )


def _effective_current_head_reviews(
    reviews: Sequence[Mapping[str, Any]],
    head_sha: str,
    *,
    known_commit_shas: Sequence[str] | None = None,
) -> list[Mapping[str, Any]]:
    """Keep the latest state-changing review from each reviewer for this exact head."""

    effective: dict[str, tuple[str, int, Mapping[str, Any]]] = {}
    state_changers = {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}
    for index, review in enumerate(reviews):
        review_head = str(review.get("commit_id", review.get("commitId", "")))
        if not _marker_matches_head(review_head, head_sha, known_commit_shas=known_commit_shas):
            continue
        state = str(review.get("state", "")).upper()
        if state not in state_changers:
            continue
        reviewer = _review_login(review) or f"review-{review.get('id', index)}"
        timestamp = str(
            review.get("submitted_at")
            or review.get("submittedAt")
            or review.get("created_at")
            or review.get("createdAt")
            or ""
        )
        # fmt: off
        try:
            review_id = int(review.get("id", index))
        except (TypeError, ValueError):
            review_id = index
        # fmt: on
        previous = effective.get(reviewer)
        if previous is None or (timestamp, review_id) >= (previous[0], previous[1]):
            effective[reviewer] = (timestamp, review_id, review)
    return [item[2] for item in sorted(effective.values(), key=lambda item: (item[0], item[1]))]


def validate_pull_request_review_contract(
    pull_request: Mapping[str, Any],
    reviews: Sequence[Mapping[str, Any]],
    issue_comments: Sequence[Mapping[str, Any]],
    review_threads: Sequence[Mapping[str, Any]],
    *,
    expected_head_sha: str | None = None,
    known_commit_shas: Sequence[str] | None = None,
    require_open: bool = True,
    require_mergeable: bool = True,
    allow_blocked_mergeable_state: bool = False,
) -> dict[str, Any]:
    """Require a completed review for the current PR head.

    GitHub formal approvals are authoritative when their ``commit_id`` is the current head.
    The Codex connector currently records its completed review as a trusted issue comment, so
    that representation is accepted only with an exact-head marker.  Abbreviated markers are
    accepted only when they resolve uniquely to the current head among the supplied PR commit
    SHAs.  Skipped bot comments, old-head reviews, unresolved threads and non-mergeable PRs never
    satisfy this gate.
    """

    head = pull_request.get("head", {})
    head_sha = str(head.get("sha", "")).lower()
    if not head_sha:
        raise TaskSessionError("PR review gate requires a current head SHA")
    if expected_head_sha and head_sha != expected_head_sha.lower():
        raise TaskSessionError(
            f"PR review gate received stale head {head_sha}; expected {expected_head_sha}"
        )
    state = str(pull_request.get("state", "")).lower()
    if require_open and state != "open":
        raise TaskSessionError(f"PR review gate requires an open PR, found {state}")
    if require_open and pull_request.get("draft") is True:
        raise TaskSessionError("PR review gate refuses a draft PR")
    if require_mergeable:
        if pull_request.get("mergeable") is not True:
            raise TaskSessionError("PR review gate requires an explicitly mergeable PR")
        mergeable_state = str(pull_request.get("mergeable_state", "")).lower()
        allowed_mergeable_states = {"clean", "has_hooks"}
        if allow_blocked_mergeable_state:
            # The review-event run is itself one of the required checks. GitHub can therefore
            # report ``blocked`` or ``unstable`` until the aggregate check containing this gate
            # succeeds. ``mergeable=True`` above still makes an actual merge conflict fail closed.
            allowed_mergeable_states.update({"blocked", "unstable"})
        if mergeable_state not in allowed_mergeable_states:
            raise TaskSessionError(
                "PR review gate requires a clean mergeable PR, found "
                f"{mergeable_state or '<missing>'}"
            )

    unresolved_threads = [
        index
        for index, thread in enumerate(review_threads, start=1)
        if thread.get("isResolved") is not True
    ]
    if unresolved_threads:
        raise TaskSessionError(
            "PR review gate refuses unresolved review threads: "
            + ", ".join(str(item) for item in unresolved_threads)
        )

    effective_reviews = _effective_current_head_reviews(
        reviews, head_sha, known_commit_shas=known_commit_shas
    )
    exact_approvals = [
        item for item in effective_reviews if str(item.get("state", "")).upper() == "APPROVED"
    ]
    current_changes = [
        item
        for item in effective_reviews
        if str(item.get("state", "")).upper() == "CHANGES_REQUESTED"
    ]
    if current_changes:
        findings = []
        for item in current_changes:
            body = _review_body(item)
            severities = []
            for raw in re.findall(r"(?i)\b(?:P[0-3]|BLOCKER|HIGH|MEDIUM|LOW|NIT)\b", body):
                try:
                    severities.append(normalize_severity(raw))
                except IssueWorkflowError:
                    continue
            findings.append(
                {
                    "review_id": item.get("id"),
                    "severity": severities or ["HIGH"],
                    "body_present": bool(body.strip()),
                }
            )
        raise TaskSessionError(
            "PR review gate found blocking current-head review findings: "
            + json.dumps(findings, ensure_ascii=False, sort_keys=True)
        )

    exact_codex_comments: list[Mapping[str, Any]] = []
    current_head_codex_comments: list[tuple[str, int, Mapping[str, Any]]] = []
    stale_codex_markers: list[str] = []
    rejected_codex_markers: list[str] = []
    for comment in issue_comments:
        if _review_login(comment) not in TRUSTED_REVIEW_LOGINS:
            continue
        body = _review_body(comment)
        lowered = body.casefold()
        if "review skipped" in lowered or "rate limit exceeded" in lowered:
            continue
        markers = reviewed_commit_markers(body)
        if not markers:
            continue
        exact_head = any(
            _marker_matches_head(marker, head_sha, known_commit_shas=known_commit_shas)
            for marker in markers
        )
        completed = any(marker in lowered for marker in REVIEW_COMPLETED_MARKERS)
        if exact_head and completed:
            timestamp = str(
                comment.get("updated_at")
                or comment.get("updatedAt")
                or comment.get("created_at")
                or comment.get("createdAt")
                or ""
            )
            # fmt: off
            try:
                comment_id = int(comment.get("id", 0))
            except (TypeError, ValueError):
                comment_id = 0
            # fmt: on
            current_head_codex_comments.append((timestamp, comment_id, comment))
        else:
            stale_codex_markers.extend(markers)

    if current_head_codex_comments:
        _, _, latest_codex_comment = max(
            current_head_codex_comments, key=lambda item: (item[0], item[1])
        )
        latest_codex_body = _review_body(latest_codex_comment)
        if _is_approving_codex_review(latest_codex_body):
            exact_codex_comments.append(latest_codex_comment)
        elif REVIEW_BLOCKING_MARKER_RE.search(latest_codex_body):
            rejected_codex_markers.extend(reviewed_commit_markers(latest_codex_body))

    if rejected_codex_markers:
        raise TaskSessionError(
            "PR review gate found blocking exact-head Codex verdict without an explicit "
            "approving verdict: " + ", ".join(sorted(set(rejected_codex_markers)))
        )

    if not exact_approvals and not exact_codex_comments:
        details = (
            f"; stale review markers: {', '.join(stale_codex_markers)}"
            if stale_codex_markers
            else ""
        )
        if rejected_codex_markers:
            details += (
                "; exact-head Codex review has no explicit approving verdict or contains "
                "blocking findings"
            )
        raise TaskSessionError(
            f"PR review gate has no completed approval for exact current head {head_sha}{details}"
        )

    sources: list[str] = []
    if exact_approvals:
        sources.append("github-formal-approval")
    if exact_codex_comments:
        sources.append("codex-completed-review-comment")
    return {
        "status": "PASS",
        "head_sha": head_sha,
        "reviewed_head_sha": head_sha,
        "sources": sources,
        "formal_approval_count": len(exact_approvals),
        "codex_review_comment_count": len(exact_codex_comments),
        "unresolved_thread_count": 0,
        "blocking_finding_count": 0,
        "severity_mapping": {
            "P0": "BLOCKER",
            "P1": "HIGH",
            "P2": "MEDIUM",
            "P3": "LOW",
            "NIT": "LOW",
        },
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
    task_id = task_id_from_branch(branch)
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
    if is_dependabot_pull_request(pull_request):
        base = pull_request.get("base", {})
        head = pull_request.get("head", {})
        base_repo = base.get("repo", {}).get("full_name")
        head_repo = head.get("repo", {}).get("full_name")
        if not base_repo or not head_repo or head_repo != base_repo:
            raise TaskSessionError(
                "Dependabot pull request must originate from the same repository"
            )
        head_sha = str(head.get("sha", ""))
        if not head_sha:
            raise TaskSessionError("Dependabot pull request head SHA is missing")
        return {"kind": "dependabot-pr", "head_sha": head_sha}
    event_base_sha = str(pull_request.get("base", {}).get("sha", ""))
    current_master_sha = github.branch_head(TARGET_BASE_BRANCH)
    if event_base_sha != current_master_sha:
        raise TaskSessionError(
            f"Task PR is stale: base {event_base_sha} != current {current_master_sha}"
        )
    number = int(pull_request["number"])
    commits = github.pull_request_commits(number)
    files = github.pull_request_files(number)
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


def validate_pr_review_event(
    github: GitHubClient,
    event_path: Path,
    *,
    pr_number: int | None = None,
    expected_head_sha: str | None = None,
) -> dict[str, Any]:
    event = json.loads(event_path.read_text(encoding="utf-8"))
    event_pull_request = event.get("pull_request")
    if not isinstance(event_pull_request, Mapping) and pr_number is None:
        raise TaskSessionError("Review gate event does not contain a pull request")
    number = pr_number or int(event_pull_request["number"])
    event_head_sha = (
        str(event_pull_request.get("head", {}).get("sha", ""))
        if isinstance(event_pull_request, Mapping)
        else ""
    )
    pull_request = _pull_request_with_resolved_mergeability(github, number)
    live_head_sha = str(pull_request.get("head", {}).get("sha", ""))
    if event_head_sha and event_head_sha != live_head_sha:
        raise TaskSessionError(
            f"Review gate event is stale: event head {event_head_sha} != live head {live_head_sha}"
        )
    if expected_head_sha and live_head_sha != expected_head_sha:
        raise TaskSessionError(
            f"Review gate head {live_head_sha} != expected current head {expected_head_sha}"
        )
    evidence = validate_pull_request_review_contract(
        pull_request,
        github.pull_request_reviews(number),
        github.issue_comments(number),
        github.review_threads(number),
        expected_head_sha=live_head_sha,
        known_commit_shas=_commit_shas(github.pull_request_commits(number)),
        allow_blocked_mergeable_state=True,
    )
    return {"kind": "pull-request-review", "pr_number": number, **evidence}


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
        is_task_merge = TASK_BRANCH_RE.fullmatch(str(head.get("ref", ""))) and str(
            pull_request.get("title", "")
        ).startswith("[Task ")
        base_repo = base.get("repo", {})
        head_repo = head.get("repo", {})
        is_same_repository = (
            isinstance(base_repo, Mapping)
            and isinstance(head_repo, Mapping)
            and bool(base_repo.get("full_name"))
            and head_repo.get("full_name") == base_repo.get("full_name")
        )
        is_dependabot_merge = is_dependabot_pull_request(pull_request) and is_same_repository
        if is_task_merge:
            merge_kind = "task-pr-merge"
        elif is_dependabot_merge:
            merge_kind = "dependabot-pr-merge"
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
            f"Master revision {sha} is not exactly one merged task PR result: found {len(matches)}"
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
        status = self.repository.status(root or self._canonical_root(), include_ignored=True)
        unexpected: list[str] = []
        for item in status:
            if not item.startswith("!! "):
                unexpected.append(item)
                continue
            ignored_path = item[3:].strip().replace("\\", "/").rstrip("/")
            path_parts = set(ignored_path.split("/"))
            if not (
                any(
                    ignored_path == managed or ignored_path.startswith(f"{managed}/")
                    for managed in CANONICAL_MANAGED_IGNORED_PATHS
                )
                or bool(path_parts & CANONICAL_MANAGED_IGNORED_BASENAMES)
            ):
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
                        result.add(match.group("task_id").upper())
        return result

    @staticmethod
    def _lease_state(lease: Mapping[str, Any]) -> str:
        return str(lease.get("lifecycle_state", "")).strip().lower()

    @classmethod
    def _is_active_write_lease(cls, lease: Mapping[str, Any]) -> bool:
        return lease.get("mode") == "write" and cls._lease_state(lease) not in TERMINAL_LEASE_STATES

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
        if lease.get("mode") != "write":
            return False
        state = cls._lease_state(lease)
        if state not in IMPLEMENTATION_STATES | RECOVERY_STATES:
            return False
        return cls._validated_lease_concurrency_class(lease) == "exclusive-write"

    @classmethod
    def _validate_lease_concurrency_classes(cls, leases: Sequence[Mapping[str, Any]]) -> None:
        for lease in leases:
            if lease.get("mode") == "write":
                cls._validated_lease_concurrency_class(lease)

    @classmethod
    def _lease_ownership_snapshot(
        cls, lease: Mapping[str, Any], *, delivery_owner_id: str
    ) -> dict[str, bool]:
        task_session_active = lease.get("mode") == "write"
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
        candidate_class = normalize_concurrency_class(concurrency_class)
        conflicts: list[dict[str, Any]] = []
        for lease in leases:
            if lease.get("mode") != "write":
                continue
            if str(lease.get("task_id", "")).upper() == task_id.upper():
                continue
            existing_class = cls._validated_lease_concurrency_class(lease)
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
            existing_holds_exclusion = (
                state in IMPLEMENTATION_STATES and existing_class == "exclusive-write"
            )
            candidate_requires_exclusion = candidate_class == "exclusive-write" and (
                state in IMPLEMENTATION_STATES
            )
            if existing_holds_exclusion or candidate_requires_exclusion:
                conflicts.append(
                    {
                        "task_id": str(lease.get("task_id", "")).upper(),
                        "concurrency_class": existing_class,
                        "lifecycle_state": state,
                    }
                )
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
        active_task_ids = {item.get("task_id") for item in leases if item.get("mode") == "write"}
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
                    implementation_blockers.append(
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
                "exclusive-write is reserved for global/coordination-sensitive scope. Only an "
                "exclusive lease in starting/implementation/review/qa (or unresolved recovery) "
                "holds implementation exclusion; readiness, waiting, CI and production do not.\n"
                "Normal path: targeted checks/self-review/QA/commit -> READY_FOR_DELIVERY -> acquire delivery\n"
                "-> refresh-delivery task branch -> local PRE_PUSH_CI_PASS -> PR master -> production.\n"
                "Implementation may run in parallel with compatible tasks. Do not start another task\n"
                "from this worker. READY_FOR_DELIVERY may wait for the single delivery lane; before\n"
                "PR/merge refresh onto latest origin/master and rerun the final exact-HEAD gate.\n"
                "Do not merge or push master directly.\n"
                f"Recovery: python scripts/task_session.py recover {expected}\n"
            ),
        }

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
            if self._lease_state(lease) in TERMINAL_LEASE_STATES:
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

    @staticmethod
    def _gate_evidence_path(canonical_root: Path, task_id: str) -> Path:
        return (
            canonical_root
            / ".artifacts"
            / "tasks"
            / normalize_task_id(task_id)
            / "evidence"
            / "pre-push"
            / "gate.json"
        )

    def _current_gate_evidence(
        self, task_id: str, lease: Mapping[str, Any], head_sha: str
    ) -> dict[str, Any]:
        path = self._gate_evidence_path(self._canonical_root(), task_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise TaskSessionError(
                f"Current PRE_PUSH_CI_PASS evidence is missing or invalid: {path}"
            ) from error
        if not isinstance(payload, dict):
            raise TaskSessionError(f"Invalid pre-push evidence payload: {path}")
        if payload.get("evidence_version") != 1:
            raise TaskSessionError("Pre-push evidence version is invalid")
        if payload.get("terminal_result") != "PRE_PUSH_CI_PASS":
            raise TaskSessionError("Readiness requires terminal PRE_PUSH_CI_PASS")
        expected = {
            "task_id": task_id,
            "branch": lease.get("branch"),
            "head_sha": head_sha,
            "base_sha": lease.get("base_origin_master_sha"),
            "target_base_branch": TARGET_BASE_BRANCH,
        }
        for key, value in expected.items():
            if payload.get(key) != value:
                raise TaskSessionError(f"Pre-push evidence {key} does not match current lease/HEAD")
        delivery_generation = lease.get("delivery_generation")
        if (
            delivery_generation is not None
            and payload.get("delivery_generation") != delivery_generation
        ):
            raise TaskSessionError(
                "Pre-push evidence belongs to an earlier delivery refresh generation"
            )
        try:
            from scripts.ci_contract import CONTRACT_VERSION, contract_digest
        except ModuleNotFoundError:
            from ci_contract import CONTRACT_VERSION, contract_digest
        if payload.get("contract_version") != CONTRACT_VERSION:
            raise TaskSessionError("Pre-push evidence contract version is stale")
        if payload.get("contract_digest") != contract_digest():
            raise TaskSessionError("Pre-push evidence contract digest is stale")
        if payload.get("clean_worktree") is not True:
            raise TaskSessionError("Pre-push evidence does not prove a clean worktree")
        gates = payload.get("gates")
        if not isinstance(gates, list) or any(
            not isinstance(gate, dict)
            or gate.get("applicable") is not True
            or gate.get("status") != "SUCCESS"
            for gate in gates
        ):
            raise TaskSessionError("Pre-push evidence does not contain successful applicable gates")
        unsigned_payload = dict(payload)
        evidence_digest = unsigned_payload.pop("evidence_digest", None)
        encoded = json.dumps(
            unsigned_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        if (
            not isinstance(evidence_digest, str)
            or evidence_digest != hashlib.sha256(encoded).hexdigest()
        ):
            raise TaskSessionError("Pre-push evidence digest is invalid")
        worktree = Path(str(lease["worktree"]))
        if self.repository.status(worktree):
            raise TaskSessionError("Task worktree is dirty; PRE_PUSH_CI_PASS is stale")
        return payload

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
        gate: dict[str, Any] | None = None
        gate_issue: str | None = None
        try:
            gate = self._current_gate_evidence(expected, lease, head_sha)
        except TaskSessionError as error:
            # PRE_PUSH_CI_PASS is a final delivery gate.  Implementation can reach the
            # durable queue with targeted checks and applicable QA evidence only.
            gate_issue = str(error)
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
            local_evidence = {
                "status": "valid-for-current-head"
                if gate is not None
                else "pending-final-delivery-gate",
                "pre_push_ci_pass": gate,
            }
            if gate_issue:
                local_evidence["invalidated_reason"] = gate_issue
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
                    "local_evidence": local_evidence,
                    "pre_push_ci_pass": gate,
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
            delivery_generation = uuid.uuid4().hex
            current.update(
                {
                    "base_origin_master_sha": current_base,
                    "delivery_base_origin_master_sha": current_base,
                    "delivery_head_sha": head_after,
                    "ready_head_sha": head_after,
                    "ready_base_origin_master_sha": current_base,
                    "delivery_generation": delivery_generation,
                    "task_provenance": {
                        "task_id": expected,
                        "branch": current.get("branch"),
                        "base_sha": current_base,
                        "head_sha": head_after,
                        "original_base_sha": current.get("original_base_origin_master_sha"),
                    },
                    "pre_push_ci_pass": None,
                    "local_evidence": {
                        "status": "invalidated-after-master-refresh",
                        "invalidated_at": now,
                        "previous_head_sha": head_before,
                        "previous_base_sha": old_base,
                    },
                    "delivery_gate_pass": None,
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
                    "Task delivery ownership changed during final gate validation"
                )
            current_head = self.repository.head(cwd=worktree)
            if current.get("base_origin_master_sha") != base_sha:
                raise TaskSessionError("Task delivery base changed during final gate validation")
            if current.get("delivery_head_sha") != current_head or current_head != head_sha:
                raise TaskSessionError("Task delivery HEAD changed during final gate validation")
            gate = self._current_gate_evidence(expected, current, current_head)
            current.update(
                {
                    "lifecycle_state": "delivery-gate",
                    "delivery_gate_pass": gate,
                    "pre_push_ci_pass": gate,
                    "local_evidence": {
                        "status": "valid-for-current-head",
                        "pre_push_ci_pass": gate,
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
                "delivery_generation",
                "delivery_gate_pass",
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
                    "pre_push_ci_pass": None,
                    "local_evidence": {
                        "status": "invalidated-before-review-reopen",
                        "invalidated_at": now,
                        "reason": reason,
                    },
                    "updated_at": now,
                }
            )
            delivery["owner"] = None
            delivery.pop("priority_override", None)
            delivery["updated_at"] = now
            StateStore.replace_json(lease_path, current)
            StateStore.replace_json(self.store.delivery_path, delivery)
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
                "delivery_generation",
                "delivery_gate_pass",
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
                    "pre_push_ci_pass": None,
                    "local_evidence": {
                        "status": "invalidated-before-recovery-resolution",
                        "invalidated_at": now,
                        "reason": reason,
                    },
                    "updated_at": now,
                }
            )
            current_delivery["owner"] = None
            current_delivery["updated_at"] = now
            StateStore.replace_json(lease_path, current)
            StateStore.replace_json(self.store.delivery_path, current_delivery)
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
        self._current_gate_evidence(expected, lease, head_sha)
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
            current_gate = self._current_gate_evidence(expected, current, head_sha)
            if current.get("delivery_gate_pass") != current_gate:
                raise TaskSessionError(
                    "Delivery gate evidence changed before production completion"
                )
            if "queue_budget" in current:
                history["queue_budget"] = current["queue_budget"]
            if "delivery_priority_override" in current:
                history["delivery_priority_override"] = current["delivery_priority_override"]
            history_path = self.store.history / f"task-{expected}.json"
            if history_path.exists():
                raise TaskSessionError(
                    f"Production success history already exists for Task {expected}"
                )
            now = utc_now()
            current["lifecycle_state"] = "production-success"
            current["merge_sha"] = merge_sha
            current["deployed_sha"] = deployed_sha
            current["updated_at"] = now
            StateStore.replace_json(lease_path, current)
            history["closeout_required"] = True
            self.store.create_json(history_path, history)
        return history

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
        if self.repository.current_worktree != root:
            raise TaskSessionError("finish cleanup must run from the canonical repository worktree")
        if self.repository.ref("origin/master") != deployed_sha:
            raise TaskSessionError("finish requires current origin/master at deployed SHA")
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
        if branches != [branch] or len(matches) != 1 or matches[0].branch != branch:
            raise TaskSessionError(
                "finish cleanup requires exactly one matching task branch/worktree"
            )
        if self.repository.ref(branch) != expected_head or matches[0].head != expected_head:
            raise TaskSessionError("finish cleanup branch/worktree head changed after readiness")
        if self.repository.status(worktree_path):
            raise TaskSessionError(f"finish cleanup refuses dirty task worktree {worktree_path}")
        operations = self.repository.operation_issues(worktree_path)
        if operations:
            raise TaskSessionError(
                f"finish cleanup refuses interrupted Git operation: {operations}"
            )
        if not self.repository.is_ancestor(expected_head, deployed_sha):
            raise TaskSessionError("finish cleanup refuses task head absent from deployed master")
        if self.repository.unique_commits(branch):
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
        self.repository.remove_worktree(worktree_path)
        if self.repository.ref(branch) != expected_head:
            raise TaskSessionError("finish cleanup branch changed after worktree removal")
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
            history["cleanup"] = {"worktree": str(worktree_path), "branch": branch}
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
    history = store.read_json(store.history / f"task-{normalize_task_id(task_id)}.json")
    if history is None or history.get("state") != "finished":
        raise TaskSessionError(
            f"Task {task_id} cannot be archived before controller finish and terminal production success"
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
    resolve_recovery = subparsers.add_parser("resolve-recovery")
    resolve_recovery.add_argument("task_id")
    resolve_recovery.add_argument("--reason", required=True)
    resolve_recovery.add_argument("--owner-authorize", action="store_true")
    queue_cycle = subparsers.add_parser("record-queue-cycle")
    queue_cycle.add_argument("task_id")
    queue_cycle.add_argument("--kind", choices=("review", "ci"), required=True)
    queue_cycle.add_argument("--reason", required=True)
    production = subparsers.add_parser("complete-production")
    production.add_argument("task_id")
    production.add_argument("--pr", type=int, required=True)
    production.add_argument("--merge-sha", required=True)
    production.add_argument("--deployed-sha", required=True)
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
        if args.command == "resolve-recovery":
            _print(
                controller.resolve_recovery(
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
