# V11-DB-01 Phase B: trusted PostgreSQL connection budget

Документ описывает trusted runtime collector и fail-closed rollout gate для #848. Gate подключён к production wrapper и deployment helper, но это ещё не production activation: live snapshot, owner-approved safety headroom, dry run и release approval не подтверждены.

## Последовательный выпуск: решение владельца 21.10.2026

Этот раздел задаёт новый single-slot maintenance contract. Остальные разделы сохраняют
полную консервативную модель online/blue-green collector; её фазы не отключены.
Решение [в #848](https://github.com/MikeMoore1337/your-fitness-coach/issues/848#issuecomment-6323551623)
разрешает разработку и изолированные тесты. **Production release BLOCKED** до отдельных
решений по окну, резерву, credentials/ACL, независимому dry run и выпуску.

### Исполняемые барьеры

`scripts/sequential_deploy_safety.py` работает только внутри существующего single-slot
helper. GitHub Actions сохраняет `concurrency.group=production`, `cancel-in-progress=false`.
Нового controller, lock, очереди или recovery database нет. Источник фактов — Docker и PG.

1. Wrapper выбирает `capacity-check-single-slot` до изменения конфигурации. Проверяются
   точный SHA immutable bundle, отдельный observer, полный Docker inventory и DB sessions.
   После OCI-проверки старого и нового digest потолок определяется offline engine probe
   обоих image с действующим `.env`, затем сверяется с rendered и running overrides.
   Одна QueuePool engine на процесс; неизвестные/unlimited pools и multiprocess блокируют путь.
2. До backup и stop у всех существующих legacy/blue/green consumers отключается Docker
   restart policy. Новый backend/worker/bot создаются с `YFC_CONSUMER_RESTART_POLICY=no`.
   Это native Docker fencing от автоматического перезапуска, включая перезапуск Docker/хоста;
   существующий stopped standby также не может сам подняться. Все проверки повторно сверяют
   policy и точное множество работающих consumers. Любой лишний slot/setup/replica запрещён.
3. Worker → bot → backend получают bounded graceful stop. Проверяется именно исходный
   container ID и `exited 0`; маркер в логе не заменяет чистое завершение. Timeout/SIGKILL,
   неожиданное исчезновение или неизвестный drain запрещают candidate и автоматический rollback.
4. Независимый PG observer дважды подтверждает отсутствие application sessions. Затем
   readiness → Alembic → seed выполняются отдельными одноразовыми процессами; перед и после
   каждого есть свежий barrier. После него последовательно запускаются backend → worker → bot,
   со свежей проверкой бюджета и предыдущего runtime перед каждым запуском.
5. Бюджет каждого reachable этапа, включая backup, readiness, migration, seed, steady state
   и все этапы rollback, пересчитывается при каждой проверке. Учитываются reserved slots,
   один observer и явный положительный резерв; значения по умолчанию для резерва нет.
   Application sessions заменяются проверенным ceiling, не прибавляются к нему повторно.
   Все другие clients без проверяемого runtime owner **блокируют** путь, даже если они имеют
   красивый application_name. Поэтому observed E=0 из прежнего аудита не становится допущением
   следующего выпуска; никакой ручной external allowlist здесь нет.
6. DB snapshot → socket join → новый DB snapshot и Docker inventory должны согласовываться.
   Изменившиеся PID/backend_start/client tuples/container start/restart, неизвестные DB consumer
   или пропавший observer останавливают следующий этап. Снимок из файла не принимается.

При measured cap30+30, observer1 и **только предложенном M=10**: backup=72/97,
steady/worker/rollback=71/97, setup/readiness=41/97, migration=12/97. Это модель при
положительных барьерах, а не production PASS. Candidate overlap, dual consumers и
legacy+blue+green не объявлены безопасными: они **запрещены runtime inventory/fencing**;
online collector по-прежнему считает их полные потолки и не выдаёт PASS на 97 слотах.

### Защищённый observer после остановки backend

Нужны host Python 3.14 (версия проекта), существующий `/usr/bin/psql`, отдельный libpq service `yfc_observer` и два файла:
`/etc/yfc/observer/pg_service.conf`, `/etc/yfc/observer/pgpass`.
Код **не** создаёт роли/файлы, не вызывает `sudo`, не повышает привилегии и не
включает observer автоматически. Production provision требует отдельного approval.

**Контракт доступа без привилегий root при запуске:**

| Путь | Владелец и группа | POSIX mode | Почему |
|---|---|---|---|
| Родительские каталоги `/`, `/etc`, `/etc/yfc` | root (UID 0) | directory, без group/other write; SSH deploy должен иметь traversal | Защита от подмены пути |
| `/etc/yfc/observer/` | `root:<primary-group-of-yfc-deploy>` | `0750` | `yfc-deploy` может войти, но не менять содержимое каталога |
| `pg_service.conf` | `root:<primary-group-of-yfc-deploy>` | `0640` | Конфигурация без секрета доступна только оператору/его группе |
| `pgpass` | `yfc-deploy:<primary-group-of-yfc-deploy>` | `0600` | Парольный файл читается effective user; **libpq игнорирует** файлы с любым group/other access |

Каждый файл должен быть обычным (не symlink) с ровно одной жёсткой ссылкой.
Python выполняется с effective UID пользователя `yfc-deploy` и его primary GID
(без `sudo`/root); отсутствие `getpwnam`, несоответствие UID/GID, неверный
owner/mode/type/nlink или невозможность открыть файлы с `O_NOFOLLOW` вызывает
fail-closed. Проверяется неизменность файла между `lstat` и `fstat`.
Все эти условия — часть **предлагаемой provision policy**, а не измеренные
права на production. Если фактический deployment account/группа отличаются,
не ослаблять проверку: сначала представить отдельное разрешённое решение.

Причина изменения относительно первоначальных `root:root 0700/0600`: SSH
workflows запускают helper под `yfc-deploy`, которому не доступны root-only
файлы. Простое изменение `pgpass` на mode `0640` тоже недопустимо, поскольку
libpq игнорирует доступный группе файл паролей. При provisioning секрет
передаётся по утверждённому закрытому каналу, без записи в Git, stdout,
командную строку или CI artifacts; ротация производится атомарно с сохранением
owner/mode.

**Отдельный обязательный read-only preflight production перед активацией:**
`id -u`, `id -g` и `getent passwd yfc-deploy` под текущим SSH account,
sanitized `namei -l` / `stat` только для owner/mode/type на путях выше,
`test -r` файлов из того же effective account и факт наличия `psql`.
Не печатать содержимое файлов, libpq credentials, окружение или SQL queries.
До provision ещё несуществующих файлов read-only audit должен вернуть
`NOT_PROVISIONED`, а не PASS. Не создавать роль/ACL, менять runtime или
выполнять подключение к production PostgreSQL без следующего owner approval.

План SQL для **отдельно авторизованного** provisioning (здесь не выполняется):

```sql
CREATE ROLE yfc_observer LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 1;
GRANT CONNECT ON DATABASE <application_database> TO yfc_observer;
GRANT pg_read_all_stats TO yfc_observer;
ALTER ROLE yfc_observer SET default_transaction_read_only = on;
```

Пароль задаётся отдельно утверждённым secret-процессом, не SQL в Git/argv/log.

### Одноразовая активация наблюдателя (отдельно авторизованный этап #848)

Скрипт [`scripts/provision_pg_observer.py`](../scripts/provision_pg_observer.py) создан для
**настоящего YFC VPS**, а не для Hermes BRC Docker sandbox. Он требует root,
но вносит только явно разрешённые изменения: создаёт PostgreSQL-роль
`yfc_observer`, каталог `/etc/yfc/observer` и два защищённых файла
`pg_service.conf`/`pgpass`. Ни контейнеры, ни приложение, ни миграции,
ни параметры PostgreSQL, ни правила firewall, ни `.env` не меняются.

Перед запуском уполномоченный оператор должен подтвердить сохранность
актуального соединения к VPS, отсутствие конфликтующей observer-роли и
наличие одного running Docker Compose `fit-mini-app/db` с публикацией
`127.0.0.1:5432`. Из root SSH-сессии без `exit` и `set -e`:

```bash
apt-get update
apt-cache policy postgresql-client-16 postgresql-client-18
# Install the available distro client only (not the PostgreSQL server).
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends postgresql-client-16
# On Ubuntu 26.04 "resolute" the default repositories have client 18,
# while client 16 is absent. Use instead, after verifying apt-cache policy:
# DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends postgresql-client-18
/usr/bin/psql --version
```

**Ubuntu 26.04.1 LTS (resolute/amd64), подтверждённый production host 23.10.2026:**
штатный APT не нашёл `postgresql-client-16`; клиент `postgresql-client-18` установлен
без PostgreSQL server upgrade. `psql 18.6` успешно выполнил используемые
read-only запросы к PostgreSQL server 16 и прошёл one-time observer verifier.
Команду установки версии 16 выше **не повторять** на resolute; вместо неё
использовать закомментированную строку с версией 18. Не подключать PGDG
репозиторий без отдельной необходимости и решения владельца.

Установщик **не** устанавливает пакеты автоматически, а проверяет
`/usr/bin/psql`. Скачивать его следует только с **полным 40-значным
SHA Git-коммита** в URL `raw.githubusercontent.com` и после скачивания
сверить отдельно зафиксированный SHA256 файла. Никогда не использовать
`curl | bash`, непроверенную текущую ветку или stdin с паролем в чате.
После сверки выполнять **как отдельные команды**, не завершая SSH:

```bash
python3 /root/provision_pg_observer_issue848.py --check
python3 /root/provision_pg_observer_issue848.py --apply
```

Финальные pinned commit/SHA256 предоставляет PR review evidence.
`--check` не создаёт роль/файлы, но читает Docker/PG metadata.
`--apply` создаёт случайный 256-битный пароль локально; SQL получает
только SCRAM-SHA-256 verifier через stdin (не исходный пароль и не argv);
`pgpass` создаётся с UID/GID настоящего deploy account и mode `0600`.
Проверка после установки вызывает **host psql от `yfc-deploy`** в чистом
окружении с read-only/timeouts и отвергает привилегированную роль,
лишние права на application tables, опасные memberships и невалидный
connection limit. При ошибке код сообщает только безопасную метку:
никаких паролей, содержимого файлов и SQL с деталями клиента не печатает.

Это строго **one-shot**, не updater: если каталог или роль уже существуют,
скрипт отказывается перезаписывать их и не вращает секреты. Если роль создана,
а проверка не пройдена, остановить работы и сохранить состояние для
отдельного разбора; не делать автоматический DROP/RESTART.
Успешная роль наблюдателя сама по себе **не снимает** release gates:
нужны отрицательные и положительные host-ACL проверки, approved
M/E/maintenance window, live stage barriers, #1148 provenance, #849 restore
и отдельное разрешение владельца на merge/deploy.

В service-файле: TCP endpoint установленного PG, `dbname`, `user=yfc_observer`,
`connect_timeout=5`, `passfile=/etc/yfc/observer/pgpass`; никаких application credentials.
`pg_hba`/host ACL разрешают только этот управляемый канал. Database container, mount и
application credentials для наблюдения менять не требуется. В CLI очищается ambient env,
фиксируются read-only/timeouts и проверяются фактические server address/port/database,
PG16, stats visibility, connection limit1, отсутствие superuser/опасных memberships и
прав на application tables. Значения credentials, SQL query text и client tuples не
попадают в evidence. Исчезновение psql, файла, доступа или PG даёт отказ, без fallback
на superuser, работающий backend или сохранённый JSON.

`pg_read_all_stats` открывает sensitive metadata, включая чужие query texts: роль и файл
доступны только доверенному deploy operator. Скрипт выбирает только идентичности клиентов
и агрегаты, не SQL text/username. Это не разрешение выдавать роль в production.

### Доверенная legacy attribution и граница защиты

При пустом application_name используются текущие client address+port, ESTABLISHED TCP
socket и его inode с владеющим процессом **внутри конкретного inspected контейнера**.
Probe работает от штатного container user; нет дополнительных capabilities и host /proc
scan. Проверяются один основной Python/uvicorn process и direct `db:5432` engine.
Неизвестные клиенты, pooler, IPv6-only/иная топология, inaccessible /proc или ambiguity
блокируют операцию. Исторические forensic tuples не загружаются; изменение маркеров
задним числом невозможно. Это machine bootstrap для текущих legacy sessions.

Fencing покрывает native restart policies и один authorized Actions writer. Root/Docker
administrator всё ещё способен вручную создать/start контейнер или изменить ACL между
проверкой и запуском. Поэтому отсутствие параллельных privileged writers и ограничение
DB/network credentials — обязательное production условие; этот код не заявляет защиты
от злонамеренного root. Новый неизвестный consumer блокируется при ближайшем barrier.
Действующая superuser application role из прежнего измерения требует отдельного security
решения; отдельная observer role не исправляет её права автоматически.

### Отказ и rollback

После подтверждённого drain, успешных migration/seed и отказа приложения helper сначала
чисто останавливает target, заново доказывает release sessions, повторяет schema gate,
проверяет бюджет и поднимает старые immutable images: backend → smoke → worker → bot.
После успешного smoke возвращается прежний last-successful-revision, даже если отказ
произошёл сразу после записи нового SHA.
Ошибка любого шага прекращает следующие запуски. Прерванный rollback оставляет
`manual intervention required`; target автоматически вслед за ним не запускается.

SIGKILL процесса не обрабатывается Python: Docker restart=no остаётся, уже запущенный
one-shot может ещё работать. Следующее выполнение проверяет живой inventory/PG с нуля и
не может миновать orphaned setup, незавершённый drain или частично восстановленный runtime.
Нет resume-token и автоматического продолжения по summary.json. Partial `DEPLOY_REPAIR_MODE`
блокируется до runtime mutation: этот путь требует полного проверенного baseline. Для восстановления нужны
отдельное разрешение владельца и свежие проверки; нельзя просто повторно включить все slots.

После ошибки миграции/seed автоматического app rollback нет: частичный schema/data outcome
не доказан. `check_online_migrations.py` остаётся обязательным до downtime и перед app rollback:
деструктивные/неописанные изменения блокируются. **App rollback не запускает downgrade и не
восстанавливает backup.** Данные после миграции сохраняются. Для каждого будущего диапазона
revisions нужны isolated PG16 migration и проверка старого приложения на полученной схеме;
статический AST gate и green CI не заменяют этот release-specific результат и gate #849.

Restart=no сохраняется и после успешного maintenance/rollback. После финального smoke
оператор должен отдельно разрешить возврат штатной restart policy **только у трёх проверенных
активных legacy контейнеров**, с новым inventory и подтверждением отсутствия slots/setup.
До этого crash приведёт к остановке сервиса: это осознанная граница fail-closed, а не HA.

### Оставшиеся production решения и замер окна

**env change required: yes** для будущей активации: утверждённый
`DEPLOY_DB_SAFETY_HEADROOM_CONNECTIONS` (без repository default); existing one-shot
`DEPLOY_SINGLE_SLOT_CONFIRMED_SHA=<exact merged release SHA>`; выбранный Actions single-slot
mode. `YFC_CONSUMER_RESTART_POLICY=no` передаётся только в env создаваемых consumers,
не записывается helper в production `.env`. Новая observer role/secret/service/ACL и наличие
psql требуют отдельного разрешения. Pool sizes/max_connections не меняются.

До разрешения операций необходимо: утвердить M и окно/максимум простоя; provision observer;
решить application role security и вернуть успешный provenance gate отдельно от #848;
подтвердить единственного privileged writer; выполнить разрешённый независимый dry run
на exact release с fresh topology/attribution/pools и всеми negative cases; проверить
schema compatibility старого release, #849 backup/recovery и rollback; согласовать rearm
policy; получить отдельное разрешение на stop/migration/restart/deploy.

Оценка окна = сумма измеренных graceful stop + release barriers + readiness/migration/seed
+ backend/worker/bot readiness + smoke; отдельно измеряется failed rollout + rollback.
StageRecord сохраняет start/end/duration по этапам. Лимиты drain/readiness — timeout bounds,
не прогноз длительности миграции. До staging rehearsal фактическая длительность **NO_DATA**;
численное окно и время production не выбраны. Полный production dry run не выполнен.

### Изолированная проверка реализации, 21.10.2026

- Linux / Python 3.14 / psycopg 3.3.6: **352 целевых pytest PASS**, включая три реальных
  PG16 теста роли, read-only и удерживаемой транзакции; Ruff/format и deployment/image/workflow
  contracts PASS. Fault injection проверяет обычный путь, stuck/нечистый stop, unknown consumer,
  missing observer, unreleased clients, capacity denial, interruption и fail-fast rollback.
- Отдельная Docker/PG16 лаборатория: legacy socket join без application_name, graceful stop,
  disappearance sessions при остановленном backend и restart=no — PASS. Реальные leaked SQL
  client, утрата stats privileges, сверхбюджет и SIGKILL — DENIED; автоперезапуска после SIGKILL нет.
  На Windows psql transport перенесён адаптером в отдельный DB container; production host psql,
  защищённые host files/ACL и реальные процессы production этим не проверены.
- Новая схема развёрнута с нуля до `0130_workout_rest_sessions` в отдельной PG16. Исходники
  прежней измеренной production revision `aba8275040578e69fe597bea350351cf4351392f` прошли readiness,
  dev login и authorized `/me` на этой схеме. Использован локальный runtime image с примонтированным
  старым source; это не проверка точного production rollback digest и не всех V11 journeys.
- Production аудит не повторялся; stop/migration/credentials/roles/env/pools/restart в production
  не выполнялись. Полный release rehearsal и длительность сервисного окна остаются NOT_VERIFIED.

## Что подтверждено в репозитории

Проверено относительно актуального `origin/master`, смёрженного в ветку PR 20.10.2026:

| Область | Подтверждённый факт | Статус |
|---|---|---|
| SQLAlchemy backend/worker | PostgreSQL engine использует `pool_pre_ping=true`, `pool_size=DB_POOL_SIZE`, `max_overflow=DB_MAX_OVERFLOW`, `pool_timeout=DB_POOL_TIMEOUT_SECONDS`, `pool_recycle=DB_POOL_RECYCLE_SECONDS` | `VERIFIED` |
| Локальный статический baseline | `10 + 20 = 30` соединений на один pooled engine; `pool_timeout=30 s` | `VERIFIED` как настройки репозитория |
| Alembic | `backend/alembic/env.py` использует `NullPool` и передаёт фиксированный `application_name=yfc-migration`; отдельный migration connection — последовательный этап | `VERIFIED` по исходнику и regression test |
| Setup | readiness, Alembic и seed запускаются последовательно в `backend/setup-entrypoint.sh`; seed импортирует обычный application engine | `VERIFIED` по исходнику |
| Compose topology | legacy `backend`/`worker` и blue/green `backend-*`/`worker-*`; bot — отдельные consumers без найденного SQLAlchemy engine | `VERIFIED` по исходнику |
| Rollout order | существующий helper имеет `preflight`, `backup`, `migration`, candidate start, consumer handoff, observation и rollback/single-slot paths | `VERIFIED` по исходнику |
| Existing capacity audit | текущий manual audit снимает только часть host/PostgreSQL metrics и не считает rollout budget с reserved slots и attribution | `VERIFIED` по workflow |
| Trusted runtime collector | `scripts/trusted_runtime_collector.py` связывает rendered Compose, running container IDs, allowlisted runtime env, matching OCI revision labels, live Caddy admin config и read-only PostgreSQL child snapshot из exact active container | `IMPLEMENTED`, live run `NOT_VERIFIED` |
| Connection attribution | backend/worker/setup/Alembic получают фиксированные `application_name`; collector session считается non-YFC, runtime marker drift, неизвестные sessions и unattributed connections не становятся YFC | `IMPLEMENTED`, production attribution `NOT_PROVEN` |

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
- active backend выбирается по проверенному `active_slot` и фактической live-конфигурации
  Caddy Admin API; stale `YFC_ACTIVE_UPSTREAM` из rendered Compose не выбирает контейнер;
- неизвестный/повреждённый маркер, несогласованное состояние, неожиданная
  работающая OCI revision — **не PASS**;
- если на синем/зелёном хосте остаётся работающий контейнер прежней rollback
  версии, не равной active SHA, сборщик консервативно блокирует сбор. Для
  сложной смешанной топологии требуется отдельное доказательство и точное
  соответствие service→revision, а не молчаливое расширение allowlist.

Это **исправление исходного контракта по коду**, подтверждаемое отрицательными
и положительными тестами, не подтверждение production capacity и не
автоматическое разрешение релиза. Collector считает собственную read-only
сессию как non-YFC, требует отдельно утверждённый положительный safety headroom
и реальные trusted runtime/DB значения. Legacy runtime может не содержать
модуль `postgres-child` или новые application_name markers: совместимый probe
запускается внутри проверенного active-контейнера, но отсутствие полномочий,
live gateway state, атрибуции или topology закономерно блокирует gate. Никакого
silent bootstrap или fail-open path не добавлялось.

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

Операционный collector должен записать в sanitized JSON только числовые значения и фиксированные метаданные: version, max/reserved values, current/YFC/non-YFC counts, effective pool settings, process counts, phase overlap, migration/setup/other additions, pooler mode/caps, topology applicability, snapshot provenance/freshness и источник safety headroom. Connection strings, usernames, SQL dumps и personal data запрещены. Поля `synthetic=false`, `environment`, `source` и `captured_at` — декларации, а не независимое доказательство. Deployment gate получает данные только от trusted collector-а и проверяет источник и freshness bound до передачи evidence в preflight; standalone JSON этого trust boundary не закрывает.

## Точка подключения rollout gate

`trusted_runtime_collector.py` получает effective sanitized input, проверяет источник,
freshness bound, active slot, live Caddy gateway и rendered/runtime topology, затем
передаёт модель в gate перед защищёнными этапами:

```text
connection_budget_preflight -> backup -> migration -> candidate_start -> traffic_switch -> consumer_handoff
```

Для rollback preflight является отдельным predecessor до запуска rollback candidate.
Для single-slot он стоит до backup/migration и запуска восстановленного application
process. Legacy bootstrap и idempotent paths также проходят тот же gate до первой
production mutation. `scripts/connection_budget_preflight.py` проверяет ordering
contract, а deployment helper и wrapper вызывают trusted collector; production
activation и live verification остаются отдельными owner gates.

`PASS` продолжает существующий stage. `BLOCKED` или `UNKNOWN` завершают stage с non-zero result до backup/migration/candidate mutation. PostgreSQL unreachable, missing attribution и missing headroom не являются warning. Incident recovery не использует CLI bypass: owner-authorized native GitHub `workflow_dispatch` rollback/repair/verify path остаётся отдельным разрешением и не превращает failed preflight в `PASS`.

Точки подключения в текущем Draft PR: `connection_budget_preflight` перед штатным
`preflight`/pull/backup/migration/candidate в `deploy()`, перед первым start
rollback-backend в `rollback()`, перед legacy provenance/reclaim в
`single_slot_deploy()`, а также до service inspection в `bootstrap_state()` и до
idempotent gateway/marker operations. `deploy_production.sh` выполняет отдельный
read-only `capacity-check` до записи production-конфигурации. Это **код
подготовленной блокировки**, а не production activation: до проверенной ёмкости,
числового запаса и live verification установленный код может законно остановить
развёртывание.

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
| Effective topology | `IMPLEMENTED` | rendered Compose, `ps --all`, exact `docker inspect` env/OCI labels, live Caddy admin config, configured-vs-running replica inventory, pool/phase inventory | production rendered output |
| Attribution | `IMPLEMENTED` / `NOT_PROVEN` | fixed application markers, runtime marker drift block and unattributed fail-closed path | live `pg_stat_activity` attribution |
| Safety headroom | `NOT_PROVEN` | evaluator requires explicit positive source; default collector policy leaves it unset | owner-approved number and rationale |
| Synthetic regressions | `PASS` | focused post-fix pytest: 153 passed; three Windows-specific baseline tests were excluded from this local run; exact-head CI on the final PR head passed | trusted live dry run |
| Deployment gate integration | `IMPLEMENTED_IN_DRAFT / NOT_ACTIVATED` | `scripts/zero_downtime_deploy.py`: trusted gate covers rollout, rollback, bootstrap and idempotent paths; wrapper performs early read-only check; exact-head CI on the final PR head passed | trusted live dry run, owner-approved numeric margin |
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

В этом Draft PR интегрирована `_trusted_connection_budget_preflight` в маршруты `scripts/zero_downtime_deploy.py`: rollout, rollback, legacy bootstrap и оба idempotent входа. Он получает доверенную `CollectorPolicy` и вызывает `collect_runtime_snapshot` в одном процессе. Verdict `PASS` и **строгое совпадение SHA пакета-кандидата** с запрошенным релизом — необходимые условия продолжения; любые `UNKNOWN`, `BLOCKED`, исключение сборщика или несогласованная версия прерывают операцию до защищённых действий. Диагностика ошибок фиксирована, без исходных сообщений драйвера или URL базы данных. Wrapper выполняет тот же read-only check до записи production-конфигурации.

Запас задаётся **только явно**, положительным целым `DEPLOY_DB_SAFETY_HEADROOM_CONNECTIONS` из штатного production deployment environment; значения по умолчанию **нет**, предел числа — 999999. Это источник конфигурации, **не свидетельство согласования владельцем**. Значение нельзя считать утверждённым, пока владелец не согласует число по реальным показателям и оно не будет внесено в защищённую конфигурацию. Пока оно отсутствует, gate обязан прерывать развёртывание. Тесты закрывают отсутствие, 0, отрицательное, дробное, нечисловое, слишком большое значение, ошибку сборщика, `UNKNOWN`/`BLOCKED`, несовпадение SHA и успешный фиктивный `PASS` без каких-либо production-запросов.

**Первое обновление:** старый образ может не содержать `postgres-child` и новые маркеры. Технически подготовлен совместимый read-only запуск исходника из проверенного пакета кандидата внутри active-контейнера, найденного по state и live Caddy Admin API (см. ниже). Это не гарантирует `PASS`: полномочия роли, актуальная маркировка сессий, фактический запас соединений и topology остаются неизвестны до реального dry run. Никакого fail-open обхода нет.

Существующие автоматические тесты развёртывания используют mock collector PASS исключительно внутри CI. Окончательный production verdict, фактические подключённые процессы и резервные слоты **НЕ ИЗМЕРЕНЫ**. Exact-head CI на финальном PR head прошёл и не заменяет независимый runtime dry run.

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
реальный preflight.** Bootstrap теперь сам защищён тем же gate до service
inspection и первой мутации; всё ещё отсутствуют live snapshot и утверждённое
число `DEPLOY_DB_SAFETY_HEADROOM_CONNECTIONS`. `NOT_PROVEN` остаётся
блокирующим результатом.

### Проверка SHA кандидата без ложного совпадения с active

До проверки CI обнаружен случай, когда список `context.revisions` содержал сразу SHA работающей версии и кандидата. Обычное условие `target_revision in revisions` могло разрешить неверный пакет, если запрошенный SHA равнялся **активному**, но не SHA в `.deployment-sha` кандидата. Теперь `RuntimeCollection.candidate_revision` сохраняется отдельно и gate требует `evidence.candidate_revision == config.target_revision`; отсутствие поля не допускает `PASS`. Отдельный регрессионный тест проверяет несовпадающий кандидат при наличии `target_revision` среди активных OCI labels. Это исправление не заменяет проверку подлинности образов, подтверждение PostgreSQL capacity или production dry run.

### Безопасный первый запуск на существующем backend (подготовлен в PR)

Для первого обновления теперь не требуется наличие
`scripts.trusted_runtime_collector` **внутри старого образа**. Сборщик на
хосте сначала проверяет текущую версию по state/OCI labels, находит active
backend по verified `active_slot` и live Caddy Admin API, а затем выполняет команду
`docker exec <проверенный active-container> python -c <проверенный source>`.
Источник `scripts/trusted_legacy_pg_snapshot.py` берётся из неподменённого
пакета релиза кандидата с ограничением 16 КиБ. Он выполняет **один**
read-only SELECT внутри существующего backend-контейнера с его обычной
`DATABASE_URL`; URL базы не выводится, не передаётся в аргументах или
в переменных процесса сборщика на хосте. Новый файл не копируется в
контейнер и не меняет его файловую систему. Код сам ограничивает SQL
`default_transaction_read_only`, `statement_timeout`, `lock_timeout`,
выполняет сверку суммарных счетчиков и требует право
`pg_read_all_stats` **у не-суперпользователя**. Неуспешный процесс возвращает
только `{"status":"BLOCKED"}` и ненулевой код; состояние БД не изменяется.

Вывод передаётся в существующий `_parse_child_snapshot`; provenance
работающего образа, отдельный SHA кандидата, topology, source, freshness
и весь расчет ёмкости по фазам **остаются обязательными**. Временный
bootstrap не обходит сравнение версий и не добавляет `PASS` по умолчанию.

Ограничения не скрыты: старая версия backend должна иметь Python и
`psycopg`, рабочую `DATABASE_URL`, а текущая прикладная роль —
`pg_read_all_stats` без статуса superuser. Эти факты на production
не проверены. Отсутствующее право не выдается автоматически;
ручная настройка ролей требует отдельного согласования и процедуры.
Агрегаты `pg_stat_activity` нужно сопоставить с фактическим старым
`application_name`: без разрешимой атрибуции результат останется
`UNKNOWN`/`BLOCKED`. Маркеры состояния активной версии и OCI labels
также должны реально совпадать.

**Статус:** код и тесты подготовлены в Draft PR; CI финального SHA и
независимый read-only dry run на production обязательны, и до них
снимать ограничение на merge/deploy нельзя. Это инженерное решение
первого bootstrap, **не доказательство реальной ёмкости PostgreSQL**.


## Клиентский учёт #848 (2026-10-21)

`pg_stat_activity` содержит строки серверных процессов, включая фоновые. Поэтому простой
`count(*)` завышает число обычных клиентов; пустой `application_name` фонового процесса
создаёт ложную неопределённую атрибуцию.
Источник: [PostgreSQL pg_stat_activity](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ACTIVITY-VIEW).

Цепочка: SQL → legacy/runtime parser → trusted child parser → `PostgresCapacity` → `evaluate`
→ blocking deployment preflight. В #1122 legacy и runtime используют общий `snapshot_sql`.
Все связанные счётчики получаются одним проходом с `FILTER (WHERE backend_type = 'client backend' ...)`.
В #1147 `WITH activity AS MATERIALIZED` формирует `current_connections`, `session_counts`
и backend diagnostics из одного агрегата. Изменение числа сессий между запросами не смешивает
клиентские значения. Публичный child JSON не меняется; неверные формы отклоняются.

| Тип | Учёт |
|---|---|
| `client backend` | Клиентский слот, атрибуция по точному marker |
| `autovacuum launcher`, `autovacuum worker`, `background writer`, `checkpointer`, `archiver`, `walwriter`, `logical replication launcher` | Известные встроенные процессы, не клиентские слоты |
| `parallel worker` | Worker pool; клиент-лидер уже учтён, дополнительного клиентского слота нет |
| `walsender`, `walreceiver`, `logical replication worker` | Неподтверждённая replication topology: BLOCKED |
| `startup`, `standalone backend`, generic `background worker`, extension-defined, NULL или неизвестный тип | Неподтверждённый resource/runtime contract: BLOCKED |

`max_wal_senders` ограничивает отправителей WAL отдельно. Replication slots — постоянные объекты,
а не клиентские соединения. Logical/parallel workers используют `max_worker_processes` и частные
worker limits. Эти процессы нельзя добавлять к клиентским слотам «для перестраховки».
См. [replication](https://www.postgresql.org/docs/16/runtime-config-replication.html),
[kernel resources](https://www.postgresql.org/docs/16/kernel-resources.html) и
[worker limits](https://www.postgresql.org/docs/16/runtime-config-resource.html#RUNTIME-CONFIG-RESOURCE-ASYNC-BEHAVIOR).
Connection gate не доказывает достаточность CPU/RAM/I/O. Replication и extension workers
отклоняются до отдельного измерения и документирования их ресурсов и rollout applicability.

YFC markers: только `yfc-backend`, `yfc-worker`, `yfc-setup`, `yfc-migration`.
Другой непустой marker, включая collector, — external client. NULL, пустая строка или пробелы
— unattributed client. Marker — клиентская декларация, не криптографическое доказательство;
OCI/topology/provenance guards сохраняются.

Проверяемые инварианты:

- `client_total = yfc_client + external_client + unattributed_client`;
- `observed_non_yfc_connections = external_client + unattributed_client`;
- `current_connections = observed_yfc_connections + observed_non_yfc_connections`;
- `0 <= unattributed_connections <= observed_non_yfc_connections`;
- projected phase usage = YFC ceilings + inclusive non-YFC + explicit phase consumers;
  unattributed и текущие YFC-сессии повторно не прибавляются;
- `usable = max_connections - superuser_reserved_connections - reserved_connections`;
  PG15 допускает отсутствие `reserved_connections`, PG16+ требует значение;
- malformed/partial/contradictory statistics и недостаточные права не дают PASS;
  unattributed production clients дают UNKNOWN/BLOCKED.

Тесты выполняют сам SQL на фиксированных activity rows и в PostgreSQL integration profile:
нули, клиентская/фоновая смесь, специальные типы, schema/permissions, reconciliation,
изменение числа клиентов, положительный и недостаточный headroom. Эти синтетические данные
не доказывают production capacity. #1147 остаётся owner-only, read-only, no-deploy;
`POSTGRES_BUDGET_VERDICT=NOT_VERIFIED` сохраняется.

Production metrics: PARTIAL; production safety: BLOCKED. [Owner-only audit 39555570075](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39555570075)
на master `b85ec32af5395860104c8332315a39be53851303` получил PostgreSQL 16,
`max_connections=100`, reserved slots `3+0`, 12 клиентских соединений и 5 фоновых
процессов. У 11 клиентов отсутствует атрибуция; workflow завершился с
`POSTGRES_ATTRIBUTION_INCOMPLETE`, без production mutations. Измеренные лимиты дают
`usable=97` и 85 свободных non-reserved клиентских слотов в этом снимке. Это не
утверждённый safety headroom и не расчёт rollout phases; effective pools и число
процессов/реплик этим аудитом не подтверждены. [Полные результаты и ограничения](https://github.com/MikeMoore1337/your-fitness-coach/issues/848#issuecomment-6309649378).
Нужны разрешённый live read-only снимок с полной атрибуцией, реальные topology и role privileges, active/candidate
provenance, pooler/phase overlap, freshness, положительный owner-approved численный headroom
и независимый dry run. Merge и deploy не разрешены.
