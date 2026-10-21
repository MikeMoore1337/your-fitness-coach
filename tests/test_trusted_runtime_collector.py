from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from scripts.connection_budget_preflight import PostgresCapacity, Verdict, evaluate
from scripts.trusted_runtime_collector import (
    COLLECTOR_APPLICATION_NAME,
    POOL_KEYS,
    YFC_APPLICATION_NAMES,
    CollectorFailure,
    CollectorPolicy,
    ContainerEnvironment,
    PostgresObservation,
    RuntimeContext,
    _active_revision,
    _active_state,
    _failure_payload,
    _gateway_active_upstream,
    _inspect_revisions,
    _merge_diagnostics,
    _parse_child_snapshot,
    _parse_container_environment,
    _run_bounded,
    build_topology_observation,
    build_verified_budget_model,
)

CAPTURED_AT = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
REVISION = "a" * 40


def _context(
    *,
    captured_at: datetime = CAPTURED_AT,
    revisions: tuple[str, ...] = (REVISION,),
) -> RuntimeContext:
    return RuntimeContext(
        environment="production",
        host_fingerprint="host-fingerprint",
        revisions=revisions,
        captured_at=captured_at,
    )


def _app_environment(marker: str) -> dict[str, str]:
    return {
        "APP_ENV": "prod",
        "YFC_DB_APPLICATION_NAME": marker,
        "DB_POOL_SIZE": "10",
        "DB_MAX_OVERFLOW": "20",
        "DB_POOL_TIMEOUT_SECONDS": "30",
        "DB_POOL_RECYCLE_SECONDS": "1800",
    }


def _runtime_environment(
    marker: str,
    *,
    pool_size: str = "10",
    max_overflow: str = "20",
) -> ContainerEnvironment:
    values = _app_environment(marker)
    values["DB_POOL_SIZE"] = pool_size
    values["DB_MAX_OVERFLOW"] = max_overflow
    return ContainerEnvironment(values=values, has_database_url=True)


def _compose(*, include_worker: bool = True, extra_consumer: bool = False) -> dict[str, object]:
    services: dict[str, object] = {
        "edge": {"environment": {"YFC_ACTIVE_UPSTREAM": "backend:8000"}},
        "backend": {"environment": _app_environment("yfc-backend")},
        "backend-blue": {"environment": _app_environment("yfc-backend")},
        "backend-green": {"environment": _app_environment("yfc-backend")},
        "setup": {"environment": _app_environment("yfc-setup")},
        "db": {},
    }
    if include_worker:
        services.update(
            {
                "worker": {"environment": _app_environment("yfc-worker")},
                "worker-blue": {"environment": _app_environment("yfc-worker")},
                "worker-green": {"environment": _app_environment("yfc-worker")},
            }
        )
    if extra_consumer:
        services["analytics"] = {"environment": {"DATABASE_URL": "<secret>"}}
    return {"services": services}


def _ps() -> list[dict[str, object]]:
    return [
        {"Service": "edge", "State": "running"},
        {"Service": "backend", "State": "running"},
        {"Service": "worker", "State": "running"},
    ]


def _postgres(context: RuntimeContext) -> PostgresObservation:
    return PostgresObservation(
        context=context,
        capacity=PostgresCapacity(
            server_version_major=16,
            max_connections=300,
            superuser_reserved_connections=3,
            reserved_connections=2,
            current_connections=20,
            observed_yfc_connections=8,
            observed_non_yfc_connections=12,
            unattributed_connections=0,
        ),
    )


def _topology(
    *,
    context: RuntimeContext | None = None,
    include_worker: bool = True,
    extra_consumer: bool = False,
):
    return build_topology_observation(
        _compose(include_worker=include_worker, extra_consumer=extra_consumer),
        _ps(),
        context or _context(),
    )


def _approved_policy() -> CollectorPolicy:
    return CollectorPolicy(
        safety_headroom_connections=10,
        safety_headroom_source="owner-approved-headroom-record",
    )


def test_collector_session_is_counted_as_non_yfc_capacity_demand() -> None:
    assert COLLECTOR_APPLICATION_NAME not in YFC_APPLICATION_NAMES


