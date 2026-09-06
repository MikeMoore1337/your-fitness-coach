# Scheduled regression и закрытые Allure-отчёты

Этот документ описывает единственный scheduled-контур YFC и его закрытые HTML-отчёты. Он
дополняет быстрый PR CI и не заменяет targeted проверки, QA, real-device или production
validation.

## Топология и ownership

Владелец расписания — `.github/workflows/ci.yml`. Второго nightly/weekly workflow для тех же
suite нет.

| Запуск | Cron (UTC) | Время `Europe/Moscow` | Профиль |
| --- | --- | --- | --- |
| Daily | `17 2 * * *` | каждый день 05:17 | `daily-regression` |
| Weekly | `43 3 * * 0` | воскресенье 06:43 | `weekly-exhaustive` |

`workflow_dispatch` запускается только на `master` и принимает `run_kind`: `daily` или
`weekly`. Неизвестный cron не классифицируется и завершается ошибкой. Выбор профиля и периода
отчёта находится в `scripts/scheduled_regression.py`, а соответствие профилей CI-группам — в
`scripts/ci_contract.py`.

`pr-critical` остаётся обычным blocking CI. Daily/Weekly не являются его dependency и не
входят в ожидание merge или production deploy.

## Профили

Daily запускает bounded deterministic набор:

- `quality`;
- `frontend-checks`;
- `frontend-e2e` (4 shard, Chromium);
- `frontend-mobile-regression` (Chromium + WebKit);
- `python-tests` (4 shard, PostgreSQL test stack);
- `migrated-stack` (Alembic, migrated API и browser smoke);
- `critical-smoke`;
- `workflow-config`.

Weekly включает Daily и дополнительно запускает `policy`, dependency audit, расширенный mobile
набор, `frontend-cross-browser` (Chromium + Firefox + WebKit), image/deployment/container
contracts. Тестовый Allure-агрегат ожидает только suite, которые фактически производят Allure
results: `frontend-checks`, `frontend-e2e`, `frontend-mobile-regression`, `python-tests`,
`migrated-stack`, а для Weekly также `frontend-mobile-regression-extended` и
`frontend-cross-browser`. Native policy, audit и deployment результаты остаются в обычных CI
jobs.

Новая UI Quality task подключает уже существующую suite через профиль и group registry. Она не
создаёт второй scheduler и не дублирует screenshots, traces или visual baselines.

## Локальное воспроизведение

Проверить routing без запуска тестов:

```powershell
& .venv\Scripts\python.exe scripts\scheduled_regression.py contract
& .venv\Scripts\python.exe scripts\ci_contract.py route --event schedule --schedule-cron "17 2 * * *" --json
& .venv\Scripts\python.exe scripts\ci_contract.py route --event workflow_dispatch --run-kind weekly --json
```

Обычные команды suite остаются теми же, что и в group registry:

```powershell
npm --prefix frontend ci
npm --prefix frontend run check
npm --prefix frontend run e2e:ci
npm --prefix frontend run e2e:mobile-regression
npm --prefix frontend run e2e:mobile-regression:extended
npm --prefix frontend run e2e:cross-browser
& .venv\Scripts\python.exe scripts\run_pytest.py backend\tests bot\tests -q -n 4 --dist=worksteal
```

Allure adapters включаются только при наличии `ALLURE_RESULTS_DIR`. Для локального запуска
установите их из отдельного scheduled-only lockfile (обычный `frontend/package-lock.json` при
этом не меняется) и используйте путь под `.artifacts/runtime/tests/`:

```powershell
npm --prefix frontend\scheduled-report ci --omit=peer --ignore-scripts --no-audit --no-fund
$env:ALLURE_VITEST_REPORTER_PATH = (Resolve-Path 'frontend\scheduled-report\node_modules\allure-vitest\dist\reporter.js').Path
$env:ALLURE_PLAYWRIGHT_REPORTER_PATH = (Resolve-Path 'frontend\scheduled-report\node_modules\allure-playwright').Path
$env:ALLURE_RESULTS_DIR = "$PWD\.artifacts\runtime\tests\allure-results\local"
npm --prefix frontend run test
& .venv\Scripts\python.exe scripts\run_pytest.py backend\tests bot\tests -q
```

Playwright сохраняет native `list`/GitHub reporter и добавляет `allure-playwright` только в
scheduled/report mode. Vitest сохраняет `default` reporter и аналогично добавляет
`allure-vitest`. `run_pytest.py` передаёт `--alluredir` только при заданном env. В CI этот
scheduled-only lockfile устанавливается только scheduled jobs; обычный PR `npm ci` его не
трогает. Python adapter аналогично вынесен в `backend/requirements-scheduled-report.txt` и не
входит в общий `requirements-dev.txt`.

## Aggregation и публикация

Каждый parallel job пишет в отдельный result directory. Composite action
`.github/actions/upload-allure-results` упаковывает его в tar.gz, шифрует AES-256-CBC с PBKDF2 и
проверкой HMAC, а затем загружает только короткоживущий encrypted Actions artifact. Plaintext
results, HTML, screenshots и traces не используются как межjob transport.

Изолированный `scheduled-report` job:

1. скачивает artifacts только с текущим `run_id`;
2. проверяет целостность и расшифровывает bundles;
3. добавляет suite/tier/run-kind labels, browser и synthetic dataset parameters;
4. проверяет attachments и generated report на traversal, symlink и чувствительные строки;
5. генерирует Allure HTML независимо от verdict тестовых jobs;
6. публикует immutable report и только после этого обновляет `latest` и root index;
7. пишет прямую ссылку в GitHub Actions Summary.

Ожидаемые пути на закрытом origin:

```text
https://allure.your-fitness-coach.ru/
https://allure.your-fitness-coach.ru/daily/latest/
https://allure.your-fitness-coach.ru/daily/YYYY-MM-DD/<run-id>/
https://allure.your-fitness-coach.ru/weekly/latest/
https://allure.your-fitness-coach.ru/weekly/YYYY-Www/<run-id>/
```

Immutable path не перезаписывается. `latest` и history содержат только опубликованные entries.
При missing/malformed suite создаётся synthetic failed integrity case и report получает статус
`incomplete`; ссылка может быть опубликована для диагностики, но финальный scheduled gate
остаётся красным. При test failure report публикуется с честными failed counts, а исходный
workflow также остаётся красным.

## Закрытый hosting contract

Выбран отдельный Cloudflare Worker `yfc-allure-report-origin` как static origin с приватным R2
binding `REPORTS`; его custom domain — `https://allure.your-fitness-coach.ru`. Worker делает только
GET/HEAD, превращает `/` и пути с trailing slash в точный `index.html`, не выполняет listing и
возвращает controlled `404` для отсутствующих объектов. `workers.dev`, public `r2.dev`, Pages,
прямой R2-origin и публичный directory listing не используются. Worker-конфигурация находится в
`deploy/allure-report-worker/wrangler.toml`; bucket — `yfc-allure-reports`.

Cloudflare Access application создаётся до включения custom domain Worker; policy — default deny и
explicit owner/team allowlist. `Include Everyone`, `all valid emails`, public bypass и shared-link
access запрещены. Custom Domain Worker создаёт управляемую DNS-запись сам, поэтому отдельный
ручной CNAME не добавляется.

До внешней настройки требуется отдельный owner checkpoint с подтверждением Cloudflare plan и
стоимости. Только после него разрешены custom hostname/DNS, Access application/policy, R2 bucket,
service token и GitHub secrets. Используются только имена секретов:

