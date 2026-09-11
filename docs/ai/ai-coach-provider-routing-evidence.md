# AI Coach: evidence для provider routing (Task 92B)

Статус на 2026-09-11: `RESEARCH_FIRST`, multiprovider production implementation не одобрена.

Этот документ фиксирует bounded evidence и следующий owner checkpoint. Он не выбирает второго
provider, не разрешает paid fallback и не заменяет отдельное решение по privacy contract.

## Owner decision и границы

Owner decision от 2026-09-11 разрешает только research-first workstream:

- сохранить текущий single-provider route и controlled `unavailable` state;
- собирать только metadata-only evidence из текущего AI Coach operation;
- не добавлять второго provider ради архитектурной избыточности;
- после измеримого gap вернуться с конкретным предложением, максимум с двумя providers,
  bounded fallback и явной privacy matrix.

Поэтому в Task 92B не добавляются router, provider adapter, новые API keys, user-supplied keys,
автоматическая покупка quota, hidden paid fallback, migration или новый production flow.

## Current baseline

| Область | Текущее состояние | Вывод для routing |
| --- | --- | --- |
| Route | `GroqDirectAdapter`, fixed HTTPS `api.groq.com`, model `openai/gpt-oss-120b` | один provider; fallback не включён |
| Cost | runtime policy `free_only`, cost class `free` | paid/promo/unknown route не разрешён |
| Data | generic route — `verified_generic_only`; personal route отдельный и consent-gated | data class нельзя понижать ради fallback |
| Output | strict JSON Schema проверяется на provider и повторно в YFC | capability gap пока не доказан |
| Retry | bounded process-local retry/cooldown, blind cascade отсутствует | повтор и failover остаются разными решениями |
| Rollback | kill switch и controlled unavailable сохраняют deterministic core flow | безопасный одно-provider fallback уже есть |

`backend/fitminiapp_api/ai_coach/service.py` уже формирует полезные metadata-only поля:
request/job/data class, prompt/schema/policy versions, configured/actual model, outcome,
error code, attempts, latency, nullable usage и period-report revision. До этого изменения
JSON formatter отбрасывал значительную часть этих полей и переименовывал событие в
`application_log`, поэтому 90B не мог построить полный aggregate.

Task 92B добавляет только безопасную whitelist-передачу этих полей в JSON logs. Prompt, answer,
raw context, memory values, user id, exact measurements и provider payload по-прежнему не
попадают в event.

## Evidence from 90B

90B зафиксировал ограниченную production beta, но не provider decision:

- bounded cohort — примерно 2–3 реальных пользователя, configured allowlist — 3 account IDs;
- один owner-reported `unavailable`/rate-limit episode и слишком строгая per-user quota;
- в доступном container window — только 2 `answer` samples, latency 888–1110 ms;
- provider, error code, data class и attempts в старом log aggregation были недоступны;
- domain/safety/privacy/core-flow blocker в bounded observation не наблюдался, но denominator,
  полный период и statistical quality/error rate отсутствуют.

Это evidence для устранения measurement gap, но не измеримый multi-provider trigger. В частности,
один rate-limit episode нельзя отделить от local per-user quota, organization quota или
transient provider condition по старому snapshot.

## Evidence matrix

| Возможный trigger | Текущий evidence | Статус |
| --- | --- | --- |
| outage/capacity | нет полного provider-attributed ряда; есть только bounded `unavailable` observation | `NOT_ESTABLISHED` |
| rate/quota | один owner-reported episode; local quota и provider quota не разделялись | `SIGNAL_ONLY` |
| capability/tool/structured output | текущий route имеет проверяемый strict structured-output path; провал capability не измерен | `NOT_ESTABLISHED` |
| latency | 2 samples, 888–1110 ms, без target/SLO и полного окна | `NOT_ESTABLISHED` |
| cost | runtime `free_only`; per-request cost aggregate отсутствует; paid fallback не разрешён | `NOT_ESTABLISHED` |
| privacy/data location | current provider contract нужно проверять перед любым personalized/fallback route; это constraint, а не incident | `CONSTRAINT_REQUIRES_REVIEW` |
| approved-job quality | bounded useful observation без denominator и versioned real-user sample | `NOT_ESTABLISHED` |

## Official provider checks (rechecked 2026-09-11)

Проверены только официальные материалы текущего provider; live inference/smoke с credentials не
выполнялся.

- Groq rate limits зависят от RPM/RPD/TPM/TPD и применяются на уровне организации; для
  `openai/gpt-oss-120b` опубликованы Developer-plan базовые limits 30 RPM, 1K RPD, 8K TPM и
  200K TPD, но точные лимиты конкретной организации нужно смотреть в Console.
- Groq указывает для `openai/gpt-oss-120b` JSON Schema capability и strict structured-output
  support; в отдельной документации отмечено, что structured outputs не совмещаются с tool use.
  Текущий YFC не передаёт model-controlled tools: personal tool выполняется backend-side до
  provider, поэтому это не является установленным gap.
- Groq описывает inference как не сохраняющий customer data по умолчанию, но допускает
  временные logs inputs/outputs для reliability/abuse monitoring до 30 дней; указанная data
  location для retained customer data — GCP buckets в США. Это нельзя переносить на другого
  provider без отдельной проверки и owner/privacy decision.

Источники:

- [Groq rate limits](https://console.groq.com/docs/rate-limits)
- [Groq GPT-OSS 120B model](https://console.groq.com/docs/model/openai/gpt-oss-120b)
- [Groq structured outputs](https://console.groq.com/docs/structured-outputs)
- [Groq API errors](https://console.groq.com/docs/errors)
- [Groq data controls and retention](https://console.groq.com/docs/your-data)
- [Groq policies and notices](https://console.groq.com/docs/legal)

## Collection contract before the next decision

После штатного rollout metadata-only formatter owner/operations должны собрать агрегаты без
выгрузки raw logs:

1. outcome/error-code counts by `job`, `data_class`, configured/actual model and provider;
2. latency bands and sample count for a known observation window;
3. attempts/retry counts and cooldown/unavailable events;
4. nullable usage/cost fields as reported by provider, without fabricated cost;
5. capability/output-validation failures separately from safety refusal and local quota;
6. no raw prompt/answer/context, user id, memory value, account id or provider payload.

Минимально достаточный window и thresholds не выдумываются этой task: owner должен утвердить
их вместе с job/cohort и target reliability/cost/latency. До этого текущий route остаётся
единственным, а `unavailable` — валидным fallback без AI.

## Owner checkpoint

Текущий результат: `CONTINUE_SINGLE_PROVIDER_RESEARCH`.

Для перехода к production multiprovider implementation owner должен получить новый evidence-backed
decision, в котором есть:

- воспроизводимый trigger из matrix с observation window, denominator и impact;
- выбранный approved job и trusted data class;
- максимум два конкретных providers/models с capability, cost/free classification, terms/date,
  retention/data-location и privacy compatibility;
- parity eval plan против текущего Groq route, включая safety, grounding, structured output,
  latency/cost и no-provider path;
- bounded retry/failover/cooldown, idempotency и kill-switch/rollback to one provider;
- explicit approval на provider count и privacy matrix.

До такого решения production router не реализуется.

## Configuration and deployment impact

Изменения не добавляют environment keys, secrets, dependencies, migrations или provider calls.
`env change required: no`. Обычный PR-based release telemetry fix может быть продолжен по
lifecycle; real provider smoke и production credentials не требуются.
