# Make Feature index — Product V11-04 / Issue #819

Status: test-only contract proof added; exact-head CI and runtime-hardening PR receipt pending
Mode: normal — multi-layer test audit plus scoped regression-test changes; no production mutation or irreversible data operation.
Branch: `codex/819-test-quality-coverage`
Current base: `bc48d09c3415c4b146a0400efc18cb9031413d18` (`origin/master`)
Owner authorization: implementation and Draft PR only; merge/deploy remain separate gates.

## Current stage

Implementation is split by deployment scope. The source request is preserved in `01-request.md`; audit decisions and the test matrix are in `02-solution.md`; receipts are in `03-verification.md` and the scoped acceptance audit is in `04-acceptance-audit.md`. The test-only branch contains the negative generated-consumer contract proof. Production-path API error hardening is isolated in a separate Draft PR because it must not be mixed into this no-deploy branch.

## Success criteria

- Recheck #815 baseline numbers and current master/CI evidence.
- Audit backend pytest, frontend Vitest, Playwright, PostgreSQL integration coverage and workflows against the nine requested journeys.
- Implement only confirmed test-trust gaps or reproducible test instability; do not absorb #1091, #1072, #986, #848 or #849 product/operations scope.
- Prove changed tests fail for the bad behavior where practical, then pass on the corrected test contract.
- Classify skips/xfails and the Firefox/WebKit mobile failure without weakening assertions.
- Create a Draft PR and Issue comment; do not merge, deploy or close #819.

## Current decisions

- D1: use existing test runners, fixtures and CI workflows; do not add a new framework or controller.
- D2: prioritize behavior/risk coverage over raw coverage percentage.
- D3: keep evidence boundaries explicit: local Windows, Docker/PostgreSQL, mocked browser, CI and production are separate.
- D4: if a production defect is found, record a reproduction and stop that product fix outside this PR.
- D5: the confirmed frontend error-leak defect is fixed only in the separate runtime-hardening Draft PR; #1119 remains test/docs/tooling-only and retains `deploy_required=false`.
- D6: API drift proof uses a synthetic temporary OpenAPI producer, the existing `openapi-typescript` package and a real TypeScript consumer. Mutations for endpoint/method, required field, nullability, enum and request type must fail; no production schema or second generator is added.

## Open questions / gates

- Draft PR #1119 remains open and test-only. Its previous exact-head run `39217415385` was green for `33fff54be9c98c2aaa90cba18918b46df754c301`; the added negative-proof test requires a fresh exact-head run.
- Separate runtime Draft PR `codex/819-safe-api-errors` is prepared locally from `origin/master` at `bc48d09c3415c4b146a0400efc18cb9031413d18`; its source changes require separate CI, review and release-scope classification.
- Docker/PostgreSQL and local Firefox/WebKit are unavailable on this Windows host; GitHub CI is the accepted evidence for those layers.
- Merge, deploy and Issue closure remain separate owner-authorized gates; no owner visual gate applies to this test-quality change.
