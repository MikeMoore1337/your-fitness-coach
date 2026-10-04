# Product review post-release направлений `80-101`

## Product v8 bounded reconstruction and closeout — 2026-10-04

Owner decision: Task `124B` / V8-00 is `REMOVED_FROM_PRODUCT_V8 / NO_GO BY OWNER`. It is no
longer an evidence gate, dependency or blocker, must not auto-start, and must not create V8-03.
Synthetic/demo evidence remains explicitly different from real-user evidence, but missing
real-user validation is not a universal Product v8 prerequisite.

Owner closeout decision: Product v8 is **COMPLETED**. V8-01 delivered the confirmed executable
scope and was production verified. Removed/cancelled placeholders do not count as unfinished
tasks; optional or evidence-gated external workstreams do not block closure. The empty executable
slate is the result of bounded reconciliation, not a blocker. No future product version is created
or populated automatically.

The current repository baseline for this review is
`6e231e068fe513cc5bf8ba2c24ff32c4e577ec18`. The review used the current source tree, task files,
task-related commit history and the open GitHub backlog. It did not treat a task title or an old
Dependabot/backlog description as proof of a current gap.

### Backlog review

| Direction | Current state | Decision | Reason |
|---|---|---|---|
| Hydration (`81/81A`) | Optional daily logging, Nutrition/report integration, idempotency, export/delete and UI are present; commits `aa7e5bd0`, `1e0183b4`, `4bbb5f14`. | `ALREADY_IMPLEMENTED` | The requested bounded job and non-medical boundary already exist; do not duplicate it. |
| Sleep / Mood (`82`) | Optional daily wellbeing API/UI, partial data and report/export/delete coverage are present; commit `13b6c9d9`. | `ALREADY_IMPLEMENTED` | Current implementation matches the subjective check-in boundary; no readiness or medical inference gap was found. |
| Trainer report handoff (`83/296`) | Authenticated in-product handoff to the active trainer, relationship checks, delivery state, retry and history are present; commits `55f7a9a0`, `e16e1c26`. | `ALREADY_IMPLEMENTED` | The narrow handoff job is closed; external share/Telegram delivery remains a separate `95B` decision. |
| Reminder templates (`84/64`) | Existing notification orchestration has contextual templates, default-off settings, quiet-hours/suppression/dedupe tests; commit `deed3ca0`. | `ALREADY_IMPLEMENTED` | No second scheduler or bounded template gap remains. |
| Knowledge / editorial (`85`) | Reviewed public knowledge package and source-linked content are present; commit `aad5ff3c`. Hermes operations are separate. | `ALREADY_IMPLEMENTED` | Further editorial expansion needs a new content gap and source review, not a v8 placeholder. |
| PWA (`86`) | Installability, service worker, standalone/return flow and active-workout resume are present; commits `614c3bdb`, `533c6149`. | `ALREADY_IMPLEMENTED` | No remaining bounded PWA capability was proven by this review. |
| Web Push (`86A`) | Opt-in subscriptions, ownership, delivery and lifecycle are implemented; commit `5937cb9b`. | `ALREADY_IMPLEMENTED` | Existing notification foundation is reused; no duplicate channel/scheduler is needed. |
| AI Coach bounded work (`87-92A`, `508`, `514`) | Provider/privacy/eval path, grounded core, read-only tools, beta controls, period insights, consented memory, adaptation and safe exercise/media context are implemented. | `ALREADY_IMPLEMENTED` | No new AI expansion is justified without its own privacy, provider, eval, cost and consent gate. |
| AI provider routing (`92B`) | Current route has graceful unavailable behavior; measured outage/capability/latency/cost gap and provider policy are not established. | `BLOCKED_ON_OWN_GATE` | Do not add provider redundancy for novelty; require measured trigger and owner privacy/cost decision. |
| Program imports (`93A/93B`, `504`) | Deterministic XLSX/CSV and reviewed AI-assisted document import share the preview/resolve/confirm boundary; current endpoints and tests are present. | `ALREADY_IMPLEMENTED` | Only a measured unsupported-layout gap can reopen the existing pipeline. |
| Progress (`111`, `521`, `537`) | Bento periods, factual review loop and weekly action are present; commits `aa2e7c62`, `05d9cc75`, `944d8670`. | `ALREADY_IMPLEMENTED` | No separate progress capability is missing after current master reconciliation. |
| Trainer features (`388`, `525`, `539`, `543`, `684`) | Trainer Today IA, Coach workspace, capacity, discoverability and demo parity are implemented and merged. | `ALREADY_IMPLEMENTED` | Old local task metadata is stale; no new trainer task is required for v8 selection. |
| Nutrition improvements (`114`, `515`, `522`, `523`) | Search/barcode regression, quick logging, saved-meal reuse and macro-aware suggestions are present. OCR feature-off follow-up `128G` remains tied to its own `128H`/owner path. | `ALREADY_IMPLEMENTED` / `BLOCKED_ON_OWN_GATE` | Do not reopen OCR or duplicate nutrition flows; keep the feature-off finding outside v8 until its own gate changes. |
| Owner-selected profile / public handoff (`106`, `109-111`) | Landing handoff, custom avatar and Progress bento work are already represented in current source/history; public share and report handoff foundations exist. | `ALREADY_IMPLEMENTED` | Stale “pending” labels do not justify new issues. |
| Server PDF / external report delivery (`95A/95B`) | Authenticated short-lived PDF and revocable public-share primitives exist, but the immutable server snapshot/job and separately justified external channel are not established as a current job. | `BLOCKED_ON_OWN_GATE` | Keep the existing trigger: prove a repeated delivery gap and approve each external channel; no speculative renderer/storage expansion. |
| Public/product handoff and SEO (`320-324`, existing public share flows) | Core public-to-product primitives exist; current SEO wave remains evidence-gated. | `BLOCKED_ON_OWN_GATE` | `NO_DATA`/insufficient observation is not a reason to create a mass SEO or handoff task. |
| Maintenance, controller, Hermes topology, legal/platform (`107/108/127/138/269/403/415`) | Separate infrastructure/operations or already-delivered workstreams. | `OUTSIDE_V8` / `DEFER` / `ALREADY_IMPLEMENTED` | Preserve their own lifecycle and do not turn technical backlog presence into Product v8 scope. |
| Camera / video technique evaluation (`126/127A` and any video-form analysis) | Equipment recognition has separate feasibility prerequisites; video technique analysis is explicitly prohibited. | `NO_GO` | No pose estimation, form scoring, camera correction or exercise-technique video path. |

