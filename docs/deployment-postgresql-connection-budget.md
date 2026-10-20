# V11-DB-01 Phase B: trusted PostgreSQL connection budget

Документ описывает trusted runtime collector, fail-closed расчёт и подготовленную точку подключения rollout gate для #848. Collector и application markers реализованы, но production deployment пока не вызывает новый gate: live snapshot, owner-approved safety headroom, dry run и release approval не подтверждены.

## Что подтверждено в репозитории

Проверено относительно merge commit `bc48d09c3415c4b146a0400efc18cb9031413d18` (`origin/master` на начало Phase B):

| Область | Подтверждённый факт | Статус |
|---|---|---|
| SQLAlchemy backend/worker | PostgreSQL engine использует `pool_pre_ping=true`, `pool_size=DB_POOL_SIZE`, `max_overflow=DB_MAX_OVERFLOW`, `pool_timeout=DB_POOL_TIMEOUT_SECONDS`, `pool_recycle=DB_POOL_RECYCLE_SECONDS` | `VERIFIED` |
| Локальный статический baseline | `10 + 20 = 30` соединений на один pooled engine; `pool_timeout=30 s` | `VERIFIED` как настройки репозитория |
| Alembic | `backend/alembic/env.py` использует `NullPool` и передаёт фиксированный `application_name=yfc-migration`; отдельный migration connection — последовательный этап | `VERIFIED` по исходнику и regression test |
| Setup | readiness, Alembic и seed запускаются последовательно в `backend/setup-entrypoint.sh`; seed импортирует обычный application engine | `VERIFIED` по исходнику |
| Compose topology | legacy `backend`/`worker` и blue/green `backend-*`/`worker-*`; bot — отдельные consumers без найденного SQLAlchemy engine | `VERIFIED` по исходнику |
| Rollout order | существующий helper имеет `preflight`, `backup`, `migration`, candidate start, consumer handoff, observation и rollback/single-slot paths | `VERIFIED` по исходнику |
| Existing capacity audit | текущий manual audit снимает только часть host/PostgreSQL metrics и не считает rollout budget с reserved slots и attribution | `VERIFIED` по workflow |
| Trusted runtime collector | `scripts/trusted_runtime_collector.py` связывает rendered Compose, running container IDs, allowlisted runtime env, matching OCI revision labels и read-only PostgreSQL child snapshot из exact active container | `IMPLEMENTED`, live run `NOT_VERIFIED` |
| Connection attribution | backend/worker/setup/Alembic получают фиксированные `application_name`; runtime marker drift, неизвестные sessions и unattributed connections не становятся YFC | `IMPLEMENTED`, production attribution `NOT_PROVEN` |

`30` — это не production budget. Он не учитывает фактическое число процессов, blue/green overlap, pooler, внешние сессии и PostgreSQL reservations.

## Phase B correction: active vs candidate OCI provenance (2026-10-20)

В исходном сборщике `.deployment-sha` нового immutable release bundle ошибочно
сравнивался с OCI revision **уже работающих** backend/worker контейнеров.
До начала нормального обновления последние принадлежат предыдущему релизу,
поэтому такой контроль ложно блокировал любое штатное обновление A → B.

Исправление в существующем PR #1122:

- SHA **кандидата** по-прежнему читается из immutable `.deployment-sha`;
- SHA **работающего релиза** независимо берётся из
  `DEPLOY_STATE_ROOT/last-successful-revision` (или существующего
  `.artifacts/operations/deployments/last-successful-revision`);
- при наличии `state.json` его `active_revision` должен строго совпадать
  с маркером последнего успешного релиза, а `active_slot` должен иметь
  допустимое значение;
- OCI labels работающих YFC контейнеров сравниваются с SHA **активного** релиза,
  не с SHA кандидата; итоговая provenance context включает оба SHA;
- неизвестный/повреждённый маркер, несогласованное состояние, неожиданная
  работающая OCI revision — **не PASS**;
- если на синем/зелёном хосте остаётся работающий контейнер прежней rollback
  версии, не равной active SHA, сборщик консервативно блокирует сбор. Для
  сложной смешанной топологии требуется отдельное доказательство и точное
  соответствие service→revision, а не молчаливое расширение allowlist.

