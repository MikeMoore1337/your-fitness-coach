"""Classify whether a Git diff changes the application deployed to production.

The helper is intentionally stateless: Git supplies the changed paths and the
result is derived on every invocation.  It does not create task state, leases,
queues or release records.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path


class DeploymentScopeError(RuntimeError):
    """The changed-path input could not be evaluated safely."""


_NO_DEPLOY_PREFIXES = (
    ".agents/",
    ".artifacts/",
    "codex-backlog/",
    "docs/",
    "tests/",
    "backend/tests/",
    "bot/tests/",
    "frontend/tests/",
)
_NO_DEPLOY_FILES = {
    ".codex/config.toml",  # Project-scoped developer MCP configuration, not application runtime.
    "AGENTS.md",
    "README.md",
    ".gitignore",
    ".gitattributes",
    ".pre-commit-config.yaml",
}
_DEPLOY_PREFIXES = (
    "backend/",
    "bot/",
    "frontend/",
    "deploy/",
)
_DEPLOY_FILES = {
    "Dockerfile",
    ".dockerignore",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Caddyfile",
    "pyproject.toml",
    "uv.lock",
    "frontend/package.json",
    "frontend/package-lock.json",
    # These scripts are copied into the application image and can change its
    # runtime behavior.  Host-side delivery helpers remain tooling-only.
    "scripts/check_deployment.py",
    "scripts/fetch_rapidocr_models.py",
}


def _normalize_paths(paths: Sequence[str]) -> list[str]:
    normalized: set[str] = set()
    for raw_path in paths:
        path = str(raw_path).strip().replace("\\", "/")
        while path.startswith("./"):
            path = path[2:]
        if path:
            normalized.add(path)
    return sorted(normalized)


def _is_no_deploy(path: str) -> bool:
    return path in _NO_DEPLOY_FILES or path.startswith(_NO_DEPLOY_PREFIXES)


def _is_deploy(path: str) -> bool:
    if _is_no_deploy(path):
        return False
    if path in _DEPLOY_FILES or path.startswith(_DEPLOY_PREFIXES):
        return True
    # CI/governance changes validate release behavior but do not mutate the
    # application unless an application artifact also changed.
    return not (path.startswith(".github/") or path.startswith("scripts/"))


def classify_paths(paths: Sequence[str]) -> dict[str, object]:
    """Return a deterministic, JSON-safe deployment decision."""

    normalized = _normalize_paths(paths)
    deploy_paths = [path for path in normalized if _is_deploy(path)]
    no_deploy_paths = [path for path in normalized if not _is_deploy(path)]
    reasons: list[str] = []
    if deploy_paths:
        reasons.append("application runtime, artifact, migration or deployment path changed")
    elif normalized:
        reasons.append("only documentation, governance, tests or developer tooling changed")
    else:
        reasons.append("no changed paths were supplied")
    return {
        "changed_paths": normalized,
        "deploy_required": bool(deploy_paths),
        "deploy_paths": deploy_paths,
        "no_deploy_paths": no_deploy_paths,
        "reasons": reasons,
    }


def changed_paths(root: Path, base_sha: str, head_sha: str) -> list[str]:
    """Read changed paths directly from Git without writing state."""

    command = [
        "git",
        "-c",
        f"safe.directory={root.resolve().as_posix()}",
        "diff",
        "--no-ext-diff",
        "--name-only",
        "--no-renames",
        "--diff-filter=ACMRTUXB",
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
        raise DeploymentScopeError(f"Cannot calculate changed paths: {detail}")
    return _normalize_paths(completed.stdout.splitlines())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--paths-file", type=Path)
    source.add_argument("--base")
    parser.add_argument("--head")
    source.add_argument("--path", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if bool(args.base) != bool(args.head):
            raise DeploymentScopeError("--base and --head must be provided together")
        if args.paths_file is not None:
            paths = args.paths_file.read_text(encoding="utf-8").splitlines()
        elif args.base:
            paths = changed_paths(args.root, args.base, args.head)
        elif args.path:
            paths = args.path
        else:
            raise DeploymentScopeError("one of --paths-file, --base/--head or --path is required")
        payload = classify_paths(paths)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            print(f"deploy_required={str(payload['deploy_required']).lower()}")
            print(f"changed_paths={json.dumps(payload['changed_paths'], ensure_ascii=False)}")
            print(f"reason={payload['reasons'][0]}")
        return 0
    except (DeploymentScopeError, OSError) as error:
        print(f"deployment scope error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
