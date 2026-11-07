---
name: flaky-analysis
description: >
  Investigate intermittent or retry-only test failures and remove nondeterminism
  without weakening assertions. Use for pass-on-retry, order-dependent or CI-only tests.
---

# flaky-analysis

A retry is a signal, not a fix.

## Investigate

Async races, observer/action ordering, animation/hydration races, unstable selectors, shared mutable state, order dependencies, parallel worker collisions, clock/timezone dependencies, external networks, stale authentication/session, nondeterministic seeds, cleanup leaks, resource contention and environment-specific browser/viewport behavior.

## Method

1. Establish the exact symptom.
2. Compare first failure against retry/pass.
3. Inspect isolation and parallelism.
4. Identify the nondeterministic boundary.
5. Remove its cause through condition-based synchronization, isolation or corrected test data.
6. Preserve strong assertions.
7. Repeat targeted runs sufficiently according to project policy.

Do not treat increased timeouts/retries as the primary fix without evidence of the root cause.
