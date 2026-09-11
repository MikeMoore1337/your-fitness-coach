# Hardened Hermes editorial worker (Task 129)

Это минимальный non-root container для одной bounded editorial job. Он принимает
source metadata/content packet из `/opt/data`, вызывает только OpenAI-compatible
`chat/completions`, проверяет structured response и отправляет подписанный
`hermes-editorial-intake-v2` в YFC. `HERMES_PROVIDER_MODE=local_mock` сохраняет
текущий local-only HTTP contract (`/v1` и localhost/`host.docker.internal`); после
`accepted` он отправляет только preview-only payload в allowlisted local preview endpoint.

`HERMES_PROVIDER_MODE=external` подготовлен только для отдельного owner-approved
shadow-run. В этом режиме worker принимает исключительно `https://api.groq.com/openai/v1`,
модель `openai/gpt-oss-120b`, и исключительно
`https://app.your-fitness-coach.ru/api/v1/hermes/editorial/intake`. HTTPS host/path,
порты, userinfo, query/fragment и redirects проверяются fail-closed; source URLs worker
не fetch'ит. `TELEGRAM_PREVIEW_URL` в external mode не требуется и запрещён schema-контрактом:
после accepted intake дальнейший editorial/review flow принадлежит YFC.

Для research/index записей, включая PubMed, metadata или abstract не считаются доказательством
или health claim. Worker требует сохранить неопределённость и редакторскую проверку primary
source, study design, limitations и applicability до любого health claim.

Общий бюджет provider ограничен максимум двумя попытками того же Groq candidate, включая
первичный draft, retry transient-ошибки и одну bounded quality-repair попытку. 429, quota,
timeout, network unavailable и 5xx не запускают paid tier или cloud fallback: после
исчерпания bounded budget результатом остаётся manual/no-provider. `HERMES_PROVIDER_MODEL` остаётся
provider-neutral contract, но external mode сейчас принимает только зафиксированный
candidate `openai/gpt-oss-120b`.

До HMAC intake worker выполняет детерминированный editorial preflight: числовые токены draft
должны быть заземлены в разрешённом source packet, а видимый plain-text photo caption с меткой
`Источник` должна укладываться в лимит 1024 UTF-16 символа Telegram. Если финальная YFC
проверка находит recoverable blocker, worker запрашивает bounded repair у того же approved
provider и отправляет новую immutable revision с новым idempotency key/nonce. Общий бюджет —
максимум две попытки; после исчерпания job получает terminal remediation failure и не
переигрывается бесконечно. Успешный preflight не является approval публикации:
`manual_required`, Gate B/C и единственный publisher остаются на стороне YFC.

Worker не содержит source fetching, scheduler, database client, shell/tool dispatch,
browser, MCP, plugins, Telegram Bot API или publish endpoint. Полный Hermes monolith
не является частью image. Upstream Hermes сохраняется как provenance contract и
проверяется локальным `scripts/hermes_worker.py provenance --source-dir ...`.

Из чистого checkout с локально доступным exact Hermes source checkout:

```powershell
python scripts/hermes_worker.py verify --source-dir <exact-hermes-checkout>
```

`verify` сначала сверяет рабочую копию Hermes с commit/tag/version/license, затем выполняет
весь bounded local sequence: clean tracked build, hardening boundary, local HTTP E2E, CycloneDX и
SPDX SBOM, а также CRITICAL/HIGH gate. `--source-dir` используется только для offline Git
проверки и не копируется в image. Для SBOM/security exact Trivy image и актуальная DB должны
быть доступны локально; обычный CI от внешнего Hermes/Groq/Telegram и от этого scanner path не
зависит. Отдельные команды `provenance`, `build`, `hardening`, `e2e`, `sbom` и `security`
остаются доступны для targeted проверки. Никакие команды этого local path не выполняют live
provider/Telegram calls; внешний provider quality проверяется только после Gate A в shadow-run.
