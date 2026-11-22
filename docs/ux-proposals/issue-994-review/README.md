# #994 — единый визуальный пакет для рассмотрения

**Проверенная база:** [`17c5f299`](https://github.com/MikeMoore1337/your-fitness-coach/commit/17c5f29921f379d1f5229eede40c88d5183ddcf9), dev. Данные синтетические. Ветка содержит только материалы этого пакета; код приложения не изменён.

## Решение на рассмотрение

Единый предлагаемый вариант: сохранить показанные композиции, цвета, типографику, материалы и семантику в наблюдавшихся состояниях. Исправить выявленное пересечение шапки на сверхузкой доступной ширине переносом кнопки профиля на следующую строку по существующему приёму Today. Ни Dock 4+1, ни маршруты, ни бизнес-логика не меняются. Это ограниченное решение по показанным состояниям, а не утверждение, что весь #994 проверен или реализован.

Прототип шапки получен временным CSS в браузере. На обычных 393/1280 px предложение сохраняет текущий вид; при результирующей ширине 196 CSS px — показанный перенос. Предложение не является фактической реализацией, а снимки остальных экранов — текущий render, предлагаемый к сохранению.

## Обнаруженная проблема и вариант

При настоящем Chromium zoom 200% с исходной ширины 393 px словесный знак пересекает кнопку профиля на четырёх разделах. Контейнер текста остаётся в пределах, но сами строки выходят за его край: замер сделан через `Range.getClientRects()`. Перенос увеличивает высоту шапки и требует проверки короткого экрана, клавиатуры, фокуса и safe-area при реализации.

| Экран | Light: до | Light: вариант | Dark: до | Dark: вариант |
|---|---|---|---|---|
| Plan | [до](screens/header-programs-light-before.png) | [вариант](screens/header-programs-light-proposal.png) | [до](screens/header-programs-dark-before.png) | [вариант](screens/header-programs-dark-proposal.png) |
| Nutrition | [до](screens/header-nutrition-light-before.png) | [вариант](screens/header-nutrition-light-proposal.png) | [до](screens/header-nutrition-dark-before.png) | [вариант](screens/header-nutrition-dark-proposal.png) |
| Progress | [до](screens/header-progress-light-before.png) | [вариант](screens/header-progress-light-proposal.png) | [до](screens/header-progress-dark-before.png) | [вариант](screens/header-progress-dark-proposal.png) |
| Profile | [до](screens/header-profile-light-before.png) | [вариант](screens/header-profile-light-proposal.png) | [до](screens/header-profile-dark-before.png) | [вариант](screens/header-profile-dark-proposal.png) |

Источник: [`AppShell.tsx`](https://github.com/MikeMoore1337/your-fitness-coach/blob/17c5f29921f379d1f5229eede40c88d5183ddcf9/frontend/src/app/AppShell.tsx), [`ux-ia-redesign.css`](https://github.com/MikeMoore1337/your-fitness-coach/blob/17c5f29921f379d1f5229eede40c88d5183ddcf9/frontend/src/styles/ux-ia-redesign.css). [Замеры Light](metrics/header-light-geometry.json), [замеры Dark](metrics/header-dark-geometry.json).

## Экраны: текущий вид, предложенный к сохранению

Полностраничные снимки: закреплённая панель может находиться в середине изображения из-за способа съёмки. Это не свидетельство перекрытия после прокрутки. Все размеры — CSS px. Два снимка Today в WebKit на 1440 px отдельно пересняты с `scale: css`.

| Экран | Chromium 393 Light | Chromium 393 Dark | WebKit 393 Light | WebKit 393 Dark | Chromium 1280 Light | Chromium 1280 Dark | WebKit 1280 Light | WebKit 1280 Dark |
|---|---|---|---|---|---|---|---|---|
| Today | [chromium 393 light](screens/chromium-393-light-today.png) | [chromium 393 dark](screens/chromium-393-dark-today.png) | [webkit 393 light](screens/webkit-393-light-today.png) | [webkit 393 dark](screens/webkit-393-dark-today.png) | [chromium 1280 light](screens/chromium-1280-light-today.png) | [chromium 1280 dark](screens/chromium-1280-dark-today.png) | [webkit 1280 light](screens/webkit-1280-light-today.png) | [webkit 1280 dark](screens/webkit-1280-dark-today.png) |
| Active Workout | [chromium 393 light](screens/chromium-393-light-active-workout.png) | [chromium 393 dark](screens/chromium-393-dark-active-workout.png) | [webkit 393 light](screens/webkit-393-light-active-workout.png) | [webkit 393 dark](screens/webkit-393-dark-active-workout.png) | [chromium 1280 light](screens/chromium-1280-light-active-workout.png) | [chromium 1280 dark](screens/chromium-1280-dark-active-workout.png) | [webkit 1280 light](screens/webkit-1280-light-active-workout.png) | [webkit 1280 dark](screens/webkit-1280-dark-active-workout.png) |
| Plan | [chromium 393 light](screens/chromium-393-light-programs.png) | [chromium 393 dark](screens/chromium-393-dark-programs.png) | [webkit 393 light](screens/webkit-393-light-programs.png) | [webkit 393 dark](screens/webkit-393-dark-programs.png) | [chromium 1280 light](screens/chromium-1280-light-programs.png) | [chromium 1280 dark](screens/chromium-1280-dark-programs.png) | [webkit 1280 light](screens/webkit-1280-light-programs.png) | [webkit 1280 dark](screens/webkit-1280-dark-programs.png) |
| Program Editor | [chromium 393 light](screens/chromium-393-light-program-editor.png) | [chromium 393 dark](screens/chromium-393-dark-program-editor.png) | [webkit 393 light](screens/webkit-393-light-program-editor.png) | [webkit 393 dark](screens/webkit-393-dark-program-editor.png) | [chromium 1280 light](screens/chromium-1280-light-program-editor.png) | [chromium 1280 dark](screens/chromium-1280-dark-program-editor.png) | [webkit 1280 light](screens/webkit-1280-light-program-editor.png) | [webkit 1280 dark](screens/webkit-1280-dark-program-editor.png) |
| Nutrition | [chromium 393 light](screens/chromium-393-light-nutrition.png) | [chromium 393 dark](screens/chromium-393-dark-nutrition.png) | [webkit 393 light](screens/webkit-393-light-nutrition.png) | [webkit 393 dark](screens/webkit-393-dark-nutrition.png) | [chromium 1280 light](screens/chromium-1280-light-nutrition.png) | [chromium 1280 dark](screens/chromium-1280-dark-nutrition.png) | [webkit 1280 light](screens/webkit-1280-light-nutrition.png) | [webkit 1280 dark](screens/webkit-1280-dark-nutrition.png) |
| Hydration | [chromium 393 light](screens/chromium-393-light-hydration.png) | [chromium 393 dark](screens/chromium-393-dark-hydration.png) | [webkit 393 light](screens/webkit-393-light-hydration.png) | [webkit 393 dark](screens/webkit-393-dark-hydration.png) | [chromium 1280 light](screens/chromium-1280-light-hydration.png) | [chromium 1280 dark](screens/chromium-1280-dark-hydration.png) | [webkit 1280 light](screens/webkit-1280-light-hydration.png) | [webkit 1280 dark](screens/webkit-1280-dark-hydration.png) |
| Быстрый ввод | [chromium 393 light](screens/chromium-393-light-food-quick.png) | [chromium 393 dark](screens/chromium-393-dark-food-quick.png) | [webkit 393 light](screens/webkit-393-light-food-quick.png) | [webkit 393 dark](screens/webkit-393-dark-food-quick.png) | [chromium 1280 light](screens/chromium-1280-light-food-quick.png) | [chromium 1280 dark](screens/chromium-1280-dark-food-quick.png) | [webkit 1280 light](screens/webkit-1280-light-food-quick.png) | [webkit 1280 dark](screens/webkit-1280-dark-food-quick.png) |
| Progress | [chromium 393 light](screens/chromium-393-light-progress.png) | [chromium 393 dark](screens/chromium-393-dark-progress.png) | [webkit 393 light](screens/webkit-393-light-progress.png) | [webkit 393 dark](screens/webkit-393-dark-progress.png) | [chromium 1280 light](screens/chromium-1280-light-progress.png) | [chromium 1280 dark](screens/chromium-1280-dark-progress.png) | [webkit 1280 light](screens/webkit-1280-light-progress.png) | [webkit 1280 dark](screens/webkit-1280-dark-progress.png) |
| Profile | [chromium 393 light](screens/chromium-393-light-profile.png) | [chromium 393 dark](screens/chromium-393-dark-profile.png) | [webkit 393 light](screens/webkit-393-light-profile.png) | [webkit 393 dark](screens/webkit-393-dark-profile.png) | [chromium 1280 light](screens/chromium-1280-light-profile.png) | [chromium 1280 dark](screens/chromium-1280-dark-profile.png) | [webkit 1280 light](screens/webkit-1280-light-profile.png) | [webkit 1280 dark](screens/webkit-1280-dark-profile.png) |
| Coach OS | [chromium 393 light](screens/chromium-393-light-coach.png) | [chromium 393 dark](screens/chromium-393-dark-coach.png) | [webkit 393 light](screens/webkit-393-light-coach.png) | [webkit 393 dark](screens/webkit-393-dark-coach.png) | [chromium 1280 light](screens/chromium-1280-light-coach.png) | [chromium 1280 dark](screens/chromium-1280-dark-coach.png) | [webkit 1280 light](screens/webkit-1280-light-coach.png) | [webkit 1280 dark](screens/webkit-1280-dark-coach.png) |

## Выбранные состояния: текущий вид

| Состояние | Chromium Light | Chromium Dark | WebKit Light | WebKit Dark |
|---|---|---|---|---|
| Меню быстрого добавления | [chromium light](screens/chromium-393-light-dock-quick-menu.png) | [chromium dark](screens/chromium-393-dark-dock-quick-menu.png) | [webkit light](screens/webkit-393-light-dock-quick-menu.png) | [webkit dark](screens/webkit-393-dark-dock-quick-menu.png) |
| Профиль: раскрытие | [chromium light](screens/chromium-393-light-profile-expanded.png) | [chromium dark](screens/chromium-393-dark-profile-expanded.png) | [webkit light](screens/webkit-393-light-profile-expanded.png) | [webkit dark](screens/webkit-393-dark-profile-expanded.png) |
| Поиск упражнения | [chromium light](screens/chromium-393-light-exercise-search.png) | [chromium dark](screens/chromium-393-dark-exercise-search.png) | [webkit light](screens/webkit-393-light-exercise-search.png) | [webkit dark](screens/webkit-393-dark-exercise-search.png) |
| Вода: другая порция | [chromium light](screens/chromium-393-light-hydration-custom.png) | [chromium dark](screens/chromium-393-dark-hydration-custom.png) | [webkit light](screens/webkit-393-light-hydration-custom.png) | [webkit dark](screens/webkit-393-dark-hydration-custom.png) |
| Вода: ошибка | [chromium light](screens/chromium-393-light-hydration-error.png) | [chromium dark](screens/chromium-393-dark-hydration-error.png) | [webkit light](screens/webkit-393-light-hydration-error.png) | [webkit dark](screens/webkit-393-dark-hydration-error.png) |
| Кнопка: hover | [chromium light](screens/chromium-393-light-button-hover.png) | [chromium dark](screens/chromium-393-dark-button-hover.png) | [webkit light](screens/webkit-393-light-button-hover.png) | [webkit dark](screens/webkit-393-dark-button-hover.png) |
| Кнопка: focus | [chromium light](screens/chromium-393-light-button-focus.png) | [chromium dark](screens/chromium-393-dark-button-focus.png) | [webkit light](screens/webkit-393-light-button-focus.png) | [webkit dark](screens/webkit-393-dark-button-focus.png) |
| Кнопка: pressed | [chromium light](screens/chromium-393-light-button-pressed.png) | [chromium dark](screens/chromium-393-dark-button-pressed.png) | [webkit light](screens/webkit-393-light-button-pressed.png) | [webkit dark](screens/webkit-393-dark-button-pressed.png) |

Эмуляция TMA, активная тренировка и фокус поля:

| Ориентация | Chromium Light | Chromium Dark | WebKit Light | WebKit Dark |
|---|---|---|---|---|
| 393x852 | [chromium light](screens/chromium-393x852-light-tma-workout-focus.png) | [chromium dark](screens/chromium-393x852-dark-tma-workout-focus.png) | [webkit light](screens/webkit-393x852-light-tma-workout-focus.png) | [webkit dark](screens/webkit-393x852-dark-tma-workout-focus.png) |
| 852x393 | [chromium light](screens/chromium-852x393-light-tma-workout-focus.png) | [chromium dark](screens/chromium-852x393-dark-tma-workout-focus.png) | [webkit light](screens/webkit-852x393-light-tma-workout-focus.png) | [webkit dark](screens/webkit-852x393-dark-tma-workout-focus.png) |

## Дополнительные размеры основных разделов

| Экран | Ширина | Chromium Light | Chromium Dark | WebKit Light | WebKit Dark |
|---|---:|---|---|---|---|
| Today | 320 | [chromium light](screens/chromium-320-light-today.png) | [chromium dark](screens/chromium-320-dark-today.png) | [webkit light](screens/webkit-320-light-today.png) | [webkit dark](screens/webkit-320-dark-today.png) |
| Today | 360 | [chromium light](screens/chromium-360-light-today.png) | [chromium dark](screens/chromium-360-dark-today.png) | [webkit light](screens/webkit-360-light-today.png) | [webkit dark](screens/webkit-360-dark-today.png) |
| Today | 390 | [chromium light](screens/chromium-390-light-today.png) | [chromium dark](screens/chromium-390-dark-today.png) | [webkit light](screens/webkit-390-light-today.png) | [webkit dark](screens/webkit-390-dark-today.png) |
| Today | 430 | [chromium light](screens/chromium-430-light-today.png) | [chromium dark](screens/chromium-430-dark-today.png) | [webkit light](screens/webkit-430-light-today.png) | [webkit dark](screens/webkit-430-dark-today.png) |
| Today | 768 | [chromium light](screens/chromium-768-light-today.png) | [chromium dark](screens/chromium-768-dark-today.png) | [webkit light](screens/webkit-768-light-today.png) | [webkit dark](screens/webkit-768-dark-today.png) |
| Today | 1024 | [chromium light](screens/chromium-1024-light-today.png) | [chromium dark](screens/chromium-1024-dark-today.png) | [webkit light](screens/webkit-1024-light-today.png) | [webkit dark](screens/webkit-1024-dark-today.png) |
| Today | 1440 | [chromium light](screens/chromium-1440-light-today.png) | [chromium dark](screens/chromium-1440-dark-today.png) | [webkit light](screens/webkit-1440-light-today.png) | [webkit dark](screens/webkit-1440-dark-today.png) |
| Plan | 320 | [chromium light](screens/chromium-320-light-programs.png) | [chromium dark](screens/chromium-320-dark-programs.png) | [webkit light](screens/webkit-320-light-programs.png) | [webkit dark](screens/webkit-320-dark-programs.png) |
| Plan | 360 | [chromium light](screens/chromium-360-light-programs.png) | [chromium dark](screens/chromium-360-dark-programs.png) | [webkit light](screens/webkit-360-light-programs.png) | [webkit dark](screens/webkit-360-dark-programs.png) |
| Plan | 390 | [chromium light](screens/chromium-390-light-programs.png) | [chromium dark](screens/chromium-390-dark-programs.png) | [webkit light](screens/webkit-390-light-programs.png) | [webkit dark](screens/webkit-390-dark-programs.png) |
| Plan | 430 | [chromium light](screens/chromium-430-light-programs.png) | [chromium dark](screens/chromium-430-dark-programs.png) | [webkit light](screens/webkit-430-light-programs.png) | [webkit dark](screens/webkit-430-dark-programs.png) |
| Plan | 768 | [chromium light](screens/chromium-768-light-programs.png) | [chromium dark](screens/chromium-768-dark-programs.png) | [webkit light](screens/webkit-768-light-programs.png) | [webkit dark](screens/webkit-768-dark-programs.png) |
| Plan | 1024 | [chromium light](screens/chromium-1024-light-programs.png) | [chromium dark](screens/chromium-1024-dark-programs.png) | [webkit light](screens/webkit-1024-light-programs.png) | [webkit dark](screens/webkit-1024-dark-programs.png) |
| Plan | 1440 | [chromium light](screens/chromium-1440-light-programs.png) | [chromium dark](screens/chromium-1440-dark-programs.png) | [webkit light](screens/webkit-1440-light-programs.png) | [webkit dark](screens/webkit-1440-dark-programs.png) |
| Nutrition | 320 | [chromium light](screens/chromium-320-light-nutrition.png) | [chromium dark](screens/chromium-320-dark-nutrition.png) | [webkit light](screens/webkit-320-light-nutrition.png) | [webkit dark](screens/webkit-320-dark-nutrition.png) |
| Nutrition | 360 | [chromium light](screens/chromium-360-light-nutrition.png) | [chromium dark](screens/chromium-360-dark-nutrition.png) | [webkit light](screens/webkit-360-light-nutrition.png) | [webkit dark](screens/webkit-360-dark-nutrition.png) |
| Nutrition | 390 | [chromium light](screens/chromium-390-light-nutrition.png) | [chromium dark](screens/chromium-390-dark-nutrition.png) | [webkit light](screens/webkit-390-light-nutrition.png) | [webkit dark](screens/webkit-390-dark-nutrition.png) |
| Nutrition | 430 | [chromium light](screens/chromium-430-light-nutrition.png) | [chromium dark](screens/chromium-430-dark-nutrition.png) | [webkit light](screens/webkit-430-light-nutrition.png) | [webkit dark](screens/webkit-430-dark-nutrition.png) |
| Nutrition | 768 | [chromium light](screens/chromium-768-light-nutrition.png) | [chromium dark](screens/chromium-768-dark-nutrition.png) | [webkit light](screens/webkit-768-light-nutrition.png) | [webkit dark](screens/webkit-768-dark-nutrition.png) |
| Nutrition | 1024 | [chromium light](screens/chromium-1024-light-nutrition.png) | [chromium dark](screens/chromium-1024-dark-nutrition.png) | [webkit light](screens/webkit-1024-light-nutrition.png) | [webkit dark](screens/webkit-1024-dark-nutrition.png) |
| Nutrition | 1440 | [chromium light](screens/chromium-1440-light-nutrition.png) | [chromium dark](screens/chromium-1440-dark-nutrition.png) | [webkit light](screens/webkit-1440-light-nutrition.png) | [webkit dark](screens/webkit-1440-dark-nutrition.png) |
| Progress | 320 | [chromium light](screens/chromium-320-light-progress.png) | [chromium dark](screens/chromium-320-dark-progress.png) | [webkit light](screens/webkit-320-light-progress.png) | [webkit dark](screens/webkit-320-dark-progress.png) |
| Progress | 360 | [chromium light](screens/chromium-360-light-progress.png) | [chromium dark](screens/chromium-360-dark-progress.png) | [webkit light](screens/webkit-360-light-progress.png) | [webkit dark](screens/webkit-360-dark-progress.png) |
| Progress | 390 | [chromium light](screens/chromium-390-light-progress.png) | [chromium dark](screens/chromium-390-dark-progress.png) | [webkit light](screens/webkit-390-light-progress.png) | [webkit dark](screens/webkit-390-dark-progress.png) |
| Progress | 430 | [chromium light](screens/chromium-430-light-progress.png) | [chromium dark](screens/chromium-430-dark-progress.png) | [webkit light](screens/webkit-430-light-progress.png) | [webkit dark](screens/webkit-430-dark-progress.png) |
| Progress | 768 | [chromium light](screens/chromium-768-light-progress.png) | [chromium dark](screens/chromium-768-dark-progress.png) | [webkit light](screens/webkit-768-light-progress.png) | [webkit dark](screens/webkit-768-dark-progress.png) |
| Progress | 1024 | [chromium light](screens/chromium-1024-light-progress.png) | [chromium dark](screens/chromium-1024-dark-progress.png) | [webkit light](screens/webkit-1024-light-progress.png) | [webkit dark](screens/webkit-1024-dark-progress.png) |
| Progress | 1440 | [chromium light](screens/chromium-1440-light-progress.png) | [chromium dark](screens/chromium-1440-dark-progress.png) | [webkit light](screens/webkit-1440-light-progress.png) | [webkit dark](screens/webkit-1440-dark-progress.png) |
| Profile | 320 | [chromium light](screens/chromium-320-light-profile.png) | [chromium dark](screens/chromium-320-dark-profile.png) | [webkit light](screens/webkit-320-light-profile.png) | [webkit dark](screens/webkit-320-dark-profile.png) |
| Profile | 360 | [chromium light](screens/chromium-360-light-profile.png) | [chromium dark](screens/chromium-360-dark-profile.png) | [webkit light](screens/webkit-360-light-profile.png) | [webkit dark](screens/webkit-360-dark-profile.png) |
| Profile | 390 | [chromium light](screens/chromium-390-light-profile.png) | [chromium dark](screens/chromium-390-dark-profile.png) | [webkit light](screens/webkit-390-light-profile.png) | [webkit dark](screens/webkit-390-dark-profile.png) |
| Profile | 430 | [chromium light](screens/chromium-430-light-profile.png) | [chromium dark](screens/chromium-430-dark-profile.png) | [webkit light](screens/webkit-430-light-profile.png) | [webkit dark](screens/webkit-430-dark-profile.png) |
| Profile | 768 | [chromium light](screens/chromium-768-light-profile.png) | [chromium dark](screens/chromium-768-dark-profile.png) | [webkit light](screens/webkit-768-light-profile.png) | [webkit dark](screens/webkit-768-dark-profile.png) |
| Profile | 1024 | [chromium light](screens/chromium-1024-light-profile.png) | [chromium dark](screens/chromium-1024-dark-profile.png) | [webkit light](screens/webkit-1024-light-profile.png) | [webkit dark](screens/webkit-1024-dark-profile.png) |
| Profile | 1440 | [chromium light](screens/chromium-1440-light-profile.png) | [chromium dark](screens/chromium-1440-dark-profile.png) | [webkit light](screens/webkit-1440-light-profile.png) | [webkit dark](screens/webkit-1440-dark-profile.png) |

## Проверки и границы

- Chromium/WebKit, Dark/Light: 36 запусков сбора пяти основных экранов на 320/360/390/393/430/768/1024/1280/1440 px; 180 сохранённых замеров корня без горизонтального переполнения. Только выбранные состояния.
- Дополнительные состояния на 393 px: 4/4 запуска тренировки, редактора, гидратации, быстрого ввода и Coach OS; 4/4 на 1280 px; 4/4 запуска меню, раскрытия профиля, поиска упражнения, ввода воды и синтетической ошибки с повтором. Получение снимка не доказывает корректность всех действий.
- `collectUiAudit`: 8/8 запусков шести выбранных экранов на 320/393 px без сигналов в сохранённых отчётах; 4/4 запуска выбранных дополнительных состояний без сигналов. Проверялись только правила анализатора.
- Настоящий Chromium tab zoom 200%: карточка Today 4/4; шапка — восемь сочетаний четырёх экранов и тем до/после. В варианте пересечения нет. Chromium/WebKit на CSS-ширинах 196/320/393 px: 12/12 тестов по четырём экранам, в варианте пересечений нет. Это не WebKit browser zoom.
- Клавиатурный переход к раскрытию профиля — 4/4 сочетания тем и движков; геометрия после прокрутки и `:focus-visible`. TMA-эмуляция: 8/8 запусков в двух ориентациях и темах. Реальная системная клавиатура и safe-area устройства не доказаны.
- Физический iPhone, настоящий Safari/Telegram, VoiceOver, PWA и production: **NOT_VERIFIED**. Все ошибки, loading/disabled, popover, роли и варианты данных не покрыты. Независимый Impeccable critique и detector: **NOT_RUN**.

## Решение владельца

Принять или изменить единый вариант: сохранить показанные композиции и использовать показанный перенос шапки при сверхузкой ширине. Указать, если какой-либо из экранов или состояний требует другого визуального решения. Принятие относится к дизайну показанного варианта; реализация, реальный AFTER, отдельная визуальная приёмка и разрешение на merge/deploy следуют отдельно. Непроверенные состояния остаются открытыми.

Пакет не закрывает #994 или родительскую #981 и не подменяет итоговую QA #989.
