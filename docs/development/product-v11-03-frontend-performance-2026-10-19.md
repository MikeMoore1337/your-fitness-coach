# Product V11-03 - frontend performance: implementation evidence

Issue: [#818](https://github.com/MikeMoore1337/your-fitness-coach/issues/818) ·
PR: [#1126](https://github.com/MikeMoore1337/your-fitness-coach/pull/1126) ·
2026-10-19.

## Revisions and measurement boundaries

- V11-00 historical build: `9b5a24b49408fee63339dbdc93af57767fdc977e` (2026-10-18).
- Verified base of #818 branch: `42a75a5f1fbea025204c5d1e1a928bfd6581b1a1`.
- Between these refs: 42 commits, including frontend/API client changes. The historical figures are **not a matched before-state** for #818.
- Desktop Commander hosts were offline during this work. A local Vite bundle/profile was **not** measured. Tests performed by GitHub Actions must be associated with the final exact PR HEAD.
- Browser lab, real mobile/TMA, CrUX/RUM, React Profiler and navigation timings: `NO_DATA` until captured.

Historical #815 observations, **not** proof of #818 impact:

| Metric | #815 historical | #818 base BEFORE | #818 final AFTER |
| --- | ---: | --- | --- |
| Entry JS raw | 309,087 B | NO_DATA | NO_DATA |
| Entry JS gzip | 96,775 B | NO_DATA | NO_DATA |
| Entry JS gzip budget | 96,000 B | 96,000 B | 96,000 B |
| Entry CSS gzip | 13,216 B | NO_DATA | NO_DATA |
| Core route/nav latency | NO_DATA | NO_DATA | NO_DATA |
| React render cost | NO_DATA | NO_DATA | NO_DATA |
| Repeat API requests | NO_DATA | NO_DATA | NO_DATA |
| LCP, CLS, INP - field | NO_DATA | NO_DATA | NO_DATA |

## Measured intermediate build (not the final result)

GitHub Actions run [39289139494](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39289139494), commit `087531a8`, `frontend-performance` output:

- Entry JS: **309,019 B raw / 96,761 B gzip**; budget 96,000 B -> **FAIL by 761 B**.
- Entry CSS: 64,478 B raw / 13,216 B gzip -> PASS.
- Public assets: 31 files / 646,496 B; largest 100,570 B -> PASS.
- This prompted a second code-splitting change. No before/after claim is made based on the historical #815 data.

## Source-confirmed targets and bounded changes

1. `main.tsx` imported demo session code eagerly although it only needs `clearAllDemoSessions()` for Telegram `/demo` at startup. Moved this module into an awaited dynamic import inside that narrow branch, keeping credential/session cleanup **before** render.
2. `ExerciseGuideVideo` disconnected `IntersectionObserver` after the first intersection. For looping HD videos, this removed the ability to pause playback when scrolled offscreen. Keep observing to pause out of view, resume in view, and pause/resume with document visibility. Once loaded, the source URL remains mounted: do not discard frames, replace a video with a static image, reduce bitrate/resolution or change the approved animation.
3. Move the existing authenticated wrapper, coach-vs-personal navigation decision and trainer-intent routing into an auth-only lazy module. Keep their logic unchanged; `AuthProvider` and `OnboardingGate` are lazily loaded for non-public routes. The intermediate strict budget failure above justifies a targeted bootstrap split, but navigation latency is not claimed to improve without timings.
4. Preserve the existing architecture, route-level lazy components, font `font-display: swap`, video poster/GIF fallback, and asset rules. No justified source/runtime evidence for global Query-cache tuning, new memoization, router refactor or media re-encoding.

## Regression contract

- `npm ci && npm run build && npm run perf:check` on the same production-like Node/runtime profile for both revisions. The strict `entryJsGzip: 96_000` limit remains unchanged.
- `npm run typecheck && npm run lint && npm run format:check && npm test`.
- `npx playwright test performance-hardening.spec.ts --project=chromium` with existing isolated fixtures.
- Existing `frontend-checks`, `frontend-unit`, frontend smoke and Chromium+WebKit mobile regression on **exact PR HEAD**.
- E2E checks Telegram `/demo` clears session state before the `/app` navigation; unit tests check video remains lazy, paused offscreen, resumes without a second source load and pauses when hidden.
- Where altered screens apply, preserve 320/360/393/430/1440 px and light/dark appearances. No design or media assets changed.

## Release status

`NEEDS_WORK` until the latest CI run is green, the current-master BEFORE and final AFTER are comparable, and justified runtime/field limitations are recorded. No merge or production deploy is authorized under #818 without separate owner approval.
