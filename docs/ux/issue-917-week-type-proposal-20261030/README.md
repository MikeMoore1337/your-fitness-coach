# Issue #917: макет прогрессии и истории по типам недель

Статус: **предложение для визуального согласования**. Это не реализация и не AFTER. Основа —
`dev` на `3275bc4c08238ef8b8d1f5a461e296e9159115e2`; экраны отрисованы Chromium на синтетических
данных. Изменения макета добавлены в DOM тестом после загрузки существующего приложения;
[исходник съёмки](capture-source.ts.txt) сохранён для проверки метода и данных.

Длинные снимки показывают затронутые области приложения. Нижняя навигация скрыта только на время
съёмки элемента, чтобы она не перекрывала содержимое при склейке кадра. Фокус, клавиатура, реальный
Telegram и фактическое поведение рабочего UI этими картинками не подтверждены.

## Предлагаемое поведение

- В подсказке к упражнению указан тип недели, последняя **сопоставимая** тренировка и причина
  рекомендации. При нехватке фактов нет предложения применить вес. Подробности раскрывают исходные
  ID подходов, коды причин и версию правила.
- В истории упражнений фильтр «Все / Лёгкая / Средняя / Тяжёлая» ограничивает только эту историю.
  Общие тренировки, рабочие подходы, объём и рекорды остаются общими. Пустой тип имеет явное
  состояние без вымышленного результата.
- Соседняя карточка «Предыдущий результат» сейчас читает общую историю упражнения, но называет её
  сопоставимой. В макете предлагается точечное уточнение: «Последний результат» / «По всей истории
  упражнения». Это отдельная правка `ActiveSessionSummary`, за пределами компонента подсказки;
  её нужно явно согласовать вместе с макетом. `TodayWorkout.tsx` не затрагивается.
- Групповое подтверждение тренером должно учитывать тип недели при группировке; каждое предложение
  по-прежнему подтверждается отдельно и использует собственные факты и версии подходов.

Для пользовательской реализации предполагаются существующий `SegmentedControl`, текущие токены,
русские подписи и проверка клавиатуры, состояний загрузки/ошибки и offline. Макет показывает данные
как пример: 4 общие тренировки, по 2 тяжёлых и средних, лёгких в периоде нет.

## Снимки

Все ссылки ниже относятся к одному пакету. Mobile: 320×844, 360×844, 393×844, 430×932; desktop:
1440×900. В таблице указаны размеры viewport, а не размеры вырезанной области.

### Dark

| Состояние | 320 | 360 | 393 | 430 | 1440 |
|---|---|---|---|---|---|
| Тренировка: тяжёлая | [320](workout-heavy-dark-320.png) | [360](workout-heavy-dark-360.png) | [393](workout-heavy-dark-393.png) | [430](workout-heavy-dark-430.png) | [1440](workout-heavy-dark-desktop.png) |
| Тренировка: средняя | [320](workout-medium-dark-320.png) | [360](workout-medium-dark-360.png) | [393](workout-medium-dark-393.png) | [430](workout-medium-dark-430.png) | [1440](workout-medium-dark-desktop.png) |
| Тренировка: лёгкая, нет истории | [320](workout-light-dark-320.png) | [360](workout-light-dark-360.png) | [393](workout-light-dark-393.png) | [430](workout-light-dark-430.png) | [1440](workout-light-dark-desktop.png) |
| Программа: тяжёлая | [320](program-heavy-dark-320.png) | [360](program-heavy-dark-360.png) | [393](program-heavy-dark-393.png) | [430](program-heavy-dark-430.png) | [1440](program-heavy-dark-desktop.png) |
| Программа: средняя | [320](program-medium-dark-320.png) | [360](program-medium-dark-360.png) | [393](program-medium-dark-393.png) | [430](program-medium-dark-430.png) | [1440](program-medium-dark-desktop.png) |
| Программа: лёгкая, нет истории | [320](program-light-dark-320.png) | [360](program-light-dark-360.png) | [393](program-light-dark-393.png) | [430](program-light-dark-430.png) | [1440](program-light-dark-desktop.png) |
| История: все | [320](analytics-all-dark-320.png) | [360](analytics-all-dark-360.png) | [393](analytics-all-dark-393.png) | [430](analytics-all-dark-430.png) | [1440](analytics-all-dark-desktop.png) |
| История: тяжёлая | [320](analytics-heavy-dark-320.png) | [360](analytics-heavy-dark-360.png) | [393](analytics-heavy-dark-393.png) | [430](analytics-heavy-dark-430.png) | [1440](analytics-heavy-dark-desktop.png) |
| История: средняя | [320](analytics-medium-dark-320.png) | [360](analytics-medium-dark-360.png) | [393](analytics-medium-dark-393.png) | [430](analytics-medium-dark-430.png) | [1440](analytics-medium-dark-desktop.png) |
| История: лёгкая, нет истории | [320](analytics-light-dark-320.png) | [360](analytics-light-dark-360.png) | [393](analytics-light-dark-393.png) | [430](analytics-light-dark-430.png) | [1440](analytics-light-dark-desktop.png) |

