# #832 — работающий React: AFTER

Снимки локального работающего React с синтетическим тестовым API, Chromium и WebKit. Полные снимки прокручиваемого документа показывают фиксированную навигацию в положении браузерного снимка; отдельно даны снимки видимой области.

Часть изображений сохранена в WebP без потерь; совпадение каждого пикселя с исходным PNG проверено. PWA и Telegram воспроизведены браузерными стендами. Клавиатура не рисуется: снимки с высотой окна 500 px моделируют уменьшение видимой области. Физический iPhone, системная клавиатура и настоящий Telegram: NOT_VERIFIED.

## Chromium: все состояния и размеры

| Состояние | 320 × 844 | 360 × 844 | 393 × 844 | 430 × 844 | 1440 × 900 |
| --- | --- | --- | --- | --- | --- |
| Обычный подход | [Dark](chromium-dark-320-bilateral.png) · [Light](chromium-light-320-bilateral.png) | [Dark](chromium-dark-360-bilateral.png) · [Light](chromium-light-360-bilateral.png) | [Dark](chromium-dark-393-bilateral.png) · [Light](chromium-light-393-bilateral.png) | [Dark](chromium-dark-430-bilateral.png) · [Light](chromium-light-430-bilateral.png) | [Dark](chromium-dark-1440-bilateral.png) · [Light](chromium-light-1440-bilateral.png) |
| Одинаковые значения | [Dark](chromium-dark-320-same.png) · [Light](chromium-light-320-same.png) | [Dark](chromium-dark-360-same.png) · [Light](chromium-light-360-same.png) | [Dark](chromium-dark-393-same.png) · [Light](chromium-light-393-same.png) | [Dark](chromium-dark-430-same.png) · [Light](chromium-light-430-same.png) | [Dark](chromium-dark-1440-same.webp) · [Light](chromium-light-1440-same.png) |
| Раздельные значения | [Dark](chromium-dark-320-asymmetric.png) · [Light](chromium-light-320-asymmetric.png) | [Dark](chromium-dark-360-asymmetric.png) · [Light](chromium-light-360-asymmetric.png) | [Dark](chromium-dark-393-asymmetric.png) · [Light](chromium-light-393-asymmetric.png) | [Dark](chromium-dark-430-asymmetric.png) · [Light](chromium-light-430-asymmetric.png) | [Dark](chromium-dark-1440-asymmetric.webp) · [Light](chromium-light-1440-asymmetric.png) |
| Одна сторона не завершена | [Dark](chromium-dark-320-partial.png) · [Light](chromium-light-320-partial.png) | [Dark](chromium-dark-360-partial.png) · [Light](chromium-light-360-partial.png) | [Dark](chromium-dark-393-partial.png) · [Light](chromium-light-393-partial.png) | [Dark](chromium-dark-430-partial.png) · [Light](chromium-light-430-partial.png) | [Dark](chromium-dark-1440-partial.webp) · [Light](chromium-light-1440-partial.png) |
| Подход завершён | [Dark](chromium-dark-320-completed.png) · [Light](chromium-light-320-completed.png) | [Dark](chromium-dark-360-completed.png) · [Light](chromium-light-360-completed.png) | [Dark](chromium-dark-393-completed.png) · [Light](chromium-light-393-completed.png) | [Dark](chromium-dark-430-completed.png) · [Light](chromium-light-430-completed.png) | [Dark](chromium-dark-1440-completed.webp) · [Light](chromium-light-1440-completed.webp) |
| Поочерёдно | [Dark](chromium-dark-320-alternating.png) · [Light](chromium-light-320-alternating.png) | [Dark](chromium-dark-360-alternating.png) · [Light](chromium-light-360-alternating.png) | [Dark](chromium-dark-393-alternating.png) · [Light](chromium-light-393-alternating.png) | [Dark](chromium-dark-430-alternating.png) · [Light](chromium-light-430-alternating.png) | [Dark](chromium-dark-1440-alternating.png) · [Light](chromium-light-1440-alternating.png) |
| История и прогрессия | [Dark](chromium-dark-320-history-progression.png) · [Light](chromium-light-320-history-progression.png) | [Dark](chromium-dark-360-history-progression.png) · [Light](chromium-light-360-history-progression.png) | [Dark](chromium-dark-393-history-progression.png) · [Light](chromium-light-393-history-progression.png) | [Dark](chromium-dark-430-history-progression.png) · [Light](chromium-light-430-history-progression.png) | [Dark](chromium-dark-1440-history-progression.webp) · [Light](chromium-light-1440-history-progression.png) |
| Журнал тренировок | [Dark](chromium-dark-320-history-journal.png) · [Light](chromium-light-320-history-journal.png) | [Dark](chromium-dark-360-history-journal.png) · [Light](chromium-light-360-history-journal.png) | [Dark](chromium-dark-393-history-journal.png) · [Light](chromium-light-393-history-journal.png) | [Dark](chromium-dark-430-history-journal.png) · [Light](chromium-light-430-history-journal.png) | [Dark](chromium-dark-1440-history-journal.png) · [Light](chromium-light-1440-history-journal.png) |
| Нет сети | [Dark](chromium-dark-320-offline.png) · [Light](chromium-light-320-offline.png) | [Dark](chromium-dark-360-offline.png) · [Light](chromium-light-360-offline.png) | [Dark](chromium-dark-393-offline.png) · [Light](chromium-light-393-offline.png) | [Dark](chromium-dark-430-offline.png) · [Light](chromium-light-430-offline.png) | [Dark](chromium-dark-1440-offline.png) · [Light](chromium-light-1440-offline.png) |
| Ошибка сохранения | [Dark](chromium-dark-320-error.png) · [Light](chromium-light-320-error.png) | [Dark](chromium-dark-360-error.png) · [Light](chromium-light-360-error.png) | [Dark](chromium-dark-393-error.png) · [Light](chromium-light-393-error.png) | [Dark](chromium-dark-430-error.png) · [Light](chromium-light-430-error.png) | [Dark](chromium-dark-1440-error.png) · [Light](chromium-light-1440-error.png) |
| Конфликт 409 | [Dark](chromium-dark-320-conflict.png) · [Light](chromium-light-320-conflict.png) | [Dark](chromium-dark-360-conflict.png) · [Light](chromium-light-360-conflict.png) | [Dark](chromium-dark-393-conflict.png) · [Light](chromium-light-393-conflict.png) | [Dark](chromium-dark-430-conflict.png) · [Light](chromium-light-430-conflict.png) | [Dark](chromium-dark-1440-conflict.png) · [Light](chromium-light-1440-conflict.png) |

