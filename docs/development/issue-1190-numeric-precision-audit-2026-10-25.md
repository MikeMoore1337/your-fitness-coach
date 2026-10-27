# #1190 — аудит точности числовых полей YFC

Дата аудита: 25.10.2026
Issue: [#1190](https://github.com/MikeMoore1337/your-fitness-coach/issues/1190)
База первичного аудита: `origin/master` = `605fe95b5c6643427d13edbc5bd48733809ee95b`
Изолированный worktree: `audit/1190-numeric-precision`

Это первичный read-only аудит исходного кода и контрактов, сохранённый как основание для
реализации в текущем PR. `master`, production и связанные потоки #1164/#1184 не менялись.

## Итог

Требование аудита трактуется как сохранение введённого значения в пределах объявленной точности
и возможность ввести `72`, `72.3`, `72.34` с точкой или запятой. Оно не означает перевод
счётчиков, повторов, дней, минут канонического времени или целевых калорий в дробные типы.

Подтверждены по исходному коду следующие дефекты или несовпадения контрактов:

1. Поля дневника замеров тела и пользовательских замеров ограничены `step="0.1"`.
2. Профильный рост ограничен целым числом на UI, принимает `int` в API и хранится в `Integer`;
   это единственный основной путь веса/роста, где дробный рост теряется или отвергается.
3. `ProfileForm`, `CoachPage`, `Diary` и authenticated `NutritionForm` переводят значение через
   `Number(value)` без явной нормализации запятой; также контролируемое числовое состояние
   схлопывает незавершённый черновик `72.` в `72`. Public nutrition calculator нормализует
   запятую, поэтому контракты поверхностно расходятся.
4. Фактический вес подхода ограничен `step="0.5"` в активной тренировке. Разминочный путь
   дополнительно имеет серверное правило шага `0.5` и округляет к половине килограмма.
5. История/отчёты отображают ряд пользовательских весов и замеров с максимумом одним знаком:
   `72.34` становится визуально `72,3`; `ActiveSessionSummary` и completion summary используют
   `toFixed(1)` для веса.
6. Денежные суммы CRM хранятся корректно в integer minor units, но два `type="number"` поля
   не задают `step`; нативный default `1` может отвергнуть `10.34` до уже корректного
   преобразования в 1034 копейки.
7. Ввод часов сна и ручной коррекции отдыха разрешает дробные минуты/часы, но канонически
   округляет их до целых минут/секунд. Это не потеря в БД для канонической единицы, но текущий
   UI-контракт не сохраняет введённое значение в отображаемой единице.
8. Food catalog и nutrition-label схемы принимают `Decimal` без `decimal_places`, тогда как
   `foods`/снимки рецептов имеют `Numeric(10,2)` для энергии и `Numeric(8,3)` для макронутриентов.
   Значения с большей шкалой могут быть округлены БД; это статически подтверждённый разрыв
   API/БД, но фактический PostgreSQL round-trip в этом worktree не запускался.

Отдельно найдено: `PrescriptionLoadTarget.value` и `increment_value` — дробные значения в
программной JSON-модели, без прямого numeric input в текущем просмотренном UI. Для них нужен
явный контракт точности и тест импорта/API, но UI-дефект `stepMismatch` не подтверждён.

## Матрица аудита

Статусы в колонке «факт»: `DEFECT` — ограничение видно в коде и противоречит требованию;
`PASS(static)` — цепочка по исходному коду согласована, runtime round-trip ещё нужен;
`INTENTIONAL` — целочисленность следует из смысла поля; `CONTRACT GAP` — нужно уточнить или
зафиксировать контракт до реализации.

| Экран и поле | Исходный компонент | Frontend-ограничение и парсинг | API / сервер | БД / чтение | Ожидаемая точность | Фактический результат | Минимальное исправление | Требуемый тест |
|---|---|---|---|---|---|---|---|---|
| Дневник тела: вес, грудь, талия, бёдра, бицепс, бедро; custom measurements | `frontend/src/features/diary/Diary.tsx:331-366` | `type=number`, `inputMode=decimal`, `step=0.1`; `Number(e.target.value)` | `BodyMeasurementSave` и `BodyMeasurementCustomValueSave`, `float`, диапазоны, `allow_inf_nan=False` в `backend/fitminiapp_api/schemas/workout.py:902-945`; `services/measurements.py:201-220, 348-353` без округления | `BodyMeasurement.*` и custom `Float`: `backend/fitminiapp_api/models/user.py:215-220, 274+`; миграции `0011`, `0091` | `0.01` кг/см | **DEFECT**: `72.34` не соответствует `step=0.1`; comma/incomplete зависят от native input и обработчика | `step=0.01`; хранить draft строкой до submit; один явный locale-aware parser; не округлять save/read | UI WebKit/Chromium; API `72/72.3/72.34`; comma; `72.`; min/max/NaN; DB round-trip; history/report/export |
| Профиль: рост | `frontend/src/features/profile/ProfileForm.tsx:210,475-487`; `frontend/src/pages/coach/CoachPage.tsx:324-330` | `step=1` либо default step `1`, numeric state через `Number` | `UserProfileUpdate.height_cm: int` в `backend/fitminiapp_api/schemas/user.py:129,237` | `UserProfile.height_cm: Integer` в `backend/fitminiapp_api/models/user.py:135`; исходно `0001`; обратного перехода для height нет | `0.01` см | **DEFECT**: `175.34` не проходит API/БД; профильный UI расходится с nutrition target | Отдельная additive migration к decimal-capable type и API contract; затем профильные Web/TMA/coach inputs; existing integer rows должны сохраниться | migration upgrade/downgrade policy; legacy rows; API 175/175.3/175.34; readback; generated OpenAPI/types |
| Профиль: вес | `ProfileForm.tsx:498-508`; `CoachPage.tsx:335-341` | `step=0.1`, `Number(value)`, no explicit comma parser | `weight_kg: float`, range, `allow_inf_nan=False` | `UserProfile.weight_kg: Float`; migration `0022` перевела legacy `Integer` в `Float` | `0.01` кг | **DEFECT(UI/locale)**: backend способен принять 72.34, UI native step — нет; comma path не унифицирован | `step=0.01`, string draft/parser, exact display; не менять weight model без доказанной необходимости | all three values, comma, incomplete draft, API/storage/readback |
| Nutrition target: вес и рост | `frontend/src/features/nutrition/NutritionForm.tsx:157-161,249-281`; `PublicNutritionCalculator.tsx:122-126,210-232` | authenticated form: `step=0.1`, `Number`; public form: `replace(',', '.')`, `step=0.1`; age/счётчики `step=1` | `NutritionCalculatorInput.weight_cm/height_cm/age: float`, ranges, `allow_inf_nan=False` в `schemas/nutrition.py:47-49` | `NutritionTarget.weight_kg/height_cm/age: Float`, `models/nutrition.py:62-64`; migration `0007` | вес/рост `0.01`; возраст — целые годы | **DEFECT** для weight/height UI; age — **CONTRACT GAP**: API/model float, UI/business integer | weight/height local input fix; age либо явно ужесточить до integer, либо документировать дробный возраст и добавить `0.01` | authenticated/public parity; comma; `72.`; API; calculator output; history target |
| Активная тренировка: фактический вес подхода | `frontend/src/features/workouts/TodayWorkout.tsx:825-860`; queue `useActiveWorkoutQueue.ts:193-199` | `step=0.5`, decimal input; draft string в queue | `WorkoutSetUpdate.actual_weight: float >=0` в `schemas/workout.py:140-143`; PATCH `/api/v1/workouts/sets/{set_id}` | `UserWorkoutSet.actual_weight: Float`, `models/program.py:568-572`; raw serialization/analytics use float | `0.01` кг для фактической нагрузки | **DEFECT(UI)**: backend path не ограничивает десятыми, но native UI блокирует сотые; reports may round | `step=0.01`; preserve queue string until validated; formatters with at least 2 significant fractional digits where exact value is shown | PATCH and offline retry with 72.34; idempotency/version; analytics volume; read/history/export |
| Разминочный вес и рабочий вес warmup proposal | `frontend/src/features/workouts/WarmupProposal.tsx:288-315` | `step=0.5` | `backend/fitminiapp_api/services/warmup_proposals.py:51-56,78-123`: `_is_half_increment`, `_round_to_half`, explicit 0.5 error | materializes to `UserWorkoutSet.actual_weight` Float | если это пользовательская нагрузка — `0.01`; если это ограничение доступного инвентаря — `0.5` | **DEFECT или INTENTIONAL — требует доменного решения**: сервер подтверждённо не принимает `72.34` | Не менять массово: сначала выбрать контракт warmup; при fractional policy убрать half-only только локально и сохранить отдельную plate/inventory policy | negative test `72.34`; generated proposal; apply; no unintended change to normal set path |
| Кардио: дистанция | `frontend/src/features/cardio/CardioLogging.tsx:356-360`; `TodayWorkout.tsx:1394-1398` | `step=0.01`, min `.01`; raw string до submit | `CardioSessionFields`/update `distance_km: float`, `allow_inf_nan=False`; `schemas/cardio.py:20-53` | cardio session `Numeric(7,2)` в `models/cardio.py:65`, migration `0058`; workout-set distance отдельно остаётся `Float` | `0.01` км | **PASS(static)** для CardioSession; consistency risk because workout-set distance uses Float | закрепить API/DB round-trip test; не менять уже подходящий cardio schema без необходимости | 72/72.3/72.34 km; 1000 boundary; null; report/export; workout-set parity |
| Питание: порции diary/plan/recipe/grocery/template | `FoodPickerDialog.tsx:899-1079`; `MealPlanner.tsx:296-505`; `NutritionDiary.tsx:361`; `FoodEditor.tsx:423-459`; `RecipeBrowser.tsx:275-342`; `GroceryList.tsx:173-435`; `MealTemplateBrowser.tsx:404-407` | food/recipe inputs `step=any`, meal/grocery `step=0.001`; большинство submit paths нормализуют comma | `Decimal` с `decimal_places=3` в `schemas/food_diary.py:65,86`, `nutrition_plan.py`, `recipe.py`, `grocery_list.py`, `nutrition_power.py` | `Numeric(10,3)`/`Numeric(12,3)`/`Numeric(10,3)` в соответствующих models | минимум `0.01`; фактически поддерживается до `0.001` | **PASS(static)** для основных amount paths; incomplete draft должен оставаться строкой до submit | оставить scale 3; не делать общий parser в passthrough `Input`; добавить единые тесты locale/blank/validation | `0.01`, `0.001`, comma, `72.`, negative/zero, API 422, DB/readback, repeated edit |
| Питательные факты продукта и label/photo confirmation | `FoodEditor.tsx:60-99`; `NutritionLabelReview.tsx:459-790`; `PhotoMealScanner.tsx:350-419` | input `step=any`; local paths mostly `replace(',', '.')`; label draft uses string inputs | `schemas/food.py:49-62,115-150` и `schemas/nutrition_label.py:30-44` use `Decimal` without explicit scale; photo schema has 2/3 places | `Food` and recipe snapshots: energy `Numeric(10,2)`, macros/fiber `Numeric(8,3)`; label draft canonical payload is JSON | energy `0.01`, macros/amounts at least `0.01`, current storage up to 3 for macros | **CONTRACT GAP**: API can accept more fractional places than DB preserves; DB round-trip not run | add explicit API decimal scale matching columns; verify canonical draft → confirmed Food path; preserve existing 2/3-place rows | API over-scale rejection; `72.34`; `72.3456` boundary; label draft/read/confirm; food catalog and export |
| Nutrition targets: calories, protein, fat, carbs | `ManualNutritionTargetForm.tsx:126-173` and nutrition form outputs | `step=1`, numeric keyboard | `NutritionManualTargetSave` fields `int` in `schemas/nutrition.py:87-92` | `NutritionTarget` target columns `Integer`, `models/nutrition.py:92-97`; service rounds calculated outputs | whole kcal/gram target by product contract | **INTENTIONAL** integer-only; no evidence to make target units fractional | keep integer contract; test rejection of `72.34`, not acceptance | API/UI negative fractional tests; calculation output remains integer; history unchanged |
| Гидратация: объём цели/напитка/пресета | `HydrationTracker.tsx:112-115,475-478,629-690` | numeric keyboard, integer inputs | `HydrationGoalSave.target_ml: int`, entry schemas int | `HydrationGoal/Entry/Preset.*_ml: Integer`, `models/hydration.py:55,96,122`; migration `0068` | whole ml | **INTENTIONAL** physical measurement unit is ml, current integer contract | no change; if product later wants fractional litres, add a separate unit contract rather than weaken ml | integer boundary, zero/max, account export/readback |
| Сон и ручная коррекция отдыха | `DailyWellbeingCheckIn.tsx:62-87,523-539`; `TodayWorkout.tsx:1992-2027`; `restSessions.ts` | text decimal; comma supported; converts with `Math.round(hours*60)` / `Math.round(minutes*60)` | wellbeing API `sleep_duration_minutes: int` in `schemas/daily_wellbeing.py:10-23`; recovery correction is local seconds | wellbeing `Integer` minutes, local rest journal stores integer seconds | canonical unit: 1 minute/second; if UI promises fractional hours/minutes, input precision must be explicitly defined | **CONTRACT GAP/DEFECT(UI semantics)**: `7.51` hours and `2.51` minutes are rounded on conversion and read back differently | choose canonical unit and expose matching step/label; do not silently promise arbitrary hundredths | `7,5`, `7.51`, `2,5`, boundary 0/1440, draft/error recovery, readback/history |
| Программы: повторы, подходы, длительность, отдых, недели, дни, группы | `ProgramBuilder.tsx:652-1018`; `TrainingPreferencesForm.tsx:268-287`; `CoachProgramBulkOperations.tsx:826-861`; `ExerciseCatalog.tsx:795-871`; `TemplatesList.tsx:974` | numeric inputs are integer/default step 1; reps may be textual range (`5-8`, `5+`) | `schemas/program.py:425-430,505-506,523-528` and related fields are `int`; model `program.py:141-148,193-199,245-249,523-532` is `Integer` | integer columns/JSON semantics | whole repetitions, sets, minutes, seconds, weeks/days/group IDs | **INTENTIONAL**; not a fractional-measurement defect | preserve, add explicit integer negative tests; do not alter shared input globally | reject `1.5` reps/sets/days; preserve text range semantics; API/DB round-trip |
| Программы: load target/increment | `backend/fitminiapp_api/schemas/program.py:162-169,365-366`; frontend display `ProgramImportPanel.tsx:106-213`, `ProgressionGuidance.tsx:72-108` | no direct numeric form found in audited UI; display uses locale formatting | `float` with range, no explicit `decimal_places`; values travel in prescription JSON | `program.py` JSON (`prescription`/metadata), no SQL scale | absolute kg/increment `0.01`; percentages need explicit unit precision | **CONTRACT GAP**: API/JSON path is fractional-capable but lacks declared scale and direct input evidence | document per-unit scale and add API/import validation; do not refactor program model | import/API 72.34; percent boundaries; JSON round-trip; progression calculation and report |
| Настройки уведомлений и training preferences | `NotificationsPanel.tsx:228-285,263-268`; `TrainingPreferencesForm.tsx:268-287` | intervals/minutes/counts use integer `step=1/15/30` or native default | notification schemas/models use integer hours/minutes/counts; training preference durations are integer | integer columns/contract | whole minutes, occurrences, hours, durations | **INTENTIONAL** discrete scheduling/count fields | keep integer; verify native defaults are explicit where useful | API/UI boundary and invalid fractional rejection |
| CRM: длительность/количество; суммы оплат | `CoachOperationsPanel.tsx:675,756,875-899` | counts/duration integer; payment inputs have `inputMode=decimal`, `min=0`, no `step` | payment submit normalizes comma and `Math.round(Number(value)*100)`; request uses minor integer | CRM payment fields are integer minor units; other quantities integer | amount input `0.01` currency; storage exact cents | **DEFECT(UI)** only for payment controls; storage design is correct | set `step=0.01`; keep minor-unit API/DB; retain raw draft and explicit decimal parser | `10`, `10.3`, `10.34`, comma, incomplete, 0/negative, expected ≥ paid, API/readback |
| Публичные BMI/1RM/nutrition calculators | `PublicBmiCalculator.tsx:13-17,88-105`; `PublicOneRepMaxCalculator.tsx:146-169`; `PublicNutritionCalculator.tsx` above | BMI/1RM use text + decimal keyboard and explicit comma parser; nutrition currently number + numeric state | BMI/1RM are client-only; nutrition API accepts floats | no persistence | input weight/height/load `0.01`; computed BMI/1RM display may have domain-specific rounding | BMI/1RM parser supports comma/incomplete text; public nutrition still `step=0.1` | fix public nutrition input; keep BMI display 1 decimal only if product means computed BMI, not source measurement | WebKit/Chromium input; submit/error; output and no persistence |
| История, отчёты, аналитика, export | `ProgressReportPage.tsx:116-118,406-407,678,711-721`; `ProgressExperience.tsx:90-92,207,246,949`; `ActiveSessionSummary.tsx:13-24`; `WorkoutCompletionSummary.tsx:46-50` | formatters use max 1 digit/toFixed(1) for weights/body trends; some distance uses 2 | backend `serialize_measurement` returns raw floats; progress points raw, `change=round(...,2)` at `services/progress.py:229-263`; analytics computes float volume | export serializers select raw numeric fields | show at least `0.01` where exact user measurement/load is being reported; computed aggregates may have separate precision | **DEFECT(presentation)**: stored `72.34` can be shown as `72,3`; raw API/export not proven to round | split formatters by semantic field; do not change computed percentage/integer labels; keep raw API/export | seed synthetic 72.34, verify API/history/report/chart aria/export/statistics; check volume rounding policy |

## Полная инвентаризация компонентов

Поиск выполнялся не только по `step=0.1`, но и по `type="number"`, `inputMode`, `step`,
`Number`, `parseFloat`/`parseInt`, `Math.round`, `toFixed`, `maximumFractionDigits`, Pydantic
`float`/`Decimal`, SQLAlchemy `Float`/`Numeric`/`Integer` и migration definitions.

Найденные пользовательские numeric surfaces:

- замеры: `Diary`, profile/coach profile, nutrition calculator, custom measurements;
- тренировки: actual weight/reps, cardio distance/duration/heart rate, warmup, plate calculator,
  exercise assignment and workout adaptation;
- nutrition: food editor, food picker, quick add, diary, natural input, meal planner, meal
  templates, recipes, grocery list, photo meal, nutrition label review, hydration and manual
  targets;
- programs: sets/reps/rest/duration/weeks/days/groups, imported/progression load values;
- wellbeing/recovery: sleep hours and manual rest correction;
- account/CRM: notifications, training preferences, payment amounts and integer counts;
- public calculators: BMI, nutrition and one-rep max;
- reusable control: `frontend/src/shared/ui/common.tsx:81-82` is a pure `Input` passthrough and
  does not own numeric parsing or step policy. A global change there would affect integer fields,
  so it is not a safe one-line fix.

Integer-only inventory with the reason recorded below:

- repetitions, sets, rounds, AMRAP caps, superset/group positions;
- days, weekdays, weeks, occurrences, package/session counts;
- prescribed and actual duration in minutes, rest in seconds, heart rate BPM and zones;
- hydration volumes in canonical millilitres;
- wellbeing quality/mood ratings and canonical sleep minutes;
- calories/macronutrient target values, which are currently product-level integer targets;
- barcode digits, IDs and other identifiers (numeric-looking strings, not quantities);
- plate count and bar/plate calculator `step=0.5`: physical inventory choice, no persistence;
- money storage in integer cents: storage is intentionally integer, but the user-facing amount is
  a decimal currency quantity and therefore remains in the fractional audit.

## Цепочка данных и обратная совместимость

### UI → parser → validation

Строка `72.34` сохраняет значение в public text/nutrition amount paths, но numeric state handlers
в profile/diary/authenticated nutrition convert immediately. The JavaScript synthetic check on this
worktree produced:

```text
Number("72")       = 72
Number("72.3")     = 72.3
Number("72.34")    = 72.34
Number("72.")      = 72
Number("72,34")    = NaN
Number("72,34".replace(",", ".")) = 72.34
```

Тот же assert-based synthetic run подтвердил `Math.round(7.51 * 60) = 451`,
`Math.round(2.51 * 60) = 151` и `(72.34).toFixed(1) = "72.3"`.

`stepMismatch` в этом worktree не исполнялся в браузере, но HTML-контракт виден статически:
decimal input с `step="0.1"` не принимает значение, не выровненное по этому шагу; без `step`
используется native default для number input. Для точного поведения событий и локали WebKit и
Chromium нужен отдельный браузерный прогон.

### API → DB

- Body measurements and workout weights use Python/SQLAlchemy `float`/`Float` and do not round in
  the save/serialize path. This is not proof of exact decimal storage; a PostgreSQL round-trip is
  required.
- Cardio session distance already has `Numeric(7,2)` and matching `0.01` UI/API intent.
- Nutrition amount/macro paths use `Decimal` plus scale-3/scale-2 columns, which is sufficient for
  the owner requirement. Food master/label input schemas are the exception because their API
  scale is not declared while the columns are.
- Profile height is the confirmed hard loss point: API `int` plus DB `Integer`.
- Existing integer values must remain valid in any future height migration. No migration was
  authored in this audit.

### Read → history → reports → export

`serialize_measurement` and the progress service pass raw values to the API, and the account export
selects raw measurement/workout/nutrition fields. The visible loss is in formatters: report and
progress UI defaults to one fractional digit. The implementation must not solve a presentation
problem by rounding stored values.

Для workout sets найдено важное ограничение доказательства: `WorkoutSetCreate` в
`backend/fitminiapp_api/schemas/workout.py:128-135` не задаёт отдельную проверку диапазона или
конечности `actual_weight`, но текущий пользовательский PATCH-маршрут использует
`WorkoutSetUpdate` (`backend/fitminiapp_api/api/v1/workouts.py:1327-1330`) с `float >= 0`.
Поэтому отсутствие ограничений у legacy/create-контракта отмечено как поверхность для
отдельного теста, а не как подтверждённая потеря точности.

## Подтверждённые дефекты и границы доказательства

| ID | Статус | Доказательство | Риск |
|---|---|---|---|
| NUM-D01 | `CONFIRMED` | `Diary.tsx` standard/custom `step=0.1` | user cannot enter two decimal body values through the main measurement UI |
| NUM-D02 | `CONFIRMED` | profile height `int` + `Integer` | fractional height is rejected/lost; migration compatibility required |
| NUM-D03 | `CONFIRMED` | numeric state `Number(value)` and no comma normalization in profile/diary/auth nutrition | locale and incomplete drafts are not a uniform contract; exact browser symptom still needs E2E |
| NUM-D04 | `CONFIRMED` | TodayWorkout and Warmup UI `step=0.5`; warmup service half-increment validation | actual fractional loads are blocked; warmup may be an intentional physical constraint |
| NUM-D05 | `CONFIRMED` | report/progress `maximumFractionDigits=1`, summaries `toFixed(1)` | exact values remain in API but are visually misreported |
| NUM-D06 | `CONFIRMED` | CRM payment inputs omit `step`; submit converts to cents only after native validation | valid cents can be blocked before submit |
| NUM-D07 | `CONFIRMED CONTRACT GAP` | sleep/recovery fractional display units are rounded to canonical integer minutes/seconds | user-visible value may not round-trip in entered unit |
| NUM-D08 | `CONFIRMED CONTRACT GAP` | Food/label API Decimal scale does not match explicit SQL scale | values beyond column scale may be silently rounded by DB |
| NUM-D09 | `NOT_PROVEN` | body/workout `Float` has no declared decimal scale | exact binary/JSON/DB round-trip needs PostgreSQL/API test; do not infer data loss from type alone |
| NUM-D10 | `NOT_PROVEN` | WebKit/iOS native `type=number` comma and `stepMismatch` event behavior | requires real WebKit/Chromium browser run and iOS device evidence |

## Минимальный план реализации после подготовки

1. **Contract first:** owner confirms fractional policy for profile height, actual/warmup load,
   sleep/recovery display units, progression kg/percent, and nutrition target integers.
2. **Small UI fixes:** change only affected fractional controls to `step="0.01"` (or the
   already-declared nutrition scale where finer input is intentional); keep integer fields local.
   Keep strings during editing, normalize `.`/`,` at submit, reject blank/NaN/infinite values with
   field errors. Do not change the shared passthrough `Input` globally.
3. **Profile height separately:** add the smallest additive compatible API/DB migration, preserve
   existing integer rows, update profile/coach/nutrition payloads and generated types, then verify
   all callers before changing the server contract.
4. **Server scale alignment:** add explicit Pydantic decimal places to food/label inputs matching
   existing `Numeric` columns; do not add a new abstraction or rewrite all nutrition models.
5. **Display-only corrections:** use field-specific formatters for exact body/load/distance values;
   retain deliberate integer/one-decimal presentation for computed BMI, percentages and target
   outputs.
6. **Warmup decision:** if half-kilogram increments are required by available plates, document and
   test that exception. If owner requirement applies to warmup too, change only warmup validation
   and its tests, not the general program model.

## План тестирования

### Unit/API/DB cases

| ID | Precondition/action | Expected oracle |
|---|---|---|
| NUM-T01 | submit `72`, `72.3`, `72.34` for every fractional measurement/load family | accepted where policy is fractional; returned value equals input at declared scale |
| NUM-T02 | submit `72,34`, `72.`, empty draft | comma accepted where locale contract exists; incomplete/empty is not persisted and does not become zero silently |
| NUM-T03 | min/max, just below/above, `0`, negative, `NaN`, `Infinity` | field-level 422/UI error; no row or queue mutation |
| NUM-T04 | API direct `72.34` bypassing UI | server accepts/rejects according to field contract, never relies on HTML `step` |
| NUM-T05 | DB insert/read/JSON serialize `72.34` and `72.345` | exact declared scale is preserved; over-scale inputs are rejected before DB or explicitly rounded by contract |
| NUM-T06 | edit existing integer record, then read history/report/export | value remains valid and unchanged; no destructive migration behavior |
| NUM-T07 | nutrition amount/macro `0.01`, `0.001`, over-scale value | Decimal schema, SQL scale and response/export agree |
| NUM-T08 | integer-only negative cases (`1.5` reps/sets/days, fractional hydration ml/target macros) | rejected intentionally; no broad decimal relaxation |
| NUM-T09 | payment `10`, `10.3`, `10.34`, `10,34`, blank and paid > expected | cents are exactly 1000/1030/1034; invalid business relation remains rejected |
| NUM-T10 | offline workout queue retry/version conflict with `72.34` | value survives queue, retry and idempotent replay; no rounding in analytics |
| NUM-T11 | sleep `7,5`, `7.51`; recovery `2,5`, `2.51` | behavior matches the chosen canonical unit contract and readback display |

### Browser/mobile cases

- `@playwright/test` in Chromium and WebKit at 360, 390 and 430 CSS px for measurement,
  profile, workout, nutrition and payment inputs.
- Real iOS Safari/WebKit: decimal keyboard, `.`/`,` locale, `72.` draft, validation focus and
  exact save/readback. This is evidence for #1190, not a fix for #1189.
- Check `stepMismatch`, min/max, error announcement, keyboard focus, draft recovery and submit
  retry. Keyboard positioning/scrolling is tracked separately in [#1189](https://github.com/MikeMoore1337/your-fitness-coach/issues/1189).

### Статус первичного read-only аудита

- `PASS`: source inventory, API/model/migration mapping, static caller search, synthetic Node
  parser/rounding assertions.
- `NOT_RUN`: frontend unit/E2E and backend pytest/API/DB integration; this clean worktree has no
  installed `frontend/node_modules` or backend `.venv` dependencies.
- `NOT_RUN`: PostgreSQL numeric round-trip and generated OpenAPI/types regeneration.
- `NOT_PROVEN`: physical iOS keyboard behavior, production records, production reports and
  production deployment.

## Риски и зависимости

- Changing profile height crosses API, generated frontend types, Pydantic, SQLAlchemy, migration,
  profile/coach forms, nutrition target projections and reports. It must not be hidden in a UI-only
  patch.
- `Float` is adequate for many ordinary values but does not provide a declared decimal scale;
  converting every existing float column to `Numeric` would be a migration and compatibility
  decision, not a safe audit-stage cleanup.
- `#1164` and `#1184` are concurrent streams; this report does not touch their files or scope.
- `#1189` is a separate keyboard viewport/focus issue. Numeric parser/input changes must preserve
  its reproduction coverage and must not claim to fix its visual positioning.
- Green local/static checks cannot prove physical-device behavior, production data integrity,
  owner visual acceptance, merge or deployment.

## Проверка реализации в PR #1218 (25.10.2026)

В существующей ветке `fix/1190-numeric-precision` реализована минимальная сквозная часть
аудита: строковые decimal-draft на затронутых UI-полях, нормализация точки/запятой на submit,
явные scale-ограничения API, Numeric-колонки для пользовательских дробных значений,
fail-closed миграция без скрытого округления и точное форматирование истории/отчётов. Целевые
значения `72`, `72.3`, `72.34`, `72,34`, рост `178.25`, фактический вес `42.25` и дистанция
`5.24` покрыты локальными API/DB/readback/export проверками. Целочисленные цели питания,
повторы, длительности, hydration и другие дискретные единицы оставлены целочисленными.

Проведённые проверки:

- `PASS`: backend targeted pytest — 67 тестов, включая API/DB round-trip, историю, export,
  warmup `42.25`, schema scale rejection и migration fail-closed на `178.251`.
- `PASS`: полный backend runner — 1673 теста, 38 skipped; один отдельный Windows baseline
  failure в `test_deployment_smoke` из-за Unix-only `pwd` import воспроизводится и на audit
  baseline и не затрагивает этот PR.
- `PASS`: frontend unit — 160 файлов, 1003 теста; typecheck, lint, Prettier с
  `--end-of-line auto`, build, `perf:check` и generated OpenAPI/types regeneration.
- `PASS`: Chromium и WebKit для точечного #1190 Playwright сценария сохранения `72.34`;
  отдельный mobile input-contract сценарий — 2/2.
- `FAIL / NOT_PROVEN`: mobile critical suite — 46/52 теста прошли; 6 snapshot-расхождений
  остались после исправления 2 прямых ожиданий `input[type=number]` (focused rerun 2/2) и 6
  snapshot-расхождений progress/active-workout. Snapshot-расхождения не замаскированы
  обновлением эталонов: они затрагивают уже существующий текст/композицию и требуют отдельной
  визуальной сверки владельца.
- `NOT_RUN / NOT_VERIFIED`: PostgreSQL 16 round-trip, реальный Telegram runtime, физические
  iOS/Android, production records/reports, owner visual acceptance, merge и deploy.

Известное ограничение контракта: sleep hours по-прежнему переводятся в канонические целые
минуты через `Math.round`; поэтому произвольные сотые часа не заявляются как exact readback.
