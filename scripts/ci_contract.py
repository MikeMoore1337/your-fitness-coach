"""Authoritative command groups shared by GitHub CI and the local pre-push gate.

The workflow files deliberately invoke group IDs instead of carrying a second,
hand-maintained copy of the repository's quality commands.  The same registry is
also used to calculate the contract digest stored in exact-HEAD gate evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

if __package__:
    from scripts.scheduled_regression import (
        profile_for_run_kind,
        report_suites,
        resolve_run_kind,
    )
else:
    from scheduled_regression import profile_for_run_kind, report_suites, resolve_run_kind

CONTRACT_VERSION = "ci-contract-v2"
ROUTER_VERSION = "ci-router-v2"
CI_SHARD_COUNT = 4
SHARDABLE_GROUPS = frozenset({"frontend-e2e", "python-tests"})
SHARD_RE = re.compile(r"(?P<number>[1-9][0-9]*)/(?P<count>[1-9][0-9]*)\Z")


class CIContractError(RuntimeError):
    """The shared CI contract cannot be executed safely."""


@dataclass(frozen=True)
class CommandSpec:
    """One reproducible command from the CI contract."""

    name: str
    argv: tuple[str, ...]
    cwd: str = "."
    retry_on_transient: bool = False
    retry_max_attempts: int = 1
    retry_delays_seconds: tuple[int, ...] = ()


@dataclass(frozen=True)
class GroupSpec:
    """A named command group and its required local prerequisites."""

    name: str
    commands: tuple[CommandSpec, ...]
    prerequisites: tuple[str, ...] = ()


def _cmd(
    name: str,
    *argv: str,
    cwd: str = ".",
    retry_on_transient: bool = False,
    retry_max_attempts: int = 1,
    retry_delays_seconds: tuple[int, ...] = (),
) -> CommandSpec:
    return CommandSpec(
        name=name,
        argv=argv,
        cwd=cwd,
        retry_on_transient=retry_on_transient,
        retry_max_attempts=retry_max_attempts,
        retry_delays_seconds=retry_delays_seconds,
    )


COMMAND_GROUPS: dict[str, GroupSpec] = {
    "quality": GroupSpec(
        name="quality",
        commands=(
            _cmd(
                "pre-commit",
                "python",
                "-m",
                "pre_commit",
                "run",
                "--all-files",
                "--show-diff-on-failure",
            ),
        ),
        prerequisites=("python", "pre_commit"),
    ),
    "frontend-checks": GroupSpec(
        name="frontend-checks",
        commands=(
            _cmd("generated-api-types", "npm", "run", "api:types", cwd="frontend"),
            _cmd(
                "generated-api-types-clean",
                "git",
                "diff",
                "--exit-code",
                "--",
                "frontend/src/shared/api/schema.d.ts",
            ),
            _cmd("frontend-typecheck", "npm", "run", "typecheck", cwd="frontend"),
            _cmd("frontend-lint", "npm", "run", "lint", cwd="frontend"),
            _cmd(
                "frontend-format",
                "npx",
                "prettier",
                "--check",
                ".",
                "--end-of-line",
                "auto",
                cwd="frontend",
            ),
            _cmd("frontend-unit", "npm", "run", "test", cwd="frontend"),
            _cmd("frontend-build", "npx", "vite", "build", cwd="frontend"),
        ),
        prerequisites=("npm", "frontend/node_modules"),
    ),
    "frontend-e2e": GroupSpec(
        name="frontend-e2e",
        commands=(_cmd("frontend-e2e", "npm", "run", "e2e:ci", cwd="frontend"),),
        prerequisites=("npm", "frontend/node_modules", "frontend/playwright.config.ts"),
    ),
    "frontend-mobile-regression": GroupSpec(
        name="frontend-mobile-regression",
        commands=(
            _cmd(
                "frontend-mobile-regression",
                "npm",
                "run",
                "e2e:mobile-regression",
                cwd="frontend",
            ),
        ),
        prerequisites=(
            "npm",
            "frontend/node_modules",
            "frontend/playwright.mobile-regression.config.ts",
        ),
    ),
    "frontend-mobile-regression-extended": GroupSpec(
        name="frontend-mobile-regression-extended",
        commands=(
            _cmd(
                "frontend-mobile-regression-extended",
                "npm",
                "run",
                "e2e:mobile-regression:extended",
                cwd="frontend",
            ),
        ),
        prerequisites=(
            "npm",
            "frontend/node_modules",
            "frontend/playwright.mobile-regression.extended.config.ts",
        ),
    ),
    "frontend-cross-browser": GroupSpec(
        name="frontend-cross-browser",
        commands=(
            _cmd("frontend-cross-browser", "npm", "run", "e2e:cross-browser", cwd="frontend"),
        ),
        prerequisites=(
            "npm",
            "frontend/node_modules",
            "frontend/playwright.cross-browser.config.ts",
        ),
    ),
    "python-tests": GroupSpec(
        name="python-tests",
        commands=(
            _cmd("python-dependency-consistency", "python", "-m", "pip", "check"),
            _cmd(
                "python-suite",
                "python",
                "scripts/run_pytest.py",
                "backend/tests",
                "bot/tests",
                "-q",
                "-n",
                "4",
                "--dist=worksteal",
                "--durations=20",
            ),
        ),
        prerequisites=("python", "TEST_DATABASE_URL"),
    ),
    "migrated-stack": GroupSpec(
        name="migrated-stack",
        commands=(
            _cmd("migrations-upgrade", "python", "-m", "alembic", "upgrade", "head", cwd="backend"),
            _cmd("migrations-check", "python", "-m", "alembic", "check", cwd="backend"),
            _cmd(
                "migrated-api-smoke",
                "python",
                "scripts/run_pytest.py",
                "tests/integration/test_migrated_stack.py",
                "-q",
            ),
            _cmd("migrated-browser-smoke", "npm", "run", "e2e:migrated-stack", cwd="frontend"),
        ),
        prerequisites=("python", "alembic", "npm", "frontend/node_modules", "DATABASE_URL"),
    ),
    "dependency-audit": GroupSpec(
        name="dependency-audit",
        commands=(
            _cmd(
                "frontend-dependency-audit",
                "npm",
                "audit",
                "--omit=dev",
                "--audit-level=high",
                cwd="frontend",
                retry_on_transient=True,
                retry_max_attempts=3,
                retry_delays_seconds=(2, 10),
            ),
            _cmd(
                "backend-dependency-audit",
                "uvx",
                "--from",
                "pip-audit==2.10.1",
                "pip-audit",
                "-r",
                "backend/requirements-runtime.txt",
                retry_on_transient=True,
                retry_max_attempts=3,
                retry_delays_seconds=(2, 10),
            ),
            _cmd(
                "bot-dependency-audit",
                "uvx",
                "--from",
                "pip-audit==2.10.1",
                "pip-audit",
                "-r",
                "bot/requirements.txt",
                retry_on_transient=True,
                retry_max_attempts=3,
                retry_delays_seconds=(2, 10),
            ),
        ),
        prerequisites=("npm", "uvx"),
    ),
    "frontend-dependency-audit": GroupSpec(
        name="frontend-dependency-audit",
        commands=(
            _cmd(
                "frontend-dependency-audit",
                "npm",
                "audit",
                "--omit=dev",
                "--audit-level=high",
                cwd="frontend",
                retry_on_transient=True,
                retry_max_attempts=3,
                retry_delays_seconds=(2, 10),
            ),
        ),
        prerequisites=("npm",),
    ),
    "python-dependency-audit": GroupSpec(
        name="python-dependency-audit",
        commands=(
            _cmd(
                "backend-dependency-audit",
                "uvx",
                "--from",
                "pip-audit==2.10.1",
                "pip-audit",
                "-r",
                "backend/requirements-runtime.txt",
                retry_on_transient=True,
                retry_max_attempts=3,
                retry_delays_seconds=(2, 10),
            ),
            _cmd(
                "bot-dependency-audit",
                "uvx",
                "--from",
                "pip-audit==2.10.1",
                "pip-audit",
                "-r",
                "bot/requirements.txt",
                retry_on_transient=True,
                retry_max_attempts=3,
                retry_delays_seconds=(2, 10),
            ),
        ),
        prerequisites=("uvx",),
    ),
    "policy": GroupSpec(
        name="policy",
        commands=(
            _cmd(
                "policy-tests",
                "python",
                "-m",
                "pytest",
                "tests/test_release_safeguards.py",
                "tests/test_task_session.py",
                "tests/test_pre_push_gate.py",
                "tests/test_ci_contract.py",
                "tests/test_ci_timing.py",
                "tests/test_run_task_delivery.py",
                "tests/test_scheduled_regression.py",
                "tests/test_deployment_contract.py",
                "tests/test_online_migrations.py",
                "tests/test_zero_downtime_deploy.py",
                "-q",
            ),
        ),
        prerequisites=("python",),
    ),
    "workflow-config": GroupSpec(
        name="workflow-config",
        commands=(_cmd("validate-contract", "python", "scripts/ci_contract.py", "validate"),),
        prerequisites=("python",),
    ),
    "image-contract": GroupSpec(
        name="image-contract",
        commands=(
            _cmd(
                "image-contract",
                "python",
                "scripts/deployment_contract.py",
                "check",
                "--ci-workflow",
                ".github/workflows/ci.yml",
                "--deploy-workflow",
                ".github/workflows/deploy.yml",
                "--compose",
                "docker-compose.yml",
            ),
        ),
        prerequisites=("python",),
    ),
    "deployment-contract": GroupSpec(
        name="deployment-contract",
        commands=(
            _cmd(
                "deployment-contract",
                "python",
                "scripts/deployment_contract.py",
                "check",
                "--ci-workflow",
                ".github/workflows/ci.yml",
                "--deploy-workflow",
                ".github/workflows/deploy.yml",
                "--compose",
                "docker-compose.yml",
                "--deploy-script",
                "scripts/deploy_production.sh",
            ),
        ),
        prerequisites=("python",),
    ),
    "container-contract": GroupSpec(
        name="container-contract",
        commands=(
            _cmd(
                "container-contract",
                "python",
                "scripts/deployment_contract.py",
                "check",
                "--ci-workflow",
                ".github/workflows/ci.yml",
                "--deploy-workflow",
                ".github/workflows/deploy.yml",
                "--compose",
                "docker-compose.yml",
            ),
        ),
        prerequisites=("python",),
    ),
    "critical-smoke": GroupSpec(
        name="critical-smoke",
        commands=(
            _cmd(
                "application-import-smoke",
                "python",
                "-c",
                "import os, sys; sys.path.extend(['backend', 'bot']); os.environ.update({'APP_ENV': 'test', 'APP_NAME': 'Your Fitness Coach CI', 'APP_DEBUG': 'false', 'ACCESS_TOKEN_EXPIRE_MINUTES': '60', 'REFRESH_TOKEN_EXPIRE_DAYS': '30', 'DATABASE_URL': 'postgresql+psycopg://fitminiapp:test-password@127.0.0.1:5432/fitminiapp_test', 'ENABLE_DEV_AUTH': 'true', 'TELEGRAM_BOT_TOKEN': 'test-token', 'BOT_INTERNAL_TOKEN': 'test-bot-internal-token', 'SECRET_KEY': 'test-secret-key-at-least-thirty-two-characters'}); from fitminiapp_api.main import app; from fitminiapp_bot.bot import dp; assert app.title and dp is not None",
            ),
        ),
        prerequisites=("python",),
    ),
}


PROFILE_GROUPS: dict[str, tuple[str, ...]] = {
    "frontend": (
        "quality",
        "frontend-checks",
        "frontend-e2e",
        "frontend-mobile-regression",
        "critical-smoke",
    ),
    "backend": ("quality", "python-tests", "critical-smoke"),
    "migration": (
        "quality",
        "policy",
        "python-tests",
        "migrated-stack",
        "critical-smoke",
        "workflow-config",
        "deployment-contract",
    ),
    "cross-stack": (
        "quality",
        "frontend-checks",
        "frontend-e2e",
        "frontend-mobile-regression",
        "python-tests",
        "migrated-stack",
        "dependency-audit",
        "critical-smoke",
        "policy",
        "workflow-config",
        "image-contract",
        "deployment-contract",
        "container-contract",
    ),
    "workflow-platform": (
        "quality",
        "policy",
        "workflow-config",
        "image-contract",
        "deployment-contract",
    ),
    "documentation": ("quality", "workflow-config"),
}

PROFILE_GROUPS["daily-regression"] = (
    "quality",
    "frontend-checks",
    "frontend-e2e",
    "frontend-mobile-regression",
    "python-tests",
    "migrated-stack",
    "critical-smoke",
    "workflow-config",
)
PROFILE_GROUPS["weekly-exhaustive"] = (
    *PROFILE_GROUPS["daily-regression"],
    "policy",
    "dependency-audit",
    "frontend-mobile-regression-extended",
    "frontend-cross-browser",
    "image-contract",
    "deployment-contract",
    "container-contract",
)


GROUP_TO_JOB: dict[str, str] = {
    "quality": "quality",
    "policy": "policy",
    "frontend-checks": "frontend",
    "frontend-e2e": "frontend-smoke",
    "frontend-mobile-regression": "frontend-mobile-regression",
    "frontend-mobile-regression-extended": "frontend-mobile-regression-extended",
    "frontend-cross-browser": "frontend-cross-browser",
    "python-tests": "python-tests",
    "migrated-stack": "migrated-stack",
    "dependency-audit": "dependency-audit",
    "frontend-dependency-audit": "dependency-audit",
    "python-dependency-audit": "dependency-audit",
    "container-contract": "containers",
    "critical-smoke": "critical-smoke",
    "workflow-config": "workflow-contracts",
    "image-contract": "workflow-contracts",
    "deployment-contract": "workflow-contracts",
}

ROUTER_JOB_NAMES: tuple[str, ...] = (
    "scope-router",
    "task-provenance",
    "review-contract",
    "quality",
    "policy",
    "frontend",
    "frontend-smoke",
    "frontend-mobile-regression",
    "frontend-mobile-regression-extended",
    "frontend-cross-browser",
    "python-tests",
    "migrated-stack",
    "dependency-audit",
    "containers",
    "critical-smoke",
    "workflow-contracts",
    "merge-provenance",
    "scheduled-report",
)

ROUTER_OUTPUTS: dict[str, str] = {
    "quality": "run_quality",
    "policy": "run_policy",
    "frontend": "run_frontend",
    "frontend-smoke": "run_frontend_smoke",
    "frontend-mobile-regression": "run_frontend_mobile_regression",
    "frontend-mobile-regression-extended": "run_frontend_mobile_regression_extended",
    "frontend-cross-browser": "run_frontend_cross_browser",
    "python-tests": "run_python",
    "migrated-stack": "run_migrated_stack",
    "dependency-audit": "run_dependency_audit",
    "containers": "run_containers",
    "critical-smoke": "run_critical_smoke",
    "workflow-contracts": "run_workflow_contracts",
    "merge-provenance": "run_merge_provenance",
    "scheduled-report": "run_scheduled_report",
}

ROUTER_GROUP_OUTPUTS: dict[str, str] = {
    "workflow-config": "run_workflow_config",
    "image-contract": "run_image_contract",
    "deployment-contract": "run_deployment_contract",
}

_DOCUMENTATION_POLICY_PATHS = frozenset(
    {"AGENTS.md", "codex-backlog/GLOBAL_RULES.md", "codex-backlog/TASK_EXECUTION_LIFECYCLE.md"}
)
_FRONTEND_DEPENDENCY_PATHS = frozenset({"frontend/package.json", "frontend/package-lock.json"})
_PYTHON_DEPENDENCY_FILENAMES = frozenset(
    {"requirements.txt", "requirements-runtime.txt", "requirements-dev.txt", "uv.lock"}
)
_WORKFLOW_FILENAMES = frozenset(
    {
        "Dockerfile",
        ".dockerignore",
        "docker-compose.yml",
        "docker-compose.yaml",
        "Caddyfile",
        ".trivyignore.yaml",
    }
)
_API_PREFIXES = (
    "frontend/src/shared/api/",
    "backend/fitminiapp_api/api/",
    "backend/fitminiapp_api/schemas/",
)
_API_TOKENS = ("openapi", "auth", "session", "cookie", "telegram")
_SHARED_CI_CONTRACT_PATHS = frozenset({"scripts/ci_contract.py"})
_CONTAINER_SECURITY_PATHS = frozenset({".trivyignore.yaml"})
_MIGRATION_PREFIXES = (
    "backend/alembic/",
    "backend/fitminiapp_api/db/",
    "backend/fitminiapp_api/models/",
)
_ALL_ROUTABLE_GROUPS = tuple(sorted(COMMAND_GROUPS))


def _normalized_paths(paths: Sequence[str]) -> list[str]:
    normalized: set[str] = set()
    for raw_path in paths:
        if not raw_path:
            continue
        path = raw_path.replace("\\", "/")
        while path.startswith("./"):
            path = path[2:]
        normalized.add(path)
    return sorted(normalized)


def _is_documentation_path(path: str) -> bool:
    if path in _DOCUMENTATION_POLICY_PATHS:
        return False
    if path.casefold().endswith(".md"):
        return True
    return path.startswith("docs/") and path.casefold().endswith((".md", ".txt"))


def _is_workflow_path(path: str) -> bool:
    name = Path(path).name
    return (
        path in _DOCUMENTATION_POLICY_PATHS
        or path.startswith((".github/", "scripts/", "deploy/"))
        or name in _WORKFLOW_FILENAMES
        or path.startswith(("docker-compose", "security/", ".docker/"))
        or path in {".pre-commit-config.yaml", "pyproject.toml"}
    )


def _is_frontend_path(path: str) -> bool:
    return path == "frontend" or path.startswith("frontend/")


def _is_backend_path(path: str) -> bool:
    return path in {"backend", "bot"} or path.startswith(("backend/", "bot/", "tests/integration/"))


def _is_api_path(path: str) -> bool:
    return path.startswith(_API_PREFIXES) or any(token in path.casefold() for token in _API_TOKENS)


def _is_migration_path(path: str) -> bool:
    lowered = path.casefold()
    return path.startswith(_MIGRATION_PREFIXES) or any(
        token in lowered.split("/") for token in ("migration", "migrations")
    )


def _is_container_security_path(path: str) -> bool:
    return path in _CONTAINER_SECURITY_PATHS or path.startswith("security/")


def _dependency_kind(path: str) -> tuple[bool, bool, bool]:
    normalized = path.casefold()
    name = Path(path).name.casefold()
    frontend = normalized in {item.casefold() for item in _FRONTEND_DEPENDENCY_PATHS}
    python = (
        name in _PYTHON_DEPENDENCY_FILENAMES
        and (path.startswith(("backend/", "bot/")) or path in {"uv.lock", "requirements.txt"})
    ) or normalized == "pyproject.toml"
    runtime = python and name in {"requirements.txt", "requirements-runtime.txt", "uv.lock"}
    if normalized.endswith("/package-lock.json") or normalized.endswith("/package.json"):
        frontend = True
    return frontend, python, runtime


def _profile_for_paths(
    normalized: Sequence[str],
) -> tuple[str, dict[str, bool], list[str], bool, bool, bool, bool]:
    documentation = bool(normalized) and all(_is_documentation_path(path) for path in normalized)
    frontend = any(_is_frontend_path(path) for path in normalized)
    backend = any(_is_backend_path(path) for path in normalized)
    workflow = any(_is_workflow_path(path) for path in normalized)
    shared_ci_contract = any(path in _SHARED_CI_CONTRACT_PATHS for path in normalized)
    container_security = any(
        _is_container_security_path(path) for path in normalized if not _is_documentation_path(path)
    )
    api_contract = any(
        _is_api_path(path) for path in normalized if not _is_documentation_path(path)
    )
    migration = any(
        _is_migration_path(path) for path in normalized if not _is_documentation_path(path)
    )
    frontend_dependency = False
    python_dependency = False
    runtime_dependency = False
    for path in normalized:
        if _is_documentation_path(path):
            continue
        frontend_dep, python_dep, runtime_dep = _dependency_kind(path)
        frontend_dependency |= frontend_dep
        python_dependency |= python_dep
        runtime_dependency |= runtime_dep

    reasons: list[str] = []
    if documentation:
        reasons.append("all changed paths are documentation/backlog text")
    if frontend:
        reasons.append("frontend surface changed")
    if backend:
        reasons.append("backend, bot or integration-test surface changed")
    if workflow:
        reasons.append("workflow/platform/deployment surface changed")
    if shared_ci_contract:
        reasons.append("shared CI command contract changed; using full regression profile")
    if api_contract:
        reasons.append("API/auth/session/Telegram contract risk detected")
    if migration:
        reasons.append("migration or persistence boundary changed")
    if container_security:
        reasons.append("container security configuration changed; requiring image scan")
    if frontend_dependency:
        reasons.append("frontend dependency manifest changed")
    if python_dependency:
        reasons.append("Python dependency manifest changed")

    if not normalized:
        profile = "cross-stack"
        reasons.append("empty diff is ambiguous; using conservative full profile")
    elif documentation:
        profile = "documentation"
    elif (
        shared_ci_contract
        or api_contract
        or (frontend and backend)
        or (frontend and workflow)
        or (backend and workflow)
    ):
        profile = "cross-stack"
    elif migration:
        profile = "migration"
    elif workflow:
        profile = "workflow-platform"
    elif frontend:
        profile = "frontend"
    elif backend:
        profile = "backend"
    else:
        profile = "cross-stack"
        reasons.append("path scope is unknown; using conservative full profile")

    signals = {
        "frontend": frontend,
        "backend": backend,
        "workflow_platform": workflow,
        "shared_ci_contract": shared_ci_contract,
        "documentation": documentation,
        "api_contract": api_contract,
        "migration": migration,
        "frontend_dependency": frontend_dependency,
        "python_dependency": python_dependency,
        "runtime_dependency": runtime_dependency,
        "container_security": container_security,
    }
    return (
        profile,
        signals,
        reasons,
        frontend_dependency,
        python_dependency,
        runtime_dependency,
        container_security,
    )


def expected_jobs_for_groups(groups: Sequence[str], *, event: str = "pull_request") -> list[str]:
    unknown_groups = sorted(set(groups) - set(GROUP_TO_JOB))
    if unknown_groups:
        raise CIContractError(f"Unknown CI groups in expected result set: {unknown_groups}")
    jobs = {"scope-router"}
    if event == "pull_request":
        jobs.add("task-provenance")
        jobs.add("review-contract")
    elif event == "push":
        jobs.add("merge-provenance")
    elif event in {"schedule", "workflow_dispatch"}:
        jobs.add("scheduled-report")
    for group in groups:
        job = GROUP_TO_JOB.get(group)
        if job is not None:
            jobs.add(job)
    return sorted(jobs)


def _decision_for_groups(
    *,
    profile: str,
    paths: Sequence[str],
    signals: Mapping[str, bool],
    reasons: Sequence[str],
    groups: Sequence[str],
    event: str,
) -> dict[str, object]:
    selected_groups = list(dict.fromkeys(groups))
    required_jobs = expected_jobs_for_groups(selected_groups, event=event)
    selected_group_set = set(selected_groups)
    skipped_groups = {
        group: "not required by the selected conservative profile"
        for group in _ALL_ROUTABLE_GROUPS
        if group not in selected_group_set
    }
    dependency_full = "dependency-audit" in selected_group_set
    dependency_frontend = dependency_full or "frontend-dependency-audit" in selected_group_set
    dependency_python = dependency_full or "python-dependency-audit" in selected_group_set
    outputs = {key: job in required_jobs for job, key in ROUTER_OUTPUTS.items()}
    outputs.update(
        {key: group in selected_group_set for group, key in ROUTER_GROUP_OUTPUTS.items()}
    )
    outputs.update(
        {
            "run_full_dependency_audit": dependency_full,
            "run_frontend_dependency_audit": dependency_frontend,
            "run_python_dependency_audit": dependency_python,
        }
    )
    return {
        "event": event,
        "profile": profile,
        "paths": list(paths),
        "signals": dict(signals),
        "reasons": list(reasons),
        "groups": selected_groups,
        "required_groups": selected_groups,
        "required_jobs": required_jobs,
        "skipped_groups": skipped_groups,
        "outputs": outputs,
    }


def classify_scope(paths: Sequence[str]) -> dict[str, object]:
    """Classify changed paths with a deterministic, conservative CI profile."""

    normalized = _normalized_paths(paths)
    (
        profile,
        signals,
        reasons,
        frontend_dependency,
        python_dependency,
        runtime_dependency,
        container_security,
    ) = _profile_for_paths(normalized)
    groups = list(PROFILE_GROUPS[profile])
    if frontend_dependency and "frontend-dependency-audit" not in groups:
        groups.append("frontend-dependency-audit")
    if python_dependency and "dependency-audit" not in groups:
        groups.append("python-dependency-audit")
    if runtime_dependency and "container-contract" not in groups:
        groups.append("container-contract")
    if container_security and "container-contract" not in groups:
        groups.append("container-contract")
    return _decision_for_groups(
        profile=profile,
        paths=normalized,
        signals=signals,
        reasons=reasons,
        groups=groups,
        event="pull_request",
    )


def _git_changed_paths(root: Path, base_sha: str, head_sha: str) -> list[str]:
    command = [
        "git",
        "-c",
        f"safe.directory={root.resolve().as_posix()}",
        "diff",
        "--no-ext-diff",
        "--name-only",
        "-z",
        "--find-renames",
        base_sha,
        head_sha,
    ]
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
        raise CIContractError(f"Cannot calculate changed paths: {detail}")
    return _normalized_paths(completed.stdout.split("\0"))


def route_repository(
    root: Path,
    *,
    event: str,
    base_sha: str | None = None,
    head_sha: str | None = None,
    run_kind: str | None = None,
    schedule_cron: str | None = None,
) -> dict[str, object]:
    """Build the CI route for a GitHub event from the exact repository diff."""

    if event == "pull_request":
        if not base_sha or not head_sha:
            raise CIContractError("pull_request routing requires both base_sha and head_sha")
        paths = _git_changed_paths(root, base_sha, head_sha)
        decision = classify_scope(paths)
        decision["base_sha"] = base_sha
        decision["head_sha"] = head_sha
        return decision
    if event == "push":
        return _decision_for_groups(
            profile="post-merge",
            paths=[],
            signals={"post_merge": True},
            reasons=["master push runs exact provenance and immutable container delivery"],
            groups=("container-contract",),
            event=event,
        )
    if event in {"schedule", "workflow_dispatch"}:
        resolved_run_kind = resolve_run_kind(
            event,
            run_kind=run_kind,
            schedule_cron=schedule_cron,
        )
        profile = profile_for_run_kind(resolved_run_kind)
        return _decision_for_groups(
            profile=profile,
            paths=[],
            signals={
                "scheduled_regression": True,
                "daily_regression": resolved_run_kind == "daily",
                "weekly_exhaustive": resolved_run_kind == "weekly",
            },
            reasons=[
                f"{resolved_run_kind} scheduled regression uses the authoritative "
                f"{profile} profile with report suites {list(report_suites(resolved_run_kind))}"
            ],
            groups=PROFILE_GROUPS[profile],
            event=event,
        )
    raise CIContractError(f"Unsupported CI event: {event}")


def _router_log(decision: Mapping[str, object]) -> None:
    print(f"CI_SCOPE profile={decision['profile']} event={decision['event']}", flush=True)
    print(f"CI_CHANGED_PATHS {json.dumps(decision['paths'], ensure_ascii=False)}", flush=True)
    print(
        f"CI_REQUIRED_GROUPS {json.dumps(decision['required_groups'], ensure_ascii=False)}",
        flush=True,
    )
    print(
        f"CI_REQUIRED_JOBS {json.dumps(decision['required_jobs'], ensure_ascii=False)}", flush=True
    )
    print(
        f"CI_SKIPPED_GROUPS {json.dumps(decision['skipped_groups'], ensure_ascii=False)}",
        flush=True,
    )
    print(f"CI_SCOPE_REASONS {json.dumps(decision['reasons'], ensure_ascii=False)}", flush=True)


def write_router_outputs(decision: Mapping[str, object], destination: Path) -> None:
    outputs = decision.get("outputs")
    if not isinstance(outputs, Mapping):
        raise CIContractError("Router decision has no outputs mapping")
    lines = [
        f"profile={decision['profile']}",
        f"required_groups={json.dumps(decision['required_groups'], ensure_ascii=False, separators=(',', ':'))}",
        f"required_jobs={json.dumps(decision['required_jobs'], ensure_ascii=False, separators=(',', ':'))}",
        f"skipped_groups={json.dumps(decision['skipped_groups'], ensure_ascii=False, separators=(',', ':'))}",
        f"changed_paths={json.dumps(decision['paths'], ensure_ascii=False, separators=(',', ':'))}",
    ]
    for key, value in outputs.items():
        lines.append(f"{key}={'true' if value else 'false'}")
    with destination.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines) + "\n")


def verify_results(expected_jobs: Sequence[str], results: Mapping[str, str]) -> None:
    """Fail unless every expected job completed successfully."""

    expected = list(dict.fromkeys(expected_jobs))
    unknown_expected = sorted(set(expected) - set(ROUTER_JOB_NAMES))
    if unknown_expected:
        raise CIContractError(f"Unknown expected CI jobs: {unknown_expected}")
    unknown_results = sorted(set(results) - set(ROUTER_JOB_NAMES))
    if unknown_results:
        raise CIContractError(f"Unknown actual CI jobs: {unknown_results}")
    failures = {
        job: results.get(job, "missing") for job in expected if results.get(job) != "success"
    }
    if failures:
        raise CIContractError(f"Required CI jobs did not succeed: {failures}")
    unexpected = {
        job: status
        for job, status in results.items()
        if job not in expected and status != "skipped"
    }
    if unexpected:
        raise CIContractError(f"Unexpected CI jobs ran outside the router result set: {unexpected}")


def _record_timing(
    *, group: str, command: str, duration: float, status: str, attempts: int
) -> None:
    destination = os.environ.get("CI_TIMING_FILE")
    if not destination:
        return
    record = {
        "group": group,
        "command": command,
        "duration_seconds": round(duration, 3),
        "status": status,
        "attempts": attempts,
    }
    try:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError as error:
        print(f"CI_TIMING_ARTIFACT_ERROR path={destination} error={error}", file=sys.stderr)


def _run_command(
    command: CommandSpec,
    *,
    argv: Sequence[str],
    cwd: Path,
    env: Mapping[str, str],
    group: str,
) -> None:
    started = time.perf_counter()
    attempts = 0
    returncode: int | None = None
    try:
        while True:
            attempts += 1
            if command.retry_on_transient:
                completed = subprocess.run(
                    list(argv),
                    cwd=cwd,
                    env=dict(env),
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                if completed.stdout:
                    print(completed.stdout, end="")
                if completed.stderr:
                    print(completed.stderr, end="", file=sys.stderr)
            else:
                completed = subprocess.run(list(argv), cwd=cwd, env=dict(env), check=False)
            returncode = completed.returncode
            if returncode == 0:
                return
            combined = "\n".join(
                part
                for part in (getattr(completed, "stdout", ""), getattr(completed, "stderr", ""))
                if part
            )
            transient = command.retry_on_transient and _is_transient_failure(combined)
            if not transient:
                raise CIContractError(
                    f"CI command group {group} failed at {command.name} with exit code {completed.returncode}"
                )
            if attempts >= command.retry_max_attempts:
                raise CIContractError(
                    f"BLOCKED_INFRASTRUCTURE: {group}/{command.name} exhausted "
                    f"{attempts} attempts after a transient audit/network failure"
                )
            delay_index = min(attempts - 1, len(command.retry_delays_seconds) - 1)
            delay = command.retry_delays_seconds[delay_index] if command.retry_delays_seconds else 0
            print(
                f"CI_RETRY group={group} command={command.name} attempt={attempts + 1}/"
                f"{command.retry_max_attempts} delay_seconds={delay}",
                flush=True,
            )
            time.sleep(delay)
    finally:
        duration = time.perf_counter() - started
        status = "success" if returncode == 0 else "failed"
        print(
            f"CI_TIMING group={group} command={command.name} duration_seconds={duration:.3f} "
            f"status={status} attempts={attempts}",
            flush=True,
        )
        _record_timing(
            group=group,
            command=command.name,
            duration=duration,
            status=status,
            attempts=attempts,
        )


def _is_transient_failure(output: str) -> bool:
    lowered = output.casefold()
    if re.search(
        r"(?:http(?:\s+status|\s+error)?|status(?:\s+code)?|response|code)"
        r"[^\d\r\n]{0,20}\b[e]?(?:429|500|502|503|504)\b",
        lowered,
    ):
        return True
    if re.search(
        r"\b(?:429|500|502|503|504)\b\s+"
        r"(?:too many requests|internal server error|bad gateway|service unavailable|gateway timeout)",
        lowered,
    ):
        return True
    return any(
        marker in lowered
        for marker in (
            "eai_again",
            "econnreset",
            "etimedout",
            "enotfound",
            "network timeout",
            "socket hang up",
            "fetch failed",
            "timed out",
        )
    )


def contract_payload() -> dict[str, object]:
    return {
        "version": CONTRACT_VERSION,
        "router_version": ROUTER_VERSION,
        "groups": {
            name: {
                "commands": [asdict(command) for command in spec.commands],
                "prerequisites": list(spec.prerequisites),
            }
            for name, spec in sorted(COMMAND_GROUPS.items())
        },
        "profiles": {name: list(groups) for name, groups in sorted(PROFILE_GROUPS.items())},
        "sharding": {
            "frontend-e2e": {"count": CI_SHARD_COUNT, "strategy": "playwright"},
            "python-tests": {
                "count": CI_SHARD_COUNT,
                "strategy": "pytest-node-round-robin",
            },
        },
        "routing": {
            "group_to_job": dict(sorted(GROUP_TO_JOB.items())),
            "job_names": list(ROUTER_JOB_NAMES),
            "outputs": dict(sorted(ROUTER_OUTPUTS.items())),
            "group_outputs": dict(sorted(ROUTER_GROUP_OUTPUTS.items())),
            "path_rules": {
                "documentation_policy_paths": sorted(_DOCUMENTATION_POLICY_PATHS),
                "frontend_dependency_paths": sorted(_FRONTEND_DEPENDENCY_PATHS),
                "python_dependency_filenames": sorted(_PYTHON_DEPENDENCY_FILENAMES),
                "workflow_filenames": sorted(_WORKFLOW_FILENAMES),
                "api_prefixes": list(_API_PREFIXES),
                "api_tokens": list(_API_TOKENS),
                "shared_ci_contract_paths": sorted(_SHARED_CI_CONTRACT_PATHS),
                "container_security_paths": sorted(_CONTAINER_SECURITY_PATHS),
                "migration_prefixes": list(_MIGRATION_PREFIXES),
            },
        },
    }


def contract_digest() -> str:
    encoded = json.dumps(
        contract_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resolve_argv(argv: Sequence[str]) -> list[str]:
    resolved = list(argv)
    if resolved and resolved[0] == "python":
        resolved[0] = sys.executable
    elif os.name == "nt" and resolved and resolved[0] in {"npm", "npx"}:
        resolved[0] = f"{resolved[0]}.cmd"
    return resolved


def _check_prerequisite(root: Path, prerequisite: str, env: Mapping[str, str]) -> str | None:
    if prerequisite == "alembic":
        try:
            __import__("alembic")
            return None
        except ImportError:
            return "python package alembic"
    if prerequisite in {"python", "npm", "uvx", "pre_commit"}:
        executable = {
            "python": sys.executable,
            "pre_commit": "pre-commit",
        }.get(prerequisite, prerequisite)
        if prerequisite == "pre_commit":
            try:
                __import__("pre_commit")
                return None
            except ImportError:
                return "python package pre_commit"
        if shutil.which(executable) is None:
            return executable
        return None
    if prerequisite.endswith("/"):
        return None if (root / prerequisite).is_dir() else prerequisite
    if "/" in prerequisite or prerequisite.endswith((".ts", ".json", ".yml")):
        return None if (root / prerequisite).exists() else prerequisite
    return None if env.get(prerequisite) else f"environment variable {prerequisite}"


def missing_prerequisites(
    group: str, *, root: Path, env: Mapping[str, str] | None = None
) -> list[str]:
    if group not in COMMAND_GROUPS:
        raise CIContractError(f"Unknown CI command group: {group}")
    values = env or os.environ
    return [
        missing
        for prerequisite in COMMAND_GROUPS[group].prerequisites
        if (missing := _check_prerequisite(root, prerequisite, values)) is not None
    ]


def parse_shard(value: str) -> tuple[int, int]:
    """Convert a human-facing ``N/M`` shard label to a zero-based index."""

    match = SHARD_RE.fullmatch(value)
    if match is None:
        raise CIContractError(f"Invalid shard {value!r}; expected N/M with 1 <= N <= M")
    number = int(match.group("number"))
    count = int(match.group("count"))
    if number > count:
        raise CIContractError(f"Invalid shard {value!r}; shard number cannot exceed shard count")
    return number - 1, count


def select_shard(items: Sequence[str], *, shard_index: int, shard_count: int) -> tuple[str, ...]:
    """Select a deterministic round-robin subset from an ordered item list."""

    if shard_count < 1 or not 0 <= shard_index < shard_count:
        raise CIContractError(
            f"Invalid shard coordinates: index={shard_index}, count={shard_count}"
        )
    return tuple(
        item for position, item in enumerate(items) if position % shard_count == shard_index
    )


def _normalize_python_test_node(line: str) -> str | None:
    candidate = line.strip()
    path, separator, test_id = candidate.partition("::")
    if not separator:
        return None
    normalized_path = path.replace("\\", "/")
    if not normalized_path.startswith(("backend/tests/", "bot/tests/")):
        return None
    return f"{normalized_path}::{test_id}"


def _collect_python_test_nodes(root: Path, env: Mapping[str, str]) -> tuple[str, ...]:
    argv = _resolve_argv(
        (
            "python",
            "scripts/run_pytest.py",
            "backend/tests",
            "bot/tests",
            "--collect-only",
            "-q",
        )
    )
    print(f"$ (cd . && {' '.join(argv)})", flush=True)
    completed = subprocess.run(
        argv,
        cwd=root,
        env=dict(env),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        details = "\n".join(
            part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
        )
        if len(details) > 4000:
            details = details[-4000:]
        suffix = f"\n{details}" if details else ""
        raise CIContractError(
            f"Python test collection failed with exit code {completed.returncode}{suffix}"
        )

    nodes = tuple(
        normalized
        for line in completed.stdout.splitlines()
        if (normalized := _normalize_python_test_node(line)) is not None
    )
    if not nodes:
        raise CIContractError("Python test collection returned no test node IDs")
    return nodes


def _sharded_python_command(
    command: CommandSpec,
    *,
    root: Path,
    env: Mapping[str, str],
    shard_index: int,
    shard_count: int,
) -> CommandSpec:
    all_nodes = _collect_python_test_nodes(root, env)
    selected_nodes = select_shard(all_nodes, shard_index=shard_index, shard_count=shard_count)
    if not selected_nodes:
        raise CIContractError(f"No Python tests selected for shard {shard_index + 1}/{shard_count}")

    target_paths = {"backend/tests", "bot/tests"}
    target_positions = [
        position for position, argument in enumerate(command.argv) if argument in target_paths
    ]
    if not target_positions:
        raise CIContractError("Python test command has no test target paths to shard")
    first_target = min(target_positions)
    last_target = max(target_positions) + 1
    argv = (
        *command.argv[:first_target],
        *selected_nodes,
        *command.argv[last_target:],
    )
    print(
        f"Selected {len(selected_nodes)} of {len(all_nodes)} Python tests "
        f"for shard {shard_index + 1}/{shard_count}",
        flush=True,
    )
    return CommandSpec(name=f"{command.name}-shard", argv=argv, cwd=command.cwd)


def _sharded_frontend_command(
    command: CommandSpec, *, shard_index: int, shard_count: int
) -> CommandSpec:
    shard_label = f"{shard_index + 1}/{shard_count}"
    return CommandSpec(
        name=f"{command.name}-shard",
        argv=(*command.argv, "--", f"--shard={shard_label}"),
        cwd=command.cwd,
    )


def run_group(
    group: str,
    *,
    root: Path | None = None,
    env: Mapping[str, str] | None = None,
    shard: str | None = None,
) -> None:
    if group not in COMMAND_GROUPS:
        raise CIContractError(f"Unknown CI command group: {group}")
    project_root = (root or Path.cwd()).resolve()
    effective_env = dict(os.environ) | dict(env or {})
    shard_index: int | None = None
    shard_count: int | None = None
    if shard is not None:
        if group not in SHARDABLE_GROUPS:
            raise CIContractError(f"CI group {group} does not support sharding")
        shard_index, shard_count = parse_shard(shard)
    missing = missing_prerequisites(group, root=project_root, env=effective_env)
    if missing:
        raise CIContractError(f"Required prerequisite missing for {group}: {', '.join(missing)}")
    spec = COMMAND_GROUPS[group]
    for command in spec.commands:
        effective_command = command
        if shard_index is not None and shard_count is not None:
            if group == "python-tests" and command.name == "python-suite":
                effective_command = _sharded_python_command(
                    command,
                    root=project_root,
                    env=effective_env,
                    shard_index=shard_index,
                    shard_count=shard_count,
                )
            elif group == "frontend-e2e":
                effective_command = _sharded_frontend_command(
                    command, shard_index=shard_index, shard_count=shard_count
                )
        argv = _resolve_argv(effective_command.argv)
        if argv[0] == "git":
            argv = ["git", "-c", f"safe.directory={project_root.as_posix()}", *argv[1:]]
        cwd = (project_root / effective_command.cwd).resolve()
        print(f"$ (cd {effective_command.cwd} && {' '.join(argv)})", flush=True)
        _run_command(
            effective_command,
            argv=argv,
            cwd=cwd,
            env=effective_env,
            group=group,
        )


def validate_contract() -> None:
    if not COMMAND_GROUPS:
        raise CIContractError("CI contract has no command groups")
    for profile, groups in PROFILE_GROUPS.items():
        if not groups:
            raise CIContractError(f"CI profile {profile} is empty")
        unknown = sorted(set(groups) - set(COMMAND_GROUPS))
        if unknown:
            raise CIContractError(f"CI profile {profile} references unknown groups: {unknown}")
    for name, spec in COMMAND_GROUPS.items():
        if name != spec.name or not spec.commands:
            raise CIContractError(f"Invalid command group definition: {name}")
        command_names = [item.name for item in spec.commands]
        if len(command_names) != len(set(command_names)):
            raise CIContractError(f"Duplicate command in group {name}")
        for command in spec.commands:
            if command.retry_max_attempts < 1:
                raise CIContractError(f"Invalid retry limit for command {name}/{command.name}")
            if not command.retry_on_transient and command.retry_max_attempts != 1:
                raise CIContractError(
                    f"Non-retryable command has a retry limit for {name}/{command.name}"
                )
            if command.retry_on_transient and command.retry_max_attempts > 3:
                raise CIContractError(
                    f"Retry limit exceeds three attempts for {name}/{command.name}"
                )
            if any(delay < 0 for delay in command.retry_delays_seconds):
                raise CIContractError(f"Negative retry delay for command {name}/{command.name}")
            if any(delay > 60 for delay in command.retry_delays_seconds):
                raise CIContractError(f"Retry delay exceeds 60 seconds for {name}/{command.name}")
            if len(command.retry_delays_seconds) > command.retry_max_attempts - 1:
                raise CIContractError(f"Too many retry delays for command {name}/{command.name}")
    if set(GROUP_TO_JOB) != set(COMMAND_GROUPS):
        raise CIContractError("CI router group-to-job mapping is incomplete")
    if set(ROUTER_OUTPUTS) != {
        "quality",
        "policy",
        "frontend",
        "frontend-smoke",
        "frontend-mobile-regression",
        "frontend-mobile-regression-extended",
        "frontend-cross-browser",
        "python-tests",
        "migrated-stack",
        "dependency-audit",
        "containers",
        "critical-smoke",
        "workflow-contracts",
        "merge-provenance",
        "scheduled-report",
    }:
        raise CIContractError("CI router outputs do not cover the stable job set")
    if set(ROUTER_GROUP_OUTPUTS) != {
        "workflow-config",
        "image-contract",
        "deployment-contract",
    }:
        raise CIContractError("CI router group outputs do not cover workflow contract groups")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    digest = subparsers.add_parser("digest")
    digest.add_argument("--json", action="store_true")
    groups = subparsers.add_parser("list-groups")
    groups.add_argument("--profile")
    run = subparsers.add_parser("run-group")
    run.add_argument("group", choices=sorted(COMMAND_GROUPS))
    run.add_argument("--root", type=Path, default=Path.cwd())
    run.add_argument("--shard")
    route = subparsers.add_parser("route")
    route.add_argument(
        "--event", choices=("pull_request", "push", "schedule", "workflow_dispatch"), required=True
    )
    route.add_argument("--base-sha")
    route.add_argument("--head-sha")
    route.add_argument("--run-kind", choices=("daily", "weekly"))
    route.add_argument("--schedule-cron")
    route.add_argument("--root", type=Path, default=Path.cwd())
    route.add_argument("--github-output", type=Path)
    route.add_argument("--json", action="store_true")
    verify = subparsers.add_parser("verify-results")
    verify.add_argument("--expected-jobs", required=True)
    verify.add_argument("--results-json", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        validate_contract()
        if args.command == "validate":
            print(f"CI contract valid: {CONTRACT_VERSION} {contract_digest()}")
            return 0
        if args.command == "digest":
            payload = {"version": CONTRACT_VERSION, "digest": contract_digest()}
            print(json.dumps(payload) if args.json else payload["digest"])
            return 0
        if args.command == "list-groups":
            groups = PROFILE_GROUPS.get(args.profile, tuple(COMMAND_GROUPS))
            if args.profile is not None and args.profile not in PROFILE_GROUPS:
                raise CIContractError(f"Unknown CI profile: {args.profile}")
            print(json.dumps(list(groups), ensure_ascii=False))
            return 0
        if args.command == "run-group":
            run_group(args.group, root=args.root, shard=args.shard)
            return 0
        if args.command == "route":
            decision = route_repository(
                args.root,
                event=args.event,
                base_sha=args.base_sha,
                head_sha=args.head_sha,
                run_kind=args.run_kind,
                schedule_cron=args.schedule_cron,
            )
            if args.github_output is not None:
                write_router_outputs(decision, args.github_output)
            if args.json:
                print(json.dumps(decision, ensure_ascii=False, sort_keys=True))
            else:
                _router_log(decision)
            return 0
        if args.command == "verify-results":
            expected = json.loads(args.expected_jobs)
            results = json.loads(args.results_json)
            if not isinstance(expected, list) or not all(
                isinstance(item, str) for item in expected
            ):
                raise CIContractError("Expected jobs must be a JSON string array")
            if not isinstance(results, dict) or not all(
                isinstance(key, str) and isinstance(value, str) for key, value in results.items()
            ):
                raise CIContractError("Results must be a JSON string map")
            verify_results(expected, results)
            print(f"CI_RESULT_SET_PASS expected={json.dumps(expected, separators=(',', ':'))}")
            return 0
        raise AssertionError(f"Unhandled command: {args.command}")
    except (CIContractError, OSError, json.JSONDecodeError) as error:
        print(f"ci contract error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
