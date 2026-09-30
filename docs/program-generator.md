# Детерминированный подбор программы

Task #510 использует selection policy `program_generator_v1`. Генератор не обращается к AI/LLM,
не создаёт упражнения и не сохраняет программу во время предпросмотра. Источниками служат только
публичные source-backed шаблоны YFC и канонический каталог упражнений.

## API и lifecycle

`POST /api/v1/programs/generator/preview` принимает явные `goal`, `experience`,
`days_per_week` (2–6), желаемую длительность, место, оборудование и необязательные канонические
приоритеты/предпочтения. Backend нормализует значения, отбрасывает hard-incompatible кандидатов,
считает versioned deterministic fit и возвращает либо проверенный draft, либо `no_compatible` с
reason codes.

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

## Provenance

После confirm generated template сохраняет исходный template id/slug, source provenance,
selection policy version, normalized input fingerprint, catalog revision и machine-readable
adaptation ledger в существующих `provenance`/`program_metadata` полях. Numeric score является
внутренним deterministic audit dimension и не показывается как процент совпадения.

Миграция не требуется: используются существующие Product v4 models. Новые production environment
variables и внешние providers не требуются (`env change required: no`).
