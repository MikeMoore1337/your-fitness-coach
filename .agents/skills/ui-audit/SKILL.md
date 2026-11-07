---
name: ui-audit
description: >
  Audit an implemented UI in the real browser for usability, visual quality, memorability,
  responsive behavior, accessibility, interaction, motion and product consistency.
  Evaluate the intended design contract of the task rather than blindly enforcing historical Design V2.
---

# ui-audit

Act as Senior Product Designer and UI QA Engineer. Inspect the **actual rendered UI**.

## Design authority

Determine the task mode first.

### Ordinary implementation

The active design system is the consistency baseline.

### Explicit redesign or exploration

Historical Design V2/V2.1 is not a mandatory aesthetic. Judge against the current task, selected owner direction, YFC brand anchors, usability, accessibility, performance and product truth. Read `../../references/DESIGN_GUARDRAILS.md`.

## Quality dimensions

Assess clarity, hierarchy, composition, typography, spacing, interaction, responsive behavior, accessibility, perceived performance, product consistency, memorability, delight/"wow" and distinct YFC character.

An interface can be functional yet fail the quality bar if it feels anonymous and unappealing to use repeatedly.

## No automatic style policing

Glow, glass, gradients, 3D, cards, bento layouts, large typography, unusual compositions and expressive motion are not automatically defects. Report problems only when they obstruct understanding, look accidental, are poorly executed, conflict with YFC, break mobile, harm accessibility or create disproportionate performance cost.

## Browser states

When relevant check populated, empty, loading, error, long content, validation, disabled, modal/sheet/dropdown, hover/focus/active, mobile keyboard, narrow viewport, light/dark and reduced-motion states.

## Mobile

Review one-hand flow, content priority, primary action, bottom navigation/sticky layers, keyboard, safe areas, touch, 360/390 px, horizontal overflow and Mobile Web/TMA parity. Use `$mobile-engineer` for runtime-specific issues.

## Motion audit

When motion matters, load `$motion-design-engineer`. Check purpose, responsiveness, spatial continuity, interruption, enter/exit, hierarchy, data truth, repetition fatigue, reduced motion and jank/layout shifts. Expressiveness is not itself a defect; randomness, delays or distorted actions are.

## Automated detectors

Automated design lint/detectors provide review signals, not absolute aesthetic authority. Reject false positives when a deliberate choice is supported by product/design evidence.

## Finding format

Report severity, route/state, viewport, evidence, impact, probable root cause and recommended fix direction. Follow project lifecycle severity rules for backlog audits.

## Final verdict

Ask whether users understand what to do, UI feels coherent and uniquely YFC, delight works without harming usability, mobile is good, accessibility is adequate and production quality is sufficient.

## Evidence-based reference

For a narrow read-only audit of existing screens, optionally consult `../../references/external-quality/ui-skills/improve-ui.md`; it grants no UI/color/composition change permission. See `../../../docs/development/external-ui-quality-skills.md`.
