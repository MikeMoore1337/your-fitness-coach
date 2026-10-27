# Make Feature: Issue #996 implementation

- Stage: implementation after explicit owner approval; merge/deploy remain blocked.
- Depth: normal — one approved UI flow plus a backwards-compatible API enrichment and
  cross-layer regression evidence; no new security, billing or migration risk.
- Base: `origin/master` at `dc1daeb57bc7eded67a089b206e8f84375fea8d1`.
- Approved design: Variant 02, `3a8cd073d8c3b0570d640190099be7c0209cbb0b9`.
- Scope: replacement bottom sheet, server-confirmed alternatives, existing catalog media when available, tests, Draft PR, real browser AFTER evidence.
- Constraints: preserve current preview/apply, authorization, safety-stop and current-workout-only semantics; no new endpoint, dependency, queue, lifecycle state or production action.

## Acceptance gates

- C1: approved Variant 02 behavior is implemented in the working app.
- C2: alternative cards use reliable `exercise_id` media enrichment only; missing/broken media keeps the card selectable.
- C3: targeted and repository checks pass without weakening assertions.
- C4: Draft PR exists with real synthetic browser Dark/Light AFTER screenshots.
- C5: owner visual acceptance and release approval remain pending; no merge/deploy.
