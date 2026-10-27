# Issue #871 — implementation AFTER evidence

This package demonstrates the minimal implementation of the **owner-approved** order from design-only PR #1032, commit `6fa32793c64423e625d04c264164321be87f453b`. Owner design approval is recorded in [Issue #871](https://github.com/MikeMoore1337/your-fitness-coach/issues/871#issuecomment-6216518654).

## Scope

- Only reorder existing JSX in `WorkoutCompletionSummary.tsx`: `hero → facts → recorded results disclosure → conditional personal records → optional feedback + existing feedback disclosure → next`.
- AI Coach component is left subject to the existing global UI-hidden gate and placed after the next action as an inert entry. No AI code, provider or runtime flag changes.
- Empty exercise result lists or personal records do not produce an empty disclosure.
- Existing workout metrics, API calls, feedback mutation, comments, accessible disclosure, cardio/strength formatting, links and routes stay unchanged.
- No shared CSS tokens or brand palette changes. No migrations, backend or deployment configuration.

## Real running-component screenshots (synthetic data)

These images come from the **actual frontend Vite build**, exercised by `tma-smoke.spec.ts` with deterministic mock Telegram context and mocked Platform API. They are **not** static design-only HTML prototypes.

- [AFTER Dark, 390 px](./after-390-dark-tma-mock.png)
- [AFTER Light, 390 px](./after-390-light-tma-mock.png)
- [Approved design-only BEFORE/PROPOSED and all states](https://github.com/MikeMoore1337/your-fitness-coach/blob/6fa32793c64423e625d04c264164321be87f453b/docs/ux/issue-871-workout-completion-design-20261016/README.md)

Captured after a simulated finished strength workout. This test covers actual DOM order, result disclosure geometry, editable feedback, retries, restoration, quick navigation, TMA lifecycle, and absence of horizontal overflow.

## Local verification

- `npm ci`: success.
- Vitest `tests/unit/features/workouts/WorkoutCompletionSummary.test.tsx`: **6/6 passed** (including exact DOM order and empty-list cases).
- `npm run typecheck`: passed.
- `npm run lint`: passed, including Russian user-facing UI guard.
- `npm run build`: passed.
- Playwright `tma-smoke.spec.ts --grep "completion summary survives finish retry"`: **1/1 passed**. Screenshot run repeats the scenario with `YFC_CAPTURE_871=1`, also **1/1 passed**.
- Full required GitHub CI and any additional visual goldens to be confirmed on exact PR HEAD.

## Release gates

**Implementation Draft PR only**. No owner AFTER visual acceptance, merge, or production deploy is implied by approval of the earlier design mockup. Physical iPhone/Safari, native Telegram, VoiceOver and native keyboard are **NOT VERIFIED**; mock TMA is not native Telegram. Final owner visual acceptance plus separate release authorization are required.
