# Issue #953: реализованный интерфейс

Снимки сделаны в Chromium с локальной сборкой приложения и мигрированной изолированной PostgreSQL 16. Все учётные записи, продукты и числа синтетические. Дата в данных — 8 ноября 2026 года.

Мобильный viewport: 393×844; настольный: 1280×900. Снимки показывают отдельные блоки приложения; в длинных блоках закреплённая мобильная навигация может попасть в кадр. Для кнопок приведён также снимок видимой области экрана. Уведомление о добавлении в дневник на некоторых снимках плана относится к предыдущему шагу сценария.

Снимки не являются проверкой production, реальных устройств или Telegram. Одобрение реализации и разрешение на merge или deploy — отдельные решения.

| Состояние | 393 Dark | 393 Light | 1280 Dark | 1280 Light |
|---|---|---|---|---|
| Отчёт до добавления | [dark](chromium-393-dark-report.png) | [light](chromium-393-light-report.png) | [dark](chromium-1280-dark-report.png) | [light](chromium-1280-light-report.png) |
| Два варианта дневника | [dark](chromium-393-dark-choices.png) | [light](chromium-393-light-choices.png) | [dark](chromium-1280-dark-choices.png) | [light](chromium-1280-light-choices.png) |
| Раскрытый список дневника | [dark](chromium-393-dark-choices-expanded.png) | [light](chromium-393-light-choices-expanded.png) | [dark](chromium-1280-dark-choices-expanded.png) | [light](chromium-1280-light-choices-expanded.png) |
| Проверка перед записью | [dark](chromium-393-dark-preview-diary.png) | [light](chromium-393-light-preview-diary.png) | [dark](chromium-1280-dark-preview-diary.png) | [light](chromium-1280-light-preview-diary.png) |
| Превышение предела дневника | [dark](chromium-393-dark-limit-diary.png) | [light](chromium-393-light-limit-diary.png) | [dark](chromium-1280-dark-limit-diary.png) | [light](chromium-1280-light-limit-diary.png) |
| Исключённый продукт в дневнике | [dark](chromium-393-dark-excluded-diary.png) | [light](chromium-393-light-excluded-diary.png) | [dark](chromium-1280-dark-excluded-diary.png) | [light](chromium-1280-light-excluded-diary.png) |
| Введённые предпочтения и предел дневника | [dark](chromium-393-dark-constraints-diary.png) | [light](chromium-393-light-constraints-diary.png) | [dark](chromium-1280-dark-constraints-diary.png) | [light](chromium-1280-light-constraints-diary.png) |
| Кнопки проверки в видимой области | [dark](chromium-393-dark-action-diary.png) | [light](chromium-393-light-action-diary.png) | [dark](chromium-1280-dark-action-diary.png) | [light](chromium-1280-light-action-diary.png) |
| Дневник после подтверждения | [dark](chromium-393-dark-result-diary.png) | [light](chromium-393-light-result-diary.png) | [dark](chromium-1280-dark-result-diary.png) | [light](chromium-1280-light-result-diary.png) |
| Все варианты плана | [dark](chromium-393-dark-choices-plan.png) | [light](chromium-393-light-choices-plan.png) | [dark](chromium-1280-dark-choices-plan.png) | [light](chromium-1280-light-choices-plan.png) |
| Проверка перед планированием | [dark](chromium-393-dark-preview-plan.png) | [light](chromium-393-light-preview-plan.png) | [dark](chromium-1280-dark-preview-plan.png) | [light](chromium-1280-light-preview-plan.png) |
| Превышение предела плана | [dark](chromium-393-dark-limit-plan.png) | [light](chromium-393-light-limit-plan.png) | [dark](chromium-1280-dark-limit-plan.png) | [light](chromium-1280-light-limit-plan.png) |
| Исключённый продукт в плане | [dark](chromium-393-dark-excluded-plan.png) | [light](chromium-393-light-excluded-plan.png) | [dark](chromium-1280-dark-excluded-plan.png) | [light](chromium-1280-light-excluded-plan.png) |
| Введённый предел плана | [dark](chromium-393-dark-constraints-plan.png) | [light](chromium-393-light-constraints-plan.png) | [dark](chromium-1280-dark-constraints-plan.png) | [light](chromium-1280-light-constraints-plan.png) |
| План после подтверждения | [dark](chromium-393-dark-result-plan.png) | [light](chromium-393-light-result-plan.png) | [dark](chromium-1280-dark-result-plan.png) | [light](chromium-1280-light-result-plan.png) |
| Обновлённый отчёт | [dark](chromium-393-dark-result-report.png) | [light](chromium-393-light-result-report.png) | [dark](chromium-1280-dark-result-report.png) | [light](chromium-1280-light-result-report.png) |
| Устаревший расчёт | [dark](chromium-393-dark-stale-diary.png) | [light](chromium-393-light-stale-diary.png) | [dark](chromium-1280-dark-stale-diary.png) | [light](chromium-1280-light-stale-diary.png) |
| Нет цели | [dark](chromium-393-dark-no-target.png) | [light](chromium-393-light-no-target.png) | [dark](chromium-1280-dark-no-target.png) | [light](chromium-1280-light-no-target.png) |
| Нет вариантов | [dark](chromium-393-dark-empty.png) | [light](chromium-393-light-empty.png) | [dark](chromium-1280-dark-empty.png) | [light](chromium-1280-light-empty.png) |

Дополнительная проверка узкого viewport 320×720:

| Состояние | Dark | Light |
|---|---|---|
| Два варианта дневника | [dark](chromium-320-dark-choices.png) | [light](chromium-320-light-choices.png) |
| Раскрытый список дневника | [dark](chromium-320-dark-choices-expanded.png) | [light](chromium-320-light-choices-expanded.png) |
| Проверка перед записью | [dark](chromium-320-dark-preview-diary.png) | [light](chromium-320-light-preview-diary.png) |
| Введённые предпочтения и предел дневника | [dark](chromium-320-dark-constraints-diary.png) | [light](chromium-320-light-constraints-diary.png) |
| Кнопки проверки в видимой области | [dark](chromium-320-dark-action-diary.png) | [light](chromium-320-light-action-diary.png) |
