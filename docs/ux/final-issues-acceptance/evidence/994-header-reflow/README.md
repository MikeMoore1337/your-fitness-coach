# #994 — единый AFTER: перенос мобильной шапки

**Код:** [`b50cadd3`](https://github.com/MikeMoore1337/your-fitness-coach/commit/b50cadd3efca24677b88067eac65305ee3680e60). **База:** [`17c5f299`](https://github.com/MikeMoore1337/your-fitness-coach/commit/17c5f29921f379d1f5229eede40c88d5183ddcf9). Снимки выполнены на коде указанного коммита; последующий коммит добавляет только этот пакет. Данные синтетические.

[Согласованный пакет дизайна](https://github.com/MikeMoore1337/your-fitness-coach/blob/8aaeb5d67f3aa111382b132a88f4d520a8e345d1/docs/ux-proposals/issue-994-review/README.md): владелец принял показанный вариант в чате. Это AFTER фактической реализации, не повторный снимок макета. Визуальная приёмка AFTER и разрешение на выпуск — отдельные решения.

## Что изменилось

Общее правило перенесено из стилей Today в общий файл шапки. При ширине viewport не более 240 CSS px кнопка профиля переносится под логотип; на обычной мобильной ширине шапка сохраняется. Общий компонент работает также при прямом открытии Coach OS. Логика навигации, Dock 4+1, данные и бизнес-действия не менялись.

Исходники: [общий стиль](https://github.com/MikeMoore1337/your-fitness-coach/blob/b50cadd3efca24677b88067eac65305ee3680e60/frontend/src/styles/react.css), [прежнее место правила](https://github.com/MikeMoore1337/your-fitness-coach/blob/b50cadd3efca24677b88067eac65305ee3680e60/frontend/src/styles/ux-ia-redesign.css), [регрессионный тест](https://github.com/MikeMoore1337/your-fitness-coach/blob/b50cadd3efca24677b88067eac65305ee3680e60/frontend/tests/e2e/header-reflow-994.spec.ts).

## Настоящий Chromium zoom 200%

Исходный viewport 393×852, `chrome.tabs.getZoom() = 2`, результирующий viewport около 196×426 CSS px. Снимки сделаны после загрузки раздела. Для сравнения показан исходный реальный вид до реализации; полный набор исходных и предложенных вариантов — в утверждённом пакете.

| Экран | BEFORE Light | AFTER Light | BEFORE Dark | AFTER Dark |
|---|---|---|---|---|
| Today | уже переносился | [после](screens/chromium-zoom200-light-today.png) | уже переносился | [после](screens/chromium-zoom200-dark-today.png) |
| Plan | [до](https://github.com/MikeMoore1337/your-fitness-coach/blob/8aaeb5d67f3aa111382b132a88f4d520a8e345d1/docs/ux-proposals/issue-994-review/screens/header-programs-light-before.png) | [после](screens/chromium-zoom200-light-programs.png) | [до](https://github.com/MikeMoore1337/your-fitness-coach/blob/8aaeb5d67f3aa111382b132a88f4d520a8e345d1/docs/ux-proposals/issue-994-review/screens/header-programs-dark-before.png) | [после](screens/chromium-zoom200-dark-programs.png) |
| Nutrition | [до](https://github.com/MikeMoore1337/your-fitness-coach/blob/8aaeb5d67f3aa111382b132a88f4d520a8e345d1/docs/ux-proposals/issue-994-review/screens/header-nutrition-light-before.png) | [после](screens/chromium-zoom200-light-nutrition.png) | [до](https://github.com/MikeMoore1337/your-fitness-coach/blob/8aaeb5d67f3aa111382b132a88f4d520a8e345d1/docs/ux-proposals/issue-994-review/screens/header-nutrition-dark-before.png) | [после](screens/chromium-zoom200-dark-nutrition.png) |
| Progress | [до](https://github.com/MikeMoore1337/your-fitness-coach/blob/8aaeb5d67f3aa111382b132a88f4d520a8e345d1/docs/ux-proposals/issue-994-review/screens/header-progress-light-before.png) | [после](screens/chromium-zoom200-light-progress.png) | [до](https://github.com/MikeMoore1337/your-fitness-coach/blob/8aaeb5d67f3aa111382b132a88f4d520a8e345d1/docs/ux-proposals/issue-994-review/screens/header-progress-dark-before.png) | [после](screens/chromium-zoom200-dark-progress.png) |
| Profile | [до](https://github.com/MikeMoore1337/your-fitness-coach/blob/8aaeb5d67f3aa111382b132a88f4d520a8e345d1/docs/ux-proposals/issue-994-review/screens/header-profile-light-before.png) | [после](screens/chromium-zoom200-light-profile.png) | [до](https://github.com/MikeMoore1337/your-fitness-coach/blob/8aaeb5d67f3aa111382b132a88f4d520a8e345d1/docs/ux-proposals/issue-994-review/screens/header-profile-dark-before.png) | [после](screens/chromium-zoom200-dark-profile.png) |
| Coach OS | [до](https://github.com/MikeMoore1337/your-fitness-coach/blob/8aaeb5d67f3aa111382b132a88f4d520a8e345d1/docs/ux-proposals/issue-994-review/screens/header-coach-light-before.png) | [после](screens/chromium-zoom200-light-coach.png) | [до](https://github.com/MikeMoore1337/your-fitness-coach/blob/8aaeb5d67f3aa111382b132a88f4d520a8e345d1/docs/ux-proposals/issue-994-review/screens/header-coach-dark-before.png) | [после](screens/chromium-zoom200-dark-coach.png) |

## Проверка двух браузеров: обычная и сверхузкая ширина

Viewport 393×852 и 196×852 CSS px; второй вариант — изменение viewport, а не настоящий zoom WebKit.

| Экран | Chromium 196 Light | Chromium 196 Dark | WebKit 196 Light | WebKit 196 Dark | Chromium 393 Light | Chromium 393 Dark | WebKit 393 Light | WebKit 393 Dark |
|---|---|---|---|---|---|---|---|---|
| Today | [chromium 196 light](screens/chromium-196-light-today.png) | [chromium 196 dark](screens/chromium-196-dark-today.png) | [webkit 196 light](screens/webkit-196-light-today.png) | [webkit 196 dark](screens/webkit-196-dark-today.png) | [chromium 393 light](screens/chromium-393-light-today.png) | [chromium 393 dark](screens/chromium-393-dark-today.png) | [webkit 393 light](screens/webkit-393-light-today.png) | [webkit 393 dark](screens/webkit-393-dark-today.png) |
| Plan | [chromium 196 light](screens/chromium-196-light-programs.png) | [chromium 196 dark](screens/chromium-196-dark-programs.png) | [webkit 196 light](screens/webkit-196-light-programs.png) | [webkit 196 dark](screens/webkit-196-dark-programs.png) | [chromium 393 light](screens/chromium-393-light-programs.png) | [chromium 393 dark](screens/chromium-393-dark-programs.png) | [webkit 393 light](screens/webkit-393-light-programs.png) | [webkit 393 dark](screens/webkit-393-dark-programs.png) |
| Nutrition | [chromium 196 light](screens/chromium-196-light-nutrition.png) | [chromium 196 dark](screens/chromium-196-dark-nutrition.png) | [webkit 196 light](screens/webkit-196-light-nutrition.png) | [webkit 196 dark](screens/webkit-196-dark-nutrition.png) | [chromium 393 light](screens/chromium-393-light-nutrition.png) | [chromium 393 dark](screens/chromium-393-dark-nutrition.png) | [webkit 393 light](screens/webkit-393-light-nutrition.png) | [webkit 393 dark](screens/webkit-393-dark-nutrition.png) |
| Progress | [chromium 196 light](screens/chromium-196-light-progress.png) | [chromium 196 dark](screens/chromium-196-dark-progress.png) | [webkit 196 light](screens/webkit-196-light-progress.png) | [webkit 196 dark](screens/webkit-196-dark-progress.png) | [chromium 393 light](screens/chromium-393-light-progress.png) | [chromium 393 dark](screens/chromium-393-dark-progress.png) | [webkit 393 light](screens/webkit-393-light-progress.png) | [webkit 393 dark](screens/webkit-393-dark-progress.png) |
| Profile | [chromium 196 light](screens/chromium-196-light-profile.png) | [chromium 196 dark](screens/chromium-196-dark-profile.png) | [webkit 196 light](screens/webkit-196-light-profile.png) | [webkit 196 dark](screens/webkit-196-dark-profile.png) | [chromium 393 light](screens/chromium-393-light-profile.png) | [chromium 393 dark](screens/chromium-393-dark-profile.png) | [webkit 393 light](screens/webkit-393-light-profile.png) | [webkit 393 dark](screens/webkit-393-dark-profile.png) |
| Coach OS | [chromium 196 light](screens/chromium-196-light-coach.png) | [chromium 196 dark](screens/chromium-196-dark-coach.png) | [webkit 196 light](screens/webkit-196-light-coach.png) | [webkit 196 dark](screens/webkit-196-dark-coach.png) | [chromium 393 light](screens/chromium-393-light-coach.png) | [chromium 393 dark](screens/chromium-393-dark-coach.png) | [webkit 393 light](screens/webkit-393-light-coach.png) | [webkit 393 dark](screens/webkit-393-dark-coach.png) |

## Demo, эмуляция TMA и контроль desktop

Demo: логотип в мобильной шапке по существующему контракту скрыт; проверена кнопка сценариев. Эмуляция TMA не подтверждает работу настоящего Telegram или системной клавиатуры.

| Контекст | Chromium Light | Chromium Dark | WebKit Light | WebKit Dark |
|---|---|---|---|---|
| Demo 196 | [chromium light](screens/chromium-196-light-demo.png) | [chromium dark](screens/chromium-196-dark-demo.png) | [webkit light](screens/webkit-196-light-demo.png) | [webkit dark](screens/webkit-196-dark-demo.png) |
| Demo 393 | [chromium light](screens/chromium-393-light-demo.png) | [chromium dark](screens/chromium-393-dark-demo.png) | [webkit light](screens/webkit-393-light-demo.png) | [webkit dark](screens/webkit-393-dark-demo.png) |
| TMA, эмуляция 196 | [chromium light](screens/chromium-196-light-tma.png) | [chromium dark](screens/chromium-196-dark-tma.png) | [webkit light](screens/webkit-196-light-tma.png) | [webkit dark](screens/webkit-196-dark-tma.png) |
| TMA, эмуляция 393 | [chromium light](screens/chromium-393-light-tma.png) | [chromium dark](screens/chromium-393-dark-tma.png) | [webkit light](screens/webkit-393-light-tma.png) | [webkit dark](screens/webkit-393-dark-tma.png) |
| Desktop Progress 1280 | [chromium light](screens/chromium-1280-light-progress.png) | [chromium dark](screens/chromium-1280-dark-progress.png) | [webkit light](screens/webkit-1280-light-progress.png) | [webkit dark](screens/webkit-1280-dark-progress.png) |
| Desktop Coach OS 1280 | [chromium light](screens/chromium-1280-light-coach.png) | [chromium dark](screens/chromium-1280-dark-coach.png) | [webkit light](screens/webkit-1280-light-coach.png) | [webkit dark](screens/webkit-1280-dark-coach.png) |

## Проверки и ограничения

- До исправления регрессионный тест показал пересечение строк логотипа и кнопки на 196 px. После исправления: Playwright Chromium/WebKit **12 passed, 2 skipped**; пропуски — настоящий browser zoom в WebKit. Включены шесть маршрутов, две темы, обычная ширина, геометрия, профиль и эмуляция safe-area.
- Demo — **4/4**; дополнительные снимки TMA — **4/4**; desktop — **4/4**. Сравнение снимков шапки с базой: **72/72** совпадения на 320/393/430 px, двух темах, двух движках и шести маршрутах.
- Vitest **1513 passed**, TypeScript, сборка, ESLint, проверка форматирования изменённых файлов и `perf:check` прошли локально. CI относится к итоговому SHA PR и проверяется отдельно.
- При настоящем zoom 200% подписи отдельной навигации Coach OS сокращаются; это наблюдается и на исходном dev ([BEFORE](https://github.com/MikeMoore1337/your-fitness-coach/blob/8aaeb5d67f3aa111382b132a88f4d520a8e345d1/docs/ux-proposals/issue-994-review/screens/header-coach-dark-before.png)). Навигация Coach OS не менялась и не входит в данное исправление.
- Физические iPhone, настоящий Safari/Telegram, VoiceOver, системная клавиатура и production — **NOT_VERIFIED**. Эмуляция TMA и WebKit не заменяет физическое устройство.

Примите или укажите замечания к этому единому AFTER. Визуальная приёмка не разрешает merge, deploy или закрытие #994.
