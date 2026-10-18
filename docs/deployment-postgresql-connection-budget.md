# PostgreSQL connection budget и fail-closed preflight

Документ описывает подготовленный для #848 расчёт и точку подключения rollout gate. В этой версии production deployment не вызывает preflight: фактическая PostgreSQL topology и итоговый safety headroom ещё не подтверждены владельцем.

## Что подтверждено в репозитории

Проверено на `origin/master` `7b755925ad03ea50215b9260b82e8c48cd506d22`:

| Область | Подтверждённый факт | Статус |
|---|---|---|
| SQLAlchemy backend/worker | PostgreSQL engine использует `pool_pre_ping=true`, `pool_size=DB_POOL_SIZE`, `max_overflow=DB_MAX_OVERFLOW`, `pool_timeout=DB_POOL_TIMEOUT_SECONDS`, `pool_recycle=DB_POOL_RECYCLE_SECONDS` | `VERIFIED` |
| Локальный статический baseline | `10 + 20 = 30` соединений на один pooled engine; `pool_timeout=30 s` | `VERIFIED` как настройки репозитория |
| Alembic | `backend/alembic/env.py` использует `NullPool`; отдельный migration connection — последовательный этап | `VERIFIED` по исходнику |
| Setup | readiness, Alembic и seed запускаются последовательно в `backend/setup-entrypoint.sh`; seed импортирует обычный application engine | `VERIFIED` по исходнику |
| Compose topology | legacy `backend`/`worker` и blue/green `backend-*`/`worker-*`; bot — отдельные consumers без найденного SQLAlchemy engine | `VERIFIED` по исходнику |
| Rollout order | существующий helper имеет `preflight`, `backup`, `migration`, candidate start, consumer handoff, observation и rollback/single-slot paths | `VERIFIED` по исходнику |
| Existing capacity audit | текущий manual audit снимает только часть host/PostgreSQL metrics и не считает rollout budget с reserved slots и attribution | `VERIFIED` по workflow |

`30` — это не production budget. Он не учитывает число процессов, blue/green overlap, pooler, внешние сессии и PostgreSQL reservations.

## Что остаётся `NO_DATA` / `NOT_PROVEN`

Эти значения нельзя заменять нулём или значением из `.env.example`:

| Параметр | Почему блокирует production PASS |
|---|---|
| Effective `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT_SECONDS` для каждого production process | render/runtime override не доказан |
| `max_connections`, `superuser_reserved_connections`, PostgreSQL 16+ `reserved_connections` | без них нельзя получить usable capacity |
| Pooler: наличие, режим и backend connection caps | application pool ceiling не равен PostgreSQL backend ceiling при pooler |
| Число backend/worker процессов и реплик в steady state | определяет static maximum |
| Точный candidate/blue-green overlap, all-slot overlap и rollback concurrency | разные фазы имеют разные worst cases |
| Migration, setup/seed, backup и прочие DB consumers | должны войти в фазу без двойного счёта |
| Current sessions и attribution YFC/non-YFC | current YFC sessions нельзя складывать поверх projected YFC cap; неатрибутированные сессии блокируют решение |
| Safety headroom | значение не фиксируется в коде; требуется owner-approved source и число |

В этой ветке нет production SSH/DB запроса, контейнеры не перезапускались, параметры PostgreSQL не менялись, secrets/connection strings/дампы не записывались.

## Модель

Для каждой pooled process group:

```text
process_ceiling = pool_size + max_overflow
```

Для `NullPool`/специального процесса используется только явно подтверждённый `connection_ceiling`. Missing pool fields не дают дефолт.

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

`observed_yfc` используется для проверки attribution, но не добавляется к `app_connections`: projected process caps уже описывают YFC worst case. `observed_non_yfc` и фазовые `other_connections` добавляются один раз. Если pooler известен, фаза должна содержать отдельно подтверждённый PostgreSQL backend cap; иначе verdict `UNKNOWN`.

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

