# AI Coach: production launch contract (Task 267)

Этот документ фиксирует актуальный production-контракт после явного решения владельца включить
AI Coach для 100% аутентифицированных пользователей. Исторические документы Tasks 88, 89, 90A,
90B, 92A и 92B сохраняют исходные evidence и решения на момент их выполнения; они не являются
текущим указанием оставлять AI Coach в limited beta.

## Что было исправлено

Причиной `AI Coach unavailable` был не отсутствующий provider adapter, а server-side internal
cohort boundary: `/status`, `/generate`, `/personal/generate` и создание memory требовали
`AI_COACH_UI_ENABLED=true` и account ID в `AI_COACH_INTERNAL_USER_IDS`. Текущий bundle использует
аутентификацию как единственный доступ к AI Coach, а runtime capability отдельно отражает состояние
provider и policy. Старые переменные остаются только как no-op compatibility settings для rollback
старых bundle и не являются authorization boundary.

Используется существующий backend-only `GroqDirectAdapter` с фиксированным HTTPS endpoint
`https://api.groq.com/openai/v1/chat/completions`, allowlisted model `openai/gpt-oss-120b`,
обычный plain-text response для conversational chat, bounded timeout, normalized provider errors
и без provider tools. Legacy structured JSON остаётся только на старых report endpoints. Новая
архитектура или новый платный сервис не добавляются.

## Production environment

Источник `GROQ_API_KEY` — существующий persistent host `.env`. GitHub Actions передаёт этот файл в
release bundle, но сам секрет не хранит и не выводит. Перед Compose validation
`scripts/configure_production_ai_coach.py .env`:

- требует непустой `GROQ_API_KEY`, не похожий на placeholder;
- сохраняет secret и все unrelated values;
- идемпотентно нормализует только AI Coach flags и удаляет duplicate lines этих flags;
- очищает legacy `AI_COACH_INTERNAL_USER_IDS`, чтобы rollback старого bundle не открыл AI Coach
  непредусмотренной cohort;
- не выполняет live provider request и не создаёт новую подписку или credential.

Production policy после нормализации:

| Переменная | Значение |
| --- | --- |
| `AI_COACH_ENABLED` | `true` |
| `AI_COACH_KILL_SWITCH` | `false` |
| `AI_COACH_PROVIDER` | `groq` |
| `AI_COACH_MODEL` | `openai/gpt-oss-120b` |
| `AI_COACH_COST_POLICY` | `free_only` |
| `AI_COACH_COST_CLASS` | `free` |
| `AI_COACH_DATA_POLICY` | `verified_generic_only` |
| `AI_COACH_PERSONAL_ENABLED` | `true` |
| `AI_COACH_PERSONAL_DATA_POLICY` | `verified_personal_user` |
| `AI_COACH_STRUCTURED_OUTPUT` | `true` |
| `AI_COACH_POLICY_REVISION` | `ai-coach-production-v1` |

`AI_COACH_PER_USER_REQUEST_LIMIT`, `AI_COACH_GLOBAL_REQUEST_LIMIT`, timeout и cooldown не
перезаписываются helper-ом: сохраняются текущие production значения из host `.env`. При отсутствии
допустимого ключа deploy останавливается до изменения `.env`; paid/unknown route не получает
скрытый fallback. Актуальные provider limits и data controls нужно сверять с официальными
документами перед изменением cost policy: [Groq models](https://console.groq.com/docs/models),
[Groq rate limits](https://console.groq.com/docs/rate-limits),
[Groq data controls](https://console.groq.com/docs/your-data).

## User-facing и privacy contract

- Обычный чат принимает любой поддерживаемый вопрос и вызывает provider даже при пустом app
  context. Проверенный public context добавляется только для релевантного общего или capability
  вопроса; профиль, дневник, тренировки и trainer notes не загружаются на generic path. История
  текущего разговора хранится отдельно и последние 8 user/assistant сообщений реально передаются
  provider для follow-up.
- Персональные quick prompts доступны после отдельного explicit consent и используют только
  релевантные existing readonly slices: профиль/цели, активная программа/расписание, недавние
  тренировки, история жима или сводка питания. Missing data приводит к естественному уточнению,
  а не к глобальному hardcoded отказу.
- Основной chat answer — обычный текст или безопасный markdown; внутренние route/tool/schema
  labels и ссылки на персональные экранные пути не возвращаются пользователю.
- Consent revocation и provider policy revision сохраняют fail-closed поведение.
- Memory не обязательна. `OFF` не блокирует AI Coach; `ON` принимает только user-confirmed
  разрешённые немедицинские preferences и позволяет пользователю pause/revoke/edit/delete.
- AI Coach не заменяет врача или тренера, не ставит диагнозы и не меняет canonical data.
- В telemetry остаются только технические metadata: provider/model, outcome, error class,
  repair flags, validation failure reason, attempts, latency, usage counters и version fields.
  Raw prompt, answer, personal context и provider secret не попадают в логи; account-owned история
  чата хранится отдельно и удаляется вместе с conversation/account.

## Failure and rollback

Provider timeout, network/HTTP error, malformed response, policy mismatch, quota или cooldown
дают bounded safe outcome и оставляют основные функции YFC доступными. UI предлагает повторить
запрос, но не раскрывает provider error или secret. Для incident владелец может включить
`AI_COACH_KILL_SWITCH=true` в persistent host `.env`; это отключает только AI Coach и требует
normal PR-based production release для доставки изменения.

## Required release evidence

После merge и automatic deployment production closeout должен подтвердить privacy-safe metadata без
сохранения raw content:

1. authenticated `/api/v1/ai-coach/status` возвращает `ui_enabled=true` и runtime capability;
2. реальные provider requests для «Как рассчитать КБЖУ?», «Сколько нужно пить воды?» и
   «Сколько отдыхать между подходами?» возвращают содержательный conversational answer;
3. app-help, consent-enabled personal question без/с доступным context и follow-up проходят
   настоящий provider request, а history переживает reload;
4. ответы не содержат внутренних route/tool/schema labels;
5. memory OFF и ON остаются рабочими и не расширяют context contract;
6. safe failure path не ломает приложение, а UI не показывает internal-beta copy;
7. `/health/live` и `/health/ready` остаются healthy после smoke.

Обычный CI использует deterministic provider double и не выполняет paid/live calls. Реальная
generation проверяется только отдельным production smoke после deploy, с owner/test account и без
выгрузки raw prompt/answer в artifacts или logs. Smoke evidence содержит только request type,
provider, configured/actual model, latency, outcome и generation success; отсутствие обязательного
provider credential — точный `HUMAN_REQUIRED` blocker.
