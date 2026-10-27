---
name: database-validation
description: >
  Verify database persistence, migrations, constraints, transactional behavior and
  query-visible invariants. Use when tests depend on PostgreSQL state or schema changes.
---

# database-validation

## Проверяй

- schema/migration upgrade path;
- constraints/defaults/nullability;
- transaction commit/rollback semantics;
- write -> persisted read;
- uniqueness/idempotency;
- cascade/delete behavior;
- timezone/date storage;
- race/concurrency risk;
- backward-compatible reads during rollout;
- query behavior на пустых и больших наборах, если риск существенен.

## Isolation

Предпочитай disposable/transactional/test-tenant state.
Тест не должен зависеть от случайной строки shared database.
Cleanup обязан быть детерминированным либо обеспечиваться rollback/isolated storage.

Не делай прямую DB-проверку там, где публичный contract должен быть доказан API-level assertion; DB evidence добавляется, когда persistence itself является риском.
