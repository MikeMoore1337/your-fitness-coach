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
восстановления ключа. В связанном PR #1125 пример соответствует выбранной обычной папке:
`mode=none`, `approved=false`, `plaintext_risk_acknowledged=false`; Pull по умолчанию
завершается `CONFIG_INVALID`. Только JSON boolean `true` подтверждает риск plaintext;
это не подтверждение шифрования, ACL или разрешение передавать production-данные.
Папка должна быть отдельно подготовлена оператором. Retention — семь суток,
`minimum_valid_backups=2`: при длительном сбое две последние проверенные копии могут
оставаться старше семи суток. Такое исключение требует разбора, а не удаления последней копии.

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
powershell.exe -NoProfile -File scripts/windows_backup_pull_selftest.ps1
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
| Phase B | Решения storage/privacy/key custody, защищённый SFTP, расписания и независимая off-host копия | BLOCKED_OWNER_FACTS / NOT_VERIFIED |
| Phase C | Отдельно разрешённый clean-host restore из Windows-копии, invariants/application smoke, RPO/RTO | NOT_VERIFIED + NOT_AUTHORIZED для пользовательских данных |

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
   dependencies #707 и #711;
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

## 10. Phase B.1 — protected Windows storage и secure SFTP preparation (2026-10-19)

Этот addendum сохраняет предыдущий runbook и фиксирует только read-only/synthetic подготовку после выбора владельцем `D:\YFC-Backups`. Физическая юрисдикция VPS и Windows-ПК указана владельцем как Россия; независимая юридическая проверка не выполнялась. Production payload, production SSH, BitLocker, Task Scheduler и реальный SFTP endpoint не использовались.

### 10.1 Windows storage inventory

| Контроль | Наблюдение | Состояние |
| --- | --- | --- |
| `D:` | NTFS; total `1,000,203,087,872` bytes; free `195,896,864,768` bytes | `PASS` для read-only inventory |
| `D:\YFC-Backups` | Каталог отсутствует; существующее содержимое не изменялось; production payload не записывался | `NOT_CREATED` |
| ACL/owner | ACL целевого каталога отсутствует; текущая сессия не повышена; отдельная runner identity не выбрана; parent D: имеет более широкое наследование | `BLOCKED_OWNER_FACTS` |
| BitLocker | `Get-BitLockerVolume`, `manage-bde -status D:` и `fsutil` получили access denied | `NOT_VERIFIED` |
| Recovery key | Key material не читался; custody/escrow и recovery test не подтверждены | `NOT_VERIFIED` |
| Sync/share | Путь не находится под известным OneDrive root; процесс OneDrive и target reparse point не обнаружены; SMB query получил отказ | Частичная проверка; отсутствие всех sync/share механизмов не доказано |

Каталог и ACL намеренно не создавались: при отсутствии elevated owner/runner identity это могло бы закрепить неподходящее наследование. Ранее предложенный BitLocker-encrypted VHDX/container позднее отклонён владельцем в пользу обычной папки `D:\YFC-Backups`; отдельное шифрование тома/контейнера не внедряется. Подтверждено администратором Windows: `D:` FullyDecrypted, ProtectionStatus Off, EncryptionMethod None. Перед переносом реальных персональных данных остаётся открытым отдельное решение о допустимости хранения без шифрования.

### 10.2 SFTP security state и план hardening

Предыдущая read-only VPS-инвентаризация в разделе 9.2 не подтверждала dedicated hardened read-only endpoint: наблюдались глобальные password authentication/forwarding, отсутствие подтверждённых `chroot`/`ForceCommand` и secrets-likely `.env` в широком backup root. Содержимое `.env` не читалось. В этом addendum endpoint не подключался, SSH/VPS не изменялись, поэтому состояние остаётся `BLOCKED_OWNER_FACTS / NOT_VERIFIED`.

Owner-approved план, не применённый:

