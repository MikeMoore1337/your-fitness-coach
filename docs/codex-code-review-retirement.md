# Постоянная политика: без Codex Code Review

Это owner-level решение для всего репозитория Your Fitness Coach. Отдельный Codex Code Review
не является частью development, release или merge lifecycle и не запускается вручную или
автоматически.

В active process запрещены вызов `@codex review`, `chatgpt-codex-connector`, mandatory/fresh
review, reviewed-SHA gate, connector verdict, ожидание review rate limit, usage-reset credit
ради review, waiver отсутствующего review и отдельный Codex reviewer/subagent только для
проверки diff. Исторические комментарии закрытых PR/Issue не изменяются.

## Канонический quality gate

Обычная task проходит:

```text
implementation
→ targeted tests
→ implementer self-review
→ lint/typecheck/static checks
→ commit/push
→ PR в master
→ exact-head CI
→ required checks
→ resolution существующих blocking threads
→ merge
→ deploy
→ production smoke/closeout
```

Профильные QA, security, legal, human, external и destructive gates остаются только там, где
их требует конкретная task. `master` остаётся PR-only; exact-head CI, aggregate `checks`, current
base, non-fast-forward protection, thread resolution и production closeout не ослабляются.

## Внешняя настройка

Automatic Code Review в Codex Cloud/GitHub integration не управляется файлами репозитория.
Владелец должен открыть настройки Codex Cloud для GitHub integration, выбрать этот repository и
выключить `Automatic Code Review`, если функция включена. Этот ручной шаг не является частью
repository lifecycle и не заменяется новым review для проверки данной task.
