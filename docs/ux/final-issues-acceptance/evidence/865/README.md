# #865 — «О показателях» на мобильной ширине

Это техническое evidence для проверки геометрии, а не owner visual approval.

На baseline с лимитом `164px` в Chromium на ширине `320px` подпись переносилась на
две строки: высота summary была `52px`. Исправление ограничено scoped-правилом
`frontend/src/styles/design-v2.css`: лимит для этого mobile-контрола повышен до
`172px`. Смысл, иконка, порядок блоков и desktop-композиция не менялись.

Проверка выполнена на mocked platform API, без production credentials: WebKit и
Chromium, светлая и тёмная тема, ширины `320`, `360`, `393`, `430px`. Скриншот —
реальный crop `.progress-hero`, сохранённый Playwright.

| Ширина | Тема  | Chromium BEFORE                         | Chromium AFTER                        | WebKit BEFORE                         | WebKit AFTER                        |
| -----: | ----- | --------------------------------------- | ------------------------------------- | ------------------------------------- | ----------------------------------- |
|    320 | light | [before](before/chromium-320-light.png) | [after](after/chromium-320-light.png) | [before](before/webkit-320-light.png) | [after](after/webkit-320-light.png) |
|    320 | dark  | [before](before/chromium-320-dark.png)  | [after](after/chromium-320-dark.png)  | [before](before/webkit-320-dark.png)  | [after](after/webkit-320-dark.png)  |
|    360 | light | [before](before/chromium-360-light.png) | [after](after/chromium-360-light.png) | [before](before/webkit-360-light.png) | [after](after/webkit-360-light.png) |
|    360 | dark  | [before](before/chromium-360-dark.png)  | [after](after/chromium-360-dark.png)  | [before](before/webkit-360-dark.png)  | [after](after/webkit-360-dark.png)  |
|    393 | light | [before](before/chromium-393-light.png) | [after](after/chromium-393-light.png) | [before](before/webkit-393-light.png) | [after](after/webkit-393-light.png) |
|    393 | dark  | [before](before/chromium-393-dark.png)  | [after](after/chromium-393-dark.png)  | [before](before/webkit-393-dark.png)  | [after](after/webkit-393-dark.png)  |
|    430 | light | [before](before/chromium-430-light.png) | [after](after/chromium-430-light.png) | [before](before/webkit-430-light.png) | [after](after/webkit-430-light.png) |
|    430 | dark  | [before](before/chromium-430-dark.png)  | [after](after/chromium-430-dark.png)  | [before](before/webkit-430-dark.png)  | [after](after/webkit-430-dark.png)  |

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

## Follow-up: раскрытые состояния и «Свой период»

Этот раздел относится к отдельному follow-up по #865 и не пересматривает уже принятую
коррекцию `164px → 172px`. На baseline `origin/master` раскрытие «О показателях» на
мобильной ширине раздувало auto-колонку CSS Grid до всей ширины: колонка заголовка
схлопывалась, а текст подсказки заходил на «Прогресс». В исправлении сохранена текущая
композиция: при раскрытии мобильная сетка получает фиксированную колонку подсказки
`172px`, заголовок занимает остаток, а раскрытый текст и форма периода остаются в
нормальном потоке; закрытое состояние сохраняет прежнюю геометрию.

В `ContextualHelp` также добавлен синхронный `aria-expanded` для native disclosure.
E2E проверяет клавиатурное открытие/закрытие, возврат фокуса, четыре комбинации состояний
(`closed-closed`, `help-open`, `custom-open`, `help-and-custom-open`), пересечение
DOM-боксов, выход за viewport и горизонтальный overflow. Форма «Свой период» проверяется
с заполненными датами и отдельными полями/действиями.

Матрица synthetic/mock API: Chromium и WebKit; Light и Dark; `320`, `360`, `390`, `393`,
`430`, `1280`, `1440`, `1920`, `2560px`. В каждом каталоге по 144 crop-скриншота
(`2 браузера × 9 ширин × 2 темы × 4 состояния`). Имена файлов имеют формат
`<browser>-<width>-<theme>-<state>.png`.

| Состояние                           | Chromium BEFORE                                                      | Chromium AFTER                                                      | WebKit BEFORE                                                      | WebKit AFTER                                                      |
| ----------------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------ | ----------------------------------------------------------------- |
| `help-open`, 320px, Light           | [снимок](expanded-before/chromium-320-light-help-open.png)           | [снимок](expanded-after/chromium-320-light-help-open.png)           | [снимок](expanded-before/webkit-320-light-help-open.png)           | [снимок](expanded-after/webkit-320-light-help-open.png)           |
| `help-and-custom-open`, 393px, Dark | [снимок](expanded-before/chromium-393-dark-help-and-custom-open.png) | [снимок](expanded-after/chromium-393-dark-help-and-custom-open.png) | [снимок](expanded-before/webkit-393-dark-help-and-custom-open.png) | [снимок](expanded-after/webkit-393-dark-help-and-custom-open.png) |
| `custom-open`, 1280px, Light        | [снимок](expanded-before/chromium-1280-light-custom-open.png)        | [снимок](expanded-after/chromium-1280-light-custom-open.png)        | [снимок](expanded-before/webkit-1280-light-custom-open.png)        | [снимок](expanded-after/webkit-1280-light-custom-open.png)        |
| `closed-closed`, 1440px, Dark       | [снимок](expanded-before/chromium-1440-dark-closed-closed.png)       | [снимок](expanded-after/chromium-1440-dark-closed-closed.png)       | [снимок](expanded-before/webkit-1440-dark-closed-closed.png)       | [снимок](expanded-after/webkit-1440-dark-closed-closed.png)       |

BEFORE снят в отдельном чистом worktree от `origin/master` (`2ed3b5d236ad08ade1b74a11c25d33c231d9057d`); в baseline временно добавлен только визуально нейтральный
`aria-expanded` mirror, чтобы прогнать тот же keyboard harness. API, данные и credentials
синтетические. AFTER относится к текущему Draft PR; merge, deploy и owner visual acceptance
не выполнены.

## Финальный пакет реализации PR #1013

После утверждения композиции снят отдельный финальный пакет реального AFTER:
[implementation-after-20261015](implementation-after-20261015/README.md). Он содержит 144
кадра Chromium/WebKit для обеих тем, всех требуемых ширин и четырёх сочетаний состояний,
включая заполненную форму «Свой период» и проверку полной видимости дат. Merge, deploy и
закрытие Issue по-прежнему не выполнялись; visual acceptance остаётся отдельным owner gate.
