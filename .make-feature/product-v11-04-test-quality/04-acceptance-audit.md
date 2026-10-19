# Product V11-04 / Issue #819 — acceptance audit receipt

Status for the current test-bearing line at the local final commit:
`NEEDS_WORK` until the added negative-proof test is pushed and its exact-head required CI is
green. The previous required PR CI run
[39217415385](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39217415385)
was green for the prior head; no merge, deploy or Issue closure is performed by this receipt.

## 1. Firefox/WebKit extended regression

The original scheduled failure is `39111015160`, job `Extended mobile regression (Firefox +
WebKit)`, at `frontend/tests/e2e/mobile-ui-regression.spec.ts:558`. Firefox, WebKit and the
retry all reported the same intentional WeekStrip reveal margin: a selected day button had
`left=-4`. The corrected assertion keeps document/shell geometry and the CTA checks, while
excluding only `.week-strip__day` from the broad page-level list of ordinary Today elements.

The exact extended configuration remains unchanged and selects only the two intended tests:

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

After the merge from current `origin/master`, the focused local browser run passed on both
projects:

```text
npm run e2e:mobile-regression:extended -- --project=mobile-firefox --project=mobile-webkit
4 passed (10.3s)
```

This is Windows Firefox/WebKit evidence, not a claim of physical-device, Telegram-native or
Linux-run equivalence. The supported Linux proof remains the existing workflow path, with no
production deploy:

```text
gh workflow run ci.yml --ref codex/819-test-quality-coverage -f run_kind=weekly
```

The PR workflow's exact-head required result is green, while its router correctly skips the
scheduled-only `frontend-mobile-regression-extended` and weekly cross-browser jobs. The ordinary
Chromium/WebKit PR lane is not substituted for the focused local Firefox/WebKit evidence; the
local run is reported separately above.

## 2. WeekStrip and overflow boundary

No assertion requires every horizontally scrollable WeekStrip day to be inside the viewport.
The evidence is scoped as follows:

| Property | Existing or added proof | Status |
|---|---|---|
| Rail does not create page overflow | `frontend/tests/e2e/fixtures/mobile-tma.ts:380-388` checks `document.documentElement.scrollWidth <= clientWidth`; the nutrition E2E repeats it at 1440/768/390/360px (`frontend/tests/e2e/nutrition-diary.spec.ts:2277-2302`). | COVERED |
| Selected date is revealed inside the visible rail | `WeekStrip.tsx:180-193` moves only `.week-strip__days.scrollLeft`; the unit test asserts `scrollLeft > 0` and that `window.scrollTo` is not called (`frontend/tests/unit/shared/ui/WeekStrip.test.tsx:20-43`). The focused E2E now changes the selected date at 320px and compares the real `.week-strip__days` and selected-button bounding rectangles, asserting intersection and containment without requiring all seven days to be visible. | COVERED |
| Ordinary Today elements remain viewport-checked | `mobile-ui-regression.spec.ts:120-128` checks the shell; the changed extended selector at `:558-560` excludes only `.week-strip__day` and still checks Today buttons, links and headings. | COVERED |
| Real outside-rail overflow remains a failure | The extended test appends a temporary `100vw + 32px` body element, proves the document metric is overflowing, asserts that `expectNoHorizontalOverflow()` itself rejects, removes the probe in `try/finally`, and then re-runs the helper after cleanup. This is a narrow negative oracle for page overflow, not a WeekStrip visibility rule. | COVERED |

The selected-date behavior therefore remains a scroll-container contract, while genuine document
overflow remains a failing condition.

## 3. Weekly cross-browser boundary (#821)

Workflow [39168451628](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39168451628)
is completed with conclusion `CANCELLED`; it is not `in_progress`. It is not WeekStrip evidence
and is not a weekly PASS:

- the Chromium, Firefox and WebKit lanes each scheduled 952 browser tests;
- the 60-minute cross-browser lane ended with numerous Playwright timeouts and approved visual
  baseline `#895` errors before cancellation;
- three Allure uncompressed bundle-limit violations exceeded the 50 MiB limit;
- the generated Allure report was incomplete, although publication metadata still recorded
  `published`, and the scheduled publication/aggregate result failed closed.

