# AI Coach: conversational foundation and personal read-only boundary

> Historical foundation Tasks 88–89 описывал ограниченный generic/personal rollout. Текущий
> conversational product contract находится в [ai-coach-conversations.md](ai-coach-conversations.md).
> Local defaults остаются disabled; production-доступ определяется server-side policy и
> authenticated user boundary.

В YFC есть два совместимых слоя:

- новый обычный текстовый диалог `POST /api/v1/ai-coach/conversations/{id}/messages`;
- сохранённые legacy endpoints `/generate` и `/personal/generate`, которые нужны для обратной
  совместимости и внутреннего period-report сценария.

Новый пользовательский экран не требует period-report JSON и не показывает внутренние версии,
debug-поля или служебные citation metadata в основном потоке.

## Разрешённый контур

Обычный чат принимает сообщение до 2000 символов. Conversation принадлежит текущему account, а backend
сам выбирает `job`, `context_id`, trust class и bounded context. Клиент не может передать provider,
model, system prompt, URL, файл, SQL, user ID или персональный payload. В provider уходят только
последние bounded turns, выбранные server-known references и текущая задача.

Разрешены `app_help`, `public_knowledge`, `metric_explanation`, `fitness_knowledge`,
`nutrition_knowledge` и `progression_explanation`. Для generic-вопроса используются опубликованные
актуальные Web Article или статические YFC guide pages; черновики, архив, retracted-контент,
пользовательские упражнения и произвольные URL исключены.

Персональный вопрос сначала проходит отдельную проверку consent. Затем один allowlisted read-only
tool возвращает минимальную сводку текущего пользователя: факты, даты, sufficiency, limitations
и fallback path. Tool не меняет canonical data и не получает право выбирать другой пользовательский
контекст. Если фактов недостаточно, provider всё равно получает этот ограниченный срез и сам
формирует естественное уточнение; hardcoded отказ используется только при реальной ошибке источника.

## Provider boundary

Внутренний legacy-контракт `LlmPort.generate(request, policy, context_refs)` отделяет доменную
политику от adapter. Новый чат использует отдельный `ChatLlmPort.generate_text(request,
context_refs)`: plain-text answer без `response_format`, JSON Schema или model-controlled tools.
Legacy period-report path по-прежнему использует строгий структурированный JSON, потому что это
внутренний формат отчёта, а не контракт обычного диалога.

Текущий adapter — прямой Groq adapter с fixed HTTPS endpoint и allowlisted
`openai/gpt-oss-120b`. Provider SDK types не выходят из adapter. Prompt versions, provider draft
cap и пользовательский answer cap задаются server-side. Основная генерация следует bounded retry
policy; форматный ответ может получить ровно одну отдельную plain-text repair-попытку. Blind
failover и новый платный provider не добавляются.

История диалога хранится отдельно от durable memory в account-owned таблицах. В provider попадают
только последние ограниченные сообщения текущего разговора; memory добавляется только для
персонального режима и только при отдельном memory consent. Memory не является evidence и не
может переопределить canonical tool.

## Safety и состояния

До provider выполняется классификация медицинских, лекарственных/AAS, unsafe, privacy/exfiltration,
action и prompt-injection запросов. После provider ответ получает metadata-only reason code:
`too_long`, `wrong_language`, `json_container`, `internal_label`, `url`, `prohibited_claim`,
`unsafe_content` или `other`. Безопасные presentation issues восстанавливаются локально либо
одной plain-text repair-попыткой; safety output (медицина, запрещённые инструкции, секреты,
prompt/privacy leakage) не repair-ится и fail closed. `safety_category=clear` не превращается в
safety error. Обычный чат остаётся plain text; legacy structured report path не меняется.

Основные состояния чата:

- `answer` — проверенный ответ;
- `insufficient_data` — legacy structured path не получил подходящего проверенного контекста;
- `safety_refusal` — запрос выходит за безопасную границу;
- `consent_required` — для персонального вопроса нужно отдельное согласие;
- `rate_limited` — сработала per-user или global quota;
- `unavailable` — feature flag, policy, cooldown или provider недоступны;
- `invalid_output` — форматный текст не удалось безопасно восстановить.

Для технических состояний API использует отдельные `failure_category`: `provider_failure`,
`timeout`, `rate_limit`, `repair_failed`, `presentation_validation_failed`, `internal_error`,
`safety_rejection`, `context_failure` и `generation_failure`. `structured_validation` сохраняется
только для исторических/legacy structured rows и не выдаётся обычным conversational path.
Raw provider errors, stack trace, ключи, prompt и внутренние topology пользователю не выдаются.

## Конфигурация и эксплуатационные ограничения

AI Coach выключен по умолчанию. Одного `GROQ_API_KEY` недостаточно: нужны `AI_COACH_PROVIDER`,
`AI_COACH_ENABLED`, free cost class и `AI_COACH_DATA_POLICY=verified_generic_only`. Персональный
режим дополнительно требует `AI_COACH_PERSONAL_ENABLED=true` и
`AI_COACH_PERSONAL_DATA_POLICY=verified_personal_user`; эти флаги не включаются автоматически.

Quota и cooldown в текущем сервисе process-local и не требуют shared storage. Для горизонтального
масштабирования перед отдельным rollout потребуется подтверждённый shared counter. Логи
`ai_coach_chat_generation` metadata-only: request id, request type/job, trust class, explicit
context kind, версии, provider/model, outcome, safety/failure category, repair flags, validation
reason, latency, attempts, generation success, context/history counts и nullable usage.
Текст запроса, answer, memory, personal facts и raw provider payload в логи не записываются.

Миграция `0086_ai_coach_conversations` добавляет только account-owned history. Account export
включает историю и безопасные display metadata; удаление account удаляет messages перед
conversation shell. Новых environment keys или обязательных credentials для изменения не нужно:
`env change required: no`.