1. Выделить отдельный read-only export root, в котором разрешены только `index.json`, проверенные dump archives и их manifest-файлы. Не предоставлять весь каталог, где обнаружен `.env`; template path использовать только после allowlist-проверки, а при конфликте выбрать отдельный путь вида `/srv/yfc-sftp/yfc-backup-readonly/export`.
2. Использовать `yfc-backup-readonly` с public-key-only authentication, `nologin`, без TTY, shell, agent/X11/TCP forwarding и записи; ограничение выполнить через `Match User`, `ForceCommand internal-sftp` и chroot. Глобальные SSH defaults не менять.
3. На Windows использовать отдельный pinned `known_hosts` и `StrictHostKeyChecking=yes`; fingerprint подтвердить вне канала копирования. Remote path — абсолютный, без `..`.
4. Негативными тестами проверить `cd ..`, `get ../../...`, `put`, `rename`, доступ к соседним production paths и отсутствие `.env`/secrets. Успешный list/download не является доказательством restore.
5. До reload сохранить rollback copy drop-in, выполнить `sshd -t`, проверить действующую admin session, затем сделать reversible reload; при ошибке удалить только новый drop-in, повторить `sshd -t` и reload. Ни один пункт не выполнялся.

### 10.3 Task Scheduler readiness

В проверенной среде `schtasks /query` вернул `The network address is invalid`, служба `Schedule` не обнаружена, а production task не регистрировался. Доступ к отдельному backup private key и работа без интерактивного входа не подтверждены; существующие production-labeled identities не использовались.

После закрытия storage/SFTP gates нужен отдельный runner identity с доступом только к script/config/private key и `Log on as a batch job`. Existing template сохраняет `MultipleInstancesPolicy=IgnoreNew`, `StartWhenAvailable=true`, `RunOnlyIfNetworkAvailable=true`, bounded execution time, sanitized logs и exit codes. Reboot/catch-up и фактический scheduled pull остаются `NOT_VERIFIED`.

### 10.4 Synthetic evidence

В изолированном self-test без production payload: PowerShell 7 — 28/28, Windows PowerShell 5.1 — 28/28. Покрыты success/repeat/orphan recovery, checksum mismatch, missing/corrupt metadata, pinned host key/auth/network failures, low disk, atomic promotion, preservation of a valid previous copy, failed-pull recovery, status-write failure и concurrent Pull. Это не доказывает protocol-level SFTP authentication, физическое шифрование, Task Scheduler, production permissions или clean-host restore.

### 10.5 Owner proposals и remaining gates

| Решение | Предложение, не утверждение | Нужное подтверждение |
| --- | --- | --- |
| Cadence | **OWNER-APPROVED:** один новый архив в сутки. Опрос Windows каждый час остаётся предложением, а не утверждённым расписанием | Настройка и проверка реального VPS timer / Windows pull |
| Retention | **OWNER-APPROVED:** хранить архивы 7 дней (обычно 7 ежедневных копий). При очистке не удалять единственную последнюю проверенную копию в период сбоев; отдельно сигнализировать о нарушении retention | Проверить расписание очистки и корректность безопасного удаления после валидации новой копии |
| RPO | Не хуже 24 часов | Последний успешный pull и время публикации |
| RTO | Первичная цель 8 часов | Измеренный clean-host restore |
| Encryption | **OWNER DECISION:** VHDX/зашифрованные контейнеры отклонены; использовать обычную папку на незашифрованном `D:` | Физическая защита данных отсутствует; отдельный security/privacy gate для переноса production PII |
| Key recovery | Не применяется к отклонённому BitLocker/VHDX-контейнеру; ключи SSH/SFTP при этом остаются отдельным security gate | Нельзя объявлять `encryption-at-rest=PASS` при незашифрованном D: |
| Clean host | Disposable non-public Linux VM/host, независимый от VPS и Windows-ПК, matching PostgreSQL major/revision, без внешнего egress | Exact image/revision и approved non-production inputs |

