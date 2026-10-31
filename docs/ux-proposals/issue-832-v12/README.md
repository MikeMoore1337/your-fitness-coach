# #832 — пакет для визуального и доменного согласования

Статус: **ожидает решения владельца**. Это отдельный HTML-макет с синтетическими данными; рабочий React, API и БД не изменены. Исходная ревизия dev: `f9c607ac1a2ef776b5ee2a126d4b21582b9cb630`.

[Доменный контракт и решения D1–D4](domain-contract.md) · [HTML-макет](review.html) · [Результат проверки геометрии](captures/matrix.json)

## Все состояния и размеры

Каждая ссылка — PNG Chromium; в ячейке сначала Dark, затем Light. Mobile viewport — ширина × 844 px; desktop — 1440 × 900 px. Кроме клавиатуры это снимки полного документа с прокруткой, а не экран устройства такой высоты: док в длинных изображениях скрыт только для обзора. Ниже приведены отдельные viewport-снимки с доком. Клавиатура — нарисованная модель, не системная.

| Состояние | 320 | 360 | 393 | 430 | 1440 |
| --- | --- | --- | --- | --- | --- |
| Двусторонний подход | [dark](captures/chromium-dark-320-bilateral.png) · [light](captures/chromium-light-320-bilateral.png) | [dark](captures/chromium-dark-360-bilateral.png) · [light](captures/chromium-light-360-bilateral.png) | [dark](captures/chromium-dark-393-bilateral.png) · [light](captures/chromium-light-393-bilateral.png) | [dark](captures/chromium-dark-430-bilateral.png) · [light](captures/chromium-light-430-bilateral.png) | [dark](captures/chromium-dark-1440-bilateral.png) · [light](captures/chromium-light-1440-bilateral.png) |
| Выбор способа выполнения | [dark](captures/chromium-dark-320-choose-mode.png) · [light](captures/chromium-light-320-choose-mode.png) | [dark](captures/chromium-dark-360-choose-mode.png) · [light](captures/chromium-light-360-choose-mode.png) | [dark](captures/chromium-dark-393-choose-mode.png) · [light](captures/chromium-light-393-choose-mode.png) | [dark](captures/chromium-dark-430-choose-mode.png) · [light](captures/chromium-light-430-choose-mode.png) | [dark](captures/chromium-dark-1440-choose-mode.png) · [light](captures/chromium-light-1440-choose-mode.png) |
| Одинаково для обеих сторон | [dark](captures/chromium-dark-320-same.png) · [light](captures/chromium-light-320-same.png) | [dark](captures/chromium-dark-360-same.png) · [light](captures/chromium-light-360-same.png) | [dark](captures/chromium-dark-393-same.png) · [light](captures/chromium-light-393-same.png) | [dark](captures/chromium-dark-430-same.png) · [light](captures/chromium-light-430-same.png) | [dark](captures/chromium-dark-1440-same.png) · [light](captures/chromium-light-1440-same.png) |
| Разные результаты и RIR/отказ | [dark](captures/chromium-dark-320-asymmetric.png) · [light](captures/chromium-light-320-asymmetric.png) | [dark](captures/chromium-dark-360-asymmetric.png) · [light](captures/chromium-light-360-asymmetric.png) | [dark](captures/chromium-dark-393-asymmetric.png) · [light](captures/chromium-light-393-asymmetric.png) | [dark](captures/chromium-dark-430-asymmetric.png) · [light](captures/chromium-light-430-asymmetric.png) | [dark](captures/chromium-dark-1440-asymmetric.png) · [light](captures/chromium-light-1440-asymmetric.png) |
| Одна сторона не завершена | [dark](captures/chromium-dark-320-partial.png) · [light](captures/chromium-light-320-partial.png) | [dark](captures/chromium-dark-360-partial.png) · [light](captures/chromium-light-360-partial.png) | [dark](captures/chromium-dark-393-partial.png) · [light](captures/chromium-light-393-partial.png) | [dark](captures/chromium-dark-430-partial.png) · [light](captures/chromium-light-430-partial.png) | [dark](captures/chromium-dark-1440-partial.png) · [light](captures/chromium-light-1440-partial.png) |
| Подход завершён | [dark](captures/chromium-dark-320-completed.png) · [light](captures/chromium-light-320-completed.png) | [dark](captures/chromium-dark-360-completed.png) · [light](captures/chromium-light-360-completed.png) | [dark](captures/chromium-dark-393-completed.png) · [light](captures/chromium-light-393-completed.png) | [dark](captures/chromium-dark-430-completed.png) · [light](captures/chromium-light-430-completed.png) | [dark](captures/chromium-dark-1440-completed.png) · [light](captures/chromium-light-1440-completed.png) |
| Поочерёдное выполнение | [dark](captures/chromium-dark-320-alternating.png) · [light](captures/chromium-light-320-alternating.png) | [dark](captures/chromium-dark-360-alternating.png) · [light](captures/chromium-light-360-alternating.png) | [dark](captures/chromium-dark-393-alternating.png) · [light](captures/chromium-light-393-alternating.png) | [dark](captures/chromium-dark-430-alternating.png) · [light](captures/chromium-light-430-alternating.png) | [dark](captures/chromium-dark-1440-alternating.png) · [light](captures/chromium-light-1440-alternating.png) |
| История и прогрессия | [dark](captures/chromium-dark-320-history.png) · [light](captures/chromium-light-320-history.png) | [dark](captures/chromium-dark-360-history.png) · [light](captures/chromium-light-360-history.png) | [dark](captures/chromium-dark-393-history.png) · [light](captures/chromium-light-393-history.png) | [dark](captures/chromium-dark-430-history.png) · [light](captures/chromium-light-430-history.png) | [dark](captures/chromium-dark-1440-history.png) · [light](captures/chromium-light-1440-history.png) |
| Нет сети | [dark](captures/chromium-dark-320-offline.png) · [light](captures/chromium-light-320-offline.png) | [dark](captures/chromium-dark-360-offline.png) · [light](captures/chromium-light-360-offline.png) | [dark](captures/chromium-dark-393-offline.png) · [light](captures/chromium-light-393-offline.png) | [dark](captures/chromium-dark-430-offline.png) · [light](captures/chromium-light-430-offline.png) | [dark](captures/chromium-dark-1440-offline.png) · [light](captures/chromium-light-1440-offline.png) |
| Ошибка сохранения | [dark](captures/chromium-dark-320-error.png) · [light](captures/chromium-light-320-error.png) | [dark](captures/chromium-dark-360-error.png) · [light](captures/chromium-light-360-error.png) | [dark](captures/chromium-dark-393-error.png) · [light](captures/chromium-light-393-error.png) | [dark](captures/chromium-dark-430-error.png) · [light](captures/chromium-light-430-error.png) | [dark](captures/chromium-dark-1440-error.png) · [light](captures/chromium-light-1440-error.png) |
| Конфликт 409 | [dark](captures/chromium-dark-320-conflict.png) · [light](captures/chromium-light-320-conflict.png) | [dark](captures/chromium-dark-360-conflict.png) · [light](captures/chromium-light-360-conflict.png) | [dark](captures/chromium-dark-393-conflict.png) · [light](captures/chromium-light-393-conflict.png) | [dark](captures/chromium-dark-430-conflict.png) · [light](captures/chromium-light-430-conflict.png) | [dark](captures/chromium-dark-1440-conflict.png) · [light](captures/chromium-light-1440-conflict.png) |
| Сравнение версий при 409 | [dark](captures/chromium-dark-320-conflict-review.png) · [light](captures/chromium-light-320-conflict-review.png) | [dark](captures/chromium-dark-360-conflict-review.png) · [light](captures/chromium-light-360-conflict-review.png) | [dark](captures/chromium-dark-393-conflict-review.png) · [light](captures/chromium-light-393-conflict-review.png) | [dark](captures/chromium-dark-430-conflict-review.png) · [light](captures/chromium-light-430-conflict-review.png) | [dark](captures/chromium-dark-1440-conflict-review.png) · [light](captures/chromium-light-1440-conflict-review.png) |
| Таймер v2 и модель клавиатуры | [dark](captures/chromium-dark-320-keyboard.png) · [light](captures/chromium-light-320-keyboard.png) | [dark](captures/chromium-dark-360-keyboard.png) · [light](captures/chromium-light-360-keyboard.png) | [dark](captures/chromium-dark-393-keyboard.png) · [light](captures/chromium-light-393-keyboard.png) | [dark](captures/chromium-dark-430-keyboard.png) · [light](captures/chromium-light-430-keyboard.png) | — |

