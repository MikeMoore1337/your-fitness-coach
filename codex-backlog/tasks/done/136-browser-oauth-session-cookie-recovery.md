# [Task 136] Восстановление browser OAuth после stale session cookie и изоляция transaction state

- **Статус:** completed / production `c634101` / 2026-09-03
- **Приоритет:** P0 / authentication reliability and security
- **Тип:** implementation / backend + frontend + regression hardening
- **Основная роль:** `implementer`
- **Дополнительные роли:** `security-reviewer`, `qa-verifier`
- **Зависимости:** нет hard dependency; запуск только отдельной явной командой owner

<!-- task-session
dependencies: none
executable: true
concurrency: exclusive-write
owner_gate: explicit-launch
integration: task-pr-to-master
-->

## Цель

Устранить корневую причину залипания browser OAuth после устаревшей, повреждённой или
рассинхронизированной session-cookie. Пользователь должен иметь возможность начать новый
защищённый OAuth-сеанс без удаления cookie через DevTools, перехода в incognito или ручной
очистки браузера.

Task описывает реализацию после проведённого аудита. Создание этого файла само по себе не
запускает реализацию, не меняет production и не ослабляет проверку `state`/CSRF.

## Problem

В browser OAuth сейчас используются две связанные формы состояния:

1. Authlib сохраняет `state`, `redirect_uri`, PKCE verifier и OIDC nonce в `request.session`
   под ключами вида `_state_<provider>_<state>`.
2. Starlette `SessionMiddleware` сериализует весь `request.session` в подписанную cookie
   `fit_oauth_session` с `Max-Age=600`.

Дополнительно `backend/fitminiapp_api/api/v1/auth.py` хранит в той же cookie общие ключи
`oauth_next`, `oauth_link_token`, `oauth_link_provider` и `oauth_link_family`. VK использует
отдельный ключ `vk_oauth`, но также внутри той же cookie.

При callback с `MismatchingStateError` текущий backend возвращает безопасный redirect на
`/login?auth_error=invalid_state`, но не выполняет явное восстановление OAuth-транзакции или
удаление невалидной `fit_oauth_session`. Кнопка `Повторить` на Login только вызывает
`window.location.reload()`, то есть повторяет страницу с той же cookie и не запускает новый
provider flow.

Нужно исправить именно lifecycle OAuth-транзакции и UX восстановления, сохранив обязательные
проверки `state`, PKCE, OIDC nonce, redirect URI, identity conflict и binding account-linking
к текущей session family.

## Evidence / reproduced behaviour

Аудит выполнен на актуальном на момент проверки `origin/master`
(`349ef74d5ed0821913e422f82716f4c720749744`) в отдельном read-only worktree.

### Наблюдение пользователя

По production-наблюдению пользователя:

- Telegram browser OAuth доходит до callback с `MismatchingStateError` и редиректит на
  `auth_error=invalid_state`;
- тот же flow в incognito работает;
- удаление только `fit_oauth_session` восстанавливает вход;
- proxy/TLS-маршрут провайдера уже работает;
- ручная очистка cookie не должна быть частью пользовательского recovery.

Это production-свидетельство предоставлено пользователем; точный первичный триггер конкретного
инцидента (race, истечение cookie, смена signing secret или другой порядок callback) без
снимков cookie/времени запросов доказать нельзя.

### Подтверждённые места в коде

- `backend/fitminiapp_api/main.py:98-110` настраивает `SessionMiddleware` с cookie
  `fit_oauth_session`, `max_age=600`, `Path=/`, `HttpOnly`; в prod также `Secure` и
  `SameSite=None`.
- `backend/fitminiapp_api/api/v1/auth.py:290-292` записывает общий `oauth_next`, после чего
  Authlib записывает provider state.
- `backend/fitminiapp_api/api/v1/auth.py:346-350` записывает общий link-контекст перед
  `authorize_redirect`.
- `backend/fitminiapp_api/api/v1/auth.py:365-368` извлекает и удаляет общий контекст до
  вызова `client.authorize_access_token(request)` и до фактической проверки Authlib state.
- `backend/fitminiapp_api/api/v1/auth.py:384-388` обрабатывает provider error до вызова
  Authlib и поэтому не завершает обычный state cleanup этим путём.
