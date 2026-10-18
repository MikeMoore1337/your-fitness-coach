# Make Feature: Issue #848 / V11-DB-01

- Stage: implementation in isolated worktree; production gate intentionally not activated.
- Depth: deep — production topology and PostgreSQL capacity are critical unknowns; the safe result is UNKNOWN/BLOCKED, never an inferred PASS.
- Base: `origin/master` `7b755925ad03ea50215b9260b82e8c48cd506d22`.
- Branch: `codex/848-v11-db-01`.
- Issue: [#848](https://github.com/MikeMoore1337/your-fitness-coach/issues/848); dependency [#815](https://github.com/MikeMoore1337/your-fitness-coach/issues/815) is closed as a bounded factual baseline, not a production-readiness certificate.
- Current decision: add an independent preflight module, tests and operational documentation; defer live deployment wiring until owner-approved production-shaped inputs exist.

## Acceptance gates

- C1: static engine, setup/migration, phase, pooler and external-consumer inputs are explicit; missing or malformed critical values fail closed.
- C2: formula covers steady state, candidate overlap, unexpected all-slot overlap, migrations/setup, backup/other consumers and rollback without double-counting current YFC sessions.
- C3: verdicts are exactly `PASS`, `BLOCKED` or `UNKNOWN`; only numeric, credential-free evidence is emitted.
- C4: synthetic tests cover normal headroom, exhaustion, unknown capacity, missing pools, replica/overlap, migration/setup, rollback, PostgreSQL read failure, invalid values, rejected bypass and stage ordering.
- C5: documentation gives the future insertion point and exact owner-controlled production evidence; no production query, rollout, merge or Issue closure occurs in this change.

## Open gates

- Production `max_connections`, reserved slots, pooler topology, effective `.env`, process/replica counts, attribution, overlap and safety margin: `NO_DATA`/`NOT_PROVEN`.
- Owner approval of the numeric safety headroom and sanitized evidence: required before activation.
- Independent dry run against authorized production-shaped evidence: required before production rollout.
- Draft PR #1118 is open at exact head `fd80be47`; CI run `39164466640` and aggregate `checks` passed. Reviewer/security gate remains pending.
