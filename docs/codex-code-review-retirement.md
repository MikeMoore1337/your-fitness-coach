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

## Security Review после retirement

Внешний Codex Security Review остаётся выключен вместе с Codex Code Review. Автоматический LLM
review не используется. Каждый PR вместо этого проходит deterministic security jobs: CodeQL,
runtime dependency audit и Trivy filesystem scan. Они входят в aggregate `checks`, не требуют
`OPENAI_API_KEY` и не расходуют OpenAI API quota.

Repository-native semantic Security Review через `$security-engineer` сохраняется как
manual/conditional gate для фактических security-sensitive surfaces и как owner-requested `full`
audit. Scanner finding является candidate evidence, а не автоматически подтверждённой
эксплуатируемой уязвимостью.

## Внешняя настройка

Изменения репозитория не меняют внешние Codex/GitHub settings и не создают secret, token или
автоматическое правило. Если внешняя настройка недоступна, фиксируется
`MANUAL_EXTERNAL_SETTING_REQUIRED`; это не возвращает review в repository lifecycle.
