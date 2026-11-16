---
name: qa-engineer
description: >
  Build risk-based QA strategy and route verification to focused testing skills.
  Use when behavior changes, regressions must be prevented, release confidence is
  required, or the appropriate test layer is unclear. Prioritize critical user
  journeys and trustworthy evidence over raw test count.
---

# qa-engineer

This is a QA strategy/router, not an encyclopedia of testing tools.

## First determine

- Critical user journeys and business invariants.
- Security/privacy-sensitive paths and integration boundaries.
- Areas with high change rate or high risk.
- The cheapest reliable testing level.
- Evidence required to show that the actual risk is addressed.

## Test levels

Use a proportionate balance:

- Unit tests: isolated logic.
- Integration tests: databases, queues and boundaries.
- API/contract tests: internal and external interfaces.
- Component/UI tests: interface behavior.
- E2E tests: a small set of critical end-to-end flows.
- Visual regression: stable, critical views where visual risk is material.
- Accessibility: automated checks plus keyboard/focus verification on important flows.

Do not duplicate every scenario across all levels without reason.

## Routing

Load domain-specific skills only for actual risks:

- Playwright/Web/TMA: `$playwright-testing`.
- False-green E2E risk: `$e2e-review`.
- pytest/unit/integration design: `$pytest-test-design`.
- API contracts/HTTP: `$api-testing`.
- SQL/database persistence/migrations: `$database-validation`.
- Fixtures/factories/seed/isolation: `$test-data-management`.
- Pydantic/schema validation: `$pydantic-contracts`.
- Allure reports/evidence: `$allure-reporting`.
- Specific CI/test failure: `$failure-triage`.
- Intermittent/flaky behavior: `$flaky-analysis`.
- Risk/behavior coverage gaps: `$coverage-analysis`.

The base skill plus one or two focused skills is usually sufficient.

## Required risks

Check when relevant: validation boundaries, authentication/authorization, negative/error paths, retries/idempotency, concurrency/races, timezone/date boundaries, empty/null/large inputs, external dependency failures, migrations/backward compatibility, loading/error/empty/recovery and privacy-sensitive export/deletion/telemetry.

## Mobile/TMA continuous gate

For client-facing YFC tasks use `references/MOBILE_TMA_ACCEPTANCE_MATRIX.md` and shared harness task `50A`.

Minimum coverage:

- `360x800`, `390x844`, `430x932`.
- Touch interactions and `hover: none`.
- No horizontal overflow; touch-target review.
- Keyboard/focus/safe areas/stable viewport.
- Light/dark themes and reduced motion.
- Reload/background/offline/reconnect when state is retained.
- Mobile Web and mocked TMA parity.
- Desktop regression.

Report evidence separately for: (1) automated Mobile Web, (2) mocked TMA adapter, (3) real Telegram Android, (4) real Telegram iOS and (5) unverified environments. Never present a narrow desktop viewport as real-device verification.

## Test trust

A count of green tests alone does not prove quality. For new or materially changed critical E2E cases verify that assertions match user intent, the test fails when the feature breaks, promised side effects/persistence are demonstrated, retry/skip/conditional paths do not hide failures, and checks are not limited to optimistic UI.

## Project adaptation

Before running checks, discover existing scripts, wrappers, configs, CI gates and artifact directories. Reuse these instead of inventing commands.
