# AFTER: заметка с прошлого выполнения — Issue #1195

Снимки показывают собранный React-интерфейс, а не макет. Пользователь и текст заметки вымышлены. Строки «реальный API» получены на локальном FastAPI и PostgreSQL 16: заметка сохранена через API завершённой тренировки, её дата сдвинута на неделю в тестовой базе. Остальные снимки используют синтетические ответы API. В активной тренировке показан текущий таймер отдыха v2.

Размеры приведены в CSS-пикселях. Chromium и WebKit запущены локально через Playwright. Клавиатура представлена уменьшением viewport с фокусом в поле ввода; PWA и Telegram — имитации оболочек. Эти снимки не подтверждают поведение физического устройства или настоящего Telegram.

| Экран, браузер и viewport                                   | Dark                                           | Light                                           |
| ----------------------------------------------------------- | ---------------------------------------------- | ----------------------------------------------- |
| Запланированная, реальный API, Chromium, 393 × 844          | [PNG](chromium-dark-393-live-api-planned.png)  | [PNG](chromium-light-393-live-api-planned.png)  |
| Активная, реальный API, Chromium, 393 × 844                 | [PNG](chromium-dark-393-live-api-active.png)   | [PNG](chromium-light-393-live-api-active.png)   |
| Активная с таймером, реальный API, Chromium, 393 × 844      | [PNG](chromium-dark-393-live-api-timer.png)    | [PNG](chromium-light-393-live-api-timer.png)    |
| Запланированная, chromium, 320 × 844                        | [PNG](chromium-dark-320-planned.png)           | [PNG](chromium-light-320-planned.png)           |
| Активная с таймером, chromium, 320 × 844                    | [PNG](chromium-dark-320-active.png)            | [PNG](chromium-light-320-active.png)            |
| Запланированная, chromium, 360 × 844                        | [PNG](chromium-dark-360-planned.png)           | [PNG](chromium-light-360-planned.png)           |
| Активная с таймером, chromium, 360 × 844                    | [PNG](chromium-dark-360-active.png)            | [PNG](chromium-light-360-active.png)            |
| Запланированная, chromium, 393 × 844                        | [PNG](chromium-dark-393-planned.png)           | [PNG](chromium-light-393-planned.png)           |
| Активная с таймером, chromium, 393 × 844                    | [PNG](chromium-dark-393-active.png)            | [PNG](chromium-light-393-active.png)            |
| Запланированная, chromium, 430 × 844                        | [PNG](chromium-dark-430-planned.png)           | [PNG](chromium-light-430-planned.png)           |
| Активная с таймером, chromium, 430 × 844                    | [PNG](chromium-dark-430-active.png)            | [PNG](chromium-light-430-active.png)            |
| Более старая заметка, chromium, 393 × 844                   | [PNG](chromium-dark-393-older.png)             | [PNG](chromium-light-393-older.png)             |
| Свёрнутая заметка, chromium, 393 × 844                      | [PNG](chromium-dark-393-collapsed.png)         | [PNG](chromium-light-393-collapsed.png)         |
| Запланированная, старая заметка, chromium, 1440 × 1000      | [PNG](chromium-dark-1440-older.png)            | [PNG](chromium-light-1440-older.png)            |
| Активная, старая заметка и таймер, chromium, 1440 × 1000    | [PNG](chromium-dark-1440-active-older.png)     | [PNG](chromium-light-1440-active-older.png)     |
| Запланированная, pwa, chromium, 393 × 844                   | [PNG](chromium-dark-393-pwa-planned.png)       | [PNG](chromium-light-393-pwa-planned.png)       |
| Фокус и уменьшенный viewport, pwa, chromium, 393 × 500      | [PNG](chromium-dark-393-pwa-keyboard.png)      | [PNG](chromium-light-393-pwa-keyboard.png)      |
| Запланированная, telegram, chromium, 393 × 844              | [PNG](chromium-dark-393-telegram-planned.png)  | [PNG](chromium-light-393-telegram-planned.png)  |
| Фокус и уменьшенный viewport, telegram, chromium, 393 × 500 | [PNG](chromium-dark-393-telegram-keyboard.png) | [PNG](chromium-light-393-telegram-keyboard.png) |
| Запланированная, webkit, 320 × 844                          | [PNG](webkit-dark-320-planned.png)             | [PNG](webkit-light-320-planned.png)             |
| Активная с таймером, webkit, 320 × 844                      | [PNG](webkit-dark-320-active.png)              | [PNG](webkit-light-320-active.png)              |
| Запланированная, webkit, 360 × 844                          | [PNG](webkit-dark-360-planned.png)             | [PNG](webkit-light-360-planned.png)             |
| Активная с таймером, webkit, 360 × 844                      | [PNG](webkit-dark-360-active.png)              | [PNG](webkit-light-360-active.png)              |
| Запланированная, webkit, 393 × 844                          | [PNG](webkit-dark-393-planned.png)             | [PNG](webkit-light-393-planned.png)             |
| Активная с таймером, webkit, 393 × 844                      | [PNG](webkit-dark-393-active.png)              | [PNG](webkit-light-393-active.png)              |
| Запланированная, webkit, 430 × 844                          | [PNG](webkit-dark-430-planned.png)             | [PNG](webkit-light-430-planned.png)             |
| Активная с таймером, webkit, 430 × 844                      | [PNG](webkit-dark-430-active.png)              | [PNG](webkit-light-430-active.png)              |
| Более старая заметка, webkit, 393 × 844                     | [PNG](webkit-dark-393-older.png)               | [PNG](webkit-light-393-older.png)               |
| Свёрнутая заметка, webkit, 393 × 844                        | [PNG](webkit-dark-393-collapsed.png)           | [PNG](webkit-light-393-collapsed.png)           |
| Запланированная, старая заметка, webkit, 1440 × 1000        | [PNG](webkit-dark-1440-older.png)              | [PNG](webkit-light-1440-older.png)              |
| Активная, старая заметка и таймер, webkit, 1440 × 1000      | [PNG](webkit-dark-1440-active-older.png)       | [PNG](webkit-light-1440-active-older.png)       |
| Запланированная, pwa, webkit, 393 × 844                     | [PNG](webkit-dark-393-pwa-planned.png)         | [PNG](webkit-light-393-pwa-planned.png)         |
| Фокус и уменьшенный viewport, pwa, webkit, 393 × 500        | [PNG](webkit-dark-393-pwa-keyboard.png)        | [PNG](webkit-light-393-pwa-keyboard.png)        |
| Запланированная, telegram, webkit, 393 × 844                | [PNG](webkit-dark-393-telegram-planned.png)    | [PNG](webkit-light-393-telegram-planned.png)    |
| Фокус и уменьшенный viewport, telegram, webkit, 393 × 500   | [PNG](webkit-dark-393-telegram-keyboard.png)   | [PNG](webkit-light-393-telegram-keyboard.png)   |

При отсутствии достоверной заметки блок не отображается; после восстановления сети данные перечитываются с сервера. Это подтверждено тестами, а не отдельным снимком.
