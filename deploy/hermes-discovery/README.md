# Hermes discovery runner и scheduler (Task 403)

`discovery_runner.py` — отдельный stdlib-only runtime для получения public RSS/JSON
Feed/HTML metadata. Он не импортирует hardened editorial worker и не имеет provider key,
YFC DB/intake secret, Telegram token, shell, browser, MCP, plugin или publish capability.
Source text всегда data: prompt/source instructions не исполняются.

Поток после отдельного Gate A:

```text
systemd timer
  -> hermes-discovery.service (source-only container)
  -> versioned YFC source definitions
  -> explicit HTTPS source hosts + DNS/redirect revalidation
  -> /var/lib/hermes/outbox/<stable-key>.json
  -> hermes-worker-drain.service (secrets только здесь)
  -> hardened editorial worker
  -> approved provider + HMAC YFC intake
```

## Source of truth

Canonical allowlist — `backend/fitminiapp_api/resources/news_sources.json`. Второго
редактируемого списка источников нет. Команда
`scripts/generate_hermes_source_definitions.py` проверяет canonical registry и рендерит
детерминированный `hermes-source-definitions-v1` с SHA-256 исходного файла и
`definitions_version=yfc-news-sources:<sha256>`. Этот файл является versioned deployment
artifact, его нельзя редактировать вручную. Перед установкой его SHA-256 должен быть подставлен
в оба systemd template как `HERMES_DISCOVERY_DEFINITIONS_SHA256`; external runtime отклоняет
файл с отсутствующим или несовпадающим digest. На target host он монтируется read-only в
`/opt/hermes/config/source-definitions.json`.

Тестовый `local_mock` envelope может содержать только loopback/`host.docker.internal` URLs и
существует исключительно в local E2E. Production/external mode принимает только HTTPS,
точные hosts из этого versioned файла, без IP literal, wildcard и arbitrary URL.

`pubmed-fitness-health` — включённый authoritative discovery/index source. Его RSS-запрос
ограничен MeSH major-topic терминами для физической формы, exercise therapy, спортивной
медицины и спортивного питания. Запись PubMed и abstract остаются только входными данными
для поиска: они не являются автоматически подтверждённым health claim. До редакционного
использования нужно проверить primary source, study design, limitations и applicability;
YFC intake сохраняет taxonomy/risk/manual_required boundary.

При deployment setup YFC additive bootstrap добавляет отсутствующие enabled canonical source rows
даже в непустую базу, но не перезаписывает существующие operator-managed source settings. Явное
изменение уже существующей строки выполняется только отдельной owner-approved source-allowlist
операцией.

## Discovery bounds and safety

- maximum 50 definitions, production unit ограничивает run 20 sources, 4 concurrent fetches;
- per-source timeout 10 seconds in the unit, response maximum 512 KiB, maximum 20 items;
- RSS/Atom, JSON Feed и HTML metadata имеют отдельные allowlisted MIME types;
- every source URL и every redirect revalidate exact host, scheme, port и DNS result;
  external DNS must resolve only to global addresses; localhost, RFC1918, loopback,
  link-local, reserved и cloud-metadata targets fail closed;
- redirects не следуются автоматически: максимум три hop с повторной allowlist/DNS проверкой;
- нет JavaScript/browser, source URL worker самостоятельно не fetch'ит;
- parser получает bounded bytes, а systemd `RuntimeMaxSec` прерывает зависший run;
- source outage записывается в bounded state и не превращается в «нет новостей» или quota/filler.

Discovery eligibility — это только высокий recall candidate generation. Unknown topic не
отбрасывается runner'ом; `topics` — provenance source definition. Taxonomy, risk,
`manual_required`, immutable draft revision и publication eligibility пересчитывает YFC intake.
Topic vocabulary в definitions покрывает направления Task 129, но enabled/disabled coverage
определяется только текущим canonical registry; discovery не добавляет фиктивные источники или
обязательную квоту публикаций.

## State, dedupe и restart

`/var/lib/hermes/state.json` хранит только version/hash, fetch metadata, error codes и bounded
candidate metadata; полный source packet живёт в outbox только до accepted/duplicate handoff.
Outbox пишется через fsync + atomic link/rename. Stable key вычисляется из
`source_id + canonical URL + content hash + event date`; filename, job id, idempotency key и
request nonce детерминированы этим key. Повторный timer run, crash/restart или uncertain worker
state не создаёт новый idempotency key автоматически. Pending job остаётся для повторной попытки;
после accepted/duplicate drain удаляет только этот outbox packet и отмечает state.

Два lock-файла предотвращают overlap discovery и overlap drain. Stale lock восстанавливается
только после bounded age threshold. Missed timer run не replay'ится (`Persistent=false`), а
следующий запуск снова применяет dedupe без publication quota.

## Установка и production topology Task 403

