# #1435: сводка КБЖУ

Материалы проверки #1435. Исходная версия: `d09ae132d`; данные синтетические. Снимки показывают сам блок при 320, 360, 393, 430 × 844 и 1280 × 900 CSS px в Chromium и WebKit, Light и Dark. Имена файлов содержат браузер, тему и ширину.

## До и после · 100%

В ячейке: до / после. Mobile — окно высотой 844 px; desktop — 1280 × 900 px.

| Ширина | Chromium Light                                                                | Chromium Dark                                                               | WebKit Light                                                              | WebKit Dark                                                             |
| ------ | ----------------------------------------------------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| 320    | [до](before/chromium-light-320.png) / [после](after/chromium-light-320.png)   | [до](before/chromium-dark-320.png) / [после](after/chromium-dark-320.png)   | [до](before/webkit-light-320.png) / [после](after/webkit-light-320.png)   | [до](before/webkit-dark-320.png) / [после](after/webkit-dark-320.png)   |
| 360    | [до](before/chromium-light-360.png) / [после](after/chromium-light-360.png)   | [до](before/chromium-dark-360.png) / [после](after/chromium-dark-360.png)   | [до](before/webkit-light-360.png) / [после](after/webkit-light-360.png)   | [до](before/webkit-dark-360.png) / [после](after/webkit-dark-360.png)   |
| 393    | [до](before/chromium-light-393.png) / [после](after/chromium-light-393.png)   | [до](before/chromium-dark-393.png) / [после](after/chromium-dark-393.png)   | [до](before/webkit-light-393.png) / [после](after/webkit-light-393.png)   | [до](before/webkit-dark-393.png) / [после](after/webkit-dark-393.png)   |
| 430    | [до](before/chromium-light-430.png) / [после](after/chromium-light-430.png)   | [до](before/chromium-dark-430.png) / [после](after/chromium-dark-430.png)   | [до](before/webkit-light-430.png) / [после](after/webkit-light-430.png)   | [до](before/webkit-dark-430.png) / [после](after/webkit-dark-430.png)   |
| 1280   | [до](before/chromium-light-1280.png) / [после](after/chromium-light-1280.png) | [до](before/chromium-dark-1280.png) / [после](after/chromium-dark-1280.png) | [до](before/webkit-light-1280.png) / [после](after/webkit-light-1280.png) | [до](before/webkit-dark-1280.png) / [после](after/webkit-dark-1280.png) |

## Состояния

[Частичные данные без цели](states/) сняты на всех ширинах. Нулевой день, неизвестный нутриент и превышение сняты на 393 и 1280 px в обеих темах и браузерах; имена файлов содержат браузер, тему, ширину и состояние (`zero`, `unknown`, `excess`).

## Реальный zoom Chromium · 200%

В каждой папке — Dark/Light и все пять размеров окна. Суффиксы `top`, `middle`, `bottom` показывают последовательные положения прокрутки; сами изображения сняты с окружением и dock.

- [До: все кадры](zoom-200-before/) · [после: все кадры](zoom-200/).
- 320 Light: [до](zoom-200-before/chromium-light-320-top.png) · после: [верх](zoom-200/chromium-light-320-top.png), [середина](zoom-200/chromium-light-320-middle.png), [низ](zoom-200/chromium-light-320-bottom.png).
- 393 Dark: [до](zoom-200-before/chromium-dark-393-top.png) · после: [верх](zoom-200/chromium-dark-393-top.png), [середина](zoom-200/chromium-dark-393-middle.png), [низ](zoom-200/chromium-dark-393-bottom.png).
- 1280: [Light](zoom-200/chromium-light-1280-top.png) · [Dark](zoom-200/chromium-dark-1280-top.png).

Высота всего блока, CSS px: Chromium — 320: 510,03 → 507,03; 360: 510,03 → 450,03; 393: 510,03 → 450,03; 430: 510,03 → 434,92; 1280: 454,03 → 363,81. WebKit — 320: 509,97 → 506,97; 360: 509,97 → 449,97; 393: 509,97 → 449,97; 430: 509,97 → 434,88; 1280: 453,97 → 363,78. Измерения выполнены после загрузки шрифтов.

При прокрутке в начало страницы тест считал кнопки «Добавить продукт», «Быстрый ввод», «Добавить воду», «Настройки КБЖУ» и «Изменить на эту дату», геометрически целиком находящиеся в окне: 3 → 3 на мобильных ширинах и 5 → 5 на desktop. Этот подсчёт не проверяет перекрытие элементов другими слоями.

На 320 px используется одна колонка, на остальных проверенных ширинах — две. Настоящий zoom Chromium задан через `chrome.tabs.setZoom(2)` во временном изолированном профиле и подтверждён `getZoom()`, DPR и шириной viewport: на 320/360/393/430/1280 физических px получены 160/180/196/215/640 CSS px. После исправления текст сводки помещается внутри карточки во всех проверенных сочетаниях. На исходном dev при 320 и 360 px часть текста выходила за карточку.

**Оставшееся ограничение:** при 200% и узких окнах подписи глобального dock обрезаны и часть содержимого перекрыта. То же видно на исходном dev; навигация не входит в #1435. Zoom WebKit, физические устройства, реальный Telegram и PWA не проверены. Решение владельца по реализации и разрешение на merge отсутствуют.
