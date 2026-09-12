# Task-ветки, worktree и прямой PR-flow в `master`

## Постоянная политика quality gates

Deterministic CI/tests/static-analysis checks и специальные human/external gates остаются
обязательными. Automatic Codex Code Review не включается; bounded review запрашивается только
после GREEN exact-head `checks` как финальный semantic gate. Разрешены round 1 и максимум один
re-review после одного batch fix blocking P0/P1 на изменившемся head SHA. MEDIUM/LOW/NIT не
запускают re-review, clean verdict не повторяется, третий request запрещён.
Implementer делает один bounded self-review до commit; отдельный reviewer-agent/subagent не создаётся.
Controller-команды `request-codex-review` и `validate-codex-review` проверяют PR/status/comments/
reviews/threads, переиспользуют pending/completed review текущего SHA и возвращают `HUMAN_REQUIRED`
после второго blocking P0/P1.

Normal path: implementation → targeted verification → final deterministic verification → bounded
self-review → commit/push → PR → exact-head CI GREEN → Codex review → merge → post-merge cleanup
→ product-task deploy/production closeout.
Для PR-triggered CI PR открывается перед ожиданием его required checks.
Обязательны relevant targeted tests PASS, применимые lint/format/typecheck PASS,
required integration/e2e PASS, exact-head CI GREEN и aggregate GitHub status `checks` GREEN.
Известные unresolved BLOCKER/HIGH текущей реализации/QA блокируют завершение.
PR должен быть mergeable и соответствовать branch/ruleset policy; уже существующие review threads
нужно фактически исправить и resolved до bounded review. Review не запускается до GREEN CI,
повторно на том же SHA или после clean verdict.
PR-only master, required checks, non-fast-forward protection, thread resolution и CI сохраняются.
Профильные security/legal/destructive/owner/human/external gates сохраняются по фактическому риску;
Codex review их не заменяет.
Следующую product task автоматически не запускать.


Статус ADR: **принято и действует в repository contract и live GitHub enforcement**.

## Контракт

Нормальный flow разделён на независимую implementation lane и одну serial delivery lane:

```text
Task A/B/C: implementation -> relevant fast checks -> self-review -> применимая QA
            -> commit/push -> PR master

одна delivery lane:
  current-base/provenance check -> exact-head GitHub checks -> merge master
  -> post-merge provenance/image publication
  -> immutable bundle deploy -> smoke/observation
  -> controller finish -> archive/check
```

`master` — защищённая release-ветка и единственный normal release base. Task branch создаётся
только от exact `origin/master`; stacked branches по умолчанию запрещены. Canonical controller
worktree используется для координации и closeout, но не для feature implementation. Legacy `dev`
refs могут оставаться в repository для recovery/inventory, но не являются частью normal delivery.

Несколько task могут одновременно иметь отдельные writer leases и worktrees. Legacy
`exclusive-write` metadata не создаёт repository-wide implementation barrier: отдельные worktree
позволяют независимым task идти параллельно, а реальный конфликт файлов обнаруживается при serial
delivery refresh/rebase. Очередь, delivery, GitHub CI и active production deploy не блокируют
начало отдельной implementation. Merge в `master` и product production deployment всегда serial.

GitHub Ruleset для `master` обязан быть active и требовать pull request, deletion protection,
non-fast-forward protection, strict current-base required checks и aggregate check `checks`.
Direct/force push и удаление ветки запрещены. Merge PR — release authorization; отдельный generic
approval между merge и normal deploy не создаётся.

## Shared gate

`scripts/ci_contract.py` — единственный registry команд CI. Он содержит детерминированные профили:
`frontend`, `backend`, `migration`, `cross-stack`, `workflow-platform`, `documentation`.
GitHub workflow вызывает эти group IDs; profile выбирается по изменённым путям консервативно, а
отсутствующий prerequisite даёт понятный failure. Локальный `scripts/local_checks.py` — только
добровольный быстрый dispatcher для тех же групп и не создаёт release evidence или controller state.

## Scope-aware remote CI