def test_gateway_active_upstream_reads_live_reverse_proxy_config() -> None:
    payload = {
        "apps": {
            "http": {
                "servers": {
                    "srv0": {
                        "routes": [
                            {
                                "handle": [
                                    {
                                        "handler": "reverse_proxy",
                                        "upstreams": [{"dial": "backend-blue:8000"}],
                                    }
                                ]
                            }
                        ]
                    }
                }
            }
        }
    }

    assert _gateway_active_upstream(payload) == "backend-blue:8000"


def test_verified_collector_model_carries_runtime_context_and_evaluates_all_phases() -> None:
    model, context = build_verified_budget_model(
        _postgres(_context()), _topology(), _approved_policy()
    )

    result = evaluate(model, now=CAPTURED_AT + timedelta(seconds=1))

    assert context.revisions == (REVISION,)
    assert result.status == Verdict.PASS
    assert {str(item["name"]) for item in result.phase_reports} == {
        "steady-state",
        "candidate-overlap",
        "unexpected-all-slots",
        "backup",
        "migration",
        "setup-seed",
        "worker-handoff",
        "rollback",
        "single-slot",
    }


def test_headroom_is_not_invented_by_default_policy() -> None:
    model, _ = build_verified_budget_model(_postgres(_context()), _topology())

    result = evaluate(model, now=CAPTURED_AT + timedelta(seconds=1))

    assert result.status == Verdict.UNKNOWN
    assert any(item.code == "safety_headroom_unknown" for item in result.diagnostics)


def test_untrusted_token_cannot_be_forged_on_a_verified_model() -> None:
    model, _ = build_verified_budget_model(_postgres(_context()), _topology(), _approved_policy())
    forged = replace(model, _runtime_evidence_token=True)

    result = evaluate(forged, now=CAPTURED_AT + timedelta(seconds=1))

    assert result.status == Verdict.BLOCKED
    assert any(item.code == "runtime_provenance_untrusted" for item in result.diagnostics)


def test_context_revision_mismatch_is_blocked_before_evaluation() -> None:
    postgres = _postgres(_context(revisions=("b" * 40,)))

    with pytest.raises(CollectorFailure, match="revision"):
        build_verified_budget_model(postgres, _topology(), _approved_policy())


def test_context_host_mismatch_is_blocked_before_evaluation() -> None:
    postgres = _postgres(_context())
    topology = _topology()
    topology = replace(topology, context=replace(topology.context, host_fingerprint="other-host"))

    with pytest.raises(CollectorFailure, match="host"):
        build_verified_budget_model(postgres, topology, _approved_policy())


def test_stale_and_future_contexts_cannot_pass() -> None:
    stale_model, _ = build_verified_budget_model(
        _postgres(_context(captured_at=CAPTURED_AT - timedelta(minutes=10))),
        _topology(context=_context(captured_at=CAPTURED_AT - timedelta(minutes=10))),
        _approved_policy(),
    )
    future_model, _ = build_verified_budget_model(
        _postgres(_context(captured_at=CAPTURED_AT + timedelta(minutes=1))),
        _topology(context=_context(captured_at=CAPTURED_AT + timedelta(minutes=1))),
        _approved_policy(),
    )

    stale = evaluate(stale_model, now=CAPTURED_AT)
    future = evaluate(future_model, now=CAPTURED_AT)

    assert stale.status == Verdict.BLOCKED
    assert future.status == Verdict.BLOCKED


def test_missing_worker_is_unknown_and_not_treated_as_zero_replicas() -> None:
    topology = _topology(include_worker=False)
    model, _ = build_verified_budget_model(_postgres(_context()), topology, _approved_policy())

    result = evaluate(model, now=CAPTURED_AT + timedelta(seconds=1))

    assert result.status == Verdict.UNKNOWN
    assert any(item.code == "process_pool_ceiling_unknown" for item in result.diagnostics)


def test_missing_setup_is_unknown_and_not_treated_as_zero_connections() -> None:
    compose = _compose()
    services = compose["services"]
    assert isinstance(services, dict)
    services.pop("setup")
    topology = build_topology_observation(compose, _ps(), _context())
    model, _ = build_verified_budget_model(_postgres(_context()), topology, _approved_policy())

    result = evaluate(model, now=CAPTURED_AT + timedelta(seconds=1))

    assert result.status == Verdict.UNKNOWN
    assert any(item.code == "runtime_setup_unknown" for item in topology.diagnostics)


