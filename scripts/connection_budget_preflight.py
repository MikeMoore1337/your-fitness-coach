"""Fail-closed PostgreSQL connection budget model and read-only preflight.

The module deliberately accepts sanitized effective topology as data. It does
not read a database URL, print environment contents, or mutate deployment state.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, TypeGuard, cast


class Verdict(StrEnum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class ConfigurationError(ValueError):
    """The preflight input is malformed and cannot be evaluated safely."""


class PostgresSnapshotError(RuntimeError):
    """A read-only PostgreSQL snapshot could not be collected safely."""


@dataclass(frozen=True)
class PoolSpec:
    name: str
    pool_size: int | None = None
    max_overflow: int | None = None
    pool_timeout_seconds: int | None = None
    connection_ceiling: int | None = None
    pool_type: str | None = None
    connection_ceiling_source: str | None = None

    def static_ceiling(self) -> int | None:
        if self.pool_type == "queue":
            if self.pool_size is None or self.max_overflow is None:
                return None
            return self.pool_size + self.max_overflow
        if self.pool_type in {"null", "special"}:
            return self.connection_ceiling
        return None


@dataclass(frozen=True)
class PhaseDemand:
    name: str
    processes: Mapping[str, int | None] | None
    other_connections: int | None
    pooler_backend_connections: int | None = None


@dataclass(frozen=True)
class PostgresCapacity:
    server_version_major: int | None = None
    max_connections: int | None = None
    superuser_reserved_connections: int | None = None
    reserved_connections: int | None = None
    current_connections: int | None = None
    observed_yfc_connections: int | None = None
    observed_non_yfc_connections: int | None = None


@dataclass(frozen=True)
class PoolerTopology:
    mode: str | None = None
    backend_capacity_source: str | None = None


@dataclass(frozen=True)
class TopologyInventory:
    """Explicit effective process and rollout-phase applicability inventory."""

    process_groups: Mapping[str, bool] | None = None
    rollout_phases: Mapping[str, bool] | None = None


@dataclass(frozen=True)
class EvidenceMetadata:
    """Provenance required before a model can be used as production evidence."""

    environment: str | None = None
    source: str | None = None
    captured_at: str | None = None
    max_age_seconds: int | None = None
    synthetic: bool | None = None


@dataclass(frozen=True)
class BudgetModel:
    postgres: PostgresCapacity
    pools: Mapping[str, PoolSpec]
    phases: tuple[PhaseDemand, ...]
    pooler: PoolerTopology
    safety_headroom_connections: int | None
    safety_headroom_source: str | None
    topology: TopologyInventory | None = None
    evidence: EvidenceMetadata | None = None


@dataclass(frozen=True)
class Diagnostic:
    code: str
    status: Verdict
    message: str


@dataclass(frozen=True)
class PreflightResult:
    status: Verdict
    usable_connections: int | None = None
    reserved_connections_effective: int | None = None
    observed_non_yfc_connections: int | None = None
    safety_headroom_connections: int | None = None
    worst_case_connections: int | None = None
    required_connections_with_headroom: int | None = None
    pool_caps: Mapping[str, int | None] = field(default_factory=dict)
    phase_reports: tuple[Mapping[str, object], ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "usable_connections": self.usable_connections,
            "reserved_connections_effective": self.reserved_connections_effective,
            "observed_non_yfc_connections": self.observed_non_yfc_connections,
            "safety_headroom_connections": self.safety_headroom_connections,
            "worst_case_connections": self.worst_case_connections,
            "required_connections_with_headroom": self.required_connections_with_headroom,
            "pool_caps": dict(self.pool_caps) if isinstance(self.pool_caps, Mapping) else {},
            "phases": [dict(phase) for phase in self.phase_reports],
            "diagnostics": [
                {"code": item.code, "status": item.status.value, "message": item.message}
                for item in self.diagnostics
            ],
        }


_POOL_ENV_KEYS: Final = {
    "DB_POOL_SIZE",
    "DB_MAX_OVERFLOW",
    "DB_POOL_TIMEOUT_SECONDS",
    "DB_POOL_RECYCLE_SECONDS",
}
_ENV_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$")
_POSTGRES_SNAPSHOT_SQL: Final = """
SELECT
    current_setting('server_version_num')::int,
    current_setting('max_connections')::int,
    current_setting('superuser_reserved_connections')::int,
    NULLIF(current_setting('reserved_connections', true), '')::int,
    (SELECT count(*)::int FROM pg_stat_activity)
