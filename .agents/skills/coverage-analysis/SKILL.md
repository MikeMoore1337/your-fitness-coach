---
name: coverage-analysis
description: >
  Analyze risk and behavior coverage across test layers and identify meaningful gaps.
  Use when deciding what to test, auditing existing suites or preventing redundant test growth.
---

# coverage-analysis

Code coverage - вспомогательный сигнал. Главный объект - behavior/risk coverage.

## Build a matrix

Для feature/flow перечисли:

- critical happy path;
- negative/error;
- boundary;
- auth/authz;
- persistence;
- recovery/retry;
- concurrency;
- mobile/TMA;
- accessibility;
- privacy/security;
- migration/backward compatibility;
- external dependency failure.

Для каждого риска укажи:

- existing test/evidence;
- test layer;
- доверие к доказательству;
- gap;
- recommended cheapest layer.

## Rules

- не предлагай E2E, если unit/API/integration дешевле и достаточно надёжны;
- не считай число tests метрикой качества;
- duplicate coverage допустим только для разных failure modes или release-critical defense in depth;
- критичный gap важнее косметического процента code coverage.

Output должен объяснять, какие риски реально не доказаны и почему.
