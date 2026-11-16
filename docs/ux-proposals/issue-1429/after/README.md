# Issue #1429 — AFTER

Реальный интерфейс в локальном тестовом приложении с синтетическими данными. Это не production и не снимки владельца. Chromium и WebKit запущены через Playwright; Telegram и режим PWA имитируются.

[BEFORE и утверждённый макет: тёмная тема, 393 px](../comparison-393-partial-dark.png) · [светлая тема, 393 px](../comparison-393-partial-light.png)

На длинных снимках фиксированная нижняя панель остаётся в позиции первого экрана. Отдельные снимки перехода к воде показывают фактический вид в окне и положение панели.

## Частично заполненный день

| Ширина | Chromium Light | Chromium Dark | WebKit Light | WebKit Dark |
| --- | --- | --- | --- | --- |
| 320 px | [Открыть](chromium-light-320-partial.png) | [Открыть](chromium-dark-320-partial.png) | [Открыть](webkit-light-320-partial.png) | [Открыть](webkit-dark-320-partial.png) |
| 360 px | [Открыть](chromium-light-360-partial.png) | [Открыть](chromium-dark-360-partial.png) | [Открыть](webkit-light-360-partial.png) | [Открыть](webkit-dark-360-partial.png) |
| 393 px | [Открыть](chromium-light-393-partial.png) | [Открыть](chromium-dark-393-partial.png) | [Открыть](webkit-light-393-partial.png) | [Открыть](webkit-dark-393-partial.png) |
| 430 px | [Открыть](chromium-light-430-partial.png) | [Открыть](chromium-dark-430-partial.png) | [Открыть](webkit-light-430-partial.png) | [Открыть](webkit-dark-430-partial.png) |
| 1280 px | [Открыть](chromium-light-1280-partial.png) | [Открыть](chromium-dark-1280-partial.png) | [Открыть](webkit-light-1280-partial.png) | [Открыть](webkit-dark-1280-partial.jpg) |
| 1440 px | [Открыть](chromium-light-1440-partial.png) | [Открыть](chromium-dark-1440-partial.png) | [Открыть](webkit-light-1440-partial.png) | [Открыть](webkit-dark-1440-partial.jpg) |

## Состояния, 393 px

| Состояние | Chromium Light | Chromium Dark | WebKit Light | WebKit Dark |
| --- | --- | --- | --- | --- |
| Пустой день | [Открыть](chromium-light-393-empty.png) | [Открыть](chromium-dark-393-empty.png) | [Открыть](webkit-light-393-empty.png) | [Открыть](webkit-dark-393-empty.png) |
| После повтора | [Открыть](chromium-light-393-added.png) | [Открыть](chromium-dark-393-added.png) | [Открыть](webkit-light-393-added.png) | [Открыть](webkit-dark-393-added.png) |
| Ошибка повтора | [Открыть](chromium-light-393-repeat-error.png) | [Открыть](chromium-dark-393-repeat-error.png) | [Открыть](webkit-light-393-repeat-error.png) | [Открыть](webkit-dark-393-repeat-error.png) |
| Ошибка отмены | [Открыть](chromium-light-393-undo-error.png) | [Открыть](chromium-dark-393-undo-error.png) | [Открыть](webkit-light-393-undo-error.png) | [Открыть](webkit-dark-393-undo-error.png) |
| После отмены | [Открыть](chromium-light-393-undone.png) | [Открыть](chromium-dark-393-undone.png) | [Открыть](webkit-light-393-undone.png) | [Открыть](webkit-dark-393-undone.png) |
| Подтверждение «Вчера» | [Открыть](chromium-light-393-manual.png) | [Открыть](chromium-dark-393-manual.png) | [Открыть](webkit-light-393-manual.png) | [Открыть](webkit-dark-393-manual.png) |
| Последний приём и отмена | [Открыть](chromium-light-393-last.png) | [Открыть](chromium-dark-393-last.png) | [Открыть](webkit-light-393-last.png) | [Открыть](webkit-dark-393-last.png) |
| Полный день | [Открыть](chromium-light-393-full.png) | [Открыть](chromium-dark-393-full.png) | [Открыть](webkit-light-393-full.png) | [Открыть](webkit-dark-393-full.png) |
| Загрузка дневника | [Открыть](chromium-light-393-diary-loading.png) | [Открыть](chromium-dark-393-diary-loading.png) | [Открыть](webkit-light-393-diary-loading.png) | [Открыть](webkit-dark-393-diary-loading.png) |

## Ошибка дневника и масштаб текста

| Состояние | Chromium Light | Chromium Dark | WebKit Light | WebKit Dark |
| --- | --- | --- | --- | --- |
| Ошибка дневника, вода доступна, 320 px | [Открыть](chromium-light-320-diary-error.png) | [Открыть](chromium-dark-320-diary-error.png) | [Открыть](webkit-light-320-diary-error.png) | [Открыть](webkit-dark-320-diary-error.png) |
| Текст 200%, 320 px | [Открыть](chromium-light-320-text-200.png) | — | [Открыть](webkit-light-320-text-200.png) | — |

## Переход «+ → Вода», окно 360 × 844

| Режим | Chromium Light | Chromium Dark | WebKit Light | WebKit Dark |
| --- | --- | --- | --- | --- |
| Web | [Открыть](chromium-light-360-web-water-intent.png) | [Открыть](chromium-dark-360-web-water-intent.png) | [Открыть](webkit-light-360-web-water-intent.png) | [Открыть](webkit-dark-360-web-water-intent.png) |
| Telegram, имитация safe-area | [Открыть](chromium-light-360-tma-water-intent.png) | [Открыть](chromium-dark-360-tma-water-intent.png) | [Открыть](webkit-light-360-tma-water-intent.png) | [Открыть](webkit-dark-360-tma-water-intent.png) |
