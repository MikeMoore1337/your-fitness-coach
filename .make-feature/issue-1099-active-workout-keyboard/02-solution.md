# Solution

## Requirements

- Keep one initial positioning correction when the keyboard/focus changes.
- Do not reposition the page on individual digits or server acknowledgements.
- Keep fields visible above the modeled keyboard, preserve manual scroll and existing completion,
  autosave and offline behavior.

## Evidence and choice

On baseline `afc9a3e9`, the second digit in the reps field changed the controlled row height by
removing `.active-workout-set__prefill-actions` (96 px). Browser scroll anchoring moved `scrollY`
by 105 px to keep the focused input in place; the existing `ResizeObserver` then issued a small
fractional correction. This reproduced the Issue #1099 symptom without attributing it to ACK.

Chosen D1: mark the previous-result helper dismissed only when both fields become non-empty or the
user explicitly reuses the previous result, while keeping an invisible layout reservation during
the current edit. Typing therefore does not trigger a later conditional removal. Keep the existing
viewport/observer path for genuine keyboard geometry changes and ignore only subpixel observer noise
(`<=1px`). No fixed iPhone offset, new dependency, queue, API contract or persistence state is added.

## Files and checks

- `frontend/src/features/workouts/TodayWorkout.tsx`: strength-row helper lifecycle and correction
  precision.
- `frontend/tests/e2e/active-workout-experience.spec.ts`: stable-scroll assertions and #1099 source
  instrumentation regression.
- `docs/ux/final-issues-acceptance/evidence/1099-active-workout-keyboard-20261018/`: synthetic
  BEFORE/AFTER recordings and manifest.