- `backend/fitminiapp_api/api/v1/auth.py:391-443` выполняет token/profile flow и нормализует
  ошибки state; успешный login выдаёт refresh-cookie, успешный link её не выдаёт.
- `backend/fitminiapp_api/services/oauth_login.py:202-241` реализует отдельный VK state/PKCE
  flow в общей `request.session` cookie.
- `frontend/src/pages/auth/LoginPage.tsx:18-30` показывает контролируемое сообщение для
  `invalid_state`, а `frontend/src/pages/auth/LoginPage.tsx:218-225` реализует `Повторить`
  через `window.location.reload()` без reset/start запроса.
- `frontend/src/features/auth/OAuthButtons.tsx:116-167` запускает provider link напрямую и
  не имеет отдельного recovery действия.
- `frontend/src/app/AuthProvider.tsx:320-334` после reload пытается восстановить access token
  через `/api/v1/auth/refresh`; при отсутствии refresh-cookie это даёт ожидаемый 401 и не
  исправляет OAuth session.

### Локальное воспроизведение механики cookie

Воспроизведение через `TestClient` с реальным Starlette `SessionMiddleware` и реальным
`MismatchingStateError` (без сетевого обмена с провайдером) дало:

1. Повреждённая подписанная cookie `fit_oauth_session`:
   `303 /login?next=%2Fapp&auth_error=invalid_state`, при этом `Set-Cookie` для удаления
   `fit_oauth_session` отсутствует. Браузер продолжает хранить исходное значение.
2. Валидная cookie с искусственно оставшимся `_state_google_old`:
   тот же `303`, но ответ содержит новую `Set-Cookie`; декодированное payload содержит
   `_state_google_old`, потому что callback удалил только общий `oauth_next`, а stale state
   не был очищен.

Это воспроизводит механизм залипания, но не доказывает, какой именно вариант возник в
production у Telegram.

### Поверхность текущих тестов

Фокусированный backend baseline:

```text
45 passed, 1 skipped
backend/tests/test_auth_providers.py
backend/tests/test_auth_hardening.py
backend/tests/test_telegram_oauth_proxy.py
```

Существующие `_FakeOAuthClient` и `_FakeGoogleClient` моделируют свои session keys и в
основном обходят реальные Authlib keys `_state_<provider>_<state>`. VK-тесты проверяют его
custom state, но не malformed/expired signed cookie, explicit deletion или multi-tab race.
В `frontend/node_modules` нет установленных зависимостей, поэтому frontend-тесты в рамках
аудита не запускались; текущие frontend unit/e2e проверки также не кликают `Повторить` с
проверкой recovery-запроса.

## Root cause / technical assessment

### Подтверждённая причина persistence/recovery

`fit_oauth_session` является client-side signed session, а не server-side transaction store.
При плохой подписи, истёкшем timestamp или cookie, подписанной старым secret, текущая версия
Starlette создаёт пустую session, но сама не отправляет delete-cookie. Если callback после этого
только читает отсутствующие keys и редиректит, session не считается modified и исходная плохая
cookie остаётся в браузере.

Если cookie валидна, но в ней остался stale state, callback удаляет общие metadata keys,
получает mismatch и может сериализовать оставшиеся Authlib/VK state обратно в новую cookie.
`HttpOnly` не позволяет frontend самостоятельно удалить эту cookie.

Это объясняет, почему incognito и удаление именно `fit_oauth_session` восстанавливают flow.

### Наиболее вероятные усилители

- Два последовательных start одного provider в Authlib очищают старый state этого provider;
  поздний callback закономерно получает mismatch. Это нормально с точки зрения CSRF, но текущий
  recovery не делает такой failure одноразовым и не начинает новый flow.
- Все provider states и общий login/link context живут в одной client-side cookie. Разные tabs,
  login и link flow одновременно или ответы с разным порядком `Set-Cookie` могут перезаписать
  друг друга. Общие `oauth_next` и link keys не изолированы по provider/attempt.
- Authlib записывает state с собственным expiry (по умолчанию 3600 секунд), тогда как cookie
  живёт 600 секунд. State TTL и cookie TTL не образуют явно согласованный transaction contract.
