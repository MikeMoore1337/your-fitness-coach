# Make Feature: Issue #997 implementation

- Stage: implementation complete locally; existing PR #1096 remains Draft pending exact-head CI and owner visual acceptance.
- Depth: normal — one approved preview flow across frontend data mapping, assignment freshness, accessibility, tests and browser evidence; no new backend contract, migration, dependency or production action.
- Base: exact current `origin/master` SHA `ace951a13c2672189fdc464e92bd12b6371f3914`.
- Approved design: Issue #997 package, design SHA `f17930417257814633b5178d6141662342dfff66`.
- Existing PR: #1096, branch `codex/issue-997-program-preview-implementation`; no duplicate PR created.
- Scope: factual program preview before assignment, ownership/permissions, separated actions, stale-source guard, Russian UI guard repair, WebKit focus return, responsive Dark/Light AFTER evidence.
- Constraints: preserve existing API and assignment authority; no guessed metrics, no mutations from view/select/copy/close, no merge/deploy, no activation of unrelated product work.

## Acceptance gates

- C1: approved composition and factual source mapping are implemented in the existing PR.
- C2: unknown/incomplete fields remain explicit `Нет данных`; trainer-owned plans remain read-only; actions stay distinct.
- C3: fresh source comparison prevents assignment after a changed revision/title and preserves the preview.
- C4: frontend unit/lint/typecheck/build and Chromium/WebKit browser evidence pass.
- C5: exact-head GitHub aggregate `checks`, owner visual acceptance, release approval, merge and deploy remain separate gates.
