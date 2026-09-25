# Issue #386 · integration и release contract

## Зафиксированное состояние

| Поле                          | Значение                                                        |
| ----------------------------- | --------------------------------------------------------------- |
| Current master                | `c4cb1681ba8302447307d9012e47666af5ba34ca`                      |
| `origin/master`               | тот же SHA                                                      |
| Long-lived integration branch | local `feature/app-experience-v3` от этого SHA                  |
| Task branch                   | local `task/386-app-experience-v3-stage0` от integration branch |
| Task worktree                 | `.artifacts/worktrees/task-386-app-experience-v3-stage0`        |
| Remote integration push       | нет                                                             |
| Task PR / merge / deploy      | нет                                                             |
| Production env diff           | нет; `env change required: no`                                  |

Task worktree создан после refresh canonical `master`; он не содержит uncommitted изменений на
момент старта. Изменения Stage 0 оставляются локальными до owner visual approval.

Стандартный `scripts/task_session.py start 386` не применялся: в текущем checkout нет локального
task document Issue #386, а normal controller создаёт ветку от `origin/master` и ожидает обычную
PR-to-master lane. Для этого явно owner-заданного integration-only Stage 0 использован ровно один
local feature branch и один task worktree; отдельная lease/delivery state не создавалась.

## Production deploy isolation

Фактический contract из текущих workflows:

- `.github/workflows/ci.yml` запускается для PR, push в `master`, schedule и manual dispatch;
- container publish имеет condition только для `push` в `refs/heads/master`;
- `.github/workflows/deploy.yml` слушает только completed `CI` для branch `master`;
- deploy authorization требует `workflow_run.event == push`, success и exact merged PR в `master` с
  `merge_commit_sha == DEPLOY_SHA`;
- controller-only merge и schedule/manual runs не получают production deploy decision;
- production SSH target/path остаются текущими в workflow: `77.91.90.171:1337`, user `yfc-deploy`,
  `/srv/yfc/fit-mini-app`; secrets не читались и не менялись;
- deployment script работает с immutable bundle/provenance и не делает checkout/fetch/reset из Git.

Локальный prototype server на `127.0.0.1:4178`, task branch и local feature branch не совпадают
ни с push в `master`, ни с merge commit, поэтому сами по себе не могут удовлетворить deploy gate.

## Разрешённые действия Stage 0

- read-only audit workflows, source, fixtures, catalog manifest и docs;
- docs и isolated static prototype в task worktree;
- local screenshots/evidence под `.artifacts/tasks/386/`;
- targeted deterministic checks и owner local review.

## Запрещённые действия Stage 0

- push `feature/app-experience-v3` или task branch;
- PR, merge в feature/master, production deploy или manual deploy;
- изменение `.github/workflows`, `.env`, Docker topology, authz, DB, API, runtime production UI;
- запуск #387/#388/#389/#395/#396/#397/#390/#391/#392/#393;
- создание media assets, migration, new feature flags или второго backend/mock transport.

Production visual contract: текущие YFC typography, spacing, cards, controls, Liquid Glass,
Light/Dark, icon language и shell остаются source of truth. Stage 0 prototype не является
production design specification.

## Owner gate

Stage 0 заканчивается на owner checkpoint. До явного owner visual approval нельзя переносить
prototype direction в production implementation и нельзя объединять task branch с integration branch.
После approval Stage 1 (#387) должен отдельно подтвердить exact base, разрешённую поверхность,
target context persistence и client/trainer authorization regression plan.
