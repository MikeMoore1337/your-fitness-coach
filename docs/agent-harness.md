# Agent Harness v11

YFC does not install or vendor `everything-claude-code`. The upstream repository is used only as a source of ideas that fit the existing Codex workflow.

The harness keeps the current YFC lifecycle authoritative:

- `AGENTS.md`, task contracts and `TASK_EXECUTION_LIFECYCLE.md` remain the instruction source of truth;
- `scripts/task_session.py` remains the task/controller source of truth;
- `scripts/artifact_manager.py` remains the only allocation path for generated harness artifacts;
- deterministic tests and CI remain the quality gate;
- no LLM reviewer, LLM-as-judge gate, paid API or automatic self-modification is introduced.

## Upstream concept audit

| Everything Claude Code concept | YFC decision | Reason |
| --- | --- | --- |
| agents | ALREADY_COVERED | YFC already has explicit lifecycle roles under `.agents/roles/`. |
| skills | ALREADY_COVERED | YFC already has focused project skills and routing rules. |
| rules | ALREADY_COVERED | `AGENTS.md`, `GLOBAL_RULES.md` and task contracts are stricter and project-specific. |
| commands | REJECT | Generic slash-command duplication would create a second control surface. |
| contexts | ALREADY_COVERED | Role/task routing already provides bounded implementation, research and review context. |
| hooks | ADAPT | Only the lifecycle idea is reused. Claude-specific hook configuration is not copied. |
| memory-persistence | ADAPT | Implemented as a compact derived checkpoint from `task_session.py recover`; it is not durable truth. |
| continuous-learning | ADAPT | Implemented only as owner-reviewable learning candidates under task deliverables. There is no auto-promotion. |
| verification-loop | ALREADY_COVERED | YFC targeted verification, exact-head CI and deterministic security checks are stronger. |
| eval-harness | ADAPT | Versioned eval manifests reuse existing pytest controller regressions. |
| strategic-compact | REJECT | Codex compaction plus canonical task/controller state is sufficient; no session transcript persistence is needed. |
| MCP configs | REJECT | External connectors remain task-specific and are not copied globally from another project. |

## Deterministic agent evals

Definitions live in `.agents/evals/*.json`. They do not contain executable shell fragments. Each eval maps a capability/regression contract to one or more existing `pytest` node IDs.

Validate manifests:

```bash
python scripts/agent_harness.py eval validate
```

Run the full harness:

```bash
python scripts/agent_harness.py eval run --task-id 737
```

Run one eval:

```bash
python scripts/agent_harness.py eval run \
  --suite lifecycle \
  --eval-id merged-no-deploy-recovery \
  --task-id 737
```

When `--task-id` is supplied, the report is allocated through `artifact_manager.py` under:

```text
.artifacts/tasks/<TASK_ID>/evidence/agent-evals/
```

The harness intentionally does not duplicate the controller logic. The grader is the existing deterministic regression test itself.

## Derived task checkpoint

A checkpoint is a compact projection of the read-only controller recovery snapshot:

```bash
python scripts/agent_harness.py checkpoint 737
```

Output is stored under:

```text
.artifacts/tasks/737/temporary/agent-harness/checkpoint.json
```

Properties:

- `source_of_truth=false`;
- `mutation_performed=false`;
- only bounded lifecycle/anchor/delivery fields are retained;
- worktree details, transcripts and arbitrary controller internals are not copied;
- the checkpoint is reproducible and may be deleted after terminal success.

If checkpoint state conflicts with Git, GitHub or controller state, the checkpoint loses.

## Controlled learning candidates

The harness can record a reusable pattern for owner review:

```bash
python scripts/agent_harness.py learn propose 737 \
  --pattern "Recovery must remain read only and fail closed." \
  --evidence "Task 729" \
  --evidence "Task 737" \
  --why-reusable "The invariant applies to repeated controller recovery paths." \
  --destination "AGENTS.md" \
  --conflict-analysis "Compatible with the existing recovery policy; update existing text." \
  --risk low \
  --action UPDATE_EXISTING
```

Candidates are stored under:

```text
.artifacts/tasks/<TASK_ID>/deliverables/agent-learning/
```

They contain:

- proposed reusable pattern;
- evidence references;
- reuse rationale;
- destination suggestion;
- conflict analysis;
- risk;
- proposed action;
- overlap hints against current YFC instructions;
- an explicit `auto_promotion_supported=false` marker.

The fingerprint is derived from normalized pattern text plus the destination, so repeated proposals are deterministic and deduplicated.

There is deliberately no `learn promote` command. Updating `AGENTS.md`, roles, skills or documentation remains a normal reviewed repository change. Secret-like content is rejected before candidate persistence.

## Scope boundary

The harness must not become:

- a second task controller;
- a second artifact store;
- an automatic instruction mutator;
- a session transcript archive;
- a model-based mandatory reviewer;
- a reason to run duplicate full suites in CI.

Add new evals only when they protect a concrete recurring lifecycle behavior that already has a deterministic test or when a new controller behavior receives such a regression test.