- Provider-error ветка возвращает ошибку до state validation/clear. Она не должна выдавать
  доступ, но её cleanup и различение `denied` от `invalid_state` должны быть формализованы.
- 401 `/api/v1/auth/refresh` после reload без refresh-cookie — следствие общего bootstrap
  frontend, а не способ восстановления OAuth и не причина mismatch.

### Что пока нельзя утверждать

Нельзя по текущим исходникам выбрать единственный production trigger между expired/bad cookie,
сменой secret, поздним callback после повторного start и race между tabs. Реализация должна
добавить безопасную диагностическую классификацию (без raw cookie/state/code/token) и покрыть
каждый сценарий тестом.

## Scope

В scope входят:

- единый, явно описанный lifecycle browser OAuth transaction для login и account linking;
- Telegram, Google, Yandex, VK и Apple browser OAuth login;
- Google, Yandex, VK и Apple account linking, включая action token и session-family binding;
- backend start/callback/error/recovery и cookie/session handling;
- frontend Login recovery и provider retry без redirect loop;
- observability с безопасной классификацией причины;
- backend/frontend regression tests, использующие настоящую cookie/state механику;
- короткое design decision record: server-side short-lived transaction store либо
  narrowly-scoped cookie/session design, если после проверки это действительно безопаснее и
  совместимо с deployment topology.

Предпочтительное направление для оценки — server-side short-lived transaction state с маленьким
opaque browser marker: оно убирает из signed cookie PKCE/nonce/link metadata и уменьшает race
из-за сериализации всего session. Если инфраструктура не позволяет это без неоправданной
сложности, допустим narrowly-scoped вариант с отдельным transaction namespace/cookie, но он
должен доказать корректность invalidation, multi-tab поведения и secret rotation.

## Non-goals

- отключение state/CSRF проверки или принятие callback с неизвестным/несовпавшим state;
- обмен code на token до проверки transaction/state;
- ослабление PKCE, OIDC nonce, redirect URI, provider identity или VK payload checks;
- автоматическое объединение OAuth identities или изменение account-linking policy;
- переделка Telegram Mini App `initData` auth;
- изменение refresh-token rotation, refresh-cookie или session-family модели, кроме защиты от
  случайного удаления во время OAuth recovery;
- изменение provider proxy/TLS маршрута;
- хранение access/refresh token в frontend storage;
- blanket `request.session.clear()` без доказательства, что он не удалит чужое состояние;
- автоматический запуск следующей backlog task, production deploy, merge или PR.

## Security requirements

1. Успешный callback принимается только при exact match одноразового transaction state,
   привязанного к текущему browser flow, provider, redirect URI и purpose (`login` или `link`).
2. State должен проверяться до token exchange, profile fetch и любых identity/account writes.
   Неправильный, отсутствующий, повторный, просроченный или повреждённый state всегда завершается
   отказом.
3. Сохранить PKCE для Telegram/Google/Yandex/VK и действующую OIDC nonce/claims validation
   для OIDC providers. Для VK сохранить constant-time comparison, device id, PKCE и проверку
   state, возвращённого token endpoint.
4. Link transaction должна оставаться связанной с one-time action token, целевым пользователем
   и исходной refresh session family. OAuth recovery не должен превращать link в login.
5. При provider `error` разрешить только безопасное отображение `denied`/`provider_failure`
   после формализованной проверки доступного transaction context; никогда не продолжать login
   без валидного state. Ошибка callback должна одноразово завершать только свою transaction.
6. В логи не писать raw `state`, authorization code, PKCE verifier, nonce, OAuth token,
   action token, refresh token или полную cookie. Разрешены provider, flow purpose, безопасный
   reason class, transaction hash prefix и request id, если этого достаточно для корреляции.
7. Recovery может удалять только OAuth transaction/session artifact. Нельзя удалять или
   ротировать `fit_refresh_token`, access session пользователя или DB action token просто из-за
   login `invalid_state`.
8. В prod сохранить `Secure; HttpOnly; SameSite=None; Path=/` для cross-site OAuth callback;
   deletion должна использовать то же имя, Path и Domain (если Domain будет добавлен). Нельзя
   исправлять проблему ослаблением cookie security flags.

## Why CSRF/state protection is preserved