"""
_ALLOWED_POOLER_MODES: Final = {"none", "session", "transaction"}
_ALLOWED_POOL_TYPES: Final = {"queue", "null", "special"}
_PRE_PROTECTED_STAGES: Final = ("backup", "migration", "candidate_start", "rollback")


def _is_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _mapping(value: object, *, field: str) -> Mapping[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _optional_int(value: object, *, field: str) -> int | None:
    if value is None:
        return None
    if not _is_int(value):
        raise ConfigurationError(f"{field} must be an integer")
    return value


def _optional_str(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigurationError(f"{field} must be text")
    return value


def _optional_bool(value: object, *, field: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ConfigurationError(f"{field} must be a boolean")
    return value


def _optional_bool_mapping(value: object, *, field: str) -> dict[str, bool] | None:
    if value is None:
        return None
    data = _mapping(value, field=field)
    result: dict[str, bool] = {}
    for name, present in data.items():
        if not isinstance(name, str) or not name.strip():
            raise ConfigurationError(f"{field} names must be non-empty text")
        if not isinstance(present, bool):
            raise ConfigurationError(f"{field}.{name} must be a boolean")
        result[name] = present
    return result


def model_from_mapping(payload: Mapping[str, object]) -> BudgetModel:
    """Build a model without applying defaults to missing critical values."""

    postgres = _mapping(payload.get("postgres"), field="postgres")
    postgres_capacity = PostgresCapacity(
        server_version_major=_optional_int(
            postgres.get("server_version_major"), field="postgres.server_version_major"
        ),
        max_connections=_optional_int(
            postgres.get("max_connections"), field="postgres.max_connections"
        ),
        superuser_reserved_connections=_optional_int(
            postgres.get("superuser_reserved_connections"),
            field="postgres.superuser_reserved_connections",
        ),
        reserved_connections=_optional_int(
            postgres.get("reserved_connections"), field="postgres.reserved_connections"
        ),
        current_connections=_optional_int(
            postgres.get("current_connections"), field="postgres.current_connections"
        ),
        observed_yfc_connections=_optional_int(
            postgres.get("observed_yfc_connections"),
            field="postgres.observed_yfc_connections",
        ),
        observed_non_yfc_connections=_optional_int(
            postgres.get("observed_non_yfc_connections"),
            field="postgres.observed_non_yfc_connections",
        ),
    )

    pools_value = payload.get("pools")
    pools_data = _mapping(pools_value, field="pools")
    pools: dict[str, PoolSpec] = {}
    for name, raw_pool in pools_data.items():
        if not isinstance(name, str) or not name.strip():
            raise ConfigurationError("pool names must be non-empty text")
        pool = _mapping(raw_pool, field=f"pools.{name}")
        pools[name] = PoolSpec(
            name=name,
            pool_size=_optional_int(pool.get("pool_size"), field=f"pools.{name}.pool_size"),
            max_overflow=_optional_int(
                pool.get("max_overflow"), field=f"pools.{name}.max_overflow"
            ),
            pool_timeout_seconds=_optional_int(
                pool.get("pool_timeout_seconds"),
                field=f"pools.{name}.pool_timeout_seconds",
            ),
            connection_ceiling=_optional_int(
                pool.get("connection_ceiling"),
                field=f"pools.{name}.connection_ceiling",
            ),
            pool_type=_optional_str(pool.get("pool_type"), field=f"pools.{name}.pool_type"),
            connection_ceiling_source=_optional_str(
                pool.get("connection_ceiling_source"),
                field=f"pools.{name}.connection_ceiling_source",
            ),
        )

    phases_value = payload.get("phases")
    if phases_value is None:
        phases_data: Sequence[object] = ()
    elif isinstance(phases_value, list):
        phases_data = phases_value
    else:
        raise ConfigurationError("phases must be an array")

    phases: list[PhaseDemand] = []
    for index, raw_phase in enumerate(phases_data):
        phase = _mapping(raw_phase, field=f"phases[{index}]")
        phase_name = phase.get("name")
        if not isinstance(phase_name, str) or not phase_name.strip():
            raise ConfigurationError(f"phases[{index}].name must be non-empty text")
        processes_value = phase.get("processes")
        if processes_value is None:
            processes = None
        else:
            process_data = _mapping(processes_value, field=f"phases[{index}].processes")
            processes = {}
            for process_name, count in process_data.items():
                if not isinstance(process_name, str) or not process_name.strip():
                    raise ConfigurationError("process names must be non-empty text")
                processes[process_name] = _optional_int(
                    count, field=f"phases[{index}].processes.{process_name}"
                )
        phases.append(
            PhaseDemand(
                name=phase_name,
                processes=processes,
                other_connections=_optional_int(
                    phase.get("other_connections"),
                    field=f"phases[{index}].other_connections",
                ),
                pooler_backend_connections=_optional_int(
                    phase.get("pooler_backend_connections"),
                    field=f"phases[{index}].pooler_backend_connections",
                ),
            )
        )

    pooler = _mapping(payload.get("pooler"), field="pooler")
    topology = _mapping(payload.get("topology"), field="topology")
    evidence_value = payload.get("evidence")
    evidence_data = _mapping(evidence_value, field="evidence")
    return BudgetModel(
        postgres=postgres_capacity,
        pools=pools,
        phases=tuple(phases),
        pooler=PoolerTopology(
            mode=_optional_str(pooler.get("mode"), field="pooler.mode"),
            backend_capacity_source=_optional_str(
                pooler.get("backend_capacity_source"),
                field="pooler.backend_capacity_source",
            ),
        ),
        safety_headroom_connections=_optional_int(
            payload.get("safety_headroom_connections"),
            field="safety_headroom_connections",
        ),
        safety_headroom_source=_optional_str(
            payload.get("safety_headroom_source"), field="safety_headroom_source"
        ),
        topology=TopologyInventory(
            process_groups=_optional_bool_mapping(
                topology.get("process_groups"), field="topology.process_groups"
            ),
            rollout_phases=_optional_bool_mapping(
                topology.get("rollout_phases"), field="topology.rollout_phases"
            ),
        ),
        evidence=(
            EvidenceMetadata(
                environment=_optional_str(
                    evidence_data.get("environment"), field="evidence.environment"
                ),
                source=_optional_str(evidence_data.get("source"), field="evidence.source"),
                captured_at=_optional_str(
                    evidence_data.get("captured_at"), field="evidence.captured_at"
                ),
                max_age_seconds=_optional_int(
                    evidence_data.get("max_age_seconds"), field="evidence.max_age_seconds"
                ),
                synthetic=_optional_bool(
                    evidence_data.get("synthetic"), field="evidence.synthetic"
                ),
            )
            if evidence_value is not None
            else None
        ),
    )


def read_safe_pool_environment(path: Path) -> dict[str, int]:
    """Read only allowlisted numeric pool settings; never returns secrets."""

    values: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = _ENV_ASSIGNMENT.match(line)
        if match is None or match.group(1) not in _POOL_ENV_KEYS:
            continue
        raw_value = match.group(2).split(" #", maxsplit=1)[0].strip()
        if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in {'"', "'"}:
            raw_value = raw_value[1:-1]
        if not re.fullmatch(r"[0-9]+", raw_value):
            raise ConfigurationError(f"{match.group(1)} must be a non-negative integer")
        values[match.group(1)] = int(raw_value)
    return values


def read_postgres_snapshot(connection: object) -> PostgresCapacity:
    """Read numeric PostgreSQL settings and current session count only."""

    cursor = None
    try:
        cursor = connection.cursor()  # type: ignore[attr-defined]
        cursor.execute(_POSTGRES_SNAPSHOT_SQL)
        row = cursor.fetchone()
        if not isinstance(row, Sequence) or len(row) != 5:
            raise PostgresSnapshotError("read-only PostgreSQL snapshot returned no numeric row")
        values: list[int | None] = []
        for value in row:
            if value is None:
                values.append(None)
                continue
            if isinstance(value, bool):
                raise PostgresSnapshotError("read-only PostgreSQL snapshot returned invalid data")
            try:
                parsed = int(value)
            except (TypeError, ValueError) as exc:
                raise PostgresSnapshotError(
                    "read-only PostgreSQL snapshot returned invalid data"
                ) from exc
            if parsed < 0:
                raise PostgresSnapshotError("read-only PostgreSQL snapshot returned invalid data")
            values.append(parsed)
        version_num, max_connections, superuser_reserved, reserved, current = values
        if version_num is None or max_connections is None or superuser_reserved is None:
            raise PostgresSnapshotError("read-only PostgreSQL snapshot omitted required settings")
        return PostgresCapacity(
            server_version_major=version_num // 10_000,
            max_connections=max_connections,
            superuser_reserved_connections=superuser_reserved,
            reserved_connections=reserved,
            current_connections=current,
        )
    except PostgresSnapshotError:
        raise
    except Exception:
        raise PostgresSnapshotError("read-only PostgreSQL snapshot failed") from None
    finally:
        if cursor is not None:
            with suppress(Exception):
                cursor.close()


def validate_rollout_stage_order(stages: Sequence[str]) -> None:
    """Require the future gate before every connection-increasing stage."""

    gate = "connection_budget_preflight"
    positions = [index for index, stage in enumerate(stages) if stage == gate]
    if len(positions) != 1:
        raise ConfigurationError("exactly one connection_budget_preflight stage is required")
    gate_position = positions[0]
    violations = [
        stage
        for stage in _PRE_PROTECTED_STAGES
        if stage in stages and stages.index(stage) < gate_position
    ]
    if violations:
        raise ConfigurationError("connection budget preflight must precede protected stages")


def _issue(issues: list[Diagnostic], status: Verdict, code: str, message: str) -> None:
    issues.append(Diagnostic(code=code, status=status, message=message))


def _looks_synthetic(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.casefold()
    return any(token in lowered for token in ("synthetic", "fixture", "test", "example"))


def _validate_runtime_evidence(
    model: BudgetModel,
    issues: list[Diagnostic],
    *,
    now: datetime | None,
) -> None:
    evidence = model.evidence
    if evidence is None:
        _issue(
            issues,
            Verdict.UNKNOWN,
            "runtime_evidence_unknown",
            "Production preflight requires provenance for the effective runtime snapshot",
        )
        return
    if evidence.environment is None or not evidence.environment.strip():
        _issue(
            issues,
            Verdict.UNKNOWN,
            "evidence_environment_unknown",
            "Runtime snapshot environment is unknown",
        )
    elif evidence.environment != "production":
        _issue(
            issues,
            Verdict.BLOCKED,
            "evidence_environment_invalid",
            "The supplied snapshot is not identified as production evidence",
        )
    if evidence.source is None or not evidence.source.strip():
        _issue(
            issues,
            Verdict.UNKNOWN,
            "evidence_source_unknown",
            "Runtime snapshot source is unknown",
        )
    if evidence.synthetic is not False:
        _issue(
            issues,
            Verdict.UNKNOWN,
            "synthetic_evidence_not_allowed",
            "Synthetic or undeclared evidence cannot authorize production preflight",
        )
    if evidence.captured_at is None or evidence.max_age_seconds is None:
        _issue(
            issues,
            Verdict.UNKNOWN,
            "snapshot_freshness_unknown",
            "Snapshot capture time and freshness bound are required",
        )
        return
    if not _is_int(evidence.max_age_seconds) or evidence.max_age_seconds <= 0:
        _issue(
            issues,
            Verdict.BLOCKED,
            "snapshot_freshness_invalid",
            "Snapshot max_age_seconds must be a positive integer",
        )
        return
    try:
        captured_at = datetime.fromisoformat(evidence.captured_at)
    except ValueError:
        _issue(
            issues,
            Verdict.BLOCKED,
            "snapshot_timestamp_invalid",
            "Snapshot captured_at is not a valid timestamp",
        )
        return
    if captured_at.tzinfo is None:
        _issue(
            issues,
            Verdict.BLOCKED,
            "snapshot_timestamp_invalid",
            "Snapshot captured_at must include a timezone",
        )
        return
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    age_seconds = (current_time - captured_at.astimezone(UTC)).total_seconds()
    if age_seconds < 0:
        _issue(
            issues,
            Verdict.UNKNOWN,
            "snapshot_timestamp_in_future",
            "Snapshot capture time is later than the preflight clock",
        )
    elif age_seconds > evidence.max_age_seconds:
        _issue(
            issues,
            Verdict.BLOCKED,
            "snapshot_stale",
            "The effective runtime snapshot is older than its declared freshness bound",
        )


def _validate_topology(
    model: BudgetModel,
    issues: list[Diagnostic],
) -> tuple[Mapping[str, bool] | None, Mapping[str, bool] | None]:
    topology = model.topology
    if topology is None:
        _issue(
            issues,
            Verdict.UNKNOWN,
            "topology_inventory_unknown",
            "Effective process and rollout-phase inventory is missing",
        )
        return None, None

    process_groups = topology.process_groups
    if process_groups is None:
        _issue(
            issues,
            Verdict.UNKNOWN,
            "process_inventory_unknown",
            "Effective process-group inventory is missing",
        )
    elif not process_groups:
        _issue(
            issues,
            Verdict.UNKNOWN,
            "process_inventory_unknown",
            "An empty process-group inventory does not prove zero deployment load",
        )
    elif not any(present is True for present in process_groups.values()):
        _issue(
            issues,
            Verdict.UNKNOWN,
            "process_inventory_unknown",
            "No effective process group is declared present",
        )

    rollout_phases = topology.rollout_phases
    if rollout_phases is None:
        _issue(
            issues,
            Verdict.UNKNOWN,
            "phase_inventory_unknown",
            "Effective rollout-phase inventory is missing",
        )
    elif not rollout_phases or not any(phase is True for phase in rollout_phases.values()):
        _issue(
            issues,
            Verdict.UNKNOWN,
            "phase_inventory_unknown",
            "No applicable rollout phase is explicitly declared",
        )

    if process_groups is None or rollout_phases is None:
        return process_groups, rollout_phases

    for pool_name, pool_spec in model.pools.items():
        if not isinstance(pool_name, str) or not pool_name.strip():
            _issue(
                issues,
                Verdict.BLOCKED,
                "process_inventory_invalid",
                "Process-group names must be non-empty text",
            )
            continue
        if pool_name not in process_groups:
            _issue(
                issues,
                Verdict.UNKNOWN,
                "process_inventory_incomplete",
                "A configured process pool is absent from the effective process inventory",
            )
        if pool_spec.name != pool_name:
            _issue(
                issues,
                Verdict.BLOCKED,
                "pool_name_mismatch",
                "A process pool name does not match its inventory key",
            )

    for process_name, present in process_groups.items():
        if (
            not isinstance(process_name, str)
            or not process_name.strip()
            or not isinstance(present, bool)
        ):
            _issue(
                issues,
                Verdict.BLOCKED,
                "process_inventory_invalid",
                "Process inventory entries must be non-empty names and booleans",
            )
            continue
        if present and process_name not in model.pools:
            _issue(
                issues,
                Verdict.UNKNOWN,
                "process_pool_unknown",
                "A declared process group has no effective pool settings",
            )

    supplied_phase_names = [phase.name for phase in model.phases]
    supplied_phase_set = set(supplied_phase_names)
    for phase_name, applicable in rollout_phases.items():
        if (
            not isinstance(phase_name, str)
            or not phase_name.strip()
            or not isinstance(applicable, bool)
        ):
            _issue(
                issues,
                Verdict.BLOCKED,
                "phase_inventory_invalid",
                "Rollout phase inventory entries must be non-empty names and booleans",
            )
            continue
        if applicable and phase_name not in supplied_phase_set:
            _issue(
                issues,
                Verdict.UNKNOWN,
                "rollout_phase_missing",
                "An applicable rollout phase is missing from phase demand data",
            )
        elif not applicable and phase_name in supplied_phase_set:
            _issue(
                issues,
                Verdict.BLOCKED,
                "rollout_phase_not_applicable",
                "A phase supplied in demand data is explicitly marked not applicable",
            )
    for phase_name in supplied_phase_set:
        if phase_name not in rollout_phases:
            _issue(
                issues,
                Verdict.UNKNOWN,
                "phase_inventory_incomplete",
                "A supplied rollout phase is absent from the effective phase inventory",
            )

    for phase in model.phases:
        if phase.processes is None:
            continue
        for process_name, replicas in phase.processes.items():
            if process_name not in process_groups:
                _issue(
                    issues,
                    Verdict.UNKNOWN,
                    "process_inventory_incomplete",
                    "A phase references a process absent from the effective inventory",
                )
            elif process_groups[process_name] is False and _is_int(replicas) and replicas > 0:
                _issue(
                    issues,
                    Verdict.BLOCKED,
                    "process_not_applicable",
                    "A phase assigns replicas to a process explicitly marked absent",
                )
        for process_name, present in process_groups.items():
            if present and process_name not in phase.processes:
                _issue(
                    issues,
                    Verdict.UNKNOWN,
                    "phase_process_inventory_incomplete",
                    "A phase does not enumerate every declared process group; use zero for inactive groups",
                )

    return process_groups, rollout_phases


def _pool_cap(pool_name: str, pool_spec: PoolSpec, issues: list[Diagnostic]) -> int | None:
    if pool_spec.pool_type is None:
        _issue(
            issues,
            Verdict.UNKNOWN,
            "pool_type_unknown",
            "A process pool is missing its effective pool type",
        )
        if pool_spec.pool_size is None or pool_spec.max_overflow is None:
            _issue(
                issues,
                Verdict.UNKNOWN,
                "pool_settings_unknown",
                "A pooled process is missing pool_size or max_overflow",
            )
        return None
    if pool_spec.pool_type not in _ALLOWED_POOL_TYPES:
        _issue(issues, Verdict.BLOCKED, "pool_type_invalid", "A process pool type is invalid")
        return None
    if pool_spec.pool_type == "queue":
        if pool_spec.connection_ceiling is not None:
            _issue(
                issues,
                Verdict.BLOCKED,
                "queue_ceiling_conflict",
                f"QueuePool {pool_name} cannot override pool_size + max_overflow with connection_ceiling",
            )
        if pool_spec.pool_size is None or pool_spec.max_overflow is None:
            _issue(
                issues,
                Verdict.UNKNOWN,
                "pool_settings_unknown",
                "A QueuePool is missing pool_size or max_overflow",
            )
            return None
        if not _is_int(pool_spec.pool_size) or pool_spec.pool_size < 1:
            _issue(issues, Verdict.BLOCKED, "pool_size_invalid", "A pool_size is invalid")
        if not _is_int(pool_spec.max_overflow) or pool_spec.max_overflow < 0:
            _issue(issues, Verdict.BLOCKED, "max_overflow_invalid", "A max_overflow is invalid")
        if pool_spec.pool_timeout_seconds is None:
            _issue(
                issues,
                Verdict.UNKNOWN,
                "pool_timeout_unknown",
                "A QueuePool is missing pool_timeout_seconds",
            )
        elif not _is_int(pool_spec.pool_timeout_seconds) or pool_spec.pool_timeout_seconds < 1:
            _issue(
                issues,
                Verdict.BLOCKED,
                "pool_timeout_invalid",
                "A pool_timeout_seconds value is invalid",
            )
        if (
            _is_int(pool_spec.pool_size)
            and pool_spec.pool_size >= 1
            and _is_int(pool_spec.max_overflow)
            and pool_spec.max_overflow >= 0
        ):
            return pool_spec.pool_size + pool_spec.max_overflow
        return None

    if any(
        value is not None
        for value in (
            pool_spec.pool_size,
            pool_spec.max_overflow,
            pool_spec.pool_timeout_seconds,
        )
    ):
        _issue(
            issues,
            Verdict.BLOCKED,
            "special_pool_settings_conflict",
            "NullPool or a special process cannot also declare QueuePool settings",
        )
    if pool_spec.connection_ceiling is None:
        _issue(
            issues,
            Verdict.UNKNOWN,
            "pool_ceiling_unknown",
            "NullPool or a special process requires an explicit connection ceiling",
        )
        return None
    if not _is_int(pool_spec.connection_ceiling) or pool_spec.connection_ceiling <= 0:
        _issue(
            issues,
            Verdict.BLOCKED,
            "pool_ceiling_invalid",
            "A NullPool or special-process connection ceiling must be positive",
        )
        return None
    if (
        pool_spec.connection_ceiling_source is None
        or not pool_spec.connection_ceiling_source.strip()
    ):
        _issue(
            issues,
            Verdict.UNKNOWN,
            "pool_ceiling_source_unknown",
            "An explicit connection ceiling requires a provenance source",
        )
    return pool_spec.connection_ceiling


def evaluate(
    model: BudgetModel,
    *,
    require_runtime_evidence: bool = True,
    now: datetime | None = None,
) -> PreflightResult:
    """Evaluate every phase without inventing missing capacity inputs."""

    issues: list[Diagnostic] = []
    if require_runtime_evidence:
        _validate_runtime_evidence(model, issues, now=now)
    _validate_topology(model, issues)
    postgres = model.postgres

    max_connections = postgres.max_connections
    if max_connections is None:
        _issue(
            issues,
            Verdict.UNKNOWN,
            "max_connections_unknown",
            "PostgreSQL max_connections is unknown",
        )
    elif not _is_int(max_connections) or max_connections <= 0:
        _issue(
            issues,
            Verdict.BLOCKED,
            "max_connections_invalid",
            "PostgreSQL max_connections is invalid",
        )

    superuser_reserved = postgres.superuser_reserved_connections
    if superuser_reserved is None:
        _issue(
            issues,
            Verdict.UNKNOWN,
            "superuser_reserved_connections_unknown",
            "PostgreSQL superuser reserved capacity is unknown",
        )
    elif not _is_int(superuser_reserved) or superuser_reserved < 0:
        _issue(
            issues,
            Verdict.BLOCKED,
            "superuser_reserved_connections_invalid",
            "PostgreSQL superuser reserved capacity is invalid",
        )

    version_major = postgres.server_version_major
    if version_major is None:
        _issue(
            issues,
            Verdict.UNKNOWN,
            "postgres_version_unknown",
            "PostgreSQL major version is unknown",
        )
    elif not _is_int(version_major) or version_major <= 0:
        _issue(
            issues,
            Verdict.BLOCKED,
            "postgres_version_invalid",
            "PostgreSQL major version is invalid",
        )

    reserved = postgres.reserved_connections
    if version_major is not None and _is_int(version_major) and version_major >= 16:
        if reserved is None:
            _issue(
                issues,
                Verdict.UNKNOWN,
                "reserved_connections_unknown",
                "PostgreSQL reserved_connections is required for PostgreSQL 16 or newer",
            )
    elif version_major is not None and _is_int(version_major) and version_major < 16:
        reserved = 0 if reserved is None else reserved
    if reserved is not None and (not _is_int(reserved) or reserved < 0):
        _issue(
            issues,
            Verdict.BLOCKED,
            "reserved_connections_invalid",
            "PostgreSQL reserved capacity is invalid",
        )

    usable: int | None = None
    if _is_int(max_connections) and _is_int(superuser_reserved) and _is_int(reserved):
        usable = max_connections - superuser_reserved - reserved
        if usable < 0:
            _issue(
                issues,
                Verdict.BLOCKED,
                "reserved_capacity_exceeds_maximum",
                "PostgreSQL reserved capacity exceeds max_connections",
            )

    current = postgres.current_connections
    if current is None:
        _issue(
            issues,
            Verdict.UNKNOWN,
            "current_connections_unknown",
            "Current PostgreSQL connection occupancy is unknown",
        )
    elif not _is_int(current) or current < 0:
        _issue(
            issues,
            Verdict.BLOCKED,
            "current_connections_invalid",
            "Current PostgreSQL connection occupancy is invalid",
        )
    elif _is_int(max_connections) and current > max_connections:
        _issue(
            issues,
            Verdict.BLOCKED,
            "current_connections_exceed_maximum",
            "Current PostgreSQL occupancy exceeds max_connections",
        )

    observed_non_yfc = postgres.observed_non_yfc_connections
    observed_yfc = postgres.observed_yfc_connections
    for name, value in (
        ("observed_non_yfc_connections", observed_non_yfc),
        ("observed_yfc_connections", observed_yfc),
    ):
        if value is not None and (not _is_int(value) or value < 0):
            _issue(issues, Verdict.BLOCKED, f"{name}_invalid", f"{name} is invalid")

    if current is not None and _is_int(current):
        if observed_non_yfc is None and observed_yfc is None:
            _issue(
                issues,
                Verdict.UNKNOWN,
                "connection_attribution_unknown",
                "Current sessions cannot be attributed to YFC and non-YFC consumers",
            )
        elif observed_non_yfc is None and _is_int(observed_yfc):
            observed_non_yfc = current - observed_yfc
        elif observed_yfc is None and _is_int(observed_non_yfc):
            observed_yfc = current - observed_non_yfc
        elif (
            _is_int(observed_non_yfc)
            and _is_int(observed_yfc)
            and observed_non_yfc + observed_yfc != current
        ):
            _issue(
                issues,
                Verdict.BLOCKED,
                "connection_attribution_inconsistent",
                "YFC and non-YFC session counts do not reconcile to current occupancy",
            )
        if observed_non_yfc is not None and observed_non_yfc < 0:
            _issue(
                issues,
                Verdict.BLOCKED,
                "connection_attribution_inconsistent",
                "YFC-attributed sessions exceed current occupancy",
            )
        if observed_yfc is not None and observed_yfc < 0:
            _issue(
                issues,
                Verdict.BLOCKED,
                "connection_attribution_inconsistent",
                "Non-YFC-attributed sessions exceed current occupancy",
            )
    else:
        _issue(
            issues,
            Verdict.UNKNOWN,
            "connection_attribution_unknown",
            "Current session attribution cannot be verified without occupancy",
        )

    if usable is not None and observed_non_yfc is not None and observed_non_yfc > usable:
        _issue(
            issues,
            Verdict.BLOCKED,
            "observed_non_yfc_exceeds_usable_capacity",
            "Observed non-YFC sessions already exceed usable PostgreSQL capacity",
        )

    safety = model.safety_headroom_connections
    if (
        safety is None
        or not model.safety_headroom_source
        or not model.safety_headroom_source.strip()
    ):
        _issue(
            issues,
            Verdict.UNKNOWN,
            "safety_headroom_unknown",
            "Safety headroom and its source must be supplied explicitly",
        )
    elif not _is_int(safety) or safety <= 0:
        _issue(
            issues,
            Verdict.BLOCKED,
            "safety_headroom_invalid",
            "Safety headroom must be a positive integer",
        )
    elif require_runtime_evidence and _looks_synthetic(model.safety_headroom_source):
        _issue(
            issues,
            Verdict.UNKNOWN,
            "safety_headroom_source_not_production",
            "Synthetic or test safety-headroom provenance cannot authorize production preflight",
        )

    pooler_mode = model.pooler.mode
    if pooler_mode is None:
        _issue(issues, Verdict.UNKNOWN, "pooler_topology_unknown", "Pooler topology is unknown")
    elif pooler_mode not in _ALLOWED_POOLER_MODES:
        _issue(issues, Verdict.BLOCKED, "pooler_topology_invalid", "Pooler topology is invalid")
    elif pooler_mode in {"session", "transaction"} and (
        model.pooler.backend_capacity_source is None
        or not model.pooler.backend_capacity_source.strip()
    ):
        _issue(
            issues,
            Verdict.UNKNOWN,
            "pooler_backend_source_unknown",
            "A pooler backend capacity requires a provenance source",
        )

    pool_caps: dict[str, int | None] = {}
    for pool_name, pool_spec in model.pools.items():
        pool_caps[pool_name] = _pool_cap(pool_name, pool_spec, issues)

    phase_reports: list[Mapping[str, object]] = []
    seen_phase_names: set[str] = set()
    projected_values: list[int] = []
    if not model.phases:
        _issue(issues, Verdict.UNKNOWN, "phases_unknown", "No rollout phases were supplied")

    for phase in model.phases:
        if phase.name in seen_phase_names:
            _issue(issues, Verdict.BLOCKED, "duplicate_phase", "Rollout phase names must be unique")
        seen_phase_names.add(phase.name)

        process_connections: dict[str, int] = {}
        process_total: int | None = 0
        if phase.processes is None:
            _issue(
                issues,
                Verdict.UNKNOWN,
                "phase_processes_unknown",
                "A rollout phase is missing process replica counts",
            )
            process_total = None
        else:
            for process_name, replicas in phase.processes.items():
                if replicas is None:
                    _issue(
                        issues,
                        Verdict.UNKNOWN,
                        "replica_count_unknown",
                        "A rollout phase has an unknown process replica count",
                    )
                    process_total = None
                    continue
                if not _is_int(replicas) or replicas < 0:
                    _issue(
                        issues,
                        Verdict.BLOCKED,
                        "replica_count_invalid",
                        "A rollout phase has an invalid process replica count",
                    )
                    process_total = None
                    continue
                process_pool = model.pools.get(process_name)
                cap = pool_caps.get(process_name) if process_pool is not None else None
                if process_pool is None:
                    _issue(
                        issues,
                        Verdict.UNKNOWN,
                        "process_pool_unknown",
                        "A rollout phase references a process without effective pool settings",
                    )
                    process_total = None
                    continue
                if cap is None:
                    _issue(
                        issues,
                        Verdict.UNKNOWN,
                        "process_pool_ceiling_unknown",
                        "A rollout phase references a process with unknown connection ceiling",
                    )
                    process_total = None
                    continue
                contribution = replicas * cap
                process_connections[process_name] = contribution
                if process_total is not None:
                    process_total += contribution

        other = phase.other_connections
        if other is None:
            _issue(
                issues,
                Verdict.UNKNOWN,
                "other_consumers_unknown",
                "A rollout phase is missing known non-YFC consumer connections",
            )
        elif not _is_int(other) or other < 0:
            _issue(
                issues,
                Verdict.BLOCKED,
                "other_consumers_invalid",
                "A rollout phase has invalid non-YFC consumer connections",
            )

        app_connections = process_total
        if pooler_mode in {"session", "transaction"}:
            if phase.pooler_backend_connections is None:
                _issue(
                    issues,
                    Verdict.UNKNOWN,
                    "pooler_backend_limit_unknown",
                    "A pooler phase is missing its verified PostgreSQL backend connection cap",
                )
                app_connections = None
            elif (
                not _is_int(phase.pooler_backend_connections)
                or phase.pooler_backend_connections <= 0
            ):
                _issue(
                    issues,
                    Verdict.BLOCKED,
                    "pooler_backend_limit_invalid",
                    "A pooler backend connection cap must be positive",
                )
                app_connections = None
            else:
                app_connections = phase.pooler_backend_connections
                if (
                    pooler_mode == "session"
                    and process_total is not None
                    and phase.pooler_backend_connections < process_total
                ):
                    _issue(
                        issues,
                        Verdict.BLOCKED,
                        "pooler_backend_limit_below_demand",
                        "A session pooler backend cap is below the phase session demand",
                    )
        elif phase.pooler_backend_connections is not None:
            _issue(
                issues,
                Verdict.BLOCKED,
                "pooler_backend_limit_unexpected",
                "A PostgreSQL backend cap is supplied while pooler mode is none",
            )

        projected: int | None = None
        headroom_after: int | None = None
        if (
            app_connections is not None
            and _is_int(other)
            and observed_non_yfc is not None
            and _is_int(observed_non_yfc)
        ):
            projected = observed_non_yfc + app_connections + other
            projected_values.append(projected)
            if usable is not None:
                headroom_after = usable - projected

        phase_reports.append(
            {
                "name": phase.name,
                "process_connections": process_connections,
                "app_connections": app_connections,
                "other_connections": other,
                "projected_connections": projected,
                "headroom_after": headroom_after,
            }
        )

    worst_case = max(projected_values) if projected_values else None
    required_with_headroom = None
    if worst_case is not None and _is_int(safety):
        required_with_headroom = worst_case + safety
        if usable is not None and required_with_headroom > usable:
            _issue(
                issues,
                Verdict.BLOCKED,
                "insufficient_headroom",
                "The worst rollout phase exceeds usable PostgreSQL capacity with headroom",
            )

    if any(item.status == Verdict.BLOCKED for item in issues):
        status = Verdict.BLOCKED
    elif any(item.status == Verdict.UNKNOWN for item in issues):
        status = Verdict.UNKNOWN
    else:
        status = Verdict.PASS

    return PreflightResult(
        status=status,
        usable_connections=usable,
        reserved_connections_effective=reserved,
        observed_non_yfc_connections=observed_non_yfc,
        safety_headroom_connections=safety if _is_int(safety) else None,
        worst_case_connections=worst_case,
        required_connections_with_headroom=required_with_headroom,
        pool_caps=pool_caps,
        phase_reports=tuple(phase_reports),
        diagnostics=tuple(issues),
    )


def _fallback_result(status: Verdict, code: str, message: str) -> PreflightResult:
    return PreflightResult(
        status=status,
        diagnostics=(Diagnostic(code=code, status=status, message=message),),
    )


def _print_result(result: PreflightResult, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result.as_dict(), ensure_ascii=False, sort_keys=True))
        return
    print(f"status={result.status.value}")
    for item in result.diagnostics:
        print(f"{item.status.value.lower()}={item.code}: {item.message}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        payload = json.loads(args.config.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ConfigurationError("configuration must be an object")
        result = evaluate(model_from_mapping(cast(Mapping[str, object], payload)))
    except FileNotFoundError:
        result = _fallback_result(
            Verdict.UNKNOWN,
            "configuration_unreadable",
            "The sanitized effective configuration could not be read",
        )
    except OSError:
        result = _fallback_result(
            Verdict.UNKNOWN,
            "configuration_unreadable",
            "The sanitized effective configuration could not be read",
        )
    except json.JSONDecodeError:
        result = _fallback_result(
            Verdict.BLOCKED,
            "configuration_malformed",
            "The sanitized effective configuration is not valid JSON",
        )
    except ConfigurationError:
        result = _fallback_result(
            Verdict.BLOCKED,
            "configuration_invalid",
            "The sanitized effective configuration contains invalid values",
        )
    except Exception:
        result = _fallback_result(
            Verdict.UNKNOWN,
            "preflight_execution_failed",
            "The connection budget preflight did not complete safely",
        )

    _print_result(result, as_json=args.json)
    return {Verdict.PASS: 0, Verdict.BLOCKED: 1, Verdict.UNKNOWN: 2}[result.status]


if __name__ == "__main__":
    raise SystemExit(main())
