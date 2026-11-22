# Issue #984: AFTER

Реализация: `8808a0246045806d975b72c7f2d11a3519563d80`; исходный `dev`: `29a72c9dbe0bbf75cb20e721649b80e55e1467ca`. Этот пакет добавлен отдельным коммитом; его точный SHA указан в PR. Разрешение владельца относится только к реализации #984 и Draft PR в `dev`; оно не активирует остальные задачи V14.

## Материалы

В `screens/` находятся реальные снимки приложения с тестовыми API-данными: Progress «Обзор» и «Тело», день питания и окно добавления. Имена содержат движок, тему и ширину viewport: 320, 360, 393 или 430 CSS px, высота 852 px. Full-page снимки прокручиваемых экранов показывают также содержимое ниже первого экрана. Данные синтетические, даты тестов зафиксированы.

В `video/` — записи Chromium и WebKit в светлой и тёмной теме, viewport 393 × 852. Progress: переходы периодов и разделов, browser Back/Forward, затем reduced motion. Nutrition: диалог добавления, настройки и возврат к дневнику, затем reduced motion. Записи сделаны во время браузерного теста и перекодированы локально в VP8; фактическое время анимации оценивается по реализации и тестам, а не по FPS перекодированного видео. Сохранение черновиков и отсутствие записей дополнительно проверены автоматическими тестами.

Пример снимков: [Progress](screens/progress-overview-chromium-light-393.png), [Nutrition](screens/nutrition-day-chromium-light-393.png), [добавление еды](screens/nutrition-picker-chromium-dark-393.png). Пример записи: [Progress](video/progress-chromium-light.webm), [Nutrition](video/nutrition-chromium-light.webm).

Воспроизведение съёмки из `frontend` (PowerShell; каталог должен быть абсолютным):

```powershell
npm ci
npm run build
$env:ISSUE_984_CAPTURE_DIR = 'D:\temp\issue-984-after'
npx playwright test --config=playwright.cross-browser.config.ts --project=chromium --project=webkit --workers=1 tests/e2e/progress-experience.spec.ts tests/e2e/nutrition-diary.spec.ts --grep 'issue 984 AFTER'
```

## Проверки

- PASS: `npm run build` (включает TypeScript), `npm run lint`, Prettier для изменённых файлов; применимые pre-commit hooks.
- PASS: `npx vitest run --maxWorkers=4` — 192 файла, 1524 теста. Для Windows `TEMP` и `TMP` были направлены в отдельный локальный каталог без `#` в имени.
- PASS: целевой прогон Chromium/WebKit — 19 passed, 1 skipped, включая четыре теста съёмки (CDP touch поддерживается только Chromium). Он включает локальные жесты, переход Progress ↔ Nutrition, черновики, период и историю, mocked Telegram BackButton, reduced motion и forced colors.
- PASS: Chromium 200% zoom проверен на зафиксированной версии для Progress и Nutrition в обеих темах и ширинах 320/360/393/430/1280; браузерная эмуляция не является проверкой физического устройства. Отдельно выполнялись связанные сценарии WeekStrip/Quick Add и mocked TMA.
- FAIL: общий `npm run format:check` в Windows checkout обнаруживает расхождения в сотнях неизменённых файлов; проверка изменённых файлов проходит. Это не изменение baseline и не ослабление CI.
- NOT_VERIFIED: физический iPhone, настоящий Safari и Telegram WebView; production и приёмка владельца. Результат GitHub CI и точный head следует смотреть в PR.

## Производительность

Одинаковый локальный синтетический Chromium-прогон: viewport 393 × 852, Light, 12 переключений периода, `requestAnimationFrame` и `PerformanceObserver` longtask. Сырые выборки: [BEFORE](metrics/before.json), [AFTER](metrics/after.json). Это короткие отдельные запуски, не полевые данные и не доказательство ускорения.

| Показатель | BEFORE | AFTER |
|---|---:|---:|
| Кадров в выборке | 59 | 59 |
| p50 / p95 / p99, мс | 16,7 / 16,8 / 16,8 | 16,7 / 16,8 / 16,8 |
| Long tasks | 0 | 0 |
| Сумма JS/CSS, байт | 3 826 469 | 3 833 872 |
| Сумма gzip JS/CSS, байт | 964 221 | 966 804 |

Размеры рассчитаны для всех 108 файлов `.js`/`.css` в `frontend/dist`, gzip level 9, `mtime=0`, из сборок соответствующих ревизий. Для повторения замера кадров скопируйте к базовой версии `tests/e2e/progress-experience.spec.ts` содержимое [frame-sample-append.txt](metrics/frame-sample-append.txt) в отдельный временный файл в `tests/e2e`, установите абсолютные `ISSUE984_SCREEN` и `ISSUE984_METRICS`, затем запустите `npx playwright test <временный файл> --grep 'issue 984 controlled frame sample' --workers=1` для каждой сборки. Для сопоставимости используйте fixture из исходного SHA для обеих сборок и удалите временный файл после запуска.
