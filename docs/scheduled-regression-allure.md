# Scheduled regression и закрытые Allure-отчёты

Документ описывает единственный scheduled-контур YFC и его закрытые HTML-отчёты. Он
дополняет быстрый PR CI и не заменяет targeted-проверки, QA, real-device или production
validation. Внешние настройки VPS, DNS, Cloudflare и GitHub secrets в рамках Task 107 до
следующего owner checkpoint не выполняются.

## Топология и ownership

Владелец расписания — .github/workflows/ci.yml. Второго nightly/weekly workflow для тех же
suite нет.

| Запуск | Cron (UTC) | Время Europe/Moscow | Профиль |
| --- | --- | --- | --- |
| Daily | 17 2 * * * | каждый день 05:17 | daily-regression |
| Weekly | 43 3 * * 0 | воскресенье 06:43 | weekly-exhaustive |

workflow_dispatch запускается только на master и принимает run_kind: daily или weekly.
Неизвестный cron не классифицируется и завершается ошибкой. Выбор профиля и периода отчёта
находится в scripts/scheduled_regression.py, а соответствие профилей CI-группам — в
scripts/ci_contract.py.

pr-critical остаётся обычным blocking CI. Daily/Weekly не являются его dependency и не входят
в ожидание merge или production deploy.

### Профили

Daily запускает bounded deterministic набор:

- quality;
- frontend-checks;
- frontend-e2e (4 shard, Chromium);
- frontend-mobile-regression (Chromium + WebKit);
- python-tests (4 shard, PostgreSQL test stack);
- migrated-stack (Alembic, migrated API и browser smoke);
- critical-smoke;
- workflow-config.

Weekly включает Daily и дополнительно запускает policy, dependency audit, расширенный mobile
набор, frontend-cross-browser (Chromium + Firefox + WebKit), image/deployment/container
contracts. Allure-агрегатор ожидает только suite, которые фактически производят results:
frontend-checks, frontend-e2e, frontend-mobile-regression, python-tests, migrated-stack, а для
Weekly также frontend-mobile-regression-extended и frontend-cross-browser. Native policy, audit и
deployment результаты остаются в обычных CI jobs.

## Локальное воспроизведение

Проверить routing и retention без запуска полного scheduled набора:

    & .venv\Scripts\python.exe scripts\scheduled_regression.py contract
    & .venv\Scripts\python.exe scripts\scheduled_regression.py resolve --event schedule --schedule-cron "17 2 * * *"
    & .venv\Scripts\python.exe scripts\scheduled_regression.py resolve --event schedule --schedule-cron "43 3 * * 0"

Команды существующих suite не меняются:

    npm --prefix frontend ci
    npm --prefix frontend run check
    npm --prefix frontend run e2e:ci
    npm --prefix frontend run e2e:mobile-regression
    npm --prefix frontend run e2e:mobile-regression:extended
    npm --prefix frontend run e2e:cross-browser
    & .venv\Scripts\python.exe scripts\run_pytest.py backend\tests bot\tests -q -n 4 --dist=worksteal

Для локального report-only прогона сначала установить scheduled-only adapters в
frontend\scheduled-report, затем использовать только пути под .artifacts\runtime\tests. SSH
publisher и Cloudflare credentials для локальной проверки не нужны; dry-run публикации не
подключается к VPS. Полный Weekly локально автоматически не запускается.

Пример безопасной локальной проверки publisher без SSH:

    npm --prefix frontend\scheduled-report ci --omit=peer --ignore-scripts --no-audit --no-fund
    & .venv\Scripts\python.exe scripts\publish_allure_report.py publish --report-root .artifacts\runtime\tests\allure-report --metadata .artifacts\runtime\tests\allure-report-metadata.json --publication .artifacts\runtime\tests\allure-publication.json --dry-run

## Aggregation в GitHub Actions

Каждый parallel job пишет в отдельный result directory. Composite action
.github/actions/upload-allure-results упаковывает его в tar.gz, шифрует AES-256-CBC с PBKDF2 и
проверкой HMAC, а затем загружает только короткоживущий encrypted Actions artifact. Его
retention-days по умолчанию равен 3. Plaintext results, HTML, screenshots и traces не
используются как межjob transport и не публикуются в repository artifacts.

Изолированный scheduled-report job:

