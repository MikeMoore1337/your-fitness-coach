# Issue #917: реальные AFTER прогрессии и истории

Экраны сняты с собранного React-приложения в Chromium с синтетическими ответами API.
Это работающий UI, а не DOM-макет; тестовые данные не подтверждают production или реальное
устройство. [Сценарий воспроизведения](../../../frontend/tests/e2e/issue-917-week-type.spec.ts)
также проверен в WebKit. [Утверждённый макет](../issue-917-week-type-proposal-20261030/README.md).

Mobile viewport: 320×844, 360×844, 393×844, 430×932; desktop: 1440×900.
На длинных снимках элемента фиксированный dock может оказаться посередине изображения:
он не скрывался при съёмке. Отдельные снимки viewport показывают настоящее положение dock.
TMA — эмуляция Telegram с safe areas, не физический клиент.

Основной сценарий: четыре тренировки за период, две тяжёлые и две средние; лёгких нет. Общий
объём 1 360 кг не меняется при переключении. Дополнительные состояния используют отдельные
тестовые ответы, включая завершённую тренировку без подходов. Идентификаторы и правила на
снимках синтетические.

## Dark

| Состояние | 320 | 360 | 393 | 430 | 1440 |
|---|---|---|---|---|---|
| Тренировка: тяжёлая | [320](workout-heavy-dark-320.png) | [360](workout-heavy-dark-360.png) | [393](workout-heavy-dark-393.png) | [430](workout-heavy-dark-430.png) | [1440](workout-heavy-dark-desktop.png) |
| Тренировка: средняя | [320](workout-medium-dark-320.png) | [360](workout-medium-dark-360.png) | [393](workout-medium-dark-393.png) | [430](workout-medium-dark-430.png) | [1440](workout-medium-dark-desktop.png) |
| Тренировка: лёгкая, без истории | [320](workout-light-dark-320.png) | [360](workout-light-dark-360.png) | [393](workout-light-dark-393.png) | [430](workout-light-dark-430.png) | [1440](workout-light-dark-desktop.png) |
| Программа: тяжёлая | [320](program-heavy-dark-320.png) | [360](program-heavy-dark-360.png) | [393](program-heavy-dark-393.png) | [430](program-heavy-dark-430.png) | [1440](program-heavy-dark-desktop.png) |
| Программа: средняя | [320](program-medium-dark-320.png) | [360](program-medium-dark-360.png) | [393](program-medium-dark-393.png) | [430](program-medium-dark-430.png) | [1440](program-medium-dark-desktop.png) |
| Программа: лёгкая, без истории | [320](program-light-dark-320.png) | [360](program-light-dark-360.png) | [393](program-light-dark-393.png) | [430](program-light-dark-430.png) | [1440](program-light-dark-desktop.png) |
| История: все | [320](analytics-all-dark-320.png) | [360](analytics-all-dark-360.png) | [393](analytics-all-dark-393.png) | [430](analytics-all-dark-430.png) | [1440](analytics-all-dark-desktop.png) |
| История: тяжёлая | [320](analytics-heavy-dark-320.png) | [360](analytics-heavy-dark-360.png) | [393](analytics-heavy-dark-393.png) | [430](analytics-heavy-dark-430.png) | [1440](analytics-heavy-dark-desktop.png) |
| История: средняя | [320](analytics-medium-dark-320.png) | [360](analytics-medium-dark-360.png) | [393](analytics-medium-dark-393.png) | [430](analytics-medium-dark-430.png) | [1440](analytics-medium-dark-desktop.png) |
| История: лёгкая, без истории | [320](analytics-light-dark-320.png) | [360](analytics-light-dark-360.png) | [393](analytics-light-dark-393.png) | [430](analytics-light-dark-430.png) | [1440](analytics-light-dark-desktop.png) |

### Крупный план подсказки

