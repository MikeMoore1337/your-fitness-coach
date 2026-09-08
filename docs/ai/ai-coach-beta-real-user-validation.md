# AI Coach beta: real-user validation и limited rollout decision (Task 90B)

Статус решения: `CONTINUE_LIMITED_BETA`

Дата решения: 2026-09-08

Область: реальная ограниченная production-проверка AI Coach после Task 90A.
Документ не включает новую функциональность, memory, advanced routing, paid inference или
broad/public rollout.

## 1. Итоговое решение владельца

Владелец принял решение `CONTINUE`:

- продолжить текущую ограниченную AI Coach beta для уже разрешённой когорты;
- сохранить только `free-only` inference и текущие quota-ограничения;
- разрешить текущим активным пользователям продолжать пользоваться функцией;
- не включать всех пользователей и не объявлять публичный/broad rollout;
- не включать платный provider, долгосрочную memory или advanced provider routing;
- не превращать запросы на новые возможности в scope Task 90B;
- дальнейшее расширение когорты оформлять отдельным owner decision.

Это решение относится к ограниченной beta и не означает отсутствия риска или статистического
доказательства качества. Оно основано на фактических owner observations, безопасной проверке
production runtime и доступном ограниченном telemetry snapshot.

## 2. Provenance и фактическое состояние production

Ниже зафиксирован production snapshot на момент первоначальной validation-проверки. После неё
отдельно выполнен release remediation для server-side cohort boundary и persistent image
provenance; его результат подтверждается release evidence, а не этим историческим snapshot.

### 2.1. Deployed revision

| Evidence ID | Факт | Provenance |
| --- | --- | --- |
| `PROD-REV-01` | На момент snapshot активная production revision: `005068d462a2c617887a2af2b51275d16a785e3c` | production marker и `current` на host, read-only check `2026-09-08T18:30:04Z` |
| `PROD-REV-02` | Revision `005068d…` успешно прошла production release | GitHub Actions run `34241361787`, head SHA `005068d…`, `success`, 2026-09-08 14:54:59–14:57:46 UTC |
| `PROD-REV-03` | На момент snapshot последняя merged 90A layout revision `1a27733bd49d881812c7d501c7ee33c49ea24807` не считалась deployed | release run `34262002318` остановился на `single_slot_legacy_provenance` до `pull_and_verify`/`traffic_switch`; active marker оставался `005068d…` |
| `PROD-HEALTH-01` | Public liveness/readiness отвечали `200` (`{"status":"ok"}`) | `https://app.your-fitness-coach.ru/health/live` и `/health/ready`, read-only check `2026-09-08T18:29:20.6016551Z` |
| `PROD-AUTH-01` | Неаутентифицированный запрос к AI Coach status получил `401` | `GET /api/v1/ai-coach/status`, тот же read-only check |

Проверка `PROD-REV-03` не является частью AI Coach product decision. Она важна для того, чтобы
не приписывать первоначальному production snapshot неразвёрнутую revision. Выявленный при
подготовке release blocker исправлен в текущем delivery remediation и не отменяет исходный
ограниченный beta вывод.

### 2.2. Effective runtime configuration

Read-only inspection запущенного `fit-mini-app-backend-1` на момент snapshot подтвердил
следующие значения. Секрет `GROQ_API_KEY` проверен только на наличие; его значение, длина и
содержимое не сохранялись.

| Setting | Effective production value |
| --- | --- |
| `AI_COACH_ENABLED` | `true` |
| `AI_COACH_UI_ENABLED` | `true` |
| `AI_COACH_KILL_SWITCH` | `false` |
| `AI_COACH_INTERNAL_USER_IDS` | настроены 3 account IDs; сами IDs не раскрываются |
| `AI_COACH_PROVIDER` | `groq` |
| `AI_COACH_MODEL` | `openai/gpt-oss-120b` |
| `AI_COACH_COST_POLICY` | `free_only` |
| `AI_COACH_COST_CLASS` | `free` |
| `AI_COACH_DATA_POLICY` | `verified_generic_only` |
| `AI_COACH_STRUCTURED_OUTPUT` | `true` |
| `AI_COACH_PERSONAL_ENABLED` | `false` |
| `AI_COACH_PERSONAL_DATA_POLICY` | `disabled` |
| `AI_COACH_PER_USER_REQUEST_LIMIT` | `50` |
| `AI_COACH_GLOBAL_REQUEST_LIMIT` | `200` |
| `AI_COACH_QUOTA_WINDOW_SECONDS` | `86400` (24 часа) |
| `GROQ_API_KEY` | присутствует, redacted |

