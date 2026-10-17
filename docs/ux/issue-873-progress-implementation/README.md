# YFC Issue #873 — AFTER evidence

Локальный пакет AFTER-доказательств для утверждённой переработки подробных разделов
«Прогресс». Кадры сняты после реализации в браузере на синтетических данных; это не
production- и не физическое устройство.

## Provenance

- Base master: `4c92832415d4eb994cf6b849a67074742f07ea50`
- Current merged origin/master: `269d6b625c198b8c9f1d0093d2bb911ba451e709`
- Approved design package: `18002f8bdf938ba9d7ed0e3b0353f2682000ba6d`
- Initial implementation evidence commit: `c4f8c8c2`
- Continuation application commit: `66e5f050cba410c605c0cbb804c7d153e9e8aee7`
- Evidence refresh commit: `936456db7e93bfbd72ffb52c1f3c735429897073`
- Implementation branch: `codex/issue-873-progress-implementation-v2`
- Capture browser: Playwright Chromium, reduced motion; cross-browser regression также
  выполнен в Playwright WebKit.
- Обновление mobile golden: четыре исходных PNG для Progress совпадали с `origin/master`;
  новые PNG взяты из actual-кадров GitHub Actions run `38969943158` для Chromium/WebKit в
  светлой/тёмной темах после утверждённой переработки.
- Fixture: synthetic client «Анна», период 30 дней; body — 4 точки веса и 2 точки талии,
  training — 7 завершённых из 8 запланированных, nutrition — complete/incomplete/fasted/
  missing states, cardio — 2 завершённые сессии, wellbeing — сохранённый weekly review,
  history — 1 завершённая тренировка.

## Paired BEFORE/AFTER comparison — 2026-10-17

- BEFORE снят на exact owner-requested base `4c92832415d4eb994cf6b849a67074742f07ea50`;
  AFTER — на exact continuation revision
  `936456db7e93bfbd72ffb52c1f3c735429897073` после merge с текущим `origin/master`.
- [HTML-галерея парных сравнений](./evidence/paired-20261017/gallery.html) — 88 пар рядом,
  шесть разделов, light/dark, 320/360/393/430/1440 px, обычные/раскрытые состояния и
  действие «Добавить замер».
- [Полная таблица высоты, прокрутки и действий](./evidence/paired-20261017/metrics.md).
- [Разбор Frontend smoke timeout](./evidence/paired-20261017/ci-timeout.md).
- Фикстура, область `.progress-details`, высоты viewport и `scrollY=0` одинаковы; capture
  использует Chromium и синтетические данные, изображения JPEG quality 88.

В «Теле» сокращены повторные пояснения и заголовок графика, уменьшены локальные интервалы;
яркая кнопка добавления замера остаётся рядом с последним фактом, а история/редактирование
сохраняются. При открытом редакторе внешний повтор «Как сравнивать замеры» скрывается, но
ограничения и пояснения остаются в confidence/note и встроенной подсказке дневника.

## Captures

Detail captures use the `.progress-details` region. Control captures use the
`.progress-hero` region. The desktop capture uses the body detail at 1440×900.

| Surface            | Dark                            | Light                            |
| ------------------ | ------------------------------- | -------------------------------- |
| Body, 393×844      | [PNG](./body-393-dark.png)      | [PNG](./body-393-light.png)      |
| Training, 393×844  | [PNG](./training-393-dark.png)  | [PNG](./training-393-light.png)  |
| Nutrition, 393×844 | [PNG](./nutrition-393-dark.png) | [PNG](./nutrition-393-light.png) |
| Cardio, 393×844    | [PNG](./cardio-393-dark.png)    | [PNG](./cardio-393-light.png)    |
| Wellbeing, 393×844 | [PNG](./wellbeing-393-dark.png) | [PNG](./wellbeing-393-light.png) |
| History, 393×844   | [PNG](./history-393-dark.png)   | [PNG](./history-393-light.png)   |
| Controls, 320×844  | [PNG](./controls-320-dark.png)  | [PNG](./controls-320-light.png)  |
| Controls, 360×844  | [PNG](./controls-360-dark.png)  | [PNG](./controls-360-light.png)  |
| Controls, 430×844  | [PNG](./controls-430-dark.png)  | [PNG](./controls-430-light.png)  |
| Body, 1440×900     | [PNG](./body-1440-dark.png)     | [PNG](./body-1440-light.png)     |

## Verified contracts

- One-column mobile detail hierarchy at 320/360/393/430 px; desktop body composition at
  1440 px.
- No horizontal overflow in the supported Progress matrix; header help, period controls,
  focus, URL deep links, back/forward navigation and reduced-motion behavior remain covered
  by the Progress E2E suite.
- Empty, partial and populated data stay distinguishable; missing values remain `—` or an
  explicit data-confidence state. The UI does not synthesize a result from missing records.
- Existing measurement form, edit/history path, cardio actions and confirmation dialog remain
  available. Training exercise/muscle details and nutrition report remain behind their current
  disclosure/navigation surfaces.
- The synthetic history fixture contains one completed workout; the Issue requirement for
  history evidence across at least two workouts is `NOT_VERIFIED` by this package.

## Limitations and gates

- Synthetic browser evidence only. Physical iPhone, Telegram Mini App runtime, VoiceOver,
  native keyboard/safe-area behavior and real-device touch are `NOT_VERIFIED`.
- Owner design approval is recorded as `APPROVED` by the task request. Owner AFTER visual
  acceptance is still pending; merge and deploy are forbidden for this task.
- No backend, API, database, formula, history, RBAC, privacy, environment-variable or secret
  change is included.
- Парная browser-галерея переснята после merge и точечного исправления каскада CSS; все
  AFTER-кадры и `manifest.json` привязаны к
  `936456db7e93bfbd72ffb52c1f3c735429897073`.
