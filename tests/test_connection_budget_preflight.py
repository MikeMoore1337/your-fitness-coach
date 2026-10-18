from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from scripts.connection_budget_preflight import (
    BudgetModel,
    ConfigurationError,
    PhaseDemand,
    PoolerTopology,
    PoolSpec,
    PostgresCapacity,
    PostgresSnapshotError,
    Verdict,
    evaluate,
    main,
    model_from_mapping,
    read_postgres_snapshot,
    read_safe_pool_environment,
    validate_rollout_stage_order,
)


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
    )
    default_phases = (
        PhaseDemand("steady-state", {"backend": 1, "worker": 1}, 0),
        PhaseDemand("candidate-overlap", {"backend": 2, "worker": 1}, 0),
        PhaseDemand("unexpected-all-slots", {"backend": 2, "worker": 2}, 0),
        PhaseDemand("backup", {"backend": 1, "worker": 1}, 1),
        PhaseDemand("migration", {"backend": 1, "worker": 1, "migration": 1}, 0),
        PhaseDemand("setup-seed", {"backend": 1, "worker": 1, "setup": 1}, 0),
        PhaseDemand("rollback", {"backend": 2, "worker": 1}, 0),
    )
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
            "worker": PoolSpec("worker", 10, 20, 30),
            "migration": PoolSpec("migration", connection_ceiling=1),
            "setup": PoolSpec("setup", connection_ceiling=30),
        },
        phases=phases or default_phases,
        pooler=PoolerTopology("none"),
        safety_headroom_connections=10,
        safety_headroom_source="synthetic-test-input",
    )


def test_default_2c_3c_4c_and_setup_phases_pass_with_explicit_headroom() -> None:
    result = evaluate(_model())

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
    result = evaluate(_model(max_connections=135))

    assert result.status == Verdict.BLOCKED
    assert any(item.code == "insufficient_headroom" for item in result.diagnostics)


def test_unknown_max_connections_is_not_pass() -> None:
    result = evaluate(_model(max_connections=None))

    assert result.status == Verdict.UNKNOWN
    assert any(item.code == "max_connections_unknown" for item in result.diagnostics)


def test_postgres_16_requires_reserved_connections() -> None:
    result = evaluate(_model(reserved_connections=None))

    assert result.status == Verdict.UNKNOWN
    assert any(item.code == "reserved_connections_unknown" for item in result.diagnostics)


def test_missing_pool_settings_are_unknown() -> None:
    result = evaluate(_model(backend_pool=PoolSpec("backend", pool_timeout_seconds=30)))

    assert result.status == Verdict.UNKNOWN
    assert any(item.code == "pool_settings_unknown" for item in result.diagnostics)


def test_multiple_replicas_and_rollback_are_counted() -> None:
    phases = (
        PhaseDemand("scaled", {"backend": 3, "worker": 2}, 0),
        PhaseDemand("rollback", {"backend": 2, "worker": 2}, 0),
    )
    result = evaluate(_model(phases=phases))

    assert result.status == Verdict.PASS
    assert result.worst_case_connections == 162
    scaled = result.phase_reports[0]
    assert scaled["process_connections"] == {"backend": 90, "worker": 60}


def test_postgres_15_uses_zero_reserved_connections_fallback() -> None:
    model = _model()
    model = BudgetModel(
        postgres=PostgresCapacity(
            server_version_major=15,
            max_connections=200,
            superuser_reserved_connections=3,
            reserved_connections=None,
            current_connections=20,
            observed_non_yfc_connections=12,
            observed_yfc_connections=8,
        ),
        pools=model.pools,
        phases=model.phases,
        pooler=model.pooler,
        safety_headroom_connections=model.safety_headroom_connections,
        safety_headroom_source=model.safety_headroom_source,
    )

    result = evaluate(model)

    assert result.status == Verdict.PASS
    assert result.reserved_connections_effective == 0


def test_pooler_requires_verified_backend_cap_per_phase() -> None:
    model = _model(
        phases=(PhaseDemand("steady", {"backend": 1, "worker": 1}, 0),),
    )
    model = BudgetModel(
        postgres=model.postgres,
        pools=model.pools,
        phases=model.phases,
        pooler=PoolerTopology("transaction"),
        safety_headroom_connections=model.safety_headroom_connections,
        safety_headroom_source=model.safety_headroom_source,
    )

    result = evaluate(model)

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


def test_invalid_values_are_blocked() -> None:
    result = evaluate(
        _model(
            phases=(PhaseDemand("invalid", {"backend": -1, "worker": 1}, 0),),
        )
    )

    assert result.status == Verdict.BLOCKED
    assert any(item.code == "replica_count_invalid" for item in result.diagnostics)


def test_missing_attribution_is_unknown_even_when_capacity_is_large() -> None:
    result = evaluate(_model(observed_non_yfc=None, observed_yfc=None))

    assert result.status == Verdict.UNKNOWN
    assert any(item.code == "connection_attribution_unknown" for item in result.diagnostics)


def test_inconsistent_attribution_is_blocked() -> None:
    result = evaluate(_model(current_connections=21))

    assert result.status == Verdict.BLOCKED
    assert any(item.code == "connection_attribution_inconsistent" for item in result.diagnostics)


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
