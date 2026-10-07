# Role routing guide

Roles are optional responsibility hints for a Codex session. They do not own branches,
pull requests, releases, queues, leases or persistent lifecycle state.

## Roles

| Role | Use when |
| --- | --- |
| `orchestrator` | Several genuinely independent read-only planning streams need coordination |
| `researcher` | A bounded unknown is best answered before implementation |
| `product-lawyer` | Dedicated read-only legal-risk audit and owner decision package |
| `implementer` | Production implementation |
| `qa-verifier` | Risk-based behavioral verification |

Normal integration is the native GitHub path: branch, PR, Checks, merge and Actions deployment.
Use `scripts/agent_flow.py` only as optional local routing assistance; its failure must not block
GitHub work.

Do not create a role per skill or a release-owner substitute. Use the smallest role/skill set that
matches the actual change.
