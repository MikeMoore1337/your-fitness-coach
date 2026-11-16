# Issue #954 — AFTER для визуального принятия

Снимки показывают работающий frontend с синтетическими тестовыми ответами API; имена и показатели вымышлены. Это не production и не физическое устройство.

Размеры указаны в CSS-пикселях: desktop 1280 × 720, mobile и эмуляция Telegram Mini App 390 × 844, узкий mobile 320 × 844. Chromium 151.0.7922.34, WebKit 26.5; WebKit сохраняет изображение с коэффициентом устройства 2.

На полных снимках только для съёмки скрыта фиксированная нижняя панель, чтобы она не закрывала части длинной страницы. Отдельные viewport-снимки ниже показывают фактический экран с панелью. Telegram здесь эмулируется; это не проверка реального Telegram WebView.

## Все состояния: Chromium

| Состояние | Desktop | Mobile | TMA, эмуляция |
| --- | --- | --- | --- |
| Тренер: отчёт | [Dark](after/chromium-desktop-dark-trainer-report.png) · [Light](after/chromium-desktop-light-trainer-report.png) | [Dark](after/chromium-mobile-dark-trainer-report.png) · [Light](after/chromium-mobile-light-trainer-report.png) | [Dark](after/chromium-tma-dark-trainer-report.png) · [Light](after/chromium-tma-light-trainer-report.png) |
| Тренер: изменение | [Dark](after/chromium-desktop-dark-trainer-edit.png) · [Light](after/chromium-desktop-light-trainer-edit.png) | [Dark](after/chromium-mobile-dark-trainer-edit.png) · [Light](after/chromium-mobile-light-trainer-edit.png) | [Dark](after/chromium-tma-dark-trainer-edit.png) · [Light](after/chromium-tma-light-trainer-edit.png) |
| Тренер: проверка | [Dark](after/chromium-desktop-dark-trainer-review.png) · [Light](after/chromium-desktop-light-trainer-review.png) | [Dark](after/chromium-mobile-dark-trainer-review.png) · [Light](after/chromium-mobile-light-trainer-review.png) | [Dark](after/chromium-tma-dark-trainer-review.png) · [Light](after/chromium-tma-light-trainer-review.png) |
| Тренер: ожидает ответа | [Dark](after/chromium-desktop-dark-trainer-sent.png) · [Light](after/chromium-desktop-light-trainer-sent.png) | [Dark](after/chromium-mobile-dark-trainer-sent.png) · [Light](after/chromium-mobile-light-trainer-sent.png) | [Dark](after/chromium-tma-dark-trainer-sent.png) · [Light](after/chromium-tma-light-trainer-sent.png) |
| Тренер: принято | [Dark](after/chromium-desktop-dark-trainer-accepted.png) · [Light](after/chromium-desktop-light-trainer-accepted.png) | [Dark](after/chromium-mobile-dark-trainer-accepted.png) · [Light](after/chromium-mobile-light-trainer-accepted.png) | [Dark](after/chromium-tma-dark-trainer-accepted.png) · [Light](after/chromium-tma-light-trainer-accepted.png) |
| Тренер: отклонено | [Dark](after/chromium-desktop-dark-trainer-rejected.png) · [Light](after/chromium-desktop-light-trainer-rejected.png) | [Dark](after/chromium-mobile-dark-trainer-rejected.png) · [Light](after/chromium-mobile-light-trainer-rejected.png) | [Dark](after/chromium-tma-dark-trainer-rejected.png) · [Light](after/chromium-tma-light-trainer-rejected.png) |
| Тренер: нет доступа | [Dark](after/chromium-desktop-dark-trainer-revoked.png) · [Light](after/chromium-desktop-light-trainer-revoked.png) | [Dark](after/chromium-mobile-dark-trainer-revoked.png) · [Light](after/chromium-mobile-light-trainer-revoked.png) | [Dark](after/chromium-tma-dark-trainer-revoked.png) · [Light](after/chromium-tma-light-trainer-revoked.png) |
| Тренер: нет данных | [Dark](after/chromium-desktop-dark-trainer-empty.png) · [Light](after/chromium-desktop-light-trainer-empty.png) | [Dark](after/chromium-mobile-dark-trainer-empty.png) · [Light](after/chromium-mobile-light-trainer-empty.png) | [Dark](after/chromium-tma-dark-trainer-empty.png) · [Light](after/chromium-tma-light-trainer-empty.png) |
| Тренер: программа изменилась | [Dark](after/chromium-desktop-dark-trainer-program.png) · [Light](after/chromium-desktop-light-trainer-program.png) | [Dark](after/chromium-mobile-dark-trainer-program.png) · [Light](after/chromium-mobile-light-trainer-program.png) | [Dark](after/chromium-tma-dark-trainer-program.png) · [Light](after/chromium-tma-light-trainer-program.png) |
| Тренер: ошибка | [Dark](after/chromium-desktop-dark-trainer-error.png) · [Light](after/chromium-desktop-light-trainer-error.png) | [Dark](after/chromium-mobile-dark-trainer-error.png) · [Light](after/chromium-mobile-light-trainer-error.png) | [Dark](after/chromium-tma-dark-trainer-error.png) · [Light](after/chromium-tma-light-trainer-error.png) |
| Тренер: загрузка | [Dark](after/chromium-desktop-dark-trainer-loading.png) · [Light](after/chromium-desktop-light-trainer-loading.png) | [Dark](after/chromium-mobile-dark-trainer-loading.png) · [Light](after/chromium-mobile-light-trainer-loading.png) | [Dark](after/chromium-tma-dark-trainer-loading.png) · [Light](after/chromium-tma-light-trainer-loading.png) |
| Клиент: предложение | [Dark](after/chromium-desktop-dark-client-review.png) · [Light](after/chromium-desktop-light-client-review.png) | [Dark](after/chromium-mobile-dark-client-review.png) · [Light](after/chromium-mobile-light-client-review.png) | [Dark](after/chromium-tma-dark-client-review.png) · [Light](after/chromium-tma-light-client-review.png) |
| Клиент: принято | [Dark](after/chromium-desktop-dark-client-accept.png) · [Light](after/chromium-desktop-light-client-accept.png) | [Dark](after/chromium-mobile-dark-client-accept.png) · [Light](after/chromium-mobile-light-client-accept.png) | [Dark](after/chromium-tma-dark-client-accept.png) · [Light](after/chromium-tma-light-client-accept.png) |
| Клиент: отклонено | [Dark](after/chromium-desktop-dark-client-reject.png) · [Light](after/chromium-desktop-light-client-reject.png) | [Dark](after/chromium-mobile-dark-client-reject.png) · [Light](after/chromium-mobile-light-client-reject.png) | [Dark](after/chromium-tma-dark-client-reject.png) · [Light](after/chromium-tma-light-client-reject.png) |
| Клиент: устаревшие данные | [Dark](after/chromium-desktop-dark-client-stale.png) · [Light](after/chromium-desktop-light-client-stale.png) | [Dark](after/chromium-mobile-dark-client-stale.png) · [Light](after/chromium-mobile-light-client-stale.png) | [Dark](after/chromium-tma-dark-client-stale.png) · [Light](after/chromium-tma-light-client-stale.png) |
| Клиент: недоступно | [Dark](after/chromium-desktop-dark-client-unavailable.png) · [Light](after/chromium-desktop-light-client-unavailable.png) | [Dark](after/chromium-mobile-dark-client-unavailable.png) · [Light](after/chromium-mobile-light-client-unavailable.png) | [Dark](after/chromium-tma-dark-client-unavailable.png) · [Light](after/chromium-tma-light-client-unavailable.png) |

