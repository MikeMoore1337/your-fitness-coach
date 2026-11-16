# Issue #951: AFTER выбранного варианта A

Снимки сделаны в собранном интерфейсе YFC в Playwright с синтетическими продуктами и подменёнными ответами API. Это не данные пользователя и не production. Chromium 151.0.7922.34 и WebKit 26.5 запущены на Windows; размеры ниже — CSS-пиксели. На снимках редактирования выбраны два одноимённых продукта разных брендов. Клетчатка неизвестна и отображается прочерком.

Исходный [утверждённый макет A](../README.md) и фактическая реализация показываются раздельно. Выбор макета разрешил реализацию; приёмка этих AFTER-снимков и разрешение на выпуск остаются отдельными решениями владельца.

## Выбор и редактирование

В каждой ячейке: выбор / раскрытая подборка.

| Экран | Chromium Light | Chromium Dark | WebKit Light | WebKit Dark |
| --- | --- | --- | --- | --- |
| 320×720 | [выбор](chromium-320x720-light-selected.png) / [правка](chromium-320x720-light-editing.png) | [выбор](chromium-320x720-dark-selected.png) / [правка](chromium-320x720-dark-editing.png) | [выбор](webkit-320x720-light-selected.png) / [правка](webkit-320x720-light-editing.png) | [выбор](webkit-320x720-dark-selected.png) / [правка](webkit-320x720-dark-editing.png) |
| 360×800 | [выбор](chromium-360x800-light-selected.png) / [правка](chromium-360x800-light-editing.png) | [выбор](chromium-360x800-dark-selected.png) / [правка](chromium-360x800-dark-editing.png) | [выбор](webkit-360x800-light-selected.png) / [правка](webkit-360x800-light-editing.png) | [выбор](webkit-360x800-dark-selected.png) / [правка](webkit-360x800-dark-editing.png) |
| 390×844 | [выбор](chromium-390x844-light-selected.png) / [правка](chromium-390x844-light-editing.png) | [выбор](chromium-390x844-dark-selected.png) / [правка](chromium-390x844-dark-editing.png) | [выбор](webkit-390x844-light-selected.png) / [правка](webkit-390x844-light-editing.png) | [выбор](webkit-390x844-dark-selected.png) / [правка](webkit-390x844-dark-editing.png) |
| 430×932 | [выбор](chromium-430x932-light-selected.png) / [правка](chromium-430x932-light-editing.png) | [выбор](chromium-430x932-dark-selected.png) / [правка](chromium-430x932-dark-editing.png) | [выбор](webkit-430x932-light-selected.png) / [правка](webkit-430x932-light-editing.png) | [выбор](webkit-430x932-dark-selected.png) / [правка](webkit-430x932-dark-editing.png) |
| 1280×900 | [выбор](chromium-1280x900-light-selected.png) / [правка](chromium-1280x900-light-editing.png) | [выбор](chromium-1280x900-dark-selected.png) / [правка](chromium-1280x900-dark-editing.png) | [выбор](webkit-1280x900-light-selected.png) / [правка](webkit-1280x900-light-editing.png) | [выбор](webkit-1280x900-dark-selected.png) / [правка](webkit-1280x900-dark-editing.png) |

## Состояния и восстановление

Все снимки в таблице — 390×844. Ошибки ответа и сети заданы тестовым маршрутом; ошибочная запись в дневник не создаётся.

| Движок и тема | Пусто | Загрузка | Поиск недоступен | Одиночный продукт | Ошибка расчёта | Неверное количество | Сбой подтверждения |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Chromium Light | [открыть](chromium-390x844-light-empty.png) | [открыть](chromium-390x844-light-loading.png) | [открыть](chromium-390x844-light-search-error.png) | [открыть](chromium-390x844-light-single.png) | [открыть](chromium-390x844-light-preview-error.png) | [открыть](chromium-390x844-light-invalid.png) | [открыть](chromium-390x844-light-network-error.png) |
| Chromium Dark | [открыть](chromium-390x844-dark-empty.png) | [открыть](chromium-390x844-dark-loading.png) | [открыть](chromium-390x844-dark-search-error.png) | [открыть](chromium-390x844-dark-single.png) | [открыть](chromium-390x844-dark-preview-error.png) | [открыть](chromium-390x844-dark-invalid.png) | [открыть](chromium-390x844-dark-network-error.png) |
| WebKit Light | [открыть](webkit-390x844-light-empty.png) | [открыть](webkit-390x844-light-loading.png) | [открыть](webkit-390x844-light-search-error.png) | [открыть](webkit-390x844-light-single.png) | [открыть](webkit-390x844-light-preview-error.png) | [открыть](webkit-390x844-light-invalid.png) | [открыть](webkit-390x844-light-network-error.png) |
| WebKit Dark | [открыть](webkit-390x844-dark-empty.png) | [открыть](webkit-390x844-dark-loading.png) | [открыть](webkit-390x844-dark-search-error.png) | [открыть](webkit-390x844-dark-single.png) | [открыть](webkit-390x844-dark-preview-error.png) | [открыть](webkit-390x844-dark-invalid.png) | [открыть](webkit-390x844-dark-network-error.png) |

Длинные названия и способы приготовления, 393×844: [Chromium Light](chromium-393x844-light-long-names.png), [Chromium Dark](chromium-393x844-dark-long-names.png), [WebKit Light](webkit-393x844-light-long-names.png), [WebKit Dark](webkit-393x844-dark-long-names.png).

Открытая клавиатура при моделировании Telegram Mini App, уменьшенный viewport 390×420: [Chromium Light](tma-chromium-390x420-light-keyboard.png), [Chromium Dark](tma-chromium-390x420-dark-keyboard.png), [WebKit Light](tma-webkit-390x420-light-keyboard.png), [WebKit Dark](tma-webkit-390x420-dark-keyboard.png). Это эмуляция safe-area и viewport, а не проверка на физическом телефоне или в настоящем клиенте Telegram.

Проверены отсутствие горизонтального переполнения в основной матрице, управление выбором с клавиатуры, возвращение фокуса после Escape, `aria-pressed`, reduced motion и контраст текста выбранной кнопки на её вычисленном фоне. Полная проверка screen reader, zoom и физические iOS/Android/TMA остаются непроверенными.
