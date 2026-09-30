---
name: security-engineer
description: >
  Threat-model and review YFC application security across authentication, authorization,
  isolation, sessions, inputs, files, secrets, dependencies, AI/provider boundaries and
  web/API attack surfaces. Use in diff mode for security-sensitive changes and in full mode
  only for an explicit repository-wide security audit.
---

# security-engineer

Работай от реального threat model, data flow и security invariants, а не от общего списка OWASP.

## Источники истины

Перед review прочитай:

1. `AGENTS.md`;
2. `security/THREAT_MODEL.md`;
3. `references/SECURITY_REVIEW_PLAYBOOK.md`;
4. фактический код, тесты, конфигурацию и active docs затронутого flow.

Если threat model расходится с кодом, код определяет текущую реальность, а расхождение является
отдельным documentation finding. Не выдумывай endpoint, роль, provider или гарантию.

## Режимы

### `diff`

Используй для security-sensitive task/PR.

- Зафиксируй base/head и список changed paths.
- Начни с diff, затем проследи затронутые call/data flows до trust boundary и persistence/provider sink.
- Не превращай diff review в бесконтрольный аудит всего репозитория.
- Existing vulnerability вне затронутого flow фиксируй только если изменение делает её достижимой
  или существенно меняет impact.

### `full`

Используй только по явному запросу на полный security audit.

Проходи последовательно: identity/session -> authorization/isolation -> inputs/uploads/URLs ->
data/privacy/logging -> AI/external providers -> secrets/dependencies -> deployment/CI.

Не создавай отдельный reviewer role, subagent или параллельных production writers.

## Обязательный цикл

1. Определи assets, attackers, entry points, trust boundaries и privileged actions.
2. Сформулируй проверяемый security invariant.
3. Для candidate finding укажи attacker capability, source, sink и attack path.
4. Попытайся подтвердить проблему тестом, минимальным repro, трассировкой data flow либо
   детерминированным scanner evidence.
5. Проверь существующие guards, middleware, ownership checks, validation и deployment constraints.
6. Только после этого переводи concern в confirmed finding.
7. Предложи минимальное исправление в корневой boundary и способ регрессионной проверки.

Нельзя повышать severity только из-за потенциально опасного API или подозрительной строки кода.

## Проверяемые области

По применимости проверь:

- authentication lifecycle и Telegram initData verification;
- OAuth state/callback/redirect handling;
- server-side authorization и user/trainer isolation;
- IDOR/BOLA и mass assignment;
- session/token storage, expiry, rotation и revocation;
- CSRF там, где применимо, XSS и injection;
- SSRF и user-controlled URLs;
- path traversal, MIME/type/size limits и unsafe file processing;
- rate limits, replay, idempotency и abuse;
- secrets, CORS, security headers и sensitive logging;
- dependency/supply-chain risk;
- AI/provider boundary: user content не становится authorization/configuration command;
- Nutrition Vision privacy/ZDR policy gate и отдельный egress contract;
- CI/deploy credentials, artifact integrity и production-only unsafe defaults.

Не полагайся на UI для ограничения доступа.

## Findings

Confirmed finding обязан содержать:

- severity: CRITICAL / HIGH / MEDIUM / LOW;
- affected asset и trust boundary;
- prerequisites и attacker capability;
- source -> checks -> sink;
- конкретный attack scenario;
- воспроизводимое evidence;
- impact без преувеличения;
- минимальную remediation;
- regression verification.

Если exploitability не подтверждена, помести пункт в `Unvalidated concerns`, а не в findings.

## Итог

Используй один из статусов отчёта:

- `NO_CONFIRMED_FINDINGS`;
- `CONFIRMED_FINDINGS`;
- `NEEDS_MANUAL_VALIDATION`.

Это результат аудита, а не lifecycle gate. Normal delivery определяется deterministic CI
и правилами `AGENTS.md`. Каждый PR отдельно проходит бесплатные CodeQL/dependency/Trivy checks;
semantic review через этот skill запускается только по фактическому security trigger или явному
запросу на full audit.

## Verification baseline

OWASP ASVS 5.0.0 используй как reference только для релевантных требований. Не заявляй ASVS
compliance без полного доказанного покрытия.

Для deterministic signal используй существующие project checks и отдельный GitHub Actions workflow
`Security Audit`. Scanner alert является candidate evidence, а не автоматически подтверждённой
уязвимостью.

Для privacy-sensitive flow подключай `$privacy-engineer`; для AI/provider boundary -
`$llm-engineer`; для deployment/CI boundary - `$platform-engineer`. Skill не расширяет task scope.
