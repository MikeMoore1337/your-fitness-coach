# Детерминированный подбор программы

Issue #1335 использует selection policy `program_generator_v2`. Генератор не обращается к AI/LLM,
не создаёт упражнения и не сохраняет программу во время предпросмотра. Источниками служат только
публичные source-backed шаблоны YFC и канонический каталог упражнений.

## API и lifecycle

`POST /api/v1/programs/generator/preview` принимает явные `goal`, `experience`,
`days_per_week` (2–6), желаемую длительность, место, оборудование и необязательные канонические
приоритеты/предпочтения. Backend нормализует значения, отбрасывает hard-incompatible кандидатов,
считает versioned deterministic fit и возвращает либо проверенную программу, либо `no_compatible`.
Успешный ответ содержит `program.days_per_week` отдельно от `program.days` — разных тренировок
исходного цикла. Цель совпадает с запросом, уровень программы не превышает опыт пользователя.

`POST /api/v1/programs/generator/confirm` принимает только подписанный `draft_token`. Backend
повторно проверяет входы, revision активной программы, catalog revision, source template и
ownership. При успехе создаётся private `ProgramTemplate` и назначается через существующие
Product v4 `create_template`/`assign_template_to_user` lifecycle. Повторный confirm того же draft
идемпотентен; изменение параметров запуска даёт `idempotency_conflict`.

До confirm не создаются `ProgramTemplate`, `UserProgram`, revision, workout, audit history или
иное durable program state. Reject и закрытие preview не имеют durable side effect. Trainer-owned active program нельзя заменить
личным generator confirm; active personal program требует явного `replace_active`.

## Selection и adaptation

Порядок выбора фиксирован: provenance/domain validation → hard filtering → fit dimensions →
adaptation → final validation → explanation. Fit учитывает goal, experience, schedule, equipment,
duration, priority muscles, exercise preference и adaptation cost. Stable tie-break использует
adaptation cost, goal/experience fit, substitution/duration costs и canonical `slug`/`id`; random,
current time и physical DB order не используются.

Разрешены только bounded adaptations: canonical equipment substitution и удаление optional
low-priority accessory work при pressure по длительности. Core work, progression-driving
prescriptions, exercise ordering, advanced-set metadata, weekly prescriptions, blocks и deload
semantics не flatten-ятся и не заменяются произвольными правилами. Если безопасный draft не
получается, ответ остаётся `no_compatible` — hard constraints не расслабляются молча.

## Частота и проверенные предложения

`program_metadata.days_per_week` задаёт частоту занятий; `representation_days` описывает исходный
цикл. StrongLifts — три занятия с чередованием A/B, GZCLP — три занятия с непрерывной ротацией
четырёх тренировок. Граница недели не сбрасывает ротацию. Общий путь назначения сохраняет
`day_number` исходной тренировки и календарный `week_number`; лимит материализации считает
фактические занятия, включая повторяющиеся дни. Обычные недельные и восьмидневные циклы сохраняют
свою семантику. Недельные назначения и структурированные подходы копируются до материализации.

Проверка оборудования и исключений охватывает базовые упражнения и все недельные назначения.
Заменами остаются только существующие curated canonical alternatives; сложность замены не может
превышать выбранный опыт. Структурированные и периодизированные упражнения не удаляются ради
длительности. Оценка времени учитывает наиболее длинные недельные назначения, не обещая точного
времени выполнения.

При отказе `message` связывает одну причину с конкретным кандидатом. `reason_codes` больше
не объединяет причины от разных программ. `suggestions` содержит не более трёх вариантов:
`source`, русское описание `changes` и полный объект `inputs`. Каждый вариант проходит ту же
серверную проверку. Предложения сохраняют опыт, место, приоритеты, предпочтения и исключения;
могут явно изменить цель, частоту, время и добавить конкретное оборудование. Они не содержат
`draft_token` и не являются разрешением на назначение.

Кнопка «Применить предложенное изменение» явно принимает перечисленные изменения ответов
и повторно вызывает `/preview`. Сохранение требует отдельного `/confirm` с новым подписанным
токеном. Неподтверждённые изменения не записываются в профиль. Выбор зала не подразумевает
оборудование; пустой список означает упражнения без отдельного инвентаря.

