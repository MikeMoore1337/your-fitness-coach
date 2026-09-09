# Completion checklist - release backlog v11

## Per task

- [ ] Worked in permanent `dev` or an explicitly authorized temporary branch from current `dev`.
- [ ] Read root `AGENTS.md`, `GLOBAL_RULES.md`, lifecycle, current task and primary role.
- [ ] Loaded only core `Рекомендуемые skills` initially.
- [ ] Loaded each `Условный skill` only after its actual trigger was proven.
- [ ] Ran only the exact additional lifecycle roles declared by the task.
- [ ] Did not create an agent per skill or automatic researcher/reviewer/QA chain.
- [ ] Read `ACTIVE_DESIGN_SOURCE.md` before visual work.
- [ ] For tasks `49B1-49G`, followed applicable `DESIGN_ALTERNATIVES_EXPLORATION_CONTRACT.md`.
- [ ] For client-facing UI, preserved `GLOBAL_RULES.md` UI consistency contract and did not create a local duplicate primitive/system.
- [ ] For client-facing scope, followed applicable mobile/TMA contract/matrix.
- [ ] Выполнены targeted checks; записаны точные команды и результаты.
- [ ] Self-review выполнен primary writer в текущей сессии, отдельный Codex reviewer не запускался.
- [ ] Перед merge exact-head CI и aggregate `checks` GREEN; PR mergeable, существующие threads resolved.
- [ ] Only `BLOCKER/HIGH` blocked completion.
- [ ] `MEDIUM/LOW/NIT/OUT_OF_SCOPE` did not create new schema/API/platform/product scope.
- [ ] Added or updated every `MEDIUM/LOW` in `codex-backlog/bugs/FINDINGS.md`, including findings
      fixed in the same task, and recorded their IDs/statuses in the final report.
- [ ] If blocking findings were fixed, repeat verification/QA was targeted rather than a new full audit.
- [ ] Stayed within lifecycle verification/QA limits.
- [ ] Checked final `git diff`, migrations/config/dependencies/generated artifacts.
- [ ] Did not claim real Telegram/device coverage without actual verification.
- [ ] Created one logical commit when applicable.
- [ ] Did not start the next task.

## Исторический checkpoint 49B1

- [ ] Audited real rendered UI once and covered each distinct UI pattern family rather than every duplicate route.
- [ ] Built component inventory and froze one baseline finding set before remediation.
- [ ] Closed all in-scope `MUST_FIX` findings without importing Direction A/B/C.
- [ ] Preserved business logic/API/schema/auth contracts.
- [ ] Verified mobile-first baseline plus representative desktop/light/dark states.
- [ ] Self-review/QA verified the frozen set and regressions instead of starting a second product-wide audit.


## Release gates

- [ ] Tasks `00-55` remained untouched as completed history under `tasks/done/`.
- [ ] Current task did not alter the closed `49A-49G` design decision.
- [ ] Current client-facing task reused the continuous gate established by completed task `50A`.
- [ ] Task `76` has no open release-blocking `BLOCKER/HIGH`.
- [ ] Task `77` evidence is factual.
- [ ] Task `78` production evidence exists.
- [ ] Task `79` contains go/no-go evidence.