GitHub PR CI сначала запускает дешёвый `scope-router`. Он получает exact diff между
`pull_request.base.sha` и `pull_request.head.sha`, вызывает `scripts/ci_contract.py route` и передаёт
один decision в остальные jobs. `scripts/ci_contract.py` остаётся единственным registry команд и
одновременно используется локальным dispatcher, поэтому path classification не дублируется в
workflow `if:`.

Router выбирает консервативный профиль: documentation-only оставляет quality,
workflow-contract и aggregate `checks` (policy добавляется для policy-файлов); frontend/backend/migration/API и dependency changes
получают соответствующий минимальный safe set; unknown или shared CI contract автоматически
поднимаются до `cross-stack`. Для каждого запуска в логе видны `CI_SCOPE`, `CI_CHANGED_PATHS`,
`CI_REQUIRED_GROUPS`, `CI_REQUIRED_JOBS` и причины `CI_SKIPPED_GROUPS`. Aggregate job передаёт этот
expected result set в `scripts/ci_contract.py verify-results`; required job со статусом `skipped`,
`cancelled` или отсутствующий job не может дать зелёный `checks`.

Обычные PR runs используют `cancel-in-progress` только для одного PR: новый SHA отменяет устаревший
незавершённый run того же PR. Production/release workflow сохраняет `group: production` и
`cancel-in-progress: false`. `schedule` и `workflow_dispatch` на текущем `master` запускают
bounded `daily-regression` или `weekly-exhaustive` profile и единый `scheduled-report` job; они не
вызывают production deployment. Push в `master` остаётся минимальным post-merge набором exact
provenance и immutable container delivery. Подробный scope и private Allure contract описаны в
[`docs/scheduled-regression-allure.md`](scheduled-regression-allure.md).

Frontend jobs используют стандартный download cache `actions/setup-node` с ключом от
`frontend/package-lock.json`; `node_modules` не является artifact или cache. Dependency audit не
делает `npm ci`: для frontend выполняется `npm audit --omit=dev --audit-level=high`, а Python audit
выбирается отдельно. Только подтверждённые transient `429/5xx` и network errors получают максимум
две попытки (один bounded retry) с bounded backoff; найденная vulnerability, malformed lockfile или другая
воспроизводимая ошибка остаётся blocking без retry. Timing выводится как `CI_TIMING` для каждой
команды, cache signal — как `CI_CACHE`.

`scripts/task_session.py mark-ready` фиксирует durable `READY_FOR_DELIVERY`: clean task worktree,
commit provenance, PASS targeted checks/применимой QA, исходный base SHA и текущий task HEAD.
Это bookkeeping очереди, а не разрешение merge. Перед PR delivery owner проверяет current
`origin/master`, обновляет task branch только в serial delivery lane и фиксирует минимальный
`delivery_anchor` для последующей проверки exact merged/deployed SHA. Полный локальный regression
run остаётся добровольной диагностикой и не решает, может ли PR быть принят GitHub Ruleset.
Если HEAD изменился после `READY_FOR_DELIVERY`, перед push повторяются только relevant checks;
для owner-safe возврата в эту стадию используется
`reopen-for-review --reason <...>`, который освобождает delivery lane и удаляет старый readiness
snapshot.

PR CI не выполняет отдельный LLM review job и не запускается на `pull_request_review` event.
Merge-ready определяется exact-head `checks`, deterministic quality/policy checks, актуальной
provenance, mergeability, resolved threads и `CLEAN` bounded Codex result. Review request не
создаётся до GREEN CI; rate-limit/skip не ретраятся автоматически и дают `HUMAN_REQUIRED`.

## Leases и безопасный closeout

Controller хранит machine-local coordination state в shared Git common dir:

```text
<git-common-dir>/codex-task-sessions-v1/
├── contract.json
├── state.lock
├── delivery.json
├── leases/task-<ID>.json
├── reviews/pr-<N>.json
└── history/task-<ID>.json
```

