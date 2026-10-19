# Product V11-03 - frontend performance: final profiling evidence

Issue: [#818](https://github.com/MikeMoore1337/your-fitness-coach/issues/818) ·
PR: [#1126](https://github.com/MikeMoore1337/your-fitness-coach/pull/1126) ·
2026-10-19.

## Revisions and measurement method

- Matched BEFORE: `42a75a5f1fbea025204c5d1e1a928bfd6581b1a1` (`origin/master`).
- PR before the mobile investigation fix: `775cc7343fc5f79a3f165bd1ed39ab722e12c398`.
- Final application code: `415b4e720fe0bb1c51784c40f43a3d9558fd92bd`.
- Both revisions were built in isolated worktrees with Node `24.14.0`, npm `11.11.1` and
  Vite `7.3.6`. The lab used Playwright Chromium `151.0.7922.34`, mocked
  `platform-api` fixtures, reduced motion, mobile `390x844`, CPU `4x`, `150 ms` latency,
  `1.5 Mbps` down and `750 Kbps` up.
- Cold profiles used 10 independent browser contexts per scenario, in one worker. Warm
  profiles used one context and five reloads per scenario. Client transitions used five
  same-context Today -> Nutrition and Today -> Programs navigations per revision.
- Route readiness means the first visible scenario-specific locator. `TBT`, Long Tasks,
  LCP and Resource Timing bytes are synthetic browser diagnostics, not product UX or field
  metrics. `jsEncodedBytes` is the encoded JavaScript response total observed by the page.
- The measurements use local Vite preview servers. Their responses were not browser-cache
  hits during the warm profile, so warm numbers are a comparison of the route graph rather
  than production cache performance.
- This is synthetic local evidence. Physical devices, Telegram WebView, CrUX, RUM and
  production traces remain `NO_DATA`.

## Reduced-motion CI blocker - targeted remediation

The previous PR head `d61c9df240a9fbc9ece7227fb2db7a02e450ee5e` was blocked by run
[39324048719](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39324048719).
`Frontend smoke (3/5)` failed twice in
`progress-experience.spec.ts:2992` because Chromium serialized the computed duration as
`1e-05s` while the test required the literal string `0s`. The run was on the PR merge ref
`447b0f265ca17c4351a16010a65a6e45c57adb57`; the PR head was unchanged at `d61c9df2`.

The application CSS was not the defect. `data-viz.css` already disables chart transitions with
`transition: none !important`, while the existing global reduced-motion contract sets
`transition-duration: 0.01ms !important`. `1e-05s` is the same `0.01ms` duration expressed in
seconds. The production CSS and chart behavior were therefore left unchanged.

The baseline `42a75a5f1fbea025204c5d1e1a928bfd6581b1a1` and PR `d61c9df` have identical
`progress-experience.spec.ts`, `design-system.css` and `data-viz.css` for this contract. The
original test passed locally on both revisions with Windows Chromium CSSOM returning `0s`, but
the Linux CI runner exposed the valid scientific notation. The new test explicitly confirms both
`prefers-reduced-motion: reduce` and `forced-colors: active`, then parses computed CSS durations
numerically instead of comparing a platform-specific string.

The parser accepts `0s`, `1e-05s`, `0.01ms` and lists whose every duration is at most `0.01ms`.
It rejects visible durations such as `150ms`, mixed lists containing a visible duration, and
unknown units or malformed values. No CSS, design, HD media or runtime code changed.

Local evidence for the test-fix worktree:

- Targeted reduced-motion tests: `2/2` Chromium passed, including the parser regression cases
  and both active media-feature assertions.
- `npm run typecheck`: PASS; `npm run lint`: PASS, including Russian UI and thick-lime-edge
  guards.
- `npm run test`: `157` files / `962` tests passed.
- `npm run build`: PASS, `570` modules; `npm run perf:check`: PASS with the unchanged Entry and
  CoachPage budgets below.
- Critical mobile matrix: `48/52` passed. The four failures are the already-known baseline-only
  screenshots: Progress light/dark on Chromium and Active Workout on Chromium/WebKit; all
  functional and geometry checks passed.
- `tests/test_ci_contract.py`: `53/53` passed.

Final exact-head GitHub Actions evidence is recorded below after the documentation commit. Until
that run is green, release readiness remains `NEEDS_WORK`.

## Bundle results and CoachPage contract

| Metric | BEFORE `42a75a5f` | PR before fix `775cc734` | Final code `415b4e72` | Result |
| --- | ---: | ---: | ---: | --- |
| Entry JS raw | 310,971 B | 295,985 B | 295,889 B | PASS |
| Entry JS gzip | 97,485 B | 92,971 B | 92,983 B | PASS; 3,017 B below 96,000 B |
| Entry CSS raw / gzip | 64,478 / 13,216 B | 64,478 / 13,216 B | 64,478 / 13,216 B | unchanged |
| Public assets | 31 / 647,377 B | 31 / 647,377 B | 31 / 647,377 B | unchanged |
| Largest public asset | 100,570 B | 100,570 B | 100,570 B | unchanged |
| `CoachPage` raw / gzip | 186,512 / 45,771 B | 186,586 / 45,799 B | 186,590 / 45,800 B | no growth |
| `perf:check` | expected FAIL | PASS | PASS | budget unchanged |

The earlier ~98 KB `CoachPage` result was a Rollup dependency-ownership effect. The final
code keeps Coach OS as its own private dynamic entry and does not move authenticated code to
the public bootstrap. The final private `/app` graph adds a 1,104 raw / 567 gzip
`AuthenticatedAppPage` boundary; `AuthenticatedRoutes` remains 3,027 raw / 1,497 gzip and
`AuthProvider` remains 9,858 raw / 3,571 gzip. No performance budget was raised.

## Historical three-run matrix

The earlier three-run profile is retained as historical context. It is superseded for the
mobile private-route decision by the 10-run investigation below.

| Scenario | Cache/profile | BEFORE ready p50 | PR before fix ready p50 | TBT p50 BEFORE -> PR |
| --- | --- | ---: | ---: | ---: |
| Today | cold mobile-throttled | 2,005 ms | 2,105 ms | 11 -> 143 ms |
| Active Workout | cold mobile-throttled | 2,343 ms | 2,839 ms | 117 -> 124 ms |
| Nutrition | cold mobile-throttled | 2,053 ms | 2,275 ms | 121 -> 212 ms |
| Exercise Encyclopedia | cold mobile-throttled | 1,993 ms | 1,973 ms | 12 -> 101 ms |
| Programs | cold mobile-throttled | 1,739 ms | 2,011 ms | 10 -> 95 ms |
| Coach OS | cold mobile-throttled | 1,983 ms | 2,152 ms | 37 -> 12 ms |

Those small samples motivated the controlled re-measurement; they were not treated as proof
of a regression.

## Mobile Private Route Regression - Final Investigation

### Decision table

The values below are medians of 10 cold runs under the fixed mobile profile. `Difference` is
Final minus BEFORE; the conclusion also reports the change from the PR before the fix.

| Screen | BEFORE p50 | PR before fix p50 | Final p50 | Difference | Conclusion |
| --- | ---: | ---: | ---: | ---: | --- |
| Active Workout | 3,874 ms | 3,813 ms | 3,827 ms | -47 ms | No regression versus BEFORE; final is 14 ms slower than PR before fix |
| Programs | 2,979 ms | 3,096 ms | 3,073 ms | +94 ms | Regression confirmed in PR; boundary change recovers 23 ms, residual is small but measurable |
| Nutrition | 4,089 ms | 4,052 ms | 4,060 ms | -29 ms | No regression versus BEFORE; duplicate `/me` is unchanged |
| Today | 3,113 ms | 3,482 ms | 3,225 ms | +112 ms | Regression confirmed in PR; boundary change recovers 257 ms |
| Coach OS | 3,493 ms | 3,527 ms | 3,529 ms | +36 ms | Small lab delta; Coach route graph is unchanged and chunk budget is preserved |
| Exercise Encyclopedia | 3,490 ms | 3,563 ms | 3,580 ms | +90 ms | Control route remains variable; no encyclopedia-specific code was changed |

### Cold-run distribution and transfer evidence

Each cell in the three revision columns is `p50 / p75 / min-max / SD`, in milliseconds.
Final JavaScript is the observed `count / encoded bytes`; Programs and Encyclopedia have
late route chunks that sometimes load after the readiness locator, so their resource totals
are reported as sets.

| Screen | BEFORE distribution | PR before fix distribution | Final distribution | Final JS / TBT p50 |
| --- | --- | --- | --- | --- |
| Today | 3,113 / 3,120 / 3,091-3,147 / 16 | 3,482 / 3,498 / 3,469-3,514 / 15 | 3,225 / 3,240 / 3,207-3,244 / 14 | 27 / 218,374 B; 64 ms |
| Active Workout | 3,874 / 3,887 / 3,855-3,892 / 13 | 3,813 / 3,816 / 3,804-3,824 / 6 | 3,827 / 3,832 / 3,811-3,853 / 12 | 27 / 218,374 B; 176 ms |
| Nutrition | 4,089 / 4,107 / 3,976-4,113 / 43 | 4,052 / 4,064 / 3,971-4,077 / 30 | 4,060 / 4,069 / 4,001-4,088 / 24 | 31 / 287,049 B; 22 ms |
| Programs | 2,979 / 2,987 / 2,959-3,011 / 14 | 3,096 / 3,449 / 3,074-3,475 / 178 | 3,073 / 3,084 / 3,054-3,455 / 121 | 27/28/32; 218,374/219,006/268,415 B; 60 ms |
| Coach OS | 3,493 / 3,506 / 3,472-3,516 / 16 | 3,527 / 3,541 / 3,482-3,556 / 24 | 3,529 / 3,534 / 3,488-3,542 / 17 | 34 / 271,517 B; 7 ms |
| Exercise Encyclopedia | 3,490 / 3,506 / 3,456-3,511 / 17 | 3,563 / 3,574 / 3,552-3,598 / 13 | 3,580 / 3,587 / 3,461-3,607 / 41 | 29 / 225,336 B; 60 ms |

The PR-before-fix 10-run batch confirms the direction of the earlier observation for Today
and Programs, but not for Active Workout or Nutrition. The final boundary change materially
improves Today and slightly improves Programs without restoring the failed public entry
budget or inflating CoachPage. The remaining Today/Programs residual is not silently
converted into a new hard runtime budget.

### Warm and in-app transition checks

The five-reload warm p50 values were:

| Scenario | BEFORE | Final | Final - BEFORE |
| --- | ---: | ---: | ---: |
| Today | 3,030 ms | 3,421 ms | +391 ms |
| Active Workout | 3,738 ms | 3,717 ms | -21 ms |
| Nutrition | 3,998 ms | 3,948 ms | -51 ms |
| Programs | 3,165 ms | 3,445 ms | +280 ms |
| Coach OS | 3,434 ms | 3,411 ms | -23 ms |
| Exercise Encyclopedia | 3,440 ms | 3,405 ms | -35 ms |

These warm values are diagnostic only because the local preview did not return cache hits;
they should not be used as production warm-cache claims. Same-context transitions stayed
within the existing route graph: Today -> Nutrition was `1,539 -> 1,583 ms` p50 with four
new JS resources and the same five expected API paths; Today -> Programs was `237 -> 264 ms`
p50 with no new JS resources and no duplicate API path. The small transition deltas do not
show a new navigation waterfall.

### Lazy-boundary experiments

Two isolated variants were tested against the PR-before-fix build:

1. **Private-only preload:** started `AuthenticatedRoutes` and `MiniAppPage` from
   `bootstrap` only for `/app` or `/coach`. Entry gzip became `93,017 B` and CoachPage
   stayed `45,800 B`. The five-run Today p50 was `3,475 ms`, so the earlier request start
   did not produce a reliable gain: the concurrent private requests contended for the same
   throttled connection.
2. **Combined `/app` lazy entry (selected):** moved the existing auth wrappers and
   `MiniAppPage` composition into `AuthenticatedAppPage`, a private-only lazy module. The
   experimental entry remained `92,983 B` gzip and CoachPage remained `45,800 B`. The
   five-run Today p50 was `3,228 ms` and Programs p50 was `3,076 ms`; the final 10-run
   results above confirm the direction. No public route imports this module.

The measured module graph is:

```text
PR before fix:  public entry -> AuthenticatedRoutes/AuthProvider -> MiniAppPage -> screen
Final:         public entry -> AuthenticatedAppPage
                 -> AuthenticatedRoutes/AuthProvider and MiniAppPage -> screen
```

AuthProvider, AuthGate, OnboardingGate, trainer-intent redirects and the `/api/v1/me`
authorization check remain in the same trusted path. The change starts independent private
modules together; it does not display private data before AuthGate completes.

### Hypothesis results

- **Sequential dynamic imports:** confirmed for the PR `/app` graph. In the PR-before-fix
  trace, auth chunks started around `1,020 ms` while `MiniAppPage` started around `1,478 ms`.
  In the final trace, `AuthenticatedAppPage`, auth dependencies and `MiniAppPage` started
  around `1,020 ms`.
- **Authorization cost:** not bypassed. `/api/v1/me` stayed one request for Today and two
  for Nutrition in BEFORE, PR-before-fix and Final; the Nutrition duplicate is pre-existing
  under the fixture.
- **Additional API/query work:** no new duplicate path or invalidation was found. The
  canonical Today query-count test remains green.
- **React rendering:** no React Profiler recording was available (`NO_DATA`). No broad
  memoization or Query default change was justified.
- **CoachPage ownership:** preserved. The selected `/app` composition does not move the
  MiniApp graph into CoachPage; CoachPage stays `186,590 / 45,800 B`.

### Proposed diagnostic runtime control (not owner-approved)

The existing build budget remains the hard CI control: Entry JS gzip must stay at or below
`96,000 B`. Runtime should remain a separate lab diagnostic because local and CI machines,
browser cache policy and real Telegram WebView behavior differ.

For future investigations, the evidence-based proposal is:

- use at least 10 alternating cold runs per revision with the fixed profile above;
- publish p50, p75, min, max, SD, request duplicates, JS count/encoded bytes and TBT;
- investigate a runtime regression only when p50 and p75 move in the same direction by more
  than 10% and at least 150 ms, then repeat a second batch before changing code;
- do not turn this local threshold into a CI wall-time gate or raise the existing bundle
  limit without an owner decision.

This proposal is a measurement convention, not an approved product SLA.

## Source-confirmed bounded changes

1. Telegram demo-only session code remains deferred until Telegram `/demo`; cleanup still
   completes before React renders.
2. `ExerciseGuideVideo` keeps the approved HD source/poster and pauses offscreen or when the
   document is hidden, then resumes without a second source load.
3. The authenticated `/app` composition is now one private-only lazy entry so its auth graph
   and MiniAppPage can start together. Auth, navigation, onboarding, trainer-intent routing,
   API contracts and data boundaries are unchanged.
4. CoachPage remains a separate dynamic entry and the existing `perf:check` stays strict.
5. No global Query tuning, broad memoization, router replacement, media re-encoding, CSS or
   design change, backend source change or production infrastructure change was justified.

## Reproduction commands

The committed opt-in profilers are `frontend/tests/e2e/v11-route-profile.profile.ts` and
`frontend/tests/e2e/v11-transition-profile.profile.ts`; they use the existing mocked
`platform-api` fixture and are excluded from the ordinary E2E glob by their `.profile.ts`
suffix.

```powershell
cd frontend
npm run build
npm run perf:check

$env:PW_BASE_URL = 'http://127.0.0.1:4175'
$env:PW_EXTERNAL_SERVER = '1'
$env:V11_PROFILE_MODE = 'cold'
$env:V11_PROFILE_RUNS = '10'
$env:V11_PROFILE_REVISION = '415b4e720fe0bb1c51784c40f43a3d9558fd92bd'
$env:V11_PROFILE_OUT = '..\.artifacts\runtime\tmp\v11-profile-final-cold-10.json'
npx playwright test --config=playwright.profile.config.ts tests/e2e/v11-route-profile.profile.ts

$env:V11_PROFILE_RUNS = '5'
$env:V11_PROFILE_OUT = '..\.artifacts\runtime\tmp\v11-transition-final-5.json'
npx playwright test --config=playwright.profile.config.ts tests/e2e/v11-transition-profile.profile.ts
```

Run the same commands from the BEFORE worktree with port `4174`, revision
`42a75a5f1fbea025204c5d1e1a928bfd6581b1a1` and a separate output file. Keep the two preview
servers and browser contexts isolated; do not publish trace files or fixture credentials.

## Verification and evidence boundaries

- `npm run build`: PASS on final code; 570 modules, entry `295,889 / 92,983 B`.
- `npm run perf:check`: PASS; the unchanged BEFORE guard failure is `310,971 / 97,485 B`.
- `npm run typecheck`: PASS.
- `npm run lint`: PASS, including Russian UI and thick-lime-edge guards.
- `npm run test`: PASS, 157 files / 962 tests.
- Targeted Chromium `performance-hardening.spec.ts`: PASS, 8/8.
- Mobile Chromium: 23/26 functional/geometry checks passed; the three screenshot failures
  (Progress light/dark and Active Workout full-page) reproduced exactly on BEFORE.
- Mobile WebKit: 25/26 checks passed; the Active Workout screenshot failure reproduced on
  BEFORE. No functional, safe-area or geometry failure was introduced.
- Opt-in cold, warm and transition profiles completed for both revisions as documented above.
- Pre-commit hooks for the source commit: PASS.
- Exact-head GitHub Actions run [39319719804](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39319719804)
  completed on `98be9222b7d510c8a0af02ff18370a09aa6b2cf9` with aggregate `checks: failure`.
  Attempt 1 reported four unrelated E2E failures; the failed-shard rerun (attempt 2) left only
  the existing reduced-motion assertion in `progress-experience.spec.ts:2992` failing twice:
  expected `0s`, received `1e-05s`. The test is unchanged by this PR, and all other attempt-2
  jobs passed. This is a CI acceptance blocker, not evidence of a private-route performance
  regression; it remains `NEEDS_WORK` until the repository check is resolved or owner-approved
  as baseline noise.
- The subsequent exact-head run [39321786132](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39321786132)
  completed on `0d46ff806c3978e7f8f14b08e8d9898fd989e133` with the same aggregate failure.
  `Frontend smoke (3/5)` again failed only `progress-experience.spec.ts:2992` with expected
  `0s` and received `1e-05s`; build, unit, mobile, security and other completed jobs passed.
- Real devices, Telegram clients/WebViews, CrUX/RUM, production LCP/CLS/INP, React Profiler,
  CPU/heap field data and production API traces: `NO_DATA`.

The confirmed PR regression was the `/app` lazy waterfall. The selected fix is implemented
and measured, while the remaining small lab residual and the proposed runtime convention are
explicitly not treated as owner-approved SLAs. Merge, production deploy and Issue closure
remain separate owner-authorized gates. Final status: `NEEDS_WORK` because the exact-head
aggregate `checks` is not green; the performance investigation and code fix are otherwise
complete. Release approval must wait for that CI blocker to be resolved or explicitly classified
by the owner.