### Light

| Состояние | 320 | 360 | 393 | 430 | 1440 |
|---|---|---|---|---|---|
| Тренировка: тяжёлая | [320](workout-heavy-light-320.png) | [360](workout-heavy-light-360.png) | [393](workout-heavy-light-393.png) | [430](workout-heavy-light-430.png) | [1440](workout-heavy-light-desktop.png) |
| Тренировка: средняя | [320](workout-medium-light-320.png) | [360](workout-medium-light-360.png) | [393](workout-medium-light-393.png) | [430](workout-medium-light-430.png) | [1440](workout-medium-light-desktop.png) |
| Тренировка: лёгкая, нет истории | [320](workout-light-light-320.png) | [360](workout-light-light-360.png) | [393](workout-light-light-393.png) | [430](workout-light-light-430.png) | [1440](workout-light-light-desktop.png) |
| Программа: тяжёлая | [320](program-heavy-light-320.png) | [360](program-heavy-light-360.png) | [393](program-heavy-light-393.png) | [430](program-heavy-light-430.png) | [1440](program-heavy-light-desktop.png) |
| Программа: средняя | [320](program-medium-light-320.png) | [360](program-medium-light-360.png) | [393](program-medium-light-393.png) | [430](program-medium-light-430.png) | [1440](program-medium-light-desktop.png) |
| Программа: лёгкая, нет истории | [320](program-light-light-320.png) | [360](program-light-light-360.png) | [393](program-light-light-393.png) | [430](program-light-light-430.png) | [1440](program-light-light-desktop.png) |
| История: все | [320](analytics-all-light-320.png) | [360](analytics-all-light-360.png) | [393](analytics-all-light-393.png) | [430](analytics-all-light-430.png) | [1440](analytics-all-light-desktop.png) |
| История: тяжёлая | [320](analytics-heavy-light-320.png) | [360](analytics-heavy-light-360.png) | [393](analytics-heavy-light-393.png) | [430](analytics-heavy-light-430.png) | [1440](analytics-heavy-light-desktop.png) |
| История: средняя | [320](analytics-medium-light-320.png) | [360](analytics-medium-light-360.png) | [393](analytics-medium-light-393.png) | [430](analytics-medium-light-430.png) | [1440](analytics-medium-light-desktop.png) |
| История: лёгкая, нет истории | [320](analytics-light-light-320.png) | [360](analytics-light-light-360.png) | [393](analytics-light-light-393.png) | [430](analytics-light-light-430.png) | [1440](analytics-light-light-desktop.png) |

### Раскрытые доказательства

| Контекст | Dark 393 | Light 393 | Dark 1440 | Light 1440 |
|---|---|---|---|---|
| Тренировка | [dark 393](workout-heavy-details-dark-393.png) | [light 393](workout-heavy-details-light-393.png) | [dark desktop](workout-heavy-details-dark-desktop.png) | [light desktop](workout-heavy-details-light-desktop.png) |
| Назначенная программа | [dark 393](program-heavy-details-dark-393.png) | [light 393](program-heavy-details-light-393.png) | [dark desktop](program-heavy-details-dark-desktop.png) | [light desktop](program-heavy-details-light-desktop.png) |
