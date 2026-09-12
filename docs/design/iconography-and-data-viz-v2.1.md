# Иконографика и визуализация данных Design V2.1

## Статус решения

Task 239 унифицирует функциональную иконографику поверх текущего Liquid Glass, сохраняя IA и
геометрию графиков. До явного owner visual approval новый набор является кандидатом для выпуска.
Логотип YFC, официальные provider marks и аватары не входят в функциональное семейство.

## Иконографика

- Канонический renderer: `frontend/src/shared/ui/Icon.tsx`.
- Статическая JSX-геометрия: `frontend/src/shared/ui/iconGlyphs.tsx`. HTML/SVG из внешних
  источников не интерпретируется. Существующее векторное семейство YFC переиспользовано без dependency.
- Сетка: `24×24`; поддерживаемые optical sizes: `16`, `20`, `24`.
- Иллюстративные экземпляры того же glyph на landing сохраняют размеры `56`, `80`, `110`;
  функциональные controls не используют эти размеры. Произвольное масштабирование отдельных nav icons запрещено.
- Food entry использует `nav-nutrition`, workout — общую гантель `exercise`/`nav-plan`/`week-strength`.
  `calendar` и `nav-today`, disclosure/chevron, more и rest/moon используют общую геометрию.
- Select сохраняет native поведение и CSS background adapter с той же геометрией chevron;
  unit check предотвращает расхождение. Touch date использует декоративный `Icon` с
  `pointer-events: none`; desktop date/time и нативные popup pickers остаются browser controls.
- Default/active/hover/focus/disabled/destructive/unavailable наследуют цвет и состояние control.
  Иконка не меняет accessible name, tab order, обработчики, permissions или hit area.
  Filled допустим только для явного `star-filled`; status dots не являются отдельным filled-семейством.
- Все функциональные glyphs используют `currentColor`, round cap/join и общий stroke `1.8`.
- Базовые actions, navigation, confidence, statuses, product и `WeekStrip` имеют уникальные
  семантические имена. Одинаковая семантика не получает page-local SVG, Unicode или CSS substitute.
- `nav-exercise-catalog` использует выбранный владельцем разреженный силуэт открытой папки с одной
  гантелью: внешний контур означает каталог, внутренний — упражнения; повторяющаяся grid-геометрия
  не используется.
- `AppNavigationIcon`, `CloseIcon`, `TrashIcon`, `ChevronIcon`, `CheckIcon`, `DisclosureIcon`,
  `ThemeIcon`, `DataConfidence` и `WeekStrip` являются адаптерами над тем же renderer.
- Icon-only action всегда получает accessible name от control и touch target не меньше `44px`.
  Декоративная иконка скрыта от accessibility tree; самостоятельная смысловая иконка передаёт
  `label`.
- Active state использует neutral surface, усиленный label и lime boundary. Цвет не заменяет форму
  или подпись.
- YFC brand assets и Google/Yandex/Telegram/VK/Apple marks остаются защищёнными исключениями.

## `WeekStrip`

Тип активности и статус дня — разные glyphs. `strength`, `cardio` и `rest` больше не кодируются
буквами. `completed`, `planned`, `in-progress`, `skipped`, `nutrition-incomplete`,
`nutrition-fasted` и `nutrition-missing` имеют разные формы на одном optical canvas. Легенда и
полный accessible name сохраняются, поэтому состояние не зависит от цвета.

Для тренировочных статусов используются закреплённые формы: `planned` — календарь с часами в
правом нижнем углу, `in-progress` — круговая стрелка с двумя pause-полосами, `skipped` — переход к
следующему без диагонального перечёркивания. Все три наследуют semantic tone через `currentColor`.

## Shared data-viz primitives

Канонический слой: `frontend/src/shared/ui/DataViz.tsx`.

- `TimeSeriesChart` — Nutrition, масса/антропометрия и print/PDF;
- `QuantitativeProgress` — числовой прогресс к цели;
- `TaskProgress` — выполненные элементы конечной задачи;
- `StepProgress` — этапы workflow, но не количественная цель;
- `RankedBars` — ранжированное сравнение на общей видимой шкале.

Нельзя называть `7 420 / 10 000 шагов` workflow step progress: это quantitative target.

## Правдивость данных

- `missing` остаётся отсутствием: точка не рисуется и соседние подтверждённые точки через такой
  интервал не соединяются.
- Подтверждённый `0` остаётся видимой нулевой точкой.
- Target имеет dashed geometry; actual — solid line и ring marker; смена target получает отдельную
  вертикальную метку и подпись.
- X-position использует реальные даты, а не порядковый номер точки.
- Y-scale строится по подтверждённым actual/target значениям. Нулевая baseline включается только
  для метрик, где она помогает чтению, например калорий.
- Одна точка остаётся одной точкой; insufficient/empty/error/stale не получают fake series.
- Business formulas, API aggregates и provenance не меняются визуальным слоем.
- Actual line строится монотонной smooth curve с rounded joins/caps внутри каждого непрерывного
  участка. Area fill замыкается к той же truthful visual baseline, что и reveal; пропуск разрывает
  и линию, и fill, поэтому визуальный слой не создаёт несуществующее наблюдение.

## Responsive и interaction

Mobile Web и mocked TMA используют compact v2 composition: короткая legend, минимум три X-label и
adjacent selected detail. Desktop использует тот же язык, но получает больше фактической ширины —
не отдельную v1-систему и не растянутый mobile SVG.

Точки выбираются touch/click, focus и стрелками клавиатуры. Важное значение всегда дублируется
рядом с графиком и не требует hover. `prefers-reduced-motion` отключает transition, а
`forced-colors` сохраняет solid/dashed/marker различия.

## Motion contract

Shared `DataViz` использует утверждённые tokens из `motion-v2.md`: `560ms` для первого meaningful
entrance, общий sequence не более `760ms`, stagger `25ms`, compatible update `260ms`. Entrance
запускается один раз после первой успешной загрузки/full reload или первого попадания готового
below-fold plot в viewport. Same-data refetch, theme/viewport change, TMA resume и point selection
не являются trigger.

До первого кадра axes, labels, table/ARIA alternative и final scale уже содержат фактические
значения. Actual geometry визуально раскрывается от truthful baseline: mathematical zero только
когда он включён в scale, иначе от нижней границы plot. Missing не превращается в zero и не
соединяется с соседней точкой. При reduced motion, print/PDF/export и interruption отображается
статичное конечное состояние без потери interaction или focus.

## Text/table и print

Каждый `TimeSeriesChart` содержит таблицу тех же подтверждённых данных. На экране она доступна
assistive technology, а в print/PDF становится видимой. Print использует grayscale-safe solid,
dashed и ring geometry и не зависит от tooltip или выбранного interactive state.

## Запреты

- Не добавлять generic chart dependency без отдельной доказанной необходимости.
- Не вставлять reference SVG графиков из design package: в них текст переведён в outlines.
- Не создавать page-local `line/polyline/circle` chart grammar или новый CSS progress meter.
- Не использовать emoji, Unicode arrows/stars/plus/minus и CSS-generated functional glyphs.
