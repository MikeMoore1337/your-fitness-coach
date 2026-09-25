# Активный production source of truth по дизайну

## Текущий статус

```text
ACTIVE_DESIGN = DESIGN_V2_1
STATUS = CURRENT_PRODUCTION_BASELINE_WITH_OWNER_APPROVED_SELECTED_PULSE_PILOT
DESIGN_REVIEWABILITY = FULLY_REVISABLE_BY_OWNER_APPROVED_DESIGN_TASK
BRAND_CORE = SPORT_TECH + MOBILE_FIRST + LIME_BLACK_WHITE
OWNER_DECISION_75A = START_RETHINK_EXPLORATION
OWNER_DECISION_75B = SELECT_DIRECTION_PULSE
OWNER_DECISION_75C = APPROVED
CURRENT_PILOT_TASK = 75C_COMPLETED_AND_ARCHIVED
```

`DESIGN_V2_1` остаётся текущей production baseline для Landing, `/login`, authenticated Web, Mobile Web и TMA до тех пор, пока отдельная owner-approved design task не выберет и не активирует новую систему.

Baseline нужен для consistency обычных feature/fix tasks. Он не является вечной эстетической догмой.

## App Experience v3 и approved trainer baseline

App Experience v3 — это production evolution, а не permission на RETHINK. Текущий production YFC
UI остаётся visual source of truth. Rejected Stage 0 prototype не является design source и не
должен копироваться в authenticated product.

После owner approval действуют следующие bounded interaction references:

- #387: trainer-first entry, явный workspace switch `Для себя / Клиенты`, trainer context с
  mobile dock/desktop sidebar и без duplicate global navigation;
- #388: navigation-first trainer IA — короткий `Сегодня`, `Ещё` hub и focused destinations;
  mobile primary card CTA full-width, secondary navigation имеет явную affordance, stacked actions
  используют token-based gap;
- client `Профиль` / `Прогресс` и trainer #388 — references для interaction intent, не literal
  templates для копирования.

Durable production rules находятся в `docs/design/YFC_PRODUCT_UI_CONTRACT.md`. Обычные tasks
работают в EVOLVE; RETHINK требует отдельной owner-approved redesign/exploration task, bounded
scope и owner selection направления до rollout.

27.08.2026 владелец одобрил результат Rethink-аудита `75A`, выбрал
`START_RETHINK_EXPLORATION`, затем завершил selection gate `75B` решением
`SELECT_DIRECTION_PULSE`. Это решение не активирует отдельную новую дизайн-систему и не разрешает
массовый redesign/rollout. `DESIGN_V2_1` и текущие canonical paths сохраняются. Task `75C`
реализовала ограниченный перенос выбранных концепций поверх существующего production UI, получила
owner screenshot approval 28.08.2026 и архивирована.

В owner-approved scope `75C` входят только:

- smooth lime area chart;
- форма floating bottom dock с текущими production icons/labels;
- выборочные линии, геометрия и градиенты current-action/insight/completion cards;
- Pulse motion grammar с reduced-motion и performance budget.

Landing/Login, typography, layout hierarchy, content и product flows не перерисовываются.

Pilot использует canonical `TimeSeriesChart`, `AppShell`, production icons и текущие
Today/completion surfaces. Новые styles загружаются с authenticated `MiniAppPage`, не входят в
initial public bundle и не создают новую runtime dependency. Browser/Mobile Web/mocked TMA
evidence не является real Telegram, physical-device или field-performance подтверждением.

## Что является устойчивым

Независимо от конкретной версии дизайна сохраняются:

- YFC как sport-tech продукт;
- mobile-first подход для client-facing flows;
- lime, black и white как фирменное цветовое ядро;
- фактическое поведение продукта и data truth;
- accessibility;
- usability;
- performance feasibility;
- единый продукт Web + TMA, если task не меняет platform strategy.

## Что можно пересматривать

В отдельной design exploration/redesign task можно пересмотреть полностью:

- Design V2/V2.1;
- typography;
- spacing;
- grid;
- radii;
- card/surface model;
- shadows;
- gradients;
- glow;
- glass/transparency;
- 3D/illustration/photo language;
- iconography;
- charts/data visualization;
- navigation;
- Landing composition;
- authenticated app composition;
- light/dark visual system;
- motion language;
- shared components;
- current visual motifs.

Current V2.1 docs/renders в такой задаче являются evidence/current baseline, а не обязательным visual answer.

## Ordinary implementation tasks

Если task не является redesign/exploration:

1. использовать текущий active baseline;
2. переиспользовать existing tokens/components;
3. не создавать случайный parallel design system;
4. не расширять scope визуальным redesign;
5. исправлять drift относительно текущей production system.

Это правило не означает, что baseline нельзя заменить отдельной design task.

## Dedicated design task

Design task может:

- сравнивать несколько направлений;
- использовать новые design/motion skills;
- создавать isolated prototypes;
- предлагать полный replacement visual system;
- переосмысливать ранее утверждённые V2.1 решения.

До массовой production реализации нужен owner selection/checkpoint. Для выбранного bounded scope
этот checkpoint завершён owner approval task `75C`; он не разрешает автоматически расширять pilot
до полного Pulse restyle.

После выбора новая система должна:

- получить собственные durable design docs/tokens/contracts;
- обновить этот файл;
- определить migration/rollout scope;
- обновить применимые backlog contracts.

## Current V2.1 reference paths

Пока новая система не активирована, текущими reference paths остаются:

1. `docs/design/design-direction-v2.1.md`
2. `docs/design/responsive-v2.1.md`
3. `docs/design/component-states-v2.1.md`
4. `docs/design/landing-login-v2.1.md`
5. `docs/design/tma-platform-v2.1.md`
6. `docs/design/references/design-v2.1/README.md`
7. `codex-backlog/archive/DESIGN_V2_1_INTEGRATION_NOTES.md`

Они описывают текущий baseline, а не вечные запреты.

## Historical artifacts

Tasks `49A-49G`, прежние renders и pilots остаются historical evidence. Они не создают второй active source и не запрещают будущий redesign.

## Activation rule

Изменение active production design происходит только через явное owner решение в design task.

До такого решения production tasks не должны самовольно смешивать V2.1 с новыми экспериментальными направлениями.
