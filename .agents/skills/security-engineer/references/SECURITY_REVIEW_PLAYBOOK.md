# YFC Security Review playbook

Этот playbook задаёт воспроизводимый процесс для обычной Codex-сессии. Он не вызывает внешний
Codex Security Review и не создаёт отдельного reviewer lifecycle.

## 1. Scope freeze

Для `diff`:

```text
base = merge-base(origin/master, HEAD) либо явно заданный base
head = HEAD/PR head
scope = changed files + реально затронутые callers/sinks/trust boundaries
```

Для `full` scope - весь текущий repository head, но анализ выполняется последовательными
поверхностями, чтобы findings оставались проверяемыми.

Сначала перечисли changed/inspected paths. Не скрывай, какие области не удалось проверить.

## 2. Invariant-first review

Для каждого flow сформулируй инвариант до поиска бага. Примеры:

- authenticated user не может читать/менять объект другого пользователя;
- Telegram identity принимается только после серверной криптографической проверки;
- OAuth callback нельзя привязать к чужой сессии или произвольному redirect;
- user-controlled URL не даёт backend доступ к запрещённым network targets;
- upload не превращается в произвольное чтение пути, oversized resource exhaustion или unsafe parser input;
- секреты и access tokens не попадают в response/log/telemetry;
- реальные изображения не уходят во внешний Vision provider при незакрытом policy gate;
- AI-generated text не получает прав выполнять privileged action сам по себе.

## 3. Candidate -> validation

Для candidate finding зафиксируй:

```text
Attacker capability
Entry/source
Existing guards
Transformation/data flow
Sensitive sink/action
Broken invariant
Expected impact
```

Затем попробуй опровергнуть собственную гипотезу:

- найди upstream validation/middleware;
- найди ownership/role check;
- проверь dependency/framework default;
- проверь production config;
- напиши узкий negative test или минимальный repro;
- при необходимости используй deterministic scanner signal.

Если после этого остаётся только предположение, это `Unvalidated concern`.

## 4. YFC review map

| Поверхность | Основные вопросы |
| --- | --- |
| Web / TMA -> FastAPI | auth, CORS/CSRF, validation, BOLA/IDOR, rate limits |
| Telegram initData / bot | signature/freshness/replay, identity binding, internal tokens |
| GitHub OAuth | state, callback binding, redirect allowlist, token leakage |
| Backend -> PostgreSQL | ownership filters, injection, mass assignment, transaction races |
| Upload / Nutrition Vision | size/type/path, parser abuse, privacy gate, provider egress |
| AI Coach / external AI | sensitive payload, prompt boundary, provider failure/logging, egress |
| User-controlled URLs | SSRF, redirects, DNS/IP policy, timeout/body limits |
| Trainer/admin actions | privilege escalation, object scope, auditability |
| CI/CD / container / VPS | token scope, artifact/image integrity, unsafe prod defaults |
| Logs / analytics / Allure | secrets, user content, identifiers, retention exposure |

## 5. Severity

Severity определяется сочетанием реального impact и достижимости:

- `CRITICAL` - прямой массовый/привилегированный compromise с реалистичным exploitation path;
- `HIGH` - серьёзный compromise данных/аккаунта/границы с практической эксплуатацией;
- `MEDIUM` - ограниченный impact, дополнительные prerequisites или заметное снижение защиты;
- `LOW` - hardening/defense-in-depth с малым самостоятельным impact.

Не повышай severity из-за названия CWE/OWASP без YFC-specific impact.

## 6. Deterministic evidence

Локально используй только существующие project-native команды:

```bash
python scripts/ci_contract.py run-group dependency-audit
python scripts/ci_contract.py run-group policy
python scripts/skill_safety.py scan-all
```

Запускай только применимые группы. Docker/container checks - по реальному container scope и доступности
Docker.

Каждый PR автоматически запускает бесплатные deterministic jobs CodeQL, dependency audit и Trivy
filesystem scan внутри основного CI. Отдельный workflow `Security Audit` сохраняет manual/weekly
полный deterministic прогон. Эти scanners не заменяют validation exploitability.

## 7. Report contract

```markdown
# Security Review

Mode: diff | full
Base/head:
Inspected surfaces:
Not inspected / limitations:

## Threat model delta
...

## Confirmed findings
### [SEVERITY] Короткое название
- Asset / boundary:
- Preconditions:
- Attack path:
- Evidence:
- Impact:
- Remediation:
- Regression verification:

## Unvalidated concerns
...

## Deterministic checks
...

## Residual risk
...

Status: NO_CONFIRMED_FINDINGS | CONFIRMED_FINDINGS | NEEDS_MANUAL_VALIDATION
```

Не публикуй реальные токены, секреты, персональные данные или exploit payload, если для доказательства
достаточен безопасный минимальный пример.