Редактор ревизий пока не умеет перестраивать исходную A/B-ротацию с повторяющимися днями. Для такого назначения
перестройка структуры отклоняется с понятным сообщением до изменения тренировок; отдельную
программу можно создать обычным путём. Это защищает ротацию от схлопывания в недельный шаблон.
Нативные недельные циклы `week_cycle` из #916 используют собственный планировщик и обработчик
ревизий. Их число календарных слотов не выводится из частоты старого источника; ограниченное
окно материализации сохраняется. Это отдельная модель от чередования дней StrongLifts/GZCLP.

## Воспроизведение и матрица #1335

База диагностики: `dev` / `fe0662a35f6fb1a9a5cdec072293dac5f2dbdeae`, 30.10.2026.
Локальное изолированное DEV API использует SQLite в памяти, текущий seed и синтетического
пользователя. Все 16 публичных шаблонов доступны, видны 207 записей упражнений; персональных
production-данных нет. Условия hidden/private/foreign проверяются отдельными отрицательными
тестами. Совпадение seed со спецификацией не подтверждает состояние опубликованного DEV.

Точный воспроизводимый запрос к `POST /api/v1/programs/generator/preview`:

```json
{
  "goal": "recomposition",
  "experience": "beginner",
  "days_per_week": 3,
  "preferred_session_duration_minutes": 60,
  "training_location": "home",
  "available_equipment_ids": ["bodyweight", "dumbbell", "bench"],
  "priority_muscle_ids": [],
  "preferred_exercise_ids": [],
  "excluded_exercise_ids": []
}
```

До исправления этот запрос выбирает `bwf-recommended-routine` с целью `muscle_gain`, несмотря
на запрос `recomposition`. После — `no_compatible` с проверенными предложениями; смена цели
требует явного применения. Для цели `muscle_gain`, beginner × 3 × 45/60 минут с гантелями
сервер возвращает успешную программу без смены цели. Для рекомпозиции beginner × 3 × 45/60
минут с ограниченным набором зала (`bodyweight`, `dumbbell`, `barbell`, `bench`, `cable`, `machine`)
возвращается `strength-fullbody-3d`.

Другой исходный запрос — `strength`, `beginner`, 2 дня, 60 минут, `gym`, оборудование
`["bodyweight", "barbell", "bench"]`, остальные списки пусты — ошибочно принимал StrongLifts
как двухдневную программу. Теперь он предлагает три занятия явно. Независимые тесты выбирают
StrongLifts и GZCLP независимо от ранжирования, подтверждают несколько недель и сверяют
`UserWorkout`, чередование, число занятий, подходы и недельные назначения с источником.

Повторяемая полная матрица:

```powershell
python scripts/program_generator_matrix.py --output .artifacts/runtime/issue1335-matrix.json
# Шесть обычных запросов для быстрой проверки:
python scripts/program_generator_matrix.py --sample --output .artifacts/runtime/issue1335-sample.json
```

Скрипт всегда создаёт собственную БД в памяти, переопределяет унаследованный `DATABASE_URL`,
вызывает настоящий HTTP endpoint через TestClient и не подключается к live БД. Отчёт содержит
полные входы и ответы без токенов, первую причину отказа каждого кандидата, версию каталога и
сравнение числа строк всех таблиц до/после. Скрипт проверяет предложения тем же строгим
валидатором. Отдельные API-регрессии повторно отправляют предложенные ответы через `/preview`.

Фактически проверены 5 целей × 3 уровня × 5 частот (2–6) × 4 длительности (30/45/60/90) ×
4 набора оборудования: собственный вес, гантели, гантели со скамьёй, оснащённый зал.

| Цель | Совместимая программа | Проверенный путь с изменением ответов | Всего |
|---|---:|---:|---:|
| fat_loss | 0 | 240 | 240 |
| recomposition | 20 | 220 | 240 |
| maintenance | 0 | 240 | 240 |
| muscle_gain | 51 | 189 | 240 |
| strength | 18 | 222 | 240 |
| Итого | 89 | 1111 | 1200 |

