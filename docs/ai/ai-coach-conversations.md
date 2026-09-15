# AI Coach: conversational product contract

Документ описывает текущий обычный текстовый чат AI Coach. Он дополняет legacy-контракты
периодических отчётов и персональных генераций; эти маршруты не удаляются миграцией UI.

## Пользовательский сценарий

AI Coach открывается из профиля и показывает:

- список сохранённых разговоров и кнопку `Новый чат`;
- обычные сообщения пользователя и AI Coach в одном последовательном потоке;
- composer с Enter для отправки и Shift+Enter для новой строки;
- быстрые вопросы про сегодня, итог за 30 дней, прогресс, отдых и дневник;
- свёрнутые материалы ответа и компактную оценку полезности;
- вторичную секцию отдельной memory, а не memory как основной сценарий.

Основной экран не показывает `report_version`, prompt/schema/debug metadata и не требует
периодического JSON. Обычный чат возвращает самодостаточный текст или безопасный markdown;
периодический JSON остаётся контрактом отдельного legacy-отчёта. Дисклеймер короткий: AI Coach
не заменяет врача или тренера.

## API и хранение

Основные операции:

| Операция | Назначение |
| --- | --- |
| `GET /api/v1/ai-coach/conversations` | Список собственных разговоров с bounded summary |
| `POST /api/v1/ai-coach/conversations` | Создать новый разговор |
| `GET /api/v1/ai-coach/conversations/{id}` | Получить собственную историю |
| `POST /api/v1/ai-coach/conversations/{id}/messages` | Добавить вопрос и получить результат |
| `GET /api/v1/ai-coach/quota` | Получить текущую server-owned quota |
| `DELETE /api/v1/ai-coach/conversations/{id}` | Удалить собственный разговор |
| `POST .../messages/{message_id}/feedback` | Сохранить только helpful/not helpful |

История хранится в `ai_coach_conversations` и `ai_coach_conversation_messages`, принадлежит
account и ограничена 50 разговорами/100 сообщениями. Ввод обычного чата ограничен 2000
символами; для совместимости с прежней проверкой длины первые 1600 символов лежат в старом
поле, а полный ввод — в additive overflow-поле. Сервис чтения и экспорт возвращают полный
текст. Удаление account явно удаляет messages перед conversation shell. Account export
включает историю и безопасные display metadata.

Conversation history и durable memory — разные контуры:

- history нужна для продолжения текущего разговора и содержит bounded отображаемый текст;
- memory хранит только отдельно подтверждённые немедицинские предпочтения;
- фразы пользователя не превращаются в memory автоматически;
- отключение или отзыв memory не удаляет историю диалога;
- удаление разговора не изменяет canonical тренировки, питание, профиль или цели.

## Выбор контекста

Backend не принимает от клиента готовый prompt или произвольный context. Для каждого сообщения
детерминированный selector выбирает `job`, trust class и явный scope контекста:

1. safety classifier блокирует medical, drug/AAS, exfiltration, action и prompt-injection
   запросы до контекста и provider;
2. общий вопрос (`NONE`) может идти в provider с пустым context: отсутствие записей приложения
   не блокирует generation. Проверенные public guides и Web Articles добавляются только как
   релевантное enhancement;
3. вопрос о возможностях приложения получает только capability context. Если подходящего
   материала нет, provider всё равно получает явное ограничение не придумывать функцию;
4. вопрос о личных тренировках, прогрессе, питании или периоде требует personal consent;
5. после consent запускается один allowlisted read-only tool текущего пользователя с минимальным
   scope: профиль/цели, активная программа и расписание, недавние тренировки, история жима или
   сводка питания;
6. в provider передаются только bounded facts, dates и limitations. User ID, Telegram/email,
   trainer notes, raw diary, secrets, ORM objects, внутренние tool names, route paths и schema
   metadata исключены;
7. если персонального среза недостаточно, provider получает доступный ограниченный контекст и
   отвечает естественно: называет отсутствующий факт или задаёт короткий вопрос. Глобального
   hardcoded отказа из-за missing data в обычном чате нет.

Текущие источники истины для app-help и public knowledge — implementation/routes/screens YFC,
опубликованный `frontend/src/content/publicContent.json` и текущие published `WebArticle` rows.
Для personal knowledge источники — существующие canonical services и read-only tools:
`build_progress_summary`, `build_training_analytics`, `build_nutrition_report` и
`build_progress_report`. AI Coach не пересчитывает BMR/TDEE/КБЖУ, прогрессию или другие
канонические показатели.

Периодический отчёт остаётся внутренним/вторичным shortcut: его facts могут быть выбранным
personal context, но обычный чат не обязан возвращать report sections или report JSON.

## Provider и ошибки

`ChatLlmPort.generate_text` — provider-neutral boundary нового чата. Groq adapter отправляет
plain-text messages без `response_format`, structured report schema, tools и model-controlled
loop. В provider реально передаются последние 8 user/assistant сообщений; они не используются
только для UI. Legacy `LlmPort.generate` продолжает обслуживать старые структурированные
endpoints.

Внешние ошибки нормализуются в безопасные состояния:

| API outcome | failure category | Поведение UI |
| --- | --- | --- |
| `safety_refusal` | отсутствует | Понятный отказ по конкретной категории |
| `consent_required` | отсутствует | Предложение явно включить personal consent |
| `insufficient_data` | legacy structured route | Только отдельный периодический/персональный отчёт, не обычный чат |
| `unavailable` | `provider_failure` или `generation_failure` | Общая безопасная ошибка без raw details |
| `unavailable` | `timeout` | Сообщение о таймауте и повторная попытка |
| `rate_limited` | `rate_limit` | Сообщение о лимите |
| `safety_refusal` | `safety_rejection` | Сгенерированный ответ нарушил safety boundary; repair не выполняется |
| `invalid_output` | `repair_failed` | Форматный ответ не удалось безопасно восстановить после одной попытки |

