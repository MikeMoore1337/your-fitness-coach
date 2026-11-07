---
name: api-testing
description: >
  Verify HTTP/API behavior, contracts, authorization, idempotency and failure
  semantics. Use for FastAPI endpoints, integration APIs and API-facing regressions.
---

# api-testing

Test APIs as contracts, not just HTTP status codes.

## Minimum contract

When relevant, verify method/path/query/body semantics, status codes, response schemas/business fields, authentication/authorization, validation boundaries, error shapes, idempotency/retry behavior, pagination/filtering/sorting, concurrency-sensitive writes, backward compatibility and safe failure observability.

## Evidence

For writes, prove the required side effect through the response, database/state/event or a subsequent read. HTTP `200` alone does not prove the business operation succeeded.

For FastAPI/Pydantic schema-sensitive changes, load `$pydantic-contracts`; for persistence, load `$database-validation`.