## WebKit: 393 × 844

| Состояние | Dark | Light |
| --- | --- | --- |
| Обычный подход | [Снимок](webkit-dark-393-bilateral.png) | [Снимок](webkit-light-393-bilateral.png) |
| Одинаковые значения | [Снимок](webkit-dark-393-same.webp) | [Снимок](webkit-light-393-same.webp) |
| Раздельные значения | [Снимок](webkit-dark-393-asymmetric.webp) | [Снимок](webkit-light-393-asymmetric.webp) |
| Одна сторона не завершена | [Снимок](webkit-dark-393-partial.webp) | [Снимок](webkit-light-393-partial.webp) |
| Подход завершён | [Снимок](webkit-dark-393-completed.webp) | [Снимок](webkit-light-393-completed.webp) |
| Поочерёдно | [Снимок](webkit-dark-393-alternating.webp) | [Снимок](webkit-light-393-alternating.webp) |
| История и прогрессия | [Снимок](webkit-dark-393-history-progression.webp) | [Снимок](webkit-light-393-history-progression.webp) |
| Журнал тренировок | [Снимок](webkit-dark-393-history-journal.png) | [Снимок](webkit-light-393-history-journal.png) |
| Нет сети | [Снимок](webkit-dark-393-offline.webp) | [Снимок](webkit-light-393-offline.webp) |
| Ошибка сохранения | [Снимок](webkit-dark-393-error.webp) | [Снимок](webkit-light-393-error.webp) |
| Конфликт 409 | [Снимок](webkit-dark-393-conflict.webp) | [Снимок](webkit-light-393-conflict.webp) |

## Видимая область с навигацией