Записей при подборе не добавилось ни в одной таблице. Проверенный путь означает совместимость
с **новыми** явно перечисленными ответами. В seed нет отдельных fat_loss/maintenance и
двухдневных источников: это пробел покрытия, а не основание переименовывать цель или дублировать
занятия. Невозможные ограничения, например исключение без замены или недоступный источник,
дают отказ без токена и без неподтверждённых обещаний.

Команды локальной регрессии:

```powershell
python -m pytest backend/tests/test_program_generator.py backend/tests/test_issue_396_program_library.py backend/tests/test_program_recommendation.py backend/tests/test_program_versioning.py -q
cd frontend
npm run test -- tests/unit/features/programs/ProgramRecommendation.test.tsx tests/unit/features/programs/programPreviewFacts.test.ts tests/unit/features/programs/TemplatesList.test.tsx
npm run lint
npm run build
npx playwright test app.spec.ts --grep '#1335|детерминированный подбор' --project=chromium --workers=1
# При подготовленной одноразовой PostgreSQL 16 / fitminiapp_test и RUN_MIGRATED_STACK_TEST=1:
npm run e2e:migrated-stack
```

Playwright проверяет 360/390/430 px в обеих темах, применение предложения, повторный запрос,
отсутствие автоматического подтверждения, клавиатуру, фокус, узкий экран и уменьшение высоты.
Его API-фикстуры синтетические; это браузерная регрессия, а не проверка физического iPhone.
Схема FastAPI и TypeScript обновлены вместе. Конкретный CI-статус привязан к head PR в `dev`.

Дополнительно проверен отдельный локальный PostgreSQL 16 с миграцией
`0133_profile_height_numeric`: 7 тестов `tests/integration/test_migrated_stack.py` и 4 браузерных
сценария `frontend/tests/integration/migrated-stack.spec.ts` прошли без подмены API.
Перед браузерным прогоном на такой БД выполняется
`python -m pytest tests/integration/test_migrated_stack.py -q` с `RUN_MIGRATED_STACK_TEST=1`:
этот набор подготавливает проверенный каталог, как и группа migrated-stack в CI.
Явный seed-fixture мигрированной тестовой БД проверяет ровно 16 публичных источников.
Браузерный сценарий #1335 проходит отказ → применение проверенного предложения → новый
предпросмотр без записей → отдельный confirm → идемпотентный повтор → чтение сохранённого
шаблона. Эта БД создана только для проверки; она не является опубликованным DEV или production.

Полный CI выявил устаревшие тестовые ссылки после компоновки Плана: импорт искался в библиотеке,
а кнопки редактора — в старом файле до выделения `ProgramDayEditor`. Падения воспроизведены на
чистой базе `fe0662a3`. Исправлены адреса экрана и проверяемый компонент; проверки импорта,
повторного открытия, добавления упражнений и ограничения числа дней сохранены.

Перед завершением `dev` обновился до `58cdf98f` с #916. Ветка синхронизирована обычным merge;
исходные ротации проверены совместно с нативными циклами. Дополнительный PostgreSQL-прогон:
53 теста подбора и конкурентных операций прошли. Отдельный regression подтверждает, что
30-недельный нативный цикл сохраняет своё окно из четырёх материализованных недель даже
при наличии старого `days_per_week` в metadata.

Опубликованный DEV/PostgreSQL и его migration/seed drift: `NOT_RUN` локальной матрицей;
локальная проверка PostgreSQL и миграционные проверки CI учитываются отдельно. Ручные iPhone Safari/PWA и VoiceOver владельца:
`NOT_RUN`. Production merge/deploy и закрытие Issue этой работой не выполняются.

## Provenance

После confirm generated template сохраняет исходный template id/slug, source provenance,
selection policy version, normalized input fingerprint, catalog revision и machine-readable
adaptation ledger в существующих `provenance`/`program_metadata` полях. Numeric score является
внутренним deterministic audit dimension и не показывается как процент совпадения.

Миграция не требуется: используются существующие Product v4 models. Новые production environment
variables и внешние providers не требуются (`env change required: no`).