Effective environment подтверждён именно у running backend container, а не только в persistent
`.env`. В рамках release remediation секреты и значения AI Coach policy не менялись.

После исправления server-side boundary оба generation endpoint — `POST /api/v1/ai-coach/generate`
и `POST /api/v1/ai-coach/personal/generate` — используют тот же серверный cohort predicate,
что и status endpoint. Аутентифицированный аккаунт вне allowlist получает `403` до вызова
provider; скрытие UI не считается authorization boundary. Personal route при этом остаётся
выключенным production policy.

## 3. Research method и cohort

Источники evidence:

1. owner-provided continuation brief в текущей task conversation;
2. read-only production runtime snapshot;
3. агрегированный snapshot AI Coach logs без выгрузки строк, prompt, answer или IDs;
4. текущий repository contract для server gate, quota, safety, consent и safe analytics.

Task 90A synthetic/eval suite повторно не запускалась и не используется как real-user evidence.

### 3.1. Cohort и observation period

- Фактическая user-reported cohort: примерно **2–3 реальных пользователя**, включая владельца.
- Server allowlist на момент проверки содержит 3 account IDs. Это не подменяет число distinct
  пользователей, реально отправивших запросы.
- Реальные пользователи работали в production UI и задавали обычные вопросы по назначению
  продукта. Точные персональные идентификаторы, transcripts и raw prompts в этот документ не
  попадают.
- Owner observation был передан как bounded manual check 2026-09-08; точные start/end времени,
  platform split и число сессий не зафиксированы.
- Формального отдельного research consent, записи интервью, подписанных форм и transcripts,
  сверх существующего product beta/privacy flow, не предоставлено. Это limitation исследования,
  а не выдуманное подтверждение согласия.

### 3.2. Проверенные jobs

Ниже указаны только категории реальных вопросов, не дословные пользовательские сообщения:

- объяснение значения RIR;
- вопрос о подходящей зоне пульса для кардио;
- вопрос о расчёте КБЖУ;
- другие обычные вопросы о тренировках, питании и использовании фитнес-контекста.

### 3.3. Research brief, moderator guide и observation template

**Research brief.** Цель среза — понять, можно ли продолжать ограниченную beta для уже
разрешённой когорты без broad rollout: понятны ли beta/лимиты, различим ли AI Coach и
детерминированные функции приложения, помогает ли ответ выполнить исходную задачу, и не
появились ли safety, privacy или core-flow blockers. Участник должен быть реальным пользователем
из server-side allowlist, добровольно использовать существующий product beta flow и задавать
обычный вопрос по назначению продукта. Публичный набор, новые участники и персональный AI route
в этот срез не входят.

Отдельный formal research notice/consent для этого retrospectively описанного среза owner не
предоставил; поэтому ниже зафиксирован протокол наблюдения, но не заявляется, что все его поля
были собраны в каждой сессии.

**Moderator guide для продолжения ограниченной beta.** Перед взаимодействием зафиксировать
только cohort/consent state без raw prompt и PII; затем попросить пользователя выполнить один
обычный job. После ответа проверить открытыми вопросами: понял ли пользователь, что это beta и
каковы лимиты; отличает ли AI Coach от trainer/детерминированного экрана; помог ли ответ
продолжить задачу; доверяет ли состоянию insufficient data; заметил ли source/citation и смог ли
его открыть. Отдельно отметить factual/domain issue, корректность refusal, latency, cost/limit
state, влияние на Today/Program/Nutrition/Progress и необходимость поддержки. При safety/privacy
инциденте, cross-user signal или блокировке core flow сессию остановить и передать incident owner;
не пытаться компенсировать проблему paid provider или расширением когорты.

