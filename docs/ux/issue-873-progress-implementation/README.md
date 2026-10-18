# YFC Issue #873 — AFTER evidence

Локальный пакет AFTER-доказательств для утверждённой переработки подробных разделов
«Прогресс». Кадры сняты после реализации в браузере на синтетических данных; это не
production- и не физическое устройство.

## Provenance

- Base master: `4c92832415d4eb994cf6b849a67074742f07ea50`
- Current merged origin/master: `5398f724d0f232a58fbbd55e05b92b4a0554a900`
- Approved design package: `18002f8bdf938ba9d7ed0e3b0353f2682000ba6d`
- Initial implementation evidence commit: `c4f8c8c2`
- Continuation application commit: `66e5f050cba410c605c0cbb804c7d153e9e8aee7`
- Code/test completion revision: `2f1cb8930e07a41a8b7303cb4c8b63ad45f65b82`
- Implementation branch: `codex/issue-873-progress-implementation-v2`
- Capture browser: Playwright Chromium, reduced motion; cross-browser regression также
  выполнен в Playwright WebKit.
- Fixture: synthetic client «Анна», период 30 дней; body — 4 точки веса и 2 точки талии,
  training — 7 завершённых из 8 запланированных, nutrition — complete/incomplete/fasted/
  missing states with 18 confirmed statuses and 9 days with usable data, cardio — 3
  завершённые сессии, wellbeing — сохранённый weekly review, history — 2 завершённые
  тренировки с разными датами, упражнениями, подходами и объёмом.

## Final AFTER matrix — 2026-10-18

- [Интерактивная галерея](./evidence/paired-20261018/gallery.html), [manifest](./evidence/paired-20261018/after/manifest.json)
  and [metrics](./evidence/paired-20261018/metrics.md) are pinned to capture revision
  `2f1cb8930e07a41a8b7303cb4c8b63ad45f65b82`.
- 144 Chromium captures: 7 views (`overview`, `body`, `training`, `nutrition`, `cardio`,
  `wellbeing`, `history`) × light/dark × 320/360/393/430/1024/1280/1440/1920 px; 112 default,
  28 expanded and 4 «Добавить замер» action states.
- Detail views use `.progress-details`; overview uses `.progress-summary`; viewport scroll is
  reset to zero after fonts and two animation frames. Images are JPEG quality 88.
- The older [2026-10-17 paired package](./evidence/paired-20261017/gallery.html) remains
  historical BEFORE/AFTER context on the prior one-workout fixture; it is not relabeled as
  the final two-workout evidence.

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

## Historical captures

The original six-section thumbnails and the exact-base paired package remain under
`evidence/paired-20261017/`. Use the final matrix above for current visual review.

## Verified contracts

- One-column mobile detail hierarchy at 320/360/393/430 px; desktop body composition at
  1440 px.
- No horizontal overflow in the supported Progress matrix; header help, period controls,
  focus, URL deep links, back/forward navigation and reduced-motion behavior remain covered
  by the Progress E2E suite.
- Empty, partial and populated data stay distinguishable; missing values remain `—` or an
  explicit data-confidence state. The UI does not synthesize a result from missing records.
- Body confidence cards identify whether the conclusion refers to mass or circumferences.
- Nutrition distinguishes confirmed day statuses from days with data used for averages; the
  detailed report keeps its separate filled/missing, macro, hydration, goals and CSV surfaces.
- Cardio rows match the synthetic period request and its completed-session summary; history
  shows two independent records with separate exercises, totals and preserved confirmation.
- Existing measurement form, edit/history path, cardio actions and confirmation dialog remain
  available. Training exercise/muscle details and nutrition report remain behind their current
  disclosure/navigation surfaces.

## Limitations and gates

- Synthetic browser evidence only. Physical iPhone, Telegram Mini App runtime, VoiceOver,
  native keyboard/safe-area behavior and real-device touch are `NOT_VERIFIED`.
- Owner design approval is recorded as `APPROVED` by the task request. Owner AFTER visual
  acceptance is still pending; merge and deploy are forbidden for this task.
- No production backend, API, database, formula, RBAC, privacy, environment-variable or secret
  change is included; fixture/test data changes are synthetic only.
- AFTER frames and the manifest are pinned to the code/test completion revision above. GitHub
  PR checks, owner visual acceptance, merge and deploy remain separate gates.
