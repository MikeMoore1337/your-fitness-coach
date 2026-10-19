# V11-REC-01: off-host backup и disaster recovery

Статус документа: Phase A реализована и смержена в protected master; Phase B/C:
BLOCKED_OWNER_FACTS / NOT_VERIFIED. Issue: [#849](https://github.com/MikeMoore1337/your-fitness-coach/issues/849).

Документ фиксирует контракт, локальную синтетическую проверку и runbook. Он не доказывает,
что независимая копия уже существует, что шифрование уже включено, или что восстановление на
чистом хосте уже выполнялось.

## 1. Принятый контур Phase A

Windows-ПК владельца периодически забирает архив с VPS по исходящему SSH/SFTP-соединению.
VPS не подключается к Windows-ПК. На VPS используется существующий
`scripts/db_maintenance.py`; Windows runner — `scripts/windows_backup_pull.ps1`.

Внешний SFTP-пользователь должен быть read-only и видеть только каталог off-host backup.
Парольная SSH-аутентификация запрещена: runner требует отдельный ключ и pinned
`known_hosts`. Параметр `StrictHostKeyChecking=yes` не допускает TOFU или использование
глобального `known_hosts`.

В Phase A намеренно не включены: production credentials, реальные дампы, Windows Task
Scheduler registration, изменение VPS, платное хранилище, WAL/PITR и восстановление с
production DNS. XML в `docs/operations/v11-rec-01-off-host-backup-recovery/windows-pull-task.example.xml` — только шаблон для
отдельного owner-approved шага.

## 2. Что именно считается опубликованной копией

Команда публикации создаёт архив, проверяет его через `pg_restore --list`, затем атомарно
пишет sidecar manifest и последним заменяет `index.json`. `index.json` — commit marker:
Windows runner принимает только архивы, перечисленные в нём, и не использует незавершённые
файлы из временного каталога.

```text
.artifacts/operations/backups/offhost/
  fitminiapp-<UTC>.dump
  fitminiapp-<UTC>.dump.manifest.json
  index.json
```

Manifest содержит имя, размер и SHA-256 архива, UTC timestamps, PostgreSQL major, Alembic
revision, coverage persistent state и application identity. Если release SHA или image
digests не переданы доверенным окружением, identity получает статус `not_provided`; это не
становится доказательством конкретной версии приложения. Index entry повторяет также
`published_at_utc`, чтобы проверка не теряла второй timestamp при передаче.

Для всех timestamp применяется UTC и фиксированная tolerance clock skew в 5 минут. Значение
дальше текущего времени более чем на 5 минут считается повреждённой metadata; timestamp в
пределах tolerance не превращает отрицательный возраст в `HEALTHY` — такой архив остаётся
`STALE` до наступления его времени.

`verification_status=format_verified_pg_restore_list` означает только читаемый custom-format
архив. `restore_status=not_run` остаётся до Phase C. `pg_restore --list` не является
доказательством успешного восстановления.

Публикатор повторно проверяет архив непосредственно перед публикацией, удерживает VPS lock,
проверяет каждый существующий index entry и только после успешной замены index выполняет
ротацию. Неудалённый старый файл не маскируется: незавершённая ротация возвращает ненулевой
код и требует ручного разбора.

## 3. Инвентаризация persistent state

| Объект | Phase A решение | Граница доказательства |
| --- | --- | --- |
| PostgreSQL relations | Включены в custom-format `pg_dump` | Нужна clean-host restore-проверка |
| `users.custom_avatar_image_bytes`, news images и account export bytes | Включены как binary columns PostgreSQL | Нужна проверка целостности после restore |
| named volume `postgres_data` | Восстанавливается логическим дампом, не копированием volume | WAL/PITR не входит в scope |
| `caddy_data` | Перевыпускается или пересоздаётся по отдельному runbook | Фактическая TLS/ACME recovery не проверена |
| `caddy_config`, `edge_config` | Восстанавливаются из версии приложения, Compose и approved environment | Untracked host mounts требуют owner inventory |
| `bot_polling_lock` | Эфемерный lock, создаётся заново при старте | Не является backup payload |
| Git и immutable application images | Источник versioned application files | Exact SHA/image digest должен быть зафиксирован при recovery |
| Secrets, SSH keys, TLS private keys | Исключены из dump и manifest | Отдельный approved источник и key recovery обязательны |

В репозитории нет утверждения о наличии или отсутствии независимой backup-копии. До
доказательства владельцем состояние: `NOT_PROVEN`.

## 4. Конфигурация Windows pull

Начальная форма: `docs/operations/v11-rec-01-off-host-backup-recovery/windows-pull.config.example.json`. Перед реальным запуском
владелец должен заменить placeholders, предоставить ключ, pinned host key и документ
восстановления ключа. Поле `encryption_at_rest` по умолчанию имеет
`mode=OWNER_APPROVAL_REQUIRED` и `approved=false`; Pull с ним завершается `CONFIG_INVALID`.

Runner:

- после успешного lock создаёт собственный временный `.incoming-<GUID>`, проверяет manifest,
  размер и SHA-256; другой процесс не создаёт, не очищает и не изменяет эту папку;
- при отказе в lock не пишет общий status/log и не выполняет cleanup; аварийно оставшийся
  temporary directory не является основанием удалять ранее подтверждённые копии;
- не перезаписывает существующую копию с другим digest;
- публикует архив, затем manifest; при ошибке удаляет только незавершённый новый archive;
- держит Windows file lock, поэтому параллельный Pull получает `LOCKED`;
- разделяет в status локальное состояние verified backups, `freshness_state`, последнюю
  попытку SSH pull, `last_sync_result` и время последнего получения новой независимой копии;
- сохраняет последнюю ошибку передачи в sanitized status и failure sidecar; сетевой сбой не
  превращает существующую валидную копию в `CORRUPTED`, но и не скрывается под `HEALTHY`;
- пишет только sanitized status/log: UTC, код и безопасное имя архива;
- считает локальный snapshot по фактическим файлам, а не по одному status-файлу;
- хранит минимум `minimum_valid_backups` валидных копий и не удаляет последнюю валидную;
- сообщает `STALE`, `MISSING` или `CORRUPTED`, даже если старый status-файл был healthy.

Планировщик должен быть настроен отдельно с `StartWhenAvailable`, повтором после пропущенного
запуска, `MultipleInstances=IgnoreNew` и ограничением времени. Ниже приведены exit codes,
которые должны быть видны в журнале/мониторинге:

| Код | Состояние |
| ---: | --- |
| 0 | `HEALTHY` / успешный Pull |
| 10 | `STALE` |
| 11 | `MISSING` — нет копии или remote object |
| 12 | `CORRUPTED` — manifest, размер или SHA не совпали |
| 20 | `HOST_KEY` |
| 21 | `AUTHENTICATION` |
| 22 | `NETWORK` / timeout |
| 23 | `DISK_FULL` |
| 24 | `LOCKED` |
| 25 | `CONFIG_INVALID`, включая отсутствие owner approval шифрования |
| 26 | `PROMOTE_FAILED`, включая незавершённую ротацию |
| 27 | `UNEXPECTED` |

## 5. Синтетическая проверка Phase A

Локальный self-test не подключается к VPS и не использует реальный dump:

```powershell
pwsh -NoProfile -File scripts/windows_backup_pull_selftest.ps1
```

Проверяются: успешный Pull, повторная идемпотентность, checksum mismatch с сохранением
валидной копии, восстановление orphan archive после сбоя между rename, отсутствующий manifest,
отказ pinned host key, stale status и блокировка до owner approval шифрования. Отдельная
concurrency regression удерживает первый Pull на незавершённом temporary download, запускает
второй Pull с `LOCKED`, сверяет неизменность temporary/status файлов и затем проверяет
успешное продолжение первого Pull. Дополнительно проверяются failed pull при свежей и stale
копии, восстановление после сбоя, отсутствие копий, повреждённая локальная копия и отказ
записи status. Python-тесты проверяют schema/manifest, fixed-time future timestamps,
`published_at_utc` в index, duplicate/path-safe index entries, повторную верификацию архива
публикатором и отказ от ротации при повреждённой старой записи. Отдельно проверяются
authentication failure, network timeout, low-disk margin, concurrent lock и malformed config.

Синтетический прогон не доказывает физический BitLocker/file encryption, реальную SFTP
аутентификацию, сетевой timeout, заполнение диска, VPS filesystem permissions, Task Scheduler,
production credentials, clean-host restore или production smoke. `encryption_at_rest.approved`
является только конфигурационным gate и никогда не заменяет проверку BitLocker/file encryption
и recovery key на физическом Windows-ПК. Проверка Task Scheduler вне интерактивного сеанса
также остаётся отдельным owner-approved Phase B тестом.

## 6. CI routing для Python backup-контракта

Текущая routing policy относила изменённые `scripts/` и root `tests/` к
`workflow-platform`, поэтому Python tests были skipped несмотря на изменение backup Python
implementation и tests. Узкое правило в `scripts/ci_contract.py` распознаёт backup Python
paths как Python surface; для текущего PR консервативный профиль — `cross-stack`, а
authoritative `python-tests` дополнительно собирает `tests/test_backup_manifest.py` и
`tests/test_db_maintenance.py`. Это исправление scope routing относится к общей задаче
детерминизма CI из открытого Issue #821; отдельный CI refactoring в рамках #849 не добавляется.

## 7. Runbook clean-host restore (Phase C, не выполнен)

Выполнять только по отдельному owner approval на непубличном чистом хосте. До восстановления
DNS и фоновые writer processes должны быть остановлены.

1. Зафиксировать дату, source archive, manifest, `archive_sha256`, PostgreSQL major, schema
   revision, release SHA и image digests. Скопировать архив во временный каталог clean host;
   sole local copy не удалять.
2. Установить тот же PostgreSQL major и exact application revision. Поднять только DB и
   необходимые сервисы без публичного маршрута.
3. Получить secrets, SSH keys, TLS private keys и environment из отдельно approved источника.
   Не извлекать их из dump, manifest или логов.
4. Сверить размер и SHA-256 с manifest. Затем проверить читаемость custom archive через
   `pg_restore --list`; failure останавливает runbook.
5. Создать целевую пустую БД, остановить writers и выполнить проверенный restore с
   `--clean --if-exists --no-owner --no-privileges --exit-on-error --single-transaction`.
   Не считать `pg_restore --list` заменой этому шагу.
6. Проверить Alembic revision и выполнить только согласованную миграционную последовательность
   до ожидаемого head. Миграции не должны запускаться до фиксации backup evidence.
7. Проверить binary columns, восстановить/перевыпустить Caddy state, применить approved
   environment и проверить версионные application files. Untracked host mounts сначала
   инвентаризировать, а не угадывать.
8. Выполнить integrity checks: health endpoint, подключение к БД, миграционный head, synthetic
   login/workout read path и отсутствие ошибок startup. Не использовать реальные пользовательские
   данные в опубликованном evidence.
9. Измерить фактические RPO/RTO, записать commands, exact revision, результаты smoke и все
   отклонения. Сейчас RPO/RTO: `UNKNOWN`, restore drill: `NOT_VERIFIED`.
10. DNS/traffic cutover и rollback — отдельная owner-authorized операция после успешных
    smoke checks. Она не входит в этот Phase A PR.

## 8. Гейты

| Фаза | Требование | Состояние в этом PR |
| --- | --- | --- |
| Phase A | Контракт, manifest/index, VPS helper, Windows pull, docs, synthetic checks | Реализовано; merged master revision 499b189d |
| Phase B | Owner decision по encryption/key custody/retention, независимый off-host объект, реальный SFTP pull, clean non-prod restore | BLOCKED_OWNER_FACTS / NOT_VERIFIED |
| Phase C | Production authorization, exact release, migrations, smoke, DNS/rollback evidence | NOT_VERIFIED + NOT_AUTHORIZED / не запускалось |

Issue #849 остаётся открытым до независимой off-host копии и clean-host restore evidence.

## 9. Фактическая перепроверка Phase B/C (2026-10-19)

Проверка выполнена read-only на доступном production VPS и на Windows-ПК владельца.
Production payload не скачивался на Windows, restore не выполнялся, а конфигурация VPS,
SSH/SFTP и Task Scheduler не изменялась. Поэтому ниже разделены подтверждённые локальные
факты и ещё не доказанные внешние гейты.

### 9.1 Подтверждённые факты

| Область | Факт | Граница доказательства |
| --- | --- | --- |
| Phase A | PR #1120 смержен в revision 499b189d; exact-head CI run 39218187131 имеет aggregate checks=success, deployment scope deploy_required=false | Это техническое завершение Phase A, не доказательство Phase B/C |
| VPS dump | В локальном backup-каталоге есть latest dump fitminiapp-20261018T172240Z.dump, 50 275 155 bytes; filename timestamp 2026-10-18 17:22:40Z; SHA-256 начинается с 0807d340 и заканчивается ccd4f2 | Это on-host copy, не независимый off-host объект |
| Dump format | pg_restore --list завершился кодом 0 в read-only/network-isolated контейнере | Проверена структура custom-format; restore не выполнялся |
| Database | PostgreSQL 16.0.15; размер базы около 80 MB; pg_is_in_recovery=false; Alembic head 0130_workout_rest_sessions | Это snapshot production DB, не clean-host recovery |
| Publication metadata | В backup-каталоге не найдены index.json и manifest sidecar для текущих dump-файлов | Публикатор/index contract в текущем каталоге фактически не подтверждён |
| Scheduling | YFC backup timer и Windows target task в проверенной инвентаризации отсутствуют | Отсутствие найденного задания не является доказательством настроенной периодической доставки |
| Windows client | PowerShell 7.6.6 и OpenSSH client 9.5.6.2 доступны; наблюдалось около 524.6 GB свободного места на C: и 197.9 GB на D: | Это capability/space check, не доказательство успешного pull |
| Windows target | Предусмотренный backup-каталог и YFC Scheduled Task не обнаружены | Конкретный target и schedule owner ещё не выбраны/подтверждены |

Backup-каталог содержит также secrets-likely файл .env. Его содержимое не читалось и не
передавалось. До любого SFTP-предоставления нужно отдельно исключить secrets из export surface,
проверить права и получить owner/security решение по хранению и ротации.

### 9.2 SFTP и encryption gates

Read-only inventory не подтвердил отдельный hardened read-only SFTP endpoint. Системный
пользователь с именем backup существует без login shell, но его фактический доступ к каталогу
не доказан. Эффективная конфигурация sshd при проверке не ограничивает этот путь требуемым
набором: password authentication и forwarding разрешены глобально, chroot/ForceCommand
отсутствуют. Каталог и dump-файлы принадлежат deploy-пользователю; отдельная SFTP-граница
владельцу не предоставлена.

Это состояние классифицировано как BLOCKED_OWNER_FACTS / FAILED для текущего security
контракта. SSH-аккаунт, authorized key, chroot, ForceCommand, allowlist и права не менялись.
Production identity не переиспользовалась для backup authorization.

Проверка BitLocker/file encryption на Windows не завершилась: CIM и manage-bde получили
access denied. Это NOT_VERIFIED, а не утверждение, что шифрование отсутствует. Recovery key
custody и проверка восстановления ключа также не предоставлены.

### 9.3 Сводный verdict

| Критерий | Состояние | Что требуется дальше |
| --- | --- | --- |
| Phase A contract, self-tests и exact-head CI | PASS | Ничего для Phase A; не смешивать с production activation |
| Независимый off-host object | NOT_PROVEN | Owner-approved target, privacy scope, real copy и независимая проверка digest |
| Physical encryption at rest | NOT_VERIFIED | Owner decision, device evidence и recovery-key test |
| Hardened read-only SFTP | BLOCKED_OWNER_FACTS / FAILED | Отдельная identity, key-only auth, chroot/ForceCommand, no forwarding и проверка прав |
| Windows scheduled pull | ABSENT / NOT_VERIFIED | Выбранный target, task policy, logs и успешный реальный pull |
| Clean-host restore | NOT_VERIFIED | Изолированный clean host, exact archive/revision, restore и integrity smoke |
| RPO/RTO | NOT_VERIFIED | Владелец должен задать targets и измерить их на drill |
| Merge, deploy, production restore, Issue close | NOT_AUTHORIZED | Нужны отдельные разрешения после выполнения обязательных gates |

Итог этой перепроверки: BLOCKED_OWNER_FACTS. Вердикт
PHASE_B_VERIFIED_PHASE_C_PENDING невозможен, потому что реальный независимый off-host
transfer ещё не выполнен и SFTP/encryption gates не закрыты.

### 9.4 Owner facts required before the next gate

До любой реальной передачи или изменения VPS нужно зафиксировать:

1. физическую страну/юрисдикцию storage, допустимые PII-категории и решение по privacy
   dependency #108;
2. retention/deletion policy и минимальный набор данных, который допустимо хранить off-host;
3. target RPO/RTO и критерии свежести;
4. выбранный encryption-at-rest режим, место хранения recovery key и отдельный тест его
   восстановления;
5. точный Windows target, backup identity, pinned host key и право на owner-approved
   изменение production SSH/SFTP;
6. clean-host isolation, synthetic/non-production credentials, блокировку внешних provider
   calls и exact release/image/database versions для restore drill;
7. расписание pull и подтверждённый способ доставки sanitized status/alert без публикации
   секретов или пользовательских данных.

Пока эти факты не получены, Phase B остаётся BLOCKED_OWNER_FACTS, Phase C не запускается,
а Issue #849 не закрывается. Этот документ не выдаёт разрешение на transfer, restore, merge
или deploy.
