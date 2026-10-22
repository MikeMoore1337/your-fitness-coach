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

Команда публикации создаёт dump в закрытом staging вне SFTP-каталога, проверяет его через
`pg_restore --list`, шифрует закреплённым age и переносит только готовый ciphertext. Затем
атомарно пишет sidecar manifest и последним заменяет `index.json`. `index.json` — commit marker:
Windows runner принимает только архивы, перечисленные в нём, и не использует незавершённые
файлы из временного каталога.

```text
.artifacts/operations/backups/offhost/
  fitminiapp-<UTC>.dump.age
  fitminiapp-<UTC>.dump.age.manifest.json
  index.json
```

Manifest/index v2 содержит `archive_format=age-v1`, `age_version=v1.3.2`, ожидаемый public
`recipient`, имя, размер и SHA-256 **ciphertext**, UTC timestamps, PostgreSQL major, Alembic
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
`mode=age`, `approved=false`, placeholders recipient/recovery. Pull завершается
`CONFIG_INVALID`, пока оператор не предоставит public recipient, ссылку на проверенную
offline-процедуру восстановления и отдельное разрешение активации. Режимы `none`,
`bitlocker`, `file_encryption` и `plaintext_risk_acknowledged` не обходят age-контракт.
Наличие `approved=true` само по себе не доказывает существование ключа или recoverability.

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
является только конфигурационным gate и никогда не заменяет проверку ciphertext и recovery
отдельного age identity. Реальное синтетическое шифрование и восстановление описаны в разделе 12. Проверка Task Scheduler вне интерактивного сеанса
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
4. Сверить размер и SHA-256 ciphertext с manifest v2; получить offline age identity и
   расшифровать копию в разрешённом защищённом staging по разделу 11.3. Затем проверить читаемость custom archive через
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

## 9. Историческая перепроверка Phase B/C (2026-10-19)

Ниже сохранён snapshot на указанную дату; текущая проверка и порядок активации — в разделе 13.

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

Каталог и ACL намеренно не создавались: при отсутствии elevated owner/runner identity это могло бы закрепить неподходящее наследование. Ранее предложенный BitLocker-encrypted VHDX/container позднее отклонён владельцем в пользу обычной папки `D:\YFC-Backups`; отдельное шифрование тома/контейнера не внедряется. Подтверждено администратором Windows: `D:` FullyDecrypted, ProtectionStatus Off, EncryptionMethod None. Позднее выбран age для самих файлов (раздел 12); перед реальной передачей требуется проверить этот контур и privacy delta, а состояние тома отдельно не доказывает защищённость файлов.

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

Решения о file-level age от 21.10.2026 заменили прежние предложения о plaintext storage;
ниже учтён этот выбор. Фактическая активация по-прежнему не разрешена.

| Решение | Предложение, не утверждение | Нужное подтверждение |
| --- | --- | --- |
| Cadence | **OWNER-APPROVED:** один новый архив в сутки. Опрос Windows каждый час остаётся предложением, а не утверждённым расписанием | Настройка и проверка реального VPS timer / Windows pull |
| Retention | **OWNER-APPROVED:** хранить архивы 7 дней (обычно 7 ежедневных копий). При очистке не удалять единственную последнюю проверенную копию в период сбоев; отдельно сигнализировать о нарушении retention | Проверить расписание очистки и корректность безопасного удаления после валидации новой копии |
| RPO | Первоначальное предложение 24 часа уточнено в 13.3 с учётом задержки Pull; target ещё не утверждён | Последний успешный pull и время source dump |
| RTO | Первичная цель 8 часов | Измеренный clean-host restore |
| Encryption | **OWNER-APPROVED:** обычная папка на `D:`, только `.dump.age`, шифрование на VPS до публикации; без VHDX | Проверить age ciphertext, private staging, ACL и privacy scope; состояние тома не доказывает защиту файлов |
| Key recovery | Отдельная offline age identity и две независимые защищённые recovery-копии по разделу 12.2; SSH key хранится отдельно | До активации восстановить identity из каждой копии и расшифровать синтетический файл |
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
   python3 scripts/db_maintenance.py backup --publish-dir .artifacts/operations/backups/offhost --retain-published 7 --age-path /opt/yfc-tools/age-v1.3.2/age --age-recipient "$YFC_BACKUP_AGE_RECIPIENT"
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
   Config example из #1125 остаётся fail-closed; `approved=true` допустимо только после
   проверки отдельного offline age key recovery и разрешения на реальные данные.
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
$manifestPath = Join-Path $backupRoot 'REPLACE_WITH_ARCHIVE.dump.age.manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (($manifest.schema_version -isnot [int] -and $manifest.schema_version -isnot [long]) -or
    $manifest.kind -cne 'yfc-backup-manifest' -or $manifest.schema_version -ne 2 -or
    ($manifest.archive_size_bytes -isnot [int] -and $manifest.archive_size_bytes -isnot [long]) -or
    $manifest.archive_size_bytes -le 0 -or $manifest.archive_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
    $manifest.archive_format -cne 'age-v1' -or $manifest.age_version -cne 'v1.3.2' -or
    $manifest.archive_name -cnotmatch '\.dump\.age$' -or
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

