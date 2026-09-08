# AI Coach: generic foundation and personal read-only boundary

Task 88 добавляет безопасный generic backend-контур для первой beta-версии AI Coach.
Task 89 добавляет отдельный персональный read-only boundary с явным согласием и тремя
allowlisted tools. Ни один контур не заменяет детерминированные расчёты и не включает
публичный chat-интерфейс.

## Разрешённый контур

Аутентифицированный endpoint принимает одну bounded-задачу, короткий запрос и
`context_id`, который сервер уже знает как опубликованный публичный материал:

`POST /api/v1/ai-coach/generate`

Тело запроса имеет только поля `job`, `context_id` и `message`. Клиент не может выбрать
provider, model, system prompt, URL, файл или персональные данные. Backend сам выставляет
trust class `generic`; идентификатор пользователя используется только для серверного
квотирования и не передаётся провайдеру.

Разрешены `app_help`, `public_knowledge`, `metric_explanation`, `fitness_knowledge`,
`nutrition_knowledge` и `progression_explanation`. В context попадает ровно один
опубликованный и актуальный item: reviewed Web Article, статическая публичная guide
страница или allowlisted карточка упражнения. Черновики, архив, retracted-контент,
пользовательские упражнения и произвольные URL исключены.

## Provider boundary

Внутренний контракт `LlmPort.generate(request, policy, context_refs)` отделяет доменную
политику от adapter. Текущий candidate — прямой Groq adapter с fixed HTTPS endpoint и
allowlisted `openai/gpt-oss-120b`. Provider SDK types не выходят из adapter; tools,
streaming, fallback и conversation history отсутствуют.

Каждый prompt и JSON Schema имеют версию в коде. В provider передаются только русский
system policy, bounded request и маркированный как недоверенный public evidence. Strict
structured output проверяется повторно на стороне YFC. В ответе используются только
server-known citations; ссылки из model output не принимаются.

## Safety и состояния

До provider выполняется классификация медицинских, лекарственных/AAS, unsafe,
privacy/exfiltration, action и prompt-injection запросов. После provider проверяются
schema, язык, ссылки, допустимые ref ids и запрещённые фрагменты. При отсутствии
доказательств AI не вызывается.

Endpoint возвращает структурированные состояния:

- `answer` — проверенный ответ с canonical YFC и/или reviewed primary citations;
- `insufficient_data` — подходящего опубликованного контекста нет;
- `safety_refusal` — запрос выходит за безопасную границу;
- `rate_limited` — сработала per-user или global quota;
- `unavailable` — feature flag, kill switch, cost/data policy, cooldown или provider
  недоступны;
- `invalid_output` — ответ провайдера не прошёл валидацию.

Ни одно состояние не раскрывает ключ, raw provider response, prompt, stack trace или
внутреннюю topology. Отказы и ограничения сформулированы по-русски и не маскируются
универсальным медицинским disclaimer.

## Конфигурация и эксплуатационные ограничения

AI Coach выключен по умолчанию. Одного `GROQ_API_KEY` недостаточно для запуска: нужны
отдельно разрешённые `AI_COACH_PROVIDER`, `AI_COACH_ENABLED`, free cost class и
`AI_COACH_DATA_POLICY=verified_generic_only`. Персональный route дополнительно требует
`AI_COACH_PERSONAL_ENABLED=true` и `AI_COACH_PERSONAL_DATA_POLICY=verified_personal_user`;
эти флаги не включаются вместе с generic route автоматически. Отсутствие отдельной
provider/data policy возвращает controlled-unavailable path, а отсутствие или отзыв
согласия — `consent_required`.

`AI_COACH_MAX_ATTEMPTS=1` сохраняет решение initial beta не повторять user-visible
generation и не удваивать стоимость. Контур поддерживает bounded retry для retryable
ошибок при отдельной тестовой/операционной конфигурации; blind failover отсутствует и
остаётся областью Task 92B. 429, timeout, network/5xx и misconfiguration получают
разные внутренние reason codes и cooldown.

Quota и circuit breaker в этой задаче process-local и не требуют миграции или хранения
conversation. Поэтому они являются защитой одного backend process; для горизонтального
масштабирования перед rollout потребуется отдельный подтверждённый shared counter.
Prompt/output не записываются в логи. Логи содержат только request id, job, trust class,
версии, provider/model metadata, outcome, latency, attempts, nullable usage, tool name и
safe error code.
