---
name: api-testing
description: >
  Verify HTTP/API behavior, contracts, authorization, idempotency and failure
  semantics. Use for FastAPI endpoints, integration APIs and API-facing regressions.
---

# api-testing

Проверяй API как контракт, а не только status code.

## Minimum contract

По применимости проверяй:

- method/path/query/body semantics;
- status code;
- response schema и business fields;
- auth/authz;
- validation boundaries;
- error shape;
- idempotency/retry behavior;
- pagination/filter/sort;
- concurrency/race-sensitive writes;
- backward compatibility;
- observability-safe failure behavior.

## Evidence

Для write-flow докажи нужный side effect через ответ, DB/state/event или последующий read.
Не считай `200` доказательством корректной бизнес-операции.

Для FastAPI/Pydantic schema-sensitive изменений подключай `$pydantic-contracts`.
Для persistence - `$database-validation`.
