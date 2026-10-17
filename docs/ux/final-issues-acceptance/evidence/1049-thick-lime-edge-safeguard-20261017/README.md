# Issue #1049 — Progress lime-edge safeguard

Synthetic browser evidence for the Draft PR that fixes #1049. The fixture data is the existing
deterministic `mockProgress` data from `frontend/tests/e2e/progress-experience.spec.ts`; no
personal or production data is used.

## BEFORE / AFTER

The BEFORE captures reconstruct the exact decorative declaration present on `origin/master`:
`.app-section--progress .progress-insights__column--good { border-left: 3px solid var(--v2-lime); }`.
The declaration was injected only for the baseline screenshot, then removed. This is a
synthetic source-level baseline, not a physical-device or production capture.

- Light, 1440x900, Chromium: [BEFORE](before/progress-overview-1440-light-chromium.png) · [AFTER](after/progress-overview-1440-light-chromium.png)
- Dark, 1440x900, Chromium: [BEFORE](before/progress-overview-1440-dark-chromium.png) · [AFTER](after/progress-overview-1440-dark-chromium.png)

## Mobile BEFORE / AFTER (393px)

Two extra mobile close-ups were captured after rebasing the implementation onto the current
master. BEFORE deliberately injects only the original 3px lime decoration into the test
fixture; AFTER uses the corrected production CSS. These are **synthetic test captures**, not
production screenshots or personal user data.

- «Что идёт хорошо», Dark: [BEFORE](before/progress-good-card-mobile-393-dark.png) · [AFTER](after/progress-good-card-mobile-393-dark.png)
- «Что идёт хорошо», Light: [BEFORE](before/progress-good-card-mobile-393-light.png) · [AFTER](after/progress-good-card-mobile-393-light.png)
- «Данных достаточно для оценки» (`DataConfidence`), Dark: [BEFORE](before/progress-confidence-mobile-393-dark.png) · [AFTER](after/progress-confidence-mobile-393-dark.png)
- «Данных достаточно для оценки» (`DataConfidence`), Light: [BEFORE](before/progress-confidence-mobile-393-light.png) · [AFTER](after/progress-confidence-mobile-393-light.png)

## Audited and changed sources

- Removed the decorative 3px lime `border-left` from the Progress “Что идёт хорошо” column in `ux-ia-redesign.css`.
- Removed the decorative `inset 3px 0` lime rail from `.app-section--progress .program-history-workout`.
- Removed the decorative 3px lime left edge from the report confidence container while retaining its thin uniform frame.
- Preserved `DataConfidence` message, status icons and actions while replacing its 3px one-sided lime rail with the same neutral 1px border as the other sides (throughout YFC). Active/current/selected states, keyboard focus and CTA treatments remain.

## Permanent safeguard

`frontend/scripts/check_thick_lime_edges.mjs` is called by `npm run lint`, which is part of the
mandatory `frontend-checks` group. It checks changed CSS/CSS Modules, inline JSX/TSX styles and
CSS-in-JS-like template literals. It blocks a single physical/logical lime side, one-sided inset
shadow, edge-sized lime gradient or positioned pseudo-element at 3px or more, while retaining
explicit allowed state and semantic-status contexts.

The isolated negative fixtures intentionally fail with exit code 1; allowed thin-frame,
active-tab, focus and thin-framed semantic-warning fixtures pass with exit code 0.
Thick one-sided lime rails on semantic warnings are forbidden too. The computed-style E2E
also checks Progress at 320/360/393/430/1440 px in light and dark Chromium runs. Cross-browser
verification is reported separately; this evidence is not a claim of physical iPhone,
Telegram-native or production verification.