Исправление должно менять только способ хранения и очистки transaction, а не доверие к
callback. Новый flow по-прежнему генерирует непредсказуемый state, передаёт его provider,
сверяет с одноразовым state, созданным именно этим browser start, и отклоняет mismatch до
обмена code. Очистка stale/bad cookie — это recovery от невозможности доказать transaction;
она не является разрешением callback и не возвращает его в authenticated состояние.

Отдельный transaction id/marker, если он будет введён, должен быть opaque и привязан к
browser cookie/session, provider и purpose. При mismatch backend удаляет только невалидный
OAuth artifact и направляет пользователя на новый start; старые state и provider code не
принимаются повторно. Для link flow сохраняется дополнительная DB-проверка action token и
session family. Поэтому recovery уменьшает persistence и race, но не создаёт обход CSRF/state
защиты.

## Backend requirements

1. Перед реализацией зафиксировать выбранную модель хранения transaction и её failure modes:
   server-side TTL store либо отдельный narrowly-scoped cookie/session namespace. В модели явно
   указать `transaction_id`, provider, purpose, safe next, redirect URI, state, PKCE verifier,
   OIDC nonce при наличии, created/expired timestamps, one-time status и link binding.
2. Убрать shared mutable context `oauth_next`/`oauth_link_*` из области, где он может быть
   перезаписан другой вкладкой или другим provider flow. Link context должен быть частью той же
   transaction или ссылаться на безопасно сохранённую серверную запись; raw action token не
   должен попадать в логи.
3. На start создавать новую transaction атомарно, ограничивать TTL и размер хранения, а
   предыдущую transaction завершать только по определённой политике (same provider/flow либо
   только явно superseded attempt). Нельзя без design proof уничтожать независимый flow другой
   вкладки.
4. На callback сначала разобрать и проверить transaction/state/provider/purpose/expiry/redirect
   binding, затем единожды consume/mark transaction и только после этого выполнять token/profile
   flow. Повторный callback должен быть безопасным и не выдавать token.
5. На invalid/missing/expired/malformed state и на provider error определить идемпотентный
   cleanup. Для невалидной signed cookie ответ должен уметь отправить явное удаление/замену
   `fit_oauth_session`, даже если Starlette сам превратил её в пустую session. Для валидной
   stale cookie нельзя сохранять старые `_state_*` keys в ответе.
6. Добавить safe recovery contract: либо provider-specific retry URL, который всегда создаёт
   новую transaction, либо узкий same-origin recovery endpoint/response с понятным CSRF
   контрактом. Он не должен зацикливать `/login -> callback -> /login` и не должен очищать
   refresh-cookie.
7. Сохранить safe allowlist для `next`; не переносить произвольный `next` в transaction или
   frontend redirect.
8. Сохранить текущий login/link результат: login выдаёт refresh-cookie только после успешного
   identity flow, link не выдаёт новую refresh-cookie и не теряет текущую session family.
9. Если остаётся `SessionMiddleware`, явно протестировать prod/test/dev конфигурацию на реально
   создаваемом app instance: `max_age`, `Path`, `Secure`, `HttpOnly`, `SameSite`, delete-cookie,
   bad-signature и secret rotation.
10. Добавить безопасные reason classes/metrics для `invalid_state`, `expired_state`,
    `malformed_session`, `superseded_transaction`, `provider_denied` и `provider_failure`, не
    раскрывая секреты.

## Frontend/UX requirements

- `Повторить` должен действительно начинать новый безопасный flow: использовать provider-specific
  start, либо выполнить узкий recovery и затем start. Нельзя оставлять `window.location.reload()`
  единственным действием.
- Сохранить только allowlisted `next` и показать понятное сообщение вроде «Сессия входа
  устарела. Начните вход заново»; не показывать query `code`, `state`, provider token или raw
  backend detail.
- Для `invalid_state` должен быть однозначный путь повторить вход тем же provider или выбрать
  другой; после failed attempt controls должны снова становиться доступными.
- Не выполнять бесконечный автоматический retry и не запускать provider flow повторно при каждом
  bootstrap/re-render. Busy/disabled state должен быть доступен screen reader и сбрасываться при
  отказе start.
