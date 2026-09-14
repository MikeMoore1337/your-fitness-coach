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
периодического JSON. Дисклеймер короткий: AI Coach не заменяет врача или тренера.

## API и хранение

Основные операции:

| Операция | Назначение |
| --- | --- |
| `GET /api/v1/ai-coach/conversations` | Список собственных разговоров с bounded summary |
| `POST /api/v1/ai-coach/conversations` | Создать новый разговор |
| `GET /api/v1/ai-coach/conversations/{id}` | Получить собственную историю |
| `POST /api/v1/ai-coach/conversations/{id}/messages` | Добавить вопрос и получить результат |
| `DELETE /api/v1/ai-coach/conversations/{id}` | Удалить собственный разговор |
| `POST .../messages/{message_id}/feedback` | Сохранить только helpful/not helpful |

История хранится в `ai_coach_conversations` и `ai_coach_conversation_messages`, принадлежит
account и ограничена 50 разговорами/100 сообщениями. Удаление account явно удаляет messages
перед conversation shell. Account export включает историю и безопасные display metadata.

Conversation history и durable memory — разные контуры:

- history нужна для продолжения текущего разговора и содержит bounded отображаемый текст;
- memory хранит только отдельно подтверждённые немедицинские предпочтения;
- фразы пользователя не превращаются в memory автоматически;
- отключение или отзыв memory не удаляет историю диалога;
- удаление разговора не изменяет canonical тренировки, питание, профиль или цели.

## Выбор контекста

Backend не принимает от клиента готовый prompt или произвольный context. Для каждого сообщения
детерминированный selector выбирает `job`, trust class и один из путей:

1. safety classifier блокирует medical, drug/AAS, exfiltration, action и prompt-injection
   запросы до контекста и provider;
2. generic-вопрос ищется только в опубликованных текущих YFC guides и Web Articles;
3. вопрос о личных тренировках, прогрессе, питании или периоде требует personal consent;
4. после consent запускается ровно один allowlisted read-only tool текущего пользователя;
5. в provider передаются только bounded refs с facts, dates, sufficiency, limitations и fallback
   path; user ID, Telegram/email, trainer notes, raw diary, secrets и ORM objects исключены;
6. при отсутствии подходящего доказательного контекста ответ получает `insufficient_data`, а
   provider не вызывается.

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
loop. Legacy `LlmPort.generate` продолжает обслуживать старые структурированные endpoints.

Внешние ошибки нормализуются в безопасные состояния:

| API outcome | failure category | Поведение UI |
| --- | --- | --- |
| `safety_refusal` | отсутствует | Понятный отказ по конкретной категории |
| `consent_required` | отсутствует | Предложение явно включить personal consent |
| `insufficient_data` | `context_failure` | Объяснение, где открыть источник данных |
| `unavailable` | `provider_failure` или `generation_failure` | Общая безопасная ошибка без raw details |
| `unavailable` | `timeout` | Сообщение о таймауте и повторная попытка |
| `rate_limited` | `rate_limited` | Сообщение о лимите |
| `invalid_output` | `structured_validation` | Ответ не показывается, если его нельзя безопасно очистить |

`safety_category=clear` не является safety error. Если provider добавил только удалимый URL или
markdown-link noise, validated safe prose сохраняется как текст с outcome `invalid_output`; опасные,
не-русские, чрезмерные или содержащие запрещённые утверждения фрагменты не показываются.

Frontend отключает duplicate send во время запроса, показывает loading, сохраняет введённый текст
при сетевом/validation failure и не выводит provider exception. Timeout, retry и reload не должны
создавать второй пользовательский запрос или терять уже сохранённую историю.

## Privacy, telemetry и эксплуатация

В provider попадают только минимальные данные, нужные конкретному контексту. Generic path не
получает personal data или memory. Personal path получает memory только при двух активных consent:
personal и memory. Ни один путь не выполняет запись в canonical data.

`ai_coach_chat_generation` содержит только metadata: request id, job, data class, policy/prompt/schema
versions, provider/model, outcome, safety/failure category, attempts, counts, latency и nullable
token usage. В логи не попадают message text, answer, memory values, personal facts, raw context или
secret. Feedback хранит только категорию helpfulness и не копирует текст.

Новых обязательных provider, платных сервисов или credentials нет. Существующие AI Coach flags и
free-only policy сохраняются. Миграция `0086_ai_coach_conversations` — additive, без backfill и
без production data migration вручную. Для изменения: `env change required: no`.

## Проверка

Контракт покрывается backend unit/integration тестами для generic, personal consent, follow-up,
provider failure, invalid output, safe fallback, isolation, export/delete и legacy plain-text
adapter; frontend unit тестами для chat/reload/failure/memory secondary; Playwright browser/mock-TMA
сценарием для desktop, 390px mobile, TMA safe-area, quick prompts, feedback, follow-up и reload.
Физическое Telegram-устройство, реальный provider и production deployment требуют отдельного
evidence и не подменяются mock-TMA тестом.
