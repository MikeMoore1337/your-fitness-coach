# Production deployment

Обычная production delivery запускается GitHub Actions после успешного CI на protected `master`:

GitHub is the operational source of truth for release and deployment state.

```text
merge master -> successful CI -> changed-path decision -> immutable bundle -> migrations
-> rollout -> smoke/evidence
```

Production concurrency — native Actions:

```yaml
concurrency:
  group: production
  cancel-in-progress: false
```

Никакой repository-local mutex, delivery owner или persistent delivery queue не нужен.

## Deploy scope

`scripts/deployment_scope.py` получает base/head из Git и каждый раз заново вычисляет changed
paths. Он не хранит состояние.

Application deploy требуется для фактических изменений:

- backend и bot runtime;
- frontend runtime/build inputs;
- Alembic migrations;
- Docker/Compose/Caddy/deploy configuration;
- runtime dependency lock/configuration;
- runtime scripts copied into an application image.

Только документация, backlog, governance, tests-only, CI/deploy workflow и host-side delivery
helpers не требуют application deploy: они проверяются CI и попадут в следующий deployable
release, но не перезапускают неизменившийся application runtime. Известный non-governance path
классифицируется консервативно.

## Safety

Deploy workflow:

- требует exact successful CI run для deploy revision;
- создаёт immutable `git archive` bundle из exact revision;
- передаёт migration manifest и immutable image references;
- проверяет active revision и безопасную migration последовательность;
- выполняет существующий rollout с health checks, worker/bot ownership checks и production smoke;
- сохраняет operational evidence под `.artifacts/operations/deployments/` на production host.

Deployment evidence — operational release record, не development lifecycle state.

If a read-only preflight finds a uniform running revision that differs from the recorded marker,
normal deployment fails closed before transfer or service mutation. The owner-authorized
`workflow_dispatch` operation `reconcile` accepts the exact tested revision and successful CI run,
rechecks runtime images, health, migration heads, release files and public/SEO smoke, then may
update only the existing marker and `current` symlink. It never restarts services, pulls images,
runs migrations, changes `.env` or writes application data.

## Rollback

Rollback — owner-authorized `workflow_dispatch` operation `rollback` с указанием известной
успешной active production SHA. GitHub Actions native concurrency сериализует операцию.
Текущий release state выбирает предыдущую известную успешную revision, запускает существующий
rollback helper и production smoke. Local controller state не требуется.

Failed deploy не оставляет вечного local lock/owner: queued/running Actions завершает работу по
native concurrency, а deployment evidence и health checks сообщают результат. Real deployment
failure fail-closed; cleanup/archive failure — warning.
