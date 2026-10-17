# Computed-style summary

Evidence command:

```text
CAPTURE_1049_EVIDENCE=1 CAPTURE_1049_BEFORE_EVIDENCE=1
npx playwright test tests/e2e/progress-experience.spec.ts -g "Progress has no decorative" --project=chromium
```

Observed in the deterministic fixture:

- Progress “Что идёт хорошо”: `border-left-width` is 3px in the reconstructed BEFORE and is
  absent after the fix.
- `DataConfidence`: its status text, icons and actions remain, while the former 3px
  one-sided lime border becomes a uniform neutral 1px border, asserted by the contract test.
- Progress history workout: the decorative `inset 3px 0` lime shadow is removed; the ordinary
  1px contour remains.
- No unapproved one-sided computed lime border or inset rail was found at 320, 360, 393, 430 or
  1440 px in either color scheme in the Chromium run.