State не коммитится. Create использует `O_EXCL`, update — temporary file + atomic replace под
`state.lock`. Corrupted JSON, malformed/active lock, duplicate branch/worktree, dirty/interrupted
state и неизвестная lease являются blocker; stale state lock reclaim-ится только по валидному owner
metadata, достаточному возрасту и однозначно мёртвому PID. Controller не удаляет active чужой
worktree или branch автоматически.

Task lease содержит task ID/path, branch, абсолютный worktree, original/current
`base_origin_master_sha`, target base, mode, timestamps, lifecycle state, queue sequence и session
label без secrets. `delivery.json` содержит только минимальный owner delivery lane и FIFO sequence;
это не старый release-freeze lease. Production success удерживает delivery owner до завершения
`finish`; только terminal closeout освобождает lane и передаёт её следующему FIFO candidate. `finish` запускается
из canonical controller worktree только после exact merged master SHA и terminal production success.
Он удаляет только matching clean task worktree и локальную task branch без `--force`; unique
commits, divergence refs, changed head и artifact cleanup error останавливают closeout с
сохранением данных.

Состояния `implementation`, `review`, `qa`, `ready-for-delivery`, `waiting-for-delivery`,
`delivering`, `delivery-gate`, `production-success` и `recovery-required` различаются явно.
`recover` не удаляет stale lease, dirty/interrupted worktree или unique commits автоматически.

`recover` — read-only диагностика. Он сохраняет dirty files, unique commits и interrupted Git
operations для owner-safe решения. Ни `recover`, ни `finish` не выполняют `reset --hard`, force
delete или несанкционированное восстановление.

Если recovery lease возник из-за прерванного delivery, а его единственный task worktree чист,
не имеет Git-операций и однозначно совпадает с lease, владелец может явно вернуть его в `review`:
`resolve-recovery <ID> --owner-authorize --reason <...>`. Команда проверяет branch/worktree,
base ancestry и отсутствие delivery owner, затем атомарно инвалидирует старый readiness snapshot;
она не удаляет файлы, ветки или lease и не выполняет `reset`/`stash`.

## Один пользовательский запуск

```powershell
.\.venv\Scripts\python.exe scripts\run_task_delivery.py <ID>
```

Явный выбор task владельцем или эта команда являются standing authorization для normal delivery
этой task: отдельный worktree, implementation/self-review/QA, commit, очередь delivery, refresh, task PR
в `master`, CI, immutable bundle deploy и safe closeout. Launcher не ждёт свободную delivery lane
до запуска worker: waiting после `READY_FOR_DELIVERY` — нормальное состояние, а не terminal blocker.
Останавливает только точный implementation/recovery blocker либо явно объявленный
human/legal/external/destructive/task-specific gate. Следующая product task автоматически не
запускается в разовом режиме. Явный `CONTINUE_QUEUE` через control Issue включает только bounded
batch существующих Issue-backed GREEN tasks; лимиты и точные правила описаны в
[`docs/issue-driven-continuous-workflow.md`](issue-driven-continuous-workflow.md).

Низкоуровневые команды:

```powershell
python scripts/task_session.py doctor
python scripts/task_session.py validate-metadata
python scripts/task_session.py refresh-canonical-master
python scripts/task_session.py start 135 --owner-launch --session-label codex-135
python scripts/task_session.py adopt-current 135 --owner-launch --session-label codex-135-resume
python scripts/task_session.py status
python scripts/task_session.py recover 135
python scripts/task_session.py resolve-recovery 135 --owner-authorize --reason "resume after verified recovery"
python scripts/task_session.py mark-ready 135 --head-sha <sha> --quality-verdict PASS --qa-verdict PASS
python scripts/task_session.py acquire-delivery 135
python scripts/task_session.py refresh-delivery 135
python scripts/task_session.py validate-delivery 135
python scripts/task_session.py reopen-for-review 135 --reason "address review findings"
python scripts/task_session.py complete-production 135 --pr <number> --merge-sha <sha> --deployed-sha <sha>
python scripts/task_session.py finish 135
```

### Безопасный refresh canonical `master`

