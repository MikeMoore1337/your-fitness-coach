# Make Feature: Issue #997 implementation

- Stage: final visual fixes implemented; exact-head CI pending after the follow-up push. Release, merge and deploy remain blocked.
- Depth: normal — one approved preview flow across frontend data mapping, assignment freshness, accessibility, tests and browser evidence; no new backend contract, migration, dependency or production action.
- Base: exact current `origin/master` SHA `afc9a3e918f4085e506b711c5cacfe4b5c5a0f5c`.
- Approved design: Issue #997 package, design SHA `f17930417257814633b5178d6141662342dfff66`.
- Existing PR: #1096, branch `codex/issue-997-program-preview-implementation`; no duplicate PR created.
- Scope: factual program preview before assignment, ownership/permissions, separated actions, stale-source guard, Russian UI guard repair, WebKit focus return, responsive Dark/Light AFTER evidence.
- Constraints: preserve existing API and assignment authority; no guessed metrics, no mutations from view/select/copy/close, no merge/deploy, no activation of unrelated product work.

## Acceptance gates

- C1: approved composition and factual source mapping are implemented in the existing PR.
- C2: unknown/incomplete fields remain explicit `Нет данных`; trainer-owned plans remain read-only; actions stay distinct.
- C3: fresh source comparison prevents assignment after a changed revision/title and preserves the preview.
- C4: frontend unit/lint/typecheck/build and Chromium/WebKit browser evidence pass; final local regression is 940 tests.
- C5: exact-head GitHub aggregate `checks` is pending after the follow-up push; owner visual acceptance, release approval, merge and deploy remain separate gates.
