# #874 — отчёт, PDF и числовая согласованность

Проверки используют один фиксированный synthetic набор данных из
[`tests/fixtures/progress-report-canonical.json`](../../../../../tests/fixtures/progress-report-canonical.json).
Это не production или real-user proof.

## Интегрированный срез и owner-gate

Контрольный HEAD до интеграции: `98a54cf2d55bb86b2fd33669bfba93b9edee08e6`.
Утверждённый owner visual package из `.artifacts/tasks/874-visual-proposal-20261012/`
интегрирован в PR #963 commit `f4ed57e304cace5bd6d113e4a773d3fc7542a142`.
Owner final visual approval: [comment 6128639269](https://github.com/MikeMoore1337/your-fitness-coach/issues/874#issuecomment-6128639269).

Интегрированы только согласованные изменения: единый блок полноты данных, factual summary,
one-record и empty circumference states, цветные графики тела/сна/настроения, естественная
pagination, cohesive «Сон и настроение», readable color/grayscale A4. Бизнес-формулы,
API-контракты и данные не менялись.

В текущем техническом candidate weekly private notes дополнительно исключены из report API,
browser report и server PDF. Явный `client_comment` остаётся отдельным необязательным полем
handoff; `check_ins[].note` не передаётся и автоматически не подставляется.

Прежняя frontend canonical fixture начиналась с `full`-состояния и переопределяла только
часть полей. Поэтому в одном отчёте одновременно оставались несовместимые значения
summary, adherence и data sufficiency. Теперь fixture строится с нуля из одного набора фактов:

- custom period `2026-07-26…2026-08-24`, `Europe/Moscow`, две запланированные тренировки,
  одна завершённая, одна пропущенная, один рабочий подход, объём `400 кг` и один фактический
  личный рекорд по существующему серверному правилу;
- один полный день питания из 30, `2100/155/68/230`, цели `2200/160/70/240`, 29 пропущенных
  дней; исторический период не содержит текущего календарного дня, поэтому
  `current_day_status=null`;
- две точки веса и окружности (`80→79 кг`, `90→89 см`) с фактическими датами и статусом
  `insufficient_points`; adherence и все counters data sufficiency выведены из тех же фактов.

Добавлены `assertCanonicalProgressReportInvariants` и негативный тест, который падает при
изменении derived coverage без изменения первичных фактов. Backend parity-тест дополнительно
сверяет серверные значения, а не только наличие PDF.

## Воспроизводимые результаты интеграционного среза

- frontend `typecheck`, `lint` с Russian UI guard и `build`: зелёные;
- изменённые frontend-файлы прошли Prettier check;
- полный Vitest: `838 passed`;
- backend report/public-share/wellbeing regression: `28 passed`;
- targeted backend report tests: `21 passed`;
- Ruff для `backend bot tests scripts`: зелёный;
- Playwright progress-report Chromium + WebKit: `16/16 passed`;
- browser PDF: full `5`, canonical/one-record `4`, partial `5`, empty `3`, grayscale control
  `5` страниц; числа страниц наблюдаемы и не зафиксированы в тестах жёстко;
- A4 metadata, rendered PNG, color, grayscale, no orphan headings, no empty pages и private
  note exclusion проверены локально.

`D:/Pet-projects/your-fitness-coach/.venv` full Windows pytest завершился `2308 passed,
21 skipped, 10 failed`. Эти отказы относятся к Windows-only symlink/`os.chown` ограничениям,
line-ending/hash baseline и production-host tests вне изменённого отчёта; authoritative
backend result должен быть подтверждён Linux required CI. Это не объявляется зелёным локальным
полным backend прогоном.

Targeted mypy обнаружил четыре существующие ошибки в `backend/fitminiapp_api/services/progress.py`
(строки 986–988, unrelated `CardioSession`/`BodyMeasurement` typing); ошибок в затронутых
файлах отчёта нет. Full repository format check также содержит baseline-несоответствия вне
diff; массовое форматирование не выполнялось.

## Исправление QA-пробела

QA-комментарий [6120877469](https://github.com/MikeMoore1337/your-fitness-coach/issues/874#issuecomment-6120877469)
зафиксировал, что прежние API/UI/browser/server проверки использовали разные fixtures, а
browser PDF проверял только `%PDF` и размер. В PR #963 добавлена одна воспроизводимая
сквозная проверка:

- API и server PDF получают один custom-период `2026-07-26…2026-08-24`, профильный timezone
  `Europe/Moscow`, одинаковые тренировки, кардио, питание и замеры.
- UI и browser print PDF используют тот же JSON fixture; browser PDF проходит фактическое
  извлечение текста через `scripts/extract_pdf_text.py`, а не только проверку заголовка файла.
- Сверяются имя, период, значения, периоды и единицы замеров, даты последних значений,
  агрегаты и границы приватности (`user_id`, `telegram_user_id`, свободный текст дневника).
- Отдельно проверены пустой отчёт и one-record сценарий; формулы и production PDF layout не
  изменялись.

Канонические gates:

- `backend/tests/test_progress_reports.py::test_progress_report_api_and_server_pdf_share_one_canonical_fact_set`;
- `backend/tests/test_progress_reports.py::test_progress_report_empty_pdf_has_no_fabricated_facts`;
- `backend/tests/test_progress_reports.py::test_progress_report_pdf_matches_api_metrics_without_exposing_notes_for_single_record`;
- `frontend/tests/e2e/progress-report.spec.ts` — `browser print PDF contains the canonical facts and privacy boundaries`.

Новые PDF генерируются самим тестом из этого fixture и сохраняются как CI artifacts при
`YFC_PROGRESS_REPORT_*_PDF_EVIDENCE_DIR`. Исторические PDF ниже оставлены для визуального
сравнения layout и не являются заменой канонической parity-проверки.

## Проверенная цепочка

- API: один inclusive timezone-aware диапазон для `days_7`, `days_30`, `days_90`,
  `current_month` и `custom`; проверены даты, `Europe/Moscow`, калории, Б/Ж/У,
  тренировки, подходы, объём, кардио, замеры, цели и data sufficiency.
- UI: Vitest проверяет те же canonical facts, поддерживаемые периоды и различие
  `null` («Нет данных») от числового нуля.
- Серверный PDF: pytest проверяет фактический `%PDF`, отображение чисел и единиц,
  отсутствие controls, diary free text и weekly private notes. Явный `client_comment`
  остаётся отдельным handoff-полем и не подставляется автоматически.
- Browser print PDF: Playwright Chromium/WebKit проверяет mobile/desktop print
  layout, dark/light preview, отсутствие горизонтального overflow и скрытие экранных
  controls в print media. Chromium создаёт PDF; Poppler подтвердил A4 и страницы; observed
  page counts не являются hard-coded gate.
- Public share: явный preview → create flow, immutable snapshot, no automatic
  public exposure, `no-store`/`noindex`, revoke и отсутствие private keys,
  nutrition/body в public snapshot.

## Реальные PDF

| Артефакт | PDF | Rendered pages |
| --- | --- | --- |
| Серверный PDF, custom/days-30 fixture | [PDF](server/server-progress-report-days-30.pdf) | [1](server/server-progress-report-days-30-1.png), [2](server/server-progress-report-days-30-2.png) |
| Browser print PDF, Chromium | [PDF](browser/browser-progress-report.pdf) | [1](browser/browser-progress-report-1.png), [2](browser/browser-progress-report-2.png), [3](browser/browser-progress-report-3.png), [4](browser/browser-progress-report-4.png), [5](browser/browser-progress-report-5.png) |

Актуальные ignored local AFTER/PDF находятся в `.artifacts/tasks/874-visual-proposal-20261012/`:
`browser-pdf/final/` содержит screenshots, full/canonical/partial/empty/grayscale browser PDF,
а `server-final/` — свежий server PDF и rendered pages. Synthetic evidence не публикуется как
production proof.

## Observed metadata

- Серверный PDF: A4, 2 страницы, ReportLab runtime.
- Browser PDF: A4; full 5, canonical 4, partial 5, empty 3, grayscale control 5 страниц;
  Chromium/Skia PDF. Это наблюдение, а не жёсткий тестовый threshold.
- В серверный PDF добавлена единица `мин` для значения «Минуты кардио»; формулы
  и canonical calculations не менялись.
- Screen-only controls («Показать период», «Скачать PDF», «Состав и отправка
  отчёта») в generated server PDF и browser print pages не присутствуют.

## Reproducible checks

- `backend/tests/test_progress_reports.py`: `21 passed`;
- report/public-share/wellbeing regression: `28 passed`;
- `frontend/tests/unit/pages/ProgressReportPage.test.tsx` and `DataConfidence`: `18 passed`;
- `frontend/tests/e2e/progress-report.spec.ts`: `16 passed` total — Chromium `8`, WebKit `8`;
- `npm run typecheck`, `npm run lint`, Russian UI guard, targeted Prettier and `npm run build`:
  passed;
- server PDF and browser PDF parity/privacy checks: passed on the canonical fixture.

Integration source commit: `f4ed57e304cace5bd6d113e4a773d3fc7542a142`.
Final exact HEAD и required Checks публикуются в PR #963 после завершения CI.
