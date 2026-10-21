from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from scripts.connection_budget_preflight import (
    BudgetModel,
    ConfigurationError,
    EvidenceMetadata,
    PhaseDemand,
    PoolerTopology,
    PoolSpec,
    PostgresCapacity,
    PostgresSnapshotError,
    TopologyInventory,
    Verdict,
    evaluate,
    main,
    model_from_mapping,
    read_postgres_runtime_snapshot,
    read_postgres_snapshot,
    read_safe_pool_environment,
    validate_rollout_stage_order,
)


def _evaluate(model: BudgetModel):
    """Exercise the mathematical model without treating fixtures as production evidence."""

    return evaluate(model, require_runtime_evidence=False)


def _model(
    *,
    max_connections: int | None = 200,
    reserved_connections: int | None = 2,
    observed_non_yfc: int | None = 12,
    observed_yfc: int | None = 8,
    current_connections: int | None = None,
    phases: tuple[PhaseDemand, ...] | None = None,
    backend_pool: PoolSpec | None = None,
) -> BudgetModel:
    backend = backend_pool or PoolSpec(
        name="backend",
        pool_size=10,
        max_overflow=20,
        pool_timeout_seconds=30,
        pool_type="queue",
    )
    default_phases = (
        PhaseDemand("steady-state", {"backend": 1, "worker": 1, "migration": 0, "setup": 0}, 0),
        PhaseDemand(
            "candidate-overlap", {"backend": 2, "worker": 1, "migration": 0, "setup": 0}, 0
        ),
        PhaseDemand(
            "unexpected-all-slots", {"backend": 2, "worker": 2, "migration": 0, "setup": 0}, 0
        ),
        PhaseDemand("backup", {"backend": 1, "worker": 1, "migration": 0, "setup": 0}, 1),
        PhaseDemand("migration", {"backend": 1, "worker": 1, "migration": 1, "setup": 0}, 0),
        PhaseDemand("setup-seed", {"backend": 1, "worker": 1, "migration": 0, "setup": 1}, 0),
        PhaseDemand("rollback", {"backend": 2, "worker": 1, "migration": 0, "setup": 0}, 0),
    )
    effective_phases = phases or default_phases
    active_processes = {name for phase in effective_phases for name in (phase.processes or {})}
    return BudgetModel(
        postgres=PostgresCapacity(
            server_version_major=16,
            max_connections=max_connections,
            superuser_reserved_connections=3,
            reserved_connections=reserved_connections,
            current_connections=(
                current_connections
                if current_connections is not None
                else (observed_non_yfc or 0) + (observed_yfc or 0)
            ),
            observed_non_yfc_connections=observed_non_yfc,
            observed_yfc_connections=observed_yfc,
        ),
        pools={
            "backend": backend,
            "worker": PoolSpec("worker", 10, 20, 30, pool_type="queue"),
            "migration": PoolSpec(
                "migration",
                connection_ceiling=1,
                pool_type="null",
                connection_ceiling_source="backend/alembic/env.py",
            ),
            "setup": PoolSpec(
                "setup",
                connection_ceiling=30,
                pool_type="special",
                connection_ceiling_source="backend/setup-entrypoint.sh",
            ),
        },
        phases=effective_phases,
        pooler=PoolerTopology("none"),
        safety_headroom_connections=10,
        safety_headroom_source="synthetic-test-input",
        topology=TopologyInventory(
            process_groups={
                name: name in active_processes
                for name in ("backend", "worker", "migration", "setup")
            },
            rollout_phases={phase.name: True for phase in effective_phases},
        ),
        evidence=EvidenceMetadata(
            environment="test",
            source="synthetic-test-fixture",
            captured_at="2026-10-19T00:00:00+00:00",
            max_age_seconds=86_400,
            synthetic=True,
        ),
    )