Это **исправление исходного контракта по коду**, подтверждаемое отрицательными
и положительными тестами, не подтверждение production capacity и не
автоматическое разрешение релиза. Collector всё ещё требует отдельно
утверждённый положительный safety headroom и реальные trusted runtime/DB
значения. Legacy runtime может не содержать модуль `postgres-child` или
новые application_name markers: первый upgrade по-прежнему может закономерно
блокироваться до отдельно авторизованного и проверенного способа bootstrap.
Никакой silent bootstrap или fail-open path не добавлялся.

## Что остаётся `NO_DATA` / `NOT_PROVEN`

Эти значения нельзя заменять нулём или значением из `.env.example`:

| Параметр | Почему блокирует production PASS |
|---|---|
| Effective `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT_SECONDS` для каждого production process | collector проверяет rendered/runtime equality и считает фактические running instances, но production output ещё не получен |
| `max_connections`, `superuser_reserved_connections`, PostgreSQL 16+ `reserved_connections` | без них нельзя получить usable capacity |
| Pooler: наличие, режим и backend connection caps | application pool ceiling не равен PostgreSQL backend ceiling при pooler |
| Число backend/worker процессов и реплик в steady state | collector учитывает configured и фактически running replicas, но production topology ещё не получена |
| Точный candidate/blue-green overlap, all-slot overlap и rollback concurrency | разные фазы имеют разные worst cases; scaled candidate instances учитываются консервативно |
| Migration, setup/seed, backup и прочие DB consumers | должны войти в фазу без двойного счёта |
| Current sessions и attribution YFC/non-YFC | current YFC sessions нельзя складывать поверх projected YFC cap; неатрибутированные сессии блокируют решение |
| Safety headroom | значение не фиксируется в коде; требуется owner-approved source и число |
| Snapshot provenance/freshness | private in-process token, exact host/revision context, bounded clock skew и trusted 300-second policy; stale/future/mixed snapshots fail closed |
| Effective topology inventory | process groups и применимые rollout phases должны быть перечислены явно; отсутствующие варианты отмечаются `false` |

В этой ветке нет production SSH/DB запроса, контейнеры не перезапускались, параметры PostgreSQL не менялись, secrets/connection strings/дампы не записывались. Изменения `docker-compose.yml`, backend engine setup и `backend/Dockerfile` являются deployment-affecting и намеренно не классифицируются как no-deploy.

## Модель

Для каждой pooled process group:

```text
process_ceiling = pool_size + max_overflow
```

Для каждого процесса сначала указывается эффективный тип pool:

- `pool_type=queue`: только `pool_size + max_overflow`; `connection_ceiling` одновременно запрещён;
- `pool_type=null` или `pool_type=special`: QueuePool-поля запрещены, нужен положительный явно подтверждённый `connection_ceiling` и его `connection_ceiling_source`.

Противоречивый QueuePool с меньшим `connection_ceiling` не может занизить расчёт — он получает `BLOCKED`. Missing pool type/fields не дают дефолт.

Для PostgreSQL:

```text
reserved_effective = reserved_connections                  # PostgreSQL 16+
reserved_effective = 0                                     # PostgreSQL <16, version known
usable = max_connections - superuser_reserved_connections - reserved_effective
```

`reserved_connections` для PostgreSQL 16+ обязателен. Для более старой версии нулевой fallback допустим только после подтверждения major version.

Для каждой взаимно исключающей worst-case фазы:

```text
app_connections = sum(process_replicas * process_ceiling)
phase_required = observed_non_yfc + app_connections + phase_other_connections
PASS iff phase_required + safety_headroom <= usable for every phase
```

`observed_yfc` используется для проверки attribution, но не добавляется к `app_connections`: projected process caps уже описывают YFC worst case. Дополнительно для подтверждённой фазы `steady-state` обязательно `observed_yfc <= app_connections` (или verified PostgreSQL backend cap при pooler). Поэтому явный zero-process maintenance-сценарий допустим при `observed_yfc=0`, а ненулевое наблюдаемое YFC-соединение при нулевом ceiling получает `BLOCKED`; неизвестная или неполная steady-state topology получает `UNKNOWN`. `observed_non_yfc` и фазовые `other_connections` добавляются один раз. Если pooler известен, фаза должна содержать положительный отдельно подтверждённый PostgreSQL backend cap и источник этого cap. Для `session` cap не может быть ниже raw session demand; для `transaction` cap — это именно максимальная PostgreSQL backend capacity, а не число занятых сейчас соединений. Raw client ceiling и backend cap не складываются повторно.

