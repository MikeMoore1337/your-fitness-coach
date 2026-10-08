# Product v10: Landing dependency and positioning proposal (#758)

**Дата проверки:** 2026-10-08 (Europe/Moscow)
**Проверенный revision:** `2bdea709b2caadf2a275f008581cf9730c02b01d`
**Статус:** READ-ONLY PROPOSAL COMPLETE; LANDING IMPLEMENTATION NOT STARTED

Документ описывает следующий Landing model switch, но не разрешает его. В этой
задаче не меняются Landing, публичные copy, маршруты, стили, motion, аналитика,
Coach Demo или production configuration.

## Терминальное решение

Все согласованные non-Landing Product v10 children #745–#757 закрыты в GitHub;
runtime Product v10 delivery находится на защищённом `master`, а #757 добавил
только discovery-документ. Landing остаётся отдельным owner/model-switch gate.

`PRODUCT_V10_NON_LANDING_CONVEYOR=PASS`
`PRODUCT_V10_CONVEYOR=PAUSED_FOR_LANDING_MODEL_SWITCH`
`LANDING_IMPLEMENTATION=NOT_STARTED`
`CONTROLLER=ABSENT`
`GITHUB_FLOW=AUTHORITATIVE`

## 1. Проверенный текущий Landing

### Маршруты и композиция

- `/` маршрутизируется в `frontend/src/pages/landing/LandingPage.tsx`.
- Внешняя оболочка — `PublicShell` с общим брендом, темой, skip-link,
  доступным меню и входом.
- Hero: «СИЛА В ДЕЙСТВИИ», фотографии, Web/Telegram Mini App, вход, демо и
  основной CTA.
- Последовательность страницы: движение → запись подхода, интерактивная
  тренировка, питание, прогресс, отдельный блок для тренера, «Как это работает»,
  три демо-сценария, Web/TMA continuity, FAQ/ограничения, приватность, финальный
  CTA и подвал.
- `StrengthScene` использует scroll-bound progress, а `useLandingHeroMotion` —
  короткое hero-вступление; `prefers-reduced-motion` отключает motion.
- `/for-trainers` — отдельная manifest-driven публичная страница
  `PublicContentPage`, а не второй authenticated workspace.
- `/demo` — общий изолированный demo cabinet с сценариями
  `self_training`, `nutrition`, `trainer`; демо не пишет реальные аккаунты.

Проверенные основные файлы:

- `frontend/src/main.tsx`;
- `frontend/src/pages/landing/LandingPage.tsx`;
- `frontend/src/pages/landing/LandingChapter.tsx`;
- `frontend/src/pages/landing/StrengthScene.tsx`;
- `frontend/src/pages/landing/LandingPractice.tsx`;
- `frontend/src/pages/landing/LandingProgress.tsx` и `LandingProgressContent.tsx`;
- `frontend/src/pages/landing/useLandingHeroMotion.ts`;
- `frontend/src/pages/landing/landing.css` и `strength-scene.css`;
- `frontend/src/shared/ui/PublicShell.tsx` и `public-shell.css`;
- `frontend/src/pages/demo/DemoCabinet.tsx`;
- `frontend/src/features/demo/demoContent.ts` и `demoRoute.ts`.

### Публичный content/SEO contract

`frontend/src/content/publicContent.json` и `frontend/src/content/publicContent.ts`
содержат indexable landing, training, nutrition, progress, program, knowledge,
exercise и trainer surfaces. `frontend/src/shared/seo/metadata.ts` и
`backend/fitminiapp_api/seo.py` формируют title, description, canonical, social
metadata, JSON-LD и JavaScript-free fallback. `backend/fitminiapp_api/main.py`
отдаёт `robots.txt` и sitemap из опубликованного manifest.

Фактическая production-проверка 2026-10-08:

| URL | Ответ | Индексация | Проверено |
|---|---:|---|---|
| `https://your-fitness-coach.ru/` | 200 | `index, follow` | canonical, русский fallback |
| `/for-trainers` | 200 | `index, follow` | trainer title/canonical |
| `/training` | 200 | `index, follow` | public title/canonical |
| `/app` | 200 | `noindex, nofollow` | authenticated boundary |
| `/demo` | 200 | `noindex, nofollow` | synthetic demo boundary |
| `/robots.txt` | 200 | — | Allow public, Disallow `/api/`, sitemap link |
| `/sitemap.xml` | 200 | — | root/public URLs, без `/app`, `/coach`, `/admin`, `/join`, `/login` |

Это не Search Console/Yandex Webmaster, field-CWV или organic visibility evidence.
Такие данные в этом discovery не измерялись.

## 2. Фактически доступные возможности

Ниже перечислены delivered capabilities на текущем protected `master`, а не
обещания будущего Landing. Результат #758 не вводит новые claims.

### Для самостоятельного пользователя

