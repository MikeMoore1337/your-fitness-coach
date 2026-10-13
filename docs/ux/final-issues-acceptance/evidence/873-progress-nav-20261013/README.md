# #873 — минимальная приёмка навигации Progress

Срез подготовлен на синтетических данных в актуальной ветке от `origin/master`.

- `BASE_SHA`: `11cff463834fd41c1392d646f6baaf361ac9bebc`
- `IMPLEMENTATION_SHA`: `6f49e781c20c6ae516d5cd0d8211940b745d972e`

## Что изменено

- Крайние кнопки горизонтального rail используют одну утверждённую пару glyph: `chevron-left` / `chevron-right`.
- URL, порядок DOM, пять элементов нижней панели, существующий rail, авто-показ активной вкладки, focus и touch-area не изменены.
- API, БД, миграции, данные, формулы и крупная композиция разделов Progress не затронуты.

## Реальное BEFORE / AFTER

Снимки сняты Playwright с synthetic API, без пользовательских данных:

| Движок / тема | BEFORE | AFTER |
| --- | --- | --- |
| Chromium 393, Dark | [до](before/chromium-393-dark.png) | [после](after/chromium-393-dark.png) |
| Chromium 393, Light | — | [после](after/chromium-393-light.png) |
| WebKit 393, Dark | — | [после](after/webkit-393-dark.png) |
| WebKit 393, Light | — | [после](after/webkit-393-light.png) |

До/после отличаются только формой левой краевой стрелки; состояние rail в начальной позиции скрывает отключённую левую кнопку. DOM-проверка дополнительно фиксирует точные glyph names.

## Проверки

- `npm run build` — PASS.
- `npm run typecheck` — PASS.
- `npm run lint:ui-copy` — PASS.
- `approved-mobile-ui.spec.ts`, Chromium, TMA smoke — PASS.
- `approved-mobile-ui.spec.ts`, Chromium + WebKit, 393 px, Dark/Light — 4 PASS.
- Проверены: пять элементов dock, активная вкладка без clipping, keyboard `End`, переходы разделов, отсутствие горизонтального overflow и DOM-пара `chevron-left` / `chevron-right`.

## Границы приёмки

Это техническое исправление существующего approved B-паттерна, а не новый дизайн Progress. Крупная перестройка разделов, перенос «Добавить замер» и иная композиция остаются за owner design approval. Физический iPhone/Safari, нативный Telegram и VoiceOver не проверялись.

`OWNER_VISUAL_ACCEPTANCE=PENDING`
`MERGE=false`
`DEPLOY=false`
