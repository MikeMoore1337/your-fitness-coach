---
name: pytest-test-design
description: >
  Design maintainable pytest unit and integration tests with clear boundaries,
  parametrization, fixtures and deterministic assertions. Use for Python test
  implementation or review outside browser E2E.
---

# pytest-test-design

## Principles

- One test should cover one meaningful behavior or risk.
- Arrange/act/assert should be understandable without reconstructing hidden state.
- Parametrize repeated logic without building unreadable test-case tables.
- Fixtures describe state/resources; they must not hide the test's primary action.
- Select fixture scope based on isolation cost, not speed at any cost.
- Use monkeypatch/mocks at a boundary that is genuinely outside test scope.
- Exception tests assert the exception type and meaningful error contract.
- Regression tests reproduce the original defect and fail without the fix.

## Integration

For databases use `$database-validation`; for APIs use `$api-testing`; for test data use `$test-data-management`; for flaky behavior use `$flaky-analysis`.

Reuse existing YFC pytest wrappers/configuration; do not introduce another test runner.