Подтверждённый продуктовый путь:

1. Профиль, цель, оборудование и ограничения.
2. Готовая или собственная программа и экран «Сегодня».
3. Тренировка с фактическими подходами, повторениями, весами и отдыхом.
4. Nutrition Plan: планирование питания, planned → consumed bridge, дневник и
   сохранение различия между записанным и отсутствующим днём.
5. Grocery List из плановых данных с ручными корректировками.
6. Еженедельная проверка состояния и история.
7. Прогресс по фактическим тренировкам, весам, личным рекордам и замерам без
   непрозрачного общего рейтинга.
8. Web и Telegram Mini App используют один аккаунт и общий основной контекст;
   Telegram остаётся дополнительной поверхностью быстрых действий.

Сильнейшие factual value candidates для будущей athlete-позиции:

- один цикл «план → действие сегодня → факт → проверяемая динамика»;
- планирование питания связано с дневником и списком покупок, не создавая
  незаметных consumed records;
- прогресс объясняется доступными записями и ограничениями данных.

Нельзя заявлять индивидуальный медицинский результат, автоматическое улучшение
формы, универсальный AI coaching, интеграции с часами или сохранение публичного
калькулятора без отдельного runtime evidence.

### Для тренера

На текущем `master` и production-сценариях подтверждены:

- Coach Today, inbox/daily brief и attention items;
- клиенты, явные приглашения и server-side managed-client authorization;
- программы, шаблоны, назначения и массовое безопасное применение версии;
- configurable/versioned check-ins и review actions;
- Coach Review Workspace с meaningful changes, а не сырым event noise;
- тренерские группы/labels как организационное удобство;
- structured trainer-private notes с инвариантом
  `TRAINER_PRIVATE_NOTE_MUST_NEVER_LEAK_TO_CLIENT`;
- Coach OS context: тренировки, прогресс, встречи, пакеты, ручные факты оплат и
  задачи;
- workflow automation, которая создаёт bounded attention/task/draft path;
- onboarding workflow templates с версией, назначением и историей;
- communication templates/drafts в цепочке `draft → edit → explicit trainer
  confirmation`, без auto-send.

Сильнейшие factual value candidates для будущей trainer-позиции:

- Coach Today переводит внимание тренера в одно следующее действие;
- один клиентский контекст связывает тренировку, проверку, прогресс и рабочие
  задачи;
- повторяемые программы, проверки, подключение и сообщения остаются под явным
  контролем тренера.

Границы claims: нет multi-coach organization/RBAC, публичного профиля,
marketplace, рейтингов, billing/payment processing, внешнего календаря и
автоматической отправки сообщений.

## 3. Предлагаемая двухаудиторная модель

### Переключатель «Для себя / Для тренера»

Предложение для отдельного owner-approved implementation:

- default audience на `/` — «Для себя»;
- отдельный выбор «Для тренера» ведёт к trainer narrative и `/for-trainers`;
- выбранная аудитория меняет hero, order of proof, CTA и demo entry point, но не
  меняет authz, роль пользователя или серверный workspace;
- переключатель должен быть обычной публичной навигацией, доступной клавиатуре и
  screen reader, без скрытого состояния аккаунта;
- на mobile он остаётся компактным и не конкурирует с hero CTA;
- direct links, back/forward, UTM и canonical URL должны сохранять выбранный
  context без дублирования indexable страниц.

Это messaging switch, а не Owner/Coach/Assistant role switch. Multi-Coach
permission redesign из #757 к Landing не переносится.

### Предлагаемая структура

| Поверхность | Роль | Содержание | Статус |
|---|---|---|---|
| `/` | общий вход, default «Для себя» | короткое value proposition, factual product proof, два пути | существующий Landing; изменение запрещено до model switch |
| `/for-athletes` | самостоятельный пользователь | plan → action → facts → progress, nutrition/grocery proof, Web/TMA CTA | новый proposal-only маршрут |
| `/for-trainers` | тренер | Coach Today → client context → repeatable workflows, honest limits | существующая публичная страница; future positioning refinement only |
| `/coach-demo` или эквивалентный dedicated entry | тренерская демонстрация | изолированный synthetic flow, Coach Today, client context, task/return | future decision; runtime сейчас остаётся `/demo?scenario=trainer` |

Рекомендуется не создавать второй demo engine: отдельный entry должен переиспользовать
`DemoCabinet`, `demoApi`, `demoRoute` и существующие scenario fixtures. Если
canonical `/coach-demo` будет выбран, `/demo?scenario=trainer` должен остаться
совместимым переходом или явно redirect-иться после отдельной проверки SEO.

## 4. Coach Demo: безопасная концепция

Coach Demo должен быть самостоятельным публичным доказательством trainer value,
но не выглядеть как production workspace пользователя.

Предлагаемый bounded сценарий:

