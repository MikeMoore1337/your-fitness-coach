# Issue #1051 — карточки разделов «Питание»

Синтетическое BEFORE/AFTER-доказательство для Draft PR, связанного с Issue #1051.

## Данные и воспроизводимость

- BEFORE снят с `origin/master` на SHA `396bae69530d6d21c2de89b11daa2d48c3f824d5`.
- AFTER снят из этого worktree после локального изменения `NutritionReport`.
- Использованы только существующие Playwright-фикстуры `long` и `no-data`: даты 2030 года,
  демо-значения КБЖУ и безопасные синтетические данные.
- Capture-браузер: Chromium, Playwright 1.62.1. Open-state снимки сняты без фокуса на
  заголовке, чтобы отдельно отобразить обычное визуальное состояние карточки.

## Матрица снимков

| Состояние                           |        Viewport | BEFORE                                                | AFTER                                                |
| ----------------------------------- | --------------: | ----------------------------------------------------- | ---------------------------------------------------- |
| Заполненный период, секции закрыты  |  393×932, Light | [PNG](before/mobile-393-light-closed.png)             | [PNG](after/mobile-393-light-closed.png)             |
| История целей открыта               |  393×932, Light | [PNG](before/mobile-393-light-history-open.png)       | [PNG](after/mobile-393-light-history-open.png)       |
| Заполненный период, секции закрыты  |   393×932, Dark | [PNG](before/mobile-393-dark-closed.png)              | [PNG](after/mobile-393-dark-closed.png)              |
| Заполненный период, секции закрыты  |  1440×900, Dark | [PNG](before/desktop-1440-dark-closed.png)            | [PNG](after/desktop-1440-dark-closed.png)            |
| История целей открыта               |  1440×900, Dark | [PNG](before/desktop-1440-dark-history-open.png)      | [PNG](after/desktop-1440-dark-history-open.png)      |
| Заполненный период, секции закрыты  | 1440×900, Light | [PNG](before/desktop-1440-light-closed.png)           | [PNG](after/desktop-1440-light-closed.png)           |
| Период без записей, история открыта |  430×932, Light | [PNG](before/mobile-430-light-empty-history-open.png) | [PNG](after/mobile-430-light-empty-history-open.png) |

Дополнительная проверка в Playwright покрывает ширины 320/360/393/430 px, desktop,
клавиатурное раскрытие, отсутствие вложенных рамок, смену периода, Dark/Light и
Chromium/WebKit. Снимки являются браузерным synthetic/mock evidence и не заменяют
проверку на физическом iPhone/Safari, в Telegram, VoiceOver или production.
