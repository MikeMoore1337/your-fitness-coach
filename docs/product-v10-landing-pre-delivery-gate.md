# Landing v10 — final pre-delivery gate (#895–#900 / PR #902)

Audit date: 2026-10-09. Runtime audited at `4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c`; base `origin/master` was
`64e90857157a013ce1f28c655eeefaf765cb779b`. PR #902 was OPEN, CLEAN and MERGEABLE;
the base is an ancestor of the head. The worktree was clean and no foreign changes
were found. Subsequent changes for this gate are documentation/traceability only.
The frozen frontend tree is `d9bcfd9eb12d13b1d6d434cadf7dce791b32375e`.
Required Checks for any documentation commit must finish on that new exact head;
the final head/check snapshot is recorded on PR #902 and in the local gate evidence.

```text
OWNER_VISUAL_APPROVAL=APPROVED
APPROVAL_SCOPE=FINAL_CORRECTION_VISUAL_DESIGN
VISUAL_BASELINE=FROZEN
ARCHIVE_ORIGINALS_HASHES=PASS (28/28)
ARCHIVE_VISUAL_PARITY=FAIL
ARCHIVE_PRODUCT_SCENES_ATTEMPTED=25
ARCHIVE_PRODUCT_SCENES_PIXEL_COMPARED=15
ARCHIVE_PRODUCT_SCENES_PASS=0
ARCHIVE_PRODUCT_SCENES_TIMEOUT=10
READY_FOR_MERGE_APPROVAL=NO
MERGE=FORBIDDEN
DEPLOY=FORBIDDEN
PRODUCTION_CUTOVER=FORBIDDEN
ISSUES_895_TO_900=OPEN
CONTROLLER=ABSENT
CONTROLLER_V2=ABSENT
env change required: no
```

The latest owner approval remains valid for the frozen design. Earlier REJECTED
and WAITING records describe earlier candidates. Approval does not turn failed
archive comparisons into PASS, authorize release, or close acceptance criteria.

## Checks and reproducibility

- [Required CI run 37922378285](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/37922378285): SUCCESS on `4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c`,
  aggregate `checks` green; frontend/unit/smoke, Python, security/CodeQL/audits,
  migrated stack, containers and workflow/deployment policy jobs succeeded.
- [Required mobile job](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/37922378285/job/113793200777):
  Chromium + WebKit, 10/10 PASS. The checked-in mobile config selects both projects;
  this is the shared application mobile regression group, not archive Landing
  pixel parity in WebKit.
- Firefox/extended scheduled cross-browser groups: **SKIPPED by scope**, neither
  PASS nor FAIL. No Firefox archive or Landing parity claim is made.
- Fresh local TypeScript and Vite production build passed (562 modules). Vite
  sandbox realpath EPERM is discussed below; the same build passed outside sandbox.
- Fresh `landing-production.spec.ts`: **50/50 PASS**. Matrix: athlete/coach ×
  light/dark × 320/360/390/430/768/1280/1366/1440/1498/1600/1920; labels, line
  wrapping, overflow, hero controls, routes, menu focus/theme/Escape/resize,
  hash/history, synthetic actions and mocked TMA safe-area.
- Fresh landing + analytics + navigation Vitest: **73/73 PASS** (10 files).
- Fresh auth/privacy/DemoCabinet selection: **8/8 applicable tests PASS**. A ninth
  SEO test expected hardcoded origin 4173 and failed on the audit server 4195;
  it passed **1/1 on its normal origin 4173**, without changing its assertion.
- Fresh nutrition/coach local-mutation regression: **1/1 PASS**, discussed below.

Evidence root (ignored local evidence, not a production service or lifecycle store):
`.artifacts/tasks/895/evidence/final-pre-delivery-gate/`. Raw logs, Playwright JSON,
traces, candidate PNGs, normalized source derivatives, heatmaps, per-file hashes,
diagnostic readiness captures and eight full-page captures are preserved there.
`final-correction/` is unchanged; its approved images and manifest have a separate
`frozen-visual-evidence-hashes.json` inventory in the gate evidence directory.

Run from the existing task worktree's `frontend/`, after its fresh build:

