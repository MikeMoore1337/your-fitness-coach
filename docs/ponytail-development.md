# Ponytail in YFC development

Ponytail is optional host-side Codex tooling used only to reduce unnecessary implementation
complexity. It is not part of the Your Fitness Coach runtime, dependency graph or source of truth.

YFC integration is compatible with Ponytail 4.10.0 behavior: its Codex SessionStart hook resolves
`PONYTAIL_DEFAULT_MODE` before its user config/default and accepts `off`, `lite`, `full` and
`ultra`.

## Responsibility split

- `AGENTS.md` - YFC governance, safety, lifecycle and the repository-owned fallback minimalism ladder.
- Agent Flow - deterministic role routing and per-task Ponytail mode selection.
- Graphify - optional code graph for architecture/dependency/impact navigation.
- Ponytail - optional implementation-minimalism rules injected by the Codex host when installed.

Ponytail never replaces YFC instructions and cannot expand or reduce task scope.

## Mode policy

Agent Flow selects:

| Task | Mode |
| --- | --- |
| no `implementer` pass | `off` |
| ordinary implementation | `full` |
| cross-cutting / architecture implementation | `lite` |
| security/deployment implementation | `lite` |
| automatic `ultra` | never |

A task may override inference explicitly:

```md
- **Ponytail:** off
```

or:

```md
- **Ponytail mode:** lite
```

Allowed values are `off`, `lite`, `full`, `ultra`. An invalid explicit value is a routing
error rather than a silent fallback.

## Runtime behavior

`scripts/run_task_delivery.py` passes the selected mode to the Codex worker as:

```text
PONYTAIL_DEFAULT_MODE=<mode>
```

If the Ponytail plugin is installed in that Codex environment, its existing SessionStart hook can
consume the variable. If it is not installed, the environment variable is inert and delivery
continues using the repository-owned minimalism ladder in `AGENTS.md`.

The controller deliberately does not detect, install, upgrade or pin the user's Codex plugin
installation. This keeps Cloud/local environments portable and avoids turning third-party tooling
availability into a delivery gate.

## What is intentionally disabled

YFC does not automatically run:

- `@ponytail-review`;
- Ponytail audit/debt/gain commands;
- an additional reviewer/subagent;
- Ponytail project hooks committed to this repository;
- plugin installation or updates from the task controller.

The existing implementer self-review and deterministic CI remain the quality path.

## Precedence

If Ponytail advice conflicts with the current task or YFC rules, use the normal repository
instruction precedence. In particular, minimalism never removes required validation, security,
accessibility, tests, migrations, observability or error handling.

`ultra` is explicit-only because aggressive YAGNI is useful for selected cleanup/prototype tasks
but is not a safe generic default for cross-cutting product delivery.
