# Product V11-04 / Issue #819 — acceptance audit receipt

Status at the audit commit: `NEEDS_CHANGES` until the supported Linux Firefox/WebKit
extended run is completed on this branch. No merge, deploy or Issue closure is performed by
this receipt.

## 1. Firefox/WebKit extended regression

The original scheduled failure is `39111015160`, job `Extended mobile regression (Firefox +
WebKit)`, at `frontend/tests/e2e/mobile-ui-regression.spec.ts:558`. Firefox, WebKit and the
retry all reported the same intentional WeekStrip reveal margin: a selected day button had
`left=-4`. The corrected assertion keeps document/shell geometry and the CTA checks, while
excluding only `.week-strip__day` from the broad page-level list of ordinary Today elements.

The exact extended configuration remains unchanged and selects only the intended test:

```text
frontend/playwright.mobile-regression.extended.config.ts
  mobile-firefox: Desktop Firefox, 390x844, hasTouch=true
  mobile-webkit:  iPhone 13,       390x844
  grep: @extended
```

Reproducible commands:

```powershell
cd frontend
npm run e2e:mobile-regression:extended -- --list
npm run e2e:mobile-regression:extended
```

Local Windows discovery listed exactly two tests. Local execution is not browser proof: the
host has no Playwright Firefox 153.0 build `1538` and no WebKit 26.5 build `2336`; both direct
project runs stopped at `browserType.launch` with the missing executable error. The supported
Linux proof is the existing workflow path, with no production deploy:

```text
gh workflow run ci.yml --ref codex/819-test-quality-coverage -f run_kind=weekly
```

That workflow installs Firefox/WebKit with `--with-deps`, runs the existing
`frontend-mobile-regression-extended` group, and also runs the weekly cross-browser lane. The
final result is recorded against the exact pushed SHA in the PR and Issue receipt; the ordinary
Chromium/WebKit PR lane is not substituted for this evidence.

## 2. WeekStrip and overflow boundary

No assertion requires every horizontally scrollable WeekStrip day to be inside the viewport.
The evidence is scoped as follows:

| Property | Existing or added proof | Status |
|---|---|---|
| Rail does not create page overflow | `frontend/tests/e2e/fixtures/mobile-tma.ts:380-388` checks `document.documentElement.scrollWidth <= clientWidth`; the nutrition E2E repeats it at 1440/768/390/360px (`frontend/tests/e2e/nutrition-diary.spec.ts:2277-2302`). | COVERED |
| Selected date is revealed inside the visible rail | `WeekStrip.tsx:180-193` moves only `.week-strip__days.scrollLeft`; the unit test asserts `scrollLeft > 0` and that `window.scrollTo` is not called (`frontend/tests/unit/shared/ui/WeekStrip.test.tsx:20-43`). The real E2E asserts visible `aria-current=date` and `aria-pressed=true` buttons. | COVERED |
| Ordinary Today elements remain viewport-checked | `mobile-ui-regression.spec.ts:120-128` checks the shell; the changed extended selector at `:558-560` excludes only `.week-strip__day` and still checks Today buttons, links and headings. | COVERED |
| Real outside-rail overflow remains a failure | The extended test now appends a temporary `100vw + 32px` body element, asserts the same document metric becomes overflowing, removes it, and re-runs `expectNoHorizontalOverflow`. This is a narrow negative oracle for page overflow, not a WeekStrip visibility rule. | COVERED |

The selected-date behavior therefore remains a scroll-container contract, while genuine document
overflow remains a failing condition.

## 3. API contract compatibility

The comparison used the live FastAPI application schema, not a second handwritten schema:

```powershell
& D:\Pet-projects\your-fitness-coach\.venv\Scripts\python.exe `
  scripts\export_openapi.py `
  D:\Pet-projects\your-fitness-coach\.artifacts\runtime\tmp\issue-819-openapi.json
& frontend\node_modules\.bin\openapi-typescript.cmd `
  D:\Pet-projects\your-fitness-coach\.artifacts\runtime\tmp\issue-819-openapi.json `
  -o D:\Pet-projects\your-fitness-coach\.artifacts\runtime\tmp\issue-819-schema.d.ts
git diff --no-index frontend\src\shared\api\schema.d.ts `
  D:\Pet-projects\your-fitness-coach\.artifacts\runtime\tmp\issue-819-schema.d.ts