1. скачивает artifacts только с текущим run_id;
2. проверяет целостность и расшифровывает bundles;
3. добавляет suite/tier/run-kind labels, browser и synthetic dataset parameters;
4. проверяет attachments и generated report на traversal, symlink и чувствительные строки;
5. генерирует Allure HTML независимо от verdict тестовых jobs;
6. валидирует HTML и передаёт один tar.gz stream через SSH publisher;
7. на VPS атомарно устанавливает immutable report, затем обновляет latest и root index;
8. пишет прямую ссылку в GitHub Actions Summary.

Ожидаемые пути на закрытом origin:

    https://allure.your-fitness-coach.ru/
    https://allure.your-fitness-coach.ru/daily/latest/
    https://allure.your-fitness-coach.ru/daily/YYYY-MM-DD/<run-id>/
    https://allure.your-fitness-coach.ru/weekly/latest/
    https://allure.your-fitness-coach.ru/weekly/YYYY-Www/<run-id>/

Immutable path не перезаписывается. latest и history содержат только опубликованные entries.
При missing/malformed suite создаётся synthetic failed integrity case и report получает статус
incomplete; ссылка может быть опубликована для диагностики, но финальный scheduled gate
остаётся красным. При test failure report публикуется с честными failed counts, а исходный
workflow также остаётся красным.

## VPS-based hosting contract

Task 107 использует существующий production VPS как отдельное хранилище и origin. R2 bucket,
R2 API credentials, R2-compatible publisher и отдельный Worker для report origin не используются.
YFC backend, application worker, bot, PostgreSQL и их публичный Caddy не хранят и не выдают
отчёты.

Целевая схема:

    GitHub Actions scheduled-report
      -> dedicated SSH key + pinned known_hosts
      -> forced command yfc-allure-publish-v1
      -> /srv/yfc-allure-reports на VPS
      -> allure-report-origin (Caddy :8080, read-only mount)
      -> Cloudflare Tunnel (cloudflared-allure)
      -> Cloudflare Access
      -> https://allure.your-fitness-coach.ru

allure-report-origin и cloudflared-allure включаются только Compose profile
allure-reports. У origin нет host ports, он подключён только к internal Docker network
allure_reports. Connector подключён к allure_reports и к отдельной allure_egress network,
которая не содержит application containers. Existing caddy/edge/backend/PostgreSQL topology не
меняется. В контейнер origin report volume монтируется read-only, Caddy запускается как
1501:1501, admin API выключен.

deploy/allure-report-origin/Caddyfile:

- принимает только GET и HEAD, остальные методы дают 405;
- не включает browse, поэтому directory listing выключен;
- отдаёт private, no-store, nosniff, no-referrer;
- не выдаёт /.publish.lock, /.staging, /metadata и отсутствующие пути;
- оставляет latest обычным atomic-generated index.html, а не symlink;
- возвращает controlled 404 после удаления expired immutable directory.

Публикация использует scripts/publish_allure_report.py в GitHub Actions и
scripts/allure_report_origin.py на VPS. Publisher сначала валидирует report, затем передаёт
header и tar.gz в SSH stdin. На VPS forced command проверяет protocol/header, отклоняет
traversal, symlink, hardlink, device и превышение size limit, распаковывает во внутренний
.staging, сериализует публикации через .publish.lock, делает os.replace в immutable directory и
только после этого атомарно пишет metadata/index/latest. latest никогда не указывает на staging
или неполный report.

## Cloudflare и Access diff после approval

Эта секция — точный план внешнего изменения; в текущем checkpoint он не выполнялся.

1. Создать один Tunnel для hostname allure.your-fitness-coach.ru и получить connector token.
   Token хранится только в VPS .env как ALLURE_CLOUDFLARED_TUNNEL_TOKEN; в GitHub и
   application secrets он не копируется.
2. В tunnel ingress добавить:

       hostname: allure.your-fitness-coach.ru
       service: http://allure-report-origin:8080

   Catch-all для других hostnames не добавляется.
3. DNS diff: создать managed proxied CNAME
   allure.your-fitness-coach.ru -> <tunnel-id>.cfargotunnel.com. A/AAAA на 92.118.115.93 для
   report hostname не создаётся; host port для origin не открывается.
4. Создать Cloudflare Access application на точный hostname. Allow policy содержит только
   owner/team email allowlist через выбранный identity provider. При отсутствии совпадения
   Access оставляет default deny. Include Everyone, public bypass, shared-link access,
   незащищённый hostname и широкое wildcard-правило не добавляются.
