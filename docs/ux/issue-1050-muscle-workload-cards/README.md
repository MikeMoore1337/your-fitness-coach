# Issue #1050 — карточки нагрузки по мышечным группам

Synthetic BEFORE/AFTER evidence for [Issue #1050](https://github.com/MikeMoore1337/your-fitness-coach/issues/1050).

- Branch: `codex/1050-muscle-workload-cards`
- Base: `origin/master` at `396bae69`
- Implementation and screenshots commit: [`d04e06ea`](https://github.com/MikeMoore1337/your-fitness-coach/commit/d04e06ea55652a3c56b4067600b16a0c4b161295)
- Fixture: three synthetic groups — comparable periods, no comparison, and unchanged values; one name is intentionally long.
- Evidence is browser/mock evidence only. It does not prove physical iPhone/Safari, native Telegram, VoiceOver or production behavior.

## BEFORE

- [393 px, Light](https://github.com/MikeMoore1337/your-fitness-coach/blob/d04e06ea55652a3c56b4067600b16a0c4b161295/docs/ux/issue-1050-muscle-workload-cards/evidence/before-mobile-393-light.png)
- [393 px, Dark](https://github.com/MikeMoore1337/your-fitness-coach/blob/d04e06ea55652a3c56b4067600b16a0c4b161295/docs/ux/issue-1050-muscle-workload-cards/evidence/before-mobile-393-dark.png)
- [1280 px, Light](https://github.com/MikeMoore1337/your-fitness-coach/blob/d04e06ea55652a3c56b4067600b16a0c4b161295/docs/ux/issue-1050-muscle-workload-cards/evidence/before-desktop-1280-light.png)
- [1280 px, Dark](https://github.com/MikeMoore1337/your-fitness-coach/blob/d04e06ea55652a3c56b4067600b16a0c4b161295/docs/ux/issue-1050-muscle-workload-cards/evidence/before-desktop-1280-dark.png)
- [393 px, Light, open](https://github.com/MikeMoore1337/your-fitness-coach/blob/d04e06ea55652a3c56b4067600b16a0c4b161295/docs/ux/issue-1050-muscle-workload-cards/evidence/before-mobile-393-light-open.png)

## AFTER

- [393 px, Light](https://github.com/MikeMoore1337/your-fitness-coach/blob/d04e06ea55652a3c56b4067600b16a0c4b161295/docs/ux/issue-1050-muscle-workload-cards/evidence/after-mobile-393-light.png)
- [393 px, Dark](https://github.com/MikeMoore1337/your-fitness-coach/blob/d04e06ea55652a3c56b4067600b16a0c4b161295/docs/ux/issue-1050-muscle-workload-cards/evidence/after-mobile-393-dark.png)
- [1280 px, Light](https://github.com/MikeMoore1337/your-fitness-coach/blob/d04e06ea55652a3c56b4067600b16a0c4b161295/docs/ux/issue-1050-muscle-workload-cards/evidence/after-desktop-1280-light.png)
- [1280 px, Dark](https://github.com/MikeMoore1337/your-fitness-coach/blob/d04e06ea55652a3c56b4067600b16a0c4b161295/docs/ux/issue-1050-muscle-workload-cards/evidence/after-desktop-1280-dark.png)
- [393 px, Light, open](https://github.com/MikeMoore1337/your-fitness-coach/blob/d04e06ea55652a3c56b4067600b16a0c4b161295/docs/ux/issue-1050-muscle-workload-cards/evidence/after-mobile-393-light-open.png)

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
