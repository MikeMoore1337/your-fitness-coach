# Issue #1434: повтор приёма пищи — визуальная приёмка

Синтетические данные и ответы API; снимки получены Playwright в Chromium и WebKit. Mobile — окно 393 × 844 CSS px, desktop — 1280 × 900 CSS px. Полностраничные снимки показывают положение закреплённой нижней панели в момент съёмки; отдельные кадры приёмов показывают карточку «Еда» целиком.

BEFORE: исходники `dev` `1f2367370cb8101deec8fb1d5e63dcad491da602`. AFTER: исходники PR `2af1803f9f53f550ff3bd3bcc8c2aeb9ed126487`. Последующий коммит содержит только доказательства и не изменяет приложение. Четыре недостающих кадра BEFORE WebKit Light досняты на той же базе: тест предварительно прокручивает кнопку в видимую область; проверка отсутствия скачка прокрутки сохранена и прошла.

## Дневник до и после

| Браузер | Тема | Mobile 393 | Desktop 1280 |
|---|---|---|---|
| Chromium | Light | [BEFORE](before/chromium-light-393-partial.png) · [AFTER](after/chromium-light-393-partial.png) | [BEFORE](before/chromium-light-1280-partial.png) · [AFTER](after/chromium-light-1280-partial.png) |
| Chromium | Dark | [BEFORE](before/chromium-dark-393-partial.png) · [AFTER](after/chromium-dark-393-partial.png) | [BEFORE](before/chromium-dark-1280-partial.png) · [AFTER](after/chromium-dark-1280-partial.png) |
| WebKit | Light | [BEFORE](before/webkit-light-393-partial.png) · [AFTER](after/webkit-light-393-partial.png) | [BEFORE](before/webkit-light-1280-partial.png) · [AFTER](after/webkit-light-1280-partial.png) |
| WebKit | Dark | [BEFORE](before/webkit-dark-393-partial.png) · [AFTER](after/webkit-dark-393-partial.png) | [BEFORE](before/webkit-dark-1280-partial.jpg) · [AFTER](after/webkit-dark-1280-partial.jpg) |

## Контекст каждого приёма — AFTER, mobile 393

| Приём | Chromium Light | Chromium Dark | WebKit Light | WebKit Dark |
|---|---|---|---|---|
| Завтрак | [снимок](after/chromium-light-393-empty.png) | [снимок](after/chromium-dark-393-empty.png) | [снимок](after/webkit-light-393-empty.png) | [снимок](after/webkit-dark-393-empty.png) |
| Обед | [снимок](after/chromium-light-393-lunch.png) | [снимок](after/chromium-dark-393-lunch.png) | [снимок](after/webkit-light-393-lunch.png) | [снимок](after/webkit-dark-393-lunch.png) |
| Ужин | [снимок](after/chromium-light-393-dinner.png) | [снимок](after/chromium-dark-393-dinner.png) | [снимок](after/webkit-light-393-dinner.png) | [снимок](after/webkit-dark-393-dinner.png) |
| Перекусы | [снимок](after/chromium-light-393-snacks.png) | [снимок](after/chromium-dark-393-snacks.png) | [снимок](after/webkit-light-393-snacks.png) | [снимок](after/webkit-dark-393-snacks.png) |

## Состояния — mobile 393

| Браузер и тема | Предложение | Ошибка повтора | Добавлено | Ошибка отмены | Отменено | Ручное «Вчера» |
|---|---|---|---|---|---|---|
| Chromium Light | [до](before/chromium-light-393-empty.png) · [после](after/chromium-light-393-empty.png) | [до](before/chromium-light-393-repeat-error.png) · [после](after/chromium-light-393-repeat-error.png) | [до](before/chromium-light-393-added.png) · [после](after/chromium-light-393-added.png) | [до](before/chromium-light-393-undo-error.png) · [после](after/chromium-light-393-undo-error.png) | [до](before/chromium-light-393-undone.png) · [после](after/chromium-light-393-undone.png) | [до](before/chromium-light-393-manual.png) · [после](after/chromium-light-393-manual.png) |
| Chromium Dark | [до](before/chromium-dark-393-empty.png) · [после](after/chromium-dark-393-empty.png) | [до](before/chromium-dark-393-repeat-error.png) · [после](after/chromium-dark-393-repeat-error.png) | [до](before/chromium-dark-393-added.png) · [после](after/chromium-dark-393-added.png) | [до](before/chromium-dark-393-undo-error.png) · [после](after/chromium-dark-393-undo-error.png) | [до](before/chromium-dark-393-undone.png) · [после](after/chromium-dark-393-undone.png) | [до](before/chromium-dark-393-manual.png) · [после](after/chromium-dark-393-manual.png) |
| Webkit Light | [до](before/webkit-light-393-empty.png) · [после](after/webkit-light-393-empty.png) | [до](before/webkit-light-393-repeat-error.png) · [после](after/webkit-light-393-repeat-error.png) | [до](before/webkit-light-393-added.png) · [после](after/webkit-light-393-added.png) | [до](before/webkit-light-393-undo-error.png) · [после](after/webkit-light-393-undo-error.png) | [до](before/webkit-light-393-undone.png) · [после](after/webkit-light-393-undone.png) | [до](before/webkit-light-393-manual.png) · [после](after/webkit-light-393-manual.png) |
| Webkit Dark | [до](before/webkit-dark-393-empty.png) · [после](after/webkit-dark-393-empty.png) | [до](before/webkit-dark-393-repeat-error.png) · [после](after/webkit-dark-393-repeat-error.png) | [до](before/webkit-dark-393-added.png) · [после](after/webkit-dark-393-added.png) | [до](before/webkit-dark-393-undo-error.png) · [после](after/webkit-dark-393-undo-error.png) | [до](before/webkit-dark-393-undone.png) · [после](after/webkit-dark-393-undone.png) | [до](before/webkit-dark-393-manual.png) · [после](after/webkit-dark-393-manual.png) |

Физические устройства, реальный Telegram/PWA и screen reader не проверялись. Данные снимков не являются production-данными. Принятие визуального результата не является разрешением на merge или deploy.