Поддерживаются режимы `separate-vm` и `colocated-isolated`. Для текущего запуска владелец
выбрал `colocated-isolated` на существующем YFC RU VPS: отдельная VM не создаётся. Hermes
production flag: `COLOCATED_ISOLATED_HERMES=yes`.
изолируется каталогами `/opt/hermes`, `/etc/hermes`, `/var/lib/hermes`, пользователем
`hermes` с UID/GID `10000:10000` и Docker-сетью `hermes-net`. В этой сети не должно быть
YFC-контейнеров или пересекающихся подсетей; Hermes не публикует порты и не получает YFC
volume, `.env`, БД, Redis, socket или host repository.

Установка выполняется только из exact merged release bundle. `source-definitions.json` должен
быть сгенерирован из canonical registry, а discovery и worker должны быть immutable digest
(repository digest или `sha256:<64 hex>` image ID); `latest` и floating tags запрещены.
Post-merge CI строит и сканирует `hermes-discovery` и `hermes-worker` images, публикуя refs,
выведенные общим `scripts/deployment_contract.py`. На target сначала нужно pull exact merged
ref и зафиксировать его digest или image ID; installer проверяет, что image metadata совпадает
с переданным immutable ref.
`scripts/hermes_colocation.py` копирует runtime и definitions в изолированные каталоги,
устанавливает `/etc/hermes/worker.env` с mode `0600`, рендерит units и запускает
`systemd-analyze verify`. Installer устанавливает только repository-owned таблицу
`inet hermes_egress`: policy действует на bridge `hermes-net`, разрешает DNS и точные
HTTPS-адреса canonical source/provider/intake, а остальные новые пакеты с этого bridge
отбрасывает. Перед каждым discovery policy атомарно refresh'ится; сбой DNS оставляет старую
policy и не расширяет egress. Глобальные defaults и YFC traffic не меняются, timer остаётся
disabled.

На co-located YFC публичный intake может быть преобразован Docker DNAT в приватный адрес
YFC до `forward` hook. Для этого единственного случая policy разрешает только пакет с
`ct original daddr` текущего публичного intake IP и TCP/443; прямой доступ к приватным
YFC/Docker subnet по-прежнему попадает под deny.

На co-located host guard перед каждой фазой требует: `MemAvailable >= 768 MiB`, used swap
`<= 512 MiB`, `load1 <= 1.50` на 2 vCPU и свободный `/var/lib/hermes >= 5 GiB`. Он использует
тот же canonical YFC deployment lock
`/srv/yfc/fit-mini-app/.artifacts/operations/deployments/deployment.lock` в shared-lock режиме
и не меняет его права. При нарушении возвращаются reason codes `insufficient_memory`,
`swap_pressure`, `high_load`, `insufficient_disk` или `yfc_deploy_active`; Hermes discovery и
worker не запускаются одновременно. Фазы ограничены `256 MiB/0.25 CPU` и `512 MiB/0.50 CPU`.

Пример установки (значения image и secret placeholders не являются production credentials):

```sh
python3 scripts/hermes_colocation.py install \
  --source-root /srv/yfc/fit-mini-app/current \
  --source-definitions /srv/yfc/fit-mini-app/current/.artifacts/tasks/403/evidence/source-definitions.json \
  --worker-env /etc/hermes/worker.env \
  --discovery-image registry.example/hermes-discovery@sha256:<64-hex> \
  --worker-image registry.example/hermes-worker@sha256:<64-hex> \
  --mode colocated-isolated
```

Перед включением timer проверить boundary без запуска job:

```sh
id hermes
id -nG hermes
docker network inspect hermes-net
docker network ls
systemd-analyze verify /etc/systemd/system/hermes-discovery.service /etc/systemd/system/hermes-worker-drain.service /etc/systemd/system/hermes-discovery.target /etc/systemd/system/hermes-discovery.timer
systemctl cat hermes-discovery.service hermes-worker-drain.service
systemctl status hermes-discovery.timer --no-pager
python3 /opt/hermes/hermes_egress.py validate
nft list table inet hermes_egress
python3 /opt/hermes/hermes_resource_guard.py check --phase discovery --mode colocated-isolated
```

До credentials, доказанной scoped egress policy и owner-approved external shadow timer можно
только установить и проверить. После этих gate активировать schedule одной командой:
`systemctl enable --now hermes-discovery.timer`; timer запускает worker drain, а его
`Requires/After` сначала запускают discovery. Missed runs не replay'ятся. Target остаётся
доступен для ручного bounded orchestration, но не используется как timer unit, чтобы active
target не блокировал следующие six-hour runs.

Если `/var/lib/hermes/state.json` был создан предыдущей дефектной версией от `root:root`, перед
первым запуском после обновления восстановить владельца state для контейнерного UID/GID:
`chown -R 10000:10000 /var/lib/hermes`.

`hermes_worker_drain.py` — host-side launcher; secrets передаются только worker container.
Discovery service не получает ни provider key, ни YFC HMAC secret. Рабочий runtime запускается
non-root, с read-only rootfs, no-new-privileges, drop capabilities и bounded cgroup.