This is the separate CI-efficiency/regression-truth boundary tracked by [Issue
#821](https://github.com/MikeMoore1337/your-fitness-coach/issues/821). No timeout increase,
retry addition or Allure workflow change was made in #819. The cancelled weekly lane is not
mixed with the independently passing focused WeekStrip/overflow tests.

## 4. API contract compatibility

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

## 5. Localization guard and Vale pilot

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

## 6. Remaining acceptance audit

| Acceptance risk | Existing contract/test | Finding | Action/evidence |
|---|---|---|---|
| Weak mobile geometry oracle | Focused local Firefox/WebKit run plus exact-head required CI | Original WeekStrip false positive confirmed; the changed-date rect assertion and overflow negative proof pass. | Linux scheduled-only extended lane is `NOT_RUN` by the PR router; owner may request a separate scheduled run if that platform-specific evidence is needed. |
| Export privacy / tenant isolation | `backend/tests/test_account_lifecycle.py:42-94` | Missing cross-user denial assertion was a real test gap; ownership filter already existed. | Added 404 regression assertion; local backend rerun is host-blocked, CI is authoritative. |
| Auth/RBAC and Coach access | Auth hardening, app and Coach test families above | No new incompatibility found. | Existing tests retained; #819 does not change product authorization. |
| API drift | Live OpenAPI -> existing generated types; consumer inventory above | No observed path/method/schema mismatch. | Receipt only; request typing/auth metadata remain documented GAP/DEFERRED. |
| Localization | AST guard and 19 unit cases | Current guard passes; Vale is not a proven improvement. | REJECT Vale for this PR. |
| PostgreSQL/migrations | Exact-head CI `python-tests` and migrated PostgreSQL stack | Docker/PostgreSQL is not available locally; all required Python shards and migrated stack passed. | CI is authoritative; no local host proof claimed. |
| Allure SSH publication | Scheduled report workflow and Issue #821 | Separate private publication/SSH timeout boundary. | Deferred to #821; no Allure workflow change in #819. |
| #848 / #849 isolation | PR diff against current `origin/master` is limited to the seven existing #819 paths; the sync merge only brought current master into the branch. | No #848/#849 path is in the PR diff. | No changes to #848/#849. |

## 7. Delivery boundary

Full stateless deployment-scope result for `origin/master...HEAD` is:

```text
changed_paths: 8 (after the pending contract-proof test commit)
deploy_paths: []
deploy_required: false
reason: only documentation, governance, tests or developer tooling changed
```

The existing Draft PR #1119 and branch `codex/819-test-quality-coverage` are retained. The
technical verdict is **NEEDS_WORK** until the new test-bearing exact HEAD has green required CI.
The separate runtime-hardening branch is intentionally not part of this deployment-scope result.
Linux scheduled-only extended evidence,
physical iPhone/Safari, native Telegram, VoiceOver, production activation, owner merge approval
and Issue closure remain explicit owner decisions or `NOT_VERIFIED`; none is inferred from this
receipt. Merge, production deploy and Issue closure are not performed.

## 8. Finalization receipt for the current request

This table is the authoritative short receipt for the added work. `FIXED` means the scoped
change exists in the intended branch/PR boundary; `COVERED` means existing evidence is sufficient;
`JUSTIFIED_DEFERRED` means the item belongs to another Issue or requires unavailable evidence;
`NEEDS_WORK` means a concrete receipt or gate is still missing.

| Acceptance item | Status | Receipt / remaining gate |
|---|---|---|
| Nine-journey test-quality audit and regression classification | `COVERED` | Existing audit sections and the current source/fixture/workflow inventory remain in force. |
| WeekStrip geometry and real document-overflow oracle | `COVERED` | Focused selector correction, scroll-container assertion and temporary overflow negative probe are retained. |
| Cross-user export download-link privacy | `FIXED` | `backend/tests/test_account_lifecycle.py` protects the existing ownership filter with a `404` regression assertion. |
| Producer-to-generated-consumer API contract proof | `FIXED` | `apiContractNegativeProof.test.ts` uses the installed `openapi-typescript` and TypeScript compiler; five representative schema mutations must fail. Exact-head CI after the pending commit is `NEEDS_WORK`. |
| Raw/technical API error leakage at the frontend boundary | `FIXED` | Minimal runtime patch is isolated in branch `codex/819-safe-api-errors`; it preserves raw `body`/status for codes, localizes status fallbacks, and covers client plus Warmup UI behavior. Separate runtime exact-head CI and review are `NEEDS_WORK`. |
| #1119 deploy classification | `COVERED` | Final local helper run against `origin/master...HEAD`: `deploy_required=false`, `deploy_paths=[]`, `changed_paths=8`. |
| Weekly cross-browser/Allure lane (#821) | `JUSTIFIED_DEFERRED` | No timeout/retry/workflow policy change is included; cancellation is not a weekly PASS. |
| Physical iPhone/Safari, native Telegram, VoiceOver, production smoke | `JUSTIFIED_DEFERRED` | These require direct owner-controlled environments and are not inferred from browser mocks or CI. |
| Final PR/Issue gate | `NEEDS_WORK` | Push both scoped branches, obtain exact-head required CI, then owner separately decides merge, release/deploy and Issue closure. |

No deployment, merge or Issue closure is authorized or performed by this receipt.
