# Landing #895 / PR #902 — regional recovery and owner review

Historical regional-recovery snapshot. Current results, the targeted mobile fixes,
stable progress captures and full A/B/C/D analysis are in
[final targeted polish](product-v10-landing-targeted-polish.md). That report corrects
two diagnostics below: the active Coach Today pair has no REVIEW WORKSPACE copy
difference, and both original/candidate progress overlines are uppercase.

Date: 2026-10-09. This report describes **uncommitted local WIP**, based on existing
branch `codex/landing-v10-p0-895-working` in the existing task worktree. It does not
describe a new PR head, a release or newly approved UI.

```text
PR_902_HEAD=a4df49e80e1e15f1ab125ff7047d75f03f3890f2
ORIGIN_MASTER=64e90857157a013ce1f28c655eeefaf765cb779b
PR_902=OPEN_MERGEABLE_CLEAN
PR_HEAD_REQUIRED_CI=GREEN (37941546491; not this local WIP)
OWNER_APPROVED_FINAL_CORRECTION=APPROVED
VISUAL_BASELINE=FROZEN
LOCAL_RECOVERY_OWNER_VISUAL_APPROVAL=PENDING
ARCHIVE_ORIGINALS_HASHES=PASS (28/28)
ARCHIVE_VISUAL_PARITY=FAIL
ACTIVE_ARCHIVE_SCENES=13
ACTIVE_ARCHIVE_SCENE_PASS=0
ARCHIVE_REGIONS=50 (2 PASS / 48 FAIL)
OWNER_SUPERSEDED_ARCHIVE_SCENES=12
LOWER_SUPERSEDED_VISUAL_NOT_PROVEN=10
FROZEN_FIRST_SCREEN_MENU=4 PASS / 16 FAIL
TRAINER_SIX_CHAPTERS=LOCAL_WIP_IMPLEMENTED_REVIEW_REQUIRED
READY_FOR_MERGE_APPROVAL=NO
COMMIT_PUSH_MERGE_DEPLOY_PRODUCTION_CUTOVER=NOT_PERFORMED
ISSUES_895_TO_900=OPEN
CONTROLLER=ABSENT
CONTROLLER_V2=ABSENT
env change required: no
```

## Review materials

- [Unified HTML gallery](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/region-recovery/index.html): unchanged archive → relevant approved source → candidate → regional heatmap, plus all six trainer chapters and their action states.
- [Complete numerical results and hashes](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/region-recovery/recovery-summary.json): every region's result, ratio, threshold, source/candidate/diff links, exclusions and capture geometry.
- [Capture manifest](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/region-recovery/candidate-captures.json): four trainer initial full pages, four interacted full pages, individual states, four athlete full pages, no overflow/API writes/page errors in this synthetic capture matrix.
- [Dedicated suite JSON](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/region-recovery/visual-results.json): **7 tests PASS / 39 FAIL**, exit 1. Two structural first-screen checks are not additional pixel acceptance; four independent frozen desktop pixel comparisons pass.

| Trainer candidate       | Light                                                                                                                                     | Dark                                                                                                                                     |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Desktop 1440 initial    | [Full page](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/region-recovery/review/coach-light-1440-full-initial.png)    | [Full page](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/region-recovery/review/coach-dark-1440-full-initial.png)    |
| Mobile 390 initial      | [Full page](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/region-recovery/review/coach-light-390-full-initial.png)     | [Full page](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/region-recovery/review/coach-dark-390-full-initial.png)     |
| Desktop 1440 interacted | [Full page](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/region-recovery/review/coach-light-1440-full-interacted.png) | [Full page](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/region-recovery/review/coach-dark-1440-full-interacted.png) |
| Mobile 390 interacted   | [Full page](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/region-recovery/review/coach-light-390-full-interacted.png)  | [Full page](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/region-recovery/review/coach-dark-390-full-interacted.png)  |

## Evidence authority and provenance

All 28 originals match the canonical manifest and remain unchanged. The source ZIP
hash is `2be733d3539d98ecb575e9da0449978dfaf8ee993dda8bebbadb7d7e03d3acef`.
The final three `14-13*` PNGs are comparison galleries only, not product scenes.
The previous evidence ZIP `archive-suite-final-head.zip` was inspected, including
its report/summary, four active contact sheets, normalized originals and candidate
diffs. That evidence ZIP has SHA-256
`7c6f63533b9f8086e551df9c44dc6287625bf97489a682d5b910f13e2e53c094`;
it is not the canonical Landing ZIP.

