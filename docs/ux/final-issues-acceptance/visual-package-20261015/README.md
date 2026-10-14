# YFC — единый визуальный пакет #979/#978, 15.10.2026

Единый пакет для визуальной проверки после owner feedback по [#979](https://github.com/MikeMoore1337/your-fitness-coach/issues/979) и [#978](https://github.com/MikeMoore1337/your-fitness-coach/issues/978). Основа работы — точный [origin/master `f99f1954c007567cefeec7dc882f14e68de6b0ba`](https://github.com/MikeMoore1337/your-fitness-coach/commit/f99f1954c007567cefeec7dc882f14e68de6b0ba); итоговый exact head опубликован в описании нового Draft PR.

**Merge, auto-merge, production deploy и закрытие Issues не выполнялись.** #978 и #979 остаются открытыми. Кадры сделаны локально на mocked TMA/API с синтетическими данными; production credentials и пользовательские данные не использовались.

## Что проверяется

- **#979 Progress:** локальный selector разделов — общий текстовый `SegmentedControl` с tab semantics, keyboard focus/Home/End и без directional arrow controls. Кадры: [dark](visuals/progress-430-dark.png) · [light](visuals/progress-430-light.png).
- **#978 Daily Wellbeing:** выбранные «Как спалось?» и «Как себя ощущали?» имеют единый lime lower accent в обеих темах; поле сна принимает часы (`7,5`), а API сохраняет минуты (`450`). Кадры: [dark selected](visuals/wellbeing-390-dark-selected.png) · [light selected](visuals/wellbeing-390-light-selected.png) · [dark hours form](visuals/wellbeing-390-dark-hours-form.png) · [dark saved](visuals/wellbeing-390-dark-saved.png).
- **Общая типографика и компоненты:** desktop report в двух темах, каждая полноразмерная capture разбита на три lossless PNG-полосы: [dark top](visuals/report-1440-dark-top.png) · [dark middle](visuals/report-1440-dark-middle.png) · [dark bottom](visuals/report-1440-dark-bottom.png) · [light top](visuals/report-1440-light-top.png) · [light middle](visuals/report-1440-light-middle.png) · [light bottom](visuals/report-1440-light-bottom.png).

## Матрица evidence

| Поверхность       | Браузеры         | Темы        | Viewport                                      | Данные                         |
| ----------------- | ---------------- | ----------- | --------------------------------------------- | ------------------------------ |
| Progress selector | Chromium, WebKit | dark, light | 320/360/393/430 px в targeted E2E; PNG 430 px | mocked progress fixture        |
| Daily Wellbeing   | Chromium, WebKit | dark, light | 390 px в PNG; 360/390/430 px в targeted E2E   | mocked daily API               |
| Progress report   | Chromium         | dark, light | 1440×900                                      | mocked progress report fixture |

Автоматические assertions дополнительно проверяют отсутствие горизонтального overflow, touch-targets, tab keyboard navigation, selected state, offline/exit guards, one-row action buttons, hours-to-minutes save/load/edit и invalid-hours error.

Финальный targeted run: Chromium — **24 passed, 1 skipped** (25 tests, workers=8); WebKit — **24 passed, 1 skipped** (25 tests, workers=1). В первом параллельном WebKit-прогоне два старых `approved-mobile-ui` сценария кратковременно упали; повтор 2/2 и полный serial run прошли. Assertions и timeout не ослаблялись.

## Запуск и исходники

- [HTML gallery](gallery.html)
- [machine-readable manifest](manifest.json)
- [Progress implementation](../../../../frontend/src/features/workouts/ProgressExperience.tsx) и [E2E](../../../../frontend/tests/e2e/approved-mobile-ui.spec.ts)
- [Wellbeing implementation](../../../../frontend/src/features/wellbeing/DailyWellbeingCheckIn.tsx) и [E2E](../../../../frontend/tests/e2e/daily-wellbeing.spec.ts)
- [shared selected-state tokens](../../../../frontend/src/styles/design-v2.css)
- [Progress selector styling](../../../../frontend/src/styles/ux-ia-redesign.css)
- [durable UI contract](../../../design/YFC_PRODUCT_UI_CONTRACT.md), [component states](../../../design/component-states-v2.1.md), [repository rules](../../../../AGENTS.md)

## Статус и границы

Пакет готов к owner visual acceptance и отдельному решению по merge/release. Physical iPhone/Safari, native Telegram runtime, VoiceOver, реальные virtual keyboards, production traffic и реальные пользовательские когорты здесь **NOT_VERIFIED**. Green CI не является разрешением на merge или deploy.
