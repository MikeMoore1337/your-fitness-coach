# ADR: интеграция YFC с health-платформами — discovery Task 96

**Дата проверки:** 2026-09-16 (Europe/Moscow)
**Статус:** OWNER CHECKPOINT PENDING
**Owner decision на запуск:** NARROW GO FOR DISCOVERY ONLY (2026-09-16)

Документ фиксирует bounded discovery и не является разрешением на production
implementation, deployment или переход к Task 97.

## Итог

Владелец подтвердил один продуктовый job: пользователь не должен повторно вводить
в YFC данные, которые уже записаны телефоном, часами, браслетом, весами или
health-приложением. При импорте необходимо сохранить источник, отличить imported
от manual и оставить ручное редактирование.

Это owner/user discovery signal, а не evidence массового спроса:

> single-user/owner signal; broad-market demand not validated

Технический вывод:

1. Текущий React Web/TMA не может напрямую читать Apple HealthKit или Android
   Health Connect. Это inference из официальных native API/capability contracts.
2. Минимальная будущая архитектура — текущие React/Web/TMA и backend плюс тонкий
   native bridge или companion для iOS и Android. Полный новый клиент не нужен.
3. Samsung Health следует покрывать через Health Connect. Отдельный Samsung Health
   Data SDK допустим только при доказанном gap.
4. Huawei Health Kit — отдельный provider path с собственными account, region,
   approval и privacy ограничениями; в первый P0 не входит.
5. Будущий узкий P0: read-only weight, агрегированные steps, completed
   cardio/workout session, тип, start/end/timezone, duration и distance. HR —
   P1, sleep — P2 discovery-only.
6. Для текущего release рекомендация — DEFER UNTIL NATIVE APP. Если native
   foundation появится, на следующий owner checkpoint вынести narrow P0, а не
   импорт всех health data.

## 1. Evidence и текущий baseline YFC

Подтверждено чтением текущего worktree:

- отдельного iOS/Android проекта, HealthKit, Health Connect, Samsung Health или
  Huawei Health integration нет;
- CardioSession в backend/fitminiapp_api/models/cardio.py имеет database
  constraint source = manual; текущие create/update schema и service обслуживают
  manual cardio;
- BodyMeasurement в backend/fitminiapp_api/models/user.py уникален по
  user_id + measured_on; текущий upsert не хранит source/provenance;
- UserProfile хранит IANA timezone; cardio timestamps проходят UTC-normalized
  boundary и возвращаются в timezone пользователя;
- account export включает measurements и cardio, а account deletion удаляет их
  по user ownership;
- frontend package не содержит native runtime или bridge dependency.

Не подтверждено и не выдумывается:

- support tickets, interviews, funnel metrics, cohort size и число
  заинтересованных пользователей;
- реальные permissions, device behavior, store submission, Huawei account/region
  и production sync;
- credentials, real health data, real user accounts, paid APIs и external
  aggregators;
- Garmin, Fitbit, Xiaomi/Mi Fitness, Strava и другие vendor-specific APIs.

## 2. Candidate jobs и граница данных

| Данные / job | Ценность и fallback | Основной риск | Решение |
|---|---|---|---|
| Weight | Measurements и Progress; ручной diary остаётся | Коллизия с ручным замером того же дня | P0 |
| Steps | Factual context в Progress; отсутствие допустимо | Cumulative/overlapping sources | P0, daily aggregate |
| Completed cardio/workout | История активности; manual cardio fallback | Границы сессии и дубликаты | P0 |
| Workout type | Корректная классификация cardio | Нельзя угадывать неизвестный тип | P0 |
| Start/end/timezone | Day boundaries и duration | DST и source offsets | P0 |
| Duration/distance | Существующие cardio-поля | Deterministic units; ничего не синтезировать | P0 |
| HR во время workout / average HR | Описательный контекст cardio | Sensitive data; series не равна aggregate | P1 |
| Resting HR | Только описательный trend | Нельзя делать medical/readiness inference | P1 |
| Sleep duration/summary | Возможный будущий context | Sensitive data и риск переинтерпретации | P2 discovery-only |
| Workout detection | Может убрать ручной start/finish | False positives и большая privacy surface | Defer |
| Notifications | Отдельный product job | Другая permission/delivery модель | Out of scope |

Безусловно запрещено:

