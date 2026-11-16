---
name: database-validation
description: >
  Verify database persistence, migrations, constraints, transactional behavior and
  query-visible invariants. Use when tests depend on PostgreSQL state or schema changes.
---

# database-validation

## Verify

- Schema/migration upgrade paths.
- Constraints, defaults and nullability.
- Transaction commit/rollback semantics.
- Writes followed by persisted reads.
- Uniqueness/idempotency.
- Cascade/delete behavior.
- Timezone/date storage.
- Concurrency/race conditions.
- Backward-compatible reads during rollout.
- Query behavior on empty/large datasets when risk is material.

## Isolation

Prefer disposable, transactional or dedicated test-tenant state. Tests must not depend on arbitrary rows in a shared database. Cleanup must be deterministic or guaranteed by rollback/isolated storage.

Do not use direct DB checks in place of API-level assertions when a public API contract is under test. Add database evidence when persistence itself is the risk.
