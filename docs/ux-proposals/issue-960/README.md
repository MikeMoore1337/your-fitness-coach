# Issue #960 — фактическое время отдыха: discovery-пакет

**Статус:** `DISCOVERY_ONLY` · production-код не менялся · `MERGE=FORBIDDEN` ·
`DEPLOY=FORBIDDEN`.

**Issue:** [#960](https://github.com/MikeMoore1337/your-fitness-coach/issues/960)

**Исходный SHA:** `4c92832415d4eb994cf6b849a67074742f07ea50` (`origin/master`,
2026-10-16, merge #1042).

**Ветка:** `codex/issue-960-rest-discovery`

**Owner gates:** `OWNER_DESIGN_APPROVAL=PENDING`, `OWNER_IMPLEMENTATION_APPROVAL=PENDING`,
`OWNER_VISUAL_ACCEPTANCE=NOT_APPLICABLE_YET`, `MERGE=FORBIDDEN`, `DEPLOY=FORBIDDEN`.

Этот пакет является предложением для решения владельца. SVG — статические обезличенные макеты,
не production UI и не AFTER evidence.

## Решение в одном абзаце

Предлагается отдельная сущность `workout_rest_session`, создаваемая один раз после принятого
завершения рабочего подхода. Она хранит снимок планового отдыха, отдельную скорректированную цель
и, только после явной отметки пользователя, фактический интервал. `+30 сек` и `+60 сек` меняют
только цель таймера. После достижения цели обратный счётчик остаётся на нуле, прямой счётчик
продолжает показывать время от принятого завершения предыдущего подхода до нажатия
«Закончить отдых». Это не измерение физиологической готовности и не доказательство фактического
начала следующего подхода.

## Что проверено на исходном SHA

| Область | Факт на `origin/master` | Следствие для #960 |
| --- | --- | --- |
| Надёжная граница старта | `TodayWorkout.tsx:443-497` вызывает `fit:rest` только после `activeSync.enqueue(..., immediate)` вернул `true`; для отдыха проверяется завершённый рабочий подход, а warmup/activation исключены. | Точка `START_ACCEPTED` — принятый сервером результат либо durable offline persistence, а не нажатие до принятия. |
| Плановый таймер | `RestTimer` в `TodayWorkout.tsx:1457-1700` хранит `deadline` в user/workout-scoped storage, восстанавливает его после reload/pageshow и сверяет абсолютный `Date.now()`. | Существующий deadline можно переиспользовать как UI-механику, но новая запись должна быть отдельной от set mutation. |
| Ноль и уведомление | `TodayWorkout.tsx:1563-1606` при достижении deadline удаляет storage, показывает одно локальное уведомление и compact-статус. После этого elapsed не продолжается. | Для #960 нужен второй счётчик и явный terminal action; достижение нуля не завершает rest session. |
| `+30/+60` и skip | `TodayWorkout.tsx:1641-1677` прибавляет секунды к deadline и поддерживает `Пропустить`; отдельного target snapshot или измерения пока нет. | Adjustment сохраняется в rest session и никогда не переписывает measured value; `Пропустить` не создаёт достоверный замер. |
| Offline queue | `useActiveWorkoutQueue.ts:182-260,262-324` пишет durable очередь, синхронизирует `PATCH /api/v1/workouts/sets/{set_id}` с `expected_version`/`mutation_id`, использует `crossContextCoordinator`. | Rest events должны идти через отдельный typed contract/endpoint, но могут переиспользовать существующую координацию и storage-scoping. |
| Set contract | `workouts.py:1316-1378` и `workout_sync.py:80-125` разрешают set-PATCH менять `is_completed`; `UserWorkoutExercise.rest_seconds` — план (`models/program.py:526`), `UserWorkoutSet.is_completed` — состояние подхода (`:545-584`). | Нельзя отправлять rest action через set-PATCH: это создаёт race и подменяет бизнес-смысл. `rest_seconds` и `is_completed` остаются неизменными. |
| Отчёты | `ProgressReportResponse` (`schemas/progress.py:374-390`), builder (`services/progress_reports.py:118-212`) и PDF builder (`services/progress_report_pdf.py`) не содержат rest facts. | Интеграция должна быть additive и optional; отсутствие строки означает `—`, а не `0`. |
| Coach OS | Trainer routes используют `require_coach` и `_managed_client` (`coach.py:355-359`); отчёты и timeline строятся только для действующей связи. | Rest facts можно открыть тренеру только через существующий ownership/RBAC boundary; AI Coach не входит в scope. |

### Связанные решения и исключения

- #914 закрыта после отдельного production acceptance; #927/#1011/#1012 относятся к
  безопасному текущему UI-таймеру, а не к истории фактического отдыха.
- #977 и #980 — отдельные workstreams; их поведение в #960 не переопределяется.
- После PR #1021 AI Coach UI скрыт. В #960 не добавляются карточки, ссылки, fallback-заглушки,
  provider calls или новые AI Coach entry points. Coach OS здесь означает только существующий
  deterministic trainer workspace.
- `#1002/#996` не затронуты: active-workout CSS, общие set REST endpoints и миграции в этом
  discovery-пакете не редактировались.

## Доменный контракт

### Что именно измеряется

`measured_rest_seconds` — целое число секунд между:

1. моментом, когда завершение предыдущего подхода принято сервером или надёжно сохранено в
   существующую durable offline queue (`START_ACCEPTED`);
2. явной пользовательской отметкой «Закончить отдых».

Это пользовательская отметка времени в active workout. Она не означает, что человек был
физиологически готов, не обнаруживает реальное начало следующего подхода и не доказывает, что
между двумя событиями не было отвлечения.

| Поле/понятие | Источник и смысл | Что нельзя делать |
| --- | --- | --- |
| `planned_rest_seconds` | Снимок `UserWorkoutExercise.rest_seconds` на момент start. | Не менять при добавлении фактического замера. |
| `adjusted_target_seconds` | План конкретной rest session после `+30/+60`; начально равен плану. | Не считать его фактом и не вычитать из measured. |
| `started_at` | Один `START_ACCEPTED`; UTC timestamp принятия завершения подхода. | Не запускать второй раз из повторного tap, reload, второй вкладки или retry. |
| `ended_at` | Явная terminal action пользователя. | Не выводить автоматически из достижения deadline или появления следующего поля. |
| `measured_rest_seconds` | `ended_at - started_at`, только если порядок и clock quality надёжны. | Не подставлять `0`, `planned` или время до следующего рендера. |
| `source` | `USER_CONFIRMED` для явного terminal action; отдельно сохраняется `start_acceptance` (`SERVER_CONFIRMED` или `DEVICE_DURABLE`). | Не называть значение `physiological`, `ready`, `actual_start` или `objective`. |
| `status` | `running`, `completed`, `skipped`, `interrupted`, `unknown`. | Не превращать `running` в `completed` только по timeout. |
| `quality` | `normal`, `long`, `clock_suspect`, `unknown`. | Не включать `unknown` и неподтверждённые записи в статистику. |

Старые тренировки без rest row показываются как `Нет достоверного замера` или `—`. Ноль —
это только валидное измерение длительностью менее одной отображаемой секунды, а не значение по
умолчанию.

### State machine

Domain state и transport/sync state независимы: `pending_sync`, `syncing`, `offline`, `conflict`
не являются доменными статусами и не разрешают показывать запись как server-confirmed.

```text
NONE
  └─ START_ACCEPTED (один раз) ───────────────> RUNNING
                                                   │
                         PLAN_REACHED + notify ───┤  (остаётся RUNNING)
                                                   │
                         +30/+60 ── target only ──┤
                                                   │
       явная «Закончить отдых» ──────────────────> COMPLETED
       «Пропустить» ────────────────────────────> SKIPPED
       «Прервать отдых» / abort ────────────────> INTERRUPTED
       нет надёжного восстановления/забытый stop -> UNKNOWN

COMPLETED / SKIPPED / INTERRUPTED / UNKNOWN
  └─ повтор того же idempotency key ───────────> тот же terminal response
  └─ другая terminal action ───────────────────> 409 + authoritative state
```

Правила переходов:

| Событие | Условие | Результат |
| --- | --- | --- |
| `START_ACCEPTED` | Предыдущий set подтверждён/надёжно сохранён; рабочий set; active workout; ownership прошёл. | Создать ровно одну session, зафиксировать план, `adjusted_target=planned`, запустить оба счётчика. |
| `PLAN_REACHED` | `now >= target_at`. | Один notification/haptic максимум на session; `remaining=0`; `elapsed` продолжает расти. |
| `ADJUST_TARGET(+30/+60)` | Session `running`, action idempotent. | `target_at = max(previous_target_at, now) + delta`; `started_at` и будущий measured не меняются. |
| `COMPLETE` | Явно нажата terminal action. | `ended_at`, `measured`, `status=completed`; следующий set не помечается выполненным. |
| `SKIP` | Явно нажата `Пропустить`. | `status=skipped`, `measured=null`; это не «быстрый достоверный отдых». |
| `INTERRUPT` | Явная отмена/прерывание active workout. | `status=interrupted`, `measured=null`; причина — bounded enum, без свободного диагноза. |
| `UNKNOWN` | Сессия не может быть восстановлена безопасно, clock sequence невозможна или истёк forgotten-stop policy. | История сохраняет факт неизвестности, но не число; в статистику не входит. |

`+30/+60` после уже достигнутого плана допустимы: они возобновляют обратный счётчик от текущего
момента, но не уменьшают уже показанное elapsed и не переписывают начало.

### Forgotten stop и длинный интервал

Предложение для owner decision, не медицинский или научный порог:

- до порога `LONG_REST_THRESHOLD = max(4 × adjusted_target_seconds, 2 часа)` явный finish
  получает `quality=normal`;
- после порога явный finish сохраняется как `completed`, но с `quality=long`: он виден в истории,
  имеет measured и отдельный `n_long`, но не попадает в обычную сводку без явного включения;
- после `FORGOTTEN_STOP_THRESHOLD = max(8 × adjusted_target_seconds, 12 часов)` при следующем
  resume/reconcile открытая сессия переводится в `unknown`; приложение не придумывает конец и не
  считает такой интервал нулевым;
- до автоматического `unknown` UI показывает спокойное предупреждение «Интервал заметно длиннее
  плана» без оценки дисциплины. Пользователь может явно завершить или прервать его;
- оба порога должны быть server-configurable и зафиксированы отдельным owner/domain decision.

Если владелец не принимает эти default-пороги, реализация должна оставить их nullable policy
parameters, а не зашивать непроверенное значение в UI, миграцию или отчёт.

## Additive data model

Рекомендуемый вариант — отдельная таблица `workout_rest_sessions`, не расширение
`user_workout_sets` и не замена `rest_seconds`.

```text
id
user_id                         FK, owner boundary
workout_id                      FK
completed_set_id                FK -> completed source set
next_set_id                     FK nullable, context only
planned_rest_seconds            snapshot of plan
adjusted_target_seconds         session plan after +30/+60
started_at                      UTC, START_ACCEPTED, immutable
ended_at                        UTC nullable until terminal
measured_rest_seconds           nullable; only terminal completed + valid clock
status                          running | completed | skipped | interrupted | unknown
source                          USER_CONFIRMED | SYSTEM_RECOVERY
start_acceptance                SERVER_CONFIRMED | DEVICE_DURABLE
quality                         normal | long | clock_suspect | unknown
version                         optimistic concurrency
start_mutation_id               idempotency key
terminal_mutation_id            idempotency key nullable
created_at / updated_at         UTC audit timestamps
```

Минимальные constraints/indexes:

- unique `(user_id, completed_set_id)` для одной rest session на одно принятое завершение;
- `adjusted_target_seconds >= planned_rest_seconds >= 0`;
- `measured_rest_seconds` не null только для `status=completed` и `quality in {normal,long}`;
- `ended_at >= started_at` при валидном measured;
- `version >= 1`, status transition проверяется на server boundary;
- индексы `(user_id, started_at)`, `(workout_id, completed_set_id)` и status/period query;
- `user_id` берётся из auth context, не из request body.

### Варианты и выбор

| Вариант | Плюс | Риск | Решение для #960 |
| --- | --- | --- | --- |
| **A. Session resource (рекомендуется)** | Открытая сессия переживает reload/background/offline; target adjustment и terminal action идемпотентны; history query проста. | Нужна additive таблица и отдельные transitions. | Выбрать после owner approval API/domain contract. |
| B. Только append-only events | Удобна аудиторская история событий. | Дороже чтение/repair; открытая offline session и terminal race требуют дополнительного projection. | Оставить альтернативой, не смешивать с A в первой реализации. |
| C. Поля на `UserWorkoutSet` | Меньше таблиц. | Смешивает set completion/rest semantics, ломает ownership/race boundary и не поддерживает несколько событий. | Отклонить. |

## Proposed API contract

Названия ниже — discovery contract, не существующие endpoints.

```text
POST /api/v1/workouts/{workout_id}/rest-sessions
  body: { completed_set_id, next_set_id? }
  header: Idempotency-Key
  -> создаёт/возвращает session, сервер сам читает plan и проверяет set/workout ownership

POST /api/v1/workouts/{workout_id}/rest-sessions/{session_id}/target
  body: { delta_seconds: 30 | 60, expected_version, mutation_id }
  -> меняет только adjusted_target_seconds

POST /api/v1/workouts/{workout_id}/rest-sessions/{session_id}/finish
  body: {
    action: "complete" | "skip" | "interrupt",
    expected_version,
    mutation_id,
    client_ended_at?
  }
  -> terminal idempotent transition; measured вычисляется только для complete

GET /api/v1/workouts/rest-sessions?date_from=&date_to=&exercise_id=
  -> только текущий user; old rows без session отсутствуют и сериализуются как unknown/no measurement
```

Контракт переходов:

- `POST start` требует `workout.status=in_progress`, активную программу, принадлежность set
  текущему пользователю, `is_completed=true`, допустимый рабочий set и отсутствие второй session
  для того же completion. Он не меняет set.
- Повтор `start` с тем же `Idempotency-Key` возвращает тот же resource; повтор с другим ключом
  для того же `completed_set_id` возвращает тот же resource, а не вторую сессию.
- `target` принимает только `30`/`60`; повтор `mutation_id` возвращает прежний target; stale
  `expected_version` получает structured 409 с текущим resource.
- `finish` с тем же terminal mutation id безопасно повторяется. Другая terminal action после
  terminal state получает 409, кроме точного replay.
- `skip`/`interrupt` возвращают `measured_rest_seconds=null`. `complete` возвращает измерение
  только когда server/local timestamps прошли clock validation.
- Не добавлять `is_completed`, `rest_seconds` или произвольный `user_id` в rest payload.

### Offline и accepted boundary

Для online сценария `start` отправляется после текущего server-confirmed set mutation. Для offline
сценария порядок такой:

1. set completion durable в существующем user/workout-scoped queue;
2. local rest-start durable с `start_acceptance=DEVICE_DURABLE`;
3. local target/finish actions durable в том же порядке;
4. после reconnect set mutation синхронизируется раньше rest start; затем rest actions.

Существующий `crossContextCoordinator`, account/workout scoping и lifecycle persistence можно
переиспользовать, но rest mutation не должен попадать в `PATCH /sets/{set_id}`. Если local storage
недоступно, UI сообщает «Не удалось надёжно сохранить отдых» и не выдаёт измерение как сохранённое.

## Reload, background, clock, timezone, multi-tab и races

| Ситуация | Требование |
| --- | --- |
| Reload/background | Восстановить session по `started_at` и `adjusted_target`; сразу пересчитать remaining/elapsed по absolute timestamps. Не создавать новый start. |
| Timezone change | Хранить UTC; timezone влияет только на локальное отображение истории/отчёта. |
| System clock jump назад/вперёд | Сравнить client timestamps/server receipt; при отрицательной или недоказуемой последовательности `measured=null`, `quality=clock_suspect`, status `unknown` либо явное terminal without metric. Не исправлять время «на глаз». |
| Browser timer throttling | Таймер — display only; при wake/visibility/pageshow считать от absolute timestamp, не от числа interval ticks. |
| Multi-tab | Один local coordination lock и storage event; server unique key + version. Старая вкладка после 409 принимает authoritative terminal state. |
| Duplicate tap / retry | `completionInFlight` остаётся UI guard, но correctness обеспечивают mutation/idempotency keys. Один target notification на session через durable notified marker/coordination. |
| Set conflict | Если completion не принят server и durable queue потеряна/конфликтна, rest не объявляется server-confirmed; session остаётся pending/unknown и не попадает в aggregate. |
| Logout/account switch | Storage scoped к user/workout; cleanup не переносит rest state между accounts. |
| Next set | `Закончить отдых` не ставит следующий set в `is_completed=true` и не фиксирует objective start. Следующий set завершается отдельным существующим flow. |

## History, reports, PDF и Coach OS

### History

Для каждой подтверждённой session показывать:

```text
План 01:30 · Факт 01:44 · +00:14 · Отметка пользователя
```

Для `long` — дополнительно `Длинный интервал; в обычную сводку не включён`. Для `skipped` /
`interrupted` — статус без факта. Для старого workout — `Нет достоверного замера`.

Mean/median имеют явный `n`: `Медиана 01:38 · n=6`, `Среднее 01:41 · n=6`. При `n=0`
число отсутствует (`null` в API, `—` в UI), не `0`. Рекомендуемая default aggregate включает
только `completed + quality=normal`; `n_long` показывается отдельно. Ни один aggregate не
включает `unknown`, `skipped`, `interrupted` или незаписанные старые тренировки.

### Additive report/PDF shape

После отдельного implementation approval в `ProgressReportResponse` можно добавить optional block:

```json
{
  "rest": {
    "observed_count": 6,
    "normal_count": 5,
    "long_count": 1,
    "median_seconds": 98,
    "mean_seconds": 101,
    "coverage": "5 из 18 рабочих подходов"
  }
}
```

`rest` отсутствует/пуст, если нет trusted observations; client DTO не получает internal IDs,
raw timestamps, mutation keys или данные другого аккаунта. PDF добавляет компактный блок только
при наличии данных; иначе печатает `Фактический отдых: нет достоверных замеров`, а не нулевую
метрику. Existing report download/handoff authorization остаётся источником доступа.

### Coach OS

- Phase 3 read-only: `require_coach` → `_managed_client` → current active relationship; revoked
  or unrelated client remains 404/deny.
- Trainer sees only the same deterministic facts: plan/fact/status, counts, median/mean with `n`.
- No discipline score, readiness, fatigue, recovery, medical inference or automatic program change.
- No AI Coach UI/provider path. If #1021 keeps AI Coach UI disabled, this data does not create a
  new entry point or hidden fallback.
- Report handoff remains the existing live authorized report contract; no public link or copied
  rest payload is introduced.

## UX candidates for owner review

Both candidates keep the current YFC sport-tech baseline, existing matte Liquid Glass material,
shared typography/touch tokens and the current `+30 сек / +60 сек / Пропустить` actions. The panel
stays in the active-workout flow as sticky top content and reserves its own height; it is not an
overlay over the next set. It uses synthetic data only.

### Variant A — two equal counters, recommended

Primary reading is stable in both phases:

- `Осталось 00:48` — plan countdown;
- `Прошло 00:42` — factual elapsed from accepted completion, with accessible description;
- after zero, `План завершён` remains visible while `Прошло 02:14` continues;
- one CTA `Закончить отдых` is separate from the three plan actions;
- `Далее: Тяга верхнего блока · 2-й подход` is context, not an objective start event.

This is the clearest model when both values must be compared. It costs one extra action row on
the narrowest screens, so the proposed geometry is: counters/context row, full-width terminal CTA,
then three 44px secondary actions. No control is below 44px and no negative adjustment is added.

- [Variant A · Dark](rest-time-panel-variant-a-dark.svg)
- [Variant A · Light](rest-time-panel-variant-a-light.svg)

### Variant B — phase-priority counter, alternate

The same stable panel changes emphasis without changing geometry:

- before plan deadline: large `Осталось`, smaller `Прошло`;
- after deadline: large `Прошло`, compact `План завершён`;
- target actions, finish CTA, next-set context and labels remain in the same positions.

It uses less visual competition after zero, but the changing emphasis may be less immediately
comparable than A.

- [Variant B · Dark](rest-time-panel-variant-b-dark.svg)
- [Variant B · Light](rest-time-panel-variant-b-light.svg)

### Accessibility and platform intent

Implementation must preserve, and the owner-approved mockup must be checked against:

- semantic buttons, visible `:focus-visible`, logical Tab order and no focus loss after tick/action;
- timer `aria-live=off`; one separate status announcement for plan reached/terminal result;
- `aria-label` explains that factual elapsed is from accepted previous-set completion and is not
  physiological readiness; live numbers are tabular and not color-only;
- safe-area top inset, `visualViewport`, keyboard repositioning and no dock/field overlap;
- 44×44 targets at 320/360/393/430px, 768px tablet and 1280/1440px desktop;
- Chromium and WebKit, mocked TMA Light/Dark, `prefers-reduced-motion`, forced colors and reduced
  transparency; no Telegram-only palette or component tree;
- long exercise labels wrap/ellipsis without hiding finish or plan actions;
- notification is non-blocking and never the only confirmation.

## Verification plan after owner approval

This is a plan, not evidence already produced by this discovery branch.

### Domain/backend

- transition-table unit tests for every state/action and terminal replay;
- start once after server-confirmed and durable-offline completion;
- no changes to `UserWorkoutSet.is_completed` or `UserWorkoutExercise.rest_seconds` from rest API;
- ownership, active-program, 401/403/404 boundaries, coach active relationship and revoked access;
- duplicate start/finish/target mutation, stale version, conflicting terminal action and multi-tab race;
- reload/background/reconnect, timezone, negative/forward clock jump, forgotten-stop and long quality;
- old workouts serialize `null`/unknown, never zero; aggregate returns `n` and null at `n=0`.

### Browser Web/TMA

Use synthetic fixtures and separate evidence folders for each engine/theme:

| Matrix | Required cases |
| --- | --- |
| 320/360/393/430 × Light/Dark × Chromium/WebKit | countdown, overtime elapsed, +30, +60, finish, skip, interrupt, long label, no horizontal overflow |
| 390/844 baseline | keyboard focus, safe area, fixed/sticky geometry, visualViewport resize, reload |
| 768 and 1280/1440 | one-line desktop layout, keyboard and focus, no duplicate navigation |
| mocked TMA | ready/foreground/background, safe-area events, BackButton lifecycle, reconnect, no second auth |
| reduced motion/forced colors | no essential information lost; transition/blur optional only |
| two tabs | one start, one notification, one target update, terminal convergence |

Assertions use DOM/ARIA/geometry, not decorative pixel guesses: panel bounds stay clear of the
first editable field, every target is at least 44×44, focus is visible, next set remains reachable,
`is_completed` mutations are unchanged, and notification count is one.

### History/report/PDF/Coach OS

- self history and trainer history show `—`/unknown distinctly from `0`;
- mean/median carry `n`, long and unconfirmed rows are not silently folded into defaults;
- personal report/PDF and existing report handoff remain subject/period/timezone scoped;
- trainer endpoints deny unrelated/revoked clients and expose no user IDs/mutation keys;
- PDF A4 light print has no clipped new section and labels the source as user-confirmed;
- Coach OS remains deterministic and no AI Coach/provider request appears.

### Evidence level labels

Browser automation and mocked TMA are `VERIFIED` only for those environments. Physical
iPhone/Safari, real Telegram Android/iOS, VoiceOver and field performance remain `NOT_VERIFIED`
until actually tested. No production AFTER evidence exists in this branch.

## Phasing and gates

```text
Owner selects A or B + accepts semantics/thresholds
  -> separate implementation approval
  -> Phase 1: accounting (session API/DB + offline + active-workout panel)
  -> real AFTER Dark/Light Web evidence + owner visual acceptance
  -> Phase 2: history + report/PDF additive read models
  -> Phase 3: Coach OS read-only, active relationship only
  -> separate CI/merge/release/deploy approvals
```

Phase 1 must not silently ship history aggregates or Coach OS. Phase 2 must not infer readiness.
Phase 3 must not reactivate AI Coach. Each phase has its own backward-compatible API/report tests.

## Requested owner decision

1. Выбрать `Variant A` (рекомендуемый) или `Variant B` для дальнейшего mockup approval.
2. Подтвердить термины: `План`, `Прошло`, `Закончить отдых`, `Пропустить` и явное пояснение
   «по отметке пользователя».
3. Подтвердить, что skip/interruption не дают measured value, а `+30/+60` изменяют только plan.
4. Подтвердить forgotten-stop/long policy либо назначить другие product thresholds.
5. Отдельно разрешить implementation после этого discovery. Сейчас реализация, PR, merge и
   deploy не разрешены.

## Scope ledger

| Проверено/создано | Статус |
| --- | --- |
| Live Issue #960, comments, related #914/#927/#1011/#1012, duplicate search | `VERIFIED` live on 2026-10-16; #960 has no comments and no implementation PR found |
| `origin/master` and source SHA | `VERIFIED`: `4c92832415d4eb994cf6b849a67074742f07ea50` |
| Current timer, accepted completion, queue and backend set contract | `VERIFIED` read-only; exact paths above |
| AI Coach hidden boundary | `VERIFIED` against merged PR #1021; no new AI surface proposed |
| Discovery contract and static Dark/Light mockups | `CREATED` in this directory, synthetic data |
| Production runtime/DB/API/PDF/CSS | `NOT_MODIFIED` |
| Runtime tests, browser AFTER, physical device, real TMA, VoiceOver | `NOT_RUN` / `NOT_VERIFIED` by design |

## Files in this evidence package

- [This discovery contract](README.md)
- [Variant A · Dark](rest-time-panel-variant-a-dark.svg)
- [Variant A · Light](rest-time-panel-variant-a-light.svg)
- [Variant B · Dark](rest-time-panel-variant-b-dark.svg)
- [Variant B · Light](rest-time-panel-variant-b-light.svg)

**Next gate:** explicit owner design decision on one complete candidate package, followed separately
by implementation approval. Until then the production timer and all runtime contracts remain unchanged.
