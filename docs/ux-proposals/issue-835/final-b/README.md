# #835 — вариант B, повторная визуальная приёмка

Выбранный владельцем календарный год: 12 месяцев, 3 столбца и 4 строки. Нажатие на месяц открывает увеличенный календарь; список из 365/366 дат удалён. Таблица по дням сохранена.

Клавиатура: открытие месяца переводит фокус на выбранный либо первый доступный день; стрелки перемещают фокус, Home/End — границы недели, ввод/пробел выбирают день, Escape сворачивает месяц и возвращает фокус. Будущие дни недоступны. При переключении года выбранный день и раскрытый месяц сбрасываются. Метки дат и фактов доступны экранному диктору; выбор объявляется через aria-live.

## Источники снимков

- Корневые PNG: изолированный React preview той же реализации, синтетические данные на 29 октября 2026 года. Chromium; 320×844, 390×844, 430×844, 1440×1000. Обе темы. Состояния: overview, month, unknown, future, empty, table. Снимки table ограничены viewport; остальные full-page.
- after/: настоящий экран «Прогресс → Тренировки» с перехваченным тестовым API. Chromium и WebKit, обе темы. Состояния: overview, month, selected, future. Тестовая история намеренно неполная, текущий год ограничен 30 января для проверки будущих дат. Это локальный браузер, не production и не физическое устройство.
- Никаких персональных данных в пакете нет. Предыдущие A/B-пакеты оставлены как история; принимать нужно только этот пакет B.

## Пакет макетов

| Тема / ширина | Обзор | Месяц | Неизвестно | Будущие дни | Пусто | Таблица |
| --- | --- | --- | --- | --- | --- | --- |
| dark / 320 | [overview](dark-320-overview.png) | [month](dark-320-month.png) | [unknown](dark-320-unknown.png) | [future](dark-320-future.png) | [empty](dark-320-empty.png) | [table](dark-320-table.png) |
| dark / 390 | [overview](dark-390-overview.png) | [month](dark-390-month.png) | [unknown](dark-390-unknown.png) | [future](dark-390-future.png) | [empty](dark-390-empty.png) | [table](dark-390-table.png) |
| dark / 430 | [overview](dark-430-overview.png) | [month](dark-430-month.png) | [unknown](dark-430-unknown.png) | [future](dark-430-future.png) | [empty](dark-430-empty.png) | [table](dark-430-table.png) |
| dark / 1440 | [overview](dark-1440-overview.png) | [month](dark-1440-month.png) | [unknown](dark-1440-unknown.png) | [future](dark-1440-future.png) | [empty](dark-1440-empty.png) | [table](dark-1440-table.png) |
| light / 320 | [overview](light-320-overview.png) | [month](light-320-month.png) | [unknown](light-320-unknown.png) | [future](light-320-future.png) | [empty](light-320-empty.png) | [table](light-320-table.png) |
| light / 390 | [overview](light-390-overview.png) | [month](light-390-month.png) | [unknown](light-390-unknown.png) | [future](light-390-future.png) | [empty](light-390-empty.png) | [table](light-390-table.png) |
| light / 430 | [overview](light-430-overview.png) | [month](light-430-month.png) | [unknown](light-430-unknown.png) | [future](light-430-future.png) | [empty](light-430-empty.png) | [table](light-430-table.png) |
| light / 1440 | [overview](light-1440-overview.png) | [month](light-1440-month.png) | [unknown](light-1440-unknown.png) | [future](light-1440-future.png) | [empty](light-1440-empty.png) | [table](light-1440-table.png) |

## Реальный AFTER

| Браузер / тема / ширина | Обзор | Месяц | Выбор | Будущие дни |
| --- | --- | --- | --- | --- |
| chromium / dark / 320 | [overview](after/chromium-dark-320-overview.png) | [month](after/chromium-dark-320-month.png) | [selected](after/chromium-dark-320-selected.png) | [future](after/chromium-dark-320-future.png) |
| chromium / dark / 390 | [overview](after/chromium-dark-390-overview.png) | [month](after/chromium-dark-390-month.png) | [selected](after/chromium-dark-390-selected.png) | [future](after/chromium-dark-390-future.png) |
| chromium / dark / 430 | [overview](after/chromium-dark-430-overview.png) | [month](after/chromium-dark-430-month.png) | [selected](after/chromium-dark-430-selected.png) | [future](after/chromium-dark-430-future.png) |
| chromium / light / 320 | [overview](after/chromium-light-320-overview.png) | [month](after/chromium-light-320-month.png) | [selected](after/chromium-light-320-selected.png) | [future](after/chromium-light-320-future.png) |
| chromium / light / 390 | [overview](after/chromium-light-390-overview.png) | [month](after/chromium-light-390-month.png) | [selected](after/chromium-light-390-selected.png) | [future](after/chromium-light-390-future.png) |
| chromium / light / 430 | [overview](after/chromium-light-430-overview.png) | [month](after/chromium-light-430-month.png) | [selected](after/chromium-light-430-selected.png) | [future](after/chromium-light-430-future.png) |
| webkit / dark / 320 | [overview](after/webkit-dark-320-overview.png) | [month](after/webkit-dark-320-month.png) | [selected](after/webkit-dark-320-selected.png) | [future](after/webkit-dark-320-future.png) |
| webkit / dark / 390 | [overview](after/webkit-dark-390-overview.png) | [month](after/webkit-dark-390-month.png) | [selected](after/webkit-dark-390-selected.png) | [future](after/webkit-dark-390-future.png) |
| webkit / dark / 430 | [overview](after/webkit-dark-430-overview.png) | [month](after/webkit-dark-430-month.png) | [selected](after/webkit-dark-430-selected.png) | [future](after/webkit-dark-430-future.png) |
| webkit / light / 320 | [overview](after/webkit-light-320-overview.png) | [month](after/webkit-light-320-month.png) | [selected](after/webkit-light-320-selected.png) | [future](after/webkit-light-320-future.png) |
| webkit / light / 390 | [overview](after/webkit-light-390-overview.png) | [month](after/webkit-light-390-month.png) | [selected](after/webkit-light-390-selected.png) | [future](after/webkit-light-390-future.png) |
| webkit / light / 430 | [overview](after/webkit-light-430-overview.png) | [month](after/webkit-light-430-month.png) | [selected](after/webkit-light-430-selected.png) | [future](after/webkit-light-430-future.png) |

## Проверки и границы

- 1055 frontend unit-тестов PASS; typecheck, lint, сборка и бюджет производительности PASS.
- 12 E2E PASS: Chromium/WebKit × 320/390/430 × Dark/Light. Проверяются фокус, размеры целей, выбор дня, високосный год, возврат к текущему году, запрет будущих дат, таблица и отсутствие горизонтального переполнения.
- Форматирование проверено командой CI `npx prettier --check . --end-of-line auto`; обычная локальная команда без auto сообщает CRLF в неизменённых файлах Windows checkout.
- Физический VoiceOver и другие настоящие экранные дикторы: NOT_VERIFIED. DOM-семантика и клавиатура проверены браузерной автоматизацией; WebKit не доказывает VoiceOver.
- Решение владельца требуется по финальному B и реальному AFTER. Приёмка не разрешает merge/deploy; release approval отдельно. CI нужно проверять на HEAD PR #1317.