**Минимальный observation template.** Для каждого bounded interaction достаточно заполнить
обезличенные поля `session_ref`, `job_category`, `beta_comprehension`, `coach_distinction`,
`source_use`, `insufficient_data_trust`, `helpfulness_or_completion`, `domain_error`,
`refusal_correctness`, `latency_band`, `quota_or_cost_state`, `core_flow_impact`, `support_need`,
`severity`, `evidence_note`. Допустимые значения — `observed`, `not_observed`, `unknown` или
`not_measured`; `evidence_note` не должен содержать prompt, answer, account ID, transcript,
health detail или provider payload. Этот template задаёт будущий способ сбора данных и не
превращает неизвестные поля текущего среза в наблюдения.

## 4. Evidence summary

### 4.1. Owner-provided qualitative observations

| Проверка | Результат | Статус evidence |
| --- | --- | --- |
| Общая корректность и соответствие назначению | AI Coach в целом работал корректно и был полезен | подтверждено owner observation в ограниченной проверке |
| Factual/domain errors | Заметных ошибок в проверенных взаимодействиях не обнаружено | bounded observation; нет denominator и claim о нулевом риске |
| Safety/privacy | Проблем не обнаружено | bounded observation; не является доказательством отсутствия риска во всех сценариях |
| Cross-user isolation | Утечки чужих пользовательских данных не обнаружено | bounded observation; отдельная server-side boundary остаётся обязательной |
| Core product | Основные функции приложения из-за AI Coach не ломались | bounded observation |
| Distinction | Разница между AI Coach и обычными функциями приложения была понятна | owner/user observation |
| Critical UX blockers | Критических blocker'ов для продолжения beta не выявлено | bounded observation |
| Source discovery/click-through | Отдельно не измерялось | unknown |
| Trust in insufficient-data state | Отдельно не измерялось | unknown |

### 4.2. Runtime и telemetry

Во время первоначальной ручной проверки owner сообщил:

- один случай `outcome=unavailable`;
- состояние `rate_limited`;
- исходная per-user quota была слишком маленькой для beta;
- после корректировки quota AI Coach продолжил работать исправно.

Эти два состояния зафиксированы как owner-reported runtime observations, без искусственного
добавления request IDs или точных timestamps.

Безопасный production log aggregation на 24 часа и 7 дней дал один и тот же фактически доступный
snapshot: backend container был запущен с `2026-09-08T17:55:20.922922141Z`, поэтому более ранние
события в его log stream отсутствуют.

| Signal | Snapshot result | Interpretation |
| --- | --- | --- |
| AI Coach log events | `2` | только доступное окно текущего backend container |
| `answer` | `2` | не является полным beta success rate |
| `unavailable` | `0` | не опровергает owner-reported earlier state |
| `rate_limited` | `0` | не опровергает owner-reported earlier state |
| safety/refusal/insufficient/invalid output | `0` в snapshot | не покрывает полный observation period |
| latency samples | `2` | min `888 ms`, max `1110 ms`, average `999.0 ms`; descriptive only |
| provider/error_code/data_class/attempts fields | `0` emitted fields | подтверждён observability gap |

Log aggregation выполнялась удалённо и выводила только counters/aggregates. Raw log lines не
сохранялись и не передавались в report.

### 4.3. User feedback

1. Жалоба на слишком строгий лимит / желание иметь больше запросов — это product feedback по
   доступности, а не safety, privacy или core-flow blocker. Пользователям объяснено, что текущая
   версия — бесплатная beta и лимиты связаны с free inference; это принято как допустимое
   ограничение.
2. Запрос дополнительных AI-возможностей — future product scope. Он уже покрывается отдельными
   backlog tasks и не реализуется/не дублируется в 90B.
3. Paid provider/inference для снятия ограничений не одобрен.

## 5. Metrics: definitions и limitations

Числа ниже не являются придуманными KPI. `Not measured` означает отсутствие достоверного
aggregate source на момент decision.

