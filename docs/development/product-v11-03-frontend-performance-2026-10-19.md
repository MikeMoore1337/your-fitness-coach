# Product V11-03 - frontend performance: final profiling evidence

Issue: [#818](https://github.com/MikeMoore1337/your-fitness-coach/issues/818) ·
PR: [#1126](https://github.com/MikeMoore1337/your-fitness-coach/pull/1126) ·
2026-10-19.

## Revisions and measurement method

- Matched BEFORE: `42a75a5f1fbea025204c5d1e1a928bfd6581b1a1` (`origin/master`).
- Previous PR application head: `1cb669bc91aab8390ae4cd16568f710688a85df0`.
- Final measured application source: `b516f9ca` (`perf(frontend): preserve private route chunk split`).
- The parent PR follow-up after the measured application code is the lockfile-only `aiohttp`
  security refresh; it does not change backend source or the measured frontend behavior.
- Both builds used Node `24.14.0`, npm `11.11.1`, Vite `7.3.6`, Windows and the existing
  lockfile. The browser lab used Playwright Chromium `151.0.7922.34`, mocked
  `platform-api` fixtures, reduced motion, desktop `1440x900` and mobile `390x844`.
- Mobile throttling was CPU `4x`, `150 ms` latency, `1.5 Mbps` down / `750 Kbps` up.
- The full route profiler used three runs per route/cache state and five runs for Coach OS;
  the canonical `performance-hardening.spec.ts` remains the CI regression suite.
- This is synthetic local evidence. It is not a physical-device, Telegram WebView, CrUX,
  RUM or production measurement.

## Bundle results and CoachPage investigation

| Metric | BEFORE `42a75a5f` | Previous PR app `1cb669bc` | Final `b516f9ca` | Final result |
| --- | ---: | ---: | ---: | --- |
| Entry JS raw | 310,971 B | 295,379 B | 295,985 B | PASS |
| Entry JS gzip | 97,485 B | 92,773 B | 92,971 B | PASS; 3,029 B below 96,000 B |
| Entry CSS raw / gzip | 64,478 / 13,216 B | 64,478 / 13,216 B | 64,478 / 13,216 B | unchanged |
| Public assets | 31 / 647,377 B | 31 / 647,377 B | 31 / 647,377 B | unchanged |
| Largest public asset | 100,570 B | 100,570 B | 100,570 B | unchanged |
| `CoachPage` raw / gzip | 186,512 / 45,771 B | 386,984 / 97,795 B | 186,586 / 45,799 B | returned to baseline-sized route chunk |
| `perf:check` | expected FAIL | PASS | PASS | budget unchanged |

The earlier `CoachPage` growth was a Rollup dependency-ownership effect, not new Coach OS
business logic. Moving `MiniAppPage` under the new lazy `AuthenticatedRoutes` boundary made
private feature modules attach to the CoachPage dynamic entry. The final narrow fix keeps
`MiniAppPage` as a top-level dynamic import and passes it through `AuthenticatedAppRoute`;
the auth boundary, route decisions and child behavior stay unchanged. This restores the
private route split without returning authenticated code to the public entry.

The final build emits `AuthenticatedRoutes` at 3,028 raw / 1,498 gzip and `AuthProvider` at
9,858 raw / 3,570 gzip. No performance budget was raised.

## Final route-lab matrix

`ready` is the time to the scenario's visible synthetic locator, not a field UX metric.
`TBT` and Long Tasks are browser-lab observations. Resource-timing transfer bytes are
diagnostic only; build artifact sizes above are the authoritative bundle measurements.

| Scenario | Cache/profile | BEFORE ready p50 | Final ready p50 | BEFORE → final TBT p50 | API duplicate paths |
| --- | --- | ---: | ---: | ---: | --- |
| Landing | cold desktop | 443 ms | 459 ms | 0 → 0 ms | none |
| Today | cold desktop | 874 ms | 875 ms | 0 → 0 ms | none |
| Active Workout | cold desktop | 960 ms | 973 ms | 0 → 0 ms | same `progress/summary`, `week` |
| Nutrition | cold desktop | 447 ms* | 875 ms | 0 → 0 ms | same `/api/v1/me` |
| Exercise Encyclopedia | cold desktop | 867 ms | 887 ms | 0 → 0 ms | none |
| Programs | cold desktop | 875 ms | 871 ms | 0 → 0 ms | none |
| Coach OS | cold desktop | 873 ms | 873 ms | 0 → 0 ms | none |
| Today | cold mobile-throttled | 2,005 ms | 2,105 ms | 11 → 143 ms | none |
| Active Workout | cold mobile-throttled | 2,343 ms | 2,839 ms | 117 → 124 ms | same `progress/summary`, `week` |
| Nutrition | cold mobile-throttled | 2,053 ms | 2,275 ms | 121 → 212 ms | same `/api/v1/me` |
| Exercise Encyclopedia | cold mobile-throttled | 1,993 ms | 1,973 ms | 12 → 101 ms | none |
| Programs | cold mobile-throttled | 1,739 ms | 2,011 ms | 10 → 95 ms | none |
| Coach OS | cold mobile-throttled | 1,983 ms | 2,152 ms | 37 → 12 ms | none |

`*` The BEFORE Nutrition p50 has a wide `436–860 ms` range; it is not treated as a
stable improvement or regression. The final mobile matrix shows a remaining synthetic
private-route cost from the auth-only boundary and the resulting route graph. The narrow
source fix resolves the confirmed CoachPage chunk-growth problem, but it does not prove a
private mobile route performance budget. A stricter private-route budget or a real-device
calibration would need a separate scoped decision; no broader routing or cache rewrite is
introduced here.

### Coach transitions

The final same-context transition profile measured three runs per profile:

- `/app → /coach`: desktop p50 `872 ms`, mobile-throttled p50 `609 ms`; 12 new JS
  resources and five expected Coach API calls.
- `/coach → /app`: desktop p50 `389 ms`, mobile-throttled p50 `622 ms`; four new JS
  resources and nine expected Today API calls.
- `/login → /coach`: `NO_DATA`. The authenticated synthetic fixture did not expose a
  valid login-start state consistently; the run only observed the immediate synthetic
  redirect in some attempts. This is not OAuth or real login evidence.
- Background/resume and Telegram WebView lifecycle: `NO_DATA`.

The repeated Active Workout and Nutrition duplicate paths are present in BEFORE and final
under the same fixture; they are not attributed to this change and were not “fixed” by
adding retries, cache tuning or weakened assertions.

## Source-confirmed bounded changes

1. Telegram demo-only session code remains deferred until Telegram `/demo`; cleanup still
   completes before React renders.
2. `ExerciseGuideVideo` keeps the approved HD source/poster and pauses offscreen or when the
   document is hidden, then resumes without a second source load.
3. Authenticated route internals remain outside the public bootstrap. `MiniAppPage` is kept
   as a top-level private dynamic entry so Rollup can share feature chunks instead of placing
   them in the CoachPage chunk.
4. The existing `frontend-checks` group keeps the strict `perf:check` immediately after the
   production build.
5. No global Query cache tuning, broad memoization, router replacement, media re-encoding,
   CSS/design change, backend source change or production infrastructure change was justified.
   The `aiohttp` security follow-up remains lockfile-only.

## Verification

- `npm run build`: PASS on final `b516f9ca`; 569 modules, entry `295,985 / 92,971 B`.
- `npm run perf:check`: PASS; the unchanged BEFORE guard failure remains `310,971 / 97,485 B`.
- `npm run test -- --run`: PASS, 157 files / 962 tests.
- `npm run lint`: PASS, including Russian UI and thick-lime-edge guards.
- Canonical Chromium Playwright: PASS, 8/8 `performance-hardening.spec.ts` tests.
- Pre-commit hooks for the source commit: PASS.
- Plain local `npm run format:check`: baseline failure across 539 files from existing
  line-ending formatting differences. No broad formatting rewrite was made; the repository
  CI contract uses `--end-of-line auto`.
- Full route and transition aggregates are retained as ignored local diagnostics under
  `.artifacts/runtime/tmp/profile-final.json` and `transitions-final.json`; this report is
  the committed summary.

## Evidence boundaries and release status

- Real mobile devices, real Telegram clients/WebViews, CrUX/RUM, production LCP/CLS/INP,
  production API traces, React Profiler recordings and reliable CPU/heap field profiles:
  `NO_DATA`.
- The final source evidence is technically complete for the scoped public-entry and
  CoachPage chunk work. Because the synthetic mobile private-route matrix still shows a
  route-graph/auth-boundary cost without an owner-approved private-route budget, status is
  `NEEDS_WORK` for release approval rather than an unsupported `READY_FOR_RELEASE_APPROVAL`.
- Merge, production deploy and Issue closure remain separate owner-authorized gates.