| Тип недели | 320 | 360 | 393 | 430 | 1440 |
|---|---|---|---|---|---|
| Тяжёлая | [320](workout-heavy-guidance-dark-320.png) | [360](workout-heavy-guidance-dark-360.png) | [393](workout-heavy-guidance-dark-393.png) | [430](workout-heavy-guidance-dark-430.png) | [1440](workout-heavy-guidance-dark-desktop.png) |
| Средняя | [320](workout-medium-guidance-dark-320.png) | [360](workout-medium-guidance-dark-360.png) | [393](workout-medium-guidance-dark-393.png) | [430](workout-medium-guidance-dark-430.png) | [1440](workout-medium-guidance-dark-desktop.png) |
| Лёгкая | [320](workout-light-guidance-dark-320.png) | [360](workout-light-guidance-dark-360.png) | [393](workout-light-guidance-dark-393.png) | [430](workout-light-guidance-dark-430.png) | [1440](workout-light-guidance-dark-desktop.png) |

### Фактический viewport

| Состояние | 320 | 360 | 393 | 430 | 1440 |
|---|---|---|---|---|---|
| Тяжёлая неделя | [320](workout-heavy-viewport-dark-320.png) | [360](workout-heavy-viewport-dark-360.png) | [393](workout-heavy-viewport-dark-393.png) | [430](workout-heavy-viewport-dark-430.png) | [1440](workout-heavy-viewport-dark-desktop.png) |
| Лёгкая, без истории | — | — | [393](workout-light-viewport-dark-393.png) | — | [1440](workout-light-viewport-dark-desktop.png) |

[Telegram mock: тренировка](tma-workout-dark-393.png) · [Telegram mock: история](tma-analytics-dark-393.png)

## Light

| Состояние | 320 | 360 | 393 | 430 | 1440 |
|---|---|---|---|---|---|
| Тренировка: тяжёлая | [320](workout-heavy-light-320.png) | [360](workout-heavy-light-360.png) | [393](workout-heavy-light-393.png) | [430](workout-heavy-light-430.png) | [1440](workout-heavy-light-desktop.png) |
| Тренировка: средняя | [320](workout-medium-light-320.png) | [360](workout-medium-light-360.png) | [393](workout-medium-light-393.png) | [430](workout-medium-light-430.png) | [1440](workout-medium-light-desktop.png) |
| Тренировка: лёгкая, без истории | [320](workout-light-light-320.png) | [360](workout-light-light-360.png) | [393](workout-light-light-393.png) | [430](workout-light-light-430.png) | [1440](workout-light-light-desktop.png) |
| Программа: тяжёлая | [320](program-heavy-light-320.png) | [360](program-heavy-light-360.png) | [393](program-heavy-light-393.png) | [430](program-heavy-light-430.png) | [1440](program-heavy-light-desktop.png) |
| Программа: средняя | [320](program-medium-light-320.png) | [360](program-medium-light-360.png) | [393](program-medium-light-393.png) | [430](program-medium-light-430.png) | [1440](program-medium-light-desktop.png) |
| Программа: лёгкая, без истории | [320](program-light-light-320.png) | [360](program-light-light-360.png) | [393](program-light-light-393.png) | [430](program-light-light-430.png) | [1440](program-light-light-desktop.png) |
| История: все | [320](analytics-all-light-320.png) | [360](analytics-all-light-360.png) | [393](analytics-all-light-393.png) | [430](analytics-all-light-430.png) | [1440](analytics-all-light-desktop.png) |
| История: тяжёлая | [320](analytics-heavy-light-320.png) | [360](analytics-heavy-light-360.png) | [393](analytics-heavy-light-393.png) | [430](analytics-heavy-light-430.png) | [1440](analytics-heavy-light-desktop.png) |
| История: средняя | [320](analytics-medium-light-320.png) | [360](analytics-medium-light-360.png) | [393](analytics-medium-light-393.png) | [430](analytics-medium-light-430.png) | [1440](analytics-medium-light-desktop.png) |
| История: лёгкая, без истории | [320](analytics-light-light-320.png) | [360](analytics-light-light-360.png) | [393](analytics-light-light-393.png) | [430](analytics-light-light-430.png) | [1440](analytics-light-light-desktop.png) |

### Крупный план подсказки