```

Result: `GENERATED_SCHEMA_MATCH=PASS` (the last command has no diff). The live document contains
327 paths, 388 operations and 635 component schemas. The critical operation counts are:

| Area | OpenAPI operations | Consumer/test evidence | Result |
|---|---:|---|---|
| Auth and session startup | 14 | `frontend/src/shared/api/client.ts:138-158,242-306`; `backend/tests/test_app.py:2723-2799,3471-3485`; `backend/tests/test_auth_hardening.py:109-194,236-352`. | COVERED |
| Today / check-ins | 14 | `backend/tests/test_app.py:1270-1456`; Today/WeekStrip E2E and unit evidence above. | COVERED |
| Workout / history / recovery | 43 | `backend/tests/test_app.py:1513-1602,3485-3496`; existing workout unit/E2E suites; generated aliases in `frontend/src/shared/api/types.ts:124-142`. | COVERED |
| Nutrition / diary / hydration | 78 | `backend/tests/test_hydration.py:33-327`; nutrition and target-history suites; `nutrition-diary.spec.ts:2277-2305`; generated aliases in `types.ts`. | COVERED |
| Programs / exercise encyclopedia | 41 | `backend/tests/test_app.py:1028-1207,2100-2399`; `backend/tests/test_program_*.py`; generated program aliases in `types.ts:65-80`. | COVERED |
| Coach OS | 68 | `backend/tests/test_coach_attention.py`, `test_coach_crm.py`, `test_coach_inbox.py`, `test_coach_program_rollout.py`, `test_coach_reviews.py`, `test_coach_workflow_*.py`; generated Coach aliases in `types.ts:87-123`. | COVERED for current consumers and server contracts; unreferenced write surfaces are DEFERRED |

The frontend inventory found 312 direct `api()` calls. The normalized comparison matched 190
critical path/method pairs directly. The remaining eight normalized cases are deliberate
finite/dynamic expressions, manually reconciled to the live routes: day/meal/product diary
copy, conditional favorite PUT/DELETE, target-history query suffix, advance/repeat block action,
exercise-memory query/PUT/DELETE, and progress summary/analytics query suffixes. No actual
path/method incompatibility was found.

Additional contract dimensions:

| Dimension | Evidence | Result |
|---|---|---|
| Required/optional fields, nullable fields and enums | Live OpenAPI export compared byte-for-byte through the existing `openapi-typescript` output; frontend DTOs alias `components['schemas']` (`types.ts:3-12`). | COVERED at the generated schema boundary |
| Pagination | Live operations expose the actual `limit`/`offset` constraints; representative implementations are `backend/fitminiapp_api/api/v1/check_ins.py:133-138`, `nutrition.py:665-744`, and `coach.py:380-489`. | COVERED for current endpoints; no universal envelope contract is invented |
| Error contracts | FastAPI `HTTPValidationError` is present in the live schema; `client.ts:138-165` preserves status/body and handles string/object/list `detail`, while backend tests assert 401/403/404/409/422 cases. | COVERED for current transport handling; typed per-endpoint error unions are GAP |
| Auth metadata in OpenAPI | The live document has no global `security` object because YFC uses trusted dependency checks rather than a generated OAuth scheme. | GAP, covered by backend auth/RBAC tests; no schema rewrite added |
| Request-body compile-time binding | `api<T>` accepts an untyped `body` and many calls supply inline objects. | GAP/DEFERRED; no product mismatch observed and no second generator added |

The gaps are contract-test coverage limitations, not confirmed product incompatibilities. A
separate Bug is not warranted by this audit.

## 4. Localization guard and Vale pilot

`npm run lint:ui-copy` and the existing localization unit suite passed. The targeted unit suite
also passed 19/19 tests. The current guard is AST-based and checks changed user-facing JSX,
attributes, properties and calls, with an explicit allowlist for brands and technical terms.

Small anonymized corpus, executed through `node scripts/russian_user_facing_ui.mjs --stdin`:

| Corpus item | Current guard | Interpretation |
|---|---|---|
| `Start workout` | REJECT | random English covered |
| `Начать workout` | REJECT | mixed language covered |
| `aria-label="Review date"` | REJECT | accessibility copy covered |
| `Telegram` | ALLOW | legitimate brand exception |
| `API JSON HTTP URL` | ALLOW | technical abbreviations covered |
| `Сделайте чек-ин` | ALLOW | Cyrillic anglicism is a GAP |
| `RIR`, `1RM`, `AMRAP` | REJECT | possible fitness-term false positives under the current allowlist |
| `POST /api/v1/me` | REJECT | possible technical-label false positive |
| `Начать тренировку` | ALLOW | valid Russian UI covered |
| `const path = 'rollout_preview'` | ALLOW | non-user-facing identifier is ignored |

`vale` is not installed on this host and the repository has no Vale configuration or style
package. Therefore Vale false-positive/false-negative rates are `NOT_MEASURED`, not guessed.

| Question | Current guard | Vale pilot |
|---|---|---|
| Random English, mixed JSX, aria-label | ALREADY_COVERED deterministically | Would need a custom JSX/TS extraction setup |
| Brands and technical abbreviations | ALREADY_COVERED allowlist | Would need duplicate vocabulary/style rules |
| Cyrillic anglicisms and fitness vocabulary | GAP | A generic prose rule would need domain exceptions and is not proven here |
| Objective/reproducible CI result | PASS in existing lint/test path | NOT_RUN; no measured precision gain |

Decision: **REJECT Vale adoption for #819**. The current guard already covers the requested
new-copy failure mode at the AST boundary. The observed fitness/technical false positives are a
policy/allowlist decision, not evidence that an unconfigured prose linter would be better.
No Vale dependency, duplicate guard or subjective LLM evaluation is added.

## 5. Remaining acceptance audit

| Acceptance risk | Existing contract/test | Finding | Action/evidence |
|---|---|---|---|
| Weak mobile geometry oracle | Extended mobile test and shared geometry helpers | Original WeekStrip false positive confirmed; no product overflow regression found in source. | Scoped selector fix plus negative overflow probe; Linux extended run still required. |
| Export privacy / tenant isolation | `backend/tests/test_account_lifecycle.py:42-94` | Missing cross-user denial assertion was a real test gap; ownership filter already existed. | Added 404 regression assertion; local backend rerun is host-blocked, CI is authoritative. |
| Auth/RBAC and Coach access | Auth hardening, app and Coach test families above | No new incompatibility found. | Existing tests retained; #819 does not change product authorization. |
| API drift | Live OpenAPI -> existing generated types; consumer inventory above | No observed path/method/schema mismatch. | Receipt only; request typing/auth metadata remain documented GAP/DEFERRED. |
| Localization | AST guard and 19 unit cases | Current guard passes; Vale is not a proven improvement. | REJECT Vale for this PR. |
| PostgreSQL/migrations | CI `python-tests`/migrated stack contracts | Docker/PostgreSQL is not available locally. | Use exact-head GitHub CI; do not call local host proof. |
| Allure SSH publication | Scheduled report workflow and Issue #821 | Separate private publication/SSH timeout boundary. | Deferred to #821; no Allure workflow change in #819. |
| #848 / #849 isolation | PR diff is limited to this audit, two tests and receipts; separate worktrees/issues remain separate. | No overlapping production DB/recovery changes. | No changes to #848/#849. |

## 6. Delivery boundary

The existing Draft PR #1119 and branch `codex/819-test-quality-coverage` are retained. Merge,
production deploy and Issue closure are not performed. The final verdict is `NEEDS_CHANGES` until
the Linux extended Firefox/WebKit evidence and exact-head aggregate CI are green; if that receipt
passes, the PR may be reviewed for merge separately.