### Product v8 slate

The selected *executable* slate is intentionally empty after this bounded review and closeout. The existing
backlog contains no unimplemented, independently executable product task that adds real value
without duplicating shipped behavior or bypassing an independent gate. The parked candidates are
not Product v8 tasks and do not receive new V8 numbers:

1. `V8-R1` — measurement reporting boundedness: optional reliability work, P3, size M,
   `BLOCKED_ON_EVIDENCE`, outside the main product path. First step is aggregate production
   read-only evidence; no migration, index or dashboard is pre-approved.
2. `95A` — server report snapshot hardening: possible M, authenticated Web/TMA download,
   no new product metrics, migration only if measured necessary; `BLOCKED_ON_OWN_GATE` until the
   browser-PDF delivery gap is demonstrated.
3. `95B` — temporary share/Telegram delivery: possible M/L, explicit user action and revocation,
   no unsolicited delivery; `BLOCKED_ON_OWN_GATE` until `95A` and a channel-specific owner/privacy
   decision exist.
4. `92B` — capability-aware provider routing: possible L, no frontend requirement, no migration
   assumed; `BLOCKED_ON_OWN_GATE` until measured reliability/cost/capability evidence and provider
   policy exist.
5. SEO/product handoff wave: possible M, public Web first and authenticated handoff only where a
   canonical persistence target exists; `BLOCKED_ON_OWN_GATE` under `#320-#324` evidence contract.

None of these is an executable Product v8 task. No new Product v8 Issue is created from a parked
candidate, no implementation/worktree is started, and no candidate is transferred automatically
to a future product version.

### Selection contract for a future v8 task

An approved future task must state its user job, objective gap, cheaper fallback, bounded scope,
non-goals, dependencies, risks, backend/frontend and migration impact, Web/TMA acceptance, tests,
privacy/security and observability. It may proceed without real-user evidence when those facts are
objective and technically/product-verifiable; it may not claim synthetic/demo demand as market
evidence. Sequence is independent core value -> next core workflow -> trainer/nutrition/progress ->
retention/re-engagement -> optional expansion. No Product v8 dependency may point to `124B`.

## Historical review — 2026-08-30

## Итог

Tasks `80-101` и их буквенные подзадачи — trigger-gated pool после release gate `79`: реализация
начинается только после наблюдаемой проблемы/спроса, проверки более дешёвого решения и owner
decision. Номер задаёт предпочтительный порядок, но не заменяет Trigger или dependency.

