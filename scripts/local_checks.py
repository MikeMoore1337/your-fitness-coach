"""Run optional local CI checks with one reproducible child-process environment."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

try:
    from scripts import ci_contract
except ModuleNotFoundError:
    import ci_contract


FAST_GROUPS_BY_PROFILE: dict[str, tuple[str, ...]] = {
    "frontend": ("quality", "frontend-checks"),
    "backend": ("quality", "python-tests"),
    "migration": ("quality", "migrated-stack"),
    "workflow-platform": ("quality", "workflow-config", "deployment-contract"),
    "documentation": ("quality", "workflow-config"),
    "cross-stack": ("quality", "workflow-config", "deployment-contract"),
}
LOCAL_APP_DEFAULTS: dict[str, str] = {
    "APP_NAME": "Your Fitness Coach local checks",
    "APP_DEBUG": "false",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "60",
    "REFRESH_TOKEN_EXPIRE_DAYS": "30",
    "ENABLE_DEV_AUTH": "true",
    "TELEGRAM_BOT_TOKEN": "local-test-token",
    "BOT_INTERNAL_TOKEN": "local-test-token",
    "SECRET_KEY": "local-test-secret-key-at-least-thirty-two-characters",
    "FRONTEND_BASE_URL": "http://127.0.0.1:5173",
}


class LocalChecksError(RuntimeError):
    """The local check environment or route cannot be prepared safely."""


def _git(root: Path, *args: str) -> str:
    command = ["git", "-c", f"safe.directory={root.resolve().as_posix()}", *args]
    completed = subprocess.run(
        command,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown Git error"
        raise LocalChecksError(f"Git command failed: {detail}")
    return completed.stdout.strip()


def repository_root(start: Path | None = None) -> Path:
    """Resolve the actual Git worktree instead of relying on the caller's cwd."""

    candidate = (start or Path.cwd()).resolve()
    try:
        output = _git(candidate, "rev-parse", "--show-toplevel")
    except (LocalChecksError, OSError) as error:
        raise LocalChecksError(f"Cannot resolve a Git worktree from {candidate}") from error
    if not output:
        raise LocalChecksError(f"Git returned an empty worktree root for {candidate}")
    root = Path(output).resolve()
    if not (root / ".git").exists():
        raise LocalChecksError(f"Resolved path is not a Git worktree: {root}")
    return root