| Metric | Definition | Result |
| --- | --- | --- |
| Beta availability | `AI_COACH_ENABLED=true`, UI gate и cohort allowlist активны | measured: runtime snapshot |
| Invited cohort | account IDs в server-side allowlist | configured: `3`; distinct active users: `2–3` owner-reported |
| Request outcomes | count по server `outcome` за явно известное log window | `2 answer` в доступном container window; full beta period not measured |
| Helpfulness | доля `helpful` среди privacy-safe feedback events с denominator | not measured; aggregate provider/dashboard не доступен |
| Task completion/help | пользователь завершил исходную задачу после ответа | qualitative useful/helpful observation; no numeric denominator |
| Factual/domain error | зафиксированная ошибка с severity и воспроизводимым interaction evidence | none observed in bounded check; no statistical error rate |
| Safety/refusal correctness | корректность отказов на запрещённых/unsafe jobs | no incident reported in bounded check; no real-user refusal sample |
| Source success | открытие server-known citation/source | not measured |
| Core-flow impact | AI interaction causes core app failure or blocks continuation | none observed; no automated production counter |
| Latency | response latency distribution for beta requests | 2 descriptive samples only: 888–1110 ms |
| Cost/provider | provider usage and cost class | runtime policy measured as `free`; per-request usage/cost aggregate not available |
| Support burden | AI-related support contacts per request/user | not measured |

Repository already emits a privacy-safe frontend event schema for `entry_opened`, request outcome,
failure, consent and helpfulness, but no production aggregate sink/dashboard was available for this
decision. Event schema does not permit raw prompt, response, user ID, exact fact or provider payload.

## 6. Findings

### Closed / non-blocking gate findings

| Finding | Severity | Verdict | Evidence |
| --- | --- | --- | --- |
| `OBS-90B-REAL-01` — bounded production use выявлен, ответы соответствовали назначению, core-flow и privacy/safety blocker не наблюдались | gate result | `CLOSED_FOR_LIMITED_BETA` | owner observations; `PROD-REV-01`; `PROD-HEALTH-01` |
| `OBS-90B-FEEDBACK-01` — quota dissatisfaction | product feedback | `ACCEPTED_BETA_LIMITATION` | owner feedback; current `50/200/86400` runtime quota |
| `OBS-90B-FEEDBACK-02` — запрос новых возможностей | future scope | `OUT_OF_SCOPE` | existing Tasks 91, 92A, 92B, 93B; no duplicate task created |

`OBS-90B-REAL-01` не означает «AI безопасен всегда» или «ошибок нет»; он означает только,
что в предоставленном bounded observation blocker не обнаружен.

### Open / non-blocking measurement finding

| Finding | Severity | Verdict | Impact and route |
| --- | --- | --- | --- |
| `OBS-90B-OBS-01` — AI Coach production log emission теряет `provider`, `error_code`, `data_class` и `attempts`: logger отправляет `ai_coach_generation`, но `SAFE_EVENT_NAMES`/`STRUCTURED_FIELDS` текущего JSON formatter не пропускают эти поля; safe runtime probe показал `message=application_log`, `outcome`/`latency_ms` остались, остальные поля отсутствуют | `LOW` | `OPEN_MEASUREMENT_LIMITATION` | Ухудшает post-incident attribution и full-period metrics, но не выявил safety/privacy/core-flow blocker в этой cohort. Не исправлять в 90B; не создавать duplicate follow-up task без owner triage. |

Open finding подтверждён фактическим кодом `backend/fitminiapp_api/ai_coach/service.py`,
`backend/fitminiapp_api/core/logging_config.py` и безопасным formatter probe. Existing owner-only
`codex-backlog/bugs/FINDINGS.md` синхронизирован owner-local записью с тем же ID; duplicate bug
task не создавался. Finding остаётся открытым для owner triage.

## 7. Rollout, incident и rollback record

### Staged state

| Stage | Status | Proof/limitation |
| --- | --- | --- |
| Internal | passed before 90B | Task 90A UI/evaluation gate; synthetic results не заменяют real-user evidence |
| Small invited cohort | passed | production flags, allowlist of 3 configured IDs, owner-reported 2–3 real users |
| Owner review | passed | explicit owner decision `CONTINUE` in current task input |
| Limited beta | continue | free-only, current cohort only, no broad/public exposure |

### Current controls

- `AI_COACH_INTERNAL_USER_IDS` — server-side cohort boundary; UI status также требует
  `AI_COACH_UI_ENABLED`.
- Generation endpoints повторно применяют ту же cohort boundary на сервере и возвращают `403`
  аккаунтам вне allowlist до обращения к provider; UI visibility не является защитой.
- `AI_COACH_KILL_SWITCH` — emergency request gate; при `true` AI Coach возвращает controlled
  unavailable, deterministic core не удаляется.
