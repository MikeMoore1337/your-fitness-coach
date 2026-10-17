# Issue #960 - measured rest implementation review

**Status: Draft PR #1081; NOT READY FOR MERGE OR RELEASE.**

Implementation branch: `codex/issue-960-rest-implementation`. This is distinct from the design-only Draft PR #1044. The visual direction is the existing RestTimer with its countdown on the left, the "Далее" label in the center and an additive "Факт" elapsed counter + "Стоп" on the right. The existing +30 / +60 / Пропустить row is retained.

## Implemented in this branch

- SQLAlchemy models, additive Alembic migration `0130_workout_rest_sessions.py`, typed owner-scoped rest API.
- A per-source-set unique interval; planned and adjusted targets are independent of prescribed exercise rest.
- Explicit completion, skip, interrupt and unknown with versioned/idempotent actions. `measured_seconds` remains null if unconfirmed.
- Durable browser journal for deferred post-acknowledgement synchronization. Rest stays running after the planned countdown expires until the user stops it.
- Recorded intervals in workout history and report/PDF aggregates, using the original plan as the baseline for deltas. Coach report generation reuses existing subject authorization.
- Basic backend + frontend unit tests; recovery after reload and explicit correction/skip after absence. No synthetic rest values are inferred from time in background.
- Basic retry-loop guard for client sync and acceptance of rest events queued before a workout was finished, then delivered later.

## Captured browser visuals

Real Chromium Playwright screenshot run [#39065204047](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39065204047) passed **6/6** dedicated tests. Each test generated current elapsed-rest and Variant C recovery screenshots (12 files).

| Width | Light: timer | Light: recovery | Dark: timer | Dark: recovery |
| --- | --- | --- | --- | --- |
| 320px | [PNG](visuals/after-light-320-actual.png) | [PNG](visuals/after-light-320-recovery.png) | [PNG](visuals/after-dark-320-actual.png) | [PNG](visuals/after-dark-320-recovery.png) |
| 393px | [PNG](visuals/after-light-393-actual.png) | [PNG](visuals/after-light-393-recovery.png) | [PNG](visuals/after-dark-393-actual.png) | [PNG](visuals/after-dark-393-recovery.png) |
| 430px | [PNG](visuals/after-light-430-actual.png) | [PNG](visuals/after-light-430-recovery.png) | [PNG](visuals/after-dark-430-actual.png) | [PNG](visuals/after-dark-430-recovery.png) |

Captures used synthetic workouts in Chromium on CI, **not** real iPhone/Safari/Telegram. Images are stored in this feature branch and must be reviewed by the product owner before merge.

## Non-negotiable outstanding checks

- Exact-head CI and migration against a real PostgreSQL database; migrations must remain additive.
- Browser AFTER screenshots exist for Chromium Light/Dark on 320/393/430 px, but owner review, 360px, real mobile Safari/TMA, dock/keyboard and VoiceOver remain unverified.
- Race tests for simultaneous writes from multiple browser tabs and pending journal updates; the current journal write operation itself is not guarded by an asynchronous cross-context transaction.
- Network failure and reconnect tests including pre-server-ack offline sets, stale versions and persistent HTTP 409 responses; do not discard pending data silently.
- Very old offline sessions (the API currently bounds `started_at` to 24 hours) need a reconciliation strategy; pending records must never be silently deleted.
- Full terminal transition coverage: workout finish/cancel, navigation away, user change, and verified manual correction across browser/Telegram TMA; the inline correction form is implemented but still requires browser acceptance.
- Layout verification that the existing RestTimer geometry stays the same aside from the compact right-hand fact/stop controls.
- **Policy C was approved by the owner.** A concrete **15-minute threshold is proposed for review** (not yet separately approved): after at least 15 minutes away AND at least 15 minutes beyond the planned deadline, returning to the app asks for an actual rest duration or `Не учитывать`. Extended foreground rest is not treated as an error. The time in background is never automatically saved as a measurement.

## Semantics

"Факт" records time from an acknowledged/durably queued set completion to an explicit user stop, **not objective physiological rest time**. After prolonged absence, the app asks for an explicit duration or a skipped measurement; there is no automatic 12-hour cap or a 4x planned-rest anomaly rule. Longer-than-planned rest is not automatically a negative outcome. Missing historical measurements are **never represented as zero**.

## Release gates

1. Complete reliability and integration tests and collect real AFTER evidence.
2. Policy C is approved. Obtain approval for the proposed 15-minute threshold and final visual acceptance of its implementation and the existing RestTimer layout.
3. Rebase or otherwise synchronize with the current `master` safely.
4. Green exact-head required CI; distinct explicit merge and production deploy authorization.

**No merge or deployment is authorized by this document.**
