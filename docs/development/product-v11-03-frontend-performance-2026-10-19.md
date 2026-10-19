# Product V11-03 - frontend performance: implementation evidence

Issue: [#818](https://github.com/MikeMoore1337/your-fitness-coach/issues/818) ·
PR: [#1126](https://github.com/MikeMoore1337/your-fitness-coach/pull/1126) ·
2026-10-19.

## Revisions and measurement method

- Matched BEFORE: `42a75a5f1fbea025204c5d1e1a928bfd6581b1a1` (`origin/master` at measurement time).
- Matched AFTER application code: `4e6b85235bb425ab7bcbcc81659149fa2af244d3` (PR #1126 head before this evidence-only documentation commit).
- The follow-up security unblock changes only `uv.lock`, refreshing `aiohttp` from `3.14.3` to `3.14.5`; it does not change backend source or the measured frontend application code.
- Both revisions used the same `npm ci --ignore-scripts --no-audit --no-fund`, Node `24.14.0`, npm `11.11.1`, Vite `7.3.6`, Windows runner and existing lockfile.
- Browser lab used the existing Playwright Chromium harness with mocked API fixtures, reduced motion, mobile `390x844` and desktop `1440x900`. This is synthetic local evidence, not a physical-device or production measurement.
- Historical #815 values remain useful context, but are not used as the #818 BEFORE.

## Comparable bundle results

| Metric | BEFORE `42a75a5f` | AFTER `4e6b8523` | Change | Result |
| --- | ---: | ---: | ---: | --- |
| Entry JS raw | 310,971 B | 295,379 B | -15,592 B | PASS |
| Entry JS gzip | 97,485 B | 92,773 B | -4,712 B | PASS; 3,227 B below 96,000 B |
| Entry JS gzip budget | 96,000 B | 96,000 B | unchanged | unchanged contract |
| Entry CSS raw | 64,478 B | 64,478 B | 0 B | PASS |
| Entry CSS gzip | 13,216 B | 13,216 B | 0 B | PASS |
| Public assets | 31 / 647,377 B | 31 / 647,377 B | 0 B | PASS |
| Largest public asset | 100,570 B | 100,570 B | 0 B | PASS |
| Performance guard | FAIL: +1,485 B gzip and +971 B raw | PASS | budget recovered | verified |

The BEFORE failure is the current-master fact that the existing guard exposed. The AFTER entry reduction comes from deferring Telegram demo-only session code and moving authenticated route internals behind an auth-only lazy boundary. No budget was raised.

Key chunk observation: `CoachPage` moved from 186.51 kB raw / 45.77 kB gzip to 386.98 kB raw / 97.80 kB gzip because authenticated dependencies now remain with the private route. That is an intentional route-local trade-off for a smaller public entry; authenticated route performance was not claimed improved without a route timing profile. New auth chunks were emitted separately: `AuthenticatedRoutes` 3.80 kB raw / 1.86 kB gzip, `AuthProvider` 9.86 kB raw / 3.57 kB gzip and `OnboardingGate` 0.13 kB raw / 0.13 kB gzip.

## Comparable browser-lab observations

The same `performance-hardening.spec.ts` scenarios passed on both revisions (BEFORE 7/7, AFTER 8/8; AFTER includes the new Telegram demo handoff regression).

| Lab observation, one run per revision | BEFORE | AFTER | Interpretation |
| --- | ---: | ---: | --- |
| Mobile `/` LCP | 504 ms | 564 ms | within 2,500 ms guard; single-run variance, no improvement claim |
| Mobile `/login` LCP | 368 ms | 368 ms | unchanged in this run |
| Desktop `/` LCP | 448 ms | 444 ms | within guard; single-run variance |
| Desktop `/` CLS | 0.022907 | 0.022907 | unchanged |
| Desktop `/` INP | 32 ms | 32 ms | unchanged |
| Today API requests | 11 expected paths × 1 | 11 expected paths × 1 | no duplicate fetch in either run |
| Web/TMA resource graph | equal | equal | no dedicated TMA bundle or public-content chunk in the app flow |

The Playwright LCP/CLS/INP values are laboratory observations from mocked Chromium, not CrUX, RUM, production field data or a physical Telegram WebView. Route-switch timing, React Profiler cost, low-end device CPU/memory and real resume behavior remain `NO_DATA`.

## Source-confirmed bounded changes

1. `main.tsx` now loads demo session code only for Telegram `/demo`, while cleanup still completes before React render.
2. `ExerciseGuideVideo` keeps its existing approved HD source and poster, but keeps observing visibility so looping video pauses offscreen and on document hide, then resumes without a second source load.
3. The existing authenticated wrapper, coach-vs-personal navigation decision and trainer-intent routing moved into an auth-only lazy module. Private behavior is unchanged; public bootstrap no longer carries those dependencies.
4. The existing `frontend-checks` group now runs `npm run perf:check` immediately after the production build. The strict budget is unchanged.
5. No global Query cache tuning, broad memoization, router replacement, media re-encoding, CSS/design change, backend source change or production infrastructure change was justified by the available evidence. The only follow-up outside frontend source is the lockfile-only `aiohttp` security refresh required by the repository audit.

## Verification

- `npm run build`: PASS on both matched revisions; 568 modules BEFORE, 569 AFTER.
- `npm run perf:check`: FAIL on BEFORE with the recorded budget breach; PASS on AFTER.
- `npm run typecheck`: PASS.
- `npm run lint`: PASS, including Russian UI and thick-lime-edge guards.
- CI-compatible format command `npx prettier --check . --end-of-line auto`: PASS.
- Full `npm run test`: **157 files / 962 tests passed** on AFTER.
- Targeted Chromium Playwright: BEFORE 7 passed; AFTER 8 passed.
- `uv audit --locked --no-group dev --no-group scheduled-report`: PASS after the lockfile-only `aiohttp` refresh; no known vulnerabilities reported.
- Exact code-head GitHub Actions run [39290956448](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39290956448) for `4e6b8523`: required checks reported green, including frontend checks, unit, smoke, Chromium/WebKit mobile regression, security and aggregate `checks`.
- The plain local `npm run format:check` command reports pre-existing line-ending formatting differences across 539 files; the repository CI contract uses `--end-of-line auto`, which passed. No broad formatting rewrite was made.

## Evidence boundaries and release status

- Real mobile devices, real Telegram clients/WebViews, CrUX/RUM, production LCP/CLS/INP, production API traces, React Profiler recordings and memory/CPU profiles: `NO_DATA`.
- No visual composition, design token, HD media asset, animation duration/FPS, workout/nutrition business rule, authorization policy, backend source or production infrastructure changed; the follow-up dependency change is lockfile-only.
- Status: `READY_FOR_RELEASE_APPROVAL` for the scoped implementation and evidence. Merge, production deploy and Issue closure remain separate owner-authorized gates.