def test_default_2c_3c_4c_and_setup_phases_pass_with_explicit_headroom() -> None:
    result = _evaluate(_model())

    assert result.status == Verdict.PASS
    assert result.pool_caps == {"backend": 30, "worker": 30, "migration": 1, "setup": 30}
    assert result.worst_case_connections == 132
    assert result.required_connections_with_headroom == 142
    reports = {str(item["name"]): item for item in result.phase_reports}
    assert reports["steady-state"]["app_connections"] == 60
    assert reports["candidate-overlap"]["app_connections"] == 90
    assert reports["unexpected-all-slots"]["app_connections"] == 120
    setup_connections = reports["setup-seed"]["process_connections"]
    assert isinstance(setup_connections, Mapping)
    assert setup_connections["setup"] == 30


def test_insufficient_budget_is_blocked() -> None:
    result = _evaluate(_model(max_connections=135))

    assert result.status == Verdict.BLOCKED
    assert any(item.code == "insufficient_headroom" for item in result.diagnostics)


def test_unknown_max_connections_is_not_pass() -> None:
    result = _evaluate(_model(max_connections=None))

    assert result.status == Verdict.UNKNOWN
    assert any(item.code == "max_connections_unknown" for item in result.diagnostics)


def test_postgres_16_requires_reserved_connections() -> None:
    result = _evaluate(_model(reserved_connections=None))

    assert result.status == Verdict.UNKNOWN
    assert any(item.code == "reserved_connections_unknown" for item in result.diagnostics)


def test_missing_pool_settings_are_unknown() -> None:
    result = _evaluate(_model(backend_pool=PoolSpec("backend", pool_timeout_seconds=30)))

    assert result.status == Verdict.UNKNOWN
    assert any(item.code == "pool_settings_unknown" for item in result.diagnostics)


def test_multiple_replicas_and_rollback_are_counted() -> None:
    phases = (
        PhaseDemand("scaled", {"backend": 3, "worker": 2}, 0),
        PhaseDemand("rollback", {"backend": 2, "worker": 2}, 0),
    )
    result = _evaluate(_model(phases=phases))

    assert result.status == Verdict.PASS
    assert result.worst_case_connections == 162
    scaled = result.phase_reports[0]
    assert scaled["process_connections"] == {"backend": 90, "worker": 60}


def test_postgres_15_uses_zero_reserved_connections_fallback() -> None:
    model = _model()
    model = replace(
        model,
        postgres=PostgresCapacity(
            server_version_major=15,
            max_connections=200,
            superuser_reserved_connections=3,
            reserved_connections=None,
            current_connections=20,
            observed_non_yfc_connections=12,
            observed_yfc_connections=8,
        ),
    )

    result = _evaluate(model)

    assert result.status == Verdict.PASS
    assert result.reserved_connections_effective == 0


def test_pooler_requires_verified_backend_cap_per_phase() -> None:
    model = _model(
        phases=(PhaseDemand("steady", {"backend": 1, "worker": 1}, 0),),
    )
    model = replace(model, pooler=PoolerTopology("transaction"))

    result = _evaluate(model)

    assert result.status == Verdict.UNKNOWN
    assert any(item.code == "pooler_backend_limit_unknown" for item in result.diagnostics)


def test_postgres_snapshot_query_is_read_only_and_does_not_expose_credentials() -> None:
    class Cursor:
        def execute(self, query: str) -> None:
            self.query = query

        def fetchone(self):
            return (160004, 200, 3, 2, 20)

        def close(self) -> None:
            pass

    class Connection:
        def cursor(self):
            return Cursor()

    snapshot = read_postgres_snapshot(Connection())

    assert snapshot == PostgresCapacity(
        server_version_major=16,
        max_connections=200,
        superuser_reserved_connections=3,
        reserved_connections=2,
        current_connections=20,
    )


def test_postgres_connection_failure_is_fail_closed() -> None:
    class Connection:
        def cursor(self):
            raise OSError("postgresql://secret must not be emitted")

    with pytest.raises(PostgresSnapshotError, match="snapshot"):
        read_postgres_snapshot(Connection())


