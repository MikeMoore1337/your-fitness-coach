# SEO и growth analytics: эксплуатационный контракт

Документ фиксирует production-контракт SEO, Yandex Metrica и first-touch attribution. Источником
правды для публичных маршрутов остаются `backend/fitminiapp_api/seo.py` и
`frontend/src/content/publicContent.ts`; этот документ описывает границы и ручные операции, а не
дублирует реализацию.

## Индексация и ownership

Публичный host — `https://your-fitness-coach.ru`. Для него:

- `/robots.txt` отдаётся как UTF-8 plain text со ссылкой на
  `https://your-fitness-coach.ru/sitemap.xml`;
- `/sitemap.xml` строится из того же public read model, что и публичные fallback-страницы, содержит
  абсолютные canonical URL и только надёжный `lastmod` из опубликованных данных;
- в sitemap входят публичные продуктовые страницы, `/articles` и опубликованные статьи;
- `/app`, `/login`, `/onboarding`, `/coach`, `/admin`, `/api`, preview/search/query routes и
  другие private/internal/TMA routes в sitemap не входят;
- robots не является механизмом авторизации. Для private/internal ответа используется
  `X-Robots-Tag: noindex, nofollow`, а секреты не должны попадать в URL.

Проверка ownership не реализуется meta-тегами или DNS-изменениями в репозитории. После production
deploy владелец вручную выполняет:

- Google Search Console: DNS TXT
  `google-site-verification=9zjBkYE6XiCVY7J4EYNWGhf9eZvS5rmCujZ2ixzHNlA`;
- Yandex Webmaster: файл `GET /yandex_bce1658cc6fe44e5.html` с точным содержимым:

  ```html
  <html>
    <head>
      <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    </head>
    <body>
      Verification: bce1658cc6fe44e5
    </body>
  </html>
  ```

Файл verification обслуживается напрямую, не через SPA fallback, и имеет `200`.

## Yandex Metrica

Production counter: `112530718`. Единственный runtime boundary —
`frontend/src/shared/analytics/yandexMetrica.ts`:

- loader добавляется один раз с `async` и `defer`;
- init использует `defer: true`, `webvisor: true`, `clickmap: true`, `trackLinks: true`,
  `accurateTrackBounce: true`, `sendTitle: false` и безопасные `url`/`referrer`;
- SPA route transitions отправляют явный `hit` только при изменении нормализованного pathname;
  query/hash никогда не передаются;
- product events идут через typed provider. Growth events отправляются только как `reachGoal` с
  exact goal id; прочие события не получают пользовательский payload;
- для public route Webvisor получает публичный контент, для private route `#root` получает
  `ym-hide-content`. Сбой provider не блокирует UI и не меняет бизнес-операцию.

В коде продукта нельзя вызывать `window.ym` напрямую и нельзя передавать в Metrica user ID, email,
Telegram ID, имя, workout/food values, body measurements, report text, tokens или произвольный
URL/query payload.

### CSP boundary

Единственный production source of truth для response header —
`backend/fitminiapp_api/middleware/request_context.py`, константа
`CONTENT_SECURITY_POLICY`. Для внешнего `tag.js` разрешены только `https://mc.yandex.ru` и
`https://yastatic.net` в `script-src`; для noscript/telemetry — `https://mc.yandex.ru`, а для
Chrome-specific consent/iframe runtime tag — `https://mc.yandex.md`. `connect-src` также сохраняет
`'self'`, canonical app origin `https://app.your-fitness-coach.ru` и `wss://mc.yandex.ru`; public API
запрашивается same-origin с landing, а `blob:` и эти exact Yandex origins разрешены в
`child-src`/`frame-src` для текущего `webvisor: true`.
`worker-src 'self'` явно сохраняет service-worker/worker boundary приложения.
Существующие Telegram origins и security directives (`object-src 'none'`, `base-uri 'self'`,
`form-action 'self'`, private-safe `frame-ancestors`) сохраняются. Для Yandex не используются
wildcard, общий `https:`, `unsafe-eval` или `script-src 'unsafe-inline'`.

