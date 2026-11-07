---
name: failure-triage
description: >
  Diagnose a concrete failed test or CI run from available artifacts and classify
  product, test, data, environment or infrastructure root cause before changing code.
---

# failure-triage

Begin with evidence, not by rewriting selectors.

## Evidence order

When available, inspect:

1. Failing assertion/error.
2. Test intent.
3. Trace/report/screenshot/video.
4. Request/response/console/log evidence.
5. Fixture/data/auth setup.
6. CI environment/configuration differences.
7. Relevant application code.

## Classification

Classify as product regression, assertion/intent mismatch, selector drift, timing/race, auth/session, test data, environment/browser/viewport/timezone, network/dependency, test isolation, fixture/POM drift, animation/hydration or infrastructure/tooling.

Route intermittent failures to `$flaky-analysis`.

## Output

Report a root cause or bounded hypotheses, evidence, reproduction, minimal fix direction, verification command/scope and what remains unverified.

Never "fix" a product defect by weakening its test.