5. Проверить, что Access policy применяется ко всему hostname, включая /, /daily/*, /weekly/*
   и direct immutable URLs. В Access/Tunnel dashboard не включать публичный unauthenticated
   route.

Итоговый DNS diff содержит только CNAME Tunnel; прямого DNS/IP bypass нет. Это не является
подтверждением внешнего применения: DNS, Tunnel и Access остаются owner-gated.

### Альтернатива: direct HTTPS через существующий Caddy

Если Cloudflare Tunnel/Access не используется, тот же report origin можно публиковать через
уже работающий `caddy` на VPS. В этом варианте authoritative DNS остаётся у текущего DNS-
провайдера, а `allure.your-fitness-coach.ru` получает A/AAAA на VPS. Публичный Caddy принимает
только HTTPS, требует `basic_auth argon2id` и проксирует запросы в `allure-report-origin:8080` через
внутреннюю сеть `allure_reports`. Host port для origin по-прежнему не открывается.

Для варианта Caddy в production `.env` задаются только:

    ALLURE_PUBLIC_HOSTNAME=allure.your-fitness-coach.ru
    ALLURE_BASIC_AUTH_USER=<owner-login>
    ALLURE_BASIC_AUTH_HASH=<argon2id-hash>

`ALLURE_BASIC_AUTH_HASH` получают командой `caddy hash-password --algorithm argon2id`; plaintext-пароль не хранится
в репозитории и не передаётся publisher-пользователю. Пустой hostname отключает маршрут, а
заданный hostname без user/hash приводит к fail-closed ошибке запуска Caddy. Cloudflare token
и `cloudflared-allure` для этой схемы не нужны.

Этот вариант не скрывает IP VPS и не даёт Cloudflare Access/WAF/DDoS-защиту. Доступ к origin
остаётся только через публичный Caddy с HTTPS и Basic Auth; direct `:8080`, directory listing,
write methods и служебные пути origin не публикуются.

## GitHub names и least privilege

Новые/используемые GitHub Actions secrets (значения не приводятся):

- ALLURE_REPORT_ENCRYPTION_KEY — уже используемый ключ encrypted bundles;
- ALLURE_REPORT_SSH_PRIVATE_KEY — отдельный ed25519 private key publisher;
- ALLURE_REPORT_SSH_KNOWN_HOSTS — pinned host-key entry для app.your-fitness-coach.ru.

GitHub Actions variables:

- ALLURE_REPORT_SSH_HOST — app.your-fitness-coach.ru;
- ALLURE_REPORT_SSH_PORT — 22;
- ALLURE_REPORT_SSH_USER — yfc-allure-publisher.

PROD_SSH_KEY, PROD_SSH_KNOWN_HOSTS, CLOUDFLARED_TOKEN, application .env и любые production
deployment credentials в scheduled publisher не передаются. В workflow явно используются
BatchMode=yes, IdentitiesOnly=yes, IdentityAgent=none, StrictHostKeyChecking=yes,
GlobalKnownHostsFile=none, отдельный UserKnownHostsFile, PasswordAuthentication=no,
KbdInteractiveAuthentication=no и shell=False. Значение StrictHostKeyChecking=no отсутствует.

Минимальные права dedicated publisher:

- отдельный Linux user yfc-allure-publisher, UID/GID 1501;
- locked password, без sudo, без docker group и без application secrets;
- одна authorized_keys entry с forced command /usr/bin/python3 /srv/yfc-allure/publisher.py,
  restrict и no-user-rc;
- forced command принимает только protocol publication и удаляет/создаёт объекты только в
  /srv/yfc-allure-reports;
- SSH shell, PTY, agent forwarding, TCP forwarding, X11 forwarding и user rc отключены;
- этот user не может запускать Compose, читать /root/fit-mini-app/.env или менять Caddy, Tunnel
  и application runtime.

## VPS paths и permissions

После owner-approved bootstrap ожидается:

| Путь | Owner/mode | Назначение |
| --- | --- | --- |
| /srv/yfc-allure | root:root, 0755 | immutable publisher script copy |
| /srv/yfc-allure/publisher.py | root:root, 0755 | forced-command wrapper |
| /srv/yfc-allure/allure_report_origin.py | root:root, 0755 | protocol/retention implementation |
| /srv/yfc-allure-reports | yfc-allure-publisher:yfc-allure, 0750 | only report storage root |
| /srv/yfc-allure-reports/.publish.lock | yfc-allure-publisher:yfc-allure, 0640 | cross-process publication lock, never served |
| /srv/yfc-allure-reports/metadata | yfc-allure-publisher:yfc-allure, 0750 | server-authoritative index |
| report directories | yfc-allure-publisher:yfc-allure, 0750 | immutable HTML/assets |
| report files | yfc-allure-publisher:yfc-allure, 0640 | static files |
| /root/fit-mini-app/.env | root:root, 0600 | existing application and connector config |

Caddy sees the report root only through a read-only bind mount. The static origin and connector
have no host-published ports, and the origin network has internal: true; the only public route is
Tunnel plus Access.

## Retention, storage and budget

| Данные | Retention/limit |
| --- | ---: |
| Daily HTML/assets | 14 календарных дней |
| Weekly HTML/assets | последние 4 отчёта и не более 35 календарных дней |
| Raw encrypted Actions bundles | 3 дня |
| Один encrypted bundle | до 50 MiB |
| Один generated report | до 100 MiB |

Cleanup выполняется server-side в том же forced publisher после каждой публикации. Источник
истины — /srv/yfc-allure-reports/metadata/index.json; stale paths попадают в cleanup_pending,
а следующая Daily/Weekly публикация повторяет cleanup. Отчёт сначала устанавливается целиком,
затем обновляются root index/latest, поэтому прямой URL не указывает на staging. После
успешного удаления expired immutable directory Caddy возвращает controlled 404. Отдельный
daemon, cron, database table и backend endpoint для этого не нужны.

Read-only audit текущего VPS зафиксировал:

- 92.118.115.93, 1 vCPU, RAM около 1.0 GB;
- root filesystem 15,759,073,280 bytes total, 11,977,646,080 used, 3,764,649,984 available
  (77% used);
- /root/fit-mini-app около 501 MiB, /var/lib/docker около 2.36 GiB;
- existing app caddy слушает host 80/443; backend и PostgreSQL опубликованы только на loopback;
  cloudflared profile существует, но сейчас не запущен;
- new origin/connector containers ограничены 64m каждый и не публикуют host ports.

Теоретический active HTML bound — 18 отчётов (14 Daily + 4 Weekly) по 100 MiB, примерно
1.8 GiB, плюс metadata и до 100 MiB staging. Publisher сохраняет минимум 2 GiB свободного
места и fail-closed отклоняет публикацию до нарушения резерва. При текущих 3.76 GB free полный
теоретический bound с резервом не гарантирован; перед включением нужно измерить фактический
размер первого report и подтвердить headroom. Raw results на VPS не сохраняются: encrypted
bundles живут только в Actions artifact с retention 3 дня.

Дополнительный billable storage/service в этой архитектуре не создаётся: R2 bucket, R2 API,
отдельный Worker и новый storage provider отсутствуют. Используются уже оплачиваемый VPS, его
Docker/Compose и Cloudflare Tunnel/Access account capability. Расширение платного тарифа,
новый billing/payment storage или новая платная Cloudflare service не требуется; итоговая
добавочная стоимость по решению владельца — 0.

## Точные owner commands после approval

Команды ниже являются планом и до следующего explicit approval не выполнялись.

### 1. Создать isolated publisher user и каталоги на VPS

    set -eu
    test -z "$(getent passwd 1501)" || { echo 'UID 1501 is already occupied' >&2; exit 1; }
    test -z "$(getent group 1501)" || { echo 'GID 1501 is already occupied' >&2; exit 1; }
    groupadd --system --gid 1501 yfc-allure
    useradd --system --uid 1501 --gid yfc-allure \
      --home-dir /srv/yfc-allure --shell /bin/bash yfc-allure-publisher
    passwd --lock yfc-allure-publisher
    install -d -o root -g root -m 0755 /srv/yfc-allure
    install -d -o yfc-allure-publisher -g yfc-allure -m 0750 /srv/yfc-allure-reports
    install -d -o yfc-allure-publisher -g yfc-allure -m 0750 /srv/yfc-allure-reports/metadata
    install -o root -g root -m 0755 \
      /root/fit-mini-app/current/scripts/allure_report_origin.py \
      /srv/yfc-allure/allure_report_origin.py
    install -o root -g root -m 0755 \
      /root/fit-mini-app/current/deploy/allure-report-origin/publisher.py \
      /srv/yfc-allure/publisher.py

Если имя пользователя/группа уже существуют, нужно отдельно проверить их exact UID/GID и
permissions; команды не должны молча менять чужого владельца.

### 2. Создать dedicated SSH key и forced key entry

Локально, на доверенной машине владельца:

    ssh-keygen -t ed25519 -f ./yfc-allure-publisher -C yfc-allure-publisher -N ''

Публичный ключ добавляется на VPS одной строкой (placeholder заменяется реальным ключом):

    install -d -o yfc-allure-publisher -g yfc-allure -m 0700 /srv/yfc-allure/.ssh
    printf '%s\n' 'command="/usr/bin/python3 /srv/yfc-allure/publisher.py",restrict,no-user-rc ssh-ed25519 <PUBLIC_KEY> yfc-allure-publisher' \
      > /srv/yfc-allure/.ssh/authorized_keys
    chown yfc-allure-publisher:yfc-allure /srv/yfc-allure/.ssh/authorized_keys
    chmod 0600 /srv/yfc-allure/.ssh/authorized_keys

В ALLURE_REPORT_SSH_KNOWN_HOSTS записывается pinned строка вида
app.your-fitness-coach.ru ssh-ed25519 <VERIFIED_BASE64_HOST_KEY>. <VERIFIED_BASE64_HOST_KEY>
нужно получить и сверить с fingerprint из доверенной VPS/provider console; один лишь
непроверенный ssh-keyscan источником доверия не является.

### 3. Добавить connector token в существующий VPS .env

В /root/fit-mini-app/.env, с сохранением root:root и mode 0600, добавить только необходимые
значения:

    ALLURE_REPORT_ORIGIN_UID=1501
    ALLURE_REPORT_ORIGIN_GID=1501
    ALLURE_REPORT_ORIGIN_MEMORY_LIMIT=64m
    ALLURE_CLOUDFLARED_MEMORY_LIMIT=64m
    ALLURE_CLOUDFLARED_TUNNEL_TOKEN=<TUNNEL_CONNECTOR_TOKEN>

CLOUDFLARED_TOKEN existing application profile не переиспользуется. Значение token не попадает в
GitHub secret publisher и не передаётся yfc-allure-publisher.

### 4. Включить только новый Compose profile

После доставки commit Task 107 и проверки места:

Перед запуском проверить, что значения CADDY_IMAGE и CLOUDFLARED_IMAGE в существующем .env
зафиксированы на согласованных immutable image digests; mutable local tags из .env.example для
production не использовать.

    cd /root/fit-mini-app/current
    docker compose --profile allure-reports config >/dev/null
    docker compose --profile allure-reports up -d allure-report-origin cloudflared-allure
    docker compose --profile allure-reports ps
    docker compose --profile allure-reports logs --tail=100 allure-report-origin cloudflared-allure

Ожидается только allure-report-origin и cloudflared-allure; existing application services,
database и public Caddy этим профилем не перезапускаются.

### 5. Заполнить GitHub Actions secrets/variables

В repository Actions settings добавить names из раздела выше: три secrets и три variables.
ALLURE_REPORT_SSH_PRIVATE_KEY содержит private key из шага 2, а ALLURE_REPORT_SSH_KNOWN_HOSTS —
проверенную pinned host-key строку. Не добавлять R2 names, Cloudflare token или PROD_SSH_KEY в
scheduled job.

### 6. Проверить Access/Tunnel smoke после внешнего изменения

Owner вручную проверяет через Access identity:

    https://allure.your-fitness-coach.ru/
    https://allure.your-fitness-coach.ru/daily/latest/

Без разрешённой identity ожидается Access deny; direct IP 92.118.115.93 не является report
route. Публичный bypass и Everyone allow policy не допускаются.

## Incident, rollback и rotation

- Ошибка decrypt, aggregation, generation, validation или publication не превращается в зелёный
  test verdict; finalize оставляет scheduled job красным.
- Для application rollback достаточно вернуть workflow/release commit Task 107. Backend, runtime
  и PostgreSQL не затрагиваются.
- Для report-only rollback остановить только:

      cd /root/fit-mini-app/current
      docker compose --profile allure-reports stop cloudflared-allure allure-report-origin

- В Cloudflare отключить exact public hostname/Access application и удалить только exact Tunnel
  route/CNAME после сохранения нужного evidence. Не менять app DNS wildcard.
- Отозвать dedicated Tunnel token, удалить dedicated authorized_keys line, затем при
  необходимости удалить exact /srv/yfc-allure-reports после отдельного backup/confirmation.
  Existing app services, /root/fit-mini-app, PostgreSQL и deployment credentials не удалять.
- При rotation сначала создать новый SSH key/token, проверить одну publication, затем отозвать
  старый. Values ключей не записывать в task evidence, logs или report metadata.

## Границы evidence

Scheduled browser checks используют synthetic/local fixtures. mocked TMA не является real
Telegram Android/iOS evidence, локальный report не является production validation, а Weekly не
вызывает live paid AI provider и не использует real user sessions, prompts, files или database
rows.
