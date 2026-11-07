---
name: e2e-review
description: >
  Independently review Playwright/Cypress-style end-to-end tests for false greens,
  weak assertions, bypasses, hidden skips, missing side-effect proof and test smells.
  Use after AI- or human-written E2E changes and for trust audits of existing specs.
---

# e2e-review

The question is not simply "is the test green?" but "does it actually prove the promised behavior?"

## Review contract

For each changed, critical E2E scenario:

1. Read the test name and declared intent.
2. Identify Given, When and Then.
3. Determine which broken behavior should cause failure.
4. Verify assertions actually detect that break.
5. Check isolation, authorization, data and runtime assumptions.
6. Distinguish introduced/worsened findings from pre-existing debt.

## P0: false greens and silent bypasses

Look for:

- Names promising an outcome while assertions only check a generic container.
- Actions without meaningful Then assertions.
- Swallowed errors or committed focused tests.
- Locator/Promise/boolean assertions that are almost always true.
- Conditional branches skipping mandatory steps.
- Protected-surface tests without guaranteed authentication.
- Optimistic UI mistaken for proof of backend writes.
- Critical checks placed only inside potentially empty loops.

## P1: reliability and diagnosis

Look for missing await, fixed sleeps, unstable nth/substring selectors without justification, unnecessary serial/shared state, retries masking reproducible failures, stale manually captured authentication state, unjustified forced actions, direct selector APIs that bypass locator contracts and test data depending on shared persistent environments.

## P2: maintainability

Look for zombie/duplicate tests, unused helpers/POM methods, unexplained skips with no revisit condition, meaningless abstraction and excessive duplicate testing of the same risk at one layer.

## Required evidence

Every finding must state severity, spec/test, promised intent, actual evidence, how the test can falsely pass and a concrete fix direction.

Do not automatically label a suspicious pattern as a defect; the actual test context is authoritative.

## Scope

This skill reviews E2E quality. UI aesthetics belong to `$ui-audit`; Playwright implementation patterns belong to `$playwright-testing`.
