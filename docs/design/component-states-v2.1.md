# Design V2.1 — component and state matrix

## Global state rules

1. State meaning always has text/icon/structure in addition to color.
2. Loading keeps expected geometry and does not masquerade as empty data.
3. Recoverable errors preserve entered values and provide one local retry/recovery action.
4. Disabled state explains the prerequisite when it is not self-evident.
5. Offline distinguishes queued/local state from server-confirmed state.
6. Permission denial names the missing capability without exposing internal authorization details.
7. Success is brief but remains available to assistive technology; no motion-only confirmation.

## Shared primitives

| Component | Default / interaction | Loading | Empty / error / permission / offline | Disabled / success |
| --- | --- | --- | --- | --- |
| `Button` | Primary lime only for local primary; secondary/ghost retain border or text affordance. Hover only for hover-capable pointers; pressed `translateY(1px)`; focus `3px` lime + `3px` offset. | Label becomes action-specific (`Сохраняем…`), width fixed, repeated submit blocked, `aria-busy`. | Inline retry is secondary; offline queue action states what is saved locally. | Disabled opacity alone is insufficient when reason is unknown; success label/icon is textual and returns to stable state. |
| `IconButton` | Functional glyph `18–20px` inside `44px` target, accessible name mandatory. | Stable square skeleton/spinner with name retained. | If action unavailable, hide only when it truly cannot apply; otherwise show disabled reason. | Pressed/focus parity with Button. |
| `Field` + `Input`/`Select` | Persistent visible label; hint under control; control `>=44px`; numeric values tabular and correct `inputMode`. | Form may stay editable unless submission contract requires lock. | Error adjacent and programmatically associated; recoverable error keeps value; permission message replaces unavailable control. | Disabled control remains legible; saved confirmation does not clear draft prematurely. |
| `PickerInput` | Native date/time semantics, full mobile width, visible label. | Stable control geometry. | Unsupported picker falls back to typed/native input with validation. | Same as Field. |
| `Surface` / `Card` | One semantic region; border/spacing group content. Avoid nested card for mere spacing. | Skeleton follows title/body/action anatomy. | `EmptyState`/`ErrorState` live inside owning region; permission/offline do not blank surrounding page. | Success may use quiet inline status; disabled region keeps headings readable. |
| `SectionHeader` | Title → description → optional local action; action moves below copy on narrow view. | Heading remains, content skeleton follows. | Error belongs to body, not hidden in heading. | Action disabled reason stays near action. |
| `Metric` | Label, tabular value, unit/period/hint; related metrics may share one rule-based region. | Value-width skeleton. | `Нет данных` differs from `0`; partial value includes availability note. | Success/danger not encoded by number color alone. |
| `SegmentedControl` | Shared selected capsule with raised surface, inner light edge and lime accent; `aria-selected` and keyboard arrow/tab behavior retained. | Keep period labels, block data request re-entry. | Failed period keeps prior data marked stale or shows local retry. | Unsupported periods disabled with explanation if needed. |
| `Skeleton` | Matches content geometry; no misleading progress percentage. | Motion `1.3s` only in default preference. | On timeout transitions to explicit error/retry. | Reduced motion uses static secondary fill. |
| `LoadingState` | Centered within owning region with meaningful label. | N/A | Must never persist indefinitely without timeout/recovery at flow level. | N/A |
| `EmptyState` | Explains absence and next valid action, without fake data. | N/A | Distinct from permission/error/offline. | Primary only when there is a real next action. |
| `ErrorState` | Plain-language message, optional local retry. | Retry shows busy state in place. | Sanitized; no stack/provider/raw Telegram errors. | N/A |
| `Badge` | Only status/category; `>=24px` visual height, not used as a standalone interactive target. | Reserved label width if necessary. | Text names state (`В процессе`, `Неполные данные`). | Never lime-only meaning. |

## Navigation and overlays

