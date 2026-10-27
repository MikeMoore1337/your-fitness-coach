# #1269: разбор двух нативных CodeQL alerts в auth.py

Дата проверки: 2026-10-27. [Issue #1269](https://github.com/MikeMoore1337/your-fitness-coach/issues/1269).
Вывод: **оба сигнала — false positive для исследованных трасс**. Уязвимость не воспроизведена;
существующие серверные проверки исключают передачу произвольного `provider` в оба sink.
Runtime-код не изменён. Добавлены регрессионные тесты существующих ограничений.

## Ревизии и происхождение

| Объект | Проверенная ревизия / состояние |
| --- | --- |
| База `dev` | `d358e388caa58fc27abc7f28aa2c7984a05adcc1` |
| `master` при исследовании | `8fab0f899ba06a13c6773fcdf5c3e04d34f0daaf` |
| [Bootstrap #1267](https://github.com/MikeMoore1337/your-fitness-coach/pull/1267) | OPEN, head `1a2b545df3afe5de2eba3d2df4714096080df83c`; не включён в эту ветку |
| Первое сканирование обоих alerts | `c136fecae1f429c18a941f7348b2cf854f8817bb`, 2026-10-05 10:21:16 UTC, analysis `1892433704` |
| Последнее сканирование `master` | `308cb30ffdad690ea0f175dedd227e6fc7148160`, analysis `2025838946`, 2026-10-26 |
| Сканирование #1267 | `1a2b545df3afe5de2eba3d2df4714096080df83c`, analysis `2033271429`, 2026-10-27 |

Идентификаторы, статусы и трассы получены из GitHub Code Scanning REST API, включая SARIF
`GET /repos/MikeMoore1337/your-fitness-coach/code-scanning/analyses/{id}` с
`Accept: application/sarif+json`. Это нативные результаты GitHub, не вывод локального линтера.
Первый и последний SARIF подтверждают соответствие номеров #10 и #32 этим правилам и строкам.

На момент исходного чтения оба alerts OPEN на `refs/heads/master` и `refs/pull/1267/head`.
Для `refs/heads/dev` API не вернул анализов или instances. Поэтому состояние сканирования
актуальной `dev` — **NOT_VERIFIED**, а не PASS. Исследованный код присутствует в обеих ветках.
Между последним просканированным `master` и актуальным `master` нет diff в `auth.py`,
`oauth_login.py`, `oauth_transactions.py`.

`master` и `dev` защищены активными Rulesets `21750478` и `21801287`: PR, strict required `checks`,
запрет удаления и non-fast-forward. Endpoint legacy branch protection возвращает 404;
это не отсутствие защиты: эффективные правила прочитаны через `/rules/branches/{branch}`.
Правила не изменялись.

## Alert 1: #32 — Log Injection

- [Нативный alert #32](https://github.com/MikeMoore1337/your-fitness-coach/security/code-scanning/32).
- Rule ID: `py/log-injection`, CWE-117. Security severity: **medium** (SARIF score 6.1);
  diagnostic severity: **error**. Это разные поля, хотя Issue называет сигнал warning.
- Sink: [`backend/fitminiapp_api/api/v1/auth.py:178`](https://github.com/MikeMoore1337/your-fitness-coach/blob/1a2b545df3afe5de2eba3d2df4714096080df83c/backend/fitminiapp_api/api/v1/auth.py#L178),
  `logger.warning(event, extra=extra)`.
- Описание правила: недоверенный ввод может подделывать записи логов.

### Source → sink и достижимость

SARIF содержит четыре трассы: параметр пути `provider` в `oauth_start` (строка 338),
`oauth_link_start` (398), GET callback (979), POST callback (992) → `strip().lower()` →
`_log_oauth_event(provider=...)` → `extra['provider']` → `logger.warning`.
Source здесь — имя провайдера; не пароль, OAuth code или raw state.

До всех четырёх sink вызывается
[`configured_oauth_client`](https://github.com/MikeMoore1337/your-fitness-coach/blob/1a2b545df3afe5de2eba3d2df4714096080df83c/backend/fitminiapp_api/services/oauth_login.py#L317).
Он возвращает `None`, если значение отсутствует в `settings.oauth_provider_names`.
Это свойство строит имена из фиксированных строк `telegram`, `google`, `yandex`, `vk`, `apple`;
настройки определяют только включённость этих имён. Неизвестный login start возвращает безопасный
локальный redirect без вызова auth logger; callback и link start завершаются 404.
В link start дополнительно есть `OAUTH_LINK_PROVIDERS`.

Поэтому CR/LF, домен, обратный слеш или query в `provider` не достигают auth logger.
CodeQL переносит taint через вызов, но не доказывает сохранение только фиксированного набора
после межфункциональной проверки и раннего возврата.

Остальные поля также прослежены: имена событий и категории ошибок фиксированы; purpose создаётся
сервером как `login`/`link`; state логируется лишь после проверки формата как 12 hex-символов SHA256.
Request ID ограничен `[A-Za-z0-9._:-]{1,128}`, иначе генерируется UUID.
`JsonFormatter` дополнительно проверяет provider/поля и кодирует результат JSON.
Исключения провайдера не передаются в этот лог как текст или traceback.

### Impact, воспроизведение и классификация

Подделка auth log и утечка credentials по указанным трассам **не подтверждены и исключены
проверкой провайдера**. Синтетический CR/LF-ввод не доходит до sink; raw OAuth error, code,
state и некорректный request ID отсутствуют в проверенных auth/application access logs и
диагностических ответах. Проверка не распространяется на произвольные сторонние системы логирования.

Классификация: **false positive**. Runtime-исправление не требуется. Нельзя заменять эту
классификацию на `won't fix`: действующая уязвимость здесь не принята как риск.
Статус записи после классификации и ссылки на PR/CI публикуются в Issue и PR.

Проверен [прежний отчёт #914](https://github.com/MikeMoore1337/your-fitness-coach/blob/8fab0f899ba06a13c6773fcdf5c3e04d34f0daaf/docs/ux/issue-914-acceptance/audit/codeql-remediation.md).
Он разбирал `py/clear-text-logging-sensitive-data` — alert **#11**, FIXED с 2026-10-19.
Переименование категории ошибки в `aae064a1` не является исправлением #32.
Новый дубликат #11 не создаётся; старый auth fix не переносится в `dev` отдельно от bootstrap.

## Alert 2: #10 — URL redirection from remote source

- [Нативный alert #10](https://github.com/MikeMoore1337/your-fitness-coach/security/code-scanning/10).
- Rule ID: `py/url-redirection`, CWE-601. Security severity: **medium** (SARIF score 6.1);
  diagnostic severity: **error**.
- Sink: [`backend/fitminiapp_api/api/v1/auth.py:726`](https://github.com/MikeMoore1337/your-fitness-coach/blob/1a2b545df3afe5de2eba3d2df4714096080df83c/backend/fitminiapp_api/api/v1/auth.py#L726),
  `RedirectResponse(url=f'/app?auth_linked={normalized_provider}', status_code=303)`.
- Описание правила: redirect с удалённым вводом может отправить пользователя на чужой сайт.

### Source → sink и достижимость

Две трассы: GET `provider` (979) / POST `provider` (992) → `_oauth_callback_impl` (539) →
`normalized_provider` (543) → f-string (726).

Тот же `configured_oauth_client` прекращает неизвестный provider до чтения callback и обмена code.
Для достижения link-success требуются действующая browser-bound OAuth transaction, ожидаемые
provider/state, purpose `link`, одноразовый action token и совпадающие user/session family.
`claim_oauth_transaction` и `_active_refresh_session` проверяют эти условия на сервере.

Даже форма строки sink имеет фиксированный относительный путь `/app?auth_linked=`: provider не
занимает позицию scheme или host. После allowlist в query может попасть только имя провайдера без
разделителей. Для обычного входа `next` отдельно проверяется `safe_auth_next_path`.
Клиентские роли и утверждения внешнего provider не дают права администрирования.

### Impact, воспроизведение и классификация

Open redirect, передача токенов на чужой origin, обход state/session или повышение роли по этой
трассе **не воспроизведены**. GET и POST успешной привязки дают ровно `/app?auth_linked=google`,
не выпускают новую refresh cookie и привязывают identity к прежнему владельцу без изменения ролей.
Неверные/просроченные/replayed состояния и чужая сессия покрыты существующими тестами.

Классификация: **false positive**. Предшествующего исправления #10 не обнаружено; sink и guards
уже существовали в исходном просканированном commit. Не нужен refactor или suppression.
Статус записи после классификации и ссылки на PR/CI публикуются в Issue и PR.

## Регрессионные доказательства

В `backend/tests/test_auth_hardening.py` добавлены 23 сценария. Они используют настоящий
`configured_oauth_client`; подменяется только внешняя фабрика Authlib, а не проверка allowlist.

| Проверка | Наблюдаемый результат |
| --- | --- |
| 4 crafted provider × login start/link start/GET callback/POST callback | 16 PASS: фабрика не вызвана, auth log не создан, refresh cookie не выдана |
| Ошибка start и GET/POST callback | 3 PASS: фиксированная категория, без текста исключения, code, state и синтетических секретов; JSON в одну строку |
| GET/POST link success | 2 PASS: локальный Location, identity принадлежит владельцу, роли не повышены |
| Поддельная подпись / истёкший access JWT | 2 PASS: 401 без раскрытия токена, исходный легитимный JWT продолжает работать |

Отрицательный контроль: временный pytest plugin **в памяти** обошёл provider allowlist.
Обе проверки callback для `google.evil.example` упали: получили 303 и auth log вместо 404.
Исходные файлы при контроле не изменялись. Это доказывает чувствительность тестов к удалению guard;
это не воспроизведение уязвимости текущего кода и не BEFORE/AFTER runtime-исправления.

Локально, Python 3.14 и SQLite, существующий `scripts/run_pytest.py`:

```text
backend/tests/test_auth_hardening.py
backend/tests/test_auth_providers.py
backend/tests/test_oauth_session_recovery.py
backend/tests/test_admin_authorization.py
backend/tests/test_telegram_oauth_proxy.py
backend/tests/test_vk_oauth.py
backend/tests/test_app.py::{test_me_requires_auth,test_invalid_token_treated_as_unauthorized,
test_refresh_token_rotation,test_admin_users_forbidden_for_client,test_admin_users_forbidden_for_coach}
105 passed, 1 skipped
```

SKIP: существующий `test_concurrent_first_oauth_login_creates_one_account` требует PostgreSQL locking.
Ruff lint и format для изменённого Python-файла — PASS. Полные CI/нативный CodeQL оцениваются
отдельно на PR head; локальный PASS их не заменяет.

## Security review и ограничения доставки

Проведена самопроверка diff и достижимых flow по B1/B3 и identity/session/role/logging invariants
из текущего `security/THREAT_MODEL.md` в `master` (в старой `dev` файла ещё нет).
Новые runtime/auth paths, зависимости, API-контракты, подавления и security exclusions не добавлены.
Authlib factory mock расположен после реальной границы проверки provider.
Результат: **NO_CONFIRMED_FINDINGS в исследованном объёме**. Независимый агент не запускался;
самопроверка не названа независимым аудитом.

В исходной `dev` отсутствуют workflow Security Audit и PR CodeQL job; GitHub default setup имеет
`state=not-configured`. Поэтому exact-head native CodeQL этой ветки зависит от доставки bootstrap
#1267 либо отдельного разрешённого способа сканирования. Старый анализ #1267 не доказывает
сканирование нового SHA. До получения такого анализа критерий завершения #1269 остаётся
**NOT_VERIFIED**; Issue не следует закрывать.

Alert #41 (`bot/fitminiapp_bot/polling_health.py`, 0640/Hermes), прочие findings и CI/деплой
конфигурация не входят в diff. Классификация #10/#32 не отключает правила и не ослабляет gate
новых high/critical findings. Merge и production release не выполняются.
`env change required: no` — изменены только тесты и отчёт.
