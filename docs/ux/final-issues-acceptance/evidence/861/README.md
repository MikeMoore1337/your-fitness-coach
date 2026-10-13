# #861 — поиск упражнений: actual AFTER

Это текущий browser evidence для PR #973. Снимки сделаны настоящим Playwright Chromium/WebKit тестом с безопасными синтетическими упражнениями. Реальные пользовательские данные не используются.

Проверенный сценарий общего справочника: ввести запрос при мобильной ширине, оставить searchbox в focus, убедиться, что первый результат расположен до блока фильтров и доступен в текущем viewport, затем проверить горизонтальный overflow. Дополнительно тест подтверждает, что CSS `order` не меняет DOM-порядок фильтров → счётчика → результатов и что Tab после поиска последовательно переводит фокус на три фильтра. Desktop сохраняет порядок фильтры → результаты.

## AFTER gallery

| Browser  | Mobile baseline 390                                     | Mobile compact 360                                     | Mobile large 430                                     | Desktop 1280                                            |
| -------- | ------------------------------------------------------- | ------------------------------------------------------ | ---------------------------------------------------- | ------------------------------------------------------- |
| Chromium | [PNG](after/chromium-exercise-catalog-baseline-390.png) | [PNG](after/chromium-exercise-catalog-compact-360.png) | [PNG](after/chromium-exercise-catalog-large-430.png) | [PNG](after/chromium-exercise-catalog-desktop-1280.png) |
| WebKit   | [PNG](after/webkit-exercise-catalog-baseline-390.png)   | [PNG](after/webkit-exercise-catalog-compact-360.png)   | [PNG](after/webkit-exercise-catalog-large-430.png)   | [PNG](after/webkit-exercise-catalog-desktop-1280.png)   |

Редактор программы использует отдельный `SearchableExercisePicker` и намеренно не менялся в этом PR. Алгоритм поиска, фильтры, API/DB и миграции не изменялись. Физический iPhone/Safari, настоящий Telegram и VoiceOver этим пакетом не подтверждаются.
