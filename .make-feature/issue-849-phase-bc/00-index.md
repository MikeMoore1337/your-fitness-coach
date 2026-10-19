# Make Feature: Issue #849 / V11-REC-01 Phase B/C

- Stage: evidence and decision package complete; production gates intentionally inactive.
- Depth: deep — the remaining blockers are real infrastructure, privacy, encryption and
  clean-host recovery facts, not missing application code.
- Base: origin/master revision 499b189d641b66077bdec431b39c477c7b2bc722.
- Phase A source: merged PR #1120, exact head 8929463f9b1539c25cb58a35672a8f9c548eb279.
- Issue: #849, still open; dependent observability and final-acceptance work remains owner-gated.
- Current decision: record the read-only live inventory, update the runbook and stop at
  BLOCKED_OWNER_FACTS. Do not create a second lifecycle state, transfer production payload,
  mutate VPS/Windows configuration, restore, merge, deploy or close the Issue.

## Acceptance gates

- A1: Phase A merge and exact-head CI evidence are linked to the current master baseline.
- A2: VPS on-host dump, database, scheduler, publication metadata and SFTP posture are
  recorded without exposing production host identity, credentials or payload.
- A3: Windows client capability, disk space, target/task inventory and encryption evidence
  are recorded with access-denied limits preserved as NOT_VERIFIED.
- A4: Real independent transfer, encryption/key recovery and clean-host restore are never
  inferred from synthetic tests or pg_restore --list.
- A5: The operational document and sanitized local receipt identify the owner facts required
  before Phase B can continue.

## Open gates

- Independent off-host object and real SFTP pull: NOT_PROVEN / NOT_VERIFIED.
- Physical encryption at rest and recovery-key drill: NOT_VERIFIED.
- Dedicated hardened read-only SFTP identity and production SSH authorization: BLOCKED_OWNER_FACTS.
- Windows Task Scheduler target and successful scheduled pull: ABSENT / NOT_VERIFIED.
- Clean-host restore, integrity smoke and measured RPO/RTO: NOT_VERIFIED.
- Merge, deployment, production restore and Issue closure: not authorized.

