---
name: failure-triage
description: >
  Diagnose a concrete failed test or CI run from available artifacts and classify
  product, test, data, environment or infrastructure root cause before changing code.
---

# failure-triage

Начинай с evidence, а не с попытки переписать selector.

## Evidence order

По доступности:

1. failing assertion/error;
2. test intent;
3. trace/report/screenshot/video;
4. request/response/console/log evidence;
5. fixture/data/auth setup;
6. CI environment/config diff;
7. relevant application code.

## Classification

Классифицируй минимум как одно из:

- product regression;
- assertion/intent mismatch;
- selector drift;
- timing/race;
- auth/session;
- test data;
- environment/browser/viewport/timezone;
- network/dependency;
- test isolation;
- fixture/POM drift;
- animation/hydration;
- infrastructure/tooling.

Если падение intermittent, передай `$flaky-analysis`.

## Output

Верни:

- root cause или bounded hypotheses;
- evidence;
- reproduction;
- минимальный fix direction;
- verification command/scope;
- что осталось непроверенным.

Не лечи product defect ослаблением теста.