- считать calories устройства source of truth;
- добавлять burned calories в дневной лимит КБЖУ;
- создавать medical/readiness score;
- медицински интерпретировать sleep или HR;
- считать отсутствие данных нулём;
- молча перезаписывать manual record;
- скрывать provenance imported и manual.

## 3. Официальные platform findings

Все источники ниже проверены 2026-09-16. Ограничения и terms нужно повторно
проверить на implementation kickoff.

### Apple HealthKit

HealthKit использует native HKHealthStore и granular read/share authorization
по типам данных. Доступ может быть full, limited или absent. Нативное приложение
должно включить HealthKit capability, проверить доступность и добавить purpose
strings в Info.plist.

Для P0 релевантны body mass, steps и workouts; HKWorkout содержит native
identifier, start/end и duration, а также может иметь distance и statistics.
Observer/background-delivery patterns являются нативным механизмом доставки
изменений, но не обещают серверный real-time sync; background/locked states
требуют foreground catch-up.

Следствие для YFC: pure Web/TMA не имеет нужного HealthKit boundary, поэтому
требуется native iOS component.

Источники: [HKHealthStore](https://developer.apple.com/documentation/HealthKit/HKHealthStore),
[Setting up HealthKit](https://developer.apple.com/documentation/healthkit/setting-up-healthkit),
[HKWorkout](https://developer.apple.com/documentation/healthkit/hkworkout),
[Executing observer queries](https://developer.apple.com/documentation/healthkit/executing-observer-queries),
[Protecting user privacy](https://developer.apple.com/documentation/healthkit/protecting-user-privacy),
[App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/).

### Android Health Connect

Health Connect доступен на Android 9 / API 28+ с Google Play services. На Android
14+ это system/framework component, на Android 13 и старше — отдельное Play
приложение. Work profiles не поддерживаются.

P0 mappings: WeightRecord, StepsRecord, ExerciseSessionRecord и при наличии
DistanceRecord. P1 mappings: HeartRateRecord и RestingHeartRateRecord.
SleepSessionRecord остаётся P2. Read permissions выдаются по категориям; обычный
read flow ограничен foreground, а background read требует отдельного permission
и остаётся best effort.

Для incremental sync нужны changes tokens, предпочтительно отдельные по data type.
Deletion change сообщает record ID без record type, поэтому YFC должен хранить
оба значения. Неиспользованный token может истечь в течение 30 дней; recovery —
bounded re-read и deterministic dedupe. Steps нужно получать через provider
aggregation, а не складывать overlapping raw records.

Следствие для YFC: требуется native Android component. Для Google Play понадобится
Health apps declaration и описание используемых Health Connect data types.

Источники: [availability](https://developer.android.com/health-and-fitness/health-connect/availability),
[get started](https://developer.android.com/health-and-fitness/health-connect/get-started),
[data types](https://developer.android.com/health-and-fitness/health-connect/data-types),
[read data](https://developer.android.com/health-and-fitness/health-connect/read-data),
[aggregate data](https://developer.android.com/health-and-fitness/health-connect/aggregate-data),
[sync data](https://developer.android.com/health-and-fitness/health-connect/sync-data),
[Health apps declaration](https://support.google.com/googleplay/android-developer/answer/14738291?hl=en).

### Samsung Health

Основной путь: Samsung Health на телефоне → Health Connect → native Android
bridge YFC. Samsung документирует передачу steps, exercise, HR, sleep и weight
через Health Connect. Continuous Galaxy Watch HR может синхронизироваться с
задержкой из-за battery conservation, поэтому в YFC нужен stale/last-sync state.

Samsung Health Data SDK — только fallback для конкретного отсутствующего datum или
непригодной semantics. Публичное использование требует partner registration и
signature verification; developer mode предназначен для testing, не для end users.
Отдельный SDK создаёт вторую native/permission/support surface.

Источники: [Health Connect FAQ](https://developer.samsung.com/health/health-connect-faq.html),
[access through Health Connect](https://developer.samsung.com/health/blog/en/accessing-samsung-health-data-through-health-connect),
[Data SDK overview](https://developer.samsung.com/health/data/overview.html),
[app verification](https://developer.samsung.com/health/data/guide/app-verification.html),
[developer mode](https://developer.samsung.com/health/data/guide/developer-mode.html).

### Huawei Health Kit

Huawei указывает поддержку Health Kit на Android, iOS, Web, Quick App и HarmonyOS,
но это Huawei-specific API surface, а не универсальное browser permission. Доступ
зависит от HUAWEI ID, explicit scopes, Health Service Kit или cloud/API route,
account country/region, Huawei Health authorization, callback/region routing и
approval/review.

Android device-side путь использует HMS Core / Huawei Health. Cloud path имеет
собственные OAuth и regional endpoint/data-flow constraints. Поэтому Huawei —
отдельная интеграция, а не расширение Health Connect. В первый P0 она не входит,
пока не доказаны Huawei/HarmonyOS audience и конкретный data gap.

Источники: [Health Kit](https://developer.huawei.com/consumer/en/hms/huaweihealth/),
[authorization](https://developer.huawei.com/consumer/en/doc/HMS-Plugin-Guides-V1/signing-in-and-pplying-for-permissions-0000001074001642-V1),
[Health Service Kit Android](https://developer.huawei.com/consumer/en/doc/HMSCore-Guides/android_api-0000001470860649),
[personal data](https://developer.huawei.com/consumer/en/doc/HMSCore-Guides/extended-personal-data-0000001053062445),
[status codes](https://developer.huawei.com/consumer/en/doc/HMSCore-References/hihealthstatuscodes-0000001050089560).

### Deferred vendor APIs

Garmin, Fitbit, Xiaomi/Mi Fitness, Strava и другие direct vendor/cloud APIs не
входят в основной scope: без конкретного YFC audience/data gap они умножат OAuth,
terms, retention, rate-limit и support surface.

## 4. Architecture decision matrix

Рекомендуемая граница:

    iOS Swift HealthKit adapter       Android Kotlin Health Connect adapter
                 \                                  /
                  normalized read-only batch
                                      |
                    existing authenticated YFC backend
                                      |
                    imported health read-model
                                      |
                       React Web / TMA / Progress

Основной интерфейс остаётся React/Web/TMA. Native shell вокруг существующего React
уменьшает account-linking friction. Companion connector лучше изолирует provider
code, но добавляет deep-link, account-linking и lifecycle complexity. Это отдельный
owner decision на implementation kickoff.

| Вариант | Coverage и data | Architecture / Web-TMA limits | Privacy, permissions, store | Sync / provenance | Maintenance, cost, scope, risks |
|---|---|---|---|---|---|
| 1. No-Go | Нет импорта; только manual | Текущий Web/TMA без изменений | Нет новых health permissions/store gates | Нет sync/dedupe | Минимальная стоимость; owner job не решён |
| 2. Defer until native app | Apple + Android остаются будущим направлением | Сначала native foundation; Web/TMA — fallback | Сейчас новых gates нет; позже iOS/Play review обязательны | Sync не строится | Рекомендуемое решение на текущий release; ценность откладывается |
| 3. Native bridge/companion: Apple Health + Health Connect | HealthKit и HC; Samsung через HC; P0/P1 | Swift + Kotlin connector, существующие React/backend; browser local stores недоступны | Granular permissions, HealthKit capability/purpose strings, Play declaration | Native batch; Apple anchors/observers, HC changes tokens; manual precedence | L для текущей небольшой команды, M только при готовом native shell; высокая device/store support нагрузка |
| 4. Вариант 3 + Huawei | Добавляет Huawei/HarmonyOS | Третий native/vendor или cloud OAuth path; Huawei Web не отменяет account/region work | HMS scopes, HUAWEI ID, region/review/privacy constraints | Отдельные cursor/pull/subscription/delete semantics | XL относительно текущего stack; самый высокий approval/support риск |
| 5. Узкий P0 на базе варианта 3 | Weight, steps aggregate, completed cardio/type/time/duration/distance; HR/sleep deferred | Тот же bridge; сначала foreground; real-time не обещается | Только минимальные permissions; manual flow всегда доступен | Bounded initial read, затем cursor; visible source/manual conflict | M/L; предпочтительный будущий slice, но требует двух native platforms |

### Рекомендация

Текущее решение: **DEFER UNTIL NATIVE APP** — не начинать implementation до
появления native foundation и owner responsibility matrix.

Будущее narrow implementation: вариант 5, то есть read-only Apple HealthKit +
Health Connect, Samsung только через Health Connect, Huawei deferred, P0 only,
foreground sync first и best-effort background later. Не включать calories,
readiness, medical semantics, automatic strength-set inference и all-health-data
import.

## 5. Canonical imported-data contract (proposal only)

Это proposal для будущей схемы. В Task 96 не создаются таблица, migration, API type
или production code.

Одна normalized record принадлежит ровно одному authenticated YFC account:

| Поле | Инвариант |
|---|---|
| owner/account | Trusted backend ownership; foreign user ID из browser запрещён |
| datum kind | weight, steps_daily, cardio_session, heart_rate_series, average_heart_rate, resting_heart_rate, sleep_summary |
| activity type | Controlled cardio type; unmappable value становится other |
| value + unit | kg, count, m, seconds или bpm; kcal отсутствует в P0 |
| start/end | Absolute instants в UTC; instant datum имеет одно observation time |
| source timezone | IANA timezone, если доступен, иначе source offset/unknown |
| source platform/app/device | Controlled platform, readable label и coarse device/model; без serial/MAC/advertising ID |
| source record ID/version | Opaque provider identity и version/last-modified, если есть |
| imported at | Server UTC ingestion timestamp |
| provenance/edit status | imported, manual, user_edited; source остаётся видимым после edit |
| quality | Только provider-supplied quality; иначе null |
| lifecycle | active, superseded, source_deleted |
| raw reference | Отдельный короткоживущий encrypted envelope; normalized queries не зависят от raw payload |

Units: weight — kilograms, distance — meters, duration — seconds, steps — integer
count, HR — bpm. UI может показывать kilometers/minutes, но conversion выполняется
один раз на connector boundary.

Хранятся UTC instants плюс source timezone/offset. User-facing day вычисляется в
IANA timezone аккаунта; изменение timezone не переписывает исторический event.
Missing, revoked, unavailable и out-of-window — не zero.

Primary idempotency key:

    (account, source_platform, source_app, datum_kind, source_record_id)

Для Health Connect нужно сохранять record ID и record type: deletion change не
содержит type. Более новая source version обновляет ту же запись по provider
semantics. Reconnect выполняет bounded re-read с тем же key и не создаёт duplicate.

Manual и imported records не объединяются молча. Existing CardioSession с
source = manual и уникальность BodyMeasurement по дню нельзя перезаписывать
импортом. Potential cross-source duplicates связываются или показываются для
review. User edit сохраняет исходное source value для audit/export. Provider
deletion затрагивает только свою imported row; disconnect останавливает новый sync,
но не стирает history без явного действия пользователя или approved retention rule.

Imported cardio не создаёт strength sets, planned workout или nutrition
compensation. Steps — aggregate для Progress, а не workout/calorie input.

## 6. Sync, privacy, security и UX

### Sync lifecycle

- Будущий initial import: последние 30 дней P0, bounded и видимый пользователю.
  Это YFC minimization heuristic, не provider limit; owner должен подтвердить окно.
- Apple: per-type anchored query/cursor, observer как wake-up hint, foreground
  catch-up.
- Health Connect: per-type changes token, upsert/delete processing и bounded
  re-read после expiry; Samsung attribution остаётся видимым.
- Huawei: отдельный adapter только после account/region/approval decision.
- Все connectors: bounded timeout, cancellation, exponential backoff, idempotent
  batch, account-switch cleanup и отдельные revoked/no-data/stale states.
- Feature flag и kill switch обязательны до rollout.

### Privacy и security

- Integration optional; core Web/TMA работает без неё.
- Просить одну category permission после понятного purpose explanation, не на
  first launch.
- Native permission state и credentials — iOS Keychain / Android Keystore
  equivalent, не Web localStorage, URL или analytics.
- Backend ownership и authorization остаются trusted server boundary; native state
  не даёт доступ к чужому account.
- Export включает imported values и provenance. Delete удаляет YFC copy и вызывает
  provider-side deletion только если это разрешено будущим contract и намерением
  пользователя.
- Trainer access не расширяется автоматически. AI Coach не получает imported
  health context без отдельного consented contract.
- Logs/analytics содержат только provider/category/status/count/latency/error
  class, без weight, HR, sleep, raw payloads и tokens.
- Нет diagnosis, treatment, readiness score, medical alert или health claim.
- Device calories не попадают в normalized P0 и никогда не входят в KBJU target.

### Legal/privacy checkpoint

Task 96 не устанавливает legal conclusion. В текущем worktree не подтверждены
hosting country, operator status, primary data location, recipients, retention и
точная jurisdictional audience.

LEGAL_COUNSEL_REQUIRED: YES до production health-data flow.

Нужны ответы:

1. меняют ли Apple/Android/Huawei data flows notices, consents, operator records,
   localization или cross-border controls;
2. какие поля, recipients и retention допустимы для выбранных jurisdictions;
3. остаётся ли fitness-only positioning за пределами medical-service/claim
   boundary.

До решения безопасная позиция — manual-only или disabled internal prototype.
Owner acceptance schedule/cost risk не является legal approval.

### UX concept

Будущая Settings → Integrations card показывает:

- Apple Health, Health Connect или Samsung via Health Connect;
- отдельные categories и permission state: connected, limited, revoked,
  unavailable, no data;
- last sync, stale marker и безопасный error category;
- source badge и manual/imported badge;
- edit manually, delete imported copy, disconnect/revoke;
- manual fallback при любой ошибке или unsupported platform;
- отсутствие обещаний calories added back, readiness или medical score.

В Web/TMA нельзя показывать fake locked entry point или создавать впечатление, что
browser JavaScript читает локальный HealthKit/Health Connect. User validation
концепта до production implementation ещё не проводилась.

## 7. Spike evidence

Native prototype в Task 96 не запускался: в репозитории нет native project/device
harness, а owner разрешил discovery only. Official docs доказывают архитектурную
границу, но не device correctness, permission UX или production readiness.

Минимальный будущий synthetic/non-production spike:

1. разрешить только weight и exercise/cardio;
2. импортировать один weight и одну completed session с type/time/duration/distance;
3. импортировать steps aggregate и проверить отсутствие double count;
4. обновить и удалить один source record;
5. повторить pull и подтвердить idempotency;
6. пересечь imported и manual record и проверить non-destructive provenance;
7. отозвать permission и проверить stop + manual fallback;
8. проверить отсутствие health values/raw/tokens в logs/analytics;
9. проверить isolated export/delete;
10. повторить на Android 14+ и одной старой поддерживаемой версии; Samsung
    проверить при наличии Galaxy test device.

Это deterministic contract evidence, не real-user/provider/production validation.
Credentials и real health data для spike не нужны.

## 8. Cost, risks и owner checkpoint

Официальные platform docs не дают YFC per-record price. Нельзя считать APIs
«бесплатными»: developer accounts/programs, signing, store review, partner
approval, devices, support и policy maintenance остаются затратами. Paid
aggregator не входит в scope и не считается разрешённым без отдельного contract.

Качественная оценка:

| Path | Scope | Ongoing burden | Основной риск |
|---|---|---|---|
| No-Go | S / none | Low | Owner job остаётся нерешённым |
| Defer | S сейчас; native позже | Low сейчас | Delay и зависимость от native capacity |
| Option 3 | L для текущей команды; M при готовом native shell | Medium-high | Две native platforms, stores, permissions и sync correctness |
| Option 4 | XL | High | Третий provider, Huawei region/approval/privacy/support |
| Option 5 | M/L bounded slice | Medium | Уже́ более узкое покрытие, но всё ещё две native platforms |

Owner checkpoint:

1. Финальное disposition: GO, NARROW GO, DEFER или NO-GO.
2. Если NARROW GO — утвердить вариант 5 и Huawei deferred либо другой exact scope.
3. Выбрать native shell или companion и назначить owner native maintenance,
   signing, store review, privacy documents и support.
4. Подтвердить или изменить 30-дневное initial window.
5. Решить, требуется ли Huawei audience/data evidence до roadmap entry.
6. Завершить privacy/legal decision до любого production health-data flow.

До этого checkpoint нельзя начинать production integration, deployment или Task 97.

## 9. Trigger Decision Matrix

Owner signal записан в tracked matrix на этой task branch:

| Task/direction | Evidence source | Baseline | Observed problem/demand | Decision rule | Owner decision | Date |
|---:|---|---|---|---|---|---|
| 96 | Owner/product discovery signal, 2026-09-16 | Current YFC manual cardio/measurement contracts; single-user/owner signal; broad-market demand not validated | No-repeat-manual-entry job across iOS/Android health platforms; target platforms and P0/P1/P2 specified | Compare one concrete datum/platform/job; define safe provenance; no production Go; no invented market evidence | NARROW GO FOR DISCOVERY ONLY; final Go/No-Go/defer pending owner checkpoint | 2026-09-16 |

## Discovery disposition

DISCOVERY COMPLETE FOR OWNER REVIEW; IMPLEMENTATION DEFERRED UNTIL OWNER CHECKPOINT.
