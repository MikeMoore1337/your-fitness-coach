# Issue #996 · быстрый выбор проверенной замены

Статус: **PROPOSAL / STOP_OWNER_UI_APPROVAL**. Это законченный изолированный UX-прототип и техническая проверка существующего preview/apply; production UI, API, тесты приложения, merge и deploy не менялись.

[Issue #996](https://github.com/MikeMoore1337/your-fitness-coach/issues/996) · [галерея прототипа](index.html) · [снимки и manifest](manifest.json) · [точный контракт](contract.md) · [baseline-геометрия](audit/baseline-geometry.json) · [план проверок](verification-plan.md).

## Что проверено

- `frontend/src/features/workouts/WorkoutAdaptation.tsx` — текущий путь «только в этой тренировке», отдельные `preview` и `apply`, offline/409/network/error, `pain_or_injury`, повторное открытие, блокировка двойной отправки, фокус ошибки/preview.
- `backend/fitminiapp_api/api/v1/workouts.py`, `backend/fitminiapp_api/services/workout_adaptation.py`, `backend/fitminiapp_api/schemas/workout.py` — проверка владельца тренировки, сегодняшнего workout, незапущенного target, доступного оборудования, видимых/исключённых упражнений, метрики и существующего `preview_token`.
- `frontend/tests/unit/features/workouts/WorkoutAdaptation.test.tsx`, `frontend/tests/e2e/active-workout-experience.spec.ts`, `backend/tests/test_workout_adaptation.py` — существующая регрессия preview/apply и защитные границы.
- Закрытые #860/#861 перепроверены по GitHub Issue/PR истории. #860 закрывает исходную ошибку видимости preview/ошибки; #861 относится к отдельному editor picker. Ни одна из них не реализует быстрый выбор #996.

Текущий API уже возвращает полный список для переданного набора оборудования: GET не имеет `limit`, `offset` или пагинации. Поэтому локальный поиск/фильтр в прототипе допустим только как операция над этим конкретным ответом. Если контракт получит пагинацию, лимит или серверную сортировку с потерей хвоста, кнопку «Все подходящие» нельзя реализовывать без отдельного API-решения.

## Три финальных направления

Галерея показывает одно и то же безопасное поведение в трех изолированных направлениях. Переключатели сверху позволяют увидеть `ready`, `expanded`, `loading`, `empty`, `error`, `offline`, `conflict`, `pain`, `started`, `preview` и `apply-disabled`, а также Dark/Light.

| Направление | Идея | Сильная сторона | Риск для проверки |
| --- | --- | --- | --- |
| 01 · Быстрый список | Три наиболее релевантных результата сразу; «Все подходящие» раскрывает полный ответ | Минимум действий для частой замены | В полном списке нужно удержать фокус и введенный поиск |
| 02 · Нижний лист | Короткий peek сверху, поиск и фильтр в раскрываемом слое | Спокойнее на 360–430 px | Нужен корректный возврат фокуса при закрытии слоя |
| 03 · Сравнение | Исходное упражнение и выбранный кандидат видны до preview | Меньше сомнений перед подтверждением | Больше вертикали и текста на узком экране |

Направление не выбирается автоматически: это owner design gate. Все варианты сохраняют текущий YFC material, выбор-токены и русскую локализацию; это не новая глобальная композиция и не работа #997/#1002/#867.

## Данные и границы

Фикстура прототипа обезличенная и синтетическая. Она повторяет форму ответа `WorkoutAlternativeItem` и показывает 3–5 карточек с equipment/reason, чтобы проверить иерархию, но не является доказательством актуального live-каталога. В production карточка должна строиться только из фактически возвращенных сервером `exercise_id`, `title`, `equipment_ids`, `score`, `reason_keys`; локальный каталог не является fallback для UI.

Причины в текущем ответе — технические `reason_keys` (`curated_pair`, `movement_pattern`, `primary_muscle`, `machine_variant`, `execution_variant`). Прототип использует только allowlist и нейтральный fallback. Нельзя обещать пользователю медицинскую, biomechanical или «лучшую» замену по одному ключу. Если нужны новые человекочитаемые причины, это отдельное API/контентное решение после owner approval.

## Preview/apply и состояния

1. Пользователь выбирает только уже полученный и отображаемый кандидат.
2. «Показать изменения» вызывает существующий `POST /api/v1/workouts/{workout_id}/adaptations/preview` с `reason=replace_exercise`, target, replacement и `available_equipment_ids`.
3. До успешного preview workout/program не меняются. Preview показывает transfer/load reset и предупреждения сервера.
4. «Применить только сегодня» отправляет существующий apply с тем же запросом и `preview_token`; повторная отправка блокируется на время запроса.
5. Ошибки сети, offline и 409 остаются видимыми; после 409 старый preview не применяется. `pain_or_injury`, отсутствие вариантов и уже зафиксированные факты блокируют выбор.

Поиск не закрывает клавиатурную сессию: поле остается в DOM, его value сохраняется при перерисовке списка, focus и caret возвращаются в поле. Это проверено только в headless Chromium-модели; native iOS keyboard/TMA/VoiceOver — `NOT_VERIFIED`.

## Фактический baseline до нового выбора

На текущем production-коде (Chromium, synthetic existing `mockActiveWorkout`, light, reduced motion, 360/393/430 × 844) путь от открытия замены до видимого preview потребовал **5 кликов**, из них **4 внутри диалога**. Автопрокрутка тела диалога составляла 3 события; после preview карточка preview частично выходила за нижнюю границу body viewport во всех трех ширинах. Числа сохранены без округления в [`audit/baseline-geometry.json`](audit/baseline-geometry.json); это DOM-измерение, а не оценка физического пользовательского жеста.

Физический iPhone/Safari, нативный Telegram Mini App, OS keyboard, VoiceOver, live production data и production smoke в этой стадии не проверялись.

Основные снимки: [01 Dark mobile](proposal/chromium-393-dark-quick.png), [01 Light mobile](proposal/chromium-393-light-quick.png), [02 Dark desktop](proposal/chromium-1440-dark-sheet.png), [02 Light desktop](proposal/chromium-1440-light-sheet.png), [03 Dark mobile](proposal/chromium-393-dark-compare.png), [03 Light desktop](proposal/chromium-1440-light-compare.png). Все 12 primary-captures и 18 state-captures перечислены в [`manifest.json`](manifest.json); state-captures включают loading, empty, error, offline, conflict, pain, started, preview и apply-disabled в Dark/Light.

## Следующий gate

Нужен один явный owner design approval: выбрать 01/02/03, согласовать тексты/причины и подтвердить, что локальный поиск разрешен только над полным GET-ответом. До этого кодирование нового выбора не начинается. После approval потребуются отдельные implementation checks, реальные AFTER Dark/Light, owner visual acceptance и отдельное разрешение на merge/release.

`env change required: no` · `MERGE=false` · `DEPLOY=false` · `FINAL_STATUS=STOP_OWNER_UI_APPROVAL`