- Не выдавать пользователю misleading refresh error как замену OAuth error. Отсутствие
  `fit_refresh_token` во время обычной страницы login должно оставаться тихим bootstrap outcome
  либо быть отдельно и понятно обработано.
- Для account linking сохранить возврат в account UI, текущего пользователя и понятное отличие
  `conflict`, `denied`, `invalid_state` и `provider_failure`.

## Session/cookie requirements

- `fit_oauth_session` должна иметь явный bounded TTL, согласованный с transaction TTL; не
  полагаться на расхождение Authlib `expires_in` и cookie `Max-Age`.
- Cookie payload должна оставаться малой и не содержать access/refresh token. Если выбран
  server-side store, browser cookie должна содержать только opaque marker/минимально необходимую
  привязку.
- Bad signature, old secret, expired cookie и stale transaction должны приводить к
  предсказуемому delete/replace response. Повторный start сразу после ошибки должен работать на
  той же вкладке.
- Delete должен совпадать с cookie name, Path и Domain. Нельзя удалять `fit_refresh_token`
  (`Path=/api/v1/auth`, `HttpOnly`, `SameSite=Strict`) в login OAuth recovery.
- Нужно определить поведение при ротации `SECRET_KEY`, рестарте backend, параллельных tabs и
  callback после timeout; ни один такой сценарий не должен принимать старый state.

## Test requirements

Тесты должны быть добавлены/обновлены минимум для следующих сценариев:

1. Успешный browser OAuth login с корректным state для Telegram; отдельно проверить Google,
   Yandex, VK и Apple с их provider-specific особенностями.
2. Mismatching, missing, repeated и expired state: нет token exchange, identity write или
   authenticated redirect.
3. Повторный start после `invalid_state` на той же вкладке без ручного удаления cookie.
4. Повреждённая signed cookie, истёкшая cookie и cookie от старого secret: response содержит
   нужное удаление/замену OAuth cookie, а следующий start успешен.
5. Сценарии sequential starts, двух tabs и позднего callback; политика независимых transaction
   и cleanup должна быть проверена, включая порядок `Set-Cookie`.
6. Backend restart/secret rotation и callback GET/POST; TTL/clock boundary без acceptance старого
   state.
7. Provider denial/cancel/error: безопасный mapping, одноразовый cleanup, отсутствие loop и
   отсутствие token exchange при недоказанном state.
8. VK flat callback и JSON `payload`, conflicting parameters, device id, PKCE и returned-token
   state.
9. Account linking для всех configured link providers: action-token expiry/replay/conflict,
   session-family mismatch, текущая сессия сохраняется, refresh-cookie не удаляется и не
   создаётся лишняя login-сессия.
10. Cookie contract в prod-like app instance: `Secure`, `HttpOnly`, `SameSite=None`, `Path=/`,
    bounded size, явный deletion; отдельно проверить, что refresh-cookie не входит в deletion.
11. Frontend unit test на реальный click `Повторить`: вызывается recovery/new start, а не reload;
    `next` сохраняется, секретные query values не рендерятся, нет redirect loop.
12. Frontend e2e/mock-provider test для invalid_state -> retry -> fresh start и provider
    selection; явно пометить, что mock-TMA/browser evidence не является proof реального Telegram
    или физического устройства.

Backend state tests должны проходить через реальный Authlib/Starlette integration или faithful
harness, который создаёт и читает `_state_<provider>_<state>` в настоящей signed cookie. Нельзя
считать достаточным только текущий fake client, который хранит `fake_oauth_state`.

Все временные логи, cookie fixtures, screenshots и отчёты тестов класть под `.artifacts/`.

## Acceptance criteria

- После mismatch/stale/bad OAuth session пользователь может нажать `Повторить` или повторно
  выбрать provider и начать новый browser OAuth на той же вкладке без DevTools/incognito.
- Любой callback с неправильным, отсутствующим, просроченным или повторно использованным state
  остаётся отказом и не выполняет token exchange, profile/identity write или issue token.
- Валидный callback для Telegram, Google, Yandex, VK и Apple сохраняет текущий успешный login
  contract; account linking сохраняет action-token/session-family contract.
- Invalid-state recovery удаляет/заменяет только OAuth transaction artifact и не удаляет,
  не ротирует и не инвалидирует `fit_refresh_token`.
