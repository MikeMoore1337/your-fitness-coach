# #874 — отчёт, PDF и числовая согласованность

Evidence получено на одном фиксированном synthetic наборе данных. Это не
production или real-user proof.

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
