# Telegram editorial automation (Task 129)

## Status and ownership

The canonical source of truth remains the YFC backend.  Hermes is an optional external discovery
and drafting worker behind `POST /api/v1/hermes/editorial/intake`; it is not a publisher, source
database, Telegram bot runtime or production shell.

The intake flag is off by default:

```text
HERMES_INTAKE_ENABLED=false
NEWS_AUTO_PUBLISH_LOW_RISK=false
NEWS_INGESTION_ENABLED=false
NEWS_LEGACY_SOURCE_FETCH_ENABLED=true
NEWS_PUBLICATION_ENABLED=false
```

`NEWS_LEGACY_SOURCE_FETCH_ENABLED=true` — обратно совместимое локальное значение по умолчанию. В
production-конфигурации Hermes оно нормализуется в `false`, а `NEWS_INGESTION_ENABLED=true`
остаётся включённым для downstream-этапов YFC. Этот флаг отключает только legacy-получение
источников YFC и генерацию candidate-draft; intake Hermes, обработка изображений, очередь review,
ручное редактирование/подтверждение, планирование и управление публикацией продолжают работать.
Его нельзя реализовывать изменением `NEWS_INGESTION_ENABLED`.

При `NEWS_LEGACY_SOURCE_FETCH_ENABLED=false` в review downstream допускаются только revisions с
canonical marker `evidence_metadata["submitted_by"] == "hermes_narrow_intake"`. Уже сохранённые
legacy drafts и clusters не удаляются и не переводятся обратно из `deferred`; queued/processing
legacy `NewsReviewDelivery` безопасно отменяются до Telegram send, а новые legacy delivery и
preview upgrade не создаются. Hermes owner-edited revisions сохраняют marker и продолжают
проходить review flow. Действие «Перегенерировать текст» для Hermes повторно ставит принятую
immutable revision в review flow и не включает legacy candidate generation.

Для editorial intake действует rolling-окно свежести в 60 дней: границы включаются, будущие и
неизвестные даты отклоняются. Это product/discovery heuristic, а не медицинская норма. Owner-
карточки отправляются из очереди пачками до 5 различных drafts в окнах 08:00, 13:00 и 18:00
по `Europe/Moscow`; если доступно меньше пяти, отправляется доступное количество без filler.
Пятнадцатиминутное окно допускает обычный polling worker и не меняет расписание самого Hermes.
Очередь, изображения и другие downstream-этапы продолжают обрабатываться между слотами, но новые
Telegram review cards вне этих окон не отправляются.

Hermes может передавать владельцу полноценный exact preview и управляющую карточку для тем,
которые требуют ручного решения: AAS/фармакология/пептиды/БАДы и дозировки. Такие карточки не
включаются в autopublish: `NEWS_AUTO_PUBLISH_LOW_RISK` остаётся `false`, а существующие
publication quality gates сохраняют право скрыть кнопку публикации до редактирования текста.
Это расширяет только ручной editorial recall; отсутствие exact image/caption, malformed provider
response, fallback-заглушка, неподтверждённые числа и другие технические blockers по-прежнему
fail-closed и не отправляются владельцу как будто это готовая новость.

После production release целевые значения для разделения контуров такие:

```text
NEWS_INGESTION_ENABLED=true
NEWS_LEGACY_SOURCE_FETCH_ENABLED=false
NEWS_AUTO_PUBLISH_LOW_RISK=false
```

`NEWS_INGESTION_ENABLED` поддерживает downstream-обработку; `NEWS_PUBLICATION_ENABLED` и
остальные существующие `NEWS_*` flags не меняются этим follow-up.

Telegram Bot API polling continues to have one owner.  No second polling process, bot token,
channel id or BotFather change is introduced by this task.

## Hermes boundary

