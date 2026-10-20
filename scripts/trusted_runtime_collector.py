"""Collect a bounded, read-only runtime snapshot for the connection budget gate.

The host side reads rendered Compose metadata, running-container inventory,
allowlisted runtime environment values and immutable image labels. The PostgreSQL
query runs inside the exact inspected active backend container, so the database URL
never crosses the host-side JSON boundary. No collector output contains raw
environment values, container IDs, SQL rows, or exception text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import signal
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

try:
    from scripts.connection_budget_preflight import (
        _TRUSTED_RUNTIME_EVIDENCE_TOKEN,
        BudgetModel,
        ConfigurationError,
        Diagnostic,
        EvidenceMetadata,
        PhaseDemand,
        PoolerTopology,
        PoolSpec,
        PostgresCapacity,
        PostgresSnapshotError,
        PreflightResult,
        TopologyInventory,
        Verdict,
        _mark_runtime_evidence_trusted,
        evaluate,
        read_postgres_runtime_snapshot,
    )
except ModuleNotFoundError:
    from connection_budget_preflight import (
        _TRUSTED_RUNTIME_EVIDENCE_TOKEN,
        BudgetModel,
        ConfigurationError,
        Diagnostic,
        EvidenceMetadata,
        PhaseDemand,
        PoolerTopology,
        PoolSpec,
        PostgresCapacity,
        PostgresSnapshotError,
        PreflightResult,
        TopologyInventory,
        Verdict,
        _mark_runtime_evidence_trusted,
        evaluate,
        read_postgres_runtime_snapshot,
    )

COLLECTOR_SOURCE: Final = "trusted-runtime-collector"
COLLECTOR_APPLICATION_NAME: Final = "yfc-connection-budget-collector"
TRUSTED_ENVIRONMENT: Final = "production"
TRUSTED_MAX_AGE_SECONDS: Final = 300
TRUSTED_CLOCK_SKEW_SECONDS: Final = 30
MAX_COMMAND_OUTPUT_BYTES: Final = 128_000
DEFAULT_COMMAND_TIMEOUT_SECONDS: Final = 15
FULL_REVISION = re.compile(r"^[0-9a-f]{40}$")
CONTAINER_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
APPLICATION_NAME = re.compile(r"^[A-Za-z0-9._-]{1,63}$")
POOL_KEYS: Final = (
    "DB_POOL_SIZE",
    "DB_MAX_OVERFLOW",
    "DB_POOL_TIMEOUT_SECONDS",
    "DB_POOL_RECYCLE_SECONDS",
)
YFC_APPLICATION_NAMES: Final = (
    "yfc-backend",
    "yfc-worker",
    "yfc-setup",
    "yfc-migration",
    COLLECTOR_APPLICATION_NAME,
)
BACKEND_SERVICES: Final = ("backend", "backend-blue", "backend-green")
WORKER_SERVICES: Final = ("worker", "worker-blue", "worker-green")
REVISION_SERVICES: Final = frozenset(
    {
        *BACKEND_SERVICES,
        *WORKER_SERVICES,
        "setup",
        "bot",
        "bot-blue",
        "bot-green",
    }
)


class CollectorFailure(RuntimeError):
    """A sanitized collector failure; the detail is intentionally not retained."""

    def __init__(self, code: str, status: Verdict = Verdict.UNKNOWN) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class CollectorPolicy:
    """Trusted constants. The CLI does not expose these as user-controlled inputs."""

    environment: str = TRUSTED_ENVIRONMENT
    max_age_seconds: int = TRUSTED_MAX_AGE_SECONDS
    clock_skew_seconds: int = TRUSTED_CLOCK_SKEW_SECONDS
    command_timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS
    max_output_bytes: int = MAX_COMMAND_OUTPUT_BYTES
    safety_headroom_connections: int | None = None
    safety_headroom_source: str | None = None


@dataclass(frozen=True)
class RuntimeContext:
    environment: str
    host_fingerprint: str
    revisions: tuple[str, ...]
    captured_at: datetime


@dataclass(frozen=True)
class PostgresObservation:
    context: RuntimeContext
    capacity: PostgresCapacity


@dataclass(frozen=True)
class TopologyObservation:
    context: RuntimeContext
    pools: Mapping[str, PoolSpec]
    phases: tuple[PhaseDemand, ...]
    pooler: PoolerTopology
    topology: TopologyInventory
    active_backend_service: str | None
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class RuntimeCollection:
    result: PreflightResult
    context: RuntimeContext
    # Candidate is read from the bundle marker; active SHA is independently
    # verified against running OCI images. The union of both is insufficient
    # to verify the requested deploy target.
    candidate_revision: str


@dataclass(frozen=True)
class ContainerEnvironment:
    values: Mapping[str, str | None]
    has_database_url: bool


def _now() -> datetime:
    return datetime.now(UTC)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CollectorFailure(f"{field}_invalid", Verdict.UNKNOWN)
    return cast(Mapping[str, object], value)


def _parse_nonnegative_int(value: object) -> int | None:
    if value is None:
        return None
    if _is_int(value):
        return value if value >= 0 else None
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value.strip()):
        return int(value.strip())
    return None


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise CollectorFailure("postgres_snapshot_timestamp_invalid", Verdict.BLOCKED)
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CollectorFailure("postgres_snapshot_timestamp_invalid", Verdict.BLOCKED) from exc
    if timestamp.tzinfo is None:
        raise CollectorFailure("postgres_snapshot_timestamp_invalid", Verdict.BLOCKED)
    return timestamp.astimezone(UTC)


def _validate_policy(policy: CollectorPolicy) -> None:
    if (
        policy.environment != TRUSTED_ENVIRONMENT
        or policy.max_age_seconds <= 0
        or policy.clock_skew_seconds < 0
        or policy.command_timeout_seconds <= 0
        or policy.max_output_bytes <= 0
    ):
        raise CollectorFailure("trusted_policy_invalid", Verdict.BLOCKED)
    if policy.safety_headroom_connections is not None and (
        not _is_int(policy.safety_headroom_connections)
        or policy.safety_headroom_connections <= 0
        or not policy.safety_headroom_source
    ):
        raise CollectorFailure("trusted_policy_headroom_invalid", Verdict.BLOCKED)


def _host_fingerprint() -> str:
    hostname = platform.node().strip()
    if not hostname:
        raise CollectorFailure("host_identity_unknown", Verdict.UNKNOWN)
    return hashlib.sha256(hostname.encode("utf-8")).hexdigest()[:16]


def _release_revision(release_path: Path) -> str:
    """Read the immutable candidate bundle revision, not the running revision."""
    try:
        revision = (release_path / ".deployment-sha").read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise CollectorFailure("release_revision_unavailable", Verdict.UNKNOWN) from exc
    if FULL_REVISION.fullmatch(revision) is None:
        raise CollectorFailure("release_revision_invalid", Verdict.BLOCKED)
    return revision


def _active_revision(release_path: Path) -> str:
    """Independently bind running image labels to the current release state.

    The bundle .deployment-sha identifies the *candidate*. Before rollout,
    the active backend necessarily runs an older SHA. Never pass the candidate
    revision to the runtime image provenance check.
    """
    raw_root = os.environ.get("DEPLOY_STATE_ROOT")
    state_root = (
        Path(raw_root).resolve()
        if raw_root
        else (release_path / ".artifacts" / "operations" / "deployments")
    )
    try:
        revision = (state_root / "last-successful-revision").read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise CollectorFailure("active_revision_unavailable", Verdict.UNKNOWN) from exc
    if FULL_REVISION.fullmatch(revision) is None:
        raise CollectorFailure("active_revision_invalid", Verdict.BLOCKED)
    state_file = state_root / "state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CollectorFailure("active_state_invalid", Verdict.BLOCKED) from exc
        if not isinstance(state, dict) or state.get("active_revision") != revision:
            raise CollectorFailure("active_revision_state_mismatch", Verdict.BLOCKED)
        if state.get("active_slot") not in {"legacy", "blue", "green"}:
            raise CollectorFailure("active_state_invalid", Verdict.BLOCKED)
    return revision


def _run_bounded(
    command: Sequence[str],
    *,
    cwd: Path,
    policy: CollectorPolicy,
) -> bytes:
    overflow = threading.Event()
    reader_error = threading.Event()
    stdout_buffer = bytearray()
    stderr_buffer = bytearray()

    def drain(stream: object, buffer: bytearray) -> None:
        try:
            while True:
                chunk = stream.read(8192)  # type: ignore[attr-defined]
                if not chunk:
                    return
                if len(buffer) + len(chunk) > policy.max_output_bytes:
                    overflow.set()
                    return
                buffer.extend(chunk)
        except Exception:
            reader_error.set()

    def terminate() -> None:
        if os.name == "nt":
            with suppress(OSError, subprocess.SubprocessError):
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                )
        else:
            with suppress(OSError):
                os.killpg(process.pid, signal.SIGKILL)
        with suppress(OSError):
            process.kill()

    try:
        popen_kwargs: dict[str, object] = {
            "cwd": cwd,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            popen_kwargs["start_new_session"] = True
        process = subprocess.Popen(list(command), **popen_kwargs)
    except OSError as exc:
        raise CollectorFailure("runtime_command_unavailable", Verdict.UNKNOWN) from exc

    stdout_thread = threading.Thread(
        target=drain, args=(process.stdout, stdout_buffer), daemon=True
    )
    stderr_thread = threading.Thread(
        target=drain, args=(process.stderr, stderr_buffer), daemon=True
    )
    stdout_thread.start()
    stderr_thread.start()
    deadline = time.monotonic() + policy.command_timeout_seconds
    timed_out = False
    while process.poll() is None:
        if overflow.is_set():
            terminate()
            break
        if time.monotonic() >= deadline:
            timed_out = True
            terminate()
            break
        time.sleep(0.01)
    try:
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired as exc:
            terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired as wait_exc:
                raise CollectorFailure(
                    "runtime_command_termination_failed", Verdict.BLOCKED
                ) from wait_exc
            raise CollectorFailure("runtime_command_termination_failed", Verdict.BLOCKED) from exc
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)
        if stdout_thread.is_alive() or stderr_thread.is_alive():
            raise CollectorFailure("runtime_command_output_failed", Verdict.BLOCKED)
        if timed_out:
            raise CollectorFailure("runtime_command_timeout", Verdict.BLOCKED)
        if overflow.is_set():
            raise CollectorFailure("runtime_command_output_exceeded", Verdict.BLOCKED)
        if reader_error.is_set():
            raise CollectorFailure("runtime_command_output_failed", Verdict.UNKNOWN)
        if process.returncode != 0:
            raise CollectorFailure("runtime_command_failed", Verdict.UNKNOWN)
        return bytes(stdout_buffer)
    finally:
        for stream in (process.stdout, process.stderr):
            with suppress(OSError, ValueError):
                stream.close()  # type: ignore[union-attr]


def _json_bytes(value: bytes, *, code: str) -> object:
    try:
        return json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CollectorFailure(code, Verdict.UNKNOWN) from exc


def _json_ps_bytes(value: bytes) -> object:
    try:
        return _json_bytes(value, code="runtime_process_inventory_invalid")
    except CollectorFailure:
        try:
            return [json.loads(line) for line in value.decode("utf-8").splitlines() if line.strip()]
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CollectorFailure("runtime_process_inventory_invalid", Verdict.UNKNOWN) from exc


def _compose_command(compose_file: Path, *args: str) -> list[str]:
    return [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "--profile",
        "production-slots",
        *args,
    ]


def _service_environment(service: Mapping[str, object]) -> dict[str, str | None]:
    raw = service.get("environment")
    values: dict[str, str | None] = {}
    if isinstance(raw, Mapping):
        source = raw.items()
    elif isinstance(raw, list):
        source = (
            (item.split("=", 1)[0], item.split("=", 1)[1] if "=" in item else None)
            for item in raw
            if isinstance(item, str) and item.split("=", 1)[0]
        )
    else:
        source = ()
    allowed = {
        *POOL_KEYS,
        "APP_ENV",
        "YFC_ACTIVE_UPSTREAM",
        "YFC_DB_APPLICATION_NAME",
        "YFC_POOLER_MODE",
        "YFC_POOLER_BACKEND_CAP",
    }
    for key, value in source:
        if key in allowed:
            values[key] = None if value is None else str(value)
    # Presence, not value, is all the collector needs for unknown DB consumers.
    if (isinstance(raw, Mapping) and "DATABASE_URL" in raw) or (
        isinstance(raw, list)
        and any(isinstance(item, str) and item.split("=", 1)[0] == "DATABASE_URL" for item in raw)
    ):
        values["DATABASE_URL"] = "<present>"
    return values


def _service_name(item: Mapping[str, object]) -> str | None:
    for key in ("Service", "service"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _running(item: Mapping[str, object]) -> bool:
    value = item.get("State", item.get("state", item.get("Status", item.get("status"))))
    if isinstance(value, Mapping):
        value = value.get("Status")
    return isinstance(value, str) and value.casefold().startswith(("running", "up"))


def _ps_items(payload: object) -> list[Mapping[str, object]]:
    if isinstance(payload, Mapping):
        payload = payload.get("services", payload.get("containers", []))
    if not isinstance(payload, list):
        raise CollectorFailure("runtime_process_inventory_invalid", Verdict.UNKNOWN)
    result: list[Mapping[str, object]] = []
    for item in payload:
        if isinstance(item, Mapping):
            result.append(cast(Mapping[str, object], item))
    return result


def _container_id(item: Mapping[str, object]) -> str:
    raw_id = item.get("ID", item.get("Id", item.get("id")))
    if not isinstance(raw_id, str) or CONTAINER_ID.fullmatch(raw_id) is None:
        raise CollectorFailure("runtime_container_identity_unknown", Verdict.UNKNOWN)
    return raw_id


def _running_container_ids(
    items: Sequence[Mapping[str, object]], service_name: str
) -> tuple[str, ...]:
    ids = sorted(
        _container_id(item)
        for item in items
        if _service_name(item) == service_name and _running(item)
    )
    if not ids:
        raise CollectorFailure("runtime_active_instance_unknown", Verdict.UNKNOWN)
    if len(ids) != len(set(ids)):
        raise CollectorFailure("runtime_container_identity_duplicate", Verdict.BLOCKED)
    return tuple(ids)


def _parse_container_environment(payload: object) -> ContainerEnvironment:
    if not isinstance(payload, list):
        raise CollectorFailure("runtime_environment_inventory_invalid", Verdict.UNKNOWN)
    allowed = {"APP_ENV", "YFC_DB_APPLICATION_NAME", *POOL_KEYS}
    values: dict[str, str | None] = dict.fromkeys(allowed)
    seen: set[str] = set()
    has_database_url = False
    for item in payload:
        if not isinstance(item, str):
            raise CollectorFailure("runtime_environment_inventory_invalid", Verdict.UNKNOWN)
        key, separator, raw_value = item.partition("=")
        if not key:
            raise CollectorFailure("runtime_environment_inventory_invalid", Verdict.UNKNOWN)
        if key == "DATABASE_URL":
            has_database_url = True
            continue
        if key not in allowed:
            continue
        if key in seen:
            raise CollectorFailure("runtime_environment_inventory_invalid", Verdict.BLOCKED)
        seen.add(key)
        values[key] = raw_value if separator else None
    return ContainerEnvironment(values=values, has_database_url=has_database_url)


def _inspect_runtime_environments(
    items: Sequence[Mapping[str, object]],
    *,
    cwd: Path,
    policy: CollectorPolicy,
) -> Mapping[str, tuple[ContainerEnvironment, ...]]:
    running: list[tuple[str, str]] = []
    for item in items:
        if not _running(item):
            continue
        service = _service_name(item)
        if service is None:
            raise CollectorFailure("runtime_service_identity_unknown", Verdict.UNKNOWN)
        running.append((service, _container_id(item)))
    if not running:
        return {}
    ids = [container_id for _service, container_id in running]
    if len(ids) != len(set(ids)):
        raise CollectorFailure("runtime_container_identity_duplicate", Verdict.BLOCKED)
    output = _run_bounded(
        ["docker", "inspect", "--format", "{{json .Config.Env}}", *ids],
        cwd=cwd,
        policy=policy,
    )
    lines = output.decode("utf-8", errors="strict").splitlines()
    if len(lines) != len(running):
        raise CollectorFailure("runtime_environment_inventory_invalid", Verdict.UNKNOWN)
    result: dict[str, list[ContainerEnvironment]] = {}
    for (service, _container_id_value), line in zip(running, lines, strict=True):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CollectorFailure(
                "runtime_environment_inventory_invalid", Verdict.UNKNOWN
            ) from exc
        result.setdefault(service, []).append(_parse_container_environment(payload))
    return {service: tuple(values) for service, values in result.items()}


def _runtime_environment_values(
    runtime_environments: Mapping[str, Sequence[ContainerEnvironment]] | None,
    service_name: str,
) -> Mapping[str, str | None] | None:
    if runtime_environments is None:
        return None
    observations = runtime_environments.get(service_name)
    if not observations:
        return None
    first = observations[0].values
    if any(observation.values != first for observation in observations[1:]):
        return {}
    return first


def _effective_service_environment(
    service_name: str,
    service: Mapping[str, object],
    runtime_environments: Mapping[str, Sequence[ContainerEnvironment]] | None,
) -> dict[str, str | None]:
    rendered = _service_environment(service)
    runtime_values = _runtime_environment_values(runtime_environments, service_name)
    if runtime_values is None:
        return rendered
    if not runtime_values:
        return dict.fromkeys((*POOL_KEYS, "APP_ENV", "YFC_DB_APPLICATION_NAME"))
    return {**rendered, **runtime_values}


def _service_running_count(items: Sequence[Mapping[str, object]], service_name: str) -> int | None:
    matching = [item for item in items if _service_name(item) == service_name]
    if not matching:
        return None
    return sum(1 for item in matching if _running(item))


def _configured_replicas(service: Mapping[str, object]) -> int | None:
    deploy = service.get("deploy")
    if isinstance(deploy, Mapping) and "replicas" in deploy:
        replicas = _parse_nonnegative_int(deploy.get("replicas"))
        return replicas if replicas is not None else None
    return 1


def _effective_replicas(
    services: Mapping[str, Mapping[str, object]],
    items: Sequence[Mapping[str, object]],
    name: str,
) -> int | None:
    service = services.get(name)
    if service is None:
        return None
    configured = _configured_replicas(service)
    if configured is None:
        return None
    return max(configured, _service_running_count(items, name) or 0)


def _sum_effective_replicas(
    services: Mapping[str, Mapping[str, object]],
    items: Sequence[Mapping[str, object]],
    names: Sequence[str],
) -> int | None:
    values = [_effective_replicas(services, items, name) for name in names]
    if len(values) != len(names):
        return None
    if any(value is None for value in values):
        return None
    return sum(cast(list[int], values))


def _max_effective_replicas(
    services: Mapping[str, Mapping[str, object]],
    items: Sequence[Mapping[str, object]],
    names: Sequence[str],
) -> int | None:
    values = [_effective_replicas(services, items, name) for name in names]
    if not values or any(value is None for value in values):
        return None
    return max(cast(list[int], values))


def _active_backend_service(services: Mapping[str, Mapping[str, object]]) -> str | None:
    edge = services.get("edge")
    if edge is None:
        return None
    upstream = _service_environment(edge).get("YFC_ACTIVE_UPSTREAM")
    if not isinstance(upstream, str):
        return None
    candidate = upstream.split(":", 1)[0].strip()
    return candidate if candidate in BACKEND_SERVICES else None


def _paired_worker(service_name: str | None) -> str | None:
    if service_name is None:
        return None
    if service_name == "backend":
        return "worker"
    return service_name.replace("backend-", "worker-", 1)


def _pool_spec(
    name: str,
    services: Mapping[str, Mapping[str, object]],
    service_names: Sequence[str],
    runtime_environments: Mapping[str, Sequence[ContainerEnvironment]] | None = None,
) -> PoolSpec:
    parsed: list[tuple[int | None, int | None, int | None, int | None]] = []
    for service_name in service_names:
        service = services.get(service_name)
        if service is None:
            return PoolSpec(name=name, pool_type="queue")
        environment = _effective_service_environment(service_name, service, runtime_environments)
        if _runtime_environment_values(runtime_environments, service_name) == {}:
            return PoolSpec(name=name, pool_type="queue")
        values = tuple(_parse_nonnegative_int(environment.get(key)) for key in POOL_KEYS)
        parsed.append(cast(tuple[int | None, int | None, int | None, int | None], values))
    if not parsed or any(values != parsed[0] for values in parsed[1:]):
        return PoolSpec(name=name, pool_type="queue")
    pool_size, max_overflow, timeout, _recycle = parsed[0]
    return PoolSpec(
        name=name,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout_seconds=timeout,
        connection_ceiling_source="rendered Compose runtime environment",
        pool_type="queue",
    )


def _pooler(
    services: Mapping[str, Mapping[str, object]],
) -> tuple[PoolerTopology, int | None]:
    pooler_names = [
        name
        for name in services
        if any(token in name.casefold() for token in ("pgbouncer", "pooler", "odyssey"))
    ]
    if not pooler_names:
        return PoolerTopology(mode="none"), None
    environment = _service_environment(services[pooler_names[0]])
    mode = environment.get("YFC_POOLER_MODE")
    cap = _parse_nonnegative_int(environment.get("YFC_POOLER_BACKEND_CAP"))
    return (
        PoolerTopology(
            mode=mode if mode in {"session", "transaction"} else None,
            backend_capacity_source=(
                "rendered Compose runtime pooler environment" if cap is not None else None
            ),
        ),
        cap,
    )


def _setup_pool_spec(
    services: Mapping[str, Mapping[str, object]],
    runtime_environments: Mapping[str, Sequence[ContainerEnvironment]] | None = None,
) -> PoolSpec:
    setup = services.get("setup")
    if setup is None:
        return PoolSpec("setup", pool_type="special")
    values = _effective_service_environment("setup", setup, runtime_environments)
    if _runtime_environment_values(runtime_environments, "setup") == {}:
        return PoolSpec(
            "setup",
            pool_type="special",
            connection_ceiling_source="setup readiness and seed rendered environment",
        )
    pool_size = _parse_nonnegative_int(values.get("DB_POOL_SIZE"))
    max_overflow = _parse_nonnegative_int(values.get("DB_MAX_OVERFLOW"))
    if pool_size is None or max_overflow is None or pool_size < 1:
        return PoolSpec(
            "setup",
            pool_type="special",
            connection_ceiling_source="setup readiness and seed rendered environment",
        )
    # setup-entrypoint readiness uses SQLAlchemy's default 5 + 10 QueuePool;
    # the following seed process imports the application pool settings.
    return PoolSpec(
        "setup",
        pool_type="special",
        connection_ceiling=max(15, pool_size + max_overflow),
        connection_ceiling_source="setup readiness and seed rendered environment",
    )


def _add_counts(first: int | None, second: int | None) -> int | None:
    if first is None or second is None:
        return None
    return first + second


def build_topology_observation(
    compose_payload: Mapping[str, object],
    ps_payload: object,
    context: RuntimeContext,
    *,
    runtime_environments: Mapping[str, Sequence[ContainerEnvironment]] | None = None,
) -> TopologyObservation:
    """Reduce rendered Compose and `ps` data to an allowlisted runtime model."""

    services_value = compose_payload.get("services")
    services_raw = _mapping(services_value, field="services")
    services: dict[str, Mapping[str, object]] = {}
    for name, raw in services_raw.items():
        if isinstance(name, str) and isinstance(raw, Mapping):
            services[name] = cast(Mapping[str, object], raw)
    items = _ps_items(ps_payload)
    active = _active_backend_service(services)
    active_worker = _paired_worker(active)
    candidate_backend_slots = tuple(
        name for name in BACKEND_SERVICES if name in services and name != active
    )
    candidate_worker_slots = tuple(
        name for name in WORKER_SERVICES if name in services and name != active_worker
    )

    backend_names = tuple(name for name in BACKEND_SERVICES if name in services)
    worker_names = tuple(name for name in WORKER_SERVICES if name in services)
    active_backend_count = _service_running_count(items, active) if active else None
    active_worker_count = _service_running_count(items, active_worker) if active_worker else None
    all_backend_count = _sum_effective_replicas(services, items, backend_names)
    all_worker_count = _sum_effective_replicas(services, items, worker_names)
    candidate_backend_count = (
        _add_counts(
            active_backend_count,
            _max_effective_replicas(services, items, candidate_backend_slots),
        )
        if candidate_backend_slots
        else active_backend_count
    )
    candidate_worker_count = (
        _add_counts(
            active_worker_count,
            _max_effective_replicas(services, items, candidate_worker_slots),
        )
        if candidate_worker_slots
        else active_worker_count
    )

    diagnostics: list[Diagnostic] = []
    if runtime_environments is not None:
        for name, observations in runtime_environments.items():
            service = services.get(name)
            if service is None:
                continue
            rendered = _service_environment(service)
            if any(
                any(
                    observation.values.get(key) != rendered.get(key)
                    for key in (*POOL_KEYS, "APP_ENV", "YFC_DB_APPLICATION_NAME")
                )
                for observation in observations
            ):
                diagnostics.append(
                    Diagnostic(
                        "runtime_container_environment_mismatch",
                        Verdict.BLOCKED,
                        "Running container environment differs from rendered Compose",
                    )
                )
            if any(
                observation.values != observations[0].values for observation in observations[1:]
            ):
                diagnostics.append(
                    Diagnostic(
                        "runtime_container_environment_inconsistent",
                        Verdict.UNKNOWN,
                        "Running instances of one service do not share effective runtime settings",
                    )
                )
    if active is None or active_worker is None:
        diagnostics.append(
            Diagnostic(
                "runtime_active_upstream_unknown",
                Verdict.UNKNOWN,
                "Rendered runtime does not identify an active backend and paired worker",
            )
        )
    relevant_names = set(backend_names) | set(worker_names)
    if "setup" in services:
        relevant_names.add("setup")
    else:
        diagnostics.append(
            Diagnostic(
                "runtime_setup_unknown",
                Verdict.UNKNOWN,
                "Rendered runtime does not include the setup/seed consumer",
            )
        )
    for name in sorted(relevant_names):
        environment = _effective_service_environment(name, services[name], runtime_environments)
        app_env = environment.get("APP_ENV")
        if app_env is None:
            diagnostics.append(
                Diagnostic(
                    "runtime_environment_unknown",
                    Verdict.UNKNOWN,
                    "Rendered runtime environment is missing APP_ENV",
                )
            )
        elif app_env != "prod":
            diagnostics.append(
                Diagnostic(
                    "runtime_environment_invalid",
                    Verdict.BLOCKED,
                    "Rendered application runtime is not production",
                )
            )
        application_name = environment.get("YFC_DB_APPLICATION_NAME")
        expected_application_name = (
            "yfc-backend"
            if name in BACKEND_SERVICES
            else "yfc-worker"
            if name in WORKER_SERVICES
            else "yfc-setup"
        )
        if application_name is None or APPLICATION_NAME.fullmatch(application_name) is None:
            diagnostics.append(
                Diagnostic(
                    "runtime_application_markers_unknown",
                    Verdict.UNKNOWN,
                    "Effective database application markers are incomplete",
                )
            )
        elif application_name != expected_application_name:
            diagnostics.append(
                Diagnostic(
                    "runtime_application_markers_invalid",
                    Verdict.BLOCKED,
                    "Effective database application markers do not match the process group",
                )
            )

    pooler_service_names = {
        name
        for name in services
        if any(token in name.casefold() for token in ("pgbouncer", "pooler", "odyssey"))
    }
    known_db_consumers = (
        set(BACKEND_SERVICES)
        | set(WORKER_SERVICES)
        | {
            "setup",
            *pooler_service_names,
        }
    )
    extra_db_consumers = [
        name
        for name, service in services.items()
        if name not in known_db_consumers and "DATABASE_URL" in _service_environment(service)
    ]
    if runtime_environments is not None:
        extra_db_consumers.extend(
            name
            for name, observations in runtime_environments.items()
            if name not in known_db_consumers
            and any(observation.has_database_url for observation in observations)
            and name not in extra_db_consumers
        )
    if extra_db_consumers:
        diagnostics.append(
            Diagnostic(
                "unexpected_db_consumer",
                Verdict.UNKNOWN,
                "Rendered runtime contains an additional database consumer",
            )
        )

    def phase_counts(backend: int | None, worker: int | None) -> dict[str, int | None]:
        return {
            "backend": backend,
            "worker": worker,
            "migration": 0,
            "setup": 0,
        }

    steady = phase_counts(active_backend_count, active_worker_count)
    candidate = phase_counts(candidate_backend_count, active_worker_count)
    all_slots = phase_counts(all_backend_count, all_worker_count)
    handoff = phase_counts(candidate_backend_count, candidate_worker_count)
    single = phase_counts(active_backend_count, active_worker_count)
    pooler, pooler_cap = _pooler(services)
    phase_pooler_cap = pooler_cap if pooler.mode in {"session", "transaction"} else None
    phases = (
        PhaseDemand(
            "steady-state",
            steady,
            None if extra_db_consumers else 0,
            phase_pooler_cap,
        ),
        PhaseDemand(
            "candidate-overlap",
            candidate,
            None if extra_db_consumers else 0,
            phase_pooler_cap,
        ),
        PhaseDemand(
            "unexpected-all-slots",
            all_slots,
            None if extra_db_consumers else 0,
            phase_pooler_cap,
        ),
        PhaseDemand("backup", steady, None if extra_db_consumers else 1, phase_pooler_cap),
        PhaseDemand(
            "migration",
            {**steady, "migration": 1},
            None if extra_db_consumers else 0,
            phase_pooler_cap,
        ),
        PhaseDemand(
            "setup-seed",
            {**steady, "setup": 1},
            None if extra_db_consumers else 0,
            phase_pooler_cap,
        ),
        PhaseDemand("worker-handoff", handoff, None if extra_db_consumers else 0, phase_pooler_cap),
        PhaseDemand("rollback", handoff, None if extra_db_consumers else 0, phase_pooler_cap),
        PhaseDemand("single-slot", single, None if extra_db_consumers else 0, phase_pooler_cap),
    )
    process_groups = {
        "backend": True,
        "worker": True,
        "migration": True,
        "setup": True,
    }
    if pooler.mode is None and any(
        any(token in name.casefold() for token in ("pgbouncer", "pooler", "odyssey"))
        for name in services
    ):
        diagnostics.append(
            Diagnostic(
                "pooler_topology_unknown",
                Verdict.UNKNOWN,
                "A pooler is present but its effective mode or backend cap is not proven",
            )
        )

    return TopologyObservation(
        context=context,
        pools={
            "backend": _pool_spec("backend", services, backend_names, runtime_environments),
            "worker": _pool_spec("worker", services, worker_names, runtime_environments),
            "migration": PoolSpec(
                "migration",
                connection_ceiling=1,
                pool_type="null",
                connection_ceiling_source="backend/alembic/env.py",
            ),
            "setup": _setup_pool_spec(services, runtime_environments),
        },
        phases=phases,
        pooler=pooler,
        topology=TopologyInventory(
            process_groups=process_groups,
            rollout_phases={phase.name: True for phase in phases},
        ),
        active_backend_service=active,
        diagnostics=tuple(diagnostics),
    )


def _verified_context(
    postgres: PostgresObservation,
    topology: TopologyObservation,
    policy: CollectorPolicy,
) -> RuntimeContext:
    contexts = (postgres.context, topology.context)
    if any(context.environment != policy.environment for context in contexts):
        raise CollectorFailure("runtime_context_environment_mismatch", Verdict.BLOCKED)
    if any(not context.host_fingerprint for context in contexts):
        raise CollectorFailure("runtime_context_host_unknown", Verdict.UNKNOWN)
    if any(context.host_fingerprint != contexts[0].host_fingerprint for context in contexts):
        raise CollectorFailure("runtime_context_host_mismatch", Verdict.BLOCKED)
    if any(context.revisions != contexts[0].revisions for context in contexts):
        raise CollectorFailure("runtime_context_revision_mismatch", Verdict.BLOCKED)
    if any(
        not context.revisions
        or any(FULL_REVISION.fullmatch(revision) is None for revision in context.revisions)
        for context in contexts
    ):
        raise CollectorFailure("runtime_context_revision_invalid", Verdict.BLOCKED)
    delta = abs((contexts[0].captured_at - contexts[1].captured_at).total_seconds())
    if delta > policy.clock_skew_seconds:
        raise CollectorFailure("runtime_context_time_mismatch", Verdict.BLOCKED)
    return replace(contexts[0], captured_at=min(context.captured_at for context in contexts))


def build_verified_budget_model(
    postgres: PostgresObservation,
    topology: TopologyObservation,
    policy: CollectorPolicy = CollectorPolicy(),
) -> tuple[BudgetModel, RuntimeContext]:
    """Create the only model shape that can receive the internal trust token."""

    _validate_policy(policy)
    context = _verified_context(postgres, topology, policy)
    model = BudgetModel(
        postgres=postgres.capacity,
        pools=topology.pools,
        phases=topology.phases,
        pooler=topology.pooler,
        safety_headroom_connections=policy.safety_headroom_connections,
        safety_headroom_source=policy.safety_headroom_source,
        topology=topology.topology,
        evidence=EvidenceMetadata(
            environment=policy.environment,
            source=COLLECTOR_SOURCE,
            captured_at=context.captured_at.isoformat(),
            max_age_seconds=policy.max_age_seconds,
            synthetic=False,
        ),
    )
    return (
        _mark_runtime_evidence_trusted(
            model,
            token=_TRUSTED_RUNTIME_EVIDENCE_TOKEN,
        ),
        context,
    )


def _merge_diagnostics(
    result: PreflightResult,
    diagnostics: Sequence[Diagnostic],
) -> PreflightResult:
    if not diagnostics:
        return result
    all_diagnostics = (*result.diagnostics, *diagnostics)
    status = Verdict.PASS
    if any(item.status == Verdict.BLOCKED for item in all_diagnostics):
        status = Verdict.BLOCKED
    elif any(item.status == Verdict.UNKNOWN for item in all_diagnostics):
        status = Verdict.UNKNOWN
    return replace(result, status=status, diagnostics=all_diagnostics)


def _parse_child_snapshot(payload: object, context: RuntimeContext) -> PostgresObservation:
    data = _mapping(payload, field="postgres_child_output")
    if set(data) != {"status", "captured_at", "postgres"} or data.get("status") != "PASS":
        raise CollectorFailure("postgres_snapshot_failed", Verdict.BLOCKED)
    captured_at = _parse_timestamp(data.get("captured_at"))
    postgres = _mapping(data.get("postgres"), field="postgres")
    allowed = {
        "server_version_major",
        "max_connections",
        "superuser_reserved_connections",
        "reserved_connections",
        "current_connections",
        "observed_yfc_connections",
        "observed_non_yfc_connections",
        "unattributed_connections",
    }
    if set(postgres) != allowed:
        raise CollectorFailure("postgres_snapshot_incomplete", Verdict.UNKNOWN)
    parsed: dict[str, int | None] = {}
    for key, value in postgres.items():
        if value is None and key == "reserved_connections":
            parsed[key] = None
            continue
        parsed_value = _parse_nonnegative_int(value)
        if parsed_value is None:
            raise CollectorFailure("postgres_snapshot_invalid", Verdict.BLOCKED)
        parsed[key] = parsed_value
    return PostgresObservation(
        context=replace(context, captured_at=captured_at),
        capacity=PostgresCapacity(**parsed),
    )


def _inspect_revisions(
    items: Sequence[Mapping[str, object]],
    *,
    cwd: Path,
    policy: CollectorPolicy,
    expected_revision: str,
) -> tuple[str, ...]:
    ids: list[str] = []
    for item in items:
        service = _service_name(item)
        if service not in REVISION_SERVICES or not _running(item):
            continue
        ids.append(_container_id(item))
    if not ids:
        raise CollectorFailure("runtime_revision_unknown", Verdict.UNKNOWN)
    output = _run_bounded(
        ["docker", "inspect", "--format", "{{json .Config.Labels}}", *ids],
        cwd=cwd,
        policy=policy,
    )
    revisions: set[str] = set()
    lines = output.decode("utf-8", errors="strict").splitlines()
    if len(lines) != len(ids):
        raise CollectorFailure("runtime_revision_inventory_invalid", Verdict.UNKNOWN)
    for line in lines:
        try:
            labels = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CollectorFailure("runtime_revision_inventory_invalid", Verdict.UNKNOWN) from exc
        if not isinstance(labels, Mapping):
            raise CollectorFailure("runtime_revision_unknown", Verdict.UNKNOWN)
        revision = labels.get("org.opencontainers.image.revision")
        if not isinstance(revision, str) or FULL_REVISION.fullmatch(revision.lower()) is None:
            raise CollectorFailure("runtime_revision_unknown", Verdict.UNKNOWN)
        normalized_revision = revision.lower()
        if normalized_revision != expected_revision:
            raise CollectorFailure("runtime_revision_mismatch", Verdict.BLOCKED)
        revisions.add(normalized_revision)
    return tuple(sorted(revisions))


def _legacy_child_source(release_path: Path) -> str:
    """Load fixed source for a read-only probe in a pre-collector backend.

    The source comes from the immutable candidate release, is only passed
    to python -c inside the independently verified ACTIVE backend, and
    contains no secrets or runtime-substituted values.
    """
    try:
        source = (release_path / "scripts" / "trusted_legacy_pg_snapshot.py").read_bytes()
        if not 0 < len(source) <= 16_384:
            raise CollectorFailure("legacy_probe_source_invalid", Verdict.BLOCKED)
        return source.decode("utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise CollectorFailure("legacy_probe_source_unavailable", Verdict.UNKNOWN) from exc


def collect_runtime_snapshot(
    *,
    release_path: Path,
    compose_file: Path,
    policy: CollectorPolicy = CollectorPolicy(),
) -> RuntimeCollection:
    """Collect the host/runtime pair and evaluate it without accepting JSON trust flags."""

    _validate_policy(policy)
    candidate_revision = _release_revision(release_path)
    active_revision = _active_revision(release_path)
    config_output = _run_bounded(
        _compose_command(compose_file, "config", "--format", "json"),
        cwd=release_path,
        policy=policy,
    )
    config_payload = _json_bytes(config_output, code="rendered_compose_invalid")
    compose = _mapping(config_payload, field="rendered_compose")
    ps_output = _run_bounded(
        _compose_command(compose_file, "ps", "--all", "--format", "json"),
        cwd=release_path,
        policy=policy,
    )
    ps_payload = _json_ps_bytes(ps_output or b"[]")
    ps_items = _ps_items(ps_payload)
    runtime_environments = _inspect_runtime_environments(
        ps_items,
        cwd=release_path,
        policy=policy,
    )
    inspected_revisions = _inspect_revisions(
        ps_items,
        cwd=release_path,
        policy=policy,
        expected_revision=active_revision,
    )
    # Report both candidate and running revisions, while individually
    # checking every running image against the current active marker.
    revisions = tuple(sorted({candidate_revision, active_revision, *inspected_revisions}))
    context = RuntimeContext(
        environment=policy.environment,
        host_fingerprint=_host_fingerprint(),
        revisions=revisions,
        captured_at=_now(),
    )
    topology = build_topology_observation(
        compose,
        ps_payload,
        context,
        runtime_environments=runtime_environments,
    )
    if topology.active_backend_service is None:
        raise CollectorFailure("runtime_active_upstream_unknown", Verdict.UNKNOWN)
    active_container_id = _running_container_ids(ps_items, topology.active_backend_service)[0]
    # The active image may predate the current collector module. Execute
    # audited, self-contained read-only source inside that active process;
    # DATABASE_URL never leaves the container, and no files are copied.
    child_output = _run_bounded(
        [
            "docker",
            "exec",
            active_container_id,
            "python",
            "-B",
            "-c",
            _legacy_child_source(release_path),
        ],
        cwd=release_path,
        policy=policy,
    )
    postgres = _parse_child_snapshot(
        _json_bytes(child_output, code="postgres_snapshot_invalid"), context
    )
    model, verified_context = build_verified_budget_model(postgres, topology, policy)
    result = evaluate(model, now=_now())
    return RuntimeCollection(
        result=_merge_diagnostics(result, topology.diagnostics),
        context=verified_context,
        candidate_revision=candidate_revision,
    )


def _result_payload(collection: RuntimeCollection) -> dict[str, object]:
    return {
        "source": COLLECTOR_SOURCE,
        "environment": collection.context.environment,
        "host_fingerprint": collection.context.host_fingerprint,
        "runtime_revisions": list(collection.context.revisions),
        "captured_at": collection.context.captured_at.isoformat(),
        "verdict": collection.result.as_dict(),
    }


def _failure_payload(failure: CollectorFailure) -> dict[str, object]:
    return {
        "source": COLLECTOR_SOURCE,
        "status": failure.status.value,
        "diagnostics": [
            {
                "code": failure.code,
                "status": failure.status.value,
                "message": "Trusted runtime collection did not complete safely",
            }
        ],
    }


def _child_main() -> int:
    try:
        database_url = os.environ.get("DATABASE_URL", "")
        if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise CollectorFailure("postgres_database_url_invalid", Verdict.BLOCKED)
        import psycopg

        connect_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        options = (
            "-c default_transaction_read_only=on "
            "-c statement_timeout=5000 "
            "-c lock_timeout=1000 "
            f"-c application_name={COLLECTOR_APPLICATION_NAME}"
        )
        with psycopg.connect(connect_url, connect_timeout=5, options=options) as connection:
            snapshot = read_postgres_runtime_snapshot(connection, YFC_APPLICATION_NAMES)
        payload = {
            "status": "PASS",
            "captured_at": _now().isoformat(),
            "postgres": {
                "server_version_major": snapshot.server_version_major,
                "max_connections": snapshot.max_connections,
                "superuser_reserved_connections": snapshot.superuser_reserved_connections,
                "reserved_connections": snapshot.reserved_connections,
                "current_connections": snapshot.current_connections,
                "observed_yfc_connections": snapshot.observed_yfc_connections,
                "observed_non_yfc_connections": snapshot.observed_non_yfc_connections,
                "unattributed_connections": snapshot.unattributed_connections,
            },
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    except CollectorFailure as failure:
        print(json.dumps(_failure_payload(failure), ensure_ascii=False, sort_keys=True))
        return 1 if failure.status == Verdict.BLOCKED else 2
    except ImportError, PostgresSnapshotError, OSError, ValueError:
        print(
            json.dumps(
                _failure_payload(CollectorFailure("postgres_snapshot_failed", Verdict.BLOCKED)),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    collect = subparsers.add_parser("collect")
    collect.add_argument("--release-path", type=Path, required=True)
    collect.add_argument("--compose-file", type=Path, default=Path("docker-compose.yml"))
    collect.add_argument("--json", action="store_true")
    child = subparsers.add_parser("postgres-child")
    child.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "postgres-child":
        return _child_main()
    try:
        collection = collect_runtime_snapshot(
            release_path=args.release_path,
            compose_file=args.compose_file,
        )
        print(json.dumps(_result_payload(collection), ensure_ascii=False, sort_keys=True))
        return {
            Verdict.PASS: 0,
            Verdict.BLOCKED: 1,
            Verdict.UNKNOWN: 2,
        }[collection.result.status]
    except CollectorFailure as failure:
        print(json.dumps(_failure_payload(failure), ensure_ascii=False, sort_keys=True))
        return 1 if failure.status == Verdict.BLOCKED else 2
    except ConfigurationError, OSError, ValueError:
        print(
            json.dumps(
                _failure_payload(CollectorFailure("collector_failed", Verdict.BLOCKED)),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    except Exception:
        print(
            json.dumps(
                _failure_payload(CollectorFailure("collector_failed", Verdict.BLOCKED)),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
