# YFC Codex roles v3

Role определяет ответственность прохода. Skill определяет профильные знания. Task определяет scope.

Доступно пять optional planning/verification roles:

1. `orchestrator`
2. `researcher`
3. `product-lawyer`
4. `implementer`
5. `qa-verifier`
GitHub Issues, branches, pull requests, Checks и Actions являются operational source of truth;
отдельной release/integration роли нет.

Severity/recheck/commit policy не дублируется здесь. Для обычной работы canonical path описан в
`docs/development.md` и `docs/deployment.md`.

Не создавать роль на каждый skill.

`product-lawyer` — узкая read-only роль для dedicated legal-risk audit и owner decision package;
обычные feature/fix tasks не меняют на неё primary role.