The official Nous Research Hermes Agent repository and documentation were checked on 2026-09-03:
[repository](https://github.com/NousResearch/hermes-agent) and [official documentation index](https://hermes-agent.nousresearch.com/docs/).
The repository describes a messaging gateway with Telegram and a scheduled-job capability.  This
task does not install Hermes, connect an account, configure a provider, or make a live Telegram or
provider call.  Pinning an owner-approved Hermes release and deployment image is a separate Gate A
decision.

```text
Hermes scheduled worker
  -> HMAC-signed bounded candidate/draft intake
  -> YFC allowlist + URL validation + taxonomy + risk policy
  -> immutable NewsDraftRevision and exact YFC preview
  -> owner/manual Telegram editorial workflow
  -> existing YFC publisher and reconciliation
```

Hermes may submit source metadata, a short claim packet and a structured Russian draft proposal.
YFC recomputes source identity, taxonomy, evidence and publication risk.  Hermes cannot receive a
channel token, call `sendMessage`/`sendPhoto`, call a publish endpoint, query the database, execute
general production shell commands, or send user profile/diary/measurement/initData values.
Fetched source text is untrusted input and cannot override the editorial contract.

### Intake contract

Headers are signed as `HMAC-SHA256(secret, timestamp + "\\n" + nonce + "\\n" + raw_body)`:

```text
X-Hermes-Key-Id
X-Hermes-Timestamp       # Unix seconds, bounded clock skew
X-Hermes-Nonce           # unique replay-protection value
X-Hermes-Signature       # sha256=<lowercase hex digest>
```

The payload is `hermes-editorial-intake-v1`, with one allowlisted source packet, one structured
draft proposal and provider/model/prompt/skill provenance.  The source content hash is recomputed
by YFC.  Idempotency key and nonce are unique in `hermes_editorial_submissions`; a repeated exact
request returns the same draft as `duplicate`, while a changed payload or replayed nonce fails
closed.  Body size, source count, clock skew, replay TTL and request rate are configured by the
`HERMES_INTAKE_*` variables in `.env.example`.

Receipts retain only operational metadata and hashes, never the full submitted source or draft
payload.  Normal logs contain correlation-safe ids/reason codes only.

### Hermes deterministic preflight and bounded repair (Task 142)

Перед HMAC intake worker выполняет детерминированный preflight. Числовые токены в draft должны
быть заземлены в разрешённом source packet; идентификаторы и URL не считаются доказательством
числового утверждения. Консервативный plain-text photo caption считается вместе с доверенным
source URL и меткой `Источник` и должен укладываться в лимит 1024 UTF-16 символа, установленный
[официальной документацией Telegram Bot API](https://core.telegram.org/bots/api).
Внешний GPT-OSS prompt получает динамический мягкий бюджет для трёх полей с учётом длины
доверенного URL и служебных разделителей, чтобы использовать доступное место для подтверждённых
деталей без filler; лимит 1024 и hard limits полей не изменяются.

Для `unsupported_number` и `telegram_photo_caption_too_long` разрешён один bounded repair request
к тому же approved provider. Он делит общий бюджет максимум двух provider attempts с исходным
draft и transient retry; paid/cloud fallback, новые credentials и provider shortcut запрещены.
Если repair не снимает blocker, worker завершает job fail-closed: HMAC intake, Telegram preview
и autopublish не вызываются. Успешный preflight только допускает intake; он не подтверждает
публикацию. YFC по-прежнему применяет `manual_required`, Gate B/C и остаётся единственным
publisher.

YFC имеет дополнительный final delivery gate: Hermes draft не отправляется владельцу в Telegram,
пока не собраны exact image и rendered caption и не сняты технические delivery blockers.
Fallback-заглушки, unresolved provider warnings, переполненный caption и отсутствие artifact не
создают ни preview, ни управляющую карточку. Разрешённые для owner review sensitive warnings
могут оставаться publication blockers: они показываются в полноценной карточке, но скрывают
кнопку публикации до ручного решения/редактирования. Заблокированная техническая попытка
фиксируется как bounded failure и не повторяется для той же text/image revision; новая попытка
появляется только после новой ревизии текста или изображения. Операционные состояния
`publishing_disabled` и `channel_rights_missing` не меняют требование наличия image+text preview и
не считаются содержательным fallback.

## Taxonomy and policy

`NewsCluster` stores versioned independent fields:

```text
primary_topic, topics[], content_type, product_class, evidence_level,
risk_level, audience, geography[], classification_version,
classification_reasons[], discovery_eligible, discovery_reasons[],
publication_policy, risk_reasons[], risk_policy_version
```

`sports_nutrition` and `dietary_supplements` are separate topics and separate product classes from
food, medicine and peptides.  Research is a `content_type` and never replaces the subject topics.
Unknown or ambiguous classification goes to manual review; it is not silently promoted to a safe
topic or auto-publication.

Recall discovery и eligibility публикации разделены. Primary/official fresh item с семантическими
признаками темы может остаться discovery candidate, даже если legacy coarse topic scorer не дал
совпадения. Чувствительный/предписывающий Hermes-контент сохраняется для owner review, а
publication quality gates по-прежнему блокируют unsafe или технически невалидный output. Счётчики
различают `duplicate`, `stale`, `below_threshold`, `rejected`, `candidate` и `eligible`; ошибки
загрузки источников остаются видимыми в `NewsSource` с code/time/consecutive count и не
отчитываются как «новостей нет».

The server-side policy is:

```text
blocked | manual_required | auto_eligible
```

Чувствительные medical/pharmacology, peptides, AAS/SARMs, dosage/cycle/protocol,
индивидуальные рекомендации, pregnancy/minors/chronic disease/symptoms, interactions,
recalls/contamination, preliminary или conflicting evidence и любая неоднозначность имеют как
минимум `manual_required`; Hermes intake может доставить их владельцу как полноценный preview для
ручного решения. Prompt injection, unsupported numbers и явные unsafe/guaranteed claims по-прежнему
заблокированы для delivery или publication. `auto_eligible` дополнительно требует
owner-controlled `NEWS_AUTO_PUBLISH_LOW_RISK=true`, valid source provenance, quality checks, exact
snapshot и active kill-switch. Committed default — `false`.

The deterministic style checklist checks template/AI meta language, fake personal voice, clickbait,
invented quotes, excessive exclamation and mechanical repetition.  It does not use an AI detector,
does not promise detector evasion and does not establish authorship.

## Telegram editorial UX

Immediate publish confirmation edits only the inline markup of the original preview card.  The exact
text/caption, channel, mode, text revision, image revision and artifact hash remain bound to the
same `message_id`.  Confirm calls the existing hash-bound YFC action once; queued/already-queued
removes destructive buttons and appends a status to that card.  Cancel restores the exact revision
actions on the same card.  Stale, forbidden, quality-blocked and network-failure cases keep a
recoverable card and use a callback alert.

The confirmation path must not call `callback.message.answer` or `send_message`.  Media and text
cards use the same rule.  Scheduled input may use a temporary prompt message, but its final action
still targets the original anchor card.

## Growth and attribution

Telegram posts must have standalone value, a relevant canonical CTA and no clickbait or artificial
urgency.  Campaign values and destinations are allowlisted by `news_growth.py`; no arbitrary query
parameters, source/body text, health data, Telegram ids or PII enter attribution.

The existing provider-neutral product event contract is extended only with the constrained
`telegram_news_cta_clicked` event.  A CTA click is intent, not a lead.  The reporting definitions
are distinct:

| Metric | Meaning |
| --- | --- |
| reach/view | Aggregate platform signal, not proof of reading |
| audience growth | Aggregate channel count change |
| engagement | Aggregate reaction/share/action available from Telegram |
| CTA click | Allowlisted canonical destination click |
| qualified lead | Explicit first-party Demo/Mini App/sign-up start |
| product conversion | Server-confirmed product outcome |
| activation | Separately owner-defined product milestone |

Attribution separates Telegram/Web/TMA and test/staging/production.  Analytics outages never block
the editorial pipeline.  Numeric KPI targets are intentionally not invented before a baseline.

## Task 130 handoff

Each draft metadata contains an `article_candidate` object with a stable news cluster/revision
reference, primary topic, content type, optional already-published canonical URL and
`web_lifecycle_owner: task-130`.  No Web article body, slug, SEO schema, `/articles` route, sitemap,
indexing state, Landing block or Web publish state is created here.

## Operations, kill switch and correction

1. Keep `HERMES_INTAKE_ENABLED=false` until Gate A owner approval covers the selected Hermes version,
   deployment isolation, provider/data retention, outbound domains, auth rotation and rollback.
2. Run local/mock signed intake tests and inspect the exact preview before any external setup.
3. Keep `NEWS_AUTO_PUBLISH_LOW_RISK=false`; if later activated, first run a shadow/manual sample and
   review representative Russian corpus for clarity, usefulness and template repetition.
4. Disable intake or low-risk automation immediately by flipping the corresponding flag; no Hermes
   fallback may bypass YFC policy.
5. A materially wrong post uses the existing exact snapshot/audit trail and manual correction,
   replacement or retraction path.  The original snapshot and reason remain retained according to
   editorial retention policy.
6. Provider timeout, source outage or ambiguous Telegram result stays a normalized failure/uncertain
   state.  Retries are bounded and idempotent; no duplicate publication is inferred.

Production source coverage, live Hermes/provider behavior, real Telegram/channel sends and device
smoke are deliberately unclaimed until the owner authorizes the corresponding external gates.

## Hardened editorial worker: repository integration

The tracked worker is a narrow, provider-compatible editorial adapter. It is not the official
monolithic Hermes image and does not expose the general Hermes agent loop. Its upstream provenance
is recorded in `deploy/hermes-editorial-worker/hermes-provenance.json`:

```text
Hermes version: 0.21.0
tag: v2026.8.31
commit: 29112bef099274229cadff79cdff7bf7b99c4b77
source behavior patches: 0
```

The exact upstream license is kept in `deploy/hermes-editorial-worker/LICENSES/HERMES-LICENSE`.
`license_bundle.py` builds a deterministic `/opt/licenses` bundle from the pinned Python lock,
installed distribution metadata and the Alpine APK database during the image build. The image
also contains the generated Python/Alpine inventory and the upstream license; no credential or
source content is included. The build fails if the lock and declared inventory diverge.

### Reproducible local verification

Run from a clean checkout with Docker available:

```powershell
python scripts/hermes_worker.py provenance --source-dir <exact-hermes-checkout>
python scripts/hermes_worker.py verify
```

`verify` checks the exact base digest and lock, builds with `--pull=false`, runs the hardening
boundary, executes the local HTTP E2E harness, generates CycloneDX and SPDX SBOM files, and runs
the pinned Trivy CRITICAL/HIGH gate. The source checkout is used only for offline provenance
verification; it is not copied into the runtime image. Build context is the tracked
`deploy/hermes-editorial-worker` directory and its `.dockerignore`; `.artifacts/` contains only
evidence and is never a build input or commit target.

The lock contains only the worker closure and has no floating versions or provider SDK:
`httpx`, Pydantic and their exact transitive dependencies. The base is
`python:3.13-alpine@sha256:46ee549c88617e9bc8acb843a326f1a5c0fa5608d7f9703509efe6d53b55f318`.
The final image runs as UID/GID `10000:10000`, drops all capabilities, sets
`no-new-privileges`, removes the package shell/tooling surfaces, declares `/opt/data` as the only
state volume, and is tested with a read-only root filesystem. The verification budget is 0.50
CPU, 512 MiB RAM and 64 PIDs per container; these are safety bounds, not a production capacity
benchmark.

Worker принимает одну bounded job, отправляет source packet только в OpenAI-compatible provider,
проверяет structured response и подписывает YFC intake payload. `HERMES_PROVIDER_MODE=local_mock`
сохраняет текущий local-only contract: только HTTP localhost/`host.docker.internal`, provider
base path `/v1`, YFC intake path `/api/v1/hermes/editorial/intake` и local Telegram preview mock.
`external` — отдельный подготовленный режим: только HTTPS, exact provider host `api.groq.com` с
base path `/openai/v1`, exact YFC host `app.your-fitness-coach.ru` и exact intake path
`/api/v1/hermes/editorial/intake`. Внешние URL с arbitrary host, HTTP, private/link-local/metadata
target, userinfo, query/fragment, нестандартным портом или redirect отвергаются. HTTP client не
следует redirect. Source URLs worker не fetch'ит.

Worker не имеет terminal, browser, MCP, plugin, Telegram Bot API, dashboard, database, publish или
Docker-socket capability. Запрос unsupported capability, malformed endpoint, oversized
input/output, prompt-injection marker, failed provider response, invalid schema, invalid HMAC,
duplicate replay или source outside allowlist fails closed. В external mode `TELEGRAM_PREVIEW_URL`
не требуется и запрещён конфигурационным контрактом: после accepted YFC intake downstream
editorial/review flow принадлежит YFC.

The local E2E path is:

```text
tracked source fixture
  -> hardened Docker worker
  -> local OpenAI-compatible fake HTTP provider
  -> structured draft response
  -> HMAC-signed YFC intake contract
  -> local YFC FastAPI intake
  -> taxonomy/risk classification
  -> immutable draft revision, manual_required
  -> local editorial preview mock (published=false)
```

The fake provider is an HTTP server, so this verifies the actual transport/protocol path; it does
not claim real-model quality. Local tests set `HERMES_INTAKE_ENABLED=true` only inside the
test-process YFC server. They set the local news flags to false and cannot change production.

### Deployment boundary and operations

The selected production topology remains a separate Linux `x86_64` VM; it has not been created.
The current YFC host is not a placement target: the earlier read-only baseline was 1 vCPU, about
958 MiB RAM with about 163 MiB available and swap pressure, and about 4.37 GiB free disk. The
planning minimum for a dedicated VM is 2 vCPU, 4 GiB RAM and 30 GiB SSD (20 GiB is only a short,
stateless-shadow floor), with cgroup v2, default-deny host ingress/egress firewall, no public
inbound ports, no host mounts, no Docker socket and no YFC DB/Redis/SSH access. Expected external
LLM editor workload is an unbenchmarked 0.25-1.0 vCPU and 0.5-1.5 GiB RAM; confirm the budget in
an owner-approved shadow run.

Before Gate A approval the network is local-only: the test harness uses loopback and Docker's
`host.docker.internal` mapping solely for local services. No production allowlist is changed.
After a separate approval, the VM allowlist must explicitly name the approved provider API host,
the YFC intake host/path and approved source hosts; it must deny Telegram Bot API, YFC
PostgreSQL/Redis/internal services, Docker API/socket, SSH, cloud metadata, arbitrary redirects,
registries and wildcard internet egress. There are no inbound Hermes ports.

Актуальные имена переменных worker:

```text
HERMES_INTAKE_ENABLED
HERMES_SOURCE_ALLOWLIST
HERMES_PROVIDER_MODE
HERMES_PROVIDER_BASE_URL
HERMES_PROVIDER_API_KEY
HERMES_PROVIDER_MODEL
HERMES_PROVIDER_TIMEOUT_SECONDS
HERMES_PROVIDER_MAX_ATTEMPTS
HERMES_PROVIDER_RETRY_BACKOFF_SECONDS
YFC_INTAKE_URL
YFC_HERMES_KEY_ID
YFC_HERMES_SHARED_SECRET
YFC_INTAKE_TIMEOUT_SECONDS
TELEGRAM_PREVIEW_URL              # local_mock/E2E only
TELEGRAM_PREVIEW_TIMEOUT_SECONDS  # local_mock/E2E only
```

Секретные значения — только `HERMES_PROVIDER_API_KEY` и `YFC_HERMES_SHARED_SECRET`. Telegram
token, database credential, user health data и host credential worker не нужны. Pre-Gate local
build использует локальные test values, не создаёт accounts, keys или service identities.

### Provider readiness addendum

Primary candidate для внешнего режима — Groq Free Plan, модель `openai/gpt-oss-120b`, с целевой
стоимостью LLM `$0` на старте. Published Groq Free limits являются только baseline: фактические
account tier, quota/rate limits, payment state и доступность модели должны быть проверены владельцем
перед shadow-run. Worker не может автоматически переключиться на Developer/paid Groq tier или
другой cloud provider. После максимум двух попыток того же candidate при 429/quota, timeout,
network unavailable или 5xx остаётся manual/no-provider.

`HERMES_PROVIDER_BASE_URL`, `HERMES_PROVIDER_API_KEY` и `HERMES_PROVIDER_MODEL` остаются
provider-neutral interface. В текущем external build allowlist и model pin ограничены Groq Free
candidate; добавление `api.openai.com` или любого другого provider host требует отдельного
owner-approved config/code change. Будущий optional paid fallback — OpenAI `gpt-5.6-luna` — не
подключён, credentials не создаются и автоматическим fallback не является. Gemini и OpenRouter
не подключаются.

В external mode наружу уходит source metadata/content packet только в approved Groq endpoint и
structured draft metadata в approved YFC intake; source URL не fetch'ится, а YFC intake получает
content hash вместо полного source content. Retention, training/model-improvement policy,
processing/storage region, privacy terms и фактическая cost/quota policy Groq для конкретного
account до owner verification не считаются подтверждёнными. Качество реальной модели проверяется
только в owner-approved shadow-run после Gate A; local fake E2E не является model-quality proof.

Kill switch — `HERMES_INTAKE_ENABLED=false`; keep it off until Gate A. The existing production
`NEWS_INGESTION_ENABLED` and `NEWS_PUBLICATION_ENABLED` values are not changed by this integration,
and `NEWS_AUTO_PUBLISH_LOW_RISK=false` remains required. Production задаёт
`NEWS_LEGACY_SOURCE_FETCH_ENABLED=false` через штатный deployment normalizer; rollback этого
ограниченного изменения флага восстанавливает прежнее значение окружения только через
owner-approved release. Rollback — это остановка/удаление
the separate worker workload, revoke only its approved intake/provider identities, remove its
egress rules, and return to the existing YFC manual/editorial path. Existing news pipeline flags
and publisher ownership are not rollback targets. Any later production rollback must use the
previously verified immutable application/image SHA and the normal release procedure; no blind
migration downgrade is permitted.

The evidence boundary is explicit: local/mock proves deterministic contracts, hardening,
idempotency, HMAC, taxonomy/risk and manual-required behavior; a shadow run requires owner approval
and a real provider; production and Telegram/channel proof require later external gates. This
repository integration grants neither Gate A nor any deployment authorization.

### Scheduled source discovery и monitoring

Source fetching не добавляется в hardened editorial worker. Отдельный stdlib-only
`deploy/hermes-discovery/discovery_runner.py` получает только versioned definitions, рендеренные
из canonical `backend/fitminiapp_api/resources/news_sources.json`, и пишет bounded jobs в
локальный outbox. Команда рендера:

```powershell
python scripts/generate_hermes_source_definitions.py --output <versioned-output.json>
```

Output содержит SHA-256 canonical registry и `definitions_version`; ручной второй список источников
не допускается. Реестр уже поддерживает RSS, JSON Feed и HTML metadata и фиксирует diversity
vocabulary для `sports_nutrition`, `dietary_supplements`, medicine/health, fitness/training,
bodybuilding, peptides, nutrition/food, fitness technology, research/guideline/regulation/product/
safety. Фактический набор enabled/disabled источников остаётся каноническим YFC registry; runner
не подменяет отсутствующее покрытие filler-источниками и не создаёт publication quota.
Перед внешней установкой дополнительно фиксируется SHA-256 самого versioned deployment-файла в
`HERMES_DISCOVERY_DEFINITIONS_SHA256`; external runner fail-closed отклоняет изменённый или
неподготовленный definitions-файл.
Discovery не делает обязательных publication quotas и не отбрасывает материал из-за неизвестного
topic; taxonomy/risk/publication eligibility остаются серверной ответственностью YFC.

На будущей отдельной Hermes VM systemd timer напрямую активирует `hermes-worker-drain.service`;
его `Requires`/`After` сначала запускают `hermes-discovery.service`. Первый
контейнер не получает provider/YFC secrets. Только второй host-side drain передаёт bounded job в
hardened worker с provider key и YFC HMAC secret. Входящих Hermes ports нет; source discovery
имеет exact host allowlist из definitions, HTTPS-only external mode, DNS resolution с запретом
non-global адресов, revalidation каждого redirect, MIME/size/time/concurrency bounds и no
JavaScript/browser. Host firewall должен быть default-deny и отдельно разрешать только approved
source hosts, Groq и YFC intake.
До установки нужен host preflight: account `hermes` и bind-mounted `/var/lib/hermes` должны
согласовать UID/GID `10000:10000` контейнеров, но `hermes` не должен иметь membership в группе
`docker` или доступ к `/var/run/docker.sock`. Host-side discovery/drain units запускаются от
`root` только для точных Docker/launcher commands; сами контейнеры остаются non-root с
`--user 10000:10000`, read-only rootfs, cap-drop ALL и no-new-privileges. Обе units закрепляют
одну owner-approved Docker network `hermes-net`; worker drain валидирует только bounded `hermes-*`
имя и отвергает встроенные `bridge`/`host`/`none` сети. Этот PR не устанавливает Docker или VM.

State — только bounded hashes, fetch metadata, reason codes и candidate metadata. Stable dedupe key
использует `source_id + canonical URL + content hash + event date`; restart/uncertain state не
создаёт новый idempotency key. Lock на Linux использует kernel `flock`, поэтому SIGKILL не оставляет
вечный overlap blocker; пропущенный timer run не восполняет publication quota. Accepted/duplicate
job удаляется из outbox после сохранения статуса, а pending/error job остаётся для той же retry.

Полная локальная проверка:

```powershell
python scripts/hermes_worker.py verify
```

Она включает provenance canonical registry, отдельные image build/hardening/SBOM/Trivy для worker
и discovery и E2E `fake RSS -> discovery container -> outbox -> hardened worker -> fake
OpenAI-compatible HTTP -> real local YFC intake -> manual_required draft`. Проверяются malformed,
timeout, oversized, invalid MIME, redirect SSRF, private IP, partial outage, prompt injection,
duplicate, overlap и crash/restart. Это не live Internet/provider/Telegram и не production proof.
