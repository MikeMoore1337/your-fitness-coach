# #1430 — КБЖУ приёмов пищи: BEFORE / AFTER

Рендер настоящего локального приложения с синтетическими ответами API, фиксированная дата 19 августа 2026. BEFORE: исходники dev `b462b9e35cbb248be4f3e79ad87555c940e75163`. AFTER: реализация в этом PR. Данные, браузеры и размеры окна для пар совпадают.

На снимках заполнены все четыре приёма. В обеде часть макронутриентов неизвестна, жиры равны нулю; остальные значения включают дробные граммы. Отдельные кадры ниже показывают добавление, изменение и удаление записи.

## Сравнение приёмов

Окно: 320/360/393/430 × 844 и 1280 × 900 CSS px. Изображения в таблице обрезаны по карточке еды.

| Ширина | Chromium Light | Chromium Dark | WebKit Light | WebKit Dark |
|---:|---|---|---|---|
| 320 | [до](before/chromium-light-320-meals.png) · [после](after/chromium-light-320-meals.png) | [до](before/chromium-dark-320-meals.png) · [после](after/chromium-dark-320-meals.png) | [до](before/webkit-light-320-meals.png) · [после](after/webkit-light-320-meals.png) | [до](before/webkit-dark-320-meals.png) · [после](after/webkit-dark-320-meals.png) |
| 360 | [до](before/chromium-light-360-meals.png) · [после](after/chromium-light-360-meals.png) | [до](before/chromium-dark-360-meals.png) · [после](after/chromium-dark-360-meals.png) | [до](before/webkit-light-360-meals.png) · [после](after/webkit-light-360-meals.png) | [до](before/webkit-dark-360-meals.png) · [после](after/webkit-dark-360-meals.png) |
| 393 | [до](before/chromium-light-393-meals.png) · [после](after/chromium-light-393-meals.png) | [до](before/chromium-dark-393-meals.png) · [после](after/chromium-dark-393-meals.png) | [до](before/webkit-light-393-meals.png) · [после](after/webkit-light-393-meals.png) | [до](before/webkit-dark-393-meals.png) · [после](after/webkit-dark-393-meals.png) |
| 430 | [до](before/chromium-light-430-meals.png) · [после](after/chromium-light-430-meals.png) | [до](before/chromium-dark-430-meals.png) · [после](after/chromium-dark-430-meals.png) | [до](before/webkit-light-430-meals.png) · [после](after/webkit-light-430-meals.png) | [до](before/webkit-dark-430-meals.png) · [после](after/webkit-dark-430-meals.png) |
| 1280 | [до](before/chromium-light-1280-meals.png) · [после](after/chromium-light-1280-meals.png) | [до](before/chromium-dark-1280-meals.png) · [после](after/chromium-dark-1280-meals.png) | [до](before/webkit-light-1280-meals.png) · [после](after/webkit-light-1280-meals.png) | [до](before/webkit-dark-1280-meals.png) · [после](after/webkit-dark-1280-meals.png) |

## Состояния и нижняя панель

| Состояние | Chromium Light | Chromium Dark | WebKit Light | WebKit Dark |
|---|---|---|---|---|
| Окно 393 × 844, включая dock | [открыть](after/chromium-light-393-viewport.png) | [открыть](after/chromium-dark-393-viewport.png) | [открыть](after/webkit-light-393-viewport.png) | [открыть](after/webkit-dark-393-viewport.png) |
| Добавлена запись | [открыть](after/chromium-light-393-added.png) | [открыть](after/chromium-dark-393-added.png) | [открыть](after/webkit-light-393-added.png) | [открыть](after/webkit-dark-393-added.png) |
| Изменено количество | [открыть](after/chromium-light-393-edited.png) | [открыть](after/chromium-dark-393-edited.png) | [открыть](after/webkit-light-393-edited.png) | [открыть](after/webkit-dark-393-edited.png) |
| Запись удалена: пустой приём | [открыть](after/chromium-light-393-deleted.png) | [открыть](after/chromium-dark-393-deleted.png) | [открыть](after/webkit-light-393-deleted.png) | [открыть](after/webkit-dark-393-deleted.png) |
| Длинные значения и текст 200% | [открыть](after/chromium-light-320-text-200.png) | [открыть](after/chromium-dark-320-text-200.png) | [открыть](after/webkit-light-320-text-200.png) | [открыть](after/webkit-dark-320-text-200.png) |

Текст 200% смоделирован увеличением размеров текста заголовка и сводки через CSS. Это не проверка настоящего масштабирования браузера. Геометрические проверки охватывают горизонтальное переполнение, выравнивание кнопок, размер кнопок и расположение карточки над dock в показанном положении прокрутки. Раскрытие и сворачивание проверены клавиатурой.

Снимки и проверки используют локальный Vite preview и ответы тестовой фикстуры, а не production API. Физические iPhone/Android, реальный Telegram/PWA, системная клавиатура и screen reader: NOT_VERIFIED. Принятие макета #1440 не является визуальной приёмкой реализации.