До подтверждения elevated storage/ACL identity, recovery-key custody, отдельного hardened SFTP endpoint, non-interactive key access, scheduler checks и owner targets вердикт остаётся `BLOCKED_OWNER_FACTS`. `PHASE_B_1_READY_FOR_ACTIVATION` не заявляется.

### 10.6 Owner decisions — simplified backup policy (2026-10-19)

Владелец **утвердил только частоту создания и срок хранения**: один архив в день, retention 7 суток. Ранее предложенные 30 дней и вариант VHDX/container отвергнуты; обычная целевая папка — `D:\YFC-Backups`. Windows disk evidence: `D:` BitLocker Off / FullyDecrypted; Task Scheduler Running; задач YFC нет. Опрос Windows каждый час, RPO 24 часа и RTO 8 часов пока **не утверждены и не измерены**. Ежедневный архив сам по себе не доказывает RPO ≤24 ч при недоступном ПК. Безопасная очистка должна сохранять последнюю проверенную копию при сбое очередного создания/скачивания и показывать stale alert.

Отказ от шифрованного контейнера **не является доказательством** выполнения исходного encryption-at-rest acceptance #849: физическая защита отсутствует, и до передачи реальных персональных данных требуется отдельное privacy/security решение. Hardened SFTP, реальный dump/transfer, планировщик и isolated restore также не авторизованы этим решением. Состояние остаётся `BLOCKED_OWNER_FACTS`; PR остаётся Draft, Issue OPEN. Исправленный privacy/legal контекст: [#707](https://github.com/MikeMoore1337/your-fitness-coach/issues/707) и [#711](https://github.com/MikeMoore1337/your-fitness-coach/issues/711); GitHub Issue #108 — другая задача, не privacy gate.

## 11. Техническое завершение подготовки (2026-10-21)

Этот раздел уточняет текущие условия; инвентаризация 19 октября выше является исторической.
В этом прогоне VPS, реальная папка `D:\YFC-Backups`, SSH identities, ACL и Task Scheduler
не изменялись. Phase A не переоткрывалась. PR #1123 содержит инструкции и evidence,
PR #1125 — скрипт, конфигурацию и синтетические тесты. Оба синхронизированы с master;
точные финальные SHA и CI публикуются в этих PR и Issue #849.

### 11.1 Проверенные сценарии и ограничения

Self-test запускает дочерние процессы из того же `$PSHOME`, а не всегда выбирает pwsh.
Время свежих фикстур вычисляется от UTC начала теста. В PowerShell 5.1 исправлена потеря
native stderr при `ErrorActionPreference=Stop`: диагностика сохраняется, после чего ненулевой
exit code по-прежнему обрабатывается как ошибка. Параметры SSH исключают пользовательский
config, глобальные known_hosts и SSH agent; действуют выделенные identity и pinned known_hosts.

| Проверка | Доказательство | Ограничение |
| --- | --- | --- |
| Передача и повтор | Новый архив/manifest, SHA-256 и размер; повтор без повторной загрузки | Подменённый локальный transport, не реальный SFTP |
| Неверный SHA / усечённый архив | `CORRUPTED=12`, существующие dump/manifest неизменны побайтно | Не проверяет злонамеренный VPS, способный подменить и manifest |
| Недоступный VPS, host key, auth | `NETWORK=22`, `HOST_KEY=20`, `AUTHENTICATION=21`; предыдущая копия сохранена | Ошибки инжектируются; production endpoint не использован |
| Недостаток места | `DISK_FULL=23` до загрузки нового архива; старая копия сохранена | Синтетический запас места, не физическое заполнение диска |
| Выключенный ПК | Возраст копий увеличен без Pull; Status возвращает `STALE=10`, не переписывая receipt | Реальное выключение ПК и работа Scheduler не проверялись |
| Возврат после простоя | Загружается новая копия; после ротации остаются минимум две валидные | Нельзя восстановить пропущенные дни, уже удалённые на VPS |
| Семь суток | Удаляются пары старше семи суток; копия возрастом шесть суток остаётся | Две последние валидные пары сохраняются и за пределами срока |
| Блокировка/status/повреждение | Concurrency, failure sidecar, recovery, future timestamp, повреждённая локальная копия | Не доказывает физическую защиту устройства |

