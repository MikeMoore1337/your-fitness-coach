# Make Feature index — Product V11-04 / Issue #819

Status: acceptance audit complete; Linux extended receipt pending
Mode: normal — multi-layer test audit plus scoped regression-test changes; no production mutation or irreversible data operation.
Branch: `codex/819-test-quality-coverage`
Base at start: `7b755925ad03ea50215b9260b82e8c48cd506d22` (`origin/master`)
Owner authorization: implementation and Draft PR only; merge/deploy remain separate gates.

## Current stage

Implementation and static/local verification are complete. The source request is preserved in `01-request.md`; the audit decisions and test matrix are in `02-solution.md`; receipts are in `03-verification.md` and the scoped acceptance audit is in `04-acceptance-audit.md`. Supported Linux Firefox/WebKit extended evidence remains the final open receipt.

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

## Open questions / gates

- Draft PR #1119 and Issue comment #6255004058 were created/read back. Prior exact-head run `39165842461` passed its executable PR jobs; the new audit commit requires a fresh exact-head run and the supported weekly extended lane.
- Docker/PostgreSQL and local Firefox/WebKit are unavailable on this Windows host; GitHub CI is the accepted evidence for those layers.
- Merge, deploy and Issue closure remain separate owner-authorized gates; no owner visual gate applies to this test-quality change.
