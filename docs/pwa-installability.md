# Устанавливаемый Web-клиент и возврат к тренировке

Task 86 добавляет один и тот же Web-клиент в режиме PWA. Это не второй frontend, не native-приложение
и не обещание полного offline-доступа.

## Границы платформы

Manifest и service worker дают браузеру данные для установки и локального запуска, но итоговое
решение об установке принимает конкретный браузер и ОС. Programmatic install prompt доступен не во
всех браузерах. На iOS пользовательский сценарий остаётся browser-specific: при доступной
поддержке нужно использовать «Поделиться» → «На экран Домой». Telegram Mini App не показывает
Web-install prompt: TMA уже является отдельной поверхностью и не должна получать бессмысленную
дублирующую установку.

Набор иконок содержит обычную и maskable-иконку; `id`, `start_url` и `scope` заданы относительными
same-origin путями, поэтому manifest не может перенаправить установку на внешний адрес. Shortcut
ведёт в существующий раздел «Сегодня» и не обходит auth, onboarding или server-side ownership.

## Что кэшируется

| Класс                                                                        | Стратегия                       | Ограничения                                                                                 |
| ---------------------------------------------------------------------------- | ------------------------------- | ------------------------------------------------------------------------------------------- |
| `/app` и app navigation                                                      | stale-while-revalidate          | В кэше только один static HTML shell; API не подменяется shell-ответом                      |
| App assets (`/assets/<file>`, `/assets/brand/*`, `/assets/providers/*`)      | cache-first с сетью при промахе | Ограниченный cache `yfc-pwa-static-v1`, до 80 записей и до 7 суток; landing media не входит |
| `/api/*`                                                                     | только сеть                     | Authenticated responses, queue payloads, exports, фото и support text не кэшируются         |
| `/assets/marketing/*`, `/assets/product/*`, `/static/*` и публичные страницы | только сеть                     | Публичные landing media и HTML не расширяют offline scope                                   |

Кэш содержит только код, стили, иконки и HTML-оболочку. Access token, cookies, user ID в auth-роли,
содержимое тренировки и ответы приватных API туда не записываются. Snapshot и очередь активной
тренировки продолжают жить в существующем account-scoped `localStorage`-механизме; его контракт
описан в [offline-active-workout.md](offline-active-workout.md).

При активации удаляются старые кэши с prefix `yfc-pwa-`; размер и возраст текущего кэша ограничены.
Если сеть или кэш недоступны, navigation возвращается к обычному network error, а не выдаёт
несвязанные или частично восстановленные пользовательские данные.

## Возврат к активной тренировке

Установленный запуск открывает `/app` в том же Web-клиенте. После восстановления auth-сессии
Today использует canonical snapshot/queue и показывает существующее primary action
«Продолжить тренировку». При `pagehide`, `freeze`, уходе в background и возврате через `pageshow`,
focus или visibility snapshot сохраняется, а Today-запрос инвалидируется для проверки актуального
server state.

Если session storage был уничтожен Telegram WebView или браузером, локальный snapshot не становится
доказательством авторизации: приложение ждёт обычную server-side auth/initData-проверку. Смена
пользователя и logout очищают account-scoped локальные данные по существующему auth lifecycle.
Завершённая, удалённая или потерявшая ownership тренировка не открывается как активная; очередь
синхронизируется существующими идемпотентными механизмами и конфликтами версии.

## Install UX и аналитика

Карточка установки появляется только на authenticated Web-экране Today после получения ценности:
минимум после двух app opens в bounded local state или после завершения тренировки. Это не modal и
не блокирует работу. Отказ запоминается на 30 дней. Пользователь видит пользу «быстрый запуск и
возврат», а не обещание полноценной работы без сети.

События контекстно свободны и не содержат browser fingerprint, user ID или payload тренировки:

- `pwa_install_option_shown`, `pwa_install_option_dismissed`, `pwa_install_option_accepted`;
- `pwa_standalone_launched`;
- `pwa_workout_resume_success`, `pwa_workout_resume_failure`;
- `pwa_service_worker_error` с ограниченной категорией сбоя;
- `pwa_update_available`, `pwa_update_applied`.

Эти сигналы описывают воронку и технические ошибки. Простое сравнение retention между группами не
является доказательством причинного эффекта установки.

## Обновление и rollback

Waiting worker не делает молчаливый reload. На обычном экране приложение показывает ненавязчивое
обновление и применяет его только по действию пользователя. При активной тренировке действие
откладывается; после завершения тренировки очередь и snapshot должны быть очищены/синхронизированы
по canonical flow, после чего update разрешается. При установке первого worker контролируемый
`skipWaiting` допустим, потому что ещё нет активной страницы, которую нужно беречь.

Для аварийного отключения PWA следующий production build собирается с `VITE_PWA_ENABLED=false`.
Новый shell при ближайшем сетевом открытии удаляет только зарегистрированный YFC root service
worker и кэши `yfc-pwa-*`. До получения нового shell старый cached shell может оставаться у клиента,
поэтому это не замена штатному rollback. Откат версии выполняется только стандартным blue/green
release rollback, описанным в [production-deployment.md](production-deployment.md), без ручной
миграции базы назад.

Для самого Task 86 изменение API/schema не требуется: active workout queue остаётся совместимой с
существующим backend-контрактом. Web Push subscriptions, permission UX, delivery и backend
notification integration реализованы отдельным [Task 86A](web-push-notifications.md)
и используют уже существующий PWA service worker.

## Проверка перед release

Минимальная проверка должна включать production build, отдачу `/manifest.webmanifest` и `/sw.js`,
проверку manifest/icon/maskable, отсутствие API/private cache entries, install/standalone auth,
resume online/offline/reconnect, safe update с активной тренировкой, logout/user switch, TMA без
install prompt и keyboard/focus/reflow состояния карточек. Физическое подтверждение конкретного
браузера или устройства следует указывать отдельно от browser/mock-TMA проверки.