def test_runtime_postgres_snapshot_uses_aggregates_and_requires_visibility() -> None:
    class Cursor:
        query = ""

        def execute(self, query: str) -> None:
            self.query = query

        def fetchone(self):
            return (160004, 200, 3, 2, 20, 8, 0, 12, True, False)

        def close(self) -> None:
            pass

    class Connection:
        def cursor(self):
            return Cursor()

    snapshot = read_postgres_runtime_snapshot(
        Connection(),
        ("yfc-backend", "yfc-worker"),
    )

    assert snapshot == PostgresCapacity(
        server_version_major=16,
        max_connections=200,
        superuser_reserved_connections=3,
        reserved_connections=2,
        current_connections=20,
        observed_yfc_connections=8,
        observed_non_yfc_connections=12,
        unattributed_connections=0,
    )


def test_runtime_postgres_snapshot_does_not_treat_unattributed_as_yfc() -> None:
    class Cursor:
        def execute(self, query: str) -> None:
            assert "postgresql://secret" not in query
            assert not any(
                token in query.upper() for token in ("INSERT", "UPDATE", "DELETE", "ALTER")
            )

        def fetchone(self):
            return (150000, 200, 3, None, 20, 8, 4, 8, True, False)

        def close(self) -> None:
            pass

    class Connection:
        def cursor(self):
            return Cursor()

    snapshot = read_postgres_runtime_snapshot(Connection(), ("yfc-backend",))

    assert snapshot.server_version_major == 15
    assert snapshot.observed_non_yfc_connections == 12
    assert snapshot.unattributed_connections == 4


def test_runtime_postgres_snapshot_blocks_without_pg_stat_activity_visibility() -> None:
    class Cursor:
        def execute(self, query: str) -> None:
            pass

        def fetchone(self):
            return (160004, 200, 3, 2, 20, 8, 0, 12, False, False)

        def close(self) -> None:
            pass

    class Connection:
        def cursor(self):
            return Cursor()

    with pytest.raises(PostgresSnapshotError, match="snapshot"):
        read_postgres_runtime_snapshot(Connection(), ("yfc-backend",))


def test_runtime_postgres_snapshot_blocks_attribution_mismatch() -> None:
    class Cursor:
        def execute(self, query: str) -> None:
            pass

        def fetchone(self):
            return (160004, 200, 3, 2, 20, 8, 0, 11, True, False)

        def close(self) -> None:
            pass

    class Connection:
        def cursor(self):
            return Cursor()

    with pytest.raises(PostgresSnapshotError, match="attribution"):
        read_postgres_runtime_snapshot(Connection(), ("yfc-backend",))


def test_invalid_values_are_blocked() -> None:
    result = _evaluate(
        _model(
            phases=(PhaseDemand("invalid", {"backend": -1, "worker": 1}, 0),),
        )
    )

    assert result.status == Verdict.BLOCKED
    assert any(item.code == "replica_count_invalid" for item in result.diagnostics)


def test_missing_attribution_is_unknown_even_when_capacity_is_large() -> None:
    result = _evaluate(_model(observed_non_yfc=None, observed_yfc=None))

    assert result.status == Verdict.UNKNOWN
    assert any(item.code == "connection_attribution_unknown" for item in result.diagnostics)


def test_inconsistent_attribution_is_blocked() -> None:
    result = _evaluate(_model(current_connections=21))

    assert result.status == Verdict.BLOCKED
    assert any(item.code == "connection_attribution_inconsistent" for item in result.diagnostics)


def test_observed_yfc_must_fit_confirmed_steady_state_ceiling() -> None:
    model = _model(
        phases=(
            PhaseDemand(
                "steady-state",
                {"backend": 0, "worker": 0, "migration": 0, "setup": 0},
                0,
            ),
        ),
    )

    result = _evaluate(model)

    assert result.status == Verdict.BLOCKED
    assert any(
        item.code == "observed_yfc_exceeds_steady_state_capacity" for item in result.diagnostics
    )


