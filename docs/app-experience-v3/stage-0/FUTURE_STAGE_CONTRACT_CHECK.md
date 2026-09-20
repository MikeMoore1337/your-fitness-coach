# Future stage contract check

Источник sequencing: актуальный открытый roadmap #385 на 20.09.2026. Stage 0 фиксирует только
границы и не запускает ни одну следующую issue.

## Общий product/visual contract

YFC не проектируется заново. Текущий production UI, design system, components и работающие
сценарии — source of truth. Перед каждым изменением следующий Stage сначала проверяет, можно ли
решить проблему улучшением существующего flow/component. Новый pattern, shell или navigation
допустим только при доказанном ограничении текущей архитектуры.

Старый Stage 0 prototype с новой typography/cards/hero/dashboard/navigation styling — rejected
visual exploration, не design specification и не baseline для #387.

## Stage map

| Issue | Актуальная ответственность                                                                         | Stage 0 boundary                                                                                              |
| ----- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| #387  | trainer-first workspace modes, authenticated routing, context-aware navigation и shell integration | Использовать существующие `/app`, `/coach`, `AppShell`, `CoachPage`, `TrainerModeSwitch`; без global redesign |
| #388  | evidence-driven polish существующего trainer UX после #387                                         | Не создавать изменения ради Stage; менять только подтверждённые UX-проблемы                                   |
| #389  | real-human exercise media system и pilot library с provenance/license/QA                           | Existing product/catalog integration; без AI-generated people и отдельного приложения                         |
| #395  | exercise catalog expansion и canonical content quality                                             | Не расширять каталог в Stage 0; сохранить current baseline                                                    |
| #396  | provenance-backed built-in program library expansion                                               | Только реальные externally documented routines, provenance и YFC adaptation; без fabricated programs          |
| #397  | exercise substitution и advanced set/programming semantics                                         | Minimal reusable domain/behavior contract; preserve simple straight-set UX и history                          |
| #390  | exercise discovery/details/program-builder app-like UX и media migration                           | Переиспользовать current components; consumes #395/#396/#397; без second exercise DB                          |
| #391  | Active Workout v3: set logging, rest, exercise context и advanced-set rendering                    | Переиспользовать current workout/PWA foundation; не превращать экран в dashboard                              |
| #392  | personal workspace cohesion для trainer и client-only accounts                                     | Сохранить current personal UX; client-only не наследует trainer complexity                                    |
| #393  | final integration hardening, owner acceptance и single production cutover                          | Один final PR `feature/app-experience-v3 -> master`; не staged deploy                                         |

## Dependency shape

```text
#386 Stage 0
   |
   +--> #387 Stage 1 --------------------+
   |       |                             |
   |       +--> #388 Stage 2             |
   |       +--> #390 Stage 4 <--- #389 --+
   |              ^             |
   |              +--- #395 ----+
   |              +--- #396 ----+
   |              +--- #397 ----+
   |                    |
   |                    v
   |                 #391 Stage 5
   |                    |
   +--------------------+--> #392 Stage 6
                                 |
                                 v
                              #393 Stage 7
```

Stage 3 work (#389/#395/#396/#397) может идти после approved Stage 0 visual/media contract, но
вся работа интегрируется через один `feature/app-experience-v3`. #390 consumes the approved
catalog/program/semantics contracts; #391 consumes #397 and the existing workout foundation.

## Explicit non-scope for Stage 0

- не менять production source;
- не начинать #387, #388, #389, #395, #396, #397, #390, #391, #392 или #393;
- не выбирать prototype visual direction;
- не добавлять media, migrations, API/schema, feature flags или новые trainer abstractions;
- не push/merge/deploy.

После owner approval Stage 1 должен отдельно подтвердить exact integration base, routing/context
persistence, current production component reuse и client/trainer authorization regression plan.
