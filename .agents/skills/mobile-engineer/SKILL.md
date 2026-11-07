---
name: mobile-engineer
description: >
  Engineer smartphone runtime behavior: mobile keyboard, safe areas, dynamic viewport, lifecycle,
  touch/device-specific behavior, offline/resume and Mobile Web/TMA runtime parity.
  Do not load solely because a responsive UI is visible on a phone.
---

# mobile-engineer

This v6 skill intentionally has a narrow scope.

## Outside this skill

- General visual composition: `$product-designer`.
- Ordinary responsive CSS: `$frontend-engineer`.
- Telegram Bot/Mini App APIs: `$telegram-engineer`.
- General UI audits: `$ui-audit`.

## Triggers

Use for changes/risks involving mobile keyboards, input mode/focus recovery, safe areas, `visualViewport`, dynamic/stable heights, foreground/background, reload/resume, minimize/restore, offline/reconnect, touch-only behavior, stuck hover, gestures/pointers, device memory/main-thread performance or Mobile Web/TMA runtime differences.

## YFC context

Account for phone use during workouts: one-handed interaction, short pauses, repeated taps, sweat/movement, interruptions, unreliable connections, keyboard, orientation/viewport changes and return to foreground.

## Forms

Verify `type`, `inputMode`, `enterKeyHint`, autocomplete, numeric keyboards, focus, visible errors, CTA while keyboard is open, recoverable drafts and avoidance of layout jumps.

## Safe areas and viewport

Fixed/sticky UI must not cover content or focused fields, conflict with bottom navigation or hide under system/Telegram chrome. Changing viewport, theme or background must not unnecessarily reset route/dialog/form state.

## Lifecycle and network

For critical flows, test relevant reload, resume, background/foreground, offline/reconnect, stale server state, repeated submit and local draft recovery.

## TMA

Use `$telegram-engineer` for Telegram APIs, initData, BackButton and deep links. This skill covers smartphone runtime parity and physical interaction only.

## Performance

Desktop localhost cannot prove mobile quality. Measure main-thread blocking, memory, animation/keyboard/sheet stutter, resume cost, media loading and duplicate bundles when relevant.

## Verification

Choose representative task-specific viewports, usually widths 360, 390 and 430, plus applicable keyboard/touch/lifecycle states.
