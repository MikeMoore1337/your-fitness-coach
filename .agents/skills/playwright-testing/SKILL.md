---
name: playwright-testing
description: >
  Design, implement and maintain reliable Playwright tests for YFC Web and TMA.
  Use for browser E2E, visual checks, responsive/mobile verification, auth,
  network evidence, fixtures, debugging and Playwright configuration.
---

# playwright-testing

Write Playwright tests that actually prove user behavior and produce actionable failure evidence.

## Baseline

- Prefer semantic locators using role, label and accessible name.
- Use CSS/test IDs only when semantic contracts are insufficient or geometry/style is under test.
- Use web-first assertions and automatic waiting; avoid fixed sleeps.
- Keep tests independent of ordering and isolated.
- Put shared setup in fixtures/helpers, not module-level mutable state.
- Reuse existing project URLs, configuration, authentication and test infrastructure.
- Do not add a competing fixture layer when the YFC harness already covers the need.

## Test intent

Before coding, state:

- Given: the state guaranteed to exist.
- When: the user action performed.
- Then: the observable result the test must prove.

If the scenario promises persistence or a backend side effect, a visual change alone is insufficient. Verify request/response, persisted state, reload or re-entry at the appropriate level.

## Locator order

1. `getByRole` with accessible name.
2. `getByLabel`.
3. Stable project-owned test ID.
4. Scoped text locator.
5. CSS for structure, geometry or a visual contract.
6. XPath only when alternatives are impractical.

Never turn accessible copy into a fragile global substring selector.

## Assertions and waiting

- Assert the promised state, not merely existence of an element handle.
- After navigation/actions, wait for the required outcome rather than a fixed delay.
- Arm request observers/interception **before** triggering the action.
- Assert absence only after proving the UI reached a state in which the element must disappear.
- Prove collections are nonempty before relying on assertions inside a loop.

## Network and mocking

- Do not mock YFC's own layer merely to turn an end-to-end contract test green.
- Stabilize third-party dependencies with controlled mocks when appropriate.
- For critical optimistic writes, prove the call and persistence.
- Cover offline/reconnect only when relevant to the task or risk.

## Authentication

Reuse project auth fixtures, `storageState` and setup. Never hardcode literal credentials in test specs. A protected-route test must prove it reached the intended authenticated surface, not a login/fallback page.

## Mobile/TMA

Follow the YFC Mobile/TMA acceptance matrix. Report automated viewport evidence separately from real Telegram device evidence. Check keyboard, safe areas, touch, sticky layers, viewport resizing and reload/resume where relevant.

## Visual and geometry checks

Screenshot baselines are valuable only for stable contracts. Explicit geometry assertions may verify touch targets, overlap, clipping, centering and safe areas. Confirm the locator should be rendered/visible before making non-null geometry assertions.

## Failure evidence

Prefer existing traces, screenshots, videos, Playwright reports and request/console evidence. Determine whether a failure is a product defect or a test defect before editing selectors.
