# #980 — завершённый подход: явное редактирование и возврат в работу

## AFTER

Снимки сняты на synthetic workout fixture, без пользовательских данных. В выполненной
строке статус «Выполнен» не является toggle-действием: доступны отдельные «Редактировать»,
«Отмена» и «Сохранить». «Вернуть в работу» находится во вторичном меню «Действия» и
открывает явное подтверждение с предупреждением о смене статуса и сохранении фактических
результатов. Во время чернового редактирования меню скрыто до явного «Отмена» или
«Сохранить». На completed-снимке строка проверена вместе с открытой панелью отдыха: панель
не перекрывает строку или её действие редактирования.

| Движок   | Тема  | Выполненный подход                        | Подтверждение                           |
| -------- | ----- | ----------------------------------------- | --------------------------------------- |
| Chromium | Dark  | [PNG](after/chromium-dark-completed.png)  | [PNG](after/chromium-dark-confirm.png)  |
| Chromium | Light | [PNG](after/chromium-light-completed.png) | [PNG](after/chromium-light-confirm.png) |
| WebKit   | Dark  | [PNG](after/webkit-dark-completed.png)    | [PNG](after/webkit-dark-confirm.png)    |
| WebKit   | Light | [PNG](after/webkit-light-completed.png)   | [PNG](after/webkit-light-confirm.png)   |

## AFTER — открытое редактирование

Снимки ниже сняты после нажатия «Редактировать» на уже выполненном подходе в viewport
390×844. В каждом кадре видны фактические значения fixture, статус «Выполнен»/«Выполнено»,
а также «Сохранить» и «Отмена». Для стабильной отрисовки значения первого поля фокусируются
реальным браузерным действием; изображения не редактировались и не дорисовывались.

| Движок   | Тема  | Силовой подход (42,5 кг × 9)                     | Кардио (27 мин × 6,4 км)                     |
| -------- | ----- | ------------------------------------------------ | -------------------------------------------- |
| Chromium | Dark  | [PNG](after/chromium-dark-strength-editing.png)  | [PNG](after/chromium-dark-cardio-editing.png)  |
| Chromium | Light | [PNG](after/chromium-light-strength-editing.png) | [PNG](after/chromium-light-cardio-editing.png) |
| WebKit   | Dark  | [PNG](after/webkit-dark-strength-editing.png)    | [PNG](after/webkit-dark-cardio-editing.png)    |
| WebKit   | Light | [PNG](after/webkit-light-strength-editing.png)  | [PNG](after/webkit-light-cardio-editing.png)  |

Для силового подхода открытая панель отдыха остаётся выше строки и не перекрывает строку,
поля или действия редактирования. Capture использовал временный Playwright-тест с
`mockActiveWorkout` и был удалён до evidence-only commit.

## Проверки

- strength и cardio: cross-browser E2E сценарии редактирования, отмены, сохранения и возврата;
- сохранённые вес/повторы, длительность/дистанция остаются неизменными при смене статуса;
- после сохранения completed-редактирования `is_completed` остаётся `true`, а режим закрывается;
- отмена черновика восстанавливает значения и не создаёт PATCH;
- отмена подтверждения не создаёт PATCH;
- после подтверждённого возврата подход становится текущим без запуска нового таймера отдыха;
- геометрическая проверка подтверждает отсутствие перекрытия строки панелью отдыха;
- временный capture редактирования: Chromium/WebKit × Dark/Light, 8/8 passed;
- typecheck, lint и Russian UI guard проходят.

Физические устройства, настоящий Telegram и VoiceOver не подтверждены. Финальное visual
acceptance и release approval остаются отдельными owner gates.
