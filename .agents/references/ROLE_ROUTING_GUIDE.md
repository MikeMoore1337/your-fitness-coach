# Role routing guide v3

Canonical quality/QA severity, recheck limits, commit/finalization и lifecycle находятся в `codex-backlog/TASK_EXECUTION_LIFECYCLE.md`.

Этот файл отвечает только за выбор роли.

## Роли

| Роль | Когда использовать |
| --- | --- |
| `orchestrator` | Несколько реально независимых streams, сложная convergence/integration planning |
| `researcher` | Отдельная неизвестность, которую выгодно закрыть read-only |
| `product-lawyer` | Dedicated read-only legal-risk audit, legal register и owner decision package |
| `implementer` | Production implementation |
| `qa-verifier` | Фактическая risk-based behavioral verification |
| `integration-release` | Merge/integration/release convergence |

## Правила

- Обычная feature-task имеет одного primary writer - `implementer`.
- Не использовать `orchestrator` для локальной feature-task.
- Не создавать `researcher` для обычного чтения файлов implementer'ом.
- `product-lawyer` является primary role только для dedicated legal-risk task; обычная feature-task
  сохраняет свою primary role и при trigger подключает `$ru-legal-risk` условно.
- После owner decision legal remediation выполняется отдельной implementation task, а не ролью
  `product-lawyer` автоматически.
- `integration-release` не заменяет `release-manager`; роль задаёт ответственность, skill - профессиональный workflow.
- Не создавать отдельные роли `designer`, `motion-designer`, `ai-engineer`, `security-reviewer` и т.п. Их знания выражаются skills.
- Task metadata остаётся основным маршрутом для backlog task.
