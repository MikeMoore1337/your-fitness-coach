# #974 / #869 — новый кандидат контраста индикатора гидратации

## Область изменения

Только текст внутри существующего круга гидратации: белый/почти белый цвет,
тонкая тёмная обводка и минимальный directional fallback для Chromium/WebKit.
Размер 72 px, форма, граница, заливка, расчёты, API, БД и бизнес-логика не менялись.
Старые материалы `evidence/869-contrast-20261013/` сохранены и не переписаны.

## Реальные AFTER

Снимки сделаны Playwright на synthetic fixture при DPR 2. Проверены 0%, 25%, 50%,
75%, 100% и 103%; 103% подтверждает отображение значения выше цели при заполнении
круга до 100%.

| Движок | Тема | 0% | 25% | 50% | 75% | 100% | 103% |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Chromium | Dark | [PNG](after/chromium-dark-0.png) | [PNG](after/chromium-dark-25.png) | [PNG](after/chromium-dark-50.png) | [PNG](after/chromium-dark-75.png) | [PNG](after/chromium-dark-100.png) | [PNG](after/chromium-dark-103.png) |
| Chromium | Light | [PNG](after/chromium-light-0.png) | [PNG](after/chromium-light-25.png) | [PNG](after/chromium-light-50.png) | [PNG](after/chromium-light-75.png) | [PNG](after/chromium-light-100.png) | [PNG](after/chromium-light-103.png) |
| WebKit | Dark | [PNG](after/webkit-dark-0.png) | [PNG](after/webkit-dark-25.png) | [PNG](after/webkit-dark-50.png) | [PNG](after/webkit-dark-75.png) | [PNG](after/webkit-dark-100.png) | [PNG](after/webkit-dark-103.png) |
| WebKit | Light | [PNG](after/webkit-light-0.png) | [PNG](after/webkit-light-25.png) | [PNG](after/webkit-light-50.png) | [PNG](after/webkit-light-75.png) | [PNG](after/webkit-light-100.png) | [PNG](after/webkit-light-103.png) |

## Автоматические проверки

- 24/24 Playwright checks passed: Chromium + WebKit, обе темы, шесть состояний;
- фактический raster содержит светлые пиксели текста;
- bounding box текста остаётся внутри круга;
- значение 103% сохраняется, а заливка ограничивается 100%;
- visual goldens не обновлялись.

## Границы приёмки

- Это новый owner-review candidate после отклонения почти чёрного текста в PR #974.
- Требуется явное owner visual acceptance по этим AFTER до обновления goldens.
- Merge, auto-merge и production deploy запрещены до отдельного разрешения владельца.
- Физический iPhone/Safari, настоящий Telegram и VoiceOver не подтверждены.
