from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from scripts.connection_budget_preflight import PostgresCapacity, Verdict, evaluate
from scripts.trusted_runtime_collector import (
    CollectorFailure,
    CollectorPolicy,
    PostgresObservation,
    RuntimeContext,
    _failure_payload,
    _merge_diagnostics,
    _parse_child_snapshot,
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
    assert future.status == Verdict.UNKNOWN


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
