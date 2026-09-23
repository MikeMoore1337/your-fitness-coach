from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

POLICY_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "deploy"
    / "production"
    / "journald"
    / "90-yfc-retention.conf"
)
DROP_IN_NAME = "99-yfc-retention.conf"
DROP_IN_RELATIVE = Path("etc/systemd/journald.conf.d") / DROP_IN_NAME
EXPECTED_POLICY = (
    b"[Journal]\n"
    b"SystemMaxUse=256M\n"
    b"SystemKeepFree=3G\n"
    b"RuntimeMaxUse=64M\n"
    b"MaxRetentionSec=14day\n"
    b"Compress=yes\n"
)
EXPECTED_SETTINGS = {
    "SystemMaxUse": "256M",
    "SystemKeepFree": "3G",
    "RuntimeMaxUse": "64M",
    "MaxRetentionSec": "14day",
    "Compress": "yes",
}
APPLICATION_SERVICES = frozenset(
    {
        "backend",
        "backend-blue",
        "backend-green",
        "worker",
        "worker-blue",
        "worker-green",
        "bot",
        "bot-blue",
        "bot-green",
    }
)
APPLICATION_CATEGORIES = frozenset({"backend", "worker", "bot"})
APPLICATION_LOG_OPTIONS = {"max-size": "10m", "max-file": "5"}
PERSISTENT_LIMIT_BYTES = 256 * 1024 * 1024
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_JOURNAL_SIZE = re.compile(
    r"\btake up\s+(?P<number>[0-9]+(?:\.[0-9]+)?)\s*"
    r"(?P<unit>[KMGT]?i?B|[KMGT])\b",
    re.IGNORECASE,
)
CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


class RetentionError(RuntimeError):
    """A fail-closed production log-retention configuration or verification error."""


