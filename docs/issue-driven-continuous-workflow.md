# Issue-driven continuous workflow

Этот документ описывает обычный owner-facing путь для уже существующих задач YFC. GitHub Issue
является control plane: в ней фиксируются Task ID, scope, acceptance criteria, зависимости,
checkpoint'ы, risk lane, PR, exact head и итоговый production verdict. Подробная локальная task
spec остаётся источником требований, но не может молча переопределять Issue, GitHub PR или
controller state.

## Обычная разовая задача

```text
Owner -> ChatGPT -> GitHub Issue -> Codex -> task worktree -> PR
      -> exact-head CI -> merge -> production -> cleanup/archive
```

Один owner launch покрывает обычные commit, push, PR, CI, merge, normal deploy и closeout. Для
каждой задачи сохраняется связь `1 Issue = 1 task/<ID>-<slug> branch = 1 registered worktree = 1
PR`; implementation остаётся в task worktree, а refresh, merge, deploy и production closeout
проходят через единственную serial delivery lane.

До merge обязательны:

- current base/head и task provenance;
- `checks` на exact PR head;
- отсутствие актуальных blocking P0/P1 findings из применимой проверки;
- clean/mergeable PR.

После GREEN exact-head `checks` controller запрашивает один bounded Codex semantic review. CLEAN
разрешает merge; только подтверждённые blocking P0/P1 разрешают один batch fix и re-review на новом
SHA. MEDIUM/LOW/NIT не запускают повторный review, clean result не повторяется, а второй blocking
result возвращает `HUMAN_REQUIRED`. CI не включает отдельный LLM job, automatic Code Review не
включается, а review не заменяет security/legal/human/destructive gates. Automatic Security Review
для обычного PR выключен и не сцепляется с Code Review; это отдельный manual/conditional gate,
запускаемый только при фактическом security trigger. Deterministic security scanners остаются в CI.

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
identity: на Windows — время создания процесса, на Linux — boot ID и start ticks из `/proc`, а на
macOS — bounded probes системного времени запуска процесса и boot time.
При collision launcher проверяет liveness и совпадение этой identity; один PID без identity не
считается достаточным, поэтому повторно выданный PID после crash или reboot не блокирует очередь.
Codex worker запускается через отдельный supervisor, который также проверяет exact parent
identity и запускает worker через bounded bootstrap guard. На POSIX guard запускает Codex в
отдельной process group, наблюдает lifetime supervisor и при parent-loss завершает всю группу;
это покрывает и Codex, и его tool/shell descendants. На Linux guard получает
`PR_SET_PDEATHSIG` до `exec`, а после старта переключается на обработчик, который уничтожает
worker group, поэтому SIGKILL/OOM supervisor не оставляет Codex descendants работать дальше.
На macOS тот же guard использует bounded parent-polling и тот же group kill.
Worker state с PID, process-instance identity и process-group ID записывается атомарно до
начала дальнейшей работы. При ошибке supervisor launcher сверяет и при необходимости
завершает эту группу; active queue claim сохраняется при любом abnormal worker exit, поэтому
новый launcher не reclaim-ит очередь до reconciliation.
На Windows guard сначала ждёт release от supervisor. Supervisor сначала помещает этот ещё
не запустивший Codex guard в Job Object с `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, затем отправляет
release; Codex и его дочерние процессы наследуют Job Object без assignment gap.
Claim атомарно обновляет `queue_phase`, `task_id`, `task_issue` и `worker_state` перед запуском
каждой задачи и очищает их только после полного `_deliver_one`. Если owner провалился, пока claim
содержит активную задачу, recovery сначала читает durable controller history и останавливается
с `HUMAN_REQUIRED`: claim не переносится в quarantine и не удаляется до ручной reconciliation
controller, supervisor и control Issue.
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

Состояние очереди восстанавливается из GitHub Issue/PR, exact SHA, workflow runs, production
evidence и local controller coordination state. Новая БД, daemon, permanent `dev`,
paid dependency или отдельный orchestrator для этого режима не создаются.