| Component | Contract | Boundary states |
| --- | --- | --- |
| Desktop rail | `164px`, V2 logo/icons/type, shared selected capsule; grouped primary/secondary/workspace/account destinations. Account identity uses the full first row for the client name; role and logout share the second row. | Ordinary first/last names remain fully visible; genuinely long names use a single-line ellipsis without moving or hiding logout. Long navigation labels wrap to two lines only in secondary groups; permission-hidden destinations are not authorization boundary; loading user identity uses reserved geometry. |
| Mobile bottom navigation | Personal dock: Сегодня / План / Питание / Прогресс / Добавить on one Liquid Glass plane. Four links and one action; 24px icons, targets `>=44×44px`, shared selected capsule only on the current link. Coach/Demo retain their own destinations. | Safe/content inset included; selected destination survives reload; offline does not disable navigation; keyboard flow may temporarily hide the whole dock until the input-blurring click completes. Active workout keeps navigation available and restores state. |
| More sheet | Bottom sheet up to stable viewport minus safe top; focus moves to sheet and returns to `Ещё`; close/back both work. | Overflow scrolls inside sheet; network-independent destinations remain available offline; logout/destructive action separated. |
| Dialog | Desktop centered; mobile bottom sheet/full-height only when content requires; title and close visible. | Loading action does not dismiss; recoverable error stays in dialog; escape/back restores focus; permission and expired session have explicit next step. |
| Toast/status | Non-blocking, above nav/safe area, not sole confirmation. | Queued/offline and server-confirmed messages differ; errors with required action persist in-page instead. |

## Unified YFC selected states

Решение владельца от 11.10.2026 в PR #927: `DESIGN_RULE=UNIFIED_YFC_SELECTED_STATES`.
Это ограниченная унификация Design V2.1, включённая в общий релиз #859/#867/#914/#915.
Правило становится production baseline после успешной доставки этого релиза; отдельного
повторного выбора визуального направления для следующих задач не требуется.

Выбранный интерактивный элемент получает различимую поверхность с мягким рельефом,
внутренней световой гранью, скруглением и лаймовым акцентом. Контрастные текст и пиктограмма
сохраняют читаемость. Одного изменения цвета, слабой заливки или подчёркивания недостаточно.
Невыбранные элементы нейтральны и не имитируют выбранную поверхность.

### Канонический CSS-контракт

Источник — `frontend/src/styles/design-system.css`, без отдельной библиотеки или React-обёртки.
Явно помечай контрол `data-yfc-choice="capsule"` либо `data-yfc-choice="compact"`.
Состояние берётся из существующего `aria-selected`, `aria-pressed`, `aria-current="page"` /
`"location"` / `"true"` или непосредственного нативного `input:checked` внутри label. Не заводи вторую
копию selected-состояния для стилизации и не применяй правило ко всем `.is-active`.

Общие токены: `--v2-selected-surface`, `--v2-selected-outline`, `--v2-selected-ink`,
`--v2-selected-relief`, `--v2-selected-radius`, `--v2-selected-radius-compact`,
`--v2-selected-motion`. Dark и Light определяют значения одних и тех же токенов.
Выбранная поверхность вложена в существующий control; отдельного backdrop-filter у неё нет.
Liquid Glass остаётся материалом общей панели, а информационные карточки сохраняют свои роли.

| Назначение | Форма и семантика |
| --- | --- |
| Основная навигация, SegmentedControl, workspace switch | Полная капсула; текущий маршрут — `aria-current`, вкладка — `aria-selected`. «Добавить» остаётся действием без selected state. |
| Локальная навигация, период, фильтр, режим, RIR, feedback | Компактная форма либо капсула shared SegmentedControl; `aria-pressed` для toggle, `aria-selected` для tab. Размеры и обработчики соответствуют исходному назначению. |
| Выбор дня, радио- и checkbox-группы | Компактная форма; нативное checked либо `aria-pressed`. «Сегодня» и выбранная дата различаются. Узкая неделя прокручивается внутри своей области, выбранный день виден без вертикального прыжка страницы. |
| Нативный Select, включая тип недели программы | Сохраняет нативный popup и выбранное option. Не заменяется капсульным меню и не получает вторую реализацию. |
| Строка клиента, шаг выполнения, завершённый подход, график, badge, обычная карточка | Сохраняет собственную семантику данных, текущего контекста или статуса. Не превращается автоматически в капсулу. Явная группа выбора внутри такой поверхности использует общий контракт. |

### Отличия состояний

- Selected/current сохраняется после окончания жеста и имеет поверхность + рельеф + семантику.
- Hover — временная нейтральная реакция для hover-capable pointer; не меняет выбор.
- Pressed — временная реакция на нажатие; не создаёт выбранного состояния у обычной кнопки.
- Focus-visible — отдельный контрастный outline, видимый и поверх выбранной поверхности.
- Disabled сохраняет нативный запрет действия и читаемость; причина остаётся рядом при необходимости.
- Success, warning и danger описывают результат/данные, а не выбор; их цвета и смысл сохраняются.

