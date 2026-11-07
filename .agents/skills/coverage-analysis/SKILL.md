---
name: coverage-analysis
description: >
  Analyze risk and behavior coverage across test layers and identify meaningful gaps.
  Use when deciding what to test, auditing existing suites or preventing redundant test growth.
---

# coverage-analysis

Code coverage is supplementary; behavior/risk coverage is the main objective.

## Build a matrix

For every feature/flow list critical happy, negative/error, boundary, authorization, persistence, recovery/retry, concurrency, mobile/TMA, accessibility, privacy/security, migration/backward-compatibility and external-dependency-failure paths.

For each risk record existing test/evidence, test layer, evidence reliability, remaining gap and cheapest recommended verification layer.

## Rules

- Do not recommend E2E when unit/API/integration tests can prove the behavior more cheaply and reliably.
- Test counts are not quality metrics.
- Duplicate coverage is acceptable only for different failure modes or release-critical defense in depth.
- A critical untested risk matters more than a cosmetic code-coverage percentage.

The output must explain which risks remain unproven and why.