Получить **копию** offline identity по разделу 12.2 на разрешённом recovery-хосте.
Не класть identity или plaintext в `D:\YFC-Backups`, Git, CI или синхронизируемый каталог.
Проверить возраст/size/hash, ожидаемый recipient, закрытые права staging, swap/pagefile,
доступный объём и отсутствие production mounts. Затем выполнить:

```powershell
$age = 'C:\YFC-Backup-Tools\age.exe'
$identity = 'REPLACE_WITH_APPROVED_OFFLINE_IDENTITY_COPY'
$staging = 'REPLACE_WITH_EXISTING_PROTECTED_RECOVERY_DIRECTORY'
$expectedRecipient = 'REPLACE_WITH_APPROVED_PUBLIC_RECIPIENT'
if ($manifest.recipient -cne $expectedRecipient) { throw 'Unexpected recovery recipient' }
if ((Get-FileHash -LiteralPath $age -Algorithm SHA256).Hash.ToLowerInvariant() -ne
    '2821a4ed191da07372acd302e5f6feae7a7985e285e1417765ebe74025af45f0') { throw 'Untrusted age binary' }
$ageVersion = & $age --version
if ($LASTEXITCODE -ne 0 -or $ageVersion -cne 'v1.3.2') { throw 'Unsupported age version' }
if (-not (Test-Path -LiteralPath $staging -PathType Container)) { throw 'Protected staging missing' }
$ciphertext = $archive
$archive = Join-Path $staging ('restore-' + [guid]::NewGuid().ToString('N') + '.dump')
& $age --decrypt --identity $identity --output $archive $ciphertext
if ($LASTEXITCODE -ne 0) {
    Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
    throw 'Decryption failed; preserve ciphertext and stop'
}
$plaintextSha = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
```

