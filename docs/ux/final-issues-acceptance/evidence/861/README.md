# #861 — поиск упражнений: actual AFTER

Это текущий browser evidence для PR #973. Снимки сделаны настоящим Playwright Chromium/WebKit тестом с безопасными синтетическими упражнениями. Реальные пользовательские данные не используются.

Проверенный сценарий общего справочника: ввести запрос при мобильной ширине, оставить searchbox в focus, убедиться, что первый результат расположен до блока фильтров и доступен в текущем viewport, затем проверить горизонтальный overflow. Мобильный DOM и визуальный порядок совпадают: searchbox → счётчик и результаты → блок создания (если доступен) → фильтры; Tab переводит фокус на результат, затем на блок создания и фильтры, а Shift+Tab возвращает фокус в обратной последовательности. Desktop сохраняет порядок фильтры → блок создания → счётчик и результаты. CSS `order` для этого сценария не используется.

## AFTER gallery

| Browser  | Mobile baseline 390                                     | Mobile compact 360                                     | Mobile large 430                                     | Desktop 1280                                            |
| -------- | ------------------------------------------------------- | ------------------------------------------------------ | ---------------------------------------------------- | ------------------------------------------------------- |
| Chromium | [PNG](after/chromium-exercise-catalog-baseline-390.png) | [PNG](after/chromium-exercise-catalog-compact-360.png) | [PNG](after/chromium-exercise-catalog-large-430.png) | [PNG](after/chromium-exercise-catalog-desktop-1280.png) |
| WebKit   | [PNG](after/webkit-exercise-catalog-baseline-390.png)   | [PNG](after/webkit-exercise-catalog-compact-360.png)   | [PNG](after/webkit-exercise-catalog-large-430.png)   | [PNG](after/webkit-exercise-catalog-desktop-1280.png)   |

## Dark AFTER gallery

| Browser  | Mobile compact 360                                      | Mobile baseline 390                                      | Mobile large 430                                      | Desktop 1280                                             |
| -------- | ------------------------------------------------------- | -------------------------------------------------------- | ----------------------------------------------------- | -------------------------------------------------------- |
| Chromium | [PNG](after/chromium-exercise-catalog-dark-compact-360.png) | [PNG](after/chromium-exercise-catalog-dark-baseline-390.png) | [PNG](after/chromium-exercise-catalog-dark-large-430.png) | [PNG](after/chromium-exercise-catalog-dark-desktop-1280.png) |
| WebKit   | [PNG](after/webkit-exercise-catalog-dark-compact-360.png)   | [PNG](after/webkit-exercise-catalog-dark-baseline-390.png)   | [PNG](after/webkit-exercise-catalog-dark-large-430.png)   | [PNG](after/webkit-exercise-catalog-dark-desktop-1280.png)   |

Тёмные снимки получены существующим Playwright cross-browser harness на dev preview с
`installPlatformApi` и тем же тестовым fixture. В capture-only запуске тема задавалась через
временный init-script; после получения PNG патч удалён из spec до commit. Тест сохранил проверки
функционального поиска, DOM-порядка, Tab/Shift+Tab и горизонтального overflow для всех размеров.

Редактор программы использует отдельный `SearchableExercisePicker` и намеренно не менялся в этом PR. Алгоритм поиска, фильтры, API/DB и миграции не изменялись. Физический iPhone/Safari, настоящий Telegram и VoiceOver этим пакетом не подтверждаются.
