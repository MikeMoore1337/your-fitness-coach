# Verification

## Confirmed locally

- `npx prettier --check` for all changed frontend source and test files — passed.
- `npm test -- --run` — 155 test files and 922 tests passed.
- `npm run lint` — passed, including Russian user-facing UI and thick-lime guards.
- `npm run typecheck` — passed.
- `npm run build` — passed; Vite transformed 568 modules.
- `git diff --check` — passed.
- Isolated Playwright preview on port 4174 — Chromium and WebKit passed (2/2).

## Real browser AFTER package

- Synthetic fixture captures are generated under `.artifacts/runtime/tests/playwright/redesign-visual-issue-997/`.
- Matrix: Dark/Light at 320, 360, 393, 430 and 1440px; source card; own long-title program; legacy/incomplete program; trainer-assigned read-only program; stale-source notice; replacement confirmation.
- Each generated PNG was visually inspected. No horizontal overflow was reported by the E2E assertions; the mobile action surface is opaque and the 1440px sheet remains right-aligned.

## Pending publication

- Commit the final local diff and push it to the existing PR #1096 branch.
- Verify exact-head GitHub aggregate `checks` and attach the final CI run/artifact link to the existing PR.
- Keep owner visual acceptance, release approval, merge and deploy pending.

## Boundaries

- Evidence is synthetic local browser/TMA-style fixture evidence only.
- Physical iPhone/Safari, native Telegram, VoiceOver, live production data/runtime and real-user behavior are not verified.
