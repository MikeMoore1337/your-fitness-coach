---
name: test-data-management
description: >
  Design deterministic test data, fixtures, factories, seeds and cleanup strategies.
  Use when tests create users, workouts, nutrition records, sessions or shared state.
---

# test-data-management

## Goals

Test data must be deterministic in shape, unique when collisions are possible, minimal for the behavior, explicitly connected to test intent, isolated between workers, disposable or cleanable, and free of production secrets or personal data.

## Rules

- Do not depend on test execution order.
- Do not share a mutable counter between parallel workers.
- Seeds must pass actual render/domain guards of the surface being tested.
- Fix timestamps/timezones whenever they affect outcomes.
- Random/faker data is acceptable only when randomness cannot make assertions nondeterministic.
- Shared fixtures need a clear owner and lifecycle.

For complex setup, first look for existing YFC factories, fixtures and helpers.
