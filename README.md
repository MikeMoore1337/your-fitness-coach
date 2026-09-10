# Your Fitness Coach

Your Fitness Coach — единый продукт для самостоятельных пользователей и тренеров. Он доступен как
адаптивное Web-приложение и Telegram Mini App, использует общий FastAPI backend и PostgreSQL, а
Aiogram-бот отвечает за Telegram-вход, поддержку и разрешённые уведомления.

Публичный репозиторий содержит production-код, миграции, автоматические проверки и безопасные
инструкции для разработчиков. Marketing-описание продукта живёт на публичном Landing; внутренние
operator runbooks хранятся отдельно и доступны только владельцу/release operators.

## Архитектура репозитория

```text
frontend/       React 19, TypeScript, Vite, TanStack Query, Vitest, Playwright
backend/        FastAPI, SQLAlchemy, Alembic, worker и backend tests
bot/            Aiogram bot и bot tests
deploy/         Caddy edge configuration
scripts/        проверки, генераторы, backup/restore и deployment helpers
tests/          cross-stack integration tests
docs/           публичные русскоязычные product и architecture contracts
codex-backlog/  публичные lifecycle rules и исторический release context
.agents/        роли, skills и verification references для Codex
.artifacts/     canonical task/runtime/operations artifacts; не коммитится
```

Основные runtime-потоки:

```text
Browser / Telegram Mini App -> edge -> FastAPI -> PostgreSQL
Telegram Bot                -> FastAPI internal API
Worker                      -> PostgreSQL и разрешённые delivery integrations
```

Авторизация, ownership и критическая валидация обеспечиваются backend-границами. Web и TMA не
имеют отдельных баз данных или параллельных бизнес-правил.

## Требования

Поддерживаемые CI/runtime версии:

- Python `3.14`;
- Node.js `24` и npm с `frontend/package-lock.json`;
- PostgreSQL `16`;
- Docker Engine или Docker Desktop с Compose v2;
- Git.

Основной documented workflow рассчитан на Linux/macOS и POSIX-compatible shell (`bash`/`zsh`).
Для запуска через Compose достаточно Docker; Python и Node нужны для разработки, генерации API
types и проверок вне контейнеров. Краткие различия локального запуска на Windows приведены ниже.

## Безопасная локальная настройка

Создайте локальный `.env` из versioned шаблона:

```bash
cp .env.example .env
```

Шаблон использует только локальные placeholders, `APP_ENV=dev`, включённый dev-login и выключенный
bot polling. Перед совместным использованием замените локальные пароли и `SECRET_KEY`. Никогда не
копируйте в репозиторий production `.env`, OAuth secrets, Telegram tokens, dumps или private keys.

Проверьте конфигурацию без раскрытия вычисленных значений:

```bash
docker compose config --quiet
```

Не запускайте `docker compose config` без `--quiet`: полный render может содержать секреты из
локального `.env`.

Production использует отдельный secret store/`.env`. При `APP_ENV=prod` приложение и deployment
script требуют production-safe flags, реальные secrets и проверенные immutable image references с
`@sha256`; локальные defaults из `.env.example` для production непригодны.

## Быстрый запуск через Docker

Поднимите PostgreSQL, migrations/setup, backend с собранным frontend и worker. Bot и публичный edge
не запускаются этой командой:

```bash
docker compose up -d --build backend worker
docker compose ps
```

После readiness приложение доступно на <http://127.0.0.1:8000>, API documentation — на
<http://127.0.0.1:8000/docs>, health checks — `/health/live` и `/health/ready`.

Остановка без удаления PostgreSQL volume:

```bash
docker compose down
```

Bot запускайте только с отдельным тестовым token и осознанно включённым
`BOT_POLLING_ENABLED=true`. Не используйте production token для локальной разработки.

## Разработка с hot reload

Создайте окружение и установите locked project dependencies:

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt -r bot/requirements.txt
npm --prefix frontend ci
docker compose up -d db
```

При запуске backend на host замените только host базы на `127.0.0.1` в переменной текущего shell;
значение пароля должно совпадать с вашим локальным `.env`:

```bash
export DATABASE_URL='postgresql+psycopg://fitminiapp:local-dev-password-change-before-sharing@127.0.0.1:5432/fitminiapp'
(cd backend && ../.venv/bin/python -m alembic upgrade head)
.venv/bin/python -m uvicorn fitminiapp_api.main:app \
  --app-dir backend \
  --reload \
  --host 127.0.0.1 \
  --port 8000
