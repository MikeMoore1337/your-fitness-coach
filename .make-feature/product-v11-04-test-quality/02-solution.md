# Product V11-04 / Issue #819 — audit decision and plan

Status: complete for Draft PR handoff; receipt-only CI rerun pending
Version: 3
Context: fresh worktree from `origin/master` at `7b755925ad03ea50215b9260b82e8c48cd506d22`.

## Requirements

The request requires a factual test-quality audit and scoped implementation, not a test-count exercise. The output must distinguish confirmed false positives, legitimate skips, environment blocks and untested risks, then provide exact-head evidence in a Draft PR and Issue comment.

## Baseline facts and sources

- `docs/development/product-v11-00-baseline-2026-10-18.md` from #815 records the prior baseline: 155 frontend unit-test files, 949 passed tests, 126 E2E files, 11 Python skip markers, 21 `test.skip` references, scheduled mobile failure at `mobile-ui-regression.spec.ts:545`, and separate Allure SSH timeout.
- Current HEAD is the merged baseline PR revision `7b755925ad03ea50215b9260b82e8c48cd506d22`; all counts and CI claims must be recomputed here.
- GitHub is the operational source of truth for #819, #815, related PRs, Checks and Actions. Local snapshots are evidence only.
- Current inventory on that HEAD: 155 frontend unit files, 78 E2E spec files / 126 E2E tree files, 179 Python test files across backend/tests/tests/bot/tests, 9 conditional frontend skip lines, 22 Python skip/skipif lines, and no xfail lines.
- Scheduled run `39111015160` failed only in `Extended mobile regression (Firefox + WebKit)` at the broad viewport selector; both browsers and the retry returned the intentional `WeekStrip` day button at `left=-4`. The separate Allure report also failed closed on incomplete results and then recorded an SSH `connection_timeout`.

## Chosen approach

Use existing pytest/Vitest/Playwright/PostgreSQL fixtures and workflow contracts. First inventory and run narrow representative tests; then inspect high-risk paths and only patch a confirmed weak assertion, fixture, skip, or deterministic test cause. Avoid broad production changes and avoid adding duplicate E2E coverage where a unit/API/integration assertion proves the invariant more cheaply.

## Coverage matrix to maintain

| Risk | Existing evidence | Trust question | Cheapest missing proof |
|---|---|---|---|
| Auth/session startup | tests and fixtures after inventory | Does the test reject unauthenticated/fallback success? | API/component regression |
| Tenant/RBAC/privacy | backend/API/E2E coverage | Is denial tied to the other tenant/role and persisted data? | pytest/API integration |
| Today/workout/rest/offline | Vitest/Playwright and #1091 coverage | Is recovery/persistence proven, not only optimistic DOM? | focused component/API/E2E |
| Nutrition/programs/coach | unit/API/E2E inventory | Are negative, empty and boundary paths asserted? | targeted unit/API |
| Mutation idempotency/conflicts | backend tests/source scan | Is duplicate/retry/stale revision behavior observable? | pytest integration |
| DB transaction/migration/legacy | migration and PostgreSQL tests | Are rollback/isolation and old rows exercised? | PostgreSQL integration |
| Mobile/TMA reconnect | scheduled and release smoke | Is the failure product, assertion, viewport or environment? | reproduce on same config |
| Russian localization | AST guard/unit inventory | Are allowed brands/technical terms preserved while new English is rejected? | guard corpus/unit |

## Plan and files

1. Read current CI/workflow/test configuration and live Issue/PR evidence.
2. Count tests/skips and map the nine journeys to real files, fixtures and assertions.
3. Reproduce the scheduled mobile failure and inspect its geometry/intent before editing.
4. Run focused backend/frontend/browser tests that are available locally; record exact commands and environment limitations.
5. Implement the smallest confirmed test-only changes, with a regression test that fails under the wrong behavior when feasible.
6. Run targeted checks, available full suites and repository-native checks on the final SHA.
7. Commit, push branch, create Draft PR linked to #819, add evidence comment, and re-read PR/Issue state.

## Main failure risks

- Stale worktree or stale Vite preview could create false failures.
- Windows virtualenv/Docker limitations may prevent complete backend/PostgreSQL proof.
- A scheduled failure may be a viewport-specific test assumption; changing the assertion without reproducing would weaken regression truth.
- Current master may have advanced since #815; no prior count is accepted without a fresh read.

## Implemented findings

- `frontend/tests/e2e/mobile-ui-regression.spec.ts`: exclude `.week-strip__day` from the page-level element-in-viewport selector. The shared shell geometry and document overflow assertions remain intact; the scroll rail is intentionally allowed to reveal its selected day.
- `backend/tests/test_account_lifecycle.py`: add the missing cross-user `POST /api/v1/me/exports/{export_id}/download-link` denial assertion (`404`). Runtime ownership filtering already existed; the test now protects it from future weakening.
- Allure publication and CI routing were audited but not changed: `checks` verifies required result groups, and Allure remains a separate scheduled/private publication concern for #821.

## Current-scope additions

- `frontend/tests/unit/shared/api/apiContractNegativeProof.test.ts` is a single Vitest regression test for the producer-to-generated-consumer boundary. It writes a temporary synthetic OpenAPI document, invokes the repository's installed `openapi-typescript`, then compiles a TypeScript consumer with the repository's installed TypeScript compiler. Five representative producer mutations are required to fail compilation: removed endpoint method, removed required response field, changed nullability, removed enum value and changed request-field type.
- The frontend client defect found during the boundary audit is not folded into this test-only PR. Raw non-JSON/technical response text could become `ApiError.message`, and two UI paths read a structured backend `detail.message` directly. The minimal fix is isolated to runtime Draft PR `codex/819-safe-api-errors`: the shared client keeps raw `body` and `status` for machine-readable codes, emits Russian status fallbacks, and the two direct consumers use the shared safe-message helper. This preserves 401 refresh/clear behavior and 403 session retention.
- No timeout, retry, Allure or weekly cross-browser policy was changed. #821 remains a separate boundary.
