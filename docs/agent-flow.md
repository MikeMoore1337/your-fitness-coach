# Agent Flow v1

Agent Flow v1 добавляет deterministic-маршрутизацию ролей поверх существующего YFC controller.
Новый agent framework не добавляется, а обычная модель delivery остаётся одно-worker.

## Принципы

- По умолчанию используется один Codex worker.
- `implementer` - единственный production writer внутри обычного task worktree.
- Явные роли, объявленные в task, имеют приоритет над inference.
- Если явного role contract нет, router может консервативно выбрать `researcher`,
  `orchestrator` или `qa-verifier` по типу задачи и затронутым поверхностям.
- `integration-release` остаётся controller-managed и не запускается как второй production writer.
- Automatic `reviewer`, `security-reviewer` и `adversarial-auditor` запрещены в normal lifecycle.
- Параллельные writers внутри одной task запрещены. Независимые tasks по-прежнему могут
  разрабатываться в отдельных worktree по существующему controller contract.

## Routing trace

Перед запуском delivery worker `scripts/run_task_delivery.py` строит routing plan через
`scripts/agent_flow.py` и сохраняет его в:

```text
.artifacts/tasks/<TASK_ID>/evidence/agent-flow/<delivery-id>.json
```

Trace содержит только ограниченные routing-данные: fingerprint task, обнаруженные поверхности,
выбранные роли, решение по Graphify и execution policy. Полный текст приватной task и scope из
GitHub Issue в trace не копируются.

## Graphify

Для нетривиальной cross-surface или architecture-задачи plan устанавливает
`graphify.bootstrap_required=true`. Worker перед широким architecture inspection запускает:

```bash
python scripts/graphify_yfc.py bootstrap
```

Graphify остаётся derived navigation data. Источником истины остаются текущие source, tests,
migrations, Git history и active documentation.

Если Graphify bootstrap не работает только из-за локального tooling/network, это само по себе не
блокирует task, когда безопасно можно перейти к прямому чтению исходников.

## Execution model

Выбранные role-passes по умолчанию выполняются последовательно одним worker. Будущая среда может
использовать уже поддерживаемый read-only subagent mechanism, но Agent Flow v1 его не устанавливает,
не требует и никогда не запускает параллельных production writers.
