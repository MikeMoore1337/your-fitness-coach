# Issue #960 - measured rest implementation review

**Status: Draft PR #1081; NOT READY FOR MERGE OR RELEASE.**

Implementation branch: `codex/issue-960-rest-implementation`. This is distinct from the design-only Draft PR #1044. The visual direction is the existing RestTimer with its countdown on the left, the "Далее" label in the center and an additive "Факт" elapsed counter + "Стоп" on the right. The existing +30 / +60 / Пропустить row is retained.

## Implemented in this branch

- SQLAlchemy models, additive Alembic migration `0130_workout_rest_sessions.py`, typed owner-scoped rest API.
- A per-source-set unique interval; planned and adjusted targets are independent of prescribed exercise rest.
- Explicit completion, skip, interrupt and unknown with versioned/idempotent actions. `measured_seconds` remains null if unconfirmed.
- Durable browser journal for deferred post-acknowledgement synchronization. Rest stays running after the planned countdown expires until the user stops it.
- Recorded intervals in workout history and report/PDF aggregates, using the original plan as the baseline for deltas. Coach report generation reuses existing subject authorization.
- Basic backend + frontend unit tests; recovery after reload and guard against cutoff intervals being called reliably measured.
- Basic retry-loop guard for client sync and acceptance of rest events queued before a workout was finished, then delivered later.

## Non-negotiable outstanding checks

- Exact-head CI and migration against a real PostgreSQL database; migrations must remain additive.
- Actual Chromium/WebKit AFTER screenshots in Light/Dark on 320/360/393/430 px and desktop, safe-area / dock / keyboard checks, real TMA and VoiceOver if available.
- Race tests for simultaneous writes from multiple browser tabs and pending journal updates; the current journal write operation itself is not guarded by an asynchronous cross-context transaction.
- Network failure and reconnect tests including pre-server-ack offline sets, stale versions and persistent HTTP 409 responses; do not discard pending data silently.
- Hard-cutoff behavior after prolonged offline periods (currently the API bounds historical start times to 24 hours, so a very old unsynced unknown session can remain pending).
- Full terminal transition coverage: workout finish/cancel, navigation away, user change, unknown and manual correction. This draft **does not yet provide a complete manual correction interface**.
- Layout verification that the existing RestTimer geometry stays the same aside from the compact right-hand fact/stop controls.
- Owner's product choice on forgotten-stop thresholds: **Policy A is a candidate, not an approved production default.**

## Semantics

"Факт" records time from an acknowledged/durably queued set completion to an explicit user stop, **not objective physiological rest time**. Elapsed time after a timeout is unknown unless corrected. Longer-than-planned rest is not automatically a negative outcome. Missing historical measurements are **never represented as zero**.

## Release gates

1. Complete reliability and integration tests and collect real AFTER evidence.
2. Obtain explicit owner design/threshold approval and final visual acceptance.
3. Rebase or otherwise synchronize with the current `master` safely.
4. Green exact-head required CI; distinct explicit merge and production deploy authorization.

**No merge or deployment is authorized by this document.**
