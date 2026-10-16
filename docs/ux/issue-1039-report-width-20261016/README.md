# #1039 — Progress report: wider mobile canvas (Dark/Light)

**Scope:** follow-up to owner feedback on the existing 393px [Light](https://github.com/MikeMoore1337/your-fitness-coach/blob/0aa43d49903d72c20b7d0111d5a56ca69e29daa3/docs/ux/final-issues-acceptance/evidence/1002-lime-edge-fix-20261016/report-393-light-after.png) and [Dark](https://github.com/MikeMoore1337/your-fitness-coach/blob/0aa43d49903d72c20b7d0111d5a56ca69e29daa3/docs/ux/final-issues-acceptance/evidence/1002-lime-edge-fix-20261016/report-393-dark-after.png) actual report screenshots. Existing **#1002 approved edge removal is already in production** and remains unchanged. This is a new standalone visual change, **not #873 Progress Details**.

## Screenshot comparison

| Theme | BEFORE (production #1002) | AFTER (real Vite UI, mocked API fixture) |
|---|---|---|
| Dark | [393px original](https://github.com/MikeMoore1337/your-fitness-coach/blob/0aa43d49903d72c20b7d0111d5a56ca69e29daa3/docs/ux/final-issues-acceptance/evidence/1002-lime-edge-fix-20261016/report-393-dark-after.png) | [393px AFTER](./after-393-dark.webp) |
| Light | [393px original](https://github.com/MikeMoore1337/your-fitness-coach/blob/0aa43d49903d72c20b7d0111d5a56ca69e29daa3/docs/ux/final-issues-acceptance/evidence/1002-lime-edge-fix-20261016/report-393-light-after.png) | [393px AFTER](./after-393-light.webp) |

These **AFTER screenshots are captured from actual `ProgressReportPage` in a local frontend production build via Playwright**, with deterministic synthetic fixture data. The captured PNGs were converted to **pixel-identical lossless WebP** to satisfy the repository's 500 KB asset-size gate. They are **not** hand-drawn mockups and **not** direct snapshots from the production domain.

## Implementation

Only under `@media screen and (max-width: 680px)` in `frontend/src/styles/design-v2.css`:
- outer report page gutter: `max(12px, safe-area)` → `max(8px, safe-area)`
- inner report document horizontal padding: `16px` → `8px`
- vertical padding remains `16px`, typographic scale and other selectors remain unchanged.
- On no-notch 393px viewport this frees approximately **24 additional horizontal content pixels**, across tables, stats, exercise cards, charts, summary and disclaimer sections. Safe-area inset constraints stay enforced.
- Print `@page A4`, printable margins, underlying data calculations, API, PDF streaming and selected report exercises remain unchanged.
- Do **not** restore thick lime-edge rules A-01…A-06 removed in #1002.

## Verification

- Targeted mobile geometry regression test in existing `progress-report.spec.ts`: mobile viewports **320, 360, 393, 430 px**, Dark and Light; report content width bounded to safe space, **no horizontal document overflow**, actual 393px screenshots.
- Existing progress-report E2E regression validates long names, PDF/print, nutrition table, confidence status, progress data, external load and sample report states.
- Full required GitHub CI and cross-browser status must be checked on exact PR HEAD.

## Gate

This is **a new owner visual change** in an already shipped report. The preceding approval of #1002 only covers thick lime edge removal. **Do not merge or deploy this Draft PR without separate owner AFTER visual acceptance and release authorization.** Physical iPhone/real Telegram TMA, native VoiceOver and physical 200% zoom are not verified by local Playwright.
