# Solution — bounded Phase B/C evidence package

## Requirements

Issue #849 asks for an independent off-host backup and a clean-host recovery proof. The
repository already contains the Phase A contract and synthetic implementation. The smallest
safe continuation is therefore a read-only live inventory plus an evidence/runbook update,
not new transfer code or production wiring.

The evidence must keep these claims separate:

1. a local PostgreSQL dump can be listed;
2. an independent off-host copy exists and can be pulled;
3. the Windows copy is encrypted and its recovery key is usable;
4. the application can be restored on an isolated clean host;
5. measured RPO/RTO meets the owner's target.

## Evidence and choice

Verified on the current production-shaped environment:

- the latest on-host dump is present and pg_restore --list succeeds in a read-only,
  network-isolated container;
- the database is PostgreSQL 16.0.15, not in recovery, with Alembic head
  0130_workout_rest_sessions;
- no current index/manifest publication evidence or YFC backup scheduler was found;
- no separate hardened read-only SFTP boundary was verified, and the effective SSH posture
  still permits password authentication/forwarding globally;
- the Windows client has PowerShell/OpenSSH and disk space, but no target directory or task;
- CIM and manage-bde access denial prevents a BitLocker conclusion;
- the Phase A self-tests and focused Python tests pass, but they are synthetic/local.

Chosen path: update
docs/operations/v11-rec-01-off-host-backup-recovery.md with the factual inventory and a
fail-closed verdict, and save a sanitized receipt under ignored .artifacts evidence. The
verdict is BLOCKED_OWNER_FACTS because the independent transfer and required owner facts do
not exist. No application source, deployment workflow, SSH configuration or scheduled task is
changed.

## Safety boundaries

- Do not read, copy, publish or hash secrets from the backup directory beyond the already
  captured dump digest; the secrets-likely .env was not read.
- Do not transfer production payload to Windows.
- Do not create accounts, keys, chroots, ForceCommand rules, timers or tasks.
- Do not run restore, migrations, DNS changes, traffic cutover or provider calls.
- Do not claim BitLocker absent when the OS checks were access-denied.
- Do not infer merge, deployment or Issue closure from green Phase A CI.

## Phase B.1 update — bounded plan, not applied

The owner-selected `D:\YFC-Backups` path is retained. The minimum safe preparation is:

1. Confirm an elevated owner/admin session and a dedicated non-production Windows runner identity. Create the empty target only after rechecking that the path is absent; do not copy a dump.
2. Prefer a dedicated BitLocker-encrypted VHDX/container mounted for this root, with recovery-key custody documented outside GitHub and a recovery test. Do not encrypt the whole D: volume. If BitLocker is unavailable, use a separately approved file/container encryption method with the same recovery-key requirements.
3. Remove inherited broad access from the target; retain full control for SYSTEM and Administrators, grant Modify only to the dedicated runner identity, and grant no access to Authenticated Users/Users. Verify owner, inheritance, reparse points, SMB shares and known sync roots after creation.
4. Keep the SFTP export root separate from the previously observed backup root that contained a secrets-likely `.env`. The proposed account is `yfc-backup-readonly`: public-key-only, no shell/TTY/forwarding/write, `internal-sftp` behind a chroot, a dedicated pinned `known_hosts`, and an allowlist limited to `index.json`, dump archives and their manifests. Apply only after owner approval, `sshd -t`, an existing-admin-session check and a reversible reload/rollback plan.
5. Use the existing Task Scheduler template only after the runner identity can read the key and config non-interactively. Preserve `IgnoreNew`, `StartWhenAvailable`, `RunOnlyIfNetworkAvailable`, bounded execution time, sanitized logs and exit codes; do not register the task in this phase.

Owner decision (2026-10-19): one archive per day and seven-day retention are **approved**. The earlier 30-day proposal is superseded; do not automatically delete the sole last validated copy on failure, and surface a stale-retention warning. The owner rejected VHDX/encrypted containers in favor of a simple `D:\YFC-Backups` directory. Admin evidence confirms `D:` BitLocker protection Off / fully decrypted; this does not satisfy physical encryption-at-rest acceptance and leaves a separate privacy/security decision before production PII transfer. Windows hourly polling, RPO <=24h and initial RTO 8h remain proposals rather than approved/measured targets. The clean-host environment should be a disposable non-public Linux VM/host, independent of both the production VPS and Windows storage, with matching PostgreSQL major/revision and external egress disabled.
