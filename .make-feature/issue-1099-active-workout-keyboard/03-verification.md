# Verification

## Confirmed locally

- Baseline reproduction: origin/master synthetic Chromium run observed `scrollY` delta 105 px.
- #1099 focused regression: Chromium passed; WebKit passed.
- #1001 keyboard matrix: Chromium 7/8 in the first matrix run; the 320 px Light reload/setup case
  timed out once and passed on an isolated retry. WebKit 8/8 passed.
- Frontend typecheck: `npm run typecheck` passed.
- Frontend lint: `npm run lint` passed, including Russian UI and thick-lime guards.
- Changed-file Prettier check passed.
- Vitest: 154 files, 917 tests passed.
- Frontend build: `npm run build` passed.
- `git diff --check` passed.

## Final candidate follow-up

- After CI exposed the first-focus helper regression, the final candidate keeps that action and
  its layout space until both fields are filled; the focused prefill smoke passed in Chromium and
  WebKit.
- Final candidate #1099 recordings were regenerated after that correction; Chromium and WebKit
  focused scroll-stability tests passed.
- The earlier CI run `39119430278` correctly caught the intermediate candidate; it is not treated as
  a green final result. Final CI run `39120646539` passed the aggregate `checks` gate on the pushed
  candidate.

## Evidence

- `docs/ux/final-issues-acceptance/evidence/1099-active-workout-keyboard-20261018/README.md`
- BEFORE: `before-origin-master-chromium.webm`.
- AFTER: `after-fixed-chromium.webm`, `after-fixed-webkit.webm`.

## Boundaries

Synthetic browser viewport evidence is not physical iPhone Safari, native Telegram Mini App,
VoiceOver or production proof. Draft PR, owner visual acceptance, merge, release and production
smoke remain pending.
