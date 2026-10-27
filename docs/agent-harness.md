# Optional Agent Harness

`scripts/agent_harness.py` can validate small JSON eval manifests against existing pytest node IDs
and write derived reports under `.artifacts/`. It can also propose owner-reviewable learning
candidates without auto-promoting instructions.

The harness stores no transcripts, credentials, leases, queues or lifecycle state. It is not a
required CI intermediary and its failure cannot block a branch, PR, merge or deployment.