def test_extra_database_consumer_blocks_a_false_pass() -> None:
    topology = _topology(extra_consumer=True)
    model, _ = build_verified_budget_model(_postgres(_context()), topology, _approved_policy())
    result = _merge_diagnostics(
        evaluate(model, now=CAPTURED_AT + timedelta(seconds=1)), topology.diagnostics
    )

    assert result.status == Verdict.UNKNOWN
    assert any(item.code == "unexpected_db_consumer" for item in result.diagnostics)
    assert any(item["other_connections"] is None for item in result.phase_reports)


def test_process_marker_mismatch_is_blocked() -> None:
    compose = _compose()
    services = compose["services"]
    assert isinstance(services, dict)
    worker = services["worker"]
    assert isinstance(worker, dict)
    environment = worker["environment"]
    assert isinstance(environment, dict)
    environment["YFC_DB_APPLICATION_NAME"] = "yfc-backend"

    topology = build_topology_observation(compose, _ps(), _context())

    assert any(item.code == "runtime_application_markers_invalid" for item in topology.diagnostics)
    assert any(item.status == Verdict.BLOCKED for item in topology.diagnostics)


def test_child_output_rejects_trust_fields_and_secret_like_values() -> None:
    payload: dict[str, object] = {
        "status": "PASS",
        "captured_at": CAPTURED_AT.isoformat(),
        "postgres": {
            "server_version_major": 16,
            "max_connections": 200,
            "superuser_reserved_connections": 3,
            "reserved_connections": 2,
            "current_connections": 20,
            "observed_yfc_connections": 8,
            "observed_non_yfc_connections": 12,
            "unattributed_connections": 0,
        },
        "trusted": True,
        "DATABASE_URL": "postgresql://secret@example/db",
    }

    with pytest.raises(CollectorFailure, match="snapshot"):
        _parse_child_snapshot(payload, _context())


def test_failure_payload_is_sanitized() -> None:
    payload = _failure_payload(CollectorFailure("runtime_command_failed", Verdict.UNKNOWN))

    rendered = str(payload)
    assert "postgresql" not in rendered
    assert "password" not in rendered
    assert payload["status"] == "UNKNOWN"


def test_pooler_mode_requires_and_propagates_a_backend_cap() -> None:
    compose = _compose()
    services = compose["services"]
    assert isinstance(services, dict)
    services["pgbouncer"] = {
        "environment": {
            "YFC_POOLER_MODE": "transaction",
            "YFC_POOLER_BACKEND_CAP": "60",
        }
    }

    topology = build_topology_observation(compose, _ps(), _context())

    assert topology.pooler.mode == "transaction"
    assert all(phase.pooler_backend_connections == 60 for phase in topology.phases)


def test_multiple_poolers_fail_closed_instead_of_using_the_first() -> None:
    compose = _compose()
    services = compose["services"]
    assert isinstance(services, dict)
    services["pgbouncer"] = {
        "environment": {
            "YFC_POOLER_MODE": "transaction",
            "YFC_POOLER_BACKEND_CAP": "60",
        }
    }
    services["pgbouncer-secondary"] = {
        "environment": {
            "YFC_POOLER_MODE": "transaction",
            "YFC_POOLER_BACKEND_CAP": "60",
        }
    }

    topology = build_topology_observation(compose, _ps(), _context())

    assert topology.pooler.mode is None
    assert any(item.code == "pooler_topology_unknown" for item in topology.diagnostics)


def test_runtime_pooler_settings_are_checked_against_rendered_configuration() -> None:
    compose = _compose()
    services = compose["services"]
    assert isinstance(services, dict)
    services["pgbouncer"] = {
        "environment": {
            "YFC_POOLER_MODE": "transaction",
            "YFC_POOLER_BACKEND_CAP": "60",
        }
    }
    runtime = {
        "pgbouncer": (
            ContainerEnvironment(
                values={"YFC_POOLER_MODE": "transaction", "YFC_POOLER_BACKEND_CAP": "100"},
                has_database_url=True,
            ),
        )
    }

    topology = build_topology_observation(
        compose,
        _ps(),
        _context(),
        runtime_environments=runtime,
    )

    assert topology.pooler.mode == "transaction"
    assert all(phase.pooler_backend_connections == 100 for phase in topology.phases)
    assert any(
        item.code == "runtime_container_environment_mismatch" and item.status == Verdict.BLOCKED
        for item in topology.diagnostics
    )


