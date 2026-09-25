# YFC Design Guardrails v7

Этот файл определяет минимальные устойчивые рамки дизайна. Он намеренно не является подробной дизайн-системой.

## Hard constraints

Сохранять:

1. YFC остаётся sport-tech продуктом.
2. Client-facing продукт проектируется mobile-first.
3. Lime, black и white остаются фирменным цветовым ядром.
4. Реальные данные, продуктовые возможности и состояния нельзя искажать ради визуального эффекта.
5. Accessibility и usable interaction являются обязательными.
6. Визуальные эффекты не должны делать core flow неприемлемо медленным или нестабильным.

## Current baseline vs redesign

Before changing visible authenticated UI, read:

1. `codex-backlog/ACTIVE_DESIGN_SOURCE.md`;
2. this file;
3. `docs/design/YFC_PRODUCT_UI_CONTRACT.md`.

Ordinary product work is **EVOLVE**. Words such as "improve", "modernize", "app-like", "Stage",
"v3" and "polish", App Experience naming, or an external reference do not imply **RETHINK** and
do not authorize a parallel visual system. **RETHINK** requires a separate owner-approved
redesign/exploration task, explicit bounded scope and owner selection of the direction before
rollout.

### Ordinary feature/fix task

Если task не является redesign/exploration:

- сохраняй текущую active production систему;
- переиспользуй существующие компоненты/tokens;
- не создавай параллельный visual language;
- не меняй глобальную дизайн-систему как побочный refactor.

### Dedicated design task

Если task явно разрешает design exploration/redesign, можно пересматривать полностью:

- Design V2/V2.1;
- typography;
- grids;
- spacing;
- radii;
- cards/surfaces;
- shadows;
- gradients;
- glow;
- transparency/glass;
- 3D/illustration/photo language;
- iconography;
- charts/data visualization;
- navigation;
- interaction model;
- motion;
- landing composition;
- light/dark system;
- shared components.

Текущий дизайн в таком режиме является evidence/anti-reference/baseline, а не обязательным ответом.

## Wow + practicality

Хороший YFC interface должен одновременно:

- быстро решать задачу;
- ощущаться отзывчивым;
- иметь собственный характер;
- быть визуально запоминающимся;
- создавать удовольствие от регулярного использования;
- поддерживать ощущение энергии, прогресса и sport-tech precision.

"Вау" допустим и в частых продуктовых сценариях - workout, nutrition, progress, logging - если он встроен в действие и не превращается в помеху.

## Apple-style references

Apple-like interaction/material principles и Liquid Glass могут использоваться как reference layer,
но не как отдельная бренд-система. При таком direction:

- YFC остаётся sport-tech, а не iOS clone;
- lime/black/white brand core сохраняется;
- Apple-like materials должны усиливать hierarchy/interaction, а не покрывать glass-эффектом каждый layer;
- physical motion, sheets, gestures и springs должны быть interruptible, responsive и иметь reduced-motion alternative;
- `$apple-design` используется условно вместе с YFC design skills, а не вместо них.

## Pattern neutrality

Не существует автоматического запрета только потому, что решение называется:

- glassmorphism;
- glow;
- gradient;
- card;
- bento;
- large type;
- asymmetry;
- 3D;
- animation;
- blur;
- skeuomorphism.

Оценивай:

- зачем это нужно;
- насколько это YFC-specific;
- качество исполнения;
- читаемость;
- interaction;
- performance;
- accessibility;
- mobile behavior.

## Owner checkpoint

Массовая смена visual system требует owner-approved design task/decision.

После выбора новой production системы обновить:

- `codex-backlog/ACTIVE_DESIGN_SOURCE.md`;
- durable design docs;
- tokens/components;
- применимые backlog contracts.
