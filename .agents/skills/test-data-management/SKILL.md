---
name: test-data-management
description: >
  Design deterministic test data, fixtures, factories, seeds and cleanup strategies.
  Use when tests create users, workouts, nutrition records, sessions or shared state.
---

# test-data-management

## Goals

Тестовые данные должны быть:

- deterministic по shape;
- unique там, где возможны collisions;
- минимальными для нужного behavior;
- явно связанными с test intent;
- изолированными между workers;
- очищаемыми или disposable;
- не содержащими production secrets/PII.

## Rules

- не полагайся на порядок запуска;
- не используй общий mutable counter между parallel workers;
- seed должен проходить реальные render/domain guards проверяемой surface;
- timestamps/timezones фиксируй, когда они влияют на outcome;
- random/faker допустим только если randomness не делает assertion неопределённым;
- shared fixtures должны иметь понятный owner и lifecycle.

Для сложного setup сначала ищи существующие YFC factories/fixtures/helpers.
