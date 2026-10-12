# Issue #906 — вариант B, Cinematic Hero

Статус: `IMPLEMENTED_NEEDS_ACCEPTANCE`.

Реализована утверждённая композиция B для `/for-athletes` и `/for-trainers`. На desktop высота Hero ограничена диапазоном `860–980px`: на QHD и ultrawide используется 980px, а на viewport 1440×900 сохраняется высота viewport. Для фотографий задана отдельная фокусировка: спортсмены `65% 27%`, тренеры `68% 27%`. Мобильные правила сохранены.

## Доказательства

Снимки сделаны из локального Vite runtime через Playwright Chromium. `before` снят на базовом SHA `c0316efc48f65e268329ba300734f6ff69d97249`, `after` — после изменения CSS; production build проверен отдельно. Каждый файл лежит в репозитории и будет доступен по SHA PR.

| Артефакт                         | Ссылка                                                          |
| -------------------------------- | --------------------------------------------------------------- |
| Галерея                          | [index.html](./index.html)                                      |
| Сводный manifest                 | [manifest.json](./manifest.json)                                |
| Provenance                       | [provenance.json](./provenance.json)                            |
| Матрица покрытия #906            | [matrix-entry.md](./matrix-entry.md)                            |
| Сравнение спортсменов, QHD, dark | [before-after](./comparison/athletes-qhd-dark-before-after.jpg) |
| Сравнение тренеров, QHD, dark    | [before-after](./comparison/trainers-qhd-dark-before-after.jpg) |

Каталоги `before/` и `after/` содержат парные снимки для обеих аудиторий, dark/light, 1440×900, 1920×1080, 2560×1440, 3440×1440, 2560×1440 с 125% CSS zoom и 320/390/430px.

## Проверки

`frontend/tests/e2e/landing-906.spec.ts` проверяет высоту Hero, границы изображения, положение CTA, горизонтальное переполнение и загрузку изображений во всех двух маршрутах и темах. Целевые прогоны выполняются в Chromium и WebKit. Визуальная приёмка и выпуск остаются за владельцем.