`safety_category=clear` не является safety error. Обычный conversational ответ не использует
structured output или JSON Schema. Безопасные Markdown и обычные английские fitness-термины
(например, RIR/RPE/Top Set) разрешены. Удалимые URL и известные внутренние route labels
сначала очищаются детерминированно; слишком длинный, JSON, неправильный по языку или содержащий
неизвестные служебные поля текст получает не более одной bounded repair-попытки. Если repair не
удался, answer не показывается. Медицинские/лекарственные утверждения, секреты, prompt leakage
и privacy leakage всегда fail closed и не передаются в repair. Персональные citation-ссылки на
внутренние экраны не возвращаются в UI.

Frontend отключает duplicate send во время запроса, показывает loading, сохраняет введённый текст
при сетевом/validation failure и не выводит provider exception. `X-Request-ID` — opaque
idempotency key одного пользовательского turn: повтор с тем же ключом возвращает сохранённый
результат, конфликт с другим текстом отклоняется, а stale processing lease можно безопасно
возобновить. Timeout, retry и reload не должны создавать второй пользовательский запрос или
терять уже сохранённую историю.

## Quota и повторная отправка

`0088_ai_coach_durable_quota` добавляет additive PostgreSQL-таблицы
`ai_coach_quota_windows` и `ai_coach_quota_reservations`, а также metadata processing для
сообщений. Quota хранит только account identity, тип окна, timestamps, limit/counter и opaque
request key; prompt, answer, context и fitness data в quota storage не попадают. Один message
может занять максимум одну reservation. Она считается только после успешного проверенного ответа;
provider timeout/5xx/429, invalid или malformed output, internal/safety/validation failure и
неудачный repair освобождают reservation. Внутренний retry/repair и клиентский replay того же
`X-Request-ID` не расходуют дополнительную единицу.

`GET /api/v1/ai-coach/quota` и response message содержат одинаковый snapshot:

```json
{
  "limit": 20,
  "used": 4,
  "remaining": 16,
  "reset_at": "2026-09-16T12:34:56+03:00",
  "retry_after_seconds": 12345,
  "can_send": true
}
```

Начальный production target — `20` успешных ответов за `86400` секунд; backend остаётся
источником истины и может вернуть другой configured limit. `rate_limit_scope=user|provider|service`
разделяет личное исчерпание от provider 429 и общего service limit. При `user` provider не
вызывается и UI блокирует только Send, сохраняя редактирование draft. При `provider`/`service`
личный counter не меняется. Countdown считает время локально от server `reset_at` или bounded
retry deadline, не делает запрос каждую секунду; refresh выполняется при достижении boundary,
focus/visibility restore, reload или message result. Expired reservation reclaim-ится после
restart/crash, а `reset_runtime_state()` не сбрасывает persistent window. Если backend process
завершился во время `processing`, следующий reload разговора атомарно освобождает reservation и
показывает повторяемый internal failure без списания. Для idempotent replay сохранённые
`provider`/`service` scope и bounded retry deadline возвращаются повторно в send/replay и в
сохранённом failed message при reload, поэтому потерянный response не превращается в новый
provider call и не выглядит как личное исчерпание.

## Privacy, telemetry и эксплуатация

В provider попадают только минимальные данные, нужные конкретному контексту. Generic path не
получает personal data или memory; персональные turns из сохранённой истории отфильтровываются
перед generic generation. Personal path получает memory только при двух активных consent:
personal и memory. Ни один путь не выполняет запись в canonical data.

`ai_coach_chat_generation` содержит только metadata: request id, job, data class, policy/prompt/schema
versions, provider/model, outcome, safety/failure category, `repair_attempted`, `repair_success`,
`validation_failure_reason`, attempts, counts, latency и nullable token usage. В логи не попадают
message text, answer, memory values, personal facts, raw context или secret. Feedback хранит только
категорию helpfulness и не копирует текст.

Новых обязательных provider, платных сервисов или credentials нет. Существующие AI Coach flags и
free-only policy сохраняются. Миграция `0087_ai_coach_long_chat_messages` и новая
`0088_ai_coach_durable_quota` — additive expand без backfill; старые ephemeral counters не
мигрируются, а persistent window создаётся при первом обращении после rollout. Ручная data
migration не требуется. Production configuration run закрепляет
`AI_COACH_QUOTA_WINDOW_SECONDS=86400` и `AI_COACH_PER_USER_REQUEST_LIMIT=20`; других env/provider/
credential changes нет: `env change required: yes` только для этих двух ключей в host `.env`.

## Проверка

Контракт покрывается backend unit/integration тестами для generic, personal consent, follow-up,
provider failure, output reason codes, sanitization, one-shot repair, safety refusal, isolation,
quota persistence/reset/concurrency/idempotency, export/delete и legacy structured adapter;
frontend unit тестами для quota/reload/failure/memory secondary; Playwright browser/mock-TMA
сценариями для desktop, 390px mobile, TMA safe-area, quick prompts, feedback, follow-up, reload
и quota decrement. Физическое Telegram-устройство не подменяет browser/mock-TMA проверку. После
merge и automatic production deployment обязательны отдельные real-provider smoke/evidence для
общих вопросов, app-help, персонального вопроса и follow-up; evidence хранит только provider/model, latency,
request type и generation success, без raw prompt/answer и personal payload.
