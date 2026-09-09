# Issue-driven continuous workflow

Этот документ описывает обычный owner-facing путь для уже существующих задач YFC. GitHub Issue
является control plane: в ней фиксируются Task ID, scope, acceptance criteria, зависимости,
checkpoint'ы, risk lane, PR, exact head и итоговый production verdict. Подробная локальная task
spec остаётся источником требований, но не может молча переопределять Issue, GitHub PR или
controller state.

## Обычная разовая задача

```text
Owner -> ChatGPT -> GitHub Issue -> Codex -> task worktree -> PR
      -> exact-head review/CI -> merge -> production -> cleanup/archive
```

Один owner launch покрывает обычные commit, push, PR, CI, merge, normal deploy и closeout. Для
каждой задачи сохраняется связь `1 Issue = 1 task/<ID>-<slug> branch = 1 registered worktree = 1
PR`; implementation остаётся в task worktree, а refresh, merge, deploy и production closeout
проходят через единственную serial delivery lane.

До merge обязательны:

- current base/head и task provenance;
- `checks` на exact PR head;
- завершённый formal GitHub approval или trusted Codex review comment с exact-head marker;
- отсутствие unresolved review threads и актуальных blocking findings;
- clean/mergeable PR.

На самом `pull_request_review` event GitHub может временно вернуть `mergeable_state=blocked` или
`unstable`, поскольку aggregate `checks` ещё ждёт результат самого `review-contract`.
Event-проверка разрешает эти состояния только вместе с exact-head завершённым review; прямой
`validate-pr-review` перед merge остаётся строгим и принимает только clean/has_hooks.

Проверка выполняется командой `scripts/task_session.py validate-pr-review`. Review старого head
не переносится на новый commit. Mapping severity не меняет blocking semantics: `P0 -> BLOCKER`,
`P1 -> HIGH`, `P2 -> MEDIUM`, `P3 -> LOW`, `NIT -> LOW`.

## Непрерывная очередь

Очередь не включается наличием backlog. Владелец явно активирует её командой или control comment
`CONTINUE_QUEUE`, например:

```powershell
& .\.venv\Scripts\python.exe scripts\run_task_delivery.py `
  --continue-queue --control-issue 218 --max-tasks 4
```

Launcher использует только существующие task specs и их GitHub Issue contracts, соблюдает порядок
canonical backlog и проверяет подтверждённые terminal dependencies. За один batch допускается не
более четырёх задач. На одну задачу допускается не более трёх review-fix и трёх CI-fix cycles;
scope expansion равен нулю. После достижения лимита, ошибки CI/deploy, dependency blocker или
отсутствия безопасной Issue contract очередь останавливается.

Единый queue claim хранится в shared Git common directory. Запись содержит PID и process-instance
identity: на Windows — время создания процесса, на Linux/POSIX с `/proc` — boot ID и start ticks.
При collision launcher проверяет liveness и совпадение этой identity; один PID без identity не
считается достаточным, поэтому повторно выданный PID после crash или reboot не блокирует очередь.
Только подтверждённый stale claim после аварийного завершения процесса атомарно переносится в
quarantine, повторно сверяется и удаляется, после чего acquire повторяется. Активный,
повреждённый, изменившийся во время recovery или непроверяемый claim остаётся `HUMAN_REQUIRED`
и не удаляется автоматически.

Для queue-mode authoritative-счётчики review-fix и CI-fix хранятся в durable controller ledger.
Перед каждым фактическим fix cycle worker обязан выполнить `record-queue-cycle`; `final.md`
содержит только проверяемый worker cross-check и не может занизить ledger. Повторная публикация
уже актуального состояния `queued` не выполняется.

Если после controller `finish` проверка worker budget или closeout обнаруживает terminal failure,
launcher публикует queue-wide `human_required` с `terminal_verdict=queue_stop` на центральном
control Issue. Следующий запуск сначала проверяет этот durable stop и не сканирует следующий task,
пока владелец не разберёт blocker.

Machine-readable control-state comment использует маркер `yfc-control-state:v1` и состояния
`queued`, `in_progress`, `review_wait`, `fix_required`, `ci_wait`, `merge_ready`, `merged`,
`deploy_wait`, `production_verified`, `human_required`, `blocked`, `cleanup_deferred`.

## Когда нужен владелец

`GREEN` — обычная реализация с активным launch/queue authorization. `YELLOW` или `RED` не
обходятся очередью. Остановка `HUMAN_REQUIRED` нужна для real-user/physical-device evidence,
визуального approval, выбора продукта, billing или paid service, provider/credential/secret,
DNS/Cloudflare/R2 и другой внешней консоли, legal counsel, destructive production/data action,
а также для любого task-specific checkpoint.

Merge не считается production success. Следующая sequential task запускается только после
terminal production verdict и bounded cleanup предыдущей задачи. Dirty, interrupted, unknown или
ambiguous worktree даёт `cleanup_deferred`; controller не использует `reset --hard`, force delete
или удаление чужой ветки.

Состояние очереди восстанавливается из GitHub Issue/PR, exact SHA, review threads, workflow runs,
production evidence и local controller coordination state. Новая БД, daemon, permanent `dev`,
paid dependency или отдельный orchestrator для этого режима не создаются.
