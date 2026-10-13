# YFC final issues conveyor — current status snapshot

Date: 2026-10-13
Current base: `origin/master` = `11cff463834fd41c1392d646f6baaf361ac9bebc`
Scope: open `[Bug]` and `[UI Backlog]` tasks covered by the final-issues acceptance audit. Index issues #859 and #959, #960 and Product V11–V13 are not implementation scope.

This is a new current snapshot. Historical acceptance documents and their evidence are unchanged. `DONE_VERIFIED` below means that the current source and the applicable automated acceptance checks confirm the issue criteria; owner visual acceptance, release checks and physical-device verification remain separate gates where noted.

## Issue → current master / change → status → remaining action

| Issue | Current implementation / PR | Status | Evidence and next action |
| --- | --- | --- | --- |
| #860 | Current replacement flow; no new implementation | `DONE_VERIFIED` | 26 cross-browser replacement/completed-exercise checks passed. Release Check remains visible in Project for owner-controlled closure. |
| #861 | Existing search behavior; PR [#973](https://github.com/MikeMoore1337/your-fitness-coach/pull/973) | `IMPLEMENTED_NEEDS_VERIFICATION` | Search results are exposed before filters with unchanged DOM order and keyboard sequence. Cross-browser evidence: [861](https://github.com/MikeMoore1337/your-fitness-coach/blob/013810014ef5c00f40740131f88599e0569ca82b/docs/ux/final-issues-acceptance/evidence/861/README.md). Owner visual acceptance remains pending. |
| #862 | Current Programs editor; no new implementation | `DONE_VERIFIED` | Six Playwright checks for save/cancel/editor import-search passed in Chromium and WebKit. No remaining code defect reproduced. |
| #863 | Current Plan/Progress composition; no new redesign | `PARTIALLY_IMPLEMENTED` | Four relevant mobile navigation checks passed. Larger hierarchy/composition changes remain owner-gated and are excluded from this conveyor. |
| #864 | Current schedule card; no new implementation | `IMPLEMENTED_NEEDS_VERIFICATION` | Current browser checks show intact card/list geometry. Physical iPhone/Safari proof is `NOT_VERIFIED`; keep in Release Check. |
| #865 | Existing Progress header; no new implementation | `DONE_VERIFIED` | The reported header/help alignment was checked across 320–1440px and Dark/Light; two cross-browser checks passed. No formula or period data changed. |
| #866 | Current completed-exercise cards; no new implementation | `IMPLEMENTED_NEEDS_VERIFICATION` | 26 focused workout/replacement checks passed. Physical device and VoiceOver remain `NOT_VERIFIED`. |
| #867 | Dock clearance fix; PR [#976](https://github.com/MikeMoore1337/your-fitness-coach/pull/976) | `IMPLEMENTED_NEEDS_VERIFICATION` | Shared viewport-bottom clearance, DOM geometry and hit-testing regression are covered; CI [38351519972](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38351519972) is green. AFTER evidence: [867](https://github.com/MikeMoore1337/your-fitness-coach/blob/0593036ead817ed0af203236a13d340b02b1a506/docs/ux/final-issues-acceptance/evidence/867-tma-clearance-20261013/README.md). Owner visual acceptance and real iPhone/Safari/Telegram/VoiceOver remain pending. |
| #868 | Water deep-link; no new implementation | `IMPLEMENTED_NEEDS_VERIFICATION` | 28 Nutrition checks, including Web/TMA and Dark/Light water intent, passed. No draft reset reproduced; retain Release Check until owner closes the evidence gate. |
| #869 | Contrast fix; PR [#974](https://github.com/MikeMoore1337/your-fitness-coach/pull/974) | `IMPLEMENTED_NEEDS_VERIFICATION` | Actual-vs-expected CI diff is limited to hydration percentage text. AFTER evidence: [869](https://github.com/MikeMoore1337/your-fitness-coach/blob/e2b112841b4fe87e39213985525f25eb9e28e684/docs/ux/final-issues-acceptance/evidence/869-contrast-20261013/README.md). CI [38351293414](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38351293414) intentionally remains red until owner visual acceptance and golden update. |
| #870 | Current profile goal layout; no new implementation | `IMPLEMENTED_NEEDS_VERIFICATION` | 30 focused checks passed across 320–1280px and Dark/Light. No new geometry change; retain Release Check. |
| #871 | Current reminder and small-screen flows; no new implementation | `IMPLEMENTED_NEEDS_VERIFICATION` | Six focused Web/PWA/TMA checks passed; approved variant B semantics were not changed. Real Telegram and physical device remain `NOT_VERIFIED`. |
| #873 | Minimal arrow alignment; PR [#979](https://github.com/MikeMoore1337/your-fitness-coach/pull/979) | `PARTIALLY_IMPLEMENTED` | Only the confirmed left/right glyph mismatch was corrected; cross-browser DOM/glyph and keyboard checks passed, CI [38354284224](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38354284224) is green. Larger section composition stays owner-gated. AFTER evidence: [873](https://github.com/MikeMoore1337/your-fitness-coach/blob/7cb6e8fb7b3947927dbdfee4cca824d8e52dd2e2/docs/ux/final-issues-acceptance/evidence/873-progress-nav-20261013/README.md). |
| #914 | Released rest timer; no new implementation | `DONE_VERIFIED` | 68 checks passed across 320/360/393/430px, Web/TMA, Chromium/WebKit, Dark/Light, background/resume, click-through and rapid actions. No active-set mutation reproduced. |
| #946 | Released Food Picker behavior; no new implementation | `DONE_VERIFIED` | Food-picker keyboard/selection checks passed; no independent choice/favorite/edit regression reproduced. |
| #947 | Released Food Picker copy/values; no new implementation | `DONE_VERIFIED` | Full names and nutrition values covered by current Nutrition checks; no new defect reproduced. |
| #948 | Released Food Picker selection state; no new implementation | `DONE_VERIFIED` | Selection/favorite/edit independence covered by the focused picker checks; no new defect reproduced. |
| #967 | Active-program rollout; PR [#975](https://github.com/MikeMoore1337/your-fitness-coach/pull/975) | `IMPLEMENTED_NEEDS_VERIFICATION` | Owner-approved contract is implemented atomically for future planned, not-started workouts only; started/completed/missed history is preserved, revision conflicts return 409, and repeated requests are guarded. 41 backend tests and frontend/type checks pass; CI [38349400787](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38349400787) is green. No migration; API request/response metadata only. Draft PR and browser AFTER/integration evidence remain pending. |
| #968 | Quick Add geometry; PR [#972](https://github.com/MikeMoore1337/your-fitness-coach/pull/972) | `IMPLEMENTED_NEEDS_VERIFICATION` | Real time/calories input matrix covers 320/360/393/430px and Dark/Light. CI [38350439236](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38350439236) is green. AFTER evidence: [968](https://github.com/MikeMoore1337/your-fitness-coach/blob/5c036e8d8af5eab1f3b3643f010a74d898b131e9/docs/ux/final-issues-acceptance/evidence/968/README.md). Owner visual acceptance remains pending. |
| #969 | Explicit exit/unsaved-draft flow; PR [#978](https://github.com/MikeMoore1337/your-fitness-coach/pull/978) | `IMPLEMENTED_NEEDS_VERIFICATION` | Measurement and wellbeing flows now have explicit return/cancel behavior, discard confirmation, draft preservation and focus restoration without a second dock. CI [38353191373](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38353191373) is green. AFTER evidence: [969](https://github.com/MikeMoore1337/your-fitness-coach/blob/c460f0f16b389bcc881c3ed7b43bbbdc3a697c97/docs/ux/final-issues-acceptance/evidence/969-quick-form-exit-20261013/README.md). Owner visual acceptance remains pending. |
| #970 | Owner package only; no production code | `BLOCKED_OWNER_DECISION` | Proposal B (responsive goal record) preserves desktop/table/PDF contracts and is published with synthetic Dark/Light mockups: [970 owner package](https://github.com/MikeMoore1337/your-fitness-coach/blob/a6b0947e6a66d8a4ce8ba2e11a1735d252284bd7/docs/ux/final-issues-acceptance/evidence/970-owner-package-20261013/README.md). Owner must choose B or the existing table/min-width option A before implementation. |

