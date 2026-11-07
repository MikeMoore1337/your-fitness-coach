# #1433: компактные рекомендации питания

Снимки сделаны в работающем приложении с вымышленными продуктами и контролируемыми ответами API. Исходная сборка BEFORE — `0a4d243de88ff62cea71fdb3768269c746a456db`; перед PR ветка обновлена до `06d09b06ba7164b096d3f7afec5a8f466ee96d8e`, где изменились только Windows updater и его тест. AFTER — реализация в том же коммите, что этот пакет. Сравнивается одна фикстура из шести вариантов с неполными БЖУ и известным остатком белка.

На 393 × 844 CSS px высота блока в Chromium уменьшилась с 1860,69 до 621,34 px, в WebKit — с 1860,64 до 621,19 px. В обеих темах исходно видны шесть действий «Проверить вариант», после изменения — два и кнопка раскрытия. Проверка одного из первых двух вариантов по-прежнему начинается с одного нажатия; для остальных сначала требуется раскрыть список. Это измерение высоты и действий, не времени или производительности. Исходные числа для каждого снимка сохранены рядом в JSON.

## Свернуто: BEFORE / AFTER

Mobile: высота окна 844 px; desktop: 1280 × 900 px. Снимок охватывает блок рекомендаций; фиксированный dock на длинных снимках остаётся в положении браузера.

| Ширина | Chromium Dark | Chromium Light | WebKit Dark | WebKit Light |
| --- | --- | --- | --- | --- |
| 320 | [до](before/chromium-dark-320.png) / [после](after/chromium-dark-320.png) | [до](before/chromium-light-320.png) / [после](after/chromium-light-320.png) | [до](before/webkit-dark-320.png) / [после](after/webkit-dark-320.png) | [до](before/webkit-light-320.png) / [после](after/webkit-light-320.png) |
| 360 | [до](before/chromium-dark-360.png) / [после](after/chromium-dark-360.png) | [до](before/chromium-light-360.png) / [после](after/chromium-light-360.png) | [до](before/webkit-dark-360.png) / [после](after/webkit-dark-360.png) | [до](before/webkit-light-360.png) / [после](after/webkit-light-360.png) |
| 393 | [до](before/chromium-dark-393.png) / [после](after/chromium-dark-393.png) | [до](before/chromium-light-393.png) / [после](after/chromium-light-393.png) | [до](before/webkit-dark-393.png) / [после](after/webkit-dark-393.png) | [до](before/webkit-light-393.png) / [после](after/webkit-light-393.png) |
| 430 | [до](before/chromium-dark-430.png) / [после](after/chromium-dark-430.png) | [до](before/chromium-light-430.png) / [после](after/chromium-light-430.png) | [до](before/webkit-dark-430.png) / [после](after/webkit-dark-430.png) | [до](before/webkit-light-430.png) / [после](after/webkit-light-430.png) |
| 1280 | [до](before/chromium-dark-1280.png) / [после](after/chromium-dark-1280.png) | [до](before/chromium-light-1280.png) / [после](after/chromium-light-1280.png) | [до](before/webkit-dark-1280.png) / [после](after/webkit-dark-1280.png) | [до](before/webkit-light-1280.png) / [после](after/webkit-light-1280.png) |

## Состояния AFTER

| Движок и тема | 393: раскрыто / проверка / пусто / ошибка | 1280: раскрыто / проверка |
| --- | --- | --- |
| Chromium Dark | [раскрыто](after/chromium-dark-393-expanded.png) · [проверка](after/chromium-dark-393-review.png) · [пусто](after/chromium-dark-393-empty.png) · [ошибка](after/chromium-dark-393-error.png) | [раскрыто](after/chromium-dark-1280-expanded.png) · [проверка](after/chromium-dark-1280-review.png) |
| Chromium Light | [раскрыто](after/chromium-light-393-expanded.png) · [проверка](after/chromium-light-393-review.png) · [пусто](after/chromium-light-393-empty.png) · [ошибка](after/chromium-light-393-error.png) | [раскрыто](after/chromium-light-1280-expanded.png) · [проверка](after/chromium-light-1280-review.png) |
| WebKit Dark | [раскрыто](after/webkit-dark-393-expanded.png) · [проверка](after/webkit-dark-393-review.png) · [пусто](after/webkit-dark-393-empty.png) · [ошибка](after/webkit-dark-393-error.png) | [раскрыто](after/webkit-dark-1280-expanded.png) · [проверка](after/webkit-dark-1280-review.png) |
| WebKit Light | [раскрыто](after/webkit-light-393-expanded.png) · [проверка](after/webkit-light-393-review.png) · [пусто](after/webkit-light-393-empty.png) · [ошибка](after/webkit-light-393-error.png) | [раскрыто](after/webkit-light-1280-expanded.png) · [проверка](after/webkit-light-1280-review.png) |

## Увеличенный текст и ограничения

В отдельной проверке размер корневого шрифта установлен на 200% при ширине 320 px; это CSS-модель увеличения текста, а не проверка системного или браузерного zoom. Длинное вымышленное имя без пробелов переносится, раскрытие дополнительных оснований доступно с клавиатуры. AFTER: [Chromium Dark](after/chromium-dark-320-text-200.png), [Chromium Light](after/chromium-light-320-text-200.png), [WebKit Dark](after/webkit-dark-320-text-200.png), [WebKit Light](after/webkit-light-320-text-200.png).

На исходной базе соседний блок статуса дня растягивал общую сетку: область рекомендаций была около 399 px при доступных 296 px и обрезалась ([Chromium BEFORE](before/chromium-light-320-text-200.png), [WebKit BEFORE](before/webkit-light-320-text-200.png)). Временное скрытие соседнего блока в диагностике уменьшало ширину до 296 px в обоих движках. Локальный CSS ограничивает ширину рекомендаций с учётом safe-area, но не исправляет соседний блок или dock: вся страница при 200% **не подтверждена**. Не проверены физические устройства, настоящий Telegram/PWA, системная клавиатура и screen reader.

Нужна отдельная фактическая визуальная приёмка владельца: принять или указать изменения для всего комплекта AFTER. Принятие макета #1440 не является приёмкой реализации и не разрешает merge или выпуск.
