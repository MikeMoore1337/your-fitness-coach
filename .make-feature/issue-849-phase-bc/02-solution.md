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
