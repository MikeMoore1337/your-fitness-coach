# Codex prompt template v10

Use one fresh Codex chat per task. Select model/reasoning manually according to `MODEL_SELECTION.md`.

```text
Выполни `codex-backlog/tasks/NN-task-name.md`.

Соблюдай `AGENTS.md`, `codex-backlog/GLOBAL_RULES.md` и полный task lifecycle.
Перед любой visual work прочитай `codex-backlog/ACTIVE_DESIGN_SOURCE.md`.
Для tasks `49B1-49G` также соблюдай применимые части `codex-backlog/DESIGN_ALTERNATIVES_EXPLORATION_CONTRACT.md`.
Для client-facing task соблюдай `codex-backlog/MOBILE_TMA_FIRST_CONTRACT.md` и mobile/TMA acceptance текущей задачи.

Перед началом выполни `python scripts/task_session.py doctor`. Task должна быть запущена controller
в отдельном `task/<ID>-<slug>` worktree от exact `origin/master`; основной `master` защищён и
integration-only.
Используй переданные controller абсолютный worktree path, branch/base SHA, canonical task path,
dependencies/concurrency и recovery command. Не меняй другой worktree и не создавай второй lease.
Открой только текущую task, её primary role и core skills. Conditional skills - только по фактическому trigger.
Выполни только дополнительные lifecycle-роли, явно указанные task.
Не запускай полный audit/suite и не подключай новые роли "для надёжности" без требования task/доказанного риска.
Только BLOCKER/HIGH блокируют завершение; non-blocking findings не расширяют scope.
Каждый MEDIUM/LOW до commit добавь или обнови в `codex-backlog/bugs/FINDINGS.md`.
Обычная task без `concurrency` metadata считается `independent-write`; `exclusive-write` допустим
только для global/coordination-sensitive изменений. Task PR открывай только в `master`, сохраняя
`[Task <ID>]`; implementation/review/QA совместимых task могут идти параллельно, а delivery owner
единолично сериализует refresh, final gate, PR, CI, merge и production. READY/waiting/CI/production
не удерживают implementation exclusion. Не deploy production вне task release contract. Не
переходи к следующей task.
```

## Current start

Текущая task после подтверждённо завершённых и перенесённых в `tasks/done/` задач `00-57`:

```text
Выполни `codex-backlog/tasks/58-workout-adaptation-experience.md`.
```

После успешного завершения `58` следующая task — `59`. Не переходить к ней в той же сессии.
