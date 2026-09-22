---
name: pytest-test-design
description: >
  Design maintainable pytest unit and integration tests with clear boundaries,
  parametrization, fixtures and deterministic assertions. Use for Python test
  implementation or review outside browser E2E.
---

# pytest-test-design

## Principles

- один тест - один значимый behavior/risk;
- arrange/act/assert должен читаться без реконструкции скрытого состояния;
- параметризуй одинаковую логику, но не превращай кейсы в нечитаемую таблицу;
- fixture должна описывать состояние/ресурс, а не скрывать основное действие теста;
- scope fixture выбирай по isolation cost, а не ради скорости любой ценой;
- monkeypatch/mock применяй на boundary, который действительно не является целью теста;
- exception test должен проверять тип и значимый contract ошибки;
- regression test воспроизводит исходный defect и падает без исправления.

## Integration

Для БД подключай `$database-validation`.
Для API - `$api-testing`.
Для данных - `$test-data-management`.
Для flaky symptom - `$flaky-analysis`.

Используй существующие YFC pytest wrappers/config и не создавай альтернативный test runner.