До расчёта preflight проверяет inventory contract. `topology.process_groups` содержит каждую возможную process group с `true`/`false`, а `topology.rollout_phases` — каждую применимую фазу с `true`/`false`; подтверждённая фаза `steady-state` обязательна для reconciliation observed YFC connections. Все группы с `true` должны присутствовать в `processes` каждой применимой фазы; неактивная группа записывается с репликами `0`. Отсутствие ключа не означает нулевую нагрузку. Применимая, но отсутствующая фаза, пустой process inventory и незадекларированная группа дают `UNKNOWN`/`BLOCKED`. Фиксированный список backend/worker/migration/setup в модели не зашит: collector должен описать фактический вариант topology и явно отметить отсутствующие элементы.

Синтетический пример для repository defaults (`C=30`, только для тестов):

| Фаза | Процессы | App maximum | Дополнение | Итог до внешних сессий |
|---|---|---:|---:|---:|
| steady state | 1 backend + 1 worker | `2C = 60` | 0 | 60 |
| candidate overlap | 2 backend + 1 worker | `3C = 90` | 0 | 90 |
| unexpected all slots | 2 backend + 2 worker | `4C = 120` | 0 | 120 |
| backup | 1 backend + 1 worker | 60 | 1 explicit backup connection | 61 |
| migration | 1 backend + 1 worker + 1 NullPool migration | 60 | 1 | 61 |
| setup/seed | 1 backend + 1 worker + 1 setup engine | 60 | 30 explicit setup ceiling | 90 |
| rollback | 2 backend + 1 worker | 90 | 0 | 90 |

Это воспроизводимый synthetic calculation, а не production evidence. Финальный safety margin намеренно не задан.

## Preflight contract

Модуль: `scripts/connection_budget_preflight.py`.

Он принимает только обезличенный JSON с разделами `postgres`, `pools`, `phases`, `topology`, `pooler`, `safety_headroom_connections`, `safety_headroom_source` и `evidence`. В `evidence` проверяются `environment=production`, `synthetic=false`, `source`, timezone-aware `captured_at` и положительный `max_age_seconds`, но эти поля не доказывают происхождение сами по себе. `model_from_mapping` не устанавливает доверие к runtime evidence; standalone JSON без внешнего trusted collector получает `BLOCKED` с кодом `runtime_provenance_untrusted`, даже если текстовые поля выглядят production-like. CLI печатает только статус, числовые результаты, имена фаз/process groups и безопасные диагностические коды. `DATABASE_URL`, password и другие секреты не читаются и не печатаются. `read_postgres_snapshot(connection)` выполняет только один `SELECT` по `current_setting(...)` и `pg_stat_activity`; attribution и provenance передаются отдельными sanitized fields.

Пример запуска в изолированном окружении:

```text
python scripts/connection_budget_preflight.py --config sanitized-connection-budget.json --json
```

Exit codes: `0=PASS`, `1=BLOCKED`, `2=UNKNOWN`. У CLI нет `--bypass`/`--ignore-unknown`; неизвестный или malformed critical input не может стать PASS.

Минимальная форма synthetic input:

