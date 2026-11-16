---
name: pydantic-contracts
description: >
  Verify Pydantic request/response/domain schemas, validation boundaries and
  serialization compatibility. Use when model fields, validators or API schemas change.
---

# pydantic-contracts

## Verify

- Required/optional/default semantics and nullable versus absent fields.
- Aliases, enums/literals and validators including boundary values.
- Nested models and datetime/timezone serialization.
- Decimal/float-sensitive fields.
- Extra/unknown field policy.
- Backward-compatible deserialization and response serialization.
- OpenAPI/schema drift when exporting a public contract.

Test observable contracts rather than validator implementation details. For endpoint behavior load `$api-testing`.