## Release Check evidence

The following current-base checks were run without changing production or user data:

- #914: 68 checks, Chromium/WebKit, Web/TMA, mobile widths and lifecycle cases — passed.
- #860/#866: 26 focused checks — passed.
- #868/#946–#948: 28 Nutrition/Food Picker checks — passed.
- #870/#871: 30 profile/reminder checks — passed.
- #862: six Programs editor checks — passed.
- #863: four approved navigation checks — passed.
- #865: two cross-browser Progress header checks — passed.

These results are acceptance evidence, not permission to merge, close issues, or deploy. The Project `YFC Development` remains synchronized: completed code-level checks are in `Release Check`; open PRs and visual gates are in `Owner Approval`; #970 is `Blocked`.

## PR and delivery ledger

| PR | Scope | CI / state |
| --- | --- | --- |
| [#972](https://github.com/MikeMoore1337/your-fitness-coach/pull/972) | #968 Quick Add | Draft; [38350439236](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38350439236) green |
| [#973](https://github.com/MikeMoore1337/your-fitness-coach/pull/973) | #861 search | Draft; [38350696177](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38350696177) green |
| [#974](https://github.com/MikeMoore1337/your-fitness-coach/pull/974) | #869 hydration contrast | Draft; [38351293414](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38351293414) red only on unchanged visual snapshots pending owner approval |
| [#975](https://github.com/MikeMoore1337/your-fitness-coach/pull/975) | #967 active-program rollout | Draft; [38349400787](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38349400787) green |
| [#976](https://github.com/MikeMoore1337/your-fitness-coach/pull/976) | #867 dock clearance | Draft; [38351519972](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38351519972) green |
| [#978](https://github.com/MikeMoore1337/your-fitness-coach/pull/978) | #969 quick-form exit | Draft; [38353191373](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38353191373) green |
| [#979](https://github.com/MikeMoore1337/your-fitness-coach/pull/979) | #873 minimal Progress nav | Draft; [38354284224](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38354284224) green |

PR #971 is the audit branch containing this snapshot. No PR was opened for #970 because owner design selection is still required. No PR was merged and no production deployment was run.

## Shared constraints and remaining gates

- #967 has the final product decision and a separate Draft PR; remaining gates are technical/browser integration evidence, owner visual acceptance and release approval.
- #867, #968, #969 and #973 have real synthetic AFTER evidence; owner visual acceptance remains pending.
- #869 must not update visual goldens until the owner accepts the demonstrated text-color-only diff.
- #873 is intentionally limited to the minimal navigation correction; any larger Progress composition requires a new owner-approved design package.
- Physical iPhone/Safari, native Telegram and VoiceOver are `NOT_VERIFIED`.
- No application DB migration was added. #967 extends the existing save contract with revision/result metadata; other listed UI PRs do not change API or DB schema.
- Existing full-repository mypy debt is baseline and was not changed or masked.