- `AI_COACH_PER_USER_REQUEST_LIMIT`, `AI_COACH_GLOBAL_REQUEST_LIMIT` и
  `AI_COACH_QUOTA_WINDOW_SECONDS` — текущая availability/budget boundary.
- `AI_COACH_COST_POLICY=free_only` и `AI_COACH_COST_CLASS=free` — платный inference не является
  fallback.
- Personal route остаётся выключенным (`AI_COACH_PERSONAL_ENABLED=false`), что не расширяет
  этот generic beta evidence до персональной rollout.

### Rollback / containment

1. При incident owner включает server-side `AI_COACH_KILL_SWITCH=true` в persistent production
   environment и выполняет штатный controlled backend restart/recreate, чтобы process перечитал
   Settings; проверить `/health/ready` и authenticated status после изменения.
2. Для cohort-only containment owner может выключить `AI_COACH_UI_ENABLED` либо сузить
   `AI_COACH_INTERNAL_USER_IDS`; это убирает entry point для неразрешённых аккаунтов. Kill switch
   остаётся предпочтительным emergency control для немедленного запрета новых AI requests.
3. После стабилизации owner проверяет безопасные outcome/error counters и возвращает ограниченный
   rollout только отдельным решением. Deterministic Today/Progress/Nutrition flows не требуют
   AI и остаются recovery path.
4. Никаких user data, consent rows или deterministic facts при rollback не удалять.

Incident owner и kill-switch authority: владелец проекта. В рамках 90B rollback не выполнялся,
поскольку blocker не наблюдался; зафиксирована только readiness/rollback procedure.

## 8. Privacy, research и release limitations

- Cohort маленькая и convenience-based, владелец входит в неё; bias и отсутствие
  representative sample ограничивают выводы.
- Точное число distinct active users, число запросов за весь период, repeat use и retention не
  установлены telemetry.
- Отдельные formal research consent/recording/transcripts не предоставлены; анализ использует
  только owner-provided observations и product flow.
- Платформа (Mobile Web/TMA/desktop) и device split не зафиксированы; real Telegram/device proof
  не заявляется.
- Source click-through, insufficient-data comprehension, helpfulness denominator и support burden
  не измерялись.
- Log retention/container restart и allowlist gap не позволяют реконструировать полный outcome
  history, provider attribution или per-request cost.
- В production request для новой проверки не отправлялся: это сохраняет free quota и не создаёт
  дополнительный user/provider side effect. No paid/live smoke was performed for Task 90B.
- Текущий active SHA и runtime snapshot подтверждают readiness limited beta, но не заменяют
  ongoing monitoring.

## 9. Follow-ups и следующий backlog item

Новые follow-up tasks в рамках 90B не создавались:

- quota complaint оставлена принятой beta limitation;
- новые capabilities уже имеют существующие backlog scopes и не дублируются;
- observability gap зафиксирован как `OBS-90B-OBS-01` с owner triage, без параллельного task;
- release remediation для persistent immutable image refs и строгой provenance-проверки включено
  в текущий delivery, потому что blocker обнаружился при выпуске этого результата.

Следующая существующая AI-задача по backlog: **Task 91 — `AI Coach: итог выбранного периода с
ограниченными рекомендациями`**. Её trigger требует successful 90B `Go` и отдельное решение по
grounded period insights; Task 91 не запускается автоматически этим документом.

## 10. Изменения и configuration impact

- Изменено: durable research/decision document, server-side cohort enforcement с regression
  tests и deploy persistence для immutable `BACKEND_IMAGE`/`BOT_IMAGE` после verified rollout.
- API surface расширен не был; generation endpoints получили обязательную server-side проверку
  существующей cohort policy.
- Migrations: нет.
- Dependencies: нет.
- Production `.env`/secrets: новых ключей и значений не требуется; `env change required: no`.
  Deploy автоматически сохраняет только immutable application image refs в persistent `.env`;
  значение `GROQ_API_KEY` не читается в report и не изменяется этим task.
- Production redeploy: требуется и выполняется через normal PR-based release для включения
  server-side gate и remediation deployment provenance; итоговая revision подтверждается
  отдельным release evidence.
- Raw prompts, answers, transcripts, account IDs, API key и personal data: не сохранялись.
