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


Automatic Codex Code Review не включается. После GREEN exact-head `checks` controller использует
один bounded review round; второй разрешён только после blocking P0/P1 и изменившегося head SHA.
Clean review не повторяется, третий request запрещён. Отдельный reviewer/subagent не создаётся.
Release требует targeted tests, применимых static analysis/integration/e2e, exact-head CI и
aggregate `checks` GREEN, CLEAN review, отсутствия unresolved BLOCKER/HIGH, mergeable PR и
resolution существующих threads.
Явные task-specific human/external/security/legal/destructive gates сохраняются.
