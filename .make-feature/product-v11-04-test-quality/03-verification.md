# Product V11-04 / Issue #819 — verification receipt

Status: static acceptance audit updated; fresh exact-head receipts pending after the final test-only commit
Exact HEAD: local final commit before push; record the pushed SHA in the GitHub receipt
Draft PR: [#1119](https://github.com/MikeMoore1337/your-fitness-coach/pull/1119)
Issue comment: [#6255004058](https://github.com/MikeMoore1337/your-fitness-coach/issues/819#issuecomment-6255004058)

## Acceptance receipts

| Criterion | Command/action | Result | Evidence |
|---|---|---|---|
| Current baseline rechecked | live Issue/PR/Actions read-back plus local inventory | confirmed | 155 unit files; 78 E2E specs / 126 E2E files; 179 Python test files; 9 frontend conditional skips; 22 Python skip/skipif lines; 0 xfail lines |
| Test-quality audit completed | source/fixture/workflow review | confirmed | auth/session, tenant/RBAC/privacy, mutations, recovery, nutrition/programs/coach, PostgreSQL, mobile/TMA and localization matrix in `02-solution.md` |
| Confirmed test gaps fixed | two test-only changes | confirmed locally | mobile selector excludes intentional `WeekStrip` scroll-rail buttons; export download-link cross-user denial asserts `404` |
| Mobile failure classified | scheduled run `39111015160` logs | confirmed | Firefox + WebKit and retry share deterministic `left=-4` geometry; not flaky and not a product overflow |
| Skips/xfails classified | static source inventory | confirmed | frontend skips are opt-in evidence/fixture-origin; Python skips are host capability or PostgreSQL-lock conditional; no xfail |
| Focused tests | Vitest WeekStrip/localization; prior backend risk set | passed/host-blocked split | 19 frontend tests passed; prior backend receipt recorded 7 passed and 78 passed/2 PostgreSQL-only skipped; this Windows rerun was stopped after the Python host-path warning/hang and is not claimed as fresh backend proof |
| Full available regression | `npm test -- --reporter=dot`, `npm run lint`, Playwright `--list` | passed/blocked split | 155 files / 949 tests passed; lint passed; 2 extended tests listed; browser execution unavailable locally |
| Exact-head CI | PR run `39165842461` | passed/obsolete for new audit commit | aggregate `checks` passed on `85fd6afbf6e7f723c3f200afc47189f65a28c74b`; scheduled-only extended Firefox/WebKit was skipped; the new audit commit requires a fresh exact-head run |
| Acceptance audit | `04-acceptance-audit.md` | complete/static | WeekStrip negative overflow probe, live OpenAPI/generated-type comparison, API matrix, localization corpus and Vale decision; Linux extended receipt remains open |
| Draft PR and Issue comment | live GitHub read-back | passed | Draft PR #1119 is open and unmerged; Issue #819 remains open with comment `6255004058` |

## Current correction receipts

| Criterion | Action | Result | Evidence |
|---|---|---|---|
| Generated API contract negative proof | Added `frontend/tests/unit/shared/api/apiContractNegativeProof.test.ts`; it invokes installed `openapi-typescript` and `typescript` against a temporary synthetic schema/consumer. | STATIC_PASS; runtime test NOT_RUN locally | Direct TypeScript check of the new test passed. Vitest could not start in the managed worktree because Windows `fs.realpathSync.native` returned `EPERM` for the worktree path; no local test pass is claimed. |
| Producer mutation coverage | Removed endpoint/method, required response field, nullable response field, enum value and request-field type are each mutated and must break the compiled consumer. | COVERED in test source; CI pending | The test asserts a compiling baseline and non-zero compile result for every mutation. |
| Safe API error boundary | Confirmed shared client used to place raw response text and structured `detail.message` into `ApiError.message`; runtime fix is isolated from #1119. | FIXED in separate Draft PR; CI pending | `codex/819-safe-api-errors` changes `client.ts`, `WarmupProposal.tsx`, `useActiveWorkoutQueue.ts` and their focused tests; raw `body` and status remain available for known codes. |
| #1119 deployment scope | Recomputed against `origin/master...HEAD` in the local final clone. | PASS: `deploy_required=false` | `changed_paths=8`, `deploy_paths=[]`; only tests/docs/tooling are in #1119. |
| #821 weekly lane | No policy or workflow change. | JUSTIFIED_DEFERRED | Scheduled cross-browser/Allure evidence remains an Issue #821 concern; cancellation is not converted into a PASS. |

## Boundaries

Production runtime, physical iPhone/Safari, native Telegram, VoiceOver, and unavailable Docker/PostgreSQL/Windows-blocked suites are not accepted as verified without direct evidence. Local `docker compose ps` could not connect to Docker Desktop; CI remains the PostgreSQL/browser evidence path.