Детали официального CSP-контракта сверяются с
[инструкцией Yandex Metrica для CSP](https://yandex.com/support/metrica/en/code/install-counter-csp);
региональные и Webvisor origins не добавляются без фактического runtime-требования.

## Growth event registry

Registry и goal IDs находятся в `frontend/src/shared/analytics/productEvents.ts`. Все implemented
goals context-free: в goal нет параметров, а событие достигается только после соответствующего
успешного действия.

| Goal ID                         | Успешный источник                                        |
| ------------------------------- | -------------------------------------------------------- |
| `registration_started`          | отправка email-регистрации                               |
| `registration_completed`        | успешный ответ регистрации                               |
| `onboarding_completed`          | успешное сохранение onboarding                           |
| `first_workout_started`         | успешный старт первой тренировки                         |
| `first_workout_completed`       | успешное завершение первой тренировки                    |
| `first_food_entry_added`        | успешное добавление первой записи дневника               |
| `program_added`                 | успешное создание программы                              |
| `trainer_application_started`   | подтверждённое действие включения режима тренера         |
| `trainer_application_completed` | успешное включение режима тренера                        |
| `client_invited`                | успешное создание invite link                            |
| `share_created`                 | успешное создание report handoff                         |
| `calculator_started`            | первое meaningful действие в публичном калькуляторе КБЖУ или 1ПМ |
| `calculator_result`             | показ валидного результата публичного калькулятора КБЖУ или 1ПМ  |

Следующие имена поддержаны только типами/registry для будущей реализации и не должны объявляться
реализованными до появления соответствующего успешного product flow:

`calculator_saved`, `public_program_opened`,
`public_program_saved`, `exercise_added_from_public_page`.

### Воронка публичных калькуляторов

Публичные `/nutrition` и `/calculators/1rm` используют только два action-only события:

- `calculator_started` отправляется один раз после первого изменения поля или попытки отправки
  формы на текущей странице;
- `calculator_result` отправляется один раз после показа валидного результата в текущем просмотре
  страницы;
- оба события содержат только typed `name` и безопасный `surface`; значения пола, возраста, роста,
  веса, активности, цели, повторений и результата не попадают в событие, URL, журнал или provider
  payload;
- `calculator_saved` остаётся будущим событием: публичная форма ничего не сохраняет.

Рабочая последовательность измерения: `calculator_started` → `calculator_result` → переход в
Your Fitness Coach → регистрация → активация. Для отчёта сопоставляются доли `result / started`,
переходы на приложение и последующая регистрация/активация; эти события не объявляются прогнозом
трафика или качества результата. До появления устойчивой выборки сравнение органики ведётся с
GSC T0: 0 кликов и 0 показов за устоявшиеся 28 дней по 2026-09-11.

## First-touch attribution

Канонический allowlist полей:

`first_touch_source`, `first_touch_medium`, `first_touch_campaign`, `first_landing_path`,
`first_referrer`, `first_touch_at`, `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`,
`utm_term`.

`first_touch_source` классифицируется как `google`, `yandex`, `telegram`, `direct`, `referral` или
`utm`. Сохраняются только allowlisted UTM keys, безопасные token values и referrer без query/hash,
userinfo и control characters. Email, phone-like values, JWT-подобные значения, health/fitness
payload и произвольные query parameters не сохраняются.

До auth запись immutable и хранится в client-safe `localStorage` под
`yfc:analytics:first-touch:v1`. После появления authenticated user frontend один раз отправляет
её на `POST /api/v1/me/acquisition` без user ID в body. Backend валидирует allowlist и сохраняет
не более одной записи на пользователя. Повторная отправка idempotent, ошибка сети оставляет запись
для retry и не блокирует приложение.

Attribution входит в account export и удаляется вместе с аккаунтом. BI backfill, identity stitching
и отправка attribution в Yandex не выполняются в рамках этого контракта.

## Production smoke и ручной post-deploy gate

После automatic deployment проверить напрямую:

1. `https://your-fitness-coach.ru/` — `200`, canonical public host, public Metrica noscript и
   отсутствие webmaster meta verification;
2. `https://your-fitness-coach.ru/robots.txt` — `200`, UTF-8 plain text, canonical sitemap;
3. `https://your-fitness-coach.ru/sitemap.xml` — `200`, absolute URLs, `/articles`, без private/API
   routes;
4. `https://your-fitness-coach.ru/yandex_bce1658cc6fe44e5.html` — `200` и exact verification body.

Финальный статус задачи остаётся `MANUAL_ACTION_REQUIRED`, пока владелец не выполнит все семь
действий: Google DNS TXT, Search Console verification, submit sitemap в Google, Yandex HTML
verification, submit sitemap в Yandex, настройка JS event goals в Metrica с exact implemented IDs,
Realtime/Debug проверка pageview и goals.

Для этой реализации `env change required: no`: новые production keys, secrets, DNS или provider
credentials не добавляются. Counter ID и verification file — versioned application contract.

## Локальная проверка

Тесты не используют внешнюю сеть. Минимальные проверки затронутого контура:

```powershell
python -m pytest backend/tests/test_acquisition.py backend/tests/test_account_export.py backend/tests/test_app.py
npm run typecheck -- --force
npm run lint -- --quiet
npm run test -- tests/unit/shared/analytics/attribution.test.ts tests/unit/shared/analytics/productEvents.test.ts tests/unit/shared/analytics/yandexMetrica.test.ts
```
