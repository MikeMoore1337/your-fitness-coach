# Issue #998 — evidence package

Все captures сняты Chromium Playwright из локального YFC browser harness на synthetic fixture
данных. `before-*` — baseline `origin/master` `4c92832415d4eb994cf6b849a67074742f07ea50`;
`after-*` — финальный исходник implementation branch перед commit. Surface capture —
отрендеренная область `.active-workout`, не приватный пользовательский скриншот.

Ширины: 320, 360, 393, 430 и desktop 1440 CSS px. `after-*-open.png` содержит одновременно
раскрытые RIR и progression disclosures. Состояния и ссылки:

| Тема  |  Ширина | BEFORE                             | AFTER свернуто                   | AFTER раскрыто                       |
| ----- | ------: | ---------------------------------- | -------------------------------- | ------------------------------------ |
| Dark  |     320 | [before](before-dark-320.png)      | [after](after-dark-320.png)      | [open](after-dark-320-open.png)      |
| Dark  |     360 | [before](before-dark-360.png)      | [after](after-dark-360.png)      | [open](after-dark-360-open.png)      |
| Dark  |     393 | [before](before-dark-393.png)      | [after](after-dark-393.png)      | [open](after-dark-393-open.png)      |
| Dark  |     430 | [before](before-dark-430.png)      | [after](after-dark-430.png)      | [open](after-dark-430-open.png)      |
| Dark  | desktop | [before](before-dark-desktop.png)  | [after](after-dark-desktop.png)  | [open](after-dark-desktop-open.png)  |
| Light |     320 | [before](before-light-320.png)     | [after](after-light-320.png)     | [open](after-light-320-open.png)     |
| Light |     360 | [before](before-light-360.png)     | [after](after-light-360.png)     | [open](after-light-360-open.png)     |
| Light |     393 | [before](before-light-393.png)     | [after](after-light-393.png)     | [open](after-light-393-open.png)     |
| Light |     430 | [before](before-light-430.png)     | [after](after-light-430.png)     | [open](after-light-430-open.png)     |
| Light | desktop | [before](before-light-desktop.png) | [after](after-light-desktop.png) | [open](after-light-desktop-open.png) |

Browser proof: Chromium, `frontend/tests/e2e/issue-998-rir-guidance.spec.ts`, reduced motion,
fixed date `2026-08-20`, mocked platform API, no private data. WebKit responsive checks passed,
but screenshots are intentionally Chromium-only to keep one comparable visual baseline.

Physical iPhone/Safari, real Telegram Mini App runtime and VoiceOver remain `NOT_VERIFIED`.
