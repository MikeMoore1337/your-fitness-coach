# #865 — «О показателях» на мобильной ширине

Это техническое evidence для проверки геометрии, а не owner visual approval.

На baseline с лимитом `164px` в Chromium на ширине `320px` подпись переносилась на
две строки: высота summary была `52px`. Исправление ограничено scoped-правилом
`frontend/src/styles/design-v2.css`: лимит для этого mobile-контрола повышен до
`172px`. Смысл, иконка, порядок блоков и desktop-композиция не менялись.

Проверка выполнена на mocked platform API, без production credentials: WebKit и
Chromium, светлая и тёмная тема, ширины `320`, `360`, `393`, `430px`. Скриншот —
реальный crop `.progress-hero`, сохранённый Playwright.

| Ширина | Тема | Chromium BEFORE | Chromium AFTER | WebKit BEFORE | WebKit AFTER |
| ---: | --- | --- | --- | --- | --- |
| 320 | light | [before](before/chromium-320-light.png) | [after](after/chromium-320-light.png) | [before](before/webkit-320-light.png) | [after](after/webkit-320-light.png) |
| 320 | dark | [before](before/chromium-320-dark.png) | [after](after/chromium-320-dark.png) | [before](before/webkit-320-dark.png) | [after](after/webkit-320-dark.png) |
| 360 | light | [before](before/chromium-360-light.png) | [after](after/chromium-360-light.png) | [before](before/webkit-360-light.png) | [after](after/webkit-360-light.png) |
| 360 | dark | [before](before/chromium-360-dark.png) | [after](after/chromium-360-dark.png) | [before](before/webkit-360-dark.png) | [after](after/webkit-360-dark.png) |
| 393 | light | [before](before/chromium-393-light.png) | [after](after/chromium-393-light.png) | [before](before/webkit-393-light.png) | [after](after/webkit-393-light.png) |
| 393 | dark | [before](before/chromium-393-dark.png) | [after](after/chromium-393-dark.png) | [before](before/webkit-393-dark.png) | [after](after/webkit-393-dark.png) |
| 430 | light | [before](before/chromium-430-light.png) | [after](after/chromium-430-light.png) | [before](before/webkit-430-light.png) | [after](after/webkit-430-light.png) |
| 430 | dark | [before](before/chromium-430-dark.png) | [after](after/chromium-430-dark.png) | [before](before/webkit-430-dark.png) | [after](after/webkit-430-dark.png) |

The same run also keeps `768/1280/1440px` reference crops in both directories.

## Evidence

- BEFORE UI baseline: local integration commit `ede84193`.
- AFTER UI/evidence commit: `f7a900a743a6ecbc71b97a954d3ed2e036ef8404`.
- Required Linux run `38223908839` failed only on the four `progress-390x844-{dark,light}.png`
  goldens for Chromium/WebKit. Diff inspection showed only the approved `164px → 172px`
  contextual-help width change and its downstream progress-layout shift; no threshold or
  unrelated snapshot was changed. The four CI `*-actual.png` files are preserved in the run
  artifact [playwright-mobile-regression-38223908839](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38223908839).
- Regression: `frontend/tests/e2e/progress-experience.spec.ts` checks one text
  line, a minimum `44px` touch target and no right-edge overflow at each required
  mobile width.
- Mobile Web/PWA-like and mocked TMA parity: `frontend/tests/e2e/tma-smoke.spec.ts`,
  Chromium and WebKit, `2 passed`.
- Owner visual status: `OWNER_865_VISUAL_APPROVAL=GRANTED` on 12.10.2026. The approval
  covers only the one-line «О показателях» correction; release, merge and deploy remain
  separate gates.
