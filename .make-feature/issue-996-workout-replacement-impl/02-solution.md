# Solution

- Branch base: exact `origin/master` SHA `dc1daeb57bc7eded67a089b206e8f84375fea8d1`.
- Approved visual source: Variant 02, `3a8cd073d8c3b0570d640190099be7c0209cbb0b9`.
- Keep the existing WorkoutAdaptation endpoint, preview/apply contract and current-workout
  authorization semantics. Add only backwards-compatible media fields to alternatives.
- Resolve media server-side from the candidate exercise identity/catalog source, then render
  it through existing `ExerciseMediaAsset`; missing or broken media keeps a selectable card
  with the existing fallback and never invents an image.
- Keep search/filter local to the complete server response. No new endpoint, dependency,
  queue, lifecycle state, or production action.
