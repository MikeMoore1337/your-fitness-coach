# Make Feature index — Product V11-03 / Issue #818

Status: NEEDS_WORK for release approval; the scoped chunk fix is verified, but synthetic mobile private-route overhead remains unbudgeted. Merge, deploy and Issue closure remain separate owner gates.
Mode: normal — existing PR continuation with matched frontend performance evidence and bounded source/test changes.
Branch: `codex/818-v11-frontend-perf`; PR #1126.
Current base: `42a75a5f1fbea025204c5d1e1a928bfd6581b1a1` (`origin/master`).
Measured application head: `b516f9ca` (`perf(frontend): preserve private route chunk split`).

## Current stage

The final source pass restores the private dynamic chunk graph: `CoachPage` returns to 186.59 kB raw / 45.80 kB gzip while the public entry remains 295,985 raw / 92,971 gzip. Matched route and transition evidence is recorded in [the implementation report](../../docs/development/product-v11-03-frontend-performance-2026-10-19.md). The remaining mobile private-route cost is explicit lab evidence, not a production claim.

## Success criteria

- Current-master and exact PR bundle sizes are measured with the unchanged performance budget.
- Confirmed entry/bootstrap and media playback bottlenecks are fixed without redesign or HD-media degradation.
- Existing auth, Today, mocked TMA, public landing, video visibility and duplicate-query paths have regression evidence.
- Exact-head GitHub checks must be re-read after the final report commit; unavailable physical-device and field evidence is explicit `NO_DATA`.
- Merge, deploy and Issue closure remain owner-authorized.

## Decisions

- Keep the existing PR #1126 and its branch; do not create a competing PR.
- Defer Telegram demo-only code and authenticated route internals with existing Vite/React lazy imports.
- Keep `MiniAppPage` as a top-level private dynamic import and pass it into `AuthenticatedAppRoute` so Rollup does not attach its feature graph to `CoachPage`.
- Keep HD exercise video source/poster and pause/resume it from visibility signals; do not re-encode or replace media.
- Enforce the existing `entryJsGzip: 96_000` budget after the frontend build; do not raise it.
- Do not tune TanStack Query, add broad memoization, refactor routing or change backend source without measured evidence. Keep the required `aiohttp` lockfile security refresh narrow.

## Open evidence

- Real device/TMA WebView behavior, CrUX/RUM and production field metrics remain `NO_DATA`.
- `/login → /coach` cold OAuth behavior remains `NO_DATA` under the synthetic authenticated fixture.
- A stricter private-route mobile budget or follow-up route preloading requires a separate scoped decision.
- Owner release approval, merge and production deploy remain pending.
