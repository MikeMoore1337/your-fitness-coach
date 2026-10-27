# Design V2.1 — активная production specification

Редизайн Task 151 описан в [Протоколе силы](strength-protocol.md). После его публикации этот
документ остаётся историческим основанием; новые визуальные решения задаёт Протокол силы.

## Статус и граница решения

```text
DESIGN_ID = DESIGN_V2_1
SPECIFICATION_STATE = ACTIVE_PRODUCTION
OWNER_APPROVED_AT = 2026-08-22
ACTIVATED_BY = 49G
PRODUCTION_SOURCE = DESIGN_V2_1
```

Точный финальный owner token:

```text
FINAL_APPROVE_V2_1: Landing=DESIGN_V2_QUIET_PACE; LOGIN=A_SURFACES_STATES+V2_TYPE+OPTION_1_SPLIT+240PX_CENTERED_AUTH+35PX_CONTINUATION; DESKTOP_APP=V2_CONTENT+A_RAIL+V2_ICONS_TYPE; MOBILE_TMA=V2_COMPACT_FONT_NORMALIZED+BOTTOM_NAV_VIEWPORT_PINNED
```

Owner approval подтверждён handoff task `49F`; task `49G` активировала этот документ как
production source. Исторические Design V2 документы сохранены рядом и не переопределяют V2.1.

## Design Read

- Пользователь: самостоятельный пользователь, клиент тренера; на desktop также тренер.
- Главная задача: сразу понять текущее действие, выполнить его и увидеть подтверждённый результат.
- Primary surfaces: Mobile Web и TMA; desktop — полноценная дополнительная поверхность;
  Coach workspace — desktop-first с честным mobile fallback.
- Характер: Quiet Pace — спокойный, точный sport-tech без glow, glass, decorative gradients и
  шаблонной KPI-card сетки.
- Узнаваемый мотив: один lime-маркер текущего действия, фактические workout/nutrition/progress
  данные и прямой ритм `сейчас → контекст → подтверждение`.
- Плотность: умеренная на Landing и Personal desktop, компактная без microtype на mobile,
  повышенная на Coach desktop.
- Motion: короткий feedback состояния; не является частью брендинга и никогда не блокирует input.

## Неизменяемые seams hybrid

| Слой                  | Source                | Разрешённое исключение                                                                      |
| --------------------- | --------------------- | ------------------------------------------------------------------------------------------- |
| Typography, numbers   | Design V2             | `/login` использует ту же V2 type system; headline desktop ровно `35px`.                    |
| Global spacing/radii  | Design V2             | Только layout geometry `/login` и desktop rail; локальная A token migration запрещена.      |
| Color semantics       | Design V2             | `/login` получает A-style two-plane allocation, но обе plane используют V2 semantic colors. |
| Landing               | normalized Quiet Pace | Никаких мотивов A/B/C и никакого нового copy/product promise.                               |
| Authenticated content | Design V2             | На desktop меняется только anatomy rail; content/data language остаются V2.                 |
| Mobile/TMA            | Design V2             | Уплотнение proximity и привязка bottom navigation к viewport; layout A/B/C запрещён.        |
| Motion                | Design V2             | Telegram haptics остаются optional platform feedback, не shared visual behavior.            |

## Design tokens

### Цвета и semantics

Использовать semantic variables, а не literal colors внутри feature CSS.

| Token intent      | Light     | Dark      | Использование                                |
| ----------------- | --------- | --------- | -------------------------------------------- |
| canvas            | `#F4F5F2` | `#101310` | page/root background                         |
| surface           | `#FFFFFF` | `#161916` | task/entity region, dialog/sheet             |
| surface-secondary | `#ECEDE9` | `#1E221E` | grouped facts, selected/hover background     |
| surface-strong    | `#DADCD7` | `#292E29` | pressed/disabled support, never primary text |
| text-primary      | `#161A17` | `#EEF0EA` | headings/body/actions                        |
| text-secondary    | `#59605B` | `#AFB5AD` | descriptions/meta                            |
| border            | `#C9CDC8` | `#3A413A` | rules, controls, region boundaries           |
| lime              | `#9EE02B` | `#A8E83A` | one primary action/current marker/focus      |
| lime-hover        | `#8DCE20` | `#98D62F` | hover capable pointers only                  |
| accent-text       | `#486414` | `#B9EA72` | non-filled accent copy on matching surface   |
| on-lime           | `#102015` | `#102015` | text/icon on lime                            |
| danger            | `#B93838` | `#EF7474` | error/destructive meaning with text/icon     |
| danger-surface    | `#F9E7E7` | `#2C1717` | recoverable error region                     |
| warning           | `#98600F` | `#E5B963` | warning/partial data with copy               |
| warning-surface   | `#F5EAD5` | `#2B2314` | warning region                               |
| success           | `#486414` | `#A8E83A` | confirmation with text/icon                  |
| success-surface   | `#ECEDE9` | `#1E221E` | success region                               |

Lime не обозначает danger, passive decoration или несколько конкурирующих actions. Charts retain
units, period and text/table alternative; цвет не является единственным носителем смысла.

### Typography

- Font stack: `Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`.
- Новых web fonts нет. `font-display`, preconnect и font preload не нужны.
- Weights: `400` body, `600` label/subheading, `700` action/section, `800` только display/current emphasis.
- Global app scale: caption/meta `12/1.4`, body `15/1.5`, body-large `16/1.5`, section
  `18–22/1.15`, page `24–34/1.1`.