def test_runtime_active_slot_wins_over_stale_rendered_upstream() -> None:
    ps = [
        *_ps(),
        {"Service": "backend-blue", "State": "running"},
        {"Service": "worker-blue", "State": "running"},
    ]

    topology = build_topology_observation(
        _compose(),
        ps,
        _context(),
        active_gateway_upstream="backend-blue:8000",
        active_slot="blue",
    )

    assert topology.active_backend_service == "backend-blue"
    assert not any(item.code == "runtime_active_upstream_mismatch" for item in topology.diagnostics)


def test_runtime_active_slot_mismatch_is_blocked() -> None:
    topology = build_topology_observation(
        _compose(),
        _ps(),
        _context(),
        active_gateway_upstream="backend-green:8000",
        active_slot="blue",
    )

    assert any(
        item.code == "runtime_active_slot_mismatch" and item.status == Verdict.BLOCKED
        for item in topology.diagnostics
    )


def test_runtime_environment_drift_blocks_rendered_topology() -> None:
    runtime = {
        "backend": (_runtime_environment("yfc-worker"),),
        "worker": (_runtime_environment("yfc-worker"),),
    }

    topology = build_topology_observation(
        _compose(),
        _ps(),
        _context(),
        runtime_environments=runtime,
    )

    assert any(
        item.code == "runtime_container_environment_mismatch" and item.status == Verdict.BLOCKED
        for item in topology.diagnostics
    )


def test_runtime_pool_override_is_used_and_inconsistent_instances_are_unknown() -> None:
    runtime = {
        "backend": (
            _runtime_environment("yfc-backend", pool_size="40"),
            _runtime_environment("yfc-backend", pool_size="50"),
        ),
        "worker": (_runtime_environment("yfc-worker"),),
    }

    topology = build_topology_observation(
        _compose(),
        _ps(),
        _context(),
        runtime_environments=runtime,
    )

    assert topology.pools["backend"].pool_size is None
    assert any(
        item.code == "runtime_container_environment_inconsistent" and item.status == Verdict.UNKNOWN
        for item in topology.diagnostics
    )


def test_running_database_consumer_outside_rendered_compose_is_unknown() -> None:
    ps = [*_ps(), {"Service": "analytics", "State": "running"}]
    runtime = {
        "analytics": (
            ContainerEnvironment(
                values=dict.fromkeys(("APP_ENV", "YFC_DB_APPLICATION_NAME", *POOL_KEYS)),
                has_database_url=True,
            ),
        )
    }

    topology = build_topology_observation(
        _compose(),
        ps,
        _context(),
        runtime_environments=runtime,
    )

    assert any(item.code == "unexpected_db_consumer" for item in topology.diagnostics)


def test_all_slots_use_actual_running_instances_when_scaled() -> None:
    ps = [
        *_ps(),
        {"Service": "backend-blue", "State": "running"},
        {"Service": "backend-blue", "State": "running"},
    ]

    topology = build_topology_observation(_compose(), ps, _context())
    all_slots = next(phase for phase in topology.phases if phase.name == "unexpected-all-slots")
    candidate = next(phase for phase in topology.phases if phase.name == "candidate-overlap")

    assert all_slots.processes is not None
    assert all_slots.processes["backend"] == 4
    assert candidate.processes is not None
    assert candidate.processes["backend"] == 3


def test_container_environment_parser_does_not_retain_database_url() -> None:
    parsed = _parse_container_environment(
        [
            "APP_ENV=prod",
            "YFC_DB_APPLICATION_NAME=yfc-backend",
            "DATABASE_URL=postgresql://user:secret@example/db",
        ]
    )

    assert parsed.has_database_url is True
    assert "secret" not in repr(parsed.values)


def test_bounded_command_timeout_is_fail_closed() -> None:
    with pytest.raises(CollectorFailure, match="timeout"):
        _run_bounded(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            cwd=Path.cwd(),
            policy=CollectorPolicy(command_timeout_seconds=1),
        )