1. открыть подготовленный Coach Today;
2. выбрать attention item;
3. открыть одного synthetic клиента;
4. посмотреть тренировку, meaningful progress и безопасную рабочую заметку в
   demo-only контексте;
5. открыть операционную задачу/следующее действие;
6. вернуться в Coach Today и перейти к CTA «Начать со своими данными».

Не включать в публичное demo: реальные клиенты, private notes реальных людей,
платежи, приглашения, отправку сообщений, organization/RBAC и claims о
multi-coach. Synthetic state должен оставаться отделённым от analytics и
production account data; meaningful demo action может измеряться только как
обезличенный event.

## 5. Будущие implementation surfaces

При отдельном owner/model-switch prompt минимальный likely diff следует начинать
с существующих поверхностей:

| Задача | Файлы/границы для проверки | Не делать заранее |
|---|---|---|
| Routes | `frontend/src/main.tsx`, `shared/navigation/router.tsx` | не добавлять route сейчас |
| Landing composition | `pages/landing/LandingPage.tsx`, `landing.css`, `StrengthScene.tsx`, `strength-scene.css` | не менять hero/copy/motion сейчас |
| Shared public shell | `shared/ui/PublicShell.tsx`, `public-shell.css`, theme tokens | не вводить новый shell |
| Athlete/trainer public content | `content/publicContent.json/.ts`, `pages/public/PublicContentPage.tsx`, `public-content.css` | не дублировать content store |
| Coach Demo | `pages/demo/DemoCabinet.tsx`, `features/demo/demoApi.ts`, `demoContent.ts`, `demoRoute.ts`, `demo-mode` tests | не создавать второй demo runtime |
| SEO/fallback | `shared/seo/metadata.ts`, `backend/fitminiapp_api/seo.py`, `main.py` | не менять robots/canonical без route decision |
| Measurement | `shared/analytics/productEvents.ts`, attribution/Yandex boundary | не добавлять provider или PII event payload |
| Regression | existing `LandingPage`, `landing-production`, `public-content`, `demo-mode`, SEO/backend tests | не переформатировать весь repo |

Эта таблица — dependency map, не список изменений, разрешённых в #758.

## 6. Порядок измерений и аналитические зависимости

1. **Truth baseline.** Зафиксировать delivered claims, audience, canonical route,
   demo boundary и запрещённые обещания.
2. **Acquisition.** Сохранить first-touch attribution и добавить только
   allowlisted audience/CTA events, без email, client ID, private note или
   health data.
3. **Funnel.** Для athlete: landing view → audience choice → demo/own data →
   auth start/complete → onboarding complete → first useful action. Для trainer:
   trainer entry → demo/own data → trainer mode activated → first invite → first
   client connected.
4. **Quality.** Разделить synthetic demo events и real-account events; проверять
   deduplication, consent, route surface и отсутствие authenticated content в
   public analytics.
5. **Decision.** Только после достаточного фактического окна выбирать order,
   CTA или copy; не выдавать отсутствие измерений за отсутствие спроса и не
   обещать ranking uplift.

Существующий `productEvents.ts` уже содержит Landing, trainer CTA, demo,
onboarding, invite и client-connected события. Достаточно переиспользовать их,
если они покрывают будущий funnel; новый analytics provider не нужен.

## 7. Ограничения и gates

- Любая новая authenticated UI surface остаётся вне Landing proposal и проходит
  русский UI guard отдельно.
- Любая новая health-adjacent data category, external provider, payment flow,
  legal claim или cross-border flow останавливается на соответствующем gate.
- Public copy должна ссылаться только на delivered capabilities выше.
- Owner/model-switch approval нужен до изменения `/`, `/for-athletes`,
  `/for-trainers`, Coach Demo, hero, styles, motion или CTA hierarchy.
- После разрешения implementation нужен один bounded visual evidence package для
  desktop/mobile, затем обычный GitHub Flow и exact-head checks.

## 8. Проверки, выполненные в discovery

- live GitHub state #745–#758 сверено; #745–#757 CLOSED, #758 OPEN;
- current protected `origin/master` fetched at `2bdea709…`;
- source audit Landing, PublicShell, public manifest, demo runtime, analytics,
  SEO/fallback, routes and existing tests выполнен;
- production HTTP read-only check `/`, `/for-trainers`, `/training`, `/app`,
  `/demo`, `/robots.txt`, `/sitemap.xml` выполнен;
- confirmed no P0/P1 SEO blocker in checked responses;
- Search Console/Yandex Webmaster, field performance and organic demand не
  проверялись;
- production files were not changed; Landing implementation was not started.

## Закрытие C0 proposal

`PRODUCT_V10_NON_LANDING_CONVEYOR=PASS`
`PRODUCT_V10_CONVEYOR=PAUSED_FOR_LANDING_MODEL_SWITCH`
`LANDING_IMPLEMENTATION=NOT_STARTED`
