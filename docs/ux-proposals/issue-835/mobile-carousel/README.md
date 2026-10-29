# #835 — один месяц на мобильном экране

Текущий пакет заменяет мобильную сетку из `final-b`. Desktop сохраняет 12 месяцев 3×4. PR #1317, backend и миграции в этой доработке не менялись.

На 320–430 px показан один крупный месяц: понедельник–воскресенье, прямой выбор дня, стрелки, счётчик положения и нативный горизонтальный scroll-snap. Между декабрём и январём нет циклического перехода. Текущий год открывается на текущем месяце в часовом поясе аккаунта, прошлые — на январе. Выбранная дата сохраняется при перелистывании; смена года сбрасывает её и начальный месяц. Неизвестная история, подтверждённый ноль, активность и будущие дни различаются. Таблица и легенда сохранены.

## Демонстрация

[Короткая запись плавных переходов и настоящих touch-событий Chromium](swipe-demo.webm). Эмуляция 390×844, Dark, обычный motion: смена года, выбор 29 февраля, перелистывание, горизонтальные и вертикальный touch-жесты. Это локальный тестовый браузер, не физический телефон.

## Настоящий AFTER

Все снимки сделаны в настоящем разделе «Прогресс → Тренировки», с перехваченным синтетическим API. Съёмка через page screenshot сохраняет layout viewport; снимки больших элементов могли менять размер viewport и сбивать вложенную прокрутку, поэтому они не используются в этом пакете.

Chromium и WebKit; Dark/Light; mobile 320×844, 360×844, 390×844, 430×844; desktop 1440×1000. Overview — полная страница; остальные кадры — viewport после действия. PNG в WebKit может иметь другую физическую ширину из-за device scale factor.

Тестовые данные: текущий год намеренно ограничен 30 января для проверки будущих дней; 2024 содержит неизвестные значения, одну тренировку/4 подхода 27 января и подтверждённый ноль 28 января; 2023 — подтверждённо пустой год. Это не данные владельца и не восстановленная история.