def test_zero_process_steady_state_with_no_observed_yfc_can_pass() -> None:
    model = _model(
        observed_yfc=0,
        phases=(
            PhaseDemand(
                "steady-state",
                {"backend": 0, "worker": 0, "migration": 0, "setup": 0},
                0,
            ),
        ),
    )

    result = _evaluate(model)

    assert result.status == Verdict.PASS
    assert result.phase_reports[0]["app_connections"] == 0


def test_empty_process_inventory_is_not_proven_zero_load() -> None:
    model = _model(phases=(PhaseDemand("steady-state", {}, 0),))
    model = replace(
        model,
        topology=TopologyInventory(
            process_groups={"backend": True, "worker": True, "migration": False, "setup": False},
            rollout_phases={"steady-state": True},
        ),
    )

    result = _evaluate(model)

    assert result.status == Verdict.UNKNOWN
    assert any(item.code == "phase_process_inventory_incomplete" for item in result.diagnostics)


def test_missing_applicable_rollout_phase_is_unknown() -> None:
    model = _model()
    model = replace(model, phases=(model.phases[0],))

    result = _evaluate(model)

    assert result.status == Verdict.UNKNOWN
    assert any(item.code == "rollout_phase_missing" for item in result.diagnostics)


def test_phase_process_inventory_must_include_required_worker() -> None:
    model = _model(phases=(PhaseDemand("steady", {"backend": 1}, 0),))
    model = replace(
        model,
        topology=TopologyInventory(
            process_groups={"backend": True, "worker": True, "migration": False, "setup": False},
            rollout_phases={"steady": True},
        ),
    )

    result = _evaluate(model)

    assert result.status == Verdict.UNKNOWN
    assert any(item.code == "phase_process_inventory_incomplete" for item in result.diagnostics)


def test_explicitly_absent_worker_variant_can_pass() -> None:
    model = _model(phases=(PhaseDemand("steady", {"backend": 1}, 0),))

    result = _evaluate(model)

    assert result.status == Verdict.PASS
    assert result.worst_case_connections == 42


def test_queue_pool_cannot_be_lowered_by_connection_ceiling() -> None:
    result = _evaluate(
        _model(
            backend_pool=PoolSpec(
                "backend",
                10,
                20,
                30,
                1,
                pool_type="queue",
            )
        )
    )

    assert result.status == Verdict.BLOCKED
    assert any(item.code == "queue_ceiling_conflict" for item in result.diagnostics)


@pytest.mark.parametrize("mode", ["session", "transaction"])
def test_pooler_modes_use_verified_positive_backend_capacity(mode: str) -> None:
    model = _model(
        phases=(PhaseDemand("steady", {"backend": 1, "worker": 1}, 0, 60),),
    )
    model = replace(model, pooler=PoolerTopology(mode, "sanitized-pooler-config"))

    result = _evaluate(model)

    assert result.status == Verdict.PASS
    report = result.phase_reports[0]
    assert report["process_connections"] == {"backend": 30, "worker": 30}
    assert report["app_connections"] == 60
    assert report["projected_connections"] == 72


@pytest.mark.parametrize("mode", ["session", "transaction"])
def test_pooler_zero_backend_capacity_is_blocked(mode: str) -> None:
    model = _model(
        phases=(PhaseDemand("steady", {"backend": 1, "worker": 1}, 0, 0),),
    )
    model = replace(model, pooler=PoolerTopology(mode, "sanitized-pooler-config"))

    result = _evaluate(model)

    assert result.status == Verdict.BLOCKED
    assert any(item.code == "pooler_backend_limit_invalid" for item in result.diagnostics)


def test_malformed_process_topology_is_blocked_at_mapping_boundary() -> None:
    with pytest.raises(ConfigurationError):
        model_from_mapping(
            {"topology": {"process_groups": {"backend": "present"}}},
        )


