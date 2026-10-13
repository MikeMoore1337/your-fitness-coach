# #980 — завершённый подход: явное редактирование и возврат в работу

## AFTER

Снимки сняты на synthetic workout fixture, без пользовательских данных. В выполненной
строке статус «Выполнен» не является toggle-действием: доступны отдельные «Редактировать»,
«Отмена» и «Сохранить». «Вернуть в работу» находится во вторичном меню «Действия» и
открывает явное подтверждение с предупреждением о смене статуса и сохранении фактических
результатов. Во время чернового редактирования меню скрыто до явного «Отмена» или
«Сохранить». На completed-снимке строка проверена вместе с открытой панелью отдыха: панель
не перекрывает строку или её действие редактирования.

Текущий набор `-390-` снят на SHA изменения после исправления #980. В нём дополнительно
зафиксированы увеличенный отступ после «Последний рабочий результат», видимые поля
редактирования, выровненные summary/details rows и отдельные viewport-кадры RIR/footer
после прокрутки к цели. Старые PNG без суффикса `-390-` сохранены как историческое
доказательство предыдущего состояния и в финальную таблицу не входят.

| Движок   | Тема  | Выполненный подход                        | Подтверждение                           |
| -------- | ----- | ----------------------------------------- | --------------------------------------- |
| Chromium | Dark  | [PNG](after/chromium-390-dark-completed.png)  | [PNG](after/chromium-390-dark-confirm.png)  |
| Chromium | Light | [PNG](after/chromium-390-light-completed.png) | [PNG](after/chromium-390-light-confirm.png) |
| WebKit   | Dark  | [PNG](after/webkit-390-dark-completed.png)    | [PNG](after/webkit-390-dark-confirm.png)    |
| WebKit   | Light | [PNG](after/webkit-390-light-completed.png)   | [PNG](after/webkit-390-light-confirm.png)   |

## AFTER — открытое редактирование

Снимки ниже сняты после нажатия «Редактировать» на уже выполненном подходе в viewport
390×844. В каждом кадре видны фактические значения fixture, статус «Выполнен»/«Выполнено»,
а также «Сохранить» и «Отмена». Для стабильной отрисовки значения первого поля фокусируются
реальным браузерным действием; изображения не редактировались и не дорисовывались.

| Движок   | Тема  | Силовой подход (42,5 кг × 9)                     | Кардио (27 мин × 6,4 км)                     |
| -------- | ----- | ------------------------------------------------ | -------------------------------------------- |
| Chromium | Dark  | [PNG](after/chromium-390-dark-strength-editing.png)  | [PNG](after/chromium-390-dark-cardio-editing.png)  |
| Chromium | Light | [PNG](after/chromium-390-light-strength-editing.png) | [PNG](after/chromium-390-light-cardio-editing.png) |
| WebKit   | Dark  | [PNG](after/webkit-390-dark-strength-editing.png)    | [PNG](after/webkit-390-dark-cardio-editing.png)    |
| WebKit   | Light | [PNG](after/webkit-390-light-strength-editing.png)  | [PNG](after/webkit-390-light-cardio-editing.png)  |

Для силового подхода открытая панель отдыха остаётся выше строки и не перекрывает строку,
поля или действия редактирования. Capture выполнен штатным Playwright-тестом с
`mockActiveWorkout`; в репозитории остаётся тот же E2E-сценарий как воспроизводимая проверка.

| Движок   | Тема  | RIR после прокрутки к цели | Нижние действия / CTA после прокрутки |
| -------- | ----- | -------------------------- | -------------------------------------- |
| Chromium | Dark  | [PNG](after/chromium-390-dark-rir-actions.png)   | [PNG](after/chromium-390-dark-footer-actions.png)   |
| Chromium | Light | [PNG](after/chromium-390-light-rir-actions.png)  | [PNG](after/chromium-390-light-footer-actions.png)  |
| WebKit   | Dark  | [PNG](after/webkit-390-dark-rir-actions.png)     | [PNG](after/webkit-390-dark-footer-actions.png)     |
| WebKit   | Light | [PNG](after/webkit-390-light-rir-actions.png)    | [PNG](after/webkit-390-light-footer-actions.png)    |

Причины исправлены адресно в геометрии design-v2: completed block получает дополнительный
вертикальный отступ после истории, поля используют `border-box`, а controls и их дочерние
элементы не могут навязать ширину больше доступной колонки. Summary/details rows используют
единый min-height 44 px, flex-центрирование и одинаковые вертикальные отступы. Общая причина
нижнего перекрытия исправлена через уже существующий Telegram viewport adapter: нижний inset
dock и scroll clearance учитывают `--yfc-viewport-bottom` и safe-area. Глобальный `overflow-x`
для маскировки проблемы не менялся.

Geometry regression отдельно проверяет DOM rect веса/длительности, реальный focus и
Tab/Shift+Tab, отсутствие горизонтального overflow, summary rows, RIR, кардио-пульс и кнопку
«Завершить тренировку» на 320/360/390/393/430 px в Dark/Light. Keyboard regression проверяет
тот же набор ширин с modeled virtual keyboard, safe-area и скрытием dock при фокусе; TMA dock
regression живёт в PR #976.

## Проверки

- strength и cardio: cross-browser E2E сценарии редактирования, отмены, сохранения и возврата;
- сохранённые вес/повторы, длительность/дистанция остаются неизменными при смене статуса;
- после сохранения completed-редактирования `is_completed` остаётся `true`, а режим закрывается;
- отмена черновика восстанавливает значения и не создаёт PATCH;
- отмена подтверждения не создаёт PATCH;
- после подтверждённого возврата подход становится текущим без запуска нового таймера отдыха;
- геометрическая проверка подтверждает отсутствие перекрытия строк, RIR, кардио-раздела и CTA
  fixed bottom dock после целевой прокрутки;
- capture редактирования и нижних действий: Chromium/WebKit × Dark/Light, 4/4 Playwright tests
  passed;
- geometry matrix: 20/20 Playwright tests passed; keyboard/safe-area matrix: 20/20 passed;
- typecheck, lint и Russian UI guard проходят.

Физические устройства, настоящий Telegram и VoiceOver не подтверждены. Финальное visual
acceptance и release approval остаются отдельными owner gates.
