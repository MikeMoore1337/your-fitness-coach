"""Shared immutable image naming and deployment-source contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path

REGISTRY = "ghcr.io"
IMAGE_KINDS = ("backend", "bot", "hermes-discovery", "hermes-worker")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class DeploymentContractError(RuntimeError):
    """The build and deployment image contract is invalid."""


def _validate_kind(kind: str) -> str:
    if kind not in IMAGE_KINDS:
        raise DeploymentContractError(f"Unsupported image kind: {kind}")
    return kind


def _validate_revision(revision: str) -> str:
    if not REVISION_RE.fullmatch(revision):
        raise DeploymentContractError("revision must be a full lowercase Git SHA")
    return revision


def _validate_repository(repository: str) -> str:
    if not REPOSITORY_RE.fullmatch(repository):
        raise DeploymentContractError(f"Invalid GitHub repository slug: {repository}")
    return repository.lower()


def image_ref(repository: str, kind: str, revision: str) -> str:
    return f"{REGISTRY}/{_validate_repository(repository)}-{_validate_kind(kind)}:{_validate_revision(revision)}"


def local_tag(kind: str, revision: str) -> str:
    return f"yfc-{_validate_kind(kind)}:ci-{_validate_revision(revision)[:12]}"


def refs(repository: str, kind: str, revision: str) -> dict[str, str]:
    return {
        "kind": _validate_kind(kind),
        "revision": _validate_revision(revision),
        "image_ref": image_ref(repository, kind, revision),
        "local_tag": local_tag(kind, revision),
    }


def validate_files(
    *,
    ci_workflow: Path,
    deploy_workflow: Path,
    compose: Path,
    deploy_script: Path | None = None,
) -> None:
    ci = ci_workflow.read_text(encoding="utf-8")
    deploy = deploy_workflow.read_text(encoding="utf-8")
    compose_text = compose.read_text(encoding="utf-8")
    errors: list[str] = []
    if "scripts/deployment_contract.py refs" not in ci:
        errors.append("CI does not resolve image references through deployment_contract.py")
    if "scripts/deployment_contract.py refs" not in deploy:
        errors.append(
            "deploy workflow does not resolve image references through deployment_contract.py"
        )
    if "git archive" not in deploy or "deployment-migration-manifest.json" not in deploy:
        errors.append(
            "deploy workflow does not transfer an immutable commit bundle and migration manifest"
        )
    if "backend/alembic/versions" not in deploy:
        errors.append("deploy workflow bundle does not include migration sources")
    if "${BACKEND_IMAGE" not in compose_text or "${BOT_IMAGE" not in compose_text:
        errors.append("Compose application services do not consume BACKEND_IMAGE/BOT_IMAGE")
    if "GHCR_BACKEND_IMAGE" in deploy or "GHCR_BOT_IMAGE" in deploy:
        errors.append("deploy workflow contains an independent GHCR image-name source")
    if "sync-dev:" in deploy or "DEV_SYNC_APP" in deploy:
        errors.append("deploy workflow contains the removed dev synchronization lane")
    if "fit-mini-app-backend" in ci or "fit-mini-app-bot" in ci:
        errors.append("CI contains legacy hardcoded application image names")
    if deploy_script is not None:
        script = deploy_script.read_text(encoding="utf-8")
        if "BACKEND_IMAGE" not in script or "BOT_IMAGE" not in script:
            errors.append("deploy script does not require both application image references")
        if ".deployment-sha" not in script:
            errors.append("deploy script does not verify immutable bundle provenance")
        if "git fetch" in script or "git reset" in script or "git rev-parse" in script:
            errors.append("deploy script depends on a production Git checkout")
    if errors:
        raise DeploymentContractError("; ".join(errors))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    ref_parser = subparsers.add_parser("refs")
    ref_parser.add_argument("--repository", required=True)
    ref_parser.add_argument("--revision", required=True)
    ref_parser.add_argument("--kind", choices=IMAGE_KINDS, required=True)
    check = subparsers.add_parser("check")
    check.add_argument("--ci-workflow", type=Path, required=True)
    check.add_argument("--deploy-workflow", type=Path, required=True)
    check.add_argument("--compose", type=Path, required=True)
    check.add_argument("--deploy-script", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "refs":
            for key, value in refs(args.repository, args.kind, args.revision).items():
                print(f"{key}={value}")
            return 0
        if args.command == "check":
            validate_files(
                ci_workflow=args.ci_workflow,
                deploy_workflow=args.deploy_workflow,
                compose=args.compose,
                deploy_script=args.deploy_script,
            )
            print(json.dumps({"ok": True, "image_kinds": IMAGE_KINDS}))
            return 0
        raise AssertionError(f"Unhandled command: {args.command}")
    except (DeploymentContractError, OSError) as error:
        print(f"deployment contract error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
