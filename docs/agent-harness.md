# Optional Agent Harness

`scripts/agent_harness.py` can validate small JSON eval manifests against existing pytest node IDs
and write derived reports under `.artifacts/`. It can also propose owner-reviewable learning
candidates without auto-promoting instructions.

The harness stores no transcripts, credentials, leases, queues or lifecycle state. It is not a
required CI intermediary and its failure cannot block a branch, PR, merge or deployment.

The external upstream [ECC Codex plugin](development/ecc-external-codex.md) may be used in a separate, explicitly permitted **development-only** Codex Desktop session. It is not installed by this repository and must never become a second harness, a CI dependency, a runtime service, or a source of application state. ECC live activation is currently **NOT_VERIFIED**.
