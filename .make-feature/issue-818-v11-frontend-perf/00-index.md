# Make Feature index — Product V11-03 / Issue #818

Status: READY_FOR_RELEASE_APPROVAL for scoped implementation; merge, deploy and Issue closure remain separate owner gates.
Mode: normal — existing PR continuation with matched frontend performance evidence and bounded source/test changes.
Branch: `codex/818-v11-frontend-perf`; PR #1126.
Current base: `42a75a5f1fbea025204c5d1e1a928bfd6581b1a1` (`origin/master`).
Measured application head: `4e6b85235bb425ab7bcbcc81659149fa2af244d3`.

## Current stage

The existing PR implementation is accepted for this pass. Matched BEFORE/AFTER bundle and browser-lab evidence is recorded in [the implementation report](../../docs/development/product-v11-03-frontend-performance-2026-10-19.md). The final documentation commit contains no application-runtime change after the measured application head.

## Success criteria

- Current-master and exact PR bundle sizes are measured with the unchanged performance budget.
- Confirmed entry/bootstrap and media playback bottlenecks are fixed without redesign or HD-media degradation.
- Existing auth, Today, mocked TMA, public landing, video visibility and duplicate-query paths have regression evidence.
- Exact-head GitHub checks are green; unavailable physical-device and field evidence is explicit `NO_DATA`.
- Merge, deploy and Issue closure remain owner-authorized.

## Decisions

- Keep the existing PR #1126 and its branch; do not create a competing PR.
- Defer Telegram demo-only code and authenticated route internals with existing Vite/React lazy imports.
- Keep HD exercise video source/poster and pause/resume it from visibility signals; do not re-encode or replace media.
- Enforce the existing `entryJsGzip: 96_000` budget after the frontend build; do not raise it.
- Do not tune TanStack Query, add broad memoization, refactor routing or change backend without measured evidence.

## Open evidence

- Real device/TMA WebView behavior, CrUX/RUM and production field metrics remain `NO_DATA`.
- Owner release approval, merge and production deploy remain pending.
