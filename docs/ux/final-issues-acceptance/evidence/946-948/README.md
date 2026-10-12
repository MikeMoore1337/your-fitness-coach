# #946–#948 — мобильный выбор продуктов

> **Примечание к merge:** оригинальные 48 PNG из PR #941 сохранены в [archive/pr941](archive/pr941/README.md), поскольку в master уже имеются более новые файлы с теми же именами. В after оставлены файлы master. Синтетические снимки не считаются проверкой физического iPhone.


Это один browser-evidence пакет для трёх связанных Issues. Снимки сняты из рабочей сборки PR #958 (`e1c7e906d226265f589669cc85d424e4e8f9e802`) адресным Playwright-тестом `frontend/tests/e2e/nutrition-diary.spec.ts`.

Покрытие: Chromium и WebKit; ширины 320 и 393 CSS px; dark и light; шесть состояний на каждый набор:

1. `search-closed` — поиск с закрытой клавиатурой;
2. `keyboard-open-rice-search` — фокус на запросе «рис» при уменьшенной видимой области;
3. `keyboard-open-rice-results` — результаты «рис» над клавиатурой;
4. `potato-results` — результаты «картофель» с полными калориями и единицами;
5. `pressed` — pressed/favorite interaction до выбора продукта;
6. `selected` — выбранный продукт и сохранённые значения.

## Прямые кадры

| Browser | Размер/тема | Search закрыт | Keyboard/search | Keyboard/results | Картофель | Pressed | Selected |
|---|---|---|---|---|---|---|---|
| Chromium | 320 dark | [open](after/chromium-320-dark-search-closed.png) | [open](after/chromium-320-dark-keyboard-open-rice-search.png) | [open](after/chromium-320-dark-keyboard-open-rice-results.png) | [open](after/chromium-320-dark-potato-results.png) | [open](after/chromium-320-dark-pressed.png) | [open](after/chromium-320-dark-selected.png) |
| Chromium | 320 light | [open](after/chromium-320-light-search-closed.png) | [open](after/chromium-320-light-keyboard-open-rice-search.png) | [open](after/chromium-320-light-keyboard-open-rice-results.png) | [open](after/chromium-320-light-potato-results.png) | [open](after/chromium-320-light-pressed.png) | [open](after/chromium-320-light-selected.png) |
| Chromium | 393 dark | [open](after/chromium-393-dark-search-closed.png) | [open](after/chromium-393-dark-keyboard-open-rice-search.png) | [open](after/chromium-393-dark-keyboard-open-rice-results.png) | [open](after/chromium-393-dark-potato-results.png) | [open](after/chromium-393-dark-pressed.png) | [open](after/chromium-393-dark-selected.png) |
| Chromium | 393 light | [open](after/chromium-393-light-search-closed.png) | [open](after/chromium-393-light-keyboard-open-rice-search.png) | [open](after/chromium-393-light-keyboard-open-rice-results.png) | [open](after/chromium-393-light-potato-results.png) | [open](after/chromium-393-light-pressed.png) | [open](after/chromium-393-light-selected.png) |
| WebKit | 320 dark | [open](after/webkit-320-dark-search-closed.png) | [open](after/webkit-320-dark-keyboard-open-rice-search.png) | [open](after/webkit-320-dark-keyboard-open-rice-results.png) | [open](after/webkit-320-dark-potato-results.png) | [open](after/webkit-320-dark-pressed.png) | [open](after/webkit-320-dark-selected.png) |
| WebKit | 320 light | [open](after/webkit-320-light-search-closed.png) | [open](after/webkit-320-light-keyboard-open-rice-search.png) | [open](after/webkit-320-light-keyboard-open-rice-results.png) | [open](after/webkit-320-light-potato-results.png) | [open](after/webkit-320-light-pressed.png) | [open](after/webkit-320-light-selected.png) |
| WebKit | 393 dark | [open](after/webkit-393-dark-search-closed.png) | [open](after/webkit-393-dark-keyboard-open-rice-search.png) | [open](after/webkit-393-dark-keyboard-open-rice-results.png) | [open](after/webkit-393-dark-potato-results.png) | [open](after/webkit-393-dark-pressed.png) | [open](after/webkit-393-dark-selected.png) |
| WebKit | 393 light | [open](after/webkit-393-light-search-closed.png) | [open](after/webkit-393-light-keyboard-open-rice-search.png) | [open](after/webkit-393-light-keyboard-open-rice-results.png) | [open](after/webkit-393-light-potato-results.png) | [open](after/webkit-393-light-pressed.png) | [open](after/webkit-393-light-selected.png) |

## Что доказано

- visible viewport offsets обновляются через `visualViewport.resize`; обработчик `visualViewport.scroll` не запускает зацикленный `scrollIntoView`;
- модальное окно и результаты остаются в доступной области при контролируемом уменьшении viewport до 420 px;
- длинные кириллические/латинские названия переносятся, вторичные действия переходят на нижнюю строку карточки;
- pressed/selected поверхности читаемы, favorite не выбирает продукт, `aria-pressed` и итоговые значения проверяются;
- данные, основа расчёта и значения КБЖУ не изменялись.

Это эмуляция браузерной геометрии, а не снимок физического iPhone, iOS Safari с системной клавиатурой, Telegram Mini App на устройстве или VoiceOver.
