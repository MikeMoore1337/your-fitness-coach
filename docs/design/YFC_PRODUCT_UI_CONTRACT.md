# YFC Product UI Contract

Статус: active contract для authenticated Web/Mobile Web/TMA UI.

Этот документ закрепляет production evolution после owner-approved #387/#388. Он не создаёт
новую дизайн-систему и не заменяет `codex-backlog/ACTIVE_DESIGN_SOURCE.md`: active design source
остаётся authoritative для текущей visual baseline.

## Режим работы

Обычная product/fix task работает в режиме **EVOLVE**:

- production UI, существующие tokens и shared components являются baseline;
- сначала переиспользуется существующий паттерн, затем добавляется только необходимое локальное
  поведение;
- слова «улучшить», «modernize», «app-like», «Stage», «v3» и «polish» сами по себе не являются
  разрешением на redesign;
- нельзя создавать параллельную typography, color, card или navigation system.

Режим **RETHINK** возможен только в отдельной задаче, где явно указаны redesign/exploration scope,
owner approval exploration и owner selection направления до rollout. В bounded design task
допустимы новые решения, но они должны быть отдельно зафиксированы и не распространяются на
обычные tasks автоматически.

Перед изменением visible authenticated UI прочитай:

1. `codex-backlog/ACTIVE_DESIGN_SOURCE.md`;
2. `.agents/references/DESIGN_GUARDRAILS.md`;
3. этот contract;
4. фактические shared primitives и affected production flow.

Bounded exception к contract записывается в task и получает explicit owner approval; молчание или
ссылка на App Experience v3 исключением не являются.

## Source of truth и primitives

- Текущая production implementation — source of truth для поведения, состояний и визуальных
  токенов.
- Используй существующие `Button`, `IconButton`, `Surface`, `SectionHeader`, `Card`,
  `SemanticCard`, `SegmentedControl`, `Icon` и Glass helpers, когда их семантика подходит.
- Для action controls сохраняй shared `--touch-target` (сейчас 44px), `--v2-space-*`, radius,
  focus и color tokens.
- Не копируй page-local button/card CSS, если shared primitive уже выражает нужный смысл.
- Не создавай giant universal component. Новая primitive оправдана только повторяющимся stable
  interaction pattern с одинаковой семантикой и доказанной повторной потребностью.

## Information architecture

Базовая последовательность:

`overview -> navigation -> focused destination -> action/detail`

Overview отвечает на «что требует внимания» и ведёт в destination; destination показывает
детали и действие. Не дублируй большой detail module на overview и destination.

Не используй endless aggregate pages, giant accordions вместо навигации или глубокие меню для
частого действия. Secondary information раскрывается progressive disclosure.

Approved #388 trainer pattern — короткий `Сегодня`, отдельный `Ещё` hub и focused destinations
для operations/clients/programs; это guidance, а не literal template для каждого нового экрана.

## Global и local navigation

- В каждом context есть одна primary navigation system: mobile dock или desktop sidebar.
- Не дублируй global destinations одновременно в dock + horizontal tabs или sidebar + horizontal
  tabs.
- Tabs/segmented controls используются только для реальной local subsection navigation.
- Workspace/context switch не является destination tab.
- В trainer context trainer dock/sidebar остаётся trainer navigation; personal dock остаётся
  personal navigation; `Для себя / Клиенты` — отдельный workspace switch.

Approved #387 trainer pattern сохраняет trainer-first entry, явный workspace switch и
context-specific navigation.

## CTA и action hierarchy

Если у card/surface одно primary action:

- на mobile primary CTA занимает доступную ширину внутри surface;
- высота interactive control не меньше shared `--touch-target`;
- card padding сохраняется;
- используй shared `Button` и существующий variant; desktop может оставаться компактнее, если
  это соответствует production layout.

Если действий несколько:

- primary и secondary различимы по hierarchy;
- stacked mobile actions имеют явный token-based vertical gap (approved #388 finance pattern —
  `--v2-space-3`, 12px), а не visually fused geometry;
- secondary action не обязан становиться большой primary button.

Navigation action обязан иметь affordance: semantic control, достаточный touch target и видимый
row/button treatment. Text-only text, который фактически ведёт по navigation, запрещён.
Chevron допустим для compact navigation row.

## Typography, surfaces и responsive behavior

- Сохраняй current production typography roles и scale.
- Не добавляй giant authenticated hero/marketing language в частые рабочие surfaces.
- Cards/surfaces должны поддерживать task hierarchy, а не превращать страницу в декоративную
  стопку одинаковых rectangles.
- Каждое новое visible interaction проверяется в Light, Dark, representative mobile и desktop.
- Mobile — отдельная composition: проверяй overflow, safe-area/dock overlap и touch spacing, а не
  только shrink desktop.
- Web и TMA используют одну product identity; platform-specific safe area/BackButton/viewport не
  являются поводом для отдельной visual system.

## Accessibility и deterministic guardrails

Сохраняй semantic controls, visible keyboard focus, readable contrast, minimum touch target,
reduced-motion behavior, safe-area awareness и отсутствие dock overlap.

Текущий code-backed baseline после #387/#388:

- shared primitives и tokens: `frontend/src/shared/ui/common.tsx`, `Icon.tsx`,
  `frontend/src/styles/design-system.css`;
- trainer navigation/CTA guardrails: `frontend/tests/e2e/coach-workspace.spec.ts`;
- assertions покрывают mobile full-width primary CTA, minimum touch height, finance action gap,
  secondary navigation affordance, dock overlap, no horizontal overflow и отсутствие duplicate
  trainer navigation.

Не кодируй subjective visual taste brittle lint rules. Добавляй deterministic assertion только
для stable geometry, semantics, navigation или accessibility invariant, которую реально можно
проверить без screenshot pixel guessing.

## Concrete examples

### DO

- короткий overview и focused destination;
- mobile full-width single primary card CTA;
- neutral navigation row с chevron для secondary destination;
- trainer mobile dock **или** desktop sidebar как primary navigation;
- отдельный workspace switch;
- существующие `Button`, `Card` и spacing/touch tokens.

### DON'T

- новый giant authenticated hero/dashboard visual language;
- endless page из полных CRM modules;
- duplicate global navigation;
- text, который ведёт как link, но не имеет affordance;
- две stacked buttons, визуально слипшиеся;
- page-local custom button/card system при наличии shared primitive;
- копирование rejected Stage 0 prototype styling.

## Change checklist

Перед commit visible UI task должна ответить:

1. Это EVOLVE или explicit RETHINK?
2. Какой текущий production component/token переиспользован?
3. Как устроены overview → destination → action/detail?
4. Есть ли одна primary navigation в каждом context?
5. Как проверены mobile/desktop, Light/Dark, touch/focus и dock/overflow?
6. Какой deterministic test защищает новый stable invariant?
