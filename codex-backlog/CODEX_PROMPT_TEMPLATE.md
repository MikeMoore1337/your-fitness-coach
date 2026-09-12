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
Обычная task без `concurrency` metadata считается `independent-write`; legacy `exclusive-write` не
создаёт repository-wide implementation barrier. Task PR открывай только в `master`, сохраняя
`[Task <ID>]`; implementation/self-review/QA task могут идти параллельно в отдельных worktree, а
delivery owner единолично сериализует refresh, current-base/provenance check, PR, exact-head CI,
bounded Codex review, merge и product delivery. После GREEN `checks` один раз вызови
`request-codex-review --round 1`; при blocking P0/P1 сделай один batch fix, affected checks, новый
exact-head CI и максимум `--round 2`. CLEAN разрешает merge, второй blocking result даёт
`HUMAN_REQUIRED`, третья проверка запрещена. Не deploy production вне task release contract. Не
переходи к следующей task.
```

## Current start

Текущая task после подтверждённо завершённых и перенесённых в `tasks/done/` задач `00-57`:

```text
Выполни `codex-backlog/tasks/58-workout-adaptation-experience.md`.
```

После успешного завершения `58` следующая task — `59`. Не переходить к ней в той же сессии.


Automatic Codex Code Review не включается. Bounded review запускается только после exact-head CI
GREEN; отдельный reviewer/subagent не создаётся. Self-review выполняется один раз implementer в
текущей сессии. Release требует targeted tests, применимых static analysis/integration/e2e,
exact-head CI и aggregate `checks` GREEN, CLEAN review, отсутствия unresolved BLOCKER/HIGH,
mergeable PR и resolution существующих threads.
Явные task-specific human/external/security/legal/destructive gates сохраняются.
