---
name: flaky-analysis
description: >
  Investigate intermittent or retry-only test failures and remove nondeterminism
  without weakening assertions. Use for pass-on-retry, order-dependent or CI-only tests.
---

# flaky-analysis

Retry - сигнал, а не исправление.

## Ищи

- async race;
- action/request observer ordering;
- animation/hydration race;
- unstable selectors;
- shared mutable state;
- order dependency;
- parallel worker collision;
- clock/timezone dependency;
- external network dependency;
- stale auth/session;
- nondeterministic seed;
- cleanup leak;
- resource contention;
- environment-specific viewport/browser behavior.

## Method

1. установи конкретный symptom;
2. сравни first failure и retry/pass;
3. проверь isolation и parallelism;
4. найди nondeterministic boundary;
5. устрани причину condition-based synchronization/isolation/data fix;
6. сохрани сильный assertion;
7. повтори targeted run достаточное число раз согласно project policy.

Не повышай timeout и retries как основной fix без доказанной причины.
