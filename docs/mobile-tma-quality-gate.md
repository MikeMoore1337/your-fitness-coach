# Mobile Web/TMA quality gate

## Контракт поверхностей

Mobile Web и Telegram Mini App — основные клиентские поверхности Your Fitness Coach. Desktop Web
остаётся полноценной поверхностью для тех же функций и подходит для подробных и массовых сценариев.
Coach/Admin могут быть desktop-first, но их базовый smartphone smoke обязателен: изменение общего
frontend не должно случайно делать эти разделы недоступными на телефоне.

Все поверхности используют один React frontend, один backend/API, одну бизнес-логику и одну active
approved design system `DESIGN_V2_1`. TMA не имеет отдельного component tree, палитры, typography,
навигационного языка или feature logic. Допустимые отличия ограничены platform adapter: signed
`initData`, Telegram `BackButton`, theme/viewport/safe-area events, shell colors, lifecycle и
обоснованные platform capabilities.

Task `72` является финальным platform hardening перед релизом. Она не заменяет этот continuous gate
и не является первым TMA pass для задач `50–70`.

## Общий test harness

Переиспользуемая основа находится в следующих файлах:

- `frontend/tests/helpers/telegramMock.ts` — deterministic Telegram mock для unit/component tests;
- `frontend/tests/e2e/fixtures/mobile-tma.ts` — mobile contexts, Telegram runtime controller,
  lifecycle/network helpers и layout assertions для Playwright;
- `frontend/tests/e2e/fixtures/platform-api.ts` — компактный stateful API seam для platform smoke;
- `frontend/tests/e2e/tma-smoke.spec.ts` — continuous Mobile Web/TMA smoke.
- `frontend/tests/e2e/demo-mode.spec.ts` — три изолированных demo scenario, reset/expiry и TMA
  boundary без auth/linking side effects.

Playwright harness задаёт `360x800`, `390x844` и `430x932`, настоящий touch context и
`hover: none`. Telegram mock содержит официальные поля `initData`, `version`, `platform`,
`colorScheme`, `isActive`, `viewportHeight`, `viewportStableHeight`, `safeAreaInset`,
`contentSafeAreaInset` и lifecycle `BackButton`. Он управляемо отправляет `themeChanged`,
`viewportChanged`, `safeAreaChanged`, `contentSafeAreaChanged`, `activated`, `deactivated` и
`backButtonClicked`, а также фиксирует обращения к `MainButton`, `SecondaryButton` и
`HapticFeedback` без реального Telegram client.

Имена и семантика сверены с официальным Telegram Mini Apps API:
`https://core.telegram.org/bots/webapps`. При изменении mock-контракта их нужно перепроверять заново,
а не переносить из памяти или стороннего SDK.

Общие assertions проверяют horizontal overflow, минимальную геометрию touch targets и пересечение
fixed/sticky UI с action/content. Network helper переключает offline/reconnect на уровне browser
context; feature API mock может одновременно моделировать отказ только backend-запросов.

## Playwright E2E contract

Этот раздел является общим контрактом для `frontend/tests/e2e/**` и применяется вместе с
требованиями конкретного сценария. Он не меняет продуктовую семантику и не разрешает добавлять
production hooks только ради удобства теста.

### Локаторы и assertions

1. Сначала используется доступная семантика: role и accessible name, затем scoped landmark,
   dialog, section, form или card. Повторяемый сценарий выносит такой scope в helper с явным
   именем, а не скрывает глобальный поиск.
2. `.first()`, `.last()`, `.nth()` и positional/CSS selectors допустимы только когда тест сначала
   фиксирует cardinality или связывает элемент с активным продуктовым идентификатором, именем,
   ролью, состоянием (`aria-current`, `aria-selected`) либо иным действующим инвариантом.
   Исторический порядок DOM сам по себе инвариантом не является.
3. `data-testid` добавляется только если действующий role/name и scoped semantic locator не могут
   выразить контракт. Ненужный production hook удаляется после миграции потребителей на семантику.
4. `toHaveCSS` и bounding-box assertions описывают только действующий visual/platform contract:
   active design source, touch target, overflow, safe area, keyboard/fixed/sticky overlap или
   доказуемую responsive order. Цвет, размер, radius, `position` и DOM-порядок без такой опоры не
   являются regression contract.
5. Ожидания должны быть event-, response-, state- или assertion-driven. `waitForTimeout`,
   произвольные sleeps, увеличенные retries/timeouts, `skip`/`fixme` и обход strict locator
   errors не используются для закрытия регрессии. Внешний runtime prerequisite остаётся
   отдельным явно обозначенным lane и не считается PASS обычного smoke.

### Lanes и evidence

- `npm run e2e:ci` — authoritative Chromium suite; в CI он выполняется четырьмя shards и включает
  `tma-smoke.spec.ts` и `demo-mode.spec.ts`.
- `npm run e2e:migrated-stack` — отдельный authoritative Chromium lane с FastAPI и PostgreSQL;
  он проверяет реальный browser/API/database path и не заменяется route mock.
- `playwright.cross-browser.config.ts` — дополнительный локальный Chromium/Firefox/WebKit lane;
  он не является CI gate, пока не подключён отдельной job.
- `csp-theme-bootstrap.spec.ts` требует `YFC_FASTAPI_ORIGIN=1`; без поднятого FastAPI это
  отдельный неисполненный prerequisite, а не успешная проверка.
