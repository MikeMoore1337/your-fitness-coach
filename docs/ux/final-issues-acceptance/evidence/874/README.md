# #874 — отчёт, PDF и числовая согласованность

Проверки используют один фиксированный synthetic набор данных из
[`tests/fixtures/progress-report-canonical.json`](../../../../tests/fixtures/progress-report-canonical.json).
Это не production или real-user proof.

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
  отсутствие controls и diary free text. Разрешённая заметка weekly check-in
  сохраняется по текущему контракту.
- Browser print PDF: Playwright Chromium/WebKit проверяет mobile/desktop print
  layout, dark/light preview, отсутствие горизонтального overflow и скрытие экранных
  controls в print media. Chromium создаёт PDF; Poppler подтвердил A4 и страницы.
- Public share: явный preview → create flow, immutable snapshot, no automatic
  public exposure, `no-store`/`noindex`, revoke и отсутствие private keys,
  nutrition/body в public snapshot.

## Реальные PDF

| Артефакт | PDF | Rendered pages |
| --- | --- | --- |
| Серверный PDF, custom/days-30 fixture | [PDF](server/server-progress-report-days-30.pdf) | [1](server/server-progress-report-days-30-1.png), [2](server/server-progress-report-days-30-2.png) |
| Browser print PDF, Chromium | [PDF](browser/browser-progress-report.pdf) | [1](browser/browser-progress-report-1.png), [2](browser/browser-progress-report-2.png), [3](browser/browser-progress-report-3.png), [4](browser/browser-progress-report-4.png), [5](browser/browser-progress-report-5.png) |

## Observed metadata

- Серверный PDF: A4, 2 страницы, 40,496 bytes, ReportLab 5.0.1 runtime.
- Browser PDF: A4, 5 страниц, 424,682 bytes, Chromium/Skia PDF.
- В серверный PDF добавлена единица `мин` для значения «Минуты кардио»; формулы
  и canonical calculations не менялись.
- Screen-only controls («Показать период», «Скачать PDF», «Состав и отправка
  отчёта») в generated server PDF и browser print pages не присутствуют.

## Reproducible checks

- `backend/tests/test_progress_reports.py`: `19 passed`.
- `backend/tests/test_public_shares.py`: `3 passed`.
- `frontend/tests/unit/pages/ProgressReportPage.test.tsx`: `13 passed`.
- `frontend/tests/e2e/progress-report.spec.ts`: `12 passed` total — Chromium `6`,
  WebKit `6`.

Source/evidence commit: `f7a900a743a6ecbc71b97a954d3ed2e036ef8404`.
