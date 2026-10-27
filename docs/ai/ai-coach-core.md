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
- `rate_limited` — сработала user quota или общий service/provider rate limit; scope возвращается
  отдельно и не выдаёт provider details пользователю;
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

### Пользовательская quota

Лимит AI Coach хранится в PostgreSQL в account-owned `ai_coach_quota_windows`, а короткая
reservation — в content-free `ai_coach_quota_reservations`. Это единый источник для процессов,
workers, вкладок и устройств; `reset_runtime_state()` не сбрасывает данные. По умолчанию
production target — `20` успешных ответов за rolling window `86400` секунд, но limit и window
остаются server-configurable. User и service windows блокируются в стабильном порядке, поэтому
параллельные запросы не oversubscribe quota.

Один пользовательский message резервирует не более одной единицы перед provider-вызовом.
Reservation учитывается временно и после успешного проверенного ответа переводится в `consumed`;
provider timeout/5xx/429, malformed или invalid output, internal error, safety rejection,
validation/context failure и неудачная repair-попытка переводят её в `released`. Одна bounded
repair/internal retry того же message не создаёт новую единицу. Истёкшие reservations безопасно
reclaim-ятся после process crash; старые process-local counters не мигрируются, поэтому при
rollout первая persistent window начинается с первого обращения после deploy.

`GET /api/v1/ai-coach/quota` и conversational response возвращают server-owned snapshot:
`limit`, `used`, `remaining`, точный `reset_at`, `retry_after_seconds` и `can_send`. При
исчерпании user quota provider не вызывается. `rate_limit_scope=user|provider|service` отделяет
личный лимит от provider 429 и общего service limit; provider `Retry-After` используется только
если он надёжно нормализован и не раскрывается как raw HTTP/provider error.

Логи `ai_coach_chat_generation` и quota-события metadata-only: request id, request type/job,
trust class, explicit context kind, версии, provider/model, outcome, safety/failure category,
repair flags, validation reason, latency, attempts, generation success, context/history counts,
quota remaining/limit/reset и nullable usage. Текст запроса, answer, memory, personal facts,
raw provider payload и содержимое reservation в логи не записываются.

Миграция `0086_ai_coach_conversations` добавляет только account-owned history, а additive migration
`0088_ai_coach_durable_quota` добавляет durable quota/reservation, request-key table и metadata для
processing и idempotency. Expand не меняет существующий check `status IN ('complete', 'failed')`:
in-flight сообщение хранится как `failed` с непустым `processing_started_at`, а API сериализует
его эффективный статус как `processing`. Это сохраняет online rollout без table rewrite и
одновременно даёт crash recovery. Account export
включает историю и безопасные display metadata; удаление account удаляет messages перед
conversation shell и quota rows по account cascade. Production helper закрепляет
`AI_COACH_QUOTA_WINDOW_SECONDS=86400` и `AI_COACH_PER_USER_REQUEST_LIMIT=20`; provider, model,
credentials, paid/free policy и existing global protective limit не меняются. Для этой env-части
изменение требуется при следующем production configuration run: `env change required: yes` —
только эти два ключа в persistent host `.env`.