Полный синтетический self-test (38 сценариев в каждой оболочке) прошёл в PowerShell 7.6.6
и Windows PowerShell 5.1.26100.9444 на source PR #1125
[`faaa87245168feae82024c436631520734cced79`](https://github.com/MikeMoore1337/your-fitness-coach/commit/faaa87245168feae82024c436631520734cced79).
Целевые Python tests: 26 passed (`test_backup_manifest`, `test_db_maintenance`, `test_deployment_scope`).

Отдельно реально восстановлен **только синтетический** PostgreSQL 16 custom dump (2 934 bytes)
из Windows-файла в новый контейнер без сети, портов и production mounts, с DB в tmpfs.
Исходный контейнер удалён до восстановления. Проверены две строки, binary bytes `00017fff`,
sequence next value `2`, действующий FK и отказ restore усечённого архива в пустую БД.
Исходный Windows-файл после отрицательного теста сохранил SHA-256.
Image ID: `sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`.
SHA-256 синтетического архива: `cc6f94a2c270e844d92befeb4f34469b310e014450a25d8b3ac5d24bf914588e`.
Измерено 6,66 s от запуска синтетического source до проверки negative restore; это не RTO YFC.
Application smoke: `NOT_RUN`. `BACKUP_RECOVERY=NOT_PROVEN` для реальных данных.

### 11.2 Действия оператора после отдельного разрешения

На VPS требуется:

1. Подтвердить export allowlist и отдельный read-only SFTP endpoint из раздела 10.2.
   В chroot `remote_root` указывается относительно видимого корня, например `/export`,
   а не автоматически берётся host path из примера config. Проверить отрицательные операции.
2. Через существующий cron/systemd запускать **один backup в сутки**, с согласованным UTC
   временем. Штатная команда из корня checkout:

   ```sh
   python3 scripts/db_maintenance.py backup --publish-dir .artifacts/operations/backups/offhost --retain-published 7
   ```

   `--retain-published 7` — число архивов, не календарный TTL. При одном успешном архиве
   в сутки это семь последних успешных дней; сбои могут увеличить их возраст. Не добавлять
   отдельный `find -delete`/аварийную очистку: при ошибке dump/publication старый index и
   проверенные копии должны сохраниться. Повторный ручной backup в тот же день требует
   операторского решения, иначе count-based retention уменьшит окно простоя ПК.
3. Проверить свободное место для retained + нового/partial dump и metadata, права publisher,
   noninteractive Docker access, ненулевой exit при сбое и доставку sanitized оповещения.

На Windows требуется:

1. После privacy/security решения подготовить `D:\YFC-Backups` с ACL только для выбранной
   runner identity и разрешённых администраторов, исключить sync/share и reparse redirects.
   Не наследовать широкие права D: без проверки. Отдельно защитить scripts/config/keys от записи.
2. Подготовить выделенный SSH key и pinned host key, проверить доступ вне интерактивного сеанса.
   Config example из #1125 остаётся fail-closed; не ставить `approved=true` для обычной папки.
3. Согласовать интервал Pull: XML предлагает один час, но это **не** ещё одно создание архива
   и пока не утверждённое расписание. Проверить `StartWhenAvailable`, `IgnoreNew`, network
   availability, deadline и тип входа runner. S4U из шаблона не доказывает доступ к защищённым
   ключам/сетевым ресурсам. Зарегистрировать задачу только после разрешения и этих проверок.
4. Выполнить разрешённые проверки после reboot, пропущенного запуска и offline; проверить
   Task Scheduler exit result и независимую доставку `STALE`/ошибки. Выключенный ПК сам
   не отправит уведомление. Target freshness 36 h в config — технический default, не RPO SLA.
5. Подтвердить фактический digest/размер Windows-копии и получить отдельное разрешение на drill.

Production environment keys не меняются: `env change required: no`. Активация потребует
описанных host-side настроек; они не выполняются merge/deploy приложения автоматически.

### 11.3 Восстановление из Windows-архива в чистую изолированную PostgreSQL

Команды ниже — инструкция, **не разрешение** на использование пользовательских данных.
Для такого drill заранее согласовать dataset, владельца, RPO/RTO, срок удаления drill-копии,
изолированный хост и его защиту. Проверить образ и доверенность источника: restore выполняет
SQL из dump. Не использовать production Compose, `.env`, volumes, network или credentials.
Архив с Windows сохранять до успешного окончания всех проверок.

На авторизованной Windows-машине выбрать конкретный manifest, а не автоматически latest:

```powershell
$ErrorActionPreference = 'Stop'
$backupRoot = 'D:\YFC-Backups'
$manifestPath = Join-Path $backupRoot 'REPLACE_WITH_ARCHIVE.dump.manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.kind -ne 'yfc-backup-manifest' -or $manifest.schema_version -ne 1 -or
    $manifest.verification_status -ne 'format_verified_pg_restore_list' -or
    $manifest.archive_name -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,191}$' -or
    $manifest.manifest_name -ne "$($manifest.archive_name).manifest.json" -or
    [IO.Path]::GetFileName($manifestPath) -ne $manifest.manifest_name) { throw 'Invalid manifest' }
$archive = Join-Path $backupRoot $manifest.archive_name
if ((Get-Item -LiteralPath $archive).Length -ne [int64]$manifest.archive_size_bytes -or
    (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.archive_sha256) {
    throw 'Archive size/SHA-256 mismatch'
}
```

Подготовить заранее локальный PostgreSQL image того же major, что указан в manifest,
зафиксировать проверенный immutable digest и подставить его вместо placeholder. На хосте
должно хватать RAM для dump и развёрнутой БД; tmpfs может попасть в swap/pagefile, поэтому
защита host/pagefile также входит в отдельное решение. Для больших данных выбрать заранее
согласованное защищённое временное хранилище, не production volume и не новый VHDX.

```powershell
$image = 'postgres@sha256:REPLACE_WITH_VERIFIED_DIGEST'
docker image inspect $image
if ($LASTEXITCODE -ne 0) { throw 'Approved local image missing' }
$container = 'yfc-recovery-' + [guid]::NewGuid().ToString('N')
$timer = [Diagnostics.Stopwatch]::StartNew()
docker run --detach --pull=never --name $container --network=none `
    --tmpfs /var/lib/postgresql/data:rw --tmpfs /restore:rw,noexec,nosuid `
    -e POSTGRES_HOST_AUTH_METHOD=trust $image
if ($LASTEXITCODE -ne 0) { throw 'Isolated container failed to start' }
# No published ports, no network, no host binds; trust is limited to this disposable container.
$ready = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    docker exec $container pg_isready -U postgres
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $ready) { throw 'Isolated PostgreSQL not ready' }
docker cp $archive "${container}:/restore/backup.dump"
if ($LASTEXITCODE -ne 0) { throw 'Copy to isolated container failed' }
$isolatedDigest = docker exec $container sha256sum /restore/backup.dump
if ($LASTEXITCODE -ne 0 -or ($isolatedDigest -split '\s+')[0] -ne $manifest.archive_sha256) {
    throw 'Isolated copy checksum mismatch'
}
$serverVersion = docker exec $container psql -X -A -t -U postgres -d postgres -c 'SHOW server_version_num;'
if ($LASTEXITCODE -ne 0 -or [math]::Floor([int]$serverVersion / 10000) -ne [int]$manifest.database_major) {
    throw 'PostgreSQL major mismatch'
}
docker exec $container pg_restore --list /restore/backup.dump
if ($LASTEXITCODE -ne 0) { throw 'Archive not listable' }
docker exec $container createdb -U postgres --template=template0 yfc_recovery
if ($LASTEXITCODE -ne 0) { throw 'Empty database creation failed' }
docker exec $container pg_restore -U postgres --dbname=yfc_recovery --no-owner `
    --no-privileges --exit-on-error --single-transaction /restore/backup.dump
if ($LASTEXITCODE -ne 0) { throw 'Restore failed; keep Windows original' }
$revision = docker exec $container psql -X -A -t -v ON_ERROR_STOP=1 -U postgres -d yfc_recovery `
    -c 'SELECT version_num FROM alembic_version ORDER BY version_num;'
if ($LASTEXITCODE -ne 0 -or ($revision -join "`n").Trim() -ne $manifest.schema_revision) {
    throw 'Schema revision mismatch'
}
$timer.Stop()
$timer.Elapsed.TotalSeconds
```

В новой пустой БД не нужны `--clean` и `--create`: имя назначения задаётся явно, production
не затрагивается. Не передавать binary dump через PowerShell text pipeline. При ошибке
остановиться, не запускать приложение и не менять оригинал. Просмотр списка archive сам
по себе не проверяет строки.

После restore проверить заранее согласованные aggregate row counts, FK/unique constraints,
sequence values и binary-column digests, не печатая персональные записи. Сопоставить schema
revision с manifest **до** миграций, затем выполнять только согласованную последовательность.
Application smoke требует exact YFC revision/images и отдельного изолированного внутреннего
контура для backend/DB: без Telegram bot, background writers, публичных портов и provider
egress; test identity/dataset должны быть разрешены отдельно. Проверить `/health/ready`,
подключение к БД и согласованный login/workout read сценарий. DB-only тест это не заменяет.

Зафиксировать UTC начала/окончания, digest, image/release/schema, команды и коды, проверки
инвариантов, application smoke, отклонения. RTO отсчитывать от согласованного сценария потери
сервиса, включая получение ключей/образов и smoke; elapsed одного pg_restore — лишь часть.
RPO вычислять от момента сценария до `created_at_utc`, не времени скачивания; targets
нельзя выбирать после результата. В public evidence — только разрешённые агрегаты/статусы.
После проверки/фиксации результата удалить **только созданный** `$container` командой
`docker rm --force $container`, отдельно подтвердить удаление drill-копий по retention;
Windows original не удалять. DNS/cutover не входит в drill.

Опции сверены с [PostgreSQL 16 pg_restore](https://www.postgresql.org/docs/16/app-pgrestore.html)
и [pg_dump](https://www.postgresql.org/docs/16/app-pgdump.html). Реальный пользовательский
restore не выполнялся; `BACKUP_RECOVERY=PASS` не заявляется.

### 11.4 Незашифрованный диск: отдельное решение

Обычная папка и ACL не защищают dump при краже диска, offline-чтении или компрометации
администратора. Ранее зафиксированное `D: FullyDecrypted` не соответствует исходному
encryption-at-rest acceptance #849. Нужны решение по privacy/security #707/#711,
категориям данных, хранению в заявленной юрисдикции, доступу, удалению, custody и recovery keys.
Checkbox `plaintext_risk_acknowledged` не закрывает эти условия и не даёт права передачи.

Вариант для отдельного решения без оплаты/VHDX — шифровать **отдельные архивы** публичным
ключом, например [age](https://github.com/FiloSottile/age), до записи в Windows-папку.
Private decryption key хранить отдельно от диска с копиями; отдельно проверить его recovery.
Текущий publisher/Pull этот формат **не реализует**: `mode=file_encryption` является лишь
конфигурационным утверждением, не вызовом шифрования. Понадобятся согласованные изменения
publish/manifest, ciphertext checksum, rotation и decrypt/restore, включая защиту temporary
plaintext и swap. Простое шифрование уже скачанного `.dump` с последующим удалением
не доказывает, что plaintext не сохранился на незашифрованном SSD. Способ хранения не изменён.
