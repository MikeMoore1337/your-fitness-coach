# Короткий промпт Codex

Для любой current/pending task этого backlog достаточно:

```text
Выполни `codex-backlog/tasks/<имя-task>.md`.

Соблюдай `AGENTS.md`, `codex-backlog/GLOBAL_RULES.md`
и полный task lifecycle.

Все предыдущие tasks считаются выполненными.
Не переходи к следующей task.
```

`Полный task lifecycle` определён в `codex-backlog/TASK_EXECUTION_LIFECYCLE.md`. Task сама задаёт минимальные роли и skills.

Текущая task:

```text
Выполни `codex-backlog/tasks/104-telegram-news-images-moderation-publishing.md`.

Соблюдай `AGENTS.md`, `codex-backlog/GLOBAL_RULES.md`
и полный task lifecycle.

Все предыдущие tasks считаются выполненными.
Не переходи к следующей task.
```


Codex Code Review полностью отключён в delivery lifecycle: controller не публикует review-комментарии,
не вызывает review-команды и не ждёт LLM-вердикта. Отдельный reviewer/subagent не создаётся.
Release требует targeted tests, применимых static analysis/integration/e2e, exact-head CI и
aggregate `checks` GREEN, отсутствия unresolved BLOCKER/HIGH, mergeable PR и resolution
существующих threads.
Явные task-specific human/external/security/legal/destructive gates сохраняются. Automatic Security
Review для обычного PR выключен и не сцепляется с Code Review; это отдельный
manual/conditional gate, запрашивай его только при фактическом security trigger. Deterministic
security scanners остаются в CI.
