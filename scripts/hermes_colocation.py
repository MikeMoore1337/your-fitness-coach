"""Install the isolated Hermes runtime without coupling it to the YFC Compose app."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

IMAGE_REF_PATTERN = re.compile(r"^(?:sha256:[0-9a-f]{64}|[^\s@]+@sha256:[0-9a-f]{64})$")
HERMES_UID = 10000
HERMES_GID = 10000
DEFAULT_DEPLOYMENT_LOCK = "/srv/yfc/fit-mini-app/.artifacts/operations/deployments/deployment.lock"
WORKER_ENV_NAMES = frozenset(
    {
        "HERMES_WORKER_IMAGE",
        "HERMES_PROVIDER_BASE_URL",
        "HERMES_PROVIDER_API_KEY",
        "HERMES_PROVIDER_MODEL",
        "HERMES_PROVIDER_TIMEOUT_SECONDS",
        "HERMES_PROVIDER_MAX_ATTEMPTS",
        "HERMES_PROVIDER_RETRY_BACKOFF_SECONDS",
        "YFC_INTAKE_URL",
        "YFC_HERMES_KEY_ID",
        "YFC_HERMES_SHARED_SECRET",
        "YFC_INTAKE_TIMEOUT_SECONDS",
    }
)


class ColocationError(RuntimeError):
    """Installation stopped before an unsafe host mutation."""


def validate_image_ref(value: str) -> str:
    if (
        not isinstance(value, str)
        or IMAGE_REF_PATTERN.fullmatch(value) is None
        or "latest" in value.casefold()
    ):
        raise ColocationError("image reference must be an immutable digest or image ID")
    return value


def _run(
    args: list[str], *, check: bool = True, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, capture_output=capture, text=True, shell=False)


def _atomic_copy(source: Path, target: Path, *, mode: int, uid: int, gid: int) -> None:
    if source.is_symlink() or not source.is_file():
        raise ColocationError(f"source artifact is not a regular file: {source}")
    if target.is_symlink():
        raise ColocationError(f"target artifact is a symlink: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=target.parent, prefix=f".{target.name}.", delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        shutil.copyfile(source, temporary)
        os.chmod(temporary, mode)
        if hasattr(os, "chown"):
            os.chown(temporary, uid, gid)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _prepare_directory(path: Path, *, mode: int, uid: int, gid: int) -> None:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ColocationError(f"unsafe Hermes directory: {path}")
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, mode)
    if hasattr(os, "chown"):
        os.chown(path, uid, gid)


def _env_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        value = value.removeprefix("export ").strip()
        name, separator, _ = value.partition("=")
        if separator and re.fullmatch(r"[A-Z][A-Z0-9_]+", name):
            values[name] = value[len(name) + 1 :]
    return values


def _env_names(path: Path) -> set[str]:
    return set(_env_values(path))


def _env_value_is_nonempty(value: str) -> bool:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return bool(value)


def validate_worker_env(path: Path) -> set[str]:
    if path.is_symlink() or not path.is_file():
        raise ColocationError("worker.env must be a regular file")
    if path.name == ".env" or path.resolve() == Path("/srv/yfc/fit-mini-app/.env"):
        raise ColocationError("YFC application .env cannot be used as Hermes worker.env")
    if os.name == "posix" and path.stat().st_mode & 0o777 != 0o600:
        raise ColocationError("worker.env must have mode 0600 before installation")
    names = _env_names(path)
    missing = sorted(WORKER_ENV_NAMES - names)
    if missing:
        raise ColocationError(f"worker.env is missing required variable names: {','.join(missing)}")
    unexpected = sorted(names - WORKER_ENV_NAMES)
    if unexpected:
        raise ColocationError(
            f"worker.env contains unexpected variable names: {','.join(unexpected)}"
        )
    values = _env_values(path)
    empty = sorted(name for name in WORKER_ENV_NAMES if not _env_value_is_nonempty(values[name]))
    if empty:
        raise ColocationError(f"worker.env contains empty required values: {','.join(empty)}")
    return names


def validate_definitions(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ColocationError("source definitions must be a regular file")
    raw = path.read_bytes()
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ColocationError("source definitions are not valid JSON") from exc
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != "hermes-source-definitions-v1"
        or not isinstance(document.get("sources"), list)
        or not document["sources"]
    ):
        raise ColocationError("source definitions contract is invalid")
    registry_hash = document.get("source_registry_sha256")
    definitions_version = document.get("definitions_version")
    if (
        not isinstance(registry_hash, str)
        or not isinstance(definitions_version, str)
        or definitions_version != f"yfc-news-sources:{registry_hash}"
    ):
        raise ColocationError("source definitions provenance is invalid")
    return hashlib.sha256(raw).hexdigest()


def _docker_inspect(name: str) -> list[dict[str, Any]]:
    result = _run(["docker", "network", "inspect", name], capture=True)
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ColocationError("Docker network inspection returned invalid JSON") from exc
    if not isinstance(value, list) or not value or not isinstance(value[0], dict):
        raise ColocationError("Docker network inspection returned no network")
    return value


def verify_image(value: str, *, role: str) -> None:
    result = _run(
        ["docker", "image", "inspect", value, "--format", "{{json .}}"],
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        raise ColocationError(f"{role} image is not present on the target host")
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ColocationError(f"{role} image inspection returned invalid JSON") from exc
    if not isinstance(document, dict):
        raise ColocationError(f"{role} image inspection returned invalid metadata")
    image_id = document.get("Id")
    repo_digests = document.get("RepoDigests")
    if value.startswith("sha256:"):
        matches = image_id == value
    else:
        matches = isinstance(repo_digests, list) and value in repo_digests
    if not matches:
        raise ColocationError(f"{role} image metadata does not match the pinned reference")


def _network_subnets(
    document: dict[str, Any],
) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    subnets: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for config in (document.get("IPAM") or {}).get("Config") or []:
        if not isinstance(config, dict) or not isinstance(config.get("Subnet"), str):
            continue
        try:
            subnets.append(ipaddress.ip_network(config["Subnet"], strict=False))
        except ValueError as exc:
            raise ColocationError("Docker network has invalid subnet") from exc
    return subnets


def ensure_network(name: str = "hermes-net", *, mode: str = "colocated-isolated") -> list[str]:
    existing = _run(["docker", "network", "inspect", name], check=False, capture=True)
    if existing.returncode != 0:
        _run(
            [
                "docker",
                "network",
                "create",
                "--driver",
                "bridge",
                "--label",
                f"yfc.hermes.mode={mode}",
                name,
            ]
        )
    documents = _docker_inspect(name)
    network = documents[0]
    if network.get("Driver") != "bridge":
        raise ColocationError("hermes-net must use the bridge driver")
    containers = network.get("Containers") or {}
    if any("fit-mini-app" in str(item.get("Name", "")) for item in containers.values()):
        raise ColocationError("hermes-net is attached to a YFC container")
    hermes_subnets = _network_subnets(network)
    if not hermes_subnets:
        raise ColocationError("hermes-net has no inspectable subnet")
    names = _run(
        ["docker", "network", "ls", "--format", "{{.Name}}"], capture=True
    ).stdout.splitlines()
    for other in names:
        if other == name:
            continue
        for document in _docker_inspect(other):
            if any(
                left.overlaps(right)
                for left in hermes_subnets
                for right in _network_subnets(document)
            ):
                raise ColocationError(f"hermes-net subnet overlaps Docker network {other}")
    return [str(value) for value in hermes_subnets]


def _ensure_identity() -> None:
    geteuid = getattr(os, "geteuid", None)
    if os.name != "posix" or not callable(geteuid) or geteuid() != 0:
        raise ColocationError("Hermes installation must run as root on Linux")
    for command, expected in (
        (["getent", "passwd", str(HERMES_UID)], "hermes"),
        (["getent", "group", str(HERMES_GID)], "hermes"),
    ):
        result = _run(command, check=False, capture=True)
        if result.returncode == 0 and not result.stdout.startswith(f"{expected}:"):
            raise ColocationError("UID/GID 10000 is already assigned to another identity")
    user = _run(["id", "-u", "hermes"], check=False, capture=True)
    if user.returncode != 0:
        group = _run(["getent", "group", str(HERMES_GID)], check=False, capture=True)
        if group.returncode != 0:
            _run(["groupadd", "--system", "--gid", str(HERMES_GID), "hermes"])
        _run(
            [
                "useradd",
                "--system",
                "--uid",
                str(HERMES_UID),
                "--gid",
                str(HERMES_GID),
                "--home-dir",
                "/var/lib/hermes",
                "--no-create-home",
                "--shell",
                "/usr/sbin/nologin",
                "hermes",
            ]
        )
    elif user.stdout.strip() != str(HERMES_UID):
        raise ColocationError("existing hermes user does not have UID 10000")
    group = _run(["id", "-g", "hermes"], check=False, capture=True)
    if group.returncode != 0 or group.stdout.strip() != str(HERMES_GID):
        raise ColocationError("existing hermes group does not have GID 10000")
    passwd = _run(["getent", "passwd", "hermes"], capture=True).stdout.strip().split(":")
    if len(passwd) < 7 or passwd[6] != "/usr/sbin/nologin":
        raise ColocationError("hermes must use /usr/sbin/nologin")
    _run(["usermod", "--lock", "--shell", "/usr/sbin/nologin", "hermes"])
    groups = _run(["id", "-nG", "hermes"], capture=True).stdout.split()
    if "docker" in groups:
        raise ColocationError("hermes must not belong to the docker group")


def _render_units(
    source_root: Path,
    target_root: Path,
    *,
    definitions_digest: str,
    discovery_image: str,
    mode: str,
    deployment_lock: str,
) -> None:
    source = source_root / "deploy" / "hermes-discovery" / "systemd"
    target_root.mkdir(parents=True, exist_ok=True)
    replacements = {
        "@SOURCE_DEFINITIONS_SHA256@": definitions_digest,
        "@DISCOVERY_IMAGE@": discovery_image,
        "@HERMES_DEPLOYMENT_MODE@": mode,
        "@COLOCATED_ISOLATED_HERMES@": "yes" if mode == "colocated-isolated" else "no",
        "@HERMES_YFC_DEPLOYMENT_LOCK@": deployment_lock,
    }
    for name in ("hermes-discovery.service.template", "hermes-worker-drain.service.template"):
        rendered = (source / name).read_text(encoding="utf-8")
        for marker, value in replacements.items():
            rendered = rendered.replace(marker, value)
        if any(marker in rendered for marker in replacements):
            raise ColocationError(f"unresolved systemd template marker in {name}")
        _atomic_copy_text(rendered, target_root / name.removesuffix(".template"), mode=0o644)
    for name in ("hermes-discovery.target", "hermes-discovery.timer"):
        _atomic_copy_text(
            (source / name).read_text(encoding="utf-8"), target_root / name, mode=0o644
        )


def _atomic_copy_text(value: str, target: Path, *, mode: int) -> None:
    if target.is_symlink():
        raise ColocationError(f"target artifact is a symlink: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=target.parent, prefix=f".{target.name}.", mode="w", encoding="utf-8", delete=False
    ) as handle:
        handle.write(value)
        temporary = Path(handle.name)
    try:
        os.chmod(temporary, mode)
        if hasattr(os, "chown"):
            os.chown(temporary, 0, 0)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def install(args: argparse.Namespace) -> dict[str, object]:
    discovery_image = validate_image_ref(args.discovery_image)
    worker_image = validate_image_ref(args.worker_image)
    source_root = args.source_root.resolve(strict=True)
    definitions = args.source_definitions.resolve(strict=True)
    worker_env = args.worker_env.resolve(strict=True)
    definitions_digest = validate_definitions(definitions)
    validate_worker_env(worker_env)
    worker_env_values = _env_values(worker_env)
    if worker_env_values.get("HERMES_WORKER_IMAGE") != worker_image:
        raise ColocationError(
            "worker.env HERMES_WORKER_IMAGE does not match the pinned worker image"
        )
    verify_image(discovery_image, role="discovery")
    verify_image(worker_image, role="worker")
    subnets = [] if args.skip_network else ensure_network(mode=args.mode)
    _ensure_identity()
    runtime_root = args.runtime_root
    config_root = args.config_root
    state_root = args.state_root
    _prepare_directory(runtime_root, mode=0o755, uid=0, gid=0)
    _prepare_directory(config_root, mode=0o755, uid=0, gid=0)
    _prepare_directory(state_root, mode=0o700, uid=HERMES_UID, gid=HERMES_GID)
    _prepare_directory(state_root / "outbox", mode=0o700, uid=HERMES_UID, gid=HERMES_GID)
    hermes_root = source_root / "deploy" / "hermes-discovery"
    for name in (
        "discovery_runner.py",
        "hermes_worker_drain.py",
        "hermes_resource_guard.py",
        "hermes_egress.py",
        "hermes-discovery-provenance.json",
        "source-definitions.schema.json",
        "deployment-mode.schema.json",
    ):
        _atomic_copy(hermes_root / name, runtime_root / name, mode=0o444, uid=0, gid=0)
    _atomic_copy(definitions, config_root / "source-definitions.json", mode=0o444, uid=0, gid=0)
    _atomic_copy(worker_env, config_root / "worker.env", mode=0o600, uid=0, gid=0)
    _run(
        [
            sys.executable,
            str(runtime_root / "hermes_egress.py"),
            "refresh",
            "--definitions",
            str(config_root / "source-definitions.json"),
            "--worker-env",
            str(config_root / "worker.env"),
            "--network",
            "hermes-net",
        ]
    )
    _render_units(
        source_root,
        args.systemd_root,
        definitions_digest=definitions_digest,
        discovery_image=discovery_image,
        mode=args.mode,
        deployment_lock="none" if args.mode == "separate-vm" else args.deployment_lock,
    )
    _run(
        [
            "systemd-analyze",
            "verify",
            *(
                str(args.systemd_root / name)
                for name in (
                    "hermes-discovery.service",
                    "hermes-worker-drain.service",
                    "hermes-discovery.target",
                    "hermes-discovery.timer",
                )
            ),
        ]
    )
    _run(["systemctl", "daemon-reload"])
    _run(["systemctl", "disable", "hermes-discovery.timer"], check=False)
    return {
        "status": "installed",
        "mode": args.mode,
        "colocated_isolated_hermes": args.mode == "colocated-isolated",
        "uid_gid": "10000:10000",
        "paths": {
            "runtime": str(runtime_root),
            "config": str(config_root),
            "state": str(state_root),
        },
        "network": "hermes-net",
        "network_subnets": subnets,
        "public_ports": [],
        "images": {"discovery": discovery_image, "worker": worker_image},
        "source_definitions_sha256": definitions_digest,
        "timer_enabled": False,
        "worker_env_names": sorted(WORKER_ENV_NAMES),
        "secrets_logged": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("--source-root", type=Path, required=True)
    install_parser.add_argument("--source-definitions", type=Path, required=True)
    install_parser.add_argument("--worker-env", type=Path, required=True)
    install_parser.add_argument("--discovery-image", required=True)
    install_parser.add_argument("--worker-image", required=True)
    install_parser.add_argument(
        "--mode", choices=("separate-vm", "colocated-isolated"), default="colocated-isolated"
    )
    install_parser.add_argument("--deployment-lock", default=DEFAULT_DEPLOYMENT_LOCK)
    install_parser.add_argument("--runtime-root", type=Path, default=Path("/opt/hermes"))
    install_parser.add_argument("--config-root", type=Path, default=Path("/etc/hermes"))
    install_parser.add_argument("--state-root", type=Path, default=Path("/var/lib/hermes"))
    install_parser.add_argument("--systemd-root", type=Path, default=Path("/etc/systemd/system"))
    install_parser.add_argument("--skip-network", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        print(json.dumps(install(args), ensure_ascii=False, sort_keys=True))
        return 0
    except (ColocationError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Hermes co-location install failed: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