Импорт остаётся одним пользовательским job и pipeline под umbrella `93`, но delivery разделён:
`93A` даёт deterministic XLSX/CSV template import без AI, а `93B` условно добавляет AI-разбор
неоднородных XLSX/CSV/TXT/DOCX после измеримого gap. Draft, matching, preview и confirmed write не
расходятся между этапами. Food-photo остаётся отдельной задачей `94`. Billing, локализация и private
progress photos без AI/body analysis остаются в конце.

## Критерии ревизии

- конкретный пользователь и Job-to-be-Done;
- overlap с уже реализованным продуктом;
- минимальный путь к ценности и более дешёвый fallback;
- external/provider/operations dependency;
- privacy/security/domain risk;
- возможность завершить task одним логическим результатом;
- честный success signal без выдуманных KPI.

## Решения по направлениям

| Tasks | Решение | Обоснование и обязательный Trigger |
|---|---|---|
| `80` | Ранний обязательный candidate после `79` | Hygiene/security/docs уменьшают риск следующих изменений; history rewrite и rotation требуют отдельного checkpoint. |
| `81` | Сохранить как optional feature | Hydration — короткий сценарий рядом с Nutrition; никакой навязанной медицинской нормы. |
| `82` | Объединить sleep + mood | Один optional wellbeing check-in; данные входят в отчёт только при заполнении и с coverage. |
| `83` | Узкий in-product handoff | Отчёт передаётся текущему trainer через существующие auth/relationship boundaries; external delivery остаётся в `95B`. |
| `84` | Расширить task `64` | Templates еды, воды и разминки default-off, с quiet hours и suppression/dedupe; второй scheduler не нужен. |
| `85` | Bounded editorial package | GI, источники КБЖУ, BMI и HR zones требуют reviewed primary sources и честных ограничений. |
| `86` | Owner-confirmed PWA | Web (~60%) — независимый primary channel; browser/TMA return требует больше действий и хуже доступен, чем home-screen launch; Task сохраняет bounded offline foundation и active-workout resume без обещания полного offline. |
| `86A` | Отдельный Web Push follow-up | Web Push нужен из-за существующих уведомлений и неуниверсальности Telegram; subscriptions, delivery, permission UX, backend integration, privacy и lifecycle не смешиваются с Task `86`. |
| `87-89` | Строгая AI-цепочка | Сначала provider/privacy/safety/eval decision, затем grounded core и отдельно consented read-only tools. |
| `90A-90B` | Декомпозировать | Internal UI/evals и real-user rollout имеют разные evidence gates; синтетические user results запрещены. |
| `91` | Только после успешной beta | AI итог периода расширяет factual report; нужны consent, evidence anchors, domain evals и non-AI fallback. |
| `92A`, `92B` | Оценивать независимо | Memory решает continuity, routing — provider resilience/cost; допустим `Go` только для одной capability. |
| `93A-93B` | Один pipeline, два delivery gate | `93A` даёт canonical XLSX/CSV import без provider dependency. `93B` запускается только при измеримом gap и добавляет source-grounded AI proposal/rerank поверх того же deterministic matching/preview/confirm. |
| `94A-94B` | Декомпозировать после AI/import | Фото еды сначала проходит corpus/eval/privacy/cost Go/No-Go; production output — только editable draft. |
| `95A-95B` | Только после gap task `67` | Browser print-to-PDF остаётся fallback; share/Telegram добавляют отдельный риск. |
| `96` | Research-only | Нужен один конкретный wearable datum/platform/job; calories/readiness не становятся product truth. |
| `97` | Conditional | Делегирование оправдано только реальной командой и responsibility matrix. |
| `98` | Research-only | Native feasibility запускается лишь при измеримом Web/TMA/PWA limitation. |
| `99A-99C` | Декомпозировать и оставить в хвосте | Commercial decision, billing state и rollout имеют разные owner checkpoints. |
| `100A-100B` | Декомпозировать и оставить в хвосте | Core locale и Public Web/SEO требуют разных scope и language review. |
| `101` | Последняя очередь | Body images чувствительны; нужны спрос, safe storage и lifecycle task `65`. AI/body analysis исключён. |
| `103-105` | Завершённая отдельная ветка | Telegram editorial operations архивированы и не входят в pending sequence. |
| `106` | Завершённая owner-selected bounded Landing task | Развела запуск Mini App, поддержку и подписку на подтверждённый публичный канал без нового Telegram runtime. |
| `107` | Owner-selected QA/platform task вне основной очереди | Scheduled Daily/Weekly regression, единый закрытый Allure HTML и retention уменьшают latency обнаружения regressions. Публичный repo требует реальной access boundary; implementation и внешняя инфраструктура запускаются только отдельным owner approval. |
| `108` | Owner-selected legal-risk task вне основной очереди | Разовый snapshot недостаточен: read-only baseline и owner decision package объединены с отдельно одобряемым legal-impact intake/delta gate будущих задач. Primary role — `product-lawyer`, core skill — `$ru-legal-risk`; итоговый baseline/gate обязательно проверяет профильный российский юрист, а `LEGAL_COUNSEL_REQUIRED` выделяет дополнительные спорные вопросы; remediation отделена в follow-ups. |
| `109` | Owner-selected Landing task вне основной очереди | Уникальность выражается через фактический feedback loop YFC, без competitor comparison, fake proof и гарантий результата. Security/trust claim не обязателен и разрешён только из approved baseline task `108`; copy и screenshots требуют owner approval до commit. |
| `110` | Owner-selected profile/media task вне основной очереди | Текущий emoji fallback детерминирован и остаётся последней ступенью. Custom avatar — private media с mobile/desktop upload, safe processing, replace/delete/export и precedence `custom -> provider -> emoji`; production migration/deploy отдельно gated. |
| `111` | Owner-selected Progress redesign task вне основной очереди | Референс задаёт bento hierarchy, но не palette и не новые hydration/steps/health-score данные. Периоды `1/7/30/90/365/custom` используют единый factual progress/report contract, inclusive dates/timezone и измеренную performance. |
| `126A-126C` | Owner-selected camera/equipment feature вне основной очереди | Exercise catalog уже расширяется в `120A-120D`, поэтому новую базу не дублировать. После `120D` и successful AI foundation `90B` сначала провести отдельный Vision/privacy/cost/eval gate. Production AI определяет только bounded equipment candidates; упражнения всегда берутся из canonical YFC catalog и добавляются только после явного user choice через existing program flow. |

