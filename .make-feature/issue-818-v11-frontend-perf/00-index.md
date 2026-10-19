# Make Feature index — Product V11-03 / Issue #818

Status: READY_FOR_RELEASE_APPROVAL after exact-head required CI; merge, deploy and Issue closure remain separate owner gates.
Mode: normal — existing PR continuation with matched 10-run mobile evidence and a bounded private lazy-boundary fix.
Branch: `codex/818-v11-frontend-perf`; PR #1126.
Matched BEFORE: `42a75a5f1fbea025204c5d1e1a928bfd6581b1a1`.
PR before fix: `775cc7343fc5f79a3f165bd1ed39ab722e12c398`.
Final application code: `415b4e720fe0bb1c51784c40f43a3d9558fd92bd`.

## Current stage

The private `/app` lazy waterfall was reproduced with 10 cold mobile runs per revision.
Today improved from PR p50 `3,482 ms` to final `3,225 ms`; Programs improved from
`3,096 ms` to `3,073 ms`. Active Workout and Nutrition were not regressions versus BEFORE.
Entry JS remains `295,889 raw / 92,983 gzip`; CoachPage remains `186,590 raw / 45,800 gzip`.

## Success criteria

- Exact BEFORE, PR-before-fix and final bundle/runtime evidence is documented.
- The confirmed `/app` lazy waterfall is fixed without moving private code into the public entry.
- Auth, onboarding, trainer-intent routing, Today, Active Workout, Nutrition, Programs,
  Encyclopedia, Coach OS, TMA behavior, HD media and design contracts remain intact.
- `perf:check`, typecheck, lint, Vitest, targeted Chromium and mobile Chromium/WebKit checks
  are recorded; baseline-only screenshot failures are not misclassified as new regressions.
- Exact-head GitHub checks are re-read after the evidence/documentation commit.
- Merge, deploy and Issue closure remain owner-authorized.

## Decisions

- Continue PR #1126; do not create a competing PR or force-push.
- Keep `AuthenticatedAppPage` private-only and compose the existing auth wrappers with the
  existing `MiniAppPage` inside that lazy entry.
- Keep the public entry budget at `96,000 B` gzip and keep CoachPage separate.
- Do not apply the rejected preload experiment, global Query tuning, broad memoization, router
  replacement, media re-encoding, CSS/design changes or backend changes.
- Keep the suggested runtime threshold as a diagnostic convention only; it is not an owner-
  approved SLA or CI gate.

## Open evidence

- Real device/TMA WebView behavior, CrUX/RUM, production traces, React Profiler and CPU/heap
  field data remain `NO_DATA`.
- Warm local-preview numbers are diagnostic because the preview did not return cache hits.
- The remaining Today/Programs lab residual is documented, not hidden behind a new limit.
