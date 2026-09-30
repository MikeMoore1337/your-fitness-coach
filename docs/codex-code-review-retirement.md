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

## Repository-native Security Review

Внешний Codex Security Review остаётся выключен вместе с Codex Code Review. Вместо него каждый PR
автоматически проходит собственный repository-native Codex Security Review в `diff` mode через
официальный GitHub Action и YFC threat model. Review read-only, не создаёт отдельного reviewer-agent
и не вызывает `@codex security review`.

Validated `CRITICAL`/`HIGH` findings блокируют aggregate `checks`; `MEDIUM`/`LOW` и
unvalidated concerns advisory. Missing credential, action failure или malformed structured result
fail-closed. Dedicated `full` audit остаётся owner-requested. Deterministic security scanners
остаются отдельным источником evidence.

## Внешняя настройка

Изменения репозитория не меняют внешние Codex/GitHub settings и не создают secret, token или
автоматическое правило. Если внешняя настройка недоступна, фиксируется
`MANUAL_EXTERNAL_SETTING_REQUIRED`; это не возвращает review в repository lifecycle.