`refresh-canonical-master` — единственная штатная операция для выравнивания локального
canonical controller checkout. Она сначала получает актуальный `origin/master`, в online mode
сверяет его SHA с live protected `master`, проверяет чистый canonical worktree и controller state,
а затем выполняет только `git merge --ff-only` к проверенному exact SHA. `git pull`, `reset`,
stash, обычный merge и push не используются. Task branches/worktrees, leases, PR и production
state этой операцией не меняются.

Операция возвращает machine-readable `result`:

| Result | Значение |
| --- | --- |
| `ALIGNED` | `master == origin/master == live/master`, mutation не выполнялась. |
| `REFRESHED` | canonical `master` fast-forward-нут; `old_sha`, `new_sha`, `behind_before` и `updated_commits` сохранены. |
| `WAITING` | remote/live freshness или безопасная serialisation временно недоступны: offline, active delivery/production или concurrent controller operation. Refs не меняются. |
| `BLOCKED` | dirty/ignored significant state, ahead/diverged refs, active Git operation, recovery/ambiguous state либо fetch/verification/fast-forward error. Никакого stash/reset/retry вслепую нет. |

Checkpoint автоматически выполняется перед `start`/`adopt-current` и перед
`refresh-delivery`. `refresh-delivery` по-прежнему refresh/rebase-ит только task branch и
обновляет минимальный `delivery_anchor`; canonical refresh не является GitHub CI result.
Пути `.artifacts/`, локальное environment/editor state, tooling caches и owner-only backlog
исключены из проверки ожидаемого ignored state, но неожиданный ignored path за этой границей
остаётся blocker (включая debug/log артефакты).
После устранения причины повторный online запуск идемпотентен и даёт `ALIGNED`.

Task-файл не копируется в worktree: owner-local canonical path остаётся единственным источником
backlog metadata. `validate-metadata` проверяет dependencies, `executable`, concurrency, owner gate
и integration policy. Неполные или unknown значения остаются fail-closed.

## CI и production provenance

PR в `master` обязан быть same-repository task branch с `[Task <ID>]` в title и commit messages,
его base SHA должен быть current, а `checks` — successful на exact PR head. PR-triggered CI выполняет
полный применимый профиль. После merge push-CI не повторяет full regression suite: он подтверждает
merged task PR provenance и публикует immutable backend/bot images через
`scripts/deployment_contract.py`.

`deploy.yml` принимает только successful `master` workflow run, ещё раз проверяет association с
merged task PR и current master, checkout выполняется только на GitHub runner. Runner создаёт
bundle из exact commit и migration manifest. Production host получает bundle по SSH, распаковывает
его в release directory, проверяет `.deployment-sha`, запускает `deploy_production.sh` с
immutable image refs и persistent state, а затем сохраняет release `.env`. На production host нет
шага `git fetch`, `git reset`, `git rev-parse` или зависимости от Git checkout.

Post-merge CI и deployment используют exact SHA; rollback/skip/manual-intervention verdict не
маскируется успешным job. Smoke, migration gate, image revision/digest, slot ownership, worker/bot
handoff и host lock остаются в deployment evidence под persistent `.artifacts/operations`.

Любая exceptional операция — history rewrite, direct/force push, manual production command,
bootstrap, infrastructure recovery или deployment SHA вне current merged `master` — требует
отдельного owner authorization, backup и operator preflight.

`--quality-verdict PASS` подтверждает выполненные targeted tests и применимый static analysis,
а не bounded Codex semantic verdict. `--qa-verdict PASS` подтверждает фактические проверки поведения;
`--qa-verdict NOT_REQUIRED` используется, когда task не объявляет QA-проверку;
отдельная QA-роль запускается только по task. Readiness не заменяет final exact-head CI gate.
Legacy имя recovery-команды `reopen-for-review` означает возврат к исправлению и повторной
проверке изменённых сценариев; отдельного reviewer оно не запускает.

Automatic Codex GitHub review не включается изменениями репозитория и настраивается только вне
репозитория в Codex Cloud settings. Если владелец не меняет внешнюю настройку, это фиксируется как
`MANUAL_EXTERNAL_SETTING`, но не блокирует repository changes. GitHub ruleset допускает ноль
approving reviews; его deterministic protections сохраняются.