```json
{
  "postgres": {
    "server_version_major": 16,
    "max_connections": 200,
    "superuser_reserved_connections": 3,
    "reserved_connections": 2,
    "current_connections": 20,
    "observed_yfc_connections": 8,
    "observed_non_yfc_connections": 12,
    "unattributed_connections": 0
  },
  "pooler": {"mode": "none"},
  "pools": {
    "backend": {"pool_type": "queue", "pool_size": 10, "max_overflow": 20, "pool_timeout_seconds": 30},
    "worker": {"pool_type": "queue", "pool_size": 10, "max_overflow": 20, "pool_timeout_seconds": 30},
    "migration": {"pool_type": "null", "connection_ceiling": 1, "connection_ceiling_source": "backend/alembic/env.py"},
    "setup": {"pool_type": "special", "connection_ceiling": 30, "connection_ceiling_source": "backend/setup-entrypoint.sh"}
  },
  "topology": {
    "process_groups": {"backend": true, "worker": true, "migration": true, "setup": true},
    "rollout_phases": {
      "steady-state": true,
      "candidate-overlap": true,
      "unexpected-all-slots": true,
      "migration": true,
      "setup-seed": true,
      "rollback": true
    }
  },
  "phases": [
    {"name": "steady-state", "processes": {"backend": 1, "worker": 1, "migration": 0, "setup": 0}, "other_connections": 0},
    {"name": "candidate-overlap", "processes": {"backend": 2, "worker": 1, "migration": 0, "setup": 0}, "other_connections": 0},
    {"name": "unexpected-all-slots", "processes": {"backend": 2, "worker": 2, "migration": 0, "setup": 0}, "other_connections": 0},
    {"name": "migration", "processes": {"backend": 1, "worker": 1, "migration": 1, "setup": 0}, "other_connections": 0},
    {"name": "setup-seed", "processes": {"backend": 1, "worker": 1, "migration": 0, "setup": 1}, "other_connections": 0},
    {"name": "rollback", "processes": {"backend": 2, "worker": 1, "migration": 0, "setup": 0}, "other_connections": 0}
  ],
  "safety_headroom_connections": 10,
  "safety_headroom_source": "synthetic-test-input",
  "evidence": {
    "environment": "test",
    "source": "synthetic-test-fixture",
    "captured_at": "2026-10-19T00:00:00+00:00",
    "max_age_seconds": 86400,
    "synthetic": true
  }
}
```

The `10` and the full topology above are test data, not an approved production threshold or production evidence. `evaluate(..., require_runtime_evidence=False)` can be used in unit tests for the mathematical calculation; the CLI/default production path rejects synthetic, stale, missing or non-production evidence and blocks standalone provenance declarations from authorizing a production PASS.

## Trusted runtime collector Phase B

Модуль `scripts/trusted_runtime_collector.py` реализует следующий bounded flow:

```text
release/.deployment-sha + docker compose config/ps
        ↓ docker inspect exact IDs: allowlisted env + image revision labels
        ↓
effective topology snapshot (allowlisted values only)
        ↓ docker exec exact active container ID
read-only PostgreSQL child snapshot (no URL leaves the container)
        ↓ exact context + freshness validation
private trusted model → existing evaluator → sanitized verdict
```

Host-side collection требует explicit release directory и запускает только `docker compose config`, `docker compose ps --all`, `docker inspect` и `docker exec` для exact ID выбранного running backend с bounded timeout/output. Collector не выполняет `restart`, `up`, `down`, `pull`, dump, DDL/DML или изменение конфигурации. Пример owner-authorized dry run:

```text
python scripts/trusted_runtime_collector.py collect --release-path /srv/yfc/releases/<sha> --json
```

Команда пока не запускалась на production. Child mode подключается к уже настроенному `DATABASE_URL` внутри активного backend-контейнера с `connect_timeout=5`, `statement_timeout=5s`, `lock_timeout=1s`, `default_transaction_read_only=on` и фиксированным `application_name`. В stdout попадают только числовые поля, timestamp и безопасный статус. Ошибка child процесса не переносит текст исключения, URL, password или token в host output.

PostgreSQL query агрегирует `pg_stat_activity` без query text, client address, username или user data. Нужна роль с `pg_read_all_stats`, но не superuser; `is_superuser=true`, отсутствие visibility, mismatch counts или malformed row дают fail-closed. Точное разбиение: известные YFC application names, пустая/неизвестная метка (`unattributed`) и остальные non-YFC. `observed_non_yfc` включает `unattributed` как conservative upper bound, а сам `unattributed > 0` переводит production evaluation в `UNKNOWN`; такие sessions никогда не становятся YFC.