## WebKit: ключевые состояния

| Состояние | Desktop | Mobile |
| --- | --- | --- |
| Тренер: отчёт | [Dark](after/webkit-desktop-dark-trainer-report.png) · [Light](after/webkit-desktop-light-trainer-report.png) | [Dark](after/webkit-mobile-dark-trainer-report.png) · [Light](after/webkit-mobile-light-trainer-report.png) |
| Тренер: проверка | [Dark](after/webkit-desktop-dark-trainer-review.png) · [Light](after/webkit-desktop-light-trainer-review.png) | [Dark](after/webkit-mobile-dark-trainer-review.png) · [Light](after/webkit-mobile-light-trainer-review.png) |
| Тренер: нет доступа | [Dark](after/webkit-desktop-dark-trainer-revoked.png) · [Light](after/webkit-desktop-light-trainer-revoked.png) | [Dark](after/webkit-mobile-dark-trainer-revoked.png) · [Light](after/webkit-mobile-light-trainer-revoked.png) |
| Тренер: программа изменилась | [Dark](after/webkit-desktop-dark-trainer-program.png) · [Light](after/webkit-desktop-light-trainer-program.png) | [Dark](after/webkit-mobile-dark-trainer-program.png) · [Light](after/webkit-mobile-light-trainer-program.png) |
| Клиент: предложение | [Dark](after/webkit-desktop-dark-client-review.png) · [Light](after/webkit-desktop-light-client-review.png) | [Dark](after/webkit-mobile-dark-client-review.png) · [Light](after/webkit-mobile-light-client-review.png) |
| Клиент: устаревшие данные | [Dark](after/webkit-desktop-dark-client-stale.png) · [Light](after/webkit-desktop-light-client-stale.png) | [Dark](after/webkit-mobile-dark-client-stale.png) · [Light](after/webkit-mobile-light-client-stale.png) |