Twenty existing final-correction PNGs were copied without modification into
[`final-895`](design/references/product-v10-landing-approved/final-895/README.md)
and pinned by SHA-256. No renderer-generated image became a golden. These images
cover the first screen/menu only. Four desktop comparisons pass; sixteen mobile
comparisons fail because the captures at 09:24 UTC predate existing commit
`05277f8f` (10:10 UTC), which adds a 44px target to the hero-footer link and moves
the bottom strip. The exact screenshot capture commit was not recorded. The later
delivery head must not be represented as its runtime SHA. This discrepancy is
retained for owner review, not labelled antialiasing or automatically rebaselined.

The 12 superseded archive scenes are no longer accepted through DOM alone:
`14-04`/`14-10` have relevant frozen first-screen pixel checks; `14-08`,
`14-08_1`, `14-08_2`, `14-10_2`, `14-10_3`, `14-10_4`, `14-11`, `14-11_1`,
`14-11_2`, `14-12` are **VISUAL_NOT_PROVEN** for their lower content. The suite
fails explicitly for that missing proof instead of returning SKIP or visual PASS.

## Regional comparisons and remaining differences

[`landing-archive-regions.json`](../frontend/tests/fixtures/landing-archive-regions.json)
partitions 13 active captures into 50 copy/product/adjacent-section regions. The
RGB channel tolerance remains 16 and the acceptance threshold remains **0.01**.
No scaling, image registration, threshold increase or source-image editing is used
to obtain acceptance. Full-screen ratios remain diagnostic only.

The top 72px are excluded only for the later approved sticky matte Glass header:
owner directive `88e2a024-1c27-494d-982f-0a516ebd186e`, FINAL VISUAL FIX P0-2,
including sticky/scroll states, followed by FINAL_CORRECTION_VISUAL_DESIGN approval.
The bottom of the two progress captures is separately excluded for the later compact
athlete Coach OS teaser directive `6aa84c98-df4b-4cf1-bdcb-a2ac545bfd6d`, section 2,
screenshot 3. Exact rectangles and source paths are in the fixture/results. Content
occluded by the later header is not thereby proven. No other region is waived.

All 13 active scenes remain FAIL. The two regional PASS results are small partial
closing areas; they do not establish complete scene or page acceptance. The gallery
and summary list each region's original/candidate/heatmap and numerical ratio.

| Archive scene | State and diagnosis                                                                                                            |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `14-05`       | Lowered effort pose, opacity and rep count verified; residual photo/text edges remain. Capture/rendering cause unresolved.     |
| `14-05_1`     | Record phase, 3 reps and 18kg × 3 verified; residual geometry/rasterization remains.                                           |
| `14-05_2`     | Result state verified. Near-threshold copy still fails; no tolerance waiver.                                                   |
| `14-05_3`     | Initial training and planned-food state verified; training/nutrition regions differ in text/edge positions.                    |
| `14-06`       | Completed training summary and purchases state verified; residual geometry/rendering remains.                                  |
| `14-07`       | Progress summary and explicitly consumed diary state verified; adjacent sections compared separately.                          |
| `14-07_1`     | Real nested progress frame removed locally; card is now comparable. Overline casing and small text/edge offsets remain FAIL.   |
| `14-07_2`     | Loaded progress and selected weekly answer verified; residual typography/geometry remains FAIL.                                |
| `14-08_3`     | Why/demo/continuity split; residual positions/rendering unresolved.                                                            |
| `14-08_4`     | Archive FAQ says «Понятные границы», current says «Понятные правила». No silent reversal of approved copy.                     |
| `14-09`       | FAQ wording plus page-end scroll clamp/footer geometry differences; not all changed pixels represent a content defect.         |
| `14-10_1`     | Archive includes REVIEW WORKSPACE; current Russian overline omits it. Other Coach Today/process edges differ; logic unchanged. |
| `14-12_1`     | Later trainer FAQ copy directive exists; unchanged footer/product regions still fail. No whole-scene waiver.                   |

Fonts are awaited; candidate DPR is 1 and viewport/crop/state/scroll geometry is
recorded. Original PNGs contain browser chrome and do not record original DPR,
browser zoom, font binaries or rasterizer. Minor rasterization is plausible for
some edges but has **not** been proved as the complete cause. Remaining differences
are not asserted to be harmless, nor is each whole ratio asserted to be a UI defect.