| Тип недели | 320 | 360 | 393 | 430 | 1440 |
|---|---|---|---|---|---|
| Тяжёлая | [320](workout-heavy-guidance-light-320.png) | [360](workout-heavy-guidance-light-360.png) | [393](workout-heavy-guidance-light-393.png) | [430](workout-heavy-guidance-light-430.png) | [1440](workout-heavy-guidance-light-desktop.png) |
| Средняя | [320](workout-medium-guidance-light-320.png) | [360](workout-medium-guidance-light-360.png) | [393](workout-medium-guidance-light-393.png) | [430](workout-medium-guidance-light-430.png) | [1440](workout-medium-guidance-light-desktop.png) |
| Лёгкая | [320](workout-light-guidance-light-320.png) | [360](workout-light-guidance-light-360.png) | [393](workout-light-guidance-light-393.png) | [430](workout-light-guidance-light-430.png) | [1440](workout-light-guidance-light-desktop.png) |

### Фактический viewport

| Состояние | 320 | 360 | 393 | 430 | 1440 |
|---|---|---|---|---|---|
| Тяжёлая неделя | [320](workout-heavy-viewport-light-320.png) | [360](workout-heavy-viewport-light-360.png) | [393](workout-heavy-viewport-light-393.png) | [430](workout-heavy-viewport-light-430.png) | [1440](workout-heavy-viewport-light-desktop.png) |
| Лёгкая, без истории | — | — | [393](workout-light-viewport-light-393.png) | — | [1440](workout-light-viewport-light-desktop.png) |

[Telegram mock: тренировка](tma-workout-light-393.png) · [Telegram mock: история](tma-analytics-light-393.png)

## Неполные факты прогрессии

| Состояние | Dark 393 | Light 393 | Dark 1440 | Light 1440 |
|---|---|---|---|---|
| Не записан RIR | [393](workout-missing-rir-dark-393.png) | [393](workout-missing-rir-light-393.png) | [1440](workout-missing-rir-dark-desktop.png) | [1440](workout-missing-rir-light-desktop.png) |
| Не записан RIR: доказательства | [393](workout-missing-rir-details-dark-393.png) | [393](workout-missing-rir-details-light-393.png) | [1440](workout-missing-rir-details-dark-desktop.png) | [1440](workout-missing-rir-details-light-desktop.png) |
| Неполный подход | [393](workout-incomplete-dark-393.png) | [393](workout-incomplete-light-393.png) | [1440](workout-incomplete-dark-desktop.png) | [1440](workout-incomplete-light-desktop.png) |
| Неполный подход: доказательства | [393](workout-incomplete-details-dark-393.png) | [393](workout-incomplete-details-light-393.png) | [1440](workout-incomplete-details-dark-desktop.png) | [1440](workout-incomplete-details-light-desktop.png) |

## Неполная или недоступная история

| Состояние | Dark 393 | Light 393 | Dark 1440 | Light 1440 |
|---|---|---|---|---|
| Есть тренировка, нет рабочих подходов | [393](analytics-no-sets-dark-393.png) | [393](analytics-no-sets-light-393.png) | [1440](analytics-no-sets-dark-desktop.png) | [1440](analytics-no-sets-light-desktop.png) |
| Тип не удалось подтвердить | [393](analytics-unknown-dark-393.png) | [393](analytics-unknown-light-393.png) | [1440](analytics-unknown-dark-desktop.png) | [1440](analytics-unknown-light-desktop.png) |
| Ошибка загрузки | [393](analytics-error-dark-393.png) | [393](analytics-error-light-393.png) | [1440](analytics-error-dark-desktop.png) | [1440](analytics-error-light-desktop.png) |
| Нет сети | [393](analytics-offline-dark-393.png) | [393](analytics-offline-light-393.png) | [1440](analytics-offline-dark-desktop.png) | [1440](analytics-offline-light-desktop.png) |

## Раскрытые доказательства

| Контекст | Dark 393 | Light 393 | Dark 1440 | Light 1440 |
|---|---|---|---|---|
| Тренировка | [393](workout-heavy-details-dark-393.png) | [393](workout-heavy-details-light-393.png) | [1440](workout-heavy-details-dark-desktop.png) | [1440](workout-heavy-details-light-desktop.png) |
| Назначенная программа | [393](program-heavy-details-dark-393.png) | [393](program-heavy-details-light-393.png) | [1440](program-heavy-details-dark-desktop.png) | [1440](program-heavy-details-light-desktop.png) |

Доказательства в раскрытии показывают фактически возвращённые идентификаторы подходов,
коды причин и версию правила. Наличие снимков не заменяет визуальную приёмку владельцем.