| Состояние | 320 | 360 | 393 | 430 |
| --- | --- | --- | --- | --- |
| Одинаковые значения | [Dark](chromium-dark-320-same-viewport.png) · [Light](chromium-light-320-same-viewport.png) | [Dark](chromium-dark-360-same-viewport.png) · [Light](chromium-light-360-same-viewport.png) | [Dark](chromium-dark-393-same-viewport.png) · [Light](chromium-light-393-same-viewport.png) | [Dark](chromium-dark-430-same-viewport.png) · [Light](chromium-light-430-same-viewport.png) |
| Раздельные значения | [Dark](chromium-dark-320-asymmetric-viewport.png) · [Light](chromium-light-320-asymmetric-viewport.png) | [Dark](chromium-dark-360-asymmetric-viewport.png) · [Light](chromium-light-360-asymmetric-viewport.png) | [Dark](chromium-dark-393-asymmetric-viewport.png) · [Light](chromium-light-393-asymmetric-viewport.png) | [Dark](chromium-dark-430-asymmetric-viewport.png) · [Light](chromium-light-430-asymmetric-viewport.png) |
| Одна сторона не завершена | [Dark](chromium-dark-320-partial-viewport.png) · [Light](chromium-light-320-partial-viewport.png) | [Dark](chromium-dark-360-partial-viewport.png) · [Light](chromium-light-360-partial-viewport.png) | [Dark](chromium-dark-393-partial-viewport.png) · [Light](chromium-light-393-partial-viewport.png) | [Dark](chromium-dark-430-partial-viewport.png) · [Light](chromium-light-430-partial-viewport.png) |
| Конфликт 409 | [Dark](chromium-dark-320-conflict-viewport.png) · [Light](chromium-light-320-conflict-viewport.png) | [Dark](chromium-dark-360-conflict-viewport.png) · [Light](chromium-light-360-conflict-viewport.png) | [Dark](chromium-dark-393-conflict-viewport.png) · [Light](chromium-light-393-conflict-viewport.png) | [Dark](chromium-dark-430-conflict-viewport.png) · [Light](chromium-light-430-conflict-viewport.png) |

Для всех состояний, кроме журнала, дополнительно доступны файлы `chromium-<тема>-393-<состояние>-viewport.png` и `webkit-<тема>-393-<состояние>-viewport.png`.

## Таймер и модель уменьшенного viewport

| Браузер / тема | 320 × 500 | 360 × 500 | 393 × 500 | 430 × 500 |
| --- | --- | --- | --- | --- |
| chromium / dark | [Снимок](chromium-dark-320-keyboard-viewport-model.png) | [Снимок](chromium-dark-360-keyboard-viewport-model.png) | [Снимок](chromium-dark-393-keyboard-viewport-model.png) | [Снимок](chromium-dark-430-keyboard-viewport-model.png) |
| chromium / light | [Снимок](chromium-light-320-keyboard-viewport-model.png) | [Снимок](chromium-light-360-keyboard-viewport-model.png) | [Снимок](chromium-light-393-keyboard-viewport-model.png) | [Снимок](chromium-light-430-keyboard-viewport-model.png) |
| webkit / dark | [Снимок](webkit-dark-320-keyboard-viewport-model.png) | [Снимок](webkit-dark-360-keyboard-viewport-model.png) | [Снимок](webkit-dark-393-keyboard-viewport-model.png) | [Снимок](webkit-dark-430-keyboard-viewport-model.png) |
| webkit / light | [Снимок](webkit-light-320-keyboard-viewport-model.png) | [Снимок](webkit-light-360-keyboard-viewport-model.png) | [Снимок](webkit-light-393-keyboard-viewport-model.png) | [Снимок](webkit-light-430-keyboard-viewport-model.png) |

## Смоделированные оболочки

- PWA: [Chromium](chromium-pwa-393-prefill.png) · [WebKit](webkit-pwa-393-prefill.png).
- Telegram: [Chromium](chromium-telegram-393-prefill.png) · [WebKit](webkit-telegram-393-prefill.png).

Пакет подготовлен для отдельной визуальной приёмки владельцем; он не является разрешением на merge или развёртывание.