## Restored #898 journey — exact plan and local WIP

Placement: current hero → cycle → one existing Coach Today → approved process
summary → the six chapters below → demos → continuity → FAQ → closing/footer.
No athlete StrengthScene/training/nutrition/progress section is added to trainer.
The process summary is preserved because it is visible in canonical `14-10_1`.
The six independent chapters are absent from the canonical archive; use the approved
#852 full-page trainer references as the explicit fallback authorized by the owner.
They cannot be cancelled by a directive to remove athlete duplicates.

| Order / anchor     | Original source and component                                 | Interactive states                                                                                                   |
| ------------------ | ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| 1 `coach-connect`  | #852 «Знакомство. С продолжением.» / `LandingV10CoachJourney` | Waiting → accepted invitation; no automatic program assignment.                                                      |
| 2 `coach-program`  | #852 «Ваш план. Для конкретного человека.» / same component   | Choose version 1/2 with existing tab material → explicit assignment → frozen version.                                |
| 3 `coach-facts`    | #852 «За цифрами — ваш клиент.» / same component              | Inbox → Client 360 facts → return. No private notes.                                                                 |
| 4 `coach-review`   | #852 «Сначала факты. Потом вывод.» / same component           | Facts/changes → checked; no automatic program mutation.                                                              |
| 5 `coach-decision` | #852 «Общая версия. Личное применение.» / same component      | Select clients → preview selected only → separate confirm. Selection change invalidates preview; empty set disabled. |
| 6 `coach-followup` | #852 «Внимание продолжается.» / same component                | Create editable draft → edit → separate confirm. No notification or real message is sent.                            |

Source markup/CSS: original ignored prototype
`.artifacts/tasks/landing-v10-refinement/design.tsx` (`CoachNarrative`) and
`refinement.css`; relevant approved images are
`full-page-852/coach-{light,dark}-{1440,390}-full.png`.
The gallery shows the actual full source and labelled display crops of its desktop
chapters, not an unrelated first-screen image. Display crops are not test goldens.
Candidate chapter images are also labelled display crops, cut from complete
screenshots taken at scrollY=0. Their raw full-page sources and crop coordinates
are retained in the capture manifest. This avoids placing a sticky header across
a clipped chapter heading without altering the header, DOM or styles. The capture
uses neutral focus; keyboard/focus behavior is verified separately by E2E.

Minimal implementation: one journey component, shared exported `SectionTitle`,
original scoped chapter styles and existing icons/Glass tab buttons. The existing
Coach Today is reused once. Version selection, explicit confirmation safeguards and
44px touch targets complete #898's interactive contract. Each scene is synthetic and
local; no API/business capability is reimplemented. Independent examples may show
different plan versions and are labelled as actions affecting only that scene.

## Proven defects fixed and harness corrections

1. **Missing six chapters:** now local interactive WIP from #852, not silently
   declared approved. Four initial and four interacted full-page trainer captures
   plus every chapter's intermediate states are supplied for new owner review.
2. **Nested progress frame:** the V10 caller previously wrapped `LandingProgress`
   in another `ref-product`, retaining the component's old inner frame. Its existing
   `className` API now styles the single actual frame. Lazy readiness and all other
   callers are preserved. This lower-section restoration also awaits owner review.
3. **WebKit focus return:** native dialog did not return focus after a mouse click
   that does not focus buttons. The actual legal trigger is now remembered and
   focused on close. Both triggers have a unit regression; browser Escape check
   passes. No visual composition, legal text or route changed.
4. **Harness:** recompute scene scroll after lazy progress loads; wait for the
   actual StrengthScene phase/pose/reps; separate header and teaser overrides;
   wait for navigation/network and progress readiness before geometry/interactions.
   First WebKit run's eight failures and bounded triage results are retained.
   Final WebKit 56/56 passes without force clicks or weakened assertions.

## Regression evidence and reproducibility

Current WIP: Chromium Landing **56/56 PASS**; WebKit Landing **56/56 PASS**;
targeted Vitest **88/88 PASS**; auth/privacy/DemoCabinet **9/9 PASS** including
the nutrition local-mutation check; correct-origin SEO **1/1 PASS**. TypeScript
project build, scoped ESLint, Russian UI guard, changed-file Prettier and Vite
production build pass. Raw logs are in the gallery evidence directory.

