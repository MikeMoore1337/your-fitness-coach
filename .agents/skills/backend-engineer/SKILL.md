---
name: backend-engineer
description: >
  Design or change backend services, APIs, business logic, transactions and external integrations
  with production reliability. Use when server-side behavior or API contracts change. Do not use
  as the primary skill for persistence-only schema work or pure infrastructure changes.
---

# backend-engineer

Structure backend services around clear business boundaries.

## API

- Explicit request/response schemas.
- Validate at the boundary.
- Stable error contracts and correct HTTP status/protocol semantics.
- Pagination, filtering and sorting contracts.
- Version only when necessary; preserve backward compatibility.

## Business logic

- Do not hide business rules in controllers/routers.
- Make transaction boundaries explicit.
- Order side effects predictably.
- Make repeated operations idempotent when the request may be retried.

## Integrations

For external services, handle timeouts, safe retries with backoff, rate limits, partial failures, malformed responses, observability and sandbox/test doubles.

## Errors

Never return stack traces to clients. Log enough for investigation without logging secrets or sensitive data.

## Security

- Server-side authorization and least privilege.
- Input validation, safe serialization and secure secret handling.
- Protection against relevant injection, SSRF, path traversal and other attack classes.

## Privacy and data exposure

For APIs handling user or sensitive data:

- Return only necessary fields.
- Never rely on client-side filtering to hide sensitive records.
- Account for export/deletion lifecycle.
- Do not log whole payloads by default.
- Minimize data sent to external integrations.
- Authorize access to each object, not only authentication.

For data lifecycle changes, load `$privacy-engineer`.

## Tests

Cover happy paths, validation, authentication/authorization, transaction rollback, duplicate/retry scenarios, external integration failures and critical business invariants.

## Project adaptation

First identify the backend framework, module structure, contract generation process, authorization model and project commands. If API contracts generate client types or SDKs, use the existing generator workflow; never manually edit generated output.
