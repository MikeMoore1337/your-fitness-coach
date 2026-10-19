# Make Feature: Issue #849 / V11-REC-01 Phase B/C

- Stage: Phase B.1 read-only storage/SFTP preparation recorded; production gates intentionally inactive.
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

## Phase B.1 follow-up — 2026-10-19

- Owner-selected target: `D:\YFC-Backups`; no production payload was written.
- Read-only Windows inventory: `D:` is NTFS, total 1,000,203,087,872 bytes, free 195,896,864,768 bytes; the target path does not exist.
- BitLocker and recovery-key custody remain `NOT_VERIFIED`: CIM/`Get-BitLockerVolume`, `manage-bde -status D:`, and `fsutil` checks were denied in the non-elevated session. No key material was read.
- Target ACL/structure was not created because the parent D: ACL is broader than the required backup boundary and the dedicated runner identity/elevated owner is not confirmed.
- Known OneDrive checks did not place the target under a known OneDrive root; no OneDrive process or target reparse point was observed. SMB-share inspection and Task Scheduler inspection were unavailable/denied, so third-party sync and share absence are not proven.
- Synthetic Windows pull self-test passed 28/28 in PowerShell 7 and 28/28 in Windows PowerShell 5.1. This is contract evidence only, not live SFTP or physical-encryption evidence.
- Decision remains `BLOCKED_OWNER_FACTS`; the next gate is an owner-approved elevated storage/identity check and a separately approved SFTP hardening plan.