Не принимать partial plaintext при любой ошибке age. Windows PULL никогда не выполняет
этот шаг: закрытый age key не нужен Scheduler. Оригинал `.age` сохраняется.

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
if ($LASTEXITCODE -ne 0 -or ($isolatedDigest -split '\s+')[0] -ne $plaintextSha) {
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

### 11.4 Историческое решение о диске

Незашифрованная папка и ACL сами по себе не защищают dump при offline-чтении диска.
Предложенный ранее plaintext opt-in заменён решением владельца: отдельные age-архивы
в обычной папке. Текущий контракт и оставшиеся условия приведены ниже.

## 12. Обязательное age-шифрование: решение владельца, 2026-10-22

Сохраняются обычная `D:\YFC-Backups`, один архив в сутки, семь суток хранения, исходящий
Windows PULL через SSH/SFTP и Task Scheduler. VHDX, облако и платные сервисы не нужны.
Реализация — существующий [PR #1125, exact HEAD `f0ad024ef4b486fd99cb41677cf6c6785c6a2571`](https://github.com/MikeMoore1337/your-fitness-coach/tree/f0ad024ef4b486fd99cb41677cf6c6785c6a2571), инструкции — этот PR #1123. Установка на VPS/Windows,
реальные ключи владельца, ACL, SSH, расписания, production transfer, merge и deploy не выполнены.

### 12.1 Формат и границы защиты

- VPS хранит только public X25519 recipient. `backup --publish-dir` требует явные
  `--age-recipient` и абсолютный `--age-path`. Исполняемый файл сверяется с закреплённым
  SHA-256 и `--version` перед запуском. Автоматической загрузки/установки/PATH fallback нет.
- Dump создаётся с `pg_dump --format=custom` в отдельном временном каталоге с закрытыми
  правами вне export. После `pg_restore --list` запускается age; при любой ошибке encryption
  index не меняется и ротация не начинается. Временный plaintext удаляется при штатном выходе
  и исключении. После kill/power loss он может остаться: оператор проверяет закрытые `.dump-*`
  staging после перезапуска. Удаление файла не доказывает стирание SSD/swap или host snapshots.
- В export попадают только готовые `.dump.age`, manifest и index. Index заменяется последним;
  orphan после сбоя между ciphertext/manifest/index не считается копией. Оператор сверяет
  его digest/причину и отдельно решает cleanup; runner не восстанавливает index догадкой.
- Manifest и index принимают только целочисленный `schema_version=2`; manifest содержит
  `archive_format=age-v1`, `age_version=v1.3.2`, public `recipient`, положительный целочисленный
  `archive_size_bytes` и lowercase SHA-256 **зашифрованного файла**. Index повторяет эти поля.
  Размер/хеш проверяются заново при загрузке и локальной ротации. Формат v1 не импортируется.
- Windows проверяет `.dump.age`, бинарный заголовок age X25519, совпадение recipient с config,
  manifest/index и фактический размер/SHA. Заголовок — структурная проверка, не доказательство
  криптографической подлинности. За корректное создание отвечает доверенный publisher с
  закреплённым age. SHA рядом с архивом не защищает от VPS, способного заменить оба объекта;
  pinned SSH защищает транспорт. Age при расшифровке проверяет целостность ciphertext.
- Закрытого age identity на VPS и в Windows runner нет. SSH identity — отдельный ключ для
  read-only доступа, не ключ расшифровки. Незашифрованные local `.dump` блокируют Pull с
  `CONFIG_INVALID` и сохраняются для перехода. Старые/чужие manifest не становятся валидными.
- После простоя скачиваются доступные новые копии; при ошибке передачи ротация не выполняется.
  Windows удаляет пары старше семи суток, сохраняя минимум две проверенные; VPS хранит семь
  последних успешных публикаций. При одном архиве в сутки это обычное семидневное окно;
  сбои могут увеличить возраст двух защищённых копий. Такие исключения требуют оповещения.

Age защищает конфиденциальность копий при отдельном закрытом ключе, но не является защитой
от удаления копий скомпрометированным администратором Windows. Сам VPS уже имеет исходную БД.
Физические ACL, private staging, backup/privacy geography и оповещения остаются условиями активации.

### 12.2 Offline identity: создание, восстановление, потеря и смена

Эти действия выполняет владелец после отдельного разрешения, на доверенном offline recovery-хосте.
В текущей работе создавались и удалялись только одноразовые синтетические identities.

1. Проверить бинарники по разделу 12.3. Подготовить закрытый несинхронизируемый staging вне
   репозитория, CI, VPS и backup-каталога; проверить права и отсутствие записи секретов в
   transcripts/логах/скриншотах. Выполнить `age-keygen -o <private-identity-file>`; не выводить
   файл с `AGE-SECRET-KEY-...` в терминал. `age-keygen -y <private-identity-file>` выдаёт public
   recipient: только его передать publisher и Windows config по проверенному каналу.
2. Сделать две независимо хранимые offline recovery-копии identity, например запечатанные
   бумажные копии с проверенным полным текстом в разных защищённых физических местах.
   Допустим имеющийся защищённый offline носитель; покупка носителя/сервиса не требуется.
   Зафиксировать доступ ответственного и резервного хранителя без самого секрета в Issue.
   Не хранить единственную recovery-копию на ПК с backup или рядом с ним.
3. До активации зашифровать безопасный тестовый файл выбранным recipient, убрать рабочую
   identity и восстановить её из **каждой** recovery-копии в закрытый staging. Проверить
   `age-keygen -y`, успешную расшифровку и SHA исходного тестового файла. Записать дату,
   public recipient и результат без private identity. Только затем указать конкретную ссылку
   в `key_recovery_document`; boolean `approved` не заменяет эту проверку.
4. Для восстановления получить разрешённую offline копию identity, проверить public recipient,
   ciphertext manifest/size/SHA и использовать отдельный recovery staging из раздела 11.3.
   При неверном/отсутствующем ключе или ошибке age остановиться, удалить только созданный
   partial plaintext и сохранить `.age` неизменным. Не запускать pg_restore на partial output.
5. Потеря всех identities делает старые архивы невосстановимыми. Новый ключ не расшифрует их.
   Зафиксировать инцидент, сохранить ciphertext, искать независимую recovery-копию; если БД
   ещё доступна, отдельно согласовать новый recipient и новую зашифрованную цепочку.
6. При смене/компрометации ключа остановить ротацию, отдельно согласовать переход. Использовать
   новый export и отдельный защищённый набор старых копий: текущий publisher откажет при
   несовпадении recipient в существующем index, Windows не примет старый recipient как новый.
   Старые identities хранить до разрешённого истечения всех соответствующих копий и проверки
   нового restore. Перешифрование требует decrypt в закрытом staging и не стирает уже утёкшие копии.

У age нет центрального отзыва уже выпущенных архивов: исключение старого recipient из новых
публикаций защищает только будущие копии. Отзыв отдельного SSH key прекращает транспортный
доступ, но не делает ранее скачанный ciphertext недоступным владельцу старой age identity.

После drill отдельно подтвердить удаление созданного plaintext и временной identity на recovery-хосте;
offline оригиналы и проверенную `.age` не удалять. Приватный ключ никогда не прикладывать к evidence.

### 12.3 Бесплатные бинарники и закрепление происхождения

Источник — [официальный FiloSottile/age v1.3.2](https://github.com/FiloSottile/age/releases/tag/v1.3.2),
лицензия BSD-3-Clause. Получены только assets этого GitHub release по HTTPS; до распаковки
SHA-256 сопоставлен с `digest` официального GitHub Releases API. После распаковки отдельно
посчитаны SHA исполняемых файлов. Runtime pins находятся в `scripts/age-toolchain.json` PR #1125.

| Платформа | Release asset | SHA-256 архива |
| --- | --- | --- |
| Linux amd64 | `age-v1.3.2-linux-amd64.tar.gz` | `cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10` |
| Windows amd64 | `age-v1.3.2-windows-amd64.zip` | `f48d8f8f9ebe903ab5027ed067652f2cc1db94bc206976430133b905dcd8e8c7` |

| Исполняемый файл | SHA-256 |
| --- | --- |
| Linux `age` | `eb7dd1b518f0a307c99cd97782623c5321da049154b04acd2d98d21aa7bc9b2c` |
| Linux `age-keygen` | `0a0009db842259d6717f7eeb30acb6b90d2a2eb924c6acd0a0db0ca1f1537899` |
| Windows `age.exe` | `2821a4ed191da07372acd302e5f6feae7a7985e285e1417765ebe74025af45f0` |
| Windows `age-keygen.exe` | `1549c7049be32695594bedd09bbd352a94b6013a9d5c43364f3c6cd7a09ab61c` |

Перед установкой получить точный asset с официального release, проверить archive SHA, распаковать
в отдельный каталог и проверить binary SHA; до этого ничего не исполнять. Не использовать mirrors,
latest-URL, сторонние wrappers или автообновление. Установленный binary/config/pins должны быть
недоступны на запись SFTP/непривилегированным пользователям. Поддержка других архитектур требует
отдельно проверенных pins; автоматической подмены нет. Использовано доверие к официальному GitHub
HTTPS/API. Дополнительная Sigsum-проверка обоих assets выполнена 22.10.2026: `PASS`.
Использованы два upstream public signing keys из
[SIGSUM.md на закреплённой ревизии](https://github.com/FiloSottile/age/blob/b74dce4cdbe35b5e5f66c06d9612b72f89028758/SIGSUM.md),
официальный `sigsum-verify v0.13.1` и встроенная policy `sigsum-generic-2025-1`.
Проверка прошла offline в одноразовом контейнере с read-only mounts только публичных assets,
proofs и signing keys; production secrets/data не подключались. SHA-256 proofs:
Linux `98402fa59b4e433426156b4a7e74a32e44902e0434c61158f7de18ffc84f1f97`,
Windows `00ae35a24a47b9bace52ec62f06d402f38f6ecba4ca099d060a137e82ef0bc1d`.
Повторно сверены оба archive SHA и все четыре binary SHA из таблиц выше.
Sigsum подтверждает подпись/включение в transparency log в рамках этой policy, а не
воспроизводимость сборки из исходников, отсутствие уязвимостей или установку на VPS.
В Releases API `immutable=false`; фиксированные SHA сохраняются, latest/автообновления не используются.

Для повторной проверки после получения официального verifier и public keys оператор выполняет
следующие команды в каталоге с assets/proofs; private age identity здесь не нужна:

```sh
sigsum-verify -k age-sigsum-key.pub -P sigsum-generic-2025-1 age-v1.3.2-linux-amd64.tar.gz.proof < age-v1.3.2-linux-amd64.tar.gz
sigsum-verify -k age-sigsum-key.pub -P sigsum-generic-2025-1 age-v1.3.2-windows-amd64.zip.proof < age-v1.3.2-windows-amd64.zip
```

### 12.4 Переход с незашифрованных архивов

Автоматическая миграция и удаление legacy не выполняются. Сначала остановить старые jobs и ротацию,
зафиксировать фактическую последнюю проверенную копию/manifest, размер/SHA и доступный объём.
Не считать перенос legacy с последующим удалением гарантией стирания SSD.

1. На VPS сохранить старые проверенные копии в закрытом **неэкспортируемом** quarantine вне нового
   export. Старый SFTP account не должен иметь к нему доступа; проверить реальные права отдельно.
   Создать чистый export для v2, настроить только public recipient и закреплённый age.
2. На Windows до нового Pull переместить старые plaintext-копии с manifest в отдельно защищённый
   несинхронизируемый quarantine вне `D:\YFC-Backups`, с отдельной owner/privacy оценкой хранения.
   Если защищённое место и запас объёма не подготовлены, переход остановить и сохранить originals.
   До этого runner блокирует Pull и ничего из legacy не удаляет.
3. Создать новый encrypted backup, получить его в обычную `D:\YFC-Backups`; проверить ciphertext
   size/SHA и offline key recovery. Выполнить отдельно разрешённый isolated restore из Windows-копии
   с данными/schema/invariants/application smoke, согласовать RPO/RTO и получить следующую
   ежедневную проверенную копию. Старые originals пока сохраняются, новая ротация их не касается.
4. Только после подтверждения замены и отдельного решения владельца удалить или оставить до
   согласованного срока legacy/quarantine и старый export. Удаление, физическое стирание и
   повторная выдача SFTP-доступа не входят в этот PR. При сбое новой схемы остановиться;
   возвращение к plaintext-экспорту или `mode=none` не допускается.

### 12.5 Синтетическая проверка и условия реальной активации

Выполнен полный синтетический цикл: PostgreSQL **16.15** → custom dump **5 979 bytes** →
реальный закреплённый Linux age **6 179 bytes** → локальная SFTP-имитация → настоящий Windows
PULL в PowerShell **7.6.6** и **5.1.26100.9444** → Windows age decrypt → новая PostgreSQL 16.
Исходный PostgreSQL-контейнер и plaintext dump удалены **до** восстановления; identities не
передавались Linux publisher. Проверены строки, binary bytes, schema revision, sequence и FK.
Настоящий age отклонил malformed recipient. Отказали неверный ключ, отсутствующий ключ и
повреждённый ciphertext; recovery из отдельной
синтетической identity-копии прошёл. Одноразовые identities и drill-файлы удалены после теста.

Синтетический ciphertext SHA-256:
`7803a39f5e1d2fe09ba1882613322f81518e2376856e7cb6b1949630a6511423`.
PostgreSQL image: `postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`;
Python publisher: `python@sha256:29e1fe7a54021a1d8990f59223f1246a4239b106895363680b23aa1265f73cb3`.
Контейнеры без сети, портов и production mounts; DB в tmpfs. Дамп проверен реальным
`pg_restore --list` в source PG16; Compose adapter внутри publisher заменён этим отдельным
вызовом, шифрование выполнял исходный `_encrypt_archive` без подмены. Время запуска новой БД,
restore и SQL-проверок **2,393 s** — синтетическая величина, не RTO продукта.

46 целевых Python-тестов (manifest/publication/maintenance/deployment scope) прошли. Windows
self-test: **46/46 в каждой оболочке** на том же exact source HEAD; проверены downgrade/type/recipient/format rejection, plaintext rename,
обрыв передачи, SHA/truncation, host-key/auth, locking, disk margin, статус после простоя,
catch-up, семидневную ротацию, её отказ и побайтное сохранение предыдущих проверенных копий.
Ошибка age/ENOSPC и сбои записи manifest/index проверены Python fault injection; физическое
заполнение диска не выполнялось. Реальный Scheduler/reboot, SFTP endpoint/ACL, application smoke
и production restore — `NOT_RUN`. Exact-head CI и security-check URLs фиксируются в обоих PR
и Issue #849 после проверки финальных head, без заявления о production readiness.

Для реальной активации остаются отдельные условия: privacy/security #707/#711 и география;
проверенные offline key custody/recovery; защита executable/config/staging/ACL и переход legacy;
read-only SFTP с отрицательными тестами; запас диска и VPS retention относительно простоя ПК;
owner-approved время ежедневного backup, интервал Pull/Task Scheduler, оповещения и reboot test;
подтверждённая независимая `.age`-копия; отдельно разрешённый clean-host drill с application smoke
и заранее согласованными RPO/RTO. `BACKUP_RECOVERY=NOT_PROVEN`, Issue #849 остаётся OPEN.

`env change required: no` для application runtime: `.env`, Compose, deployment contract и
runtime keys не меняются. Активация требует host-side установки age/pins и передачи public
recipient через явный `--age-recipient` (пример использует shell variable `YFC_BACKUP_AGE_RECIPIENT`),
Windows config `mode=age`, recipient/recovery reference и отдельно разрешённых действий выше.

## 13. Подготовка активации (22.10.2026, без production changes)

### 13.1 Текущие факты и границы проверки

Проверены live `master=efbf14b453bae3d3c2ba32b2cf04784c47fd8968`, source PR #1125
`f0ad024ef4b486fd99cb41677cf6c6785c6a2571` и прежний docs HEAD #1123
`3e46ebe53056c6b224a3666c497a43c0fe3c0015`. Оба PR OPEN/Draft, без merge.
У source exact HEAD aggregate `checks=success`, CodeQL Python/JS, Dependency audit и Free PR
security audit успешны: [CI 39678838169](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39678838169).
Исходники не менялись: существующие 46 Python tests, по 46 PowerShell-сценариев и PG16/age
synthetic restore из раздела 12.5 повторно не запускались. Их старые отчёты проверены;
это не новый production drill. После изменения этого runbook нужен новый docs exact-head CI.

| Область | Read-only наблюдение 22.10.2026 | Вывод для активации |
| --- | --- | --- |
| VPS access | Основной SSH alias завершился timeout; существующий второй alias с `BatchMode=yes`, `StrictHostKeyChecking=yes` дал доступ к хосту с YFC backend/worker/bot и DB containers | Доступ для ограниченной диагностики есть; это не разрешение на изменение хоста. Hermes relay показывает sandbox devices, они не использовались как production evidence |
| PostgreSQL/tools | В DB container `postgres`, `pg_dump`, `pg_restore` версии **16.15**; размер текущей БД **87 268 375 bytes**. Docker доступен. В PATH и предусмотренном `/opt/yfc-tools/age-v1.3.2/age` age не найден | PG16 capability подтверждена; установка pinned age и права executable ещё требуются. Это не исчерпывающий поиск всех executable хоста |
| VPS archives | В двух существующих backup roots найдены старые `.dump`, включая копии до 19.10 размером до **51 592 746 bytes**; index/manifest в проверенном application backup root не найдены. Архивы не открывались, не перемещались и не удалялись | Ciphertext publication и свежий off-host backup `NOT_PROVEN`. Историческое наличие `.env` из раздела 9 не подтверждено в этом root сейчас; разрешать весь root по-прежнему нельзя |
| VPS permissions | Backup roots `0700`, владелец deploy; несколько legacy dump имеют `0664`, внешний parent `/srv` — root-owned `0755` | Есть место для отдельного export/chroot проекта, но фактические publish/read/write/traversal permissions нового endpoint `NOT_VERIFIED` |
| SSH/SFTP | `yfc-backup-readonly` отсутствует; существующий `backup` имеет `nologin`. Effective sshd для предполагаемого пользователя: password auth/TTY/forwarding разрешены, `ForceCommand=none`, `ChrootDirectory=none`, `AuthenticationMethods=any` | Hardened dedicated endpoint отсутствует в проверенной конфигурации. `nologin` сам по себе не доказывает read-only SFTP |
| VPS space/jobs | На filesystem backup roots свободно **25 032 531 968 bytes**, `/tmp` — около **1 GB**. В проверенных system timers/root cron/cron files YFC dump job не найден; есть системный `dpkg-db-backup.timer` | Объём достаточен относительно наблюдаемых старых dumps, но peak нового dump+ciphertext/retention и задания вне проверенного scope `NOT_VERIFIED`; системное задание не изменять |
| Plaintext cleanup | `TemporaryDirectory` закрывает `.dump-*` staging на нормальном выходе/исключении; source review и прежняя fault injection доступны | Crash/power-loss cleanup на VPS и отсутствие plaintext в snapshots/swap `NOT_VERIFIED`; процедура ниже обязательна |
| Windows tools/storage | Реальные PowerShell **7.6.6**, **5.1.26100.9444**, OpenSSH **9.5p2** доступны. D: NTFS, total **1 000 203 087 872**, free **183 331 258 368 bytes**. `D:\YFC-Backups` отсутствует | Target ACL и dedicated runner не подготовлены; незашифрованных файлов в отсутствующем target нет, это не аудит всего D: |
| Windows age | age не найден в PATH; уже имеющиеся synthetic tools в ignored artifacts имеют правильные archive/binary SHA и `age --version=v1.3.2` | Проверенный portable tool доступен для диагностики; защищённая operational installation `NOT_VERIFIED`, автоматически ничего не установлено |
| Scheduler | Sandbox-запросы сообщили недоступность службы. Повторная read-only проверка вне sandbox подтвердила `Schedule=Running`; точная задача `\YFC\OffHostBackupPull` не найдена | Возможность службы подтверждена; batch logon, отдельный key, reboot/catch-up и выполнение без входа пользователя `NOT_VERIFIED` |
| Windows ACL/sync | Parent D: имеет права обычных Users/Authenticated Users. Target не находится под известным OneDrive root, OneDrive process не найден, D: не reparse point. Read-only SMB query не нашёл share, покрывающий target | Новый каталог требует отдельного ACL. Эти проверки не исключают все сторонние sync agents/remote access; нужен owner inventory и проверка точного runner context |

Dedicated SSH key и отдельный pinned known_hosts предусмотрены runner: `-F NUL`,
`IdentitiesOnly=yes`, `IdentityAgent=none`, `StrictHostKeyChecking=yes`, без global known_hosts.
Настоящий backup SSH key не создавался; доступ к нему от имени будущего runner не проверен.
Внешний размер/количество архивов не доказывает валидность их содержимого или recoverability.

### 13.2 Privacy/security delta к Task 108

[#707](https://github.com/MikeMoore1337/your-fitness-coach/issues/707#issuecomment-5997663176)
закрыт после Stage B reconciliation: владелец сообщил о внешней российской юридической
проверке без blocking objections и об уведомлении Роскомнадзора. Детали заключения/подачи
в public evidence `NOT_PROVIDED`. Закрытие
[#711](https://github.com/MikeMoore1337/your-fitness-coach/issues/711#issuecomment-5997663344)
подтверждает технический baseline, сохраняя непроверенные регионы/договоры/retention как UNKNOWN.
Повторять эти стадии или объявлять их незавершёнными не требуется. Новый Windows backup flow
проверяется как конкретная delta в существующей рамке Task 108, а не как новая legal program.

В разделе 10 сохранено сообщение владельца «VPS и Windows в России»; это `OWNER_REPORTED`,
не независимое подтверждение физического места и не отдельное разрешение на новую передачу.
До активации владелец/privacy owner фиксирует в защищённом intake:

- фактическую страну/место размещения ПК и VPS, хранителей, физический доступ и перемещения ПК;
  место изолированного restore host и двух key-recovery copies; точный адрес не публикуется;
- маршрут VPS → исходящий SSH/SFTP → ПК, фактические VPN/proxy/relay, endpoints, обработчиков
  и страны хранения/обработки; IP, DNS или VPN не используются как доказательство юрисдикции;
- фактический состав полного DB dump: идентификация/auth metadata, тренировки, питание,
  измерения, coach/client records, binary columns и другие присутствующие таблицы; целесообразность,
  минимизацию и классификацию чувствительных данных подтверждают owner/privacy/counsel;
- цели, доступ, retention 7 суток с исключением защищённых последних копий, правила удаления,
  incident handling и повторного применения удалений после восстановления старого snapshot;
- применимость прежнего counsel решения к этой delta либо отдельное решение по MATERIAL/UNKNOWN.
  Выбор age и наличие SSH не заменяют эту проверку.

Результат: baseline решения признаны; storage/transport/data-scope delta —
`OWNER_PRIVACY_DECISION_REQUIRED`, спорные правовые вопросы — `LEGAL_COUNSEL_REQUIRED`.
Соответствие законодательству по этой проверке не заявляется.

### 13.3 Предложения по эксплуатации — ещё не утверждены

Создание **одного архива в сутки** и retention **7 дней** уже утверждены. Остальные значения
ниже — предложения для решения владельца до измерения drill, не действующая конфигурация.

| Параметр | Предложение | Условие проверки |
| --- | --- | --- |
| Время backup | 03:00 Europe/Moscow = 00:00 UTC ежедневно; проверить существующее окно нагрузки | Измерить длительность/peak disk первого backup, не менять PostgreSQL |
| Windows Pull | Каждый час с 03:30 MSK; `StartWhenAvailable`, `IgnoreNew`, повтор после отказа | XML — шаблон; согласовать timezone, batch identity и фактический logon type, проверить без интерактивного входа |
| RPO | Номинально 24 часа; первоначальный предельный возраст независимо полученной копии **26 часов** | Суточный интервал + ожидание Pull/завершения могут превысить 24 часа. Если требуется строго ≤24 часов, это предложение недостаточно: согласовать иную политику до активации |
| RTO | **8 часов** от объявления полной потери VPS до проверенного изолированного приложения | Измерять получение ciphertext/ключа, provision, decrypt, PG restore, schema/invariants и application smoke; отдельно учитывать traffic cutover. 2,393 s synthetic не использовать |
| Сбой | Немедленный sanitized alert при ненулевом publisher/Pull exit, host-key/auth/crypto mismatch или disk failure | Существующий разрешённый канал, без archive payload, secrets и данных пользователей; проверить доставку на тестовой ошибке |
| Нет новой копии | Alert при возрасте >26 часов или `MISSING`/`CORRUPTED`, затем напоминание раз в сутки до устранения | Проверять время source dump и receipt независимо; старый `HEALTHY` не считать свежей копией |
| Потеря связи/ПК выключен | Alert после двух пропущенных часовых receipts, критический по RPO; восстановление связи — одно уведомление | Нужен наблюдатель вне ПК и желательно вне VPS. Локальная Windows задача не способна сообщить о собственном выключении; канал/наблюдатель пока не выбраны и не реализованы |
| Restore drills | После первой независимой копии, смены ключа/версии PG и далее ежеквартально | Каждый real-data drill отдельно разрешить; recording без PII. Частоту утверждает владелец |

VPS хранит семь **успешных публикаций**, Windows — пары старше семи суток с минимум двумя
valid copies. Простой ПК около/свыше семи дней может дать необратимый пропуск ежедневных копий;
catch-up получает только ещё существующие. Длительность простоя и такое ограничение надо принять
заранее; при нарушении срока защищёнными копиями нужен отдельный privacy/retention разбор.
Без утверждённого внешнего observer потеря связи end-to-end остаётся `NOT_VERIFIED`.

### 13.4 Последовательность первоначальной активации и отката

Все действия таблицы **подготовлены, но не выполнены**. Текущий запрос разрешает только
read-only диагностику и разработку документации. Для каждого изменяющего среду шага требуется
отдельное явное разрешение с точным host/account/path и границами данных. Сначала review/CI
существующих PR, затем отдельные merge/release разрешения; эта таблица их не выдаёт.

| Шаг | Предварительные условия и действие | Проверка успешности | Безопасный откат | Разрешение владельца |
| --- | --- | --- | --- | --- |
| 1. Privacy/security и физическое место | Закрыть delta из 13.2, выбрать ответственного, допустимые данные, access/retention и RPO/RTO | Датированное решение owner/privacy; counsel по MATERIAL/UNKNOWN, private evidence reference без адресов/секретов в Issue | При нехватке фактов остановить активацию; существующие копии не менять | Требуется решение по реальным данным и местам хранения |
| 2. Age identity и recovery | Доверенная offline среда, проверенные binaries, закрытый staging; владелец создаёт identity по 12.2, передаёт только public recipient, делает две независимо защищённые копии | Из каждой копии отдельно восстановлены identity/recipient и расшифрован synthetic файл с исходным SHA; private key не попал в VPS/backup/Git/CI/logs | До успешной проверки не активировать recipient. Сохранить рабочие recovery copies; cleanup только созданных временных key/plaintext, без заявления о физическом стирании | Отдельное разрешение на настоящий ключ; действие выполняет владелец |
| 3. VPS tools/private staging/SFTP | Подтверждены pinned age/Sigsum, publisher identity и диск; подготовить closed staging и отдельный ciphertext export, dedicated public-key-only internal-sftp/chroot по 10.2 | `sshd -t`, независимая admin session и новый login; list/get synthetic object успешны, put/rename/remove/traversal/shell/TTY/forwarding запрещены; secrets невидимы; publisher может писать, SFTP user не может | Сохранить конфигурацию, при сбое убрать только новый drop-in/mount, проверить `sshd -t` и reload без потери admin access; копии сохранить | VPS install/users/SSH/ACL/mount/reload — отдельное точное разрешение |
| 4. Windows storage/SSH | Выбрана runner identity; создать D:\YFC-Backups, script/config/SSH paths с нужными ACL, исключить sync/share/reparse; age identity вне этих путей | Под runner write+atomic rename в synthetic target разрешены, посторонний read/write запрещён; отдельный SSH key работает с out-of-band pinned host fingerprint | До real-data transfer исправить ACL/paths; вернуть прежние ACL только для подготовленных объектов по сохранённому descriptor. Не ослаблять реальные backup ACL ради rollback | Отдельное разрешение на каталог, ACL и настоящий SSH key |
| 5. Расписания/logs/alerts | Утвердить 13.3 и бесплатный существующий alert channel/observer; подготовить **выключенные** timer/task, ограниченные logs, нет конфликтующих jobs | Проверены command paths/timezone/noninteractive key access, ненулевые exits, sanitized тестовый alert и пропуск heartbeat; повторный schedule не создаёт второй ежедневный dump | Отключить/удалить только новые задания/правила уведомлений, сохранить evidence и копии | Отдельное разрешение на registration/config; включение только после шагов 6–9 |
| 6. Legacy transition | Инвентаризация метаданных/последней valid копии, запас места и закрытый quarantine; остановить конфликтующие старые jobs/rotation и выполнить 12.4 | Originals сохранены, новый v2 export пуст и не открывает старый plaintext; Windows target ciphertext-only; известен допустимый перерыв backup | Остановить новый flow, сохранить legacy и ciphertext. Не возвращать plaintext export, `mode=none` и не удалять originals | Отдельное разрешение на остановку jobs, перемещение/карантин; удаление legacy требует ещё одного решения после restore |
| 7. Первый реальный `.dump.age` | Шаги 1–6 успешны; approved public recipient, patched helper exact revision, private staging/export и peak disk готовы; один ручной publisher run | `pg_restore --list` исходного dump, age version/hash, ciphertext manifest/index v2 с size/SHA/recipient; index последним; plaintext штатно очищен | При ошибке сохранить старый index/копии, остановить jobs; после crash осмотреть только принадлежащий этому запуску закрытый staging, подтвердить отсутствие живого writer и отдельно разрешить cleanup | Отдельное разрешение на production dump/encryption/publication; без передачи на этом шаге |
| 8. Независимое получение Windows | Закрыты legal/transport/ACL/key gates; отдельно разрешить transfer exact archive и запустить ручной Pull под runner | Windows-held ciphertext и manifest size/SHA совпали, receipt/freshness сохранены; повтор не перезаписывает; независимость от VPS подтверждена доступом к сохранённому object при недоступном источнике | Остановить Pull, сохранить старые valid пары и полученный ciphertext, расследовать failure; не менять host pin автоматически | Отдельное разрешение на передачу production данных в выбранное место |
| 9. Clean-host восстановление | Отдельно approved закрытый host/PG16/exact app revision, secrets из разрешённого источника; writers/bot/provider egress/public routes отключены; цели RPO/RTO согласованы заранее | Decrypt Windows-копии recovered key, затем настоящий PG restore, Alembic/schema, rows/binary/sequence/FK, health и application smoke по разделу 7; измерить полный RTO/RPO без PII в evidence | При сбое остановить drill, закрыть/очистить только разрешённую isolated среду и временный plaintext/key; source DB, ciphertext и offline originals сохранить | Отдельное разрешение на перенос/расшифровку/restore реальных данных и временные secrets. Traffic cutover сюда не входит |
| 10. Штатная работа | Шаги 7–9 приняты, получена следующая ежедневная valid копия, alarms и recovery evidence проверены | Разрешить включение schedules; подтвердить неинтерактивный/reboot/catch-up цикл, ежедневную свежесть, exit/logs/alerts, 7-day policy и сохранение двух valid копий | Отключить только новые schedules/rotation, сохранить последние копии; вручную возобновлять backup только по согласованному безопасному режиму. Удаление данных не является автоматическим rollback | Отдельное разрешение на включение и эксплуатационную приёмку; legacy deletion и traffic cutover разрешаются отдельно |

На шаге 3 publisher helper разрешает publish path только **внутри BACKUP_DIR**. Нельзя просто
передать `/srv/yfc/backups` или произвольный chroot path в `--publish-dir`. После отдельного
разрешения оператор может предоставить именно ciphertext child через read-only bind mount
в `/export` нового root-owned chroot; способ и persistent mount надо проверить на фактическом
хосте. Chroot parents не должны быть writable ни SFTP-пользователю, ни publisher. Писать в
отдельный export child может только publisher; read-only mount не заменяет SSH restrictions.
Export allowlist включает служебный `.publish.lock`, index и ciphertext/manifest; ни `.env`,
ни `.dump-*`/`.age-*` staging туда не попадают.

Перед шагом 7 измерить размещение staging на том же filesystem и свободный объём под сохранённые
копии + новый plaintext dump + ciphertext + partial/metadata + согласованный запас. По старым
файлам до 51,6 MB и 25 GB free сейчас не видно дефицита, но реальный peak/рост не измерен.
После crash оператор не использует wildcard cleanup: сверяет владельца/путь/живой процесс и
удаляет только согласованные abandoned files, не последние verified копии. Удаление не доказывает
стирание SSD/swap/snapshots. До выполнения проверки этот контроль `NOT_VERIFIED`.

### 13.5 Итог готовности

- `CODE_READY=PASS` для неизменённого source HEAD #1125: source review, существующие целевые
  тесты/синтетический restore и live exact-head/security CI; это не production readiness.
- `ACTIVATION_READINESS=BLOCKED`: необходимы owner/privacy delta, реальные offline keys/recovery,
  VPS age/SFTP/staging/legacy/ACL, Windows runner/ACL/SSH, schedules/alerts и согласованные targets.
- `BACKUP_RECOVERY=NOT_PROVEN`: настоящая независимая защищённая копия не получена и не
  восстановлена с application smoke в разрешённой изолированной среде.

`env change required: no` для application runtime. Обязательные будущие host-side действия:
pinned age install, public recipient/publisher arguments, private staging/export/SSH/mount/ACL,
Windows runner config/key/known_hosts, schedules/alerts, legacy transition и recovery evidence.
Настоящие ключи, копии, users/SSH/ACL/schedules, приложение и PostgreSQL не изменялись;
merge/deploy/real restore не выполнялись. Issue #849 остаётся OPEN, существующие PR — Draft.
