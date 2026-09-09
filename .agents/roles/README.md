# YFC Codex roles v3

Role определяет ответственность прохода. Skill определяет профильные знания. Task определяет scope.

Доступно шесть ролей:

1. `orchestrator`
2. `researcher`
3. `product-lawyer`
4. `implementer`
5. `qa-verifier`
6. `integration-release`

Lifecycle/severity/recheck/commit policy не дублируется здесь. Для backlog task canonical source - `codex-backlog/TASK_EXECUTION_LIFECYCLE.md`.

Не создавать роль на каждый skill.

`product-lawyer` — узкая read-only роль для dedicated legal-risk audit и owner decision package;
обычные feature/fix tasks не меняют на неё primary role.
