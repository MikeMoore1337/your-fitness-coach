# #995: макет заметки к выполнению упражнения

Статус: **макет ожидает согласования владельца**. Основа экрана — React из `dev` на
[`3275bc4c`](https://github.com/MikeMoore1337/your-fitness-coach/commit/3275bc4c08238ef8b8d1f5a461e296e9159115e2):
он содержит историю подходов [#1132 / PR #1314](https://github.com/MikeMoore1337/your-fitness-coach/pull/1314),
общую заметку [#1195 / PR #1342](https://github.com/MikeMoore1337/your-fitness-coach/pull/1342)
и исправление таймера [#1338 / PR #1343](https://github.com/MikeMoore1337/your-fitness-coach/pull/1343).

Новый блок добавлен только временным DOM-прототипом поверх работающего React с синтетическими
ответами API. Поле, метки и состояния на снимках демонстрируют дизайн; они **не сохраняют данные**.
Это не реальные AFTER реализации и не свидетельство работы API, базы данных или offline-очереди.

## Предложение

- После основных действий текущего подхода и двух кнопок истории — компактная строка
  «Заметка к упражнению». Она показывает последнюю сохранённую заметку с датой, типом недели и
  контекстом нагрузки. Указанная нагрузка относится к тренировке, из которой взята заметка.
- Раскрытие показывает прошлое наблюдение отдельно от ввода заметки к текущему выполнению.
  Можно ввести текст и выбрать «Легко», «Тяжело», «Повысить вес». Метки ничего не меняют
  автоматически. После последнего подхода блок остаётся доступен в раскрытом выполненном упражнении.
- Показаны пустая история, длинный текст, редактирование и удаление, состояние после сохранения
  на устройстве без сети и предложение разрешить конфликт версий. Сообщение об устройстве
  допустимо только после подтверждённого локального сохранения; конфликт не должен незаметно
  перезаписать серверную версию.
- Нагрузка из #1132 и общая заметка #1195 остаются отдельными источниками. Если последняя
  сохранённая заметка старше последнего выполнения, её дата и нагрузка должны относиться именно
  к её исходной тренировке. При недоказанной идентичности заметка не показывается как подходящая.

## Матрица снимков

Ссылки ниже ведут к отдельным PNG. `320` и `360` — 800 px высотой, `393` — 844 px,
`430` — 932 px, desktop — 1440 × 900. «Клавиатура» — уменьшенный до 480 px viewport с
фокусом в поле, **не** снимок нативной клавиатуры.

| Браузер, тема   | 320                                                                                                                                                           | 360                                                                                                                                                           | 393                                                                                                                                                           | 430                                                                                                                                                           | Desktop                                                                                            |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Chromium, Dark  | [строка](design/chromium-dark-320-collapsed.png) · [ввод](design/chromium-dark-320-editor.png) · [клавиатура](design/chromium-dark-320-keyboard-model.png)    | [строка](design/chromium-dark-360-collapsed.png) · [ввод](design/chromium-dark-360-editor.png) · [клавиатура](design/chromium-dark-360-keyboard-model.png)    | [строка](design/chromium-dark-393-collapsed.png) · [ввод](design/chromium-dark-393-editor.png) · [клавиатура](design/chromium-dark-393-keyboard-model.png)    | [строка](design/chromium-dark-430-collapsed.png) · [ввод](design/chromium-dark-430-editor.png) · [клавиатура](design/chromium-dark-430-keyboard-model.png)    | [строка](design/chromium-dark-1440-collapsed.png) · [ввод](design/chromium-dark-1440-editor.png)   |
| Chromium, Light | [строка](design/chromium-light-320-collapsed.png) · [ввод](design/chromium-light-320-editor.png) · [клавиатура](design/chromium-light-320-keyboard-model.png) | [строка](design/chromium-light-360-collapsed.png) · [ввод](design/chromium-light-360-editor.png) · [клавиатура](design/chromium-light-360-keyboard-model.png) | [строка](design/chromium-light-393-collapsed.png) · [ввод](design/chromium-light-393-editor.png) · [клавиатура](design/chromium-light-393-keyboard-model.png) | [строка](design/chromium-light-430-collapsed.png) · [ввод](design/chromium-light-430-editor.png) · [клавиатура](design/chromium-light-430-keyboard-model.png) | [строка](design/chromium-light-1440-collapsed.png) · [ввод](design/chromium-light-1440-editor.png) |
| WebKit, Dark    | [строка](design/webkit-dark-320-collapsed.png) · [ввод](design/webkit-dark-320-editor.png) · [клавиатура](design/webkit-dark-320-keyboard-model.png)          | [строка](design/webkit-dark-360-collapsed.png) · [ввод](design/webkit-dark-360-editor.png) · [клавиатура](design/webkit-dark-360-keyboard-model.png)          | [строка](design/webkit-dark-393-collapsed.png) · [ввод](design/webkit-dark-393-editor.png) · [клавиатура](design/webkit-dark-393-keyboard-model.png)          | [строка](design/webkit-dark-430-collapsed.png) · [ввод](design/webkit-dark-430-editor.png) · [клавиатура](design/webkit-dark-430-keyboard-model.png)          | [строка](design/webkit-dark-1440-collapsed.png) · [ввод](design/webkit-dark-1440-editor.png)       |
| WebKit, Light   | [строка](design/webkit-light-320-collapsed.png) · [ввод](design/webkit-light-320-editor.png) · [клавиатура](design/webkit-light-320-keyboard-model.png)       | [строка](design/webkit-light-360-collapsed.png) · [ввод](design/webkit-light-360-editor.png) · [клавиатура](design/webkit-light-360-keyboard-model.png)       | [строка](design/webkit-light-393-collapsed.png) · [ввод](design/webkit-light-393-editor.png) · [клавиатура](design/webkit-light-393-keyboard-model.png)       | [строка](design/webkit-light-430-collapsed.png) · [ввод](design/webkit-light-430-editor.png) · [клавиатура](design/webkit-light-430-keyboard-model.png)       | [строка](design/webkit-light-1440-collapsed.png) · [ввод](design/webkit-light-1440-editor.png)     |

## Состояния, 393 × 844

| Состояние                         | Chromium Dark                                          | Chromium Light                                          | WebKit Dark                                          | WebKit Light                                          |
| --------------------------------- | ------------------------------------------------------ | ------------------------------------------------------- | ---------------------------------------------------- | ----------------------------------------------------- |
| Нет прошлой заметки               | [PNG](design/chromium-dark-393-empty.png)              | [PNG](design/chromium-light-393-empty.png)              | [PNG](design/webkit-dark-393-empty.png)              | [PNG](design/webkit-light-393-empty.png)              |
| Длинный текст                     | [PNG](design/chromium-dark-393-long.png)               | [PNG](design/chromium-light-393-long.png)               | [PNG](design/webkit-dark-393-long.png)               | [PNG](design/webkit-light-393-long.png)               |
| Редактирование и удаление         | [PNG](design/chromium-dark-393-edit-delete.png)        | [PNG](design/chromium-light-393-edit-delete.png)        | [PNG](design/webkit-dark-393-edit-delete.png)        | [PNG](design/webkit-light-393-edit-delete.png)        |
| Нет сети, сохранено на устройстве | [PNG](design/chromium-dark-393-offline.png)            | [PNG](design/chromium-light-393-offline.png)            | [PNG](design/webkit-dark-393-offline.png)            | [PNG](design/webkit-light-393-offline.png)            |
| Конфликт версий                   | [PNG](design/chromium-dark-393-conflict-bottom.png)    | [PNG](design/chromium-light-393-conflict-bottom.png)    | [PNG](design/webkit-dark-393-conflict-bottom.png)    | [PNG](design/webkit-light-393-conflict-bottom.png)    |
| Упражнение выполнено              | [PNG](design/chromium-dark-393-completed-exercise.png) | [PNG](design/chromium-light-393-completed-exercise.png) | [PNG](design/webkit-dark-393-completed-exercise.png) | [PNG](design/webkit-light-393-completed-exercise.png) |
| TMA, браузерная имитация          | [PNG](design/chromium-dark-393-tma-simulated.png)      | [PNG](design/chromium-light-393-tma-simulated.png)      | [PNG](design/webkit-dark-393-tma-simulated.png)      | [PNG](design/webkit-light-393-tma-simulated.png)      |

## Проверка макета

Локальный Playwright: 28 сценариев в Chromium и WebKit — 20 сочетаний темы и размера,
4 сценария после последнего подхода и 4 сценария с браузерной имитацией TMA. Проверены отсутствие
горизонтального переполнения, размеры элементов выбора, клавиатурное раскрытие и выбор метки,
фокус поля в модели клавиатуры, достижимость кнопок завершения, размеры таймера и неизменность
положения RIR и кнопки подхода при вставке макета. Проверены исходное соседство и порядок кнопок
подстановки #1132. Изменение макета не меняет тестовые результаты подходов.

Сценарии и оформление прототипа: [prototype.spec.ts](prototype.spec.ts),
[prototype.config.ts](prototype.config.ts). Из `frontend/` с установленными зависимостями:

```powershell
node ./node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5175 --strictPort
# Во втором терминале:
node ./node_modules/@playwright/test/cli.js test --config ../docs/ux-proposals/issue-995/prototype.config.ts --grep prototype
```

Физический iPhone, Safari/PWA, нативная клавиатура, реальный Telegram и screen reader:
`NOT_VERIFIED`. Независимый `qa-verifier`: `NOT_RUN`. Согласование макета не является
финальной визуальной приёмкой, разрешением на merge в `dev` или разрешением на production.