## WebKit и настоящие размеры viewport

Ниже — WebKit 393 × 844; для клавиатуры видна моделируемая область клавиатуры.

| Состояние | Dark | Light |
| --- | --- | --- |
| Двусторонний подход | [PNG](captures/webkit-dark-393-bilateral.png) | [PNG](captures/webkit-light-393-bilateral.png) |
| Выбор способа выполнения | [PNG](captures/webkit-dark-393-choose-mode.png) | [PNG](captures/webkit-light-393-choose-mode.png) |
| Одинаково для обеих сторон | [PNG](captures/webkit-dark-393-same.png) | [PNG](captures/webkit-light-393-same.png) |
| Разные результаты и RIR/отказ | [PNG](captures/webkit-dark-393-asymmetric.png) | [PNG](captures/webkit-light-393-asymmetric.png) |
| Одна сторона не завершена | [PNG](captures/webkit-dark-393-partial.png) | [PNG](captures/webkit-light-393-partial.png) |
| Подход завершён | [PNG](captures/webkit-dark-393-completed.png) | [PNG](captures/webkit-light-393-completed.png) |
| Поочерёдное выполнение | [PNG](captures/webkit-dark-393-alternating.png) | [PNG](captures/webkit-light-393-alternating.png) |
| История и прогрессия | [PNG](captures/webkit-dark-393-history.png) | [PNG](captures/webkit-light-393-history.png) |
| Нет сети | [PNG](captures/webkit-dark-393-offline.png) | [PNG](captures/webkit-light-393-offline.png) |
| Ошибка сохранения | [PNG](captures/webkit-dark-393-error.png) | [PNG](captures/webkit-light-393-error.png) |
| Конфликт 409 | [PNG](captures/webkit-dark-393-conflict.png) | [PNG](captures/webkit-light-393-conflict.png) |
| Сравнение версий при 409 | [PNG](captures/webkit-dark-393-conflict-review.png) | [PNG](captures/webkit-light-393-conflict-review.png) |
| Таймер v2 и модель клавиатуры | [PNG](captures/webkit-dark-393-keyboard.png) | [PNG](captures/webkit-light-393-keyboard.png) |

