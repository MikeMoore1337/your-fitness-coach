# QA automation architecture v1

## Purpose

YFC keeps implementation and read-only QA roles as optional working modes.
Merge, deployment and release state belongs to GitHub, not to an agent role.

## QA work profiles

| Профиль | Lifecycle owner | Core skills |
| --- | --- | --- |
| qa-architect | qa-verifier / orchestrator for genuine multi-stream scope | qa-engineer + coverage-analysis |
| test-implementer | implementer | qa-engineer + relevant implementation skill |
| test-reviewer | qa-verifier | qa-engineer + e2e-review or pytest-test-design |
| ci-investigator | qa-verifier | failure-triage + relevant framework skill |
| flaky-analyst | qa-verifier | flaky-analysis + relevant framework skill |
| coverage-analyst | qa-verifier | coverage-analysis + qa-engineer |

Это modes, не новые entries в `.agents/roles`.

## Skill map

- strategy/router: qa-engineer
- browser implementation: playwright-testing
- E2E trust review: e2e-review
- Python tests: pytest-test-design
- HTTP contracts: api-testing
- persistence: database-validation
- fixtures/seeds: test-data-management
- Pydantic schemas: pydantic-contracts
- report evidence: allure-reporting
- concrete failure: failure-triage
- intermittent failure: flaky-analysis
- risk gaps: coverage-analysis
- visual/product quality: ui-audit remains authoritative

## External inspiration

The contracts are YFC-authored and not vendored copies.

Useful external references considered during design:

- testdino-hq/playwright-skill - broad Playwright practices and trace/debug/test architecture guidance (MIT);
- voidmatcha/e2e-skills - false-green review concepts and failure taxonomy (Apache-2.0);
- mauricio2093/playwright-audit-skill - audit/evidence/reporting ideas; only general concepts were used.

YFC project conventions, GitHub Flow, existing harnesses and Mobile/TMA evidence rules take precedence over generic examples from those projects.

## Routing principle

Typical QA pass: `$qa-engineer` + 1-2 domain skills.

Do not load all QA skills together.
