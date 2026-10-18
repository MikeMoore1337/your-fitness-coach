# Issue #873 focused BEFORE/AFTER comparisons

- Fixture: `frontend/tests/e2e/progress-experience.spec.ts::mockProgress`.
- Browser: Playwright Chromium with reduced motion.
- BEFORE source: preserved `paired-20261018/after` captures at
  `2f1cb8930e07a41a8b7303cb4c8b63ad45f65b82`, before the final visual refinement.
- AFTER source: new captures at
  `00e2701adcb5ae889f27aa72555265628c19df25`.
- The four pairs keep the same fixture, theme, viewport and UI state on both sides. The old
  files are linked in place and were not renamed or overwritten.

## Included pairs

1. Weekly Review / Wellbeing, dark, 393×844, expanded: the forbidden one-sided lime rail is
   replaced by neutral informational treatment.
2. Body, light, 393×844, expanded: outer surfaces and the expanded history/editing content are
   separated with the existing spacing tokens.
3. Body, dark, 1440×1000, expanded: the desktop two-column hierarchy remains legible while the
   diary is open.
4. Body, light, 393×844, `action-add-measurement`: the form and history remain reachable in the
   action state.

This is synthetic browser evidence only. It does not prove physical iPhone/Safari, native
Telegram, VoiceOver, real touch, production data or owner visual acceptance.
