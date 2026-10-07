# Artifact lifecycle

`.artifacts/` is ignored derived storage for logs, screenshots, traces, reports, temporary data,
deployment evidence and protected operational backups. It is never task, release or lifecycle
authority.

Use the canonical layout:

- `worktrees/` — local convenience only;
- `tasks/<LABEL>/{temporary,evidence,deliverables,logs}/` — explicitly requested local evidence;
- `runtime/{cache,tmp,tests}/` — reproducible test/runtime data;
- `shared/` — reusable local assets;
- `operations/{backups,deployments,recovery}/` — protected operational data.

`scripts/artifact_manager.py` performs path-safe, bounded inventory and cleanup. Cleanup is
best-effort: a stale worktree, local branch, missing optional metadata or cleanup failure may emit
a warning but cannot change a successful PR, merge or deployment into a failure. Dirty worktrees,
unique commits, backups and deployment evidence are preserved.