В effective topology учитываются backend/worker base и blue/green services, active upstream, configured и фактически running instances всех slots, runtime pool values, Alembic `NullPool`, setup/seed ceiling, backup connection, worker handoff, rollback, single-slot и pooler. OCI revision каждого running application container обязан совпадать с release SHA; runtime marker/pool drift блокируется, а несовпадающие экземпляры одного service дают `UNKNOWN`. Дополнительный service с `DATABASE_URL`, отсутствующая worker pair, missing application marker, contradictory pool values или неизвестный pooler не превращаются в ноль: они дают `UNKNOWN`/`BLOCKED`.

### Trust boundary и provenance policy

`model_from_mapping()` не принимает поле `trusted`, `synthetic=false`, source, environment или headroom как доказательство. Private in-process token создаётся только в collector module после проверки:

- production environment;
- immutable release marker и full OCI revision labels, совпадающие с release SHA;
- allowlisted runtime environment и exact container ID для связи inspected image с child snapshot;
- одинаковый hashed host context и revision tuple для topology и PostgreSQL observations;
- capture timestamps в доверенном clock-skew window;
- trusted 300-second max age, не значение из входного JSON;
- complete topology, pool, phase и attribution fields.

Любая подмена sanitized JSON, изменение revision, runtime environment drift, mixed host/environment, stale/future snapshot, partial child output, missing policy, timeout или collector crash остаются без private token и не могут дать production `PASS`. Private token не является криптографической аттестацией: код с теми же host/container полномочиями может подделать in-process boundary. Host fingerprint — только усечённый SHA-256 hostname; raw hostname и container IDs не входят в verdict.

### Safety headroom

В collector policy окончательный headroom по умолчанию отсутствует. Это намеренно даёт `safety_headroom_unknown`, пока владелец не подтвердит число и источник. После получения runtime data можно показать:

```text
observed usable capacity = max_connections - superuser_reserved - reserved
maximum measured slack = usable - worst_case_required
```

`maximum measured slack` — верхняя граница наблюдаемого запаса, а не рекомендация. Рекомендация должна отдельно учитывать кратковременные spikes, внешние consumers, изменение replicas/pool size и confidence измерения; collector не фиксирует это решение самостоятельно.

## Подготовка read-only evidence

Следующие команды только подготовлены для owner-authorized host run. В этой задаче они не выполнялись.

1. Безопасно вывести только allowlisted numeric pool settings из production `.env`:

   ```text
   awk -F= '/^(DB_POOL_SIZE|DB_MAX_OVERFLOW|DB_POOL_TIMEOUT_SECONDS|DB_POOL_RECYCLE_SECONDS)=/{print $1"="$2}' .env
   ```

2. Снять PostgreSQL numeric capacity/current occupancy без дампа:

   ```text
   psql "$DATABASE_URL" -XAtc "SELECT current_setting('server_version_num')::int, current_setting('max_connections')::int, current_setting('superuser_reserved_connections')::int, NULLIF(current_setting('reserved_connections', true), '')::int, (SELECT count(*)::int FROM pg_stat_activity);"
   ```

   `DATABASE_URL` здесь — уже настроенный secret environment, он не должен попадать в shell output, artifact или report. На PostgreSQL <16 пустое `reserved_connections` преобразуется в version-aware zero fallback; на PostgreSQL 16+ его отсутствие — `UNKNOWN`.

3. Зафиксировать фактические Compose service instances/process counts read-only командами `docker compose ps --format json`, `docker compose config --services` и `docker compose top` для backend/worker и blue/green services. Не считать логические Compose service definitions фактическими replicas.

4. Для attribution получить только counts по заранее owner-approved allowlist role/application identifiers. Нельзя угадывать владельца соединения по похожему имени или складывать весь `pg_stat_activity` поверх projected YFC cap. Любая неразрешённая/неатрибутированная сессия остаётся в `UNKNOWN`.

Операционный collector должен записать в sanitized JSON только числовые значения и фиксированные метаданные: version, max/reserved values, current/YFC/non-YFC counts, effective pool settings, process counts, phase overlap, migration/setup/other additions, pooler mode/caps, topology applicability, snapshot provenance/freshness и источник safety headroom. Connection strings, usernames, SQL dumps и personal data запрещены. Поля `synthetic=false`, `environment`, `source` и `captured_at` — декларации, а не независимое доказательство. Будущий deployment adapter должен получать данные от trusted collector-а, проверять источник и owner-approved freshness bound до передачи evidence в preflight; standalone JSON этого trust boundary не закрывает.