def test_synthetic_input_cannot_be_used_as_production_evidence() -> None:
    result = evaluate(_model())

    assert result.status != Verdict.PASS
    assert any(item.code == "synthetic_evidence_not_allowed" for item in result.diagnostics)


def test_relabelled_synthetic_snapshot_cannot_authorize_production_preflight() -> None:
    model = replace(
        _model(),
        safety_headroom_source="owner-approved-headroom-record",
        evidence=EvidenceMetadata(
            environment="production",
            source="owner-approved-runtime-collector",
            captured_at="2026-10-19T00:00:00+00:00",
            max_age_seconds=3600,
            synthetic=False,
        ),
    )

    result = evaluate(model, now=datetime(2026, 10, 19, tzinfo=UTC))

    assert result.status == Verdict.BLOCKED
    assert any(item.code == "runtime_provenance_untrusted" for item in result.diagnostics)


def test_stale_runtime_snapshot_is_blocked() -> None:
    model = replace(
        _model(),
        safety_headroom_source="owner-approved-headroom-record",
        evidence=EvidenceMetadata(
            environment="production",
            source="sanitized-runtime-snapshot",
            captured_at="2026-10-18T00:00:00+00:00",
            max_age_seconds=60,
            synthetic=False,
        ),
    )

    result = evaluate(model, now=datetime(2026, 10, 19, tzinfo=UTC))

    assert result.status == Verdict.BLOCKED
    assert any(item.code == "snapshot_stale" for item in result.diagnostics)


def test_no_bypass_flag_is_accepted(tmp_path: Path) -> None:
    config = tmp_path / "budget.json"
    config.write_text("{}\n", encoding="utf-8")

    with pytest.raises(SystemExit) as error:
        main(["--config", str(config), "--bypass", "--json"])

    assert error.value.code == 2


def test_cli_unknown_and_malformed_configuration_fail_closed(tmp_path: Path) -> None:
    assert main(["--config", str(tmp_path / "missing.json")]) == 2

    malformed = tmp_path / "malformed.json"
    malformed.write_text("{\n", encoding="utf-8")

    assert main(["--config", str(malformed)]) == 1


def test_stage_order_requires_preflight_before_protected_stages() -> None:
    validate_rollout_stage_order(["connection_budget_preflight", "backup", "migration"])

    with pytest.raises(ConfigurationError):
        validate_rollout_stage_order(["backup", "connection_budget_preflight"])


def test_safe_env_reader_allowlists_only_numeric_pool_settings(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://user:secret@example/db\n"
        "DB_POOL_SIZE=10\n"
        "DB_MAX_OVERFLOW='20' # bounded\n"
        "DB_POOL_TIMEOUT_SECONDS=30\n",
        encoding="utf-8",
    )

    values = read_safe_pool_environment(env_file)

    assert values == {
        "DB_POOL_SIZE": 10,
        "DB_MAX_OVERFLOW": 20,
        "DB_POOL_TIMEOUT_SECONDS": 30,
    }
    assert "DATABASE_URL" not in values
    assert "secret" not in json.dumps(values)


def test_mapping_parser_does_not_supply_missing_production_defaults() -> None:
    model = model_from_mapping({"postgres": {}, "pools": {}, "phases": []})
    result = evaluate(model)

    assert result.status == Verdict.UNKNOWN
    assert result.worst_case_connections is None


@pytest.mark.parametrize("unknown", (0, 3))
def test_inclusive_unknown_count_is_not_added_twice(unknown) -> None:
    model = _model()
    model = replace(model, postgres=replace(model.postgres, unattributed_connections=unknown))
    result = _evaluate(model)
    assert result.status == Verdict.PASS
    assert result.worst_case_connections == 132
    invalid = replace(model, postgres=replace(model.postgres, unattributed_connections=13))
    assert _evaluate(invalid).status == Verdict.BLOCKED
