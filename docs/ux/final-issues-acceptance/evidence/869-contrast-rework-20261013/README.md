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

| Движок   | Тема  | 0%                                | 25%                                | 50%                                | 75%                                | 100%                                | 103%                                |
| -------- | ----- | --------------------------------- | ---------------------------------- | ---------------------------------- | ---------------------------------- | ----------------------------------- | ----------------------------------- |
| Chromium | Dark  | [PNG](after/chromium-dark-0.png)  | [PNG](after/chromium-dark-25.png)  | [PNG](after/chromium-dark-50.png)  | [PNG](after/chromium-dark-75.png)  | [PNG](after/chromium-dark-100.png)  | [PNG](after/chromium-dark-103.png)  |
| Chromium | Light | [PNG](after/chromium-light-0.png) | [PNG](after/chromium-light-25.png) | [PNG](after/chromium-light-50.png) | [PNG](after/chromium-light-75.png) | [PNG](after/chromium-light-100.png) | [PNG](after/chromium-light-103.png) |
| WebKit   | Dark  | [PNG](after/webkit-dark-0.png)    | [PNG](after/webkit-dark-25.png)    | [PNG](after/webkit-dark-50.png)    | [PNG](after/webkit-dark-75.png)    | [PNG](after/webkit-dark-100.png)    | [PNG](after/webkit-dark-103.png)    |
| WebKit   | Light | [PNG](after/webkit-light-0.png)   | [PNG](after/webkit-light-25.png)   | [PNG](after/webkit-light-50.png)   | [PNG](after/webkit-light-75.png)   | [PNG](after/webkit-light-100.png)   | [PNG](after/webkit-light-103.png)   |

### H₂O при выключенной цели

Это отдельная goal-disabled fixture: `goal.enabled=false`, `goal.target_ml=null` и
`progress_percent=null`. Поэтому UI показывает `H₂O`, а не процент. В каждой проверке
подтверждены заполненный дневник (`850 мл записано`), отсутствие цели, читаемость текста
и нахождение текста внутри существующего круга.

| Движок   | Тема  | AFTER                                        |
| -------- | ----- | -------------------------------------------- |
| Chromium | Dark  | [PNG](after/chromium-dark-h2o-disabled.png)  |
| Chromium | Light | [PNG](after/chromium-light-h2o-disabled.png) |
| WebKit   | Dark  | [PNG](after/webkit-dark-h2o-disabled.png)    |
| WebKit   | Light | [PNG](after/webkit-light-h2o-disabled.png)   |

## Автоматические проверки

- 28/28 Playwright checks passed: 24 процентных состояния Chromium + WebKit, обе темы,
  шесть уровней заполнения, и 4 отдельных H₂O goal-disabled состояния;
- фактический raster содержит светлые пиксели текста;
- bounding box текста остаётся внутри круга;
- значение 103% сохраняется, а заливка ограничивается 100%;
- пороги visual-тестов не менялись.

## Точечное обновление stale goldens

CI run [38367622656](https://github.com/MikeMoore1337/your-fitness-coach/actions/runs/38367622656)
показал устаревший только для утверждённого контраста `nutrition-390x844-light.png`:

- Chromium: 175 стабильных пикселей по отчёту Playwright, ratio 0.01;
- WebKit: 166 стабильных пикселей по отчёту Playwright, ratio 0.01.

После owner-approved near-white текста с тонкой тёмной обводкой заменены только два
Linux snapshot path из этого failure:

- `frontend/tests/e2e/mobile-ui-regression.spec.ts-snapshots/mobile-chromium/linux/nutrition-390x844-light.png`;
- `frontend/tests/e2e/mobile-ui-regression.spec.ts-snapshots/mobile-webkit/linux/nutrition-390x844-light.png`.

Независимая проверка RGB с порогом изменения канала `>16` дала 301/288 пикселей и
ограничила diff одним и тем же индикатором: `x=299, y=1747, width=32`, высота 15 px
для Chromium и 14 px для WebKit. Остальные snapshots, пороги и старые материалы не
переписывались. До owner-approved contrast старые goldens не обновлялись; текущая замена
разрешена только для этих двух stale hydration goldens после аппрува.

## Границы приёмки

- Это новый owner-review candidate после отклонения почти чёрного текста в PR #974.
- Owner visual acceptance относится только к near-white `H₂O`/percent тексту с тонкой
  тёмной обводкой; она не является аппрувом компактного дизайна гидратации или других задач.
- Merge, auto-merge и production deploy запрещены до отдельного разрешения владельца.
- Геометрия, заливка, расчёты, API и БД не менялись; `ARCHIVE_VISUAL_PARITY=FAIL` и
  архивные evidence остаются без ослабления.
- Физический iPhone/Safari, настоящий Telegram и VoiceOver не подтверждены.
