# V11-REC-01: резервная копия PostgreSQL на Windows

Актуальное решение владельца для [Issue #849](https://github.com/MikeMoore1337/your-fitness-coach/issues/849),
22.10.2026: обычные **незашифрованные `backup-YYYY-MM-DD.tar.gz`**. Age, BitLocker,
VHDX и отдельные ключи восстановления не нужны. Это заменяет прежнее требование age.
Архивы содержат данные БД открытым текстом после распаковки; доступ ограничивают права
каталогов и существующий защищённый SFTP. SHA-256 обнаруживает повреждение, но не
заменяет доверенный источник: SSH host key должен оставаться закреплённым.

Этот PR готовит исходники и шаблоны. Он не разрешает production dump/restore, перенос
пользовательских данных или включение расписаний. `BACKUP_RECOVERY=NOT_PROVEN` до
отдельно разрешённого восстановления реальной независимой копии с application smoke.

## 1. Формат и создание

Используется существующий `scripts/db_maintenance.py backup`: `pg_dump --format=custom
--no-owner --no-privileges` через существующий Compose service `db`. Каталог работающей
PostgreSQL, WAL, `.env`, credentials, ключи и host volumes в tar не попадают.
До публикации dump проверяется `pg_restore --list`. Это проверка формата, не восстановление.

В архиве ровно два обычных USTAR-файла:

- `database.dump`: PostgreSQL custom dump;
- `recovery.json`: версия формата, UTC начала создания dump, PostgreSQL major и Alembic revision.

Имя содержит дату МСК (UTC+03:00). Повторное создание в ту же дату отказывает до нового
pg_dump, если целевой архив уже существует. Обновление не перезаписывает дневную копию.
Промежуточные файлы находятся вне SFTP export, в приватном временном каталоге backup root;
они удаляются при успехе и ошибке. Публикация архива выполняется rename на том же томе,
затем atomic manifest и последним — `index.json`, служащий признаком завершения.
Linux publisher сохраняет существующий `flock` от параллельной публикации.

Manifest/index **v3**, `archive_format=tar-gzip-pg-custom`, содержат размер и SHA-256 всего
`.tar.gz`, время создания/публикации, статус `format_verified_pg_restore_list`. Manifest
также содержит revision/image identity, если переданы существующие `YFC_RELEASE_SHA`,
`YFC_BACKEND_IMAGE_DIGEST`, `YFC_BOT_IMAGE_DIGEST`; иначе identity явно неизвестна.
`restore_status=not_run` не меняется от успешного скачивания.

Команда для будущей разрешённой активации, **не выполнять сейчас**:

```sh
python3 scripts/db_maintenance.py backup \
  --publish-dir .artifacts/operations/backups/offhost-tar \
  --retain-published 7
```

Без `--publish-dir` прежний raw `.dump` helper для локального safety backup/restore
сохраняется. Его существующие вызывающие скрипты не меняются. Для новых независимых
копий всегда использовать публикацию `.tar.gz`.

## 2. Переход без удаления старых копий

Не менять установленные конфигурации, `.age`/`.dump`, старые manifest/index, SSH identity,
`known_hosts` и age-toolchain. Они сохраняются для отдельно разрешённого использования.
Новый publisher не принимает legacy index v1/v2 и отказывает при legacy/неожиданных файлах
в новом export. Смешивать форматы или автоматически переконвертировать копии нельзя.

Для перехода подготовить новый VPS-каталог `offhost-tar` и Windows-каталог
`D:\YFC-Backups\tar-gz`, скопировать три скрипта из одного проверенного commit:
`db_maintenance.py` и `backup_manifest.py` на VPS; `windows_backup_pull.ps1` и
`backup_manifest.py` на Windows. Сохранить старые исходники и конфигурации отдельно
до проверки нового пути. Не менять target существующего задания поверх старой конфигурации.
Старая Windows-конфигурация с `encryption_at_rest` явно отклоняется новым runner.
Legacy-файлы в локальном каталоге игнорируются, не учитываются в числе исправных и не ротируются.

Частичный сбой publication оставляет старый index действующим и старые копии сохранными.
Новый orphan без manifest/index не считается исправным. Не удалять его автоматически:
остановить расписание, проверить digest/содержимое и отдельно разрешить исправление.
Windows умеет завершить прерванное продвижение, когда архив без manifest уже совпадает
с проверенным удалённым объектом. Несовпадающий локальный файл не перезаписывается.

## 3. Windows PULL и SFTP

Шаблон: [windows-pull.config.example.json](v11-rec-01-off-host-backup-recovery/windows-pull.config.example.json).
Для проверки tar Windows использует **Python 3.10+ и только стандартную библиотеку**;
пакеты через pip, age и WSL не нужны. Указать абсолютный `python_path` к доверенному
существующему Python, без Windows Store alias. Не передавать в конфигурации passwords.

Сохранить существующие dedicated read-only SFTP account, chroot и SSH host key.
Не менять глобальный sshd, credentials, shell/TTY/forwarding или ACL в рамках этого PR.
Внутри существующего chroot оператор после отдельного разрешения публикует новый
`/offhost-tar` с completed archives, manifest и index. Publisher имеет запись, SFTP user —
только list/get; приватный staging остаётся вне chroot. `remote_root` в JSON задаётся
относительно **видимого SFTP root**, а не абсолютного host path.

Runner сохраняет `StrictHostKeyChecking=yes`, отдельный `UserKnownHostsFile`,
`GlobalKnownHostsFile=NUL`, `BatchMode=yes`, `IdentitiesOnly=yes`, `IdentityAgent=none`,
`-F NUL`, dedicated identity. Не заменять pin результатом непроверенного `ssh-keyscan`.
Проверка нового пути после разрешения: list/get synthetic archive успешно;
put/rename/remove/traversal/shell/TTY/forwarding запрещены; неверный host key отклоняется.
SSH key — ключ доступа SFTP, он сохраняется; отдельного ключа расшифрования больше нет.

Runner скачивает только index/новые объекты через outbound SFTP во временный каталог
на том же диске. До продвижения проверяет manifest/index, size/SHA-256, gzip целиком,
два допустимых tar member и соответствие встроенных metadata sidecar. Нет `extractall`:
при распаковке читаются только фиксированные имена. Абсолютные пути, `..`, Windows paths,
ссылки, устройства, FIFO, каталоги, PAX/longname extensions, дубликаты, лишние файлы,
посторонний хвост, плохой checksum/CRC и усечение отклоняются. Лимит обычного USTAR member
— менее 8 GiB; больший dump отклонится до публикации. Перед таким ростом потребуется
явное расширение формата и тестов, не молчаливый fallback.

```powershell
& 'C:\YFC\Python\python.exe' --version
& 'C:\YFC\scripts\windows_backup_pull.ps1' -Mode Pull -ConfigPath 'C:\YFC\windows-pull-tar.config.json'
& 'C:\YFC\scripts\windows_backup_pull.ps1' -Mode Status -ConfigPath 'C:\YFC\windows-pull-tar.config.json'
```

`Status` проверяет локальные копии, ничего не скачивает. Логи/status не содержат данных БД,
ключей или native stderr. Сохраняются отдельные состояния локальной копии, свежести,
последнего Pull и последней ошибки. Сбой сети не делает исправную старую копию повреждённой.

## 4. Расписание, хранение и предупреждение

| Параметр | Значение |
| --- | --- |
| Создание VPS | ежедневно 03:00 МСК = 00:00 UTC |
| Windows PULL | каждый час XX:30, catch-up после включения/сети |
| Хранение | 7 суток на обеих сторонах |
| Защищённый минимум | последние 2 исправные копии, даже старше 7 суток |
| Свежесть | `STALE` только при возрасте **больше 26 часов** от создания dump |

VPS вращает только повторно проверенные записи своего v3 index после успешной публикации.
Повреждение прежней indexed копии прекращает публикацию и удаление. Windows вращает только
проверенные tar.gz/sidecar после успешного Pull; повреждённые/legacy файлы не удаляет.
Конфигурация не позволяет уменьшить минимум ниже двух. Выключенный PC может пропустить
новые копии после истечения VPS retention: две сохранённые старые копии не доказывают RPO.

[Windows Task Scheduler XML](v11-rec-01-off-host-backup-recovery/windows-pull-task.example.xml)
содержит `PT1H`, старт `00:30+03:00`, `StartWhenAvailable` и **оба Enabled=false**.
Не импортировать и не включать задачу сейчас. Существующую задачу также не изменять.
Пример для будущего VPS timer, который сейчас **не устанавливается и не включается**:

```ini
[Timer]
OnCalendar=*-*-* 00:00:00 UTC
Persistent=true
AccuracySec=1s
Unit=yfc-backup-tar.service
```

Service должен запускаться из существующего app root под утверждённым publisher identity,
`UMask=0077`; использовать команду раздела 1. Сам systemd timer не имеет Enabled-поля:
disabled означает отсутствие `systemctl enable/start` и проверенный inactive state.
Существующий timer оставить disabled/inactive; не заменять его автоматически.

Коды: `0 HEALTHY`, `10 STALE`, `11 MISSING`, `12 CORRUPTED`, `20 HOST_KEY`,
`21 AUTHENTICATION`, `22 NETWORK`, `23 DISK_FULL`, `24 LOCKED`, `25 CONFIG_INVALID`,
`26 PROMOTE_FAILED`, `27 UNEXPECTED`. Код 10 и status JSON — локальное предупреждение.
Доставка уведомлений на выключенном PC не доказана; перед запуском согласовать канал,
который действительно увидит владелец, и проверить stale/failure notification.

## 5. Безопасное восстановление

Выбрать конкретную PC-held копию и соответствующий manifest из доверенного SFTP source.
Не запускать SQL из недоверенного dump: SHA не является авторизацией содержимого.
Проверить свободное место для распакованного dump и БД, закрытые ACL recovery-каталога,
PostgreSQL major, доверенный image и отсутствие production network/volumes/credentials.

```powershell
$python = 'C:\YFC\Python\python.exe'
$archive = 'D:\YFC-Backups\tar-gz\backup-YYYY-MM-DD.tar.gz'
$manifest = "$archive.manifest.json"
$restore = 'D:\YFC-Recovery\NEW-EMPTY-DIRECTORY'
& $python -I 'C:\YFC\scripts\backup_manifest.py' $archive --manifest $manifest --output-dir $restore
if ($LASTEXITCODE -ne 0) { throw 'Archive rejected; preserve original and stop' }
```

`--output-dir` должен отсутствовать: helper создаёт его после полной проверки. Он не
перезаписывает существующий каталог. Ошибка ввода-вывода может оставить частичный output;
не использовать его и не удалять оригинальный архив. Передать `database.dump` бинарным
файлом в **новую изолированную non-production PostgreSQL** того же major. Не использовать
PowerShell text pipeline для binary. Внутри изолированного контура:

```sh
pg_restore --list /restore/database.dump
createdb --template=template0 yfc_recovery
pg_restore --dbname=yfc_recovery --no-owner --no-privileges --exit-on-error \
  --single-transaction /restore/database.dump
```

Проверить Alembic revision до миграций, согласованные counts/invariants, binary columns,
FK/unique constraints и sequence; затем отдельно разрешённый application smoke на exact
release/image. Не запускать bot/background writers/provider egress. Зафиксировать начало,
окончание, digest, версии, команды/коды и измеренный RTO/RPO по заранее согласованной методике.
Не выбирать targets после результата. DNS/cutover и production restore сюда не входят.
Оригинал с Windows сохраняется до отдельного разрешения на удаление.

## 6. Проверки и оставшиеся действия

```powershell
python -m pytest -o addopts= tests/test_backup_manifest.py tests/test_db_maintenance.py -q
pwsh -NoProfile -File scripts/windows_backup_pull_selftest.ps1 -PythonPath 'C:\PATH\python.exe'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/windows_backup_pull_selftest.ps1 -PythonPath 'C:\PATH\python.exe'
```

Python-тесты не обращаются к настоящей БД и не запускают pg_dump. Windows self-test работает
с синтетическими локальными файлами и fake SFTP, проверяет pinned-key options, corruption,
offline/catch-up, lock, disk, статус, границу 26 часов и last-two retention. Настоящий
SFTP и изолированный pg_restore требуют отдельного синтетического integration evidence;
никакой synthetic PASS не доказывает production recovery.

До реального запуска остаются: review/merge PR; доставка проверенных host-side scripts
и новой конфигурации без удаления старой; существующие SFTP/host-key/ACL проверки для нового
каталога; privacy/data-location решение (#707/#711) для реальных данных; согласованные
RPO/RTO и уведомления; отдельное разрешение на настоящий backup/PULL/drill; затем отдельное
включение Windows-задачи и VPS timer и наблюдение первого дневного цикла.

`env change required: no` для приложения/PostgreSQL. Host-side нужны новый export path,
`python_path`, новая Pull-конфигурация и будущая команда расписания без age flags.
Приложение, PostgreSQL, существующие архивы/конфигурации и выключенные расписания этим PR
не изменяются. Encryption/key-recovery gates сняты текущим решением владельца.

Исторические решения и проверки остаются в [PR #1125](https://github.com/MikeMoore1337/your-fitness-coach/pull/1125)
и [PR #1123](https://github.com/MikeMoore1337/your-fitness-coach/pull/1123).
Их age-команды не применять к новым архивам. Полный clean-host recovery acceptance #849,
включая приложение и независимую реальную копию, этим изменением не закрывается.
