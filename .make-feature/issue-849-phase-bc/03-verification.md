# Verification — Phase B/C live inventory and fail-closed decision

| Criterion | Action | Result | Evidence |
|---|---|---|---|
| Phase A baseline | Re-read Issue #849/PR #1120 and exact-head GitHub evidence | PASS | PR #1120 merged at 499b189d; CI run 39218187131 aggregate checks=success; deploy_required=false |
| VPS dump presence | Read-only backup directory inventory | PASS for on-host copy | Latest dump is 50,275,155 bytes; full digest is kept only in the ignored local receipt |
| Dump readability | Run pg_restore --list in a read-only, network-isolated container | PASS | Exit code 0; no restore performed |
| Publication metadata | Check current backup directory for index/manifest | NOT_PROVEN | No current index.json or manifest sidecar found |
| Scheduler | Inspect systemd/cron and Windows Scheduled Tasks | ABSENT / NOT_VERIFIED | No YFC backup timer or target Windows task found |
| SFTP boundary | Inspect account, effective sshd posture and directory permissions | BLOCKED_OWNER_FACTS / FAILED | No verified dedicated hardened read-only endpoint; no changes made |
| Windows encryption | Read-only CIM/manage-bde checks | NOT_VERIFIED | Access denied; no BitLocker conclusion |
| Real independent transfer | Attempt production pull | NOT_AUTHORIZED / NOT_PERFORMED | Privacy, encryption and identity gates remain open |
| Clean-host restore | Execute Phase C drill | NOT_AUTHORIZED / NOT_PERFORMED | No clean host or approved non-production recovery inputs |
| Synthetic PowerShell contract | Run scripts/windows_backup_pull_selftest.ps1 in PowerShell 7 and Windows PowerShell | PASS | 28/28 scenarios in each shell |
| Focused Python contract | Run backup manifest, DB maintenance, CI contract and deployment scope tests | PASS | 78 passed |
| Final decision | Apply Issue #849 phase gates | BLOCKED_OWNER_FACTS | Independent off-host copy, hardened SFTP, encryption/key recovery and owner targets are missing |

The production inventory was read-only. No production payload was downloaded, no configuration was
mutated, no scheduled task was registered, no restore or migration ran, and no merge/deploy/Issue
close was performed.

## Phase B.1 verification update — 2026-10-19

| Criterion | Result | Evidence boundary |
|---|---|---|
| D: volume | PASS (read-only) | NTFS; total 1,000,203,087,872 bytes; free 195,896,864,768 bytes |
| `D:\YFC-Backups` | NOT_CREATED | Path absent; no existing content changed and no payload written |
| ACL/owner preparation | BLOCKED_OWNER_FACTS | Target ACL does not exist; parent ACL is broad; current session is not elevated and runner identity is not selected |
| BitLocker / recovery key | NOT_VERIFIED | CIM/`Get-BitLockerVolume`, `manage-bde` and `fsutil` were denied; key material was not read |
| Sync/share boundary | PARTIAL / NOT_VERIFIED | Not under a known OneDrive root; no OneDrive process or target reparse point observed; SMB query denied and this does not cover every sync provider |
| Task Scheduler | NOT_VERIFIED | `schtasks /query` returned “The network address is invalid”; Schedule service was not available; no task was registered |
| Synthetic pull contract | PASS | 28/28 in PowerShell 7 and 28/28 in Windows PowerShell 5.1, including checksum, host-key/auth/network failures, corruption, low disk, atomic promotion, prior-copy preservation and concurrency |
| Live SFTP authentication | NOT_VERIFIED | No authorized protected endpoint was used; the self-test uses an isolated fake SFTP adapter |
| Final decision | BLOCKED_OWNER_FACTS | Storage encryption/key custody, elevated ACL identity, hardened endpoint authorization and scheduler access remain open |

No production dump, production SSH key, VPS configuration, scheduled task, restore or merge/deploy operation was performed.