def test_running_image_revision_must_match_release_sha(tmp_path: Path, monkeypatch) -> None:
    other_revision = "b" * 40

    def fake_run(command, *, cwd, policy):
        assert command[-1] == "container"
        del cwd, policy
        return json.dumps({"org.opencontainers.image.revision": other_revision}).encode() + b"\n"

    monkeypatch.setattr("scripts.trusted_runtime_collector._run_bounded", fake_run)

    with pytest.raises(CollectorFailure, match="revision"):
        _inspect_revisions(
            [{"Service": "backend", "State": "running", "ID": "container"}],
            cwd=tmp_path,
            policy=CollectorPolicy(),
            expected_revision=REVISION,
        )


def test_predeploy_running_revision_uses_active_state_not_candidate(
    tmp_path: Path, monkeypatch
) -> None:
    """A valid upgrade has active=A while immutable candidate bundle=B."""
    monkeypatch.delenv("DEPLOY_STATE_ROOT", raising=False)
    state_root = tmp_path / ".artifacts" / "operations" / "deployments"
    state_root.mkdir(parents=True)
    state_root.joinpath("last-successful-revision").write_text(REVISION + "\n", encoding="utf-8")
    state_root.joinpath("state.json").write_text(
        json.dumps({"active_revision": REVISION, "active_slot": "blue"}),
        encoding="utf-8",
    )
    tmp_path.joinpath(".deployment-sha").write_text("b" * 40 + "\n", encoding="utf-8")

    from scripts.trusted_runtime_collector import _release_revision

    assert _release_revision(tmp_path) == "b" * 40
    assert _active_revision(tmp_path) == REVISION
    assert _active_state(tmp_path) == (REVISION, "blue")

    def fake_run(command, *, cwd, policy):
        del cwd, policy
        assert command[-1] == "active-container"
        return json.dumps({"org.opencontainers.image.revision": REVISION}).encode() + b"\n"

    monkeypatch.setattr("scripts.trusted_runtime_collector._run_bounded", fake_run)
    assert _inspect_revisions(
        [{"Service": "backend-blue", "State": "running", "ID": "active-container"}],
        cwd=tmp_path,
        policy=CollectorPolicy(),
        expected_revision=_active_revision(tmp_path),
    ) == (REVISION,)


@pytest.mark.parametrize(
    ("state_revision", "state_slot", "marker", "error"),
    (
        ("b" * 40, "blue", REVISION, "active_revision_state_mismatch"),
        (REVISION, "unknown", REVISION, "active_state_invalid"),
        (REVISION, "blue", "not-a-full-sha", "active_revision_invalid"),
    ),
)
def test_predeploy_active_revision_fails_closed_for_invalid_state(
    tmp_path: Path,
    monkeypatch,
    state_revision: str,
    state_slot: str,
    marker: str,
    error: str,
) -> None:
    monkeypatch.delenv("DEPLOY_STATE_ROOT", raising=False)
    state_root = tmp_path / ".artifacts" / "operations" / "deployments"
    state_root.mkdir(parents=True)
    state_root.joinpath("last-successful-revision").write_text(marker, encoding="utf-8")
    state_root.joinpath("state.json").write_text(
        json.dumps({"active_revision": state_revision, "active_slot": state_slot}),
        encoding="utf-8",
    )
    with pytest.raises(CollectorFailure, match=error):
        _active_revision(tmp_path)


