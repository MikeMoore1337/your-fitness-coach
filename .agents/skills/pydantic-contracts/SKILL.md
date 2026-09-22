---
name: pydantic-contracts
description: >
  Verify Pydantic request/response/domain schemas, validation boundaries and
  serialization compatibility. Use when model fields, validators or API schemas change.
---

# pydantic-contracts

## Проверяй

- required/optional/default semantics;
- nullable vs missing;
- aliases;
- enums/literals;
- validators и boundary values;
- nested models;
- datetime/timezone serialization;
- decimal/float-sensitive fields;
- extra/unknown field policy;
- backward-compatible deserialization;
- response serialization;
- OpenAPI/schema drift, если contract экспортируется наружу.

Тестируй не внутреннюю реализацию validator, а observable contract.
Для endpoint behavior подключай `$api-testing`.