| Браузер / тема / ширина | Обзор | Месяц | Неизвестно | Выбор | Будущие дни | Таблица | Пусто |
| --- | --- | --- | --- | --- | --- | --- | --- |
| chromium / dark / 320 | [overview](after/chromium-dark-320-overview.png) | [month](after/chromium-dark-320-month.png) | [unknown](after/chromium-dark-320-unknown.png) | [selected](after/chromium-dark-320-selected.png) | [future](after/chromium-dark-320-future.png) | [table](after/chromium-dark-320-table.png) | [empty](after/chromium-dark-320-empty.png) |
| chromium / dark / 360 | [overview](after/chromium-dark-360-overview.png) | [month](after/chromium-dark-360-month.png) | [unknown](after/chromium-dark-360-unknown.png) | [selected](after/chromium-dark-360-selected.png) | [future](after/chromium-dark-360-future.png) | [table](after/chromium-dark-360-table.png) | [empty](after/chromium-dark-360-empty.png) |
| chromium / dark / 390 | [overview](after/chromium-dark-390-overview.png) | [month](after/chromium-dark-390-month.png) | [unknown](after/chromium-dark-390-unknown.png) | [selected](after/chromium-dark-390-selected.png) | [future](after/chromium-dark-390-future.png) | [table](after/chromium-dark-390-table.png) | [empty](after/chromium-dark-390-empty.png) |
| chromium / dark / 430 | [overview](after/chromium-dark-430-overview.png) | [month](after/chromium-dark-430-month.png) | [unknown](after/chromium-dark-430-unknown.png) | [selected](after/chromium-dark-430-selected.png) | [future](after/chromium-dark-430-future.png) | [table](after/chromium-dark-430-table.png) | [empty](after/chromium-dark-430-empty.png) |
| chromium / dark / 1440 | [overview](after/chromium-dark-1440-overview.png) | [month](after/chromium-dark-1440-month.png) | — | [selected](after/chromium-dark-1440-selected.png) | [future](after/chromium-dark-1440-future.png) | [table](after/chromium-dark-1440-table.png) | [empty](after/chromium-dark-1440-empty.png) |
| chromium / light / 320 | [overview](after/chromium-light-320-overview.png) | [month](after/chromium-light-320-month.png) | [unknown](after/chromium-light-320-unknown.png) | [selected](after/chromium-light-320-selected.png) | [future](after/chromium-light-320-future.png) | [table](after/chromium-light-320-table.png) | [empty](after/chromium-light-320-empty.png) |
| chromium / light / 360 | [overview](after/chromium-light-360-overview.png) | [month](after/chromium-light-360-month.png) | [unknown](after/chromium-light-360-unknown.png) | [selected](after/chromium-light-360-selected.png) | [future](after/chromium-light-360-future.png) | [table](after/chromium-light-360-table.png) | [empty](after/chromium-light-360-empty.png) |
| chromium / light / 390 | [overview](after/chromium-light-390-overview.png) | [month](after/chromium-light-390-month.png) | [unknown](after/chromium-light-390-unknown.png) | [selected](after/chromium-light-390-selected.png) | [future](after/chromium-light-390-future.png) | [table](after/chromium-light-390-table.png) | [empty](after/chromium-light-390-empty.png) |
| chromium / light / 430 | [overview](after/chromium-light-430-overview.png) | [month](after/chromium-light-430-month.png) | [unknown](after/chromium-light-430-unknown.png) | [selected](after/chromium-light-430-selected.png) | [future](after/chromium-light-430-future.png) | [table](after/chromium-light-430-table.png) | [empty](after/chromium-light-430-empty.png) |
| chromium / light / 1440 | [overview](after/chromium-light-1440-overview.png) | [month](after/chromium-light-1440-month.png) | — | [selected](after/chromium-light-1440-selected.png) | [future](after/chromium-light-1440-future.png) | [table](after/chromium-light-1440-table.png) | [empty](after/chromium-light-1440-empty.png) |
| webkit / dark / 320 | [overview](after/webkit-dark-320-overview.png) | [month](after/webkit-dark-320-month.png) | [unknown](after/webkit-dark-320-unknown.png) | [selected](after/webkit-dark-320-selected.png) | [future](after/webkit-dark-320-future.png) | [table](after/webkit-dark-320-table.png) | [empty](after/webkit-dark-320-empty.png) |
| webkit / dark / 360 | [overview](after/webkit-dark-360-overview.png) | [month](after/webkit-dark-360-month.png) | [unknown](after/webkit-dark-360-unknown.png) | [selected](after/webkit-dark-360-selected.png) | [future](after/webkit-dark-360-future.png) | [table](after/webkit-dark-360-table.png) | [empty](after/webkit-dark-360-empty.png) |
| webkit / dark / 390 | [overview](after/webkit-dark-390-overview.png) | [month](after/webkit-dark-390-month.png) | [unknown](after/webkit-dark-390-unknown.png) | [selected](after/webkit-dark-390-selected.png) | [future](after/webkit-dark-390-future.png) | [table](after/webkit-dark-390-table.png) | [empty](after/webkit-dark-390-empty.png) |
| webkit / dark / 430 | [overview](after/webkit-dark-430-overview.png) | [month](after/webkit-dark-430-month.png) | [unknown](after/webkit-dark-430-unknown.png) | [selected](after/webkit-dark-430-selected.png) | [future](after/webkit-dark-430-future.png) | [table](after/webkit-dark-430-table.png) | [empty](after/webkit-dark-430-empty.png) |
| webkit / dark / 1440 | [overview](after/webkit-dark-1440-overview.png) | [month](after/webkit-dark-1440-month.png) | — | [selected](after/webkit-dark-1440-selected.png) | [future](after/webkit-dark-1440-future.png) | [table](after/webkit-dark-1440-table.png) | [empty](after/webkit-dark-1440-empty.png) |
| webkit / light / 320 | [overview](after/webkit-light-320-overview.png) | [month](after/webkit-light-320-month.png) | [unknown](after/webkit-light-320-unknown.png) | [selected](after/webkit-light-320-selected.png) | [future](after/webkit-light-320-future.png) | [table](after/webkit-light-320-table.png) | [empty](after/webkit-light-320-empty.png) |
| webkit / light / 360 | [overview](after/webkit-light-360-overview.png) | [month](after/webkit-light-360-month.png) | [unknown](after/webkit-light-360-unknown.png) | [selected](after/webkit-light-360-selected.png) | [future](after/webkit-light-360-future.png) | [table](after/webkit-light-360-table.png) | [empty](after/webkit-light-360-empty.png) |
| webkit / light / 390 | [overview](after/webkit-light-390-overview.png) | [month](after/webkit-light-390-month.png) | [unknown](after/webkit-light-390-unknown.png) | [selected](after/webkit-light-390-selected.png) | [future](after/webkit-light-390-future.png) | [table](after/webkit-light-390-table.png) | [empty](after/webkit-light-390-empty.png) |
| webkit / light / 430 | [overview](after/webkit-light-430-overview.png) | [month](after/webkit-light-430-month.png) | [unknown](after/webkit-light-430-unknown.png) | [selected](after/webkit-light-430-selected.png) | [future](after/webkit-light-430-future.png) | [table](after/webkit-light-430-table.png) | [empty](after/webkit-light-430-empty.png) |
| webkit / light / 1440 | [overview](after/webkit-light-1440-overview.png) | [month](after/webkit-light-1440-month.png) | — | [selected](after/webkit-light-1440-selected.png) | [future](after/webkit-light-1440-future.png) | [table](after/webkit-light-1440-table.png) | [empty](after/webkit-light-1440-empty.png) |

## Проверки

- 1074 frontend unit-теста; 19 целевых тестов календаря/Прогресса, включая timezone на границе месяца/года и reduced motion.
- 20 E2E: Chromium/WebKit × 320/360/390/430/1440 × Dark/Light. Кнопки, 12 месяцев, точное выравнивание одного месяца, ширина ячеек в пределах 1/7 календаря, нативная горизонтальная прокрутка, сохранение выбора, смена года, високосный февраль, будущие/неизвестные/нулевые/пустые данные, клавиатура, таблица и отсутствие page overflow.
- В Chromium дополнительно dispatchTouchEvent: свайп вперёд/назад и вертикальный жест, который не меняет месяц. В WebKit проверены wheel scrolling и кнопки; физический touch на iOS не проверен.
- Отдельный Chromium E2E с обычным motion и видеозаписью; основная матрица с reduced motion.
- Typecheck, lint, `npx prettier --check . --end-of-line auto`, build и perf:check.
- Невидимые месяцы inert/aria-hidden; активен ровно один месяц. Даты имеют полные русские имена и факты, выбранная дата — aria-pressed, изменения объявляются через aria-live; нативная таблица доступна отдельно. Это проверка DOM и клавиатуры, не полная аттестация WCAG.
- Физические VoiceOver/другие экранные дикторы и Telegram WebView: NOT_VERIFIED.

Точные результаты CI публикуются в Issue #835 и PR #1317 на финальном SHA. Требуется новая визуальная приёмка этого пакета. Она не разрешает merge/deploy. Env change required: no; PR в целом содержит ранее подготовленную миграцию, она не изменена этой доработкой. #1201 HOLD.