## Контракт импорта `93A-93B`

- `93A` строит versioned XLSX/CSV template, allowlist, size/complexity limits, безопасное хранение,
  deterministic extraction, neutral draft, preview/resolution и atomic confirmed write без AI.
- `93B` переиспользует этот pipeline для evidence-backed heterogeneous XLSX/CSV/TXT/DOCX. AI
  возвращает только строгую нейтральную схему, source spans и `null` для отсутствующих данных.
- Matching сначала использует stable ID, normalization, exact match, global/user aliases и
  token/fuzzy retrieval с domain hints, включая транслитерацию и языковые варианты.
- AI может только rerank ограниченный список разрешённых кандидатов. Один AI-score никогда не
  является основанием для automatch.
- Private exercises другого пользователя не попадают в candidates. Новые user-scoped aliases
  сохраняются только после явного подтверждения и не меняют global aliases.
- До транзакционной записи пользователь видит preview, unresolved/ambiguous rows и вручную
  подтверждает каждое опасное сопоставление. Результат — редактируемый draft программы.
- При unavailable/quota/policy/cost failure `93A` остаётся полноценным deterministic fallback.

## Общие routing contracts

- Umbrella `90`, `92`, `93`, `94`, `95`, `99`, `100`, `126` запрещено выполнять одним change set.
- External research, real-user validation, production provider/price/channel actions и rollout
  требуют фактического evidence/owner checkpoint.
- Все UI tasks `80-101` наследуют active `DESIGN_V2_1`, Mobile Web/TMA contracts и owner screenshot
  checkpoint.
- Existing canonical domains (`36`, `65`, `67`, `71`, Telegram Core) переиспользуются.

## Сверка с историческим AI Coach backlog

Исторический архив `ai-coach.zip` рассмотрен только как источник требований. В актуальные tasks
перенесены `generic/personalized` classification, fail-closed privacy metadata, neutral provider
contracts, evidence bundles, controlled unavailable states, safe Markdown/links и независимые
memory/provider gates. Не перенесены фиксированные providers, лишняя provider redundancy,
autonomous writes, streaming, web search, MCP, multi-agent и тяжёлый RAG до доказанной потребности.

Эта ревизия не подтверждает market demand, не назначает следующую task и не разрешает production
actions.