Matrix: athlete/coach × light/dark × 320/360/390/430/768/1280/1366/1440/1498/1600/1920,
plus six-chapter actions at 320/390/1440, keyboard/menu/theme/hash/history, full
tertiary Glass CTA and real DemoCabinet destinations, no horizontal overflow,
reduced motion and mocked Telegram safe-area/resizing. Native Telegram was not run.
Firefox was not executed; it is neither PASS nor FAIL. No production/API smoke or
real-user data write is claimed.

The dedicated suite is independent of ordinary Playwright. Run after a fresh build:

```powershell
cd frontend
npm run build
npm run e2e:landing-visual
```

It starts a strict-port local preview on 4176. An explicit external preview can be
selected with `PW_EXTERNAL_SERVER=1` and `PW_BASE_URL`.
The prepared `landing-visual.yml` workflow runs the same configuration on Windows
with the locked Playwright dependency and preserves failing artifacts. It is manual,
not added to required jobs while references/proof remain unresolved. It has not been
pushed or run in GitHub. It does not convert failures to SKIP or continue-on-error.
Existing required CI at `a4df49e8` remains historical proof for that exact PR head
only; the local recovery code has no remote exact-head CI yet.

The complete dedicated suite was repeated on the final build with its own managed
preview and `PW_PREVIEW_PORT=4201`: **7 PASS / 39 FAIL**, exit 1. An earlier isolated
immutable-originals smoke also passed. Port 4176 was already occupied by an unrelated
preview and was not reused or stopped. The 28 canonical,
35 legacy approved and 20 copied final-correction PNG hashes were independently
rechecked; this integrity check is not additional visual acceptance.

Known independent issues: historical demo-mode nutrition quick-add failure was
not reproduced in the current targeted test (1/1 PASS within the 9-test run); no
nutrition implementation was changed and this is not a claim that all environments
are fixed. Windows sandbox EPERM occurred before Vitest could start and previously
during Vite realpath; identical permitted outside-sandbox runs passed. Neither is
hidden or used to excuse archive FAIL. Global formatting was not run.

## Acceptance reconciliation and remaining gates

| Issue | Implemented locally                                                                                | Verified / incomplete                                                                                                                                | GitHub state                      |
| ----- | -------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| #895  | Existing approved header/hero/CTA retained; recovery WIP and evidence prepared                     | Final-correction approval retained; this recovery and archive FAIL not approved                                                                      | OPEN; no commit/push/merge/deploy |
| #896  | Shared matte header, hero-only audience switch, tertiary Glass CTA                                 | Four frozen desktop PASS; responsive routes/material/keyboard verified. No new composition. Archive hero overridden only within owner scope          | OPEN / PARTIAL                    |
| #897  | Athlete scenes retained; nested progress frame restored                                            | Synthetic interactions verified; 13 active archive scenes still FAIL; lower teaser has no relevant latest approved screenshot                        | OPEN / PARTIAL                    |
| #898  | Six independent interactive chapters, one existing Coach Today, no athlete duplicates              | Action/confirmation/no-write tests pass in Chromium/WebKit; four initial/interacted page pairs supplied; fresh owner visual approval missing         | OPEN / LOCAL_WIP_REVIEW_REQUIRED  |
| #899  | Existing approved mobile header/menu/theme/audience behavior retained                              | Functional 320–1920 matrix passes in both engines; sixteen frozen mobile pixel mismatches retained; native TMA not proved                            | OPEN / PARTIAL                    |
| #900  | Immutable references, regional metrics/heatmaps, failing proof checks and manual CI entry prepared | Canonical 28 hashes pass; 25 scenes dispositioned. Full legacy 45-image pixel acceptance, new owner approval and production/release gates incomplete | OPEN / BLOCKED                    |

Blockers: residual archive-region FAIL; mobile approved-capture/44px-target delta;
ten lower scenes without current visual proof; new #898/progress owner review;
unresolved FAQ/overline and process-summary/source requirements; #900 CI/release
acceptance not complete. Original archive and old #852 cannot be made simultaneously
identical where later approved decisions conflict. Those differences are explicit,
not reasons to change the frozen hero/header/CTA or invent new styling.

Non-blocking evidence limits are labelled separately: historical quick-add and
sandbox EPERM, unexecuted Firefox/native TMA, and remote CI applying only to the
unchanged PR head. No Issues were closed. The next action is owner review of the
linked gallery and lower-scene WIP; **READY_FOR_MERGE_APPROVAL=NO**.
