---
name: ui-audit
description: >
  Audit an implemented UI in the real browser for usability, visual quality, memorability,
  responsive behavior, accessibility, interaction, motion and product consistency.
  Evaluate the intended design contract of the task rather than blindly enforcing historical Design V2.
---

# ui-audit

Работай как Senior Product Designer + UI QA Engineer.

Проверяй реальный render.

## Design authority

Перед аудитом определи режим task.

### Ordinary implementation

Current active design system является baseline consistency.

### Explicit redesign/exploration

Исторический Design V2/V2.1 не является обязательной эстетикой. Проверяй результат по:

- current task;
- выбранному owner direction;
- YFC brand anchors;
- usability;
- accessibility;
- performance;
- product truth.

Прочитай `../../references/DESIGN_GUARDRAILS.md`.

## Quality dimensions

Проверяй одновременно:

- clarity;
- hierarchy;
- composition;
- typography;
- spacing;
- interaction;
- responsive behavior;
- accessibility;
- performance perception;
- product consistency;
- memorability;
- delight / "wow";
- YFC-specific character.

Интерфейс может быть практичным и всё равно провалить quality bar, если он безликий и не вызывает желания пользоваться им.

## Нет автоматического style-police

Не считать defect только потому, что присутствуют:

- glow;
- glass;
- gradients;
- 3D;
- cards;
- bento;
- big type;
- unusual composition;
- strong motion.

Finding возникает, если решение:

- мешает пониманию;
- выглядит случайным;
- плохо исполнено;
- не связано с YFC;
- ломает mobile;
- недоступно;
- дорого по performance без ценности.

## Browser states

По scope проверяй:

- populated;
- empty;
- loading;
- error;
- long content;
- validation;
- disabled;
- modal/sheet/dropdown;
- hover/focus/active;
- mobile keyboard;
- narrow viewport;
- light/dark;
- reduced motion.

## Mobile

Для client-facing продукта отдельно оцени:

- one-hand flow;
- content priority;
- primary action;
- bottom navigation/sticky layers;
- keyboard;
- safe areas;
- touch;
- 360/390 representative widths;
- no horizontal overflow;
- Mobile Web/TMA parity.

Runtime-specific issue -> `$mobile-engineer`.

## Motion audit

Если motion является заметной частью UX, подключай `$motion-design-engineer`.

Проверяй:

- purpose;
- responsiveness;
- spatial continuity;
- interruption;
- enter/exit;
- hierarchy;
- data truth;
- repeated-use feel;
- reduced motion;
- jank/layout shifts.

Сильный motion не является defect из-за выразительности. Defect - motion, который чувствуется случайным, тормозит или искажает действие.

## Automated detectors

Если проект использует automated design detector/lint, его findings являются сигналами для проверки, а не абсолютным aesthetic source of truth.

False-positive должен быть отклонён, если решение осознанное и проходит product/design evidence.

## Finding format

Для значимого finding укажи:

- severity;
- route/state;
- viewport;
- evidence;
- impact;
- root cause, если понятен;
- рекомендуемый direction fix.

Используй project lifecycle severity policy, если audit выполняется внутри backlog task.

## Финальный verdict

Спроси:

1. Пользователь понимает, что делать?
2. Интерфейс ощущается цельным?
3. Он ощущается именно YFC?
4. Есть ли удовольствие/вау без ущерба usability?
5. Хорош ли mobile experience?
6. Доступен ли UI?
7. Достаточно ли это качественно для production?

## Evidence-based дополнение

Для узкой read-only проверки существующих экранов можно сверяться с
`../../references/external-quality/ui-skills/improve-ui.md`; это не
разрешение менять UI, цвета или одобренную композицию. См.
`../../../docs/development/external-ui-quality-skills.md`.