Для оценки дока и таймера в видимой области без длинного снимка:
- одинаково: [chromium dark](captures/chromium-dark-393-same-viewport.png) · [chromium light](captures/chromium-light-393-same-viewport.png) · [webkit dark](captures/webkit-dark-393-same-viewport.png) · [webkit light](captures/webkit-light-393-same-viewport.png)
- раздельный ввод: [chromium dark](captures/chromium-dark-393-asymmetric-viewport.png) · [chromium light](captures/chromium-light-393-asymmetric-viewport.png) · [webkit dark](captures/webkit-dark-393-asymmetric-viewport.png) · [webkit light](captures/webkit-light-393-asymmetric-viewport.png)
- неполная сторона: [chromium dark](captures/chromium-dark-393-partial-viewport.png) · [chromium light](captures/chromium-light-393-partial-viewport.png) · [webkit dark](captures/webkit-dark-393-partial-viewport.png) · [webkit light](captures/webkit-light-393-partial-viewport.png)
- 409: [chromium dark](captures/chromium-dark-393-conflict-viewport.png) · [chromium light](captures/chromium-light-393-conflict-viewport.png) · [webkit dark](captures/webkit-dark-393-conflict-viewport.png) · [webkit light](captures/webkit-light-393-conflict-viewport.png)
- выбор версии: [chromium dark](captures/chromium-dark-393-conflict-review-viewport.png) · [chromium light](captures/chromium-light-393-conflict-review-viewport.png) · [webkit dark](captures/webkit-dark-393-conflict-review-viewport.png) · [webkit light](captures/webkit-light-393-conflict-review-viewport.png)

## Baseline текущего React

[Dark, 393 × 844](captures/baseline-react-dark-393.png) · [Light, 393 × 844](captures/baseline-react-light-393.png). Это реальные снимки локального React с тестовым API, снятые до разработки #832 на указанной ревизии. Они показывают текущий обычный подход, не поддержку сторон.

## Проверки и границы

- PASS: 256 комбинаций HTML-макета — Chromium/WebKit × Dark/Light × 13 состояний × 320/360/393/430/1440 px, кроме модели мобильной клавиатуры на desktop. Проверялись отсутствие горизонтального overflow, минимальные размеры видимых кнопок, обрезка их текста, положение сфокусированного поля относительно модели клавиатуры и таймера, ошибки страницы.
- PASS: 32 проверки взаимодействий HTML-макета в Chromium/WebKit и двух темах: раскрытие раздельного ввода, независимый RIR, сохранение значений при отклонённом объединении, блокировка неполного/завершённого/конфликтного подхода, выбор первой стороны, показ обеих версий и выбор режима.
- PASS: 2 существующих теста #1162 в локальном Chromium на текущем baseline React с синтетическим API. Они не проверяют #832.
- Таймер, история и конфликт в HTML — иллюстрация предлагаемого поведения. Полноценные offline/409, API, миграция, PostgreSQL, accessibility, Web/PWA/TMA и CI для #832 ещё не выполнялись.
- Независимый QA-подагент: BLOCKED — Toolkit preflight вернул `CONSENT_OR_STATE_DENIED`; инвентарь и условия отдельного вызова не подтверждены. Просмотр выполнен в основном контексте.
- Физический iPhone, нативная клавиатура, настоящий Telegram и аппаратный screen reader: NOT_VERIFIED.

## Решения владельца

1. D1: одна или обе стороны для завершения и учёта частичного факта.
2. D2: сумма явно подтверждённых повторов и внешнего объёма сторон; примеры и альтернатива — в контракте.
3. D3: сравнение каждой стороны отдельно и сохранение прежней скалярной истории без выдуманного режима.
4. D4: сохранение идентичности и сторон в экспорте и нейтральном импорте #833.
5. Визуальный пакет целиком: компактный общий ввод, раскрытие сторон, состояния и разрешение на реализацию согласованного варианта.

Отдельные визуальная приёмка реального AFTER и разрешение на merge в dev остаются после реализации; production и master вне задачи.
