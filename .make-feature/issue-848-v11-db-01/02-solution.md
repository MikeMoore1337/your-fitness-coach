# Solution — implemented

## Requirements

The model must be explicit about effective pool ceilings, phase topology, PostgreSQL reserved capacity, current non-YFC sessions, pooler behavior, known additional consumers and an owner-supplied safety headroom. It must never turn a missing production input into zero.

## Evidence and choice

Verified on current master:

- `backend/fitminiapp_api/db/session.py` creates one PostgreSQL SQLAlchemy `QueuePool` per process with `pool_pre_ping=True`, `pool_size`, `max_overflow`, `pool_timeout` and `pool_recycle` from settings.
- `backend/alembic/env.py` uses `pool.NullPool`; `backend/setup-entrypoint.sh` performs readiness, migrations and seed in one setup service, sequentially.
- `docker-compose.yml` defines legacy backend/worker/bot plus blue/green backend/worker/bot services; the bot has no direct SQLAlchemy engine in the inspected source.
- `scripts/zero_downtime_deploy.py` has preflight, backup, migration, candidate start, consumer handoff, rollback and single-slot paths. Its existing host capacity check is CPU/memory/disk only.
- #815 closeout and the current V11 baseline explicitly leave effective production connection budget/headroom `NOT_PROVEN`/`NO_DATA`.

Chosen path: standard-library standalone `scripts/connection_budget_preflight.py`, pure evaluation over sanitized JSON, a read-only DB-API snapshot adapter, and focused pytest coverage. Production wiring is documented but intentionally absent until the owner supplies and approves production-shaped facts.

## Contract

1. `PostgresCapacity` contains numeric server/reserved/current-session facts. PostgreSQL <16 uses an explicit version-aware `reserved_connections=0` fallback; PostgreSQL >=16 requires the setting.
2. `PoolSpec` has an explicit `pool_type`: QueuePool uses only `pool_size + max_overflow` and rejects a contradictory `connection_ceiling`; NullPool/special processes require a positive ceiling and its provenance source.
3. `TopologyInventory` explicitly declares process groups and applicable rollout phases with booleans. Every declared-present group is enumerated in every applicable phase (zero means inactive); missing keys and missing applicable phases are `UNKNOWN`. No fixed backend/worker/migration/setup set is required.
4. Each `PhaseDemand` names process counts and explicit `other_connections`. Phases are mutually exclusive worst-case snapshots; sequential migration and setup are separate phases, so current YFC sessions are not added on top of their configured process ceilings.
5. For no pooler, `phase_app_connections = sum(process_count * pool_ceiling)`. For a known session/transaction pooler, each phase must provide a positive verified PostgreSQL backend cap and the pooler must provide its provenance source. Backend cap is used once, never as current occupancy.
6. `usable = max_connections - superuser_reserved_connections - reserved_connections`.
7. `required(phase) = observed_non_yfc_connections + phase_app_connections + phase_other_connections`; `PASS` requires every phase to satisfy `required + safety_headroom <= usable`.
8. The default/CLI path also requires non-synthetic, fresh, production-labelled evidence; a synthetic calculation can be exercised only with an explicit test-only opt-out.
9. Missing/unreadable attribution, topology, evidence or headroom is `UNKNOWN`; invalid values or insufficient known headroom are `BLOCKED`. Only `PASS` exits zero. There is no bypass flag.
10. A future deployment adapter must run the preflight before backup, migration, candidate launch and rollback. This branch does not call it from production deployment code.

## Plan

- Add the pure model/CLI and read-only snapshot adapter.
- Add deterministic synthetic tests for formula, topology, errors, no-bypass behavior and stage order.
- Add the operational document with confirmed/unknown inventory, evidence commands, rollout insertion point, rollback behavior and owner gates.
- Run targeted pytest/ruff and the repository checks that are practical in the isolated worktree; report skipped or environment-blocked checks separately.

Implementation is limited to the standalone preflight, deterministic tests and this operational document. The existing deployment helper is not imported or changed because the effective production topology, attribution and owner-approved headroom are still unavailable; activating that gate now would create an unverified production behavior change.
