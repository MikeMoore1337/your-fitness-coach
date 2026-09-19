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
выбранные роли, решение по Graphify, `agent_budget` и execution policy. Полный текст приватной task
и scope из GitHub Issue в trace не копируются.

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

## Ponytail

Agent Flow also records a bounded Ponytail mode for the task. This does not install or require the
plugin. The delivery controller exports the selected mode through `PONYTAIL_DEFAULT_MODE`; a host
with Ponytail installed can consume it, while a host without the plugin uses the equivalent compact
YFC minimalism ladder from `AGENTS.md`.

Ponytail is never used to add a review loop. See `docs/ponytail-development.md`.

## Agent budget и live worker guard

Каждый plan содержит `agent_budget`.

- ordinary implementation: до 160 completed tool actions;
- research/cross-cutting/architecture/security/deployment: до 240;
- safe read-only parallelism: максимум 2 subagents одновременно и 10 collab tool calls;
- если routing не разрешил read-only parallelism, subagent/collab budget равен нулю;
- одинаковая ошибка одного action 4 раза без progress блокируется;
- одинаковый action 8 раз без progress блокируется;
- короткий 2-3 step cycle, повторённый 4 раза без progress, блокируется.

Progress для loop history - успешный `file_change`. Guard читает только структурированный
`codex exec --json` stream, а в evidence пишет counters/reason codes и SHA-256 signatures, не raw
prompt/command/tool args/results.

Отчёт успешной task сохраняется под task-scoped delivery evidence. Guard не добавляет LLM-pass и
не является reviewer.

## External skill safety

Layer 1: перед worker launch controller запускает `scripts/skill_safety.py scan-all`.

- scan полностью offline/deterministic;
- `CRITICAL` блокирует запуск;
- `WARNING` сохраняется как evidence и не блокирует;
- external/vendored skill должен иметь `SOURCE.json` с immutable commit и license provenance;
- тот же lightweight scan подключён в pre-commit/CI.

Layer 2: при изменении `.agents/skills/**` CI routing добавляет
`external-skill-security`. Эта группа запускает pinned NVIDIA SkillSpector через
`scripts/skillspector_guard.py` в static-only режиме, без LLM. Обычные product tasks без skill
changes этот инструмент не устанавливают и не запускают.

## Execution model

Выбранные role-passes по умолчанию выполняются последовательно одним worker. Если текущий Codex host
уже предоставляет safe collab/subagent mechanism и plan разрешает read-only parallelism, worker может
использовать его только в пределах `agent_budget`. Agent Flow не устанавливает agent framework и
никогда не разрешает параллельных production writers.
