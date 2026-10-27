# Issue #996 — реальное AFTER Variant 02

Этот пакет предназначен для визуальной приёмки реализации утверждённого Variant 02
(`3a8cd073d8c3b0570d640190099be7c0209cbb0b9`) в PR #1095.

## Условия capture

- implementation SHA: `ce2e8ba8ae40bb0785d2c6a703d3389bfc67d7e6`;
- дата: 2026-10-18, Europe/Moscow;
- браузер PNG: Playwright Chromium, проект `chromium`;
- viewport: `320×844`, `360×844`, `393×844`, `430×844`, `1440×844`;
- темы: Dark и Light; `prefers-reduced-motion: reduce`;
- источник: локальный production build, открытый через Vite preview;
- данные: синтетический Playwright fixture без production credentials и персональных данных;
- media: существующий каталог YFC, thumbnail `dumbbell-bench-press-0289-SpYC0Kp.jpg`
  отдается из `backend/assets/exercise-guides/gymvisual/`; для остальных candidates
  проверен существующий fallback `Нет фото`;
- capture command: `YFC_ISSUE_996_AFTER_DIR=docs/ux/issue-996-acceptance/after`
  - `npm run e2e:ci -- --config=playwright.cross-browser.config.ts --project=chromium`
  - `--workers=1 --grep "#996 real AFTER"`;
- capture result: 20/20 passed (10 обязательных viewport captures + 10 state captures).

## Обязательные viewport captures

| Theme | 320                                    | 360                                    | 393                                    | 430                                    | 1440                                    |
| ----- | -------------------------------------- | -------------------------------------- | -------------------------------------- | -------------------------------------- | --------------------------------------- |
| Dark  | [PNG](./issue-996-after-dark-320.png)  | [PNG](./issue-996-after-dark-360.png)  | [PNG](./issue-996-after-dark-393.png)  | [PNG](./issue-996-after-dark-430.png)  | [PNG](./issue-996-after-dark-1440.png)  |
| Light | [PNG](./issue-996-after-light-320.png) | [PNG](./issue-996-after-light-360.png) | [PNG](./issue-996-after-light-393.png) | [PNG](./issue-996-after-light-430.png) | [PNG](./issue-996-after-light-1440.png) |

## Состояния для приёмки

| State                                       | Dark                                                   | Light                                                   |
| ------------------------------------------- | ------------------------------------------------------ | ------------------------------------------------------- |
| Preview с отдельным Apply ниже ряда выбора  | [PNG](./issue-996-after-preview-dark-393.png)          | [PNG](./issue-996-after-preview-light-393.png)          |
| Ошибка preview                              | [PNG](./issue-996-after-error-dark-393.png)            | [PNG](./issue-996-after-error-light-393.png)            |
| Offline                                     | [PNG](./issue-996-after-offline-dark-393.png)          | [PNG](./issue-996-after-offline-light-393.png)          |
| Conflict 409 на Apply                       | [PNG](./issue-996-after-conflict-dark-393.png)         | [PNG](./issue-996-after-conflict-light-393.png)         |
| Modeled keyboard / сохранение фокуса поиска | [PNG](./issue-996-after-keyboard-modeled-dark-393.png) | [PNG](./issue-996-after-keyboard-modeled-light-393.png) |

WebKit прогнал те же 31 сценарий `#996` на тех же viewport/theme combinations: 31/31
passed; PNG выше оставлены единым Chromium capture package для сопоставимости.

## Границы доказательства

Это synthetic browser evidence для визуальной приёмки. Оно не заменяет физический iPhone,
нативный Telegram Mini App, VoiceOver, реальную OS keyboard и production runtime.
Owner visual acceptance, merge и production deploy остаются отдельными pending gates.
