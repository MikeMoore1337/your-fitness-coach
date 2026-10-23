# Solution record

## Trusted flow

`trusted_runtime_collector.py` runs bounded host commands against rendered Compose,
`ps --all`, exact running container IDs, OCI revision labels and the live Caddy Admin
API config. It compares allowlisted runtime environment values with rendered Compose,
checks every running application image against the active release SHA, resolves the
active backend from verified state plus live gateway config, then executes a child
PostgreSQL collector inside that exact container. The child uses the existing locked
`psycopg` dependency and read-only connection options. Only allowlisted numeric fields
and fixed metadata leave the child/host boundary.

Configured replicas are never used as the only runtime count: all-slots sums the larger
of configured and observed running instances per known service, while candidate overlap
uses the largest effective candidate slot. A runtime marker/pool mismatch or inconsistent
instances fail closed instead of silently lowering the budget.

`connection_budget_preflight.py` now has a private in-process trust token. The mapping
parser cannot populate it, and a forged `trusted=true`, `synthetic=false`, source or
environment cannot authorize production evaluation. The collector verifies exact host
and revision context, a trusted 300-second freshness policy and complete attribution
before marking the model.

## Runtime attribution

Backend, worker, setup and Alembic use fixed PostgreSQL `application_name` values.
The collector uses its own fixed name but is counted as non-YFC demand, so its
read-only session cannot create a false PASS. Unknown or empty
`pg_stat_activity.application_name` is counted conservatively as non-YFC and yields
`UNKNOWN`, never YFC. The collector requires `pg_read_all_stats` visibility and
rejects superuser execution. Multiple poolers or runtime/rendered pooler drift are
unknown/blocked rather than modeled from the first pooler.

Alembic uses the fixed `yfc-migration` marker independently of application settings;
SQLite keeps empty `connect_args` so test mode remains unchanged. The marker is a
client declaration, not cryptographic identity; live attribution remains `NOT_PROVEN`
until an authorized PostgreSQL snapshot confirms it.

## Deployment boundary

The trusted gate runs before existing backup/migration/candidate stages, with matching
predecessors for rollback, legacy bootstrap and single-slot/idempotent paths. The
production wrapper performs an early read-only capacity check before configuration
mutation; owner-approved live verification and release activation remain separate.
Compose, backend engine setup and Dockerfile changes are intentionally
deployment-affecting and must remain visible to `deployment_scope.py`.
