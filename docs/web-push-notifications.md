# Web Push для браузерных уведомлений

Task 86A добавляет добровольный Web Push для авторизованных пользователей Web-клиента. Telegram
Mini App не использует этот канал: в нём продолжает работать существующая Telegram-доставка и
центр уведомлений приложения.

## Границы и безопасность

Web Push является дополнительным каналом существующего notification orchestration. Worker не
создаёт отдельный scheduler: он сначала создаёт per-subscription delivery rows для уже созданного
канонического события, затем доставляет их с теми же category gates, quiet hours, cancellation и
retry правилами.

Сервер считает browser subscription capability, а не identity. После аутентифицированного запроса
endpoint и ключи связываются с текущим аккаунтом; повторная регистрация идемпотентна, устройства
хранятся независимо. При logout, смене аккаунта или удалении аккаунта локальная и серверная
подписка отзываются в best-effort режиме. Ответы `400`, `404` и `410` удаляют устаревшую или
недействительную подписку.

В push передаётся только фиксированный нейтральный payload версии протокола. В нём нет имени,
текста напоминания, данных тренировки, питания, здоровья, пользователя или приватного URL. Клик
открывает только внутренний allowlisted `/app` fallback; авторизация, onboarding и проверка
владения данными происходят уже в приложении.

Endpoint хранится как capability и не попадает в API-ответы, логи, analytics или account export.
Для дедупликации хранится HMAC endpoint, а не открытый endpoint. В telemetry разрешены только
категория, провайдер, outcome и короткий безопасный код ошибки; browser fingerprint не собирается.

## Конфигурация и VAPID

По умолчанию канал выключен:

```dotenv
WEB_PUSH_ENABLED=false
WEB_PUSH_VAPID_SUBJECT=mailto:ops@example.invalid
WEB_PUSH_VAPID_PUBLIC_KEY=
WEB_PUSH_VAPID_PRIVATE_KEY=
WEB_PUSH_ENDPOINT_HOSTS=fcm.googleapis.com,*.push.services.mozilla.com,*.push.apple.com,*.notify.windows.com
WEB_PUSH_DELIVERY_TIMEOUT_SECONDS=10
```

При включении `WEB_PUSH_ENABLED=true` приложение проверяет provider-compatible credential-free
`mailto:` mailbox или HTTPS origin без path/query/fragment, uncompressed P-256 public key и
совпадение public/private VAPID key. Private key задаётся
только через production secret store или защищённый runtime secret; его нельзя помещать в Git,
`.env`-артефакты, логи или клиентский bundle. Поддерживаются PEM, base64url raw 32-byte key и
base64url DER private key.

Endpoint host allowlist намеренно конфигурируется явно. Нельзя добавлять произвольные hosts или
разрешать HTTP: endpoint — внешняя capability, поэтому сервер проверяет HTTPS, отсутствие
credentials/fragment, стандартный порт и точное имя разрешённого provider host.

## Поддержка платформ

| Поверхность | Поведение |
| --- | --- |
| Chromium, Firefox, Edge | Web Push доступен в secure context при наличии Notification, PushManager и активного service worker; permission запрашивается только явным действием пользователя. |
| Safari на macOS | Поддержка зависит от версии Safari/ОС; нужен secure context и явное действие пользователя. |
| iOS/iPadOS 16.4+ | Только установленное на экран «Домой» Web App; обычная вкладка Safari получает объяснение и не показывает кнопку подписки. |
| Telegram Mini App | Web Push UX скрыт; используется существующий Telegram channel. |
| HTTP, unsupported browser, denied permission | Канал gracefully деградирует в in-app center; подписка не создаётся. |

Ограничения основаны на [WebKit Web Push для iOS и iPadOS](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/),
[WebKit Web Push для Safari](https://webkit.org/blog/12945/meet-web-push/),
[MDN PushManager.subscribe](https://developer.mozilla.org/en-US/docs/Web/API/PushManager/subscribe)
и [Microsoft Edge Web Push](https://learn.microsoft.com/en-us/microsoft-edge/progressive-web-apps/how-to/push).

## Rollout, disable и rollback

1. Выпустить миграцию `0075_web_push_delivery` в expand-фазе до включения delivery worker.
2. Сначала оставить `WEB_PUSH_ENABLED=false`, проверить production config и VAPID key pair,
   затем включить канал для ограниченной аудитории штатной конфигурационной процедурой.
3. Наблюдать доли `sent`, `retry`, `expired`, `failed`, `cancelled` и безопасные error
   codes. Endpoint, payload и VAPID private key в наблюдаемость не попадают.
4. Для немедленного отключения установить `WEB_PUSH_ENABLED=false` и выполнить обычный rollout.
   Новые rows не создаются, worker не делает outbound delivery; уже сохранённые подписки остаются
   до следующего добровольного включения или штатного cleanup.
5. При неуспешном релизе использовать стандартный blue/green rollback приложения. Миграцию базы
   назад в production вручную не выполнять: таблицы совместимы с отключённым каналом, а обратная
   миграция применяется только по отдельному проверенному migration plan.

VAPID secret rotation выполняется отдельной owner-authorized operational procedure: сначала
публикуется новый public key, затем клиентские подписки перерегистрируются, после чего старый
private key удаляется из secret store. Ротация не является частью обычного task rollout.

## Проверка

Автоматические проверки покрывают validation/ownership/idempotency подписок, fan-out на несколько
устройств, retry и cleanup provider failures, safe export/logging, auth/logout lifecycle, service
worker push/click handlers и permission states. Browser automation в mock Web/TMA подтверждает
контракт интерфейса; она не заменяет физическую проверку iOS Home Screen, реальную browser push
доставку или production smoke с настоящими VAPID credentials.