```powershell
npx vite preview --host 127.0.0.1 --port 4195 --strictPort
# In a second terminal:
$env:PW_BASE_URL='http://127.0.0.1:4195'
$env:LANDING_VISUAL_COMPARE='1'
$env:LANDING_VISUAL_EVIDENCE_DIR='D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/archive-suite'
npx playwright test --config=playwright.landing-visual.config.ts --reporter=list,json
```

The actual run returned exit 1: **1 hash test PASS, 25 scene tests FAIL**, no skips,
no retries. `playwright.config.ts` explicitly ignores this spec; dedicated config
has `updateSnapshots: 'none'`. The comparator always runs its comparison (setting
`LANDING_VISUAL_COMPARE=1` does not bypass or replace the pixel assertions).
No test, fixture, threshold, golden or runtime was changed during this gate.

## Archive hashes and scene results

[Canonical manifest](design/references/landing-archive-owner-canonical/MANIFEST.json):
all 28 PNGs matched their SHA-256 values. The actual local `Landing.zip` also matched
`2be733d3539d98ecb575e9da0449978dfaf8ee993dda8bebbadb7d7e03d3acef`.
The last three (`14-13`, `14-13_1`, `14-13_2`) are comparison-only gallery images;
they were hashed but are not product scenes or public sections.
The 35 older manifest files also matched their hashes, and all 10 supplemental
PNGs exist. Availability of these 45 references is not 45-scene visual acceptance.

Official threshold: changedPixelRatio ≤ **0.01**; RGB channel tolerance **16**;
candidate DPR **1**, fonts awaited, browser chrome excluded using the checked-in
source crops. The original browser viewport/DPR/zoom provenance is not independently
recorded in the PNGs, so the fixture's inferred dimensions cannot be certified as
fully calibrated merely because the crops have equal dimensions.

Candidate links below refer to local files on the review machine. Diagnostic links
for timeouts show current replacement content; they do **not** substitute a matching
scene or create a changedPixelRatio. `N/A` is not zero. All rows remain FAIL.

