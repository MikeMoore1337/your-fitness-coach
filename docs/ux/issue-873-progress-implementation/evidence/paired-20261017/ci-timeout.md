# Issue #873 — Frontend smoke (2/5) timeout analysis

## Observed CI failure

- Workflow run: [39001903034](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39001903034).
- Job: Frontend smoke (2/5), job `117309650365`; aggregate checks job `117312452888`.
- The shard reached `Running 165 tests using 2 workers, shard 2 of 5`, then was cancelled at
  the 15-minute job limit from `.github/workflows/ci.yml`. The cancellation cleanup killed the
  Playwright/Chromium/npm processes. No test result or trace was emitted for the cancelled tail.

## Reproduction and root cause

The same shard was reproduced locally with Chromium and two workers. The first deterministic
stall was in `final-ux-closeout.spec.ts`, the `history` surface. The PR changed production
`WorkoutHistory` to `compact`, so the rendered `.workout-history-card` is a plain section and
has no direct child `summary`. The closeout test still executed
`.workout-history-card > summary.click()` and then waited for state that could never be reached.

The exact base `4c92832415d4eb994cf6b849a67074742f07ea50` still rendered the collapsible card,
which explains why the stale selector was green before the PR. This is a test/production-contract
drift, not evidence of a renderer loop or a slow product request.

## Fix and verification

The test now accepts both valid render modes: it verifies the history card, clicks the direct
summary only when one exists, and asserts the contextual row. No global timeout was changed,
and no test was skipped.

The first post-change CI run also exposed four deterministic Progress screenshot mismatches in
the mobile regression job (48/52 passed): the approved continuation reduced the Progress outer
vertical gap from 28px to 4px. Chromium and WebKit retry actuals were byte-identical within the
CI artifact. After inspecting those actual/diff images, only the four Progress captures for each
tracked platform (8 files: Linux and Windows, light and dark) were refreshed from stable actual
captures. This is a visual-contract update for the intentional layout change, not a timeout
workaround, tolerance increase or unrelated golden refresh.

- `npx playwright test --shard=2/5 --workers=2 --retries=0`: `165 passed (4.1m)` locally;
  the run passed the former stall point and both `glass-polish` contrast cases.
- `final-ux-closeout.spec.ts`: `3 passed (44.4s)` on the current application revision.
- Body measurement/history regression: `1 passed (3.1s)`.
- `glass-polish.spec.ts` contrast regression: `2 passed (3.1s)`.
- Critical mobile Progress screenshot contract after the oracle update: `4 passed (14.4s)`
  locally; the full local mobile run was `51 passed, 1 failed` on the unrelated existing
  WebKit active-workout screenshot baseline, while the CI artifact's other 48 mobile tests had
  passed before the four Progress mismatches.
- `npm run typecheck`, `npm run lint` (including Russian UI guard), `npm run build` and
  targeted Prettier check: passed.
- The evidence-only capture test is explicitly skipped unless `CAPTURE_ISSUE_873=1`.

The smoke job cap remains the workflow's 15 minutes; `playwright.config.ts` does not add a
global timeout. The remaining proof gate is the GitHub Actions run for the pushed current HEAD.
Physical iPhone, native TMA and VoiceOver remain `NOT_VERIFIED`.
