"""Audit production provenance and reconcile only existing metadata.

The helper reads GitHub/host evidence supplied by the caller and inspects the
running Docker services.  ``reconcile`` may atomically update the existing
marker and ``current`` symlink after every read-only safety check passes; it
never pulls images, starts or stops services, runs migrations, or changes
application configuration.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Collection, Sequence
from pathlib import Path
from typing import cast

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REVISION_LABEL = "org.opencontainers.image.revision"
BOT_RUNTIME_MARKERS = ("polling_file_lock_acquired", "telegram_polling_started")
SERVICES = ("backend", "worker", "bot")
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
ALEMBIC_REVISION_LINE_RE = re.compile(r"(?P<revision>[^\s()]+)(?:\s+\([^)]*\))?")


class ProvenanceError(RuntimeError):
    """Production provenance is not safe to accept."""


def is_full_sha(value: object) -> bool:
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None


def parse_alembic_revisions(output: str) -> set[str]:
    """Extract revision tokens from deterministic ``alembic`` output lines."""

    revisions: set[str] = set()
    for raw_line in output.splitlines():
        line = ANSI_ESCAPE_RE.sub("", raw_line).strip()
        if not line:
            continue
        match = ALEMBIC_REVISION_LINE_RE.fullmatch(line)
        if match:
            revisions.add(match.group("revision"))
    return revisions


def alembic_revisions_are_consistent(current: Collection[str], heads: Collection[str]) -> bool:
    """Return whether current database revisions include every Alembic head."""

    return bool(current) and bool(heads) and set(heads).issubset(current)


def classify_marker_runtime(recorded_revision: object, runtime_revisions: Sequence[object]) -> str:
    """Classify the durable marker against the currently running services."""

    revisions = [value for value in runtime_revisions if isinstance(value, str)]
    if len(revisions) != len(runtime_revisions) or not revisions:
        return "INVALID_RUNTIME"
    if any(not is_full_sha(value) for value in revisions):
        return "INVALID_RUNTIME"
    if len(set(revisions)) != 1:
        return "MIXED_RUNTIME"
    if not is_full_sha(recorded_revision):
        return "INVALID_MARKER"
    if recorded_revision == revisions[0]:
        return "OK"
    return "PROVENANCE_RECONCILIATION_REQUIRED"


def _run(command: Sequence[str]) -> str:
    completed = subprocess.run(
        list(command),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout


def _json_command(command: Sequence[str]) -> object:
    try:
        return json.loads(_run(command))
    except json.JSONDecodeError as exc:
        raise ProvenanceError(f"command returned invalid JSON: {' '.join(command)}") from exc


def _read_revision(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    if not value:
        return None
    return value


def _container_id(service: str) -> str:
    rows = [
        value.strip()
        for value in _run(
            [
                "docker",
                "ps",
                "--filter",
                f"label=com.docker.compose.service={service}",
                "--format",
                "{{.ID}}",
            ]
        ).splitlines()
        if value.strip()
    ]
    if len(rows) != 1:
        raise ProvenanceError(
            f"expected exactly one running {service} container, found {len(rows)}"
        )
    return rows[0]


def _service_snapshot(service: str) -> dict[str, object]:
    container_id = _container_id(service)
    container_payload = _json_command(["docker", "inspect", container_id])
    if not isinstance(container_payload, list) or len(container_payload) != 1:
        raise ProvenanceError(f"docker inspect returned no unique {service} container")
    container = container_payload[0]
    if not isinstance(container, dict):
        raise ProvenanceError(f"docker inspect returned invalid {service} data")
    config = container.get("Config")
    state = container.get("State")
    if not isinstance(config, dict) or not isinstance(state, dict):
        raise ProvenanceError(f"{service} container metadata is incomplete")
    container_image_id = container.get("Image")
    image_ref = config.get("Image")
    if not isinstance(image_ref, str) or not image_ref:
        raise ProvenanceError(f"{service} container image reference is missing")
    image_payload = _json_command(["docker", "image", "inspect", image_ref])
    if not isinstance(image_payload, list) or len(image_payload) != 1:
        raise ProvenanceError(f"docker image inspect returned no unique {service} image")
    image = image_payload[0]
    if not isinstance(image, dict):
        raise ProvenanceError(f"docker image metadata for {service} is invalid")
    labels = image.get("Config", {}).get("Labels", {})
    if not isinstance(labels, dict):
        labels = {}
    revision = labels.get(REVISION_LABEL)
    repo_digests = image.get("RepoDigests", [])
    if not isinstance(repo_digests, list):
        repo_digests = []
    immutable_digests = [
        value.rsplit("@", maxsplit=1)[-1]
        for value in repo_digests
        if isinstance(value, str) and "@" in value and DIGEST_RE.fullmatch(value.rsplit("@", 1)[-1])
    ]
    status = state.get("Status")
    health_payload = state.get("Health")
    health = health_payload.get("Status") if isinstance(health_payload, dict) else None
    result: dict[str, object] = {
        "service": service,
        "container_id": container_id,
        "image_ref": image_ref,
        "container_image_id": container_image_id,
        "image_id": image.get("Id"),
        "revision": revision,
        "repo_digests": sorted(immutable_digests),
        "status": status,
        "health": health,
        "immutable_image": bool(immutable_digests)
        and container_image_id == image.get("Id")
        and isinstance(container_image_id, str)
        and container_image_id.startswith("sha256:"),
    }
    if service in {"backend", "worker"} and health != "healthy":
        raise ProvenanceError(f"{service} health is {health!r}, expected 'healthy'")
    if status != "running":
        raise ProvenanceError(f"{service} status is {status!r}, expected 'running'")
    if not is_full_sha(revision):
        raise ProvenanceError(f"{service} OCI revision is not a full lowercase Git SHA")
    if not immutable_digests:
        raise ProvenanceError(f"{service} image has no immutable RepoDigest")
    if not result["immutable_image"]:
        raise ProvenanceError(f"{service} container does not match its immutable image ID")
    if image_ref.rsplit(":", maxsplit=1)[-1] != revision:
        raise ProvenanceError(f"{service} image tag does not match OCI revision {revision}")
    if service == "bot":
        logs = _run(["docker", "logs", "--tail", "200", container_id])
        runtime_markers = {marker: marker in logs for marker in BOT_RUNTIME_MARKERS}
        result["runtime_markers"] = runtime_markers
        if not all(runtime_markers.values()):
            raise ProvenanceError("bot polling ownership markers are not present in current logs")
    return result


def _database_snapshot(container_id: str) -> dict[str, object]:
    current = _run(["docker", "exec", container_id, "alembic", "current"])
    heads = _run(["docker", "exec", container_id, "alembic", "heads"])
    current_revisions = sorted(parse_alembic_revisions(current))
    head_revisions = sorted(parse_alembic_revisions(heads))
    consistent = alembic_revisions_are_consistent(current_revisions, head_revisions)
    return {
        "current": current.strip(),
        "heads": heads.strip(),
        "current_revisions": current_revisions,
        "head_revisions": head_revisions,
        "consistent": consistent,
    }


def _summaries(state_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(
        state_root.glob("*/summary.json"), key=lambda item: item.stat().st_mtime, reverse=True
    )[:20]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            rows.append({"path": str(path), "error": f"{type(exc).__name__}: {exc}"})
            continue
        rows.append(
            {
                "path": str(path),
                "target_revision": payload.get("target_revision")
                if isinstance(payload, dict)
                else None,
                "previous_revision": payload.get("previous_revision")
                if isinstance(payload, dict)
                else None,
                "verdict": payload.get("verdict") if isinstance(payload, dict) else None,
            }
        )
    return rows


def inspect_production(app_root: Path) -> dict[str, object]:
    """Read the host state without changing it."""

    state_root = app_root / ".artifacts" / "operations" / "deployments"
    marker_path = state_root / "last-successful-revision"
    recorded_revision = _read_revision(marker_path)
    services: dict[str, dict[str, object]] = {}
    errors: list[str] = []
    for service in SERVICES:
        try:
            services[service] = _service_snapshot(service)
        except (OSError, ProvenanceError, subprocess.CalledProcessError) as exc:
            services[service] = {"service": service, "error": f"{type(exc).__name__}: {exc}"}
            errors.append(f"{service}: {exc}")

    revisions = [
        services[service].get("revision") for service in SERVICES if "revision" in services[service]
    ]
    valid_revisions = [value for value in revisions if isinstance(value, str)]
    runtime_revision = (
        valid_revisions[0]
        if len(valid_revisions) == len(SERVICES) and len(set(valid_revisions)) == 1
        else None
    )
    status = classify_marker_runtime(recorded_revision, revisions)
    if errors:
        status = "INVALID_RUNTIME"

    current_path = app_root / "current"
    current_target: str | None = None
    current_error: str | None = None
    if current_path.is_symlink():
        try:
            current_target = str(current_path.resolve(strict=True))
        except OSError as exc:
            current_error = f"{type(exc).__name__}: {exc}"
            errors.append(f"current symlink: {exc}")
    elif current_path.exists():
        current_error = "current is not a symlink"
        errors.append(current_error)

    release_path = (
        app_root / "releases" / runtime_revision if isinstance(runtime_revision, str) else None
    )
    release_sha = _read_revision(release_path / ".deployment-sha") if release_path else None
    release_ok = bool(release_path and release_path.is_dir() and release_sha == runtime_revision)
    if runtime_revision and not release_ok:
        errors.append(f"immutable release for runtime {runtime_revision} is missing or mismatched")

    database: dict[str, object] = {"consistent": False, "error": "backend container unavailable"}
    backend = services.get("backend", {})
    backend_id = backend.get("container_id")
    if isinstance(backend_id, str):
        try:
            database = _database_snapshot(backend_id)
            if not database["consistent"]:
                errors.append("database migration state is not at a known Alembic head")
        except (OSError, ProvenanceError, subprocess.CalledProcessError) as exc:
            database = {"consistent": False, "error": f"{type(exc).__name__}: {exc}"}
            errors.append(f"database: {exc}")

    return {
        "status": status,
        "recorded_revision": recorded_revision,
        "runtime_revision": runtime_revision,
        "runtime_revisions": revisions,
        "runtime_uniform": runtime_revision is not None,
        "services": services,
        "release": {
            "path": str(release_path) if release_path else None,
            "deployment_sha": release_sha,
            "exists_and_matches": release_ok,
        },
        "current": {"target": current_target, "error": current_error},
        "database": database,
        "summaries": _summaries(state_root),
        "errors": errors,
    }


def _verification_errors(snapshot: dict[str, object], expected_revision: str) -> list[str]:
    errors: list[str] = []
    if not is_full_sha(expected_revision):
        errors.append("requested revision must be a full lowercase Git SHA")
    if snapshot.get("runtime_revision") != expected_revision:
        errors.append(
            f"runtime revision {snapshot.get('runtime_revision')!r} does not match requested {expected_revision}"
        )
    if not snapshot.get("runtime_uniform"):
        errors.append("runtime services are not uniform")
    if snapshot.get("status") in {"MIXED_RUNTIME", "INVALID_RUNTIME", "INVALID_MARKER"}:
        errors.append(f"runtime provenance status is {snapshot.get('status')}")
    services = snapshot.get("services")
    if not isinstance(services, dict) or set(services) != set(SERVICES):
        errors.append("backend, worker and bot service evidence is incomplete")
    else:
        for service in SERVICES:
            raw_data = services.get(service)
            data = cast(dict[str, object], raw_data) if isinstance(raw_data, dict) else {}
            if not isinstance(data, dict) or data.get("error"):
                errors.append(f"{service} runtime evidence is invalid")
                continue
            if data.get("revision") != expected_revision:
                errors.append(f"{service} OCI revision does not match requested revision")
            if not data.get("immutable_image"):
                errors.append(f"{service} image is not immutable")
    release = snapshot.get("release")
    if not isinstance(release, dict) or not release.get("exists_and_matches"):
        errors.append("requested immutable release directory is not verified")
    database = snapshot.get("database")
    if not isinstance(database, dict) or database.get("consistent") is not True:
        errors.append("database/migration state is not verified")
    snapshot_errors = snapshot.get("errors")
    if isinstance(snapshot_errors, list):
        errors.extend(str(error) for error in snapshot_errors)
    return list(dict.fromkeys(errors))


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise


def _atomic_symlink(link: Path, target: Path) -> None:
    temporary = link.with_name(f".{link.name}.reconcile")
    with contextlib.suppress(FileNotFoundError):
        temporary.unlink()
    os.symlink(target, temporary, target_is_directory=True)
    os.replace(temporary, link)


def reconcile(app_root: Path, expected_revision: str) -> dict[str, object]:
    snapshot = inspect_production(app_root)
    errors = _verification_errors(snapshot, expected_revision)
    if errors:
        raise ProvenanceError("; ".join(errors))
    release = snapshot["release"]
    assert isinstance(release, dict)
    release_path = Path(str(release["path"]))
    state_root = app_root / ".artifacts" / "operations" / "deployments"
    marker = state_root / "last-successful-revision"
    previous_marker = snapshot.get("recorded_revision")
    _atomic_text(marker, expected_revision + "\n")
    current = app_root / "current"
    current_snapshot = snapshot.get("current")
    previous_current = (
        current_snapshot.get("target") if isinstance(current_snapshot, dict) else None
    )
    if previous_current != str(release_path):
        _atomic_symlink(current, release_path)
    return {
        "status": "RECONCILED",
        "recorded_revision": previous_marker,
        "runtime_revision": expected_revision,
        "post_marker": _read_revision(marker),
        "post_current": str(current.resolve(strict=True)),
        "application_mutation": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("snapshot", "verify", "reconcile"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--app-root", type=Path, required=True)
        if command != "snapshot":
            subparser.add_argument("--expected-revision", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "snapshot":
            result = inspect_production(args.app_root)
        elif args.command == "verify":
            result = inspect_production(args.app_root)
            errors = _verification_errors(result, args.expected_revision)
            if errors:
                raise ProvenanceError("; ".join(errors))
            result["status"] = "VERIFIED"
        else:
            result = reconcile(args.app_root, args.expected_revision)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ProvenanceError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
