# Landing #895–#900 / PR #902 — owner-approved production delivery

## Owner decision

The owner explicitly approved the **last complete recovery WIP** for both audiences,
both themes, desktop/mobile, all six interactive Coach OS chapters, corrected FAQ,
mobile typography, stable progress loading, matte Glass header and CTA. This
supersedes earlier visual rejection and pending review **for this candidate**.

The owner accepts **documented historical archive pixel differences for this release**
and authorizes normal protected merge and production deployment **only after
functional, security/privacy and release checks pass**. Unknown technical defects
are not waived. No new design change is authorized.

OWNER_VISUAL_APPROVAL=APPROVED · VISUAL_BASELINE=FROZEN.
ARCHIVE_VISUAL_PARITY=FAIL · HISTORICAL_PIXEL_DIFFERENCES=OWNER_ACCEPTED_FOR_PR_902_ONLY.
REQUIRED_FUNCTIONAL_SECURITY_PRIVACY_RELEASE_CHECKS=MANDATORY.
CONTROLLER=ABSENT · CONTROLLER_V2=ABSENT. Environment change required: **no**.

## Provenance and unchanged evidence

The existing #895 worktree and PR branch were discovered from Git. All **52 WIP
files** matched the last owner-review report byte for byte before documentation
updates; all **176 candidate PNGs** matched that report's manifest. Six restored
chapters are in LandingV10CoachJourney.tsx; athlete FAQ says «Понятные границы.»,
coach FAQ «Понятные правила.». Runtime is unchanged after approval.

[Approved WIP hashes and historical result](design/references/product-v10-landing-release-895.json) ·
[176 explicitly approved state references](design/references/product-v10-landing-acceptance.json) ·
[Canonical original manifest](design/references/landing-archive-owner-canonical/MANIFEST.json).

Original ZIP SHA-256:
2be733d3539d98ecb575e9da0449978dfaf8ee993dda8bebbadb7d7e03d3acef.
All **28 canonical originals** retain their hashes; three are design gallery
images, never public product scenes. Archive, legacy and FINAL-895-FROZEN PNGs
and historical result files remain unchanged.

The previous dedicated visual run remains **7 PASS / 40 FAIL**, zero skips:
13 active archive scene pixel FAILs, ten lower-reference proof FAILs, sixteen
frozen mobile frame FAILs and the then-pending approval-completeness FAIL.
48 of 50 archive regions fail. Historical classification remains 2 confirmed
regions (one FAQ copy bug fixed), 46 unresolved whole-region pixel differences.
Sixteen mobile frozen differences lie below y729/741 after the existing 44px
link fix. Approval accepts differences; it never turns a comparison into PASS.

## Narrow release exception and future protection

Issue #900 explicitly allows **fail or a bounded, explicit owner-approved
exception**. This release uses that option. Master rules still require the exact
checks aggregate and current base. No rule, CI assertion, comparison threshold,
historical golden, testIgnore or security/privacy check is weakened for delivery.

playwright.landing-visual.config.ts still executes immutable archive and frozen
comparisons separately. Its nonzero result is FAIL even when this release is
eligible. The existing manual Windows workflow preserves failures. Ordinary
required CI is functional/security evidence, **not archive pixel-parity proof**.
The approval-completeness test is an approval inventory, never a pixel comparator.

Approval is recorded against 176 existing candidate hashes, without replacing
historical goldens. Later implementation changes are outside this exception and
need applicable tests and visual review. No general suppression, automatic golden
promotion or future waiver is introduced.

The 500KB large-file hook has a path-specific exception only for the four
immutable desktop first-screen PNGs in FINAL-895-FROZEN (728–920KB). Their SHA-256
checks remain mandatory in the dedicated suite. Other files retain the 500KB limit.

## Acceptance and mandatory delivery checks

| Issue | Implemented / approved                                                   | Required before closure                                                             |
| ----- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------- |
| #895  | Complete recovery, accepted visual differences, existing PR #902         | Exact-head CI, protected merge, master CI, production delivery/smoke/provenance     |
| #896  | Hero wrap/photos, hero-only switch, matte Glass header/CTA               | Route/theme/menu/keyboard/motion/width matrix, live hero/header                     |
| #897  | Athlete flow, compact Coach OS preview, typography, stable progress, FAQ | Synthetic no-write interactions, progress-ready, live athlete/CTA/Demo              |
| #898  | One Coach Today plus six separate interactive chapters                   | Initial/changed states, synthetic-only privacy, live coach/auth/Demo                |
| #899  | Themes, 320/360/390/430, menu/focus/safe-area                            | Required Chromium/WebKit mobile, Landing matrix, live responsive smoke              |
| #900  | Hashes, preserved diagnostics, release-scoped owner exception            | Security/privacy, release SHA/digests/health/readiness/provenance, live screenshots |

Prior unchanged-runtime checks: Chromium **66/66**, WebKit **66/66**, Vitest **88/88**,
auth/demo/privacy **9/9**, SEO **1/1**, TypeScript, changed ESLint/Prettier, Russian
UI guard and build PASS. New exact-head required CI and production checks remain
mandatory. GitHub PR Checks, Actions and Issue comments record final delivery state.

## Known separate limitations

- Historical demo nutrition quick-add failure did not reproduce in isolated
  current-runtime regression. No nutrition fix/skip or PASS for the old failure is
  claimed. Required CI must still pass.
- Windows sandbox EPERM is environmental; permitted fresh build/browser runs
  passed. No source workaround was added.
- Optional Firefox is **not run**, neither PASS nor FAIL. TMA evidence is mocked;
  native Telegram device testing is not claimed.
- Footer legal actions retain the explicit archive preview-document placeholder.
  This recovery does not claim completed legal-document publication or new data
  consent. Existing analytics consent and authentication remain mandatory.
- No exhaustive accessibility/security certification or real-user conversion
  success is asserted. Local synthetic scenes must never perform real writes.

## Historical records

[Reconciliation/region diagnosis](product-v10-landing-visual-acceptance.md),
[targeted polish](product-v10-landing-targeted-polish.md),
[region recovery](product-v10-landing-region-recovery.md) and
[pre-delivery history](product-v10-landing-pre-delivery-gate.md) preserve prior
REJECTED/WAITING/FAIL. Their old stop statuses are superseded only by the owner
decision above; they are not current delivery authority.

## Exact-head CI correction before merge

First full-recovery HEAD b94cfe84 failed required CI: the copy guard lacked the
approved official name Client 360, the full-page Coach Today unit lookup exceeded
5 seconds, and Docker's frontend-only build context could not resolve test-only
static JSON imports from docs. These are technical check defects, not accepted
visual exceptions. The fixes preserve runtime and appearance: exact phrase-only
allowlist with positive/negative regression, scoped Coach Today queries retaining
all assertions/timeouts, and typed runtime manifest reads following the existing
archive comparator pattern. No Docker/backend code or baseline is changed.

Fresh unchanged-runtime browser checks passed **132/132** (66 Chromium + 66 WebKit).
The post-approval dedicated historical suite is **8 PASS / 39 FAIL**, zero skips:
approval inventory now passes under the explicit owner decision; all 13 active
archive scene, ten lower-reference and sixteen mobile frozen failures remain FAIL.
The earlier 7/40 report is preserved as history. No pixel failure became PASS.
New exact-head required CI must replace the failed first attempt before merge.
