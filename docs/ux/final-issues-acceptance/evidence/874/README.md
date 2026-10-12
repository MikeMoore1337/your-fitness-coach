# #874 — отчёт, PDF и числовая согласованность

Проверки используют один фиксированный synthetic набор данных из
[`tests/fixtures/progress-report-canonical.json`](../../../../tests/fixtures/progress-report-canonical.json).
Это не production или real-user proof.

## Текущий технический срез и owner-gate

Сверка baseline выполнена от контрольного HEAD
`3e7fb0743df127a11505c25fbc48ddb1687393a8` в отдельном linked worktree PR #963.
Production UI, формулы, PDF layout и approved navigation в этом срезе не изменялись.

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

## Воспроизводимые результаты текущего среза

- `backend/tests/test_progress_reports.py`: `21 passed`;
- canonical Vitest: `2 passed`;
- frontend `typecheck`, `lint` и Russian UI guard: зелёные;
- frontend production `build`: зелёный;
- targeted Playwright Chromium browser-PDF test: `1 passed`;
- targeted API/server-PDF test фактически извлекает и сравнивает значения, даты, единицы,
  период и privacy boundaries.

WebKit, полный required CI и final exact-head aggregate для будущего коммита не выдаются за
пройденные этим локальным срезом проверки.

## Визуальные результаты до owner approval

Аудит текущего production UI подтвердил открытые визуальные критерии: повторяющиеся большие
карточки полноты данных, повтор первой/последней сессии при одной записи, пустой заголовок
таблицы окружностей и неэкономную pagination browser PDF. Подготовлен отдельный локальный
`PROPOSAL ONLY` пакет BEFORE/AFTER с вариантами компактной полноты данных, one-record/empty
states, цветной диаграммы для print/PDF, grayscale-проверки и pagination storyboard.

Пакет не загружен в публичный репозиторий: он содержит synthetic user evidence и требует
одного owner approval перед любым изменением production UI. Одобрение общего цветового
направления PDF (`OWNER_COLOR_PRINT_DIRECTION=APPROVED`) не считается одобрением конкретной
верстки.

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