Переход выбора использует shared motion, без перемещения контента. Reduced motion отключает
декоративный переход. Forced colors использует системные Highlight/HighlightText и сохраняет
фокус. Выбор не зависит от прозрачности или поддержки backdrop-filter.

### Применение и проверка

Для нового контрола сначала определи семантику, переиспользуй shared primitive, затем включи
контракт и выбери подходящую форму. Случайные page-local selected-заливки, подчёркивания,
тени и новые токены запрещены без конкретной функциональной причины. Существующие размеры
и расположение меняются только ради читаемости, доступности или подтверждённого дефекта.

Проверяй ARIA/native state, клавиатуру и восстановление фокуса; computed surface/ink/relief;
контраст; минимум 44×44px; отсутствие overflow/перекрытия CTA; обе темы, 320/360/393/430px,
desktop, Chromium/WebKit и mocked TMA; reduced motion и forced colors. Добавляй тесты этих
инвариантов и реальные скриншоты разных типов. Не фиксируй декоративные пиксели новым тестом.
Эмуляция, физическое устройство и проверка screen reader всегда обозначаются отдельно.

## Surface matrix

| Surface | Loading | Empty/partial | Error/retry | Success/offline/permission |
| --- | --- | --- | --- | --- |
| Landing | Header/primary copy remain HTML; product proof reserves size. | No fake testimonials/metrics; omit unsupported block. | Essential navigation/CTA remain usable if optional visual fails. | No success state; offline static content and internal routes remain readable. |
| `/login` | Provider stack geometry reserved; label `Открываем способ входа…`; one provider busy, others follow existing lock policy. | Provider unavailable shown as factual recovery, not blank slot. | Cancellation, provider unavailable, invalid/expired state, conflict and OAuth return each have plain copy and retry/back. | Valid TMA launch bypasses provider list; disabled provider explains availability. |
| Today | Page heading/current action skeleton; facts load independently. | `Нет тренировки сегодня`, no nutrition entry, insufficient progress remain distinct. | Current action failure has local retry; secondary facts may degrade independently. | Offline labels cached facts as cached; queued actions not presented as confirmed. |
| Active workout | Confirmed sets remain visible; current set inputs never disappear behind full-page loading. | No active workout returns to Today with explicit state. | Submit failure keeps weight/reps and exposes retry; conflict requests refresh/reconcile without duplicate set. | Completed set has text/check + optional haptic; offline queued state explicitly named; finish disabled until valid prerequisites. |
| Nutrition | Summary and meal sections load independently. | Full/incomplete/absent/intentionally unfilled day are separate labels. | Add/edit retains values; retry is scoped to failed operation. | Saved entry reflected in summary; offline local draft not counted as server-confirmed. |
| Progress/data | Period/units stay visible; chart/table skeletons aligned. | Insufficient data explains minimum; `0` remains a valid value. | Prior data may remain with stale notice and retry. | Positive/negative interpretation uses text and neutral evidence, not color promise. |
| Coach desktop/mobile fallback | Roster and selected client summary can load independently. | No clients, no active program and no data are separate states. | List, summary and client detail recover independently. | Permission is server-backed; client identity remains visible; destructive confirmation names client. |

## Login provider state order

1. Initial provider list: Telegram, Google, Яндекс, VK ID.
2. Provider pressed: pressed → busy; prevent double submit.
3. Redirect handoff: сохранить allowlisted requested section в page/session state без
   фиктивного жёстко заданного destination.
4. OAuth return success: continue to allowlisted internal destination.
5. Cancel: restore same provider list and focus to invoked provider.
6. Provider unavailable: error region + another provider; do not imply account loss.
7. Invalid/expired state or conflict: explain recovery without silent account merge.
8. Valid signed TMA launch: no browser provider screen; platform auth loading/error boundary only.

## Accessibility acceptance for implementation

- Semantic heading order and landmark navigation.
- All controls reachable and operable by keyboard; visible focus is never clipped.
- Focus restoration for dialog/sheet/BackButton navigation.
- Error/status announcement through existing live-region pattern where appropriate.
- Touch targets meet practical `44x44px` minimum; mobile primary actions `>=48px`.
- Contrast verified from rendered computed colors for both themes; lime-on-white body copy is not used.
- At 200% zoom and narrow reflow, no two-dimensional scroll is required for the core task.
- Reduced motion preserves sequence and confirmation.
