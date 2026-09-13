# Codex Code Review: retirement from delivery lifecycle

Файл сохраняет историческое имя для durable-ссылок, но действующий контракт полностью исключает
Codex Code Review из автоматического delivery lifecycle. Controller не хранит и не читает review
state, не публикует `@codex review` или `@codex security review`, не вызывает review-команды и не
ждёт LLM-вердикта. Исторические комментарии в PR игнорируются как lifecycle gate.

## Канонический quality gate

```text
implementation
→ targeted verification
→ final deterministic verification
→ один bounded local self-review implementer
→ commit/push
→ PR в master
→ exact-head required CI GREEN
→ merge exact PR head
→ post-merge cleanup
→ product-task deploy/production closeout, если требуется task contract
```

После GREEN exact-head `checks` merge принимается по deterministic CI, current-base/provenance,
mergeability, branch/ruleset policy и resolved threads. Отдельного Codex semantic gate больше нет;
round state, request/validation commands и comment parser не являются частью executable controller.
Параллельные implementation worktrees сохраняются, а refresh, PR/CI, merge, deploy и closeout
остаются в одной serial delivery lane.

Единственное исключение — прямое указание владельца в отдельном сообщении для конкретного PR. Такое
действие не запускается controller и не меняет normal lifecycle.

## Отдельный Security Review

Security Review остаётся manual/conditional gate только для фактических security-sensitive surfaces:
auth/authz, secrets, untrusted network, uploads/parsers, user-controlled URLs, sensitive data,
payments, admin actions, cryptography/headers, webhook verification, privilege escalation,
dependency-security task или dedicated security audit. Он не сцепляется автоматически с обычным PR,
а deterministic security scanners остаются в CI. Отсутствие Security Review не блокирует ordinary
task без security trigger.

## Внешняя настройка

Изменения репозитория не меняют внешние Codex/GitHub settings и не создают secret, token или
автоматическое правило. Если внешняя настройка недоступна, фиксируется
`MANUAL_EXTERNAL_SETTING_REQUIRED`; это не возвращает review в repository lifecycle.
