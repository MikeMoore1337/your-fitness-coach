# Repository-native Security Review

YFC может выполнять содержательный Security Review обычной Codex-сессией, без отдельного
`@codex security review`.

Канонические источники:

- `security/THREAT_MODEL.md`;
- `.agents/skills/security-engineer/SKILL.md`;
- `.agents/skills/security-engineer/references/SECURITY_REVIEW_PLAYBOOK.md`.

## Быстрый diff review

Используй для PR/task, где реально затронут security-sensitive surface:

```text
Проведи repository-native Security Review в режиме diff.
Не вызывай внешний @codex security review.
Прочитай AGENTS.md, security/THREAT_MODEL.md,
.agents/skills/security-engineer/SKILL.md и его SECURITY_REVIEW_PLAYBOOK.md.
Base = merge-base(origin/master, HEAD), head = HEAD.
Начни с diff, проследи только затронутые trust boundaries и data flows.
Каждый finding сначала валидируй тестом/repro/code-path evidence.
Неподтверждённое оставь в Unvalidated concerns.
Ничего не исправляй, пока сначала не покажешь findings и evidence.
```

Если review выполняется внутри уже авторизованной implementation task, последнюю строку можно заменить
на: `Подтверждённые findings в scope task исправляй минимально и добавляй regression test.`

## Полный review

```text
Проведи repository-native Security Review в режиме full текущего YFC.
Не вызывай внешний @codex security review и не создавай reviewer subagent.
Используй security/THREAT_MODEL.md и SECURITY_REVIEW_PLAYBOOK.md.
Последовательно проверь identity/session, authz/isolation, inputs/uploads/URLs,
data/privacy/logging, AI/provider boundaries, secrets/dependencies и CI/deploy.
Не публикуй finding без validation evidence.
Верни единый отчёт с Confirmed findings, Unvalidated concerns,
Deterministic checks, Residual risk и итоговым audit status.
```

## Deterministic Security Audit

GitHub Actions workflow `Security Audit` запускается:

- вручную через Actions -> Security Audit -> Run workflow;
- по недельному расписанию.

Он не подключён к normal PR lane. Workflow выполняет:

- CodeQL для Python и JavaScript/TypeScript;
- существующий YFC dependency audit через `scripts/ci_contract.py`;
- Trivy filesystem scan для HIGH/CRITICAL dependency/configuration findings.

Scanner alert - это сигнал для проверки, а не автоматически подтверждённый exploit.

## Локальные проверки

По применимости:

```bash
python scripts/ci_contract.py run-group dependency-audit
python scripts/ci_contract.py run-group policy
python scripts/skill_safety.py scan-all
```

Не устанавливай новый security tool в runtime проекта только ради разового review. Для Docker scope
используй существующий container CI contract.

## Evidence hygiene

Локальные repro, логи и отчёты складывай в task-owned `.artifacts/` по правилам `AGENTS.md`.
Не коммить токены, реальные персональные данные, raw production dumps и exploit payload, если
безопасного минимального evidence достаточно.

Repository-native Security Review не заменяет deterministic CI и не становится обязательным
LLM-verdict для обычной доставки.