- Валидная stale cookie не reserialize-ит старые `_state_*` после failed callback; malformed,
  expired и old-secret cookie получают явный предсказуемый recovery response.
- Login retry не вызывает reload-loop, не теряет allowlisted `next`, не показывает provider
  secrets и остаётся доступным при keyboard/screen-reader navigation.
- Multi-tab/sequential-start policy задокументирована и покрыта тестами; race не приводит к
  принятию старого state.
- Cookie attributes и TTL подтверждены тестом для prod-like конфигурации, а логи не содержат
  OAuth secrets.
- Фокусированные backend/frontend/security проверки зелёные; broader suite запускается только
  по отдельному решению owner согласно workflow проекта.

## Regression risks

- Неправильное удаление cookie с другим Path/Domain может оставить stale cookie или удалить не
  тот artifact.
- Blanket session reset может потерять link context или будущие session keys; cleanup должен
  быть namespace/transaction-scoped.
- Server-side store без TTL/cleanup может стать утечкой state или operational burden; cookie
  marker не должен стать bearer token.
- Слишком агрессивное supersede поведение может ломать параллельные tabs; слишком мягкое —
  оставлять race и повторный callback.
- Ошибка в provider-specific mapping может превратить denial в loop или скрыть реальный
  invalid_state.
- Изменение порядка callback может выдать refresh-cookie для link или потерять текущую
  authenticated session.
- Неявная смена `SameSite=None`/`Secure`/Path может сломать cross-site callback в production.
- Тесты, использующие только fake client, могут дать false green и не обнаружить реальную
  cookie/state проблему.

## Files/components likely affected

- `backend/fitminiapp_api/api/v1/auth.py`
- `backend/fitminiapp_api/services/oauth_login.py`
- `backend/fitminiapp_api/main.py` и/или отдельный session/OAuth transaction service
- `backend/fitminiapp_api/services/auth_redirects.py`
- `backend/fitminiapp_api/services/account_linking.py`
- `backend/fitminiapp_api/api/v1/me.py` — только если link start contract потребует изменения
- DB model/migration или TTL store configuration — только если выбран server-side design
- `backend/tests/test_auth_providers.py`
- `backend/tests/test_auth_hardening.py`
- `backend/tests/test_telegram_oauth_proxy.py`
- `backend/tests/test_vk_oauth.py`
- отдельный backend test для real session-cookie/Authlib lifecycle
- `frontend/src/pages/auth/LoginPage.tsx`
- `frontend/src/features/auth/OAuthButtons.tsx`
- `frontend/src/app/AuthProvider.tsx`
- `frontend/src/shared/api/client.ts` и `frontend/src/shared/auth/redirects.ts` — только при
  добавлении recovery API/contract
- `frontend/tests/unit/pages/auth/LoginPage.test.tsx`
- `frontend/tests/unit/features/auth/OAuthButtons.test.tsx`
- `frontend/tests/e2e/auth.spec.ts`

## Definition of Done

1. В начале реализации зафиксировано design decision между server-side transaction store и
   narrowly-scoped cookie/session вариантом, включая multi-tab, TTL, restart и secret-rotation
   failure modes.
2. Реализован provider-neutral lifecycle для login/link, не обходящий state/CSRF/PKCE/OIDC/VK
   проверки.
3. Invalid/stale/malformed/expired OAuth state имеет идемпотентный backend cleanup и рабочий
   same-tab retry без ручной очистки cookie.
4. Frontend `Повторить` запускает новый flow/recovery, а не reload-loop; safe `next` и UX
   ошибок сохранены.
5. Refresh-cookie и authenticated account-linking session защищены от побочного удаления или
   выпуска неправильных токенов.
6. Добавлены focused tests из списка выше, включая настоящую signed cookie/Authlib state path;
   fake-only coverage не считается достаточной.
7. Security review подтверждает, что mismatch/unknown/expired state не может привести к
   token exchange или account write, а логи/ответы не раскрывают секреты.
8. Изменения проверены в рамках task scope, отдельный broader/full suite не объявляется
   пройденным без фактического запуска.
9. Только после отдельного owner launch могут рассматриваться commit, PR, deploy и production
   evidence; создание текущей backlog task их не авторизует.
