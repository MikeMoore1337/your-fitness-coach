# #980 — завершённый подход: явное редактирование и возврат в работу

## AFTER

Снимки сняты на synthetic workout fixture, без пользовательских данных. В выполненной
строке статус «Выполнен» не является toggle-действием: доступны отдельные «Редактировать»
и «Вернуть в работу». Второе действие открывает подтверждение с предупреждением о смене
статуса и сохранении фактических результатов.

| Движок | Тема | Выполненный подход | Подтверждение |
| --- | --- | --- | --- |
| Chromium | Dark | [PNG](after/chromium-dark-completed.png) | [PNG](after/chromium-dark-confirm.png) |
| Chromium | Light | [PNG](after/chromium-light-completed.png) | [PNG](after/chromium-light-confirm.png) |
| WebKit | Dark | [PNG](after/webkit-dark-completed.png) | [PNG](after/webkit-dark-confirm.png) |
| WebKit | Light | [PNG](after/webkit-light-completed.png) | [PNG](after/webkit-light-confirm.png) |

## Проверки

- strength и cardio: 4 cross-browser E2E сценария редактирования, отмены и возврата;
- сохранённые вес/повторы, длительность/дистанция остаются неизменными при смене статуса;
- отмена подтверждения не создаёт PATCH;
- после подтверждённого возврата подход становится текущим без запуска таймера отдыха;
- typecheck, lint и Russian UI guard проходят.

Физические устройства, настоящий Telegram и VoiceOver не подтверждены. Финальное visual
acceptance и release approval остаются отдельными owner gates.