def test_predeploy_active_revision_missing_marker_is_unknown(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DEPLOY_STATE_ROOT", raising=False)
    with pytest.raises(CollectorFailure, match="active_revision_unavailable") as raised:
        _active_revision(tmp_path)
    assert raised.value.status == Verdict.UNKNOWN


def test_predeploy_single_slot_uses_last_successful_revision(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DEPLOY_STATE_ROOT", raising=False)
    state_root = tmp_path / ".artifacts" / "operations" / "deployments"
    state_root.mkdir(parents=True)
    state_root.joinpath("last-successful-revision").write_text(REVISION, encoding="utf-8")
    assert _active_revision(tmp_path) == REVISION


def test_legacy_probe_source_absent_or_oversized_fails_closed(
    tmp_path: Path,
) -> None:
    from scripts.trusted_runtime_collector import _legacy_child_source

    with pytest.raises(CollectorFailure, match="legacy_probe_source_unavailable"):
        _legacy_child_source(tmp_path)

    (tmp_path / "scripts").mkdir()
    source_path = tmp_path / "scripts" / "trusted_legacy_pg_snapshot.py"
    source_path.write_bytes(b"x" * 16_385)
    with pytest.raises(CollectorFailure, match="legacy_probe_source_invalid"):
        _legacy_child_source(tmp_path)

    source_path.unlink()
    outside = tmp_path / "not-the-bundle.py"
    outside.write_text("print('unsafe')", encoding="utf-8")
    source_path.symlink_to(outside)
    with pytest.raises(CollectorFailure, match="legacy_probe_source_invalid"):
        _legacy_child_source(tmp_path)


def test_collect_snapshot_binds_active_image_and_candidate_provenance(
    tmp_path: Path, monkeypatch
) -> None:
    """The full collector passes the *running* SHA to OCI inspection."""
    monkeypatch.delenv("DEPLOY_STATE_ROOT", raising=False)
    active_revision = REVISION
    candidate_revision = "b" * 40
    state_root = tmp_path / ".artifacts" / "operations" / "deployments"
    state_root.mkdir(parents=True)
    state_root.joinpath("last-successful-revision").write_text(
        active_revision + "\n", encoding="utf-8"
    )
    state_root.joinpath("state.json").write_text(
        json.dumps({"active_revision": active_revision, "active_slot": "blue"}),
        encoding="utf-8",
    )
    tmp_path.joinpath(".deployment-sha").write_text(candidate_revision + "\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "trusted_legacy_pg_snapshot.py").write_text(
        "print('sanitized')\n", encoding="utf-8"
    )
    inspected: list[str] = []

    def fake_run(command, *, cwd, policy):
        del cwd, policy
        if command[-3:] == ["config", "--format", "json"]:
            return json.dumps(_compose()).encode()
        if command[-4:] == ["ps", "--all", "--format", "json"]:
            return json.dumps(_ps()).encode()
        if "http://127.0.0.1:2019/config/" in command:
            return json.dumps(
                {
                    "apps": {
                        "http": {
                            "servers": {
                                "srv0": {
                                    "routes": [
                                        {
                                            "handle": [
                                                {
                                                    "handler": "reverse_proxy",
                                                    "upstreams": [{"dial": "backend-blue:8000"}],
                                                }
                                            ]
                                        }
                                    ]
                                }
                            }
                        }
                    }
                }
            ).encode()
        assert command[-4:-1] == ["python", "-B", "-c"]
        assert command[-1].splitlines() == ["print('sanitized')"]
        return b"{}"

    def verify_running_revision(_items, *, cwd, policy, expected_revision):
        del cwd, policy
        inspected.append(expected_revision)
        assert expected_revision == active_revision
        return (active_revision,)

    from scripts import trusted_runtime_collector as collector

    monkeypatch.setattr(collector, "_now", lambda: CAPTURED_AT)
    monkeypatch.setattr(collector, "_host_fingerprint", lambda: "host-fingerprint")
    monkeypatch.setattr(collector, "_run_bounded", fake_run)
    monkeypatch.setattr(collector, "_inspect_runtime_environments", lambda *args, **kwargs: {})
    monkeypatch.setattr(collector, "_inspect_revisions", verify_running_revision)
    monkeypatch.setattr(
        collector, "_running_container_ids", lambda *args, **kwargs: ("active-container",)
    )
    monkeypatch.setattr(
        collector,
        "build_topology_observation",
        lambda compose, ps, context, **kwargs: _topology(context=context),
    )
    monkeypatch.setattr(
        collector,
        "_parse_child_snapshot",
        lambda payload, context: _postgres(context),
    )

    actual = collector.collect_runtime_snapshot(
        release_path=tmp_path,
        compose_file=tmp_path / "docker-compose.yml",
        policy=_approved_policy(),
    )
    assert inspected == [active_revision]
    assert actual.context.revisions == tuple(sorted((active_revision, candidate_revision)))
    assert actual.candidate_revision == candidate_revision
    assert actual.result.status == Verdict.PASS


@pytest.mark.parametrize("unattributed", (None, 1))
def test_verified_runtime_with_unknown_client_attribution_cannot_pass(unattributed) -> None:
    postgres = _postgres(_context())
    postgres = replace(
        postgres, capacity=replace(postgres.capacity, unattributed_connections=unattributed)
    )
    model, _ = build_verified_budget_model(postgres, _topology(), _approved_policy())

    result = evaluate(model, now=CAPTURED_AT + timedelta(seconds=1))

    assert result.status == Verdict.UNKNOWN
    assert any(item.code == "connection_attribution_incomplete" for item in result.diagnostics)