- Owner-checkpoint screenshot scenarios (`YFC_CAPTURE_*`) — opt-in visual evidence и не входят в
  regression count без соответствующего флага. Их `skip` не должен скрывать поведенческий тест.

В итоговом отчёте automated Mobile Web, mocked TMA, migrated real browser/API stack, real Telegram
и physical-device evidence перечисляются раздельно. Browser/mock результат никогда не выдаётся за
доказательство реального Telegram client или физического устройства.

### Task 146: mobile visual/layout lanes

`mobile-ui-regression.spec.ts` содержит узкий risk-based набор для Today, Active Workout, Nutrition,
Progress, Profile и mocked TMA. Критический lane запускается командами:

```bash
cd frontend
npm run e2e:mobile-regression
```

Он выполняет Chromium и mobile WebKit на `390x844`; тесты дополнительно проверяют `360x800`,
`430x932`, TMA safe-area/viewport/lifecycle, keyboard/fixed navigation, touch targets,
horizontal overflow и long-content geometry. `320x800` и landscape остаются stress-проверками
scheduled/extended lane:

```bash
cd frontend
npm run e2e:mobile-regression:extended
```

PR profile включает critical Chromium + WebKit lane. Extended Firefox + WebKit lane выполняется
только schedule/manual и не запускает production deployment. Baselines разделены по browser project
и runner platform, чтобы Windows и Linux не смешивали renderer/font raster; их принимают только
после review diff и явного `MANUAL_VISUAL_APPROVAL`. Визуальные snapshots не заменяют geometry,
accessibility, mocked TMA или migrated real-backend checks.

Для setup/install/build и command-group timing новые jobs используют `CI_TIMING` в логах и
`.artifacts/runtime/ci/*-timing.jsonl` в job artifact. Кешируются только npm download cache,
uv cache и Playwright browser cache; `node_modules`, credentials и dynamic test state не кешируются.

## Что фиксирует continuous smoke

`tma-smoke.spec.ts` проверяет без дублирования больших feature suites:

1. automatic TMA auth через raw mock `initData` без browser login;
2. одинаковые YFC tokens, section tree и bottom navigation в Mobile Web и TMA;
3. Light/Dark и runtime theme change без потери route/draft/dialog/workout state;
4. current/stable viewport, safe area, content safe area, foreground/background и BackButton;
5. запуск тренировки, локальную запись offline, однократный reconnect и resume после reload;
6. nutrition entry с focused mobile input и скрытием bottom navigation над keyboard;
7. открытие/возврат Today, Progress и Profile;
8. touch, отсутствие horizontal overflow и отсутствие Telegram-only palette/component tree;
9. browser Mobile Web regression на том же API seam.
10. единый недельный обзор: insufficient/sufficient data, пропуск вопросов, accept/keep/defer,
    восстановление черновика после reload и одинаковое поведение Mobile Web/TMA.
11. три demo scenario на `360/390`, Dark TMA mock, reset/reload, expired/forbidden states и
    отсутствие auth/notification/invitation запросов.

Глубокие бизнес-сценарии остаются в существующих feature e2e:
`active-workout-experience.spec.ts`, `offline-workout.spec.ts`, `nutrition-diary.spec.ts`,
`progress-experience.spec.ts` и `today-dashboard.spec.ts`.

Локальный focused gate:

```bash
cd frontend
npm run e2e:tma-smoke
```

Обычный `npm run e2e:ci` также включает `tma-smoke.spec.ts` и `demo-mode.spec.ts`, поэтому smoke является частью
репозиторного CI, а не отдельной ручной проверкой. Dedicated `mobile-ui-regression.spec.ts` намеренно не дублируется
в этом suite: его critical-проверки являются обязательным отдельным `frontend-mobile-regression` job с собственными
browser/platform snapshots.

## Checklist для client-facing tasks 50–70

Для каждой новой или изменённой client-facing функции:

- [ ] расширен `tma-smoke.spec.ts` или явно подтверждено, что существующий scenario уже покрывает
      изменённый platform contract;
- [ ] основной flow пройден на `360x800` и `390x844` в touch context с `hover: none`;
- [ ] нет horizontal overflow, а основные touch targets практически удобны;
- [ ] при input/sticky/fixed UI проверены keyboard, focus, safe area, content safe area и отсутствие
      перекрытия primary/recovery actions;
- [ ] recoverable draft/queue/active state переживает применимые theme, viewport,
      background/foreground, reload и temporary offline/reconnect transitions;
- [ ] Mobile Web и TMA используют общий component tree, tokens, labels и business behavior;
- [ ] browser desktop regression не сломан;
- [ ] очевидная TMA regression исправлена в текущей task и не отложена до task `72`;
- [ ] automated Mobile Web, mocked TMA и real-device evidence перечислены раздельно.

## Уровни evidence

Browser emulation и mocked Telegram adapter обязательны для автоматизации, но не доказывают работу
реального Telegram client. В отчёте отдельно указываются:

1. automated Mobile Web;
2. mocked TMA adapter;
3. real Telegram Android;
4. real Telegram iOS;
5. Telegram Desktop, если проверялся;
6. непроверенные среды и ограничения.

Raw `initData` разрешено передавать только backend validation boundary. Его нельзя писать в logs,
analytics, rendered errors, screenshots или third-party telemetry. Harness использует только
фиктивные test values и не обращается к Telegram, BotFather или production services.
