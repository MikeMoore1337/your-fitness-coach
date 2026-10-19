# Request contract

Implement Phase B of Issue #848: connect the existing fail-closed PostgreSQL
connection-budget model to trusted runtime sources without activating the production
deployment gate.

Required outcomes:

1. Read-only PostgreSQL collector: version, max/reserved slots, current occupancy and
   YFC/non-YFC/unattributed attribution; no superuser requirement, writes, dumps,
   secrets or unbounded output.
2. Effective topology from rendered Compose/runtime: backend and worker replicas,
   base and blue/green slots, pools and overrides, setup/seed, Alembic, backup,
   worker handoff, rollback, single-slot, pooler and unexpected consumers.
3. Provenance boundary: standalone JSON cannot set trust; PostgreSQL and topology
   observations share environment, host, revisions and freshness context; stale,
   future, partial, mixed or contradictory evidence fails closed.
4. Existing budget math remains authoritative, including observed non-YFC sessions,
   no double-counting observed YFC sessions, reserved capacity and explicit headroom.
5. Gate integration is prepared and stage order is tested, but `deploy.yml` and
   `zero_downtime_deploy.py` remain unwired until separate owner approval.
6. Deterministic tests, release-scope evidence and technical documentation.

Acceptance boundary:

- Production activation is `BLOCKED` until live read-only evidence, owner-approved
  headroom, authorized dry run and release approval exist.
- Issue #848 stays open; work is delivered as a Draft PR with exact-head checks.
