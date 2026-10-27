# Unified YFC selected states · 7f78f0d7a28e9db0688fe763556b28ce9ba411a6

## Shared contract

`frontend/src/styles/design-system.css`: `--v2-selected-surface`, `--v2-selected-outline`,
`--v2-selected-ink`, `--v2-selected-relief`, `--v2-selected-radius`,
`--v2-selected-radius-compact`, `--v2-selected-radius-pill`, `--v2-selected-motion`. Существующие motion, focus и
touch-target tokens переиспользованы. Dark/Light используют одну грамматику с отдельной
палитрой. Семантический opt-in — `data-yfc-choice="capsule"|"compact"`; источник состояния —
ARIA либо нативный checked. Глобальная стилизация `.is-active` не вводилась.
Нижняя вкладка: радиус `9999px` на всех ширинах; Dark — дымчатый графит/лаймовый текст,
Light — мягкая лаймовая поверхность/тёмно-зелёный текст. Навигационное стекло: 95% Dark,
96% Light, blur 20px, saturate 112%; материал повторяет матовую панель таймера отдыха.

## Компоненты

AppShell: personal/Coach navigation, дополнительные ссылки, профиль и More; shared
SegmentedControl; Progress: local rail, period и trends; WeekStrip picker; TrainerModeSwitch;
Coach local navigation и attention filters; RIR; WorkoutAdaptation reason/time/equipment/replacement;
workout feedback; Nutrition modes/completeness/source filters; ProgramRecommendation и legacy
radio groups; program deload checkbox; BodyPriorityPicker; onboarding goals; exercise picker;
profile anchors; email mode tabs; AI feedback/history; Coach workflow selection.

Локальные конфликтующие selected-переопределения удалены. Смена периода сохраняет DOM-узел
и фокус переключателя. Стрелки Progress rail сохраняют ширину области во время нажатия.
Узкая неделя прокручивает только свой внутренний rail. Desktop navigation — минимум 44px.
TMA adapter удерживает скрытую панель до окончания native click, а не только pointerup.

## Сознательно сохранено

- Нативные Select, включая тип недели программы: native popup/option и клавиатурное управление.
- Обычные карточки и строки клиентов, шаг выполнения, завершённый подход: контекст/статус данных.
- Success/warning/danger, графики, информационные badges, поля текста и основные CTA: другая семантика.
- Favorite star и camera/busy controls: самостоятельные действия, не выбор раздела/варианта.
- Public Landing exploration: вне scope authenticated consistency pass.
- PDF: принятая последовательная структура и Oswald/Inter сохранены; новой PDF-правки нет.
- #871/#872: отдельные owner gates, не блокируют независимые изменения.

## Документация

Обновлены `AGENTS.md`, `docs/design/component-states-v2.1.md`,
`docs/design/YFC_PRODUCT_UI_CONTRACT.md`, `codex-backlog/ACTIVE_DESIGN_SOURCE.md`,
`docs/design/iconography-and-data-viz-v2.1.md`. Канонический контракт:
`component-states-v2.1.md#unified-yfc-selected-states`. Baseline активируется после успешного
разрешённого production-релиза #927; повторное решение владельца для переиспользования не нужно.

## Проверки

- 829 Vitest: новые проверки pointerup/native-click, cancel/window blur, принятия записи и внутреннего WeekStrip;
  существующий Progress test усилен проверкой сохранения узла и клавиатурного фокуса.
- 20 новых Coach cases: обе темы, четыре мобильные ширины и desktop, Chromium/WebKit.
- Расширены approved mobile и workout scenarios: общие computed surface/ink/relief, контраст
  минимум 4.5:1, иконки, 44×44px, ARIA, keyboard focus, стабильная ширина rail и скролл.
- Forced colors проверяет fallback, reduced motion — отсутствие заметного перехода.
  Неподдерживаемое WebKit свойство forced-color-adjust не выдаётся за поддерживаемое.
- Общая матрица: 208 сценариев, retries/failures/flaky = 0.
- Дополнительно: {'mobile-goldens': {'startTime': '2026-10-11T11:26:36.979Z', 'duration': 31302.263000000003, 'expected': 10, 'skipped': 0, 'unexpected': 0, 'flaky': 0}, 'ancillary': {'startTime': '2026-10-11T11:27:08.886Z', 'duration': 62805.652, 'expected': 23, 'skipped': 0, 'unexpected': 1, 'flaky': 0}, 'catalog': {'startTime': '2026-10-11T11:29:50.961Z', 'duration': 17057.702, 'expected': 2, 'skipped': 0, 'unexpected': 0, 'flaky': 0}, 'ancillary-initial': {'startTime': '2026-10-11T11:27:08.886Z', 'duration': 62805.652, 'expected': 23, 'skipped': 0, 'unexpected': 1, 'flaky': 0, 'classification': 'PRE_EXISTING_PERFORMANCE_FAILURE_OUTSIDE_SCOPE'}, 'ancillary-rerun': {'expected': 0, 'unexpected': 3, 'flaky': 0, 'classification': 'PRE_EXISTING_PERFORMANCE_FAILURE_OUTSIDE_SCOPE', 'log': 'ancillary-rerun/ancillary-rerun.log'}, 'p1-stress': {'startTime': '2026-10-11T10:52:44.266Z', 'duration': 553601.9099999999, 'expected': 256, 'skipped': 0, 'unexpected': 0, 'flaky': 0}, 'windows-mobile-goldens': {'startTime': '2026-10-11T11:14:46.003Z', 'duration': 26559.206, 'expected': 10, 'skipped': 0, 'unexpected': 0, 'flaky': 0}, 'p1-late-read': {'startTime': '2026-10-11T10:17:46.825Z', 'duration': 32976.901999999995, 'expected': 16, 'skipped': 0, 'unexpected': 0, 'flaky': 0}, 'p1-protocol': {'expected': 36, 'unexpected': 0, 'flaky': 0}}. Ancillary Pulse performance finding сохранён отдельно как pre-existing и вне scope; см. `audit/ancillary-status.json`. Required CI проверяется отдельно по GitHub Actions. Merge/deploy запрещены до нового owner approval.

Это реальные browser screenshots работающей Vite production-сборки, API synthetic.
Физический iPhone, VoiceOver и native Telegram не проверены. Данные production-пользователей
для съёмки не изменялись. Env change required: no.