## Точка подключения rollout gate

После отдельного owner approval future adapter должен получить effective sanitized input от `trusted_runtime_collector.py`, проверить источник, freshness bound и rendered steady-state topology, затем выполнить:

```text
connection_budget_preflight -> backup -> migration -> candidate_start -> traffic_switch -> consumer_handoff
```

Для rollback preflight должен быть отдельным predecessor до запуска rollback candidate. Для single-slot он должен быть до backup/migration и до запуска восстановленного application process. `scripts/connection_budget_preflight.py` уже проверяет этот ordering contract, но в текущем PR этот контракт дополнительно реализован в deployment helper; код не активирован на production и требует exact-head CI и owner-reviewed live verification.

`PASS` продолжает существующий stage. `BLOCKED` или `UNKNOWN` завершают stage с non-zero result до backup/migration/candidate mutation. PostgreSQL unreachable, missing attribution и missing headroom не являются warning. Incident recovery не использует CLI bypass: owner-authorized native GitHub `workflow_dispatch` rollback/repair/verify path остаётся отдельным разрешением и не превращает failed preflight в `PASS`.

Точки подключения в текущем Draft PR: `connection_budget_preflight` перед штатным `preflight`/pull/backup/migration/candidate в `deploy()`, перед первым start rollback-backend в `rollback()` и перед legacy provenance/reclaim/backup/migration в `single_slot_deploy()`. Это **код подготовленной блокировки**, а не production activation: до проверенной ёмкости, числового запаса и корректного bootstrap установленный код может законно остановить развёртывание. `.github/workflows/deploy.yml` не изменён.

## Rollback и failure behavior

- Preflight failure до service mutation: stop, no backup/migration/candidate launch.
- PostgreSQL query failure: `UNKNOWN`, sanitized diagnostic only.
- Known insufficient capacity or invalid numeric input: `BLOCKED`.
- Failure after a future gate has passed remains under the existing rollout helper's rollback/evidence contract; this PR не меняет его behavior.
- A rollback action must have its own phase budget. It cannot inherit a successful deploy verdict from another topology.

## Owner approvals before activation

## Phase B readiness matrix

| Критерий | Статус | Доказательство | Что осталось |
|---|---|---|---|
| Trusted collector | `IMPLEMENTED` | bounded host/child flow in `scripts/trusted_runtime_collector.py`; 300-second trusted policy | owner-authorized live dry run |
| PostgreSQL snapshot | `IMPLEMENTED` | read-only aggregate query, PG16 reserved slots, non-superuser visibility check | real production values and role verification |
| Effective topology | `IMPLEMENTED` | rendered Compose, `ps --all`, exact `docker inspect` env/OCI labels, configured-vs-running replica inventory, pool/phase inventory | production rendered output |
| Attribution | `IMPLEMENTED` / `NOT_PROVEN` | fixed application markers, runtime marker drift block and unattributed fail-closed path | live `pg_stat_activity` attribution |
| Safety headroom | `NOT_PROVEN` | evaluator requires explicit positive source; default collector policy leaves it unset | owner-approved number and rationale |
| Synthetic regressions | `PASS` | targeted pytest: 317 passed, включая runtime drift, scaled candidate/all-slots, revision, host/timestamp, trust and timeout negatives | exact-head CI |
| Deployment gate integration | `IMPLEMENTED_IN_DRAFT / NOT_ACTIVATED` | `scripts/zero_downtime_deploy.py`: guarded three rollout paths, missing-margin/BLOCKED/UNKNOWN tests | exact-head CI, trusted live dry run, owner-approved numeric margin, safe bootstrap before merge |
| Production dry run | `NOT_VERIFIED` | no SSH/DB/docker production command executed | authorized read-only dry run |
| Owner approval | `BLOCKED` | no Phase C activation decision in this request | explicit release/gate approval |

## Owner approvals before activation

Нужны отдельные подтверждения:

1. exact sanitized production snapshot: effective pool values, PostgreSQL version/max/reserved, pooler, process/replica topology, current attribution and phase overlap;
2. owner-approved numeric safety headroom and its rationale/source;
3. security review of the deployment-boundary integration;
4. independently verified authorized dry run with the real rendered topology;
5. separate release approval before any production deployment.