def _is_reparse(entry: os.stat_result) -> bool:
    return stat.S_ISLNK(entry.st_mode) or bool(
        getattr(entry, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT
    )


def _run(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    environment = {
        "LC_ALL": "C",
        "PATH": os.environ.get("PATH", os.defpath),
        "SYSTEMD_PAGER": "cat",
        "PAGER": "cat",
    }
    try:
        result = subprocess.run(
            list(arguments),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RetentionError(f"{Path(arguments[0]).name} could not complete") from error
    if result.returncode:
        raise RetentionError(f"{Path(arguments[0]).name} failed with status {result.returncode}")
    return result


def _read_policy(source: Path) -> bytes:
    try:
        source_stat = source.lstat()
        if _is_reparse(source_stat) or not stat.S_ISREG(source_stat.st_mode):
            raise RetentionError("The source journald policy must be a regular file")
        content = source.read_bytes()
    except OSError as error:
        raise RetentionError("The source journald policy is unavailable") from error
    if content != EXPECTED_POLICY:
        raise RetentionError("The source journald policy does not match the approved settings")
    return content


def _directory(path: Path, *, create: bool = False) -> None:
    try:
        entry = path.lstat()
    except FileNotFoundError:
        if not create:
            raise RetentionError(f"Required systemd directory is missing: {path}")
        try:
            path.mkdir(mode=0o755)
        except FileExistsError:
            pass
        except OSError as error:
            raise RetentionError(f"Cannot create the journald drop-in directory: {path}") from error
        entry = path.lstat()
    except OSError as error:
        raise RetentionError(f"Cannot inspect systemd directory: {path}") from error
    if not stat.S_ISDIR(entry.st_mode) or _is_reparse(entry):
        raise RetentionError(f"Unsafe systemd directory: {path}")


def _systemd_parent(root: Path) -> Path:
    if not root.is_absolute():
        raise RetentionError("The production root must be absolute")
    _directory(root)
    etc = root / "etc"
    systemd = etc / "systemd"
    _directory(etc)
    _directory(systemd)
    return systemd


def _prepare_directory(root: Path, *, create: bool) -> Path:
    systemd = _systemd_parent(root)
    drop_in_dir = systemd / "journald.conf.d"
    _directory(drop_in_dir, create=create)
    return drop_in_dir


def _target_state(target: Path) -> tuple[bytes | None, int | None]:
    try:
        entry = target.lstat()
    except FileNotFoundError:
        return None, None
    except OSError as error:
        raise RetentionError("Cannot inspect the YFC journald drop-in") from error
    if _is_reparse(entry) or not stat.S_ISREG(entry.st_mode):
        raise RetentionError("The YFC journald drop-in must be a regular non-symlink file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags)
        with os.fdopen(descriptor, "rb") as policy_file:
            opened = os.fstat(policy_file.fileno())
            if _is_reparse(opened) or not stat.S_ISREG(opened.st_mode):
                raise RetentionError("The YFC journald drop-in changed to an unsafe file type")
            return policy_file.read(), stat.S_IMODE(opened.st_mode)
    except OSError as error:
        raise RetentionError("Cannot safely read the YFC journald drop-in") from error


def _atomic_write(target: Path, content: bytes, mode: int = 0o644) -> None:
    temporary_name: str | None = None
    descriptor: int | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        with os.fdopen(descriptor, "wb") as temporary:
            descriptor = None
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            os.fchmod(temporary.fileno(), mode)
        _target_state(target)
        os.replace(temporary_name, target)
        temporary_name = None
        if os.name == "posix":
            directory_fd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except OSError as error:
        raise RetentionError("Cannot atomically install the YFC journald drop-in") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def _restore_target(target: Path, previous: bytes | None, mode: int | None) -> None:
    current, _current_mode = _target_state(target)
    if previous is None:
        if current is not None:
            target.unlink()
        return
    _atomic_write(target, previous, mode if mode is not None else 0o644)


def _effective_settings(output: str) -> dict[str, str]:
    section = ""
    settings: dict[str, str] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
        elif section == "Journal" and "=" in line:
            key, value = line.split("=", 1)
            if key in EXPECTED_SETTINGS:
                settings[key] = value.strip()
    return settings


def _verify_effective(run: CommandRunner) -> dict[str, str]:
    result = run(["systemd-analyze", "cat-config", "systemd/journald.conf"])
    actual = _effective_settings(result.stdout)
    if actual != EXPECTED_SETTINGS:
        raise RetentionError("Merged journald settings do not match the approved YFC policy")
    return actual


def _journal_usage_bytes(run: CommandRunner) -> int:
    result = run(["journalctl", "--disk-usage"])
    match = _JOURNAL_SIZE.search(result.stdout)
    if match is None:
        raise RetentionError("journalctl returned an unrecognized disk-usage value")
    unit = match.group("unit").upper().replace("IB", "B")
    powers = {"": 0, "B": 0, "K": 1, "KB": 1, "M": 2, "MB": 2, "G": 3, "GB": 3, "T": 4, "TB": 4}
    prefix = unit[:-1] if unit.endswith("B") else unit
    exponent = powers.get(unit, powers.get(prefix))
    if exponent is None:
        raise RetentionError("journalctl returned an unsupported disk-usage unit")
    return int(float(match.group("number")) * (1024**exponent))


def _active(run: CommandRunner) -> None:
    result = run(["systemctl", "is-active", "systemd-journald"])
    if result.stdout.strip() != "active":
        raise RetentionError("systemd-journald is not active")


def _configure_journald(
    *,
    source: Path = POLICY_SOURCE,
    root: Path = Path("/"),
    run: CommandRunner = _run,
    effective_uid: int | None = None,
) -> dict[str, object]:
    # Validate all repository-controlled input before touching any system location.
    policy = _read_policy(source)
    uid = os.geteuid() if effective_uid is None and hasattr(os, "geteuid") else effective_uid
    if uid not in {0}:
        raise RetentionError("Installing a missing or changed journald policy requires root")

    _systemd_parent(root)
    usage_before = _journal_usage_bytes(run)
    drop_in_dir = _prepare_directory(root, create=True)
    target = drop_in_dir / DROP_IN_NAME
    previous, previous_mode = _target_state(target)
    changed = previous != policy
    if changed:
        _atomic_write(target, policy)
    elif os.name == "posix" and previous_mode != 0o644:
        target.chmod(0o644)

    try:
        effective = _verify_effective(run)
    except RetentionError:
        if changed:
            try:
                _restore_target(target, previous, previous_mode)
            except RetentionError as restore_error:
                raise RetentionError(
                    "Effective journald verification failed and the prior drop-in could not be restored"
                ) from restore_error
        raise

    restarted = False
    if changed:
        try:
            run(["systemctl", "restart", "systemd-journald"])
            restarted = True
            _active(run)
        except RetentionError as activation_error:
            try:
                _restore_target(target, previous, previous_mode)
                run(["systemctl", "restart", "systemd-journald"])
                _active(run)
            except RetentionError as restore_error:
                raise RetentionError(
                    "Journald activation failed and the prior policy could not be restored"
                ) from restore_error
            raise activation_error
    else:
        _active(run)
    usage_after = _journal_usage_bytes(run)
    vacuumed = False
    if usage_after > PERSISTENT_LIMIT_BYTES:
        run(["journalctl", "--rotate"])
        run(["journalctl", "--vacuum-time=14days", "--vacuum-size=256M"])
        usage_after = _journal_usage_bytes(run)
        vacuumed = True

    return {
        "policy_version": 1,
        "desired_settings": effective,
        "drop_in_installed": True,
        "changed": changed,
        "services_restarted": ["systemd-journald"] if restarted else [],
        "journald_active": True,
        "persistent_journal_directory_present": (root / "var/log/journal").is_dir(),
        "runtime_journal_directory_present": (root / "run/log/journal").is_dir(),
        "journal_usage_before_bytes": usage_before,
        "journal_usage_after_bytes": usage_after,
        "vacuumed": vacuumed,
        "usage_above_persistent_cap_after_vacuum": vacuumed
        and usage_after > PERSISTENT_LIMIT_BYTES,
    }


def _verify_installed_journald(
    *,
    source: Path = POLICY_SOURCE,
    root: Path = Path("/"),
    run: CommandRunner = _run,
) -> dict[str, object]:
    policy = _read_policy(source)
    systemd_parent = _systemd_parent(root)
    drop_in_dir = systemd_parent / "journald.conf.d"
    try:
        _directory(drop_in_dir)
    except RetentionError as error:
        if not drop_in_dir.exists() and not drop_in_dir.is_symlink():
            raise RetentionError(
                "The approved YFC journald policy is not installed; root provisioning is required"
            ) from error
        raise
    target = drop_in_dir / DROP_IN_NAME
    installed, mode = _target_state(target)
    if installed != policy or (os.name == "posix" and mode != 0o644):
        raise RetentionError(
            "The approved YFC journald policy is not installed; root provisioning is required"
        )
    effective = _verify_effective(run)
    _active(run)
    usage = _journal_usage_bytes(run)
    if usage > PERSISTENT_LIMIT_BYTES:
        raise RetentionError(
            "Journal usage exceeds policy and requires privileged bounded vacuuming"
        )
    return {
        "policy_version": 1,
        "desired_settings": effective,
        "drop_in_installed": True,
        "changed": False,
        "services_restarted": [],
        "journald_active": True,
        "persistent_journal_directory_present": (root / "var/log/journal").is_dir(),
        "runtime_journal_directory_present": (root / "run/log/journal").is_dir(),
        "journal_usage_before_bytes": usage,
        "journal_usage_after_bytes": usage,
        "vacuumed": False,
        "usage_above_persistent_cap_after_vacuum": False,
    }


def _verify_application_logs(run: CommandRunner) -> dict[str, object]:
    default_driver = run(["docker", "info", "--format", "{{.LoggingDriver}}"])
    if default_driver.stdout.strip() != "json-file":
        raise RetentionError(
            "The Docker default logging driver changed from the measured json-file driver"
        )
    container_ids = run(
        [
            "docker",
            "ps",
            "--filter",
            "label=com.docker.compose.project=fit-mini-app",
            "--format",
            "{{.ID}}",
        ]
    ).stdout.splitlines()
    checked: list[dict[str, str]] = []
    counts = dict.fromkeys(APPLICATION_CATEGORIES, 0)
    for container_id in container_ids:
        result = run(
            [
                "docker",
                "inspect",
                "--format",
                '{{.Name}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.HostConfig.LogConfig.Type}}|{{json .HostConfig.LogConfig.Config}}',
                container_id,
            ]
        )
        fields = result.stdout.strip().split("|", maxsplit=3)
        if len(fields) != 4:
            raise RetentionError("Docker returned invalid application container metadata")
        name, service, driver, raw_options = fields
        if service not in APPLICATION_SERVICES:
            continue
        try:
            options = json.loads(raw_options)
        except json.JSONDecodeError as error:
            raise RetentionError("Docker returned invalid application logging options") from error
        if driver != "json-file" or options != APPLICATION_LOG_OPTIONS:
            raise RetentionError(f"Application logging policy is incorrect for service {service}")
        category = service.removesuffix("-blue").removesuffix("-green")
        counts[category] += 1
        checked.append(
            {
                "container": name.lstrip("/"),
                "service": service,
                "driver": driver,
                "max-size": options["max-size"],
                "max-file": options["max-file"],
            }
        )
    if any(count != 1 for count in counts.values()):
        raise RetentionError("Expected one active backend, worker, and bot application container")
    return {
        "docker_default_driver": "json-file",
        "application_containers": checked,
    }


def _production_systemd_host() -> bool:
    return sys.platform == "linux" and Path("/run/systemd/system").is_dir()


def main(argv: Sequence[str] | None = None, *, output: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ensure or verify bounded YFC production logs")
    parser.add_argument("--revision", required=True, help="exact deployed 40-character revision")
    parser.add_argument(
        "--verify-application-logs",
        action="store_true",
        help="verify active Compose application container LogConfig after rollout",
    )
    arguments = parser.parse_args(argv)
    if re.fullmatch(r"[0-9a-f]{40}", arguments.revision) is None:
        parser.error("--revision must be a full lowercase Git commit SHA")
    if not _production_systemd_host():
        raise SystemExit("production log retention requires a Linux host running systemd")
    try:
        if arguments.verify_application_logs:
            result: dict[str, object] = _verify_application_logs(_run)
        else:
            uid = os.geteuid() if hasattr(os, "geteuid") else None
            result = (
                _configure_journald(effective_uid=uid) if uid == 0 else _verify_installed_journald()
            )
        result["captured_at_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
        result["deployed_revision"] = arguments.revision
        (output or sys.stdout).write(json.dumps(result, sort_keys=True) + "\n")
    except RetentionError as error:
        raise SystemExit(str(error)) from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