- Mobile guardrails: body не меньше `14px`, meta не меньше `12px`, body line-height не меньше `1.4`.
- Landing display: desktop `clamp(56px, 5.8vw, 84px)/0.98`; tablet `48–64/1.0`;
  mobile `44px` на `430`, `42px` на `390`, `40px` на `360`, line-height `0.98–1.02`.
- Login continuation: desktop `35/1.04`, weight `700`, одна строка при `>=1024`; mobile title
  `26/1.1`, естественный перенос.
- Numeric working values: `font-variant-numeric: tabular-nums`; value и unit остаются рядом,
  но unit визуально вторичен.
- Line length: marketing/body `45–68ch`; auth helper `28–48ch`; data descriptions `24–56ch`.

### Spacing, grid and containers

- Canonical V2 component spacing: `4 / 8 / 12 / 18 / 28 / 44px`.
- Responsive page gutters: `16px` at `360/390`, `20px` at `430`, `24px` at `768/1024`,
  `32px` at `1280/1440`.
- Landing container: `max-width: 1180px`; authenticated default: `980px`; wide data/Coach:
  `1180px` only when the screen benefits from parallel data regions.
- Desktop content grid: 12 columns, `16px` gap at `1024`, `20px` at `1280`, `24px` at `1440`.
- Mobile grid: one column. Two columns allowed only for short numeric fields/metrics with a tested
  long-label fallback to one column.
- Compactness means removing repeated wrapper padding and reducing unrelated gaps. It never means
  shrinking text, target size, error copy or safe-area reserve.

### Geometry and elevation

- Control radius `12px`; compact nav/data subregion `8px`; task region `16px`; large panel/dialog
  `20px`; pill only for true status/filter/toggle semantics.
- Border `1px`; selected rail item additionally gets `3px` lime inline marker.
- No border nesting when whitespace/rule already groups content.
- Raised elevation: Light `0 8px 24px rgba(23,32,24,.08)`, Dark
  `0 8px 24px rgba(0,0,0,.16)`; only menus/popovers/temporary raised elements.
- Overlay elevation: Light `0 18px 42px rgba(23,32,24,.14)`, Dark
  `0 18px 42px rgba(0,0,0,.28)`; dialogs/sheets only.
- Landing proof, cards and app regions are flat; blur, glass, glow, decorative gradient and
  rotation are prohibited.

### Icons, illustration and product imagery

- Canonical YFC logo/mark only; functional glyphs use shared `Icon` and the contract in
  `iconography-and-data-viz-v2.1.md`.
- Functional icons use `currentColor`, `1.8px` stroke, `16/20/24px` optical sizes in at least
  `44px` interactive target.
- No emoji or colored icon circles as generic decoration.
- Product proof uses controlled renders/current components with fixture label; never real personal data.
- Landing raster derivatives reserve exact `width`/`height` or `aspect-ratio`, match active theme,
  and lazy-load only below fold. Hero proof may be live/HTML-first; no new stock or AI imagery.

## Component contracts

- Buttons: primary lime, secondary surface+border, ghost for low-emphasis; one primary per local
  hierarchy; `44px` minimum, `48–58px` for mobile core actions.
- Inputs/selects: visible label, `44px` minimum, `12px` radius, persistent unit/hint; numeric fields
  use appropriate `inputMode`; invalid retains entered value and shows adjacent error.
- Navigation: A-derived `164px` desktop rail at `>=900`; mobile has five-item bottom navigation
  pinned to viewport, plus `Ещё` sheet for secondary destinations.
- Cards/data regions: use `Surface`, `Card`, `Metric`, `SectionHeader`; prefer rules/whitespace over
  card-inside-card. Today exposes one current action before context.
- Dialog/sheet: modal dialog at desktop, bottom sheet at mobile; visible close/back path, focus trap
  and restoration; content scrolls independently; primary action remains reachable above keyboard.
- Loading/empty/error/success/disabled/permission/offline states follow
  `component-states-v2.1.md`; no blank page and no indefinite primary-action spinner.
- Charts and progress use only the shared primitives and truthful semantics defined in
  `iconography-and-data-viz-v2.1.md`.

## Motion

- Базовые durations: fast `120ms`, standard `180ms`, slow `260ms`; easing
  `cubic-bezier(.2,0,0,1)`.
- Selected Pulse pilot добавляет grammar `respond -> gather -> settle`: frequent current-action
  feedback остаётся в `120–180ms`, а редкая workout completion choreography ограничена `760ms`.
- Shared chart reveal использует `560ms`, не откладывает axes/units/period/values и завершается в
  общем окне не более `760ms`.
- Prohibited: autoplay loops, scroll hijacking, decorative parallax, staggered list entrance,
  motion-dependent understanding.
- `prefers-reduced-motion: reduce`: travel/overshoot/reveal отключаются; final color, boundary,
  artwork, status, focus и content остаются доступны.

## Final render set

`references/design-v2.1/README.md` связывает каждый board с выбранным source и evidence boundary.
Boards являются static fixture renders: они подтверждают только hierarchy/composition,
а не runtime, conversion, AT, physical device или real Telegram behavior.
