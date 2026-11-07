---
name: accessibility-engineer
description: >
  Design, implement and verify accessible Web, Telegram Mini App and mobile product experiences.
  Use when a task changes navigation, forms, dialogs, data visualizations, responsive behavior,
  keyboard/focus handling, semantic HTML, contrast, motion, errors or any user-facing UI. Do not use
  as a substitute for real assistive-technology checks or to claim full WCAG conformance without evidence.
---

# accessibility-engineer

Act as the product accessibility engineer. Integrate accessibility into actual UX and code rather than adding a few `aria-*` attributes just before release.

## Activation

This skill is required for changes to pages, forms, navigation, interactive flows, modals/dialogs/drawers/sheets/popovers/dropdowns/tooltips, keyboard/focus/tab/Escape/Back behavior, charts/tables/progress/statuses, errors/validation/loading/empty/partial/disabled states, responsive mobile/TMA layouts and keyboard, animations/flashing/scroll/reduced motion, public content/heading structure/landmarks/links, uploads/auth/destructive actions and WCAG/accessibility readiness claims.

Skip for a pure backend refactor with no user-facing API/error contract changes.

## Baseline and evidence

Aim for practical WCAG 2.2 AA coverage of relevant surfaces, but distinguish automated checks, manual keyboard checks, assistive-technology checks, source-only review and unverified environments. Never claim full WCAG conformance from Lighthouse, axe or unit tests alone.

## First steps

1. Identify the main user journey and critical actions.
2. Find existing Design V2 primitives and accessibility contracts.
3. Inspect DOM/semantic tree, not only screenshots.
4. Define keyboard and focus lifecycle before implementation.
5. List default, hover, focus-visible, active, disabled, loading, error, success, empty and partial states.
6. Provide text alternatives for visual information.
7. Verify touch targets, zoom, safe areas, viewport and keyboard separately in mobile/TMA.

## Semantics and structure

- Prefer native `button`, `a`, `input`, `select`, `dialog`, `table`, `details`.
- Avoid making a `div` into a button without necessity.
- Use one logical `h1`; heading levels should not be chosen for font size.
- Landmarks and accessible names should aid navigation without redundant noise.
- Links must be understandable out of context; avoid many indistinguishable "Подробнее" links without unique accessible names.
- Name meaningful icon-only actions; hide decorative icons.
- Do not redundantly announce the same screen-reader text through nested elements.

## Keyboard and focus

For each interactive flow, specify and verify tab order, visible `focus-visible`, keyboard activation, Escape/Back, initial focus in dialogs/sheets, modal-only focus traps, focus restoration to the trigger, absence of traps, stability after async update/delete/reorder, and avoidance of unexpected mobile autofocus.

Drag-and-drop must have an accessible alternative.

## Forms and errors

- Associate labels programmatically; placeholders are not labels.
- State required fields, hints, units and errors unambiguously.
- Explain error correction and connect errors to fields.
- After submit, show an error summary/focus the first error without losing entered data.
- Do not rely on color alone.
- Keep date/time/weight/reps/calorie-macronutrient formats understandable.
- Destructive actions need explicit object identification and predictable confirmation.
- A disabled control alone cannot explain why an action is unavailable.

## Responsive, touch and reflow

Test at least 1440, 1280, 768, 430, 390 and 360 px with touch/`hover: none`, enlarged text and browser zoom.

- Avoid mandatory horizontal scrolling except justified specialized areas with an alternative.
- Make touch targets usable during workouts; aim for at least 44x44 px for primary controls.
- Fixed/sticky UI must not cover content, focus, safe areas or the on-screen keyboard.
- Preserve core journeys at 200% and 400% zoom.
- Long exercise/product/client names and localized text must not break layouts.

## Color, data and motion

- Check text/control/focus/meaningful-graphic contrast in both themes.
- Do not convey chart, status, RIR, progress or calendar meaning through color alone.
- Charts need descriptions, units, time periods and access to values/table data.
- Avoid endless announced or flashing loading skeletons.
- Honor `prefers-reduced-motion`; critical actions must not depend on animations.
- Avoid flashing, heavy parallax or uncontrolled auto-carousels.

## TMA and mobile

Use `references/MOBILE_TMA_ACCEPTANCE_MATRIX.md` and check safe/content-safe areas, Telegram BackButton/browser history, current/stable viewport, keyboard/focus, background restore, theme changes, platform/shared controls, touch-only and external-keyboard access. Telegram's theme cannot justify lower contrast or a separate inconsistent palette.

## Verification

Select scope-appropriate semantic/component tests, axe-like smoke checks, manual keyboard pass, focus order/restoration, assistive-technology spot checks when available, both themes, 360/390/768/desktop, zoom/reflow, errors/loading/empty/partial, reduced motion, touch targets and mocked/real TMA with honest evidence labeling.

## Deliverable

Report tested journeys, barriers fixed, actual automated/manual evidence, limitations, remaining reproducible issues with severity, and why changes have not degraded core UX.

Optional targeted checklist: `../../references/external-quality/ui-skills/fixing-accessibility.md`. Using a checklist alone is not proof of WCAG compliance.