| Original                                                                                                                                                                                                              | Audience / state            | Result | changedPixelRatio | Threshold | Candidate                                                                                                                                            | Classification                                                                                                                                                                                                                                   |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------- | ------ | ----------------- | --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [2026-10-08_14-04.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-04.png)     | athlete / initial           | FAIL   | 0.459176          | 0.01      | [suite PNG](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/archive-suite/candidate/2026-10-08_14-04.png)   | Hero/photo crop and height differ materially; header/tertiary CTA also contain explicit later owner overrides. Original viewport provenance is not calibrated well enough to attribute the crop entirely to normalization.                       |
| [2026-10-08_14-05.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-05.png)     | athlete / effort            | FAIL   | 0.095206          | 0.01      | [suite PNG](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/archive-suite/candidate/2026-10-08_14-05.png)   | State normalization defect: phase=0 includes multiple lift poses; fixture progress=0.46 captures the raised pose while the original effort photo is lowered. Sticky header and residual alignment also differ.                                   |
| [2026-10-08_14-05_1.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-05_1.png) | athlete / record            | FAIL   | 0.079586          | 0.01      | [suite PNG](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/archive-suite/candidate/2026-10-08_14-05_1.png) | Sticky header absent in source scroll capture; small geometry/text/photo residuals remain. Cannot classify all residuals as antialiasing.                                                                                                        |
| [2026-10-08_14-05_2.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-05_2.png) | athlete / result            | FAIL   | 0.069269          | 0.01      | [suite PNG](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/archive-suite/candidate/2026-10-08_14-05_2.png) | Sticky header plus result-frame alignment/overlay residuals. No proven renderer-only explanation.                                                                                                                                                |
| [2026-10-08_14-05_3.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-05_3.png) | athlete / initial           | FAIL   | 0.051342          | 0.01      | [suite PNG](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/archive-suite/candidate/2026-10-08_14-05_3.png) | Sticky header plus residual text/panel alignment and Glass treatment differences; unchanged archive crop does not pass.                                                                                                                          |
| [2026-10-08_14-06.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-06.png)     | athlete / summary-purchases | FAIL   | 0.057196          | 0.01      | [suite PNG](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/archive-suite/candidate/2026-10-08_14-06.png)   | Summary/purchases state reached. Sticky header and panel/text residuals remain; not a timeout or real data write.                                                                                                                                |
| [2026-10-08_14-07.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-07.png)     | athlete / progress-diary    | FAIL   | 0.074357          | 0.01      | [suite PNG](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/archive-suite/candidate/2026-10-08_14-07.png)   | Progress/diary state reached. Sticky header, photo/section offset and text/panel residuals remain.                                                                                                                                               |
| [2026-10-08_14-07_1.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-07_1.png) | athlete / initial           | FAIL   | 0.250702          | 0.01      | [suite PNG](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/archive-suite/candidate/2026-10-08_14-07_1.png) | Capture readiness defect: loading fallback instead of chart. Loaded diagnostic shows nested progress frame, spacing/height differences and owner-approved compact teaser replacing photographic bridge. Waiting alone does not establish parity. |
| [2026-10-08_14-07_2.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-07_2.png) | athlete / weekly            | FAIL   | 0.240439          | 0.01      | [suite PNG](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/archive-suite/candidate/2026-10-08_14-07_2.png) | Weekly selection reached but chart still loading in official capture. Loaded diagnostic retains nested-frame/geometry differences and compact-teaser override.                                                                                   |
| [2026-10-08_14-08.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-08.png)     | athlete / initial           | FAIL   | N/A (timeout)     | 0.01      | [diagnostic only](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/diagnostic/2026-10-08_14-08.png)          | Owner-approved composition override; stale archive selector causes timeout. Current replacement capture is diagnostic only, not a matching candidate or a PASS.                                                                                  |
| [2026-10-08_14-08_1.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-08_1.png) | athlete / changes           | FAIL   | N/A (timeout)     | 0.01      | [diagnostic only](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/diagnostic/2026-10-08_14-08_1.png)        | Owner-approved composition override; stale archive selector causes timeout. Current replacement capture is diagnostic only, not a matching candidate or a PASS.                                                                                  |
| [2026-10-08_14-08_2.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-08_2.png) | athlete / message           | FAIL   | N/A (timeout)     | 0.01      | [diagnostic only](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/diagnostic/2026-10-08_14-08_2.png)        | Owner-approved composition override; stale archive selector causes timeout. Current replacement capture is diagnostic only, not a matching candidate or a PASS.                                                                                  |
| [2026-10-08_14-08_3.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-08_3.png) | athlete / initial           | FAIL   | 0.062159          | 0.01      | [suite PNG](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/archive-suite/candidate/2026-10-08_14-08_3.png) | Sticky header, small section/text offsets and public terminology changes. Some copy follows later owner screenshots; remaining exact geometry not accepted by archive test.                                                                      |
| [2026-10-08_14-08_4.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-08_4.png) | athlete / initial           | FAIL   | 0.055343          | 0.01      | [suite PNG](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/archive-suite/candidate/2026-10-08_14-08_4.png) | Sticky header and FAQ title/copy change (boundaries to rules) plus residual geometry. Later owner follow-up uses rules; strict archive comparison still fails.                                                                                   |
| [2026-10-08_14-09.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-09.png)     | athlete / initial           | FAIL   | 0.099265          | 0.01      | [suite PNG](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/archive-suite/candidate/2026-10-08_14-09.png)   | FAQ/footer alignment and title/CTA copy/style differences, plus sticky header. Final owner visual approval is not a measured archive-parity waiver.                                                                                              |
| [2026-10-08_14-10.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-10.png)     | coach / initial             | FAIL   | 0.508467          | 0.01      | [suite PNG](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/archive-suite/candidate/2026-10-08_14-10.png)   | Material hero/photo crop and height difference plus later owner-approved header/tertiary CTA. Original viewport/crop needs provenance reconciliation; not merely font rasterization.                                                             |
| [2026-10-08_14-10_1.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-10_1.png) | coach / initial             | FAIL   | 0.070315          | 0.01      | [suite PNG](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/archive-suite/candidate/2026-10-08_14-10_1.png) | Coach Today and repeatable-process chapters present. Sticky header plus text/panel alignment residuals remain.                                                                                                                                   |
| [2026-10-08_14-10_2.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-10_2.png) | coach / bridge-effort       | FAIL   | N/A (timeout)     | 0.01      | [diagnostic only](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/diagnostic/2026-10-08_14-10_2.png)        | Owner-approved composition override; stale archive selector causes timeout. Current replacement capture is diagnostic only, not a matching candidate or a PASS.                                                                                  |
| [2026-10-08_14-10_3.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-10_3.png) | coach / effort              | FAIL   | N/A (timeout)     | 0.01      | [diagnostic only](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/diagnostic/2026-10-08_14-10_3.png)        | Owner-approved composition override; stale archive selector causes timeout. Current replacement capture is diagnostic only, not a matching candidate or a PASS.                                                                                  |
| [2026-10-08_14-10_4.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-10_4.png) | coach / record              | FAIL   | N/A (timeout)     | 0.01      | [diagnostic only](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/diagnostic/2026-10-08_14-10_4.png)        | Owner-approved composition override; stale archive selector causes timeout. Current replacement capture is diagnostic only, not a matching candidate or a PASS.                                                                                  |
| [2026-10-08_14-11.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-11.png)     | coach / result              | FAIL   | N/A (timeout)     | 0.01      | [diagnostic only](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/diagnostic/2026-10-08_14-11.png)          | Owner-approved composition override; stale archive selector causes timeout. Current replacement capture is diagnostic only, not a matching candidate or a PASS.                                                                                  |
| [2026-10-08_14-11_1.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-11_1.png) | coach / initial             | FAIL   | N/A (timeout)     | 0.01      | [diagnostic only](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/diagnostic/2026-10-08_14-11_1.png)        | Owner-approved composition override; stale archive selector causes timeout. Current replacement capture is diagnostic only, not a matching candidate or a PASS.                                                                                  |
| [2026-10-08_14-11_2.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-11_2.png) | coach / initial             | FAIL   | N/A (timeout)     | 0.01      | [diagnostic only](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/diagnostic/2026-10-08_14-11_2.png)        | Owner-approved composition override; stale archive selector causes timeout. Current replacement capture is diagnostic only, not a matching candidate or a PASS.                                                                                  |
| [2026-10-08_14-12.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-12.png)     | coach / initial             | FAIL   | N/A (timeout)     | 0.01      | [diagnostic only](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/diagnostic/2026-10-08_14-12.png)          | Owner-approved composition override; stale archive selector causes timeout. Current replacement capture is diagnostic only, not a matching candidate or a PASS.                                                                                  |
| [2026-10-08_14-12_1.png](https://github.com/MikeMoore1337/your-fitness-coach/blob/4bfc6061a1d6c288c6e5fa86ff54f21cee3f5f5c/docs/design/references/landing-archive-owner-canonical/screenshots/2026-10-08_14-12_1.png) | coach / initial             | FAIL   | 0.092391          | 0.01      | [suite PNG](D:/Pet-projects/your-fitness-coach/.artifacts/tasks/895/evidence/final-pre-delivery-gate/archive-suite/candidate/2026-10-08_14-12_1.png) | FAQ/footer alignment/title and closing CTA/style differences, plus sticky header. Exact archive pixels not matched.                                                                                                                              |

## Failure classification and owner overrides

The official outcome is FAIL, not a new visual rejection by the agent. The owner
approved the current look; a failed test cannot silently revoke that approval or
silently waive archive acceptance either.

1. **Confirmed stale state/selector normalization:** 10 timeouts seek `.ref-bridge`
   on athlete, or `.ref-bridge`/StrengthScene/training/progress/difference on coach.
   The post-restoration owner directive explicitly replaced the athlete photographic
   bridge with a compact teaser + Coach Today preview and removed self-like trainer
   chapters. `LandingV10AthletePage.tsx` and `LandingV10CoachPage.tsx` implement that
   composition. These are bounded documented owner changes, not missing network data.
2. **Confirmed capture-readiness defect:** progress images `14-07_1/2` capture
   `Загружаем пример прогресса…`. The suite waits for fonts and visible images but
   not lazy `LandingProgressContent`. A separate diagnostic awaits the actual
   `Объём тренировок` heading and resamples geometry. It does not replace official
   screenshots or results. Even after readiness, nested panel borders/spacing and
   section height differ; diagnostic full-frame ratios are 0.272072 / 0.279744.
3. **Confirmed phase/pose under-specification:** strength effort progress 0.46 is
   still phase 0 but renders the lifted photograph; the archive effort pose is
   lowered. `data-phase=0` alone does not establish the same animation frame.
4. **Visible non-parity beyond rendering noise:** hero/photo crops and heights,
   progress nested frame/spacing, header presence after scrolling, FAQ wording and
   footer/CTA alignment differ. Some header/CTA/teaser/copy changes have explicit
   later owner approval; the full set of residuals has no bounded parity disposition.
   Sticky header removal or other appearance changes are not authorized by this audit.
5. **Rendering variability remains unquantified:** small text edges may contain
   antialiasing differences, but no evidence justifies labelling every residual as
   rendering-only. Original viewport/zoom and reference scroll alignment need careful
   calibration. Threshold stays 1%; no masking or golden recapture was performed.

`LandingProgress.tsx` now wraps shared lazy content in a `ref-product` panel while
the retained inner styles also draw a frame. The loaded diagnostic visibly contains
two borders. This is a concrete candidate/archive geometry difference; the audit
does not fix it while the visual baseline is frozen. At 1440 both themes have the
same current measured section heights: hero 860 px, athlete progress 1027.75 px,
athlete teaser 720.390625 px, coach work 728.390625 px and coach process 598.171875 px.
These candidate-only measures do not prove their equality with the archive.

Latest explicit approved overrides: audience switch only in hero; no switch/label
in desktop header or mobile menu; same translucent matte Glass in both themes;
full compact tertiary Glass CTAs; compact athlete Coach OS teaser with preview;
no self proof chapters on trainer. They are recorded in the owner follow-ups and
the latest approval, not inferred from CI. No new waiver of unrelated pixel or
six-interactive-chapter criteria is inferred.

## Acceptance reconciliation

Implementation, verification and issue closure are separate. Every issue below is
OPEN; no unchecked original acceptance item was changed to checked. Source/test
links are repository-relative; screenshots/logs are in the local gate directory.

| Issue / criterion                                                                                        | Implementation and concrete evidence                                                                                                                                                                       | Verification / remaining gap                                                                                                                                                                                                                                                                   |
| -------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| #896 A1: 1280/1440 hero, two audiences/themes, no lone В                                                 | [Hero](../frontend/src/pages/landing/LandingV10Hero.tsx); [matrix regression](../frontend/tests/e2e/landing-production.spec.ts), geometry test; final-correction desktop PNGs                              | Functional wrap/destinations PASS at all 11 widths; archive hero 14-04 / 14-10 FAIL. Exact four old-image equality not proven.                                                                                                                                                                 |
| #896 A2: normal/sticky/focus glass header vs old crops                                                   | [Shell](../frontend/src/pages/landing/LandingV10Shell.tsx), [CSS](../frontend/src/pages/landing/landing-v10.css); final-correction header crops; menu focus test                                           | Latest hero-only switch and transparent Glass approved. Original header-switch/СЦЕНАРИЙ requirement superseded by explicit owner directive. Old crop identity not PASS.                                                                                                                        |
| #896 A3: photo/brand/CTA/keyboard/reduced motion                                                         | Hero/Shell/StrengthScene; 50-test matrix/menu and required CI brand/soft-glass/strength tests                                                                                                              | Interaction checks PASS; photo-crop parity unresolved. This combined acceptance criterion is PARTIAL.                                                                                                                                                                                          |
| #896 A4: fresh diffs, typography/viewport measures, sign-off                                             | 25-case JSON + heatmaps; diagnostic/results.json (DPR/fonts/section boxes); frozen final-correction screenshots                                                                                            | Owner final-correction sign-off APPROVED. Measured archive parity FAIL; original viewport provenance incomplete.                                                                                                                                                                               |
| #897 A1: four full athlete pages, identical section order/height/density                                 | [Athlete page](../frontend/src/pages/landing/LandingV10AthletePage.tsx); fresh athlete light/dark 1440/390 full PNGs                                                                                       | Current composition implemented; exact old full-page identity superseded for explicit teaser/header changes, otherwise NOT PROVEN. 15 athlete archive cases FAIL.                                                                                                                              |
| #897 A2: no huge blanks/cutoffs/color transitions                                                        | StrengthScene retained; 50-test section overflow assertions; eight full-page captures; progress-ready diagnostics                                                                                          | No horizontal overflow verified. Blank/height fidelity cannot be PASS: suite captures a loading state and loaded progress geometry differs.                                                                                                                                                    |
| #897 A3: synthetic interactions/privacy, plan ≠ consumed, preview ≠ Demo                                 | [Scenes](../frontend/src/pages/landing/LandingV10Scenes.tsx), [shared sections](../frontend/src/pages/landing/LandingV10SharedSections.tsx); interactive no-API-writes test; DemoCabinet entry regressions | Local training, nutrition plan/purchases/diary, explicit confirmation and no writes PASS. Athlete has a compact shared Coach Today preview authorized by later owner follow-up; no full #coach-work/process mounted.                                                                           |
| #897 A4: before/after measures + owner reapproval                                                        | Archived original/candidate/heatmap links, full-page captures, final-correction approval                                                                                                                   | APPROVED frozen look; archive measurements FAIL. No issue-close or release sign-off.                                                                                                                                                                                                           |
| #898 A1: four coach full pages / exact geometry                                                          | [Coach page](../frontend/src/pages/landing/LandingV10CoachPage.tsx); fresh coach light/dark 1440/390 full PNGs                                                                                             | Own hero/cycle/Coach Today/process/demo/continuity/FAQ/closing implemented; self chapters removed by owner follow-up. 10 coach archive cases FAIL (7 timeouts). Old full-page identity not proven.                                                                                             |
| #898 A2: one Coach Today, six interactive synthetic proof chapters                                       | Shared ArchiveCoachWork facts/changes/draft; coach-process static four-row path; matrix checks #coach-work once; synthetic interaction test                                                                | One Coach Today verified. Six separate interactive invite/program/Client360/weekly/selected-client rollout/message chapters are NOT present in this page. Three interactive tabs + static path do not satisfy six chapters. Owner acceptance reconciliation remains unresolved; no UI changed. |
| #898 A3: desktop/mobile themes, privacy, real demo routes/auth                                           | Matrix 50/50, auth/Demo/public acquisition 8/8, analytics/navigation units, [auth spec](../frontend/tests/e2e/auth.spec.ts)                                                                                | Functional route/consent/TMA/synthetic boundary PASS. Pixel/theme parity beyond approved captures NOT PROVEN. Existing #875 flow preserved.                                                                                                                                                    |
| #898 A4: side-by-side + fresh owner approval before release                                              | Local gallery and final-correction matrix                                                                                                                                                                  | Latest design APPROVED; new gate shows residual archive gaps. Release NOT AUTHORIZED.                                                                                                                                                                                                          |
| #899 A1: 320/360/390/430 no overflow/wrap/clipped controls                                               | Matrix geometry tests (both themes/audiences); fresh 1440/390 full pages + frozen 320/390 hero/menu evidence                                                                                               | Functional assertions PASS, including one-line last hero span, active labels and all-section horizontal overflow. Not a screenshot parity PASS.                                                                                                                                                |
| #899 A2: glass/audience/menu focus/Escape/scroll/theme                                                   | Shell focus loop/outside pointer/Escape; hero audience links; mobile menu regression at 320, resize at 1440                                                                                                | Keyboard/focus/theme/navigation PASS. Latest owner explicitly removes audience from menu/header; it remains only in hero.                                                                                                                                                                      |
| #899 A3: no CTA overlap, 44px+, safe-area, final photo crop                                              | Matrix hero touch heights ≥44 and hero overlap/width assertions; mocked TMA safe-area 24/34; final-correction PNGs                                                                                         | Hero targets and mocked safe-area PASS. Native hardware safe-area and exact final photo-crop parity are not established by these tests; criterion PARTIAL.                                                                                                                                     |
| #899 A4: same light/dark geometry, contrast/tokens                                                       | Measured sections identical between themes at 1440; computed Glass assertions, visible-label tests, frozen owner-reviewed captures                                                                         | Geometry/token/label functional checks PASS. No blanket WCAG compliance or pixel equality claim; full contrast audit not repeated. СЦЕНАРИЙ is removed by later owner decision.                                                                                                                |
| #899 A5: open/closed menus, screenshot diffs, keyboard/reduced motion/TMA                                | Frozen 320/390 open/closed PNGs; menu/mocked-TMA matrix; 50/50 + CI strength motion tests                                                                                                                  | Behavior and available captures verified. Old mobile reference pixel diffs not reaccepted; native Telegram client not tested (mocked TMA only).                                                                                                                                                |
| #899 A6: owner mobile approval/evidence before delivery                                                  | Latest owner approved current baseline; frozen final-correction gallery includes both 320/390 audiences/themes/menus                                                                                       | Design APPROVED; release/production approval absent. Keep issue OPEN pending remaining evidence/release disposition.                                                                                                                                                                           |
| #900: originals pinned; full 45-photo availability/mapping                                               | 28 current hashes PASS, 35 legacy manifest hashes PASS, 10 supplemental PNGs present; canonical manifest + legacy-reference-availability.json                                                              | Availability verified. Full 45-photo comparison/disposition is NOT COMPLETE; 25 canonical product scenes attempted; 3 gallery-only excluded.                                                                                                                                                   |
| #900: fresh normalization/fonts/DPR/state, full matrix                                                   | Dedicated visual config/spec + normalization fixture; fresh build; 50 functional tests; scene JSON/diagnostics                                                                                             | DPR1/fonts awaited; inferred original crop/viewport and strength pose/lazy readiness are insufficient. Deterministic parity gate FAIL. Zoom/DPR variants not covered by current suite.                                                                                                         |
| #900: detect geometry/chapters; pinned references in required CI                                         | [Dedicated spec](../frontend/tests/e2e/landing-approved-visual.spec.ts); [ordinary config](../frontend/playwright.config.ts) testIgnore                                                                    | Comparator detects mismatch locally, but it is EXCLUDED from ordinary PR E2E. Required GREEN does not enforce archive parity. Incomplete six-chapter coverage is documented, not hidden.                                                                                                       |
| #900: a11y/focus/motion/routes/Demo/no real writes/SEO/UTM/hash/TMA                                      | 50/50 Landing, 73/73 unit, 8/8 auth/privacy/demo + SEO origin retry 1/1; original exact-head CI/security/mobile job                                                                                        | Scoped functional verification PASS. No exhaustive accessibility/security certification or native TMA/Firefox claim.                                                                                                                                                                           |
| #900 release 1–2: diagnosis + fresh visual approval                                                      | This report, immutable diffs, final-correction owner approval                                                                                                                                              | Diagnosis recorded and frozen look APPROVED; archive/acceptance gaps need disposition. No new appearance changes authorized.                                                                                                                                                                   |
| #900 release 3–4: protected merge, post-merge CI, digest deploy, smoke/readiness/provenance/live screens | No merge commit or deploy run for this candidate                                                                                                                                                           | NOT STARTED / FORBIDDEN. #900 and parent #895 cannot close. Historical #858 deploy evidence is not delivery of PR #902.                                                                                                                                                                        |

## Known problems, blockers and scope

**Blockers to merge readiness:** failed dedicated archive gate; incomplete provenance/
state normalization and unaccepted residual geometry; incomplete #898 six-interactive-
chapter criterion; archive comparator excluded from ordinary required E2E; incomplete
per-reference acceptance disposition. Current visual approval is preserved. Resolving
these requires a bounded owner disposition and/or authorized test calibration/visual
fix; this audit neither changes the design nor weakens the test.

**Known non-blockers for this frozen frontend gate:**

- Historical `demo-mode.spec.ts:1318` nutrition quick-add failure. Fresh exact-runtime
  regression now passes 1/1, including nutrition/coach local mutations. This test body
  and nutrition runtime were not changed by #895; the changed DemoCabinet file only
  moves TaskProgress's import, and the only demo spec diff scopes the public hero
  locator. A persistent independent product defect is **not reproduced**, and the
  historical root cause is not asserted as proven. Keep the prior failure record;
  no nutrition fix, skip or assertion change was made.
- Windows sandbox EPERM on Vite realpath for `src/main.tsx` was reproduced; the
  identical fresh build outside sandbox passed. Earlier setup.ts/unit EPERM is a
  historical environment symptom; current outside-sandbox 73/73 units pass. Required
  Linux CI is green. No source workaround or lowered quality gate was introduced.
- The SEO campaign test's fixed `127.0.0.1:4173` expectation fails against 4195;
  correct-origin 4173 retry passes. Both results remain in evidence.
- Firefox scheduled groups were scope-skipped. Mocked TMA does not prove native
  Telegram client behavior. Legal footer actions expose explicit preview-document
  placeholders; they are not evidence of completed production legal delivery.

No backend, auth, analytics, SEO runtime, dependencies, env keys, app layout, branch,
service, golden or threshold was changed by this gate. No merge/deploy/cutover or
issue closure was performed. Standard Git/GitHub remains the operational source of
truth; the artifact directory contains evidence only.
