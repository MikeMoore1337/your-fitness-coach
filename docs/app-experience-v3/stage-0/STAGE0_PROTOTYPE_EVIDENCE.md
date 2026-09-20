# Stage 0 prototype evidence · historical IA artifact

## Owner status

Owner decision: prototype visual direction is **not approved**. It is retained only as an isolated
IA/click-path artifact for Stage 0 history. Current production YFC UI, components and flows are the
only visual baseline for #387 and later implementation stages.

## Состав

Путь: `docs/app-experience-v3/stage-0/prototype/`.

Это отдельный static HTML/CSS/JS package без imports из production frontend и без API calls. Он
показывает только navigational questions:

- trainer shell и context label;
- role separation `Тренер` / `Клиент`;
- persistent-in-session UI switch `Work · Тренер` / `Personal · Для себя`;
- trainer Today, client-only home и personal home;
- desktop rail и mobile bottom navigation;
- catalog/search, exercise detail и explicit future media slot;
- active workout hierarchy block → exercise → set → action;
- Light/Dark и три exploratory directions, которые не переносятся в production.

Все действия прототипа либо меняют локальный URL state, либо показывают non-writing notice.
Изображений, downloaded/generated media, AI people и новых pipeline в package нет.

## Rejected visual exploration record

| Direction      | Что было исследовано               | Owner status                 |
| -------------- | ---------------------------------- | ---------------------------- |
| Command Stack  | action-first trainer Today         | rejected as visual direction |
| Client Radar   | multi-client attention composition | rejected as visual direction |
| Exercise Stage | catalog/detail/workout composition | rejected as visual direction |

Ни одно направление не является победителем, design specification или основанием для нового shell.
Сохраняются только вопросы IA: default trainer entry, Work/Personal context и отдельные docks.

## Render matrix

Historical screenshots and exact commands are recorded in
`.artifacts/tasks/386/evidence/prototype/PROTOTYPE_RENDER_MATRIX.md`. Minimum requested evidence:

| View     | Theme | State                                    |
| -------- | ----- | ---------------------------------------- |
| 390×844  | Light | trainer Work Today / Command Stack       |
| 390×844  | Dark  | trainer Work Today / Command Stack       |
| 1440×900 | Light | trainer Work Today / Command Stack       |
| 320×800  | Light | client-only home / Exercise Stage stress |

## Limitations

Это browser localhost evidence. Оно не является production deploy, real Telegram, physical-device,
backend authorization или media semantic approval. Перед Stage 1 нужен implementation contract для
точечного изменения существующего shared shell; visual redesign approval для этого prototype не
требуется и не предоставлялась.