```

В другом терминале:

```bash
npm --prefix frontend run dev
```

Vite открывается на <http://127.0.0.1:5173> и проксирует `/api`, `/health` и exercise-guide assets
на backend `127.0.0.1:8000`.

Не коммитьте созданный `.env`.

### Локальная разработка на Windows

Production-like и CI команды выше остаются canonical. При локальной работе в PowerShell замените:

- `cp .env.example .env` на `Copy-Item .env.example .env`;
- `python3.14` на `py -3.14`;
- `.venv/bin/python` на `.venv\Scripts\python.exe`;
- `export DATABASE_URL='...'` на `$env:DATABASE_URL = '...'`.

Остальные команды `docker compose` и `npm --prefix frontend ...` одинаковы. WSL также может
использовать основной POSIX workflow без этих замен.

## Миграции и API types

Применить миграции в Compose-контуре:

```bash
docker compose run --rm setup
```

Проверить, что model metadata не требует новой миграции:

```bash
(cd backend && ../.venv/bin/python -m alembic check)
```

После изменения FastAPI contract перегенерируйте OpenAPI snapshot и TypeScript types:

```bash
npm --prefix frontend run api:types
git diff -- frontend/openapi.json frontend/src/shared/api/schema.d.ts
```

Оба generated файла являются tracked source of truth и должны изменяться только вместе с
намеренным API contract.

## Проверки

Единая подготовка и быстрый route-aware набор локальных checks:

```bash
.venv/bin/python scripts/local_checks.py
```

В Windows PowerShell используйте `.\.venv\Scripts\python.exe scripts\local_checks.py`. Команда
сама определяет Git worktree, активный Python, `PATH`/`PYTHONPATH`, безопасные test `APP_*` и
изолированную SQLite-базу в отдельном каталоге запуска под `.artifacts/runtime`, который удаляется
после завершения; переданный `TEST_DATABASE_URL` используется как изолированный test database URL.
По умолчанию выполняется только relevant fast route. Полный
GitHub route можно добровольно проверить через `--full`; его результат не создаёт release evidence
и не заменяет required GitHub `checks`.

Выбирайте targeted набор по изменённому риску. Скрипт Python складывает pytest cache и temp files в
`.artifacts/runtime/{cache,tmp,tests}/` согласно [lifecycle документации](docs/artifacts-lifecycle.md):

```bash
.venv/bin/python scripts/run_pytest.py backend/tests/test_account_lifecycle.py -q
.venv/bin/python scripts/run_pytest.py bot/tests -q
npm --prefix frontend run check
```

Browser/TMA regression:

```bash
(cd frontend && npx playwright install chromium && npm run e2e:tma-smoke)
```

Repository hooks и platform config:

```bash
.venv/bin/python -m pre_commit run --all-files
docker compose config --quiet
git diff --check
```

Полная CI matrix определена в [`.github/workflows/ci.yml`](.github/workflows/ci.yml). Она включает
frontend checks, browser tests, Python tests, migrated PostgreSQL smoke и dependency audits.
Scheduled Daily/Weekly scope и закрытые Allure-отчёты описаны в
[`docs/scheduled-regression-allure.md`](docs/scheduled-regression-allure.md).

## Mobile Web и Telegram Mini App

Mobile Web browser tests и mocked TMA adapter проверяют responsive layout, theme, safe-area,
keyboard, BackButton и lifecycle contracts, но не заменяют Telegram Android/iOS validation.

Корректные формулировки evidence:

- `Mobile Web automated` — браузерный viewport;
- `mocked TMA` — Telegram adapter эмулирован Playwright fixtures;
- `real Telegram Android/iOS` — только фактический запуск соответствующего клиента;
- `production validated` — только post-deploy checks на развёрнутой revision.

Не называйте mocked TMA или localhost production/real-device проверкой.

## Документация

- contributor architecture и task boundaries: [`AGENTS.md`](AGENTS.md);
- Mobile Web/TMA test contract: [`docs/mobile-tma-quality-gate.md`](docs/mobile-tma-quality-gate.md);
- public content и SEO boundaries: [`docs/seo/public-content.md`](docs/seo/public-content.md);
- blue/green production contract: [`docs/production-deployment.md`](docs/production-deployment.md);
- domain contracts: [`docs/exercise-domain.md`](docs/exercise-domain.md),
  [`docs/food-domain.md`](docs/food-domain.md) и
  [`docs/training-analytics.md`](docs/training-analytics.md);
- активная UI-система: [`docs/design/design-direction-v2.1.md`](docs/design/design-direction-v2.1.md);
  lifecycle локальных artifacts: [`docs/artifacts-lifecycle.md`](docs/artifacts-lifecycle.md).

Документы под `docs/` ведутся на русском. Детальные временные audit reports, screenshots и test
traces хранятся в `.artifacts/tasks/<TASK_ID>/evidence/` или `.artifacts/runtime/tests/` и не
коммитятся. Внутренние operational, security, provider,
legal-risk и owner-only документы также не публикуются в Git.

## Production и deployment

Новая production revision попадает в удалённый `master` только как результат merged pull request.
Ruleset требует green check `checks`, запрещает direct push, force-push и удаление `master`; workflow
дополнительно проверяет provenance exact SHA и его соответствие текущему `origin/master`.

Merge PR является release authorization. После него человек не участвует в normal deployment path:
post-merge CI публикует проверенные immutable images и автоматически запускает
`.github/workflows/deploy.yml`; `production` environment не содержит reviewers или wait timer.
Workflow собирает bundle из exact commit и передаёт его на host вместе с image refs и migration
manifest. Fail-closed `scripts/deploy_production.sh` проверяет `.deployment-sha`, затем выполняет
preflight, PostgreSQL backup, migrations, blue/green rollout, smoke/observation gates и
автоматический возврат прежнего slot при ошибке до commit state; host не требует Git checkout.

`workflow_dispatch` CI используется только для bounded scheduled regression на `master` с явным
выбором `daily` или `weekly`; он не выбирает произвольный production SHA и не запускает deploy.
History rewrite, direct/force push, ручные production-команды,
bootstrap, восстановление инфраструктуры, DNS/Cloudflare/secrets и deployment SHA вне текущего
merged `master` остаются exceptional production actions и требуют отдельного owner approval,
проверенной backup-ветки и operator preflight.

## Ограничения

- Real Telegram Android/iOS и production provider checks требуют внешней среды и не могут быть
  доказаны локальными fixtures.
- Локальный dev-login запрещён production validation.
- Repository не хранит production secrets, off-host backups, provider consoles, alert destinations
  или restricted deletion ledger.
- Owner-only roadmap, findings и task-файлы не публикуются в Git и не являются частью runtime.
