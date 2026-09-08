"""Fail-closed production rollouts for the current single-host Docker Compose stack."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - production deployment runs on Linux
    fcntl = None  # type: ignore[assignment]

SLOTS = ("blue", "green")
STATE_VERSION = 1


class DeploymentError(RuntimeError):
    """The rollout stopped without an unverified traffic state."""


REGISTRY_PULL_ATTEMPTS = 5
REGISTRY_PULL_BASE_DELAY_SECONDS = 10


@dataclass(frozen=True)
class ReleaseState:
    version: int
    active_slot: str
    active_revision: str
    active_backend_image: str
    active_bot_image: str
    rollback_slot: str | None = None
    rollback_revision: str | None = None
    rollback_backend_image: str | None = None
    rollback_bot_image: str | None = None

    @classmethod
    def from_path(cls, path: Path) -> ReleaseState:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            state = cls(**value)
        except (OSError, TypeError, json.JSONDecodeError) as exc:
            raise DeploymentError(f"cannot read deployment state {path}: {exc}") from exc
        if state.version != STATE_VERSION or state.active_slot not in {"legacy", *SLOTS}:
            raise DeploymentError(f"unsupported deployment state in {path}")
        return state


@dataclass(frozen=True)
class DeployConfig:
    target_revision: str
    base_url: str
    public_base_url: str
    backend_image: str
    bot_image: str
    root: Path
    state_root: Path
    observation_seconds: float
    readiness_timeout_seconds: int
    probe_interval_seconds: float
    probe_timeout_seconds: float
    seo_timeout_seconds: float
    backend_drain_seconds: int
    worker_drain_seconds: int
    bot_drain_seconds: int
    bot_polling_enabled: bool


@dataclass(frozen=True)
class ConsumerLease:
    service: str
    container_id: str
    started_at: str
    required_markers: tuple[str, ...]


@dataclass
class StageRecord:
    name: str
    started_at: float
    ended_at: float = 0.0
    status: str = "running"
    reason: str | None = None


@dataclass
class Evidence:
    deployment_id: str
    target_revision: str
    previous_revision: str
    active_slot: str
    candidate_slot: str
    started_at: float
    ended_at: float = 0.0
    verdict: str = "manual intervention required"
    stages: list[StageRecord] = field(default_factory=list)
    capacity: dict[str, int] = field(default_factory=dict)
    probe: dict[str, object] = field(default_factory=dict)
    worker_handoff_seconds: float | None = None
    bot_handoff_seconds: float | None = None


def _deployment_setting(key: str, default: str) -> str:
    if key in os.environ:
        return os.environ[key]
    env_path = Path(".env")
    if not env_path.is_file():
        return default
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(key)}\s*=\s*(.*?)\s*$")
    value = default
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        match = pattern.match(line)
        if match is None:
            continue
        value = match.group(1).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", maxsplit=1)[0].rstrip()
    return value


def configured_timeout(key: str, default: int) -> int:
    raw = _deployment_setting(key, str(default)).strip()
    match = re.fullmatch(r"([1-9][0-9]*)(?:s)?", raw)
    if match is None:
        raise DeploymentError(f"{key} must be a positive whole number of seconds")
    return int(match.group(1))


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


_IMMUTABLE_IMAGE_REF = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")
_APPLICATION_IMAGE_ASSIGNMENT = re.compile(
    r"^(?:\s*export\s+)?(?P<key>BACKEND_IMAGE|BOT_IMAGE)\s*="
)


def _persist_application_image_refs(path: Path, *, backend_image: str, bot_image: str) -> None:
    """Atomically persist only verified immutable application image references."""

    values = {"BACKEND_IMAGE": backend_image, "BOT_IMAGE": bot_image}
    for key, value in values.items():
        if not _IMMUTABLE_IMAGE_REF.fullmatch(value):
            raise DeploymentError(
                f"{key} must be an immutable image reference ending in @sha256:<64 hex>"
            )
    if not path.is_file():
        raise DeploymentError(f"environment file does not exist: {path}")

    original = path.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in original else "\n"
    trailing_newline = original.endswith(("\n", "\r"))
    seen: set[str] = set()
    updated_lines: list[str] = []
    for line in original.splitlines():
        match = _APPLICATION_IMAGE_ASSIGNMENT.match(line)
        if match is None:
            updated_lines.append(line)
            continue
        key = match.group("key")
        if key not in seen:
            updated_lines.append(f"{key}={values[key]}")
            seen.add(key)

    for key, value in values.items():
        if key not in seen:
            updated_lines.append(f"{key}={value}")

    content = newline.join(updated_lines) + (newline if trailing_newline else "")
    mode = path.stat().st_mode
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def _run(
    args: Sequence[str],
    *,
    env: dict[str, str] | None = None,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        check=check,
        env=env,
        text=True,
        capture_output=capture,
    )


def _compose(*args: str, env: dict[str, str] | None = None, capture: bool = False):
    return _run(
        ["docker", "compose", "--profile", "production-slots", *args],
        env=env,
        capture=capture,
    )


def _pull_images_with_retry(*services: str, env: dict[str, str]) -> None:
    for attempt in range(1, REGISTRY_PULL_ATTEMPTS + 1):
        try:
            _compose("pull", *services, env=env)
            return
        except subprocess.CalledProcessError:
            if attempt == REGISTRY_PULL_ATTEMPTS:
                raise
            delay = REGISTRY_PULL_BASE_DELAY_SECONDS * attempt
            print(
                f"Registry pull attempt {attempt} failed; retrying in {delay} seconds",
                file=sys.stderr,
            )
            time.sleep(delay)


def _slot_service(kind: str, slot: str) -> str:
    return kind if slot == "legacy" else f"{kind}-{slot}"


def _upstream(slot: str) -> str:
    return f"{_slot_service('backend', slot)}:8000"


def _slot_environment(
    slot: str,
    *,
    backend_image: str,
    bot_image: str,
) -> dict[str, str]:
    env = os.environ.copy()
    upper = slot.upper()
    env[f"BACKEND_{upper}_IMAGE"] = backend_image
    env[f"BOT_{upper}_IMAGE"] = bot_image
    return env


def _legacy_environment(*, backend_image: str, bot_image: str) -> dict[str, str]:
    env = os.environ.copy()
    env["BACKEND_IMAGE"] = backend_image
    env["BOT_IMAGE"] = bot_image
    return env


def _online_migration_command(active_revision: str, target_revision: str) -> list[str]:
    command = [
        sys.executable,
        "scripts/check_online_migrations.py",
        active_revision,
        target_revision,
    ]
    manifest = os.environ.get("DEPLOY_MIGRATION_MANIFEST", "").strip()
    if manifest:
        command.extend(["--manifest", manifest])
    return command


def _image_digest(image: str, expected_revision: str) -> str:
    result = _run(
        [
            "docker",
            "image",
            "inspect",
            "--format",
            '{{json .RepoDigests}}|{{index .Config.Labels "org.opencontainers.image.revision"}}',
            image,
        ],
        capture=True,
    ).stdout.strip()
    digests_json, separator, revision = result.partition("|")
    if not separator or revision != expected_revision:
        raise DeploymentError(
            f"image {image} revision {revision!r} does not match {expected_revision}"
        )
    digests = json.loads(digests_json)
    if not isinstance(digests, list) or not digests:
        raise DeploymentError(f"image {image} has no immutable repository digest")
    if image.startswith("sha256:"):
        matching = [value for value in digests if isinstance(value, str)]
    else:
        repository = image.split("@", 1)[0].rsplit(":", 1)[0]
        matching = [
            value for value in digests if isinstance(value, str) and value.startswith(repository)
        ]
    digest = matching[0] if matching else digests[0]
    if not isinstance(digest, str) or "@sha256:" not in digest:
        raise DeploymentError(f"image {image} returned an invalid repository digest")
    return digest


def _capacity() -> dict[str, int]:
    memory_kib = 0
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                memory_kib = int(line.split()[1])
                break
    disk = shutil.disk_usage(Path.cwd())
    report = {
        "cpu_count": os.cpu_count() or 0,
        "memory_available_mb": memory_kib // 1024,
        "disk_available_mb": disk.free // (1024 * 1024),
    }
    minimums = {
        "cpu_count": int(_deployment_setting("DEPLOY_MIN_CPU_COUNT", "2")),
        "memory_available_mb": int(_deployment_setting("DEPLOY_MIN_AVAILABLE_MEMORY_MB", "1536")),
        "disk_available_mb": int(_deployment_setting("DEPLOY_MIN_AVAILABLE_DISK_MB", "4096")),
    }
    missing = {
        key: (report[key], required) for key, required in minimums.items() if report[key] < required
    }
    if missing:
        raise DeploymentError(f"parallel-slot capacity gate failed: {missing}")
    return report


def _single_slot_capacity() -> dict[str, int]:
    memory_kib = 0
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                memory_kib = int(line.split()[1])
                break
    disk = shutil.disk_usage(Path.cwd())
    report = {
        "cpu_count": os.cpu_count() or 0,
        "memory_available_mb": memory_kib // 1024,
        "disk_available_mb": disk.free // (1024 * 1024),
    }
    minimums = {
        "cpu_count": 1,
        "memory_available_mb": 64,
        "disk_available_mb": 2048,
    }
    missing = {
        key: (report[key], required) for key, required in minimums.items() if report[key] < required
    }
    if missing:
        raise DeploymentError(f"single-slot capacity gate failed: {missing}")
    return report


def _reclaim_single_slot_docker_space() -> None:
    """Remove only Docker data that is not referenced by any container."""
    _run(["docker", "image", "prune", "--all", "--force"])
    _run(["docker", "builder", "prune", "--all", "--force"])


@contextlib.contextmanager
def _deployment_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as lock_file:
        if fcntl is None:
            yield
            return
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise DeploymentError("another production deployment owns the host lock") from exc
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _switch_gateway(active_slot: str, fallback_slot: str) -> None:
    gateway_env = [
        "-e",
        f"YFC_ACTIVE_UPSTREAM={_upstream(active_slot)}",
        "-e",
        f"YFC_ASSET_FALLBACK_UPSTREAM={_upstream(fallback_slot)}",
    ]
    base = ["exec", "-T", *gateway_env, "edge", "caddy"]
    _compose(
        *base,
        "validate",
        "--config",
        "/etc/caddy/Caddyfile",
        "--adapter",
        "caddyfile",
    )
    expected_config = json.loads(
        _compose(
            *base,
            "adapt",
            "--config",
            "/etc/caddy/Caddyfile",
            "--adapter",
            "caddyfile",
            capture=True,
        ).stdout
    )
    current_config = json.loads(
        _compose(
            "exec",
            "-T",
            "edge",
            "wget",
            "-qO-",
            "http://127.0.0.1:2019/config/",
            capture=True,
        ).stdout
    )
    if current_config == expected_config:
        return
    deadline = time.monotonic() + float(
        _deployment_setting("DEPLOY_GATEWAY_IDLE_TIMEOUT_SECONDS", "30")
    )
    while time.monotonic() < deadline:
        upstreams = json.loads(
            _compose(
                "exec",
                "-T",
                "edge",
                "wget",
                "-qO-",
                "http://127.0.0.1:2019/reverse_proxy/upstreams",
                capture=True,
            ).stdout
        )
        if isinstance(upstreams, list) and all(
            isinstance(item, dict) and item.get("num_requests") == 0 for item in upstreams
        ):
            break
        time.sleep(0.05)
    else:
        raise DeploymentError("gateway had no bounded request-free switch point")
    _compose(
        *base,
        "reload",
        "--config",
        "/etc/caddy/Caddyfile",
        "--adapter",
        "caddyfile",
    )
    current = _compose(
        "exec",
        "-T",
        "edge",
        "wget",
        "-qO-",
        "http://127.0.0.1:2019/config/",
        capture=True,
    ).stdout
    if _upstream(active_slot) not in current:
        raise DeploymentError("gateway reload returned without the requested active upstream")


def _service_is_running(service: str) -> bool:
    result = _compose("ps", "--status", "running", "--services", service, capture=True)
    return service in result.stdout.splitlines()


def _consumer_lease(service: str, required_markers: tuple[str, ...]) -> ConsumerLease:
    container_id = _compose("ps", "-q", service, capture=True).stdout.strip()
    if not container_id:
        raise DeploymentError(f"{service} has no container for ownership verification")
    started_at = _run(
        ["docker", "inspect", "--format", "{{.State.StartedAt}}", container_id],
        capture=True,
    ).stdout.strip()
    if not started_at:
        raise DeploymentError(f"{service} has no current container start boundary")
    return ConsumerLease(service, container_id, started_at, required_markers)


def _current_run_logs(lease: ConsumerLease) -> str:
    return _compose(
        "logs",
        "--no-color",
        "--since",
        lease.started_at,
        lease.service,
        capture=True,
    ).stdout


def _container_exited_cleanly(lease: ConsumerLease) -> bool:
    state = _run(
        [
            "docker",
            "inspect",
            "--format",
            "{{.State.Status}} {{.State.ExitCode}}",
            lease.container_id,
        ],
        capture=True,
    ).stdout.strip()
    return state == "exited 0"


def _wait_for_ownership(lease: ConsumerLease, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _lease_is_current_and_healthy(lease, require_markers=False):
            raise DeploymentError(f"{lease.service} stopped before ownership confirmation")
        output = _current_run_logs(lease)
        if all(marker in output for marker in lease.required_markers):
            return
        time.sleep(1)
    raise DeploymentError(f"{lease.service} ownership confirmation timed out")


def _lease_is_current_and_healthy(lease: ConsumerLease, *, require_markers: bool = True) -> bool:
    if not _service_is_running(lease.service):
        return False
    current_id = _compose("ps", "-q", lease.service, capture=True).stdout.strip()
    if current_id != lease.container_id:
        return False
    current_started_at = _run(
        ["docker", "inspect", "--format", "{{.State.StartedAt}}", current_id],
        capture=True,
    ).stdout.strip()
    if current_started_at != lease.started_at:
        return False
    health = _run(
        [
            "docker",
            "inspect",
            "--format",
            "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
            current_id,
        ],
        capture=True,
    ).stdout.strip()
    if health not in {"healthy", "running"}:
        return False
    return not require_markers or all(
        marker in _current_run_logs(lease) for marker in lease.required_markers
    )


def _stop_slot_consumers(slot: str, config: DeployConfig, *, require_running: bool = True) -> None:
    worker = _slot_service("worker", slot)
    if _service_is_running(worker):
        worker_lease = _consumer_lease(worker, ("worker_started",))
        _compose("stop", "-t", str(config.worker_drain_seconds), worker)
        if "worker_stopped" not in _current_run_logs(
            worker_lease
        ) and not _container_exited_cleanly(worker_lease):
            raise DeploymentError(
                f"{worker} did not acknowledge a completed drain within "
                f"{config.worker_drain_seconds}s; consumer state is uncertain"
            )
    elif require_running:
        raise DeploymentError(f"{worker} was not running before consumer handoff")
    bot = _slot_service("bot", slot)
    if _service_is_running(bot):
        _compose("stop", "-t", str(config.bot_drain_seconds), bot)
    elif require_running:
        raise DeploymentError(f"{bot} was not running before consumer handoff")


def _start_slot_consumers(
    slot: str,
    *,
    env: dict[str, str],
    evidence: Evidence,
    config: DeployConfig,
) -> tuple[ConsumerLease, ConsumerLease]:
    ownership_timeout = config.readiness_timeout_seconds
    worker = _slot_service("worker", slot)
    started = time.monotonic()
    if slot == "legacy":
        _compose("start", worker)
    else:
        _compose(
            "up",
            "-d",
            "--no-build",
            "--no-deps",
            "--wait",
            "--wait-timeout",
            str(ownership_timeout),
            worker,
            env=env,
        )
    worker_lease = _consumer_lease(worker, ("worker_started",))
    _wait_for_ownership(worker_lease, timeout=ownership_timeout)
    evidence.worker_handoff_seconds = round(time.monotonic() - started, 3)

    bot = _slot_service("bot", slot)
    started = time.monotonic()
    if slot == "legacy":
        _compose("start", bot)
    else:
        _compose("up", "-d", "--no-build", "--no-deps", bot, env=env)
    bot_markers = (
        ("polling_file_lock_acquired", "telegram_polling_started")
        if config.bot_polling_enabled
        else ("polling_disabled",)
    )
    bot_lease = _consumer_lease(bot, bot_markers)
    _wait_for_ownership(bot_lease, timeout=ownership_timeout)
    evidence.bot_handoff_seconds = round(time.monotonic() - started, 3)
    return worker_lease, bot_lease


def _candidate_smoke(
    slot: str,
    *,
    timeout_seconds: int = 10,
    require_progress_report_shell: bool = False,
) -> None:
    release_contract_args = (
        ["--expect-progress-report-shell"] if require_progress_report_shell else []
    )
    if slot == "legacy":
        _run(
            [
                sys.executable,
                "scripts/check_deployment.py",
                "http://127.0.0.1:8000",
                "--allow-http",
                "--expected-environment",
                "prod",
                "--timeout",
                str(timeout_seconds),
                *release_contract_args,
            ]
        )
        return
    _compose(
        "exec",
        "-T",
        _slot_service("backend", slot),
        "python",
        "/app/scripts/check_deployment.py",
        "http://127.0.0.1:8000",
        "--allow-http",
        "--expected-environment",
        "prod",
        *release_contract_args,
    )


def _public_smoke(
    config: DeployConfig,
    *,
    require_progress_report_shell: bool = False,
) -> None:
    release_contract_args = (
        ["--expect-progress-report-shell"] if require_progress_report_shell else []
    )
    _run(
        [
            sys.executable,
            "scripts/check_deployment.py",
            config.base_url,
            "--expected-environment",
            "prod",
            *release_contract_args,
        ]
    )
    _run(
        [
            sys.executable,
            "scripts/check_seo_surface.py",
            config.public_base_url,
            "--timeout",
            str(config.seo_timeout_seconds),
        ]
    )


def _write_evidence(path: Path, evidence: Evidence) -> None:
    evidence.ended_at = time.time()
    _atomic_json(path, asdict(evidence))


@contextlib.contextmanager
def _stage(evidence: Evidence, name: str) -> Iterator[None]:
    stage = StageRecord(name=name, started_at=time.time())
    evidence.stages.append(stage)
    try:
        yield
    except BaseException as exc:
        stage.status = "failed"
        stage.reason = f"{type(exc).__name__}: {exc}"
        raise
    else:
        stage.status = "passed"
    finally:
        stage.ended_at = time.time()


def _start_probe(
    config: DeployConfig,
    output: Path,
    stop_file: Path,
    compatibility_stop_file: Path,
) -> subprocess.Popen[str]:
    maximum_duration = max(
        300.0,
        config.readiness_timeout_seconds + config.observation_seconds + 300.0,
    )
    return subprocess.Popen(
        [
            sys.executable,
            "scripts/continuous_deployment_probe.py",
            config.base_url,
            "--duration",
            str(maximum_duration),
            "--interval",
            str(config.probe_interval_seconds),
            "--timeout",
            str(config.probe_timeout_seconds),
            "--expected-environment",
            "prod",
            "--output",
            str(output),
            "--stop-file",
            str(stop_file),
            "--compatibility-stop-file",
            str(compatibility_stop_file),
        ],
        text=True,
    )


def _wait_observation(
    process: subprocess.Popen[str],
    seconds: float,
    services: Sequence[str],
    consumer_leases: Sequence[ConsumerLease],
) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        code = process.poll()
        if code is not None:
            raise DeploymentError(f"continuous public probe stopped early with exit code {code}")
        for service in services:
            if not _service_is_running(service):
                raise DeploymentError(f"{service} stopped during the observation window")
        for lease in consumer_leases:
            if not _lease_is_current_and_healthy(lease):
                raise DeploymentError(
                    f"{lease.service} lost current-run ownership or health during observation"
                )
        time.sleep(min(5.0, max(0.0, deadline - time.monotonic())))


def _finish_probe(
    process: subprocess.Popen[str], output: Path, stop_file: Path
) -> dict[str, object]:
    _atomic_text(stop_file, "stop\n")
    try:
        return_code = process.wait(timeout=60)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
        raise DeploymentError("continuous public probe did not stop cleanly")
    if not output.is_file():
        raise DeploymentError(f"continuous probe did not write {output}")
    report = json.loads(output.read_text(encoding="utf-8"))
    if return_code != 0 or report.get("failure_count") != 0:
        raise DeploymentError(f"continuous public probe failed: {report}")
    return report


def bootstrap_state(config: DeployConfig) -> None:
    state_path = config.state_root / "state.json"
    if state_path.exists():
        raise DeploymentError(f"deployment state already exists: {state_path}")
    for service in ("backend", "worker", "bot", "edge"):
        if not _service_is_running(service):
            raise DeploymentError(f"legacy bootstrap requires running service {service}")
    _public_smoke(config)
    backend_container = _compose("ps", "-q", "backend", capture=True).stdout.strip()
    bot_container = _compose("ps", "-q", "bot", capture=True).stdout.strip()
    backend_image_ref = _run(
        ["docker", "inspect", "--format", "{{.Config.Image}}", backend_container], capture=True
    ).stdout.strip()
    bot_image_ref = _run(
        ["docker", "inspect", "--format", "{{.Config.Image}}", bot_container], capture=True
    ).stdout.strip()
    active_revision_path = config.state_root / "last-successful-revision"
    if not active_revision_path.is_file():
        raise DeploymentError("legacy bootstrap requires last-successful-revision evidence")
    active_revision = active_revision_path.read_text(encoding="utf-8").strip()
    backend_image = _image_digest(backend_image_ref, active_revision)
    bot_image = _image_digest(bot_image_ref, active_revision)
    _compose("up", "-d", "--no-build", "--no-deps", "--wait", "edge")
    _switch_gateway("legacy", "legacy")
    state = ReleaseState(
        version=STATE_VERSION,
        active_slot="legacy",
        active_revision=active_revision,
        active_backend_image=backend_image,
        active_bot_image=bot_image,
    )
    _atomic_json(state_path, asdict(state))
    _public_smoke(config)
    print(f"Zero-downtime state initialized at legacy revision {active_revision}")


def rollback(config: DeployConfig) -> None:
    state_path = config.state_root / "state.json"
    state = ReleaseState.from_path(state_path)
    if state.active_revision != config.target_revision:
        raise DeploymentError(
            f"rollback expected active revision {config.target_revision}, found {state.active_revision}"
        )
    if (
        state.rollback_slot is None
        or state.rollback_revision is None
        or state.rollback_backend_image is None
        or state.rollback_bot_image is None
    ):
        raise DeploymentError("deployment state has no rollback-capable revision")

    rollback_env = (
        _slot_environment(
            state.rollback_slot,
            backend_image=state.rollback_backend_image,
            bot_image=state.rollback_bot_image,
        )
        if state.rollback_slot != "legacy"
        else os.environ.copy()
    )
    rollback_backend = _slot_service("backend", state.rollback_slot)
    if state.rollback_slot == "legacy":
        _compose("start", rollback_backend)
    else:
        _compose(
            "up",
            "-d",
            "--no-build",
            "--no-deps",
            "--wait",
            "--wait-timeout",
            str(config.readiness_timeout_seconds),
            rollback_backend,
            env=rollback_env,
        )
    _candidate_smoke(state.rollback_slot)

    switched = False
    consumers_stopped = False
    state_committed = False
    persistent_images_updated = False
    try:
        _switch_gateway(state.rollback_slot, state.active_slot)
        switched = True
        _public_smoke(config)
        consumers_stopped = True
        _stop_slot_consumers(state.active_slot, config)
        rollback_evidence = Evidence(
            deployment_id=f"rollback-{int(time.time())}-{state.rollback_revision[:12]}",
            target_revision=state.rollback_revision,
            previous_revision=state.active_revision,
            active_slot=state.active_slot,
            candidate_slot=state.rollback_slot,
            started_at=time.time(),
        )
        _start_slot_consumers(
            state.rollback_slot, env=rollback_env, evidence=rollback_evidence, config=config
        )
        next_state = ReleaseState(
            version=STATE_VERSION,
            active_slot=state.rollback_slot,
            active_revision=state.rollback_revision,
            active_backend_image=state.rollback_backend_image,
            active_bot_image=state.rollback_bot_image,
            rollback_slot=state.active_slot,
            rollback_revision=state.active_revision,
            rollback_backend_image=state.active_backend_image,
            rollback_bot_image=state.active_bot_image,
        )
        _persist_application_image_refs(
            config.root / ".env",
            backend_image=state.rollback_backend_image,
            bot_image=state.rollback_bot_image,
        )
        persistent_images_updated = True
        _public_smoke(config)
        _atomic_json(state_path, asdict(next_state))
        state_committed = True
        _atomic_text(config.state_root / "last-successful-revision", state.rollback_revision + "\n")
    except BaseException:
        if switched and not state_committed:
            try:
                _switch_gateway(state.active_slot, state.active_slot)
                if consumers_stopped:
                    active_env = (
                        _slot_environment(
                            state.active_slot,
                            backend_image=state.active_backend_image,
                            bot_image=state.active_bot_image,
                        )
                        if state.active_slot != "legacy"
                        else os.environ.copy()
                    )
                    _stop_slot_consumers(state.rollback_slot, config)
                    _start_slot_consumers(
                        state.active_slot,
                        env=active_env,
                        evidence=rollback_evidence,
                        config=config,
                    )
                if persistent_images_updated:
                    _persist_application_image_refs(
                        config.root / ".env",
                        backend_image=state.active_backend_image,
                        bot_image=state.active_bot_image,
                    )
                _public_smoke(config)
            except BaseException as rollback_exc:
                raise DeploymentError(
                    "rollback restoration was incomplete: "
                    f"{type(rollback_exc).__name__}: {rollback_exc}"
                ) from rollback_exc
        raise
    print(
        f"Rollback verified: active revision={state.rollback_revision}; slot={state.rollback_slot}"
    )


def deploy(config: DeployConfig) -> Evidence:
    state_path = config.state_root / "state.json"
    if not state_path.is_file():
        raise DeploymentError(
            "zero-downtime state is not initialized; use the documented owner-approved bootstrap"
        )
    state = ReleaseState.from_path(state_path)
    if state.active_revision == config.target_revision:
        _switch_gateway(state.active_slot, state.active_slot)
        if state.rollback_slot is not None:
            _compose("stop", "-t", "45", _slot_service("backend", state.rollback_slot))
        _atomic_text(config.state_root / "last-successful-revision", config.target_revision + "\n")
        _public_smoke(config, require_progress_report_shell=True)
        print(f"Revision {config.target_revision} is already active; verified idempotent no-op")
        return Evidence(
            deployment_id=f"noop-{config.target_revision[:12]}",
            target_revision=config.target_revision,
            previous_revision=state.active_revision,
            active_slot=state.active_slot,
            candidate_slot=state.active_slot,
            started_at=time.time(),
            ended_at=time.time(),
            verdict="active",
        )

    candidate_slot = "blue" if state.active_slot in {"legacy", "green"} else "green"
    deployment_id = f"{int(time.time())}-{config.target_revision[:12]}-{uuid.uuid4().hex[:8]}"
    deployment_root = config.state_root / deployment_id
    evidence_path = deployment_root / "summary.json"
    probe_path = deployment_root / "continuous-probe.json"
    probe_stop_path = deployment_root / "continuous-probe.stop"
    compatibility_stop_path = deployment_root / "asset-compatibility.stop"
    evidence = Evidence(
        deployment_id=deployment_id,
        target_revision=config.target_revision,
        previous_revision=state.active_revision,
        active_slot=state.active_slot,
        candidate_slot=candidate_slot,
        started_at=time.time(),
    )
    candidate_backend = config.backend_image
    candidate_bot = config.bot_image
    candidate_env: dict[str, str] | None = None
    probe: subprocess.Popen[str] | None = None
    switched = False
    state_committed = False
    candidate_backend_mutated = False
    candidate_consumers_mutated = False
    consumers_stopped = False
    persistent_images_updated = False

    try:
        with _stage(evidence, "preflight"):
            evidence.capacity = _capacity()
            _compose("config", "--quiet")
            _switch_gateway(state.active_slot, state.active_slot)
            _public_smoke(config)

        with _stage(evidence, "pull_and_verify"):
            preliminary_env = _slot_environment(
                candidate_slot,
                backend_image=config.backend_image,
                bot_image=config.bot_image,
            )
            _pull_images_with_retry(
                "setup",
                _slot_service("backend", candidate_slot),
                _slot_service("worker", candidate_slot),
                _slot_service("bot", candidate_slot),
                env=preliminary_env,
            )
            candidate_backend = _image_digest(config.backend_image, config.target_revision)
            candidate_bot = _image_digest(config.bot_image, config.target_revision)
            candidate_env = _slot_environment(
                candidate_slot,
                backend_image=candidate_backend,
                bot_image=candidate_bot,
            )
            candidate_env["BACKEND_IMAGE"] = candidate_backend
            candidate_env["BOT_IMAGE"] = candidate_bot
            _compose("config", "--quiet", env=candidate_env)
            _run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--env-file",
                    ".env",
                    candidate_backend,
                    "python",
                    "-c",
                    "from fitminiapp_api.core.config import settings; assert settings.app_env == 'prod'",
                ],
            )
            _run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--env-file",
                    ".env",
                    candidate_bot,
                    "python",
                    "-c",
                    "from fitminiapp_bot.config import settings; assert settings.app_env == 'prod'",
                ],
            )

        probe = _start_probe(config, probe_path, probe_stop_path, compatibility_stop_path)

        with _stage(evidence, "backup"):
            _run([sys.executable, "scripts/db_maintenance.py", "backup"])

        with _stage(evidence, "migration"):
            _run(_online_migration_command(state.active_revision, config.target_revision))
            _compose("run", "--rm", "--no-deps", "setup", env=candidate_env)

        with _stage(evidence, "candidate_start"):
            candidate_backend_service = _slot_service("backend", candidate_slot)
            candidate_backend_mutated = True
            _compose(
                "up",
                "-d",
                "--no-build",
                "--no-deps",
                "--wait",
                "--wait-timeout",
                str(config.readiness_timeout_seconds),
                candidate_backend_service,
                env=candidate_env,
            )

        with _stage(evidence, "candidate_smoke"):
            _candidate_smoke(candidate_slot, require_progress_report_shell=True)
            if probe.poll() is not None:
                raise DeploymentError("public route failed while the candidate was prepared")

        with _stage(evidence, "traffic_switch"):
            _switch_gateway(candidate_slot, state.active_slot)
            switched = True

        with _stage(evidence, "external_verification"):
            _public_smoke(config, require_progress_report_shell=True)

        with _stage(evidence, "consumer_handoff"):
            consumers_stopped = True
            _stop_slot_consumers(state.active_slot, config)
            candidate_consumers_mutated = True
            consumer_leases = _start_slot_consumers(
                candidate_slot, env=candidate_env, evidence=evidence, config=config
            )

        with _stage(evidence, "observation"):
            _wait_observation(
                probe,
                config.observation_seconds,
                (
                    _slot_service("backend", candidate_slot),
                    _slot_service("worker", candidate_slot),
                    _slot_service("bot", candidate_slot),
                    "edge",
                ),
                consumer_leases,
            )

        with _stage(evidence, "drain_and_cleanup"):
            _atomic_text(compatibility_stop_path, "compatibility window complete\n")
            next_state = ReleaseState(
                version=STATE_VERSION,
                active_slot=candidate_slot,
                active_revision=config.target_revision,
                active_backend_image=candidate_backend,
                active_bot_image=candidate_bot,
                rollback_slot=state.active_slot,
                rollback_revision=state.active_revision,
                rollback_backend_image=state.active_backend_image,
                rollback_bot_image=state.active_bot_image,
            )
            _switch_gateway(candidate_slot, candidate_slot)
            evidence.probe = _finish_probe(probe, probe_path, probe_stop_path)
            probe = None
            _persist_application_image_refs(
                config.root / ".env",
                backend_image=candidate_backend,
                bot_image=candidate_bot,
            )
            persistent_images_updated = True
            _atomic_json(state_path, asdict(next_state))
            state_committed = True
            _atomic_text(
                config.state_root / "last-successful-revision", config.target_revision + "\n"
            )
            _compose(
                "stop",
                "-t",
                str(config.backend_drain_seconds),
                _slot_service("backend", state.active_slot),
            )
            superseded_slot = state.rollback_slot
            if superseded_slot not in {None, state.active_slot, candidate_slot}:
                _compose(
                    "rm",
                    "-f",
                    "-s",
                    _slot_service("backend", superseded_slot),
                    _slot_service("worker", superseded_slot),
                    _slot_service("bot", superseded_slot),
                )
        evidence.verdict = "active"
        return evidence
    except BaseException:
        rollback_verified = not switched
        if switched and not state_committed:
            rollback_stage = StageRecord(name="rollback", started_at=time.time())
            evidence.stages.append(rollback_stage)
            try:
                _switch_gateway(state.active_slot, state.active_slot)
                if candidate_consumers_mutated:
                    _stop_slot_consumers(candidate_slot, config, require_running=False)
                active_env = (
                    _slot_environment(
                        state.active_slot,
                        backend_image=state.active_backend_image,
                        bot_image=state.active_bot_image,
                    )
                    if state.active_slot != "legacy"
                    else os.environ.copy()
                )
                if consumers_stopped:
                    _start_slot_consumers(
                        state.active_slot, env=active_env, evidence=evidence, config=config
                    )
                if persistent_images_updated:
                    _persist_application_image_refs(
                        config.root / ".env",
                        backend_image=state.active_backend_image,
                        bot_image=state.active_bot_image,
                    )
                _public_smoke(config)
                evidence.verdict = "rolled back"
                rollback_verified = True
                rollback_stage.status = "passed"
            except BaseException as rollback_exc:
                rollback_stage.status = "failed"
                rollback_stage.reason = f"{type(rollback_exc).__name__}: {rollback_exc}"
                evidence.verdict = "manual intervention required"
            finally:
                rollback_stage.ended_at = time.time()
        else:
            if not state_committed:
                evidence.verdict = "not switched"
        if not state_committed and rollback_verified:
            mutated_services = []
            if candidate_backend_mutated:
                mutated_services.append(_slot_service("backend", candidate_slot))
            if candidate_consumers_mutated:
                mutated_services.extend(
                    (
                        _slot_service("worker", candidate_slot),
                        _slot_service("bot", candidate_slot),
                    )
                )
            with contextlib.suppress(BaseException):
                if mutated_services:
                    _compose("rm", "-f", "-s", *mutated_services)
        raise
    finally:
        if probe is not None:
            with contextlib.suppress(BaseException):
                evidence.probe = _finish_probe(probe, probe_path, probe_stop_path)
        _write_evidence(evidence_path, evidence)


def _legacy_running_image(service: str) -> str:
    container_id = _compose("ps", "-q", service, capture=True).stdout.strip()
    if not container_id or not _service_is_running(service):
        raise DeploymentError(f"single-slot rollout requires running legacy service {service}")
    # A single-slot reclaim may remove a mutable tag from an image that the running
    # container still references.  Snapshot the immutable image ID so provenance and
    # rollback do not depend on that tag surviving reclaim.
    image = _run(
        ["docker", "inspect", "--format", "{{.Image}}", container_id],
        capture=True,
    ).stdout.strip()
    if not image:
        raise DeploymentError(f"legacy service {service} has no image reference")
    return image


def _stop_legacy_services(config: DeployConfig) -> None:
    for service, timeout in (
        ("worker", config.worker_drain_seconds),
        ("bot", config.bot_drain_seconds),
        ("backend", config.backend_drain_seconds),
    ):
        if not _service_is_running(service):
            raise DeploymentError(f"legacy service {service} stopped before maintenance handoff")
        worker_lease = (
            _consumer_lease(service, ("worker_started",)) if service == "worker" else None
        )
        _compose("stop", "-t", str(timeout), service)
        if _service_is_running(service):
            raise DeploymentError(f"legacy service {service} remained running after stop")
        if (
            worker_lease is not None
            and "worker_stopped" not in _current_run_logs(worker_lease)
            and not _container_exited_cleanly(worker_lease)
        ):
            raise DeploymentError(
                "worker did not acknowledge a completed drain within "
                f"{config.worker_drain_seconds}s; consumer state is uncertain"
            )


def _start_legacy_backend(env: dict[str, str], config: DeployConfig) -> None:
    _compose(
        "up",
        "-d",
        "--no-build",
        "--no-deps",
        "--force-recreate",
        "--wait",
        "--wait-timeout",
        str(config.readiness_timeout_seconds),
        "backend",
        env=env,
    )
    _candidate_smoke("legacy", timeout_seconds=config.readiness_timeout_seconds)


def _start_legacy_consumers(
    env: dict[str, str],
    evidence: Evidence,
    config: DeployConfig,
    *,
    require_markers: bool,
    best_effort: bool = False,
) -> tuple[ConsumerLease, ConsumerLease]:
    errors: list[str] = []
    worker_lease: ConsumerLease | None = None
    bot_lease: ConsumerLease | None = None

    started = time.monotonic()
    try:
        _compose(
            "up",
            "-d",
            "--no-build",
            "--no-deps",
            "--force-recreate",
            "--wait",
            "--wait-timeout",
            str(config.readiness_timeout_seconds),
            "worker",
            env=env,
        )
        worker_markers = ("worker_started",) if require_markers else ()
        worker_lease = _consumer_lease("worker", worker_markers)
        _wait_for_ownership(worker_lease, timeout=config.readiness_timeout_seconds)
        evidence.worker_handoff_seconds = round(time.monotonic() - started, 3)
    except BaseException as worker_exc:
        if not best_effort:
            raise
        errors.append(f"worker: {type(worker_exc).__name__}: {worker_exc}")

    started = time.monotonic()
    try:
        _compose(
            "up",
            "-d",
            "--no-build",
            "--no-deps",
            "--force-recreate",
            "bot",
            env=env,
        )
        bot_markers = (
            ("polling_file_lock_acquired", "telegram_polling_started")
            if config.bot_polling_enabled
            else ("polling_disabled",)
        )
        if not require_markers:
            bot_markers = ()
        bot_lease = _consumer_lease("bot", bot_markers)
        _wait_for_ownership(bot_lease, timeout=config.readiness_timeout_seconds)
        evidence.bot_handoff_seconds = round(time.monotonic() - started, 3)
    except BaseException as bot_exc:
        errors.append(f"bot: {type(bot_exc).__name__}: {bot_exc}")

    if errors:
        raise DeploymentError("consumer restoration was incomplete: " + "; ".join(errors))
    if worker_lease is None or bot_lease is None:
        raise DeploymentError("consumer restoration returned no verified ownership lease")
    return worker_lease, bot_lease


def single_slot_deploy(config: DeployConfig) -> Evidence:
    confirmed_sha = os.environ.get("DEPLOY_SINGLE_SLOT_CONFIRMED_SHA", "")
    if confirmed_sha != config.target_revision:
        raise DeploymentError(
            "single-slot rollout requires DEPLOY_SINGLE_SLOT_CONFIRMED_SHA "
            "to equal the exact target revision"
        )
    if (config.state_root / "state.json").exists():
        raise DeploymentError(
            "single-slot rollout is only allowed before blue/green state initialization"
        )

    active_revision_path = config.state_root / "last-successful-revision"
    if not active_revision_path.is_file():
        raise DeploymentError("single-slot rollout requires last-successful-revision evidence")
    active_revision = active_revision_path.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", active_revision):
        raise DeploymentError("last-successful-revision is not a full Git SHA")

    deployment_id = (
        f"single-slot-{int(time.time())}-{config.target_revision[:12]}-{uuid.uuid4().hex[:8]}"
    )
    evidence = Evidence(
        deployment_id=deployment_id,
        target_revision=config.target_revision,
        previous_revision=active_revision,
        active_slot="legacy",
        candidate_slot="legacy",
        started_at=time.time(),
    )
    evidence_path = config.state_root / deployment_id / "summary.json"

    if active_revision == config.target_revision:
        _switch_gateway("legacy", "legacy")
        _public_smoke(config, require_progress_report_shell=True)
        evidence.verdict = "active"
        _write_evidence(evidence_path, evidence)
        print(f"Revision {config.target_revision} is already active; verified single-slot no-op")
        return evidence

    old_backend = ""
    old_bot = ""
    target_env: dict[str, str] | None = None
    services_stopped = False
    persistent_images_updated = False

    try:
        with _stage(evidence, "single_slot_legacy_provenance"):
            old_backend = _image_digest(_legacy_running_image("backend"), active_revision)
            old_bot = _image_digest(_legacy_running_image("bot"), active_revision)
            old_worker = _image_digest(_legacy_running_image("worker"), active_revision)
            if old_worker != old_backend:
                raise DeploymentError(
                    "legacy backend and worker do not use the same verified image digest"
                )
            _legacy_running_image("edge")

        with _stage(evidence, "single_slot_docker_reclaim"):
            _reclaim_single_slot_docker_space()

        with _stage(evidence, "single_slot_preflight"):
            evidence.capacity = _single_slot_capacity()
            _compose("config", "--quiet")
            _switch_gateway("legacy", "legacy")
            _public_smoke(config)

        with _stage(evidence, "pull_and_verify"):
            preliminary_env = _legacy_environment(
                backend_image=config.backend_image,
                bot_image=config.bot_image,
            )
            _pull_images_with_retry(
                "setup",
                "backend",
                "worker",
                "bot",
                env=preliminary_env,
            )
            target_backend = _image_digest(config.backend_image, config.target_revision)
            target_bot = _image_digest(config.bot_image, config.target_revision)
            target_env = _legacy_environment(
                backend_image=target_backend,
                bot_image=target_bot,
            )
            _compose("config", "--quiet", env=target_env)
            _run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--env-file",
                    ".env",
                    target_backend,
                    "python",
                    "-c",
                    "from fitminiapp_api.core.config import settings; assert settings.app_env == 'prod'",
                ]
            )
            _run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--env-file",
                    ".env",
                    target_bot,
                    "python",
                    "-c",
                    "from fitminiapp_bot.config import settings; assert settings.app_env == 'prod'",
                ]
            )

        with _stage(evidence, "backup"):
            _run([sys.executable, "scripts/db_maintenance.py", "backup"])

        with _stage(evidence, "migration_gate"):
            _run(_online_migration_command(active_revision, config.target_revision))

        with _stage(evidence, "pre_stop_capacity"):
            evidence.capacity = _single_slot_capacity()

        with _stage(evidence, "maintenance_stop"):
            services_stopped = True
            _stop_legacy_services(config)

        with _stage(evidence, "migration"):
            if target_env is None:
                raise DeploymentError("target images were not resolved before maintenance")
            _compose("run", "--rm", "--no-deps", "setup", env=target_env)

        with _stage(evidence, "application_start"):
            _start_legacy_backend(target_env, config)
            _public_smoke(config, require_progress_report_shell=True)
            consumer_leases = _start_legacy_consumers(
                target_env,
                evidence,
                config,
                require_markers=True,
            )

        with _stage(evidence, "verification"):
            for lease in consumer_leases:
                if not _lease_is_current_and_healthy(lease):
                    raise DeploymentError(
                        f"{lease.service} lost current-run ownership after single-slot start"
                    )
            _public_smoke(config, require_progress_report_shell=True)
            if target_env is None:
                raise DeploymentError("target images were not resolved before verification")
            _persist_application_image_refs(
                config.root / ".env",
                backend_image=target_env["BACKEND_IMAGE"],
                bot_image=target_env["BOT_IMAGE"],
            )
            persistent_images_updated = True
            _atomic_text(active_revision_path, config.target_revision + "\n")

        evidence.verdict = "active"
        print(f"Single-slot deployment verified: revision={config.target_revision}; slot=legacy")
        return evidence
    except BaseException:
        if services_stopped and old_backend and old_bot:
            rollback_stage = StageRecord(name="single_slot_rollback", started_at=time.time())
            evidence.stages.append(rollback_stage)
            try:
                for service, timeout in (
                    ("worker", config.worker_drain_seconds),
                    ("bot", config.bot_drain_seconds),
                    ("backend", config.backend_drain_seconds),
                ):
                    if _service_is_running(service):
                        _compose("stop", "-t", str(timeout), service)
                rollback_env = _legacy_environment(
                    backend_image=old_backend,
                    bot_image=old_bot,
                )
                rollback_errors: list[str] = []
                try:
                    _start_legacy_backend(rollback_env, config)
                except BaseException as rollback_backend_exc:
                    rollback_errors.append(
                        f"backend: {type(rollback_backend_exc).__name__}: {rollback_backend_exc}"
                    )
                try:
                    _start_legacy_consumers(
                        rollback_env,
                        evidence,
                        config,
                        require_markers=True,
                        best_effort=True,
                    )
                except BaseException as rollback_consumers_exc:
                    rollback_errors.append(
                        "consumers: "
                        f"{type(rollback_consumers_exc).__name__}: {rollback_consumers_exc}"
                    )
                if persistent_images_updated:
                    try:
                        _persist_application_image_refs(
                            config.root / ".env",
                            backend_image=old_backend,
                            bot_image=old_bot,
                        )
                    except BaseException as rollback_env_exc:
                        rollback_errors.append(
                            "environment image refs: "
                            f"{type(rollback_env_exc).__name__}: {rollback_env_exc}"
                        )
                try:
                    _public_smoke(config)
                except BaseException as rollback_smoke_exc:
                    rollback_errors.append(
                        f"public smoke: {type(rollback_smoke_exc).__name__}: {rollback_smoke_exc}"
                    )
                if rollback_errors:
                    raise DeploymentError(
                        "rollback restoration was incomplete: " + "; ".join(rollback_errors)
                    )
                evidence.verdict = "rolled back"
                rollback_stage.status = "passed"
            except BaseException as rollback_exc:
                rollback_stage.status = "failed"
                rollback_stage.reason = f"{type(rollback_exc).__name__}: {rollback_exc}"
                evidence.verdict = "manual intervention required"
            finally:
                rollback_stage.ended_at = time.time()
        else:
            evidence.verdict = "not stopped"
        raise
    finally:
        _write_evidence(evidence_path, evidence)


def _config(args: argparse.Namespace) -> DeployConfig:
    root = Path.cwd().resolve()
    polling_value = _deployment_setting("BOT_POLLING_ENABLED", "true").strip().lower()
    if polling_value not in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
        raise DeploymentError("BOT_POLLING_ENABLED must be a boolean value")
    return DeployConfig(
        target_revision=args.target_revision,
        base_url=args.base_url,
        public_base_url=args.public_base_url,
        backend_image=os.environ["BACKEND_IMAGE"],
        bot_image=os.environ["BOT_IMAGE"],
        root=root,
        state_root=Path(
            os.environ.get(
                "DEPLOY_STATE_ROOT", str(root / ".artifacts" / "operations" / "deployments")
            )
        ).resolve(),
        observation_seconds=float(_deployment_setting("DEPLOY_OBSERVATION_SECONDS", "900")),
        readiness_timeout_seconds=configured_timeout("DEPLOY_READINESS_TIMEOUT_SECONDS", 180),
        probe_interval_seconds=float(_deployment_setting("DEPLOY_PROBE_INTERVAL_SECONDS", "1")),
        probe_timeout_seconds=float(_deployment_setting("DEPLOY_PROBE_TIMEOUT_SECONDS", "5")),
        seo_timeout_seconds=float(_deployment_setting("DEPLOY_SEO_TIMEOUT_SECONDS", "20")),
        backend_drain_seconds=configured_timeout("DEPLOY_BACKEND_DRAIN_SECONDS", 45),
        worker_drain_seconds=configured_timeout("DEPLOY_WORKER_DRAIN_SECONDS", 90),
        bot_drain_seconds=configured_timeout("DEPLOY_BOT_DRAIN_SECONDS", 45),
        bot_polling_enabled=polling_value in {"1", "true", "yes", "on"},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("deploy", "bootstrap", "rollback", "single-slot"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("target_revision")
        subparser.add_argument("base_url")
        subparser.add_argument("public_base_url")
    args = parser.parse_args()
    try:
        config = _config(args)
        with _deployment_lock(config.state_root / "deployment.lock"):
            if args.command == "bootstrap":
                bootstrap_state(config)
            elif args.command == "rollback":
                rollback(config)
            elif args.command == "single-slot":
                evidence = single_slot_deploy(config)
                print(
                    f"Deployment verdict: {evidence.verdict}; "
                    f"revision={evidence.target_revision}; slot={evidence.candidate_slot}"
                )
            else:
                evidence = deploy(config)
                print(
                    f"Deployment verdict: {evidence.verdict}; "
                    f"revision={evidence.target_revision}; slot={evidence.candidate_slot}"
                )
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError, DeploymentError) as exc:
        print(f"Production deployment failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
