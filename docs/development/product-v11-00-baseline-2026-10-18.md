# Product V11-00 — factual baseline and engineering audit

Дата аудита: 2026-10-18, Europe/Moscow
Baseline: 9b5a24b49408fee63339dbdc93af57767fdc977e (9b5a24b4)
Ветка аудита: codex/815-v11-00-baseline
Родитель: [Issue #814](https://github.com/MikeMoore1337/your-fitness-coach/issues/814)
Контракт аудита: [Issue #815](https://github.com/MikeMoore1337/your-fitness-coach/issues/815)

## Итоговый статус

VERIFIED: baseline снят с актуального master, проведены безопасные локальные проверки,
проверены исходники, workflow и последние доступные GitHub Actions.

PRODUCT_V11=PLANNED_NOT_ACTIVE: разрешение владельца покрывает read-only этап #815, но не
активацию остальных задач, merge, deploy или production-изменения.

NOT_PROVEN/NO_DATA: production p50/p95/p99 API, фактическая PostgreSQL connection budget,
production pool waits, real-user PWA/TMA/mobile metrics, React render traces, off-host backup и
clean-host restore. Отсутствие таких данных не трактуется как отсутствие соответствующих
ресурсов или резервных копий.

BLOCKED локально: Docker daemon и PostgreSQL stack недоступны; полная локальная Python-команда
не завершилась на Windows virtualenv/realpath окружении. GitHub CI остаётся источником истины для
репозитория.

Ограничения аудита соблюдены: production не изменялся, реальные персональные данные не
копировались, фоновые задания не создавались, удалённый controller/controller v2 не
восстанавливался.

## 1. Предусловия, V10 и activation gate

| Проверка | Результат | Доказательство и граница вывода |
|---|---|---|
| Product V10 #744 | VERIFIED — Issue закрыта с completed | [#744](https://github.com/MikeMoore1337/your-fitness-coach/issues/744) |
| Финальная V10-задача #858 | VERIFIED — Issue закрыта с completed | [#858](https://github.com/MikeMoore1337/your-fitness-coach/issues/858) |
| Актуальный master | VERIFIED | GitHub refs/heads/master указывает на 9b5a24b4; последний commit — fix(rest): retain offline recovery until terminal ACK (#1091) |
| Product V11 activation | BLOCKED/PLANNED_NOT_ACTIVE | В #814 activation требует V10 closeout/reconciliation, clean master, owner approval и factual baseline. Владелец разрешил только read-only #815. |
| PR на актуальном master | VERIFIED | Открытых PR на момент snapshot: #1115, #1111, #1109, #1094. PR ниже не считаются частью baseline. |
| Hardening #705 | VERIFIED как исторический input | Повторены только still-relevant gaps: production latency/field data, observability, recovery и security evidence; старые исследования и visual work не дублировались. [#705](https://github.com/MikeMoore1337/your-fitness-coach/issues/705) |

### Дочерние задачи V11

Все задачи ниже были сверены с текущими Issue. Состояние open не означает разрешение на
реализацию: порядок — это инженерная зависимость для планирования после отдельной активации.

| Issue | Направление | Текущий вывод и зависимость |
|---|---|---|
| #816 | Code health/refactoring | После #815; характеризующие тесты координировать с #819. Не восстанавливать router/controller. |
| #817 | Backend/API/PostgreSQL performance | После #815; источник входов для #820, #848 и #822. |
| #818 | Frontend/Web/Mobile/TMA performance | После #815; связать с #986, источник входов для #822. |
| #819 | Test quality/coverage/regression truth | После #815; может идти параллельно с #816 и #821. |
| #820 | Data integrity/concurrency/recovery hardening | После backend/test baseline; координация с #817, #819 и #849. |
| #821 | CI efficiency/determinism/regression truth | После #815; может идти параллельно с #819, без удаления значимого покрытия. |
| #822 | Observability/production performance evidence | После #817, #818, #820 и отдельного backup signal #849. |
| #823 | Cleanup/localization/product polish | После решения semantic/media конфликтов и characterization coverage. |
| #824 | Final acceptance/continuous engineering guard | Последняя gate после exact-head CI, owner acceptance, release и smoke gates. |
| #848 | PostgreSQL connection budget | P0, перед rollout; сейчас BLOCKED, см. раздел 7. |
| #849 | Off-host recovery/clean-host restore | P0, owner/security gate; сейчас BLOCKED, см. раздел 7. |
| #850 | Container runtime hardening | P1, можно исследовать параллельно с #851, но изменения контейнеров сериализовать с #1086. |
| #851 | Immutable base images/SBOM | P1, перед release; координация с container CI и #850. |

## 2. Методика и воспроизводимость

### GitHub evidence

Проверены read-only Issue/PR/commit/workflow resources GitHub API. Основные ссылки:

- [master commit](https://github.com/MikeMoore1337/your-fitness-coach/commit/9b5a24b49408fee63339dbdc93af57767fdc977e);
- [current master CI run #39148713613](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39148713613);
- [scheduled run #39111015160](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39111015160);
- [scheduled run #39106821544](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39106821544);
- [representative successful PR run #39057112340](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39057112340).

### Локальные команды

Команды выполнялись из отдельного worktree на baseline SHA. node_modules и build output
остались ignored и не входят в diff.

~~~powershell
git status --short --branch
git rev-parse HEAD

# frontend baseline
cd frontend
npm ci --ignore-scripts --no-audit --no-fund
npm run build
npm run perf:check
npm test -- --reporter=dot
npm run lint

# repository contracts
cd ..
python scripts/local_checks.py --group workflow-config
python scripts/local_checks.py --group image-contract
python scripts/local_checks.py --group deployment-contract
python scripts/local_checks.py --group policy

# inventory
rg --files backend frontend/src frontend/tests .github/workflows
rg -n "with_for_update|selectinload|joinedload|Index\\(|UniqueConstraint" backend/fitminiapp_api backend/alembic
~~~

На Windows npm run build, Vitest и lint пришлось повторить с повышенным доступом из-за
EPERM: realpath внутри repository-local worktree. Это не меняло исходники или lockfile.

## 3. Backend, API и PostgreSQL

### Статический baseline

| Объект | Наблюдение | Статус |
|---|---|---|
| Backend Python source | 542 .py файлов; 21 файл api/v1; 137 service files; 41 model file; 131 Alembic migration files | VERIFIED |
| API inventory | 372 совпадения endpoint decorators в api/v1 — эвристический инвентарь, не утверждение о 372 уникальных публичных маршрутах | VERIFIED с оговоркой |
| Крупнейшие API modules | workouts.py 67,440 B; ai_coach.py 59,446 B; coach.py 58,236 B; nutrition.py 50,166 B; auth.py 48,784 B; programs.py 33,433 B | VERIFIED |
| Критические области | auth/me, Today/check-ins, workouts/rest/active workout, nutrition, coach/Coach OS, programs/imports и ai_coach представлены отдельными API/service boundaries | VERIFIED |
| SQLAlchemy engine | PostgreSQL: pool_pre_ping=true, pool_size=10, max_overflow=20, pool_timeout=30 s, pool_recycle=1800 s; SQLite path без QueuePool | VERIFIED |
| Номинальный engine ceiling | 10 + 20 = 30 connections на один SQLAlchemy engine; фактический application total зависит от числа процессов/replicas, blue-green slots, PostgreSQL max_connections и возможного pooler | VERIFIED как расчёт, NOT_PROVEN как production budget |
| Request diagnostics | RequestContextMiddleware already emits sanitized request_id, route, status, duration_ms, sql_query_count, sql_duration_ms, pool size/checked-out/overflow; health probes исключены | VERIFIED по исходнику |
| Production diagnostics | Production log window, percentiles, pool waits/timeouts и slow-query samples не предоставлены этому audit | NO_DATA |

### N+1, serialization, repeated calculations и locking

Проведён bounded source scan, без утверждения runtime-профиля:

- with_for_update: 148 совпадений; это показывает существенную concurrency surface, но не
  наличие блокировок в каждом пути и не время ожидания;
- selectinload: 95, joinedload: 116 совпадений; в workouts и analytics уже есть eager-load
  цепочки для exercises/sets/adaptations, поэтому универсальный «добавить eager loading» не
  является доказательным fix;
- Index(: 140 и UniqueConstraint: 233 совпадения в application/migration source;
- yield_per и SERIALIZABLE в bounded scan не найдены; это не доказывает, что они нигде не
  нужны, а лишь задаёт вопрос для #817/#820;
- runtime EXPLAIN (ANALYZE, BUFFERS), query count per critical flow, response serialization
  size и repeated-calculation profile не сняты: нет production-shaped PostgreSQL snapshot и
  локальный Docker DB недоступен.

Следующий безопасный профиль для #817: synthetic accounts in isolated PostgreSQL, fixed route
fixtures, SQLAlchemy request metrics, EXPLAIN on the top flows, and comparison of query count,
SQL time, total time and response bytes. Нельзя выдавать synthetic numbers за production.

### Процессы и контейнерный topology

docker-compose.yml описывает db, setup, backend, worker, bot, edge, optional
caddy/cloudflared, optional Allure services и blue/green backend/worker/bot slots. Backend и
worker используют один application image, bot — отдельный image. Dockerfile запускает backend и
bot под non-root appuser; deployment shell требует immutable image references на deployment
host. Фактическое число production processes/replicas и их connection consumption не доказано.

## 4. Frontend, PWA и TMA

### Fresh build metrics

Команда: npm ci --ignore-scripts --no-audit --no-fund, npm run build, затем
npm run perf:check на baseline 9b5a24b4.

| Метрика | Результат | Статус |
|---|---:|---|
| Vite transformed modules | 568 | VERIFIED |
| Entry JS | 309,087 B raw / 96,775 B gzip | VERIFIED |
| Entry CSS | 64,478 B raw / 13,216 B gzip | VERIFIED |
| Public assets | 31 files / 647,377 B raw | VERIFIED |
| Largest public asset | assets/marketing/strength-hero.webp, 100,570 B | VERIFIED |
| Existing entry JS gzip budget | 96,000 B | VERIFIED |
| Budget result | FAIL: 96,775 B, превышение 775 B; остальные перечисленные budgets прошли | VERIFIED |

Крупнейшие emitted JS chunks по raw/gzip: index-B2ZkNDM-.js 454,373/117,445 B,
index-CW2q1LGC.js 309,087/96,775 B, NutritionPage 227,751/54,602 B,
MiniAppPage 207,017/56,909 B, CoachPage 186,518/45,777 B. Это bundle inventory, а не
измерение browser download или route TTI.

Source inventory: 261 frontend source files, 155 unit-test files, 126 E2E files. Lazy route
entries include MiniApp, ProgressReport, Coach, Nutrition, Programs/Templates, Landing, auth,
public content and Admin. Actual first load, navigation latency, LCP/INP/CLS and memory on
iPhone/Safari/Telegram WebView were not measured.

### Query/cache and render surface

@tanstack/react-query is present. The global client uses staleTime=30_000, retry=1 and
refetchOnWindowFocus=false; several Coach/Diary paths override focus behavior. Bounded source
counts (excluding tests): 335 useQuery, 205 useMutation, 178 invalidateQueries, 546
queryKey occurrences and 324 queryClient occurrences. These are search counts, not duplicate
request proof. A runtime trace with network request grouping and React Profiler is still required
for Today, Workout, Nutrition, Programs and Coach OS.

Public assets are modest in aggregate, but #986 remains an independent active media stream. Its
open draft PRs have stale or non-master bases and must not be treated as part of this baseline.

## 5. Tests and CI

### Local checks

| Check | Result | Status |
|---|---|---|
| Frontend build/typecheck | Vite build passed; 568 modules; 2.99 s Vite build phase | VERIFIED |
| Frontend unit | 155 files, 949 tests passed; Vitest wall duration 45.74 s | VERIFIED |
| Frontend lint | ESLint, Russian UI guard and lime-edge guard passed | VERIFIED |
| Frontend performance guard | Failed only entry JS gzip by 775 B | VERIFIED finding |
| workflow-config | Passed | VERIFIED |
| image-contract | Passed | VERIFIED |
| deployment-contract | Passed | VERIFIED |
| policy | 304 passed, 4 skipped, 1 failed in 3.59 s; failure is Windows symlink/realpath permission in test_production_provenance.py::test_reconcile_changes_only_existing_metadata | BLOCKED local environment |
| Full Python backend/bot suite | Attempted with isolated SQLite; uv/Windows virtualenv reported Failed to find real location...; direct xdist run produced no completion after more than two minutes and was interrupted | BLOCKED local environment; not a pass claim |
| Docker/PostgreSQL migrated stack | Docker daemon named pipe unavailable | BLOCKED |

### GitHub Actions durations and failures

Durations below are timestamp deltas from the GitHub run/job payloads; jobs run in parallel, so a
sum is not a workflow wall time.

| Run | Trigger/SHA | Result | Observed timing and slow work |
|---|---|---|---|
| [39148713613](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39148713613) | push, 9b5a24b4 | success | Run timestamps 368 s; scope-router 17 s, backend container 119 s, bot 72 s, Hermes worker 56 s, discovery 42 s, branch-checks 24 s. Application/test jobs were skipped by the scope router. |
| [39147094429](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39147094429) | push, f774d44… | success | 216 s; backend container 172 s, bot 74 s, Hermes discovery 55 s, worker 48 s. |
| [39125121648](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39125121648) | push, fd3ff4d… | success | 201 s; backend container 150 s, bot 78 s, discovery 54 s, worker 46 s. |
| [39057112340](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39057112340) | representative PR | success | 1,336 s; slowest jobs were Frontend smoke 395 s, 375 s, 364 s, Python shard 324 s, Frontend checks 170 s. |
| [39111015160](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39111015160) | scheduled, afc9a3e… | failure | 3,906 s; extended mobile job cancelled after 3,632 s. The failing assertion was mobile-ui-regression.spec.ts:545 in Firefox and WebKit (keeps long content inside viewport). Allure then marked the weekly report incomplete because cross-browser bundles were absent. |
| [39106821544](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/39106821544) | scheduled, ace951a… | failure | 1,039 s; test bundles were published, but Allure publication failed with SSH publication failed: connection_timeout, followed by invalid publication JSON. |

The inspected aggregate jobs failed closed when required results were cancelled/failed. No
false-green was identified in these runs. This is not an exhaustive audit of all historical runs.

### Caching and duplication observations

The workflow already uses setup-node npm cache keyed by frontend/package-lock.json, setup-uv
cache keyed by uv.lock, and separate Playwright browser caches for smoke/mobile/extended/
cross-browser. Each isolated job still repeats npm ci, Vite build and browser installation by
design of runner isolation; cache-hit values for the inspected runs were not exported in the
available payload. #821 should measure cache hit/miss and artifact transfer before proposing any
change. Coverage must remain unchanged.

Static skip scan found no xfail; it found 11 Python skip markers and 21 test.skip references,
including explicit opt-in visual evidence, PostgreSQL-only locking/concurrency tests and platform
capability skips. Current scheduled Allure snapshots reported 14–15 skipped tests. Each skip needs
classification in #819; none is silently treated as passing coverage.

## 6. Infrastructure and recovery evidence

### #848 — PostgreSQL connection budget

Repository evidence proves only the per-engine defaults: pool_size=10, max_overflow=20,
pool_timeout=30 s, pool_pre_ping=true. It does not provide production max_connections,
reserved superuser slots, pooler settings, number of backend/worker/blue-green processes,
connection occupancy, wait/timeout history or safe rollout headroom.

Verdict: BLOCKED. #848 can start with a read-only inventory, but cannot be READY for a
fail-closed rollout gate until owner-approved production-shaped connection facts and a bounded
calculation are available. No PostgreSQL setting was changed.

### #849 — off-host backup and clean-host restore

scripts/db_maintenance.py creates a custom-format pg_dump through Compose under
.artifacts/operations/backups, verifies it with pg_restore --list, and creates a safety dump
before an explicitly confirmed restore. This is a local backup/restore helper.

No repository evidence proves an off-host copy, Windows-PC/SFTP transfer, digest verification on
the independent copy, clean-host restore, RPO/RTO or latest successful drill. This is an evidence
gap, not proof that backups do not exist.

Verdict: BLOCKED. The owner/security gate and the clean-host/independent host are required;
the audit did not run a restore and did not copy data.

### #850 — container runtime hardening

backend/Dockerfile and bot/Dockerfile use non-root appuser; CI self-check commands use
--read-only --cap-drop ALL --security-opt no-new-privileges --user. The regular Compose services
do not uniformly declare those runtime restrictions; the Allure origin is explicitly read-only
with a non-root UID and tmpfs. This is a bounded, source-verifiable gap for #850; no runtime
change was made.

### #851 — immutable images and SBOM

Some sources are pinned by digest: uv copy and Hermes Python/Alpine bases. Backend and bot build
Dockerfiles still use mutable node:24-alpine/python:3.14-slim tags, while Compose defaults also
contain mutable PostgreSQL/Caddy/cloudflared references (cloudflared:latest). Deployment scripts
verify immutable references at release time, which is a downstream gate rather than a complete
source pin.

The inspected CI source has Trivy/image contract checks and license/provenance generation, but no
bounded backend/bot SBOM publication step using a recognized SBOM format was found in this audit.
Exact registry artifacts and current production image digests were not queried.

### #822 — observability

Application request/SQL/pool fields are already structured and sanitized in source. Production
log retention, export, worker heartbeat freshness, queue lag, backup freshness and independent
uptime evidence are NO_DATA. #822 must consume #817/#818/#820 and the independently verified
#849 signal; it must not invent a production percentile from the local build or CI.

## 7. Problems and prioritization

Confidence describes confidence in the finding itself, not confidence that production is broken.

| Priority | Finding | Impact | Confidence | Effort | Status |
|---|---|---|---|---|---|
| P0 | Effective PostgreSQL connection budget is unknown beyond the 30-connection per-engine default ceiling | Connection exhaustion, pool waits and unsafe blue/green rollout | High | M | BLOCKED / #848 |
| P0 | Off-host and clean-host recovery proof is absent from repository evidence | Full VPS loss may not be recoverable within owner target | High for evidence gap; not a claim of absent backups | L | BLOCKED / #849 |
| P1 | Entry JS gzip is 96,775 B against existing 96,000 B budget | Initial-load budget is already exceeded by 775 B | High | XS–S | VERIFIED, implementation deferred |
| P1 | Scheduled extended mobile regression fails the viewport assertion in Firefox/WebKit | Mobile regression truth and weekly report completeness | High | M | VERIFIED failure, #819/#821 input |
| P1 | Scheduled Allure publication has SSH timeout/invalid publication JSON path | Loss of discoverable regression evidence | High | M | VERIFIED failure, #821/#822 input |
| P1 | Media PRs #1094/#1109/#1111/#1115 are draft and/or based on stale/non-master heads | Asset/manifest conflicts with #818/#823 and semantic media risk | High | M | VERIFIED coordination risk |
| P1 | Runtime hardening and immutable source image/SBOM contract are incomplete in source | Container escape/supply-chain and auditability risk | Medium–high | M | NOT_PROVEN/OPEN #850/#851 |
| P2 | No production latency/pool/slow-query window is available | Cannot rank backend bottlenecks or set accepted SLOs | High | M | NO_DATA |
| P2 | Query invalidation and render surface is large; duplicate requests are not proven | Potential Today/Coach/Nutrition overfetch and render cost | Medium | M | NOT_PROVEN, #817/#818 |
| P2 | Local Windows worktree/venv restrictions block Docker/full Python reproduction | Slower local verification; not a product defect by itself | High | S | BLOCKED local environment |

## 8. Proposed budgets

These are PROPOSED, not accepted targets or production measurements. Owner approval and a
production-shaped baseline must precede using them as release gates.

| Surface | Proposed starting budget | Measurement source required |
|---|---|---|
| Today/Workout/Nutrition/Programs authenticated reads | p95 <=500 ms, p99 <=1,000 ms; 5xx and timeout rates separate | Sanitized production window or fixed isolated PostgreSQL load |
| Coach OS and aggregate reports | p95 <=800 ms, p99 <=1,500 ms | Same; split DB, serialization and total request time |
| SQL pool | Steady checked-out <=80% of configured pool, overflow 0 in normal traffic, pool timeout 0 | Structured request logs plus DB/pool metrics; #848 owns rollout calculation |
| Initial JS | Keep raw <=310,000 B and gzip <=96,000 B; current gzip is over by 775 B | Existing scripts/check_frontend_performance.mjs |
| Initial CSS/public assets | Raw <=335,000 B CSS, gzip <=52,500 B CSS, public raw <=850,000 B, largest asset <=120,000 B | Existing performance guard |
| Authenticated route chunks | Target <=60,000 B gzip per major route chunk; exceptions require evidence | Vite manifest plus browser transfer/route trace |
| Lab mobile UX | LCP p75 <=2.5 s, INP p75 <=200 ms, CLS p75 <=0.1 as provisional web thresholds | Real-user field data; TMA/iPhone split required |
| CI | Required PR wall <=25 min on representative run; no Python/frontend shard >7 min without reason; no coverage reduction | GitHub job timestamps, CI_TIMING and cache-hit data |
| Recovery | No numeric RPO/RTO proposed here | Owner decision in #849 based on measured dump size, copy and clean-host drill |

## 9. Parallel development and conflict matrix

### Safe parallel tracks after explicit V11 activation

| Track | Can run with | Must not overlap silently with |
|---|---|---|
| #819 test/coverage inventory | #816 and #821 | Characterization changes that alter what is being measured |
| #821 CI timing/cache audit | #819, #850, #851 | Workflow edits from media/security PRs without exact-head recheck |
| #817 backend profiling | #818 and #849 planning | #1086 Docker/security patch and any schema-changing work without rebase |
| #849 recovery design/evidence | #817, #818, #821 | Production restore/copy operations without explicit owner approval |
| #850/#851 container hardening and supply chain | Each other in analysis phase | Merge ordering with #1086; release image contract must be checked once |
| #818 frontend profiling | #817, #819, #821 | #986 media manifest/asset changes without a single rebased head |

### Current independent work to preserve

- #1091 is already included in baseline 9b5a24b4; do not roll it back while profiling rest or
  Active Workout.
- #986 is still open. Draft PR #1094 (07f27a7…), #1109 (a1755e1…), #1111
  (34cb999…) and #1115 (63adc21…) cover media/source pilots; they require their own
  visual, CI and semantic gates and should be rebased before any merge.
- #1072 is open scientific nutrition validation; research/content decisions are not a license
  for a broad nutrition performance rewrite.
- #1086 is open container libexpat1 security work; it overlaps backend image/container checks
  and must be coordinated with #850/#851.

## 10. Recommended execution order

This is a planning recommendation only; it does not activate work.

1. Keep #815 evidence and exact baseline immutable; resolve owner decisions below.
2. Start #819 and #821 in parallel to classify skips, reproduce the mobile failure, explain
   scheduled-report failure, and record cache-hit timings.
3. Run #817 backend profiling with isolated synthetic PostgreSQL; calculate #848 before any
   rollout or pool change.
4. Run #818 frontend route/network/render profiling, keeping #986 media review separate; reduce
   the 775 B guard breach only in a separately scoped implementation task.
5. Run #820 concurrency/data-integrity characterization and #849 independent recovery drill.
6. Use those results for #822 structured operational signals, with UNKNOWN/NO_DATA states
   explicit and no new paid monitoring stack.
7. Coordinate #850/#851 with #1086, then run exact container/security/SBOM checks.
8. Do #816/#823 targeted cleanup only after behavior coverage and media/content conflicts are
   characterized.
9. #824 is last: exact-head checks, owner visual/semantic gates, merge, deploy and production
   smoke remain separate gates.

## 11. READY / BLOCKED verdicts requested

| Task | Verdict | Why |
|---|---|---|
| #848 | **BLOCKED** | Per-engine defaults are known, but effective production total, PostgreSQL headroom and rollout topology are not proven. |
| #849 | **BLOCKED** | Repository contains only a local Compose dump/restore helper; off-host copy, independent host and clean restore are not proven and require owner/security decisions. |
| #819 | **READY** | The baseline is sufficient to start a bounded read-only test/coverage/regression audit. Current scheduled mobile and Allure failures are actionable inputs; local Windows limitations do not authorize weakening assertions. |

READY for #819 means ready to investigate, not ready to merge, release or close #815.

## 12. Owner decisions required

1. Explicitly activate selected V11 child tasks after reviewing this baseline; read-only #815
   authorization alone is not activation of #816–#824 or #848–#851.
2. Approve the proposed budgets or provide product-specific targets and measurement windows.
3. For #848, provide/approve the production topology and effective connection budget inputs:
   PostgreSQL max_connections, reserved slots, pooler, process/replica/blue-green counts,
   expected headroom and fail-closed rollout rule.
4. For #849, approve the Windows-PC/SFTP/off-host design, key ownership, retention, RPO/RTO and
   clean-host drill location. Do not upload real database contents to GitHub or this repository.
5. For #821/#819, decide whether scheduled mobile failures and incomplete Allure publication are
   release-blocking until fixed, while retaining meaningful coverage.
6. For #818/#986, approve the order of media/source PRs and the required visual/semantic gates.
7. For #850/#851/#1086, choose the owner-approved base image/SBOM and runtime-hardening contract.
8. For #822, name the existing sanitized telemetry source and accountable owner; otherwise record
   NO_DATA rather than creating a speculative monitoring stack.

## 13. Evidence boundary

This report is a reproducible engineering baseline, not a production readiness certificate. It
does not claim that production is slow, that backups are missing, that PostgreSQL is exhausted,
or that a particular React component is the bottleneck. Those claims require the measurement
sources explicitly listed above.
