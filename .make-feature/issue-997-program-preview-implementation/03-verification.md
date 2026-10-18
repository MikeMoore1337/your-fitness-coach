# Verification

## Confirmed locally

- `npx prettier --check` for all changed frontend source and test files — passed.
- `npm test` — 155 test files and 940 tests passed.
- `npm run lint` — passed, including Russian user-facing UI and thick-lime guards.
- `npm run typecheck` — passed.
- `npm run build` — passed; Vite transformed 568 modules.
- `git diff --check` — passed.
- Isolated Playwright preview on port 4188 — Chromium and WebKit passed (2/2) after the final footer/content layout fix.
- Full `app.spec.ts` cross-browser run reached 65/68; the three failures were two hard-coded-port failures in an unrelated date test and a repeatable WebKit-only unrelated cardio form timeout. The date test passed in focused Chromium/WebKit retry with `PW_BASE_URL`; the #997 preview test passed in both browsers.
- Exact-head GitHub Actions for the follow-up commit is pending.

## Real browser AFTER package

- Synthetic fixture captures are generated under `.artifacts/runtime/tests/playwright/redesign-visual-issue-997/`.
- Matrix: Dark/Light at 320, 360, 393, 430 and 1440px; source card; own long-title program; legacy/incomplete program; trainer-assigned read-only program; stale-source notice; replacement confirmation.
- Each final generated PNG was visually inspected. No horizontal overflow was reported by the E2E assertions; the footer reserves its own space, the primary action is readable and full-width within the mobile action content box, and the 1440px sheet remains right-aligned.
- New exact-head CI artifact links will be recorded after the follow-up workflow completes.

## Ready for visual acceptance

- The follow-up implementation commit is not yet pushed. After exact-head CI is green, the PR remains Draft and the next gate is owner visual acceptance of the complete AFTER package.
- Keep release approval, merge and deploy pending until separately authorized.

## Boundaries

- Evidence is synthetic local browser/TMA-style fixture evidence only.
- Physical iPhone/Safari, native Telegram, VoiceOver, live production data/runtime and real-user behavior are not verified.
