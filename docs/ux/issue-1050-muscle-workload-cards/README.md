# Issue #1050 — карточки нагрузки по мышечным группам

Synthetic BEFORE/AFTER evidence for [Issue #1050](https://github.com/MikeMoore1337/your-fitness-coach/issues/1050).

- Branch: `codex/1050-muscle-workload-cards`
- Base: updated to include production #1047, #1048 and #1049 from current `origin/master`
- Implementation and screenshots commit: [`d04e06ea`](https://github.com/MikeMoore1337/your-fitness-coach/commit/d04e06ea55652a3c56b4067600b16a0c4b161295)
- Fixture: three synthetic groups — comparable periods, no comparison, and unchanged values; one name is intentionally long.
- Evidence is browser/mock evidence only. It does not prove physical iPhone/Safari, native Telegram, VoiceOver or production behavior.

## BEFORE

- [393 px, Light](evidence/before-mobile-393-light.png)
- [393 px, Dark](evidence/before-mobile-393-dark.png)
- [1280 px, Light](evidence/before-desktop-1280-light.png)
- [1280 px, Dark](evidence/before-desktop-1280-dark.png)
- [393 px, Light, open](evidence/before-mobile-393-light-open.png)

## AFTER

- [393 px, Light](evidence/after-mobile-393-light.png)
- [393 px, Dark](evidence/after-mobile-393-dark.png)
- [1280 px, Light](evidence/after-desktop-1280-light.png)
- [1280 px, Dark](evidence/after-desktop-1280-dark.png)
- [393 px, Light, open](evidence/after-mobile-393-light-open.png)


## Integration and contrast regression

- Resolved the overlapping Progress E2E tests with #1049 while retaining both suites.
- Corrected unreadable group and section headings in mobile Dark: headings explicitly use the same ar(--text) token as the readable numeric results.
- Added computed-color checks across 320/360/393/430/1280 px, Light/Dark in Chromium and WebKit.
- AFTER screenshots were regenerated from the integrated worktree with the contrast fix. All screenshot links are relative so they refer to the version being reviewed.

## Проверки

- `npm run typecheck` — passed.
- `npm run lint` — passed, including Russian UI-copy guard.
- Prettier for changed files and the shared frontend format step — passed.
- `vite build` — passed.
- Targeted Vitest — 11/11 passed.
- Full Vitest parallel run — 884/889 passed; five unrelated existing page suites reached the 5-second timeout. Sequential rerun of those five files — 64/64 passed.
- Targeted Playwright Chromium — passed for 320/360/393/430/1280 px, Light/Dark, keyboard disclosure, overflow and dock geometry.
- Targeted Playwright WebKit — passed.
- Shared UI audit — 3/3 passed on a fresh preview server.
- No production environment keys or contracts changed: `env change required: no`.

Visual acceptance is pending. Merge and deploy were not performed.