Он принимает только обезличенный JSON с разделами `postgres`, `pools`, `phases`, `pooler`, `safety_headroom_connections` и `safety_headroom_source`. CLI печатает только статус, числовые результаты, имена фаз/process groups и безопасные диагностические коды. `DATABASE_URL`, password и другие секреты не читаются и не печатаются. `read_postgres_snapshot(connection)` выполняет только один `SELECT` по `current_setting(...)` и `pg_stat_activity`; attribution передаётся отдельными numeric fields.

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
    "observed_non_yfc_connections": 12
  },
  "pooler": {"mode": "none"},
  "pools": {
    "backend": {"pool_size": 10, "max_overflow": 20, "pool_timeout_seconds": 30},
    "worker": {"pool_size": 10, "max_overflow": 20, "pool_timeout_seconds": 30},
    "migration": {"connection_ceiling": 1},
    "setup": {"connection_ceiling": 30}
  },
  "phases": [
    {"name": "steady-state", "processes": {"backend": 1, "worker": 1}, "other_connections": 0},
    {"name": "candidate-overlap", "processes": {"backend": 2, "worker": 1}, "other_connections": 0},
    {"name": "unexpected-all-slots", "processes": {"backend": 2, "worker": 2}, "other_connections": 0},
    {"name": "migration", "processes": {"backend": 1, "worker": 1, "migration": 1}, "other_connections": 0},
    {"name": "setup-seed", "processes": {"backend": 1, "worker": 1, "setup": 1}, "other_connections": 0},
    {"name": "rollback", "processes": {"backend": 2, "worker": 1}, "other_connections": 0}
  ],
  "safety_headroom_connections": 10,
  "safety_headroom_source": "synthetic-test-input"
}
```

The `10` above is test data, not an approved production threshold.

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

Операционный collector должен записать в sanitized JSON только числа: version, max/reserved values, current/YFC/non-YFC counts, effective pool settings, process counts, phase overlap, migration/setup/other additions, pooler mode/caps и источник safety headroom. Connection strings, usernames, SQL dumps и personal data запрещены.

## Точка подключения rollout gate

После отдельного owner approval future adapter должен собрать effective sanitized input и выполнить:

```text
connection_budget_preflight -> backup -> migration -> candidate_start -> traffic_switch -> consumer_handoff
```

Для rollback preflight должен быть отдельным predecessor до запуска rollback candidate. Для single-slot он должен быть до backup/migration и до запуска восстановленного application process. `scripts/connection_budget_preflight.py` уже проверяет этот ordering contract, но текущий deployment helper намеренно не импортирует его.

`PASS` продолжает существующий stage. `BLOCKED` или `UNKNOWN` завершают stage с non-zero result до backup/migration/candidate mutation. PostgreSQL unreachable, missing attribution и missing headroom не являются warning. Incident recovery не использует CLI bypass: owner-authorized native GitHub `workflow_dispatch` rollback/repair/verify path остаётся отдельным разрешением и не превращает failed preflight в `PASS`.

## Rollback и failure behavior

- Preflight failure до service mutation: stop, no backup/migration/candidate launch.
- PostgreSQL query failure: `UNKNOWN`, sanitized diagnostic only.
- Known insufficient capacity or invalid numeric input: `BLOCKED`.
- Failure after a future gate has passed remains under the existing rollout helper's rollback/evidence contract; this PR не меняет его behavior.
- A rollback action must have its own phase budget. It cannot inherit a successful deploy verdict from another topology.

## Owner approvals before activation

Нужны отдельные подтверждения:

1. exact sanitized production snapshot: effective pool values, PostgreSQL version/max/reserved, pooler, process/replica topology, current attribution and phase overlap;
2. owner-approved numeric safety headroom and its rationale/source;
3. security review of the deployment-boundary integration;
4. independently verified authorized dry run with the real rendered topology;
5. separate release approval before any production deployment.

До этих approvals verdict для production остаётся `UNKNOWN`/`BLOCKED`; production rollout не разрешён. Runtime environment changes in this PR: `no`.
