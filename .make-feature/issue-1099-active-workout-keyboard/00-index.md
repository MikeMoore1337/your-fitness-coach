# Make Feature: Issue #1099 keyboard-input scroll fix

- Stage: implementation complete; READY_FOR_VISUAL_ACCEPTANCE package in preparation.
- Depth: normal — the defect crosses React layout state, viewport positioning and E2E evidence,
  but stays inside the existing active-workout architecture; no new service or lifecycle state.
- Base: `origin/master` at `afc9a3e918f4085e506b711c5cacfe4b5c5a0f5c`.
- Branch: `codex/1099-active-workout-keyboard`.
- Scope: Issue #1099 only; PR #1098 and its branch are not modified.
- Decision D1: dismiss the previous-result helper only once both fields are meaningfully filled or
  explicitly reused, reserve its layout during the current edit, and ignore only subpixel
  positioning noise in the existing visibility correction.

## Acceptance gates

- C1: prove the jump source with the same fixture before changing code.
- C2: preserve autosave, ACK, offline queue, focus, values, manual scroll and completion flow.
- C3: assert stable `scrollY` after typing and ACK at 320/360/393/430 px in Dark/Light.
- C4: pass Chromium and WebKit targeted regression plus repository frontend checks.
- C5: publish real synthetic browser BEFORE/AFTER recordings; physical iPhone/TMA and owner
  visual/release approval remain separate gates.