def child_environment(
    root: Path,
    *,
    base: Mapping[str, str] | None = None,
    runtime_tmp: Path | None = None,
) -> dict[str, str]:
    """Build one safe environment shared by every child check in this invocation."""

    environment = dict(os.environ if base is None else base)
    if environment.get("APP_ENV", "").casefold() in {"prod", "production"}:
        raise LocalChecksError("local checks refuse APP_ENV=prod; use an isolated test environment")
    python_bin = Path(sys.executable).resolve().parent
    path_entries = [str(python_bin)]
    frontend_bin = root / "frontend" / "node_modules" / ".bin"
    if frontend_bin.is_dir():
        path_entries.append(str(frontend_bin))
    if environment.get("PATH"):
        path_entries.append(environment["PATH"])
    environment["PATH"] = os.pathsep.join(path_entries)

    python_paths = [str(root / "backend"), str(root / "bot")]
    if environment.get("PYTHONPATH"):
        python_paths.append(environment["PYTHONPATH"])
    environment["PYTHONPATH"] = os.pathsep.join(python_paths)
    environment["CI"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["APP_ENV"] = "test"
    environment["YFC_PROCESS_TMP"] = tempfile.gettempdir()
    for key, value in LOCAL_APP_DEFAULTS.items():
        environment[key] = value

    runtime_parent = root / ".artifacts" / "runtime" / "tmp" / "local-checks"
    runtime_parent.mkdir(parents=True, exist_ok=True)
    if runtime_tmp is None:
        runtime_tmp = Path(tempfile.mkdtemp(prefix="run-", dir=runtime_parent))
    else:
        runtime_tmp = runtime_tmp.resolve()
        if not runtime_tmp.is_relative_to(runtime_parent.resolve()):
            raise LocalChecksError("local runtime directory must stay under .artifacts/runtime/tmp")
    runtime_tmp.mkdir(parents=True, exist_ok=True)
    test_database_url = environment.get("TEST_DATABASE_URL")
    if not test_database_url:
        test_database_url = f"sqlite:///{(runtime_tmp / 'test.db').as_posix()}"
        environment["TEST_DATABASE_URL"] = test_database_url
    environment["DATABASE_URL"] = test_database_url
    for key in ("TMP", "TEMP", "TMPDIR"):
        environment[key] = str(runtime_tmp)
    return environment


def _working_tree_paths(root: Path, base_sha: str) -> list[str]:
    tracked = _git(root, "diff", "--name-only", base_sha).splitlines()
    untracked = _git(root, "ls-files", "--others", "--exclude-standard").splitlines()
    return list(dict.fromkeys([*tracked, *untracked]))


def _current_route(root: Path) -> dict[str, object]:
    base_sha = _git(root, "rev-parse", "origin/master")
    head_sha = _git(root, "rev-parse", "HEAD")
    paths = _working_tree_paths(root, base_sha)
    if paths:
        decision = ci_contract.classify_scope(paths)
        decision["base_sha"] = base_sha
        decision["head_sha"] = head_sha
        return decision
    return ci_contract.route_repository(
        root,
        event="pull_request",
        base_sha=base_sha,
        head_sha=head_sha,
    )


def selected_groups(
    root: Path,
    *,
    requested: Sequence[str] | None = None,
    full: bool = False,
    route: Mapping[str, object] | None = None,
) -> tuple[str, ...]:
    """Select fast local groups or the voluntary full route without changing state."""

    if requested and full:
        raise LocalChecksError("Use --group or --full, not both")
    if requested:
        groups = tuple(dict.fromkeys(requested))
    else:
        decision = route or _current_route(root)
        profile = str(decision["profile"])
        required_groups = decision.get("required_groups")
        if not isinstance(required_groups, Sequence) or isinstance(required_groups, str):
            raise LocalChecksError("CI route has no valid required group list")
        groups = (
            tuple(str(group) for group in required_groups)
            if full
            else FAST_GROUPS_BY_PROFILE[profile]
        )
    unknown = sorted(set(groups) - set(ci_contract.COMMAND_GROUPS))
    if unknown:
        raise LocalChecksError(f"Unknown local check groups: {unknown}")
    return groups


def _print_plan(root: Path, groups: Sequence[str], route: Mapping[str, object] | None) -> None:
    branch = _git(root, "branch", "--show-current") or "(detached HEAD)"
    head = _git(root, "rev-parse", "HEAD")
    base = _git(root, "rev-parse", "origin/master")
    profile = str(route["profile"]) if route is not None else "explicit"
    print(
        "LOCAL_CHECKS "
        f"root={root} branch={branch} head={head} base={base} "
        f"python={Path(sys.executable).resolve()} profile={profile} "
        f"groups={','.join(groups)}",
        flush=True,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, help="Git worktree or subdirectory")
    parser.add_argument(
        "--group",
        action="append",
        choices=sorted(ci_contract.COMMAND_GROUPS),
        help="Run an explicit CI contract group; repeat for several groups",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run the complete GitHub route as voluntary local diagnostics",
    )
    parser.add_argument("--plan", action="store_true", help="Print the route without running it")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        ci_contract.validate_contract()
        root = repository_root(args.repo)
        route = None if args.group else _current_route(root)
        groups = selected_groups(root, requested=args.group, full=args.full, route=route)
        runtime_parent = root / ".artifacts" / "runtime" / "tmp" / "local-checks"
        runtime_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="run-", dir=runtime_parent) as runtime_dir:
            environment = child_environment(root, runtime_tmp=Path(runtime_dir))
            _print_plan(root, groups, route)
            if args.plan:
                return 0
            for group in groups:
                ci_contract.run_group(group, root=root, env=environment, local=True)
            print(f"LOCAL_CHECKS_PASS groups={','.join(groups)}", flush=True)
            return 0
    except (LocalChecksError, ci_contract.CIContractError, OSError) as error:
        print(f"local checks error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