- `ALLURE_REPORT_ENCRYPTION_KEY` — ключ шифрования bundles;
- `ALLURE_R2_ENDPOINT`;
- `ALLURE_R2_BUCKET`;
- `ALLURE_R2_ACCESS_KEY_ID`;
- `ALLURE_R2_SECRET_ACCESS_KEY`.

R2 credential ограничивается list/read/write/delete objects одного bucket; Worker binding получает
только read через приватный R2 API. Права на DNS, Access, Worker deployment, account
administration и human read не выдаются. Values не хранятся в repository, metadata, logs или report.

## Retention и budget

| Данные | Retention/limit |
| --- | ---: |
| Daily HTML/assets | 14 календарных дней |
| Weekly HTML/assets | последние 4 отчёта и не более 35 календарных дней |
| Encrypted raw results | 3 дня |
| Один encrypted bundle | до 50 MiB |
| Один generated report | до 100 MiB |

Удаление выполняется по server-authoritative `metadata/index.json`; cleanup queue сохраняется
при частичной ошибке и повторяется следующим publish. Current report не удаляется из retention
до публикации replacement. Cache-control для объектов — `private, no-store`.

До изменения baseline два scheduled запуска занимали примерно 3.22–3.28 минуты wall-clock и
около 29–30 Actions job-minutes при округлении job durations. Billing usage endpoint для
публичного repository в текущем read-only контексте недоступен (404), поэтому Actions quota и
фактическая стоимость должны быть проверены после внешнего owner checkpoint.

Для выбранного минимального варианта ориентир при действующем Cloudflare Free: R2 Standard даёт
10 GB-month, 1M Class A и 10M Class B операций в месяц без оплаты, egress бесплатен; сверх free
лимитов текущая ставка R2 Standard — $0.015/GB-month, $4.50/M Class A и $0.36/M Class B.
Workers Free даёт 100,000 входящих requests/day и до 10 ms CPU на invocation; Workers Paid
начинается с $5/month за account. Это тарифный ориентир, а не подтверждение текущего плана YFC:
owner должен проверить план, валюту/налоги и budget alerts в аккаунте. Источники: [R2 pricing]
(https://developers.cloudflare.com/r2/pricing/), [Workers pricing]
(https://developers.cloudflare.com/workers/platform/pricing/), [Access pricing]
(https://www.cloudflare.com/sase/products/access/).

После первого Daily и Weekly запуска в evidence фиксируются wall duration, job-minutes, cache hits,
report bytes, generation, publication и cleanup duration. Расчётный верхний bound активной HTML-
истории — 18 отчётов по 100 MiB, то есть около 1.8 GiB до фактического измерения; это не обещание
фактического storage usage или тарифа.

## Incident, rollback и rotation

- Публикация, decrypt, aggregation, generation и cleanup имеют отдельные failed statuses; их
  ошибка не превращается в зелёный test verdict.
- При publication/access incident сначала отключается соответствующий scheduled/manual route
  или возвращается предыдущий workflow commit; product runtime и PostgreSQL не затрагиваются.
- При ошибке до загрузки immutable report current prefix удаляется только по точному пути. После
  успешной загрузки immutable report prefix сохраняется для безопасного retry, а root index/state
  и latest считаются опубликованными только после соответствующих успешных операций; failed
  cleanup остаётся в queue.
- Для rollback внешней конфигурации удаляются/отключаются только exact Access application и
  Worker custom domain, Worker остаётся без `workers.dev`, отзывается R2 service credential,
  удаляются GitHub secrets и объекты bucket по подтверждённому cleanup plan. DNS не меняется
  широким wildcard.
- При rotation создаётся новый credential/key, проверяется новый run, затем старый secret/token
  отзывается. Значения ключей не записываются в task evidence.

## Границы evidence

Scheduled browser checks используют synthetic/local fixtures. `mocked TMA` не является real
Telegram Android/iOS evidence, локальный report не является production validation, а Weekly не
вызывает live paid AI provider и не использует real user sessions, prompts, files или database
rows.
