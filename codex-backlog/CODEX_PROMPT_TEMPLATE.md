# Codex prompt template

```text
Issue: <GitHub Issue URL or number>
Goal: <one-sentence outcome>
Scope: <included files/behavior>
Out of scope: <explicit exclusions>
Risk gates: <only real human/external/destructive gates, or none>

Use standard GitHub Flow: inspect current source, branch from origin/master, implement, run
targeted checks, open/update the PR to master, wait for required Checks, and stop after the
requested merge/deploy outcome. Git/GitHub/Actions are the source of truth. Do not create local
controller state, leases, queues, fingerprints, mandatory task mirrors or cleanup gates.
```
