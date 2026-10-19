# Solution record

## Trusted flow

`trusted_runtime_collector.py` runs bounded host commands against rendered Compose,
`ps --all` and OCI revision labels, then executes a child PostgreSQL collector inside
the active backend image. The child uses the existing locked `psycopg` dependency and
read-only connection options. Only allowlisted numeric fields and fixed metadata leave
the child/host boundary.

`connection_budget_preflight.py` now has a private in-process trust token. The mapping
parser cannot populate it, and a forged `trusted=true`, `synthetic=false`, source or
environment cannot authorize production evaluation. The collector verifies exact host
and revision context, a trusted 300-second freshness policy and complete attribution
before marking the model.

## Runtime attribution

Backend, worker, setup, Alembic and the collector use fixed PostgreSQL
`application_name` values. Unknown or empty `pg_stat_activity.application_name` is
counted conservatively as non-YFC and yields `UNKNOWN`, never YFC. The collector
requires `pg_read_all_stats` visibility and rejects superuser execution.

## Deployment boundary

The future insertion point is immediately before existing backup/migration/candidate
stages, with a matching predecessor for rollback and single-slot paths. This change
does not modify the deployment workflow or activate the gate. Compose, backend engine
setup and Dockerfile changes are intentionally deployment-affecting and must remain
visible to `deployment_scope.py`.