## Узкий экран 320 × 844

| Состояние | Chromium | WebKit |
| --- | --- | --- |
| Тренер: изменение | [Dark](after/chromium-mobile-320-dark-trainer-edit.png) · [Light](after/chromium-mobile-320-light-trainer-edit.png) | [Dark](after/webkit-mobile-320-dark-trainer-edit.png) · [Light](after/webkit-mobile-320-light-trainer-edit.png) |
| Тренер: проверка | [Dark](after/chromium-mobile-320-dark-trainer-review.png) · [Light](after/chromium-mobile-320-light-trainer-review.png) | [Dark](after/webkit-mobile-320-dark-trainer-review.png) · [Light](after/webkit-mobile-320-light-trainer-review.png) |
| Тренер: нет доступа | [Dark](after/chromium-mobile-320-dark-trainer-revoked.png) · [Light](after/chromium-mobile-320-light-trainer-revoked.png) | [Dark](after/webkit-mobile-320-dark-trainer-revoked.png) · [Light](after/webkit-mobile-320-light-trainer-revoked.png) |
| Тренер: нет данных | [Dark](after/chromium-mobile-320-dark-trainer-empty.png) · [Light](after/chromium-mobile-320-light-trainer-empty.png) | [Dark](after/webkit-mobile-320-dark-trainer-empty.png) · [Light](after/webkit-mobile-320-light-trainer-empty.png) |
| Клиент: предложение | [Dark](after/chromium-mobile-320-dark-client-review.png) · [Light](after/chromium-mobile-320-light-client-review.png) | [Dark](after/webkit-mobile-320-dark-client-review.png) · [Light](after/webkit-mobile-320-light-client-review.png) |
| Клиент: устаревшие данные | [Dark](after/chromium-mobile-320-dark-client-stale.png) · [Light](after/chromium-mobile-320-light-client-stale.png) | [Dark](after/webkit-mobile-320-dark-client-stale.png) · [Light](after/webkit-mobile-320-light-client-stale.png) |

## Реальный viewport с нижней навигацией

| Состояние | Mobile Chromium | TMA Chromium, эмуляция |
| --- | --- | --- |
| Тренер: отчёт | [Dark](after/chromium-mobile-dark-trainer-report-viewport.png) · [Light](after/chromium-mobile-light-trainer-report-viewport.png) | [Dark](after/chromium-tma-dark-trainer-report-viewport.png) · [Light](after/chromium-tma-light-trainer-report-viewport.png) |
| Тренер: проверка | [Dark](after/chromium-mobile-dark-trainer-review-viewport.png) · [Light](after/chromium-mobile-light-trainer-review-viewport.png) | [Dark](after/chromium-tma-dark-trainer-review-viewport.png) · [Light](after/chromium-tma-light-trainer-review-viewport.png) |
| Клиент: предложение | [Dark](after/chromium-mobile-dark-client-review-viewport.png) · [Light](after/chromium-mobile-light-client-review-viewport.png) | [Dark](after/chromium-tma-dark-client-review-viewport.png) · [Light](after/chromium-tma-light-client-review-viewport.png) |
| Клиент: устаревшие данные | [Dark](after/chromium-mobile-dark-client-stale-viewport.png) · [Light](after/chromium-mobile-light-client-stale-viewport.png) | [Dark](after/chromium-tma-dark-client-stale-viewport.png) · [Light](after/chromium-tma-light-client-stale-viewport.png) |
| Клиент: недоступно | [Dark](after/chromium-mobile-dark-client-unavailable-viewport.png) · [Light](after/chromium-mobile-light-client-unavailable-viewport.png) | [Dark](after/chromium-tma-dark-client-unavailable-viewport.png) · [Light](after/chromium-tma-light-client-unavailable-viewport.png) |