До этих approvals verdict для production остаётся `UNKNOWN`/`BLOCKED`; standalone provenance и отсутствие production integration — `BLOCKED`, недостающие runtime facts — `UNKNOWN`. Production rollout не разрешён. Production environment changes in this PR: `no`. Code/config changes that would affect the next image/runtime are present and must be deployed only through the existing protected release path; `deployment_scope.py` must report `deploy_required=true` for this diff.

## Phase C: подключение блокирующей проверки (Draft, 20.10.2026)

В этом Draft PR интегрирована `_trusted_connection_budget_preflight` в три маршрута `scripts/zero_downtime_deploy.py`. Он получает доверенную `CollectorPolicy` и вызывает `collect_runtime_snapshot` в одном процессе. Verdict `PASS` и присутствие требуемого SHA — необходимые условия продолжения; любые `UNKNOWN`, `BLOCKED`, исключение сборщика или несогласованная версия прерывают операцию до защищённых действий. Диагностика ошибок фиксирована, без исходных сообщений драйвера или URL базы данных. Событие сохраняется в stage history обычного развёртывания.

Запас задаётся **только явно**, положительным целым `DEPLOY_DB_SAFETY_HEADROOM_CONNECTIONS` из штатного production deployment environment; значения по умолчанию **нет**, предел числа — 999999. Это источник конфигурации, **не свидетельство согласования владельцем**. Значение нельзя считать утверждённым, пока владелец не согласует число по реальным показателям и оно не будет внесено в защищённую конфигурацию. Пока оно отсутствует, gate обязан прерывать развёртывание. Тесты закрывают отсутствие, 0, отрицательное, дробное, нечисловое, слишком большое значение, ошибку сборщика, `UNKNOWN`/`BLOCKED`, несовпадение SHA и успешный фиктивный `PASS` без каких-либо production-запросов.

**Критическое ограничение первого обновления:** текущие действующие контейнеры могут не содержать `scripts.trusted_runtime_collector postgres-child` и новые `application_name` markers. В этом случае до появления поддерживаемого приложения нельзя получить trusted `PASS`; встроенный gate обоснованно блокирует даже первое применение Phase B. Не сливать данный Draft PR в `master` до отдельного, документированного и безопасно проверенного bootstrap-пути, который не требует приписывать legacy-контейнеру несуществующие данные. Возврат к обычному workflow при неизвестной ёмкости запрещён; экстренное восстановление допускается только по отдельно авторизованному и проверяемому пути, не меняющему вердикт gate задним числом.

Существующие автоматические тесты развёртывания используют mock collector PASS исключительно внутри CI. Окончательный production verdict, фактические подключённые процессы и резервные слоты **НЕ ИЗМЕРЕНЫ**. CI после этих изменений должен быть проверен на *финальном* SHA и он не заменяет независимый runtime dry run.

### Обязательная ранняя проверка (перед записью конфигурации)

`scripts/deploy_production.sh` теперь вызывает
`python3 scripts/zero_downtime_deploy.py capacity-check TARGET_SHA BASE_URL PUBLIC_BASE_URL`
**до** `configure_production_auth.py`, других редакторов `.env`, настройки
журнала и запуска Compose. Проверка не выполняет самостоятельных записей и
требует того же доверенного наблюдения, что и повторная проверка внутри
`deploy()`. Её отказ останавливает shell с ненулевым кодом без изменения
настроек. Проверка rollback производится перед запуском rollback backend;
single-slot — перед освобождением пространства, остановкой сервисов и
резервным копированием. Контракт порядка закреплён в
`tests/test_deployment_contract.py`.

`tests/test_zero_downtime_deploy.py` также создаёт чувствительную тестовую
`.env` сразу с правами `0600`, проверяя сохранение ограничений доступа.
Это исправление замечания CodeQL, не исключение из сканера.

**Эти изменения не означают, что собраны данные production или запущен
реальный preflight.** Отсутствует безопасный bootstrap к старому активному
образу и утверждённое число `DEPLOY_DB_SAFETY_HEADROOM_CONNECTIONS`.
`NOT_PROVEN` остаётся блокирующим результатом.
