# Issue #996 · быстрый выбор проверенной замены

Статус: **OWNER_SELECTED_VARIANT_02 / FINAL_VISUAL_ACCEPTANCE_PENDING**. Владелец выбрал Variant 02 «Нижний лист» и отдельно зафиксировал композицию footer: **Показать изменения | Отмена** в одной горизонтальной строке, в этом порядке, без переноса на 320/360/393/430 px. Это законченный design/evidence-пакет; production UI, API, application tests, merge и deploy не менялись.

[Issue #996](https://github.com/MikeMoore1337/your-fitness-coach/issues/996) · [галерея прототипа](index.html) · [снимки и manifest](manifest.json) · [точный контракт](contract.md) · [baseline-геометрия](audit/baseline-geometry.json) · [план BEFORE/AFTER и проверок](verification-plan.md).

## Что проверено

- `frontend/src/features/workouts/WorkoutAdaptation.tsx` — текущая последовательность «только в этой тренировке», отдельные preview/apply, offline/409/network/error, `pain_or_injury`, повторное открытие, блокировка двойной отправки, фокус ошибки/preview.
- `backend/fitminiapp_api/api/v1/workouts.py`, `backend/fitminiapp_api/services/workout_adaptation.py`, `backend/fitminiapp_api/schemas/workout.py` — владелец и текущий workout, незапущенный target, equipment subset, видимые/исключённые/уже использованные упражнения, metric match и `preview_token`.
- `frontend/tests/unit/features/workouts/WorkoutAdaptation.test.tsx`, `frontend/tests/e2e/active-workout-experience.spec.ts`, `backend/tests/test_workout_adaptation.py` — существующие границы preview/apply и регрессии.
- Закрытые #860/#861 перепроверены по live Issue/PR истории. Они не реализуют отдельный быстрый выбор #996.

Текущий GET возвращает полный массив `WorkoutAlternativeItem` без `limit`, `offset` и pagination. Поэтому «Все подходящие», поиск и equipment-фильтры в пакете работают только внутри уже полученного полного ответа. Локальный каталог не является клиентским fallback. Если API станет возвращать неполное множество, функция должна быть заблокирована до отдельного API-решения.

## Утверждённая композиция Variant 02

1. В верхней части листа остаётся короткий peek и карточка исходного упражнения.
2. `Все подходящие` раскрывает поиск и фильтры поверх полного ответа сервиса.
3. Кандидат содержит только название, фактически возвращённое оборудование и нейтральную подпись **«Допустимо при выбранном оборудовании»**. Технические `reason_keys` и `score` не показываются; новые причины не придумываются.
4. Footer всегда содержит одну строку `Показать изменения | Отмена`. У кнопок одинаковая ширина, `white-space: nowrap`, минимальная высота 44 px и safe-area padding снизу. В состоянии готового preview кнопка `Применить только сегодня` появляется отдельной строкой ниже и не объединяется с preview.
5. `Показать изменения` только строит preview. До отдельного apply не меняются workout, программа и будущие тренировки.

Порядок keyboard focus в footer совпадает с визуальным порядком: `Показать изменения` → `Отмена`; отдельный apply следует после них. Cancel остаётся доступной при 409, offline, ошибке, пустом списке, зафиксированных подходах и pain/injury. После отмены прототип закрывает лист, возвращает кнопку «Открыть замену снова», а повторное открытие возвращает фокус на close control.

## Пользовательские объяснения

Допустимость объясняется только наблюдаемыми данными текущего ответа: кандидат присутствует в серверном списке и его `equipment_ids` показаны как теги. Недопустимость не маскируется клиентской фильтрацией: пустой ответ, ошибка сети, offline, конфликт актуальности, зафиксированные факты и pain/injury имеют отдельные тексты и disabled-состояния. Никакие технические ключи причины не выводятся напрямую.

## Evidence и BEFORE/AFTER

- `proposal-v2/` — Dark/Light primary-captures Variant 02 для 320/360/393/430 px и 1440 px.
- `states-v2/` — Dark/Light loading, empty, error, offline, conflict/409, pain, started, preview и apply-disabled.
- `audit/baseline-geometry.json` — фактический baseline текущего production-кода: 5 кликов до видимого preview, 4 внутри диалога на 360/393/430, 3 DOM scroll events; preview частично выходил за body viewport.
- `audit/variant-02-geometry.json` — измерения нового статического прототипа: одна строка footer, порядок, отсутствие overflow, safe-area padding, focus и повторное открытие.

Сравнение BEFORE/AFTER не объявляет улучшение кликов до реализации: в implementation stage нужно повторить тот же synthetic fixture, браузер, reduced-motion и viewport height, затем сопоставить click count, scroll events, body/preview rects, footer rects, `scrollWidth/clientWidth`, focus order и request trace. Реальные AFTER Dark/Light и owner visual acceptance остаются отдельным gate.

## Границы

Не меняются backend/API, правила совместимости, RBAC, сохранённые подходы, program/future workouts, AI Coach, Product V12/V14, active-set styles, navigation #867 и preview программ #997. Physical iPhone/Safari, native TMA, OS keyboard, VoiceOver, live production data и production smoke в этой стадии — `NOT_VERIFIED`.

`env change required: no` · `IMPLEMENTATION=false` · `MERGE=false` · `DEPLOY=false` · `NEXT_GATE=OWNER_FINAL_VISUAL_ACCEPTANCE`
